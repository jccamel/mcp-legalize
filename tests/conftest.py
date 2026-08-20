"""Shared test setup.

`mcp_legalize` loads every `indices/index_*.json` into memory at import time,
so the environment variable that points at that directory MUST be set before
the module is first imported. pytest loads conftest before any test module,
which makes this the only reliable place to do it.

Pointing it at a non-existent directory keeps the suite independent of whatever
the developer happens to have cloned under `repos/`.
"""

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

os.environ["LEGALIZE_INDICES_DIR"] = str(_PROJECT_ROOT / "tests" / "_no_such_indices")

if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def _load_module_from_path(name: str, path: Path):
    """Import a standalone script that is not part of an importable package."""
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_update_index = _load_module_from_path(
    "update_index", _PROJECT_ROOT / "scripts" / "update_index.py"
)

_check_updates = _load_module_from_path(
    "check_updates", _PROJECT_ROOT / "scripts" / "check_updates.py"
)


@pytest.fixture(scope="session")
def update_index():
    """The indexer script, exposed as a fixture.

    Importing it straight from conftest (`from conftest import update_index`)
    only works under pytest's default `prepend` import mode; it raises on
    `--import-mode=importlib`. Fixtures are resolved by pytest itself, so they
    work under either mode.
    """
    return _update_index


@pytest.fixture(scope="session")
def check_updates():
    """The staleness-check script, exposed as a fixture for the same reason."""
    return _check_updates


@pytest.fixture
def indexer_cli(tmp_path):
    """Runs the indexer as the CLI it is, in an isolated repo and index.

    The ruleset stamp is decided inside `main()` — reading the previous index,
    comparing fingerprints, choosing what to rescan — so testing it through the
    module's helpers would test something other than what runs in production.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    indice = tmp_path / "index.json"

    # El hijo escribe su informe con la codificacion de la consola, que en
    # Windows es cp1252. Sin forzarla, los acentos llegan aquí como caracteres
    # de reemplazo y cualquier assert sobre un mensaje real falla por el
    # transporte y no por el comportamiento.
    entorno = {**os.environ, "PYTHONIOENCODING": "utf-8"}

    def correr(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(_PROJECT_ROOT / "scripts" / "update_index.py"),
             "--repo", str(repo), "--index", str(indice), *args],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            env=entorno, timeout=120,
        )

    return SimpleNamespace(repo=repo, indice=indice, correr=correr)
