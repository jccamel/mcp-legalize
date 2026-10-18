"""Tests that a law is found whatever the case of its id (defect #4).

`_resolve_ley` upper-cased the requested id and then looked it up as-is, while
the indexer stores ids exactly as the frontmatter or the file name gives them.
Any id with a lower-case letter could therefore be listed by `buscar_ley` and
never fetched by `obtener_ley` or `obtener_articulo`. Measured on 2026-10-18:

    legalize-es   245 of 25,889 ids   e.g. BOJA-b-2021-90044
    legalize-se    44 of  8,990 ids   e.g. SFS-1827-60s.1007

plus every purely numeric id, which the indexer prefixes with the lower-case
country code (`yy_12345`).

Comparing without case is safe on today's corpora: no two ids in either one
differ only by case. Where they might, an exact match still wins, and two ids
that tie once case is ignored are reported as ambiguous rather than one being
picked silently. The id returned is always the one stored, never the client's
spelling of it.
"""

import pytest

import mcp_legalize
from mcp_legalize import ErrorRespuesta, LeyCompleta


def doc(titulo="Ley de prueba"):
    return {"titulo": titulo, "_ruta": "x.md"}


@pytest.fixture
def corpus(monkeypatch):
    def con(*ids):
        monkeypatch.setitem(mcp_legalize._DOCS_POR_PAIS, "xx", {i: doc(i) for i in ids})
    return con


def resolver(id_ley):
    return mcp_legalize.obtener_ley.fn(id_ley, pais="xx", solo_metadata=True)


@pytest.mark.parametrize("guardado", [
    "BOJA-b-2021-90044",     # legalize-es
    "SFS-1827-60s.1007",     # legalize-se
    "xx_12345",              # numeric id, prefixed by the indexer
])
def test_an_id_with_lower_case_letters_is_found_as_written(corpus, guardado):
    corpus(guardado, "OTRA-1")

    resultado = resolver(guardado)

    assert isinstance(resultado, LeyCompleta)
    assert resultado.id == guardado


@pytest.mark.parametrize("pedido", ["boja-b-2021-90044", "BOJA-B-2021-90044", " BOJA-b-2021-90044.md "])
def test_the_client_may_spell_the_case_differently(corpus, pedido):
    """The id returned is the stored one, not the client's spelling."""
    corpus("BOJA-b-2021-90044", "OTRA-1")

    resultado = resolver(pedido)

    assert isinstance(resultado, LeyCompleta)
    assert resultado.id == "BOJA-b-2021-90044"


def test_a_partial_id_matches_without_case_too(corpus):
    corpus("SFS-1827-60s.1007", "SFS-1828-79s.1553")

    resultado = resolver("60S.1007")

    assert isinstance(resultado, LeyCompleta)
    assert resultado.id == "SFS-1827-60s.1007"


def test_an_exact_match_wins_over_a_case_insensitive_one(corpus):
    corpus("A-1", "a-1")

    assert resolver("a-1").id == "a-1"
    assert resolver("A-1").id == "A-1"


def test_two_ids_that_tie_once_case_is_ignored_are_ambiguous(corpus):
    """Picking one silently would serve a law the client did not name."""
    corpus("Ab-1", "aB-1")

    resultado = resolver("AB-1")

    assert isinstance(resultado, ErrorRespuesta)
    assert sorted(resultado.sugerencias) == ["Ab-1", "aB-1"]


def test_obtener_articulo_resolves_the_same_way(corpus, monkeypatch):
    corpus("BOJA-b-2021-90044")
    monkeypatch.setattr(mcp_legalize, "_read_file", lambda d, p: "Artículo 1\nUno.\n")

    resultado = mcp_legalize.obtener_articulo.fn("boja-b-2021-90044", "1", pais="xx")

    assert resultado.error is None
    assert resultado.id == "BOJA-b-2021-90044"
