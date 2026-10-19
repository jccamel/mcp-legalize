# Implementation Plan: Fin de vigencia, con las expiradas separadas de las derogadas

**Branch**: `feat/003-fin-vigencia` | **Date**: 2026-10-19 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/003-fin-vigencia/spec.md`

## Summary

El indexador lee `end_of_validity`, lo guarda en una columna nueva `fecha_fin_vigencia` si es
una fecha válida, y, en las leyes `repealed` sin `repeal_date`, lo usa también como
`fecha_derogacion` (Q1). Las tres herramientas que devuelven una ley añaden el campo
`fecha_fin_vigencia`; `buscar_ley` y `contar_leyes` añaden `fin_vigencia_desde` y
`fin_vigencia_hasta`, construidos con la misma función que los demás rangos de fecha. El
esquema cambia y `FORMATO` pasa a 2: cada corpus se reindexa una vez, con el remedio de
siempre. La equivalencia se comprueba con el banco de paridad de la spec 002, cuyas únicas
diferencias aceptables son las de Q1.

## Technical Context

**Language/Version**: Python ≥ 3.12 (CI en 3.12, 3.13 y 3.14)

**Primary Dependencies**: `fastmcp`, `pydantic`, `sqlite3` de la biblioteca estándar. Sin
dependencias nuevas.

**Storage**: un índice SQLite por corpus (`legalize_indice.py`, ADR 0009). Columna nueva en
`leyes`; `FORMATO` de `"1"` a `"2"`.

**Testing**: pytest, test primero y visto fallar; asserts en las herramientas MCP y en el
indexador por su CLI.

**Target Platform**: servidor MCP por stdio; indexador y `check_updates` como scripts.

**Project Type**: servidor MCP de solo lectura con indexador.

**Performance Goals**: los de la spec 002: búsquedas por texto y artículos con p95 < 5 ms; el
filtro nuevo, medido sobre EU (R7).

**Constraints**: cambios aditivos en el contrato (FR-009); paridad con 0 diferencias fuera de
las deliberadas; degradar sin fallar ante valores malformados.

**Scale/Scope**: 2.267 leyes europeas con `end_of_validity`; es, se y fr no lo traen.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principio | Evaluación | Estado |
|---|---|---|
| I. Fidelidad | La fecha se devuelve tal como la da la fuente; el servidor no la interpreta ni cambia el estado (Q3). Las expiradas nunca se presentan como derogadas (FR-003). Banco de paridad con las diferencias de Q1 enumeradas | ✅ |
| II. Índice no confiable | La fecha es un valor del corpus: se valida al indexar (R2) y se sanea al servir (R5); los filtros van como parámetros enlazados | ✅ |
| III. Una sola fuente | La traducción de claves de la fuente sigue solo en `_build_entry` (R1); el filtro, en `construir_filtro` con la función de rangos existente (R4) | ✅ |
| IV. Degradar sin silencio | Un `end_of_validity` malformado cuesta ese campo; un índice de formato 1 se informa como `FORMATO` | ✅ |
| V. Test primero | Cada tarea empieza con su test en rojo; no se prevé cambiar ningún test existente (ver abajo) | ✅ |
| VI. Medir | Las cifras de la spec están medidas; el índice SQL de la columna se decide midiendo (R7) | ✅ |
| VII. Sellos que invalidan | `FORMATO` sube con el esquema y fuerza la reconstrucción | ✅ |
| Restricciones técnicas | Sin dependencias nuevas | ✅ |
| Flujo | Spec con spec-kit; no contradice ningún ADR aceptado (0001 claves en castellano, 0002 degradar por entrada, 0009 índice) | ✅ |

**Re-check tras el diseño**: sin cambios. El único coste nuevo es operativo (reindexar los
corpus antes de reiniciar el servidor), y está en el contrato.

## Project Structure

### Documentation (this feature)

```text
specs/003-fin-vigencia/
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
scripts/update_index.py      # _build_entry: end_of_validity → fecha_fin_vigencia; Q1; validación de fecha (R1, R2)
legalize_indice.py           # columna nueva, FORMATO 2, inserción por nombre de columna, filtro (R3, R4)
mcp_legalize.py              # campo en tres modelos; dos parámetros en buscar_ley y contar_leyes; instrucciones (R4, R5)
indices/index_legalize-mock.db   # regenerado con el formato 2
specs/002-indice-sqlite/paridad/banco.py   # fecha_fin_vigencia como campo nuevo del contrato (R6)
README.md, README.es.md      # campo y filtros nuevos; reindexar tras actualizar
tests/
├── test_fin_vigencia.py     # NUEVO: el dato, Q1, FR-003, Q3, filtros, buscar = contar
└── test_fin_vigencia_indexador.py   # NUEVO: lectura y validación en el indexador, por su CLI
```

**Structure Decision**: los módulos sueltos de siempre en la raíz; ningún módulo nuevo.

## Cambios en tests existentes

Ninguno previsto. Los tests de formato usan `legalize_indice.FORMATO` y nombres de campo, no
posiciones, así que el cambio de esquema no los toca. Si al implementar apareciera alguno, se
avisa antes de modificarlo.

## Orden de implementación

1. **Indexador y esquema** (R1–R3): tests del indexador en rojo; columna, `FORMATO` 2,
   inserción por nombre, lectura de `end_of_validity` con su validación y regla de Q1.
2. **Respuestas** (R5): el campo en las tres herramientas.
3. **Filtros** (R4): `fin_vigencia_desde`/`hasta` y la igualdad entre buscar y contar.
4. **Cierre**: índice de `mock` regenerado; instrucciones del servidor y README; reindexar los
   cuatro corpus, banco de paridad con las diferencias de Q1 comprobadas una a una, medición
   del filtro sobre EU (R7) y quickstart completo.

Una PR para toda la feature; cada commit pasa la suite.

## Complexity Tracking

Sin violaciones de la constitución que justificar.
