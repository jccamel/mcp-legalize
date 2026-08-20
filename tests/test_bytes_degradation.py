"""Tests for issue #14: a malformed `_bytes` must cost its own entry, nothing more.

`_read_file` already settled the rule for the sibling path — *"una ley ilegible
degrada a texto vacío, no a un fallo"*. Reading a document's **size** did not
follow it: an index entry whose `_bytes` was present but not an integer let the
exception escape to the tool layer, and the healthy documents alongside it were
never returned.

Four of the six tools went down. `listar_paises` was the worst of them: it takes
no arguments, so a client could not steer around the bad entry — it could not
even enumerate the jurisdictions.

`.get("_bytes", 0)` defended against the key being *absent*. It never defended
against the key being *present and the wrong type*, which is what a crafted
index supplies. A compromised corpus is the documented threat model
(`README.md:10`), and it produces a compromised index.

The tests assert at the tool boundary rather than against the coercion helper.
The helper returning 0 proves nothing on its own: the defect was that a raw
value reached Pydantic and the arithmetic, so what has to stay true is that a
*tool call* survives, and that the healthy documents still come back.
"""

import pytest

import mcp_legalize


def documento(**campos):
    base = {
        "titulo": "Ley de prueba", "identificador": "XX-1", "pais": "xx",
        "rango": "ley", "estado": "in_force", "fecha_publicacion": "2020-01-01",
        "ultima_actualizacion": "2020-01-01", "fuente": "https://example.test",
        "_ruta": "xx/1.md", "_bytes": 10,
    }
    base.update(campos)
    return base


# Cada valor es algo que un índice manipulado puede llevar y `.get("_bytes", 0)`
# deja pasar intacto. `True` está aquí porque en Python es un `int` y un
# `isinstance(valor, int)` a secas lo aceptaría, contándolo como 1 byte.
VALORES_MALFORMADOS = ["not-an-int", None, [], {}, 3.7, True]


@pytest.fixture
def indice_con_entrada_corrupta(monkeypatch):
    """Un país con dos documentos sanos y uno corrupto en medio.

    Devuelve una función para elegir el valor malformado, de modo que cada test
    ejercite el mismo escenario con un tipo distinto.
    """
    def montar(valor_malo):
        docs = {
            "GOOD-1": documento(titulo="Ley buena", _bytes=10),
            "EVIL-1": documento(titulo="Ley hostil", _bytes=valor_malo),
            "GOOD-2": documento(titulo="Otra ley buena", _bytes=20),
        }
        monkeypatch.setitem(mcp_legalize._DOCS_POR_PAIS, "tst", docs)
        monkeypatch.setitem(mcp_legalize._META_POR_PAIS, "tst", {})
        monkeypatch.setitem(mcp_legalize._INDEX_FILE_POR_PAIS, "tst", "index_tst")
        return docs
    return montar


@pytest.mark.parametrize("valor_malo", VALORES_MALFORMADOS)
def test_buscar_ley_still_returns_the_healthy_documents(indice_con_entrada_corrupta, valor_malo):
    """One corrupt entry must not deny the client the other two."""
    indice_con_entrada_corrupta(valor_malo)

    resultados = mcp_legalize.buscar_ley.fn(pais="tst", limite=10)

    assert [r.id for r in resultados] == ["GOOD-1", "EVIL-1", "GOOD-2"]


@pytest.mark.parametrize("valor_malo", VALORES_MALFORMADOS)
def test_the_corrupt_entry_reports_zero_bytes(indice_con_entrada_corrupta, valor_malo):
    """The entry is served, with the unusable size degraded to 0.

    Dropping the document instead would hide a law from the client because its
    *metadata* was malformed. The text is what matters; the size is decoration.
    """
    indice_con_entrada_corrupta(valor_malo)

    resultados = mcp_legalize.buscar_ley.fn(pais="tst", limite=10)
    corrupto = next(r for r in resultados if r.id == "EVIL-1")

    assert corrupto.bytes == 0


@pytest.mark.parametrize("valor_malo", VALORES_MALFORMADOS)
def test_estadisticas_survives_and_counts_only_the_valid_sizes(
    indice_con_entrada_corrupta, valor_malo
):
    """`total_bytes += doc.get("_bytes", 0)` used to raise TypeError here."""
    indice_con_entrada_corrupta(valor_malo)

    stats = mcp_legalize.estadisticas.fn(pais="tst")

    assert stats.total_documentos == 3
    assert stats.total_megabytes == round(30 / 1_048_576, 1)


@pytest.mark.parametrize("valor_malo", VALORES_MALFORMADOS)
def test_listar_paises_survives(indice_con_entrada_corrupta, valor_malo):
    """The tool that takes no arguments, so a client cannot avoid the bad entry."""
    indice_con_entrada_corrupta(valor_malo)

    paises = mcp_legalize.listar_paises.fn()

    assert "tst" in [p.codigo for p in paises]


@pytest.mark.parametrize("valor_malo", VALORES_MALFORMADOS)
def test_obtener_ley_serves_the_corrupt_entry(indice_con_entrada_corrupta, valor_malo):
    """Asking for the corrupt document by id must not raise either."""
    indice_con_entrada_corrupta(valor_malo)

    ley = mcp_legalize.obtener_ley.fn("EVIL-1", pais="tst", solo_metadata=True)

    assert ley.id == "EVIL-1"


def test_a_valid_size_is_still_reported(indice_con_entrada_corrupta):
    """The guard must not flatten legitimate sizes to 0 on its way past."""
    indice_con_entrada_corrupta("not-an-int")

    resultados = mcp_legalize.buscar_ley.fn(pais="tst", limite=10)

    assert [r.bytes for r in resultados if r.id != "EVIL-1"] == [10, 20]
