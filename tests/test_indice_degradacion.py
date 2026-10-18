"""Tests that a malformed index costs what is malformed, nothing more (#18, ADR 0002).

They replace `test_index_shape`, which pinned the same invariants on the JSON
index: a container of the wrong type was skipped, a healthy neighbour survived,
the server still started, and an entry of the wrong shape cost that entry.

The database moves where each invariant can break. A whole file can still be
unusable — not SQLite, a schema with something added, another format — and
`legalize_indice.abrir` refuses it; what has to stay true is that the refusal
costs that corpus and the server goes on with the others. Inside a database the
schema fixes the columns, but not the type of each value: SQLite stores the type
of the value, not of the column, so a crafted file can put a blob or a number
where a title goes. That row is served with what can be read of it.

The tests load real files through `_load_indices` and assert through the tools,
as the old ones did.
"""

import sqlite3

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


def escribir(indices, nombre, pais, documentos):
    escritor = legalize_indice.Escritor(legalize_indice.ruta_indice(indices, nombre))
    escritor.poner_meta("pais", pais)
    for doc_id, entry in documentos.items():
        escritor.poner_ley(doc_id, entry, "Artículo 1\nTexto.\n")
    escritor.confirmar()
    return legalize_indice.ruta_indice(indices, nombre)


def manipular(ruta, *sentencias, defensivo=True):
    """Altera una base de datos como lo haría quien controla el fichero."""
    con = sqlite3.connect(ruta)
    if not defensivo:
        con.setconfig(sqlite3.SQLITE_DBCONFIG_DEFENSIVE, False)
    for sentencia in sentencias:
        con.execute(sentencia)
    con.commit()
    con.close()


SANO = {"A": {"titulo": "Ley buena", "_ruta": "a.md", "_bytes": 10}}


def no_sqlite(ruta):
    ruta.write_bytes(b"\x80\x05 esto no es una base de datos")


def vacio(ruta):
    ruta.write_bytes(b"")


def con_trigger(ruta):
    manipular(ruta, "CREATE TRIGGER t AFTER INSERT ON meta BEGIN DELETE FROM leyes; END")


def otro_formato(ruta):
    manipular(ruta, "UPDATE meta SET valor = '\"99\"' WHERE clave = 'formato'")


def truncado(ruta):
    ruta.write_bytes(ruta.read_bytes()[:3000])


ESTROPEAR = [no_sqlite, vacio, con_trigger, otro_formato, truncado]


def cargar():
    mcp_legalize._load_indices()
    return mcp_legalize._CONEXIONES


# ─────────────────────── a whole file that cannot be used ────────────────────

@pytest.mark.parametrize("estropear", ESTROPEAR, ids=lambda f: f.__name__)
def test_an_unusable_database_is_skipped(entorno, estropear):
    estropear(escribir(entorno, "legalize-t", "t", SANO))

    assert cargar() == {}


@pytest.mark.parametrize("estropear", ESTROPEAR, ids=lambda f: f.__name__)
def test_a_healthy_index_survives_an_unusable_neighbour(entorno, estropear):
    """The failure must cost the bad file, never the good one beside it."""
    estropear(escribir(entorno, "legalize-t", "t", SANO))
    escribir(entorno, "legalize-sano", "sano", SANO)

    assert list(cargar()) == ["sano"]
    assert [r.id for r in mcp_legalize.buscar_ley.fn()] == ["A"]


@pytest.mark.parametrize("estropear", ESTROPEAR, ids=lambda f: f.__name__)
def test_the_total_can_be_computed_after_skipping_a_database(entorno, estropear):
    """`_TOTAL_DOCS` is computed in the module body, outside any per-file guard."""
    estropear(escribir(entorno, "legalize-t", "t", SANO))

    conexiones = cargar()

    assert sum(c.execute("SELECT count(*) FROM leyes").fetchone()[0] for c in conexiones.values()) == 0


def test_a_valid_index_is_unaffected(entorno):
    escribir(entorno, "legalize-sano", "sano", SANO)

    cargar()

    assert [r.id for r in mcp_legalize.buscar_ley.fn(pais="sano")] == ["A"]


# ────────────────────── a row with values of the wrong type ──────────────────

@pytest.fixture
def con_fila_corrupta(entorno):
    ruta = escribir(entorno, "legalize-t", "t", {
        "GOOD-1": {"titulo": "Ley buena", "rango": "ley", "_ruta": "a.md", "_bytes": 10},
        "EVIL-1": {"titulo": "Ley hostil", "rango": "ley", "_ruta": "e.md", "_bytes": 5},
        "GOOD-2": {"titulo": "Otra buena", "rango": "ley", "_ruta": "b.md", "_bytes": 20},
    })
    manipular(ruta, "UPDATE leyes SET titulo = x'00ff', rango = 12, estado = 3.5, "
                    "fecha_publicacion = x'01', fuente = -1, ruta = 7, mtime = 'ayer' "
                    "WHERE id = 'EVIL-1'")
    cargar()


def test_the_tools_keep_working_with_a_row_of_the_wrong_types(con_fila_corrupta):
    """The defect's signature in #18: four tools raised on one bad entry."""
    assert [r.id for r in mcp_legalize.buscar_ley.fn(pais="t", limite=10)] == ["GOOD-1", "EVIL-1", "GOOD-2"]
    assert mcp_legalize.contar_leyes.fn(pais="t").total == 3
    assert mcp_legalize.listar_paises.fn()[0].codigo == "t"
    assert mcp_legalize.estadisticas.fn(pais="t").total_documentos == 3
    assert mcp_legalize.listar_rangos.fn(pais="t") is not None


def test_the_row_of_the_wrong_types_is_served_with_what_can_be_read(con_fila_corrupta):
    ley = mcp_legalize.obtener_ley.fn("EVIL-1", pais="t", solo_metadata=True)

    assert ley.id == "EVIL-1"
    assert isinstance(ley.titulo, str)


def test_filters_keep_working_over_a_row_of_the_wrong_types(con_fila_corrupta):
    resultados = mcp_legalize.buscar_ley.fn(pais="t", consulta="buena", rango="ley", fecha_desde="2000")

    assert isinstance(resultados, list)


# ─────────────────────────────── the meta table ──────────────────────────────

def test_a_malformed_meta_still_degrades(entorno):
    """A value that is not JSON is ignored; the country comes from the file name."""
    ruta = escribir(entorno, "legalize-t", "t", SANO)
    manipular(ruta, "UPDATE meta SET valor = 'no es json' WHERE clave = 'pais'")

    conexiones = cargar()

    assert sum(c.execute("SELECT count(*) FROM leyes").fetchone()[0] for c in conexiones.values()) == 1


def test_a_country_that_is_not_text_still_degrades(entorno):
    ruta = escribir(entorno, "legalize-t", "t", SANO)
    manipular(ruta, "UPDATE meta SET valor = '[1, 2]' WHERE clave = 'pais'")

    conexiones = cargar()

    assert len(conexiones) == 1
