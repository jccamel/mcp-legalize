"""One diacritics convention for the Spanish prose in this codebase.

Issue #1 D2 started as "the security block in `update_index.py` lost its
accents while the rest of the file kept them". By the time it came up for fixing
the scope had changed, and not in our favour: the A1 refactor removed most of
that block, and the comments written to replace it matched the surrounding ASCII
style instead of correcting it. The mixed state had also spread to
`legalize_injection.py`, `check_updates.py` and `conftest.py` — every one of
them written or edited during this issue.

So this is not a one-off cleanup. It is the same failure as C1: a convention
that only exists in someone's head drifts the moment someone else writes a line,
and the person who broke it here was us, three times, without noticing.

The guard scans prose only — comments and docstrings — and skips anything inside
backticks or quotes, because `indices/` is a path, `version` is a JSON key and
`linea` is a variable. Code keeps its ASCII identifiers; this is about the text
a human reads.
"""

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent

# Forms that are unambiguously missing an accent in Spanish prose. Each one is a
# real word only in its accented spelling, so a hit is always a defect.
SIN_TILDE = {
    "asi": "así", "tambien": "también", "tamano": "tamaño", "vacia": "vacía",
    "inyeccion": "inyección", "decision": "decisión", "auditoria": "auditoría",
    "sustitucion": "sustitución", "busqueda": "búsqueda", "posicion": "posición",
    "habia": "había", "podia": "podía", "crecia": "crecía", "tenia": "tenía",
    "minusculas": "minúsculas", "mayusculas": "mayúsculas", "unico": "único",
    "unica": "única", "multilingue": "multilingüe", "deteccion": "detección",
    "informacion": "información", "comprobacion": "comprobación",
    "despues": "después", "segun": "según", "atras": "atrás", "codigo": "código",
    "numero": "número", "raiz": "raíz", "practica": "práctica", "estan": "están",
    "aqui": "aquí", "actuan": "actúan", "ademas": "además", "dia": "día",
    "dias": "días", "ultimo": "último", "ultima": "última", "facil": "fácil",
    "dificil": "difícil", "rapido": "rápido", "quedo": "quedó",
    "caracter": "carácter", "excepcion": "excepción", "funcion": "función",
    "condicion": "condición", "ejecucion": "ejecución", "validacion": "validación",
    "generacion": "generación", "seleccion": "selección", "expresion": "expresión",
    "operacion": "operación", "aplicacion": "aplicación", "razon": "razón",
    "configuracion": "configuración", "documentacion": "documentación",
    "implementacion": "implementación", "verificacion": "verificación",
    "normalizacion": "normalización", "resolucion": "resolución",
    "proteccion": "protección", "interpretacion": "interpretación",
    "direccion": "dirección", "metodo": "método", "parametro": "parámetro",
    "parametros": "parámetros", "automatico": "automático", "estatico": "estático",
    "dinamico": "dinámico", "generico": "genérico", "especifico": "específico",
    "tecnico": "técnico", "publico": "público", "minimo": "mínimo",
    "maximo": "máximo", "optimo": "óptimo", "tipico": "típico", "critico": "crítico",
    "analisis": "análisis", "termino": "término", "logica": "lógica",
    "politica": "política", "garantia": "garantía", "proximo": "próximo",
    "aparecio": "apareció", "corrio": "corrió", "aca": "acá", "alla": "allá",
}

# Deliberately absent, and each for a reason worth writing down. Adding any of
# these would make the guard fire on correct Spanish, and a guard that cries
# wolf gets deleted.
#
#   aun / aún      "aun así" is correct without the accent
#   hacia / hacía  a preposition and a verb, both real
#   esta / está    a determiner and a verb
#   mas / más      an archaic conjunction and an adverb
#   solo / sólo    the accent is optional since 2010
#   seria / sería  an adjective and a verb
#   pais, articulo, titulo, version, linea, modulo
#                  all of them are parameter names or JSON keys that
#                  legitimately appear un-accented inside prose
#   indice/indices `LEGALIZE_INDICES_DIR` appears bare in the server docstring,
#                  outside any backticks. Tried including it; it fired there.
#   extension, dimension
#                  ordinary English words, and English appears in prose here
#                  whenever a technical term is quoted
#   limite         the name of a `buscar_ley` parameter
AMBIGUAS = {"aun", "hacia", "esta", "mas", "solo", "seria", "pais", "articulo",
            "titulo", "version", "linea", "modulo", "indice", "indices",
            "extension", "dimension", "limite"}

assert not (SIN_TILDE.keys() & AMBIGUAS), "una forma no puede estar en las dos listas"

PALABRA = re.compile(r"[A-Za-z]+")
# Backticks and quoted literals name code, not prose.
CODIGO_EN_PROSA = re.compile(r"`[^`]*`|\"[^\"]*\"|'[^']*'")


def lineas_de_prosa(texto: str):
    """Comment and docstring lines, with their line numbers."""
    dentro_de_docstring = False
    for numero, linea in enumerate(texto.splitlines(), 1):
        despojada = linea.strip()
        es_prosa = despojada.startswith("#") or dentro_de_docstring or despojada.startswith('"""')
        if despojada.count('"""') % 2 == 1:
            dentro_de_docstring = not dentro_de_docstring
        if es_prosa and despojada:
            yield numero, despojada


def ficheros_del_proyecto():
    """The modules whose prose is Spanish.

    `tests/` is excluded on purpose: its docstrings are written in English, and
    several forms on the list above are ordinary English words — `decision` and
    `indices` most obviously. Running a Spanish accent check over English prose
    produces confident nonsense.

    Which language each surface should speak is D1, a separate item with a
    decision behind it. This guard only enforces the convention where Spanish is
    already the convention.
    """
    for patron in ("*.py", "scripts/*.py"):
        yield from sorted(RAIZ.glob(patron))


@pytest.mark.parametrize(
    "fichero", list(ficheros_del_proyecto()), ids=lambda f: f.name
)
def test_spanish_prose_keeps_its_diacritics(fichero):
    hallazgos = []
    for numero, linea in lineas_de_prosa(fichero.read_text(encoding="utf-8")):
        for palabra in PALABRA.findall(CODIGO_EN_PROSA.sub(" ", linea)):
            correcta = SIN_TILDE.get(palabra.lower())
            if correcta and correcta != palabra.lower():
                hallazgos.append(f"{fichero.name}:{numero} {palabra} -> {correcta}")

    assert hallazgos == []


def test_the_guard_would_notice():
    """A word list this specific can rot into matching nothing.

    The test above passes on a clean tree either way, so without this one a typo
    in the list — or a change to how prose is detected — would look identical to
    success.
    """
    prosa = '# Esto se escribio asi, y tambien la comprobacion quedo sin tilde.\n'

    hallados = [
        SIN_TILDE[p.lower()]
        for _, l in lineas_de_prosa(prosa)
        for p in PALABRA.findall(CODIGO_EN_PROSA.sub(" ", l))
        if p.lower() in SIN_TILDE
    ]

    assert sorted(hallados) == ["así", "comprobación", "quedó", "también"]


def test_code_inside_prose_is_left_alone():
    """`indices/` is a directory and `version` is a JSON key, not bad spelling."""
    prosa = '# El fichero va a `indices/` y la clave "version" no lleva tilde.\n'

    hallados = [
        p for _, l in lineas_de_prosa(prosa)
        for p in PALABRA.findall(CODIGO_EN_PROSA.sub(" ", l))
        if p.lower() in SIN_TILDE
    ]

    assert hallados == []
