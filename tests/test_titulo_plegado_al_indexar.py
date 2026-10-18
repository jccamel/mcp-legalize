"""Tests that a title search folds the query, never the corpus (#15, spec 002).

They replace `test_search_normalization_cache`. Issue #15 measured that every
title search re-folded all 12,291 Spanish titles — 886 ms of an 896 ms request —
and a lazy per-document cache fixed it. The database removes the cache: each
title is stored already folded when the index is written, and the query is the
only thing folded at request time.

The invariant is the same and is stated the same way, as a count rather than a
time: no title is folded while answering a request. The other two guarantees of
the old file stay too — folding still ignores accents and case, and a title
changed in the index is never answered from its previous folded form.
"""

import pytest

import legalize_normalizacion
import mcp_legalize


def documento(titulo):
    return {"titulo": titulo, "rango": "ley", "estado": "in_force",
            "fecha_publicacion": "2020-01-01", "_ruta": "xx/1.md", "_bytes": 10}


@pytest.fixture
def corpus(instalar_corpus):
    docs = {f"DOC-{i}": documento(f"Ley {i} de ordenación territorial") for i in range(50)}
    instalar_corpus("tst", docs)
    return instalar_corpus, docs


@pytest.fixture
def titulos_plegados(monkeypatch):
    """Cuenta las llamadas al plegado que reciben un título del corpus.

    Los argumentos de la consulta también se pliegan, una vez por petición; esas
    no son el trabajo que #15 perseguía y no se cuentan.
    """
    llamadas = []
    original = legalize_normalizacion.normalizar

    def espia(texto):
        if texto.startswith("Ley ") and "ordenación" in texto:
            llamadas.append(texto)
        return original(texto)

    monkeypatch.setattr(legalize_normalizacion, "normalizar", espia)
    return llamadas


@pytest.mark.parametrize("consulta", ["ordenación", "zzzznope"])
def test_a_title_search_folds_no_title(corpus, titulos_plegados, consulta):
    """Matched or unmatched, the corpus is not folded at request time."""
    mcp_legalize.buscar_ley.fn(consulta=consulta, pais="tst", limite=100)
    mcp_legalize.contar_leyes.fn(consulta=consulta, pais="tst")

    assert titulos_plegados == []


def test_folding_still_ignores_accents_and_case(corpus):
    for consulta in ["ordenación", "ORDENACION", "ordenacion", "Ordenación"]:
        resultados = mcp_legalize.buscar_ley.fn(consulta=consulta, pais="tst", limite=100)
        assert len(resultados) == 50, f"falló con {consulta!r}"


def test_a_title_changed_in_the_index_is_found_by_its_new_words(corpus):
    """Reindexing replaces the folded title with the title."""
    instalar, docs = corpus
    mcp_legalize.buscar_ley.fn(consulta="ordenación", pais="tst", limite=100)

    instalar("tst", {**docs, "DOC-0": documento("Ley completamente distinta")})

    assert [r.id for r in mcp_legalize.buscar_ley.fn(consulta="completamente", pais="tst")] == ["DOC-0"]
    assert len(mcp_legalize.buscar_ley.fn(consulta="ordenación", pais="tst", limite=100)) == 49
