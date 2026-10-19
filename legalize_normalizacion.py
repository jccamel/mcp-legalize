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

Cómo se pliega (ADR 0008). Antes una tabla enumeraba a mano las vocales
acentuadas; lo que no listaba sobrevivía al plegado y el patrón de término
`[0-9a-z]` partía la palabra. Medido el 2026-10-18: 875 palabras francesas
rotas (`être` → "tre", `arrêté` → "arr", `œuvre` → "uvre") y 1.864 españolas
(`año` sin término, `España` → "espa"). Ahora:

- Se quitan todas las marcas diacríticas tras la descomposición canónica (NFD),
  así que un idioma que nadie enumeró también se pliega. Solo canónica: NFKD
  reescribiría ordinales y ligaduras (`1º`, `ﬁ`), que no son diacríticos.
- La `ñ` se conserva como letra: plegarla a `n` juntaría año con ano y uña con
  una. El tokenizador la admite en su patrón.
- Una tabla pequeña cubre lo que Unicode no descompone (œ, æ, ß, ø, ł) y el
  punto volado catalán, que partía `col·legi`.

Sigue plegando å ä ö a a a o, como aceptó el ADR 0004 para el sueco.

No importa nada del proyecto. La función entera forma parte de la huella del
tokenizador, así que cambiar cómo se pliega invalida los índices construidos
antes, que el indexador reconstruye solo.
"""

import re
import unicodedata

# Letras que la descomposición canónica no separa en base + marca, y el punto
# volado catalán. Se aplican tras quitar las marcas.
TABLA = str.maketrans({
    "œ": "oe", "æ": "ae", "ß": "ss", "ø": "o", "ł": "l", "đ": "d",
    "·": "",
})

# Marcas combinantes de los bloques diacríticos. Tras NFD son ellas las que
# llevan el acento, la diéresis, la cedilla o el anillo.
_MARCAS_RE = re.compile("[̀-ͯ᪰-᫿᷀-᷿⃐-⃿︠-︯]")

# Letras que NFD separa en base + marca pero que son letras propias de su
# alfabeto, no vocales acentuadas: plegarlas funde palabras distintas. Se
# recomponen antes de quitar las marcas.
#   - `ñ`: *año* no es *ano* (ADR 0008).
#   - `й`, `ї`, `ў`: en ruso, búlgaro, ucraniano y bielorruso son letras del
#     alfabeto; `йод` (yodo) no es `иод` (ADR 0010).
# `ё` no está: plegarla a `е` es la equivalencia habitual al buscar en ruso.
_CONSERVADAS = {
    "n\u0303": "\u00f1",
    "\u0438\u0306": "\u0439",
    "\u0456\u0308": "\u0457",
    "\u0443\u0306": "\u045e",
}


def normalizar(texto: str) -> str:
    """Minúsculas y diacríticos plegados, para comparar; nunca para servir.

    Todo son operaciones en C —`lower`, `normalize`, `replace`, `sub`,
    `translate`—, porque el tokenizador pasa por aquí el corpus entero.
    """
    descompuesto = unicodedata.normalize("NFD", texto.lower())
    for separada, letra in _CONSERVADAS.items():
        descompuesto = descompuesto.replace(separada, letra)
    return _MARCAS_RE.sub("", descompuesto).translate(TABLA)
