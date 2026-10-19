# Feature Specification: Fin de vigencia, con las expiradas separadas de las derogadas

**Feature Branch**: `feat/003-fin-vigencia`

**Created**: 2026-10-19

**Status**: Draft

**Input**: User description: "Fin de vigencia (`end_of_validity`) del corpus europeo, con las
leyes expiradas separadas de las derogadas." Es el último pendiente de la prueba del corpus
europeo; los otros dos, el falso positivo de «User:» y `spec_version`, se cerraron en las
PR #58 y #59.

## Contexto

Una ley deja de estar en vigor de dos maneras distintas: la **deroga** otra norma, o
**expira** porque ella misma fijaba hasta cuándo valía. El servidor solo conoce la primera:
lee la fecha de derogación de `repeal_date`, una extensión de los corpus español y sueco, y la
guarda en el índice como `fecha_derogacion` para los filtros `derogada_desde` y
`derogada_hasta`. Esa fecha no se devuelve en ninguna respuesta: solo sirve para filtrar.

El corpus europeo no trae `repeal_date`. Trae `end_of_validity`, otra extensión (ninguna de
las dos está en el núcleo de la Legalize Format Spec v0.4), con la fecha en que la ley dejó
o dejará de estar en vigor, sea cual sea el motivo. Hoy el servidor la ignora. Medido el
2026-10-19:

| Corpus | Leyes | Derogadas con fecha | Expiradas con fecha | Fecha de origen |
|---|---|---|---|---|
| es | 25.889 | 2.830 de 2.830 | 0 de 2.089 | `repeal_date` |
| se | 8.990 | 5.718 de 5.718 | — | `repeal_date` |
| eu | 18.607 | **0 de 1.107** | **0 de 674** | `end_of_validity`, que hoy se ignora |
| fr | 83 | — | — | ninguna |

En el corpus europeo, `end_of_validity` aparece en 2.267 leyes, todas con fecha `AAAA-MM-DD`
y ninguna con el `9999-12-31` que EUR-Lex usa a veces para «sin fin»:

| `status` | Fecha pasada | Fecha futura |
|---|---|---|
| `repealed` | 1.061 | 0 |
| `expired` | 670 | 0 |
| `in_force` | 11 | 525 |

Las 525 `in_force` con fecha futura son leyes con vigencia programada: siguen en vigor y ya se
sabe cuándo dejarán de estarlo. Las 11 `in_force` con fecha pasada son leyes cuyo estado en el
corpus va por detrás de su fecha.

Consecuencia hoy: un cliente que pregunta qué leyes europeas se derogaron en 2020, o cuáles
expiran el año que viene, no obtiene nada, y no hay nada en la respuesta que le diga que la
fecha existe.

**Decisión previa del usuario:** las expiradas van separadas de las derogadas. Una fecha de
expiración no se presenta como fecha de derogación.

## User Scenarios & Testing *(mandatory)*

Actores: el **cliente** (el asistente que llama a las herramientas) y el **operador** (quien
mantiene los índices).

### User Story 1 - Ver cuándo deja de estar en vigor una ley (Priority: P1)

El cliente consulta una ley europea y recibe la fecha en que dejó o dejará de estar en vigor,
tal como la da la fuente, en un campo propio, con independencia de si se derogó, expiró o
sigue en vigor con fecha de fin prevista.

**Why this priority**: es el dato que hoy se pierde en 2.267 leyes, y sin él no hay nada que
filtrar. Por sí solo ya permite a un cliente responder «¿hasta cuándo estuvo en vigor?».

**Independent Test**: con un corpus sintético con una ley de cada caso (derogada, expirada, en
vigor con fecha futura y sin fecha), las tres primeras devuelven su fecha y la cuarta nada, en
`buscar_ley`, `obtener_ley` y `obtener_articulo`.

**Acceptance Scenarios**:

1. **Given** una ley `expired` con `end_of_validity: 2005-05-20`, **When** el cliente la
   obtiene, **Then** recibe la fecha 2005-05-20 en el campo de fin de vigencia, y los filtros
   de derogación no la encuentran.
2. **Given** una ley `in_force` con `end_of_validity: 2031-01-08`, **When** el cliente la
   obtiene, **Then** recibe la fecha 2031-01-08 como fin de vigencia y su estado sigue siendo
   `in_force`.
3. **Given** una ley sin `end_of_validity`, **When** el cliente la obtiene, **Then** el campo
   de fin de vigencia viene vacío, no con una fecha inventada.

---

### User Story 2 - Filtrar por fecha de fin de vigencia (Priority: P1)

El cliente pregunta qué leyes dejaron o dejarán de estar en vigor en un intervalo («qué
reglamentos expiran en 2027») y recibe exactamente esas, con los mismos límites inclusivos y
la misma precisión de fecha que los demás filtros.

**Why this priority**: es la pregunta que motivó el cambio y la que hoy no tiene respuesta.

**Independent Test**: con el corpus sintético, filtrar por un intervalo devuelve las leyes
cuya fecha de fin cae dentro, combinado con `estado` para separar expiradas de derogadas, y
`contar_leyes` da el mismo número.

**Acceptance Scenarios**:

1. **Given** leyes con fecha de fin en 2026, 2027 y 2028, **When** el cliente filtra el fin de
   vigencia hasta `"2027"`, **Then** recibe las de 2026 y 2027 (todo 2027 incluido).
2. **Given** el mismo filtro con `estado="expired"`, **When** se ejecuta, **Then** solo
   recibe las expiradas.
3. **Given** cualquier combinación de filtros, **When** se pide a `buscar_ley` y a
   `contar_leyes`, **Then** el número coincide.

---

### User Story 3 - Las derogadas europeas, en los filtros de derogación (Priority: P2)

El cliente que ya usa `derogada_desde`/`derogada_hasta` para buscar leyes derogadas en un
periodo encuentra también las europeas, sin cambiar sus llamadas.

**Why this priority**: hace que un filtro que ya existe deje de excluir en silencio un corpus
entero.

**Independent Test**: en el corpus sintético, una ley `repealed` con `end_of_validity` aparece
en los filtros de derogación (Q1), y una `expired` no aparece nunca.

**Acceptance Scenarios**:

1. **Given** una ley europea `repealed` con `end_of_validity: 2017-07-19`, **When** el
   cliente filtra `derogada_desde="2017"`, **Then** la ley aparece, con `fecha_fin_vigencia`
   2017-07-19.
2. **Given** una ley europea `expired` con `end_of_validity: 2010-01-01`, **When** el cliente
   filtra por fecha de derogación, **Then** no aparece.

---

### User Story 4 - El operador reindexa una vez (Priority: P3)

El operador actualiza el servidor y `check_updates.py` le dice qué corpus hay que reindexar
para que la fecha nueva esté disponible, con el remedio de siempre y sin flags.

**Why this priority**: es el coste operativo del cambio; sin él la fecha nueva no llegaría a
los índices ya construidos.

**Independent Test**: con un índice construido antes del cambio, `check_updates` lo informa y
el remedio propuesto lo deja al día.

**Acceptance Scenarios**:

1. **Given** un índice anterior al cambio, **When** el operador ejecuta `check_updates.py`,
   **Then** lo ve informado con su remedio, y ejecutarlo una vez lo resuelve.

---

### Edge Cases

- **`end_of_validity` con otro tipo o forma** (un número, una lista, `"pronto"`, una fecha
  imposible): el campo de fin de vigencia queda vacío para esa ley, la ley se indexa y nada
  más se pierde (degradar, no fallar).
- **`9999-12-31` u otra fecha centinela de «sin fin»**: no aparece en los corpus actuales. La
  fecha se reproduce tal cual, como cualquier otro valor del corpus; no se interpreta.
- **Una ley con `repeal_date` y `end_of_validity` a la vez**: `fecha_derogacion` sigue saliendo
  de `repeal_date`, y el fin de vigencia de `end_of_validity`; ninguna sustituye a la otra.
- **`in_force` con fecha pasada** (11 leyes): se devuelven el estado y la fecha que da el
  corpus, sin corregir ninguno de los dos. El servidor no deduce el estado de la fecha.
- **Corpus sin `end_of_validity`** (es, se, fr): sus respuestas no cambian, salvo por el campo
  nuevo vacío.
- **Un valor hostil** en `end_of_validity`: no es una fecha, así que no llega al cliente; si
  lo fuera, pasa por el mismo saneado que el resto de metadatos.

## Requirements *(mandatory)*

### Functional Requirements

**Dato (historia 1)**

- **FR-001**: El indexador MUST leer `end_of_validity` del frontmatter de cada ley y guardarlo
  en el índice tal como lo da la fuente, siempre que sea una fecha con forma `AAAA-MM-DD`,
  `AAAA-MM` o `AAAA`. Cualquier otro valor MUST dejar el campo vacío para esa ley, sin
  afectar a nada más.
- **FR-002**: `buscar_ley`, `obtener_ley` y `obtener_articulo` MUST devolver esa fecha en un
  campo nuevo y opcional, `fecha_fin_vigencia`, vacío cuando la ley no la tiene. Ningún campo
  existente cambia de nombre, de tipo ni de significado.
- **FR-003**: Una fecha de `end_of_validity` de una ley `expired` MUST NOT usarse nunca como
  fecha de derogación: los filtros de derogación no la encuentran (decisión previa del
  usuario).

**Derogación (historia 3)**

- **FR-004**: Una ley `repealed` sin `repeal_date` pero con `end_of_validity` MUST tomar esa
  fecha también como `fecha_derogacion`, de modo que `derogada_desde`/`derogada_hasta` la
  encuentren sin cambiar las llamadas (Q1). Es una diferencia deliberada en el banco de
  paridad: un campo que salía vacío ahora sale relleno. Solo las leyes `repealed`: una
  `expired` o `in_force` nunca recibe `fecha_derogacion` de `end_of_validity` (FR-003).
- **FR-005**: `fecha_derogacion` de una ley con `repeal_date` MUST seguir saliendo de
  `repeal_date`, exista o no `end_of_validity`.

**Filtros (historia 2)**

- **FR-006**: `buscar_ley` y `contar_leyes` MUST aceptar dos filtros nuevos y opcionales,
  `fin_vigencia_desde` y `fin_vigencia_hasta`, sobre `fecha_fin_vigencia` (Q2), con la misma
  semántica que los demás filtros de fecha: inclusivos en los dos extremos, con la precisión
  del límite (`"2027"` es todo 2027), y exigiendo que la fecha exista.
- **FR-007**: `buscar_ley` y `contar_leyes` MUST describir siempre la misma consulta: el mismo
  conjunto de filtros produce el mismo recuento que resultados devuelve la búsqueda.

**Fecha futura**

- **FR-008**: Una ley `in_force` con `end_of_validity` futura MUST devolver esa fecha en
  `fecha_fin_vigencia`, como cualquier otra (Q3): un solo campo con lo que dice la fuente, y
  el cliente compara con la fecha de hoy si lo necesita. El servidor no compara fechas con el
  día actual ni cambia el estado de la ley según la fecha.

**Lo que se conserva**

- **FR-009**: Los cambios en las herramientas MUST ser solo aditivos: un cliente que no conoce
  los campos ni los filtros nuevos recibe las mismas respuestas que hoy. El banco de paridad
  de la spec 002 (1.178 peticiones) MUST dar 0 diferencias, sin contar los campos nuevos.
- **FR-010**: El nombre del campo nuevo MUST seguir la regla del ADR 0001: clave del servidor
  en castellano; el valor es el de la fuente.
- **FR-011**: El valor MUST pasar por el mismo saneado que el resto de metadatos antes de
  llegar al modelo.
- **FR-012**: El cambio de lo que guarda el índice MUST hacer que los índices construidos
  antes se informen en `check_updates` y se reconstruyan con el remedio de siempre, sin flags
  (ADR 0009).
- **FR-013**: Las instrucciones del servidor y los dos README MUST describir el campo nuevo y,
  si los hay, los filtros nuevos.

### Key Entities *(include if feature involves data)*

- **Fin de vigencia**: la fecha en que una ley dejó o dejará de estar en vigor, por cualquier
  motivo, tal como la da la fuente. Puede ser pasada o futura. Sale de `end_of_validity`.
- **Derogación**: el fin de vigencia causado por otra norma. Su fecha sale de `repeal_date`
  y, en las leyes `repealed` que no lo traen, de `end_of_validity` (Q1).
- **Expiración**: el fin de vigencia que la propia ley fijaba. Se distingue por el estado
  `expired`; su fecha nunca es una fecha de derogación.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Las 2.267 leyes europeas con `end_of_validity` devuelven su fecha de fin de
  vigencia; las que no lo traen, nada.
- **SC-002**: Ninguna de las 670 leyes europeas `expired` aparece con fecha de derogación.
- **SC-003**: Preguntar por las leyes europeas expiradas en un año devuelve exactamente las
  que la fuente fecha en ese año, y el recuento coincide con la búsqueda.
- **SC-004**: El banco de paridad de la spec 002 da 0 diferencias fuera de los campos nuevos,
  en es, eu, fr y se.
- **SC-005**: Un índice construido antes del cambio queda al día con una sola ejecución del
  remedio que propone `check_updates`.

## Clarifications

### Session 2026-10-19

- Q: ¿Las leyes europeas `repealed` entran en los filtros de derogación? → A: sí. En una ley
  `repealed` sin `repeal_date`, `fecha_derogacion` toma `end_of_validity` (FR-004). Las
  expiradas siguen fuera (FR-003).
- Q: ¿El fin de vigencia lleva filtros propios? → A: sí, `fin_vigencia_desde` y
  `fin_vigencia_hasta`, con la semántica de los demás filtros de fecha (FR-006).
- Q: ¿Qué se hace con las leyes `in_force` con fecha de fin futura? → A: la fecha va en
  `fecha_fin_vigencia` como cualquier otra; el servidor no la compara con la fecha de hoy
  (FR-008).

### Corrección del 2026-10-19, al planificar

La primera versión decía que `fecha_derogacion` se devuelve al cliente. No es así: hoy solo
se guarda para filtrar. Se corrigieron el contexto, FR-003 y dos escenarios; las decisiones
Q1–Q3 no cambian, y Q1 sigue siendo lo que encuentran los filtros de derogación. Devolver
también `fecha_derogacion` queda fuera de alcance.

## Assumptions

- `end_of_validity` significa lo mismo en todas las leyes europeas: la fecha en que la ley
  deja de estar en vigor, sea por derogación, por expiración o prevista. Lo confirma su
  presencia en los tres estados.
- La fecha se toma tal cual: el servidor no la compara con la fecha de hoy ni deduce de ella
  el estado.
- Si otro corpus empieza a traer `end_of_validity`, recibe el mismo tratamiento; no hay nada
  específico de la UE en la regla.
- Quedan fuera de alcance los demás campos de extensión europeos (`eli`, `subjects`,
  `entry_into_force`, `document_date`…).
