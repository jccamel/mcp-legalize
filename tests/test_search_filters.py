"""Tests for the filters over fields the index already carried.

`departamento`, `fecha_derogacion` and `ultima_actualizacion` were indexed and
returned on every result, but `buscar_ley` had no way to filter on them. The data
was there; the question could not be asked.

Which fields got a filter was decided by cardinality against the live Spanish
corpus, not by adding one per column:

| Field | Documents | Distinct values | Filter |
|---|---|---|---|
| `departamento` | 12,291 | 149 | yes — it groups |
| `fecha_derogacion` | 1,924 | 1,152 | yes, as a range |
| `ultima_actualizacion` | 12,291 | 4,953 | yes, as a range |
| `fuente` | 12,291 | 12,291 | no |
| `identificador` | 12,291 | 12,291 | no |

The last two have one distinct value per document, so filtering on them is
`obtener_ley` with extra steps. A filter that never groups anything is API
surface with no question behind it.

Dates are ranges rather than equality because `fecha_derogacion` alone has 1,152
distinct values; asking for an exact repeal date is not a question anyone has.
They reuse the `fecha_publicacion` convention — ISO strings compared as strings,
which works because the corpus stores `YYYY-MM-DD` throughout, and a bare year
compares correctly as a prefix.

`departamento` matches as a normalized substring, like `rango` and `estado`,
because the values are long official names ("Ministerio de Agricultura, Pesca y
Alimentación") that nobody will type in full.
"""

import pytest

import mcp_legalize


def documento(**campos):
    base = {
        "titulo": "Ley de prueba", "identificador": "XX-1", "pais": "xx",
        "rango": "ley", "estado": "in_force", "fecha_publicacion": "2020-01-01",
        "ultima_actualizacion": "2020-01-01", "fuente": "https://example.test",
        "_ruta": "xx/1.md", "_bytes": 10,
    }
    base.update(campos)
    return base


@pytest.fixture
def corpus(monkeypatch):
    docs = {
        "HACIENDA": documento(
            titulo="Ley tributaria",
            departamento="Ministerio de Economía y Hacienda",
            ultima_actualizacion="2024-06-01",
        ),
        "AGRICULTURA": documento(
            titulo="Ley agraria",
            departamento="Ministerio de Agricultura, Pesca y Alimentación",
            ultima_actualizacion="2020-03-15",
        ),
        "DEROGADA": documento(
            titulo="Ley derogada",
            departamento="Jefatura del Estado",
            estado="repealed",
            fecha_derogacion="2015-05-20",
            ultima_actualizacion="2015-05-20",
        ),
        "SIN_DEPARTAMENTO": documento(titulo="Ley huérfana"),
    }
    monkeypatch.setitem(mcp_legalize._DOCS_POR_PAIS, "tst", docs)
    monkeypatch.setitem(mcp_legalize._META_POR_PAIS, "tst", {})
    monkeypatch.setitem(mcp_legalize._INDEX_FILE_POR_PAIS, "tst", "index_tst")
    return docs


def ids(resultados):
    return sorted(r.id for r in resultados)


# ─────────────────────────────── departamento ────────────────────────────────

def test_departamento_matches_a_substring(corpus):
    """Nobody types "Ministerio de Agricultura, Pesca y Alimentación" in full."""
    assert ids(mcp_legalize.buscar_ley.fn(pais="tst", departamento="agricultura")) == ["AGRICULTURA"]


def test_departamento_ignores_case_and_accents(corpus):
    """Same normalization the other text filters use."""
    assert ids(mcp_legalize.buscar_ley.fn(pais="tst", departamento="ECONOMIA")) == ["HACIENDA"]


def test_departamento_excludes_documents_that_have_none(corpus):
    """An absent field must not match, rather than matching everything."""
    resultados = mcp_legalize.buscar_ley.fn(pais="tst", departamento="ministerio")

    assert "SIN_DEPARTAMENTO" not in ids(resultados)


def test_no_departamento_filter_returns_everything(corpus):
    """The filter must cost nothing when it is not used."""
    assert len(mcp_legalize.buscar_ley.fn(pais="tst")) == 4


# ─────────────────────────── fecha_derogacion ────────────────────────────────

def test_derogadas_desde_selects_by_repeal_date(corpus):
    assert ids(mcp_legalize.buscar_ley.fn(pais="tst", derogada_desde="2015-01-01")) == ["DEROGADA"]


def test_derogadas_hasta_excludes_later_repeals(corpus):
    assert mcp_legalize.buscar_ley.fn(pais="tst", derogada_hasta="2010-01-01") == []


def test_a_law_that_was_never_repealed_is_not_returned_by_a_repeal_filter(corpus):
    """The field is empty on 10,367 of the 12,291 Spanish documents.

    An empty value must not be treated as "before any date" — asking which laws
    were repealed before 2020 must not return every law still in force.
    """
    resultados = mcp_legalize.buscar_ley.fn(pais="tst", derogada_hasta="2020-01-01")

    assert ids(resultados) == ["DEROGADA"]


# ───────────────────────── ultima_actualizacion ──────────────────────────────

def test_actualizada_desde_selects_recent_revisions(corpus):
    assert ids(mcp_legalize.buscar_ley.fn(pais="tst", actualizada_desde="2024-01-01")) == ["HACIENDA"]


def test_actualizada_hasta_selects_stale_ones(corpus):
    assert ids(mcp_legalize.buscar_ley.fn(pais="tst", actualizada_hasta="2016-01-01")) == ["DEROGADA"]


def test_a_bare_year_works_as_a_bound(corpus):
    """ISO strings compare as strings, so "2024" is a valid lower bound."""
    assert ids(mcp_legalize.buscar_ley.fn(pais="tst", actualizada_desde="2024")) == ["HACIENDA"]


# ───────────────────────────── combinations ──────────────────────────────────

def test_filters_combine(corpus):
    """Each filter narrows; they are not alternatives."""
    resultados = mcp_legalize.buscar_ley.fn(
        pais="tst", departamento="ministerio", actualizada_desde="2024-01-01",
    )

    assert ids(resultados) == ["HACIENDA"]


def test_a_filter_that_matches_nothing_returns_nothing(corpus):
    assert mcp_legalize.buscar_ley.fn(pais="tst", departamento="inexistente") == []
