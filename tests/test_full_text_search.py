"""Tests for searching the body of the law (#31, part 3 of 4).

`buscar_ley` matched a substring against `titulo` and nothing else, which made
word order decide the answer: `proteccion de datos` returned five documents and
`datos proteccion` returned none. The `texto` parameter answers a different
question — which documents *contain all of these terms* — against the inverted
index built in part 2.

**`texto` and `consulta` stay separate on purpose.** They answer different
questions, and collapsing them would make one call mean two things. Every
existing call keeps working, which is the bar #30 already met.

**Served from the corpus database (spec 002).** The body is a full-text table
in each corpus's SQLite database, so there is nothing to load lazily: the query
goes to it directly, and the terms reach it quoted, as text, never as syntax.
Lazy loading of the old postings, and the tests that pinned it, went with them.
"""

import pickle
import sqlite3

import pytest

import mcp_legalize


def documento(**campos):
    base = {
        "titulo": "Ley de prueba", "identificador": "XX-1", "pais": "tst",
        "rango": "ley", "estado": "in_force", "fecha_publicacion": "2020-01-01",
        "ultima_actualizacion": "2020-01-01", "fuente": "https://example.test",
        "_ruta": "tst/1.md", "_bytes": 10,
    }
    base.update(campos)
    return base


@pytest.fixture
def corpus(instalar_corpus):
    """Un país con el texto de cada ley buscable, como lo deja el indexador."""
    docs = {
        "ARRENDA": documento(titulo="Ley de arrendamientos", estado="in_force"),
        "TELE": documento(titulo="Ley del teletrabajo", estado="repealed"),
        "AMBAS": documento(titulo="Ley mixta", estado="in_force"),
        "NINGUNA": documento(titulo="Ley aparte", estado="in_force"),
    }
    cuerpos = {
        "ARRENDA": "Del arrendamiento urbano.",
        "TELE": "Del teletrabajo.",
        "AMBAS": "Del arrendamiento y del teletrabajo.",
        "NINGUNA": "Otra materia.",
    }
    instalar_corpus("tst", docs, cuerpos)
    return docs


def ids(resultados):
    return sorted(r.id for r in resultados)


# ───────────────────────────── searching text ────────────────────────────────

def test_a_term_finds_the_documents_that_contain_it(corpus):
    assert ids(mcp_legalize.buscar_ley.fn(pais="tst", texto="arrendamiento")) == ["AMBAS", "ARRENDA"]


def test_two_terms_intersect_rather_than_union(corpus):
    """All of the terms, not any of them. A union would return most of a corpus."""
    assert ids(mcp_legalize.buscar_ley.fn(pais="tst", texto="arrendamiento teletrabajo")) == ["AMBAS"]


def test_word_order_does_not_change_the_answer(corpus):
    """The defect that motivated #31: `datos proteccion` returned nothing."""
    uno = ids(mcp_legalize.buscar_ley.fn(pais="tst", texto="arrendamiento urbano"))
    otro = ids(mcp_legalize.buscar_ley.fn(pais="tst", texto="urbano arrendamiento"))

    assert uno == otro == ["ARRENDA"]


def test_a_term_absent_from_the_corpus_returns_nothing(corpus):
    assert mcp_legalize.buscar_ley.fn(pais="tst", texto="zzzznope") == []


def test_one_absent_term_empties_the_whole_result(corpus):
    """Intersection: a term nothing contains rules out every document."""
    assert mcp_legalize.buscar_ley.fn(pais="tst", texto="arrendamiento zzzznope") == []


def test_the_query_is_normalized_like_the_index(corpus):
    """The tokenizer folds accents and case when building; the query must agree."""
    assert ids(mcp_legalize.buscar_ley.fn(pais="tst", texto="ARRENDAMIENTO")) == ["AMBAS", "ARRENDA"]


def test_terms_below_the_minimum_length_are_ignored(corpus):
    """`de` and `el` were never indexed, so requiring them would match nothing."""
    assert ids(mcp_legalize.buscar_ley.fn(pais="tst", texto="el arrendamiento")) == ["AMBAS", "ARRENDA"]


# ─────────────────────── composing with the filters ──────────────────────────

def test_texto_composes_with_the_other_filters(corpus):
    resultados = mcp_legalize.buscar_ley.fn(pais="tst", texto="teletrabajo", estado="in_force")

    assert ids(resultados) == ["AMBAS"]


def test_texto_composes_with_consulta(corpus):
    """They answer different questions and must narrow together, not replace."""
    resultados = mcp_legalize.buscar_ley.fn(pais="tst", texto="arrendamiento", consulta="mixta")

    assert ids(resultados) == ["AMBAS"]


def test_a_search_without_texto_is_unchanged(corpus):
    """The bar #30 met: nothing that works today stops working."""
    assert len(mcp_legalize.buscar_ley.fn(pais="tst")) == 4


# ─────────────────────────── untrusted text index ────────────────────────────

def test_a_corrupt_inverted_index_is_reported_instead_of_raising(corpus):
    """The text index is untrusted input like the rest of the index — #18's lesson.

    Still never an exception. What changed (spec 001, FR-010; approved
    2026-10-16) is that the answer is no longer `[]`, which a client cannot tell
    from "no matches": it is an error naming the country and why.
    """
    ruta = mcp_legalize._CONEXIONES["tst"].execute("PRAGMA database_list").fetchone()[2]
    con = sqlite3.connect(ruta)
    # Quien manipula el índice usa un SQLite sin modo defensivo. Sin las hojas
    # del texto buscable, el esquema sigue intacto y el daño aparece al consultar.
    con.setconfig(sqlite3.SQLITE_DBCONFIG_DEFENSIVE, False)
    con.execute("DELETE FROM cuerpo_data WHERE id > 10")
    con.commit()
    con.close()

    resultado = mcp_legalize.buscar_ley.fn(pais="tst", texto="arrendamiento")

    assert isinstance(resultado, mcp_legalize.ErrorRespuesta)
    assert "tst: ilegibles" in resultado.sugerencias


# ──────────────────────── no code execution (spec 001, US3) ───────────────────

class _Centinela:
    """Unpickling this creates a file. If the file exists, code ran."""

    def __init__(self, ruta):
        self.ruta = str(ruta)

    def __reduce__(self):
        from pathlib import Path
        return (Path(self.ruta).touch, ())


def test_a_malicious_old_bin_runs_nothing_on_a_text_search(corpus, tmp_path, monkeypatch):
    """Write access to `indices/` must not be code execution (principle II).

    The server used to `pickle.load` the `.bin` on the first full-text query.
    A pickle can name any callable to run while it is being read, so a planted
    file ran arbitrary code inside the server process. The old `.bin` is now
    recognised by its name and never opened.
    """
    centinela = tmp_path / "pwned"
    indices = tmp_path / "indices"
    indices.mkdir()
    monkeypatch.setattr(mcp_legalize, "INDICES_DIR", indices)
    (indices / "inverted_tst.bin").write_bytes(pickle.dumps(_Centinela(centinela)))

    mcp_legalize.buscar_ley.fn(pais="tst", texto="arrendamiento")

    assert not centinela.exists()
