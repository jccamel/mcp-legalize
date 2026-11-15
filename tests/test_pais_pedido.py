"""Tests that every tool that takes `pais` reads it the same way (#69, #70).

Found on 2026-11-11. Six tools take a country code and each decided on its own
what an unknown one meant. `buscar_ley`, `contar_leyes` and `listar_rangos`
rejected it; `estadisticas(pais="zz")` returned the statistics of every country
(140,241 documents on the indices of that day), and `obtener_ley` and
`obtener_articulo` searched everywhere. A client that mistyped a code got an
answer about a different question, with nothing to tell it so (principle IV).

And the code was compared as written: `pais="ES"` was "no reconocido", while
ids stopped distinguishing case on 2026-10-18, for the reason that applies
here too — the client writes what it has seen, in the case it prefers.

The assertions go through the six tools.
"""

import pytest

import mcp_legalize

CUERPO = "# Ley\n\n###### Artículo 1.\n\nTexto.\n"


@pytest.fixture
def dos_paises(instalar_corpus):
    instalar_corpus("es", {"LEY-ES": {"titulo": "Ley española", "rango": "ley", "estado": "in_force",
                                      "fecha_publicacion": "2001-01-01", "_ruta": "es.md"}},
                    {"LEY-ES": CUERPO})
    instalar_corpus("se", {"LEY-SE": {"titulo": "Svensk lag", "rango": "lag", "estado": "in_force",
                                      "fecha_publicacion": "2002-01-01", "_ruta": "se.md"}},
                    {"LEY-SE": CUERPO})


LLAMADAS = {
    "buscar_ley": lambda pais: mcp_legalize.buscar_ley.fn(pais=pais),
    "contar_leyes": lambda pais: mcp_legalize.contar_leyes.fn(pais=pais),
    "obtener_ley": lambda pais: mcp_legalize.obtener_ley.fn("LEY-ES", pais=pais),
    "obtener_articulo": lambda pais: mcp_legalize.obtener_articulo.fn("LEY-ES", "1", pais=pais),
    "listar_rangos": lambda pais: mcp_legalize.listar_rangos.fn(pais=pais),
    "estadisticas": lambda pais: mcp_legalize.estadisticas.fn(pais=pais),
}


@pytest.mark.parametrize("herramienta", LLAMADAS)
def test_an_unknown_country_is_an_error_that_lists_the_known_ones(dos_paises, herramienta):
    """Never the answer for every country: that is a different question."""
    resultado = LLAMADAS[herramienta]("zz")

    assert isinstance(resultado, mcp_legalize.ErrorRespuesta)
    assert "zz" in resultado.error
    assert resultado.sugerencias == ["es", "se"]


@pytest.mark.parametrize("herramienta", LLAMADAS)
@pytest.mark.parametrize("escrito", ["ES", "Es", " es "])
def test_the_country_code_is_read_whatever_its_case(dos_paises, herramienta, escrito):
    assert not isinstance(LLAMADAS[herramienta](escrito), mcp_legalize.ErrorRespuesta)


def test_a_code_in_capitals_selects_that_country_and_no_other(dos_paises):
    assert [r.id for r in mcp_legalize.buscar_ley.fn(pais="ES")] == ["LEY-ES"]
    assert mcp_legalize.contar_leyes.fn(pais="ES").total == 1
    assert mcp_legalize.estadisticas.fn(pais="SE").paises == ["se"]
    assert [r.rango for r in mcp_legalize.listar_rangos.fn(pais="SE")] == ["lag"]


def test_what_comes_back_is_the_stored_code(dos_paises):
    """The client can use what it reads as the next filter, as with ids."""
    assert mcp_legalize.buscar_ley.fn(pais="ES")[0].pais == "es"
    assert mcp_legalize.obtener_ley.fn("LEY-ES", pais="ES", solo_metadata=True).pais == "es"


def test_a_law_is_not_looked_for_outside_the_country_asked(dos_paises):
    """With a known country that does not have the law, the law is not found."""
    resultado = mcp_legalize.obtener_ley.fn("LEY-ES", pais="se")

    assert isinstance(resultado, mcp_legalize.ErrorRespuesta)
    assert "LEY-ES" in resultado.error


def test_no_country_still_means_every_country(dos_paises):
    assert [r.id for r in mcp_legalize.buscar_ley.fn()] == ["LEY-ES", "LEY-SE"]
    assert mcp_legalize.estadisticas.fn().total_documentos == 2
