"""Tests that tie the README's factual claims to the code.

Issue #12 was filed because the README had drifted out of line with eleven
merged fixes: metadata sanitization was still documented as English-only, the
worked example printed output the code no longer produces, and the ruleset
fingerprint added in #7 appeared nowhere.

None of that was noticed for two days, because nothing could notice it. The
lesson is the one C1 already taught in `test_config_docs.py`: documentation that
nothing checks is a comment with a wider audience.

These guards cover the claims that name something the code owns — the tool
surface and the index metadata schema. Claims about behaviour are pinned where
that behaviour lives: the error contract in `test_error_contract.py`, the
value-passthrough rule in `test_value_passthrough.py`, the environment variables
in `test_config_docs.py`.
"""

import re
from pathlib import Path

import pytest

import mcp_legalize

README = (Path(__file__).resolve().parent.parent / "README.md").read_text(encoding="utf-8")


def herramientas_registradas() -> set[str]:
    """The names FastMCP actually exposes.

    A decorated tool becomes an object carrying the original function as `.fn`,
    which is also how the rest of the suite calls them.
    """
    return {
        nombre for nombre in dir(mcp_legalize)
        if not nombre.startswith("_") and hasattr(getattr(mcp_legalize, nombre), "fn")
    }


def test_the_readme_documents_every_tool():
    """A tool added without a README row is a tool nobody will call."""
    documentadas = {
        nombre for nombre in herramientas_registradas()
        if f"`{nombre}`" in README
    }

    assert documentadas == herramientas_registradas()


def test_there_are_six_tools():
    """Keeps the test above from passing on an empty set.

    It compares a set against itself filtered by the README, so a broken
    introspection would make it vacuously true.
    """
    assert len(herramientas_registradas()) == 6


# The keys `update_index.py` writes under `_meta.seguridad`. Pinned in
# `test_ruleset_stamp.py` against a real indexer run; repeated here only to
# check that the README's field table lists the same ones.
CAMPOS_SEGURIDAD = ["escaneado_en", "patrones", "cuarentena", "forzados", "avisos"]


@pytest.mark.parametrize("campo", CAMPOS_SEGURIDAD)
def test_the_readme_documents_every_security_field(campo):
    """`patrones` is the one that was missing, and it is the one that matters.

    An auditor reading `_meta.seguridad` needs to know the index records which
    ruleset produced its findings, not only when it was scanned.
    """
    tabla = README[README.index("### Index provenance"):]

    assert f"| `{campo}` |" in tabla


SECCIONES_QUE_CUENTAN_IDIOMAS = [
    pytest.param("#### 2. Metadata sanitization", "#### 3.", id="mitigation-2"),
    pytest.param("#### Covered", "### Operational recommendations", id="covered"),
]


@pytest.mark.parametrize("desde,hasta", SECCIONES_QUE_CUENTAN_IDIOMAS)
def test_the_documented_language_count_matches_the_scanner(desde, hasta):
    """The README claims six languages. It used to claim one, in one of these.

    Asserted per section rather than over the whole document. Both places state
    the count independently, so a document-wide search is satisfied by whichever
    one still says it — which is how the first version of this test passed while
    the claim had been removed from the section that matters.
    """
    idiomas = {p.label.split(".")[0] for p in mcp_legalize.legalize_injection.PATTERNS}
    idiomas -= {"generic", "tech", "meta"}
    assert len(idiomas) == 6

    inicio = README.index(desde)
    seccion = README[inicio:README.index(hasta, inicio)]
    # El ajuste de linea no debe decidir si una afirmacion esta escrita o no:
    # en la seccion 2 la frase cae partida entre dos lineas.
    seccion = " ".join(seccion.split())

    assert "six languages" in seccion


def test_the_readme_does_not_claim_english_only_sanitization():
    """The exact sentence issue #1 A1 made false, kept as a regression guard.

    It survived two days and eleven PRs after the behaviour changed, which is
    what makes it worth naming rather than trusting nobody will write it again.
    """
    assert "Common injection phrases in English" not in README

