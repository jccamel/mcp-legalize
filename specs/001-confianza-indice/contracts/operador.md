# Contrato: superficie del operador

## Variable de entorno nueva

| Variable | Default | Efecto |
|---|---|---|
| `LEGALIZE_REPOS_DIR` | `<script_dir>/repos` | Único directorio desde el que el servidor puede leer documentos. Un índice cuyo corpus queda fuera de él no se sirve |

- Se documenta en el docstring de `mcp_legalize.py` y en la tabla de Configuration del README.
  `test_config_docs.py` exige las dos cosas.
- Se resuelve una vez al arrancar, enlaces incluidos. Un valor que no exista o no sea un
  directorio produce un aviso, y no se sirve ningún índice, en lugar de caer en un directorio
  por defecto.

## Avisos nuevos en stderr del servidor

Todos llevan el nombre del fichero formateado con `!r` y nunca una ruta sin escapar (FR-016).

| Situación | Aviso |
|---|---|
| Corpus de un índice fuera de `LEGALIZE_REPOS_DIR` | `[SEGURIDAD] <índice>: el corpus <ruta> está fuera de LEGALIZE_REPOS_DIR (<raíz>); índice ignorado.` |
| Postings en el formato anterior | `[AVISO] <fichero>: formato anterior de postings, no se carga. Regenéralo: python scripts/update_index.py --repo <repo>` (por FR-003 basta sin `--force-all`) |
| Postings ilegibles o con una estructura inesperada | `[AVISO] <fichero>: <motivo>; la búsqueda por texto en <país> no está disponible.` |
| Sello del tokenizador o generación distintos | `[AVISO] <fichero>: <qué no coincide>; regenéralo con update_index.py.` |

## `scripts/update_index.py`

- Sin cambios en los flags.
- En cualquier pasada, los postings resultantes coinciden con los documentos del JSON (FR-001,
  FR-002).
- Si el sello del tokenizador del índice no coincide con el actual, o si los postings faltan o no
  son utilizables, la pasada reconstruye los postings aunque no haya cambios en disco, y no
  responde "El índice ya está al día" (FR-003, FR-013).
- Los postings no se reconstruyen por un cambio del ruleset de seguridad, que solo afecta al
  escaneo. Si ese reescaneo pone documentos en cuarentena, sí los retira de los postings.
- El sello del tokenizador en `_meta` solo se escribe cuando se han escrito los postings con ese
  tokenizador (FR-015). Si la escritura de los postings falla, el JSON se queda sin sello de
  tokenizador, y la siguiente pasada los reconstruye.

## `scripts/check_updates.py`

- Para el estado `TOKENS`, el comando propuesto (`update_index.py --repo <dir>`) pasa a resolverlo
  en una sola ejecución (FR-014). No hace falta proponer `--force-all`.
- Añade un estado `POSTINGS` para índices cuyos postings faltan, están en el formato anterior o
  no corresponden a la generación del JSON, con el mismo remedio.
