"""Tests for the tokenizer that full-text search will be built on (#31, part 1).

This module is deliberately the whole of the tokenizing decision — the regex, the
minimum length, the normalization it depends on and the body-extraction rule —
because every one of those changes which documents a query matches, and a
posting list built under one set is wrong under another.

`huella` exists for the reason A3 recorded for the scanner ruleset: an index that
says *when* it was built but not *with what* leaves no way to tell a fresh index
from a stale one short of rebuilding blindly. It is a content hash rather than a
hand-maintained version because, in that issue's words, *"lo que depende de que
alguien se acuerde de actualizarlo, se desincroniza"*.

The tokenizer is presence-only: a document either contains a term or it does not.
That is what #31 decided when it chose set intersection over ranking, and the
choice is part of the fingerprint so a later move to term frequencies invalidates
old indices rather than silently mixing two formats.
"""

import pytest

import legalize_tokenizer as tk


# ─────────────────────────────── tokenizing ──────────────────────────────────

def test_splits_a_sentence_into_terms():
    assert tk.tokens("Ley de protección de datos") == {"ley", "proteccion", "datos"}


def test_terms_shorter_than_the_minimum_are_dropped():
    """`de`, `la`, `y` carry no search value and would dominate every posting list."""
    assert tk.tokens("de la ley y el orden") == {"ley", "orden"}


def test_a_term_appearing_twice_is_stored_once():
    """Presence, not frequency — the decision that keeps postings at ~85 MB."""
    assert tk.tokens("ley ley ley") == {"ley"}


def test_accents_are_folded_the_same_way_search_folds_them():
    """The tokenizer must agree with `buscar_ley`, or `texto` and `consulta`
    would disagree about what matches — the split-defence problem A1 and A2
    were filed to remove."""
    assert tk.tokens("protección") == tk.tokens("proteccion")


def test_case_is_folded():
    assert tk.tokens("LEY Orden") == {"ley", "orden"}


def test_digits_are_kept():
    """Article and law numbers are searchable terms."""
    assert "2020" in tk.tokens("Ley 5/2020 de medidas")


def test_punctuation_does_not_produce_terms():
    assert tk.tokens("ley, orden; ¿derecho?") == {"ley", "orden", "derecho"}


def test_empty_text_produces_no_terms():
    assert tk.tokens("") == set()


# ──────────────────────────── body extraction ────────────────────────────────

def test_frontmatter_is_not_indexed_as_body():
    """The metadata surface is served and scanned separately.

    Indexing it here would make a title term appear as a body hit, which is a
    different question from the one `texto` answers.
    """
    documento = "---\ntitle: Ley tributaria\n---\nEl arrendamiento urbano\n"

    assert tk.tokens_de_documento(documento) == {"arrendamiento", "urbano"}


def test_a_document_without_frontmatter_is_all_body():
    assert tk.tokens_de_documento("El arrendamiento urbano") == {"arrendamiento", "urbano"}


# ───────────────────────────────── huella ────────────────────────────────────

def test_the_fingerprint_is_stable_across_calls():
    """It identifies a ruleset, so it cannot depend on when it was asked."""
    assert tk.huella() == tk.huella()


def test_the_fingerprint_is_short_and_hexadecimal():
    """Same shape as the scanner's, since both land in `_meta` and get printed."""
    h = tk.huella()

    assert len(h) == 12
    assert all(c in "0123456789abcdef" for c in h)


@pytest.mark.parametrize("atributo, valor", [
    ("_PATRON_TOKEN", __import__("re").compile(r"[a-z]{4,}")),
    ("_MIN_LONGITUD", 4),
    ("_MODO", "frecuencia"),
])
def test_the_fingerprint_changes_when_the_rules_change(monkeypatch, atributo, valor):
    """Every input that alters a posting list must move the fingerprint.

    `_MODO` is in here because #31 chose presence over frequency. If that is
    ever revisited, indices built the old way must be rejected rather than
    silently mixed with new ones.
    """
    antes = tk.huella()
    monkeypatch.setattr(tk, atributo, valor)

    assert tk.huella() != antes


def test_the_fingerprint_covers_the_frontmatter_rule(monkeypatch):
    """What counts as body is part of the tokenizer, even though it lives elsewhere.

    Hashes the source of `separar` rather than its delimiter, because the rule is
    in the logic — what closes a block, what happens when nothing does — and A2
    was filed precisely because two implementations cut in different places.
    """
    import legalize_frontmatter

    antes = tk.huella()

    def separar_distinto(texto):
        return "", texto

    monkeypatch.setattr(legalize_frontmatter, "separar", separar_distinto)

    assert tk.huella() != antes


def test_the_fingerprint_covers_the_normalization_table(monkeypatch):
    """Folding is part of the tokenizer even though the table lives elsewhere.

    Issue #32 proposes changing exactly this for Swedish. When it does, every
    posting list built under the old folding has to be invalidated.
    """
    import mcp_legalize

    antes = tk.huella()
    tabla = dict(mcp_legalize._NORMALIZE_TABLE)
    tabla[ord("ö")] = ord("x")
    monkeypatch.setattr(mcp_legalize, "_NORMALIZE_TABLE", tabla)

    assert tk.huella() != antes
