"""Tests that tie the configuration docs to the configuration code.

Issue #1 C1, C2 and C3 were all one failure: the code read four environment
variables, the module docstring listed three, the README listed the same three
*and* pointed the reader at the docstring for the rest. Nothing connected the
two, so the docs drifted the moment a fourth variable was added — the same shape
as the duplicated frontmatter parsers and the duplicated injection vocabularies,
except the second copy was prose.

Documentation that nothing checks is a comment with a wider audience. These
tests make the three descriptions of one fact fail together when they disagree.

They also pin the two claims a reader would act on, because a limit that is
really a default and a default that is really a limit are the kind of thing
prose gets wrong silently:

    LEGALIZE_MAX_LIMIT          a hard cap — `limite` is clamped to it
    LEGALIZE_MAX_CONTENT_CHARS  only a default — a caller may ask for more
"""

import inspect
import re
from pathlib import Path

import pytest

import mcp_legalize

RAIZ = Path(__file__).resolve().parent.parent
FUENTE = (RAIZ / "mcp_legalize.py").read_text(encoding="utf-8")
README = (RAIZ / "README.md").read_text(encoding="utf-8")
DOCSTRING = mcp_legalize.__doc__ or ""

NOMBRE = re.compile(r"LEGALIZE_[A-Z_]+")


def variables_leidas() -> set[str]:
    """The variables the code actually reads."""
    return set(re.findall(r'os\.environ\.get\(\s*"(LEGALIZE_[A-Z_]+)"', FUENTE))


# ─────────────────────────── The three descriptions agree ────────────────────

def test_the_code_reads_the_variables_the_docstring_lists():
    assert set(NOMBRE.findall(DOCSTRING)) == variables_leidas()


def test_the_readme_lists_the_same_variables():
    assert set(NOMBRE.findall(README)) == variables_leidas()


def test_there_is_something_to_check():
    """Guards the two tests above against passing on an empty set.

    Both compare sets, so a regex that stopped matching would make them pass by
    finding nothing anywhere. This is the assertion that makes them mean
    something.
    """
    assert len(variables_leidas()) == 4


def defaults_del_codigo() -> dict[str, str]:
    """Variable -> literal default, for the ones that have a literal one."""
    hallados = re.findall(r'os\.environ\.get\(\s*"(LEGALIZE_[A-Z_]+)",\s*"([^"]*)"\s*\)', FUENTE)
    return {nombre: valor for nombre, valor in hallados if valor}


@pytest.mark.parametrize("variable,valor", sorted(defaults_del_codigo().items()))
def test_the_documented_default_matches_the_code(variable, valor):
    """A default documented as a different number is worse than none at all."""
    assert f"(default: {valor})" in tramo(DOCSTRING, variable)
    assert f"`{valor}`" in tramo(README, variable)


def tramo(texto: str, variable: str) -> str:
    """The slice of `texto` that describes `variable`, up to the next one.

    Both the docstring entry and the README row wrap or extend past the variable
    name, and a naive whole-document search would let one variable's default
    satisfy another's assertion.
    """
    inicio = texto.index(variable)
    siguiente = NOMBRE.search(texto, inicio + len(variable))
    return texto[inicio:siguiente.start() if siguiente else len(texto)]


def test_no_configuration_file_is_advertised():
    """`python-dotenv` was removed in `1d332bb`; the docstring kept promising it.

    A reader who creates the `.env` the docs describe gets a file that is never
    read and configuration that silently does nothing.
    """
    assert ".env" not in DOCSTRING
    assert ".env" not in README


# ─────────────────────────── The claims are true ─────────────────────────────

def test_max_limit_is_a_hard_cap(monkeypatch):
    """Documented as clamping silently, so a caller cannot exceed it."""
    docs = {
        f"XX-{i}": {
            "titulo": f"Ley {i}", "identificador": f"XX-{i}", "pais": "xx",
            "rango": "ley", "estado": "in_force", "fecha_publicacion": "2020-01-01",
            "ultima_actualizacion": "2020-01-01", "fuente": "https://example.test",
            "_ruta": f"xx/{i}.md",
        }
        for i in range(mcp_legalize.MAX_LIMIT + 50)
    }
    monkeypatch.setitem(mcp_legalize._DOCS_POR_PAIS, "xx", docs)

    resultados = mcp_legalize.buscar_ley.fn(limite=mcp_legalize.MAX_LIMIT + 50)

    assert isinstance(resultados, list)
    assert len(resultados) == mcp_legalize.MAX_LIMIT


@pytest.mark.parametrize(
    "herramienta,parametro",
    [("obtener_ley", "max_chars"), ("obtener_articulo", "contexto_chars")],
)
def test_max_content_chars_is_only_a_default(herramienta, parametro):
    """Documented as *not* a cap — it seeds a parameter the caller can raise.

    Asserted through the signature because that is exactly what the claim is
    about: the value reaches the caller as a default, and nothing clamps the
    argument afterwards.
    """
    firma = inspect.signature(getattr(mcp_legalize, herramienta).fn)

    assert firma.parameters[parametro].default == mcp_legalize.MAX_CONTENT_CHARS
    assert f"min({parametro}" not in FUENTE
