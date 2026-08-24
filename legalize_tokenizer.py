"""Tokenizador para la búsqueda a texto completo.

Un solo sitio decide qué es un término, por el mismo motivo que `legalize_frontmatter`
decide qué es frontmatter y `legalize_injection` qué es un patrón: dos copias de
la misma regla divergen, y aquí una divergencia significa que `texto` y `consulta`
dejarían de coincidir sobre los mismos documentos.

Es de PRESENCIA, no de frecuencia: un documento contiene un término o no lo
contiene. Es lo que decidió #31 al elegir intersección de conjuntos frente a
ranking, y lo que mantiene los postings en ~85 MB para el corpus español en vez
del doble. Ordenar por relevancia es una opinión sobre qué ley importa más, y
este servidor no opina — devuelve lo que dice la fuente.
"""

import hashlib
import inspect
import re

import legalize_frontmatter
import mcp_legalize

# Longitud mínima de un término. Por debajo quedan las palabras vacías —"de",
# "la", "y"— que aparecen en casi todos los documentos: engordan cada lista de
# postings y no separan nada al buscarlas.
_MIN_LONGITUD = 3

# Qué cuenta como término. Se aplica sobre texto YA normalizado, así que las
# vocales acentuadas ya vienen plegadas y no hay que enumerarlas aquí.
#
# Esto explica por qué el tokenizador español funciona sin cambios sobre el
# corpus sueco: `_NORMALIZE_TABLE` pliega å ä ö antes de que este patrón las
# vea. Que ese plegado sea correcto para el sueco es otra cuestión, medida y
# abierta en #32.
_PATRON_TOKEN = re.compile(rf"[0-9a-z]{{{_MIN_LONGITUD},}}")

# Presencia o frecuencia. Entra en la huella a propósito: si algún día se guarda
# la frecuencia para poder ordenar por relevancia, los índices construidos con
# el modo anterior tienen que quedar invalidados en vez de mezclarse en silencio
# con los nuevos.
_MODO = "presencia"


def tokens(texto: str) -> set[str]:
    """Los términos de un texto, sin repetir.

    Normaliza con la misma tabla que usa `buscar_ley`. Si divergieran, buscar
    `protección` por título y por texto daría resultados distintos sobre el
    mismo documento.
    """
    return set(_PATRON_TOKEN.findall(mcp_legalize._normalize(texto)))


def tokens_de_documento(documento: str) -> set[str]:
    """Los términos del CUERPO de un documento, sin el frontmatter.

    El frontmatter se sirve y se escanea aparte: sus campos ya son buscables por
    `buscar_ley`. Indexarlo aquí haría que un término del título apareciera como
    coincidencia de cuerpo, que es otra pregunta distinta de la que responde
    `texto`.
    """
    return tokens(legalize_frontmatter.cuerpo(documento))


def huella() -> str:
    """Huella del tokenizador: identifica CON QUÉ se construyó un índice.

    Misma razón que `legalize_injection.huella`, y por eso la misma forma. Un
    índice que registra cuándo se construyó pero no bajo qué reglas no se puede
    distinguir de uno caducado sin reconstruirlo a ciegas.

    Es una huella del contenido y no un número de versión a mano: lo que depende
    de que alguien se acuerde de actualizarlo, se desincroniza.

    Cubre todo lo que cambia qué documentos devuelve una consulta:
    - la forma canónica del patrón de token, con sus flags;
    - la longitud mínima, que hoy vive dentro del patrón pero debe seguir
      contando si algún día se saca de ahí;
    - la tabla de normalización, aunque viva en `mcp_legalize`: es parte del
      tokenizador aunque no esté en este fichero, y #32 propone justamente
      cambiarla para el sueco;
    - la regla de recorte del frontmatter, que decide qué es cuerpo;
    - presencia frente a frecuencia.
    """
    tabla = mcp_legalize._NORMALIZE_TABLE
    partes = [
        _PATRON_TOKEN.pattern,
        str(_PATRON_TOKEN.flags),
        str(_MIN_LONGITUD),
        _MODO,
        # Ordenada para que reordenar la tabla sin cambiarla no cueste un
        # reíndice, igual que las etiquetas del escáner van ordenadas.
        repr(sorted(tabla.items())),
        # El código de `separar` y no su delimitador: la regla de qué cuenta
        # como frontmatter está en la lógica —qué cierra el bloque, qué pasa si
        # no cierra—, no solo en la cadena "---". A2 se abrió precisamente
        # porque dos implementaciones cortaban en sitios distintos.
        inspect.getsource(legalize_frontmatter.separar),
    ]
    return hashlib.sha256("\x00".join(partes).encode("utf-8")).hexdigest()[:12]
