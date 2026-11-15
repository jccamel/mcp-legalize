"""Tests that a law whose text cannot be read is not served as an empty law (#68).

`_read_file` degrades to an empty string when the file is missing, the path is
rejected or the read fails. That keeps the tools answering, which was the point
(ADR 0002), but the empty string then travelled on as if it were the law:
`obtener_ley` returned an empty body with `texto_truncado=False`, and
`obtener_articulo` answered "Artículo no encontrado". Nothing told the client
that nobody had read the law (principle IV). Found on 2026-11-11.

It is easy to reach. The indexer keeps orphans unless `--remove-orphans` is
passed, so a law deleted from the corpus stays in the index pointing at
nothing; so does a file moved or renamed without reindexing.

Now `obtener_ley` answers with `ErrorRespuesta` when it was asked for the text
and could not read it, and `solo_metadata=True` still answers. `obtener_articulo`
keeps its own contract — the law was found, so `id`, `pais` and `titulo` are
real — with an `error` that is not "Artículo no encontrado". A file that exists
and has an empty body is still an empty law: that is what the source says.

Measured on 2026-11-15 on the six indices (140,241 laws): no law points at a
missing file and none has an empty body. This is a defect of the contract, not
of today's data.
"""

import pytest

import mcp_legalize
from mcp_legalize import ArticuloResultado, ErrorRespuesta, LeyCompleta

CUERPO = "# Ley\n\n###### Artículo 1.\n\nTexto.\n"
NO_ENCONTRADO = "Artículo no encontrado"


@pytest.fixture
def sin_fichero(instalar_corpus):
    raiz = instalar_corpus("t", {"LEY-1": {"titulo": "Ley de aguas", "_ruta": "es/ley.md"}},
                           {"LEY-1": CUERPO})
    (raiz / "es" / "ley.md").unlink()


@pytest.fixture
def ruta_rechazada(instalar_corpus):
    instalar_corpus("t", {"LEY-1": {"titulo": "Ley de aguas", "_ruta": "/etc/hosts"}})


@pytest.fixture
def cuerpo_vacio(instalar_corpus):
    instalar_corpus("t", {"LEY-1": {"titulo": "Ley de aguas", "_ruta": "es/ley.md"}},
                    {"LEY-1": ""})


@pytest.mark.parametrize("caso", ["sin_fichero", "ruta_rechazada"])
def test_obtener_ley_says_the_text_is_unavailable(request, caso):
    request.getfixturevalue(caso)

    resultado = mcp_legalize.obtener_ley.fn("LEY-1", pais="t")

    assert isinstance(resultado, ErrorRespuesta)
    assert "no está disponible" in resultado.error
    assert "LEY-1" in resultado.error


@pytest.mark.parametrize("caso", ["sin_fichero", "ruta_rechazada"])
def test_the_metadata_is_still_served(request, caso):
    """Asking only for the metadata never reads the file."""
    request.getfixturevalue(caso)

    resultado = mcp_legalize.obtener_ley.fn("LEY-1", pais="t", solo_metadata=True)

    assert isinstance(resultado, LeyCompleta)
    assert resultado.titulo == "Ley de aguas"


@pytest.mark.parametrize("caso", ["sin_fichero", "ruta_rechazada"])
def test_obtener_articulo_does_not_say_the_article_is_missing(request, caso):
    """"Artículo no encontrado" claims the law was read; it was not."""
    request.getfixturevalue(caso)

    resultado = mcp_legalize.obtener_articulo.fn("LEY-1", "1", pais="t")

    assert isinstance(resultado, ArticuloResultado)
    assert resultado.error is not None and resultado.error != NO_ENCONTRADO
    assert "no disponible" in resultado.error
    assert (resultado.id, resultado.titulo, resultado.texto) == ("LEY-1", "Ley de aguas", None)


def test_a_file_with_an_empty_body_is_still_an_empty_law(cuerpo_vacio):
    ley = mcp_legalize.obtener_ley.fn("LEY-1", pais="t")
    articulo = mcp_legalize.obtener_articulo.fn("LEY-1", "1", pais="t")

    assert isinstance(ley, LeyCompleta)
    assert ley.texto_truncado is False
    assert articulo.error == NO_ENCONTRADO
