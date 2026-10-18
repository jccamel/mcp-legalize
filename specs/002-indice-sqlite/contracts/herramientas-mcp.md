# Contrato: herramientas MCP

**Todo lo que no aparece aquí se mantiene exactamente como en `main` tras #52** (FR-001): los
nombres, los parámetros, los tipos de respuesta, los campos y los errores.

## `buscar_ley` y `contar_leyes`: parámetro nuevo `frase`

```text
frase: str = ""      # opcional; vacío = no se filtra por frase
```

- Devuelve solo las leyes cuyo cuerpo contiene `frase` como secuencia exacta de palabras,
  plegada como el resto (ADR 0008). `"Arrendamiento URBANO"` equivale a
  `"arrendamiento urbano"`, y `forêt` a `foret`.
- Las palabras cortas cuentan dentro de la frase: `"ley de 1978"` exige el `de`.
- Se combina con `consulta`, `texto` y todos los filtros: deben cumplirse todos.
- Si un país no tiene texto buscable, aparece en `sin_consultar` como hoy con `texto`.
- Si `frase` no tiene ninguna palabra (solo puntuación), se trata como `consulta_sin_terminos`.
- El contenido nunca se interpreta como sintaxis del motor: comillas, `AND`, `*` y paréntesis
  son texto.

## `obtener_articulo`: parámetro nuevo `capitulo` y campo nuevo `ubicaciones`

```text
capitulo: str = ""   # opcional; una de las cadenas devueltas en `ubicaciones`

ArticuloResultado {
  …campos de hoy…
  ubicacion: str | None         # NUEVO: dónde está la aparición devuelta
  ubicaciones: list[str] | None # NUEVO: todas las apariciones, solo si hay más de una
}
```

| Petición | Respuesta |
|---|---|
| Número único, sin `capitulo` | Como hoy; `ubicacion` rellena y `ubicaciones` a `None` |
| Número repetido, sin `capitulo` | La primera aparición, como hoy, y `ubicaciones` con todas, en orden |
| Número repetido, `capitulo` válido | Esa aparición; `ubicaciones` con todas |
| `capitulo` que no corresponde | `error: "Artículo no encontrado"` y `ubicaciones` con las válidas |
| Documento sin encabezados de artículo | Como hoy (recurso anclado a inicio de línea); `ubicacion` a `None` |

- La ubicación es la cadena de encabezados de nivel superior que contienen la aparición,
  unidos con « › » (por ejemplo, «2 kap. Barnpension»). Si dos apariciones empatan, se añade
  « (2) ». Las ubicaciones salen del corpus: pasan por `_sanitize_metadata`.
- El servidor no interpreta nombres de capítulo: solo compara con las ubicaciones que él
  mismo devolvió.

## Diferencias deliberadas con hoy (FR-002)

| Diferencia | Por qué |
|---|---|
| Los motivos `formato_anterior` y `generacion_distinta` de `sin_consultar` desaparecen | El formato anterior hace que el corpus entero no se sirva, y la generación ya no existe |
| Un corpus en el formato anterior no se sirve hasta reindexarlo | R8: dos implementaciones de cada regla violarían el principio III |

Ninguna diferencia más es aceptable: el banco de paridad (quickstart §2) lo comprueba.
