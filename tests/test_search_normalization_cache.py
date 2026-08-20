"""Tests for issue #15: `buscar_ley` must not re-normalize the corpus per request.

Every request re-lowercased and re-translated all 12,291 titles through a
30-entry table. Measured on the live Spanish corpus, `_normalize` was 886 ms of
an 896 ms request — 99.3% of the work — and none of it was reused.

The `break` on `limite` hid it. It only fires when results are *found*, so a
query that matched a hundred documents cost 12 ms while a query that matched
none cost 900 ms, and `limite=1` cost exactly as much as `limite=100`.

These tests count normalization calls instead of measuring wall-clock time.
Timing assertions are too flaky for CI, and the count is the honest statement of
the defect anyway: the complaint was never "this is slow", it was "this work is
repeated". A cache that stops the repetition satisfies the count; one that
merely got faster would not.

The cache is lazy by decision: the startup path stays untouched, and a server
whose clients never search by title never pays for it. The cost lands on the
first title search instead, which is why one test pins that the second request
does no normalization at all.
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
    """Un país con documentos suficientes para que repetir el trabajo se note."""
    docs = {
        f"DOC-{i}": documento(titulo=f"Ley {i} de ordenación territorial")
        for i in range(50)
    }
    monkeypatch.setitem(mcp_legalize._DOCS_POR_PAIS, "tst", docs)
    monkeypatch.setitem(mcp_legalize._META_POR_PAIS, "tst", {})
    monkeypatch.setitem(mcp_legalize._INDEX_FILE_POR_PAIS, "tst", "index_tst")
    return docs


@pytest.fixture
def contar_normalize(monkeypatch):
    """Cuenta las llamadas a `_normalize` sobre títulos del corpus.

    Solo cuenta las que reciben un título: `buscar_ley` normaliza también los
    argumentos de la consulta, y esas llamadas son una por petición, no una por
    documento — no son el trabajo que este issue persigue.
    """
    llamadas = []
    original = mcp_legalize._normalize

    def espia(text):
        if text.startswith("Ley ") and "ordenación" in text:
            llamadas.append(text)
        return original(text)

    monkeypatch.setattr(mcp_legalize, "_normalize", espia)
    return llamadas


def test_a_repeated_search_does_not_renormalize_the_corpus(corpus, contar_normalize):
    """The second identical request must reuse the first one's work."""
    mcp_legalize.buscar_ley.fn(consulta="ordenación", pais="tst", limite=10)
    contar_normalize.clear()

    mcp_legalize.buscar_ley.fn(consulta="ordenación", pais="tst", limite=10)

    assert contar_normalize == []


def test_a_different_query_reuses_the_same_cached_titles(corpus, contar_normalize):
    """The cache keys on the document, not on the query."""
    mcp_legalize.buscar_ley.fn(consulta="ordenación", pais="tst", limite=10)
    contar_normalize.clear()

    mcp_legalize.buscar_ley.fn(consulta="territorial", pais="tst", limite=10)

    assert contar_normalize == []


def test_an_unmatched_query_is_no_more_expensive_than_a_matched_one(corpus, contar_normalize):
    """The defect's signature: a query returning nothing scanned everything.

    Both queries walk all 50 documents — one because it matches them all and is
    capped by `limite`, the other because it matches none. Neither may normalize
    a title twice.
    """
    mcp_legalize.buscar_ley.fn(consulta="ordenación", pais="tst", limite=100)
    contar_normalize.clear()

    mcp_legalize.buscar_ley.fn(consulta="zzzznope", pais="tst", limite=100)

    assert contar_normalize == []


def test_a_search_without_a_query_never_normalizes_a_title(corpus, contar_normalize):
    """No `consulta` means no title comparison, so no title work at all.

    This is what keeps the cache lazy: a client that only filters by country or
    status must not trigger the corpus-wide normalization.
    """
    mcp_legalize.buscar_ley.fn(pais="tst", limite=10)

    assert contar_normalize == []


def test_the_cache_does_not_change_which_documents_match(corpus):
    """Accent- and case-insensitive matching must survive the optimization."""
    for consulta in ["ordenación", "ORDENACION", "ordenacion", "Ordenación"]:
        resultados = mcp_legalize.buscar_ley.fn(consulta=consulta, pais="tst", limite=100)
        assert len(resultados) == 50, f"falló con {consulta!r}"


def test_a_title_edited_in_the_index_is_not_served_from_a_stale_cache(corpus):
    """A reloaded index must not keep the previous title's normalized form.

    The cache lives beside the document, so replacing the document replaces its
    cache. This pins that a future keyed-by-id cache would not silently serve
    stale titles.
    """
    mcp_legalize.buscar_ley.fn(consulta="ordenación", pais="tst", limite=100)

    corpus["DOC-0"] = documento(titulo="Ley completamente distinta")

    assert mcp_legalize.buscar_ley.fn(consulta="completamente", pais="tst", limite=10)
