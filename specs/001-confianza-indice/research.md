# Research: Confianza en el índice

Mediciones del 2026-10-16 en macOS (Apple Silicon), Python 3.14.8, sobre clones superficiales
de `legalize-es` (commit `c1b7254a`) y `legalize-se` (commit `0e6c4b6`). Cada carga se midió en
un subproceso nuevo, quedándose con el mejor de tres intentos. El RSS incluye los ~15 MB del
intérprete. Scripts: `bench/formatos.py` y `bench/incremental.py` en el scratchpad de la sesión.

## Punto de partida: los corpus ya no son los que dice el código

| | ES | SE |
|---|---|---|
| Documentos | **25.889** (el README y los comentarios dicen 12.291) | 8.990 |
| Cuerpo leído | 1.892 MiB | 99 MiB |
| Términos / postings | 560.577 / 28.019.271 | 146.151 / 2.762.200 |
| Índice JSON | 19,5 MB (el comentario dice 8,7 MB) | 6,0 MB |
| Postings en pickle | 142,3 MB (el ADR 0003 dice ~85 MB) | 15,3 MB |
| Indexado completo | 133,6 s, pico de RSS 4,4 GB | 7,3 s, 572 MB |
| Pasada incremental del 1% (hoy, con el defecto #1) | 2,75 s, 374 MB | — |

El español ha duplicado su tamaño desde que se escribieron esas cifras. Corregir las cifras del
README y de los comentarios queda fuera de esta spec, pero las decisiones de abajo se toman con
las de hoy.

## R1 — Formato de los postings (FR-007, FR-008, SC-007)

**Decision**: un fichero de texto UTF-8 propio, de solo datos: `inverted_<repo>.postings`.
Contiene una cabecera, la tabla de ids de documento y una línea por término con los índices de
documento codificados como deltas. La biblioteca estándar lo lee con `str.split` e `int()`. Al
cargar se guarda la cadena cruda de cada término, y las listas se decodifican solo para los
términos que se consultan.

**Rationale**:

| Formato | ES disco | ES carga | ES RSS | SE disco | SE carga | SE RSS |
|---|---|---|---|---|---|---|
| pickle actual | 142,3 MB | 0,36 s | 394 MB | 15,3 MB | 0,05 s | 75 MB |
| JSON, ids como texto | 501,8 MB | 1,38 s | 3.111 MB | 42,4 MB | 0,16 s | 326 MB |
| JSON, ids como enteros | 158,1 MB | 1,43 s | 1.556 MB | 15,4 MB | 0,16 s | 187 MB |
| **Texto por líneas con deltas** | **75,8 MB** | **0,16 s** | **176 MB** | **9,3 MB** | **0,04 s** | **45 MB** |
| SQLite | 191,8 MB | ~0 s | 16 MB | 20,6 MB | ~0 s | 16 MB |

- Es mejor que pickle en las tres medidas: la mitad de disco, menos de la mitad de tiempo de carga
  y menos de la mitad de memoria. Leerlo no puede ejecutar código, porque solo hay `split` e
  `int`.
- La decodificación perezosa cuesta como mucho 2,8 ms en el término más frecuente (`articulo`,
  25.159 documentos) y 0,4 ms en uno típico (`arrendamiento`, 2.108).
- Usar índices enteros en lugar de ids de texto hace que la intersección trabaje con conjuntos de
  enteros.

**Alternatives considered**:

- **JSON**: no ejecuta código, pero con el corpus español ocupa entre 1,5 y 3 GB de memoria y
  tarda 1,4 s en cargar, cuatro veces más que hoy. Viola SC-007.
- **SQLite**: es el mejor en memoria y ni siquiera hay carga. Lo descarto porque abrir una base de
  datos manipulada es una superficie de ataque en sí misma (esquema, disparadores, vistas,
  páginas corruptas). Defenderse exige `trusted_schema=OFF`, modo defensivo y comprobaciones de
  celdas, y depende de la versión de SQLite que traiga cada Python. El texto plano no tiene nada
  de eso. Queda como opción si la memoria llega a importar más que la superficie de ataque.
- **msgpack u otros formatos binarios**: suponen una dependencia nueva, que exige su propio ADR,
  para un beneficio que el formato de texto ya da.
- **marshal**: no ejecuta código, pero su propia documentación advierte de que no es seguro ante
  datos malformados o maliciosos.

## R2 — Postings coherentes en una pasada incremental (FR-001 a FR-003, SC-006)

**Decision**: fusionar. Si los postings previos son utilizables (formato vigente, mismo
tokenizador y misma generación que el JSON que se va a actualizar), se cargan, se retiran los
documentos reprocesados, puestos en cuarentena, renombrados o retirados como huérfanos, y se
añaden los términos de los reprocesados. Si no son utilizables, se reconstruyen desde cero
tokenizando todos los documentos del índice.

**Rationale**, sobre el corpus español:

| Cambiados | Retokenizar todo | Fusionar (carga incluida) |
|---|---|---|
| 258 (1%) | 49,7 s | 7,3 s |
| 1.294 (5%) | 49,4 s | 10,2 s |

La fusión se midió con postings de pickle e ids de texto. Con índices enteros debería costar
igual o menos.

**Alternatives considered**:

- **Retokenizar siempre**: es lo más simple y no puede quedar incoherente, pero convierte una
  pasada incremental de ~3 s en una de ~53 s, la mitad que un indexado completo (134 s).
- **Guardar también la relación documento → términos**: la retirada sería directa, pero duplica
  el tamaño de los postings, y retirar ya cuesta poco al recorrer los términos.

**Presupuesto (SC-006)**: una pasada incremental que modifique hasta el 5% del corpus español
MUST completarse en **≤ 20 s**, frente a los 133,6 s del indexado completo de hoy. La cifra es
la fusión medida (10,2 s) más la pasada de hoy (2,75 s), con un margen del 50%. Una
reconstrucción forzada por tokenizador, generación o postings inutilizables no entra en ese
presupuesto, porque cuesta lo mismo que un indexado completo.

**Riesgo anotado**: el indexado completo del español ya tiene un pico de 4,4 GB de RSS, porque
guarda los términos de cada documento como conjuntos de cadenas. Ni la fusión ni la
reconstrucción pueden empeorarlo. Reducirlo queda fuera de esta spec.

## R3 — Generación del par JSON/postings (FR-009, casos límite)

**Decision**: cada pasada que escribe postings genera un identificador aleatorio (128 bits en
hexadecimal) y lo escribe en la cabecera de los postings y en `_meta.generacion` del JSON.
Primero se escriben los postings y después el JSON, de forma atómica y en ese orden, así que el
JSON es el punto de confirmación.

- Si falla la escritura de los postings, el JSON se escribe sin `generacion` ni `tokenizador`,
  de modo que el servidor los da por no utilizables y la siguiente pasada los reconstruye.
- Si falla la escritura del JSON después de los postings, el JSON antiguo conserva la generación
  antigua, el desajuste se detecta y la siguiente pasada reconstruye.

**Alternatives considered**: un hash del contenido del JSON obligaría a leer y procesar 19,5 MB
en cada arranque. Un número de pasada correlativo permite colisiones si se restaura una copia
de seguridad.

## R4 — Formato anterior (FR-008, Q2)

**Decision**: el fichero nuevo tiene otro nombre (`.postings` en lugar de `.bin`), así que el
código nuevo nunca abre un `.bin`. Si existe un `inverted_<repo>.bin` y no su `.postings`, el
motivo es `formato_anterior`, con el aviso al operador. Esto se decide solo por la existencia
del fichero, sin leer un solo byte. El indexador borra el `.bin` al escribir el `.postings`.

**Alternatives considered**: detectar pickle por su byte mágico `\x80` exige abrir el fichero
igualmente. Es seguro, pero innecesario si el nombre ya distingue el formato.

## R5 — Directorio autorizado (FR-004 a FR-006, Q1)

**Decision**: `LEGALIZE_REPOS_DIR`, por defecto `<script_dir>/repos`, se resuelve una vez al
importar el módulo. Al cargar cada índice:

1. La raíz del corpus se calcula como hoy a partir de `directorio_base`, sea relativa al
   proyecto o absoluta.
2. Se resuelve con `Path.resolve()`, enlaces incluidos, y se exige que esté dentro de
   `LEGALIZE_REPOS_DIR`. Si no lo está, el índice no se carga y se avisa (FR-005).
3. La raíz validada se guarda en una tabla por país, y `_resolve_ruta` la lee de ahí, no de
   `_meta`. La contención de cada documento se valida contra esa raíz, que a su vez está dentro
   de `LEGALIZE_REPOS_DIR`.

**Rationale**: los índices que ya existen siguen funcionando sin regenerarse. El del mock
(`repos/legalize-mock`) y el de un corpus clonado según el README quedan dentro de `repos/`. El
índice ya no puede ampliar lo que el servidor lee, solo elegir dentro de lo que el operador ha
autorizado.

**Alternatives considered**: guardar solo el nombre del repo en el índice obligaría a regenerar
todos los índices y no aporta seguridad adicional, porque la comprobación de contención es la
misma.

## R6 — Un solo sitio para el formato de postings (principio III)

**Decision**: un módulo nuevo, `legalize_postings.py`, que se encarga de escribir, leer, validar
y diagnosticar la disponibilidad de los postings, y que devuelve el motivo. Lo usan el
indexador, el servidor y `check_updates.py`. No importa `mcp_legalize`, para no repetir el ciclo
de importaciones que hoy duplica la carga del servidor (#9, fuera de esta spec).

**Alternatives considered**: repartir el formato entre el indexador (escritura) y el servidor
(lectura) es exactamente el tipo de copia doble que el principio III prohíbe.
