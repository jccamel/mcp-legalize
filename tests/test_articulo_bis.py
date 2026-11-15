"""Tests that an article inserted as "3 bis" is its own article, not a second "3" (#72).

The number captured from a heading stopped at the digits, so `Artículo 3 bis`
was stored as article `3`, in a second row with location `CAPÍTULO I (2)`.
`obtener_articulo(articulo="3")` listed two `ubicaciones` as if the number
were repeated, the client could not tell that the second was the *bis*, and
`3 bis` was only found by scanning the file. Without the index, asking for
`3` returned `3 bis` whenever it came first.

The Latin multiplicative suffixes are part of the number. Measured on
2026-11-15 over the article headings of the local corpora: in es, `bis` 3,172
(1,138 laws), `ter` 931, `quater`/`quáter` 461, up to `duovicies`; in fr,
2,100 headings in 16 laws; none in eu or se.

The asserts go through `obtener_articulo`, both through the index and through
the text when the index cannot be used.
"""

import pytest

import legalize_articulos
import legalize_indice
import mcp_legalize

CUERPO = (
    "## CAPÍTULO I\n\n"
    "###### Artículo 3\n\nTexto del tres.\n\n"
    "###### Artículo 3 bis\n\nTexto del tres bis.\n\n"
    "###### Artículo 3 quáter\n\nTexto del tres quáter.\n\n"
    "###### Artículo 4\n\nTexto del cuatro.\n"
)


@pytest.fixture
def ley(instalar_corpus):
    instalar_corpus("es", {"LEY-1": {"titulo": "Ley de prueba", "_ruta": "ley.md"}},
                    cuerpos={"LEY-1": CUERPO})


@pytest.fixture
def solo_indice(monkeypatch):
    """Fails if the server falls back to scanning the text."""
    def no(*_):
        raise AssertionError("se localizó sobre el texto, no en el índice")
    monkeypatch.setattr(mcp_legalize, "_localizar_articulo", no)


@pytest.fixture
def sin_indice(monkeypatch):
    """The text on disk no longer has the indexed length, so the index is not used."""
    monkeypatch.setattr(mcp_legalize, "_read_file", lambda d, p: CUERPO + "\n")


def articulo(numero):
    return mcp_legalize.obtener_articulo.fn("LEY-1", numero, pais="es")


@pytest.mark.parametrize("modo", ["solo_indice", "sin_indice"])
@pytest.mark.parametrize("numero, texto", [
    ("3", "Texto del tres."),
    ("3 bis", "Texto del tres bis."),
    ("3 BIS", "Texto del tres bis."),
    ("3 quáter", "Texto del tres quáter."),
    ("4", "Texto del cuatro."),
])
def test_each_article_is_found_by_its_whole_number(ley, request, modo, numero, texto):
    request.getfixturevalue(modo)

    resultado = articulo(numero)

    assert resultado.error is None
    assert texto in resultado.texto
    assert "Texto del tres" not in resultado.texto.replace(texto, "")
    assert resultado.ubicaciones is None


def test_three_is_not_found_in_three_bis_when_bis_comes_first(instalar_corpus, monkeypatch):
    """Without the index the text is scanned in order: `3` must skip `3 bis`."""
    cuerpo = "###### Artículo 3 bis\n\nEl bis.\n\n###### Artículo 3\n\nEl tres.\n"
    instalar_corpus("es", {"LEY-1": {"titulo": "Ley", "_ruta": "ley.md"}}, cuerpos={"LEY-1": cuerpo})
    monkeypatch.setattr(mcp_legalize, "_read_file", lambda d, p: cuerpo + "\n")

    resultado = articulo("3")

    assert "El tres." in resultado.texto
    assert "El bis." not in resultado.texto


def test_a_word_after_the_number_that_is_not_a_suffix_is_not_part_of_it(instalar_corpus):
    """`Artículo 5 Disposiciones` is article 5, as before."""
    cuerpo = "###### Artículo 5 Disposiciones generales\n\nEl cinco.\n"
    instalar_corpus("es", {"LEY-1": {"titulo": "Ley", "_ruta": "ley.md"}}, cuerpos={"LEY-1": cuerpo})

    assert "El cinco." in articulo("5").texto


def test_changing_the_article_rules_changes_the_index_format(monkeypatch):
    """Positions in the index were computed with the rules of their day: an
    index built with others is rebuilt, like one with another status rule."""
    antes = legalize_articulos.huella()
    monkeypatch.setattr(legalize_articulos, "CUALQUIER_NUMERO", r"\d+")

    assert legalize_articulos.huella() != antes
    assert antes in legalize_indice.FORMATO
