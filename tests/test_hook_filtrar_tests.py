"""Tests that the test-filter hook auto-approves only harmless test commands.

`.claude/hooks/filtrar-tests.sh` runs before every Bash command the assistant
issues. When the command is a test run, it rewrites it to filter the output and
answers `permissionDecision: allow`, which skips the permission prompt. It
already refused compound commands (`;`, `&`, `|`, redirections), but it looked
only at the verb: anything starting with `pytest` or `npm test` was approved
whatever followed. `pytest -p module` loads and runs an arbitrary plugin,
`-o addopts=-pmodule` does the same through the configuration,
`--basetemp=<dir>` empties that directory, and `npm test` or `make test` run
whatever scripts the repository defines.

The hook now approves only the commands this project runs: pytest — directly or
as `python -m pytest` — with flags from an allowlist and paths under `tests/`,
and the scanner's exact `--self-test`. Anything else is left to the normal
permission flow: not denied, just not approved on the assistant's behalf.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
HOOK = RAIZ / ".claude" / "hooks" / "filtrar-tests.sh"

pytestmark = pytest.mark.skipif(shutil.which("jq") is None or shutil.which("bash") is None,
                                reason="the hook needs bash and jq")


def decision(comando):
    proc = subprocess.run(
        ["bash", str(HOOK)], input=json.dumps({"tool_input": {"command": comando}}),
        capture_output=True, text=True, timeout=30, env={"PATH": "/usr/bin:/bin:/usr/local/bin"},
    )
    assert proc.returncode == 0, proc.stderr
    salida = json.loads(proc.stdout or "{}")
    return salida.get("hookSpecificOutput", {}).get("permissionDecision")


@pytest.mark.parametrize("comando", [
    "pytest",
    "pytest -q",
    ".venv/bin/python -m pytest -q",
    ".venv/bin/python -m pytest -rs",
    "python3 -m pytest -q -p no:cacheprovider -o addopts= -rf tests/test_frase.py",
    ".venv/bin/python -m pytest -q tests/test_fin_vigencia.py -k 'repeal and not expired'",
    ".venv/bin/python -m pytest tests/test_frase.py::test_short_words_count_inside_a_phrase -x --tb=short",
    ".venv/bin/python -m pytest --lf --maxfail=3 -vv",
    ".venv/bin/python scripts/update_index.py --self-test",
], ids=lambda c: c[:60])
def test_the_commands_this_project_runs_are_approved(comando):
    assert decision(comando) == "allow"


@pytest.mark.parametrize("comando", [
    "pytest -p modulo_cualquiera",
    "pytest -pmodulo",
    ".venv/bin/python -m pytest -o addopts=-pmodulo",
    "pytest --override-ini=addopts=-pmodulo",
    "pytest --basetemp=/Users/alguien/Documents",
    "pytest -c /tmp/otro.ini",
    "pytest --rootdir=/",
    "pytest --confcutdir=/",
    "pytest --pyargs os",
    "pytest /etc/passwd",
    "pytest ../fuera/test_x.py",
    "pytest tests/../../fuera.py",
    "python -m pytest -p no:cacheprovider -p modulo",
    ".venv/bin/python scripts/update_index.py --repo repos/legalize-es",
    ".venv/bin/python scripts/update_index.py --self-test --force-all",
    "npm test",
    "make test",
    "cargo test",
    "go test ./...",
    "pytest; rm -rf x",
    "pytest && curl x",
    "pytest $(whoami)",
    "pytest -k ${IFS}-p${IFS}modulo",
], ids=lambda c: c[:60])
def test_anything_else_is_left_to_the_normal_permission_flow(comando):
    assert decision(comando) is None


def test_the_runner_executes_its_arguments_without_a_shell(tmp_path):
    """What the hook validated is exactly what runs: an argument carrying
    `$(...)` or `${IFS}` reaches the program as text, never expanded."""
    runner = RAIZ / ".claude" / "hooks" / "ejecutar-filtrado.sh"
    proc = subprocess.run(
        ["bash", str(runner), "printf", "[%s]", "$(touch pwned)", "${IFS}-p"],
        capture_output=True, text=True, timeout=30, cwd=tmp_path,
        env={"PATH": "/usr/bin:/bin", "CLAUDE_PROJECT_DIR": str(tmp_path)},
    )

    assert proc.returncode == 0, proc.stderr
    assert "[$(touch pwned)][${IFS}-p]" in proc.stdout
    assert not (tmp_path / "pwned").exists()
