# Feature Specification: Leyes cuyo título dice que se derogaron, aunque el estado diga que no

**Feature Branch**: `feat/004-estado-segun-titulo`

**Created**: 2026-10-19

**Status**: Clarified

**Input**: User description: "UK laws whose title says they were repealed or revoked arrive with
status in_force. […] keep `estado` exactly as the corpus gives it (ADR 0001; spec 003 Q3), and
have the server add a field of its own when the title contradicts the status, so the model does
not present a repealed law as in force. Filtering by estado=repealed in buscar_ley/contar_leyes
should also find these laws, and the server instructions must explain the field. The title is
untrusted corpus text. Needs a new ADR. Parity: no change in es, eu, fr, se."

## Contexto

El corpus del Reino Unido (86.671 leyes, incorporado el 2026-10-19) trae **todas** sus leyes con
`status: in_force`. Pero la fuente marca en el propio título las que ya no están en vigor.
Medido el 2026-10-19 sobre el índice UK:

| Marca en el título | Leyes |
|---|---|
| `(repealed)` | 380 |
| `(revoked)` | 34 |
| `(repealed d.m.aaaa)`, p. ej. `Deer Act 1963 (Repealed 25.10.1991)` | 176 |
| Variantes irregulares: `(repealed 15/02/1999)`, `(repealed 1. 4. 1991)`, `(repealed and superseded 21.5.1997)`, `1985(repealed 5.11.1993 for Act except s. 1 and 1.4.1996 otherwise)` | 4 |
| **Total** | **594**, todas `in_force` |

Ninguna de las 594 trae `repeal_date`, `repealed_by` ni `end_of_validity`. La marca va siempre
al final del título; las mayúsculas varían (`repealed`, `Repealed`, `REPEALED`). En los corpus
es, eu, fr y se no hay ninguna marca de este tipo (0 de 53.569 títulos).

Consecuencia hoy: el cliente recibe `estado: in_force` para una ley cuyo título dice que se
derogó, y la presenta como vigente. `buscar_ley(estado="repealed", pais="uk")` no devuelve nada.

Dos decisiones aceptadas impiden corregir el estado: el ADR 0001 (los valores del corpus se
reproducen literalmente, nunca se normalizan) y la Q3 de la spec 003 (el estado no se deduce de
otro dato).

**Decisión previa del usuario:** `estado` sigue tal como lo da el corpus. El servidor añade un
campo **propio** que avisa cuando el título contradice al estado, y el filtro por estado
derogado encuentra también estas leyes.

## User Scenarios & Testing *(mandatory)*

Actores: el **cliente** (el asistente que llama a las herramientas) y el **operador** (quien
mantiene los índices).

### User Story 1 - El cliente no presenta como vigente una ley que su título da por derogada (Priority: P1)

El cliente obtiene una ley británica cuyo título termina en `(repealed)` y, además de
`estado: in_force` tal como lo da la fuente, recibe un aviso del servidor que dice que el
título contradice al estado, con la marca del título reproducida literalmente.

**Why this priority**: es el error que motiva el cambio: hoy 594 leyes se presentan como
vigentes sin nada que lo contradiga en la respuesta.

**Independent Test**: con un corpus sintético con una ley `in_force` titulada `… (repealed)`,
otra `… (Revoked)`, otra `… (repealed 5.11.1993)` y otra sin marca, las tres primeras traen el
aviso en `buscar_ley`, `obtener_ley` y `obtener_articulo`, y la cuarta no.

**Acceptance Scenarios**:

1. **Given** una ley `in_force` titulada `Licensing Act 1964 (repealed)`, **When** el cliente
   la obtiene, **Then** recibe `estado: in_force` sin cambios y un aviso que contiene la marca
   `(repealed)` tal cual.
2. **Given** una ley `in_force` titulada `Deer Act 1963 (Repealed 25.10.1991)`, **When** el
   cliente la obtiene, **Then** el aviso reproduce `(Repealed 25.10.1991)` literalmente, sin
   reinterpretar la fecha.
3. **Given** una ley sin marca en el título, **When** el cliente la obtiene, **Then** el campo
   de aviso viene vacío.
4. **Given** una ley `repealed` cuyo título también dice `(repealed)`, **When** el cliente la
   obtiene, **Then** no hay aviso: el título no contradice al estado.

---

### User Story 2 - Filtrar por derogadas encuentra estas leyes (Priority: P1)

El cliente pregunta qué leyes británicas están derogadas y recibe también las que solo lo dice
su título, sin cambiar sus llamadas.

**Why this priority**: sin esto, el filtro por estado excluye en silencio las 594 leyes; el
aviso solo llega si el cliente ya ha encontrado la ley.

**Independent Test**: con el corpus sintético, `estado="repealed"` devuelve las leyes con
marca, `contar_leyes` da el mismo número, y `estado="in_force"` no las devuelve.

**Acceptance Scenarios**:

1. **Given** las cuatro leyes del corpus sintético, **When** el cliente filtra
   `estado="repealed"`, **Then** recibe las tres con marca y no la que no la tiene.
2. **Given** el mismo filtro, **When** se pide a `buscar_ley` y a `contar_leyes`, **Then** el
   número coincide.
3. **Given** `estado="in_force"`, **When** se ejecuta, **Then** las leyes con marca no aparecen
   [NEEDS CLARIFICATION: Q2, ¿una ley con aviso deja de contar como `in_force` en el filtro?].

---

### User Story 3 - El operador reindexa una vez (Priority: P3)

El operador actualiza el servidor y `check_updates.py` le dice qué índices hay que reconstruir
para que el aviso esté disponible, con el remedio de siempre.

**Why this priority**: es el coste operativo; sin él el aviso no llega a los índices ya
construidos.

**Independent Test**: con un índice anterior al cambio, `check_updates` lo informa y su remedio
lo deja al día.

**Acceptance Scenarios**:

1. **Given** un índice anterior al cambio, **When** el operador ejecuta `check_updates.py`,
   **Then** lo ve informado con su remedio, y ejecutarlo una vez lo resuelve.

---

### Edge Cases

- **Marca en mitad del título** (`… (repealed) Order 1990`): no es una marca de estado; no hay
  aviso. Solo cuenta la marca final, que es donde aparece en las 594 medidas.
- **Variantes irregulares** (`15/02/1999`, `1. 4. 1991`, `repealed and superseded …`, sin
  espacio antes del paréntesis): son marcas; el aviso reproduce el paréntesis tal cual.
- **Derogación parcial** (`(repealed 5.11.1993 for Act except s. 1 …)`): el aviso la reproduce
  literalmente, así que el cliente ve la excepción; cuenta como derogada en el filtro.
- **Un título hostil** que termina en `(repealed <instrucciones>)`: el aviso pasa por el mismo
  saneado y tope de longitud que el título, así que no llega al cliente nada que el título
  saneado no llevara ya.
- **Una marca absurdamente larga**: se corta al tope del aviso; nunca puede alargar la
  respuesta más que el propio título.
- **Una ley cuyo estado ya es `repealed`, `partially_repealed`, `expired` o `annulled`**: el
  título no contradice al estado; sin aviso, y el filtro la encuentra por su propio estado.
- **Corpus sin marcas** (es, eu, fr, se): respuestas idénticas, salvo el campo nuevo vacío.

## Requirements *(mandatory)*

### Functional Requirements

**Aviso (historia 1)**

- **FR-001**: Una ley cuyo título **termina** en un paréntesis que empieza por `repealed` o
  `revoked` (sin distinguir mayúsculas, con o sin espacio antes) y cuyo `estado` es `in_force`
  o está vacío MUST considerarse «derogada según su título».
- **FR-002**: `buscar_ley`, `obtener_ley` y `obtener_articulo` MUST devolver, para esas leyes,
  un campo nuevo y opcional, `aviso_estado`, que reproduce la marca del título literalmente.
  Para las demás leyes MUST venir vacío. Ningún campo existente cambia de nombre, de tipo ni
  de valor; en particular, `estado` sigue siendo el del corpus (ADR 0001).
- **FR-003**: `aviso_estado` sale del título, que es texto del corpus: MUST pasar por el mismo
  saneado que el título y MUST NOT ser más largo que el título saneado.
- **FR-004**: La regla de qué es una marca de derogación en el título MUST vivir en un único
  sitio, que usan igual el indexador y el servidor, y MUST NOT depender del país: se aplica a
  cualquier corpus (hoy solo la cumple el británico).

**Filtro (historia 2)**

- **FR-005**: `buscar_ley` y `contar_leyes` con `estado="repealed"` MUST devolver también las
  leyes derogadas según su título, y los dos MUST dar el mismo número.
- **FR-006**: `revoked` MUST tratarse como `repealed` a efectos del filtro: es la palabra que
  la fuente usa para la legislación secundaria. El aviso conserva la palabra original.
- **FR-007**: La fecha que traiga la marca MUST NOT usarse como `fecha_derogacion`: solo
  aparece, literal, en el aviso, y los filtros `derogada_desde`/`derogada_hasta` no encuentran
  estas leyes (Q1).
- **FR-007b**: `buscar_ley` y `contar_leyes` con `estado="in_force"` MUST NOT devolver las
  leyes derogadas según su título (Q2): una ley sale en un filtro de estado o en el otro, nunca
  en los dos.

**Instrucciones y documentación**

- **FR-008**: Las instrucciones del servidor MUST explicar `aviso_estado`: que es del
  servidor, no de la fuente; que cuando existe el estado del corpus está contradicho por el
  título, y que el cliente no debe presentar esa ley como vigente.
- **FR-009**: `estadisticas` MUST seguir contando `estados` tal como los da el corpus, y MUST
  dar aparte cuántas leyes tienen aviso, para que el desajuste con `contar_leyes` sea visible.
- **FR-010**: Un ADR nuevo MUST registrar la decisión y su relación con el ADR 0001 y la Q3 de
  la spec 003; README y README.es MUST describir el campo.

**Índices**

- **FR-011**: Un índice construido antes del cambio MUST detectarse como desfasado y
  reconstruirse con el remedio que propone `check_updates.py`.

### Key Entities

- **Marca de derogación en el título**: el paréntesis final del título que empieza por
  `repealed` o `revoked`, con lo que traiga detrás (fecha, excepciones), tal cual.
- **Aviso de estado**: valor del servidor, derivado de la marca, presente solo cuando el título
  contradice al estado del corpus.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Reindexado el corpus UK, las 594 leyes medidas traen aviso y ninguna otra lo trae.
- **SC-002**: `buscar_ley(estado="repealed", pais="uk")` pasa de 0 resultados a 594, y
  `contar_leyes` da el mismo número.
- **SC-003**: El banco de paridad da 0 diferencias en es, eu, fr y se, salvo el campo nuevo
  vacío.
- **SC-004**: Ningún título hostil del banco de pruebas de inyección hace llegar al cliente, a
  través del aviso, texto que no llegara ya por el título saneado.
- **SC-005**: El tiempo de una búsqueda filtrada por estado no empeora de forma medible (p95
  dentro del margen de ruido de la medición actual).

## Assumptions

- La marca de derogación solo se reconoce al final del título, porque ahí están las 594 medidas;
  si otra fuente la pone en otro sitio, será otra decisión con su medición.
- Solo `repealed` y `revoked`. No se reconocen otras palabras (`spent`, `lapsed`, `expired`)
  porque no aparecen en ningún título medido.
- El aviso no traduce ni interpreta la marca; el cliente la lee tal cual.
- El cambio exige reindexar los corpus; no cambia el formato de los ficheros de la fuente.
- Los demás hallazgos del corpus UK (sin `end_of_validity`, sin `.legalize.yml`, `_PAIS_NOMBRE`
  sin `uk` ni `eu`) quedan fuera de esta spec.

## Clarifications

### Session 2026-10-19

- Q: ¿La fecha de la marca del título se usa como fecha de derogación? → A: no. Solo aparece,
  literal, en `aviso_estado`; no se interpreta ni alimenta `derogada_desde`/`derogada_hasta`
  (FR-007). Hay formatos irregulares y derogaciones parciales cuya fecha no vale para toda la ley.
- Q: ¿Una ley con aviso sigue saliendo al filtrar `estado="in_force"`? → A: no. Sale con
  `repealed` y no con `in_force` (FR-007b). `estadisticas` sigue contando el estado literal del
  corpus y da aparte el número de avisos (FR-009).
