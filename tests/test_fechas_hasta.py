"""Tests that a date bound means the whole period it names (defect #6).

The date filters compared strings as they came, and every date in both corpora
is `YYYY-MM-DD` (measured on 2026-10-18). A bound of `"2001"` is documented as
valid, but `"2001-05-01" > "2001"` as strings, so `fecha_hasta="2001"` excluded
every law of 2001 — the opposite of what anyone writing it means. Reproduced in
the review of 2026-10-16: with two laws, `fecha_hasta="2001"` counted 1 and
`fecha_desde="2001"` counted 2.

Each date is now compared truncated to the precision of the bound, so a bound
names a whole year, a whole month or a single day, inclusively at both ends.
The same rule applies to the three ranges: publication, repeal and last update.
"""

import pytest

import mcp_legalize

FECHAS = ["2000-12-31", "2001-01-01", "2001-06-15", "2001-12-31", "2002-01-01"]


@pytest.fixture
def corpus(monkeypatch):
    docs = {
        f"F-{i}": {
            "titulo": f"Ley {i}", "_ruta": "x.md",
            "fecha_publicacion": f, "fecha_derogacion": f, "ultima_actualizacion": f,
        }
        for i, f in enumerate(FECHAS)
    }
    monkeypatch.setitem(mcp_legalize._DOCS_POR_PAIS, "xx", docs)
    return docs


def fechas(**filtros):
    """The publication dates `buscar_ley` returns, checked against `contar_leyes`."""
    encontrados = mcp_legalize.buscar_ley.fn(pais="xx", limite=100, **filtros)
    assert mcp_legalize.contar_leyes.fn(pais="xx", **filtros).total == len(encontrados)
    return sorted(r.fecha_publicacion for r in encontrados)


@pytest.mark.parametrize("prefijo", ["fecha", "derogada", "actualizada"])
def test_an_upper_bound_of_a_year_includes_the_whole_year(corpus, prefijo):
    """The reproduction: "until 2001" must include 2001."""
    assert fechas(**{f"{prefijo}_hasta": "2001"}) == FECHAS[:4]


@pytest.mark.parametrize("prefijo", ["fecha", "derogada", "actualizada"])
def test_an_upper_bound_of_a_month_includes_the_whole_month(corpus, prefijo):
    assert fechas(**{f"{prefijo}_hasta": "2001-06"}) == FECHAS[:3]


@pytest.mark.parametrize("prefijo", ["fecha", "derogada", "actualizada"])
def test_a_full_date_bound_is_inclusive(corpus, prefijo):
    assert fechas(**{f"{prefijo}_hasta": "2001-06-15"}) == FECHAS[:3]
    assert fechas(**{f"{prefijo}_desde": "2001-06-15"}) == FECHAS[2:]


@pytest.mark.parametrize("prefijo", ["fecha", "derogada", "actualizada"])
def test_a_lower_bound_of_a_year_starts_at_its_first_day(corpus, prefijo):
    assert fechas(**{f"{prefijo}_desde": "2001"}) == FECHAS[1:]


def test_a_range_of_one_year_equals_the_year_filter(corpus):
    assert fechas(fecha_desde="2001", fecha_hasta="2001") == fechas(anno="2001") == FECHAS[1:4]
