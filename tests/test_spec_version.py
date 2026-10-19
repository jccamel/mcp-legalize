"""Tests that the indexer refuses a corpus written for a newer Legalize spec.

The Legalize Format Spec, v0.4: "A consumer MUST refuse a repo whose
`spec_version` is newer than the version it implements. Reading a newer
manifest with older rules yields paths that are wrong rather than absent." The
indexer is this project's consumer of a corpus repository, and it never read
`.legalize.yml` at all: a corpus written for a later spec would have been
indexed under rules that no longer describe it, in silence.

A repository without a manifest predates v0.4, and the spec says to read it as
if it declared v0.4's default layout, so it is indexed (SE and FR have none). A
manifest whose version cannot be read is refused like a newer one: nothing
proves it is not.
"""

import pytest


@pytest.fixture
def corpus(indexer_cli):
    ruta = indexer_cli.repo / "d" / "ley.md"
    ruta.parent.mkdir(parents=True)
    ruta.write_text("---\ntitle: Ley\nidentifier: TST-1\n---\nArtículo 1\nUno.\n", encoding="utf-8")

    def manifiesto(texto):
        (indexer_cli.repo / ".legalize.yml").write_text(texto, encoding="utf-8")

    def indexar():
        return indexer_cli.correr("--pais", "tst", "--force-all")

    indexer_cli.manifiesto, indexer_cli.indexar = manifiesto, indexar
    return indexer_cli


@pytest.mark.parametrize("contenido", [
    None,
    'spec_version: "0.4"\ncountry: "tst"\n',
    "# Legalize Format Spec v0.4\nspec_version: '0.4'\n",
    "spec_version: 0.4  # comentario\n",
    'spec_version: "0.3"\n',
], ids=["no manifest", "0.4 quoted", "0.4 single quotes", "0.4 bare with comment", "older"])
def test_a_corpus_of_this_spec_or_older_is_indexed(corpus, contenido):
    if contenido is not None:
        corpus.manifiesto(contenido)

    proc = corpus.indexar()

    assert proc.returncode == 0, proc.stderr
    assert "TST-1" in corpus.leer()["documentos"]


@pytest.mark.parametrize("contenido", [
    'spec_version: "0.5"\n',
    'spec_version: "1.0"\n',
    'spec_version: "0.4.1"\n',
    'country: "tst"\n',
    'spec_version: "cuatro"\n',
    'spec_version: ["0.4"]\n',
], ids=["0.5", "1.0", "0.4.1", "missing", "not a version", "not a scalar"])
def test_a_corpus_of_a_newer_or_unreadable_spec_is_refused(corpus, contenido):
    corpus.manifiesto(contenido)

    proc = corpus.indexar()

    assert proc.returncode != 0
    assert "spec_version" in proc.stderr
    assert not corpus.indice.exists()


def test_refusing_leaves_the_previous_index_untouched(corpus):
    corpus.indexar()
    antes = corpus.indice.read_bytes()
    corpus.manifiesto('spec_version: "0.5"\n')

    proc = corpus.indexar()

    assert proc.returncode != 0
    assert corpus.indice.read_bytes() == antes
