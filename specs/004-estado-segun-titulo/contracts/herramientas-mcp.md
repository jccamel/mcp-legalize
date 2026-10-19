# Contrato: herramientas MCP

Todos los cambios son aditivos. Un cliente que no conoce los campos nuevos recibe lo mismo que
hoy, salvo las diferencias deliberadas de la tabla final.

## Campo nuevo en las respuestas

```text
DocumentoResumen, LeyCompleta, ArticuloResultado {
  …campos de hoy…
  aviso_estado: str | None   # NUEVO, del servidor: la marca del título que contradice al
                             # estado, literal; None si no la hay
}
```

- Solo cuando el título termina en una marca de derogación (R1) y `estado` es `in_force` o
  está vacío. `estado` no cambia: sigue siendo el de la fuente (ADR 0001).
- La marca se reproduce tal cual (`(repealed)`, `(Revoked)`, `(repealed 5.11.1993 for Act
  except s. 1 …)`); su fecha no se interpreta (Q1).
- Pasa por el saneado de metadatos, con tope de 100 caracteres.

## Filtro `estado` en `buscar_ley` y `contar_leyes`

- `estado="repealed"` encuentra también las leyes con aviso, incluidas las `(revoked)`.
- `estado="in_force"` ya no las encuentra (Q2).
- `contar_leyes` y `buscar_ley` dan el mismo número con los mismos filtros.
- `derogada_desde`/`derogada_hasta` no cambian: estas leyes no tienen fecha de derogación (Q1).

## `estadisticas`

```text
Estadisticas {
  …campos de hoy…            # `estados` sigue contando el estado literal del corpus
  avisos_estado: int         # NUEVO: cuántas leyes tienen aviso
}
```

## Instrucciones del servidor

Explican que `aviso_estado` es del servidor y no de la fuente, que cuando existe el título
contradice al estado y que no se debe presentar esa ley como vigente.

## Diferencias deliberadas con hoy

| Diferencia | Por qué |
|---|---|
| `estado="repealed"` en UK pasa de 0 a 594 leyes; `estado="in_force"` de 86.671 a 86.077 | Q2 |
| Un corpus indexado con el formato 2 no se sirve hasta reindexarlo | R5: cambia lo que guarda `estado_norm` |
