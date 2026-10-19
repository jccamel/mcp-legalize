#!/usr/bin/env python3
"""Decide si una orden es una ejecución de tests que se puede aprobar sola.

Lo llama `filtrar-tests.sh` con la orden como único argumento. Si se aprueba,
escribe en stdout sus argumentos ya separados, como lista JSON, y sale con 0;
si no, sale con 1 y la orden sigue el flujo normal de permisos.

Antes el hook miraba solo el verbo: todo lo que empezaba por `pytest` o `npm
test` se aprobaba fuera cual fuera el resto. `pytest -p modulo` carga y ejecuta
un plugin arbitrario, `-o addopts=-pmodulo` hace lo mismo por la configuración,
`--basetemp=<dir>` vacía ese directorio y `npm test` o `make test` ejecutan lo
que el repositorio defina. Ahora se aprueba solo lo que este proyecto ejecuta:
pytest con argumentos de una lista blanca y rutas bajo `tests/`, y el
`--self-test` exacto del escáner.

Los argumentos que se devuelven son los que se ejecutan, sin volver a pasar por
un shell: validar el texto y ejecutarlo con `bash -c` dejaba que bash expandiera
después variables o comodines (`-k ${IFS}-p${IFS}modulo` se convertía en
`-p modulo`).
"""

# El hook lo ejecuta con el `python3` del PATH, que puede ser más antiguo que
# el del proyecto (el de macOS es 3.9): nada de sintaxis posterior en tiempo de
# ejecución.
from __future__ import annotations

import json
import re
import shlex
import sys

_PYTHON = re.compile(r"(\.venv/bin/)?python3?")
_SIN_VALOR = re.compile(
    r"-[qv]+|-r[a-zA-Z]+|-[xsl]|--(lf|ff|sw|co|collect-only|strict-markers|no-header)"
    r"|--tb=(short|long|line|no|native|auto)|--(maxfail|durations)=\d+"
    r"|--import-mode=(prepend|append|importlib)")
# Una ruta bajo tests/, sin `..`, con un id de test opcional detrás de `::`.
_RUTA = re.compile(r"tests(/[\w.-]+)*(::[^/\s]+)*")


def _es_ruta_de_tests(arg: str) -> bool:
    ruta = arg.split("::", 1)[0]
    return bool(_RUTA.fullmatch(arg)) and ".." not in ruta.split("/")


def argumentos(orden: str) -> list[str] | None:
    """Los argumentos de `orden` si se puede aprobar sola; None si no."""
    try:
        tokens = shlex.split(orden)
    except ValueError:
        return None
    if tokens[:1] == ["pytest"]:
        resto = tokens[1:]
    elif len(tokens) >= 3 and _PYTHON.fullmatch(tokens[0]) and tokens[1:3] == ["-m", "pytest"]:
        resto = tokens[3:]
    elif (len(tokens) == 3 and _PYTHON.fullmatch(tokens[0])
          and tokens[1:] == ["scripts/update_index.py", "--self-test"]):
        return tokens
    else:
        return None

    i = 0
    while i < len(resto):
        arg = resto[i]
        siguiente = resto[i + 1] if i + 1 < len(resto) else None
        if _SIN_VALOR.fullmatch(arg) or _es_ruta_de_tests(arg):
            i += 1
        elif arg in ("-k", "-m") and siguiente is not None and not siguiente.startswith("-"):
            # La expresión la interpreta pytest con su propia gramática de
            # nombres, sin evaluar código.
            i += 2
        elif arg == "-p" and siguiente is not None and re.fullmatch(r"no:[\w.]+", siguiente):
            # Solo para DESACTIVAR un plugin; activar uno es ejecutar código.
            i += 2
        elif arg == "-o" and siguiente == "addopts=":
            # Solo para vaciar `addopts`; cualquier otro valor podría añadir
            # opciones que esta lista no ha visto.
            i += 2
        else:
            return None
    return tokens


if __name__ == "__main__":
    resultado = argumentos(sys.argv[1]) if len(sys.argv) == 2 else None
    if resultado is None:
        sys.exit(1)
    print(json.dumps(resultado))
