#!/usr/bin/env python3
"""
legalize_repo.py
================
Única fuente de verdad sobre dónde está un corpus y qué commit lo identifica.

`update_index.py` sella el commit en el índice y `check_updates.py` lo compara
con el del disco. Son los dos lados de un mismo contrato y cada uno tenía su
propia copia de la consulta a git, palabra por palabra — la misma forma de
deriva que este proyecto ya arregló en el parser de frontmatter y en el
vocabulario de inyección.

La raíz de un corpus sale del índice, que es entrada no confiable (principio
II), así que también vive aquí la regla que la contiene dentro del directorio
que autoriza el operador: la aplican el servidor, antes de leer un documento,
y `check_updates.py`, antes de ejecutar git en ella.
"""

import os
import subprocess
from pathlib import Path


def raiz_del_corpus(directorio_base: str, proyecto: Path, autorizada: Path) -> Path:
    """La raíz de un corpus, resuelta y comprobada contra el directorio autorizado.

    El índice puede decir dónde está su corpus, pero solo dentro de
    `autorizada` (`LEGALIZE_REPOS_DIR`): puede elegir, no ampliar. La raíz se
    calcula relativa a `proyecto` o absoluta, y se resuelve con los enlaces
    seguidos antes de comprobar la contención, así que ni `..` ni un enlace
    dentro del directorio autorizado que apunte fuera la cumplen.

    Lanza ValueError si queda fuera o no es texto.
    """
    if not isinstance(directorio_base, str):
        raise ValueError(f"'directorio_base' no es texto: {directorio_base!r}")
    raiz = (Path(proyecto) / directorio_base).resolve()
    autorizada = Path(autorizada).resolve()
    if not raiz.is_relative_to(autorizada):
        raise ValueError(
            f"el corpus {directorio_base!r} está fuera de LEGALIZE_REPOS_DIR ({str(autorizada)!r})"
        )
    return raiz


# Nada de la configuración del propio repositorio puede hacer que git ejecute
# una orden. `rev-parse` no refresca el índice de git, así que hoy no dispara
# `core.fsmonitor` ni ganchos; se desactivan igualmente, porque el corpus es
# entrada no confiable y lo que hoy no ejecuta una orden de git puede hacerlo en
# una versión futura. La primera barrera es `raiz_del_corpus`.
_GIT = ["git", "-c", "core.fsmonitor=false", "-c", f"core.hooksPath={os.devnull}",
        "--no-optional-locks"]
_ENTORNO_GIT = {"GIT_CONFIG_NOSYSTEM": "1", "GIT_PAGER": "cat", "PAGER": "cat",
                "GIT_TERMINAL_PROMPT": "0"}


def _git(corpus_dir: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [*_GIT, "-C", str(corpus_dir), *args],
        capture_output=True, text=True, timeout=5, env={**os.environ, **_ENTORNO_GIT},
    )


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
        raiz = _git(corpus_dir, "rev-parse", "--show-toplevel")
        if raiz.returncode != 0:
            return ""
        declarada = raiz.stdout.strip()
        if not declarada or Path(declarada).resolve() != corpus_dir.resolve():
            return ""

        head = _git(corpus_dir, "rev-parse", "HEAD")
        return head.stdout.strip() if head.returncode == 0 else ""
    except Exception:
        # Sin git instalado, con un repo corrupto o con un timeout, la respuesta
        # honesta es la misma: no sabemos qué commit identifica este corpus.
        return ""
