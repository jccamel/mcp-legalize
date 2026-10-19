"""Tests that the index files a law under `repealed` when its title says so (spec 004).

The UK corpus gives every law `status: in_force`, and marks the ones no longer in
force at the end of the title instead. Measured on 2026-10-19: 594 of 86,671
titles end with `(repealed)`, `(revoked)` or `(repealed <date>)`, and none of
them carries `repeal_date`, `repealed_by` or `end_of_validity`. No title in es,
eu, fr or se has such a mark.

`estado` stays exactly as the corpus gives it (ADR 0001). What changes is the
internal column the status filter reads: a law whose title contradicts its
status is filed under `repealed`, so the filter finds it (Q2).
"""

import os
import sqlite3

import pytest

CASOS = {
    # id: (title, status or None, what the status filter files it under)
    "REP": ("Licensing Act 1964 (repealed)", "in_force", "repealed"),
    "REV": ("The Scallops Order 2010 (Revoked)", "in_force", "repealed"),
    "FEC": ("Deer Act 1963 (Repealed 25.10.1991)", "in_force", "repealed"),
    "PAR": ("Shipbuilding Act 1985(repealed 5.11.1993 for Act except s. 1 and 1.4.1996 otherwise)",
            "in_force", "repealed"),
    "VAC": ("Fireworks Act 1964 (repealed)", None, "repealed"),
    "DER": ("Finance Act 1964 (repealed)", "repealed", "repealed"),
    "SIN": ("Environmental Protection Act 1990", "in_force", "in_force"),
    "MED": ("The Repeals (repealed) Order 1990", "in_force", "in_force"),
    # Signo Kelvin (U+212A) en lugar de la k: con IGNORECASE en Unicode casaría.
    "KEL": ("Betting Act 1963 (revoKed)", "in_force", "in_force"),
}


def escribir(repo, id_ley, titulo, estado):
    ruta = repo / "d" / f"{id_ley}.md"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    meta = {"identifier": id_ley, "title": f'"{titulo}"'}
    if estado is not None:
        meta["status"] = estado
    cabecera = "".join(f"{k}: {v}\n" for k, v in meta.items())
    ruta.write_text(f"---\n{cabecera}---\n##### 1\n\nText.\n", encoding="utf-8")
    marca = ruta.stat().st_mtime + 10
    os.utime(ruta, (marca, marca))


@pytest.fixture
def indexado(indexer_cli):
    for id_ley, (titulo, estado, _) in CASOS.items():
        escribir(indexer_cli.repo, id_ley, titulo, estado)
    proc = indexer_cli.correr("--pais", "uk")
    assert proc.returncode == 0, proc.stderr
    return indexer_cli


def estado_filtrado(indexer_cli) -> dict[str, str]:
    con = sqlite3.connect(indexer_cli.indice)
    try:
        return dict(con.execute("SELECT id, estado_norm FROM leyes"))
    finally:
        con.close()


def test_the_status_is_kept_exactly_as_the_corpus_gives_it(indexado):
    """ADR 0001: the value is the source's, never normalised to serve it."""
    documentos = indexado.leer()["documentos"]

    for id_ley, (titulo, estado, _) in CASOS.items():
        assert documentos[id_ley]["titulo"] == titulo
        assert documentos[id_ley]["estado"] == (estado or ""), id_ley


@pytest.mark.parametrize("id_ley", sorted(CASOS))
def test_a_law_is_filed_under_repealed_when_its_title_contradicts_its_status(indexado, id_ley):
    """Its own status otherwise: a mark mid-title or with a look-alike letter is not one."""
    assert estado_filtrado(indexado)[id_ley] == CASOS[id_ley][2]
