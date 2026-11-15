"""Tests that moving a file inside the corpus keeps the id of its law (#67).

A file that moved to another directory is a new path to the indexer, while the
entry for its old path still held the id. The duplicate check ran before
orphans were removed, so the file was taken for a duplicate of itself and
indexed as `LEY-1__b_ley1`. With `--remove-orphans` the old entry then went
too: a corpus that reorganised its directories changed every id, and a client
could no longer open a law by the id it had.

An entry whose file is no longer on disk does not claim its id against a file
that declares it: the file takes the id over, in the entry's place. A file
that is still on disk keeps the id, as before (`test_docid_collision`).
"""

import pytest


def escribir(repo, nombre, identificador, titulo="Ley de prueba"):
    ruta = repo / nombre
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(f"---\ntitle: {titulo}\nidentificador: {identificador}\n---\ncuerpo\n",
                    encoding="utf-8")
    return ruta


def mover(origen, destino):
    destino.parent.mkdir(parents=True, exist_ok=True)
    origen.rename(destino)


@pytest.mark.parametrize("extra", [(), ("--remove-orphans",)], ids=["incremental", "remove-orphans"])
def test_a_moved_file_keeps_the_id_of_its_law(indexer_cli, extra):
    repo = indexer_cli.repo
    escribir(repo, "a/ley1.md", "LEY-1")
    escribir(repo, "a/ley2.md", "LEY-2")
    assert indexer_cli.correr("--pais", "tst").returncode == 0

    mover(repo / "a/ley1.md", repo / "b/ley1.md")
    proc = indexer_cli.correr("--pais", "tst", *extra)

    assert proc.returncode == 0, proc.stderr
    documentos = indexer_cli.leer()["documentos"]
    assert {k: v["_ruta"] for k, v in documentos.items()} == {"LEY-1": "b/ley1.md", "LEY-2": "a/ley2.md"}
    assert "ya reclamaba" not in proc.stdout + proc.stderr
    assert "Movidos           : 1" in proc.stdout


def test_a_moved_file_is_served_from_its_new_place(indexer_cli):
    """The entry is the file's, not the old one's: its text and title are the new ones."""
    repo = indexer_cli.repo
    escribir(repo, "a/ley1.md", "LEY-1", titulo="Antes")
    assert indexer_cli.correr("--pais", "tst").returncode == 0

    mover(repo / "a/ley1.md", repo / "b/ley1.md")
    escribir(repo, "b/ley1.md", "LEY-1", titulo="Después")
    indexer_cli.correr("--pais", "tst", "--remove-orphans")

    ley = indexer_cli.leer()["documentos"]["LEY-1"]
    assert (ley["_ruta"], ley["titulo"]) == ("b/ley1.md", "Después")


def test_a_copy_left_in_place_is_still_a_duplicate(indexer_cli):
    """Only an entry whose file is gone gives up its id."""
    repo = indexer_cli.repo
    escribir(repo, "b/ley1.md", "LEY-1")
    assert indexer_cli.correr("--pais", "tst").returncode == 0

    escribir(repo, "a/ley1.md", "LEY-1")
    proc = indexer_cli.correr("--pais", "tst")

    documentos = indexer_cli.leer()["documentos"]
    assert documentos["LEY-1"]["_ruta"] == "b/ley1.md"
    assert documentos["LEY-1__a_ley1"]["_ruta"] == "a/ley1.md"
    assert "ya reclamaba" in proc.stdout + proc.stderr
