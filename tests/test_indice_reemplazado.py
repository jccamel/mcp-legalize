"""Tests that the server serves the index on disk, not the one it opened (#78).

The indexer writes a new database and puts it in place with `os.replace`. A
running server kept its connection to the old file until it was restarted,
while the laws it read from disk were the new ones: searches answered from
the old index, and laws added by the pass did not exist for the server.

Each tool now checks, before answering, whether the file behind each index is
still the one it opened. One that changed is registered again, exactly as at
startup, so the answer is the one a restart would give: the new index if it can
be served, and no index for that country if it cannot.

The files are real and the asserts go through the tools.
"""

import os

import pytest

import legalize_indice
import mcp_legalize


@pytest.fixture
def entorno(tmp_path, monkeypatch):
    """An indices directory, an authorised repos dir, and the server's tables isolated."""
    indices = tmp_path / "indices"
    repos = tmp_path / "repos"
    indices.mkdir()
    repos.mkdir()
    monkeypatch.setattr(mcp_legalize, "INDICES_DIR", indices)
    monkeypatch.setattr(mcp_legalize, "REPOS_DIR", repos)
    for tabla in ("_CONEXIONES", "_META_POR_PAIS", "_INDEX_FILE_POR_PAIS",
                  "_RAIZ_POR_PAIS", "_TEXTO_NO_DISPONIBLE"):
        monkeypatch.setattr(mcp_legalize, tabla, {})
    return indices


def escribir(indices, nombre, pais, ids):
    """Writes an index the way the indexer does: a new file, then `os.replace`."""
    destino = legalize_indice.ruta_indice(indices, nombre)
    temporal = destino.with_name(destino.name + ".nuevo")
    escritor = legalize_indice.Escritor(temporal)
    escritor.poner_meta("pais", pais)
    for doc_id in ids:
        escritor.poner_ley(doc_id, {"titulo": f"Ley {doc_id}", "_ruta": f"{doc_id}.md", "_bytes": 10},
                           "Artículo 1\nTexto.\n")
    escritor.confirmar()
    os.replace(temporal, destino)
    return destino


def ids(pais):
    resultado = mcp_legalize.buscar_ley.fn(pais=pais, limite=50)
    return [r.id for r in resultado] if isinstance(resultado, list) else resultado


def paises():
    return [p.codigo for p in mcp_legalize.listar_paises.fn()]


def test_a_law_added_by_a_new_pass_is_served_without_a_restart(entorno):
    escribir(entorno, "legalize-t", "t", ["A-1"])
    mcp_legalize._load_indices()
    assert ids("t") == ["A-1"]

    escribir(entorno, "legalize-t", "t", ["A-1", "A-2"])

    assert ids("t") == ["A-1", "A-2"]
    assert mcp_legalize.obtener_ley.fn("A-2", pais="t", solo_metadata=True).id == "A-2"
    assert mcp_legalize.contar_leyes.fn(pais="t").total == 2
    assert mcp_legalize.estadisticas.fn(pais="t").total_documentos == 2


def test_a_law_removed_by_a_new_pass_is_no_longer_served(entorno):
    escribir(entorno, "legalize-t", "t", ["A-1", "A-2"])
    mcp_legalize._load_indices()

    escribir(entorno, "legalize-t", "t", ["A-1"])

    assert isinstance(mcp_legalize.obtener_ley.fn("A-2", pais="t", solo_metadata=True),
                      mcp_legalize.ErrorRespuesta)


def test_an_index_replaced_by_one_that_cannot_be_served_stops_being_served(entorno):
    """What a restart would do: the bad file costs that country, not the others."""
    ruta = escribir(entorno, "legalize-t", "t", ["A-1"])
    escribir(entorno, "legalize-u", "u", ["U-1"])
    mcp_legalize._load_indices()

    temporal = ruta.with_name("estropeado")
    temporal.write_bytes(b"esto no es una base de datos")
    os.replace(temporal, ruta)

    assert paises() == ["u"]
    assert ids("u") == ["U-1"]
    assert isinstance(mcp_legalize.obtener_ley.fn("A-1", solo_metadata=True), mcp_legalize.ErrorRespuesta)


def test_an_index_that_was_deleted_stops_being_served(entorno):
    ruta = escribir(entorno, "legalize-t", "t", ["A-1"])
    escribir(entorno, "legalize-u", "u", ["U-1"])
    mcp_legalize._load_indices()

    ruta.unlink()

    assert paises() == ["u"]


def test_an_index_that_now_declares_another_country_is_served_under_it(entorno):
    escribir(entorno, "legalize-t", "t", ["A-1"])
    mcp_legalize._load_indices()

    escribir(entorno, "legalize-t", "v", ["V-1"])

    assert paises() == ["v"]
    assert ids("v") == ["V-1"]


def test_an_index_that_did_not_change_is_not_opened_again(entorno, capsys):
    escribir(entorno, "legalize-t", "t", ["A-1"])
    mcp_legalize._load_indices()
    capsys.readouterr()

    for _ in range(3):
        assert ids("t") == ["A-1"]
    mcp_legalize.listar_paises.fn()

    assert capsys.readouterr().err == ""
