"""Tests that Greek and Cyrillic text is searchable, folded as its readers expect (ADR 0010).

The term pattern was `[0-9a-zñ]{3,}`, so a word in Greek or Cyrillic produced no
term at all and `texto` could not find it. Measured on 2026-10-19, that left out
of full-text search the multilingual annexes of 496 European laws in Cyrillic
(125,345 words) and 431 in Greek (26,167 words), and 35 and 37 Spanish ones.

Folding keeps working as ADR 0008 set it, with the same exception extended:
`ñ` stays a letter because folding it merges *año* with *ano*. In the same way
`й`, `ї` and `ў` are letters of their own in Russian, Bulgarian, Ukrainian and
Belarusian, so they are kept (`йод`, iodine, is not `иод`). `ё` folds to `е`,
the usual equivalence in Russian search, and Greek loses its accents and
diaeresis, as Greek search does.
"""

import pytest

import legalize_normalizacion as ln
import legalize_tokenizer as tk
import mcp_legalize


@pytest.fixture
def corpus(instalar_corpus):
    instalar_corpus("eu", {
        "BG": {"titulo": "Регламент за йода", "_ruta": "bg.md"},
        "EL": {"titulo": "Κανονισμός της Ευρωπαϊκής Ένωσης", "_ruta": "el.md"},
        "UK": {"titulo": "Угода з Україною", "_ruta": "uk.md"},
        "RU": {"titulo": "Иодированная соль", "_ruta": "ru.md"},
    }, {
        "BG": "Приложение I. Европейският съюз определя съдържанието на йод в солта.",
        "EL": "Παράρτημα I. Η Ευρωπαϊκή Ένωση καθορίζει την περιεκτικότητα.",
        "UK": "Додаток. Україна та Європейський союз погоджують ёлки.",
        "RU": "Приложение. Иод и елки.",
    })


def ids(**filtros):
    resultado = mcp_legalize.buscar_ley.fn(pais="eu", limite=100, **filtros)
    assert isinstance(resultado, list), resultado
    return sorted(r.id for r in resultado)


@pytest.mark.parametrize("texto,esperado", [
    ("Ευρωπαϊκή", ["EL"]),
    ("ευρωπαικη ενωση", ["EL"]),
    ("ΕΥΡΩΠΑΪΚΉ", ["EL"]),
    ("съюз", ["BG"]),
    ("союз", ["UK"]),
    ("Приложение", ["BG", "RU"]),
], ids=["greek accented", "greek folded", "greek upper", "bulgarian", "ukrainian", "cyrillic capital"])
def test_greek_and_cyrillic_words_are_found_in_the_body(corpus, texto, esperado):
    assert ids(texto=texto) == esperado


def test_short_i_is_its_own_letter(corpus):
    """`йод` (iodine, Bulgarian) and `иод` (the Russian spelling) are different words."""
    assert ids(texto="йод") == ["BG"]
    assert ids(texto="иод") == ["RU"]


def test_yi_is_its_own_letter(corpus):
    assert ids(texto="Україна") == ["UK"]
    assert ids(texto="украіна") == []


def test_yo_folds_to_ye(corpus):
    """The usual equivalence in Russian search: `ёлки` and `елки` are one word."""
    assert ids(texto="ёлки") == ["RU", "UK"]


def test_the_title_folds_the_same_way(corpus):
    """`consulta` and `texto` share the folding (principle III)."""
    assert ids(consulta="ευρωπαικης") == ["EL"]
    assert ids(consulta="йода") == ["BG"]


def test_a_phrase_in_greek_is_found(corpus):
    assert ids(frase="Ευρωπαϊκή Ένωση") == ["EL"]


@pytest.mark.parametrize("letra", ["й", "Й", "ї", "Ї", "ў", "Ў"])
def test_the_kept_letters_survive_normalisation_as_letters(letra):
    plegada = ln.normalizar(letra)

    assert plegada == letra.lower()
    assert tk.tokens(plegada * 3) == {plegada * 3}
