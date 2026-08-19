"""Tests for `_resolve_ruta`, the path-traversal boundary of the MCP server.

Every document the server returns is read from disk through this function. It is
the only thing standing between a malicious or stale index entry and an
arbitrary file read, so its contract is pinned here before any refactor moves it.
"""

import sys

import pytest

import mcp_legalize


PAIS = "test"


@pytest.fixture
def repo_root(tmp_path, monkeypatch):
    """Point the server at an isolated corpus rooted at `tmp_path/repos/legalize-test`.

    `_resolve_ruta` builds its root as `_SCRIPT_DIR / directorio_base`, so both
    the script directory and the country metadata have to be redirected.
    """
    root = tmp_path / "repos" / "legalize-test"
    (root / "test").mkdir(parents=True)
    (root / "test" / "LAW-1.md").write_text("body", encoding="utf-8")

    monkeypatch.setattr(mcp_legalize, "_SCRIPT_DIR", tmp_path)
    monkeypatch.setitem(
        mcp_legalize._META_POR_PAIS, PAIS, {"directorio_base": "repos/legalize-test"}
    )
    return root


def _doc(**fields):
    return dict(fields)


# ─────────────────────────── Accepted ────────────────────────────────────────

def test_resolves_a_nested_relative_path(repo_root):
    ruta = mcp_legalize._resolve_ruta(_doc(_ruta="test/LAW-1.md"), PAIS)

    assert ruta == (repo_root / "test" / "LAW-1.md").resolve()
    assert ruta.read_text(encoding="utf-8") == "body"


def test_accepts_a_path_that_does_not_exist_yet(repo_root):
    """A missing file is not a security failure — `_read_file` handles it.

    Containment is still asserted: a non-existent path must resolve inside the
    root, otherwise the check would be trivially satisfiable by any typo.
    """
    ruta = mcp_legalize._resolve_ruta(_doc(_ruta="test/MISSING.md"), PAIS)

    assert not ruta.exists()
    assert ruta.is_relative_to(repo_root.resolve())


# ─────────────────────────── Rejected ────────────────────────────────────────

def test_rejects_posix_absolute_path(repo_root):
    """Rejected on every platform — but not always by the same guard.

    On POSIX, `Path("/etc/passwd").is_absolute()` is True and the first check
    fires. On Windows the same string has a root but no drive, so Python treats
    it as root-relative, `is_absolute()` returns False, and the rejection falls
    through to the containment check instead. The path never escapes either
    way; only the error message differs. See
    `test_posix_absolute_path_is_not_absolute_on_windows` below.
    """
    with pytest.raises(ValueError):
        mcp_legalize._resolve_ruta(_doc(_ruta="/etc/passwd"), PAIS)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-style drive paths")
def test_rejects_windows_absolute_path(repo_root):
    with pytest.raises(ValueError, match="absoluta"):
        mcp_legalize._resolve_ruta(_doc(_ruta=r"C:\Windows\System32\drivers\etc\hosts"), PAIS)


@pytest.mark.skipif(sys.platform != "win32", reason="documents a Windows-only quirk")
def test_posix_absolute_path_is_not_absolute_on_windows(repo_root):
    """Pins the platform quirk so a future refactor cannot lose the second guard.

    The `is_absolute()` check alone does not stop `/etc/passwd` on Windows.
    Only the `relative_to` containment check does. Anyone tempted to drop the
    containment check as redundant should read this test first.
    """
    from pathlib import Path

    assert Path("/etc/passwd").is_absolute() is False

    with pytest.raises(ValueError, match="fuera del directorio"):
        mcp_legalize._resolve_ruta(_doc(_ruta="/etc/passwd"), PAIS)


def test_rejects_parent_directory_traversal(repo_root):
    with pytest.raises(ValueError, match="fuera del directorio"):
        mcp_legalize._resolve_ruta(_doc(_ruta="../../../etc/passwd"), PAIS)


def test_rejects_traversal_hidden_mid_path(repo_root):
    """`a/../../b` normalises out of the root even though it starts inside it."""
    with pytest.raises(ValueError, match="fuera del directorio"):
        mcp_legalize._resolve_ruta(_doc(_ruta="test/../../secrets.md"), PAIS)


def test_rejects_sibling_directory_with_shared_prefix(tmp_path, repo_root):
    """`legalize-test-evil` shares a string prefix with the root but is outside it.

    This is why the check uses `Path.relative_to` and not `str.startswith`;
    a prefix comparison would accept this path.
    """
    evil = tmp_path / "repos" / "legalize-test-evil"
    evil.mkdir(parents=True)
    (evil / "payload.md").write_text("owned", encoding="utf-8")

    with pytest.raises(ValueError, match="fuera del directorio"):
        mcp_legalize._resolve_ruta(_doc(_ruta="../legalize-test-evil/payload.md"), PAIS)


def test_rejects_document_without_any_path(repo_root):
    with pytest.raises(ValueError, match="sin ruta"):
        mcp_legalize._resolve_ruta(_doc(titulo="no path at all"), PAIS)


def test_rejects_empty_path(repo_root):
    with pytest.raises(ValueError, match="sin ruta"):
        mcp_legalize._resolve_ruta(_doc(_ruta="", _archivo=""), PAIS)


def test_rejects_path_pointing_at_a_directory(repo_root):
    with pytest.raises(ValueError, match="fichero regular"):
        mcp_legalize._resolve_ruta(_doc(_ruta="test"), PAIS)


def test_rejects_symlink_escaping_the_root(repo_root, tmp_path):
    outside = tmp_path / "outside.md"
    outside.write_text("secret", encoding="utf-8")
    link = repo_root / "test" / "escape.md"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation not permitted on this platform")

    with pytest.raises(ValueError, match="fuera del directorio"):
        mcp_legalize._resolve_ruta(_doc(_ruta="test/escape.md"), PAIS)


# ─────────────────────────── `_read_file` contract ───────────────────────────

def test_read_file_returns_empty_string_when_path_is_rejected(repo_root):
    """A rejected path must not raise into the tool layer — it degrades to ''."""
    assert mcp_legalize._read_file(_doc(_ruta="/etc/passwd"), PAIS) == ""


def test_read_file_returns_empty_string_for_missing_file(repo_root):
    assert mcp_legalize._read_file(_doc(_ruta="test/MISSING.md"), PAIS) == ""


def test_read_file_returns_content_for_a_valid_document(repo_root):
    assert mcp_legalize._read_file(_doc(_ruta="test/LAW-1.md"), PAIS) == "body"


@pytest.mark.xfail(
    strict=True,
    reason="mcp_legalize._read_file catches only OSError; read_text raises "
           "ValueError on an embedded null byte and the exception escapes",
)
def test_read_file_degrades_on_a_path_the_filesystem_rejects(repo_root):
    """`_read_file` must never raise into the tool layer, whatever the index says.

    `_resolve_ruta` accepts an embedded null byte: `resolve()` tolerates it and
    the path stays inside the root, so neither guard fires. The failure lands on
    `read_text`, which raises `ValueError` — while `_read_file` only catches
    `OSError`. The exception escapes and takes `obtener_ley` down with it.

    A crafted index is exactly the threat `_resolve_ruta` is documented to
    defend against, so this path is reachable. Marked xfail because the fix
    belongs to `mcp_legalize.py`, not to this test branch.
    """
    assert mcp_legalize._read_file(_doc(_ruta="test/a\x00b.md"), PAIS) == ""


# ─────────────────────────── Known defect: issue #1 / B3 ─────────────────────

@pytest.mark.xfail(
    strict=True,
    reason="issue #1 B3: `_archivo` holds a bare filename, so the fallback "
           "silently resolves outside the document's actual directory and the "
           "document comes back empty instead of erroring",
)
def test_archivo_fallback_does_not_silently_resolve_to_the_wrong_file(repo_root):
    """An index entry with only `_archivo` must fail loudly, not read nothing.

    `_archivo` is written as `md_path.name`. For the real nested layout
    (`test/LAW-1.md`) the fallback builds `<root>/LAW-1.md`, which does not
    exist, and `_read_file` swallows the error and returns an empty string.
    A caller cannot distinguish that from a genuinely empty law.
    """
    doc = _doc(_archivo="LAW-1.md")

    ruta = mcp_legalize._resolve_ruta(doc, PAIS)

    assert ruta == (repo_root / "test" / "LAW-1.md").resolve()
