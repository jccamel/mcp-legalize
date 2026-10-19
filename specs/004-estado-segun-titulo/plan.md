# Implementation Plan: Leyes cuyo título dice que se derogaron, aunque el estado diga que no

**Branch**: `feat/004-estado-segun-titulo` | **Date**: 2026-10-19 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/004-estado-segun-titulo/spec.md`

## Summary

Un módulo nuevo, `legalize_estado.py`, decide qué es una marca de derogación al final de un
título (R1) y cuándo contradice al estado. El índice usa esa regla para escribir `estado_norm`,
la columna interna del filtro, con `repealed` en las leyes con aviso: `estado="repealed"` las
encuentra y `estado="in_force"` no (Q2), sin tocar `construir_filtro`. La columna `estado` sigue
siendo literal (ADR 0001). El servidor calcula `aviso_estado` del título al servir, con la
misma regla, y lo sanea; no se guarda. `FORMATO` pasa a `"3." + huella de la regla`, así que
cada corpus se reindexa una vez, y cualquier cambio futuro de la regla vuelve a forzarlo.
`estadisticas` añade `avisos_estado`. ADR 0012.

## Technical Context

**Language/Version**: Python ≥ 3.12 (CI en 3.12, 3.13 y 3.14)

**Primary Dependencies**: `fastmcp`, `pydantic`, `sqlite3` y `re` de la biblioteca estándar.
Sin dependencias nuevas.

**Storage**: índice SQLite por corpus (ADR 0009). Sin columnas nuevas; cambia el contenido de
`estado_norm` y `FORMATO`.

**Testing**: pytest, test primero y visto fallar; asserts en las herramientas MCP y en el
indexador por su CLI.

**Target Platform**: servidor MCP por stdio; indexador y `check_updates` como scripts.

**Project Type**: servidor MCP de solo lectura con indexador.

**Performance Goals**: el filtro de estado no empeora (SC-005); es la misma subcadena sobre la
misma columna (R7).

**Constraints**: cambios aditivos en el contrato; paridad con 0 diferencias en es, eu, fr y
se; el aviso no puede llevar al cliente nada que el título saneado no lleve (FR-003).

**Scale/Scope**: 594 de 86.671 leyes UK; 0 en los demás corpus.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principio | Evaluación | Estado |
|---|---|---|
| I. Fidelidad | `estado` se devuelve literal; el aviso es un campo del servidor, nombrado como tal en las instrucciones, que reproduce la marca del título sin interpretar su fecha (Q1). El filtro deja de devolver como `in_force` leyes que la fuente da por derogadas en el título (Q2); es una decisión del servidor, registrada en el ADR 0012 | ✅ |
| II. No confiable | El aviso sale del título, ya presente en la respuesta, y pasa por `_sanitize_metadata` con tope medido (R3). Nada nuevo se guarda en el índice que haya que validar. `re.ASCII` evita marcas falsas con el signo Kelvin (R1) | ✅ |
| III. Una sola fuente | La regla vive solo en `legalize_estado`; la usan el índice y el servidor (R2). El filtro sigue saliendo de `construir_filtro` | ✅ |
| IV. Degradar sin silencio | Un índice anterior se rechaza como `FORMATO`, en vez de servir un filtro de estado viejo sin avisar (R5) | ✅ |
| V. Test primero | Cada tarea empieza con su test en rojo | ✅ |
| VI. Medir | 594 marcas, 0 falsos positivos, marca máxima de 63 caracteres, todo medido (R1, R3) | ✅ |
| VII. Sellos | `FORMATO` incluye la huella de la regla (R5) | ✅ |
| Restricciones técnicas | Sin dependencias nuevas | ✅ |
| Flujo | No contradice el ADR 0001 (los valores siguen literales) ni la Q3 de la spec 003 (el estado no se deduce: se añade un aviso aparte). El ADR 0012 lo deja escrito | ✅ |

**Re-check tras el diseño**: sin cambios. El coste nuevo es operativo: reindexar los cinco
corpus antes de reiniciar el servidor.

## Project Structure

### Documentation (this feature)

```text
specs/004-estado-segun-titulo/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── herramientas-mcp.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
legalize_estado.py           # NUEVO: marca_derogacion, aviso, estado_filtrable, huella (R1, R2, R4)
legalize_indice.py           # estado_norm con estado_filtrable; FORMATO 3.<huella>; avisos_estado en contar y conteos_validos (R3, R5, R6)
mcp_legalize.py              # aviso_estado en los tres modelos vía _estado_y_vigencia; avisos_estado en estadisticas; instrucciones y docstring del filtro (R3, R6)
indices/index_legalize-mock.db   # regenerado con el formato 3
specs/002-indice-sqlite/paridad/banco.py   # aviso_estado y avisos_estado como campos nuevos
docs/decisiones/0012-aviso-de-estado.md, docs/decisiones/README.md
README.md, README.es.md      # el campo, el filtro y reindexar tras actualizar
CLAUDE.md                    # legalize_estado.py en «Estructura»
tests/
├── test_aviso_estado.py             # NUEVO: aviso en las tres herramientas, filtros, buscar = contar, estadisticas, título hostil
└── test_aviso_estado_indexador.py   # NUEVO: estado_norm, FORMATO y check_updates, por la CLI
```

**Structure Decision**: un módulo nuevo en la raíz, como `legalize_articulos`; ningún otro.

## Cambios en tests existentes

Ninguno previsto. Los tests de formato usan `legalize_indice.FORMATO`. Si alguno compara las
claves de `conteos` o los campos de `Estadisticas` de forma exacta, se avisa antes de
modificarlo.

## Orden de implementación

1. **Regla** (R1, R2, R4): `legalize_estado` con sus casos, incluido el signo Kelvin, probados
   a través del filtro y del aviso, no solo del helper.
2. **Índice** (R3, R5): `estado_norm` y `FORMATO`; `check_updates` informa `FORMATO` en un
   índice de formato 2.
3. **Respuestas y filtros** (R3): `aviso_estado` en las tres herramientas; `repealed` las
   encuentra, `in_force` no; buscar = contar.
4. **Estadísticas** (R6).
5. **Cierre**: ADR 0012, instrucciones, README y README.es, `CLAUDE.md`, índice de `mock`
   regenerado; reindexar los cinco corpus, banco de paridad, quickstart completo y medición del
   filtro (R7).

Una PR para toda la feature; cada commit pasa la suite.

## Complexity Tracking

Sin violaciones de la constitución que justificar.
