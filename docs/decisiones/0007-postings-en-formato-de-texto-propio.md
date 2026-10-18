# 0007 — Postings en un formato de texto propio, atados a su índice JSON

- **Estado:** Sustituida por [0009](0009-indice-en-base-de-datos.md)
- **Fecha:** 2026-10-16
- **Ámbito:** `legalize_postings.py`; `scripts/update_index.py`; `scripts/check_updates.py`; carga de postings en `mcp_legalize.py`
- **Sustituye a:** [0003](0003-indice-invertido-en-fichero-aparte.md)

## Contexto

El ADR 0003 dejó los postings en un `.bin` aparte, en pickle, cargado bajo demanda. El fichero
aparte y la carga bajo demanda eran buenas decisiones, pero el formato no: el servidor hacía
`pickle.load` de un fichero que su propio comentario llamaba entrada no confiable, y escribir en
`indices/` equivalía a ejecutar código. Además, una reindexación incremental reescribía los
postings solo con los documentos de esa pasada, y un sello de tokenizador cambiado se notificaba
pero no forzaba nada. La spec 001 reúne los cuatro defectos.

## Decisión

- Los postings pasan a `inverted_<repo>.postings`, en un formato de texto que define
  `legalize_postings.py`: firma, sello del tokenizador, `generacion`, una tabla de ids y una
  línea por término con deltas. Se lee con `str.split` e `int()`, y las listas se decodifican de
  forma perezosa.
- El `.bin` anterior se reconoce por su nombre y no se abre nunca, ni para migrarlo. El único
  camino es reindexar (decisión Q2 de la spec).
- Cada pasada del indexador **fusiona** los postings previos si son utilizables y los
  **reconstruye** si no. La invariante es que contengan exactamente los términos de los
  documentos del JSON.
- Una `generacion` aleatoria ata los postings al JSON. Los postings se escriben primero y el JSON
  después, y los sellos solo se escriben si los postings se escribieron.
- La carga sigue siendo bajo demanda y por país, como en el 0003.

## Alternativas consideradas

Medidas sobre el corpus español (25.889 documentos, 560.577 términos, 28 M de postings):

| Formato | Disco | Carga | RSS |
|---|---|---|---|
| pickle (0003) | 142,3 MB | 0,36 s | 394 MB |
| JSON, ids como texto | 501,8 MB | 1,38 s | 3.111 MB |
| JSON, ids como enteros | 158,1 MB | 1,43 s | 1.556 MB |
| **texto propio con deltas** | **75,8 MB** | **0,24 s** (con validación) | **176 MB** |
| SQLite | 191,8 MB | ~0 s | 16 MB |

- **JSON:** no ejecuta código, pero ocupa entre 1,5 y 3,1 GB residentes y cuadruplica la carga.
- **SQLite:** es el mejor en memoria, pero abrir una base de datos manipulada es una superficie
  de ataque en sí misma, y la defensa depende de la versión de SQLite de cada Python.
- **msgpack:** una dependencia nueva para nada que el texto no dé ya.
- **marshal:** su propia documentación advierte de que no es seguro ante datos maliciosos.
- **Retokenizar siempre en lugar de fusionar:** 49 s frente a 10,2 s con un 5% de cambios.

## Consecuencias

- **Positivas:**
  - escribir en `indices/` deja de dar ejecución de código;
  - la búsqueda por texto no pierde documentos tras un `git pull`;
  - la mitad de disco y de memoria que el pickle;
  - una pasada incremental del 5% del corpus español tarda 17,1 s, frente a 137,6 s del
    indexado completo.
- **Negativas / costes:**
  - hay que reindexar una vez cada corpus que tuviera `.bin`; hasta entonces, esos países no
    admiten búsqueda por texto y `contar_leyes` lo indica con `formato_anterior`;
  - el formato es propio y lo tiene que mantener este proyecto.
- **Reglas que se derivan:**
  - Nadie más que `legalize_postings.py` lee o escribe postings.
  - Cualquier cambio de formato sube la versión de la firma (`legalize-postings 2`), y los
    ficheros con otra firma se tratan como `ilegibles` hasta reindexar.
  - Ningún sello se escribe sin que exista lo que sella.

## Cómo revertirla

No hay vuelta atrás al pickle: lo prohíbe el principio II de la constitución. Cambiar a otro
formato se hace detrás de `legalize_postings.estado` y `escribir`, y con una firma nueva.
