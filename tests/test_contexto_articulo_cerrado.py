"""Tests that `contexto_chars` limits every article, not only the last one (#76).

`contexto_chars` was applied only to an article that runs to the end of the
document. An article closed by the next heading came back whole whatever its
length, so a client that asked for 2,000 characters could receive far more,
while `max_chars` in `obtener_ley` did cap and the READMEs described the two
side by side. Measured on 2026-11-15 on the five real corpora: 249,233 closed
articles are longer than 2,000 characters after their heading, and 100 longer
than the default of 80,000, the longest 728,069 (uk). Those 100 went out whole.

Now one rule cuts every article, open or closed, at `contexto_chars` counted
from the end of its heading, which always comes whole. The cut is reported with
the fields that already said so for an open article: `texto_truncado`,
`chars_totales`, `chars_devueltos`. Asserted through `obtener_articulo`, on the
path that reads positions from the index and on the one that locates the
article in a document without Markdown headings.
"""

import pytest

import mcp_legalize

LARGO = "a" * 500
ENCABEZADO = "###### Artículo 1."
CON_ENCABEZADOS = f"# Ley\n\n{ENCABEZADO}\n\n{LARGO}\n\n###### Artículo 2.\n\nDos.\n"
SIN_ENCABEZADOS = f"Artículo 1. {LARGO}\n\nArtículo 2. Dos.\n"


@pytest.fixture
def ley(instalar_corpus):
    def instalar(cuerpo):
        instalar_corpus("t", {"LEY-1": {"titulo": "Ley", "_ruta": "ley.md"}}, {"LEY-1": cuerpo})
    return instalar


def pedir(articulo, contexto):
    return mcp_legalize.obtener_articulo.fn("LEY-1", articulo, pais="t", contexto_chars=contexto)


def test_a_closed_article_is_cut_at_contexto_chars(ley):
    ley(CON_ENCABEZADOS)

    resultado = pedir("1", 100)

    assert resultado.error is None
    assert ENCABEZADO in resultado.texto and "Artículo 2" not in resultado.texto
    assert resultado.texto_truncado is True
    assert resultado.chars_devueltos == len(ENCABEZADO) + 100
    assert resultado.chars_totales == len(f"{ENCABEZADO}\n\n{LARGO}")


def test_a_closed_article_is_cut_the_same_without_markdown_headings(ley):
    ley(SIN_ENCABEZADOS)

    resultado = pedir("1", 100)

    assert resultado.error is None
    assert "Artículo 2" not in resultado.texto
    assert resultado.texto_truncado is True
    assert resultado.chars_devueltos < len(f"Artículo 1. {LARGO}")


@pytest.mark.parametrize("cuerpo", [CON_ENCABEZADOS, SIN_ENCABEZADOS], ids=["indexed", "fallback"])
def test_a_closed_article_shorter_than_the_limit_is_unchanged(ley, cuerpo):
    ley(cuerpo)

    resultado = pedir("1", 10_000)

    assert LARGO in resultado.texto and "Artículo 2" not in resultado.texto
    assert resultado.texto_truncado is False
    assert resultado.chars_totales is None and resultado.chars_devueltos is None


def test_an_open_article_is_cut_as_before(ley):
    ley(f"# Ley\n\n###### Artículo 1.\n\nUno.\n\n###### Artículo 2.\n\n{LARGO}\n")

    resultado = pedir("2", 100)

    assert resultado.texto_truncado is True
    assert resultado.chars_devueltos == len("###### Artículo 2.") + 100
