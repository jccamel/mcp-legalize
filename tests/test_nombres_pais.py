"""Tests that `listar_paises` names every jurisdiction with an indexed corpus.

The EU and UK corpora are indexed (EU since spec 003, UK since 2026-10-19), but
the name table did not know them, so `listar_paises` fell back to the code in
capitals: the European Union came out as "EU" and the United Kingdom as "UK".
"""

import pytest

import mcp_legalize


@pytest.mark.parametrize("codigo,nombre", [
    ("eu", "European Union"),
    ("uk", "United Kingdom"),
])
def test_an_indexed_jurisdiction_is_listed_by_its_name(instalar_corpus, codigo, nombre):
    instalar_corpus(codigo, {"A-1": {"titulo": "Some Act", "_ruta": "a.md"}}, {"A-1": "Text."})

    pais = mcp_legalize.listar_paises.fn()[0]

    assert (pais.codigo, pais.nombre) == (codigo, nombre)
