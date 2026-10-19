"""Tests that the indexer reads when a law stops being in force (spec 003).

The EU corpus carries `end_of_validity`, an extension like Spain's
`repeal_date`: the date a law stopped or will stop being in force, whatever the
reason. Measured on 2026-10-19 it is in 2,267 of 18,607 European laws (1,061
repealed, 670 expired, 536 in force), and no European law carries
`repeal_date`. The indexer ignored it, so the date never reached the index.

It now becomes `fecha_fin_vigencia`. A repealed law without `repeal_date` also
takes it as its repeal date, so the repeal filters find European repealed laws
(Q1). An expired law never does: an expiry is not a repeal (FR-003). A value
that is not a real date leaves the field empty and costs nothing else (FR-001).
"""

import os

import pytest


def escribir(repo, nombre, **meta):
    ruta = repo / "d" / nombre
    ruta.parent.mkdir(parents=True, exist_ok=True)
    cabecera = "".join(f"{k}: {v}\n" for k, v in {"title": "Reglamento", **meta}.items())
    ruta.write_text(f"---\n{cabecera}---\nArtículo 1\nTexto.\n", encoding="utf-8")
    marca = ruta.stat().st_mtime + 10
    os.utime(ruta, (marca, marca))


@pytest.fixture
def indexado(indexer_cli):
    escribir(indexer_cli.repo, "expirada.md", identifier="EXP", status="expired",
             end_of_validity="2005-05-20")
    escribir(indexer_cli.repo, "derogada.md", identifier="DER", status="repealed",
             end_of_validity="2017-07-19")
    escribir(indexer_cli.repo, "ambas.md", identifier="AMB", status="repealed",
             repeal_date="2010-01-01", end_of_validity="2011-02-02")
    escribir(indexer_cli.repo, "futura.md", identifier="FUT", status="in_force",
             end_of_validity="2031-01-08")
    escribir(indexer_cli.repo, "sin.md", identifier="SIN", status="in_force")
    escribir(indexer_cli.repo, "anno.md", identifier="ANN", status="expired", end_of_validity="2020")
    escribir(indexer_cli.repo, "mes.md", identifier="MES", status="expired", end_of_validity="2020-03")
    for i, malo in enumerate(["pronto", "2023-02-30", "20-01-2020", "[2020-01-01]", "2020-13"]):
        escribir(indexer_cli.repo, f"mala{i}.md", identifier=f"MALA{i}", status="repealed",
                 end_of_validity=malo)
    proc = indexer_cli.correr("--pais", "eu")
    assert proc.returncode == 0, proc.stderr
    return indexer_cli.leer()["documentos"]


def campos(documentos, id_ley):
    doc = documentos[id_ley]
    return doc.get("fecha_fin_vigencia"), doc.get("fecha_derogacion"), doc.get("estado")


def test_an_expired_law_has_an_end_of_validity_and_no_repeal_date(indexado):
    """FR-003: an expiry is never presented as a repeal."""
    assert campos(indexado, "EXP") == ("2005-05-20", None, "expired")


def test_a_repealed_law_without_repeal_date_takes_the_date_as_its_repeal(indexado):
    """Q1: the repeal filters find European repealed laws."""
    assert campos(indexado, "DER") == ("2017-07-19", "2017-07-19", "repealed")


def test_repeal_date_still_comes_from_repeal_date(indexado):
    """FR-005: each field keeps its own source when both exist."""
    assert campos(indexado, "AMB") == ("2011-02-02", "2010-01-01", "repealed")


def test_a_future_end_in_force_is_kept_and_the_status_untouched(indexado):
    """Q3: the date is the source's; the status is not deduced from it."""
    assert campos(indexado, "FUT") == ("2031-01-08", None, "in_force")


def test_a_law_without_end_of_validity_has_none(indexado):
    assert campos(indexado, "SIN") == (None, None, "in_force")


@pytest.mark.parametrize("id_ley,fecha", [("ANN", "2020"), ("MES", "2020-03")])
def test_a_year_or_a_month_is_a_date_at_its_own_precision(indexado, id_ley, fecha):
    assert campos(indexado, id_ley)[0] == fecha


@pytest.mark.parametrize("i", range(5))
def test_a_value_that_is_not_a_real_date_is_dropped_and_the_law_kept(indexado, i):
    """FR-001: `pronto`, 30 February, day-first, a list, month 13."""
    assert campos(indexado, f"MALA{i}") == (None, None, "repealed")


# ─────────── Q1 through the tools: the repeal filters (US3) ────────────────

@pytest.fixture
def servido(indexado, indexer_cli, monkeypatch):
    """The index the real indexer wrote, registered in the server."""
    import mcp_legalize

    for tabla in ("_CONEXIONES", "_META_POR_PAIS", "_INDEX_FILE_POR_PAIS",
                  "_RAIZ_POR_PAIS", "_TEXTO_NO_DISPONIBLE"):
        monkeypatch.setattr(mcp_legalize, tabla, {})
    monkeypatch.setattr(mcp_legalize, "REPOS_DIR", indexer_cli.repo.parent)
    mcp_legalize._registrar_indice(indexer_cli.indice, indexer_cli.repo.parent.resolve())
    return mcp_legalize


def derogadas(m, **filtros):
    resultado = m.buscar_ley.fn(pais="eu", limite=100, **filtros)
    assert m.contar_leyes.fn(pais="eu", **filtros).total == len(resultado)
    return sorted(r.id for r in resultado)


def test_a_european_repealed_law_is_found_by_the_repeal_filters(servido):
    """Q1: before, derogada_desde found no European law at all."""
    assert "DER" in derogadas(servido, derogada_desde="2017", derogada_hasta="2017")


def test_an_expired_law_is_never_found_by_the_repeal_filters(servido):
    """FR-003, through the tools: an expiry is not a repeal."""
    encontradas = derogadas(servido, derogada_desde="1900")

    assert "EXP" not in encontradas and "ANN" not in encontradas and "MES" not in encontradas
    assert encontradas == ["AMB", "DER"]


# ──────────────── the operator rebuilds once (US4, FR-012) ──────────────────

def test_an_index_of_the_previous_format_is_reported_and_rebuilt_once(
    check_updates, tmp_path, monkeypatch, capsys,
):
    """The schema change raises FORMATO. An index written before is reported,
    and the remedy check_updates proposes, run once with no flags, leaves it
    current and carrying the new date."""
    import json
    import sqlite3
    import subprocess
    import sys
    from pathlib import Path

    import legalize_indice as li

    repo = tmp_path / "repos" / "legalize-xx"
    escribir(repo, "a.md", identifier="EXP", status="expired", end_of_validity="2005-05-20")
    indices = tmp_path / "indices"
    indices.mkdir()
    indice = indices / "index_legalize-xx.db"

    # El esquema del formato 1: el de hoy sin la columna de la spec 003.
    con = sqlite3.connect(indice)
    for sentencia in li.ESQUEMA:
        con.execute(sentencia.replace("fecha_fin_vigencia TEXT NOT NULL, ", ""))
    for clave, valor in {"formato": "1", "directorio_base": str(repo),
                         "pais_predeterminado": "xx"}.items():
        con.execute("INSERT INTO meta VALUES (?, ?)", (clave, json.dumps(valor)))
    con.commit()
    con.close()

    monkeypatch.setattr(check_updates, "_INDICES_DIR", indices)
    monkeypatch.setattr(check_updates, "_PROJECT_DIR", tmp_path)
    monkeypatch.setattr(check_updates.legalize_repo, "head_commit", lambda _: "")

    def comprobar():
        try:
            check_updates.main()
        except SystemExit:
            pass
        return capsys.readouterr().out

    assert "FORMATO" in comprobar()

    proc = subprocess.run(
        [sys.executable, str(Path(check_updates.__file__).parent / "update_index.py"),
         "--repo", str(repo), "--index", str(indice)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
    )
    assert proc.returncode == 0, proc.stderr

    assert "FORMATO" not in comprobar()
    assert li.como_dict(indice)["documentos"]["EXP"]["fecha_fin_vigencia"] == "2005-05-20"


@pytest.mark.parametrize("fecha", ["٢٠٢٠-٠١-٠١", "２０２０", "2020-0１"],
                         ids=["arabic-indic", "fullwidth year", "mixed"])
def test_a_date_written_with_non_ascii_digits_is_not_a_date(indexer_cli, fecha):
    """Found by the security review of spec 003: Python's `\\d` matches any
    Unicode digit and `int()` accepts them, so `٢٠٢٠-٠١-٠١` was stored. It
    then compares as text against "2020" and sorts nowhere sensible. A date
    from the source is written in ASCII digits; anything else is dropped like
    any other value that is not a date (FR-001)."""
    escribir(indexer_cli.repo, "a.md", identifier="NOASCII", status="expired", end_of_validity=fecha)
    proc = indexer_cli.correr("--pais", "eu")
    assert proc.returncode == 0, proc.stderr

    documentos = indexer_cli.leer()["documentos"]

    assert campos(documentos, "NOASCII") == (None, None, "expired")
