# Implementation Plan: Confianza en el índice

**Branch**: `docs/001-confianza-indice` | **Date**: 2026-10-16 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/001-confianza-indice/spec.md`

## Summary

El servidor y el indexador confían en el índice más de lo que permite su modelo de amenaza. El
plan hace cinco cambios:

- **Postings en otro formato** ([R1](research.md#r1--formato-de-los-postings-fr-007-fr-008-sc-007)):
  los postings pasan de pickle a un formato de texto propio (`.postings`) que no puede ejecutar
  código. Ocupa la mitad de disco y de memoria y carga en la mitad de tiempo.
- **Pasadas incrementales coherentes** ([R2](research.md#r2--postings-coherentes-en-una-pasada-incremental-fr-001-a-fr-003-sc-006)):
  el indexador fusiona los postings previos en lugar de reescribirlos solo con los documentos de
  la pasada. Si no son utilizables, los reconstruye.
- **Par JSON y postings atado** ([R3](research.md#r3--generación-del-par-jsonpostings-fr-009-casos-límite)):
  una `generacion` común vincula los dos ficheros, y los sellos solo se escriben si los postings
  se escribieron de verdad.
- **Raíz decidida por el operador** ([R5](research.md#r5--directorio-autorizado-fr-004-a-fr-006-q1)):
  la raíz de los documentos ya no sale del índice, sino de `LEGALIZE_REPOS_DIR`.
- **Señal de "no se pudo buscar"** ([contrato](contracts/herramientas-mcp.md)): `contar_leyes`
  informa siempre de los países que no pudo consultar y por qué, y `buscar_ley` conserva su
  lista.

Un módulo nuevo, `legalize_postings.py`, es la única fuente de verdad del formato y de su
disponibilidad.

## Technical Context

**Language/Version**: Python ≥ 3.10 (CI de 3.10 a 3.13; medido en 3.14.8)

**Primary Dependencies**: `fastmcp`, `pydantic`. Ninguna nueva: el formato usa solo la
biblioteca estándar.

**Storage**: ficheros en `indices/`: `index_<repo>.json` y `inverted_<repo>.postings`, este
último en lugar de `inverted_<repo>.bin`.

**Testing**: pytest (385 tests hoy). Corpus sintéticos en `tmp_path` y el mock versionado.

**Target Platform**: servidor MCP por stdio en macOS, Linux y Windows. La CI corre en Linux.

**Project Type**: servidor MCP más dos scripts de operador. Módulos sueltos en la raíz, sin
empaquetado.

**Performance Goals**:

- SC-006: una pasada incremental que modifique hasta el 5% de ES tarda ≤ 20 s (hoy, 133,6 s el
  completo y 2,75 s el incremental defectuoso).
- SC-007: arrancar sin búsquedas no carga postings. La primera búsqueda por texto en ES carga en
  ≤ 0,36 s, lo mismo que el pickle actual (el formato elegido midió 0,16 s).

**Constraints**:

- Ninguna lectura de un fichero no confiable puede ejecutar código.
- stdout está reservado a JSON-RPC.
- El pico de RSS del indexado completo de ES (4,4 GB) no puede empeorar.

**Scale/Scope**: ES tiene 25.889 documentos, 560.577 términos y 28 M de postings; SE, 8.990
documentos y 146.151 términos.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principio | Evaluación | Estado |
|---|---|---|
| I. Fidelidad a la fuente | Ningún cambio toca el texto ni los metadatos servidos (FR-017). Un resultado parcial pasa a ser distinguible (`sin_consultar`) | ✅ |
| II. Corpus e índice no confiables | La raíz sale del entorno y no del índice. Los postings no pueden ejecutar código. El `.bin` ni siquiera se abre | ✅ Es el objeto de la feature |
| III. Una sola fuente de verdad | `legalize_postings.py` es el único que escribe, lee y diagnostica. `buscar_ley` y `contar_leyes` comparten `_filtrar_docs`, y también la disponibilidad | ✅ |
| IV. Degradar sin silencio | Unos postings inutilizables cuestan la búsqueda por texto de ese país, y se dice. Un índice fuera de la raíz cuesta ese índice, y se avisa | ✅ |
| V. Test primero, visto fallar | Cada tarea empieza por el test que reproduce el defecto (los cinco ya se reprodujeron a mano). Los cambios a tests existentes se listan abajo | ✅ Ver «Cambios en tests existentes» |
| VI. Medir antes de fijar | Todos los números del plan salen de research.md, medidos hoy contra ES y SE | ✅ |
| VII. Sellos derivados que invalidan | `generacion` y `tokenizador` invalidan de verdad: fuerzan la reconstrucción, y el remedio propuesto la resuelve | ✅ |
| Restricciones técnicas | Sin dependencias nuevas. Variable nueva documentada y comprobada por `test_config_docs.py` | ✅ |
| Flujo | ADR 0007 sustituye al 0003 | ✅ Tarea incluida |

**Re-check post-diseño**: sin violaciones. No hace falta rellenar Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/001-confianza-indice/
├── spec.md
├── plan.md              # este fichero
├── research.md          # R1–R6, con las mediciones
├── data-model.md        # formato .postings, _meta, estados y transiciones
├── quickstart.md        # validación de punta a punta por historia
├── contracts/
│   ├── herramientas-mcp.md
│   └── operador.md
├── checklists/requirements.md
└── tasks.md             # lo genera /speckit-tasks
```

### Source Code (repository root)

```text
legalize_postings.py         # NUEVO: escribir, leer, validar y estado() con motivo
mcp_legalize.py              # LEGALIZE_REPOS_DIR, _RAIZ_POR_PAIS, carga vía legalize_postings,
                             # Conteo.sin_consultar, señal en buscar_ley, instrucciones
scripts/update_index.py      # fusión/reconstrucción, generacion, orden de escritura, borra .bin
scripts/check_updates.py     # estado POSTINGS vía legalize_postings.estado
legalize_tokenizer.py        # sin cambios de reglas (la huella no cambia)
indices/index_legalize-mock.json      # regenerado (generacion, tokenizador)
indices/inverted_legalize-mock.postings  # NUEVO, versionado junto al JSON del mock
.gitignore                   # excepción para el .postings del mock
README.md                    # Configuration, Mitigations, Index provenance, Limitations
CONTRIBUTING.md              # nada, salvo que cambie algún comando
docs/decisiones/0007-*.md    # NUEVO, sustituye a 0003; actualizar 0003 e índice

tests/test_postings_format.py          # NUEVO: formato, validación, motivos, no ejecuta código
tests/test_incremental_postings.py     # NUEVO: historia 1 y 5 de punta a punta con el indexador
tests/test_repos_dir.py                # NUEVO: historia 2 a través de las herramientas
tests/test_text_search_availability.py # NUEVO: historia 4 (buscar_ley + contar_leyes)
tests/test_full_text_search.py         # adaptado (ver abajo)
tests/test_contar_leyes.py             # adaptado (ver abajo)
tests/test_inverted_index.py           # adaptado (ver abajo)
tests/test_resolve_ruta.py             # adaptado (ver abajo)
```

**Structure Decision**: se mantiene la estructura plana del proyecto (módulos sueltos en la
raíz) y se añade un único módulo, como ya se hizo con `legalize_frontmatter`,
`legalize_injection` y `legalize_tokenizer`.

## Cambios en tests existentes

Por el principio V y `CLAUDE.md`, ningún test existente cambia sin decirlo.

| Test | Cambio | Motivo | Aprobación |
|---|---|---|---|
| `test_full_text_search.py::test_a_country_without_an_inverted_index_degrades_to_no_results` | Pasa a esperar `ErrorRespuesta` que nombra el país, y su docstring explica el cambio | FR-010 y Q3: `[]` era indistinguible de "sin coincidencias" | ✅ Aprobado por el usuario el 2026-10-16 |
| `test_full_text_search.py::test_a_corrupt_inverted_index_degrades_instead_of_raising` | Ídem, con motivo `ilegibles`; se mantiene que no lanza excepción | FR-008 y FR-010 | ✅ Aprobado por el usuario el 2026-10-16 |
| Fixtures `corpus` de `test_full_text_search.py` y `test_contar_leyes.py` | Escriben `.postings` con `legalize_postings.escribir`, el sello real del tokenizador y la generación en `_meta` | Hoy escriben pickle con el sello falso `cafe12345678`, que FR-009 declara no utilizable. El comportamiento que prueban no cambia | Pendiente: forma parte de aprobar este plan |
| `test_inverted_index.py::leer_invertido` y los tests de nombre de fichero | Leen con `legalize_postings.leer` y esperan `.postings` | R1 y R4: cambian el formato y el nombre | Pendiente: forma parte de aprobar este plan |
| Fixture `repo_root` de `test_resolve_ruta.py` | Fija también `LEGALIZE_REPOS_DIR` y `_RAIZ_POR_PAIS` en `tmp_path` | R5: la raíz deja de leerse de `_meta`. Los asserts no cambian | Pendiente: forma parte de aprobar este plan |

Todo lo demás en estos ficheros se queda como está, y los tests que ya pasan deben seguir pasando
sin tocarlos.

## Orden de implementación

Cada paso es una PR o un commit que funciona por sí solo y sigue la disciplina rojo → verde:

1. **`legalize_postings.py`** con su test de formato y validación. Nadie lo usa todavía.
2. **Historia 3 + R4** (P1): el servidor lee `.postings` mediante el módulo y nunca abre un
   `.bin`; el indexador escribe `.postings` y borra el `.bin`. Se adaptan los fixtures.
3. **Historia 1 + R3** (P1): generación, fusión y reconstrucción, y el orden de escritura.
4. **Historia 2 + R5** (P1): `LEGALIZE_REPOS_DIR` y `_RAIZ_POR_PAIS`; la documentación de la
   variable entra en el mismo commit por `test_config_docs.py`.
5. **Historia 4** (P2): `Conteo.sin_consultar` y la señal en `buscar_ley`. Se cambian los dos
   tests aprobados y las instrucciones del servidor.
6. **Historia 5** (P2): el tokenizador fuerza la reconstrucción, el sello solo se escribe con
   los postings y `check_updates.py` gana el estado `POSTINGS`.
7. **Cierre**: regenerar los índices del mock, escribir el ADR 0007, actualizar el README,
   recorrer el quickstart contra ES y SE y comprobar SC-006 y SC-007 con medición.

Al terminar, recuérdame ejecutar `/security-review`: el cambio toca rutas, el índice y lo que se
devuelve al modelo.

## Complexity Tracking

Sin violaciones de la constitución que justificar.
