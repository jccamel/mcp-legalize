# Data Model: Fin de vigencia

## Tabla `leyes` (índice SQLite por corpus, `FORMATO` 2)

Una columna nueva; el resto, sin cambios.

| Columna | Tipo | Contenido |
|---|---|---|
| `fecha_fin_vigencia` | `TEXT NOT NULL` | `end_of_validity` de la fuente si es una fecha válida (R2); `''` si no hay o no lo es |

`fecha_derogacion` no cambia de forma; cambia de dónde puede salir (Q1).

## De la fuente al índice

| Fuente | `fecha_derogacion` | `fecha_fin_vigencia` |
|---|---|---|
| `repeal_date` presente | `repeal_date` | `end_of_validity`, si la hay |
| `repealed`, sin `repeal_date`, con `end_of_validity` | `end_of_validity` (Q1) | `end_of_validity` |
| `expired` con `end_of_validity` | vacía (FR-003) | `end_of_validity` |
| `in_force` con `end_of_validity` (pasada o futura) | vacía | `end_of_validity` (Q3) |
| sin `end_of_validity` | como hoy | vacía |
| `end_of_validity` que no es una fecha | como hoy | vacía (FR-001) |

## Efecto esperado por corpus (medido el 2026-10-19)

| Corpus | Leyes con `fecha_fin_vigencia` | Leyes que ganan `fecha_derogacion` |
|---|---|---|
| eu | 2.267 | 1.061 (`repealed`) |
| es, se, fr | 0 | 0 |

## Respuestas

| Modelo | Campo nuevo |
|---|---|
| `DocumentoResumen` (`buscar_ley`) | `fecha_fin_vigencia: str \| None` |
| `LeyCompleta` (`obtener_ley`) | `fecha_fin_vigencia: str \| None` |
| `ArticuloResultado` (`obtener_articulo`) | `fecha_fin_vigencia: str \| None` |

`None` si la columna está vacía; si no, el valor saneado con `_sanitize_metadata`.

## `meta`

`formato` pasa a `"2"`. Ninguna clave nueva.
