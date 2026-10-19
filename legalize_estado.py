#!/usr/bin/env python3
"""
`legalize_estado.py`
====================
Única fuente de verdad sobre cuándo el título de una ley contradice a su estado
(spec 004, ADR 0012).

El corpus del Reino Unido trae todas sus leyes con `status: in_force` y marca
al final del título las que ya no lo están: `Licensing Act 1964 (repealed)`,
`… (revoked)`, `… (Repealed 25.10.1991)`. Medido el 2026-10-19: 594 de 86.671
títulos, y ninguna de esas leyes trae `repeal_date`, `repealed_by` ni
`end_of_validity`. En es, eu, fr y se, ninguno de 53.569 títulos.

El estado no se corrige: se sirve tal como lo da la fuente (ADR 0001). Lo que
sale de aquí es un aviso aparte, que el servidor calcula al servir, y el estado
bajo el que el índice archiva la ley para el filtro. Las dos cosas usan las
mismas funciones, así que no pueden discrepar.

No importa nada del proyecto: lo usan `legalize_indice` y el servidor.
"""

import hashlib
import inspect
import re

# El paréntesis final del título, si empieza por `repealed` o `revoked`, con lo
# que lleve detrás (fecha, excepciones). Medido el 2026-10-19 sobre los 86.671
# títulos UK: casa con las 594 leyes que tienen `repealed` o `revoked` entre
# paréntesis en cualquier sitio del título, también las cuatro irregulares
# (`15/02/1999`, `1. 4. 1991`, `and superseded`, sin espacio antes), y con
# ninguna otra. `re.ASCII` porque con IGNORECASE en Unicode el signo Kelvin
# (U+212A) casa con la `k` de `revoked`: un título manipulado podría parecer
# una marca sin llevar la palabra.
_MARCA_RE = re.compile(r"\((?:repealed|revoked)\b[^()]*\)\s*$", re.IGNORECASE | re.ASCII)

# Los estados que una marca contradice. Una ley `repealed`, `expired`… ya dice
# que no está en vigor: la marca no añade nada.
ESTADOS_CONTRADECIBLES = ("", "in_force")

# Bajo qué estado archiva el filtro una ley con aviso. `revoked` también: es la
# palabra de la fuente para la legislación secundaria (34 leyes).
ESTADO_ARCHIVADO = "repealed"


def marca_derogacion(titulo) -> str | None:
    """La marca de derogación del final de `titulo`, literal, o None."""
    if not isinstance(titulo, str):
        return None
    m = _MARCA_RE.search(titulo)
    return m.group(0).rstrip() if m else None


def aviso(estado, titulo) -> str | None:
    """La marca del título si contradice al estado, o None.

    Los dos valores salen del índice, que es entrada no confiable: uno que no
    sea texto no contradice nada.
    """
    if not isinstance(estado, str) or estado.strip() not in ESTADOS_CONTRADECIBLES:
        return None
    return marca_derogacion(titulo)


def estado_filtrable(estado, titulo) -> str:
    """El estado bajo el que el filtro encuentra la ley: `repealed` si hay aviso."""
    return ESTADO_ARCHIVADO if aviso(estado, titulo) else estado


def huella() -> str:
    """Huella de la regla: identifica con qué regla se archivó un índice.

    Entra en el formato del índice (`legalize_indice.FORMATO`): si la regla
    cambia, un índice archivado con la anterior daría un filtro de estado que
    no corresponde, así que deja de servirse y se reconstruye. Es una huella
    del contenido, como la del tokenizador, y no un número que haya que
    acordarse de subir.
    """
    partes = [
        _MARCA_RE.pattern,
        str(_MARCA_RE.flags),
        repr(ESTADOS_CONTRADECIBLES),
        ESTADO_ARCHIVADO,
        inspect.getsource(marca_derogacion),
        inspect.getsource(aviso),
        inspect.getsource(estado_filtrable),
    ]
    return hashlib.sha256("\x00".join(partes).encode("utf-8")).hexdigest()[:12]
