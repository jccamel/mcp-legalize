# Data Model: Leyes cuyo título dice que se derogaron

## Marca de derogación (derivada, no se guarda)

- **Origen**: `titulo` de la ley, texto del corpus (no confiable).
- **Regla**: R1. El paréntesis final que empieza por `repealed` o `revoked`, sin distinguir
  mayúsculas ASCII.
- **Valor**: el paréntesis literal, p. ej. `(Repealed 25.10.1991)`. Nunca se interpreta la fecha
  (Q1).

## Aviso de estado (`aviso_estado`, en la respuesta)

| Condición | `estado` (literal) | `aviso_estado` | Filtro `estado` lo encuentra con |
|---|---|---|---|
| Marca y `estado` `in_force` o vacío | sin cambios | la marca, saneada, ≤ 100 caracteres | `repealed` (no `in_force`) |
| Marca y cualquier otro estado | sin cambios | None | su propio estado |
| Sin marca | sin cambios | None | su propio estado |

## Índice (`leyes`)

- Sin columnas nuevas.
- `estado`: literal, como hasta ahora.
- `estado_norm`: `normalizar(estado_filtrable(estado, titulo))`. Es interno: solo lo usa
  `construir_filtro`.
- `meta.formato`: `"3." + legalize_estado.huella()` (R5).
- `meta.conteos`: añade `avisos_estado` (entero ≥ 0), validado por `conteos_validos`.
