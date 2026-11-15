"""Tests that a negative size asks for nothing, instead of cutting from the end (#73).

`max_chars` and `contexto_chars` went straight into a slice. In Python a
negative bound counts from the end, so `obtener_ley(max_chars=-5)` returned the
law without its last five characters and said `chars_devueltos=-5`; in
`obtener_articulo` a negative `contexto_chars` could put the end of an article
before its heading. Found on 2026-11-11.

Below zero is read as zero, as `buscar_ley` already reads `limite`: nothing of
the text is returned, and the response says how much there is. A text cut
somewhere nobody asked for, presented with a count that cannot be true, is the
failure principle I names.
"""

import pytest

import mcp_legalize

CUERPO = "# Ley\n\n###### Artículo 1.\n\nPrimero.\n\n###### Artículo 2.\n\nSegundo y último, sin nada detrás.\n"


@pytest.fixture
def ley(instalar_corpus):
    instalar_corpus("t", {"LEY-1": {"titulo": "Ley", "_ruta": "ley.md"}}, {"LEY-1": CUERPO})


@pytest.mark.parametrize("pedido", [-1, -5, -10_000])
def test_a_negative_max_chars_returns_no_text_and_says_how_much_there_is(ley, pedido):
    resultado = mcp_legalize.obtener_ley.fn("LEY-1", pais="t", max_chars=pedido)

    assert resultado.texto_truncado is True
    assert resultado.chars_devueltos == 0
    assert resultado.chars_totales == len(CUERPO)
    assert "Primero" not in resultado.texto and "Segundo" not in resultado.texto


@pytest.mark.parametrize("pedido", [-1, -5, -10_000])
def test_a_negative_contexto_chars_returns_the_heading_of_an_open_article(ley, pedido):
    """Article 2 runs to the end of the document: `contexto_chars` is what cuts it."""
    resultado = mcp_legalize.obtener_articulo.fn("LEY-1", "2", pais="t", contexto_chars=pedido)

    assert resultado.error is None
    assert "###### Artículo 2." in resultado.texto
    assert "Segundo" not in resultado.texto
    assert resultado.texto_truncado is True
    assert resultado.chars_devueltos == len("###### Artículo 2.")


def test_a_negative_contexto_chars_cuts_the_same_when_the_index_has_no_positions(instalar_corpus):
    """Without Markdown headings the article is located on the file, by another path."""
    cuerpo = "Artículo 1. Primero.\n\nArtículo 2. Segundo y último, sin nada detrás.\n"
    instalar_corpus("t", {"LEY-1": {"titulo": "Ley", "_ruta": "ley.md"}}, {"LEY-1": cuerpo})

    resultado = mcp_legalize.obtener_articulo.fn("LEY-1", "2", pais="t", contexto_chars=-20)

    assert resultado.error is None
    assert "Artículo 2" in resultado.texto
    assert "Segundo" not in resultado.texto
    assert resultado.texto_truncado is True


def test_zero_and_positive_sizes_are_unchanged(ley):
    assert mcp_legalize.obtener_ley.fn("LEY-1", pais="t", max_chars=0).chars_devueltos == 0
    assert mcp_legalize.obtener_ley.fn("LEY-1", pais="t", max_chars=5).chars_devueltos == 5
    assert mcp_legalize.obtener_ley.fn("LEY-1", pais="t").texto_truncado is False
