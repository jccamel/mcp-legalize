# Feature Specification: Confianza en el índice

**Feature Branch**: `001-confianza-indice`

**Created**: 2026-10-16

**Status**: Draft

**Input**: User description: "Confianza en el índice: agrupar los defectos #1 (una reindexación
incremental deja el índice invertido solo con los documentos de esa pasada), #2 (la raíz contra la
que se valida una ruta sale del propio índice), #3 (los postings se deserializan con un formato que
puede ejecutar código) y #8 (un cambio de tokenizador se detecta pero nunca fuerza la
reconstrucción, y el remedio propuesto no lo resuelve). Sustituye al ADR 0003." Se añade el #10
(la búsqueda por texto devuelve cero tanto si no hay coincidencias como si no se puede buscar),
porque decide qué ve el cliente cuando los postings no son utilizables.

## User Scenarios & Testing *(mandatory)*

Actores:

- **Cliente MCP**: el modelo que consulta legislación y razona sobre lo que recibe como si fuera
  la respuesta completa.
- **Operador**: la persona que clona corpus, ejecuta el indexador y comprueba la frescura de los
  índices.
- **Atacante**: quien controla el contenido de un corpus o puede escribir en el directorio de
  índices. Es el modelo de amenaza del proyecto (principio II de la constitución).

### User Story 1 - La búsqueda por texto no pierde documentos al actualizar (Priority: P1)

El operador hace `git pull` de un corpus y ejecuta el indexador, que solo procesa los ficheros
que cambiaron. A partir de ese momento, el cliente que busca por términos del cuerpo tiene que
encontrar todos los documentos que los contienen, no solo los modificados en la última pasada.

**Why this priority**: es un defecto de pérdida de datos silenciosa en el flujo de mantenimiento
que el README recomienda, y afecta a cualquier instalación que se actualice. El cliente recibe
una respuesta parcial presentada como completa, lo que viola el principio I.

**Independent Test**: indexar un corpus de varios documentos, modificar uno, reindexar de forma
incremental y comprobar que una búsqueda por un término de un documento no modificado lo sigue
devolviendo, y que `contar_leyes` da la misma cifra que tras una reconstrucción desde cero.

**Acceptance Scenarios**:

1. **Given** un corpus indexado con los documentos A y B, ambos con el término "arrendamiento",
   **When** se modifica solo B y se reindexa de forma incremental, **Then** buscar
   "arrendamiento" devuelve A y B.
2. **Given** el mismo corpus, **When** se modifica B quitando el término "arrendamiento" y se
   reindexa, **Then** buscar "arrendamiento" devuelve solo A.
3. **Given** un documento que pasa a cuarentena en una reindexación incremental, **When** se
   busca un término que solo contenía ese documento, **Then** no aparece en los resultados.
4. **Given** un documento eliminado del disco y reindexado con retirada de huérfanos, **When**
   se busca un término suyo, **Then** no aparece en los resultados.
5. **Given** un índice ya al día cuyo fichero de postings falta, **When** el operador ejecuta el
   indexador, **Then** los postings se reconstruyen y el indexador no responde "ya está al día".

---

### User Story 2 - Un índice manipulado no puede leer fuera del corpus (Priority: P1)

Un atacante que puede escribir un fichero de índice declara como directorio base la raíz del
sistema y como ruta de un documento un fichero del sistema. El servidor no debe servir nunca un
fichero que esté fuera del directorio de corpus autorizado por el operador, diga lo que diga el
índice.

**Why this priority**: es una lectura arbitraria de ficheros, reproducida (`/etc/hosts` servido
por `obtener_ley`), que contradice lo que promete el README y el principio II.

**Independent Test**: colocar un índice cuyo directorio base sea "/" y una entrada cuya ruta sea
"etc/hosts", y comprobar que `obtener_ley` y `obtener_articulo` no devuelven su contenido y que
el rechazo queda registrado.

**Acceptance Scenarios**:

1. **Given** un índice con directorio base "/" y ruta "etc/hosts", **When** el cliente pide esa
   ley, **Then** no recibe el contenido del fichero y el rechazo queda registrado.
2. **Given** un índice con un directorio base relativo que escapa con "../", **When** el cliente
   pide un documento, **Then** no se sirve nada fuera del directorio autorizado.
3. **Given** un índice legítimo generado por el indexador para un corpus dentro del directorio
   autorizado, **When** el cliente pide una ley, **Then** se sirve igual que hoy.
4. **Given** un índice legítimo cuyo corpus está fuera del directorio autorizado, **When** el
   servidor arranca, **Then** el operador recibe un aviso que nombra el índice y explica cómo
   autorizarlo, y ese corpus no se sirve; los demás sí.

---

### User Story 3 - Cargar los postings no puede ejecutar código (Priority: P1)

Un atacante que puede escribir en el directorio de índices sustituye el fichero de postings de un
país por uno manipulado. La primera búsqueda por texto en ese país no debe ejecutar nada; en el
peor caso, la búsqueda en ese país deja de estar disponible y se dice así.

**Why this priority**: es ejecución de código en el proceso del servidor a partir de un fichero
que el propio código declara no confiable, la consecuencia más grave posible del modelo de
amenaza.

**Independent Test**: escribir un fichero de postings con un contenido que, en el formato
anterior, ejecutaría código al cargarse, buscar por texto en ese país y comprobar que no se
ejecuta nada y que el cliente recibe la señal de búsqueda no disponible.

**Acceptance Scenarios**:

1. **Given** un fichero de postings manipulado, **When** el cliente busca por texto en ese país,
   **Then** no se ejecuta código, el resto de países responden con normalidad y el cliente sabe
   que en ese país no se pudo buscar.
2. **Given** un fichero de postings en el formato anterior, generado por una versión previa,
   **When** el servidor intenta usarlo, **Then** no lo carga, avisa al operador de que hay que
   reindexar y trata la búsqueda en ese país como no disponible.
3. **Given** un fichero de postings truncado o con una estructura inesperada, **When** se busca
   por texto, **Then** el comportamiento es el mismo que en el escenario 1.

---

### User Story 4 - El cliente distingue "no hay resultados" de "no se pudo buscar" (Priority: P2)

El cliente busca por términos del cuerpo en un país cuyos postings no existen, no se pueden leer
o se construyeron con otro tokenizador. Hoy recibe una lista vacía y `contar_leyes` responde
cero, exactamente igual que si no hubiera coincidencias. Tiene que poder distinguir las dos
situaciones.

**Why this priority**: sin esto, las historias 1 a 3 cambian un fallo ruidoso por otro silencioso.
Es el principio IV aplicado a la búsqueda por texto.

**Independent Test**: con un país sin postings y otro con postings, buscar y contar por texto en
cada uno y en todos a la vez, y comprobar que la respuesta permite saber qué países no se
pudieron consultar.

**Acceptance Scenarios**:

1. **Given** un país sin postings utilizables, **When** el cliente busca o cuenta por texto
   solo en ese país, **Then** la respuesta indica que la búsqueda por texto no está disponible
   ahí y no se puede confundir con "cero coincidencias".
2. **Given** dos países, uno con postings utilizables y otro sin ellos, **When** el cliente
   cuenta por texto sin filtrar por país, **Then** recibe el total del primero y, en la misma
   respuesta, la lista de países no consultados con el motivo de cada uno.
3. **Given** el mismo par de países, **When** el cliente busca por texto sin filtrar por país,
   **Then** recibe la lista de resultados del primero con la forma de siempre, y el conteo de
   esa misma consulta le dice que el segundo no se consultó.
4. **Given** que ningún país pedido tiene postings utilizables, **When** el cliente busca por
   texto, **Then** recibe un error que nombra los países y el motivo, no una lista vacía.
5. **Given** una consulta cuyos términos se descartan todos por ser demasiado cortos, **When**
   se busca por texto, **Then** la respuesta dice que la consulta no tiene términos buscables,
   no que no haya coincidencias.

---

### User Story 5 - Un cambio de tokenizador se resuelve con el remedio que se propone (Priority: P2)

El tokenizador cambia (patrón, longitud mínima, tabla de normalización o regla de frontmatter).
La comprobación de frescura marca el índice y propone un comando. Ejecutar ese comando tiene que
dejar el índice al día en una sola pasada, aunque ningún fichero haya cambiado en disco.

**Why this priority**: hoy el comando propuesto responde "ya está al día" y el aviso se repite
para siempre; o, si había cambios en disco, sella la huella nueva sobre postings mezclados. Es el
principio VII.

**Independent Test**: construir un índice, alterar su sello de tokenizador, ejecutar el comando
que propone la comprobación de frescura y verificar que el aviso desaparece y que los postings
son idénticos a los de una reconstrucción desde cero.

**Acceptance Scenarios**:

1. **Given** un índice con un sello de tokenizador distinto del actual y sin cambios en disco,
   **When** el operador ejecuta el comando propuesto, **Then** los postings se reconstruyen por
   completo y la comprobación de frescura deja de marcarlo.
2. **Given** el mismo índice con algunos ficheros modificados, **When** se reindexa, **Then** se
   reconstruyen los postings de todos los documentos, no solo de los modificados.
3. **Given** unos postings cuyo sello no coincide con el tokenizador del servidor, **When** el
   cliente busca por texto en ese país, **Then** la búsqueda se trata como no disponible (como en
   la historia 4), no se responde con postings construidos con otras reglas.

### Edge Cases

- El índice JSON se escribe con éxito pero falla la escritura de los postings: el índice debe
  quedar marcado de forma que el siguiente indexado los reconstruya, y el servidor debe tratar la
  búsqueda por texto en ese país como no disponible, no como "sin coincidencias".
- Los postings existen pero corresponden a otra generación del índice JSON (uno de los dos se
  copió o restauró por separado): no deben usarse.
- Dos ficheros reclaman el mismo identificador y uno recibe un id derivado de su ruta: sus
  términos deben quedar asociados a su id definitivo.
- Un documento cambia de identificador entre dos pasadas: sus términos no pueden seguir
  apuntando al id antiguo.
- El directorio de corpus autorizado es un enlace simbólico: la validación debe hacerse sobre la
  ruta resuelta.
- El índice no declara directorio base: se usa el directorio autorizado por defecto.
- Hay índices de varias generaciones en el mismo directorio: cada país se juzga por separado y
  uno inutilizable no afecta a los demás.

## Requirements *(mandatory)*

### Functional Requirements

**Coherencia de los postings (historia 1)**

- **FR-001**: Tras cualquier pasada del indexador, los postings de un país MUST contener
  exactamente los términos de los documentos presentes en su índice JSON en ese momento, ni más
  ni menos, sea la pasada completa o incremental.
- **FR-002**: Un documento en cuarentena, retirado como huérfano o renombrado MUST desaparecer
  de los postings en la misma pasada en que cambia en el índice JSON.
- **FR-003**: Si los postings faltan o no son utilizables, el indexador MUST reconstruirlos
  aunque el índice JSON esté al día.

**Contención de rutas (historia 2)**

- **FR-004**: El directorio contra el que se valida la ruta de un documento MUST decidirlo el
  operador, MUST NOT poder ampliarlo el contenido de un índice y MUST NOT depender del directorio
  de trabajo desde el que se arranca el servidor. Lo fija una variable de entorno
  (`LEGALIZE_REPOS_DIR`, por defecto `<proyecto>/repos`), documentada junto a las demás y
  comprobada por los tests de documentación de la configuración.
- **FR-005**: Un índice cuyo corpus declarado queda fuera del directorio autorizado MUST NOT
  servirse, MUST generar un aviso que nombre el índice y el remedio, y MUST NOT impedir que se
  sirvan los demás índices.
- **FR-006**: Toda ruta de documento MUST resolverse (enlaces incluidos) y validarse contra el
  directorio autorizado del FR-004 antes de leerse. Las defensas actuales se mantienen: rutas
  absolutas, caracteres de control y ficheros no regulares.

**Formato de los postings (historia 3)**

- **FR-007**: Leer un fichero de postings MUST NOT poder ejecutar código, sea cual sea su
  contenido.
- **FR-008**: Un fichero de postings en un formato que no es el vigente, truncado o con una
  estructura inesperada MUST tratarse como no utilizable, con un aviso al operador que diga cómo
  regenerarlo. Los postings en el formato anterior MUST NOT leerse nunca, ni para migrarlos: el
  único camino es reindexar.
- **FR-009**: Los postings MUST llevar el sello del tokenizador con el que se construyeron y una
  identificación de la generación del índice JSON al que acompañan, y MUST considerarse no
  utilizables si cualquiera de los dos no coincide.

**Señal de búsqueda no disponible (historia 4)**

- **FR-010**: Cuando una búsqueda o un conteo por texto no puede consultar uno o más países, la
  respuesta MUST permitir al cliente saber qué países no se consultaron y por qué:
  - `contar_leyes` MUST incluir siempre en su respuesta los países no consultados y el motivo
    de cada uno (sin postings, ilegibles, sello distinto, generación distinta). La lista va
    vacía cuando se consultaron todos.
  - `buscar_ley` MUST conservar su tipo de retorno de lista mientras se haya podido consultar al
    menos un país pedido, y MUST devolver `ErrorRespuesta` con los países y motivos cuando no se
    pudo consultar ninguno.
  - Las instrucciones del servidor y el docstring de `buscar_ley` MUST decir que la forma de
    saber si una búsqueda por texto fue completa es contar con los mismos filtros.
- **FR-011**: Una consulta de texto sin ningún término buscable MUST distinguirse de una consulta
  sin coincidencias.
- **FR-012**: `buscar_ley` y `contar_leyes` MUST seguir saliendo del mismo filtro y MUST dar la
  misma señal ante la misma consulta (principio III).

**Sellos que invalidan (historia 5)**

- **FR-013**: Si el sello del tokenizador de un índice no coincide con el actual, el indexador
  MUST reconstruir los postings de todos los documentos en esa pasada, haya o no cambios en disco.
- **FR-014**: El remedio que propone la comprobación de frescura para cualquier estado caducado
  (commit, reglas o tokenizador) MUST dejar ese estado resuelto en una sola ejecución.
- **FR-015**: El sello del índice MUST NOT actualizarse si los postings no se reconstruyeron con
  ese tokenizador.

**Transversales**

- **FR-016**: Cada rechazo (ruta, postings no utilizables, índice fuera del directorio
  autorizado) MUST registrarse en stderr de forma que no se pueda inyectar líneas falsas en el
  registro.
- **FR-017**: Ningún cambio de esta spec MUST alterar el contenido de los documentos que se
  sirven ni los valores de sus metadatos (principio I).
- **FR-018**: La documentación (README: Mitigations, Index provenance, Limitations; ADR 0003)
  MUST reflejar el comportamiento nuevo, y las afirmaciones comprobables MUST tener su test.

### Key Entities *(include if feature involves data)*

- **Índice JSON de un país**: metadatos de cada documento, `_meta` con procedencia, sellos y
  registro de seguridad. Lo genera el indexador; el servidor lo trata como no confiable.
- **Postings de un país**: relación término → documentos que lo contienen, construida a partir
  del cuerpo de cada documento aceptado. Acompañan a un índice JSON concreto y llevan su sello de
  tokenizador y su identificación de generación.
- **Directorio de corpus autorizado**: el directorio, o los directorios, que el operador declara
  como fuente legítima de documentos. Es el único límite de lo que el servidor puede leer.
- **Sello de tokenizador**: huella de las reglas que deciden qué es un término. Ya existe en el
  índice y en los postings.
- **Señal de disponibilidad de la búsqueda por texto**: qué países se consultaron, cuáles no y
  por qué (sin postings, ilegibles, sello distinto, generación distinta).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Tras cualquier secuencia de modificaciones, altas, bajas, cuarentenas y
  reindexaciones incrementales sobre un corpus de prueba, el 100% de un conjunto fijo de
  consultas por texto devuelve los mismos documentos y el mismo conteo que tras una
  reconstrucción desde cero.
- **SC-002**: Ninguna combinación de directorio base y ruta escrita en un índice permite leer un
  fichero fuera del directorio autorizado: 0 lecturas en todos los casos del banco de pruebas
  (raíz del sistema, "../", rutas absolutas, enlaces simbólicos que escapan).
- **SC-003**: Ningún fichero de postings manipulado del banco de pruebas ejecuta código al
  usarse: 0 efectos observables fuera del proceso de búsqueda.
- **SC-004**: En el 100% de las consultas por texto sobre países sin postings utilizables, el
  cliente puede distinguir la respuesta de un "cero coincidencias" leyendo únicamente la
  respuesta.
- **SC-005**: En el 100% de los estados caducados que detecta la comprobación de frescura,
  ejecutar una vez el remedio propuesto hace que la siguiente comprobación de ese índice salga
  limpia.
- **SC-006**: Una reindexación incremental tras un `pull` que toca una fracción pequeña del
  corpus sigue siendo sensiblemente más barata que una reconstrucción completa. El presupuesto
  concreto se mide contra el corpus español durante la planificación (principio VI) y se fija
  allí.
- **SC-007**: El tiempo de arranque del servidor y su memoria residente sin búsquedas por texto
  no empeoran respecto a hoy (la carga bajo demanda del ADR 0003 se conserva).

## Clarifications

### Session 2026-10-16

- Q: ¿De dónde sale el directorio de corpus autorizado? → A: de la variable de entorno
  `LEGALIZE_REPOS_DIR`, por defecto `<proyecto>/repos` (FR-004). Se descartaron un directorio
  fijo sin configuración y una lista de directorios elegibles por nombre.
- Q: ¿Qué ocurre con los postings ya generados en el formato anterior? → A: no se cargan nunca,
  ni siquiera para migrarlos; el servidor avisa al operador con el comando para reindexar
  (FR-008). Se descartaron un comando de migración y una lectura restringida transitoria,
  porque ambos deserializan un fichero no confiable.
- Q: ¿Cómo sabe el cliente que un país no se pudo consultar? → A: `contar_leyes` lo dice
  siempre en un campo de su respuesta; `buscar_ley` mantiene su lista y solo devuelve error si no
  se pudo consultar ningún país pedido (FR-010). Se descartaron devolver error ante cualquier
  país no consultado, porque ocultaría los resultados de los demás, y cambiar `buscar_ley` a un
  objeto, porque rompe el contrato de lista.

## Assumptions

- El alcance son los defectos #1, #2, #3, #8 y #10 del análisis del 2026-10-16. Se quedan fuera,
  como arreglos pequeños por PR, la extracción de artículos (#5), los ids en minúsculas (#4), las
  fechas `YYYY` en `*_hasta` (#6), el título sin sanear en `obtener_articulo` (#7) y la doble
  carga del módulo (#9).
- Quien puede escribir en el directorio de índices es un atacante posible, pero no controla las
  variables de entorno (entre ellas `LEGALIZE_REPOS_DIR`) ni el código del servidor. Si las controlara, no habría defensa posible
  desde aquí.
- La búsqueda sigue siendo por presencia e intersección, sin ranking (ADR 0005), y la carga bajo
  demanda por país se conserva (ADR 0003).
- El nuevo formato de postings se elige en la planificación, midiendo la carga y el tamaño frente
  al actual contra los corpus español y sueco. El ADR que sustituye al 0003 registra esa elección.
- No se añaden dependencias de ejecución sin un ADR (constitución, Restricciones técnicas).
- Los índices versionados del corpus mock se regeneran como parte del cambio.
- Reindexar cada corpus una vez tras el cambio es un coste aceptado (Q2). El sueco tardó 49 s;
  el español se mide en la planificación.
