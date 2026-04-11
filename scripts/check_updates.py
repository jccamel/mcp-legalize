#!/usr/bin/env python3
"""
scripts/check_updates.py
========================
Comprueba si algún repositorio de país tiene commits nuevos que no
han sido indexados todavía.

Uso:
    python scripts/check_updates.py

Salida de ejemplo:
    [ES] OK        — índice al día (6d25b87)
    [SE] DESACTUAL — repo en 9f3a1c2, índice en 82b00c0  →  git pull && python scripts/update_index.py --repo repos/legalize-se
    [AT] SIN GIT   — repos/legalize-at no es un repositorio git
    [PT] VACÍO     — el repositorio no tiene commits
"""

import json
import subprocess
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).parent
_PROJECT_DIR = _SCRIPT_DIR.parent
_INDICES_DIR = _PROJECT_DIR / "indices"
_REPOS_DIR   = _PROJECT_DIR / "repos"


def _git_head(repo_dir: Path) -> str:
    try:
        r = subprocess.run(
            ["git", "-C", str(repo_dir), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def main() -> None:
    if not _INDICES_DIR.exists():
        print(f"[ERROR] No se encuentra el directorio de índices: {_INDICES_DIR}", file=sys.stderr)
        sys.exit(1)

    outdated = []

    for index_path in sorted(_INDICES_DIR.glob("index_*.json")):
        try:
            with index_path.open("r", encoding="utf-8") as f:
                meta = json.load(f).get("_meta", {})
        except Exception as exc:
            print(f"[??] {index_path.name}: error al leer — {exc}")
            continue

        pais = meta.get("pais_predeterminado") or index_path.stem.replace("index_", "")
        label = f"[{pais.upper():4}]"
        dir_base = meta.get("directorio_base", "")
        indexed_commit = meta.get("git_commit", "")

        if not dir_base:
            print(f"{label} SIN RUTA  — el índice no tiene 'directorio_base'")
            continue

        repo_dir = _PROJECT_DIR / dir_base
        if not repo_dir.is_dir():
            print(f"{label} SIN REPO  — {repo_dir} no existe")
            continue

        current_commit = _git_head(repo_dir)

        if not current_commit:
            print(f"{label} SIN GIT   — {repo_dir} no es un repositorio git o está vacío")
            continue

        if not indexed_commit:
            print(f"{label} SIN LOCK  — el índice no tiene commit registrado, regenera con --force-all")
            outdated.append(pais)
            continue

        if current_commit == indexed_commit:
            print(f"{label} OK        — índice al día ({current_commit[:7]})")
        else:
            print(
                f"{label} DESACTUAL — repo en {current_commit[:7]}, "
                f"índice en {indexed_commit[:7]}"
                f"\n           → python scripts/update_index.py --repo {dir_base}"
            )
            outdated.append(pais)

    if outdated:
        print(f"\n{len(outdated)} repo(s) desactualizados: {', '.join(outdated)}")
        sys.exit(1)
    else:
        print("\nTodos los índices están al día.")


if __name__ == "__main__":
    main()
