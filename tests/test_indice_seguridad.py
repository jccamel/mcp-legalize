"""Tests that a tampered index database is refused before it is queried (spec 002, US2).

Whoever can write to `indices/` is the threat model's attacker (constitution
principle II). The JSON index needed path containment; the pickle it replaced
needed to disappear. A SQLite database brings its own surface: a schema can
carry triggers and views that change what a query does, an FTS3 tokenizer can
be registered from SQL, a page can be corrupt.

`legalize_indice.abrir` answers all of it the same way: open read-only, in
SQLite's defensive mode with `trusted_schema=OFF` and `query_only`, and compare
the schema against the canonical one before running a single query on the
data. Anything else in the schema rejects the database, with a reason, and costs
only that corpus.
"""

import shutil
import sqlite3
import types

import pytest

import legalize_indice as li


@pytest.fixture
def valida(tmp_path):
    ruta = li.ruta_indice(tmp_path / "ok", "tst")
    escritor = li.Escritor(ruta)
    escritor.poner_ley("TST-A", {"titulo": "Ley", "_ruta": "a.md", "_bytes": 1}, "Artículo 1\nTexto.\n")
    escritor.confirmar()
    return ruta


def manipular(valida, tmp_path, *sentencias, writable_schema=False):
    """Una copia de la base de datos válida, alterada con una conexión normal."""
    copia = tmp_path / "evil" / "index_tst.db"
    copia.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(valida, copia)
    con = sqlite3.connect(copia)
    if writable_schema:
        con.execute("PRAGMA writable_schema=ON")
    for s in sentencias:
        con.execute(s)
    con.commit()
    con.close()
    return copia


def motivo(ruta):
    with pytest.raises(ValueError) as exc:
        li.abrir(ruta)
    return str(exc.value)


def test_a_valid_database_opens(valida):
    assert li.abrir(valida).execute("SELECT count(*) FROM leyes").fetchone()[0] == 1


@pytest.mark.parametrize("sentencia", [
    "CREATE TRIGGER t AFTER INSERT ON meta BEGIN DELETE FROM leyes; END",
    "CREATE VIEW v AS SELECT * FROM leyes",
    "CREATE TABLE extra(x)",
    "CREATE INDEX extra_titulo ON leyes(titulo)",
    "CREATE VIRTUAL TABLE otra USING fts3(texto, tokenize=simple)",
    "CREATE TABLE cuerpo_extra(x)",
], ids=["trigger", "view", "extra table", "extra index", "fts3 table", "fake shadow table"])
def test_anything_beyond_the_canonical_schema_is_refused(valida, tmp_path, sentencia):
    assert motivo(manipular(valida, tmp_path, sentencia)) == "esquema_inesperado"


def test_a_different_statement_for_a_table_of_the_format_is_refused(valida, tmp_path):
    """A column changed in place, which `sqlite_master` would otherwise accept by name."""
    sql = dict(sqlite3.connect(valida).execute("SELECT name, sql FROM sqlite_master"))["meta"]
    otro = sql.replace("valor TEXT NOT NULL", "valor TEXT NOT NULL DEFAULT 'x'")
    copia = tmp_path / "evil" / "index_tst.db"
    copia.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(valida, copia)
    con = sqlite3.connect(copia)
    # Un atacante usa su propio SQLite sin modo defensivo; este lo trae activo
    # por defecto y hay que quitarlo para poder reescribir el esquema.
    con.setconfig(sqlite3.SQLITE_DBCONFIG_DEFENSIVE, False)
    con.setconfig(sqlite3.SQLITE_DBCONFIG_WRITABLE_SCHEMA, True)
    con.execute("UPDATE sqlite_master SET sql = ? WHERE name = 'meta'", (otro,))
    con.commit()
    con.close()

    assert motivo(copia) in {"esquema_inesperado", "ilegible"}


def test_another_format_version_is_refused(valida, tmp_path):
    copia = manipular(valida, tmp_path, "UPDATE meta SET valor = '\"99\"' WHERE clave = 'formato'")

    assert motivo(copia) == "formato_distinto"


def test_a_truncated_database_is_unreadable(valida, tmp_path):
    copia = tmp_path / "index_tst.db"
    copia.write_bytes(valida.read_bytes()[:3000])

    assert motivo(copia) in {"ilegible", "esquema_inesperado"}


def test_a_file_that_is_not_sqlite_is_unreadable(tmp_path):
    ruta = tmp_path / "index_tst.db"
    ruta.write_bytes(b"\x80\x05 esto era un pickle")

    assert motivo(ruta) == "ilegible"


def test_a_missing_file_is_unreadable(tmp_path):
    assert motivo(tmp_path / "index_tst.db") == "ilegible"


def test_the_connection_cannot_write(valida):
    con = li.abrir(valida)

    with pytest.raises(sqlite3.OperationalError):
        con.execute("INSERT INTO meta VALUES ('x', '\"y\"')")


def test_the_connection_cannot_rewrite_the_schema(valida):
    """Defensive mode: no writable_schema, no shadow-table writes, even if asked."""
    con = li.abrir(valida)

    with pytest.raises(sqlite3.Error):
        con.execute("PRAGMA writable_schema=ON")
        con.execute("UPDATE sqlite_master SET sql = sql")


def test_a_python_without_defensive_mode_refuses_to_open(valida, monkeypatch):
    """Python < 3.12 has no `setconfig`: refuse rather than open undefended."""
    monkeypatch.setattr(li, "sqlite3", types.SimpleNamespace(Connection=object))

    assert motivo(valida) == "sin_modo_defensivo"


def test_the_opened_connection_carries_every_hardening_setting(valida):
    """Read-only mode alone already stops writes, so the tests above would pass
    without the other settings. This one pins each of them, so removing any is
    caught: defensive mode, no trusted schema, query-only, cell-size checks."""
    con = li.abrir(valida)

    assert con.getconfig(sqlite3.SQLITE_DBCONFIG_DEFENSIVE) is True
    assert con.execute("PRAGMA trusted_schema").fetchone()[0] == 0
    assert con.execute("PRAGMA query_only").fetchone()[0] == 1
    assert con.execute("PRAGMA cell_size_check").fetchone()[0] == 1


def test_defensive_mode_is_requested_explicitly(valida, monkeypatch):
    """Some SQLite builds enable defensive mode by default, so seeing it on proves
    nothing about `abrir`. This records what `abrir` asks for: the hardening must
    not depend on how the platform's SQLite was compiled."""
    pedidos = []

    class Espia(sqlite3.Connection):
        def setconfig(self, opcion, valor=True):
            pedidos.append((opcion, valor))
            return super().setconfig(opcion, valor)

    real = sqlite3.connect
    monkeypatch.setattr(li.sqlite3, "connect", lambda *a, **k: real(*a, factory=Espia, **k))

    li.abrir(valida)

    assert (sqlite3.SQLITE_DBCONFIG_DEFENSIVE, True) in pedidos


# ───────────────────────────── through the server ────────────────────────────

def test_the_server_serves_nothing_on_a_python_without_defensive_mode(valida, tmp_path, monkeypatch, capsys):
    """T015: the refusal reaches the operator, and no corpus is served undefended."""
    import mcp_legalize

    indices = valida.parent
    (tmp_path / "repos").mkdir()
    monkeypatch.setattr(mcp_legalize, "INDICES_DIR", indices)
    monkeypatch.setattr(mcp_legalize, "REPOS_DIR", tmp_path / "repos")
    for tabla in ("_CONEXIONES", "_META_POR_PAIS", "_INDEX_FILE_POR_PAIS",
                  "_RAIZ_POR_PAIS", "_TEXTO_NO_DISPONIBLE"):
        monkeypatch.setattr(mcp_legalize, tabla, {})
    monkeypatch.setattr(li, "sqlite3", types.SimpleNamespace(Connection=object))

    mcp_legalize._load_indices()

    assert mcp_legalize._CONEXIONES == {}
    assert any(l.startswith("[SEGURIDAD]") and "sin_modo_defensivo" in l
               for l in capsys.readouterr().err.splitlines())


@pytest.fixture
def con_texto(instalar_corpus):
    """Bodies that tell a literal reading of a query from an operator reading."""
    documentos = {
        "ARRENDA": {"titulo": "Ley de arrendamientos urbanos", "_ruta": "a.md"},
        "TELE": {"titulo": "Ley del teletrabajo", "_ruta": "t.md"},
        "AMBAS": {"titulo": "Ley mixta", "_ruta": "m.md"},
        "PORCIENTO": {"titulo": "Ley del 50% y del guion_bajo", "_ruta": "p.md"},
    }
    cuerpos = {
        "ARRENDA": "Del arrendamiento urbano.",
        "TELE": "Del teletrabajo.",
        "AMBAS": "Del arrendamiento y del teletrabajo.",
        "PORCIENTO": "Otra materia.",
    }
    instalar_corpus("tst", documentos, cuerpos)


def ids(resultado):
    import mcp_legalize
    assert isinstance(resultado, (list, mcp_legalize.ErrorRespuesta)), resultado
    return sorted(r.id for r in resultado) if isinstance(resultado, list) else resultado.error


# Cada consulta lleva sintaxis de FTS5. Leída como texto, sus términos son los
# que extrae el tokenizador; leída como sintaxis, daría otra respuesta (la de
# la derecha), o un error del motor.
SINTAXIS_FTS = [
    ("arrendamiento AND urbano", []),                  # como operador: ["ARRENDA"]
    ("arrendamiento OR teletrabajo", ["AMBAS"]),       # como operador: los tres
    ("arrendamiento NOT urbano", []),                  # como operador: ["AMBAS"]
    ("arrend*", []),                                   # como prefijo: dos leyes
    ("NEAR(arrendamiento urbano)", []),                # como operador: ["ARRENDA"]
    ("texto:arrendamiento", []),                       # como columna: dos leyes
    ('"arrendamiento" "urbano"', ["ARRENDA"]),
    ('arrendamiento" OR "teletrabajo', ["AMBAS"]),
    ("(arrendamiento) )", ["AMBAS", "ARRENDA"]),
    ("arrendamiento ^urbano", ["ARRENDA"]),
]


@pytest.mark.parametrize("texto,esperado", SINTAXIS_FTS, ids=[t for t, _ in SINTAXIS_FTS])
def test_fts_syntax_in_texto_is_searched_as_text(con_texto, texto, esperado):
    """T016 / FR-006: nothing the client writes reaches the engine as syntax."""
    import mcp_legalize

    assert ids(mcp_legalize.buscar_ley.fn(pais="tst", texto=texto)) == esperado
    assert mcp_legalize.contar_leyes.fn(pais="tst", texto=texto).total == len(esperado)


@pytest.mark.parametrize("consulta,esperado", [
    ("50%", ["PORCIENTO"]),
    ("%", ["PORCIENTO"]),
    ("_", ["PORCIENTO"]),
    ('"', []),
    ("' OR 1=1 --", []),
    ("arrendamientos AND", []),
])
def test_a_title_query_is_a_literal_substring(con_texto, consulta, esperado):
    """`consulta` is a substring, with no wildcard and no SQL of its own."""
    import mcp_legalize

    assert ids(mcp_legalize.buscar_ley.fn(pais="tst", consulta=consulta)) == esperado


@pytest.mark.parametrize("termino", ["AND", "NEAR(", "x*", 'a"b', "texto:y", "(", ")", "^z", "OR NOT"])
def test_each_term_reaches_match_as_a_string(valida, termino):
    """Today the tokenizer only emits `[0-9a-zñ]{3,}` in lower case, which FTS5
    never reads as an operator, so the tools above would pass without quoting.
    Quoting is the second barrier: it must hold on its own if the term rule
    ever widens."""
    con = li.abrir(valida)

    con.execute("SELECT count(*) FROM cuerpo WHERE cuerpo MATCH ?", (li.terminos_fts([termino]),)).fetchone()
