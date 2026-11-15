"""Tests that an id resolves the same way whatever countries are searched (#75).

`_resolve_ley` tried each country in turn with exact, case-insensitive and
substring matching, so the countries searched changed the answer:

- an id that matched several laws by substring was ambiguous with `pais` and
  "not found" without it, which is false;
- a unique partial match in an earlier country beat an exact id in a later one;
- an empty id (`""`, `".md"`) is a substring of every id, so a corpus with one
  law served it to a request that named nothing.

Resolution now goes by phase over every country searched — exact, then without
case, then by substring — and a phase only gives way to the next when it finds
nothing.

The asserts go through `obtener_ley` and `obtener_articulo`, the two tools that
resolve an id.
"""

import pytest

import mcp_legalize
from mcp_legalize import ArticuloResultado, ErrorRespuesta, LeyCompleta

TEXTO = "Artículo 1\nUno.\n"


def doc(ruta="x.md"):
    return {"titulo": "Ley de prueba", "_ruta": ruta}


@pytest.fixture
def leer(monkeypatch):
    monkeypatch.setattr(mcp_legalize, "_read_file", lambda d, p: TEXTO)


def ley(id_ley, pais=""):
    return mcp_legalize.obtener_ley.fn(id_ley, pais=pais, solo_metadata=True)


def articulo(id_ley, pais=""):
    return mcp_legalize.obtener_articulo.fn(id_ley, "1", pais=pais)


# ─────────────────────────────────── #75 ─────────────────────────────────────

def test_an_id_ambiguous_across_all_countries_is_ambiguous_not_missing(instalar_corpus, leer):
    instalar_corpus("aa", {"LEY-10": doc()})
    instalar_corpus("bb", {"LEY-12": doc()})

    for resultado in (ley("LEY-1"), articulo("LEY-1")):
        assert isinstance(resultado, ErrorRespuesta)
        assert "ambiguo" in resultado.error
        assert sorted(resultado.sugerencias) == ["LEY-10", "LEY-12"]


def test_an_exact_id_in_a_later_country_beats_a_partial_match_in_an_earlier_one(instalar_corpus, leer):
    instalar_corpus("aa", {"LEY-10": doc()})
    instalar_corpus("bb", {"LEY-1": doc()})

    resultado = ley("LEY-1")
    fragmento = articulo("LEY-1")

    assert isinstance(resultado, LeyCompleta)
    assert (resultado.id, resultado.pais) == ("LEY-1", "bb")
    assert isinstance(fragmento, ArticuloResultado)
    assert (fragmento.id, fragmento.pais) == ("LEY-1", "bb")


def test_a_case_insensitive_id_in_a_later_country_beats_a_partial_match(instalar_corpus):
    instalar_corpus("aa", {"BOJA-b-10": doc()})
    instalar_corpus("bb", {"BOJA-b-1": doc()})

    resultado = ley("boja-B-1")

    assert (resultado.id, resultado.pais) == ("BOJA-b-1", "bb")


@pytest.mark.parametrize("pedido", ["", "   ", ".md", " .MD "])
def test_an_empty_id_names_no_law(instalar_corpus, leer, pedido):
    instalar_corpus("aa", {"LEY-1": doc()})

    for resultado in (ley(pedido), ley(pedido, pais="aa"), articulo(pedido)):
        assert isinstance(resultado, ErrorRespuesta)
        assert "LEY-1" not in resultado.error


def test_the_same_id_in_two_countries_asks_for_the_country(instalar_corpus):
    instalar_corpus("aa", {"LEY-1": doc()})
    instalar_corpus("bb", {"LEY-1": doc()})

    resultado = ley("LEY-1")

    assert isinstance(resultado, ErrorRespuesta)
    assert "pais" in resultado.error
    assert ley("LEY-1", pais="bb").pais == "bb"
