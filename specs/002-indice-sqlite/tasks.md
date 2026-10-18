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

- [ ] T001 Ejecutar `.venv/bin/python -m pytest -rs` y `scripts/update_index.py --self-test`
  en `main`. Anotar la línea base (hoy 576 tests, 2 skips) en la sección Notes de
  `specs/002-indice-sqlite/tasks.md`.
- [ ] T002 Crear el script del banco de paridad
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
- [ ] T003 Generar la referencia: crear un worktree de `main` en el scratchpad, ejecutar
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

- [ ] T004 Crear `tests/test_indice_formato.py`:
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
- [ ] T005 [P] En `tests/test_indice_formato.py`, el esquema de `sqlite_master` es exactamente
  el SQL canónico de [data-model.md](data-model.md), y `meta.formato` es el vigente.

### Implementación

- [ ] T006 Crear `legalize_indice.py`. Docstring en español con el porqué (research R1–R7).
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
- [ ] T007 En `legalize_indice.py`, implementar `localizar_articulos(cuerpo)`: una pasada
  lineal por los encabezados Markdown con las plantillas del servidor
  (`_ARTICULO_EN_ENCABEZADO_TEMPLATE`, `_CUALQUIER_NUMERO`, terminación `(?![\w*-])`) y su
  regla de final (siguiente encabezado de nivel ≤ o con otro artículo). Devuelve
  `(orden, numero, ubicacion, inicio, fin)`. La ubicación es la cadena de encabezados de
  nivel superior que lo contienen, unidos con « › », con « (2) » si hay empate. Las
  plantillas pasan de `mcp_legalize` a este módulo (principio III), y `mcp_legalize` las
  importa de aquí.
- [ ] T008 Implementar `legalize_indice.abrir(ruta)`:
  - URI `mode=ro`;
  - `setconfig(SQLITE_DBCONFIG_DEFENSIVE, True)`, y si falta `setconfig`, `ValueError`;
  - `PRAGMA trusted_schema=OFF`, `query_only=ON` y `cell_size_check=ON`;
  - comparación de `sqlite_master` con `ESQUEMA`;
  - comprobación de `meta.formato`.

  Devuelve la conexión o lanza `ValueError` con el motivo (`ilegible`, `esquema_inesperado` o
  `formato_distinto`). Sin `enable_load_extension`.
- [ ] T009 Ejecutar T004–T005 (en verde). Commit
  `feat: add legalize_indice, the per-corpus database the index moves to`.

### Indexador: construcción completa (base de US1 y US4)

- [ ] T010 Hacer que `scripts/update_index.py` escriba `index_<repo>.db` con
  `legalize_indice.Escritor`, en lugar del JSON y el `.postings`:
  - la pasada completa, con el escáner, la cuarentena, los duplicados, el truncado de
    metadatos y el registro de seguridad de hoy (en `meta.seguridad` como JSON);
  - las huellas `patrones` y `tokenizador`, y `directorio_base`, `pais_predeterminado`,
    `git_commit` y `generado_en`.

  En esta tarea, cualquier pasada es completa; la incremental llega en US4.
- [ ] T011 Migrar los tests del grupo «Lectura del índice generado» de [plan.md](plan.md):
  - `test_ruleset_stamp`, `test_repo_identity`, `test_docid_collision`,
    `test_metadata_scan`, `test_metadata_length` y `test_frontmatter`;
  - la parte del indexador de `test_estado_del_texto`, `test_incremental_postings` y
    `test_carga_unica`.

  Cambio único: `json.loads(indice.read_text())` pasa a `legalize_indice.como_dict(indice)`,
  y la ruta del índice pasa a `.db`. Los asserts no cambian.
- [ ] T012 Añadir a `tests/conftest.py` el fixture `instalar_corpus(pais, documentos,
  cuerpos=None)`. Escribe una base de datos real en `tmp_path` con `legalize_indice.Escritor`,
  crea los ficheros del cuerpo bajo un `LEGALIZE_REPOS_DIR` temporal y la registra en el
  servidor por la vía de carga normal.
- [ ] T013 Ejecutar la suite: solo pueden fallar los tests del servidor, que aún leen de
  memoria. Commit `feat(index): write the per-corpus database instead of JSON and postings`.

**Checkpoint**: el indexador produce bases de datos válidas; el servidor aún no las lee.

---

## Phase 3: User Story 2 - El índice sigue siendo entrada no confiable (Priority: P1)

**Goal**: abrir y consultar una base de datos manipulada no tiene efectos fuera del proceso
(FR-004 a FR-006).

**Independent Test**: el banco de bases de datos manipuladas del quickstart §4.

- [ ] T014 [P] [US2] Crear `tests/test_indice_seguridad.py`. Por cada caso, `abrir()` da
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
- [ ] T015 [P] [US2] En `tests/test_indice_seguridad.py`, un test con `abrir` parcheado para
  simular un Python sin `setconfig`: el servidor no sirve ningún índice y avisa con
  `[SEGURIDAD]`.
- [ ] T016 [P] [US2] En `tests/test_indice_seguridad.py`, un test con texto del cliente que
  contiene sintaxis de FTS5 (`"`, `AND`, `NEAR(`, `*`, `(`, `)`, `col:valor`) en `texto`,
  `consulta` y `frase`: ninguna llamada lanza un error del motor, y el resultado equivale a
  buscar ese texto literal.
- [ ] T017 [US2] Completar en `legalize_indice.abrir` lo que T014–T016 exijan y no estuviera
  en T008. Commit `fix(security): open the index database as untrusted input`.

---

## Phase 4: User Story 1 - El cliente no nota el cambio (Priority: P1) 🎯 MVP

**Goal**: el servidor lee de las bases de datos, con las mismas respuestas (FR-001 a FR-003).

**Independent Test**: el banco de paridad contra `referencia-main.json` (quickstart §2).

### Adaptación de tests existentes (autorizada en plan.md)

- [ ] T018 [US1] Migrar los fixtures del grupo «Fixture» de [plan.md](plan.md):
  `test_error_contract`, `test_contar_leyes`, `test_full_text_search`, `test_search_filters`,
  `test_fechas_hasta`, `test_resolve_ley_mayusculas`, `test_plegado`, la parte del servidor
  de `test_estado_del_texto`, `test_articulo_por_encabezado`, `test_articulo_sin_prefijos`,
  `test_articulo_truncado`, `test_articulo_metadatos_saneados`, `test_bytes_degradation`,
  `test_value_passthrough`, `test_config_docs`, `test_resolve_ruta` y `test_repos_dir`.

  La inyección en `_DOCS_POR_PAIS`, `_META_POR_PAIS`, `_INDEX_FILE_POR_PAIS` y `_read_file`
  pasa a `instalar_corpus(...)`. Los asserts no cambian. Ejecutar y comprobar que fallan
  porque el servidor aún lee de memoria.
- [ ] T019 [US1] En `tests/test_text_search_availability.py`, `MOTIVOS_DEL_CONTRATO` pierde
  `formato_anterior` y `generacion_distinta`. Es la diferencia deliberada del contrato.

### Implementación

- [ ] T020 [US1] En `legalize_indice.py`, implementar `construir_filtro(...)`: una sola
  función que devuelve `(sql_where, parametros)` para `buscar_ley` y `contar_leyes` (R6).
  - `instr(columna_norm, ?) > 0` para consulta, rango, estado, jurisdicción y departamento;
  - `anno` como prefijo de `fecha_publicacion`;
  - `fecha_*` que dejan pasar los vacíos;
  - `derogada_*` y `actualizada_*` que exigen que la fecha exista;
  - límites superiores con `substr(f, 1, length(?)) <= ?`.

  Para `texto`, los términos de `legalize_tokenizer.tokens` van entrecomillados para FTS5 y
  unidos con `AND`, en un `n IN (SELECT rowid FROM cuerpo WHERE cuerpo MATCH ?)`. Si no hay
  términos, el motivo es `consulta_sin_terminos`. Orden `ORDER BY n`.
- [ ] T021 [US1] En `mcp_legalize.py`, reescribir la carga y la consulta:
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
- [ ] T022 [US1] Sustituir los tests del grupo «Objeto retirado» de [plan.md](plan.md) por sus
  equivalentes sobre la base de datos, conservando los invariantes:
  - `test_index_shape` → filas malformadas degradan esa fila, no la herramienta (ADR 0002);
  - `test_search_normalization_cache` → el título se pliega al indexar, no en cada consulta;
  - `test_postings_format` y la parte de postings de `test_inverted_index` → cubiertos por
    `test_indice_formato` y `test_indice_seguridad`. Se borran.
- [ ] T023 [US1] Ejecutar la suite completa (en verde). Reindexar los cuatro corpus locales,
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

- [ ] T024 [P] [US4] En `tests/test_incremental_postings.py`, ya migrado en T011,
  confirmar que los escenarios de la spec 001 siguen en verde sobre la base de datos. Añadir:
  - una interrupción simulada (`Escritor.confirmar` parcheado para lanzar a mitad): la base
    de datos anterior queda intacta y el temporal desaparece;
  - un índice solo en formato anterior: la pasada lo migra sin flags y borra el `.json` y el
    `.postings`.
- [ ] T025 [P] [US4] En `tests/test_inverted_index.py`, el ciclo «estado caducado → remedio →
  limpio» con `FORMATO` en lugar de `POSTINGS` (formato anterior, formato distinto, esquema
  inesperado), además de `TOKENS` y `REGLAS`.
- [ ] T026 [US4] Implementar en `scripts/update_index.py` la pasada incremental:
  1. copia la base de datos vigente a un temporal (research R1);
  2. recalcula las leyes con cambio de tamaño o `mtime`, los huérfanos con
     `--remove-orphans`, las cuarentenas y los renombrados, en una transacción;
  3. hace `optimize`, `VACUUM` y `os.replace`.

  El reescaneo completo cuando cambian `patrones`, `tokenizador` o `formato` se mantiene. Si
  `os.replace` falla en Windows con el fichero abierto, avisar y conservar el temporal.
- [ ] T027 [US4] En `scripts/check_updates.py`, leer los sellos con
  `legalize_indice.abrir` y `meta`. Desaparece `POSTINGS` y aparece `FORMATO`, con el remedio
  `update_index.py --repo <dir>`.
- [ ] T028 [US4] Medir la pasada incremental del 1 % y del 5 % de ES (presupuesto de la
  spec 001: ≤ 20 s) y anotarla en Notes. Commit
  `feat(index): incremental runs inside one transaction, swapped in whole`.

---

## Phase 6: User Story 5 - Los artículos se preparan una vez (Priority: P3)

**Goal**: los artículos se leen de las filas, con `capitulo` y `ubicaciones` (FR-014 a
FR-016).

**Independent Test**: paridad de artículos y quickstart §6.

- [ ] T029 [P] [US5] Crear `tests/test_indice_articulos.py`:
  - para cada documento de los tests de artículos existentes, más un corpus sintético con
    `1 §` repetido por capítulo, los `(inicio, fin)` de la primera aparición en
    `articulos` coinciden con `_localizar_articulo(cuerpo, n, contexto)`;
  - pedir con `capitulo` cada ubicación devuelve esa aparición;
  - una `capitulo` desconocida da «Artículo no encontrado» con `ubicaciones`;
  - un número único da `ubicaciones=None`;
  - las ubicaciones pasan por `_sanitize_metadata`.
- [ ] T030 [US5] En `mcp_legalize.py`, `obtener_articulo` lee la fila por
  `(ley, numero COLLATE NOCASE)` en orden:
  - sin `capitulo`, la primera; con `capitulo`, la de esa ubicación exacta;
  - `ArticuloResultado` gana `ubicacion` y `ubicaciones`; esta última solo si hay más de una
    aparición;
  - `texto_truncado` se calcula con `fin` de la fila y `contexto_chars` como hoy;
  - sin filas, recurre a `_localizar_articulo` sobre el fichero (documentos sin encabezados).

  Parámetro nuevo opcional: `capitulo: str = ""`.
- [ ] T031 [US5] Repetir la medición de artículos de la sesión del 2026-10-18 (ES, SE, FR
  con muestreo y EU) con la rama: ningún inicio equivocado, corte, desborde ni prefijo
  fantasma. Medir SC-008 sobre una muestra sueca. Commit
  `feat: articles located at index time, and repeated numbers reachable by chapter`.

---

## Phase 7: User Story 3 - Buscar una frase exacta (Priority: P2)

**Goal**: el parámetro `frase` en `buscar_ley` y `contar_leyes` (FR-007, FR-008).

**Independent Test**: quickstart §5.

- [ ] T032 [P] [US3] Crear `tests/test_frase.py`:
  - un corpus sintético con «arrendamiento urbano» seguido en unos documentos y las palabras
    separadas en otros: `frase` devuelve solo los primeros y `texto` sigue devolviendo ambos;
  - plegado (`"ARRENDAMIENTO URBANO"`, `forêt`/`foret`);
  - palabras cortas dentro de la frase (`"ley de 1978"` exige el `de`);
  - combinación con `texto`, `pais` y fechas;
  - `contar_leyes` coincide con `buscar_ley`;
  - frase sin palabras → `consulta_sin_terminos`;
  - un país sin texto buscable aparece en `sin_consultar`.
- [ ] T033 [US3] Añadir `frase` a `construir_filtro`: la frase plegada como **una única**
  cadena FTS5 entrecomillada, con `"` escapado como `""`. Añadir `frase: str = ""` a
  `buscar_ley` y `contar_leyes`, con docstring, instrucciones del servidor y Tool reference
  del README.
- [ ] T034 [US3] Medir SC-006 en ES (`frase="arrendamiento urbano"`: 4 frente a 573 en la
  prueba de concepto). Commit `feat: search for an exact phrase`.

---

## Phase 8: Polish & Cross-Cutting

- [ ] T035 Python 3.12 como suelo:
  - `.github/workflows/ci.yml` con la matriz `['3.12', '3.13']` (añadir `3.14` si
    `requirements.lock` instala) y la rama del lock en 3.12;
  - el README (Installation) y los comentarios que citan 3.10;
  - comprobar que `test_config_docs` y `test_readme_claims` siguen en verde.
- [ ] T036 Sustituir `indices/index_legalize-mock.json` e
  `indices/inverted_legalize-mock.postings` por `indices/index_legalize-mock.db`, generado
  con `update_index.py`, y ajustar las excepciones de `.gitignore`.
- [ ] T037 Retirar `legalize_postings.py` y cualquier referencia restante (comprobarlo con
  `grep`).
- [ ] T038 [P] Escribir `docs/decisiones/0009-indice-en-base-de-datos.md`: la decisión, las
  medidas de la prueba de concepto y las finales, las alternativas (JSON + postings,
  Tantivy, motores externos) y la seguridad. Marcar los ADR 0003 y 0007 como sustituidos por
  el 0009 y actualizar el índice.
- [ ] T039 [P] Actualizar `README.md`:
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

- Línea base (T001): _pendiente_
- Referencia de paridad (T003): _pendiente_
- Mediciones (T028, T031, T034, T040): _pendiente_
