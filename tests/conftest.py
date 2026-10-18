"""Shared test setup.

`mcp_legalize` opens every `indices/index_*.db` at import time, so the
environment variable that points at that directory MUST be set before
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
    indice = tmp_path / "index.db"

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

    def leer() -> dict:
        """The index as `{"_meta", "documentos"}`, read through the hardened path."""
        import legalize_indice
        return legalize_indice.como_dict(indice) if indice.exists() else {}

    def poner_meta(clave: str, valor) -> None:
        """Overwrites a meta entry, as whoever controls the file could."""
        import json
        import sqlite3
        con = sqlite3.connect(indice)
        con.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (clave, json.dumps(valor)))
        con.commit()
        con.close()

    def texto_buscable() -> dict[str, set[str]]:
        """`{term: ids}` of the full-text table, limited to what the tokenizer
        calls a term. The table indexes short words too; the query side never
        asks for them, so they are left out of what a test compares."""
        import sqlite3
        import legalize_tokenizer
        con = sqlite3.connect(indice)
        con.execute("CREATE VIRTUAL TABLE temp.vocab USING fts5vocab(main, cuerpo, 'instance')")
        salida: dict[str, set[str]] = {}
        for termino, id_ley in con.execute(
                "SELECT v.term, l.id FROM temp.vocab v JOIN leyes l ON l.n = v.doc"):
            if legalize_tokenizer.tokens(termino) == {termino}:
                salida.setdefault(termino, set()).add(id_ley)
        con.close()
        return salida

    return SimpleNamespace(repo=repo, indice=indice, correr=correr, leer=leer,
                           poner_meta=poner_meta, texto_buscable=texto_buscable)


@pytest.fixture
def crear_indice():
    """Writes an index database with the given meta and documents.

    `crear(ruta, meta, documentos=None)`, for the tests that hand
    `check_updates.py` an index in a particular state. Each meta value is
    written as is, so a test can leave a stamp out or set a stale one.
    """
    import legalize_indice

    def crear(ruta, meta, documentos=None):
        escritor = legalize_indice.Escritor(ruta)
        for clave, valor in meta.items():
            escritor.poner_meta(clave, valor)
        for doc_id, entry in (documentos or {}).items():
            escritor.poner_ley(doc_id, entry, "")
        escritor.confirmar()
        return ruta

    return crear


@pytest.fixture
def instalar_corpus(tmp_path, monkeypatch):
    """Installs a real per-corpus index database and registers it in the server.

    Spec 002 moved the index from dictionaries in memory to a SQLite database
    per corpus. Tests used to inject dictionaries into `_DOCS_POR_PAIS`; they now
    describe the same documents and this fixture writes them with the indexer's
    own writer, so every test exercises the real database rather than a
    stand-in.

    `instalar(pais, documentos, cuerpos=None, meta=None)`:
    - `documentos`: `{id: entry}` with the keys the JSON index had
      (`titulo`, `rango`, `_ruta`, ...);
    - `cuerpos`: `{id: body}`; each is also written to its `_ruta` under a
      temporary `LEGALIZE_REPOS_DIR`, so `obtener_ley` reads it from disk;
    - `meta`: extra meta entries (for example a different `tokenizador`).

    Can be called more than once to install several countries. The server's
    tables are restored after the test.
    """
    import legalize_indice
    import legalize_tokenizer
    import mcp_legalize

    repos = tmp_path / "repos"
    indices = tmp_path / "indices_instalados"
    monkeypatch.setattr(mcp_legalize, "REPOS_DIR", repos)
    for tabla in ("_CONEXIONES", "_META_POR_PAIS", "_INDEX_FILE_POR_PAIS",
                  "_RAIZ_POR_PAIS", "_TEXTO_NO_DISPONIBLE"):
        monkeypatch.setattr(mcp_legalize, tabla, {})

    def instalar(pais, documentos, cuerpos=None, meta=None):
        cuerpos = cuerpos or {}
        raiz = repos / f"legalize-{pais}"
        raiz.mkdir(parents=True, exist_ok=True)
        escritor = legalize_indice.Escritor(legalize_indice.ruta_indice(indices, f"legalize-{pais}"))
        for doc_id, entry in documentos.items():
            entry = {"pais": pais, **entry}
            cuerpo = cuerpos.get(doc_id, "")
            ruta = entry.get("_ruta")
            if isinstance(ruta, str) and ruta and not ruta.startswith("/") and ".." not in ruta:
                destino = raiz / ruta
                destino.parent.mkdir(parents=True, exist_ok=True)
                destino.write_text(cuerpo, encoding="utf-8")
            escritor.poner_ley(doc_id, entry, cuerpo)
        datos_meta = {"pais_predeterminado": pais, "directorio_base": str(raiz),
                      "tokenizador": legalize_tokenizer.huella(), **(meta or {})}
        for clave, valor in datos_meta.items():
            escritor.poner_meta(clave, valor)
        escritor.confirmar()
        mcp_legalize._registrar_indice(
            legalize_indice.ruta_indice(indices, f"legalize-{pais}"), repos.resolve())
        return raiz

    return instalar
