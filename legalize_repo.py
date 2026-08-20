#!/usr/bin/env python3
"""
legalize_repo.py
================
Única fuente de verdad sobre qué commit identifica a un corpus.

`update_index.py` sella el commit en el índice y `check_updates.py` lo compara
con el del disco. Son los dos lados de un mismo contrato y cada uno tenía su
propia copia de la consulta a git, palabra por palabra — la misma forma de
deriva que este proyecto ya arregló en el parser de frontmatter y en el
vocabulario de inyección.
"""

import subprocess
from pathlib import Path


def head_commit(corpus_dir: Path) -> str:
    """El HEAD del repositorio git cuya RAÍZ es `corpus_dir`, o "" si no lo es.

    Exigir la raíz no es un detalle. `git -C <dir>` sube por el árbol hasta
    encontrar el primer `.git`, así que un directorio que solo está *dentro* de
    un repositorio devuelve el HEAD del repositorio que lo contiene.
    `repos/legalize-mock` vive dentro de este mismo proyecto: su índice quedaba
    sellado con el HEAD de mcp-legalize, se declaraba desactualizado en cuanto
    se hacía cualquier commit aquí, y como ese índice está versionado, ensuciaba
    el árbol de trabajo cada vez que alguien reindexaba.

    Devolver "" es la respuesta correcta y no una degradación: un corpus que no
    es su propio repositorio no tiene un commit que lo identifique, y fingir uno
    prestado es precisamente el error.
    """
    corpus_dir = Path(corpus_dir)
    try:
        raiz = subprocess.run(
            ["git", "-C", str(corpus_dir), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=5,
        )
        if raiz.returncode != 0:
            return ""
        declarada = raiz.stdout.strip()
        if not declarada or Path(declarada).resolve() != corpus_dir.resolve():
            return ""

        head = subprocess.run(
            ["git", "-C", str(corpus_dir), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        return head.stdout.strip() if head.returncode == 0 else ""
    except Exception:
        # Sin git instalado, con un repo corrupto o con un timeout, la respuesta
        # honesta es la misma: no sabemos qué commit identifica este corpus.
        return ""
