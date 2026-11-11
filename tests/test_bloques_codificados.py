"""Tests that looking for encoded blocks costs one attempt per run, not one per character.

`obtener_ley` and `obtener_articulo` look for base64 blocks in the text they
are about to serve. The pattern was `[A-Za-z0-9+/]{60,}={1,2}`, and it could
begin a match at any character: over a long run of letters with no `=` after
it, every position was a new attempt that walked to the end of the run and
back. Measured on 2026-11-11: 20,000 letters took 1.17 s, so the 80,000
characters `obtener_ley` serves by default took about 19 s, on every call. One
hostile file was enough to hang the server, and the corpus is the attacker
(principle II).

Nothing here measures time (CONTRIBUTING): what is pinned is the property that
caused the repetition. A pattern that cannot begin in the middle of a run has
one place to start per run.
"""

import logging

import mcp_legalize

TIRADA = "A" * 500


def test_a_run_of_base64_letters_offers_a_single_place_to_start():
    """Mid-run, the pattern may not begin a match: that is what made the cost quadratic."""
    patron = next(p for p, tipo in mcp_legalize._SUSPICIOUS_ENCODING_PATTERNS if tipo == "base64_block")
    texto = TIRADA + "=="

    assert patron.match(texto, 0)
    assert [pos for pos in range(1, len(TIRADA) - 80) if patron.match(texto, pos)] == []


def test_a_base64_block_is_still_reported_when_a_law_is_served(instalar_corpus, caplog):
    """The fix must not silence the check: a padded block in a body is logged."""
    cuerpo = "# Ley\n\nAnexo " + TIRADA + "== fin\n"
    instalar_corpus("t", {"LEY-1": {"titulo": "Ley", "_ruta": "ley.md"}}, {"LEY-1": cuerpo})
    with caplog.at_level(logging.WARNING, logger="mcp_legalize.security"):
        mcp_legalize.obtener_ley.fn("LEY-1", pais="t")

    assert sum("base64_block" in r.getMessage() for r in caplog.records) == 1


def test_no_more_than_three_blocks_of_a_kind_are_reported(instalar_corpus, caplog):
    cuerpo = "# Ley\n\n" + " ".join(TIRADA + "=" for _ in range(10)) + "\n"
    instalar_corpus("t", {"LEY-1": {"titulo": "Ley", "_ruta": "ley.md"}}, {"LEY-1": cuerpo})
    with caplog.at_level(logging.WARNING, logger="mcp_legalize.security"):
        mcp_legalize.obtener_ley.fn("LEY-1", pais="t")

    assert sum("base64_block" in r.getMessage() for r in caplog.records) == 3
