"""Tests for searching an exact phrase in the body (spec 002, US3).

`texto` asks which laws contain all of some words, in any order and anywhere:
measured on the Spanish corpus, "arrendamiento urbano" as words matches 573
laws, as a phrase 4. A client looking for a legal term made of several words
needs the second answer, and could not get it.

`frase` gives it. The phrase is folded like everything else (ADR 0008) and goes
to the engine as one quoted string, so the engine splits it with the tokenizer
that indexed the text: short words count inside a phrase, and nothing the
client writes is read as syntax.
"""

import pytest

import mcp_legalize


def documento(titulo, fecha="2020-01-01"):
    return {"titulo": titulo, "fecha_publicacion": fecha, "_ruta": f"{titulo}.md"}


@pytest.fixture
def corpus(instalar_corpus):
    instalar_corpus("tst", {
        "SEGUIDA": documento("seguida"),
        "SEPARADA": documento("separada"),
        "INVERTIDA": documento("invertida", fecha="2010-01-01"),
        "FORET": documento("foret"),
        "LEY1978": documento("ley1978"),
        "SIN_DE": documento("sinde"),
    }, {
        "SEGUIDA": "Del Arrendamiento Urbano y sus prórrogas.",
        "SEPARADA": "Del arrendamiento rústico. Suelo urbano.",
        "INVERTIDA": "Urbano arrendamiento, y también arrendamiento urbano.",
        "FORET": "Le régime de la forêt domaniale.",
        "LEY1978": "Conforme a la ley de 1978.",
        "SIN_DE": "Conforme a la ley 1978.",
    })
    instalar_corpus("otro", {"OTRO-1": documento("otro")}, {"OTRO-1": "Arrendamiento urbano."},
                    meta={"tokenizador": "otra-huella"})


def ids(resultado):
    assert isinstance(resultado, list), resultado
    return sorted(r.id for r in resultado)


def buscar(**filtros):
    resultado = mcp_legalize.buscar_ley.fn(pais=filtros.pop("pais", "tst"), limite=100, **filtros)
    if isinstance(resultado, list):
        conteo = mcp_legalize.contar_leyes.fn(pais=filtros.get("pais", "tst"), **filtros)
        assert conteo.total == len(resultado), "contar_leyes describe otra consulta"
    return resultado


def test_a_phrase_matches_only_the_laws_that_contain_it_in_order(corpus):
    assert ids(buscar(frase="arrendamiento urbano")) == ["INVERTIDA", "SEGUIDA"]


def test_the_same_words_as_texto_still_match_anywhere(corpus):
    assert ids(buscar(texto="arrendamiento urbano")) == ["INVERTIDA", "SEGUIDA", "SEPARADA"]


@pytest.mark.parametrize("frase,esperado", [
    ("ARRENDAMIENTO URBANO", ["INVERTIDA", "SEGUIDA"]),
    ("forêt domaniale", ["FORET"]),
    ("foret domaniale", ["FORET"]),
])
def test_a_phrase_is_folded_like_the_index(corpus, frase, esperado):
    assert ids(buscar(frase=frase)) == esperado


def test_short_words_count_inside_a_phrase(corpus):
    """`texto` drops words under three characters; a phrase cannot."""
    assert ids(buscar(frase="ley de 1978")) == ["LEY1978"]


@pytest.mark.parametrize("filtros,esperado", [
    ({"texto": "prorrogas"}, ["SEGUIDA"]),
    ({"fecha_hasta": "2015"}, ["INVERTIDA"]),
    ({"consulta": "seguida"}, ["SEGUIDA"]),
])
def test_a_phrase_combines_with_the_other_filters(corpus, filtros, esperado):
    assert ids(buscar(frase="arrendamiento urbano", **filtros)) == esperado


@pytest.mark.parametrize("frase", [
    'arrendamiento" OR "rustico', "arrendamiento AND urbano", "NEAR(arrendamiento urbano)",
    "arrend*", "texto:arrendamiento",
])
def test_nothing_in_a_phrase_is_read_as_syntax(corpus, frase):
    """FR-006: as text, none of these is a phrase any document contains."""
    assert ids(buscar(frase=frase)) == []


def test_punctuation_around_a_phrase_is_only_punctuation(corpus):
    assert ids(buscar(frase="(arrendamiento urbano)")) == ids(buscar(frase="arrendamiento urbano"))


def test_a_phrase_without_words_was_not_searched(corpus):
    conteo = mcp_legalize.contar_leyes.fn(pais="tst", frase="¿ — !")

    assert [(p.pais, p.motivo) for p in conteo.sin_consultar] == [("tst", "consulta_sin_terminos")]
    error = mcp_legalize.buscar_ley.fn(pais="tst", frase="¿ — !")
    assert isinstance(error, mcp_legalize.ErrorRespuesta)
    assert "frase" in error.error and "tres caracteres" not in error.error


def test_a_country_without_searchable_text_is_listed_as_not_searched(corpus):
    conteo = mcp_legalize.contar_leyes.fn(frase="arrendamiento urbano")

    assert conteo.total == 2
    assert [(p.pais, p.motivo) for p in conteo.sin_consultar] == [("otro", "tokenizador_distinto")]
