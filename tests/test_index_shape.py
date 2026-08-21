"""Tests for issue #18: the index container must be validated, not just its root.

`_load_indices` checked that the JSON root was a dict and nothing else. What it
took out of that dict — `documentos`, and the entries inside it — reached the
tools raw, so a crafted index broke them in two different ways:

- `documentos` as a str or a list, or an entry that is not a dict, left four of
  the six tools raising `AttributeError`;
- `documentos: null` stored the bad value in `_DOCS_POR_PAIS` *before* the
  failing `len()`, so the per-file `except` logged an error over an already
  poisoned dict and the module body then died on it. The server did not start.

That second one is the reason this is not another field-level fix. A healthy
index sitting in the same directory was lost too, and an MCP client saw a dead
server rather than a tool error.

`_meta` is the counter-example worth keeping in mind: it degrades correctly on
any shape because every read of it goes through `.get()` with a default. The
tests below pin that same outcome for `documentos`, at the level where the
index enters the process rather than at each consumer.
"""

import json

import pytest

import mcp_legalize


def escribir_indice(directorio, contenido, nombre="index_t.json"):
    directorio.mkdir(parents=True, exist_ok=True)
    (directorio / nombre).write_text(json.dumps(contenido), encoding="utf-8")
    return directorio


def cargar(directorio, monkeypatch):
    """Vuelve a ejecutar la carga apuntando a un directorio de prueba.

    `_load_indices` escribe en diccionarios de módulo, así que se aíslan con
    monkeypatch para no arrastrar estado entre tests.
    """
    monkeypatch.setattr(mcp_legalize, "INDICES_DIR", directorio)
    monkeypatch.setattr(mcp_legalize, "_DOCS_POR_PAIS", {})
    monkeypatch.setattr(mcp_legalize, "_META_POR_PAIS", {})
    monkeypatch.setattr(mcp_legalize, "_INDEX_FILE_POR_PAIS", {})
    mcp_legalize._load_indices()
    return mcp_legalize._DOCS_POR_PAIS


DOCUMENTOS_MALFORMADOS = ["no-es-dict", [1, 2], None, 7, True]

INDICE_SANO = {
    "_meta": {"pais": "sano"},
    "documentos": {"A": {"titulo": "Ley buena", "_ruta": "a.md", "_bytes": 10}},
}


@pytest.mark.parametrize("documentos", DOCUMENTOS_MALFORMADOS)
def test_an_index_with_a_malformed_documentos_is_skipped(tmp_path, monkeypatch, documentos):
    """A container of the wrong type must not be stored at all."""
    escribir_indice(tmp_path, {"_meta": {"pais": "t"}, "documentos": documentos})

    assert cargar(tmp_path, monkeypatch) == {}


@pytest.mark.parametrize("documentos", DOCUMENTOS_MALFORMADOS)
def test_a_healthy_index_survives_a_malformed_neighbour(tmp_path, monkeypatch, documentos):
    """The failure must cost the bad file, never the good one beside it.

    This is the case that made #18 worse than a tool-level defect: the process
    died before serving anything, so the healthy corpus was lost with it.
    """
    escribir_indice(tmp_path, {"_meta": {"pais": "t"}, "documentos": documentos})
    escribir_indice(tmp_path, INDICE_SANO, nombre="index_sano.json")

    cargado = cargar(tmp_path, monkeypatch)

    assert list(cargado) == ["sano"]


@pytest.mark.parametrize("documentos", DOCUMENTOS_MALFORMADOS)
def test_total_docs_can_be_computed_after_loading_a_malformed_index(
    tmp_path, monkeypatch, documentos
):
    """`_TOTAL_DOCS` runs in the module body, outside the per-file `except`.

    The old code stored `documentos` before the `len()` that failed, so the
    guard logged an error over an already poisoned dict and this sum — the
    module-body line the guard never covered — killed the import.
    """
    escribir_indice(tmp_path, {"_meta": {"pais": "t"}, "documentos": documentos})

    cargado = cargar(tmp_path, monkeypatch)

    assert sum(len(d) for d in cargado.values()) == 0


def test_entries_that_are_not_dicts_are_dropped_and_the_rest_kept(tmp_path, monkeypatch):
    """One malformed entry costs that entry, following `_bytes_de` and `_read_file`.

    Rejecting the whole file would make a single bad document hide a corpus.
    """
    escribir_indice(tmp_path, {"_meta": {"pais": "t"}, "documentos": {
        "GOOD-1": {"titulo": "Ley buena", "_ruta": "a.md", "_bytes": 10},
        "EVIL-1": "no-es-dict",
        "EVIL-2": [1, 2],
        "GOOD-2": {"titulo": "Otra buena", "_ruta": "b.md", "_bytes": 20},
    }})

    cargado = cargar(tmp_path, monkeypatch)

    assert sorted(cargado["t"]) == ["GOOD-1", "GOOD-2"]


def test_the_tools_keep_working_when_an_entry_was_dropped(tmp_path, monkeypatch):
    """The defect's signature: four tools raised `AttributeError` on a bad entry."""
    escribir_indice(tmp_path, {"_meta": {"pais": "t"}, "documentos": {
        "GOOD-1": {"titulo": "Ley buena", "_ruta": "a.md", "_bytes": 10},
        "EVIL-1": "no-es-dict",
    }})
    cargar(tmp_path, monkeypatch)

    assert [r.id for r in mcp_legalize.buscar_ley.fn(pais="t", limite=10)] == ["GOOD-1"]
    assert mcp_legalize.listar_paises.fn()[0].codigo == "t"
    assert mcp_legalize.estadisticas.fn(pais="t").total_documentos == 1
    assert mcp_legalize.listar_rangos.fn(pais="t") is not None


def test_a_valid_index_is_unaffected(tmp_path, monkeypatch):
    """The guard must not cost a well-formed index anything."""
    escribir_indice(tmp_path, INDICE_SANO)

    cargado = cargar(tmp_path, monkeypatch)

    assert list(cargado["sano"]) == ["A"]


def test_a_malformed_meta_still_degrades_as_it_already_did(tmp_path, monkeypatch):
    """`_meta` was never the problem — this pins that the fix does not break it."""
    escribir_indice(tmp_path, {"_meta": "roto", "documentos": {
        "A": {"titulo": "Ley buena", "_ruta": "a.md", "_bytes": 10},
    }})

    cargado = cargar(tmp_path, monkeypatch)

    assert sum(len(d) for d in cargado.values()) == 1
