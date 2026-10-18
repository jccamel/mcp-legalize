# Feature Specification: Índice en una base de datos por corpus

**Feature Branch**: `feat/002-indice-sqlite`

**Created**: 2026-10-18

**Status**: Draft

**Input**: User description: "Índice en SQLite + FTS5: sustituir el índice JSON en memoria y
los postings de texto propio por una base de datos por corpus, manteniendo el contrato de las
herramientas MCP." La motivación es la prueba de concepto del 2026-10-18 (memoria
`prueba-sqlite-fts5`), cuyos recuentos coinciden con los del servidor actual. El usuario ha
aceptado los costes: suelo de Python 3.12, unas cinco veces más de disco a cambio de la
búsqueda por frase, y reescribir el indexador y la capa de consulta.

## Contexto

El índice actual es un JSON que se carga entero en memoria, acompañado de un fichero de
postings con formato propio. Funciona y se ha endurecido mucho, pero casi todos los defectos
corregidos desde el 2026-10-16 vinieron de infraestructura de índice escrita a mano:
deserialización insegura, postings que se perdían en una pasada incremental, generación y
orden de escritura, comparación de fechas, ids en minúsculas, un validador que duplicaba el
patrón del tokenizador, artículos que se localizaban en cada consulta y un esquema rígido que
no acoge los campos nuevos de la spec.

La prueba de concepto, medida sobre el corpus español (25.889 leyes):

| | Hoy | Con base de datos |
|---|---|---|
| Arranque | 484 ms | 0,2 ms |
| Memoria tras las consultas | 363 MB | 27 MB |
| Primera búsqueda por texto | 241 ms | 0,07 ms |
| Filtros | 2–4 ms | 0,5–0,7 ms |
| Artículo | 0,5 ms (hasta 47 ms en códigos franceses) | 0,08 ms |
| Búsqueda por frase exacta | no existe | sí |
| Disco | ~96 MB | 474 MB |

## User Scenarios & Testing *(mandatory)*

Actores:

- **Cliente MCP**: el modelo que consulta legislación.
- **Operador**: quien clona los corpus, indexa y comprueba la frescura.
- **Atacante**: quien controla el contenido de un corpus o puede escribir en el directorio de
  índices (principio II).

### User Story 1 - El cliente no nota el cambio, salvo en lo que mejora (Priority: P1)

Las siete herramientas devuelven lo mismo que hoy ante las mismas peticiones: los mismos
documentos, los mismos recuentos, el mismo texto de cada artículo, los mismos errores y los
mismos campos. Lo que cambia es la memoria, el tiempo de arranque y el tiempo de respuesta.

**Why this priority**: es la condición para migrar. Una migración que cambie respuestas en
silencio rompería al cliente, y el principio I no lo permite.

**Independent Test**: lanzar un banco fijo de peticiones contra los corpus ES, SE, FR y EU con
el índice actual y con el nuevo, y comparar las respuestas campo a campo.

**Acceptance Scenarios**:

1. **Given** los cuatro corpus indexados con el sistema actual y con el nuevo, **When** se
   lanza el banco de peticiones (búsquedas por título, por texto, filtros, fechas, conteos,
   leyes, artículos, ids en minúsculas y errores), **Then** las respuestas coinciden. Las
   únicas excepciones son las diferencias deliberadas que la spec enumera.
2. **Given** el servidor arrancado sin ninguna consulta, **When** se mide su memoria, **Then**
   es una fracción de la actual y no crece con el número de corpus cargados.
3. **Given** cualquier consulta del banco, **When** se cronometra, **Then** responde en menos
   tiempo que hoy o en el mismo.

---

### User Story 2 - El índice sigue siendo entrada no confiable (Priority: P1)

Quien puede escribir en el directorio de índices planta una base de datos manipulada. Abrirla
y consultarla no puede ejecutar código, escribir en disco, leer ficheros fuera del corpus
autorizado ni afectar a los demás corpus.

**Why this priority**: es el principio II. Un formato nuevo no puede abrir el agujero que la
spec 001 cerró.

**Independent Test**: un banco de bases de datos manipuladas (esquema con disparadores o vistas,
tokenizador registrado, páginas corruptas, rutas que escapan, tipos inesperados, otro formato)
y comprobar en cada caso que no hay efectos fuera del proceso, que ese corpus degrada con un
motivo y que los demás responden.

**Acceptance Scenarios**:

1. **Given** una base de datos cuyo esquema intenta ejecutar algo al consultarla, **When** el
   cliente busca, **Then** no se ejecuta nada y el corpus queda marcado como no utilizable.
2. **Given** una base de datos corrupta o de otra versión, **When** el servidor arranca,
   **Then** ese corpus no se sirve, se avisa al operador con el remedio y los demás siguen.
3. **Given** una ruta de documento que escapa de `LEGALIZE_REPOS_DIR`, **When** se pide la
   ley, **Then** no se sirve, igual que hoy.

---

### User Story 3 - Buscar una frase exacta (Priority: P2)

El cliente busca "arrendamiento urbano" como frase y recibe solo las leyes que contienen esas
palabras seguidas. Hoy recibe las que contienen las dos en cualquier sitio: 573 leyes en ES,
frente a 4 que tienen la frase.

**Why this priority**: es la capacidad nueva que justifica el coste en disco, y la que más
reduce los resultados irrelevantes en las búsquedas jurídicas.

**Independent Test**: en un corpus sintético con la frase en unos documentos y las palabras
separadas en otros, la búsqueda por frase devuelve solo los primeros, y la búsqueda actual
sigue devolviendo ambos.

**Acceptance Scenarios**:

1. **Given** documentos con "arrendamiento urbano" seguido y otros con las dos palabras
   separadas, **When** el cliente busca la frase, **Then** solo recibe los primeros.
2. **Given** la misma búsqueda sin pedir frase, **When** se ejecuta, **Then** el resultado es
   el de hoy. Ninguna petición existente cambia de significado.
3. **Given** una frase con acentos o mayúsculas distintos ("ARRENDAMIENTO URBANO", "forêt
   domaniale"), **When** se busca, **Then** se pliega como el resto (ADR 0008).

4. **Given** una petición con `frase` y con otros filtros (`texto`, país, fechas), **When** se
   ejecuta, **Then** se combinan como se combinan hoy `texto` y los filtros: todos a la vez.

---

### User Story 4 - Mantener los índices sin maquinaria propia (Priority: P2)

El operador hace `git pull` y reindexa. La pasada incremental actualiza solo lo que cambió, y
una interrupción a mitad deja el índice anterior intacto, no uno a medias. Un campo nuevo de la
spec se añade al índice sin inventar sellos.

**Why this priority**: es la otra mitad de la motivación. Elimina la familia de defectos que
la spec 001 tuvo que cerrar (fusión, generación, orden de escritura).

**Independent Test**: la propiedad de la spec 001 (incremental igual a completo tras una
secuencia de altas, bajas, cambios, cuarentenas y renombrados), más una interrupción simulada
a mitad de pasada.

**Acceptance Scenarios**:

1. **Given** cualquier secuencia de cambios en el corpus, **When** se reindexa de forma
   incremental, **Then** el índice es igual al de una reconstrucción completa.
2. **Given** una pasada interrumpida a mitad, **When** el servidor arranca, **Then** sirve el
   índice anterior completo.
3. **Given** un índice del formato actual (JSON más postings), **When** el operador ejecuta el
   indexador, **Then** se construye el nuevo sin pasos manuales, y `check_updates` lo informa
   hasta entonces.

---

### User Story 5 - Los artículos se preparan una vez (Priority: P3)

Al indexar, cada artículo queda localizado con su posición y su lugar en la estructura
(capítulo, título…). `obtener_articulo` deja de recorrer el documento en cada consulta, y el
truncado por `contexto_chars` deja de depender de que el final no esté marcado.

**Why this priority**: es lo que hace rápido el caso de los códigos franceses, y lo que
permitiría resolver los números de artículo repetidos de los capítulos suecos.

**Independent Test**: las mediciones de extracción de artículos ya hechas (ES, SE, FR, EU)
repetidas con el índice nuevo: mismos resultados y ningún desborde, corte ni prefijo fantasma.

**Acceptance Scenarios**:

1. **Given** cualquier artículo del banco de medición, **When** se pide, **Then** el texto es
   idéntico al de hoy.
2. **Given** un número de artículo que se repite en el documento (los `1 §` de cada capítulo
   sueco), **When** se pide sin más, **Then** se devuelve la primera aparición, como hoy, y la
   respuesta lista todas las apariciones con su ubicación en la estructura (por ejemplo,
   «2 kap. Barnpension»).
3. **Given** esa lista, **When** el cliente vuelve a pedir el artículo indicando en `capitulo`
   una de las ubicaciones devueltas, **Then** recibe esa aparición.
4. **Given** una `capitulo` que no corresponde a ninguna aparición, **When** se pide, **Then**
   la respuesta es «artículo no encontrado» con la lista de ubicaciones válidas, nunca otra
   aparición elegida en silencio.

### Edge Cases

- Un corpus enorme (el mayor fichero europeo ocupa 46 MB): indexar no puede superar la memoria
  de hoy (4,15 GB de pico en ES).
- Dos procesos leen el índice mientras el indexador lo reescribe: cada lectura ve una versión
  completa, la anterior o la nueva.
- Un corpus en cuarentena parcial: las leyes excluidas no aparecen en ninguna búsqueda,
  tampoco por frase.
- Un índice de un corpus con la misma ley repetida por identificador: se resuelve como hoy
  (id derivado de la ruta).
- Consultas con caracteres que el buscador interpreta como operadores (comillas, `AND`, `*`,
  paréntesis): se tratan como texto, nunca como sintaxis del motor.
- Un `LEGALIZE_INDICES_DIR` que mezcla índices del formato actual y del nuevo durante la
  transición.

## Requirements *(mandatory)*

### Functional Requirements

**Equivalencia (historia 1)**

- **FR-001**: Las siete herramientas MUST conservar nombres, parámetros, tipos de respuesta y
  campos actuales. Ninguna petición existente MUST cambiar de significado.
- **FR-002**: Para el banco de peticiones fijado en el plan, las respuestas MUST coincidir con
  las del sistema actual sobre los cuatro corpus. Cada diferencia deliberada MUST estar
  enumerada y justificada en el plan.
- **FR-003**: Se conservan todas las reglas vigentes:
  - plegado (ADR 0008, la `ñ` como letra);
  - saneado de metadatos y envoltorio `<untrusted_content>`;
  - raíz `LEGALIZE_REPOS_DIR`;
  - ids sin distinguir mayúsculas y ambigüedad por mayúsculas;
  - fechas inclusivas con la precisión del límite;
  - localización de artículos por encabezado sin prefijos;
  - `sin_consultar`, `texto_truncado`, `estado_texto` y `ultima_modificacion`;
  - escáner y cuarentena por fichero, con su registro en el índice.

**Seguridad (historia 2)**

- **FR-004**: La base de datos MUST tratarse como entrada no confiable. Abrirla y consultarla
  MUST NOT poder ejecutar código, escribir, cargar extensiones ni usar el esquema para alterar
  las consultas. Si no se pueden garantizar esas condiciones en la plataforma, el corpus MUST
  NOT servirse.
- **FR-005**: Una base de datos ilegible, de otra versión o con un esquema inesperado MUST
  costar solo ese corpus, con un aviso al operador que diga cómo regenerarla.
- **FR-006**: Ninguna entrada del cliente MUST llegar al motor como sintaxis de consulta.

**Frase (historia 3)**

- **FR-007**: `buscar_ley` y `contar_leyes` MUST aceptar un parámetro nuevo y opcional,
  `frase`, que devuelve solo las leyes cuyo cuerpo contiene ese texto como frase exacta, plegada
  igual que el resto (ADR 0008). Se combina con todos los demás filtros, `texto` incluido.
  Ninguna petición existente cambia de significado (decisión Q1).
- **FR-008**: `contar_leyes` MUST aceptar la misma búsqueda por frase que `buscar_ley` y salir
  del mismo filtro (principio III).

**Mantenimiento (historia 4)**

- **FR-009**: Tras cualquier pasada del indexador, el índice MUST contener exactamente las
  leyes y términos de los documentos aceptados, ni más ni menos.
- **FR-010**: Una pasada interrumpida MUST dejar utilizable el índice anterior completo.
- **FR-011**: Pasar del formato actual al nuevo MUST hacerse ejecutando el indexador, sin pasos
  manuales. Los índices del formato actual MUST NOT servirse una vez existe el nuevo, y
  `check_updates.py` MUST informar de los que quedan por migrar, con su remedio.
- **FR-012**: El índice MUST registrar con qué reglas se construyó (escáner, tokenizador,
  formato) y MUST reconstruirse cuando cambien, como hoy.
- **FR-013**: Añadir un campo del frontmatter al índice MUST NOT requerir más que declararlo y
  reindexar.

**Artículos (historia 5)**

- **FR-014**: La localización de cada artículo MUST calcularse al indexar con las mismas reglas
  que hoy, y `obtener_articulo` MUST devolver el mismo texto que hoy para el banco de medición.
- **FR-015**: Cuando el número pedido aparece más de una vez como encabezado de artículo,
  `obtener_articulo` MUST devolver la primera aparición, como hoy, y MUST listar todas las
  apariciones con su ubicación en la estructura, en un campo nuevo y opcional de la respuesta
  (decisión Q2).
- **FR-016**: `obtener_articulo` MUST aceptar un parámetro nuevo y opcional, `capitulo`, cuyo
  valor es una de las ubicaciones devueltas en esa lista, y MUST devolver esa aparición. Una
  `capitulo` que no corresponde a ninguna devuelve «artículo no encontrado» con la lista de
  ubicaciones válidas. El servidor no interpreta nombres de capítulo que no haya producido él.

**Transversales**

- **FR-017**: El suelo de Python pasa a 3.12 y la CI MUST cubrir de 3.12 a 3.13 (más las
  versiones posteriores que ya se prueban).
- **FR-018**: Toda cifra del README y del código sobre tamaños o tiempos MUST actualizarse con
  las medidas nuevas (principio VI).
- **FR-019**: Los ADR 0003 y 0007 MUST marcarse como sustituidos por un ADR nuevo que registre
  esta decisión y sus medidas.

### Key Entities *(include if feature involves data)*

- **Base de datos de un corpus**: un fichero por corpus en el directorio de índices. Contiene
  las leyes, sus artículos, el texto buscable y los sellos con los que se construyó.
- **Ley**: los metadatos que hoy están en el JSON, más los campos nuevos de la spec
  (`estado_texto`, `ultima_modificacion` y, cuando se decida, `end_of_validity`).
- **Artículo**: número, posición en el cuerpo, lugar en la estructura y si su final lo marca
  el documento o no.
- **Texto buscable**: el cuerpo plegado de cada ley aceptada, con posiciones para la búsqueda
  por frase.
- **Sellos**: las huellas del escáner y del tokenizador, la versión del formato y el registro
  de seguridad que hoy está en `_meta.seguridad`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El 100% de las peticiones del banco devuelven la misma respuesta que hoy en los
  cuatro corpus, salvo las diferencias enumeradas en el plan.
- **SC-002**: La memoria residente del servidor con ES, SE, FR y EU cargados es al menos 5
  veces menor que hoy.
- **SC-003**: El servidor responde a su primera consulta en menos de 50 ms desde que arranca,
  frente a casi medio segundo hoy.
- **SC-004**: Ninguna consulta del banco tarda más que hoy. Las búsquedas por texto y los
  artículos tardan menos de 5 ms en el 95% de los casos.
- **SC-005**: Ninguna base de datos del banco de manipuladas produce efectos fuera del proceso
  de consulta.
- **SC-006**: La búsqueda por frase devuelve solo documentos que contienen la frase en el 100%
  de los casos del banco.
- **SC-007**: Indexar el corpus español completo no tarda más ni ocupa más memoria que hoy
  (150 s y 4,15 GB). El tamaño en disco queda registrado.
- **SC-008**: En el corpus sueco, el 100% de las apariciones de un número de artículo
  repetido se pueden obtener eligiendo su ubicación.

## Clarifications

### Session 2026-10-18

- Q: ¿Cómo pide el cliente una búsqueda por frase? → A: un parámetro nuevo y opcional,
  `frase`, en `buscar_ley` y `contar_leyes`, que se combina con los demás filtros (FR-007).
  Se descartaron las comillas dentro de `texto`, porque cambiarían el significado de
  peticiones existentes, y un booleano `exacta`, porque no permite combinar una frase con
  palabras sueltas.
- Q: ¿Qué pasa con los números de artículo repetidos? → A: se devuelve la primera aparición,
  como hoy, con la lista de todas y su ubicación, y un parámetro opcional `capitulo` permite
  elegir otra (FR-015, FR-016). El valor de `capitulo` es una de las ubicaciones que devuelve
  el propio servidor, así que no hace falta ninguna regla para interpretar nombres de capítulo.

## Assumptions

- El contrato de las herramientas es el de `main` tras #52.
- El escáner y la cuarentena no cambian de reglas en esta spec. El falso positivo «User:» del
  corpus europeo se trata aparte.
- `spec_version` (leer `.legalize.yml` y rechazar versiones posteriores) y `end_of_validity`
  (con las expiradas separadas de las derogadas, como decidió el usuario) se tratan aparte. Si
  el plan los incluye porque cuestan una columna, se dirá allí.
- La prueba de concepto del 2026-10-18 es la referencia de rendimiento. El plan vuelve a medir
  con la implementación real.
- Los clones locales de ES, SE, FR y EU siguen disponibles para las mediciones.
