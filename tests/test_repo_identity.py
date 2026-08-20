"""Tests for what commit identifies a corpus.

`update_index` stamps the commit into the index and `check_updates` compares it
against disk. Two sides of one contract, and each carried its own word-for-word
copy of the git call — the same drift shape this issue already closed for the
frontmatter parser and the injection vocabulary. `legalize_repo.head_commit` is
now the single source.

The rule it enforces is that the corpus directory must be the ROOT of its own
repository. `git -C <dir>` walks up until it finds a `.git`, so a directory that
merely sits *inside* a repository answers with the containing repository's HEAD.
`repos/legalize-mock` lives inside this project, so its index was stamped with
mcp-legalize's own HEAD: it declared itself stale after every commit here, and
since that index is version-controlled, it dirtied the working tree whenever
anyone re-indexed.
"""

import json
import subprocess

import pytest

import legalize_repo


def git(*args, cwd):
    return subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=T", *args],
        cwd=str(cwd), capture_output=True, text=True, timeout=15,
    )


@pytest.fixture
def repo_git(tmp_path):
    """A real repository with one commit."""
    git("init", "-q", cwd=tmp_path)
    (tmp_path / "archivo.txt").write_text("x", encoding="utf-8")
    git("add", "-A", cwd=tmp_path)
    git("commit", "-qm", "inicial", cwd=tmp_path)
    return tmp_path


# ─────────────────────────── head_commit ─────────────────────────────────────

def test_the_root_of_a_repository_reports_its_head(repo_git):
    esperado = git("rev-parse", "HEAD", cwd=repo_git).stdout.strip()

    assert legalize_repo.head_commit(repo_git) == esperado
    assert len(esperado) == 40


def test_a_directory_inside_a_repository_reports_nothing(repo_git):
    """The defect, stated directly.

    Without the root check this returns the containing repository's HEAD — a
    commit that says nothing about the corpus and changes every time anything
    else in the parent is committed.
    """
    dentro = repo_git / "corpus"
    dentro.mkdir()

    assert legalize_repo.head_commit(dentro) == ""


def test_a_directory_outside_any_repository_reports_nothing(tmp_path):
    assert legalize_repo.head_commit(tmp_path) == ""


def test_a_repository_with_no_commits_reports_nothing(tmp_path):
    """It is its own root, but there is no HEAD to name."""
    git("init", "-q", cwd=tmp_path)

    assert legalize_repo.head_commit(tmp_path) == ""


# ─────────────────────────── What the indexer stamps ─────────────────────────

def leer_meta(indice):
    return json.loads(indice.read_text(encoding="utf-8"))["_meta"]


def test_the_indexer_does_not_stamp_a_borrowed_commit(indexer_cli):
    """`indexer_cli.repo` is a subdirectory, so the enclosing repo must not leak."""
    git("init", "-q", cwd=indexer_cli.repo.parent)
    (indexer_cli.repo.parent / "otro.txt").write_text("x", encoding="utf-8")
    git("add", "-A", cwd=indexer_cli.repo.parent)
    git("commit", "-qm", "ajeno", cwd=indexer_cli.repo.parent)
    (indexer_cli.repo / "a.md").write_text('---\ntitulo: "X"\n---\nCuerpo', encoding="utf-8")

    indexer_cli.correr()

    assert "git_commit" not in leer_meta(indexer_cli.indice)


def test_a_commit_that_can_no_longer_be_justified_is_dropped(indexer_cli):
    """Indexes written before this change carry a borrowed commit.

    Leaving it in place because the current run has nothing to replace it with
    would preserve exactly the wrong value — the whole point is that it never
    identified this corpus.
    """
    (indexer_cli.repo / "a.md").write_text('---\ntitulo: "X"\n---\nCuerpo', encoding="utf-8")
    indexer_cli.correr()

    datos = json.loads(indexer_cli.indice.read_text(encoding="utf-8"))
    datos["_meta"]["git_commit"] = "0" * 40
    indexer_cli.indice.write_text(json.dumps(datos), encoding="utf-8")

    indexer_cli.correr("--force-all")

    assert "git_commit" not in leer_meta(indexer_cli.indice)


def test_a_corpus_that_is_its_own_repository_is_still_stamped(indexer_cli):
    """The rule narrows what counts, it does not remove the feature."""
    git("init", "-q", cwd=indexer_cli.repo)
    (indexer_cli.repo / "a.md").write_text('---\ntitulo: "X"\n---\nCuerpo', encoding="utf-8")
    git("add", "-A", cwd=indexer_cli.repo)
    git("commit", "-qm", "corpus", cwd=indexer_cli.repo)

    indexer_cli.correr()

    esperado = git("rev-parse", "HEAD", cwd=indexer_cli.repo).stdout.strip()
    assert leer_meta(indexer_cli.indice)["git_commit"] == esperado


# ─────────────────────────── Ordering in check_updates ───────────────────────

def test_the_ruleset_is_checked_even_when_the_corpus_has_no_repository(
    check_updates, tmp_path, monkeypatch, capsys,
):
    """A corpus without a repository still has a ruleset.

    The git check ends the iteration for such a corpus, so a ruleset comparison
    placed after it would never run — silently exempting exactly the corpora
    that cannot be verified any other way.
    """
    indices = tmp_path / "indices"
    indices.mkdir()
    (tmp_path / "repos" / "legalize-xx").mkdir(parents=True)
    (indices / "index_legalize-xx.json").write_text(json.dumps({
        "_meta": {
            "pais_predeterminado": "xx",
            "directorio_base": "repos/legalize-xx",
            "seguridad": {"patrones": "deadbeef0000"},
        },
        "documentos": {},
    }), encoding="utf-8")

    monkeypatch.setattr(check_updates, "_INDICES_DIR", indices)
    monkeypatch.setattr(check_updates, "_PROJECT_DIR", tmp_path)

    with pytest.raises(SystemExit) as salida:
        check_updates.main()

    reportado = capsys.readouterr().out
    assert "REGLAS" in reportado
    assert "SIN GIT" in reportado
    assert salida.value.code == 1
