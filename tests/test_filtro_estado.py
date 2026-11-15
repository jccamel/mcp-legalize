"""Tests that the `estado` filter matches a state, not a fragment of one (#71).

The filter was a substring match on the folded value, like `rango` and the
title, so `estado="repealed"` also returned the laws that are
`partially_repealed`: 3 French laws on the local indices of 2026-11-11, out of
10,252. The docstring of `buscar_ley` lists the two as different states.

`estado` is a closed vocabulary — measured on 2026-11-15 over the six local
indices: `in_force`, `repealed`, `expired`, `annulled`, `partially_repealed` —
so the filter compares the whole value, still without case or accents. The
other text filters keep matching substrings.
"""

import pytest

import mcp_legalize


@pytest.fixture
def corpus(instalar_corpus):
    instalar_corpus("fr", {
        "FR-1": {"titulo": "Loi abrogée", "estado": "repealed", "_ruta": "1.md"},
        "FR-2": {"titulo": "Loi partiellement abrogée", "estado": "partially_repealed", "_ruta": "2.md"},
        "FR-3": {"titulo": "Loi en vigueur", "estado": "in_force", "_ruta": "3.md"},
    })


def ids(**filtros):
    return [r.id for r in mcp_legalize.buscar_ley.fn(limite=50, **filtros)]


def test_repealed_does_not_return_partially_repealed(corpus):
    assert ids(estado="repealed") == ["FR-1"]
    assert mcp_legalize.contar_leyes.fn(estado="repealed").total == 1


def test_partially_repealed_returns_its_laws(corpus):
    assert ids(estado="partially_repealed") == ["FR-2"]
    assert mcp_legalize.contar_leyes.fn(estado="partially_repealed").total == 1


@pytest.mark.parametrize("pedido", ["Repealed", " REPEALED "])
def test_the_state_is_compared_without_case_or_surrounding_spaces(corpus, pedido):
    assert ids(estado=pedido) == ["FR-1"]


def test_a_fragment_of_a_state_is_not_a_state(corpus):
    assert ids(estado="repeal") == []
    assert mcp_legalize.contar_leyes.fn(estado="repeal").total == 0


def test_other_text_filters_still_match_substrings(corpus):
    """`rango`, `departamento` and the title are open vocabularies."""
    assert ids(consulta="abrog") == ["FR-1", "FR-2"]
