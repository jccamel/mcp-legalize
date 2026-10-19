# 0012 — Cuando el título contradice al estado, un aviso del servidor; el estado no se toca

- **Estado:** Aceptada
- **Fecha:** 2026-10-19
- **Ámbito:** `legalize_estado.py`, `legalize_indice.py` (`estado_norm`, `FORMATO`, `contar`), `mcp_legalize.py` (`aviso_estado`, `avisos_estado`)

## Contexto

El corpus del Reino Unido (86.671 leyes) trae todas sus leyes con `status: in_force` y marca al
final del título las que ya no lo están. Medido el 2026-10-19: 594 títulos acaban en
`(repealed)` (380), `(revoked)` (34), `(repealed d.m.aaaa)` (176) o una variante irregular (4),
una de ellas una derogación parcial (`(repealed 5.11.1993 for Act except s. 1 …)`). Ninguna trae
`repeal_date`, `repealed_by` ni `end_of_validity`. En es, eu, fr y se no hay ninguna marca.

El cliente leía `estado: in_force` y presentaba esas leyes como vigentes, y
`estado="repealed"` no encontraba ninguna. Corregir `estado` contradiría el ADR 0001 (los
valores del corpus se reproducen, nunca se normalizan) y la Q3 de la spec 003 (el estado no se
deduce de otro dato).

## Decisión

- `estado` se sirve tal como lo da la fuente.
- Cuando el título termina en una marca de derogación (un paréntesis que empieza por `repealed`
  o `revoked`, solo con letras ASCII) y `estado` es `in_force` o vacío, el servidor añade su
  propio campo, `aviso_estado`, con la marca literal y saneada. La fecha de la marca no se
  interpreta ni se usa como fecha de derogación.
- El filtro de estado archiva esas leyes como `repealed` en `estado_norm`, la columna interna
  que solo lee el filtro: `estado="repealed"` las encuentra y `estado="in_force"` no.
- `estadisticas` cuenta `estados` literal y da aparte `avisos_estado`.
- La regla vive solo en `legalize_estado.py`, que usan el índice y el servidor. `FORMATO` lleva
  su huella.

## Alternativas consideradas

| Alternativa | Por qué no |
|---|---|
| Sobrescribir `estado` con `repealed` al indexar | Contradice el ADR 0001 y la Q3 de la spec 003: el servidor diría algo distinto de la fuente sin señalarlo |
| Solo avisar en las instrucciones del servidor | Los filtros seguirían excluyendo en silencio las 594 leyes |
| Guardar el aviso en una columna del índice | Un dato más que un índice manipulado podría desalinear del título; calcularlo al servir lo saca de un título que ya se sanea |
| Calcular el filtro al consultar, con una función SQL | Recorre las 86.671 filas en cada consulta con estado |
| Una huella aparte en `meta`, como la del tokenizador | Tres sitios nuevos que comprobar y un estado degradado más que inventar; `FORMATO` ya invalida y reconstruye |

## Consecuencias

- **Positivas:**
  - el cliente no presenta como vigente una ley que su título da por derogada, y ve las
    excepciones de una derogación parcial tal cual;
  - `estado="repealed"` encuentra las 594 leyes en UK;
  - el banco de paridad no cambia en es, eu, fr y se.
- **Negativas / costes:**
  - `estadisticas` (86.671 `in_force` en UK) y `contar_leyes(estado="in_force")` (86.077) no
    coinciden; `avisos_estado` explica la diferencia;
  - cambiar la regla obliga a reindexar todos los corpus, porque cambia `FORMATO`.
- **Reglas que se derivan:**
  - otra forma de marcar una derogación en el título entra en `legalize_estado.py`, con su
    medición sobre todos los corpus;
  - `estado_norm` deja de ser «`estado` plegado» y pasa a ser «el estado bajo el que se
    filtra»: no se sirve nunca.

## Cómo revertirla

Quitar `legalize_estado.py` y sus usos en `legalize_indice.poner_ley`, `contar`,
`conteos_validos` y `FORMATO`, y en `mcp_legalize._estado_y_vigencia`, `Estadisticas` y las
instrucciones. Reindexar todos los corpus.
