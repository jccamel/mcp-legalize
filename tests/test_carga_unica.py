"""Tests that the server is loaded once, and only by what serves (defect #9).

`legalize_tokenizer` imported `mcp_legalize` to reach `_normalize`. The server
imports the tokenizer, so running `python mcp_legalize.py` — the way the README
configures every MCP client — loaded the module twice: once as `__main__` and
once as `mcp_legalize`, each copy reading every index into memory. Reproduced in
the review of 2026-10-16: two `[Legalize MCP] Total:` lines at startup. On the
Spanish corpus that doubles a 0.47 s, 225 MB load.

The same import dragged the whole server into the two operator scripts:
`update_index.py` and `check_updates.py` loaded every index and required
`fastmcp` just to fold accents.

The folding table now lives in `legalize_normalizacion`, which both the server
and the tokenizer import, as the frontmatter, injection and postings rules
already do. Moving it must not change the tokenizer fingerprint: the table is
the same, and every index built under it must stay current.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def correr(codigo: str) -> subprocess.CompletedProcess:
    entorno = {**os.environ, "LEGALIZE_INDICES_DIR": str(RAIZ / "indices"),
               "PYTHONIOENCODING": "utf-8"}
    return subprocess.run([sys.executable, "-W", "ignore", "-c", codigo], cwd=RAIZ,
                          capture_output=True, text=True, encoding="utf-8",
                          env=entorno, timeout=120)


def test_running_the_server_as_a_script_loads_the_indices_once():
    """`run_path` executes the file as a script does, without starting stdio."""
    proc = correr(
        "import runpy, sys\n"
        "runpy.run_path('mcp_legalize.py', run_name='como_script')\n"
        "print('segunda copia:', 'mcp_legalize' in sys.modules)\n"
    )

    assert proc.returncode == 0, proc.stderr
    assert proc.stderr.count("[Legalize MCP] Total:") == 1
    assert "segunda copia: False" in proc.stdout


def test_the_indexer_does_not_need_or_load_the_server():
    """With `fastmcp` unimportable, importing the server would exit with an error."""
    proc = correr(
        "import sys, runpy\n"
        "sys.modules['fastmcp'] = None\n"
        "sys.argv = ['update_index.py', '--self-test']\n"
        "runpy.run_path('scripts/update_index.py', run_name='__main__')\n"
    )

    assert proc.returncode == 0, proc.stderr
    assert "[Legalize MCP]" not in proc.stdout + proc.stderr


def test_the_freshness_check_does_not_need_or_load_the_server():
    proc = correr(
        "import sys, runpy\n"
        "sys.modules['fastmcp'] = None\n"
        "sys.argv = ['check_updates.py']\n"
        "try:\n"
        "    runpy.run_path('scripts/check_updates.py', run_name='__main__')\n"
        "except SystemExit:\n"
        "    pass\n"
    )

    assert "fastmcp" not in proc.stderr
    assert "[Legalize MCP]" not in proc.stdout + proc.stderr
    assert "[MOCK" in proc.stdout


def test_moving_the_table_keeps_every_existing_index_current():
    """The versioned mock index was stamped before the move; its stamp must still match."""
    import legalize_tokenizer

    meta = json.loads((RAIZ / "indices" / "index_legalize-mock.json").read_text(encoding="utf-8"))["_meta"]

    assert legalize_tokenizer.huella() == meta["tokenizador"]


def test_the_server_and_the_tokenizer_fold_text_the_same_way():
    """Principle III: one table, so `consulta` and `texto` cannot diverge."""
    import legalize_tokenizer
    import mcp_legalize

    muestra = "PROTECCIÓN Förordning Çà"

    assert mcp_legalize._normalize(muestra) == "proteccion forordning ca"
    assert legalize_tokenizer.tokens(muestra) == {"proteccion", "forordning"}
