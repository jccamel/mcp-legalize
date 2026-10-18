"""Tests for `legalize_indice`, the per-corpus database the index moves to (spec 002).

The index used to be a JSON file loaded whole into memory plus a postings file in
a format this project owned. Nearly every defect fixed after 2026-10-16 came from
that hand-written infrastructure: unsafe deserialisation, postings lost on
incremental runs, generations and write order, a validator copying the
tokenizer's pattern. A SQLite database per corpus replaces both, measured on the
Spanish corpus at 27 MB resident against 363 and sub-millisecond queries.

These tests pin the format itself:

- **Round trip.** What the indexer writes, `como_dict` reads back in the shape
  the JSON index had, so the tests that inspect a generated index keep their
  assertions (plan.md, "Cambios en tests existentes").
- **The schema is the whitelist.** `sqlite_master` must equal the canonical SQL
  exactly; `abrir` refuses anything else before running a single query
  (research R2). The security tests live in `test_indice_seguridad.py`.
- **Absent values are empty strings**, as an absent JSON key behaved, and
  `estado_texto` is stored resolved.
"""

import sqlite3

import pytest

import legalize_indice as li
import legalize_tokenizer as tk

CUERPO_A = "###### Artículo 1. Objeto.\n\nEl arrendamiento urbano.\n\n###### Artículo 2.\n\nEl segundo.\n"
CUERPO_B = "##### 1 §\n\nFörsta.\n"


def campos(**extra):
    base = {
        "titulo": "Ley de prueba", "pais": "tst", "rango": "ley", "estado": "in_force",
        "fecha_publicacion": "2001-05-01", "ultima_actualizacion": "2020-01-01",
        "fuente": "https://example.test", "_ruta": "d/a.md", "_bytes": 10, "_mtime": 1.5,
        "estado_texto": "point_in_time",
    }
    base.update(extra)
    return base


@pytest.fixture
def indice(tmp_path):
    ruta = li.ruta_indice(tmp_path, "tst")
    escritor = li.Escritor(ruta)
    escritor.poner_ley("TST-A", campos(departamento="Hacienda", ultima_modificacion="X-9",
                                       estado_texto="as_enacted"), CUERPO_A)
    escritor.poner_ley("TST-B", campos(_ruta="d/b.md", titulo="Lag"), CUERPO_B)
    escritor.poner_meta("patrones", "03446b5a64e4")
    escritor.poner_meta("tokenizador", tk.huella())
    escritor.poner_meta("pais_predeterminado", "tst")
    escritor.poner_meta("seguridad", {"escaneado_en": "2026-10-18T00:00:00", "patrones": "03446b5a64e4",
                                      "cuarentena": {}, "forzados": {}, "avisos": {}, "duplicados": {},
                                      "metadatos": {}, "truncados": {}})
    escritor.confirmar()
    return ruta


def test_the_database_is_one_file_named_after_the_index(tmp_path, indice):
    assert indice == tmp_path / "index_tst.db"
    assert [p.name for p in tmp_path.iterdir()] == ["index_tst.db"]


def test_como_dict_returns_the_shape_the_json_index_had(indice):
    datos = li.como_dict(indice)

    a = datos["documentos"]["TST-A"]
    assert a["titulo"] == "Ley de prueba"
    assert a["identificador"] == "TST-A"
    assert a["pais"] == "tst"
    assert (a["_ruta"], a["_bytes"], a["_mtime"]) == ("d/a.md", 10, 1.5)
    assert a["departamento"] == "Hacienda"
    assert (a["estado_texto"], a["ultima_modificacion"]) == ("as_enacted", "X-9")
    assert datos["_meta"]["patrones"] == "03446b5a64e4"
    assert set(datos["_meta"]["seguridad"]) == {
        "escaneado_en", "patrones", "cuarentena", "forzados", "avisos",
        "duplicados", "metadatos", "truncados",
    }
    assert datos["_meta"]["total_documentos"] == 2


def test_optional_fields_absent_in_the_frontmatter_are_absent_in_the_shape(indice):
    """The JSON only carried them when present; `como_dict` keeps that."""
    b = li.como_dict(indice)["documentos"]["TST-B"]

    for campo in ("departamento", "jurisdiccion", "fecha_derogacion", "derogado_por", "ultima_modificacion"):
        assert campo not in b


def test_documents_keep_the_order_they_were_written_in(indice):
    """Results come out in corpus order, as the JSON's insertion order did."""
    assert list(li.como_dict(indice)["documentos"]) == ["TST-A", "TST-B"]


def test_ids_are_unique_without_regard_to_case(tmp_path):
    escritor = li.Escritor(li.ruta_indice(tmp_path, "tst"))
    escritor.poner_ley("TST-A", campos(), CUERPO_A)

    with pytest.raises(sqlite3.IntegrityError):
        escritor.poner_ley("tst-a", campos(), CUERPO_A)


def test_an_absent_text_state_is_stored_resolved(tmp_path):
    escritor = li.Escritor(li.ruta_indice(tmp_path, "tst"))
    sin = campos(); del sin["estado_texto"]
    escritor.poner_ley("TST-C", sin, CUERPO_B)
    escritor.confirmar()

    assert li.como_dict(li.ruta_indice(tmp_path, "tst"))["documentos"]["TST-C"]["estado_texto"] == "point_in_time"


def test_the_schema_is_exactly_the_canonical_one(indice):
    """The whitelist `abrir` checks before any query (research R2)."""
    con = sqlite3.connect(indice)
    filas = {(t, n, s) for t, n, s in con.execute(
        "SELECT type, name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' AND sql IS NOT NULL")}

    assert filas == li.esquema_esperado()
    assert dict(con.execute("SELECT clave, valor FROM meta"))["formato"] == f'"{li.FORMATO}"'


def test_a_written_database_opens_through_the_hardened_path(indice):
    con = li.abrir(indice)

    assert con.execute("SELECT count(*) FROM leyes").fetchone()[0] == 2


def test_articles_are_located_once_when_the_law_is_written(indice):
    con = li.abrir(indice)
    filas = con.execute(
        "SELECT numero, ubicacion, inicio, fin FROM articulos a JOIN leyes l ON l.n = a.ley "
        "WHERE l.id = 'TST-A' ORDER BY orden").fetchall()

    assert [f[0] for f in filas] == ["1", "2"]
    assert CUERPO_A[filas[0][2]:filas[0][3]].strip() == "###### Artículo 1. Objeto.\n\nEl arrendamiento urbano."


def test_the_searchable_text_is_folded_like_the_rest(indice):
    con = li.abrir(indice)

    assert con.execute("SELECT count(*) FROM cuerpo WHERE cuerpo MATCH '\"arrendamiento\"'").fetchone()[0] == 1
    assert con.execute("SELECT count(*) FROM cuerpo WHERE cuerpo MATCH '\"forsta\"'").fetchone()[0] == 1


def test_an_interrupted_write_leaves_nothing_behind(tmp_path):
    ruta = li.ruta_indice(tmp_path, "tst")
    escritor = li.Escritor(ruta)
    escritor.poner_ley("TST-A", campos(), CUERPO_A)
    escritor.descartar()

    assert list(tmp_path.iterdir()) == []
