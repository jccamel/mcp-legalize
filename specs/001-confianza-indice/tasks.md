---

description: "Task list for specs/001-confianza-indice"
---

# Tasks: Confianza en el índice

**Input**: Design documents from `specs/001-confianza-indice/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/)

**Tests**: OBLIGATORIOS. La constitución (principio V, no negociable) exige escribir cada test
antes que el arreglo, **ejecutarlo y verlo fallar por el motivo correcto**, y anotar ese fallo
en el commit. Ningún paso de implementación empieza con su test en verde.

**Organization**: una fase por historia de usuario. El orden de las fases sigue las
dependencias del plan, no solo la prioridad. US3 va antes que US1 aunque las dos son P1, porque
la generación de US1 vive en la cabecera del formato de US3.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: puede ir en paralelo (ficheros distintos y sin dependencias pendientes)
- **[Story]**: historia de la spec a la que pertenece (US1–US5)

## Path Conventions

Proyecto plano: módulos en la raíz, scripts en `scripts/`, tests en `tests/`. Ejecutar siempre
con `.venv/bin/python`.

## Reglas comunes a todas las tareas

- Comentarios y docstrings del código en español con tildes (`tests/test_prose_style.py`).
  Docstrings de `tests/` en inglés, explicando por qué existe el test.
- Asserts en el punto de llamada: las herramientas MCP con `.fn(...)` y los scripts con `main()`
  o un subproceso, no en helpers privados (CONTRIBUTING, "Tests").
- Ningún assert sobre tiempo transcurrido.
- Commits *conventional* con un cuerpo que explique el porqué, una unidad de comportamiento por
  commit, sin `Co-Authored-By`. El pre-commit ejecuta la suite.
- Un test existente solo se cambia si lo autoriza la tabla «Cambios en tests existentes» de
  [plan.md](plan.md).

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: dejar la línea base verificada antes de tocar nada.

- [X] T001 Ejecutar `.venv/bin/python -m pytest -rs` y `.venv/bin/python scripts/update_index.py --self-test`; confirmar que la suite está verde con exactamente los 2 skips de Windows y anotar el número de tests (hoy 385) como línea base en `specs/001-confianza-indice/tasks.md` (sección Notes)
- [X] T002 [P] Añadir `!indices/inverted_legalize-mock.postings` a `.gitignore` junto a la excepción existente `!indices/index_legalize-mock.json`, para que el mock pueda versionar sus postings (plan, Project Structure)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: `legalize_postings.py`, la única fuente de verdad del formato y de su disponibilidad
(R6). En esta fase nadie lo usa todavía.

**⚠️ CRITICAL**: ninguna historia puede empezar hasta que esta fase esté en verde.

### Tests (escribir primero y verlos fallar: el módulo no existe)

- [X] T003 Crear `tests/test_postings_format.py` con tests que escriben con `legalize_postings.escribir` y leen con `legalize_postings.leer`:
  - una ida y vuelta conserva término → conjunto de ids;
  - el fichero empieza exactamente por las líneas `legalize-postings 1`, `tokenizador <huella>`, `generacion <32 hex>` y `documentos <N>`, seguidas de N líneas de ids y de una línea `<término>\t<d1>,<d2>,…` por término "en orden lexicográfico";
  - el primer delta es el índice y cada uno de los siguientes es "≥ 1";
  - dos escrituras del mismo contenido con la misma generación son idénticas byte a byte;
  - leer no decodifica ninguna lista hasta que se consulta un término (se cuenta con un espía, no con tiempo).
- [X] T004 En `tests/test_postings_format.py`, un test parametrizado por cada regla de validación de [data-model.md](data-model.md). Cada caso debe dar el motivo `ilegibles` sin lanzar excepción:
  - "la primera línea no es exactamente `legalize-postings 1`";
  - "faltan cabeceras o `N` no es un entero no negativo";
  - "hay menos de `N` líneas de ids o algún id está vacío";
  - "una línea de término no tiene tabulador, el término no cumple el patrón o aparece repetido";
  - "un delta no es entero, es menor que 1 (o que 0 en el primero), o la suma acumulada llega a `N` o más".

  Incluir un fichero binario arbitrario y uno vacío.
- [X] T005 En `tests/test_postings_format.py`, tests de `legalize_postings.estado(...)` que cubren los cinco motivos y su orden de evaluación, en el que gana el primero que se cumple:
  - "`formato_anterior` → existe `inverted_<repo>.bin` y no existe `.postings`";
  - "`sin_postings` → no existe ninguno";
  - "`ilegibles`";
  - "`tokenizador_distinto` → la huella de la cabecera ≠ la esperada";
  - "`generacion_distinta` → la generación de la cabecera ≠ la del JSON, o el JSON no la tiene".

  Añadir también el caso utilizable (motivo `None`).
- [X] T006 En `tests/test_postings_format.py`, test de seguridad (SC-003): con `inverted_x.bin` presente y sin `.postings`, `estado` devuelve `formato_anterior` **sin abrir el `.bin`**. Comprobarlo parcheando `open`/`Path.open`/`Path.read_bytes` para que fallen si se llaman con esa ruta, y escribiendo en el `.bin` un pickle que, si se deserializara, crearía un fichero centinela en `tmp_path`; el centinela no debe existir. Añadir un test que verifique que `legalize_postings` no importa `pickle` ni `mcp_legalize`.

### Implementación

- [X] T007 Crear `legalize_postings.py` con docstring de módulo en español que explique por qué existe (R1, R6) y con:
  - `escribir(ruta, postings: dict[str, set[str]], tokenizador: str, generacion: str)`: atómica, con fichero temporal en el mismo directorio y `os.replace`;
  - `leer(ruta)`: devuelve un objeto con `tokenizador`, `generacion`, la tabla de ids y la consulta perezosa por término a un `set[str]` de ids, o lanza `ValueError` con el motivo;
  - `estado(directorio, nombre_repo, huella_tokenizador_esperada, generacion_json) -> (postings | None, motivo | None)`, con los motivos exactos `formato_anterior`, `sin_postings`, `ilegibles`, `tokenizador_distinto` y `generacion_distinta`;
  - `ruta_postings(directorio, nombre_repo)` y `ruta_formato_anterior(directorio, nombre_repo)`;
  - `nueva_generacion()`, que devuelve 32 hex de `secrets.token_hex(16)`.

  El módulo solo usa la biblioteca estándar, no importa `pickle`, `mcp_legalize` ni `legalize_tokenizer` (la huella llega como parámetro) y nunca abre un `.bin`. Un error de decodificación perezosa deja ese objeto marcado como `ilegibles` para el resto del proceso (data-model).
- [X] T008 Ejecutar `tests/test_postings_format.py` (verde), la suite completa y `tests/test_prose_style.py`; hacer commit `feat: add legalize_postings, a code-free format for the inverted index` contando en el cuerpo los fallos observados en T003–T006.

**Checkpoint**: el formato existe y está probado; servidor e indexador siguen como estaban.

---

## Phase 3: User Story 3 - Cargar los postings no puede ejecutar código (Priority: P1) 🎯 MVP

**Goal**: el servidor y el indexador dejan pickle; el servidor nunca abre un `.bin` (FR-007, FR-008, R4).

**Independent Test**: con un `inverted_<repo>.bin` malicioso y sin `.postings`, una búsqueda con `texto` no ejecuta nada y el resto de países responde con normalidad (quickstart §4).

### Tests for User Story 3 (primero, y verlos fallar)

- [X] T009 [US3] En `tests/test_full_text_search.py` (nuevo test, sin tocar los existentes), escribir un test de punta a punta: un `inverted_tst.bin` cuyo pickle crearía un fichero centinela y ningún `.postings`; después, `mcp_legalize.buscar_ley.fn(pais="tst", texto="arrendamiento")` y comprobar que el centinela no existe. Hoy falla, porque `_cargar_invertido` lo deserializa. Anotar el fallo.
- [X] T010 [P] [US3] En `tests/test_inverted_index.py`, un test nuevo que comprueba que tras `update_index.py` existe `inverted_<repo>.postings`, no existe `inverted_<repo>.bin` aunque hubiera uno previo, y el `.postings` se lee con `legalize_postings.leer`. Verlo fallar.

### Adaptación de tests existentes (autorizada en plan.md)

- [X] T011 [US3] Adaptar los fixtures `corpus` de `tests/test_full_text_search.py` y de `tests/test_contar_leyes.py` para que escriban con `legalize_postings.escribir`, usando `legalize_tokenizer.huella()` en lugar de `"cafe12345678"`, una generación fija, y `_META_POR_PAIS["tst"] = {"generacion": <la misma>}`. Ningún assert cambia.
- [X] T012 [US3] Adaptar `leer_invertido` y los tests de nombre de fichero de `tests/test_inverted_index.py` para que usen `legalize_postings.leer` y esperen `.postings`. Ningún assert de contenido cambia.

### Implementation for User Story 3

- [X] T013 [US3] En `mcp_legalize.py`:
  - sustituir `_cargar_invertido` y `_invertido` por una carga vía `legalize_postings.estado(INDICES_DIR, <repo>, legalize_tokenizer.huella(), _META_POR_PAIS[pais].get("generacion"))`;
  - guardar en `_INVERTIDO_POR_PAIS[pais]` la tupla `(postings | None, motivo | None)`, cargada una sola vez y bajo demanda como hoy;
  - quitar `import pickle`;
  - emitir los avisos de [contracts/operador.md](contracts/operador.md) a stderr con el nombre de fichero formateado con `!r`.

  `_docs_con_texto` sigue devolviendo `None` cuando no hay postings utilizables; la señal al cliente llega en US4.
- [X] T014 [US3] En `scripts/update_index.py`, sustituir `_ruta_invertido` y `_write_invertido` (pickle) por `legalize_postings.escribir` y `ruta_postings`, borrar el `.bin` del formato anterior si existe tras escribir con éxito el `.postings`, y quitar `import pickle`. Provisionalmente, escribir `_meta.generacion` con la generación usada, para que los postings recién escritos sean utilizables; US1 fija el orden definitivo de escritura.
- [X] T015 [US3] Ejecutar T009–T012 (verdes) y la suite completa; hacer commit `fix(security): never deserialise the inverted index with pickle`.

**Checkpoint**: escribir en `indices/` ya no da ejecución de código. Las búsquedas por texto funcionan con índices regenerados.

---

## Phase 4: User Story 1 - La búsqueda por texto no pierde documentos al actualizar (Priority: P1)

**Goal**: los postings coinciden siempre con los documentos del JSON tras cualquier pasada (FR-001 a FR-003, FR-009, R2, R3).

**Independent Test**: indexar, modificar un documento, reindexar de forma incremental, y comprobar que `contar_leyes` coincide con una reconstrucción desde cero (quickstart §2).

### Tests for User Story 1 (primero, y verlos fallar)

- [X] T016 [US1] Crear `tests/test_incremental_postings.py` con un corpus sintético en `tmp_path` (al menos 4 documentos) y el indexador ejecutado de verdad (`main()` con `sys.argv` parcheado o en un subproceso). Cubrir los escenarios 1–4 de US1:
  - modificar B conserva A en los postings;
  - quitar un término de B lo retira solo de B;
  - un documento que pasa a cuarentena desaparece de los postings;
  - un huérfano retirado con `--remove-orphans` desaparece.

  El escenario 1 debe fallar hoy con el defecto reproducido en el análisis.
- [X] T017 [US1] En `tests/test_incremental_postings.py`, el test de propiedad de SC-001: tras una secuencia fija de altas, bajas, modificaciones, renombrados de `identificador` y duplicados, los postings incrementales son iguales a los de una pasada `--force-all` sobre el mismo disco.
- [X] T018 [US1] En `tests/test_incremental_postings.py`, los casos de escenario 5 y de borde:
  - con el JSON al día y el `.postings` borrado, el indexador reconstruye y no imprime "El índice ya está al día";
  - un `.postings` con otra generación provoca una reconstrucción;
  - si la escritura del `.postings` falla (`legalize_postings.escribir` parcheado para lanzar), el JSON queda sin `generacion` ni `tokenizador`, y la pasada siguiente reconstruye.

### Implementation for User Story 1

- [X] T019 [US1] En `scripts/update_index.py`, antes del bucle de pendientes, obtener `legalize_postings.estado(...)` de los postings previos con la huella actual y la `generacion` previa del JSON.
  - **Si son utilizables (FUSIONAR):** cargarlos como conjuntos y retirar los ids de los documentos reprocesados, de los puestos en cuarentena, de los renombrados (`old_doc_id != doc_id`) y de los huérfanos retirados.
  - **Si no lo son (RECONSTRUIR):** marcar que hay que tokenizar todos los documentos que queden en el JSON, incluidos los que no cambiaron en disco.

  Seguir el diagrama de transiciones de [data-model.md](data-model.md).
- [X] T020 [US1] En `scripts/update_index.py`, implementar la reconstrucción: tokenizar con `legalize_tokenizer.tokens_de_documento` cada documento del JSON que no se haya procesado en la pasada, leyendo su `_ruta` desde `repo_dir`, y sin superar el pico de RSS actual. Lo que se guarda por documento es un conjunto de términos; liberar cada uno en cuanto se vuelca a los postings.
- [X] T021 [US1] En `scripts/update_index.py`:
  - cambiar la condición de salida temprana "El índice ya está al día" para que solo se dé si no hay cambios en disco **y** los postings previos son utilizables (FR-003);
  - fijar el orden de escritura de R3: generación nueva con `legalize_postings.nueva_generacion()`, primero `.postings`, después el JSON con `_meta.generacion` y `_meta.tokenizador`;
  - si falla la escritura del `.postings`, escribir el JSON **sin** esas dos claves (FR-015).
- [X] T022 [US1] Ejecutar T016–T018 (verdes) y la suite; medir una pasada incremental del 1% y del 5% sobre `repos/legalize-es` con el script del quickstart §2 y anotar los tiempos en Notes. El presupuesto es "≤ 20 s" hasta el 5% (SC-006); si no se cumple, parar y revisar antes de seguir. Hacer commit `fix(index): keep the inverted index whole across incremental runs`.

**Checkpoint**: `git pull` + `update_index.py` deja la búsqueda por texto completa.

---

## Phase 5: User Story 2 - Un índice manipulado no puede leer fuera del corpus (Priority: P1)

**Goal**: la raíz de los documentos la decide `LEGALIZE_REPOS_DIR` y no el índice (FR-004 a FR-006, R5).

**Independent Test**: un índice con `directorio_base: "/"` y `_ruta: "etc/hosts"` no sirve el fichero y el resto de países responde (quickstart §3).

### Tests for User Story 2 (primero, y verlos fallar)

- [X] T023 [P] [US2] Crear `tests/test_repos_dir.py`. Cada test carga índices escritos en `tmp_path` mediante `mcp_legalize._load_indices` con `INDICES_DIR` y `LEGALIZE_REPOS_DIR` parcheados, y asserts a través de `obtener_ley.fn` y `obtener_articulo.fn`. Casos:
  - `directorio_base: "/"` y `_ruta: "etc/hosts"` → sin el contenido, con aviso `[SEGURIDAD]` en stderr y un índice sano vecino servido;
  - `directorio_base` relativo con `../` que escapa;
  - `directorio_base` absoluto fuera;
  - un enlace simbólico dentro de `LEGALIZE_REPOS_DIR` que apunta fuera (skip donde no se puedan crear enlaces, igual que el test existente);
  - un índice sin `directorio_base` usa `LEGALIZE_REPOS_DIR`;
  - un índice legítimo dentro se sirve igual que hoy.

  El primero debe fallar hoy sirviendo `/etc/hosts`.
- [X] T024 [P] [US2] En `tests/test_repos_dir.py`, un test de que un aviso con un nombre de índice que contenga `\n`, ` ` o `\x85` no puede fabricar una línea falsa en stderr (FR-016), como hace hoy `test_no_rejection_message_can_forge_a_security_log_line`.

### Adaptación de tests existentes (autorizada en plan.md)

- [X] T025 [US2] Adaptar el fixture `repo_root` de `tests/test_resolve_ruta.py` para que además fije `LEGALIZE_REPOS_DIR` y `_RAIZ_POR_PAIS[PAIS]` sobre `tmp_path`. Ningún assert cambia; el test del enlace simbólico debe seguir ejecutándose (es el que vigila la CI).

### Implementation for User Story 2

- [X] T026 [US2] En `mcp_legalize.py`:
  - leer `LEGALIZE_REPOS_DIR` con valor por defecto `<script_dir>/repos` y resolverlo una sola vez;
  - si no existe o no es un directorio, avisar y no servir ningún índice;
  - añadir `_RAIZ_POR_PAIS`;
  - en `_load_indices`, calcular la raíz como hoy a partir de `directorio_base`, resolverla y exigir `is_relative_to(LEGALIZE_REPOS_DIR)`; si falla, ignorar ese índice con el aviso `[SEGURIDAD]` de [contracts/operador.md](contracts/operador.md) usando `!r`;
  - en `_resolve_ruta`, usar `_RAIZ_POR_PAIS[pais]` en lugar de `_META_POR_PAIS[...]["directorio_base"]` y conservar las demás defensas (FR-006).
- [X] T027 [US2] Documentar `LEGALIZE_REPOS_DIR` en el docstring de configuración de `mcp_legalize.py` y en la tabla Configuration de `README.md`, con su valor por defecto exacto, para que `tests/test_config_docs.py` pase. Añadir a Mitigation 3 del README que la raíz la decide el operador y no el índice.
- [X] T028 [US2] Ejecutar T023–T025, `tests/test_config_docs.py` y la suite (verdes); hacer commit `fix(security): take the corpus root from the operator, not from the index`.

**Checkpoint**: ningún contenido de índice amplía lo que el servidor puede leer.

---

## Phase 6: User Story 4 - El cliente distingue "no hay resultados" de "no se pudo buscar" (Priority: P2)

**Goal**: `Conteo.sin_consultar` y la señal de `buscar_ley` (FR-010 a FR-012, Q3, [contracts/herramientas-mcp.md](contracts/herramientas-mcp.md)).

**Independent Test**: con un país sin postings y otro con postings, `contar_leyes` lista el que falta y `buscar_ley` limitado a ese país devuelve un error (quickstart §5).

### Tests for User Story 4 (primero, y verlos fallar)

- [ ] T029 [P] [US4] Crear `tests/test_text_search_availability.py` con dos países sintéticos (`ok`, que tiene postings, y `sin`, que no). Cubrir:
  - `contar_leyes.fn(texto=...)` → `total` del país `ok` y `sin_consultar == [PaisNoConsultado(pais="sin", motivo="sin_postings")]`;
  - con todos los países disponibles, `sin_consultar == []`;
  - sin `texto`, `sin_consultar == []` aunque falten postings;
  - `buscar_ley.fn(pais="sin", texto=...)` es `ErrorRespuesta` y sus `sugerencias` contienen `"sin: sin_postings"`;
  - `buscar_ley.fn(texto=...)` sin país devuelve una lista con los resultados de `ok`;
  - `texto="de la"` (sin términos de 3 o más caracteres) → `ErrorRespuesta` en `buscar_ley` y motivo `consulta_sin_terminos` en `contar_leyes`;
  - los motivos posibles son exactamente los del contrato.
- [ ] T030 [P] [US4] En `tests/test_text_search_availability.py`, un test de FR-012: para un conjunto fijo de consultas, el conjunto de países no consultados según `contar_leyes` coincide con el que se deduce de `buscar_ley`. Las dos salen de `_filtrar_docs`, así que el assert va sobre las herramientas.
- [ ] T031 [US4] Verificar que `tests/test_contar_leyes.py::test_buscar_ley_still_returns_a_bare_list` sigue pasando sin cambios: es el contrato de lista que Q3 protege.

### Cambio de tests existentes (aprobado por el usuario el 2026-10-16)

- [ ] T032 [US4] En `tests/test_full_text_search.py`, cambiar `test_a_country_without_an_inverted_index_degrades_to_no_results` y `test_a_corrupt_inverted_index_degrades_instead_of_raising` para que esperen `ErrorRespuesta` con el país y el motivo (`sin_postings` e `ilegibles`), y conserven que no se lanza ninguna excepción. Reescribir los docstrings explicando que `[]` era indistinguible de "sin coincidencias" (FR-010, Q3) y renombrar los tests en consecuencia. Verlos fallar antes de T033.

### Implementation for User Story 4

- [ ] T033 [US4] En `mcp_legalize.py`:
  - añadir el modelo `PaisNoConsultado(pais: str, motivo: str)` y `Conteo.sin_consultar: list[PaisNoConsultado] = []`;
  - hacer que `_filtrar_docs` (o una función que compartan `buscar_ley` y `contar_leyes`) calcule los países no consultados con sus motivos de `_INVERTIDO_POR_PAIS`, más `consulta_sin_terminos` cuando `legalize_tokenizer.tokens(texto)` está vacío;
  - `contar_leyes` rellena `sin_consultar`;
  - `buscar_ley` devuelve `ErrorRespuesta(error=..., sugerencias=["<pais>: <motivo>", ...])` solo si no se pudo consultar ningún país pedido o si la consulta no tiene términos, y en otro caso la lista de siempre.

  Los códigos de país pasan por `_sanitize_metadata`.
- [ ] T034 [US4] En `mcp_legalize.py`:
  - añadir `contar_leyes` a la lista de herramientas de las instrucciones de `FastMCP(...)`, junto con la frase de que la forma de saber si una búsqueda por texto fue completa es contar con los mismos filtros;
  - actualizar el docstring de `buscar_ley`, que hoy dice "si no lo tiene, no devuelve resultados";
  - corregir "las otras cinco herramientas" en el docstring de `obtener_articulo`.

  Actualizar la Tool reference de `README.md` para que `tests/test_readme_claims.py` siga en verde.
- [ ] T035 [US4] Ejecutar T029–T032 y la suite (verdes); hacer commit `fix: tell the client when full-text search could not run`.

**Checkpoint**: "no se pudo buscar" y "cero coincidencias" ya no se confunden.

---

## Phase 7: User Story 5 - Un cambio de tokenizador se resuelve con el remedio que se propone (Priority: P2)

**Goal**: el sello del tokenizador invalida de verdad y el remedio de `check_updates.py` lo resuelve (FR-013 a FR-015).

**Independent Test**: se altera `_meta.tokenizador`, se ejecuta lo que propone `check_updates.py` y el aviso desaparece (quickstart §6).

### Tests for User Story 5 (primero, y verlos fallar)

- [ ] T036 [P] [US5] En `tests/test_incremental_postings.py`:
  - con `_meta.tokenizador` alterado y sin cambios en disco, `update_index.py` reconstruye los postings de **todos** los documentos y no imprime "El índice ya está al día" (escenario 1);
  - con el sello alterado y un fichero modificado, se reconstruye todo y no solo lo modificado (escenario 2).

  Hoy el primero falla con "El índice ya está al día", como se reprodujo en el análisis.
- [ ] T037 [P] [US5] En `tests/test_inverted_index.py` (tests nuevos junto a los de `check_updates`):
  - para cada estado caducado (`TOKENS`, el nuevo `POSTINGS` con `.postings` ausente, en formato anterior o con otra generación), ejecutar `check_updates.main()`, después el comando que propone (`update_index.py --repo <dir>`) y otra vez `check_updates.main()`, y comprobar que ese índice deja de aparecer (SC-005, FR-014);
  - con unos postings cuyo sello no coincide con el tokenizador del servidor, `contar_leyes(texto=...)` informa `tokenizador_distinto` (escenario 3).

### Implementation for User Story 5

- [ ] T038 [US5] En `scripts/update_index.py`, hacer que un sello de tokenizador previo distinto de `legalize_tokenizer.huella()` cuente como postings no utilizables, y por tanto se reconstruyan. Si T019–T021 ya lo cubren mediante `legalize_postings.estado`, este test lo deja fijado. Confirmar que el sello solo se escribe junto con unos postings escritos (FR-015).
- [ ] T039 [US5] En `scripts/check_updates.py`:
  - añadir el estado `POSTINGS` usando `legalize_postings.estado(...)` con la huella actual y `_meta.generacion`;
  - el aviso nombra el motivo y propone `python scripts/update_index.py --repo <dir_base>`, sin `--force-all`;
  - el índice cuenta como desactualizado una sola vez aunque entre por varios estados.
- [ ] T040 [US5] Ejecutar T036–T037 y la suite (verdes); hacer commit `fix(index): make a changed tokenizer stamp force the rebuild it reports`.

**Checkpoint**: todo estado caducado que se detecta se resuelve con el remedio que se propone.

---

## Phase 8: Polish & Cross-Cutting Concerns

- [ ] T041 Regenerar `indices/index_legalize-mock.json` y crear `indices/inverted_legalize-mock.postings` con `.venv/bin/python scripts/update_index.py --repo repos/legalize-mock --force-all`. Comprobar que `scripts/check_updates.py` ya no marca el mock por `TOKENS` ni `POSTINGS` (sí lo marcará `SIN GIT`, por diseño) y versionar los dos ficheros.
- [ ] T042 [P] Crear `docs/decisiones/0007-postings-en-formato-de-texto-propio.md` con la plantilla. Debe recoger:
  - la decisión de R1 y R4, con la tabla de mediciones de [research.md](research.md);
  - las alternativas JSON, SQLite, msgpack y marshal;
  - generación y fusión (R2, R3).

  Marcar el 0003 como "Sustituida por 0007" en su fichero y en `docs/decisiones/README.md`.
- [ ] T043 [P] Actualizar `README.md`:
  - Mitigations: delimitadores sin cambios, contención de rutas con `LEGALIZE_REPOS_DIR` y un párrafo nuevo sobre los postings sin ejecución de código;
  - Index provenance: `generacion` y `tokenizador`;
  - Keeping indices current: estado `POSTINGS`;
  - Limitations: retirar lo que esta feature cierra.

  Mantener verdes `tests/test_readme_claims.py` y `tests/test_config_docs.py`.
- [ ] T044 Recorrer [quickstart.md](quickstart.md) §1–§7 contra `repos/legalize-es` y `repos/legalize-se` con índices en un directorio temporal. Anotar en Notes:
  - SC-006: pasada incremental del 1% y del 5% de ES, con presupuesto "≤ 20 s";
  - SC-007: arranque sin búsquedas y primera búsqueda por texto en ES, "≤ 0,36 s";
  - pico de RSS del indexado completo de ES, que no puede superar los 4,4 GB de hoy.
- [ ] T045 Ejecutar `.venv/bin/python -m pytest -rs` (verde, exactamente 2 skips) y `scripts/update_index.py --self-test`; comprobar que el test del enlace simbólico pasa; recordar al usuario que ejecute `/security-review` (el cambio toca rutas, el índice y lo que se devuelve al modelo).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Fase 1)**: sin dependencias.
- **Foundational (Fase 2)**: depende de la 1 y bloquea todas las historias.
- **US3 (Fase 3)**: depende de la 2. Es la base de US1, US4 y US5, porque cambia el formato que
  leen.
- **US1 (Fase 4)**: depende de US3 (necesita la generación en la cabecera del formato).
- **US2 (Fase 5)**: depende solo de la Fase 2; puede ir en paralelo con US3 y US1, porque toca
  `_load_indices` y `_resolve_ruta`, que no comparten código con los postings.
- **US4 (Fase 6)**: depende de US3 (los motivos salen de `legalize_postings.estado`).
- **US5 (Fase 7)**: depende de US1 (comparte la lógica de fusionar o reconstruir del indexador).
- **Polish (Fase 8)**: depende de todas.

```text
Fase 1 → Fase 2 ─┬─→ US3 ─┬─→ US1 ──→ US5 ─┐
                 │        └─→ US4 ─────────┤
                 └─→ US2 ──────────────────┴─→ Polish
```

### Within Each User Story

Test nuevo → verlo fallar → adaptar fixtures autorizados → implementar → verde → commit. Un
commit por historia, con el fallo observado en el cuerpo.

### Parallel Opportunities

- T002 en paralelo con T001.
- T010 en paralelo con T009 (ficheros distintos).
- **US2 entera en paralelo con US3 y US1**, en otra rama o worktree: `tests/test_repos_dir.py`,
  `_load_indices` y `_resolve_ruta` no se cruzan con los postings. Al fusionar, el conflicto
  esperable es en `mcp_legalize.py`, en zonas distintas.
- T023 y T024 en paralelo entre sí.
- T029 y T030 en paralelo entre sí.
- T036 y T037 en paralelo entre sí.
- T042 y T043 en paralelo.

## Parallel Example: User Story 2 junto a User Story 3

```text
Rama A: T009 → T010 → T011 → T012 → T013 → T014 → T015   (US3)
Rama B: T023 ∥ T024 → T025 → T026 → T027 → T028          (US2)
```

## Implementation Strategy

### MVP First

1. Fases 1 y 2: el formato existe y está probado.
2. Fase 3 (US3): cierra la ejecución de código, el defecto más grave. **Parar y validar**:
   quickstart §4, y comprobar que con índices regenerados la búsqueda por texto funciona.
3. Si hubiera que entregar ya, US3 sola es un PR fusionable.

### Incremental Delivery

Un PR por fase de historia, en el orden US3 → US2 → US1 → US4 → US5 → Polish. Cada PR lleva su
historia completa con los tests y deja `main` en verde con los cuatro jobs de CI. Los tres P1
(US3, US2 y US1) cierran los tres agujeros de seguridad o de pérdida de datos. Los P2 (US4 y US5)
cierran los silencios que quedarían después.

## Notes

- Línea base (T001, 2026-10-16): 383 passed, 2 skipped (385), self-test OK con 24 patrones, huella del cuerpo 03446b5a64e4.
- Carga de `.postings` del corpus español con validación de términos (T007): 0,24 s, presupuesto 0,36 s. `docs("articulo")`: 2,7 ms.
- T022 (ES, 25.889 docs): indexado completo 137,6 s con pico de 4,21 GB (antes 4,4 GB). Incremental del 1% (258 docs): 11,3 s y 814 MB. Del 5% (1.294 docs): 17,1 s y 1,0 GB. Presupuesto SC-006 de 20 s: cumplido. Términos tras las incrementales: 560.577, igual que el completo.
- Mediciones SC-007 / RSS finales (T044): _pendiente_
- Los números de corpus del README (12.291 documentos, 8,7 MB, ~85 MB) están desactualizados
  (hoy son 25.889, 19,5 MB y 142 MB), pero corregirlos queda fuera de esta spec. Conviene abrir
  una tarea aparte.
