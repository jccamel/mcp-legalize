---

description: "Task list for specs/003-fin-vigencia"
---

# Tasks: Fin de vigencia, con las expiradas separadas de las derogadas

**Input**: Design documents from `specs/003-fin-vigencia/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/)

**Tests**: OBLIGATORIOS (constitución, principio V). Cada test nuevo se escribe antes que el
código, se ejecuta y se ve fallar por el motivo correcto, y el fallo se anota en el commit.

**Organization**: el esquema y el indexador son la base de todas las historias. Después
vienen US1 (el dato en las respuestas), US2 (los filtros), US3 (las derogadas europeas en los
filtros de derogación, Q1) y US4 (el operador reindexa una vez).

## Format: `[ID] [P?] [Story] Description`

## Reglas comunes

- Comentarios del código en español con tildes; docstrings de `tests/` en inglés.
- Asserts en el punto de llamada: herramientas `.fn` e indexador por su CLI (`indexer_cli`).
- Ningún test existente cambia sin avisar antes (plan.md: no se prevé ninguno).
- Commits *conventional* con cuerpo que explique el porqué y sin atribución a IA. El
  pre-commit ejecuta la suite, así que cada commit la deja en verde.
- Ningún valor del cliente se concatena en SQL: los filtros nuevos van como parámetros.

---

## Phase 1: Setup

- [X] T001 Línea base: `.venv/bin/python -m pytest -rs` y `scripts/update_index.py
  --self-test` en la rama; anotar el número de tests en Notes.
- [X] T002 Referencia de paridad nueva, **antes de tocar código**: con los índices actuales
  (formato 1, reglas `546d466524e0`), ejecutar
  `specs/002-indice-sqlite/paridad/banco.py . specs/003-fin-vigencia/paridad/referencia.json`.
  Hace falta porque la referencia de la spec 002 es anterior a la #58, que añadió a EU la ley
  `32016R1778`; compararse con ella mezclaría ese cambio con los de esta feature. Anotar en
  Notes el commit y el sha256. Añadir `specs/003-fin-vigencia/paridad/*.json` al ignorado si
  el patrón de `.gitignore` no lo cubre ya.

---

## Phase 2: Foundational (esquema e indexador)

**Purpose**: que el índice guarde la fecha. Bloquea las cuatro historias.

### Tests

- [X] T003 [P] Crear `tests/test_fin_vigencia_indexador.py`, a través del indexador
  (`indexer_cli`), con un corpus de una ley por caso del data-model:
  - `expired` con `end_of_validity` → `fecha_fin_vigencia` con la fecha y
    `fecha_derogacion` vacía (FR-003);
  - `repealed` sin `repeal_date` y con `end_of_validity` → las dos con la fecha (Q1);
  - `repealed` con `repeal_date` y `end_of_validity` distintas → cada una de su clave
    (FR-005);
  - `in_force` con fecha futura → `fecha_fin_vigencia` con la fecha, estado intacto (Q3);
  - sin `end_of_validity` → vacía;
  - `end_of_validity` de forma inválida (`"pronto"`, `"2023-02-30"`, `"20-01-2020"`, una
    lista) → vacía, la ley indexada y sin aviso que la saque del índice (FR-001);
  - `AAAA` y `AAAA-MM` aceptadas tal cual.

  Leer el índice con `indexer_cli.leer()`. Debe fallar: hoy `end_of_validity` se ignora.

### Implementación

- [X] T004 En `legalize_indice.py`: columna `fecha_fin_vigencia TEXT NOT NULL` en `leyes`,
  campo en `_CAMPOS_TEXTO` y en `_OPCIONALES` (vacía = ausente en `como_dict` y
  `fila_a_doc`), `FORMATO = "2"`. `Escritor.poner_ley` pasa a insertar por nombre de columna,
  sin depender del orden (`_CAMPOS_TEXTO[:13]`, R3).
- [X] T005 En `scripts/update_index.py`, en `_build_entry`: leer `end_of_validity` (y
  `fecha_fin_vigencia`, por simetría con las demás claves) como campo opcional, validado por
  una función nueva que acepta `AAAA`, `AAAA-MM` y `AAAA-MM-DD` reales (R2). Después, la regla
  de Q1: si `estado` es `repealed`, no hay `fecha_derogacion` y sí `fecha_fin_vigencia`,
  `fecha_derogacion` toma esa fecha. Comentarios con las cifras medidas de EU.
- [X] T006 Regenerar `indices/index_legalize-mock.db` con el formato 2 (si no, la suite y
  `check_updates` lo dan por `FORMATO`). Suite en verde. Commit
  `feat(index): read end_of_validity, and use it as the repeal date of repealed laws`.

**Checkpoint**: el índice guarda la fecha; ninguna herramienta la devuelve todavía.

---

## Phase 3: User Story 1 - Ver cuándo deja de estar en vigor una ley (Priority: P1) 🎯 MVP

**Goal**: FR-002, FR-008, FR-010, FR-011.

**Independent Test**: escenarios 1–3 de la historia 1.

- [X] T007 [P] [US1] Crear `tests/test_fin_vigencia.py` con `instalar_corpus` (los mismos
  casos que T003 ya resueltos): `buscar_ley`, `obtener_ley` y `obtener_articulo` devuelven
  `fecha_fin_vigencia` con la fecha o `None`; una `in_force` futura sigue siendo `in_force`;
  un valor hostil en la columna (base de datos manipulada) llega saneado. Debe fallar: el
  campo no existe.
- [X] T008 [US1] En `mcp_legalize.py`: `fecha_fin_vigencia: Optional[str] = None` en
  `DocumentoResumen`, `LeyCompleta` y `ArticuloResultado`, rellenado en un solo sitio
  (junto a `_estado_del_texto`) con `_sanitize_metadata(..., max_len=50)`, o `None` si vacío.
- [X] T009 [US1] Instrucciones del servidor: qué es `fecha_fin_vigencia`, que puede ser
  futura y que no cambia el estado. Commit
  `feat: tell the client when a law stops being in force`.

---

## Phase 4: User Story 2 - Filtrar por fecha de fin de vigencia (Priority: P1)

**Goal**: FR-006, FR-007.

**Independent Test**: escenarios 1–3 de la historia 2.

- [X] T010 [P] [US2] En `tests/test_fin_vigencia.py`: `fin_vigencia_desde`/`hasta` con fechas
  en 2026, 2027 y 2028; `hasta="2027"` incluye todo 2027; combinado con `estado="expired"`;
  una ley sin fecha nunca cumple el filtro; `contar_leyes` coincide con `buscar_ley` en cada
  caso; un valor del cliente con sintaxis SQL (`"2027' OR 1=1 --"`) no devuelve nada inesperado.
  Debe fallar: los parámetros no existen.
- [X] T011 [US2] En `legalize_indice.construir_filtro`: `fin_vigencia_desde`/`hasta` con
  `rango_fechas("fecha_fin_vigencia", ..., exige=True)`. En `mcp_legalize.py`: los dos
  parámetros al final de `buscar_ley` y `contar_leyes`, pasados por `_consultas`; docstrings.
  Commit `feat: filter laws by the date they stop being in force`.

---

## Phase 5: User Story 3 - Las derogadas europeas, en los filtros de derogación (Priority: P2)

**Goal**: FR-003, FR-004, FR-005 a través de las herramientas.

**Independent Test**: escenarios 1–2 de la historia 3.

- [X] T012 [P] [US3] En `tests/test_fin_vigencia.py`, con un corpus construido **por el
  indexador** (la regla de Q1 vive allí): una `repealed` con solo `end_of_validity` aparece
  con `derogada_desde`; una `expired` con fecha no aparece nunca con ningún filtro de
  derogación. Si T005 ya está, este test pasa: se comprueba quitando temporalmente la regla
  de Q1 de `_build_entry` y viéndolo fallar, y se anota en el commit.

---

## Phase 6: User Story 4 - El operador reindexa una vez (Priority: P3)

**Goal**: FR-012.

- [X] T013 [P] [US4] En `tests/test_fin_vigencia_indexador.py`: un índice escrito con el
  formato 1 (construido con un esquema de formato 1 a mano en el test) → `check_updates`
  informa `FORMATO`; `update_index.py --repo` sin flags lo deja al día y con la fecha. Si ya
  pasa (el mecanismo es el de la spec 002), se comprueba bajando `FORMATO` a mano y viéndolo
  fallar.

---

## Phase 7: Polish & Cross-Cutting

- [X] T014 [P] `specs/002-indice-sqlite/paridad/banco.py`: `fecha_fin_vigencia` en
  `CAMPOS_NUEVOS`.
- [X] T015 [P] `README.md` y `README.es.md`: el campo y los filtros en «Tools», y que tras
  actualizar hay que reindexar antes de reiniciar el servidor. `tests/test_readme_es.py`
  sigue en verde (comprueba que las dos versiones nombren lo mismo).
- [X] T016 Reindexar es, eu, fr y se (`check_updates` debe pedirlo como `FORMATO`). Ejecutar
  el banco y compararlo con `specs/003-fin-vigencia/paridad/referencia.json`. Las únicas
  diferencias admitidas son peticiones con `derogada_desde`/`derogada_hasta` que ahora
  incluyen leyes europeas `repealed` (Q1): comprobar cada una y anotarlas en Notes.
- [X] T017 Quickstart §3–§5 sobre los índices reales (SC-001, SC-002, SC-003, SC-005) y
  medición del filtro nuevo sobre EU (R7: p95; índice SQL solo si supera 5 ms). Anotar en
  Notes.
- [X] T018 `pytest -rs` (los 2 skips de Windows) y `--self-test`. Commit final
  `docs: close spec 003 - end of validity in the READMEs, parity and measurements`.
  Recordar `/security-review` al usuario (toca el índice y lo que se devuelve al modelo).

---

## Dependencies & Execution Order

```text
Setup (T001–T002) → Foundational (T003–T006) ─┬─→ US1 (T007–T009) ─┬─→ Polish (T014–T018)
                                              ├─→ US2 (T010–T011) ─┤
                                              ├─→ US3 (T012) ──────┤
                                              └─→ US4 (T013) ──────┘
```

- T002 va antes que cualquier cambio de código: es la referencia.
- US1, US2, US3 y US4 dependen solo de la base; US2 toca `_consultas`, US1 los modelos.
- T016 necesita US1 y US2 (el banco lee las respuestas y los filtros nuevos no están en él).

### Parallel Opportunities

- T003 ∥ T002 (el test no toca índices reales).
- T007, T010, T012 y T013 son tests en ficheros o funciones distintos.
- T014 ∥ T015.

## Implementation Strategy

1. **MVP**: Setup + Foundational + US1. Con eso el cliente ya ve la fecha.
2. US2 y US3 completan las preguntas por fecha; US4 asegura la transición.
3. Polish: paridad con la referencia nueva, mediciones y documentación.

Una sola PR; cada commit pasa la suite.

## Notes

- Línea base (T001, 2026-10-19, rama en 1ee3893): 684 passed, 2 skipped; self-test OK (huella 546d466524e0); `check_updates` con todo al día.
- Referencia de paridad (T002): 1.178 peticiones, generada con el código en 1ee3893 y los índices de formato 1. `specs/003-fin-vigencia/paridad/referencia.json` (ignorada por git), sha256 4983973aafbbe78d…
- Paridad tras la feature (T016, 2026-10-19). Se reindexaron los cuatro corpus, que `check_updates` daba como `FORMATO` (`esquema_inesperado`): se 8,5 s, fr 17,5 s, eu 80 s y es 149 s. Resultado: 1.178 peticiones; `fecha_fin_vigencia` sale rellena en 313 respuestas.
  - Hay 4 diferencias, todas de Q1 y comprobadas una a una:
    - `contar_leyes` con `derogada_desde="2000"` sube en 1.016, tanto en eu (0 → 1.016) como en total (5.462 → 6.478). Son exactamente las leyes EU `repealed`, sin `repeal_date` y con `end_of_validity` desde 2000, contadas en los ficheros;
    - en las dos `buscar_ley` de eu con ese filtro, todos los resultados nuevos son leyes `repealed` de EU con fecha de fin desde 2000.
  - Ninguna otra diferencia.
- Mediciones (T017, sobre los índices reales):
  - SC-001: 2.267 leyes EU con `fecha_fin_vigencia`.
  - SC-002: `estado="expired"` con `derogada_desde="1900"` da 0, y `repealed` da 1.061.
  - SC-003: expiradas en 2010, 51 en los ficheros, 51 con `contar_leyes` y 51 con `buscar_ley`.
  - SC-005: lo cubre el test y la ejecución real (FORMATO → al día con una sola pasada).
  - R7: filtro de fin de vigencia sobre eu, p95 de 2,8 ms en `contar_leyes` y 2,1 ms en `buscar_ley`. Por debajo de los 5 ms, así que no hace falta índice SQL.
  - Suite final: 714 passed y 2 skips de Windows; self-test OK.
