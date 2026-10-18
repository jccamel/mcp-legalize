"""Tests for `legalize_postings`, the format of the inverted index (spec 001).

The inverted index used to be a pickle. The server called `pickle.load` on a
file its own comment described as untrusted input, so anyone who could write to
`indices/` got code execution on the first full-text query. Constitution
principle II forbids that: an untrusted file is never deserialised with a format
that can run code.

The replacement is a plain text file this project owns. Measured on the Spanish
corpus (research.md, R1) it also beats the pickle on every axis: 75.8 MB on disk
against 142.3, 0.16 s to load against 0.36, 176 MB resident against 394.

These tests pin three things:

- **The format round-trips** and its layout is the one in data-model.md, so the
  indexer and the server cannot drift apart (principle III).
- **Every malformed file is rejected as unreadable, never raised.** One corrupt
  file costs full-text search in that country and nothing else (principle IV).
- **The old `.bin` is recognised by its name and never opened.** Not opened
  "safely", not sniffed for a magic byte: never opened at all.
"""

import builtins
import pickle
import re
import sys
from pathlib import Path

import pytest

import legalize_postings as lp

HUELLA = "0123456789ab"
GEN = "f" * 32
OTRA_GEN = "e" * 32


def postings_de_prueba():
    return {
        "arrendamiento": {"ES-1", "ES-2"},
        "urbano": {"ES-2"},
        "rustico": {"ES-1", "ES-3"},
    }


def escribir_valido(directorio: Path, nombre: str = "tst", generacion: str = GEN):
    ruta = lp.ruta_postings(directorio, nombre)
    lp.escribir(ruta, postings_de_prueba(), tokenizador=HUELLA, generacion=generacion)
    return ruta


# ─────────────────────────────── round trip ──────────────────────────────────

def test_a_round_trip_keeps_every_term_and_its_documents(tmp_path):
    ruta = escribir_valido(tmp_path)

    leidos = lp.leer(ruta)

    for termino, docs in postings_de_prueba().items():
        assert leidos.docs(termino) == docs


def test_an_absent_term_has_no_documents(tmp_path):
    leidos = lp.leer(escribir_valido(tmp_path))

    assert leidos.docs("teletrabajo") == set()


def test_the_header_carries_the_stamps(tmp_path):
    leidos = lp.leer(escribir_valido(tmp_path))

    assert leidos.tokenizador == HUELLA
    assert leidos.generacion == GEN


def test_the_file_has_the_layout_the_data_model_describes(tmp_path):
    """Header, then the id table, then one line per term in lexicographic order.

    Pinned at the byte level because two writers of this format would be the
    drift principle III forbids: the layout is decided here, once.
    """
    lineas = escribir_valido(tmp_path).read_text(encoding="utf-8").split("\n")

    assert lineas[0] == "legalize-postings 1"
    assert lineas[1] == f"tokenizador {HUELLA}"
    assert lineas[2] == f"generacion {GEN}"
    assert lineas[3] == "documentos 3"
    assert lineas[4:7] == ["ES-1", "ES-2", "ES-3"]
    terminos = [l.split("\t")[0] for l in lineas[7:] if l]
    assert terminos == sorted(terminos) == ["arrendamiento", "rustico", "urbano"]


def test_lists_are_delta_encoded(tmp_path):
    """First value is the index itself; every following one is the gap, ≥ 1."""
    texto = escribir_valido(tmp_path).read_text(encoding="utf-8")

    assert "arrendamiento\t0,1\n" in texto   # ES-1 (0), ES-2 (0+1)
    assert "rustico\t0,2\n" in texto          # ES-1 (0), ES-3 (0+2)
    assert "urbano\t1\n" in texto             # ES-2 (1)


def test_the_same_content_is_written_byte_for_byte_the_same(tmp_path):
    """A file that changes when nothing real changed is noise for any freshness check."""
    a = escribir_valido(tmp_path / "a").read_bytes()
    b = escribir_valido(tmp_path / "b").read_bytes()

    assert a == b


def test_lists_are_not_decoded_until_a_term_is_queried(tmp_path, monkeypatch):
    """Lazy decoding is what keeps the load at 0.16 s on the Spanish corpus.

    Counted, not timed: the complaint would be "every list is decoded", not
    "this is slow" (CONTRIBUTING, "Do not assert on elapsed time").
    """
    decodificados = []
    original = lp.Postings._decodificar
    monkeypatch.setattr(lp.Postings, "_decodificar",
                        lambda self, t: decodificados.append(t) or original(self, t))

    leidos = lp.leer(escribir_valido(tmp_path))
    assert decodificados == []

    leidos.docs("urbano")
    assert decodificados == ["urbano"]


def test_a_document_id_with_a_line_break_cannot_be_written(tmp_path):
    """Ids are one per line. A newline in one would shift the whole table.

    Frontmatter ids cannot carry one, but the indexer derives ids from file
    paths when two documents claim the same identifier, and a file name can.
    """
    with pytest.raises(ValueError):
        lp.escribir(lp.ruta_postings(tmp_path, "tst"), {"termino": {"A\nB"}},
                    tokenizador=HUELLA, generacion=GEN)


def test_a_written_file_is_never_left_half_written(tmp_path):
    """Written beside the target and renamed into place, like the JSON index."""
    ruta = escribir_valido(tmp_path)

    assert [p.name for p in tmp_path.iterdir()] == [ruta.name]


# ───────────────────────── validation: unreadable files ──────────────────────

def _cabecera(n=3, tokenizador=HUELLA, generacion=GEN, firma="legalize-postings 1"):
    return f"{firma}\ntokenizador {tokenizador}\ngeneracion {generacion}\ndocumentos {n}\n"


IDS = "ES-1\nES-2\nES-3\n"

ESTRUCTURA_INVALIDA = {
    "wrong signature": _cabecera(firma="legalize-postings 2") + IDS + "ley\t0\n",
    "no signature": "tokenizador x\n" + IDS,
    "missing headers": "legalize-postings 1\ntokenizador " + HUELLA + "\n",
    "count not an integer": _cabecera(n="tres") + IDS,
    "negative count": _cabecera(n=-1) + IDS,
    "fewer ids than declared": _cabecera(n=5) + IDS,
    "an empty id": _cabecera() + "ES-1\n\nES-3\n",
    "term line without a tab": _cabecera() + IDS + "ley 0\n",
    "term outside the token pattern": _cabecera() + IDS + "Ley\t0\n",
    "term shorter than three": _cabecera() + IDS + "ab\t0\n",
    "repeated term": _cabecera() + IDS + "ley\t0\nley\t1\n",
    "malformed generation": _cabecera(generacion="xyz") + IDS,
    "empty file": "",
}


@pytest.mark.parametrize("contenido", ESTRUCTURA_INVALIDA.values(),
                         ids=ESTRUCTURA_INVALIDA.keys())
def test_a_structurally_broken_file_is_unreadable_not_an_exception(tmp_path, contenido):
    lp.ruta_postings(tmp_path, "tst").write_text(contenido, encoding="utf-8")

    postings, motivo = lp.estado(tmp_path, "tst", HUELLA, GEN)

    assert postings is None
    assert motivo == lp.ILEGIBLES


def test_arbitrary_binary_is_unreadable(tmp_path):
    lp.ruta_postings(tmp_path, "tst").write_bytes(bytes(range(256)) * 4)

    assert lp.estado(tmp_path, "tst", HUELLA, GEN) == (None, lp.ILEGIBLES)


DELTAS_INVALIDOS = {
    "not an integer": "ley\t0,x\n",
    "zero gap after the first": "ley\t0,0\n",
    "negative first": "ley\t-1\n",
    "negative gap": "ley\t1,-1\n",
    "first beyond the table": "ley\t3\n",
    "running sum beyond the table": "ley\t1,2\n",
    "empty list": "ley\t\n",
}


@pytest.mark.parametrize("linea", DELTAS_INVALIDOS.values(), ids=DELTAS_INVALIDOS.keys())
def test_a_corrupt_list_is_caught_when_decoded_and_marks_the_file_unreadable(tmp_path, linea):
    """Lists are decoded lazily, so a bad delta surfaces at query time.

    Validating every list at load would cost what decoding them all costs,
    which is what lazy decoding exists to avoid (data-model.md). What must hold
    is that the error is caught, and that the file stays unreadable afterwards
    instead of answering the next term as if nothing happened.
    """
    ruta = lp.ruta_postings(tmp_path, "tst")
    ruta.write_text(_cabecera() + IDS + linea + "otro\t0\n", encoding="utf-8")
    leidos = lp.leer(ruta)

    with pytest.raises(ValueError):
        leidos.docs("ley")
    assert leidos.motivo == lp.ILEGIBLES
    with pytest.raises(ValueError):
        leidos.docs("otro")


# ─────────────────────────────── availability ────────────────────────────────

def test_usable_postings_have_no_reason(tmp_path):
    escribir_valido(tmp_path)

    postings, motivo = lp.estado(tmp_path, "tst", HUELLA, GEN)

    assert motivo is None
    assert postings.docs("urbano") == {"ES-2"}


def test_no_file_at_all(tmp_path):
    assert lp.estado(tmp_path, "tst", HUELLA, GEN) == (None, lp.SIN_POSTINGS)


def test_a_different_tokenizer(tmp_path):
    escribir_valido(tmp_path)

    assert lp.estado(tmp_path, "tst", "ba9876543210", GEN) == (None, lp.TOKENIZADOR_DISTINTO)


def test_a_different_generation(tmp_path):
    escribir_valido(tmp_path)

    assert lp.estado(tmp_path, "tst", HUELLA, OTRA_GEN) == (None, lp.GENERACION_DISTINTA)


def test_a_json_without_a_generation_never_matches(tmp_path):
    """The indexer leaves it out when writing the postings failed (FR-015)."""
    escribir_valido(tmp_path)

    assert lp.estado(tmp_path, "tst", HUELLA, None) == (None, lp.GENERACION_DISTINTA)


def test_reasons_are_evaluated_in_the_documented_order(tmp_path):
    """Unreadable beats a stamp mismatch: a broken file has no stamps to compare."""
    lp.ruta_postings(tmp_path, "tst").write_text("basura", encoding="utf-8")

    assert lp.estado(tmp_path, "tst", "otra", None)[1] == lp.ILEGIBLES


def test_the_reasons_are_exactly_the_contracted_ones():
    assert lp.MOTIVOS == (
        "formato_anterior", "sin_postings", "ilegibles",
        "tokenizador_distinto", "generacion_distinta",
    )


# ───────────────────────── the old format is never opened ────────────────────

class _Centinela:
    """Unpickling this creates a file. If the file exists, code ran."""

    def __init__(self, ruta):
        self.ruta = str(ruta)

    def __reduce__(self):
        return (Path(self.ruta).touch, ())


def test_an_old_bin_is_recognised_without_being_opened(tmp_path, monkeypatch):
    centinela = tmp_path / "pwned"
    viejo = lp.ruta_formato_anterior(tmp_path, "tst")
    viejo.write_bytes(pickle.dumps(_Centinela(centinela)))

    abiertos = []
    open_original, path_open_original = builtins.open, Path.open

    def vigilar(ruta):
        if Path(ruta).resolve() == viejo.resolve():
            abiertos.append(ruta)
            raise AssertionError("the old .bin was opened")

    def open_vigilado(file, *a, **k):
        if isinstance(file, (str, Path)):
            vigilar(file)
        return open_original(file, *a, **k)

    def path_open_vigilado(self, *a, **k):
        vigilar(self)
        return path_open_original(self, *a, **k)

    monkeypatch.setattr(builtins, "open", open_vigilado)
    monkeypatch.setattr(Path, "open", path_open_vigilado)

    resultado = lp.estado(tmp_path, "tst", HUELLA, GEN)

    assert resultado == (None, lp.FORMATO_ANTERIOR)
    assert abiertos == []
    assert not centinela.exists()


def test_a_current_file_wins_over_a_leftover_bin(tmp_path):
    """Once reindexed the .bin is deleted, but if one survives it changes nothing."""
    lp.ruta_formato_anterior(tmp_path, "tst").write_bytes(b"\x80\x05 cualquier cosa")
    escribir_valido(tmp_path)

    assert lp.estado(tmp_path, "tst", HUELLA, GEN)[1] is None


def test_the_module_cannot_unpickle_and_does_not_reach_the_server():
    """No `pickle` to misuse, and no import of `mcp_legalize`.

    Importing the server from here would repeat the cycle that used to load it
    twice when run as a script (#9 of the review); the tokenizer fingerprint is
    passed in as an argument instead.

    `legalize_tokenizer` used to be forbidden too, for the same cycle. Since #48
    the tokenizer no longer imports the server, and the format now validates
    terms with the tokenizer's own pattern instead of a copy that diverged
    (ADR 0008), so that import is allowed.
    """
    fuente = Path(lp.__file__).read_text(encoding="utf-8")

    importados = set(re.findall(r"^\s*(?:import|from)\s+([\w.]+)", fuente, re.MULTILINE))
    assert "pickle" not in importados
    assert "mcp_legalize" not in importados


def test_a_new_generation_is_32_hex_and_not_repeated():
    a, b = lp.nueva_generacion(), lp.nueva_generacion()

    assert re.fullmatch(r"[0-9a-f]{32}", a)
    assert a != b
