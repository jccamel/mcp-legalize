---

description: "Task list for specs/002-indice-sqlite"
---

# Tasks: Índice en una base de datos por corpus

**Input**: Design documents from `specs/002-indice-sqlite/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/)

**Tests**: OBLIGATORIOS (constitución, principio V). Cada test nuevo se escribe antes que el
código, se ejecuta y se ve fallar por el motivo correcto, y el fallo se anota en el commit.

**Organization**: el orden sigue las dependencias reales. La referencia de paridad tiene que
existir antes de tocar nada. El módulo de índice y la construcción completa son la base de
todas las historias. Después vienen US2 (seguridad), US1 (paridad del servidor), US4
(mantenimiento), US5 (artículos) y US3 (frase).

## Format: `[ID] [P?] [Story] Description`

## Reglas comunes

- Comentarios del código en español con tildes; docstrings de `tests/` en inglés.
- Asserts en el punto de llamada (herramientas `.fn`, scripts).
- Ningún assert de tiempo.
- Commits *conventional* con cuerpo que explique el porqué y sin atribución a IA. El
  pre-commit ejecuta la suite.
- Un test existente solo cambia como autoriza la tabla «Cambios en tests existentes» de
  [plan.md](plan.md).
- **Ningún valor del cliente se concatena en SQL ni llega a FTS5 como sintaxis** (FR-006).

---

## Phase 1: Setup

- [X] T001 Ejecutar `.venv/bin/python -m pytest -rs` y `scripts/update_index.py --self-test`
  en `main`. Anotar la línea base (hoy 576 tests, 2 skips) en la sección Notes de
  `specs/002-indice-sqlite/tasks.md`.
- [X] T002 Crear el script del banco de paridad
  `specs/002-indice-sqlite/paridad/banco.py`. Recibe un directorio de índices y una salida
  JSON, y ejecuta por corpus (es, se, fr, eu) una lista fija de peticiones con sus respuestas
  completas vía `model_dump()`:
  - `listar_paises`, `listar_rangos` y `estadisticas`;
  - `buscar_ley` y `contar_leyes` con `consulta`, `texto`, `rango`, `estado`, `anno`,
    `fecha_desde`/`fecha_hasta` (`YYYY` y `YYYY-MM`), `derogada_*`, `actualizada_*`,
    `departamento`, `limite` y `offset`;
  - `obtener_ley` con `solo_metadata` y con texto, sobre 20 ids por corpus, incluidos ids en
    minúsculas;
  - `obtener_articulo` sobre 200 pares (ley, número) por corpus, tomados con semilla fija de
    los encabezados de artículo, más 20 números inexistentes y prefijos (`L110`);
  - los errores: país desconocido, ley inexistente, id ambiguo.

  Determinista y sin dependencias nuevas.
- [X] T003 Generar la referencia: crear un worktree de `main` en el scratchpad, ejecutar
  `banco.py` contra `indices/` con el código de `main` y guardar
  `specs/002-indice-sqlite/paridad/referencia-main.json`. Si pasa de 5 MB, se guarda fuera del
  repo y se registran solo el resumen y su sha256. Anotar el commit de `main` y el de cada
  corpus en Notes.

---

## Phase 2: Foundational

**Purpose**: `legalize_indice.py` con su esquema, su escritor, la apertura segura y
`como_dict`; el indexador construyendo la base de datos completa; y el ayudante de tests.

**⚠️ CRITICAL**: ninguna historia empieza antes.

### Tests (en rojo primero)

- [X] T004 Crear `tests/test_indice_formato.py`:
  - escribir con `legalize_indice` un corpus de 3 leyes (con artículos y cuerpo) y leerlo con
    `abrir()` y `como_dict()`;
  - `como_dict` devuelve `{"_meta": {...}, "documentos": {id: {...}}}` con las claves que
    tenía el JSON: `titulo`, `identificador`, `pais`, `rango`, `estado`, `fecha_publicacion`,
    `ultima_actualizacion`, `fuente`, `_ruta`, `_bytes`, `_mtime`, `estado_texto`,
    `ultima_modificacion`, `jurisdiccion`, `departamento`, `fecha_derogacion`,
    `derogado_por`, y `_meta.seguridad` con sus siete claves;
  - columnas «`NOT NULL`, con `''` como valor ausente»;
  - `id` único «`COLLATE NOCASE`»;
  - `estado_texto` resuelto a `point_in_time` si falta.
- [X] T005 [P] En `tests/test_indice_formato.py`, el esquema de `sqlite_master` es exactamente
  el SQL canónico de [data-model.md](data-model.md), y `meta.formato` es el vigente.

### Implementación

- [X] T006 Crear `legalize_indice.py`. Docstring en español con el porqué (research R1–R7).
  Contiene:
  - `ESQUEMA`, el SQL canónico, que es también la lista blanca;
  - `FORMATO = "1"`;
  - `ruta_indice(directorio, nombre)`;
  - `class Escritor`: abre un temporal en el mismo directorio y ofrece
    `poner_ley(id, campos, cuerpo)`, que inserta en `leyes`, en `cuerpo` (con
    `legalize_normalizacion.normalizar`) y en `articulos`;
  - `quitar_ley(id)`, `poner_meta(clave, valor)` y `confirmar()`: transacción, `optimize`
    de FTS5, `VACUUM` y `os.replace`. Si algo falla, el temporal se borra;
  - `como_dict(ruta)`.

  Solo usa la biblioteca estándar, `legalize_normalizacion` y `legalize_tokenizer`. No
  importa `pickle` ni `mcp_legalize`.
- [X] T007 En `legalize_indice.py`, implementar `localizar_articulos(cuerpo)`: una pasada
  lineal por los encabezados Markdown con las plantillas del servidor
  (`_ARTICULO_EN_ENCABEZADO_TEMPLATE`, `_CUALQUIER_NUMERO`, terminación `(?![\w*-])`) y su
  regla de final (siguiente encabezado de nivel ≤ o con otro artículo). Devuelve
  `(orden, numero, ubicacion, inicio, fin)`. La ubicación es la cadena de encabezados de
  nivel superior que lo contienen, unidos con « › », con « (2) » si hay empate. Las
  plantillas pasan de `mcp_legalize` a este módulo (principio III), y `mcp_legalize` las
  importa de aquí.
- [X] T008 Implementar `legalize_indice.abrir(ruta)`:
  - URI `mode=ro`;
  - `setconfig(SQLITE_DBCONFIG_DEFENSIVE, True)`, y si falta `setconfig`, `ValueError`;
  - `PRAGMA trusted_schema=OFF`, `query_only=ON` y `cell_size_check=ON`;
  - comparación de `sqlite_master` con `ESQUEMA`;
  - comprobación de `meta.formato`.

  Devuelve la conexión o lanza `ValueError` con el motivo (`ilegible`, `esquema_inesperado` o
  `formato_distinto`). Sin `enable_load_extension`.
- [X] T009 Ejecutar T004–T005 (en verde). Commit
  `feat: add legalize_indice, the per-corpus database the index moves to`.

### Indexador: construcción completa (base de US1 y US4)

- [X] T010 Hacer que `scripts/update_index.py` escriba `index_<repo>.db` con
  `legalize_indice.Escritor`, en lugar del JSON y el `.postings`:
  - la pasada completa, con el escáner, la cuarentena, los duplicados, el truncado de
    metadatos y el registro de seguridad de hoy (en `meta.seguridad` como JSON);
  - las huellas `patrones` y `tokenizador`, y `directorio_base`, `pais_predeterminado`,
    `git_commit` y `generado_en`.

  En esta tarea, cualquier pasada es completa; la incremental llega en US4.
- [X] T011 Migrar los tests del grupo «Lectura del índice generado» de [plan.md](plan.md):
  - `test_ruleset_stamp`, `test_repo_identity`, `test_docid_collision`,
    `test_metadata_scan`, `test_metadata_length` y `test_frontmatter`;
  - la parte del indexador de `test_estado_del_texto`, `test_incremental_postings` y
    `test_carga_unica`.

  Cambio único: `json.loads(indice.read_text())` pasa a `legalize_indice.como_dict(indice)`,
  y la ruta del índice pasa a `.db`. Los asserts no cambian.
- [X] T012 Añadir a `tests/conftest.py` el fixture `instalar_corpus(pais, documentos,
  cuerpos=None)`. Escribe una base de datos real en `tmp_path` con `legalize_indice.Escritor`,
  crea los ficheros del cuerpo bajo un `LEGALIZE_REPOS_DIR` temporal y la registra en el
  servidor por la vía de carga normal.
- [X] T013 Ejecutar la suite: solo pueden fallar los tests del servidor, que aún leen de
  memoria. Commit `feat(index): write the per-corpus database instead of JSON and postings`.

**Checkpoint**: el indexador produce bases de datos válidas; el servidor aún no las lee.

---

## Phase 3: User Story 2 - El índice sigue siendo entrada no confiable (Priority: P1)

**Goal**: abrir y consultar una base de datos manipulada no tiene efectos fuera del proceso
(FR-004 a FR-006).

**Independent Test**: el banco de bases de datos manipuladas del quickstart §4.

- [X] T014 [P] [US2] Crear `tests/test_indice_seguridad.py`. Por cada caso, `abrir()` da
  `ValueError` con su motivo y ningún efecto, comprobado con un centinela en `tmp_path`:
  - disparador `AFTER INSERT`;
  - vista;
  - tabla de más;
  - `leyes` con otro SQL;
  - fichero truncado;
  - fichero que no es SQLite;
  - `meta.formato` distinto;
  - un intento de `fts3_tokenizer` registrado en el esquema;
  - escritura con la conexión abierta: debe fallar por `query_only`.
- [X] T015 [P] [US2] En `tests/test_indice_seguridad.py`, un test con `abrir` parcheado para
  simular un Python sin `setconfig`: el servidor no sirve ningún índice y avisa con
  `[SEGURIDAD]`.
- [X] T016 [P] [US2] En `tests/test_indice_seguridad.py`, un test con texto del cliente que
  contiene sintaxis de FTS5 (`"`, `AND`, `NEAR(`, `*`, `(`, `)`, `col:valor`) en `texto`,
  `consulta` y `frase`: ninguna llamada lanza un error del motor, y el resultado equivale a
  buscar ese texto literal.
- [X] T017 [US2] Completar en `legalize_indice.abrir` lo que T014–T016 exijan y no estuviera
  en T008. Commit `fix(security): open the index database as untrusted input`.

---

## Phase 4: User Story 1 - El cliente no nota el cambio (Priority: P1) 🎯 MVP

**Goal**: el servidor lee de las bases de datos, con las mismas respuestas (FR-001 a FR-003).

**Independent Test**: el banco de paridad contra `referencia-main.json` (quickstart §2).

### Adaptación de tests existentes (autorizada en plan.md)

- [X] T018 [US1] Migrar los fixtures del grupo «Fixture» de [plan.md](plan.md):
  `test_error_contract`, `test_contar_leyes`, `test_full_text_search`, `test_search_filters`,
  `test_fechas_hasta`, `test_resolve_ley_mayusculas`, `test_plegado`, la parte del servidor
  de `test_estado_del_texto`, `test_articulo_por_encabezado`, `test_articulo_sin_prefijos`,
  `test_articulo_truncado`, `test_articulo_metadatos_saneados`, `test_bytes_degradation`,
  `test_value_passthrough`, `test_config_docs`, `test_resolve_ruta` y `test_repos_dir`.

  La inyección en `_DOCS_POR_PAIS`, `_META_POR_PAIS`, `_INDEX_FILE_POR_PAIS` y `_read_file`
  pasa a `instalar_corpus(...)`. Los asserts no cambian. Ejecutar y comprobar que fallan
  porque el servidor aún lee de memoria.
- [X] T019 [US1] En `tests/test_text_search_availability.py`, `MOTIVOS_DEL_CONTRATO` pierde
  `formato_anterior` y `generacion_distinta`. Es la diferencia deliberada del contrato.

### Implementación

- [X] T020 [US1] En `legalize_indice.py`, implementar `construir_filtro(...)`: una sola
  función que devuelve `(sql_where, parametros)` para `buscar_ley` y `contar_leyes` (R6).
  - `instr(columna_norm, ?) > 0` para consulta, rango, estado, jurisdicción y departamento;
  - `anno` como prefijo de `fecha_publicacion`;
  - `fecha_*` que dejan pasar los vacíos;
  - `derogada_*` y `actualizada_*` que exigen que la fecha exista;
  - límites superiores con `substr(f, 1, length(?)) <= ?`.

  Para `texto`, los términos de `legalize_tokenizer.tokens` van entrecomillados para FTS5 y
  unidos con `AND`, en un `n IN (SELECT rowid FROM cuerpo WHERE cuerpo MATCH ?)`. Si no hay
  términos, el motivo es `consulta_sin_terminos`. Orden `ORDER BY n`.
- [X] T021 [US1] En `mcp_legalize.py`, reescribir la carga y la consulta:
  - `_load_indices` abre cada `index_*.db` con `legalize_indice.abrir`, comprueba
    `directorio_base` contra `LEGALIZE_REPOS_DIR` como hoy, avisa del formato anterior
    (contrato del operador) y registra las conexiones por país, en el orden de hoy;
  - `_filtrar_docs`, `_resolve_ley` (`COLLATE NOCASE`, exacta primero y empates de
    mayúsculas como ambigüedad), `listar_paises`, `listar_rangos`, `estadisticas` y
    `_doc_resumen` pasan a leer de las conexiones;
  - se conservan `_sanitize_metadata`, `_wrap_untrusted`, `_resolve_ruta`, `_read_file`,
    `sin_consultar` (con los motivos de [data-model.md](data-model.md)) y la
    `_estado_del_texto` de #52.
  - Se retiran `_DOCS_POR_PAIS`, `_INVERTIDO_POR_PAIS`, `_campo_normalizado` y el uso de
    `legalize_postings`.
- [X] T022 [US1] Sustituir los tests del grupo «Objeto retirado» de [plan.md](plan.md) por sus
  equivalentes sobre la base de datos, conservando los invariantes:
  - `test_index_shape` → filas malformadas degradan esa fila, no la herramienta (ADR 0002);
  - `test_search_normalization_cache` → el título se pliega al indexar, no en cada consulta;
  - `test_postings_format` y la parte de postings de `test_inverted_index` → cubiertos por
    `test_indice_formato` y `test_indice_seguridad`. Se borran.
- [X] T023 [US1] Ejecutar la suite completa (en verde). Reindexar los cuatro corpus locales,
  ejecutar `paridad/banco.py` con la rama y compararlo con `referencia-main.json`. Las únicas
  diferencias admitidas son las de [contracts/herramientas-mcp.md](contracts/herramientas-mcp.md).
  Cualquier otra se corrige antes de seguir. Commit
  `feat: serve every tool from the per-corpus database, answers unchanged`.

**Checkpoint (MVP)**: servidor sobre SQLite con paridad comprobada en los cuatro corpus.

---

## Phase 5: User Story 4 - Mantener los índices sin maquinaria propia (Priority: P2)

**Goal**: pasada incremental, interrupción segura y transición desde el formato anterior
(FR-009 a FR-013).

**Independent Test**: quickstart §7 y la propiedad incremental = completo.

- [X] T024 [P] [US4] En `tests/test_incremental_postings.py`, ya migrado en T011,
  confirmar que los escenarios de la spec 001 siguen en verde sobre la base de datos. Añadir:
  - una interrupción simulada (`Escritor.confirmar` parcheado para lanzar a mitad): la base
    de datos anterior queda intacta y el temporal desaparece;
  - un índice solo en formato anterior: la pasada lo migra sin flags y borra el `.json` y el
    `.postings`.
- [X] T025 [P] [US4] En `tests/test_inverted_index.py`, el ciclo «estado caducado → remedio →
  limpio» con `FORMATO` en lugar de `POSTINGS` (formato anterior, formato distinto, esquema
  inesperado), además de `TOKENS` y `REGLAS`.
- [X] T026 [US4] Implementar en `scripts/update_index.py` la pasada incremental:
  1. copia la base de datos vigente a un temporal (research R1);
  2. recalcula las leyes con cambio de tamaño o `mtime`, los huérfanos con
     `--remove-orphans`, las cuarentenas y los renombrados, en una transacción;
  3. hace `optimize`, `VACUUM` y `os.replace`.

  El reescaneo completo cuando cambian `patrones`, `tokenizador` o `formato` se mantiene. Si
  `os.replace` falla en Windows con el fichero abierto, avisar y conservar el temporal.
- [X] T027 [US4] En `scripts/check_updates.py`, leer los sellos con
  `legalize_indice.abrir` y `meta`. Desaparece `POSTINGS` y aparece `FORMATO`, con el remedio
  `update_index.py --repo <dir>`.
- [X] T028 [US4] Medir la pasada incremental del 1 % y del 5 % de ES (presupuesto de la
  spec 001: ≤ 20 s) y anotarla en Notes. Commit
  `feat(index): incremental runs inside one transaction, swapped in whole`.

---

## Phase 6: User Story 5 - Los artículos se preparan una vez (Priority: P3)

**Goal**: los artículos se leen de las filas, con `capitulo` y `ubicaciones` (FR-014 a
FR-016).

**Independent Test**: paridad de artículos y quickstart §6.

- [X] T029 [P] [US5] Crear `tests/test_indice_articulos.py`:
  - para cada documento de los tests de artículos existentes, más un corpus sintético con
    `1 §` repetido por capítulo, los `(inicio, fin)` de la primera aparición en
    `articulos` coinciden con `_localizar_articulo(cuerpo, n, contexto)`;
  - pedir con `capitulo` cada ubicación devuelve esa aparición;
  - una `capitulo` desconocida da «Artículo no encontrado» con `ubicaciones`;
  - un número único da `ubicaciones=None`;
  - las ubicaciones pasan por `_sanitize_metadata`.
- [X] T030 [US5] En `mcp_legalize.py`, `obtener_articulo` lee la fila por
  `(ley, numero COLLATE NOCASE)` en orden:
  - sin `capitulo`, la primera; con `capitulo`, la de esa ubicación exacta;
  - `ArticuloResultado` gana `ubicacion` y `ubicaciones`; esta última solo si hay más de una
    aparición;
  - `texto_truncado` se calcula con `fin` de la fila y `contexto_chars` como hoy;
  - sin filas, recurre a `_localizar_articulo` sobre el fichero (documentos sin encabezados).

  Parámetro nuevo opcional: `capitulo: str = ""`.
- [X] T031 [US5] Repetir la medición de artículos de la sesión del 2026-10-18 (ES, SE, FR
  con muestreo y EU) con la rama: ningún inicio equivocado, corte, desborde ni prefijo
  fantasma. Medir SC-008 sobre una muestra sueca. Commit
  `feat: articles located at index time, and repeated numbers reachable by chapter`.

---

## Phase 7: User Story 3 - Buscar una frase exacta (Priority: P2)

**Goal**: el parámetro `frase` en `buscar_ley` y `contar_leyes` (FR-007, FR-008).

**Independent Test**: quickstart §5.

- [X] T032 [P] [US3] Crear `tests/test_frase.py`:
  - un corpus sintético con «arrendamiento urbano» seguido en unos documentos y las palabras
    separadas en otros: `frase` devuelve solo los primeros y `texto` sigue devolviendo ambos;
  - plegado (`"ARRENDAMIENTO URBANO"`, `forêt`/`foret`);
  - palabras cortas dentro de la frase (`"ley de 1978"` exige el `de`);
  - combinación con `texto`, `pais` y fechas;
  - `contar_leyes` coincide con `buscar_ley`;
  - frase sin palabras → `consulta_sin_terminos`;
  - un país sin texto buscable aparece en `sin_consultar`.
- [X] T033 [US3] Añadir `frase` a `construir_filtro`: la frase plegada como **una única**
  cadena FTS5 entrecomillada, con `"` escapado como `""`. Añadir `frase: str = ""` a
  `buscar_ley` y `contar_leyes`, con docstring, instrucciones del servidor y Tool reference
  del README.
- [X] T034 [US3] Medir SC-006 en ES (`frase="arrendamiento urbano"`: 4 frente a 573 en la
  prueba de concepto). Commit `feat: search for an exact phrase`.

---

## Phase 8: Polish & Cross-Cutting

- [X] T035 Python 3.12 como suelo:
  - `.github/workflows/ci.yml` con la matriz `['3.12', '3.13']` (añadir `3.14` si
    `requirements.lock` instala) y la rama del lock en 3.12;
  - el README (Installation) y los comentarios que citan 3.10;
  - comprobar que `test_config_docs` y `test_readme_claims` siguen en verde.
- [X] T036 Sustituir `indices/index_legalize-mock.json` e
  `indices/inverted_legalize-mock.postings` por `indices/index_legalize-mock.db`, generado
  con `update_index.py`, y ajustar las excepciones de `.gitignore`.
- [X] T037 Retirar `legalize_postings.py` y cualquier referencia restante (comprobarlo con
  `grep`).
- [X] T038 [P] Escribir `docs/decisiones/0009-indice-en-base-de-datos.md`: la decisión, las
  medidas de la prueba de concepto y las finales, las alternativas (JSON + postings,
  Tantivy, motores externos) y la seguridad. Marcar los ADR 0003 y 0007 como sustituidos por
  el 0009 y actualizar el índice.
- [X] T039 [P] Actualizar `README.md`:
  - Overview, Configuration, Keeping indices current (`FORMATO`) e Index provenance (`meta`);
  - sustituir la Mitigation 7 por la apertura segura de la base de datos;
  - cifras nuevas medidas (FR-018).

  Actualizar las cifras desfasadas de `CONTRIBUTING.md` (número de tests, Python).
- [ ] T040 Medición final:
  - SC-002: memoria del servidor con los cuatro corpus;
  - SC-003: arranque hasta la primera consulta;
  - SC-004: p95 de texto y artículos;
  - SC-007: indexado completo de ES (tiempo, memoria y disco).

  Anotarlo en Notes. Repetir el banco de paridad completo.
- [ ] T041 Ejecutar `pytest -rs` (exactamente los 2 skips de Windows, con el test del enlace
  simbólico en verde) y `--self-test`. Recordar `/security-review` al usuario.

---

## Dependencies & Execution Order

```text
Setup (T001–T003) → Foundational (T004–T013) → US2 (T014–T017) → US1 (T018–T023) ─┬─→ US4 (T024–T028)
                                                                                     ├─→ US5 (T029–T031)
                                                                                     └─→ US3 (T032–T034) → Polish
```

- **US2 antes que US1**: el servidor no debe abrir ninguna base de datos sin la apertura
  segura completa.
- **US4, US5 y US3** dependen de US1 (el servidor ya lee de la base de datos), pero no entre
  sí. Las tres tocan `mcp_legalize.py` o `update_index.py` en zonas distintas.

### Parallel Opportunities

- T004 ∥ T005; T014 ∥ T015 ∥ T016; T024 ∥ T025; T029 y T032 en ramas distintas tras US1; T038 ∥ T039.

## Implementation Strategy

**MVP = Fases 1–4**: el servidor sirve de SQLite con paridad comprobada y apertura segura.
A partir de ahí, cada historia es una PR que se puede fusionar por sí sola.

Como el cambio es grande, conviene entregarlo en varias PR apiladas en este orden:
1. Foundational + US2;
2. US1;
3. US4;
4. US5;
5. US3;
6. Polish.

Cada una pasa la CI por sí sola.

## Notes

- Línea base (T001, 2026-10-18): 576 passed, 2 skipped; self-test OK (huella 03446b5a64e4). `main` en cc72413.
- Referencia de paridad (T003): 1.178 peticiones (191 buscar_ley, 96 contar_leyes, 162 obtener_ley, 720 obtener_articulo, 9 de listado), 0 excepciones, generada con `main` cc72413 sobre los corpus es c1b7254a, se 0e6c4b6, fr e38417f, eu 46c90a58. `paridad/referencia-main.json` (3,7 MB, ignorado por git), sha256 fa3f780975e8991c…
- Ajustes de orden (2026-10-18), para que cada commit pase el pre-commit en verde:
  - Python 3.12 en la CI se adelanta a la fase 2: las PR apiladas pasan la CI por sí solas, y en 3.10/3.11 no hay `setconfig`. La protección de `main` sigue exigiendo los checks de 3.10 y 3.11 y hay que cambiarla con permiso del usuario.
  - T010 escribe los dos formatos (JSON+postings y `.db`) hasta US4; `test_indice_desde_indexador.py` exige que contengan lo mismo y en el mismo orden.
  - T011 (migrar los tests que leen el JSON) pasa a US4, al retirar el JSON; T012 (`instalar_corpus`) y T016 (sintaxis de FTS5 a través de las herramientas) pasan a US1, donde el servidor ya lee la base de datos.
- Decisiones al implementar US1 (2026-10-18, aprobadas por el usuario):
  - `leyes.id` es `UNIQUE` binario, no `COLLATE NOCASE`. La regla de duplicados del indexador distingue mayúsculas; con `NOCASE`, un fichero con `BOJA-B` junto a `BOJA-b` abortaba la escritura del corpus entero. En los corpus reales hay 0 choques (es, eu, fr, se). La búsqueda sin mayúsculas sigue por `id_casefold`, y el comportamiento del #4 no cambia.
  - `sin_postings` sigue en el contrato, pero ningún país servido lo alcanza: todo corpus servido trae su FTS. Los tests que lo usaban con un país servido pasan a `tokenizador_distinto` (`test_text_search_availability`), o se retiran por estar cubiertos (`test_full_text_search`, el del país sin índice invertido).
  - Se retiran sin sustituto los dos tests de carga perezosa de `test_full_text_search`: no hay nada que cargar.
  - Se retira `test_an_index_built_before_the_field_existed_answers_unknown`: el escritor guarda `estado_texto` resuelto, así que ese índice no puede existir.
  - `test_bytes_degradation` manipula la columna `bytes` del `.db` con valores que SQLite puede guardar (texto, real, blob). Al migrarlo apareció un defecto: dos tamaños de 2^63−1 desbordaban `sum(bytes)` en `listar_paises`. Ahora se usa `total()` solo sobre enteros.
  - T022: `test_index_shape` → `test_indice_degradacion.py`; `test_search_normalization_cache` → `test_titulo_plegado_al_indexar.py`. Las comillas de `terminos_fts` tienen su propio test: el tokenizador ya impide hoy que llegue sintaxis, así que los tests a través de las herramientas no las cubrían.
- Paridad de US1 (T023, 2026-10-18): 1.178 peticiones, 0 diferencias con `referencia-main.json`. Los cuatro corpus se reindexaron con `--force-all`: sin cambios, la pasada incremental no escribe el `.db`, y eso lo resuelve T024. El `.db` de `mock` se generó aparte para el banco; el del repositorio llega en T035. Sin él, las 7 diferencias eran todas de `mock`. Tamaños: es 530 MB, eu 248 MB, fr 77 MB, se 42 MB.
- US4 (2026-10-18), con el plan y los cambios de tests aprobados por el usuario:
  - La pasada escribe sobre una copia del `.db` vigente y repite en el `Escritor`, en el mismo orden, cada cambio de `documentos`, así que la posición de cada ley es la de una reconstrucción. Un `.db` ausente, ilegible, de otro formato o con otro esquema se reconstruye entero. Un JSON sin `.db` se migra sin flags y después se borran `.json`, `.postings` y `.bin`. Si cambia el tokenizador, se rehacen todos los cuerpos conservando ids y orden.
  - T013 queda absorbida aquí: el indexador ya no escribe JSON ni postings. `--index` acepta una ruta `.json` y la toma como su `.db`.
  - Tests sustituidos según la tabla aprobada:
    - los de postings ausentes o de otra generación pasan a «`.db` ausente / inutilizable se reconstruye»;
    - el de escritura fallida de postings pasa al de interrupción;
    - el de la huella dentro del fichero de postings se retira;
    - el del `.bin` pasa a «la migración borra el formato anterior».
  - `test_indice_desde_indexador` deja de comparar con el JSON y compara con el corpus y con una reconstrucción.
  - `check_updates.py`: `POSTINGS` → `FORMATO` (formato anterior, distinto, esquema inesperado e ilegible). Al migrarlo apareció que un valor de `meta` de otro tipo tiraba el informe (`TypeError` con `directorio_base` numérico); ahora degrada esa comprobación. Tiene test.
  - Si `os.replace` falla (Windows con el servidor abierto), el temporal se conserva y el error dice dónde está. Sin test: no se reproduce en macOS.
- Mediciones:
  - T028 (2026-10-18, ES, 25.889 leyes): migración sin cambios 2,96 s; pasada incremental del 1 % (258 ficheros) 6,7 s; del 5 % (1.294) 12,2 s. Presupuesto de la spec 001: ≤ 20 s. Paridad tras migrar y dos pasadas incrementales: 0 diferencias en 1.178 peticiones.
  - T031 (2026-10-18): para la primera aparición de cada número, las filas dan el mismo `(inicio, corte, fin)` que `localizar`. Ningún inicio fuera de un encabezado, ningún final fuera de sitio y ningún encabezado que no nombre su número:
    - se: 8.990 leyes, 167.839 filas, 0 distintos de 126.898 números;
    - es: 25.889 leyes, 406.686 filas, 0 de 393.060;
    - eu: 18.606 leyes, 108.742 filas, 0 de 107.538;
    - fr: muestra de 20 leyes, 45.644 filas, 0 de 41.776. Tardó 896 s: comparar contra `localizar` es cuadrático en los códigos franceses, justo el coste que las filas quitan al servidor.

    SC-008: en se, las 49.032 apariciones de números repetidos se obtienen todas con `capitulo` (100 %).
  - Ajustes en US5:
    - Una repetición sin encabezados por encima se marca `(2)`, no ` (2)`.
    - Con un `capitulo` que no corresponde, `ubicaciones` se lista aunque el número sea único.
    - Los tests de artículos que ya existían instalan ahora el cuerpo real (antes parcheaban `_read_file`), así que pasan por las filas: si se sabotea el corte, fallan 23.
    - El banco ignora los campos nuevos del contrato (`ubicacion`, `ubicaciones`) cuando la referencia no los tiene, y cuenta aparte cuántas respuestas los traen rellenos.
  - T034 / SC-006 (2026-10-18). Frase frente a palabras; de cada frase se revisaron hasta 100 resultados, y ninguno carece de la frase en su texto:

    | Corpus | Frase | Como frase | Tiempo | Como palabras |
    |---|---|---|---|---|
    | es | «arrendamiento urbano» | 4 | 0,4 ms | 573 (las cifras de la prueba de concepto) |
    | es | «proteccion de datos» | 3.424 | 83,7 ms | 8.833 |
    | es | «ley de enjuiciamiento civil» | 401 | 12,1 ms | 812 |
    | se | «allmän försäkring» | 274 | 0,5 ms | 368 |
    | eu | «data protection» | 904 | 3,0 ms | 3.913 |
    | fr | «fonds de commerce» | 36 | 8,7 ms | 68 |

    Para T040: contar una frase muy común supera el objetivo de p95 < 5 ms del quickstart (83,7 ms con 3.424 resultados).
  - Ajuste en US3: una `frase` sin palabras da su propio mensaje de error; el de `texto` no cambia, porque el banco compara su texto exacto.
  - Paridad tras US3: 0 diferencias en 1.178 peticiones.
  - T040 (2026-10-18). Con los cuatro corpus, `main` (cc72413) frente a la rama, en la misma máquina:
    - carga de los cinco índices: 143 ms y +163 MB en `main`; 27 ms y +4 MB en la rama;
    - primera consulta: 0,2 ms en las dos;
    - memoria tras el banco completo: +578 MB frente a +182 MB (3,1×). SC-002 se cumple al cargar, pero no tras el banco: lo que crece es servir el texto de los ficheros, igual en las dos;
    - p95: texto 9,6 frente a 3,7 ms; artículos 7,2 frente a 2,7 ms;
    - indexado completo de ES (SC-007): 150 s y 4,14 GB en `main`; 201 s y 0,56 GB en la rama. **El tiempo NO cumple SC-007 (+34 %); queda abierto.** Perfil sobre se: ~6 s de `localizar_todos` en ES y la escritura en FTS5; el plegado (~39 s) ya se pagaba antes. Una caché de escritura mayor no ayuda.
    - Al medir aparecieron dos peticiones más lentas que en `main`, ya corregidas:
      - `estadisticas` y `listar_rangos` (hasta 92 ms frente a 3–9): ahora usan conteos preparados al indexar (`meta.conteos`), validados y recalculados si no sirven;
      - id inexistente sin país (8,1 frente a 5,2 ms): la subcadena recorre solo el índice de ids.
    - Paridad final: 0 diferencias en 1.178 peticiones.
