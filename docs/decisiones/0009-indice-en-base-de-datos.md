# 0009 — El índice de cada corpus es una base de datos SQLite, abierta como entrada no confiable

- **Estado:** Aceptada
- **Fecha:** 2026-10-18
- **Ámbito:** `legalize_indice.py`; `scripts/update_index.py`; `scripts/check_updates.py`; la carga y las consultas de `mcp_legalize.py`; `legalize_articulos.py`
- **Sustituye a:** [0007](0007-postings-en-formato-de-texto-propio.md)
- **Spec:** [`specs/002-indice-sqlite`](../../specs/002-indice-sqlite/spec.md)

## Contexto

El índice era un JSON por corpus cargado entero en memoria, más unos postings con formato propio
(0007) atados a él por una `generacion`. Casi todos los defectos corregidos desde el 2026-10-16
vinieron de esa infraestructura escrita a mano: deserialización insegura, postings que se perdían
en una pasada incremental, orden de escritura y generación entre dos ficheros, un validador que
copiaba el patrón del tokenizador y dejó a España sin búsqueda por texto. Además, cada consulta
recorría el corpus en Python, los artículos se localizaban en el texto en cada llamada (hasta
95 ms en los códigos franceses) y no había forma de buscar una frase exacta.

El 0007 descartó SQLite porque abrir una base de datos manipulada es una superficie de ataque y
la defensa dependía de la versión de SQLite de cada Python. Desde Python 3.12,
`Connection.setconfig` permite pedir el modo defensivo explícitamente, sea cual sea la
compilación local, y eso cambia el balance.

## Decisión

- Cada corpus se indexa en `indices/index_<repo>.db`, con el esquema que fija
  `legalize_indice.ESQUEMA`:
  - las leyes, con sus campos ya plegados para los filtros;
  - los artículos, localizados al indexar con `legalize_articulos.localizar_todos`, con su
    ubicación en la estructura;
  - el cuerpo, en una tabla FTS5 sin contenido (`unicode61 remove_diacritics 0`), alimentada con
    el texto plegado por `legalize_normalizacion` (ADR 0008);
  - `meta`: seguridad, sellos, conteos de los listados y formato.
- **Abrir** (`legalize_indice.abrir`) es la única forma de leerla, para el servidor, el indexador
  y `check_updates.py`:
  - en solo lectura, con el modo defensivo, `trusted_schema=OFF`, `query_only` y
    `cell_size_check`;
  - el esquema se compara sentencia a sentencia con el canónico antes de consultar nada (de las
    tablas internas de FTS5 solo se exigen nombre y tipo);
  - sin `setconfig` (Python < 3.12), no se sirve ningún índice. El suelo del proyecto sube a
    3.12.
- **Escribir** (`Escritor`) es siempre sobre un temporal del mismo directorio —una copia del
  índice vigente en las pasadas incrementales—, en una sola transacción, que se sustituye entero
  con `os.replace`. No hay generación ni orden de escritura.
- **Consultar:**
  - todo lo que manda el cliente llega como parámetro enlazado;
  - cada término de `texto` va como cadena FTS5 entrecomillada, unida con `AND`;
  - una `frase`, como una sola cadena entrecomillada;
  - los filtros de texto usan `instr` sobre columnas plegadas, no `LIKE`.
- El formato anterior se reconoce por su nombre y no se abre. El indexador lo migra sin flags y
  borra el `.json`, el `.postings` y el `.bin`. Hasta entonces el servidor no sirve ese corpus y
  `check_updates.py` lo informa como `FORMATO`.

## Alternativas consideradas

Prueba de concepto sobre el corpus español (25.889 leyes, 2026-10-18):

| | JSON + postings (0007) | SQLite + FTS5 |
|---|---|---|
| Disco | ~96 MB | 474 MB (×5, por la búsqueda por frase) |
| Arranque | 484 ms | 0,2 ms |
| Memoria tras consultar | 363 MB | 27 MB |
| Primera búsqueda por texto | 241 ms | 0,07 ms |
| Artículo | 0,5 ms (7–47 ms en códigos franceses) | 0,08 ms |
| Frase exacta | no | sí |

- **Seguir con JSON + postings:** mantiene la maquinaria que ha producido los defectos, la
  memoria crece con cada corpus y no da frases. Las transacciones de SQLite eliminan la
  generación, la fusión de postings y el orden de escritura.
- **Tantivy u otro motor embebido:** una dependencia binaria nueva y un formato que este
  proyecto no puede validar antes de abrirlo. SQLite viene con Python.
- **Un motor externo (Elasticsearch, Meilisearch):** un servicio que operar, para un servidor
  que hoy es un proceso y unos ficheros.
- **FTS5 con `detail=none` o `detail=column`:** ahorra disco, pero elimina la búsqueda por
  frase, que es lo que el usuario eligió a cambio del disco.

## Medidas finales

Con los cuatro corpus (es, eu, fr, se) y el banco de paridad de 1.178 peticiones:

| | `main` (cc72413) | Esta decisión |
|---|---|---|
| Carga de los cinco índices | 143 ms, +163 MB | 27 ms, +4 MB |
| Memoria tras el banco completo (sobre una base de 100 MB) | +578 MB | +182 MB |
| p95 búsquedas por texto | 9,6 ms | 3,7 ms |
| p95 artículos | 7,2 ms | 2,7 ms |
| Indexado completo de ES | 150 s, 4,14 GB | 201 s, 0,56 GB |

La mayor parte de la memoria tras el banco es servir el texto de los ficheros, igual en los
dos. El indexado completo es un 34 % más lento: unos 6 s de `localizar_todos` y la escritura en
FTS5. El plegado del cuerpo (~39 s en ES) ya se pagaba antes al tokenizar.

Además:
- **Paridad (SC-001):** el banco responde igual que `main`, con 0 diferencias en 1.178
  peticiones. Solo cambian las diferencias deliberadas del contrato.
- **Artículos (FR-014):** las filas dan el mismo inicio, corte y final que localizar sobre el
  texto, en todos los números de es, se, eu y una muestra de fr. En sueco, las 49.032
  apariciones de números repetidos se alcanzan con `capitulo`.
- **Frase (SC-006):** «arrendamiento urbano» da 4 leyes como frase frente a 573 como palabras.
- **Pasada incremental en ES:** 6,7 s al 1 % y 12,2 s al 5 %, dentro de los 20 s de la
  spec 001.

## Consecuencias

- **Positivas:**
  - Desaparecen `legalize_postings.py`, la generación, la fusión de postings, la carga perezosa
    y la caché de títulos.
  - Una pasada interrumpida deja el índice anterior intacto.
  - Los artículos se localizan una vez y los números repetidos por capítulo son alcanzables.
  - Hay búsqueda por frase.
  - Los campos nuevos de la spec de Legalize son columnas.
- **Negativas / costes:**
  - Python ≥ 3.12.
  - Unas cinco veces más disco que el formato anterior (es 530 MB, eu 248 MB, fr 77 MB,
    se 42 MB).
  - Hay que reindexar una vez cada corpus.
  - Contar una frase muy común es más lento que una búsqueda típica (84 ms con 3.424
    resultados en ES).
- **Reglas que se derivan:**
  - Nadie más que `legalize_indice.py` conoce el esquema.
  - Cualquier cambio de esquema sube `FORMATO`. Un índice de otro formato no se sirve y el
    indexador lo reconstruye.
  - Ninguna consulta se hace sobre una conexión que no venga de `abrir`.
  - Nada que llegue del cliente se concatena en SQL ni en una expresión MATCH sin
    entrecomillar.
  - Lo que se lee de la base de datos sigue siendo no confiable:
    - los metadatos pasan por `_sanitize_metadata`;
    - las posiciones de artículo se comprueban contra el texto;
    - los conteos de `meta` se validan antes de usarlos.
  - Los ADR 0002 (degradar por entrada) y 0005 (presencia sin ranking) siguen vigentes: la
    búsqueda no ordena por relevancia.

## Cómo revertirla

Volver al JSON exigiría recuperar `legalize_postings.py` y la carga en memoria, que siguen en el
historial anterior a la spec 002, y reindexar. Cambiar de motor se hace detrás de
`legalize_indice` (`Escritor`, `abrir` y las funciones de consulta), sin tocar las
herramientas.
