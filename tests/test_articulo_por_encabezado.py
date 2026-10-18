"""Tests that `obtener_articulo` returns the article, not a mention of it.

The article was located by searching the body for `artículo N` anywhere, and
cut at the next `artículo M` anywhere. Legal prose is full of cross-references,
so both searches hit sentences instead of headings. Measured on the Spanish
corpus on 2026-10-17 over 20,473 headed articles:

    started somewhere else            3,722  (18.2%)
    cut short before the next one     5,328  (26.0%)

Two real cases, reduced to the fixtures below:

- `BOE-A-2018-743`, article 4, came back starting at "…artículo 4.2 de la Ley
  Orgánica 15/1999…", a reference inside a different article.
- `BOE-A-2003-19572`, article 5, was cut at "…lo establecido en el artículo
  26.2…" and lost 1,446 characters.

For a server whose client reasons over the text as if it were the law, that is
the failure constitution principle I calls the worst: a wrong or truncated
passage presented as the article. "Not found" is a better answer than that.

The corpora mark articles as Markdown headings (`###### Artículo N.`,
`##### N §`), so the article is now found among headings and ends at the next
heading of the same or a higher level. Documents without headings still work,
through the old patterns anchored to the start of a line, which is where an
article title is and a cross-reference is not.
"""

import pytest

import mcp_legalize
from mcp_legalize import ArticuloResultado


@pytest.fixture
def ley(instalar_corpus, monkeypatch):
    """One law whose body each test supplies."""
    instalar_corpus("xx", {
        "XX-1": {"titulo": "Ley de prueba", "pais": "xx", "_ruta": "xx/1.md"},
    })
    cuerpo = {}
    monkeypatch.setattr(mcp_legalize, "_read_file", lambda doc, pais: cuerpo["texto"])

    def articulo(texto, numero):
        cuerpo["texto"] = texto
        resultado = mcp_legalize.obtener_articulo.fn(id_ley="XX-1", articulo=numero, pais="xx")
        assert isinstance(resultado, ArticuloResultado)
        return resultado

    return articulo


def texto(resultado):
    """The article text, without the untrusted-content wrapper."""
    assert resultado.error is None, resultado.error
    return resultado.texto.split("---\n", 1)[1].rsplit("\n</untrusted_content>", 1)[0]


# ─────────────────────── the two defects, from real cases ────────────────────

def test_a_reference_before_the_article_is_not_the_article(ley):
    """BOE-A-2018-743: the first textual mention used to win over the heading."""
    cuerpo = (
        "###### Artículo 1. Objeto.\n\n"
        "Se aplica lo dispuesto en el artículo 4.2 de la Ley Orgánica 15/1999.\n\n"
        "###### Artículo 4. Tratamiento.\n\n"
        "Texto real del artículo cuatro.\n"
    )

    resultado = texto(ley(cuerpo, "4"))

    assert resultado.startswith("###### Artículo 4. Tratamiento.")
    assert "Texto real del artículo cuatro." in resultado
    assert "Ley Orgánica 15/1999" not in resultado


def test_a_reference_inside_the_article_does_not_cut_it(ley):
    """BOE-A-2003-19572: the article ended at the first `artículo N` it quoted."""
    cuerpo = (
        "###### Artículo 5. Procedimientos sanitarios.\n\n"
        "1\\. De acuerdo con lo establecido en el artículo 26.2 de la Ley 16/2003,\n"
        "segundo párrafo que el cliente nunca veía.\n\n"
        "2\\. Apartado final del artículo cinco.\n\n"
        "###### Artículo 6. Otro.\n\n"
        "Texto del seis.\n"
    )

    resultado = texto(ley(cuerpo, "5"))

    assert "segundo párrafo que el cliente nunca veía." in resultado
    assert "Apartado final del artículo cinco." in resultado
    assert "Texto del seis." not in resultado


# ───────────────────────────── heading variants ──────────────────────────────

@pytest.mark.parametrize("encabezado", [
    "###### Artículo 7. Normas.",
    "###### Art. 7. Normas reguladoras.",
    "### ARTÍCULO 7",
    "###### **Artículo 7.** Normas.",
    "###### Artículo 7. Naturaleza y sede.",
])
def test_every_heading_form_in_the_spanish_corpus_is_found(ley, encabezado):
    """The five most frequent heading shapes measured in `legalize-es`."""
    cuerpo = f"Preámbulo que menciona el artículo 7.\n\n{encabezado}\n\nCuerpo del siete.\n"

    resultado = texto(ley(cuerpo, "7"))

    assert resultado.startswith(encabezado)
    assert "Preámbulo" not in resultado


def test_article_1_is_not_article_10(ley):
    cuerpo = "###### Artículo 10.\n\nEl diez.\n\n###### Artículo 1.\n\nEl uno.\n"

    resultado = texto(ley(cuerpo, "1"))

    assert "El uno." in resultado
    assert "El diez." not in resultado


def test_an_article_ends_at_a_higher_level_heading(ley):
    """The last article of a chapter must not swallow the next chapter's title."""
    cuerpo = (
        "###### Artículo 9. Último del capítulo.\n\nTexto del nueve.\n\n"
        "## CAPÍTULO II\n\n###### Artículo 10.\n\nEl diez.\n"
    )

    resultado = texto(ley(cuerpo, "9"))

    assert "Texto del nueve." in resultado
    assert "CAPÍTULO II" not in resultado


# ─────────────────────────────── Swedish § ───────────────────────────────────

def test_a_swedish_paragraph_is_found_by_its_heading_not_a_reference(ley):
    """SFS-2000-461: a line opening with "18 § lagen (…)" is a reference."""
    cuerpo = (
        "##### 3 §\n\n"
        "18 § lagen (1998:674) om inkomstgrundad ålderspension ska inte gälla.\n\n"
        "##### 18 §\n\nDen riktiga paragrafen.\n"
    )

    resultado = texto(ley(cuerpo, "18"))

    assert resultado.startswith("##### 18 §")
    assert "Den riktiga paragrafen." in resultado


def test_a_swedish_paragraph_is_not_cut_by_a_reference_line(ley):
    cuerpo = (
        "##### 3 §\n\nFörsta stycket.\n"
        "5 § lagen (1998:674) gäller också.\nSista stycket.\n\n"
        "##### 4 §\n\nFjärde.\n"
    )

    resultado = texto(ley(cuerpo, "3"))

    assert "Sista stycket." in resultado
    assert "Fjärde." not in resultado


def test_a_swedish_paragraph_ends_at_the_next_chapter(ley):
    cuerpo = "##### 10 §\n\nTionde.\n\n## 2 kap. Barnpension\n\n##### 1 §\n\nEfterlevande.\n"

    resultado = texto(ley(cuerpo, "10"))

    assert "Tionde." in resultado
    assert "2 kap." not in resultado


def test_german_paragraph_headings_still_work(ley):
    cuerpo = "##### § 3\n\nDritter, siehe § 4.\n\n##### § 4\n\nVierter.\n"

    resultado = texto(ley(cuerpo, "3"))

    assert "Dritter, siehe § 4." in resultado
    assert "Vierter." not in resultado


# ───────────────────── documents without Markdown headings ───────────────────

def test_without_headings_a_line_start_title_still_works(ley):
    """The mock corpus and older documents: `Artículo N` alone on its line."""
    cuerpo = (
        "Artículo 1\nTexto uno, véase el artículo 2 de esta ley.\nMás texto del uno.\n"
        "Artículo 2\nTexto dos.\n"
    )

    resultado = texto(ley(cuerpo, "1"))

    assert "Más texto del uno." in resultado
    assert "Texto dos." not in resultado


def test_a_mention_in_prose_alone_is_not_found_rather_than_returned(ley):
    """Principle I: "not found" beats a sentence presented as the article."""
    resultado = ley("Preámbulo que cita el artículo 7 de otra ley.\n", "7")

    assert resultado.error == "Artículo no encontrado"
    assert resultado.texto is None


def test_an_article_ends_at_the_next_article_even_on_a_lower_heading_level(ley):
    """BOE-A-2012-5842: `# Artículo 5` at level 1, the next one at level 6.

    "Same or higher level" alone ran article 5 on into article 18 in three
    measured documents with inconsistent heading levels. The next heading that
    names an article ends this one, whatever its level.
    """
    cuerpo = "# Artículo 5\n\nEl capital social.\n\n###### Artículo 18\n\nOtra cosa.\n"

    resultado = texto(ley(cuerpo, "5"))

    assert "El capital social." in resultado
    assert "Otra cosa." not in resultado
