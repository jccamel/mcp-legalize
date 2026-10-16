"""Tests for searching the body of the law (#31, part 3 of 4).

`buscar_ley` matched a substring against `titulo` and nothing else, which made
word order decide the answer: `proteccion de datos` returned five documents and
`datos proteccion` returned none. The `texto` parameter answers a different
question — which documents *contain all of these terms* — against the inverted
index built in part 2.

**`texto` and `consulta` stay separate on purpose.** They answer different
questions, and collapsing them would make one call mean two things. Every
existing call keeps working, which is the bar #30 already met.

**Loaded lazily, per corpus.** The postings file is 75.8 MB for the Spanish corpus
and 9.3 MB for the Swedish one (spec 001, research.md R1). Loading every one at import would charge a cost at
startup that a deployment whose clients never search by text would never use —
the same reasoning already accepted for the normalization cache in #15, with
larger stakes.

**Ordering, decided in #31 question 4 and measured there**: the text
intersection runs first because it is the cheapest and most selective step (0.08
ms, and it can cut the candidate set by 95%), then the cheap string comparisons,
then the normalizing ones. `texto` therefore replaces `_iter_docs` as the source
of candidates rather than joining the filter chain.
"""

import pickle

import pytest

import legalize_postings
import legalize_tokenizer
import mcp_legalize

GENERACION = "a" * 32


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
def corpus(tmp_path, monkeypatch):
    """Un país con su índice invertido en disco, como lo deja el indexador."""
    docs = {
        "ARRENDA": documento(titulo="Ley de arrendamientos", estado="in_force"),
        "TELE": documento(titulo="Ley del teletrabajo", estado="repealed"),
        "AMBAS": documento(titulo="Ley mixta", estado="in_force"),
        "NINGUNA": documento(titulo="Ley aparte", estado="in_force"),
    }
    postings = {
        "arrendamiento": ["ARRENDA", "AMBAS"],
        "urbano": ["ARRENDA"],
        "teletrabajo": ["TELE", "AMBAS"],
    }
    indices = tmp_path / "indices"
    indices.mkdir(parents=True, exist_ok=True)
    # Escritos como los deja el indexador: formato sin código, sello real del
    # tokenizador y la generación que los ata al índice JSON (spec 001).
    legalize_postings.escribir(
        legalize_postings.ruta_postings(indices, "tst"), postings,
        tokenizador=legalize_tokenizer.huella(), generacion=GENERACION,
    )

    monkeypatch.setattr(mcp_legalize, "INDICES_DIR", indices)
    monkeypatch.setitem(mcp_legalize._DOCS_POR_PAIS, "tst", docs)
    monkeypatch.setitem(mcp_legalize._META_POR_PAIS, "tst", {"generacion": GENERACION})
    monkeypatch.setitem(mcp_legalize._INDEX_FILE_POR_PAIS, "tst", "index_tst")
    monkeypatch.setattr(mcp_legalize, "_INVERTIDO_POR_PAIS", {})
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


# ───────────────────────────── lazy loading ──────────────────────────────────

def test_the_inverted_index_is_not_loaded_until_a_text_search(corpus):
    """~85 MB per corpus must not be charged to a deployment that never uses it."""
    mcp_legalize.buscar_ley.fn(pais="tst", estado="in_force")

    assert mcp_legalize._INVERTIDO_POR_PAIS == {}


def test_the_inverted_index_is_loaded_once(corpus, monkeypatch):
    """A second text search must reuse the first one's load."""
    cargas = []
    original = mcp_legalize._cargar_invertido

    def espia(pais):
        cargas.append(pais)
        return original(pais)

    monkeypatch.setattr(mcp_legalize, "_cargar_invertido", espia)
    mcp_legalize.buscar_ley.fn(pais="tst", texto="arrendamiento")
    mcp_legalize.buscar_ley.fn(pais="tst", texto="teletrabajo")

    assert cargas == ["tst"]


def test_a_country_without_an_inverted_index_says_it_could_not_search(corpus, monkeypatch):
    """A corpus indexed before part 2, or whose postings failed to write.

    This test used to expect `[]`, on the reasoning that an empty list "says
    truthfully that no document is known to contain those terms". It does not
    say that to a client: `[]` is also exactly what a search with no matches
    returns, so the client concluded "no law contains these words" when nobody
    had looked (spec 001, FR-010; decision Q3, approved 2026-10-16).

    The other half of the old reasoning still holds and is kept: one country
    without postings must not break the tool for the others. That is why this
    is an error only when the search was limited to the country that cannot
    answer — searching every country still returns the others' results.
    """
    monkeypatch.setattr(mcp_legalize, "INDICES_DIR", corpus and mcp_legalize.INDICES_DIR.parent / "vacio")

    resultado = mcp_legalize.buscar_ley.fn(pais="tst", texto="arrendamiento")

    assert isinstance(resultado, mcp_legalize.ErrorRespuesta)
    assert "tst: sin_postings" in resultado.sugerencias


def test_a_corrupt_inverted_index_is_reported_instead_of_raising(corpus, tmp_path, monkeypatch):
    """The postings are untrusted input like the JSON index — #18's lesson.

    Still never an exception. What changed (spec 001, FR-010; approved
    2026-10-16) is that the answer is no longer `[]`, which a client cannot tell
    from "no matches": it is an error naming the country and why.
    """
    (mcp_legalize.INDICES_DIR / "inverted_tst.postings").write_bytes(b"no soy unos postings")
    monkeypatch.setattr(mcp_legalize, "_INVERTIDO_POR_PAIS", {})

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
    (mcp_legalize.INDICES_DIR / "inverted_tst.bin").write_bytes(
        pickle.dumps(_Centinela(centinela))
    )
    monkeypatch.setattr(mcp_legalize, "_INVERTIDO_POR_PAIS", {})

    mcp_legalize.buscar_ley.fn(pais="tst", texto="arrendamiento")

    assert not centinela.exists()
