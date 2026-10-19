# Contrato: herramientas MCP

Todos los cambios son aditivos (FR-009). Un cliente que no conoce los campos ni los
parámetros nuevos recibe lo mismo que hoy, salvo la diferencia deliberada de Q1.

## Campo nuevo en las respuestas

```text
DocumentoResumen, LeyCompleta, ArticuloResultado {
  …campos de hoy…
  fecha_fin_vigencia: str | None   # NUEVO: la fecha en que la ley dejó o dejará de estar
                                   # en vigor, tal como la da la fuente; None si no la da
}
```

- Puede ser pasada o futura. El servidor no la compara con la fecha de hoy ni deduce de ella el
  estado (Q3): una ley `in_force` con fecha futura sigue siendo `in_force`.
- Pasa por el saneado de metadatos, como el resto de fechas.

## Parámetros nuevos en `buscar_ley` y `contar_leyes`

```text
fin_vigencia_desde: str = ""   # AAAA, AAAA-MM o AAAA-MM-DD, inclusivo
fin_vigencia_hasta: str = ""   # inclusivo con la precisión del límite: "2027" es todo 2027
```

- La misma semántica que `derogada_desde`/`derogada_hasta` y `actualizada_desde`/`hasta`:
  exigen que la fecha exista, así que una ley sin fin de vigencia no los cumple.
- Se combinan con todos los demás filtros. Para separar expiradas de derogadas, con `estado`.
- `contar_leyes` con los mismos filtros devuelve el mismo número que resultados devuelve
  `buscar_ley` (FR-007).

## Diferencias deliberadas con hoy

| Diferencia | Por qué |
|---|---|
| `derogada_desde`/`derogada_hasta` encuentran también las leyes `repealed` que solo traen `end_of_validity` (1.061 en EU) | Q1: hoy excluyen en silencio un corpus entero |
| Un corpus indexado con el formato 1 no se sirve hasta reindexarlo | El esquema cambia (ADR 0009) |

`fecha_derogacion` sigue sin devolverse en ninguna respuesta; solo se usa para filtrar.
Ninguna diferencia más es aceptable: el banco de paridad lo comprueba (quickstart §2).
