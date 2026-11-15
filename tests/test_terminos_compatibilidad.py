"""Tests that `texto` finds words with compatibility characters (#74, ADR 0013).

The query builds its terms with `legalize_tokenizer._PATRON_TOKEN`; the index
is FTS5 `unicode61`. A word with a character outside the pattern was one token
in the index and was split, or dropped, in the query, so `texto` could never
match it. Measured on 2026-11-15, counting index terms that the pattern cannot
produce: ordinals (`13ª`: es 639, se 121), superscripts and subscripts (`cm³`,
`co₂`: uk 2,331), ligatures (`aﬁliacion`, `beneﬁt`), Latin letters that do not
decompose (`ð`, `ı`, `ħ`) and modifier apostrophes that glue two words
(`bishopʼs`).

Text is now folded with compatibility decomposition, those letters are in the
folding table and the modifier apostrophes separate words, on both sides, so
the word is found whether it is written with the special character or without
it. Other scripts (Georgian, Arabic) stay out: ADR 0010 asks for a decision of
their own.

The asserts go through `buscar_ley` and `contar_leyes`.
"""

import pytest

import mcp_legalize

CUERPOS = {
    "QUIM-1": "Las emisiones de co₂ no superarán 10 hm³ por año.",
    "LIGA-1": "Régimen de aﬁliación a la Seguridad Social.",
    "ORDI-1": "Según la disposición 13ª del convenio.",
    "ISLA-1": "Lög um heilbrigðisþjónustu.",
    "APOS-1": "With the bishopʼs consent.",
    "OTRA-1": "Texto sin nada de eso.",
}


@pytest.fixture
def corpus(instalar_corpus):
    instalar_corpus("xx", {
        i: {"titulo": "Ley de aﬁliación" if i == "LIGA-1" else f"Ley {i}", "_ruta": f"{i}.md"}
        for i in CUERPOS
    }, cuerpos=CUERPOS)


def ids(**filtros):
    resultado = mcp_legalize.buscar_ley.fn(pais="xx", limite=50, **filtros)
    assert isinstance(resultado, list), resultado
    return [r.id for r in resultado]


@pytest.mark.parametrize("texto, esperado", [
    ("co2", "QUIM-1"), ("co₂", "QUIM-1"),
    ("hm3", "QUIM-1"), ("hm³", "QUIM-1"),
    ("afiliación", "LIGA-1"), ("aﬁliación", "LIGA-1"),
    ("13a", "ORDI-1"), ("13ª", "ORDI-1"),
    ("heilbrigdisthjonustu", "ISLA-1"), ("heilbrigðisþjónustu", "ISLA-1"),
    ("bishop", "APOS-1"),
])
def test_a_word_is_found_with_or_without_its_special_character(corpus, texto, esperado):
    assert ids(texto=texto) == [esperado]
    assert mcp_legalize.contar_leyes.fn(pais="xx", texto=texto).total == 1


def test_a_phrase_with_a_subscript_is_found(corpus):
    assert ids(frase="emisiones de co2") == ["QUIM-1"]


def test_the_title_filter_folds_the_same_way(corpus):
    """`consulta` and `texto` share the folding (principle III)."""
    assert ids(consulta="afiliacion") == ["LIGA-1"]
