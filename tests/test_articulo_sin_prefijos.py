"""Tests that an article number is matched whole, never as a prefix of another.

The heading patterns ended the requested number with `\\b`. French codes number
articles with hyphens — `L110-1`, `L123-1-1`, `R*512-9-3` — and `\\b` matches
right before a hyphen, so `articulo="L110"` returned `Article L110-1`, and an
`L123-1` that does not exist would have returned `L123-1-1`. Found on
2026-10-18 while testing `legalize-fr` (83 codes, over 170,000 articles):
the client asked for one article and received another, which constitution
principle I ranks as the worst failure.

The number must now be followed by something that cannot continue it: not a
letter or digit, not `-`, not `*`.

The same patterns, with any number, decide where an article ends when heading
levels are inverted. They only accepted digits, so a French `Article L…`
heading was never recognised as "another article"; now the code prefixes are
accepted too.
"""

import pytest

import mcp_legalize
from mcp_legalize import ArticuloResultado


@pytest.fixture
def ley(instalar_corpus):
    def articulo(texto, numero):
        instalar_corpus("fr", {
            "LEGITEXT000005634379": {"titulo": "Code de commerce", "_ruta": "fr/x.md"},
        }, {"LEGITEXT000005634379": texto})
        resultado = mcp_legalize.obtener_articulo.fn("LEGITEXT000005634379", numero, pais="fr")
        assert isinstance(resultado, ArticuloResultado)
        return resultado

    return articulo


def texto(resultado):
    assert resultado.error is None, resultado.error
    return resultado.texto.split("---\n", 1)[1].rsplit("\n</untrusted_content>", 1)[0]


CODIGO = (
    "#### Section 1\n\n"
    "##### Article L110-1-1\n\nLe sous-article.\n\n"
    "##### Article L110-1\n\nLa loi répute actes de commerce.\n\n"
    "##### Article L110-2\n\nLe deuxième.\n\n"
    "##### Article R*512-9-3\n\nUn article réglementaire.\n\n"
    "##### Article LO121\n\nUne loi organique.\n\n"
    "##### Article LO122\n\nLa suivante.\n"
)


def test_a_number_that_only_prefixes_another_is_not_found(ley):
    """The reproduction: `L110` returned `Article L110-1`."""
    resultado = ley(CODIGO, "L110")

    assert resultado.error == "Artículo no encontrado"


def test_a_missing_article_does_not_resolve_to_its_sub_article(ley):
    """`L110-1-1` exists, `L110-1` does not: asking for `L110-1` finds nothing."""
    sin_l110_1 = CODIGO.replace("##### Article L110-1\n", "##### Article L999\n")

    resultado = ley(sin_l110_1, "L110-1")

    assert resultado.error == "Artículo no encontrado"


def test_an_article_is_not_confused_with_an_earlier_sub_article(ley):
    """`L110-1-1` comes first in the document; asking for `L110-1` must skip it."""
    resultado = texto(ley(CODIGO, "L110-1"))

    assert resultado.startswith("##### Article L110-1\n")
    assert "La loi répute actes de commerce." in resultado
    assert "Le sous-article." not in resultado


def test_an_asterisked_regulatory_article_is_found(ley):
    resultado = texto(ley(CODIGO, "R*512-9-3"))

    assert "Un article réglementaire." in resultado
    assert "Une loi organique." not in resultado


def test_an_organic_law_article_is_found_and_ends_at_the_next(ley):
    resultado = texto(ley(CODIGO, "LO121"))

    assert "Une loi organique." in resultado
    assert "La suivante." not in resultado


def test_a_french_article_ends_at_the_next_one_even_on_a_lower_level(ley):
    """Inverted levels: `Article L…` must count as "another article"."""
    cuerpo = "# Article L1\n\nLe premier.\n\n###### Article L2\n\nLe second.\n"

    resultado = texto(ley(cuerpo, "L1"))

    assert "Le premier." in resultado
    assert "Le second." not in resultado


def test_without_headings_a_prefix_is_not_found_either(ley):
    resultado = ley("Article L110-1\nLa loi répute actes de commerce.\n", "L110")

    assert resultado.error == "Artículo no encontrado"


@pytest.mark.parametrize("cuerpo,numero,esperado", [
    ("###### Artículo 7. Naturaleza.\n\nSiete.\n", "7", "Siete."),
    ("###### Artículo 1 bis.\n\nUno bis.\n", "1", "Uno bis."),
    ("##### 3 §\n\nTredje.\n", "3", "Tredje."),
    ("##### § 4\n\nVierter.\n", "4", "Vierter."),
])
def test_spanish_swedish_and_german_headings_are_unchanged(ley, cuerpo, numero, esperado):
    """Pins what must not move: the number followed by `.`, a space or `§`."""
    assert esperado in texto(ley(cuerpo, numero))
