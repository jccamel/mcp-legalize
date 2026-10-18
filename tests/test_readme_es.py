"""Tests that the Spanish README states the same checkable facts as the English one.

`README.md` is pinned against the code by `test_readme_claims`, `test_config_docs`
and `test_value_passthrough`. `README.es.md` is a translation of it, and a
translation nobody checks drifts the same way the English page did before those
tests existed. These do not check the prose; they check that every name a reader
acts on — tools, variables and their defaults, values the server returns, states
`check_updates` reports — appears in both versions, and that each links to the
other.
"""

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
INGLES = (RAIZ / "README.md").read_text(encoding="utf-8")
CASTELLANO = (RAIZ / "README.es.md").read_text(encoding="utf-8")

# Lo que un lector usa tal cual: si falta o cambia en una versión, esa versión
# miente. Los nombres salen del README inglés, que ya está atado al código.
HERRAMIENTAS = ["listar_paises", "buscar_ley", "contar_leyes", "obtener_ley",
                "obtener_articulo", "listar_rangos", "estadisticas"]
VALORES = ["in_force", "repealed", "expired", "annulled",
           "point_in_time", "current", "as_enacted"]
ESTADOS_CHECK = ["DESACTUAL", "REGLAS", "TOKENS", "FORMATO", "RAÍZ"]
CAMPOS_SEGURIDAD = ["escaneado_en", "patrones", "cuarentena", "forzados", "avisos"]


@pytest.mark.parametrize("nombre", HERRAMIENTAS + VALORES + ESTADOS_CHECK + CAMPOS_SEGURIDAD)
def test_both_versions_name_it(nombre):
    assert f"`{nombre}`" in INGLES
    assert f"`{nombre}`" in CASTELLANO


def test_both_versions_list_the_same_variables_with_the_same_defaults():
    def variables(texto):
        return dict(re.findall(r"\| `(LEGALIZE_[A-Z_]+)` \| `([^`]+)` \|", texto))

    assert variables(CASTELLANO) == variables(INGLES)
    assert len(variables(INGLES)) == 5


def test_both_versions_show_the_same_badges():
    def cabecera(texto):
        return re.findall(r"\[!\[[^\]]*\]\([^)]+\)\]", texto[:texto.index("\n---\n")])

    assert cabecera(CASTELLANO) == cabecera(INGLES)


def test_each_version_links_to_the_other():
    assert "(README.es.md)" in INGLES
    assert "(README.md)" in CASTELLANO


def test_both_versions_have_the_seven_mitigations():
    def mitigaciones(texto):
        return re.findall(r"^#### (\d)\. ", texto, re.MULTILINE)

    assert mitigaciones(CASTELLANO) == mitigaciones(INGLES) == list("1234567")
