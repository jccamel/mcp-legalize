"""Tests for issue #21: the index must not store unbounded frontmatter values.

The indexer copied frontmatter through `_get` at whatever length the file
supplied. The server caps values in `_sanitize_metadata`, but on the way *out* —
so a 100,000-character title was stored whole, loaded into memory at import by
every server reading that index, and only trimmed when it was served. A thousand
such documents add ~100 MB of permanent resident memory while the responses look
perfectly normal.

**The cap is measured, not guessed.** An earlier draft of the issue proposed
1,000 characters; the Spanish corpus rejected it, because the longest genuine
title is 1,658 (`BOE-A-2021-20004`, against a median of 147). Truncating a real
consolidated law would be a worse outcome than storing a fake one, so the limit
sits at 8,000 — nearly five times the longest real value, which cuts a payload
without threatening a law.

One limit rather than one per field, on purpose. A per-field table would be a
second set of numbers to keep in step with the server's own `max_len` values,
and it would go stale the moment a jurisdiction arrives with longer titles than
Spain's. Every non-title field measures under 100 characters today, so a shared
ceiling costs them nothing.

Truncation is reported. Silently shortening a title is the same quiet data loss
that #20 was filed for; the operator should be able to tell a hostile corpus
from an unusually verbose one.
"""

import json

import pytest

import mcp_legalize


@pytest.fixture
def indexar(indexer_cli):
    def correr(*extra_args):
        proc = indexer_cli.correr("--pais", "tst", *extra_args)
        datos = (
            json.loads(indexer_cli.indice.read_text(encoding="utf-8"))
            if indexer_cli.indice.exists() else {}
        )
        return datos, proc.stdout + proc.stderr
    correr.repo = indexer_cli.repo
    return correr


def escribir(directorio, nombre, titulo):
    ruta = directorio / nombre
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(f"---\ntitle: {titulo}\n---\ncuerpo limpio\n", encoding="utf-8")
    return ruta


def test_an_oversized_title_is_truncated_in_the_index(indexar, update_index):
    """The 100,000-character case from the issue."""
    escribir(indexar.repo / "test", "a.md", "A" * 100_000)

    datos, _ = indexar()

    titulo = next(iter(datos["documentos"].values()))["titulo"]
    assert len(titulo) == update_index._MAX_META_CHARS


def test_the_document_is_still_indexed(indexar):
    """Truncating is not rejecting: the law stays, only the oversized value shrinks."""
    escribir(indexar.repo / "test", "a.md", "A" * 100_000)

    datos, _ = indexar()

    assert len(datos["documentos"]) == 1


def test_the_truncation_is_reported(indexar):
    """Quiet data loss is the thing this project keeps refusing to ship."""
    escribir(indexar.repo / "test", "a.md", "A" * 100_000)

    _, salida = indexar()

    assert "test/a.md" in salida
    assert "titulo" in salida


def test_the_truncation_is_counted_in_the_summary(indexar):
    escribir(indexar.repo / "test", "a.md", "A" * 100_000)

    _, salida = indexar()

    assert "Metadatos truncados" in salida


def test_the_longest_real_title_survives_untouched(indexar, update_index):
    """1,658 chars — `BOE-A-2021-20004`, the longest title in the Spanish corpus.

    The cap exists to stop a payload, never to edit a law. If this test ever
    fails, the limit was set below something the corpus really contains.
    """
    largo_real = 1_658
    assert largo_real < update_index._MAX_META_CHARS
    escribir(indexar.repo / "test", "a.md", "L" * largo_real)

    datos, salida = indexar()

    assert len(next(iter(datos["documentos"].values()))["titulo"]) == largo_real
    assert "Metadatos truncados" not in salida


def test_a_normal_corpus_reports_nothing(indexar):
    """The guard must cost a well-formed corpus nothing."""
    escribir(indexar.repo / "test", "a.md", "Ley 1/2020 de prueba")

    datos, salida = indexar()

    assert next(iter(datos["documentos"].values()))["titulo"] == "Ley 1/2020 de prueba"
    assert "Metadatos truncados" not in salida


def test_the_cap_leaves_room_above_every_field_the_server_serves(update_index):
    """The index must never hold less than what the server is willing to return.

    If a server `max_len` ever exceeded the index cap, the index would be the
    silent bottleneck and the server's limit would become a lie.
    """
    caps_servidor = [500, 200, 100, 50]  # los valores usados en `_doc_resumen`
    assert update_index._MAX_META_CHARS > max(caps_servidor)


def test_truncation_is_stamped_in_the_index(indexar):
    """A corpus that ships 100 KB titles is a provenance fact, like #20 and #22."""
    escribir(indexar.repo / "test", "a.md", "A" * 100_000)

    datos, _ = indexar()

    sellado = datos["_meta"]["seguridad"]["truncados"]
    assert list(sellado) == ["test/a.md"]
    assert sellado["test/a.md"] == ["titulo"]
