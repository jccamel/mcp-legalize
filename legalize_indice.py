#!/usr/bin/env python3
"""
`legalize_indice.py`
====================
Única fuente de verdad sobre el índice de un corpus: una base de datos SQLite
por corpus, `index_<repo>.db` (spec 002, ADR 0009).

Antes el índice era un JSON cargado entero en memoria más unos postings con
formato propio. Casi todos los defectos corregidos desde el 2026-10-16 vinieron
de esa infraestructura escrita a mano: deserialización insegura, postings que se
perdían en una pasada incremental, generación y orden de escritura, un validador
que copiaba el patrón del tokenizador. Medido sobre el corpus español, la base de
datos responde con 27 MB residentes frente a 363 y en menos de un milisegundo.

Lo escribe el indexador, y lo leen el servidor y `check_updates.py`. Ninguno de
los tres conoce el esquema: pasan por aquí.

- **Escribir.** `Escritor` trabaja sobre un temporal del mismo directorio —una
  copia del índice vigente en las pasadas incrementales— y lo sustituye entero
  con `os.replace` al confirmar. Una pasada interrumpida deja el índice
  anterior intacto, sin generaciones ni orden de escritura que cuidar.
- **Abrir.** La base de datos es entrada no confiable, igual que lo era el JSON
  (principio II). `abrir` la abre en solo lectura, con el modo defensivo de
  SQLite, `trusted_schema=OFF` y `query_only`, y compara su esquema con el
  canónico antes de hacerle una sola consulta. Cualquier disparador, vista o
  tabla de más, y cualquier SQL distinto en una tabla propia, la rechaza.

No importa `mcp_legalize`.
"""

import json
import os
import sqlite3
import tempfile
import urllib.parse
from pathlib import Path

import legalize_articulos
import legalize_normalizacion

FORMATO = "1"

# El esquema canónico. Es también la lista blanca de `abrir`: el SQL de cada
# objeto propio debe coincidir carácter a carácter.
ESQUEMA = (
    "CREATE TABLE meta(clave TEXT PRIMARY KEY, valor TEXT NOT NULL)",
    "CREATE TABLE leyes("
    "n INTEGER PRIMARY KEY, id TEXT NOT NULL UNIQUE, id_casefold TEXT NOT NULL, "
    "pais TEXT NOT NULL, "
    "titulo TEXT NOT NULL, rango TEXT NOT NULL, estado TEXT NOT NULL, "
    "fecha_publicacion TEXT NOT NULL, ultima_actualizacion TEXT NOT NULL, "
    "fecha_derogacion TEXT NOT NULL, fuente TEXT NOT NULL, jurisdiccion TEXT NOT NULL, "
    "departamento TEXT NOT NULL, estado_texto TEXT NOT NULL, ultima_modificacion TEXT NOT NULL, "
    "derogado_por TEXT NOT NULL, ruta TEXT NOT NULL, bytes INTEGER NOT NULL, mtime REAL NOT NULL, "
    "longitud INTEGER NOT NULL, titulo_norm TEXT NOT NULL, rango_norm TEXT NOT NULL, "
    "estado_norm TEXT NOT NULL, jurisdiccion_norm TEXT NOT NULL, departamento_norm TEXT NOT NULL)",
    "CREATE INDEX leyes_fecha_publicacion ON leyes(fecha_publicacion)",
    "CREATE INDEX leyes_ruta ON leyes(ruta)",
    "CREATE INDEX leyes_id_casefold ON leyes(id_casefold)",
    "CREATE TABLE articulos("
    "ley INTEGER NOT NULL, orden INTEGER NOT NULL, numero TEXT NOT NULL COLLATE NOCASE, "
    "ubicacion TEXT NOT NULL, inicio INTEGER NOT NULL, fin_encabezado INTEGER NOT NULL, "
    "fin INTEGER NOT NULL, abierto INTEGER NOT NULL, PRIMARY KEY (ley, orden)) WITHOUT ROWID",
    "CREATE INDEX articulos_numero ON articulos(ley, numero)",
    "CREATE VIRTUAL TABLE cuerpo USING fts5("
    "texto, content='', contentless_delete=1, tokenize='unicode61 remove_diacritics 0')",
)

# Tablas que FTS5 crea por su cuenta. Su SQL lo decide la versión de SQLite, no
# este módulo, así que de ellas solo se exige nombre y tipo: un índice escrito
# con otra versión de SQLite tiene que poder abrirse. No pueden hacer daño: con
# `trusted_schema=OFF` y el modo defensivo no se pueden escribir, y los
# disparadores y las vistas se rechazan aparte.
_TABLAS_FTS = frozenset({"cuerpo_data", "cuerpo_idx", "cuerpo_docsize", "cuerpo_config", "cuerpo_content"})

# Campos de texto de `leyes`, con la clave que tenían en el JSON.
_CAMPOS_TEXTO = (
    ("pais", "pais"), ("titulo", "titulo"), ("rango", "rango"), ("estado", "estado"),
    ("fecha_publicacion", "fecha_publicacion"), ("ultima_actualizacion", "ultima_actualizacion"),
    ("fecha_derogacion", "fecha_derogacion"), ("fuente", "fuente"),
    ("jurisdiccion", "jurisdiccion"), ("departamento", "departamento"),
    ("estado_texto", "estado_texto"), ("ultima_modificacion", "ultima_modificacion"),
    ("derogado_por", "derogado_por"), ("ruta", "_ruta"),
)
# Los que el JSON solo llevaba si venían en el frontmatter.
_OPCIONALES = ("jurisdiccion", "departamento", "fecha_derogacion", "derogado_por", "ultima_modificacion")
_NORMALIZADOS = ("titulo", "rango", "estado", "jurisdiccion", "departamento")


def ruta_indice(directorio: Path, nombre: str) -> Path:
    """El índice de un repositorio `legalize-<nombre>` o similar: `index_<nombre>.db`."""
    return Path(directorio) / f"index_{nombre}.db"


# ─────────────────────────────── escribir ────────────────────────────────────

def _texto(valor) -> str:
    return "" if valor is None else valor if isinstance(valor, str) else str(valor)


def _entero(valor) -> int:
    # `bool` es un `int` en Python: aceptarlo contaría `True` como 1 byte, una
    # cifra falsa en vez de un fallo (la regla de `_bytes_de`, ADR 0002).
    return valor if isinstance(valor, int) and not isinstance(valor, bool) else 0


def _real(valor) -> float:
    return float(valor) if isinstance(valor, (int, float)) and not isinstance(valor, bool) else 0.0


class Escritor:
    """Construye un índice en un temporal y lo sustituye entero al confirmar.

    Con `base`, el temporal empieza como copia de ese índice: es la pasada
    incremental. Sin ella, empieza vacío. En los dos casos el índice vigente no
    se toca hasta `confirmar`, así que un lector nunca ve uno a medias y una
    interrupción no cuesta nada.
    """

    def __init__(self, destino: Path, base: Path | None = None):
        self.destino = Path(destino)
        self.destino.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.destino.parent, prefix=".index_", suffix=".tmp.db")
        os.close(fd)
        self._tmp = Path(tmp)
        if base is not None:
            with open(base, "rb") as origen, open(self._tmp, "wb") as copia:
                while bloque := origen.read(1 << 20):
                    copia.write(bloque)
        else:
            self._tmp.unlink()
        # Sin transacciones implícitas del módulo: la única es la que abre y
        # cierra este escritor.
        self._con = sqlite3.connect(self._tmp, isolation_level=None)
        # El temporal se descarta si algo falla, así que no necesita diario.
        self._con.execute("PRAGMA journal_mode=OFF")
        self._con.execute("PRAGMA synchronous=OFF")
        if base is None:
            for sentencia in ESQUEMA:
                self._con.execute(sentencia)
            self.poner_meta("formato", FORMATO)
        self._con.execute("BEGIN")

    def ids(self) -> dict[str, tuple[str, int, float]]:
        """`{id: (ruta, bytes, mtime)}` de lo que ya tiene el índice, en su orden."""
        return {i: (r, b, t) for i, r, b, t in
                self._con.execute("SELECT id, ruta, bytes, mtime FROM leyes ORDER BY n")}

    def meta(self) -> dict:
        return {c: json.loads(v) for c, v in self._con.execute("SELECT clave, valor FROM meta")}

    def poner_meta(self, clave: str, valor) -> None:
        self._con.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)",
                          (clave, json.dumps(valor, ensure_ascii=False, sort_keys=True)))

    def quitar_meta(self, clave: str) -> None:
        self._con.execute("DELETE FROM meta WHERE clave = ?", (clave,))

    def poner_ley(self, id_ley: str, campos: dict, cuerpo: str) -> None:
        """Escribe una ley; `cuerpo` es el texto sin frontmatter que se sirve.

        Si el id ya existe con las mismas letras, la reemplaza conservando su
        posición, como hacía el JSON al reasignar una clave. Un id que solo
        difiere en mayúsculas es otra ley: la regla de duplicados del indexador
        distingue mayúsculas, y una unicidad que no lo hiciera dejaría que un
        solo fichero manipulado abortara la escritura del corpus entero.
        """
        valores = {col: _texto(campos.get(clave)) for col, clave in _CAMPOS_TEXTO}
        if not valores["estado_texto"]:
            valores["estado_texto"] = "point_in_time"
        normalizados = [legalize_normalizacion.normalizar(valores[c]) for c in _NORMALIZADOS]
        fila = self._con.execute("SELECT n FROM leyes WHERE id = ? COLLATE BINARY", (id_ley,)).fetchone()
        if fila:
            n = fila[0]
            self._borrar(n)
        else:
            n = (self._con.execute("SELECT coalesce(max(n), 0) + 1 FROM leyes").fetchone()[0])
        self._con.execute(
            f"INSERT INTO leyes VALUES ({', '.join('?' * 25)})",
            (n, id_ley, id_ley.casefold(), *(valores[c] for c, _ in _CAMPOS_TEXTO[:13]), valores["ruta"],
             _entero(campos.get("_bytes")), _real(campos.get("_mtime")), len(cuerpo), *normalizados),
        )
        self._con.executemany(
            "INSERT INTO articulos VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [(n, *fila) for fila in legalize_articulos.localizar_todos(cuerpo)],
        )
        self._con.execute("INSERT INTO cuerpo(rowid, texto) VALUES (?, ?)",
                          (n, legalize_normalizacion.normalizar(cuerpo)))

    def quitar_ley(self, id_ley: str) -> None:
        fila = self._con.execute("SELECT n FROM leyes WHERE id = ? COLLATE BINARY", (id_ley,)).fetchone()
        if fila:
            self._borrar(fila[0])

    def _borrar(self, n: int) -> None:
        self._con.execute("DELETE FROM leyes WHERE n = ?", (n,))
        self._con.execute("DELETE FROM articulos WHERE ley = ?", (n,))
        self._con.execute("DELETE FROM cuerpo WHERE rowid = ?", (n,))

    def confirmar(self) -> None:
        """Cierra la transacción, compacta y sustituye el índice vigente."""
        try:
            self._con.execute("COMMIT")
            self._con.execute("INSERT INTO cuerpo(cuerpo) VALUES ('optimize')")
            self._con.execute("VACUUM")
            self._con.close()
            os.replace(self._tmp, self.destino)
        except BaseException:
            self.descartar()
            raise

    def descartar(self) -> None:
        try:
            self._con.close()
        except sqlite3.Error:
            pass
        for sufijo in ("", "-journal", "-wal", "-shm"):
            Path(f"{self._tmp}{sufijo}").unlink(missing_ok=True)


# ──────────────────────────────── abrir ──────────────────────────────────────

def _objetos(con: sqlite3.Connection) -> set[tuple[str, str, str | None]]:
    return set(con.execute("SELECT type, name, sql FROM sqlite_master"))


def _referencia() -> set[tuple[str, str, str | None]]:
    con = sqlite3.connect(":memory:")
    for sentencia in ESQUEMA:
        con.execute(sentencia)
    objetos = _objetos(con)
    con.close()
    return objetos


def esquema_esperado() -> set[tuple[str, str, str]]:
    """Los objetos propios del formato, sin los internos de SQLite."""
    return {(t, n, s) for t, n, s in _referencia() if s is not None and not n.startswith("sqlite_")}


def abrir(ruta: Path) -> sqlite3.Connection:
    """Abre un índice como entrada no confiable, o lanza ValueError con el motivo.

    Motivos: `sin_modo_defensivo` (Python < 3.12), `ilegible`,
    `esquema_inesperado`, `formato_distinto`. Ninguna consulta toca las tablas
    antes de comprobar el esquema.
    """
    if not hasattr(sqlite3.Connection, "setconfig"):
        raise ValueError("sin_modo_defensivo")
    ruta = Path(ruta)
    if not ruta.is_file():
        raise ValueError("ilegible")
    uri = f"file:{urllib.parse.quote(str(ruta.resolve()))}?mode=ro"
    try:
        con = sqlite3.connect(uri, uri=True, check_same_thread=False)
        con.setconfig(sqlite3.SQLITE_DBCONFIG_DEFENSIVE, True)
        con.execute("PRAGMA trusted_schema=OFF")
        con.execute("PRAGMA query_only=ON")
        con.execute("PRAGMA cell_size_check=ON")
        objetos = _objetos(con)
    except sqlite3.DatabaseError as exc:
        raise ValueError("ilegible") from exc

    propios = {o for o in objetos if o[1] not in _TABLAS_FTS}
    fts = {(t, n) for t, n, _ in objetos if n in _TABLAS_FTS}
    referencia = _referencia()
    if (propios != {o for o in referencia if o[1] not in _TABLAS_FTS}
            or fts != {(t, n) for t, n, _ in referencia if n in _TABLAS_FTS}):
        con.close()
        raise ValueError("esquema_inesperado")
    try:
        formato = con.execute("SELECT valor FROM meta WHERE clave = 'formato'").fetchone()
    except sqlite3.DatabaseError as exc:
        con.close()
        raise ValueError("ilegible") from exc
    if not formato or formato[0] != json.dumps(FORMATO):
        con.close()
        raise ValueError("formato_distinto")
    return con


def leer_meta(con: sqlite3.Connection) -> dict:
    """La tabla `meta` decodificada. Un valor que no es JSON se ignora."""
    salida = {}
    for clave, valor in con.execute("SELECT clave, valor FROM meta"):
        try:
            salida[clave] = json.loads(valor)
        except (TypeError, ValueError):
            continue
    return salida


def como_dict(ruta: Path) -> dict:
    """El índice con la forma que tenía el JSON: `{"_meta": ..., "documentos": ...}`.

    Para inspeccionar un índice generado —los tests, un operador— sin conocer
    el esquema.
    """
    con = abrir(ruta)
    try:
        meta = leer_meta(con)
        meta.pop("formato", None)
        documentos = {}
        columnas = [c for c, _ in _CAMPOS_TEXTO]
        for fila in con.execute(
                f"SELECT id, {', '.join(columnas)}, bytes, mtime FROM leyes ORDER BY n"):
            id_ley, *textos, bytes_, mtime = fila
            entrada = {"identificador": id_ley}
            for (col, clave), valor in zip(_CAMPOS_TEXTO, textos):
                if col in _OPCIONALES and not valor:
                    continue
                entrada[clave] = valor
            entrada["_archivo"] = Path(entrada["_ruta"]).name
            entrada["_bytes"], entrada["_mtime"] = bytes_, mtime
            documentos[id_ley] = entrada
        meta["total_documentos"] = len(documentos)
        return {"_meta": meta, "documentos": documentos}
    finally:
        con.close()


# ─────────────────────────────── consultar ───────────────────────────────────

# Columnas con las que el servidor reconstruye cada ley con las claves que tenía
# el JSON, para que sus ayudantes (`_doc_resumen`, `_resolve_ruta`,
# `_wrap_untrusted`…) no cambien.
COLUMNAS_LEY = ("id", *(c for c, _ in _CAMPOS_TEXTO), "bytes", "mtime")


def fila_a_doc(fila) -> dict:
    """Una fila de `leyes` (en el orden de `COLUMNAS_LEY`) como la entrada del JSON."""
    id_ley, *textos, bytes_, mtime = fila
    doc = {"identificador": id_ley}
    for (col, clave), valor in zip(_CAMPOS_TEXTO, textos):
        if col in _OPCIONALES and not valor:
            continue
        doc[clave] = valor
    doc["_archivo"] = Path(doc["_ruta"]).name if doc.get("_ruta") else ""
    doc["_bytes"], doc["_mtime"] = bytes_, mtime
    return doc


def terminos_fts(terminos) -> str:
    """Una expresión MATCH que exige todos los términos, cada uno como texto literal.

    Cada término va entre comillas dobles, con las internas duplicadas: así FTS5
    lo trata como una cadena y nunca como sintaxis. Un `AND`, `NEAR`, `*` o
    paréntesis del cliente no puede funcionar como operador (FR-006).
    """
    return " AND ".join('"' + t.replace('"', '""') + '"' for t in sorted(terminos))


def construir_filtro(*, consulta="", rango="", estado="", anno="", jurisdiccion="", departamento="",
                     fecha_desde="", fecha_hasta="", derogada_desde="", derogada_hasta="",
                     actualizada_desde="", actualizada_hasta="", match=None) -> tuple[str, list]:
    """`(where, parametros)` para `buscar_ley` y `contar_leyes`: un solo sitio (principio III).

    Reproduce la semántica de los filtros que había en memoria:

    - Subcadena sobre la forma plegada en título, rango, estado, jurisdicción y
      departamento. `instr` y no `LIKE`, que añadiría comodines que escapar.
    - `anno` es un prefijo de la fecha de publicación.
    - Las fechas de publicación dejan pasar los documentos sin fecha; las de
      derogación y de actualización exigen que exista.
    - Los límites superiores comparan la fecha recortada a la precisión del
      límite: "2001" es todo 2001 (defecto #6).
    - `match`, si llega, es una expresión de `terminos_fts` sobre el cuerpo.

    Todos los valores van como parámetros enlazados, nunca dentro del SQL.
    """
    condiciones, parametros = [], []

    def subcadena(columna, valor):
        if valor:
            condiciones.append(f"instr({columna}, ?) > 0")
            parametros.append(legalize_normalizacion.normalizar(valor))

    def rango_fechas(columna, desde, hasta, exige):
        desde, hasta = desde.strip(), hasta.strip()
        if not (desde or hasta):
            return
        if exige:
            condiciones.append(f"{columna} != ''")
            vacia = ""
        else:
            vacia = f"{columna} = '' OR "
        if desde:
            condiciones.append(f"({vacia}{columna} >= ?)")
            parametros.append(desde)
        if hasta:
            condiciones.append(f"({vacia}substr({columna}, 1, length(?)) <= ?)")
            parametros.extend([hasta, hasta])

    if anno.strip():
        condiciones.append("substr(fecha_publicacion, 1, length(?)) = ?")
        parametros.extend([anno.strip(), anno.strip()])
    rango_fechas("fecha_publicacion", fecha_desde, fecha_hasta, exige=False)
    rango_fechas("fecha_derogacion", derogada_desde, derogada_hasta, exige=True)
    rango_fechas("ultima_actualizacion", actualizada_desde, actualizada_hasta, exige=True)
    subcadena("estado_norm", estado)
    subcadena("rango_norm", rango)
    subcadena("jurisdiccion_norm", jurisdiccion)
    subcadena("departamento_norm", departamento)
    subcadena("titulo_norm", consulta)
    if match is not None:
        condiciones.append("n IN (SELECT rowid FROM cuerpo WHERE cuerpo MATCH ?)")
        parametros.append(match)
    return (" AND ".join(condiciones) or "1"), parametros
