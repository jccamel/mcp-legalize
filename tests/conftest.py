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
import sys
from pathlib import Path

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


@pytest.fixture(scope="session")
def update_index():
    """The indexer script, exposed as a fixture.

    Importing it straight from conftest (`from conftest import update_index`)
    only works under pytest's default `prepend` import mode; it raises on
    `--import-mode=importlib`. Fixtures are resolved by pytest itself, so they
    work under either mode.
    """
    return _update_index
