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
    import legalize_indice
    return legalize_indice.como_dict(indice)["_meta"]


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

    indexer_cli.poner_meta("git_commit", "0" * 40)

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
    check_updates, crear_indice, tmp_path, monkeypatch, capsys,
):
    """A corpus without a repository still has a ruleset.

    The git check ends the iteration for such a corpus, so a ruleset comparison
    placed after it would never run — silently exempting exactly the corpora
    that cannot be verified any other way.
    """
    indices = tmp_path / "indices"
    indices.mkdir()
    (tmp_path / "repos" / "legalize-xx").mkdir(parents=True)
    crear_indice(indices / "index_legalize-xx.db", {
        "pais_predeterminado": "xx",
        "directorio_base": "repos/legalize-xx",
        "seguridad": {"patrones": "deadbeef0000"},
    })

    monkeypatch.setattr(check_updates, "_INDICES_DIR", indices)
    monkeypatch.setattr(check_updates, "_PROJECT_DIR", tmp_path)

    with pytest.raises(SystemExit) as salida:
        check_updates.main()

    reportado = capsys.readouterr().out
    assert "REGLAS" in reportado
    assert "SIN GIT" in reportado
    assert salida.value.code == 1


# ──────────────────────── a hostile root (check_updates) ─────────────────────
#
# `check_updates` runs git in the directory the index names as its corpus root.
# The index is untrusted (principle II): a tampered one could name any directory
# on disk, and a repository whose own `.git/config` runs commands —
# `core.fsmonitor`, hooks, a pager. A clone never brings its `.git/config` from
# upstream, so the realistic attacker is whoever can write to `indices/`.

def trampa(directorio, centinela):
    """A repository whose own configuration creates `centinela` if git obeys it."""
    directorio.mkdir(parents=True)
    git("init", "-q", cwd=directorio)
    (directorio / "a.md").write_text("x", encoding="utf-8")
    git("add", "-A", cwd=directorio)
    git("commit", "-qm", "x", cwd=directorio)
    ganchos = directorio / ".git" / "ganchos-hostiles"
    ganchos.mkdir()
    for gancho in ("post-checkout", "post-index-change", "reference-transaction", "pre-auto-gc"):
        script = ganchos / gancho
        script.write_text(f"#!/bin/sh\ntouch '{centinela}'\n", encoding="utf-8")
        script.chmod(0o755)
    git("config", "core.fsmonitor", f"touch '{centinela}'; false", cwd=directorio)
    git("config", "core.hooksPath", str(ganchos), cwd=directorio)
    git("config", "core.pager", f"touch '{centinela}'; cat", cwd=directorio)
    return directorio


@pytest.fixture
def entorno_check(check_updates, crear_indice, tmp_path, monkeypatch):
    indices = tmp_path / "indices"
    indices.mkdir()
    (tmp_path / "repos").mkdir()
    monkeypatch.setattr(check_updates, "_INDICES_DIR", indices)
    monkeypatch.setattr(check_updates, "_PROJECT_DIR", tmp_path)
    monkeypatch.delenv("LEGALIZE_REPOS_DIR", raising=False)
    llamadas = []
    original = check_updates.legalize_repo.head_commit
    monkeypatch.setattr(check_updates.legalize_repo, "head_commit",
                        lambda d: llamadas.append(d) or original(d))

    def indice(directorio_base):
        crear_indice(indices / "index_legalize-xx.db", {
            "pais_predeterminado": "xx", "directorio_base": directorio_base,
        })

    return tmp_path, indice, llamadas


def correr(check_updates, capsys):
    try:
        check_updates.main()
    except SystemExit:
        pass
    return capsys.readouterr().out


@pytest.mark.skipif(not hasattr(__import__("os"), "symlink"), reason="needs symlinks")
@pytest.mark.parametrize("escape", ["absoluta", "relativa", "enlace"])
def test_check_updates_runs_no_git_outside_the_authorised_directory(
    check_updates, entorno_check, capsys, escape,
):
    raiz, indice, llamadas = entorno_check
    centinela = raiz / "pwned"
    hostil = trampa(raiz / "fuera" / "evil", centinela)
    if escape == "absoluta":
        indice(str(hostil))
    elif escape == "relativa":
        indice("repos/../fuera/evil")
    else:
        try:
            (raiz / "repos" / "legalize-xx").symlink_to(hostil, target_is_directory=True)
        except OSError:
            pytest.skip("the platform refuses to create symlinks")
        indice("repos/legalize-xx")

    reportado = correr(check_updates, capsys)

    assert "RAÍZ" in reportado
    assert llamadas == []
    assert not centinela.exists()


def test_a_root_inside_the_authorised_directory_is_still_checked(
    check_updates, entorno_check, capsys,
):
    raiz, indice, llamadas = entorno_check
    (raiz / "repos" / "legalize-xx").mkdir()
    indice("repos/legalize-xx")

    reportado = correr(check_updates, capsys)

    assert "RAÍZ" not in reportado
    assert len(llamadas) == 1


def test_the_authorised_directory_follows_legalize_repos_dir(
    check_updates, entorno_check, capsys, monkeypatch,
):
    """The same directory the server serves from, chosen by the operator."""
    raiz, indice, llamadas = entorno_check
    otro = raiz / "otros-repos" / "legalize-xx"
    otro.mkdir(parents=True)
    monkeypatch.setenv("LEGALIZE_REPOS_DIR", str(raiz / "otros-repos"))
    indice(str(otro))

    reportado = correr(check_updates, capsys)

    assert "RAÍZ" not in reportado
    assert len(llamadas) == 1


def test_head_commit_obeys_no_command_from_the_repository_config(tmp_path):
    """Second barrier: even an authorised repository cannot make git run its
    configuration. The trap is checked to be armed first, so a pass means git
    was told not to obey it, not that the trap was broken."""
    centinela = tmp_path / "pwned"
    repo = trampa(tmp_path / "repo", centinela)
    git("status", cwd=repo)
    assert centinela.exists(), "la trampa no está armada"
    centinela.unlink()

    assert len(legalize_repo.head_commit(repo)) == 40
    assert not centinela.exists()


def test_head_commit_disables_the_config_that_runs_commands(repo_git, monkeypatch):
    """`rev-parse` does not refresh the index today, so the trap above stays
    quiet either way. This pins the overrides themselves, so they cannot be
    dropped in a refactor without a test noticing."""
    vistos = []
    real = subprocess.run

    def espia(args, **kw):
        vistos.append((args, kw.get("env") or {}))
        return real(args, **kw)

    monkeypatch.setattr(legalize_repo.subprocess, "run", espia)
    legalize_repo.head_commit(repo_git)

    assert vistos
    for args, env in vistos:
        assert "core.fsmonitor=false" in args
        assert any(a.startswith("core.hooksPath=") for a in args)
        assert env.get("GIT_CONFIG_NOSYSTEM") == "1"
        assert env.get("GIT_PAGER") == "cat"
