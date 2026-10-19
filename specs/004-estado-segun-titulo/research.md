# Research: Leyes cuyo título dice que se derogaron, aunque el estado diga que no

Mediciones del 2026-10-19 sobre los índices locales (`indices/index_legalize-{es,eu,fr,se,uk}.db`).

## R1 — Qué es una marca de derogación en el título

- **Decision**: el paréntesis final del título que empieza por `repealed` o `revoked`:
  `\((?:repealed|revoked)\b[^()]*\)\s*$`, con `re.IGNORECASE | re.ASCII`. Se devuelve el
  paréntesis completo, tal cual, sin el espacio final.
- **Rationale**: sobre los 86.671 títulos UK reconoce exactamente las 594 leyes que tienen
  cualquier paréntesis con `repealed`/`revoked` en cualquier sitio del título: no se pierde
  ninguna variante irregular (`15/02/1999`, `1. 4. 1991`, `and superseded`, sin espacio antes) y
  no hay falsos positivos. En es, eu, fr y se: 0 de 53.569. `re.ASCII` porque con `IGNORECASE`
  en Unicode el signo Kelvin (U+212A) casa con la `k` de `revoked`, así que un título
  manipulado podría parecer una marca sin escribir la palabra.
- **Alternatives considered**: solo las tres formas regulares (`(repealed)`, `(revoked)`,
  `(repealed d.m.aaaa)`) dejaba fuera las 4 irregulares; buscar la palabra en cualquier sitio
  del título no añade ninguna ley en los corpus actuales y abre falsos positivos en títulos como
  `… (Repealed Provisions) Order`.

## R2 — Dónde vive la regla

- **Decision**: módulo nuevo `legalize_estado.py`, con `marca_derogacion(titulo)`,
  `aviso(estado, titulo)` (la marca si el estado es `in_force` o vacío; si no, None),
  `estado_filtrable(estado, titulo)` (`"repealed"` cuando hay aviso; si no, el estado) y
  `huella()`. Lo usan el índice (`legalize_indice.poner_ley`, `contar`) y el servidor
  (`_estado_y_vigencia`).
- **Rationale**: principio III y FR-004: indexador y servidor deciden lo mismo con la misma
  función, como `legalize_articulos`. No depende del país.
- **Alternatives considered**: meter la regla en `legalize_indice` obligaría al servidor a
  importar el escritor para calcular el aviso; en `update_index._build_entry`, el servidor no
  podría usarla.

## R3 — El aviso se calcula al servir; el filtro, al indexar

- **Decision**: `aviso_estado` no se guarda: el servidor lo calcula del título y el estado de
  la fila y lo pasa por `_sanitize_metadata(…, max_len=100)`. El filtro sí necesita el índice:
  `estado_norm` (columna interna, nunca servida) se escribe con
  `normalizar(estado_filtrable(estado, titulo))`. La columna `estado` sigue siendo literal.
- **Rationale**: sin columna nueva ni nada más que validar en un índice no confiable. El aviso
  sale de un título que el servidor ya tiene y ya sanea: no puede llevar nada que el título no
  lleve (FR-003). `max_len=100`: la marca más larga medida tiene 63 caracteres
  (`(repealed 5.11.1993 for Act except s. 1 and 1.4.1996 otherwise)`). El filtro de estado es
  una subcadena sobre `estado_norm`: con `"repealed"` ahí, `estado="repealed"` las encuentra y
  `estado="in_force"` no (Q2), sin tocar `construir_filtro` y sin coste nuevo por consulta.
- **Alternatives considered**: columna `aviso_estado` en el índice: un dato más que un índice
  manipulado podría desalinear del título. Una función SQL de Python en el filtro: evita
  reindexar, pero recorre las 86.671 filas en cada consulta con estado.

## R4 — `revoked` y la palabra del filtro

- **Decision**: `estado_filtrable` devuelve `"repealed"` también para `(revoked)`; el aviso
  conserva `revoked`. `estado="revoked"` no encuentra nada, igual que hoy: no es un valor del
  vocabulario de estado.
- **Rationale**: FR-006. `revoked` es la palabra de la fuente para la legislación secundaria
  (34 leyes, todas SI/SSI).

## R5 — Invalidar los índices construidos antes

- **Decision**: `FORMATO = "3." + legalize_estado.huella()`. Un índice de formato 2 —o con
  otra regla— se rechaza con `formato_distinto`: el servidor no lo sirve, `check_updates`
  informa `FORMATO` con su remedio y el indexador lo reconstruye entero.
- **Rationale**: principio VII: el sello sale de la regla, no de acordarse de subir un número.
  Lo que cambia es el contenido de `estado_norm`, que decide qué devuelve un filtro; servir un
  índice viejo con el servidor nuevo daría `estado="repealed"` vacío sin avisar (principio IV).
  Reutiliza el camino que ya existe para `FORMATO` (spec 003), sin claves de meta nuevas.
- **Alternatives considered**: una huella aparte en `meta`, como la del tokenizador: tres
  sitios nuevos que comprobar y un estado degradado más que inventar para el filtro. Meter la
  regla en la huella del tokenizador: el servidor solo desactiva la búsqueda por texto cuando no
  coincide, y el filtro de estado seguiría sirviendo datos viejos.

## R6 — `estadisticas`

- **Decision**: `estados` sigue contando la columna literal (`in_force: 86.671` en UK). Campo
  nuevo `avisos_estado: int`, el total de leyes con aviso, calculado por `contar` al confirmar
  (`estado_norm` de `repealed` con `estado` en `legalize_estado.ESTADOS_CONTRADECIBLES`) y
  validado por `conteos_validos`.
- **Rationale**: FR-009. Sin él, `estadisticas` diría 0 derogadas y `contar_leyes` 594, y el
  cliente no sabría por qué.

## R7 — Rendimiento

- **Decision**: no hace falta medir un índice SQL nuevo: el filtro de estado es la misma
  subcadena sobre la misma columna. Se mide el p95 de `buscar_ley(estado="repealed")` y
  `contar_leyes` sobre UK antes y después (SC-005).
