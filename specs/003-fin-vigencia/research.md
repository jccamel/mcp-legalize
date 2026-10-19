# Research: Fin de vigencia

Decisiones técnicas de la spec 003. Cada una cita el código que la condiciona.

## R1. Dónde se decide qué fecha va a cada campo

- **Decision**: en el indexador, en `_build_entry` (`scripts/update_index.py`), junto al resto
  de la traducción de claves del frontmatter (`repeal_date` → `fecha_derogacion`, `status` →
  `estado`…). Allí se añade `end_of_validity` → `fecha_fin_vigencia`, y la regla de Q1: si
  `estado` es `repealed` y no hay `repeal_date`, `fecha_derogacion` toma la misma fecha.
- **Rationale**: es el único sitio que hoy decide de qué clave de la fuente sale cada campo del
  índice (principio III). El servidor sirve lo que el índice guarda y no reinterpreta.
- **Alternatives considered**: resolver Q1 en el servidor, al filtrar (`fecha_derogacion` vacía
  ⇒ mirar `fecha_fin_vigencia` si `repealed`): pondría una regla de la fuente en dos sitios y
  haría el filtro más caro; resolverla en `Escritor`: el escritor no conoce claves de la
  fuente, solo campos del índice.

## R2. Qué cuenta como fecha

- **Decision**: `end_of_validity` se acepta si tiene forma `AAAA-MM-DD`, `AAAA-MM` o `AAAA` y,
  en las dos primeras, es una fecha que existe. Cualquier otro valor deja el campo vacío para
  esa ley (FR-001). La comprobación es una función del indexador.
- **Rationale**: el filtro compara cadenas recortadas a la precisión del límite (defecto #6);
  un valor que no es una fecha daría resultados sin sentido en lugar de ninguno. Medido: las
  2.267 fechas actuales tienen forma `AAAA-MM-DD`, así que la regla no descarta ninguna.
- **Alternatives considered**: guardar el valor tal cual, como hoy `fecha_publicacion`; validar
  también las demás fechas — fuera de alcance, y cambiaría el banco de paridad.

## R3. Esquema e índices existentes

- **Decision**: columna nueva `fecha_fin_vigencia TEXT NOT NULL` en `leyes`, tratada como campo
  opcional (vacía si no hay fecha). `FORMATO` pasa de `"1"` a `"2"`.
- **Rationale**: ADR 0009: un cambio de esquema sube el formato; `abrir` rechaza la lista
  blanca anterior (`formato_distinto`) y `check_updates` informa `FORMATO` con el remedio de
  siempre, que reconstruye el índice sin flags (FR-012).
- **Consecuencia operativa**: tras actualizar el código, un corpus no se sirve hasta
  reindexarlo. El orden para el operador es reindexar y después reiniciar el servidor; queda
  en el contrato del operador y en los README.
- **Alternatives considered**: guardar la fecha en una tabla aparte o en `meta` para no tocar
  `leyes`: rompe el «una fila por ley» y complica cada consulta; aceptar índices de formato 1
  sin la columna: dos esquemas que mantener, lo que el ADR 0009 descartó.
- **Deuda que se paga aquí**: `Escritor.poner_ley` inserta por posición, con un recorte
  `_CAMPOS_TEXTO[:13]` que depende del orden de las columnas. Añadir una columna obliga a
  tocarlo; pasa a insertar por nombre de columna, que no depende del orden.

## R4. Filtros

- **Decision**: `fin_vigencia_desde` y `fin_vigencia_hasta` en `buscar_ley` y `contar_leyes`,
  construidos en `legalize_indice.construir_filtro` con la misma función que los demás
  rangos de fecha (`rango_fechas(..., exige=True)`): inclusivos, con la precisión del límite,
  y exigiendo que la fecha exista. Los parámetros se añaden al final de las firmas.
- **Rationale**: un solo constructor de `WHERE` para buscar y contar (FR-007, principio III);
  al final de la firma, ninguna llamada posicional existente cambia de significado.
- **Alternatives considered**: un único filtro `vigente_en=<fecha>`: responde otra pregunta
  («¿estaba en vigor el día X?») que necesitaría también la fecha de entrada en vigor, fuera
  de alcance.

## R5. Campo en las respuestas

- **Decision**: `fecha_fin_vigencia: Optional[str]` en `DocumentoResumen`, `LeyCompleta` y
  `ArticuloResultado`; `None` si la ley no la tiene. Pasa por `_sanitize_metadata` con el mismo
  límite que las demás fechas (`max_len=50`).
- **Rationale**: aditivo (FR-009), saneado como todo metadato (FR-011), clave en castellano
  (ADR 0001, FR-010).

## R6. Paridad

- **Decision**: el banco de la spec 002 se ejecuta contra la referencia de `main`. Se ignora el
  campo nuevo (`CAMPOS_NUEVOS`), y las diferencias que queden deben ser exactamente las de Q1:
  peticiones con `derogada_desde`/`derogada_hasta` que ahora encuentran leyes europeas
  `repealed`. Cada diferencia se comprueba contra esa explicación antes de aceptarla.
- **Rationale**: principio I; las diferencias deliberadas se enumeran, no se suponen.

## R7. Índice SQL sobre la columna nueva

- **Decision**: ninguno de entrada. `fecha_derogacion` tampoco lo tiene; se mide el filtro
  nuevo sobre EU y se añade solo si supera el objetivo de la spec 002 (p95 < 5 ms).
- **Rationale**: principio VI: medir antes de fijar.
