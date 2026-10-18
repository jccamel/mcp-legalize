# Research: Índice en una base de datos por corpus

Las cifras de referencia son las de la prueba de concepto del 2026-10-18: Python 3.14.8,
SQLite 3.54.0 con FTS5, corpus ES (25.889 leyes) y EU (18.606). Todos sus recuentos
coincidieron con los del servidor actual. Lo que no se midió entonces queda marcado como
**a medir** en la implementación (principio VI).

## R1 — Un fichero por corpus, construido aparte y sustituido entero

**Decision**: cada corpus tiene su base de datos, `indices/index_<repo>.db`. El indexador
nunca escribe sobre la base de datos que puede estar leyendo el servidor:

1. Copia la base de datos vigente a un temporal del mismo directorio.
2. Aplica la pasada (completa o incremental) en una sola transacción.
3. La sustituye con `os.replace`.

**Rationale**:

- Cubre FR-010 sin maquinaria propia: una pasada interrumpida deja el temporal a medias y la
  base de datos vigente intacta.
- El servidor abre en solo lectura y nunca ve una base de datos a medias, sin depender de
  bloqueos ni de ficheros auxiliares de WAL.
- Un lector que ya tenía abierto el fichero anterior sigue leyéndolo hasta que se reinicia,
  igual que hoy con el JSON.
- Copiar 474 MB cuesta del orden de 1 s en SSD (**a medir**), dentro del presupuesto de la
  pasada incremental de la spec 001 (≤ 20 s).

**Alternatives considered**:

- **Escribir en sitio con modo WAL.** Los lectores en solo lectura necesitan escribir el
  fichero `-shm`, y una transacción abierta durante la pasada bloquearía o retrasaría al
  servidor.
- **Una sola base de datos para todos los corpus.** Un fichero corrupto o manipulado costaría
  todos los corpus en lugar de uno (principio IV), y reindexar uno obligaría a copiar los
  demás.

**Riesgo anotado**: en Windows, `os.replace` falla si el servidor tiene el fichero abierto. El
indexador debe informarlo con un mensaje claro y dejar el temporal para reintentar. La CI
corre en Linux.

## R2 — Abrir una base de datos no confiable (FR-004, FR-005)

**Decision**: `legalize_indice.abrir(ruta)` hace, en este orden:

1. Abre con `file:…?mode=ro` (URI) y `check_same_thread=False`.
2. Activa `setconfig(SQLITE_DBCONFIG_DEFENSIVE, True)`, que exige Python 3.12. Desactiva,
   entre otras cosas, el `fts3_tokenizer` de dos argumentos, que este SQLite trae compilado
   (`ENABLE_FTS3_TOKENIZER`).
3. Ejecuta `PRAGMA trusted_schema=OFF`, `PRAGMA query_only=ON` y `PRAGMA cell_size_check=ON`.
4. No llama nunca a `enable_load_extension`.
5. **Comprueba el esquema contra una lista blanca**: `sqlite_master` debe contener
   exactamente las tablas, índices y tablas virtuales del formato, con su SQL canónico. Si
   aparece cualquier otra cosa (disparadores, vistas, tablas de más o un SQL distinto), la
   base de datos se rechaza.
6. Lee `meta.formato` y rechaza otra versión.

El fallo de cualquier paso cuesta ese corpus, con el motivo y el remedio (FR-005).

**Rationale**: la lista blanca cierra lo que no cubren `trusted_schema` y el modo defensivo.
Una base de datos manipulada no puede añadir disparadores ni vistas que alteren las consultas,
porque ni siquiera se llega a consultarla. Comparar el SQL canónico cuesta microsegundos.

**Alternatives considered**:

- **`PRAGMA integrity_check` al arrancar.** Sobre 474 MB tarda segundos. Lo deja
  `cell_size_check` para el momento de leer cada página, y queda disponible como comprobación
  del operador.
- **`immutable=1`.** Promete a SQLite que el fichero no cambia, y el indexador sí lo cambia.

## R3 — Las consultas nunca llevan sintaxis del cliente (FR-006, FR-007)

**Decision**:

- **`texto`**: se tokeniza con `legalize_tokenizer.tokens` (las mismas reglas que hoy, con
  términos de 3 o más caracteres), y cada término va como cadena entrecomillada de FTS5
  (`"término"`), unido con `AND`. Es la misma semántica que la intersección actual.
- **`frase`**: se pliega con `legalize_normalizacion.normalizar` y va como **una sola**
  cadena entrecomillada de FTS5, escapando las comillas internas (`"` → `""`). FTS5 la parte
  con el mismo tokenizador con el que indexó el texto plegado, así que las palabras cortas
  (`de`, `la`) también cuentan en la frase.
- **Título y filtros de texto**: `instr(columna_norm, ?) > 0` sobre columnas ya plegadas al
  indexar. Es exactamente la subcadena de hoy, sin los comodines de `LIKE` que habría que
  escapar.
- **Todo valor del cliente va como parámetro enlazado (`?`)**, nunca concatenado en el SQL.

**Rationale**: con cada término entrecomillado, FTS5 lo trata como texto; un `AND`, `NEAR`,
`*` o paréntesis del cliente no puede funcionar como operador. La prueba de concepto dio
recuentos idénticos con `texto` así construido.

## R4 — El texto buscable

**Decision**: una tabla FTS5 sin contenido (`content=''`) con
`tokenize='unicode61 remove_diacritics 0'`, alimentada con `normalizar(cuerpo)`. Se ejecuta
`optimize` al final de cada pasada. Mantiene `detail=full`, necesario para la búsqueda por
frase.

**Rationale**: el texto ya llega plegado según el ADR 0008. `remove_diacritics 0` impide que
FTS5 pliegue por su cuenta, y `unicode61` trata la `ñ` como letra: «año» y «ano» siguen
siendo distintos, comprobado. Al no guardar contenido, el cuerpo no se duplica; se sigue
leyendo del corpus por su `_ruta`.

**Alternatives considered**: `detail=column` o `detail=none` reducen el tamaño, pero
eliminan la búsqueda por frase, que el usuario eligió a cambio del disco.

## R5 — Artículos preparados al indexar, sin cambiar qué se devuelve (FR-014 a FR-016)

**Decision**:

- **Una pasada lineal por documento** recorre sus encabezados Markdown con las mismas
  plantillas que el servidor (`_ARTICULO_EN_ENCABEZADO_TEMPLATE`, `_CUALQUIER_NUMERO` y la
  terminación sin prefijos) y la misma regla de final: el siguiente encabezado del mismo nivel
  o superior, u otro artículo.
- **Cada aparición se guarda como fila**: número, número plegado, inicio, fin, fin real (el
  final del documento si nada lo marca), orden y **ubicación**. La ubicación es la cadena de
  encabezados de nivel superior que la contienen, unidos con « › »; si aun así dos
  apariciones empatan, se añade « (2) ».
- **`obtener_articulo`**:
  - busca la fila por número, en orden de aparición;
  - sin `capitulo`, devuelve la primera;
  - con `capitulo`, devuelve la de esa ubicación exacta;
  - si el número aparece más de una vez, lista las ubicaciones;
  - **si no hay ninguna fila, recurre a `_localizar_articulo` sobre el fichero**, que es hoy
    la única vía para los documentos sin encabezados (patrones anclados a inicio de línea).

**Rationale**: la paridad queda garantizada por construcción. El caso con encabezados usa las
mismas reglas en una sola pasada, y el caso sin encabezados usa literalmente el mismo código
que hoy. Calcularlo una vez es lineal; llamar a `_localizar_articulo` por cada número
distinto sería cuadrático en los códigos franceses (más de 10.000 artículos por código).
**Un test de paridad compara las dos vías** sobre los bancos de medición de ES, SE, FR y EU.

## R6 — Orden, paginación y equivalencia de filtros (FR-001, FR-002)

**Decision**:

- **Orden.** Los resultados salen en el orden del corpus, que es el de inserción del
  indexador (`ORDER BY n`), y por países en el orden de hoy (el de los nombres de fichero
  de índice).
- **Paginación.** `limite` y `offset` pasan a `LIMIT` y `OFFSET`, con el mismo recorte a
  `MAX_LIMIT`.
- **Fechas, con la semántica actual:**
  - las de publicación dejan pasar los documentos sin fecha;
  - las de derogación y actualización exigen que la fecha exista;
  - los límites superiores comparan la fecha recortada a su precisión
    (`substr(f, 1, length(?)) <= ?`);
  - `anno` es un prefijo.
- **Un solo constructor de la cláusula `WHERE`** lo usan `buscar_ley` y `contar_leyes`
  (principio III, como hoy `_filtrar_docs`).

## R7 — Sellos y registro de seguridad

**Decision**: una tabla `meta(clave TEXT PRIMARY KEY, valor TEXT)` con:

- `formato`: la versión del esquema;
- `patrones`: la huella del escáner;
- `tokenizador`: la huella del tokenizador, que sigue cubriendo la normalización de la
  consulta y del texto indexado;
- `directorio_base`, `pais`, `git_commit` y `generado_en`;
- `seguridad`: el JSON que hoy es `_meta.seguridad`, con las mismas claves.

`check_updates.py` lee esta tabla con `legalize_indice.abrir` y mantiene sus estados.
`POSTINGS` desaparece y aparece `FORMATO` para los índices que siguen en el formato anterior
(FR-011).

La reconstrucción por un cambio de huella sigue la lógica de hoy: cambian las reglas,
reescaneo completo; cambia el tokenizador o el formato, reconstrucción completa.

## R8 — Transición (FR-011)

**Decision**:

- **El servidor solo sirve `index_<repo>.db`.** Si para un corpus solo existe el JSON del
  formato anterior, no se sirve, se avisa con el comando que lo migra y `check_updates`
  informa `FORMATO`.
- **El indexador**, al no encontrar `.db`, construye desde cero y **borra el JSON y los
  postings anteriores** al terminar con éxito.
- **El índice versionado del mock pasa a `indices/index_legalize-mock.db`**: es un binario de
  pocos KB, y se ajustan las excepciones del `.gitignore`.

**Alternatives considered**: seguir sirviendo el JSON durante una transición mantendría dos
implementaciones de cada regla, justo lo que prohíbe el principio III.

## R9 — Python 3.12 como suelo (FR-017)

**Decision**: la matriz de CI pasa a 3.12 y 3.13 (y 3.14, si el lock lo permite). Se
actualizan el README y los comentarios que citan 3.10. Si `abrir` se ejecuta con un Python sin
`setconfig`, debe rechazar servir en vez de abrir sin modo defensivo (FR-004).

## R10 — Tests: un ayudante que construye bases de datos reales

**Decision**: un fixture de `conftest.py`, `instalar_corpus(pais, documentos, cuerpos=None)`,
escribe una base de datos real en `tmp_path` usando el mismo escritor que el indexador, y la
registra en el servidor. Los 20 ficheros de test que hoy inyectan diccionarios en
`_DOCS_POR_PAIS` cambian una o dos líneas de su fixture. **Sus asserts no cambian.**

**Rationale**: así los tests ejercitan la base de datos real, no un sustituto, y la migración
de cada fichero es mecánica y revisable. Los tests cuyo objeto deja de existir (el formato de
postings y la forma del JSON) se sustituyen por sus equivalentes sobre la base de datos; el
plan los enumera.
