"""Tests that `obtener_articulo` says when it cut the article short.

When nothing in the document marks where an article ends — the last paragraph
of a law followed by a long annex with no heading — the article is cut at
`contexto_chars` (80,000 by default). The response said nothing about it, so a
client read the first 80,000 characters as the whole passage. `obtener_ley`
already reports the same situation with `texto_truncado`, `chars_totales` and
`chars_devueltos`; `obtener_articulo` did not. Constitution principle I: a
partial result must be distinguishable from a complete one.

Measured on 2026-10-18 across every document of the three local corpora:

    legalize-es   0 articles cut this way
    legalize-fr   0
    legalize-se  49 — e.g. SFS-2015-860, paragraph 9, with 318,559 characters after it

The article now carries the same three fields as `LeyCompleta`. `contexto_chars`
stays what the configuration docs say it is: a default the caller can raise,
applied only when the document gives no end.
"""

import pytest

import mcp_legalize
from mcp_legalize import ArticuloResultado

ANEXO = "Bilaga utan rubriker. " * 40   # 880 caracteres sin ningún encabezado


@pytest.fixture
def ley(instalar_corpus):
    def articulo(texto, numero, **kw):
        instalar_corpus("se", {"SFS-1": {"titulo": "t", "_ruta": "x.md"}}, {"SFS-1": texto})
        resultado = mcp_legalize.obtener_articulo.fn("SFS-1", numero, pais="se", **kw)
        assert isinstance(resultado, ArticuloResultado) and resultado.error is None
        return resultado

    return articulo


def contenido(resultado):
    return resultado.texto.split("---\n", 1)[1].rsplit("\n</untrusted_content>", 1)[0]


def test_an_article_cut_by_the_character_limit_says_so(ley):
    """SFS-2015-860 in miniature: the last paragraph, then an annex with no heading."""
    cuerpo = "##### 8 §\n\nÅttonde.\n\n##### 9 §\n\nNionde.\n\n" + ANEXO

    resultado = ley(cuerpo, "9", contexto_chars=100)

    entero = ("##### 9 §\n\nNionde.\n\n" + ANEXO).strip()
    assert resultado.texto_truncado is True
    assert resultado.chars_totales == len(entero)
    assert resultado.chars_devueltos == len(contenido(resultado))
    assert resultado.chars_devueltos < resultado.chars_totales


def test_raising_the_limit_returns_the_whole_article(ley):
    """Not a cap: the caller who asks for more gets all of it, and is told so."""
    cuerpo = "##### 9 §\n\nNionde.\n\n" + ANEXO

    resultado = ley(cuerpo, "9", contexto_chars=10_000)

    assert resultado.texto_truncado is False
    assert ANEXO.strip() in contenido(resultado)
    assert resultado.chars_totales is None and resultado.chars_devueltos is None


def test_an_article_that_ends_at_a_heading_is_complete(ley):
    cuerpo = "##### 1 §\n\nFörsta.\n\n##### 2 §\n\nAndra.\n"

    resultado = ley(cuerpo, "1", contexto_chars=5)

    assert resultado.texto_truncado is False
    assert contenido(resultado) == "##### 1 §\n\nFörsta."


def test_an_article_longer_than_the_limit_but_with_an_end_is_not_cut(ley):
    """The limit only applies when the document gives no end; it was never a cap."""
    cuerpo = "##### 1 §\n\n" + ANEXO + "\n\n##### 2 §\n\nAndra.\n"

    resultado = ley(cuerpo, "1", contexto_chars=100)

    assert resultado.texto_truncado is False
    assert ANEXO.strip() in contenido(resultado)


def test_the_last_article_of_a_short_document_is_complete(ley):
    resultado = ley("##### 1 §\n\nFörsta och sista.\n", "1", contexto_chars=100)

    assert resultado.texto_truncado is False


def test_the_heading_less_fallback_reports_truncation_too(ley):
    resultado = ley("Artículo 1\n" + ANEXO, "1", contexto_chars=100)

    assert resultado.texto_truncado is True
    assert resultado.chars_devueltos < resultado.chars_totales


def test_a_missing_article_carries_no_truncation_fields(instalar_corpus, ley, monkeypatch):
    instalar_corpus("se", {"SFS-1": {"titulo": "t", "_ruta": "x.md"}})
    monkeypatch.setattr(mcp_legalize, "_read_file", lambda d, p: "##### 1 §\n\nFörsta.\n")

    resultado = mcp_legalize.obtener_articulo.fn("SFS-1", "99", pais="se")

    assert resultado.error == "Artículo no encontrado"
    assert resultado.texto_truncado is None
