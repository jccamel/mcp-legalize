"""Tests that a section numbered only by its heading is an article (ADR 0011).

The UK corpus marks each section with a heading that holds nothing but its number
(`##### 2`), usually under a heading with the section's title. The article rules
knew `Artículo N`, `Article N`, `N §` and `§ N`, so `obtener_articulo` found no
British section at all. Measured on 2026-10-19 over a sample of 5,000 UK laws,
4,940 number their sections this way.

A bare number is an article only in a law with no article heading of the known
kinds, and only as a clean number (`2`, `2A`): not `2.`, not `**2**`. In the
Spanish corpus that touches two laws, documented in ADR 0011; in eu, fr and se,
none. When the heading right above the number is one level up, it is the
section's title, and the section is served from it.
"""

import pytest

import legalize_articulos as la
import mcp_legalize

LEY = """# Environmental Protection Act 1990

## Part I — Integrated Pollution Control

### Preliminary

#### Preliminary.

##### 1

The following provisions have effect.

#### Prescribed processes and prescribed substances.

##### 2

The Secretary of State may prescribe.

#### Emission limits.

##### 2A

Limits may be set.

## Schedule 1

##### 1

First paragraph of the schedule.
"""

REGLAMENTO = """# The Scallops (Luce Bay) Order 2010

###### 1

This Order may be cited as the Scallops Order.

###### 2

No person may fish for scallops.
"""

CON_ARTICULOS = """# Ley de prueba

### EXPOSICIÓN DE MOTIVOS

### 1

Primera parte de la exposición.

###### Artículo 1.

El artículo de verdad.
"""


@pytest.fixture
def corpus(instalar_corpus):
    instalar_corpus("uk", {
        "ukpga-1990-43": {"titulo": "Environmental Protection Act 1990", "_ruta": "a.md"},
        "ssi-2010-429": {"titulo": "The Scallops (Luce Bay) Order 2010", "_ruta": "b.md"},
        "ES-1": {"titulo": "Ley de prueba", "_ruta": "c.md"},
    }, {"ukpga-1990-43": LEY, "ssi-2010-429": REGLAMENTO, "ES-1": CON_ARTICULOS})


def contenido(resultado):
    assert resultado.error is None, resultado.error
    return resultado.texto.split("---\n", 1)[1].rsplit("\n</untrusted_content>", 1)[0]


def seccion(id_ley, numero, **kw):
    return mcp_legalize.obtener_articulo.fn(id_ley, numero, pais="uk", **kw)


def test_a_section_of_an_act_starts_at_its_title_and_ends_before_the_next(corpus):
    texto = contenido(seccion("ukpga-1990-43", "2"))

    assert texto.startswith("#### Prescribed processes and prescribed substances.")
    assert "The Secretary of State may prescribe." in texto
    assert "Emission limits" not in texto and "Limits may be set" not in texto


def test_a_section_with_a_letter_is_found(corpus):
    assert "Limits may be set." in contenido(seccion("ukpga-1990-43", "2A"))


def test_a_regulation_without_titles_is_served_from_its_number(corpus):
    texto = contenido(seccion("ssi-2010-429", "2"))

    assert texto.startswith("###### 2")
    assert "No person may fish for scallops." in texto
    assert "cited as" not in texto


def test_a_number_repeated_in_a_schedule_is_reachable(corpus):
    """Sections and schedule paragraphs restart their numbering."""
    primero = seccion("ukpga-1990-43", "1")

    assert "The following provisions have effect." in contenido(primero)
    assert len(primero.ubicaciones) == 2
    otro = seccion("ukpga-1990-43", "1", capitulo=primero.ubicaciones[1])
    assert "First paragraph of the schedule." in contenido(otro)


def test_a_bare_number_is_not_an_article_where_known_articles_exist(corpus):
    """Parity elsewhere: a law with `Artículo N` headings is located as before."""
    texto = contenido(mcp_legalize.obtener_articulo.fn("ES-1", "1", pais="uk"))

    assert texto.startswith("###### Artículo 1.")
    assert "exposición" not in texto


@pytest.mark.parametrize("cuerpo", [LEY, REGLAMENTO, CON_ARTICULOS], ids=["act", "regulation", "with articles"])
@pytest.mark.parametrize("contexto", [20, 100_000])
def test_rows_and_locating_on_the_fly_agree(cuerpo, contexto):
    """FR-014 of spec 002, for the new rule: the indexer and the server agree."""
    primeras = {}
    for _, numero, _, inicio, fin_enc, fin, abierto in la.localizar_todos(cuerpo):
        primeras.setdefault(numero.casefold(), (numero, inicio, fin_enc, fin, abierto))
    assert primeras
    for numero, inicio, fin_enc, fin, abierto in primeras.values():
        corte = min(fin_enc + contexto, len(cuerpo)) if abierto else fin
        assert la.localizar(cuerpo, numero, contexto) == (inicio, corte, fin), numero
