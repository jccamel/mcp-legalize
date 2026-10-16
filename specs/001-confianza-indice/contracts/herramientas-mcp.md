# Contrato: herramientas MCP afectadas

Solo se describen los cambios. Todo lo que no aparece aquí se mantiene como hoy.

## `contar_leyes` → `Conteo | ErrorRespuesta`

```text
Conteo {
  total: int
  sin_consultar: list[PaisNoConsultado]   # NUEVO. Vacía si se consultaron todos los países pedidos.
}

PaisNoConsultado {
  pais: str        # código del país, saneado como cualquier metadato
  motivo: str      # uno de: "sin_postings", "ilegibles", "formato_anterior",
                   #         "tokenizador_distinto", "generacion_distinta",
                   #         "consulta_sin_terminos"
}
```

- `sin_consultar` solo puede no estar vacía cuando la consulta lleva `texto`; sin `texto` no se
  consultan postings y la lista siempre está vacía.
- `total` cuenta lo que se pudo consultar. Un cliente que lee `total` sin mirar `sin_consultar`
  obtiene la misma cifra que hoy, así que añadir el campo no rompe a nadie.
- `consulta_sin_terminos` se aplica a todos los países pedidos a la vez, porque la consulta no
  tiene ningún término de al menos tres caracteres (FR-011).
- Sigue devolviendo `ErrorRespuesta` sin índices o con un país desconocido, como hoy.

## `buscar_ley` → `list[DocumentoResumen] | ErrorRespuesta`

El tipo de retorno no cambia. Lo que cambia es cuándo se devuelve cada forma:

| Situación con `texto` | Hoy | Después |
|---|---|---|
| Todos los países pedidos tienen postings utilizables | lista | lista (sin cambios) |
| Algunos sí y otros no | lista parcial, sin señal | lista parcial; `contar_leyes` con los mismos filtros lista los que faltan |
| Ninguno los tiene utilizables | `[]` | `ErrorRespuesta`: `error` explica que la búsqueda por texto no está disponible y `sugerencias` lleva `"<pais>: <motivo>"` por cada país |
| La consulta no tiene términos buscables | `[]` | `ErrorRespuesta` que lo dice |

- El docstring de `buscar_ley` y las instrucciones del servidor dicen que la forma de saber si una
  búsqueda por texto fue completa es llamar a `contar_leyes` con los mismos filtros.
- Las instrucciones del servidor pasan a mencionar `contar_leyes`, que hoy falta en ellas.

## `obtener_ley`, `obtener_articulo` → sin cambio de forma

- Un documento cuya ruta queda fuera del directorio autorizado se trata como ahora se trata una
  ruta rechazada: se registra y el documento llega sin texto.
- Un índice entero cuyo corpus declarado queda fuera de `LEGALIZE_REPOS_DIR` no llega a cargarse
  (FR-005), así que sus leyes no se encuentran, igual que si el índice no existiera. El aviso se
  da al arrancar, no en cada llamada.

## Coherencia con `buscar_ley` (FR-012)

Las dos herramientas siguen saliendo de `_filtrar_docs`. La disponibilidad por país la calcula ese
mismo generador, o una función que comparten, de modo que la lista de `sin_consultar` y el
conjunto de resultados no puedan responder a consultas distintas.
