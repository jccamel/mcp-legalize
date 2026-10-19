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
