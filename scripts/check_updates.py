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
    [ES] REGLAS    — auditado con 03446b5a64e4, el escáner está en 9f21c0a3e1bb

Comprueba además con qué reglas de escaneo se auditó cada índice. Un índice
puede estar al día en commits y aun así llevar hallazgos calculados con un
ruleset que ya no existe, porque una pasada incremental no vuelve a mirar los
ficheros que no cambiaron en disco.
"""

import json
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).parent
_PROJECT_DIR = _SCRIPT_DIR.parent
_INDICES_DIR = _PROJECT_DIR / "indices"
_REPOS_DIR   = _PROJECT_DIR / "repos"

# Igual que en update_index.py: este script corre como `python scripts/...`, así
# que sys.path arranca en scripts/ y la raíz del proyecto no es importable.
if str(_PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(_PROJECT_DIR))

import legalize_injection  # noqa: E402  (requiere el sys.path de arriba)
import legalize_repo  # noqa: E402  (idem)
import legalize_tokenizer  # noqa: E402  (idem)


def main() -> None:
    # La consola de Windows usa cp1252 por defecto, que no sabe codificar la
    # flecha de las sugerencias, así que el script reventaba con
    # UnicodeEncodeError justo cuando tenía algo que decir: al reportar un
    # índice desactualizado. Con errors="replace" se degrada el carácter en
    # vez de perderse el informe entero.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

    if not _INDICES_DIR.exists():
        print(f"[ERROR] No se encuentra el directorio de índices: {_INDICES_DIR}", file=sys.stderr)
        sys.exit(1)

    outdated = []
    huella_actual = legalize_injection.huella()
    huella_tok_actual = legalize_tokenizer.huella()

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

        # El ruleset es ortogonal al commit: un índice puede estar al día en
        # disco y llevar una auditoría hecha con reglas ya retiradas.
        huella_indice = (meta.get("seguridad") or {}).get("patrones", "")
        if huella_indice != huella_actual:
            if huella_indice:
                motivo = (f"auditado con {huella_indice}, "
                          f"el escáner está en {huella_actual}")
            else:
                motivo = (f"no registra con qué reglas se auditó; "
                          f"el escáner está en {huella_actual}")
            print(
                f"{label} REGLAS    — {motivo}"
                f"\n           → python scripts/update_index.py --repo {dir_base}"
            )
            outdated.append(pais)

        # El tokenizador es ortogonal a las otras dos comprobaciones por el
        # mismo motivo que el ruleset lo es al commit: un índice puede estar al
        # día en disco y auditado con las reglas vigentes, y aun así llevar
        # listas de postings construidas con un patrón de token, una longitud
        # mínima o una tabla de normalización que ya cambiaron.
        huella_tok_indice = meta.get("tokenizador", "")
        if huella_tok_indice != huella_tok_actual:
            if huella_tok_indice:
                motivo = (f"tokenizado con {huella_tok_indice}, "
                          f"el tokenizador está en {huella_tok_actual}")
            else:
                # Un índice anterior a que esto existiera no lleva sello. Darlo
                # por vigente dejaría a cada índice previo reclamando un
                # tokenizador con el que nunca se construyó.
                motivo = (f"no registra con qué tokenizador se construyó; "
                          f"el tokenizador está en {huella_tok_actual}")
            print(
                f"{label} TOKENS    — {motivo}"
                f"\n           → python scripts/update_index.py --repo {dir_base}"
            )
            outdated.append(pais)

        current_commit = legalize_repo.head_commit(repo_dir)

        if not current_commit:
            print(f"{label} SIN GIT   — {repo_dir} no es la raíz de un "
                  f"repositorio git, o no tiene commits")
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
        # Un mismo repo puede entrar por reglas y por commit; se cuenta una vez.
        unicos = list(dict.fromkeys(outdated))
        print(f"\n{len(unicos)} repo(s) desactualizados: {', '.join(unicos)}")
        sys.exit(1)
    else:
        print("\nTodos los índices están al día.")


if __name__ == "__main__":
    main()
