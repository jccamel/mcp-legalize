#!/usr/bin/env python3
"""
`legalize_normalizacion.py`
===========================
Única fuente de verdad sobre cómo se pliega el texto para comparar.

La usan el servidor, para filtrar por título, rango, estado, jurisdicción y
departamento, y el tokenizador, para construir y consultar el índice invertido.
Las dos superficies tienen que plegar igual: si divergieran, buscar
`PROTECCIÓN` por título y por texto daría resultados distintos sobre el mismo
documento.

Antes la tabla vivía en `mcp_legalize` y el tokenizador importaba el servidor
entero para alcanzarla. Como el servidor importa el tokenizador, ejecutar
`python mcp_legalize.py` cargaba el módulo dos veces —como `__main__` y como
`mcp_legalize`—, cada copia con todos los índices en memoria, y los dos scripts
del operador arrancaban el servidor y exigían `fastmcp` solo para plegar
acentos (defecto #9).

No importa nada del proyecto. La tabla forma parte de la huella del
tokenizador, así que cambiarla invalida los índices construidos con la anterior.
"""

_DIACRITICS_SRC = 'áéíóúàèìòùäëïöüñçåæøÄËÏÖÜÑÇÅÆØ'
_DIACRITICS_DST = 'aeiouaeiouaeiouñcaaoaeiouñcaao'
TABLA = str.maketrans(_DIACRITICS_SRC, _DIACRITICS_DST)


def normalizar(texto: str) -> str:
    """Minúsculas y diacríticos plegados, para comparar; nunca para servir."""
    return texto.lower().translate(TABLA)
