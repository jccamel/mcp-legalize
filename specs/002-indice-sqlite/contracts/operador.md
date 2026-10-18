# Contrato: superficie del operador

## Ficheros

| Antes | Después |
|---|---|
| `indices/index_<repo>.json` + `indices/inverted_<repo>.postings` | `indices/index_<repo>.db` |

El indexador borra los ficheros del formato anterior en cuanto escribe con éxito el `.db`.

## `scripts/update_index.py`

- Mantiene los flags y el informe.
- Construye en un temporal y lo sustituye entero (research R1): una interrupción deja intacto
  el índice anterior.
- Si encuentra un corpus en el formato anterior, construye desde cero sin más pasos.
- Si no puede sustituir el fichero (Windows con el servidor abierto), lo dice y deja el
  temporal para reintentar.

## `scripts/check_updates.py`

| Estado | Cambio |
|---|---|
| `DESACTUAL`, `REGLAS`, `TOKENS` | Igual que hoy, leídos de la tabla `meta` |
| `POSTINGS` | Desaparece (ya no hay postings separados) |
| `FORMATO` | **Nuevo**: el corpus sigue en el formato anterior, o la base de datos es de otra versión, ilegible o tiene un esquema inesperado. Remedio: `update_index.py --repo <dir>` |

## Avisos del servidor (stderr, con `!r` en los nombres)

| Situación | Aviso |
|---|---|
| Solo existe el formato anterior | `[AVISO] 'index_<repo>.json': formato anterior; no se sirve. Migra con: python scripts/update_index.py --repo …` |
| Esquema inesperado o versión distinta | `[SEGURIDAD] 'index_<repo>.db': <motivo>; índice ignorado.` |
| Python sin modo defensivo | `[SEGURIDAD] este Python no permite abrir índices en modo defensivo (requiere 3.12); no se sirve ningún índice.` |

## Requisitos

Python ≥ 3.12. La CI cubre de 3.12 a 3.13 (y 3.14 si el lock lo permite).
