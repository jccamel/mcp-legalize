"""Tests that the corpus root comes from the operator, not the index (spec 001, US2).

`_resolve_ruta` validated every document path against a root — and read that
root from `_meta.directorio_base` of the very index carrying the path. The
containment check was real; the boundary it checked against was the attacker's
to choose. Reproduced in the review of 2026-10-16: an index declaring
`directorio_base: "/"` and `_ruta: "etc/hosts"` had `obtener_ley` serve the
host's `/etc/hosts`, while the README promised a malicious index could not point
at `/etc/passwd`.

Constitution principle II: no defense may rest on data the attacker controls.
The root now comes from `LEGALIZE_REPOS_DIR` (default `<project>/repos`), which
the operator sets and the index cannot. An index can still say where its corpus
is, but only somewhere inside that directory; anywhere else, the index is not
served at all, and the other indices are (FR-005).

These tests load real index files through `_load_indices` and assert through the
tools, because the defect was in how the two fit together, not in either alone.
"""

import json
import os
import sys

import pytest

import mcp_legalize

SECRETO = "SECRETO-FUERA-DEL-CORPUS-7731"


@pytest.fixture
def entorno(tmp_path, monkeypatch):
    """An operator-authorised repos dir, a secret outside it, and a healthy corpus."""
    repos = tmp_path / "repos"
    sano = repos / "legalize-ok"
    sano.mkdir(parents=True)
    (sano / "a.md").write_text("---\ntitle: Ley sana\n---\nArtículo 1\nContenido sano\n",
                               encoding="utf-8")

    fuera = tmp_path / "fuera"
    fuera.mkdir()
    (fuera / "secreto.md").write_text(f"Artículo 1\n{SECRETO}\n", encoding="utf-8")

    indices = tmp_path / "indices"
    indices.mkdir()

    monkeypatch.setattr(mcp_legalize, "INDICES_DIR", indices)
    monkeypatch.setattr(mcp_legalize, "REPOS_DIR", repos, raising=False)
    monkeypatch.setattr(mcp_legalize, "_DOCS_POR_PAIS", {})
    monkeypatch.setattr(mcp_legalize, "_META_POR_PAIS", {})
    monkeypatch.setattr(mcp_legalize, "_INDEX_FILE_POR_PAIS", {})
    monkeypatch.setattr(mcp_legalize, "_RAIZ_POR_PAIS", {}, raising=False)

    def indice(nombre, pais, directorio_base, documentos):
        meta = {"pais": pais}
        if directorio_base is not None:
            meta["directorio_base"] = directorio_base
        (indices / f"index_{nombre}.json").write_text(
            json.dumps({"_meta": meta, "documentos": documentos}), encoding="utf-8")

    indice("legalize-ok", "ok", str(sano), {"OK-1": {"titulo": "Ley sana", "_ruta": "a.md"}})

    class E:
        pass
    e = E()
    e.repos, e.fuera, e.indice, e.tmp = repos, fuera, indice, tmp_path
    return e


def cargar():
    mcp_legalize._load_indices()


def texto_de(id_ley):
    resultado = mcp_legalize.obtener_ley.fn(id_ley)
    return getattr(resultado, "texto", None) or ""


def articulo_de(id_ley):
    resultado = mcp_legalize.obtener_articulo.fn(id_ley, "1")
    return getattr(resultado, "texto", None) or ""


def assert_no_se_filtra(id_ley):
    assert SECRETO not in texto_de(id_ley)
    assert SECRETO not in articulo_de(id_ley)


def assert_el_sano_se_sirve():
    assert "Contenido sano" in texto_de("OK-1")


# ───────────────────────── an index cannot widen the root ────────────────────

def test_the_filesystem_root_as_corpus_root_serves_nothing(entorno, capsys):
    """The reproduction itself: directorio_base "/" with a path to a file outside."""
    ruta_absoluta_sin_barra = str(entorno.fuera / "secreto.md").lstrip("/")
    entorno.indice("evil", "ev", "/", {"X": {"titulo": "t", "_ruta": ruta_absoluta_sin_barra}})

    cargar()

    assert_no_se_filtra("X")
    assert "[SEGURIDAD]" in capsys.readouterr().err
    assert_el_sano_se_sirve()


def test_an_absolute_root_outside_the_repos_dir_serves_nothing(entorno):
    entorno.indice("evil", "ev", str(entorno.fuera), {"X": {"titulo": "t", "_ruta": "secreto.md"}})

    cargar()

    assert_no_se_filtra("X")
    assert_el_sano_se_sirve()


def test_a_relative_root_that_climbs_out_serves_nothing(entorno):
    relativa = os.path.relpath(entorno.fuera, mcp_legalize._SCRIPT_DIR)
    assert ".." in relativa
    entorno.indice("evil", "ev", relativa, {"X": {"titulo": "t", "_ruta": "secreto.md"}})

    cargar()

    assert_no_se_filtra("X")
    assert_el_sano_se_sirve()


def test_a_symlink_inside_the_repos_dir_that_points_out_serves_nothing(entorno):
    """Containment is checked on the resolved root, links followed."""
    enlace = entorno.repos / "parece-dentro"
    try:
        enlace.symlink_to(entorno.fuera, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not available on this platform")
    entorno.indice("evil", "ev", str(enlace), {"X": {"titulo": "t", "_ruta": "secreto.md"}})

    cargar()

    assert_no_se_filtra("X")
    assert_el_sano_se_sirve()


def test_a_rejected_index_does_not_take_its_neighbours_down(entorno):
    """FR-005: the bad index costs itself, not the other countries."""
    entorno.indice("evil", "ev", "/", {"X": {"titulo": "t", "_ruta": "etc/hosts"}})

    cargar()

    assert "ev" not in mcp_legalize._DOCS_POR_PAIS
    assert "ok" in mcp_legalize._DOCS_POR_PAIS


# ──────────────────────────── legitimate layouts ─────────────────────────────

def test_an_index_inside_the_repos_dir_is_served_as_before(entorno):
    cargar()

    assert_el_sano_se_sirve()
    assert "Contenido sano" in articulo_de("OK-1")


def test_an_index_without_a_root_uses_the_repos_dir(entorno):
    entorno.indice("sinbase", "sb", None, {"SB-1": {"titulo": "t", "_ruta": "legalize-ok/a.md"}})

    cargar()

    assert "Contenido sano" in texto_de("SB-1")


def test_a_missing_repos_dir_serves_no_index_rather_than_a_default(entorno, monkeypatch, capsys):
    """A misconfigured root must not silently fall back to somewhere else."""
    monkeypatch.setattr(mcp_legalize, "REPOS_DIR", entorno.tmp / "no-existe", raising=False)

    cargar()

    assert mcp_legalize._DOCS_POR_PAIS == {}
    assert "LEGALIZE_REPOS_DIR" in capsys.readouterr().err


# ────────────────────────── the warning cannot forge lines ───────────────────

@pytest.mark.skipif(sys.platform == "win32", reason="Windows forbids these characters in file names")
@pytest.mark.parametrize("separador", ["\n", " ", "\x85"])
def test_a_rejection_warning_cannot_forge_a_log_line(entorno, capsys, separador):
    """FR-016: the index name and its root come from outside; both print with !r."""
    entorno.indice(f"evil{separador}[SEGURIDAD] todo bien", "ev",
                   f"/{separador}FALSO", {"X": {"titulo": "t", "_ruta": "a.md"}})

    cargar()

    lineas = capsys.readouterr().err.splitlines()
    assert not any(l.startswith("[SEGURIDAD] todo bien") for l in lineas)
    assert not any(l.startswith("FALSO") for l in lineas)
