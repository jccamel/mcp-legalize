"""Tests for how the six MCP tools signal failure.

Five tools returned a union with `ErrorRespuesta`; `obtener_articulo` carried an
optional `error` field inside its success model instead. Two failure shapes on
one surface means a client cannot rely on the type and has to special-case one
tool — and it has to special-case it *everywhere*, because the nested form gives
no way to tell "nothing to return" from "found the law, not the article".

The fix is not to collapse everything into one shape. The three failure paths of
`obtener_articulo` are not the same event:

    no indices                  nothing to return  -> ErrorRespuesta
    law missing or ambiguous    nothing to return  -> ErrorRespuesta
    law found, article missing  id/pais/titulo are real information
                                                   -> ArticuloResultado.error

So the union covers the two that carry no payload, and the nested field survives
for the one case where it is not a failure but a partial result. The client's
special case now means something instead of being an accident.

A second defect went with it: `_resolve_ley` formatted the matches of an
ambiguous id into the message as a Python list repr, while `ErrorRespuesta`
already had a `sugerencias` field for exactly that. Structured data serialized
into prose has to be parsed back out, and those matches are corpus-derived
identifiers — untrusted text that now goes through the same sanitizer as every
other value returned to the model.
"""

import pytest

import mcp_legalize
from mcp_legalize import ArticuloResultado, ErrorRespuesta


SIN_INDICES = "No hay índices disponibles."

# Every tool, with the minimum arguments each needs.
HERRAMIENTAS = [
    pytest.param("listar_paises", {}, id="listar_paises"),
    pytest.param("buscar_ley", {"consulta": "x"}, id="buscar_ley"),
    pytest.param("obtener_ley", {"id_ley": "X-1"}, id="obtener_ley"),
    pytest.param("obtener_articulo", {"id_ley": "X-1", "articulo": "1"}, id="obtener_articulo"),
    pytest.param("listar_rangos", {}, id="listar_rangos"),
    pytest.param("estadisticas", {}, id="estadisticas"),
]


def llamar(nombre, argumentos):
    return getattr(mcp_legalize, nombre).fn(**argumentos)


# ─────────────────────────── One shape for "nothing to return" ───────────────

@pytest.mark.parametrize("nombre,argumentos", HERRAMIENTAS)
def test_every_tool_signals_a_missing_index_the_same_way(nombre, argumentos):
    """The headline of B1: the type alone tells the client it failed.

    `_DOCS_POR_PAIS` is empty in the suite because conftest points the server at
    a directory that does not exist, which is precisely this condition.
    """
    assert mcp_legalize._DOCS_POR_PAIS == {}, "el escenario no es el que se cree"

    assert isinstance(llamar(nombre, argumentos), ErrorRespuesta)


@pytest.mark.parametrize("nombre,argumentos", HERRAMIENTAS)
def test_every_tool_words_it_the_same_way(nombre, argumentos):
    """B2. Two spellings of one condition — `No índices disponibles` with no verb
    and no period — meant a client matching on the text saw two failures where
    there is one."""
    assert llamar(nombre, argumentos).error == SIN_INDICES


# ─────────────────────────── The three paths of obtener_articulo ─────────────

@pytest.fixture
def corpus(monkeypatch):
    """Two laws under one country, sharing a prefix that is not itself a key.

    The ids matter. `_resolve_ley` resolves an exact match before it considers
    prefixes, so if the shared prefix were also a key it would resolve cleanly
    and never reach the ambiguity branch. `XX-1` is a prefix of both and a key
    of neither.
    """
    docs = {
        "XX-10": {
            "titulo": "Ley Primera", "identificador": "XX-10", "pais": "xx",
            "rango": "ley", "estado": "in_force", "fecha_publicacion": "2020-01-01",
            "ultima_actualizacion": "2020-01-01", "fuente": "https://example.test",
            "_ruta": "xx/10.md",
        },
        "XX-12": {
            "titulo": "Ley Segunda", "identificador": "XX-12", "pais": "xx",
            "rango": "ley", "estado": "in_force", "fecha_publicacion": "2020-01-01",
            "ultima_actualizacion": "2020-01-01", "fuente": "https://example.test",
            "_ruta": "xx/12.md",
        },
    }
    monkeypatch.setitem(mcp_legalize._DOCS_POR_PAIS, "xx", docs)
    monkeypatch.setattr(mcp_legalize, "_read_file",
                        lambda doc, pais: "Artículo 1\nEl texto del primero.")
    return docs


def test_a_missing_law_is_a_plain_failure(corpus):
    resultado = mcp_legalize.obtener_articulo.fn(id_ley="XX-999", articulo="1")

    assert isinstance(resultado, ErrorRespuesta)
    assert "XX-999" in resultado.error


def test_an_ambiguous_id_returns_its_matches_as_data(corpus):
    """`XX-1` is a prefix of both laws.

    The matches used to be formatted into the message as a Python list repr, so
    a client that wanted to offer them had to parse prose back into a list.
    """
    resultado = mcp_legalize.obtener_articulo.fn(id_ley="XX-1", articulo="1", pais="xx")

    assert isinstance(resultado, ErrorRespuesta)
    assert sorted(resultado.sugerencias) == ["XX-10", "XX-12"]
    assert "XX-12" not in resultado.error, "las coincidencias no van en el mensaje"


def test_an_exact_id_wins_over_an_ambiguous_prefix(corpus):
    """`XX-10` is a key and also a prefix of nothing else — it resolves."""
    resultado = mcp_legalize.obtener_articulo.fn(id_ley="XX-10", articulo="1", pais="xx")

    assert isinstance(resultado, ArticuloResultado)
    assert resultado.id == "XX-10"


def test_a_missing_article_keeps_the_law_it_searched(corpus):
    """The one case that is neither success nor failure.

    Collapsing this into `ErrorRespuesta` would drop `id`, `pais` and `titulo`,
    and the client would have to search again to learn which law it was.
    """
    resultado = mcp_legalize.obtener_articulo.fn(id_ley="XX-10", articulo="9999", pais="xx")

    assert isinstance(resultado, ArticuloResultado)
    assert resultado.error == "Artículo no encontrado"
    assert (resultado.id, resultado.pais, resultado.titulo) == ("XX-10", "xx", "Ley Primera")


def test_a_found_article_carries_no_error(corpus):
    resultado = mcp_legalize.obtener_articulo.fn(id_ley="XX-10", articulo="1", pais="xx")

    assert isinstance(resultado, ArticuloResultado)
    assert resultado.error is None
    assert resultado.texto


def test_obtener_ley_gains_the_same_structured_suggestions(corpus):
    """`_resolve_ley` is shared, so the second caller had the same defect."""
    resultado = mcp_legalize.obtener_ley.fn(id_ley="XX-1", pais="xx")

    assert isinstance(resultado, ErrorRespuesta)
    assert sorted(resultado.sugerencias) == ["XX-10", "XX-12"]


# ─────────────────────────── Suggestions are untrusted text ──────────────────

def test_suggestions_are_sanitized_like_any_other_metadata(monkeypatch):
    """Document ids come from the corpus, so they reach the model as untrusted.

    Moving them out of the message and into a field is not enough on its own —
    it changes where they are printed, not what they may contain.
    """
    docs = {
        "XX-9-<SCRIPT>": {"titulo": "A", "pais": "xx", "_ruta": "xx/a.md"},
        "XX-9-B": {"titulo": "B", "pais": "xx", "_ruta": "xx/b.md"},
    }
    monkeypatch.setitem(mcp_legalize._DOCS_POR_PAIS, "xx", docs)

    resultado = mcp_legalize.obtener_articulo.fn(id_ley="XX-9", articulo="1", pais="xx")

    assert isinstance(resultado, ErrorRespuesta)
    assert not any("<SCRIPT" in s for s in resultado.sugerencias)
    assert any("[filtered]" in s for s in resultado.sugerencias)


def test_the_echoed_id_is_sanitized_too(monkeypatch):
    """The not-found message echoes what was asked for; it is model-supplied."""
    monkeypatch.setitem(mcp_legalize._DOCS_POR_PAIS, "xx", {"XX-1": {"_ruta": "xx/1.md"}})

    resultado = mcp_legalize.obtener_articulo.fn(id_ley="<script>alert(1)</script>", articulo="1")

    assert isinstance(resultado, ErrorRespuesta)
    assert "<SCRIPT" not in resultado.error
