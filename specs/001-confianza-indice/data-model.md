# Data Model: Confianza en el índice

## Fichero de postings: `inverted_<repo>.postings`

Texto UTF-8 con saltos de línea `\n`. Lo escribe `legalize_postings.escribir` de forma atómica
(temporal más `os.replace`) y lo lee `legalize_postings.leer`.

```text
legalize-postings 1                 ← línea 1: firma y versión del formato
tokenizador <huella de 12 hex>      ← línea 2
generacion <32 hex>                 ← línea 3
documentos <N>                      ← línea 4
<id del documento 0>                ← líneas 5 … 4+N: ids, uno por línea, en orden
…
<id del documento N-1>
<término>\t<d1>,<d2>,…              ← una línea por término, en orden lexicográfico
```

- `<d1>` es el primer índice de documento; cada `<dk>` siguiente es la diferencia con el
  anterior, y es ≥ 1.
- Los términos cumplen el patrón del tokenizador (`[0-9a-z]{3,}`).

### Reglas de validación (FR-008)

El fichero se rechaza entero, con el motivo `ilegibles`, si cualquiera de estas reglas falla:

- La primera línea no es exactamente `legalize-postings 1`.
- Faltan cabeceras, o `N` no es un entero no negativo.
- Hay menos de `N` líneas de ids, o algún id está vacío.
- Una línea de término no tiene tabulador, el término no cumple el patrón o aparece repetido.
- Un delta no es un entero, es menor que 1 (o que 0 en el primero), o la suma acumulada llega a
  `N` o más.

Las listas se decodifican de forma perezosa, al consultar el término. Un error de decodificación
en ese momento deja el país como `ilegibles` durante el resto del proceso y genera un aviso.
Validar toda la estructura al cargar costaría lo mismo que decodificarlo todo, que es lo que la
carga perezosa evita.

### Disponibilidad: `legalize_postings.estado(...) -> (postings | None, motivo | None)`

| Motivo | Condición |
|---|---|
| `formato_anterior` | Existe `inverted_<repo>.bin` y no existe `.postings` |
| `sin_postings` | No existe ninguno de los dos |
| `ilegibles` | No se puede leer o incumple las reglas anteriores |
| `tokenizador_distinto` | El tokenizador de la cabecera ≠ `legalize_tokenizer.huella()` |
| `generacion_distinta` | La generación de la cabecera ≠ `_meta.generacion` del JSON, o el JSON no la tiene |

Se evalúan en ese orden y gana el primer motivo que se cumple. Un `None` como motivo significa
que los postings son utilizables.

## Índice JSON: cambios en `_meta`

| Campo | Cambio |
|---|---|
| `generacion` | **Nuevo.** 32 hex. Solo se escribe cuando los postings de esa generación se escribieron con éxito |
| `tokenizador` | Mismo significado; ahora solo se escribe en la misma condición que `generacion` (FR-015) |
| `directorio_base` | Sin cambios de formato. El servidor deja de confiar en él: solo puede elegir dentro de `LEGALIZE_REPOS_DIR` |

`_meta.seguridad` no cambia. `test_the_timestamp_still_moves_with_the_stamp` no se ve afectado.

## Estado del servidor por país

| Tabla | Hoy | Después |
|---|---|---|
| `_INVERTIDO_POR_PAIS` | `dict | None` | `(postings | None, motivo | None)`, cargado bajo demanda como hoy |
| `_RAIZ_POR_PAIS` | — | **Nueva.** La raíz del corpus resuelta y validada contra `LEGALIZE_REPOS_DIR` al cargar el índice. `_resolve_ruta` la lee de aquí y no de `_meta` |

## Transiciones de los postings en el indexador

```text
                      ┌───────────────────────────────┐
 pasada del indexador │ estado() de los postings previos│
                      └───────────────┬───────────────┘
            utilizables ──────────────┼────────────── no utilizables (cualquier motivo)
                 │                                         │
      FUSIONAR: retirar reprocesados,           RECONSTRUIR: tokenizar todos los
      cuarentena, renombrados y huérfanos       documentos que quedan en el JSON
      retirados; añadir reprocesados                       │
                 └──────────────────┬──────────────────────┘
                     escribir .postings (generación nueva)
                                    │ ok                      │ falla
                     escribir JSON con generacion+tokenizador   escribir JSON SIN ellos
                     y borrar .bin si existía                    (la próxima pasada reconstruye)
```

"El índice ya está al día" solo se responde si no hay cambios en disco **y** los postings son
utilizables (FR-003, FR-013).

## `Conteo` y `PaisNoConsultado`

Ver [contracts/herramientas-mcp.md](contracts/herramientas-mcp.md).
