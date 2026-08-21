"""Tests for issue #20: a duplicated `identificador` must not remove a document.

`documentos[doc_id] = entry` had no existence check, so two files whose
frontmatter carried the same `identificador` collapsed into one entry. The
second file processed overwrote the first, a valid document left the corpus, and
the summary printed "6 scanned, 5 indexed" without comment.

`doc_id` comes from the frontmatter, which is untrusted corpus content. This was
the only path found where corpus content decides an index *key* rather than a
value, so a compromised corpus could hide a real law by duplicating its
identifier.

Two decisions are pinned here rather than left to processing order:

- **The first file wins.** Dropping both would turn one duplicated identifier
  into two missing laws, and renaming would break the id a client uses to come
  back to a document. Neither cost is worth paying for what is most often a
  defect in the upstream corpus.
- **`rglob` is now sorted.** Without it "first" meant "whatever the filesystem
  returned first", so the surviving document could change between runs on the
  same corpus. A rule that picks a winner is only worth having if it picks the
  same one twice.

The collision is reported and counted like quarantine is. Silence was the actual
defect — losing the document was the consequence.
"""

import json

import pytest


def escribir(directorio, nombre, identificador, titulo):
    ruta = directorio / nombre
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(
        f"---\ntitle: {titulo}\nidentificador: {identificador}\n---\ncuerpo de {titulo}\n",
        encoding="utf-8",
    )
    return ruta


@pytest.fixture
def indexar(indexer_cli):
    """Ejecuta el indexador y devuelve (índice cargado, salida combinada)."""
    def correr(*extra_args):
        proc = indexer_cli.correr("--pais", "tst", *extra_args)
        datos = (
            json.loads(indexer_cli.indice.read_text(encoding="utf-8"))
            if indexer_cli.indice.exists() else {}
        )
        return datos, proc.stdout + proc.stderr
    correr.repo = indexer_cli.repo
    return correr


def test_a_duplicated_identificador_does_not_drop_the_other_document(indexar):
    """Both files must survive as documents, whatever id the second one ends up with."""
    repo = indexar.repo / "test"
    escribir(repo, "a.md", "DUP", "Primero")
    escribir(repo, "b.md", "DUP", "Segundo")

    datos, _ = indexar()

    rutas = {v["_ruta"] for v in datos["documentos"].values()}
    assert rutas == {"test/a.md", "test/b.md"}


def test_the_first_file_in_sorted_order_keeps_the_contested_id(indexar):
    """`a.md` sorts before `b.md`, so `a.md` keeps `DUP`."""
    repo = indexar.repo / "test"
    escribir(repo, "a.md", "DUP", "Primero")
    escribir(repo, "b.md", "DUP", "Segundo")

    datos, _ = indexar()

    assert datos["documentos"]["DUP"]["_ruta"] == "test/a.md"


def test_the_collision_is_reported(indexar):
    """Silence was the defect. The operator must be told which files clashed."""
    repo = indexar.repo / "test"
    escribir(repo, "a.md", "DUP", "Primero")
    escribir(repo, "b.md", "DUP", "Segundo")

    _, salida = indexar()

    assert "test/b.md" in salida
    assert "DUP" in salida


def test_the_collision_is_counted_in_the_summary(indexar):
    """Counted like quarantine, so a gap between scanned and indexed is explained."""
    repo = indexar.repo / "test"
    escribir(repo, "a.md", "DUP", "Primero")
    escribir(repo, "b.md", "DUP", "Segundo")

    _, salida = indexar()

    assert "Identificadores duplicados" in salida


def test_the_collision_is_stamped_in_the_index(indexar):
    """A duplicated identifier is a provenance problem, so it belongs in `_meta`.

    Stamped as file → contested id, the same shape `cuarentena` and `avisos`
    use, so the entry says which file lost and which id it lost, not just how
    many collisions happened.
    """
    repo = indexar.repo / "test"
    escribir(repo, "a.md", "DUP", "Primero")
    escribir(repo, "b.md", "DUP", "Segundo")

    datos, _ = indexar()

    assert datos["_meta"]["seguridad"]["duplicados"] == {"test/b.md": ["DUP"]}


def test_three_files_sharing_an_id_all_survive(indexar):
    """The loser of a collision must not collide again with its fallback id."""
    repo = indexar.repo / "test"
    for nombre in ("a.md", "b.md", "c.md"):
        escribir(repo, nombre, "DUP", f"Ley {nombre}")

    datos, _ = indexar()

    assert len(datos["documentos"]) == 3
    assert {v["_ruta"] for v in datos["documentos"].values()} == {
        "test/a.md", "test/b.md", "test/c.md",
    }


def test_distinct_identificadores_are_untouched(indexar):
    """The guard must cost a well-formed corpus nothing."""
    repo = indexar.repo / "test"
    escribir(repo, "a.md", "LEY-1", "Primera")
    escribir(repo, "b.md", "LEY-2", "Segunda")

    datos, salida = indexar()

    assert sorted(datos["documentos"]) == ["LEY-1", "LEY-2"]
    assert "Identificadores duplicados" not in salida


def test_reindexing_the_same_file_is_not_a_collision(indexar):
    """A file keeping its own id across runs must not be reported as a clash."""
    repo = indexar.repo / "test"
    escribir(repo, "a.md", "LEY-1", "Primera")
    indexar()

    escribir(repo, "a.md", "LEY-1", "Primera revisada")
    datos, salida = indexar("--force-all")

    assert datos["documentos"]["LEY-1"]["titulo"] == "Primera revisada"
    assert "Identificadores duplicados" not in salida
