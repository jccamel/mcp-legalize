# Implementation Plan: Índice en una base de datos por corpus

**Branch**: `feat/002-indice-sqlite` | **Date**: 2026-10-18 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/002-indice-sqlite/spec.md`

## Summary

Se sustituyen el índice JSON en memoria y los postings de formato propio por una base de datos
SQLite con FTS5 por corpus. La escribe y la lee solo un módulo nuevo, `legalize_indice.py`.

- **Contrato**: el de las siete herramientas se mantiene, y lo comprueba un banco de paridad
  contra `main` sobre ES, SE, FR y EU.
- **Construcción**: el índice se construye en un temporal y se sustituye entero. Eso elimina
  la fusión de postings, la generación y el orden de escritura.
- **Seguridad**: la base de datos se abre en solo lectura, con modo defensivo y con su esquema
  comprobado contra una lista blanca, antes de hacerle ninguna consulta.
- **Artículos**: se localizan al indexar con las mismas reglas de hoy, y eso habilita
  `capitulo` y `ubicaciones` (Q2).
- **Funciones nuevas**: un parámetro opcional `frase` (Q1).
- **Python**: el suelo sube a 3.12. El ADR 0009 sustituye a los ADR 0003 y 0007.

## Technical Context

**Language/Version**: Python ≥ 3.12. Lo exige `Connection.setconfig` para el modo defensivo.

**Primary Dependencies**: `fastmcp` y `pydantic`, como hoy. `sqlite3` es de la biblioteca
estándar: **ninguna dependencia nueva**.

**Storage**: `indices/index_<repo>.db`, un fichero por corpus ([data-model.md](data-model.md)).

**Testing**: pytest, 576 tests hoy. Las bases de datos de prueba se construyen con el mismo
escritor que usa el indexador (research R10).

**Target Platform**: servidor MCP por stdio. La CI corre en Linux. En Windows, el riesgo de
`os.replace` está anotado (research R1).

**Performance Goals**: los de la spec (SC-002 a SC-004 y SC-007). La prueba de concepto ya
los supera: 0,2 ms de arranque, 27 MB, consultas por debajo de 1 ms.

**Constraints**:

- El indexado completo de ES no puede pasar de 150 s ni de 4,15 GB.
- El tamaño en disco queda registrado: unos 474 MB en ES con búsqueda por frase.

**Scale/Scope**: cuatro corpus locales con 53.568 leyes. Solo ES tiene 406.686 artículos
localizados.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principio | Evaluación | Estado |
|---|---|---|
| I. Fidelidad | Banco de paridad contra `main`; las diferencias deliberadas, enumeradas en el contrato. `estado_texto`, `texto_truncado` y `sin_consultar` se conservan | ✅ |
| II. Índice no confiable | Solo lectura, modo defensivo, `trusted_schema=OFF`, `query_only`, lista blanca del esquema antes de consultar; ningún valor del cliente concatenado en SQL ni como sintaxis de FTS5 | ✅ Es el centro del diseño |
| III. Una sola fuente | `legalize_indice.py` escribe, abre, valida y consulta; un solo constructor de `WHERE` para buscar y contar; el plegado y los términos siguen en sus módulos | ✅ |
| IV. Degradar sin silencio | Una base de datos mala cuesta su corpus, con motivo; el formato anterior se informa como `FORMATO` | ✅ |
| V. Test primero | Cada paso empieza con su test en rojo; los cambios a tests existentes se listan abajo | ✅ Ver tabla |
| VI. Medir | Todas las cifras vienen de la prueba de concepto; las que faltan, marcadas «a medir»; SC-007 se vuelve a medir | ✅ |
| VII. Sellos que invalidan | Las huellas del escáner y del tokenizador y el formato van en `meta`, y fuerzan la reconstrucción como hoy | ✅ |
| Restricciones técnicas | Sin dependencias nuevas; suelo de Python 3.12 aceptado explícitamente por el usuario | ✅ |
| Flujo | ADR 0009 sustituye a 0003 y 0007; spec con spec-kit | ✅ |

**Re-check post-diseño**: sin violaciones.

## Project Structure

### Documentation (this feature)

```text
specs/002-indice-sqlite/
├── spec.md · plan.md · research.md · data-model.md · quickstart.md
├── contracts/herramientas-mcp.md · contracts/operador.md
├── checklists/requirements.md
└── tasks.md            # /speckit-tasks
```

### Source Code (repository root)

```text
legalize_indice.py          # NUEVO: esquema, escritor, abrir() seguro, consultas, como_dict()
legalize_postings.py        # SE RETIRA (su formato lo sustituye la base de datos)
mcp_legalize.py             # la capa de consulta pasa a legalize_indice; frase, capitulo, ubicaciones
scripts/update_index.py     # escribe la base de datos (temporal + os.replace); retira el JSON
scripts/check_updates.py    # lee meta de la base de datos; estado FORMATO, adiós POSTINGS
indices/index_legalize-mock.db   # sustituye al JSON y los postings versionados del mock
.github/workflows/ci.yml    # matriz desde 3.12
README.md, CONTRIBUTING.md, docs/decisiones/0009-*.md (sustituye a 0003 y 0007)
tests/conftest.py           # instalar_corpus(): bases de datos reales para los tests
tests/test_indice_*.py      # NUEVOS: formato, seguridad, paridad, frase, capitulo
```

**Structure Decision**: se mantiene la estructura plana. Igual que `legalize_postings` en su
día, el módulo nuevo concentra todo el conocimiento del formato.

## Cambios en tests existentes

Por el principio V, ninguno cambia sin decirlo. Aprobar el plan los aprueba.

| Grupo | Ficheros | Cambio | Asserts |
|---|---|---|---|
| **Fixture** | `test_error_contract`, `test_contar_leyes`, `test_full_text_search`, `test_search_filters`, `test_fechas_hasta`, `test_resolve_ley_mayusculas`, `test_plegado`, `test_estado_del_texto` (parte del servidor), `test_articulo_*` (4), `test_bytes_degradation`, `test_value_passthrough`, `test_config_docs`, `test_resolve_ruta`, `test_repos_dir` | La inyección en `_DOCS_POR_PAIS` / `_read_file` pasa a `instalar_corpus(...)`, o a ficheros `.db` en lugar de JSON en `test_repos_dir` | **Sin cambios** |
| **Lectura del índice generado** | `test_ruleset_stamp`, `test_repo_identity`, `test_docid_collision`, `test_metadata_scan`, `test_metadata_length`, `test_frontmatter`, `test_estado_del_texto` (parte del indexador), `test_incremental_postings`, `test_carga_unica` | `json.loads(indice)` pasa a `legalize_indice.como_dict(indice)`, que devuelve la misma forma | **Sin cambios** |
| **Motivos del contrato** | `test_text_search_availability` | `MOTIVOS_DEL_CONTRATO` pierde `formato_anterior` y `generacion_distinta` | Cambia ese conjunto (diferencia deliberada del contrato) |
| **Objeto retirado → sustituido** | `test_postings_format`, `test_inverted_index` (la parte de postings), `test_index_shape`, `test_search_normalization_cache` | Prueban un formato o una caché que desaparecen. Se sustituyen por sus equivalentes sobre la base de datos: `test_indice_formato` (lista blanca, tipos, motivos), seguridad con `.db` manipulados, la forma del índice como validación de esquema, y el plegado al indexar en lugar de la caché | Los **invariantes** se conservan; cambia el objeto |
| **Contrato de `check_updates`** | `test_inverted_index` (estados) | `POSTINGS` pasa a ser `FORMATO` en el ciclo «estado caducado → remedio → limpio» | Cambia el nombre del estado |

El test del enlace simbólico y los dos tests de Windows se mantienen tal cual.

## Orden de implementación

Cada paso es un commit (o una PR) que funciona y sigue el ciclo rojo → verde:

1. **Referencia de paridad**: script del banco y respuestas de `main` sobre ES, SE, FR y EU,
   guardadas fuera del repo (quickstart §2).
2. **`legalize_indice.py`**: esquema, escritor, `abrir()` con lista blanca, `como_dict()`.
   Tests de formato y de seguridad con bases de datos manipuladas.
3. **Indexador**: escribe la base de datos con temporal y `os.replace`, en pasada completa o
   incremental; retira el formato anterior; `check_updates` con `FORMATO`. Migran los tests
   del grupo «lectura del índice generado».
4. **Servidor**: la capa de consulta pasa a `legalize_indice`. Migran los tests del grupo
   «fixture». Paridad sobre los cuatro corpus.
5. **Artículos preparados**: filas y paridad con `_localizar_articulo`, y después `capitulo` y
   `ubicaciones` (Q2).
6. **`frase`** (Q1).
7. **Cierre**: Python 3.12 en la CI, índice del mock en `.db`, retirada de
   `legalize_postings`, ADR 0009, README, CONTRIBUTING y medición final (SC-002 a SC-008).

Al terminar, recordar ejecutar `/security-review`: el cambio toca el formato del índice y su
apertura.

## Complexity Tracking

Sin violaciones de la constitución.
