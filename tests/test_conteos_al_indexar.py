"""Tests that the listings read counts prepared at index time (spec 002, T040).

`estadisticas` and `listar_rangos` counted every law on each call. With the index
in memory that took 3–9 ms on the Spanish corpus; over the database, as four
table scans, it took up to 92 ms, and SC-004 allows no request to be slower than
before. The writer now counts once, in the same transaction it commits, and
the server reads the result. A meta that does not hold usable counts —an index
written by hand, a tampered file— is counted on the spot with the same function.
"""

import json
import sqlite3

import pytest

import legalize_indice
import mcp_legalize


def documento(rango, estado, fecha, n_bytes=10):
    return {"titulo": "t", "rango": rango, "estado": estado, "fecha_publicacion": fecha,
            "_ruta": "x.md", "_bytes": n_bytes}


@pytest.fixture
def corpus(instalar_corpus):
    instalar_corpus("tst", {
        "A": documento("ley", "in_force", "2001-01-01"),
        "B": documento("decreto", "repealed", "2002-01-01"),
        "C": documento("ley", "", "2001-06-01"),
        "D": documento("", "in_force", "19"),
    })


def respuestas():
    return (mcp_legalize.estadisticas.fn(pais="tst").model_dump(),
            [r.model_dump() for r in mcp_legalize.listar_rangos.fn(pais="tst")])


def test_the_listings_answer_from_the_counts_without_scanning(corpus, monkeypatch):
    def prohibido(*a, **k):
        raise AssertionError("se ha contado al consultar")
    monkeypatch.setattr(legalize_indice, "contar", prohibido)

    estadisticas, rangos = respuestas()

    assert estadisticas["total_documentos"] == 4
    assert estadisticas["estados"] == {"in_force": 2, "repealed": 1, "desconocido": 1}
    assert [r["rango"] for r in rangos] == ["ley", "decreto", "desconocido"]
    assert estadisticas["top_annos_publicacion"] == [{"anno": "2001", "total": 2}, {"anno": "2002", "total": 1}]


@pytest.mark.parametrize("conteos", ["roto", {"estados": "x"}, {"estados": [["a", "uno"]]}, None],
                         ids=["not an object", "list not a list", "count not a number", "missing"])
def test_counts_that_cannot_be_used_are_recomputed(corpus, conteos):
    """A tampered meta costs the shortcut, never the answer."""
    esperado = respuestas()
    ruta = mcp_legalize._CONEXIONES["tst"].execute("PRAGMA database_list").fetchone()[2]
    con = sqlite3.connect(ruta)
    if conteos is None:
        con.execute("DELETE FROM meta WHERE clave = 'conteos'")
    else:
        con.execute("UPDATE meta SET valor = ? WHERE clave = 'conteos'", (json.dumps(conteos),))
    con.commit()
    con.close()
    mcp_legalize._registrar_indice(__import__("pathlib").Path(ruta), mcp_legalize.REPOS_DIR.resolve())

    assert respuestas() == esperado
