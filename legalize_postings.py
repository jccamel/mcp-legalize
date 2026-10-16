#!/usr/bin/env python3
"""
legalize_postings.py
====================
Única fuente de verdad sobre el formato del índice invertido y sobre cuándo se
puede usar.

Antes los postings se guardaban con pickle, y el servidor los cargaba con
`pickle.load` sobre un fichero que su propio comentario declaraba entrada no
fiable. Quien pudiera escribir en `indices/` ejecutaba código en la primera
búsqueda por texto. El principio II de la constitución lo prohíbe: un fichero no
confiable no se deserializa con un formato que pueda ejecutar código.

Este formato es texto plano y lo lee `str.split` con `int()`. Medido sobre el
corpus español (research.md, R1), además gana al pickle en todo: 75,8 MB en disco
frente a 142,3, 0,16 s de carga frente a 0,36 y 176 MB residentes frente a 394.

    `legalize-postings 1`
    `tokenizador <huella de 12 hex>`
    `generacion <32 hex>`
    `documentos <N>`
    `<id 0>` … `<id N-1>`          una línea por id
    `<término>\\t<d1>,<d2>,…`      una línea por término

Las listas van como deltas sobre la tabla de ids: el primero es el índice, cada
uno de los siguientes es la distancia al anterior y vale al menos 1. Se guardan
crudas al cargar y solo se decodifican las de los términos que se consultan.

Escriben el indexador; leen el servidor y `check_updates.py`. Los tres pasan por
aquí, por el mismo motivo que hay un solo parser de frontmatter y un solo
vocabulario de inyección: dos copias de una regla acaban discrepando.

No importa `mcp_legalize` ni `legalize_tokenizer`. La huella del tokenizador
llega como argumento, para no repetir el ciclo de importaciones que hoy carga el
servidor dos veces cuando se ejecuta como script.
"""

import os
import re
import secrets
import tempfile
from pathlib import Path
from typing import Iterable, Mapping

FIRMA = "legalize-postings 1"

FORMATO_ANTERIOR = "formato_anterior"
SIN_POSTINGS = "sin_postings"
ILEGIBLES = "ilegibles"
TOKENIZADOR_DISTINTO = "tokenizador_distinto"
GENERACION_DISTINTA = "generacion_distinta"

# En el orden en que `estado` los evalúa: gana el primero que se cumple.
MOTIVOS = (FORMATO_ANTERIOR, SIN_POSTINGS, ILEGIBLES, TOKENIZADOR_DISTINTO, GENERACION_DISTINTA)

# El patrón de término del tokenizador. Se repite aquí como validación de
# entrada, no como regla: quien decide qué es un término sigue siendo
# `legalize_tokenizer`, y un fichero cuyos términos no lo cumplen no lo escribió
# el indexador.
_TERMINO_RE = re.compile(r"[0-9a-z]{3,}")
_HUELLA_RE = re.compile(r"[0-9a-f]{12}")
_GENERACION_RE = re.compile(r"[0-9a-f]{32}")


def ruta_postings(directorio: Path, nombre: str) -> Path:
    """El fichero de postings de un índice `index_<nombre>.json`."""
    return Path(directorio) / f"inverted_{nombre}.postings"


def ruta_formato_anterior(directorio: Path, nombre: str) -> Path:
    """El `.bin` en pickle que dejaron las versiones anteriores.

    Solo se usa para saber si existe y para borrarlo. Nunca se abre.
    """
    return Path(directorio) / f"inverted_{nombre}.bin"


def nueva_generacion() -> str:
    """Identificador que ata unos postings al índice JSON que los acompaña.

    Aleatorio y no correlativo: un contador se repite en cuanto alguien
    restaura una copia de seguridad, y un hash del JSON obligaría a leer y
    procesar 19,5 MB en cada arranque (research.md, R3).
    """
    return secrets.token_hex(16)


def escribir(ruta: Path, postings: Mapping[str, Iterable[str]],
             tokenizador: str, generacion: str) -> int:
    """Escribe los postings de forma atómica y devuelve cuántos términos tienen.

    Se escribe a un temporal del mismo directorio y se renombra encima, como el
    índice JSON: un proceso que lea a la vez ve el fichero viejo o el nuevo,
    nunca uno a medias.

    La salida es determinista para que dos índices construidos sobre el mismo
    corpus con la misma generación salgan iguales byte a byte.
    """
    ids = sorted({d for docs in postings.values() for d in docs})
    for doc_id in ids:
        # Un id por línea: un salto dentro de uno desplazaría la tabla entera.
        # El frontmatter no puede traerlo, pero el indexador deriva ids de la
        # ruta cuando dos documentos repiten identificador, y un nombre de
        # fichero sí puede llevarlo.
        if not doc_id or "\n" in doc_id or "\r" in doc_id:
            raise ValueError(f"Id de documento no representable en postings: {doc_id!r}")
    posicion = {doc_id: i for i, doc_id in enumerate(ids)}

    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=ruta.parent, prefix=".inverted_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(f"{FIRMA}\ntokenizador {tokenizador}\ngeneracion {generacion}\n"
                     f"documentos {len(ids)}\n")
            for doc_id in ids:
                fh.write(doc_id + "\n")
            terminos = 0
            for termino in sorted(postings):
                indices = sorted(posicion[d] for d in postings[termino])
                if not indices:
                    continue
                deltas = [indices[0]] + [b - a for a, b in zip(indices, indices[1:])]
                fh.write(termino + "\t" + ",".join(map(str, deltas)) + "\n")
                terminos += 1
        os.replace(tmp, ruta)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return terminos


class Postings:
    """Postings cargados, con las listas sin decodificar hasta que se piden."""

    def __init__(self, tokenizador: str, generacion: str, ids: list[str], crudos: dict[str, str]):
        self.tokenizador = tokenizador
        self.generacion = generacion
        self.ids = ids
        self._crudos = crudos
        # Pasa a ILEGIBLES en cuanto una lista no se puede decodificar, y ya no
        # vuelve: un fichero que mintió en un término no merece crédito en el
        # siguiente.
        self.motivo: str | None = None

    def __contains__(self, termino: str) -> bool:
        return termino in self._crudos

    def terminos(self) -> list[str]:
        return list(self._crudos)

    def indices(self, termino: str) -> set[int]:
        """Las posiciones en `ids` de los documentos que contienen el término."""
        if self.motivo is not None:
            raise ValueError(f"postings {self.motivo}")
        if termino not in self._crudos:
            return set()
        return self._decodificar(termino)

    def docs(self, termino: str) -> set[str]:
        """Los ids de los documentos que contienen el término."""
        return {self.ids[i] for i in self.indices(termino)}

    def _decodificar(self, termino: str) -> set[int]:
        try:
            crudo = self._crudos[termino]
            n = len(self.ids)
            resultado: set[int] = set()
            actual = -1
            for posicion, parte in enumerate(crudo.split(",")):
                delta = int(parte)
                if delta < (0 if posicion == 0 else 1):
                    raise ValueError(f"delta {delta} no válido")
                actual = delta if posicion == 0 else actual + delta
                if actual >= n:
                    raise ValueError(f"índice {actual} fuera de la tabla de {n}")
                resultado.add(actual)
            return resultado
        except ValueError:
            self.motivo = ILEGIBLES
            raise


def _cabecera(linea: str, clave: str) -> str:
    prefijo = clave + " "
    if not linea.startswith(prefijo):
        raise ValueError(f"falta la cabecera {clave!r}")
    return linea[len(prefijo):]


def leer(ruta: Path) -> Postings:
    """Carga un fichero de postings validando su estructura.

    Lanza ValueError si el fichero no se puede leer o no cumple el formato. Las
    listas no se validan aquí, sino al decodificarlas: hacerlo al cargar costaría
    lo mismo que decodificarlas todas, que es justo lo que la carga perezosa
    evita (data-model.md).
    """
    try:
        with Path(ruta).open("r", encoding="utf-8", newline="") as fh:
            lineas = (l[:-1] if l.endswith("\n") else l for l in fh)

            if next(lineas, None) != FIRMA:
                raise ValueError("firma ausente o de otra versión")
            tokenizador = _cabecera(next(lineas, ""), "tokenizador")
            if not _HUELLA_RE.fullmatch(tokenizador):
                raise ValueError("huella de tokenizador mal formada")
            generacion = _cabecera(next(lineas, ""), "generacion")
            if not _GENERACION_RE.fullmatch(generacion):
                raise ValueError("generación mal formada")
            n = int(_cabecera(next(lineas, ""), "documentos"))
            if n < 0:
                raise ValueError("número de documentos negativo")

            ids = []
            for _ in range(n):
                doc_id = next(lineas, None)
                if not doc_id:
                    raise ValueError("faltan ids o hay uno vacío")
                ids.append(doc_id)

            crudos: dict[str, str] = {}
            for linea in lineas:
                termino, tab, lista = linea.partition("\t")
                if not tab:
                    raise ValueError("línea de término sin tabulador")
                if not _TERMINO_RE.fullmatch(termino):
                    raise ValueError(f"término fuera del patrón: {termino!r}")
                if termino in crudos:
                    raise ValueError(f"término repetido: {termino!r}")
                crudos[termino] = lista
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError(f"no se puede leer: {exc}") from exc
    return Postings(tokenizador, generacion, ids, crudos)


def estado(directorio: Path, nombre: str, huella_tokenizador: str,
           generacion_json: str | None) -> tuple[Postings | None, str | None]:
    """Los postings de un índice si se pueden usar, o el motivo por el que no.

    Devuelve `(postings, None)` o `(None, motivo)`, con el motivo de `MOTIVOS`.
    Los motivos se evalúan en ese orden y gana el primero que se cumple: un
    fichero ilegible no tiene sellos que comparar.

    El `.bin` del formato anterior se reconoce por su nombre y nunca se abre, ni
    siquiera para mirar su primer byte.
    """
    ruta = ruta_postings(directorio, nombre)
    if not ruta.exists():
        if ruta_formato_anterior(directorio, nombre).exists():
            return None, FORMATO_ANTERIOR
        return None, SIN_POSTINGS
    try:
        postings = leer(ruta)
    except ValueError:
        return None, ILEGIBLES
    if postings.tokenizador != huella_tokenizador:
        return None, TOKENIZADOR_DISTINTO
    if not generacion_json or postings.generacion != generacion_json:
        return None, GENERACION_DISTINTA
    return postings, None
