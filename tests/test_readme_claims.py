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


def test_there_are_seven_tools():
    """Keeps the test above from passing on an empty set.

    It compares a set against itself filtered by the README, so a broken
    introspection would make it vacuously true.

    Was six until #31 added `contar_leyes`. The count is asserted rather than
    left open on purpose: a new tool on the public surface should require
    someone to notice, and this failing is that notice.
    """
    assert len(herramientas_registradas()) == 7


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



# ──────────────────────────────── badges ─────────────────────────────────────
#
# A badge is a claim in the most visible line of the page, and the one a reader
# is least likely to check. Each one is tied here to the file that decides it.

RAIZ = Path(__file__).resolve().parent.parent
CI = (RAIZ / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
BADGE = re.compile(r"\[!\[([^\]]*)\]\(([^)\s]+)\)\]\(([^)\s]+)\)")


def badges() -> dict[str, tuple[str, str]]:
    """Badge alt text -> (image URL, link), for the badges above the first heading break."""
    cabecera = README[:README.index("\n---\n")]
    return {alt: (imagen, enlace) for alt, imagen, enlace in BADGE.findall(cabecera)}


def test_the_ci_badge_reports_the_workflow_that_actually_runs():
    """A badge for a workflow file that was renamed shows "no status" forever."""
    imagen, enlace = badges()["CI"]
    flujo = re.search(r"/actions/workflows/([\w.-]+)/badge\.svg", imagen).group(1)

    assert (RAIZ / ".github" / "workflows" / flujo).is_file()
    assert "branch=main" in imagen
    assert enlace.endswith(f"/actions/workflows/{flujo}")


def test_the_python_badge_lists_exactly_the_versions_ci_tests():
    """The README states 3.10 as the floor; the badge must not promise more or less than CI runs."""
    imagen, _ = next(v for alt, v in badges().items() if alt.startswith("Python"))
    from urllib.parse import unquote

    en_badge = re.findall(r"3\.\d+", unquote(imagen))
    matriz = re.search(r"python-version:\s*\[([^\]]+)\]", CI).group(1)

    assert en_badge == re.findall(r"3\.\d+", matriz)


def test_the_license_badge_names_the_license_in_the_file():
    imagen, enlace = next(v for alt, v in badges().items() if alt.startswith("License"))
    licencia = (RAIZ / "LICENSE").read_text(encoding="utf-8").splitlines()[0].split()[0]

    assert f"license-{licencia}" in imagen
    assert enlace == "LICENSE"
