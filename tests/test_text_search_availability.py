"""Tests that a client can tell "no match" from "could not search" (spec 001, US4).

With no usable postings for a country, `buscar_ley(texto=...)` returned `[]` and
`contar_leyes` returned `total=0` — exactly what a query with no matches
returns. The two answers mean opposite things: "no law contains these words"
against "nobody looked". A client reasoning over `[]` concludes the first.

`contar_leyes` exists precisely so a client can tell a complete answer from a
partial one (#37), so it is the tool that carries the signal (decision Q3):

- `Conteo.sin_consultar` lists every requested country whose full-text search
  could not run, with the reason, and is empty when all of them ran.
- `buscar_ley` keeps returning a bare list while at least one requested country
  could be searched — 16 call sites depend on that shape — and returns
  `ErrorRespuesta` only when none could.

The reasons are the ones `legalize_postings.estado` decides, plus one of the
query's own: `consulta_sin_terminos`, when no term reaches three characters.
"""

import pytest

import legalize_postings
import legalize_tokenizer
import mcp_legalize

GENERACION = "b" * 32

MOTIVOS_DEL_CONTRATO = {
    "sin_postings", "ilegibles", "formato_anterior",
    "tokenizador_distinto", "generacion_distinta", "consulta_sin_terminos",
}


def documento(pais, n):
    return {"titulo": f"Ley {n}", "pais": pais, "rango": "ley", "estado": "in_force",
            "fecha_publicacion": "2020-01-01", "_ruta": f"{n}.md", "_bytes": 1}


@pytest.fixture
def dos_paises(tmp_path, monkeypatch):
    """`ok` has usable postings; `sin` has none at all."""
    indices = tmp_path / "indices"
    indices.mkdir()
    legalize_postings.escribir(
        legalize_postings.ruta_postings(indices, "ok"),
        {"arrendamiento": {"OK-1", "OK-2"}, "urbano": {"OK-1"}},
        tokenizador=legalize_tokenizer.huella(), generacion=GENERACION,
    )
    monkeypatch.setattr(mcp_legalize, "INDICES_DIR", indices)
    monkeypatch.setattr(mcp_legalize, "_DOCS_POR_PAIS", {
        "ok": {"OK-1": documento("ok", 1), "OK-2": documento("ok", 2)},
        "sin": {"SIN-1": documento("sin", 1)},
    })
    monkeypatch.setattr(mcp_legalize, "_META_POR_PAIS",
                        {"ok": {"generacion": GENERACION}, "sin": {}})
    monkeypatch.setattr(mcp_legalize, "_INDEX_FILE_POR_PAIS",
                        {"ok": "index_ok", "sin": "index_sin"})
    monkeypatch.setattr(mcp_legalize, "_INVERTIDO_POR_PAIS", {})
    return indices


def no_consultados(conteo):
    return {(p.pais, p.motivo) for p in conteo.sin_consultar}


# ─────────────────────────────── contar_leyes ────────────────────────────────

def test_the_count_names_the_country_it_could_not_search(dos_paises):
    conteo = mcp_legalize.contar_leyes.fn(texto="arrendamiento")

    assert conteo.total == 2
    assert no_consultados(conteo) == {("sin", "sin_postings")}


def test_a_country_limited_count_says_it_could_not_search_there(dos_paises):
    conteo = mcp_legalize.contar_leyes.fn(pais="sin", texto="arrendamiento")

    assert conteo.total == 0
    assert no_consultados(conteo) == {("sin", "sin_postings")}


def test_nothing_is_listed_when_every_requested_country_was_searched(dos_paises):
    conteo = mcp_legalize.contar_leyes.fn(pais="ok", texto="teletrabajo")

    assert conteo.total == 0
    assert conteo.sin_consultar == []


def test_without_texto_no_postings_are_consulted_so_none_are_missing(dos_paises):
    conteo = mcp_legalize.contar_leyes.fn()

    assert conteo.total == 3
    assert conteo.sin_consultar == []


def test_a_query_without_searchable_terms_is_not_a_query_without_matches(dos_paises):
    """FR-011: "de la" has no term of three characters; nothing was searched."""
    conteo = mcp_legalize.contar_leyes.fn(texto="de la")

    assert no_consultados(conteo) == {("ok", "consulta_sin_terminos"),
                                      ("sin", "consulta_sin_terminos")}


def test_postings_that_turn_out_corrupt_when_decoded_are_reported_unreadable(dos_paises):
    """A bad list is only found at query time; the count must still say so."""
    ruta = legalize_postings.ruta_postings(dos_paises, "ok")
    texto = ruta.read_text(encoding="utf-8").replace("arrendamiento\t0,1", "arrendamiento\t0,9")
    ruta.write_text(texto, encoding="utf-8")

    conteo = mcp_legalize.contar_leyes.fn(pais="ok", texto="arrendamiento")

    assert no_consultados(conteo) == {("ok", "ilegibles")}


def test_every_reason_reported_is_one_the_contract_names(dos_paises):
    motivos = {p.motivo for consulta in ("arrendamiento", "de la")
               for p in mcp_legalize.contar_leyes.fn(texto=consulta).sin_consultar}

    assert motivos <= MOTIVOS_DEL_CONTRATO


# ──────────────────────────────── buscar_ley ─────────────────────────────────

def test_searching_only_an_unsearchable_country_is_an_error_not_an_empty_list(dos_paises):
    resultado = mcp_legalize.buscar_ley.fn(pais="sin", texto="arrendamiento")

    assert isinstance(resultado, mcp_legalize.ErrorRespuesta)
    assert "sin: sin_postings" in resultado.sugerencias


def test_searching_every_country_still_returns_the_list_of_those_that_could(dos_paises):
    """Q3: one country without postings must not hide the others' results."""
    resultado = mcp_legalize.buscar_ley.fn(texto="arrendamiento")

    assert isinstance(resultado, list)
    assert sorted(r.id for r in resultado) == ["OK-1", "OK-2"]


def test_a_search_without_searchable_terms_is_an_error(dos_paises):
    resultado = mcp_legalize.buscar_ley.fn(texto="de la")

    assert isinstance(resultado, mcp_legalize.ErrorRespuesta)
    assert "términos" in resultado.error


def test_a_searchable_country_with_no_match_is_still_an_empty_list(dos_paises):
    """The other side of the distinction: a real "no match" stays `[]`."""
    assert mcp_legalize.buscar_ley.fn(pais="ok", texto="teletrabajo") == []


# ───────────────────────── one filter, one answer (FR-012) ───────────────────

@pytest.mark.parametrize("pais", ["ok", "sin"])
@pytest.mark.parametrize("consulta", ["arrendamiento", "urbano arrendamiento", "teletrabajo"])
def test_the_count_and_the_search_agree_on_what_could_not_be_searched(dos_paises, pais, consulta):
    """Both tools come out of `_filtrar_docs`; they cannot describe different queries."""
    conteo = mcp_legalize.contar_leyes.fn(pais=pais, texto=consulta)
    busqueda = mcp_legalize.buscar_ley.fn(pais=pais, texto=consulta, limite=100)

    if isinstance(busqueda, mcp_legalize.ErrorRespuesta):
        deducidos = {s.split(": ")[0] for s in busqueda.sugerencias}
        assert {p.pais for p in conteo.sin_consultar} == deducidos
    else:
        assert conteo.sin_consultar == []
        assert conteo.total == len(busqueda)
