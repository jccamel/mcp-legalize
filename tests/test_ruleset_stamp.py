"""Tests for the scanner-ruleset fingerprint stamped into the index.

The index recorded *when* it was scanned and never *with what*. That gap is
worse than it sounds, because an incremental run only rescans files whose size
or mtime changed on disk: change a pattern and 12,291 documents keep findings
computed under rules that no longer exist, while `escaneado_en` is refreshed to
today. The timestamp does not merely omit the ruleset — it actively lies about
the freshness of the audit.

`legalize_injection.huella` fingerprints the rules, `update_index` stamps it
into `_meta.seguridad` and forces a full rescan when it moves, and
`check_updates` reports the mismatch.

The fingerprint is derived from the patterns rather than maintained by hand for
the same reason the vocabulary is shared at all (issue #1 A1, A2): anything that
depends on a person remembering to update it drifts out of sync. These tests
pin what it covers, and — just as importantly — what it must ignore.
"""

import json
import re

import pytest

import legalize_injection as inj


def rehacer(pattern, **cambios):
    """A copy of one pattern with fields replaced, for fingerprint sensitivity."""
    return pattern._replace(**cambios)


def huella_con(patrones):
    """The fingerprint of an arbitrary pattern list, via a temporary swap."""
    original = inj.PATTERNS[:]
    try:
        inj.PATTERNS[:] = patrones
        return inj.huella()
    finally:
        inj.PATTERNS[:] = original


# ─────────────────────────── What the fingerprint covers ─────────────────────

def test_the_fingerprint_is_stable_across_calls():
    assert inj.huella() == inj.huella()


def test_the_fingerprint_is_stable_across_processes(indexer_cli):
    """It ends up written into an index other runs compare against, so a value
    that depended on hash randomization or dict order would be worthless."""
    (indexer_cli.repo / "a.md").write_text('---\ntitulo: "X"\n---\nCuerpo', encoding="utf-8")
    indexer_cli.correr()

    grabada = json.loads(indexer_cli.indice.read_text(encoding="utf-8"))
    assert grabada["_meta"]["seguridad"]["patrones"] == inj.huella()


SENSITIVE_FIELDS = [
    pytest.param({"severity": inj.SEVERITY_WARN}, id="severity"),
    pytest.param({"gates": ("otra_cosa",)}, id="gates"),
    pytest.param({"regex": re.compile(r"algo\s+distinto", re.IGNORECASE)}, id="regex"),
    pytest.param({"regex": re.compile(
        r"ignore\s+(all\s+)?(previous|prior|earlier|above)\s+(instructions?|context|prompts?)",
        re.IGNORECASE | re.MULTILINE)}, id="flags"),
    pytest.param({"label": "en.renombrado"}, id="label"),
]


@pytest.mark.parametrize("cambio", SENSITIVE_FIELDS)
def test_the_fingerprint_moves_when_detection_changes(cambio):
    """Every field that can change what a scan finds has to move the stamp.

    `gates` is in the list for a concrete reason: a badly written gate silences
    its pattern before the regex ever runs, which is exactly how
    `en.role_override` was mute on both surfaces. A fingerprint that ignored
    gates would call that index current.
    """
    base = inj.PATTERNS[:]
    mutado = [rehacer(base[0], **cambio)] + base[1:]

    assert huella_con(mutado) != huella_con(base)


def test_reordering_the_table_does_not_move_the_fingerprint():
    """Order changes nothing about what is detected, and the labels are stored
    sorted in the index — so a reshuffle must not cost a corpus-wide rescan."""
    invertido = list(reversed(inj.PATTERNS))

    assert huella_con(invertido) == huella_con(inj.PATTERNS[:])


def test_a_metadata_only_change_does_not_move_the_body_fingerprint():
    """The index records body-scan outcomes, nothing else.

    Metadata patterns decide what is filtered at serve time and never affect a
    stored finding, so moving one must not invalidate 12,291 audits.
    """
    base = inj.PATTERNS[:]
    solo_metadatos = next(i for i, p in enumerate(base) if p.surfaces == inj.ONLY_METADATA)
    mutado = base[:]
    mutado[solo_metadatos] = rehacer(base[solo_metadatos], regex=re.compile("nuevo"))

    assert huella_con(mutado) == huella_con(base)


def test_the_two_surfaces_have_different_fingerprints():
    assert inj.huella(inj.SURFACE_BODY) != inj.huella(inj.SURFACE_METADATA)


# ─────────────────────────── What the indexer does with it ───────────────────

def leer_seguridad(indice):
    return json.loads(indice.read_text(encoding="utf-8"))["_meta"]["seguridad"]


def test_a_fresh_index_is_stamped(indexer_cli):
    (indexer_cli.repo / "a.md").write_text('---\ntitulo: "X"\n---\nCuerpo', encoding="utf-8")

    indexer_cli.correr()

    assert leer_seguridad(indexer_cli.indice)["patrones"] == inj.huella()


def test_an_unchanged_run_rescans_nothing(indexer_cli):
    (indexer_cli.repo / "a.md").write_text('---\ntitulo: "X"\n---\nCuerpo', encoding="utf-8")
    indexer_cli.correr()

    segunda = indexer_cli.correr()

    assert "El índice ya está al día" in segunda.stdout


def test_a_changed_ruleset_forces_a_rescan(indexer_cli):
    """The whole point: a stale audit must not survive behind a fresh timestamp."""
    (indexer_cli.repo / "a.md").write_text('---\ntitulo: "X"\n---\nCuerpo', encoding="utf-8")
    indexer_cli.correr()

    datos = json.loads(indexer_cli.indice.read_text(encoding="utf-8"))
    datos["_meta"]["seguridad"]["patrones"] = "deadbeef0000"
    indexer_cli.indice.write_text(json.dumps(datos), encoding="utf-8")

    tercera = indexer_cli.correr()

    assert "Reglas de escaneo" in tercera.stdout
    assert "Modificados       : 1" in tercera.stdout
    assert leer_seguridad(indexer_cli.indice)["patrones"] == inj.huella()


def test_an_index_with_no_stamp_is_rescanned(indexer_cli):
    """Every index written before this change. "We do not know" is not "current"."""
    (indexer_cli.repo / "a.md").write_text('---\ntitulo: "X"\n---\nCuerpo', encoding="utf-8")
    indexer_cli.correr()

    datos = json.loads(indexer_cli.indice.read_text(encoding="utf-8"))
    del datos["_meta"]["seguridad"]["patrones"]
    indexer_cli.indice.write_text(json.dumps(datos), encoding="utf-8")

    tercera = indexer_cli.correr()

    assert "no registra con cuáles se escaneó" in tercera.stdout
    assert "Modificados       : 1" in tercera.stdout


def test_the_timestamp_still_moves_with_the_stamp(indexer_cli):
    """Both facts are recorded; the stamp explains the timestamp, not replaces it."""
    (indexer_cli.repo / "a.md").write_text('---\ntitulo: "X"\n---\nCuerpo', encoding="utf-8")
    indexer_cli.correr()

    seguridad = leer_seguridad(indexer_cli.indice)

    assert set(seguridad) == {
        "escaneado_en", "patrones", "cuarentena", "forzados", "avisos",
        # `duplicados` entró con #20: un identificador repetido dice algo del
        # repositorio de origen, igual que un hallazgo de inyección, así que se
        # sella en el índice en lugar de quedarse en la consola de quien lo generó.
        "duplicados",
        # `metadatos` entró con #22: hasta entonces el frontmatter era la única
        # región que se indexaba y se servía sin que nadie la examinara del lado
        # del indexador. No bloquea — el servidor ya la filtra —, pero queda
        # sellada para que la huella de reglas cubra las dos superficies.
        "metadatos",
        # `truncados` entró con #21: un corpus que entrega títulos de 100 KB dice
        # algo de su procedencia, y recortarlos en silencio sería la misma
        # pérdida callada de datos que este proyecto lleva tres issues negándose
        # a aceptar.
        "truncados",
    }


# ─────────────────────────── What check_updates reports ──────────────────────

def test_check_updates_flags_an_index_audited_with_other_rules(
    check_updates, tmp_path, monkeypatch, capsys,
):
    indices = tmp_path / "indices"
    indices.mkdir()
    repo = tmp_path / "repos" / "legalize-xx"
    repo.mkdir(parents=True)
    (indices / "index_legalize-xx.json").write_text(json.dumps({
        "_meta": {
            "pais_predeterminado": "xx",
            "directorio_base": "repos/legalize-xx",
            "git_commit": "abc1234",
            "seguridad": {"patrones": "deadbeef0000"},
        },
        "documentos": {},
    }), encoding="utf-8")

    monkeypatch.setattr(check_updates, "_INDICES_DIR", indices)
    monkeypatch.setattr(check_updates, "_PROJECT_DIR", tmp_path)
    # El helper vive en el modulo compartido desde que las dos copias de la
    # consulta a git se unificaron; monkeypatch lo restaura al salir.
    monkeypatch.setattr(check_updates.legalize_repo, "head_commit",
                        lambda _: "abc1234")

    with pytest.raises(SystemExit) as salida:
        check_updates.main()

    reportado = capsys.readouterr().out
    assert "REGLAS" in reportado
    assert "deadbeef0000" in reportado and inj.huella() in reportado
    # Up to date on disk and still stale: the two facts are independent.
    assert "OK" in reportado
    assert salida.value.code == 1


def test_check_updates_stays_quiet_when_the_rules_match(
    check_updates, tmp_path, monkeypatch, capsys,
):
    indices = tmp_path / "indices"
    indices.mkdir()
    repo = tmp_path / "repos" / "legalize-xx"
    repo.mkdir(parents=True)
    (indices / "index_legalize-xx.json").write_text(json.dumps({
        "_meta": {
            "pais_predeterminado": "xx",
            "directorio_base": "repos/legalize-xx",
            "git_commit": "abc1234",
            "seguridad": {"patrones": inj.huella()},
        },
        "documentos": {},
    }), encoding="utf-8")

    monkeypatch.setattr(check_updates, "_INDICES_DIR", indices)
    monkeypatch.setattr(check_updates, "_PROJECT_DIR", tmp_path)
    # El helper vive en el modulo compartido desde que las dos copias de la
    # consulta a git se unificaron; monkeypatch lo restaura al salir.
    monkeypatch.setattr(check_updates.legalize_repo, "head_commit",
                        lambda _: "abc1234")

    check_updates.main()

    reportado = capsys.readouterr().out
    assert "REGLAS" not in reportado
    assert "Todos los índices están al día" in reportado
