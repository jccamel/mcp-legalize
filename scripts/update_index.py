#!/usr/bin/env python3
"""
scripts/update_index.py
=======================
Mantenimiento de los índices `indices/index_<repo>.json`.

Sincroniza el índice de un país con el estado real de los ficheros .md
en su respectivo repositorio (ej. repos/legalize-es).

Soporta subcarpetas arbitrarias usando recursividad (`rglob`).
"""

import argparse
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, NamedTuple

_SCRIPT_DIR = Path(__file__).parent
_PROJECT_DIR = _SCRIPT_DIR.parent
DEFAULT_INDICES_DIR = _PROJECT_DIR / "indices"

# Este script se ejecuta como `python scripts/update_index.py`, así que sys.path
# arranca en scripts/ y la raíz del proyecto no es importable. Sin esto no se
# puede compartir el parser de frontmatter con el servidor — y compartirlo es
# precisamente lo que impide que escáner y servidor vuelvan a discrepar.
if str(_PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(_PROJECT_DIR))

import legalize_frontmatter  # noqa: E402  (requiere el sys.path de arriba)
import legalize_injection  # noqa: E402  (idem)
import legalize_postings  # noqa: E402  (idem)
import legalize_repo  # noqa: E402  (idem)
import legalize_tokenizer  # noqa: E402  (idem)

# Non-law markdown files that must never end up in the index.
_SKIP_STEMS = {"readme", "license", "licence", "contributing", "code_of_conduct", "changelog", "authors"}

# --- Escaneo de prompt injection ---
#
# El vocabulario vive en legalize_injection: un solo sitio declara qué texto
# parece una inyección, y cada superficie decide qué hacer al encontrarlo. Aquí
# la decisión es cuarentena (BLOCK) o aviso (WARN); en el servidor es sustituir
# el metadato por "[filtered]". Antes había dos tablas independientes, y la de
# los metadatos se había quedado en EN/ES mientras esta crecía a seis idiomas:
# el título de una ley podía decir "Ignoriere alle vorherigen Anweisungen" y
# llegar intacto al modelo en cada resultado de búsqueda.
#
# Sigue siendo un canario, NO una defensa: la defensa real es _wrap_untrusted
# (mcp_legalize.py). Lo que se gana al compartir la tabla es que el canario no
# cante en un idioma distinto según por dónde entre el texto.

SEVERITY_BLOCK = legalize_injection.SEVERITY_BLOCK
SEVERITY_WARN = legalize_injection.SEVERITY_WARN

_Finding = legalize_injection.Finding

def _strip_frontmatter_for_scan(text: str) -> str:
    """Delega en legalize_frontmatter: ver el módulo para las reglas.

    Antes esto buscaba el primer "\\n---" con str.find, que trataba una regla
    horizontal de Markdown como delimitador de cierre y descartaba todo lo que
    hubiera encima. El servidor no cortaba ahí, así que el texto descartado se
    servía igual: un payload colocado en esa franja llegaba al modelo sin haber
    pasado nunca por los patrones de inyección.
    """
    return legalize_frontmatter.cuerpo(text)

def _check_injection(text: str) -> list[_Finding]:
    """Escanea el cuerpo del fichero en busca de patrones de prompt injection.

    Devuelve la lista de hallazgos (puede estar vacía). No imprime nada: quien
    llama decide qué reportar y qué bloquear según la severidad.

    El escaneo cubre el documento COMPLETO, sin techo de tamaño: obtener_articulo
    (mcp_legalize.py) puede extraer texto desde cualquier posición del fichero,
    así que truncar el escaneo abriría un hueco en las normas largas.
    """
    return legalize_injection.escanear(
        _strip_frontmatter_for_scan(text), legalize_injection.SURFACE_BODY,
    )

def _self_test() -> int:
    """Verifica que cada patrón detecta su muestra por el camino REAL.

    Cubre las dos superficies. En el cuerpo el riesgo es el pre-filtro de gates,
    que es lo que hace viable escanear un corpus de ~1 GB y también lo que puede
    dejar un regex mudo sin que nada falle visiblemente. En los metadatos el
    riesgo equivalente son los flags al fundir todos los patrones en un único
    regex de sustitución. Los dos caminos se prueban de punta a punta.
    """
    fallos = legalize_injection.autotest()
    for fallo in fallos:
        print(f"[FALLO] {fallo}", file=sys.stderr)

    total = len(legalize_injection.PATTERNS)
    n_cuerpo = len(legalize_injection.patrones(legalize_injection.SURFACE_BODY))
    n_meta = len(legalize_injection.patrones(legalize_injection.SURFACE_METADATA))
    if fallos:
        print(f"\nself-test: {len(fallos)} fallo(s) sobre {total} patrones.",
              file=sys.stderr)
        return 1
    print(f"self-test OK - {total} patrones detectan su muestra por el camino "
          f"real ({n_cuerpo} en cuerpo, {n_meta} en metadatos).")
    print(f"huella del ruleset de cuerpo: {legalize_injection.huella()}")
    return 0

def _warn(msg: str) -> None:
    print(f"  [AVISO] {msg}", file=sys.stderr)

def _parse_frontmatter(text: str) -> dict:
    """Delega en legalize_frontmatter: ver el módulo para las reglas.

    Comparte la localización del bloque con el escáner y con el servidor, de
    modo que los metadatos indexados salgan siempre de la misma región que los
    otros dos consideran frontmatter.
    """
    return legalize_frontmatter.parsear(text)

class _StatInfo(NamedTuple):
    size: int
    mtime: float

def _get_stat(md_path: Path) -> _StatInfo:
    s = md_path.stat()
    return _StatInfo(size=s.st_size, mtime=s.st_mtime)

def _needs_update(existing: dict, stat: _StatInfo, force: bool) -> bool:
    if force:
        return True
    if existing.get("_bytes", -1) != stat.size:
        return True
    stored_mtime = existing.get("_mtime", 0.0)
    if stored_mtime and stat.mtime > stored_mtime:
        return True
    return False

# Techo de longitud para cualquier valor que venga del frontmatter.
#
# Medido, no elegido a ojo: el título legítimo más largo del corpus español son
# 1.658 caracteres (BOE-A-2021-20004) frente a una mediana de 147, y ningún otro
# campo pasa de 100. 8.000 son casi cinco veces ese máximo real, así que corta un
# payload de 100 KB sin amenazar a una ley que crezca.
#
# Uno solo y no uno por campo a propósito: una tabla por campo sería un segundo
# juego de números que mantener en sintonía con los `max_len` del servidor, y se
# quedaría corta en cuanto llegue una jurisdicción con títulos más largos que los
# españoles.
_MAX_META_CHARS = 8_000

def _truncar_metadatos(entry: dict) -> list[str]:
    """Acota los valores del frontmatter y devuelve los campos recortados.

    El indexador guardaba lo que trajera el fichero. El servidor acota al
    servir, no al cargar, así que un título de 100.000 caracteres vivía entero
    en el índice y en la memoria de todo servidor que lo leyera: mil documentos
    así son ~100 MB residentes permanentes mientras las respuestas se ven
    perfectamente normales.

    Recortar no es rechazar: el documento se indexa igual. Y se informa, porque
    acortar un título en silencio es la misma pérdida callada de datos que
    cerró #20 — quien genera el índice debe poder distinguir un corpus hostil
    de uno inusualmente verboso.
    """
    truncados = []
    for campo, valor in entry.items():
        if campo.startswith("_") or not isinstance(valor, str):
            continue
        if len(valor) > _MAX_META_CHARS:
            entry[campo] = valor[:_MAX_META_CHARS]
            truncados.append(campo)
    return truncados

def _scan_metadatos(entry: dict) -> list[str]:
    """Hallazgos de inyección en los campos que se indexan y luego se sirven.

    `_check_injection` mira el cuerpo con el frontmatter ya recortado, así que la
    región que acaba en cada resultado de `buscar_ley` no la examinaba nadie del
    lado del indexador: el mismo texto iba a cuarentena en el cuerpo y se
    indexaba sin comentario en un título.

    No bloquea, y eso es una decisión medida, no una omisión. `meta.html_tag`
    tiene severidad `block` y detecta cualquier `<` seguido de letra, de modo que
    un título real como "Real Decreto 3/2020 <de desarrollo>" lo dispara. Poner
    ese documento en cuarentena borraría una ley legítima del corpus para frenar
    algo que el servidor ya neutraliza al servirlo. Se pierde el texto, que es lo
    único que importa, a cambio de nada.

    Lo que sí hace falta es constancia: qué fichero, qué campo y qué patrón. Un
    título hostil dice algo del repositorio de origen, igual que un hallazgo en
    el cuerpo.
    """
    hallazgos = []
    for campo, valor in entry.items():
        # Los campos que empiezan por '_' los calcula el indexador, no vienen
        # del frontmatter: no son texto no fiable.
        if campo.startswith("_") or not isinstance(valor, str) or not valor:
            continue
        for h in legalize_injection.escanear(valor, legalize_injection.SURFACE_METADATA):
            hallazgos.append(f"{campo}: {h.label}")
    return hallazgos

def _build_entry(md_path: Path, stat: _StatInfo, base_dir: Path, fallback_pais: str) -> tuple[str, dict, list[_Finding]]:
    """Construye una entrada de índice para un documento .md.

    Devuelve (doc_id, entry_dict, hallazgos_en_cuerpo, hallazgos_en_metadatos,
    campos_truncados, terminos)
    """
    text = md_path.read_text(encoding="utf-8", errors="replace")
    hallazgos = _check_injection(text)
    meta = _parse_frontmatter(text)
    # Se aprovecha la lectura que ya se hacía para escanear. Tokenizar aquí
    # cuesta una pasada más sobre un texto que ya está en memoria; hacerlo en
    # otro sitio costaría volver a leer 921 MB del disco.
    terminos = legalize_tokenizer.tokens_de_documento(text)

    try:
        ruta_relativa = md_path.relative_to(base_dir).as_posix()
    except ValueError:
        ruta_relativa = str(md_path)

    def _get(*keys: str, default: str = "") -> str:
        for k in keys:
            v = meta.get(k, "")
            if v:
                return v
        return default

    doc_id = _get("identificador", "identifier", default=md_path.stem)
    pais = _get("pais", "country", default=fallback_pais)

    # Prefix purely numerical doc IDs
    if doc_id.isdigit() and pais:
        doc_id = f"{pais}_{doc_id}"

    entry = {
        "titulo":               _get("titulo", "title"),
        "identificador":        doc_id,
        "pais":                 pais,
        "rango":                _get("rango", "rank"),
        "fecha_publicacion":    _get("fecha_publicacion", "publication_date"),
        "ultima_actualizacion": _get("ultima_actualizacion", "last_updated"),
        "estado":               _get("estado", "status"),
        "fuente":               _get("fuente", "source"),
        "_archivo":             md_path.name,
        "_ruta":                ruta_relativa,
        "_bytes":               stat.size,
        "_mtime":               stat.mtime,
    }

    # Campos opcionales: solo se incluyen si están presentes en el frontmatter.
    for field, keys in [
        ("jurisdiccion", ("jurisdiccion", "jurisdiction")),
        ("departamento",  ("departamento", "department")),
        ("fecha_derogacion", ("fecha_derogacion", "repeal_date")),
        ("derogado_por",  ("derogado_por", "repealed_by")),
    ]:
        val = _get(*keys)
        if val:
            entry[field] = val
    # Truncar antes de escanear: el escaneo cuesta en proporción al texto y no
    # tiene sentido pagarlo sobre una franja que no va a entrar en el índice.
    truncados = _truncar_metadatos(entry)
    return doc_id, entry, hallazgos, _scan_metadatos(entry), truncados, terminos

def _nombre_repo(index_path: Path) -> str:
    """El nombre con el que `legalize_postings` localiza los postings de un índice.

    Fichero aparte y no una sección del JSON: `json.load` no sabe leer una
    sección suelta, así que fundirlos obligaría al servidor a procesar todos
    los postings para llegar a los metadatos que necesita al arrancar, y haría
    imposible la carga perezosa (ADR 0003).
    """
    return index_path.stem.removeprefix("index_")

def _invertir(terminos_por_doc: dict[str, set[str]]) -> dict[str, list[str]]:
    """De documento->términos a término->documentos.

    Las listas van ordenadas para que dos índices construidos sobre el mismo
    corpus salgan byte a byte iguales: un `.bin` que cambia sin que cambie nada
    real haría ruido en cualquier comprobación de frescura.
    """
    postings: dict[str, list[str]] = {}
    for doc_id, terminos in terminos_por_doc.items():
        for termino in terminos:
            postings.setdefault(termino, []).append(doc_id)
    return {t: sorted(docs) for t, docs in sorted(postings.items())}

def _terminos_en_disco(documentos: dict, ids: Iterable[str], repo_dir: Path) -> dict[str, set[str]]:
    """Tokeniza desde disco los documentos indicados del índice.

    La ruta sale del índice, que es entrada no confiable también para el
    indexador (principio II): un `_ruta` que escape del repositorio haría que
    los términos de un fichero ajeno acabaran siendo buscables. Se exige que la
    ruta resuelta esté dentro de `repo_dir` y sea un fichero regular; si no, el
    documento se queda sin términos, igual que uno cuyo fichero ya no existe.
    """
    raiz = repo_dir.resolve()
    terminos: dict[str, set[str]] = {}
    for doc_id in ids:
        ruta_rel = documentos[doc_id].get("_ruta", "")
        if not isinstance(ruta_rel, str) or not ruta_rel:
            continue
        ruta = (raiz / ruta_rel).resolve()
        if not ruta.is_relative_to(raiz) or not ruta.is_file():
            continue
        try:
            texto = ruta.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        terminos[doc_id] = legalize_tokenizer.tokens_de_documento(texto)
    return terminos


def _postings_finales(previos, documentos: dict, terminos_por_doc: dict[str, set[str]],
                      repo_dir: Path) -> dict[str, list[str]]:
    """Los postings que corresponden exactamente a los documentos del JSON.

    Es la invariante de FR-001: tras cualquier pasada, ni más ni menos que los
    términos de los documentos que el índice tiene en ese momento.

    FUSIONAR, si los postings previos se pueden usar: de cada término se
    conservan los documentos que siguen en el JSON y no se han reprocesado en
    esta pasada, y se añaden los términos de los reprocesados. Así no hace falta
    seguir por separado cada forma de salir del índice — cuarentena, cambio de
    identificador, huérfano retirado, duplicado —: lo que ya no está en el JSON
    no se conserva. Medido sobre el corpus español: 10,2 s con un 5% de cambios,
    frente a 49 s de retokenizarlo todo (research.md, R2).

    RECONSTRUIR, si no se pueden usar o una lista resulta corrupta al
    decodificarla: se tokenizan desde disco todos los documentos del JSON que
    esta pasada no haya procesado ya.
    """
    nuevos = _invertir(terminos_por_doc)
    if previos is not None:
        descartar = {i for i, doc_id in enumerate(previos.ids)
                     if doc_id not in documentos or doc_id in terminos_por_doc}
        try:
            for termino in previos.terminos():
                indices = previos.indices(termino)
                if descartar:
                    indices = indices - descartar
                if indices:
                    nuevos.setdefault(termino, []).extend(previos.ids[i] for i in indices)
            return nuevos
        except ValueError as exc:
            print(f"\n[AVISO] postings previos ilegibles al fusionar ({exc}); "
                  f"se reconstruyen.", file=sys.stderr)
            nuevos = _invertir(terminos_por_doc)

    faltan = [d for d in documentos if d not in terminos_por_doc]
    for termino, docs in _invertir(_terminos_en_disco(documentos, faltan, repo_dir)).items():
        nuevos.setdefault(termino, []).extend(docs)
    return nuevos


def _write_invertido(index_path: Path, postings: dict[str, list[str]],
                     generacion: str) -> int:
    """Escribe los postings y devuelve cuántos términos tienen.

    El formato lo decide `legalize_postings`, no este script: antes esto era un
    `pickle.dump`, y el servidor lo cargaba con `pickle.load` sobre un fichero
    que cualquiera con escritura en `indices/` podía sustituir (spec 001).

    Lleva su propia huella del tokenizador y la generación del JSON al que
    acompaña: unos postings separados de su índice siguen siendo legibles, y
    tienen que poder decir con qué reglas y para qué índice se construyeron.

    Tras escribirlos, el `.bin` del formato anterior se borra: dejarlo al lado
    sería un fichero más que alguien podría intentar que se leyera.
    """
    nombre = _nombre_repo(index_path)
    n = legalize_postings.escribir(
        legalize_postings.ruta_postings(index_path.parent, nombre),
        postings,
        tokenizador=legalize_tokenizer.huella(), generacion=generacion,
    )
    legalize_postings.ruta_formato_anterior(index_path.parent, nombre).unlink(missing_ok=True)
    return n

def _write_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp", prefix=".index_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

class _Progress:
    """Reporta avance a stderr durante el escaneo.

    Escanear el corpus completo lleva decenas de segundos. Sin esto el script
    queda mudo el tiempo suficiente para que parezca colgado y alguien lo mate
    con Ctrl+C — que es exactamente lo que pasaba antes.
    """

    def __init__(self, total_files: int, total_bytes: int, cada: float = 0.5):
        self.total_files = total_files
        self.total_bytes = max(total_bytes, 1)
        self.cada = cada
        self.files = 0
        self.bytes = 0
        self.inicio = time.monotonic()
        self._ultimo = 0.0
        self._activo = sys.stderr.isatty()

    def avanzar(self, nbytes: int) -> None:
        self.files += 1
        self.bytes += nbytes
        ahora = time.monotonic()
        if ahora - self._ultimo < self.cada and self.files < self.total_files:
            return
        self._ultimo = ahora
        transcurrido = ahora - self.inicio
        frac = self.bytes / self.total_bytes
        eta = (transcurrido / frac - transcurrido) if frac > 0.01 else 0.0
        linea = (
            f"  escaneando {self.files:,}/{self.total_files:,} "
            f"({frac * 100:5.1f}%)  {self.bytes / 1_048_576:,.0f} MiB  "
            f"ETA {eta:4.0f}s"
        )
        if self._activo:
            print(f"\r{linea:<78}", end="", file=sys.stderr, flush=True)
        elif self.files == self.total_files or self.files % 2000 == 0:
            print(linea, file=sys.stderr, flush=True)

    def cerrar(self) -> None:
        transcurrido = time.monotonic() - self.inicio
        if self._activo:
            print("\r" + " " * 78 + "\r", end="", file=sys.stderr)
        mibs = self.bytes / 1_048_576 / max(transcurrido, 0.001)
        print(
            f"Escaneados        : {self.files:,} ficheros, "
            f"{self.bytes / 1_048_576:,.0f} MiB en {transcurrido:.1f}s ({mibs:,.0f} MiB/s)"
        )

def _load_index(index_path: Path) -> dict:
    if not index_path.exists():
        return {"_meta": {}, "documentos": {}}
    print(f"Cargando índice: {index_path} …")
    try:
        with index_path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:
        print(f"[ERROR] Índice corrupto: {exc}. Reconstruyendo.", file=sys.stderr)
        return {"_meta": {}, "documentos": {}}

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Mantiene índices de repositorios legales Legalize con detección de seguridad."
    )
    # No es `required` para que --self-test pueda correr sin repositorio.
    parser.add_argument("--repo", type=Path,
                        help="Directorio del repositorio de un país (ej. repos/legalize-es).")
    parser.add_argument("--index", type=Path,
                        help="Ruta al index JSON a generar. Si no se indica, va a indices/.")
    parser.add_argument("--pais", type=str,
                        help="Código de país a usar como fallback si no se especifica en yaml (ej. es).")
    parser.add_argument("--force-all", action="store_true",
                        help="Reindexar todos los documentos incluso si no han cambiado.")
    parser.add_argument("--remove-orphans", action="store_true",
                        help="Remover documentos del índice que ya no existen en disco.")
    parser.add_argument("--force-index-unsafe", action="store_true",
                        help="Indexar también los ficheros en cuarentena por seguridad.")
    parser.add_argument("--fail-on-quarantine", action="store_true",
                        help="Salir con código 3 si algún fichero quedó en cuarentena. "
                             "El índice se escribe igualmente; pensado para CI.")
    parser.add_argument("--show-warnings", action="store_true",
                        help="Mostrar también los hallazgos informativos (severidad warn), "
                             "que por defecto solo se cuentan en el resumen.")
    parser.add_argument("--self-test", action="store_true",
                        help="Verificar los patrones de seguridad y salir.")
    args = parser.parse_args()

    if args.self_test:
        sys.exit(_self_test())

    # El progreso y los avisos van a stderr (sin buffer) y el resto a stdout.
    # Sin esto, al redirigir la salida a un fichero o a un log de CI, stdout
    # queda en buffer de bloque y el informe aparece desordenado.
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except (AttributeError, OSError):
        pass

    if args.repo is None:
        parser.error("se requiere --repo (salvo con --self-test)")

    repo_dir = args.repo.resolve()
    if not repo_dir.is_dir():
        print(f"[ERROR] Directorio del repositorio no encontrado: {repo_dir}", file=sys.stderr)
        sys.exit(1)

    repo_name = repo_dir.name
    fallback_pais = args.pais or (repo_name.replace("legalize-", "") if "legalize-" in repo_name else "")

    index_path = args.index
    if not index_path:
        DEFAULT_INDICES_DIR.mkdir(parents=True, exist_ok=True)
        index_path = DEFAULT_INDICES_DIR / f"index_{repo_name}.json"

    print(f"Indexando repositorio: {repo_dir}")
    print(f"Archivo de índice  : {index_path}")

    data = _load_index(index_path)
    documentos: dict = data.setdefault("documentos", {})
    meta_idx: dict = data.setdefault("_meta", {})

    ruta_a_docid: dict[str, str] = {}
    for k, v in documentos.items():
        ruta = v.get("_ruta", "")
        if ruta:
            ruta_a_docid[ruta] = k

    # Escanear Markdown recursivamente. Ordenado a propósito: cuando dos
    # ficheros reclaman el mismo `identificador`, gana el primero, y "el
    # primero" solo significa algo si el recorrido no depende del orden que
    # devuelva el sistema de ficheros. Sin esto, el documento superviviente
    # podía cambiar entre dos corridas sobre el mismo corpus.
    md_files = {}
    for p in sorted(repo_dir.rglob("*.md")):
        # Evitar repositorios .git internos u ocultos si aplicara
        if ".git" in p.parts:
            continue
        # Skip documentation/meta files that live alongside the corpus.
        if p.stem.lower() in _SKIP_STEMS:
            continue
        try:
            rel_str = p.relative_to(repo_dir).as_posix()
            md_files[rel_str] = p
        except ValueError:
            pass

    md_stats = {rel: _get_stat(p) for rel, p in md_files.items()}

    print(f"Ficheros en disco : {len(md_files):,}")
    print(f"Entradas en índice: {len(documentos):,}")

    # Una pasada incremental solo escanea lo que cambió en disco, así que si el
    # ruleset cambia los documentos intactos conservan una auditoría hecha con
    # reglas que ya no existen — y `escaneado_en` se refresca igual, con lo que
    # la fecha pasa a mentir. Cuando la huella no coincide se reescanea todo.
    huella_actual = legalize_injection.huella()
    huella_previa = (meta_idx.get("seguridad") or {}).get("patrones")
    ruleset_cambiado = bool(documentos) and huella_previa != huella_actual
    if ruleset_cambiado:
        if huella_previa:
            print(f"\nReglas de escaneo : {huella_previa} -> {huella_actual} (cambiaron)")
        else:
            print(f"\nReglas de escaneo : {huella_actual} "
                  f"(el índice no registra con cuáles se escaneó)")
        print("                    Se reescanea el corpus completo: la auditoría "
              "anterior ya no es\n                    comparable.")

    forzar = args.force_all or ruleset_cambiado

    nuevos = []
    actualizados = []
    renombrados = []
    docids_validos = set()

    for rel, md_path in md_files.items():
        old_doc_id = ruta_a_docid.get(rel)
        if old_doc_id is not None:
            docids_validos.add(old_doc_id)
            if _needs_update(documentos.get(old_doc_id, {}), md_stats[rel], forzar):
                actualizados.append(rel)
        else:
            nuevos.append(rel)

    huerfanos = [d for d in documentos if d not in docids_validos]

    print(f"\nNuevos            : {len(nuevos):,}")
    print(f"Modificados       : {len(actualizados):,}")
    print(f"Huérfanos         : {len(huerfanos):,}")

    # Los postings previos se fusionan si se pueden usar y se reconstruyen si
    # no. Antes se reescribían solo con los documentos de esta pasada, así que
    # tras un `git pull` la búsqueda por texto perdía el resto del corpus sin
    # decir nada (spec 001, US1). `estado` decide igual que el servidor: mismo
    # formato, mismo tokenizador y misma generación que este JSON.
    postings_previos, motivo_previo = legalize_postings.estado(
        index_path.parent, _nombre_repo(index_path),
        legalize_tokenizer.huella(), meta_idx.get("generacion"),
    )
    # El sello del JSON cuenta igual que la cabecera de los postings. Es el que
    # mira `check_updates.py` para decir TOKENS, así que si no forzara nada aquí,
    # el remedio que propone respondería "ya está al día" y el aviso volvería
    # en cada pasada (spec 001, US5; FR-013, FR-014).
    if (motivo_previo is None and documentos
            and meta_idx.get("tokenizador") != legalize_tokenizer.huella()):
        postings_previos, motivo_previo = None, legalize_postings.TOKENIZADOR_DISTINTO
    if motivo_previo is not None and documentos:
        print(f"Índice invertido  : se reconstruye ({motivo_previo})")

    # "Al día" exige también unos postings utilizables: un JSON correcto con los
    # postings ausentes, de otra generación o de otro tokenizador no lo está.
    if not nuevos and not actualizados and not huerfanos and motivo_previo is None:
        print("\nEl índice ya está al día.")
        return

    errores = 0
    # Ficheros excluidos del índice por hallazgos de severidad `block`.
    cuarentena: dict[str, list[str]] = {}
    # Ficheros con hallazgos `block` que se indexaron por --force-index-unsafe.
    forzados: dict[str, list[str]] = {}
    # Ficheros con hallazgos `warn`: se indexan igual, solo se registran.
    avisos: dict[str, list[str]] = {}
    # Ficheros cuyo `identificador` ya lo reclamaba otro documento. Se indexan
    # bajo un id derivado de su ruta, nunca se descartan: perder una ley porque
    # otra repite su identificador convertiría un fallo del corpus en dos.
    duplicados: dict[str, str] = {}
    # Hallazgos de inyección en los campos del frontmatter que se indexan. Nunca
    # bloquean — ver `_scan_metadatos` —, solo se registran.
    metadatos: dict[str, list[str]] = {}
    # Ficheros con algún valor de frontmatter por encima de `_MAX_META_CHARS`.
    truncados: dict[str, list[str]] = {}
    # Términos de cada documento aceptado, para volcar al índice invertido.
    terminos_por_doc: dict[str, set[str]] = {}

    pendientes = nuevos + actualizados
    progreso = _Progress(len(pendientes), sum(md_stats[r].size for r in pendientes))

    for rel in pendientes:
        md_path = md_files[rel]
        progreso.avanzar(md_stats[rel].size)
        try:
            doc_id, entry, hallazgos, hallazgos_meta, campos_truncados, terminos = _build_entry(
                md_path, md_stats[rel], repo_dir, fallback_pais)
        except Exception as exc:
            _warn(f"Error en {rel}: {exc}")
            errores += 1
            continue

        if hallazgos_meta:
            metadatos[rel] = hallazgos_meta
        if campos_truncados:
            truncados[rel] = campos_truncados

        bloqueantes = [h for h in hallazgos if h.severity == SEVERITY_BLOCK]
        informativos = [h for h in hallazgos if h.severity == SEVERITY_WARN]

        if informativos:
            avisos[rel] = [h.label for h in informativos]
            if args.show_warnings:
                for h in informativos:
                    print(f"  [aviso] {rel}: {h.label} (pos {h.pos}) …{h.snippet}…",
                          file=sys.stderr)

        if bloqueantes:
            etiquetas = [h.label for h in bloqueantes]
            if args.force_index_unsafe:
                # Se indexa igualmente, pero queda constancia en el índice de
                # que alguien bypasseó el bloqueo y de qué se bypasseó.
                forzados[rel] = etiquetas
                print(f"  [FORZADO] {rel}: {', '.join(etiquetas)}", file=sys.stderr)
            else:
                cuarentena[rel] = etiquetas
                for h in bloqueantes:
                    print(f"  [CUARENTENA] {rel}: {h.label} (pos {h.pos})\n"
                          f"      contexto: …{h.snippet}…", file=sys.stderr)
                # Si el fichero ya estaba indexado y ahora resulta sospechoso,
                # se retira: dejarlo servido sería peor que no tenerlo.
                old_doc_id = ruta_a_docid.get(rel)
                if old_doc_id:
                    documentos.pop(old_doc_id, None)
                continue

        old_doc_id = ruta_a_docid.get(rel)
        if old_doc_id and old_doc_id != doc_id and old_doc_id in documentos:
            del documentos[old_doc_id]

        # El `identificador` sale del frontmatter, que es contenido no fiable, y
        # es lo único que el corpus decide y que además es una CLAVE. Sin esta
        # comprobación, dos ficheros que lo repetían colapsaban en una entrada:
        # el último procesado ganaba y el otro documento desaparecía del corpus
        # sin que el resumen lo dijera.
        #
        # Gana el primero y el segundo se queda con un id derivado de su ruta,
        # que es única por construcción. Descartarlo sería perder una ley por
        # culpa de otra; renombrarlas a ambas rompería el id con el que un
        # cliente vuelve a un documento que hoy resuelve bien.
        if doc_id in documentos and documentos[doc_id].get("_ruta") != rel:
            duplicados[rel] = doc_id
            doc_id = f"{doc_id}__{rel.replace('/', '_').removesuffix('.md')}"
            entry["identificador"] = doc_id

        documentos[doc_id] = entry
        # Los términos se registran AQUÍ y no al construir la entrada: aquí el
        # documento ya ha superado la cuarentena y el `doc_id` ya es el
        # definitivo tras resolver duplicados. Indexar antes dejaría un
        # documento en cuarentena encontrable por búsqueda aunque
        # `obtener_ley` se negara a servirlo, que es un agujero y no una
        # defensa.
        terminos_por_doc[doc_id] = terminos

    progreso.cerrar()

    if truncados:
        print(
            f"\n[AVISO] {len(truncados)} fichero(s) con metadatos por encima de "
            f"{_MAX_META_CHARS:,} caracteres. Se indexan recortados.",
            file=sys.stderr,
        )
        for fichero in sorted(truncados):
            print(f"  - {fichero}: {', '.join(truncados[fichero])}", file=sys.stderr)

    # Los metadatos no se ponen en cuarentena: el servidor ya los neutraliza al
    # servirlos y descartar la ley costaría el texto, que es lo que importa. Lo
    # que faltaba era constancia de que el corpus los trae.
    if metadatos:
        print(
            f"\n[AVISO] {len(metadatos)} fichero(s) con patrones de inyección en "
            f"metadatos. Se indexan igualmente; el servidor los filtra al "
            f"servirlos.",
            file=sys.stderr,
        )
        for fichero in sorted(metadatos):
            print(f"  - {fichero}: {', '.join(metadatos[fichero])}", file=sys.stderr)

    # Un identificador repetido es un problema de procedencia del corpus, no de
    # formato, así que se informa fichero a fichero como la cuarentena. El
    # defecto que cerró #20 fue el silencio: el documento perdido no aparecía
    # por ningún lado y "6 escaneados, 5 indexados" se imprimía sin comentario.
    if duplicados:
        print(
            f"\n[AVISO] {len(duplicados)} fichero(s) con un identificador que ya "
            f"reclamaba otro documento. Se indexan con un id derivado de su "
            f"ruta; el primero conserva el original.",
            file=sys.stderr,
        )
        for fichero in sorted(duplicados):
            print(f"  - {fichero}: '{duplicados[fichero]}' ya en uso", file=sys.stderr)

    # La cuarentena es por fichero, nunca global: un puñado de documentos
    # sospechosos no puede dejar sin índice a los otros doce mil.
    if cuarentena:
        print(
            f"\n[SEGURIDAD] {len(cuarentena)} fichero(s) en cuarentena "
            f"(excluidos del índice, el resto se indexa igualmente).",
            file=sys.stderr,
        )
        for fichero in sorted(cuarentena):
            print(f"  - {fichero}: {', '.join(cuarentena[fichero])}", file=sys.stderr)
        repo_arg = args.repo.as_posix()
        print(
            f"\nSi revisaste los ficheros y son legítimos, indéxalos con:\n"
            f"  python scripts/update_index.py --repo {repo_arg} --force-index-unsafe",
            file=sys.stderr,
        )

    if args.remove_orphans:
        for doc_id in huerfanos:
            documentos.pop(doc_id, None)

    try:
        base_dir_str = repo_dir.relative_to(_PROJECT_DIR).as_posix()
    except ValueError:
        base_dir_str = str(repo_dir)

    meta_idx["generado_en"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    meta_idx["total_documentos"] = len(documentos)
    meta_idx["directorio_base"] = base_dir_str
    meta_idx["pais_predeterminado"] = fallback_pais
    meta_idx.setdefault("version", "2.0.0")

    # Estado de seguridad del índice, para que un revisor posterior sepa qué
    # quedó fuera y por qué — o qué se forzó a entrar.
    #
    # Se fusiona con la corrida anterior: una pasada incremental solo escanea
    # los ficheros nuevos o modificados, así que los hallazgos de los que no se
    # tocaron siguen siendo válidos y no pueden desaparecer del registro. Solo
    # se purgan los ficheros que ya no están en disco.
    previo = meta_idx.get("seguridad") or {}
    escaneados = set(pendientes)

    def _fusionar(clave: str, nuevos: dict[str, list[str]]) -> dict[str, list[str]]:
        conservados = {
            f: v for f, v in (previo.get(clave) or {}).items()
            if f in md_files and f not in escaneados
        }
        conservados.update({f: sorted(labels) for f, labels in nuevos.items()})
        return dict(sorted(conservados.items()))

    meta_idx["seguridad"] = {
        # Una pasada que solo reconstruye los postings no escanea nada, así que
        # no puede refrescar la fecha del escaneo: afirmaría una auditoría que
        # no ocurrió.
        "escaneado_en": (datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
                         if pendientes else previo.get("escaneado_en")
                         or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")),
        # Con QUE se auditó, no solo cuándo. Sin esto un cambio de patrón deja
        # el índice con fecha fresca y hallazgos calculados con reglas viejas.
        "patrones": huella_actual,
        "cuarentena": _fusionar("cuarentena", cuarentena),
        "forzados": _fusionar("forzados", forzados),
        "avisos": _fusionar("avisos", avisos),
        # Un identificador repetido dice algo del repositorio de origen, igual
        # que un hallazgo de inyección, así que queda sellado en el índice y no
        # solo impreso en la consola de quien lo generó.
        "duplicados": _fusionar("duplicados", {k: [v] for k, v in duplicados.items()}),
        # La región del frontmatter también queda sellada, así que la huella de
        # reglas de A3 cubre las dos superficies y no solo el cuerpo.
        "metadatos": _fusionar("metadatos", metadatos),
        # Un corpus que entrega títulos de 100 KB dice algo de su procedencia,
        # igual que un identificador repetido o un patrón de inyección.
        "truncados": _fusionar("truncados", truncados),
    }
    # El esquema anterior guardaba esto bajo otra clave; se retira para no dejar
    # dos fuentes de verdad sobre el mismo hecho.
    meta_idx.pop("security_warnings_acknowledged", None)

    commit = legalize_repo.head_commit(repo_dir)
    if commit:
        meta_idx["git_commit"] = commit
    else:
        # Un corpus que no es su propio repositorio no tiene commit que lo
        # identifique. Conservar el anterior sería sellar el índice con el HEAD
        # de otro repositorio, que es justo lo que hacía antes.
        meta_idx.pop("git_commit", None)

    # Los postings van PRIMERO y el JSON después: el JSON es el punto de
    # confirmación. Si se interrumpe entre los dos, el JSON viejo conserva su
    # generación vieja, el desajuste se detecta y la pasada siguiente
    # reconstruye (research.md, R3).
    print("Escribiendo índice invertido …", end=" ", flush=True)
    generacion = legalize_postings.nueva_generacion()
    try:
        postings = _postings_finales(
            postings_previos, documentos, terminos_por_doc, repo_dir)
        n_terminos = _write_invertido(index_path, postings, generacion)
        print("OK")
    except Exception as exc:
        # El índice JSON sigue siendo utilizable sin el invertido: la búsqueda a
        # texto completo se degrada, el resto del servidor no. Fallar entero
        # aquí convertiría un problema de una función en uno de todas.
        print(f"\n[ERROR] no se pudo escribir el índice invertido: {exc}",
              file=sys.stderr)
        n_terminos = 0
        generacion = None

    # Con qué tokenizador se construyó el invertido y a qué generación
    # pertenece. Mismo motivo que la huella del ruleset: sin estos sellos no hay
    # forma de distinguir unos postings buenos de unos construidos con reglas que
    # ya no existen, o para otro JSON.
    #
    # Solo se escriben si los postings se escribieron de verdad (FR-015). Un
    # sello sin postings detrás afirma algo falso, y la pasada siguiente no
    # sabría que tiene que reconstruirlos.
    if generacion:
        meta_idx["tokenizador"] = legalize_tokenizer.huella()
        meta_idx["generacion"] = generacion
    else:
        meta_idx.pop("tokenizador", None)
        meta_idx.pop("generacion", None)

    print(f"Escribiendo índice ({len(documentos):,} docs) …", end=" ", flush=True)
    try:
        _write_atomic(index_path, data)
        print("OK")
    except Exception as exc:
        print(f"\n[ERROR] {exc}", file=sys.stderr)
        sys.exit(1)

    seguridad = meta_idx["seguridad"]
    print(f"Indexados         : {len(documentos):,}")
    print(f"Términos indexados: {n_terminos:,}")
    if seguridad["avisos"]:
        print(f"Avisos            : {len(seguridad['avisos']):,} (informativos, indexados)")
    if seguridad["forzados"]:
        print(f"Forzados          : {len(seguridad['forzados']):,} (indexados pese al bloqueo)")
    if seguridad["cuarentena"]:
        print(f"Cuarentena        : {len(seguridad['cuarentena']):,} (excluidos del índice)")
    if seguridad["duplicados"]:
        print(f"Identificadores duplicados: {len(seguridad['duplicados']):,} "
              f"(indexados con un id derivado de su ruta)")
    if seguridad["metadatos"]:
        print(f"Metadatos sospechosos: {len(seguridad['metadatos']):,} "
              f"(indexados; el servidor los filtra al servirlos)")
    if seguridad["truncados"]:
        print(f"Metadatos truncados: {len(seguridad['truncados']):,} "
              f"(por encima de {_MAX_META_CHARS:,} caracteres)")
    if errores:
        print(f"Errores           : {errores:,}")

    if cuarentena and args.fail_on_quarantine:
        sys.exit(3)

if __name__ == "__main__":
    main()
