"""Tests for folding: every diacritic goes, `ñ` stays a letter (ADR 0008).

The folding table listed the Spanish, Swedish and a few other accented vowels
by hand. Anything it missed survived folding and then fell outside the token
pattern `[0-9a-z]`, which split the word into fragments. Measured on 2026-10-18
over samples of the three corpora:

    legalize-fr   875 distinct words broken (1.27% of occurrences):
                  être -> "tre", arrêté -> "arr", contrôle -> "contr", œuvre -> "uvre"
    legalize-es 1,864 distinct words broken (0.48% of occurrences):
                  año -> nothing, España -> "espa", enseñanza -> "ense"
    legalize-se    11 distinct words broken: daß, Maßnahmen

The fragments collided with each other: "être" searched as "tre" matched
connaître, paraître and maître.

Folding now removes every combining mark generically, so a corpus in a language
nobody listed still folds, plus a small table for letters Unicode does not
decompose (œ, æ, ß, ø, ł) and the Catalan middle dot. `ñ` is kept as a letter
and admitted by the token pattern: folding it to `n` would merge año with ano
and uña with una. Swedish keeps the folding ADR 0004 accepted.
"""

import pytest

import legalize_normalizacion as ln
import legalize_tokenizer as tk
import mcp_legalize


@pytest.mark.parametrize("palabra,termino", [
    # Francés: lo que antes se partía
    ("être", "etre"), ("arrêté", "arrete"), ("contrôle", "controle"),
    ("œuvre", "oeuvre"), ("Forêt", "foret"), ("sûreté", "surete"), ("août", "aout"),
    # Español: la ñ se conserva y deja de partir la palabra
    ("año", "año"), ("España", "españa"), ("ENSEÑANZA", "enseñanza"), ("diseño", "diseño"),
    # Alemán y otros que la tabla no listaba
    ("Maßnahmen", "massnahmen"), ("daß", "dass"), ("złoty", "zloty"), ("Ærø", "aero"),
    # Catalán: el punto volado no parte la palabra
    ("col·legi", "collegi"),
])
def test_a_word_folds_to_one_whole_term(palabra, termino):
    assert tk.tokens(palabra) == {termino}


def test_enye_keeps_words_apart_that_differ_only_by_it():
    """The reason ñ is not folded: año and ano are different words."""
    assert tk.tokens("año") != tk.tokens("ano")
    assert tk.tokens("uña") != tk.tokens("una")


@pytest.mark.parametrize("palabra,termino", [
    ("får", "far"), ("ändra", "andra"), ("Förordning", "forordning"),
    ("protección", "proteccion"), ("Çà", None), ("français", "francais"),
])
def test_what_was_already_folded_folds_the_same(palabra, termino):
    """ADR 0004 for Swedish, and every vowel the old table listed, unchanged."""
    assert tk.tokens(palabra) == ({termino} if termino else set())


def test_ordinals_and_ligatures_are_left_as_they_are():
    """Canonical decomposition only: `1º` and `ﬁ` are not diacritics."""
    assert ln.normalizar("1º") == "1º"
    assert ln.normalizar("ﬁn") == "ﬁn"


def test_title_search_folds_the_same_way(instalar_corpus, monkeypatch):
    """`consulta` and `texto` share the folding (principle III)."""
    instalar_corpus("fr", {
        "FR-1": {"titulo": "Code forestier — Forêt et SÛRETÉ", "_ruta": "x.md"},
        "ES-1": {"titulo": "Ley de Enseñanza del Año", "_ruta": "y.md"},
    })

    assert [r.id for r in mcp_legalize.buscar_ley.fn(pais="fr", consulta="foret et surete")] == ["FR-1"]
    assert [r.id for r in mcp_legalize.buscar_ley.fn(pais="fr", consulta="ENSEÑANZA del año")] == ["ES-1"]
    assert mcp_legalize.buscar_ley.fn(pais="fr", consulta="ensenanza") == []


def test_the_fingerprint_covers_the_folding_function_not_only_its_table(monkeypatch):
    """Changing how folding works must invalidate every index built before."""
    antes = tk.huella()
    monkeypatch.setattr(ln, "_MARCAS_RE", ln.re.compile(r"[̀-̂]"))

    assert tk.huella() != antes


def test_postings_with_the_new_terms_are_readable(tmp_path):
    """The postings format validated terms against its own copy of `[0-9a-z]{3,}`.

    Found measuring the Spanish corpus after the change: the first term with
    `ñ` made the whole file unreadable, and Spain lost full-text search. Two
    copies of one rule had diverged — the failure principle III exists to stop.
    The format now validates against the tokenizer's own pattern.
    """
    import legalize_postings as lp

    terminos = tk.tokens("año enseñanza œuvre forêt Maßnahmen")
    ruta = lp.ruta_postings(tmp_path, "tst")
    lp.escribir(ruta, {t: {"DOC-1"} for t in terminos}, tokenizador=tk.huella(), generacion="a" * 32)

    postings, motivo = lp.estado(tmp_path, "tst", tk.huella(), "a" * 32)

    assert motivo is None
    assert postings.docs("año") == {"DOC-1"}
