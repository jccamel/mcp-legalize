"""Tests for `contar_leyes` (#31, part 4 of 4).

Without ranking, the first N results are arbitrary — corpus order, not
relevance. `buscar_ley` returns a bare list and never says how many results
exist, which was tolerable while a title substring filtered hard enough that
hitting `MAX_LIMIT` was unusual. With full text it is not: an assistant handed
100 documents out of 1,092, with no signal that 992 were withheld, reasons as if
it had seen the whole answer.

**A count is what makes an unranked search honest.** The client needs to tell
*"these are the 24 laws"* from *"these are 100 of 1,092, in no particular order"*.

Why a separate tool rather than a `total` field on `buscar_ley`: the field would
change the return type from `list[DocumentoResumen] | ErrorRespuesta` to a
wrapper object, breaking every existing caller — 16 call sites in this repository
alone treat the result as a list, and every MCP client breaks the same way
*silently*, because a wrapper object is still truthy. It would also re-add a
third shape to the union that #1 B1 spent effort removing.

The honest cost, stated in #31: this makes the count *available*, not
*unavoidable*. An assistant that never calls it still gets 100 of 1,092 with no
signal. Closing that needs a breaking change to the response shape, so it waits
for a major version this project does not yet have.
"""

import pickle

import pytest

import mcp_legalize


def documento(**campos):
    base = {
        "titulo": "Ley de prueba", "identificador": "XX-1", "pais": "tst",
        "rango": "ley", "estado": "in_force", "fecha_publicacion": "2020-01-01",
        "ultima_actualizacion": "2020-01-01", "fuente": "https://example.test",
        "_ruta": "tst/1.md", "_bytes": 10,
    }
    base.update(campos)
    return base


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    docs = {
        f"DOC-{i}": documento(
            titulo=f"Ley {i} de ordenación",
            estado="in_force" if i % 2 == 0 else "repealed",
        )
        for i in range(150)
    }
    postings = {"arrendamiento": [f"DOC-{i}" for i in range(50)]}
    indices = tmp_path / "indices"
    indices.mkdir(parents=True, exist_ok=True)
    with (indices / "inverted_tst.bin").open("wb") as fh:
        pickle.dump({"tokenizador": "cafe12345678", "postings": postings}, fh, protocol=5)

    monkeypatch.setattr(mcp_legalize, "INDICES_DIR", indices)
    monkeypatch.setitem(mcp_legalize._DOCS_POR_PAIS, "tst", docs)
    monkeypatch.setitem(mcp_legalize._META_POR_PAIS, "tst", {})
    monkeypatch.setitem(mcp_legalize._INDEX_FILE_POR_PAIS, "tst", "index_tst")
    monkeypatch.setattr(mcp_legalize, "_INVERTIDO_POR_PAIS", {})
    return docs


# ─────────────────────────────── counting ────────────────────────────────────

def test_it_counts_past_the_limit_that_caps_buscar_ley(corpus):
    """The whole point: 150 documents exist, `buscar_ley` can only show 100."""
    assert mcp_legalize.contar_leyes.fn(pais="tst").total == 150
    assert len(mcp_legalize.buscar_ley.fn(pais="tst", limite=100)) == 100


def test_it_accepts_the_same_filters_as_buscar_ley(corpus):
    assert mcp_legalize.contar_leyes.fn(pais="tst", estado="in_force").total == 75


def test_it_counts_a_text_search(corpus):
    assert mcp_legalize.contar_leyes.fn(pais="tst", texto="arrendamiento").total == 50


def test_text_and_filters_narrow_together(corpus):
    """Composition must match `buscar_ley`, or the count would describe a
    different query than the one the client is about to run."""
    total = mcp_legalize.contar_leyes.fn(pais="tst", texto="arrendamiento", estado="in_force").total

    assert total == 25


def test_a_query_matching_nothing_counts_zero(corpus):
    assert mcp_legalize.contar_leyes.fn(pais="tst", texto="zzzznope").total == 0


def test_the_count_agrees_with_what_buscar_ley_returns(corpus):
    """When the result set fits under the limit, the two must not disagree."""
    resultados = mcp_legalize.buscar_ley.fn(pais="tst", texto="arrendamiento",
                                            estado="in_force", limite=100)

    assert mcp_legalize.contar_leyes.fn(pais="tst", texto="arrendamiento",
                                        estado="in_force").total == len(resultados)


# ──────────────────────────── error contract ─────────────────────────────────

def test_an_unknown_country_fails_like_every_other_tool(corpus):
    """Same union with `ErrorRespuesta` the other six tools use — #1 B1."""
    resultado = mcp_legalize.contar_leyes.fn(pais="XX")

    assert isinstance(resultado, mcp_legalize.ErrorRespuesta)
    assert resultado.sugerencias


def test_no_indices_fails_the_same_way(monkeypatch):
    monkeypatch.setattr(mcp_legalize, "_DOCS_POR_PAIS", {})

    resultado = mcp_legalize.contar_leyes.fn()

    assert isinstance(resultado, mcp_legalize.ErrorRespuesta)
    assert resultado.error == "No hay índices disponibles."


# ─────────────────────────── buscar_ley untouched ────────────────────────────

def test_buscar_ley_still_returns_a_bare_list(corpus):
    """The reason this is a separate tool: 16 call sites depend on it."""
    resultados = mcp_legalize.buscar_ley.fn(pais="tst", limite=5)

    assert isinstance(resultados, list)
    assert len(resultados) == 5
