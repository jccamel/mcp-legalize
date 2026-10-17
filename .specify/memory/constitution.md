# Constitución de mcp-legalize

## Core Principles

### I. Fidelidad a la fuente

Este servidor devuelve lo que dice la ley, nada más.

- Los valores del corpus MUST devolverse literalmente: no se traducen, no se normalizan para
  servirlos ni se reescriben. Las claves son del servidor; los valores son de la norma.
- Ningún resultado MUST ordenarse según una opinión sobre qué norma importa más.
- Un texto devuelto MUST ser el de la fuente y estar completo en la parte que dice cubrir; un
  fragmento cortado o equivocado presentado como completo es el peor fallo posible aquí.
- Un resultado parcial MUST poder distinguirse de uno completo, ya sea por un campo de la
  respuesta (`texto_truncado`) o por una herramienta que dé el total (`contar_leyes`).

*Por qué:* el cliente es un modelo que razona sobre lo que recibe como si fuera la ley. No
tiene forma de detectar una omisión que el servidor no le señale.

### II. El corpus y el índice son entrada no confiable

El modelo de amenaza es un corpus comprometido, no un cliente comprometido.

- Todo texto que sale del corpus hacia el modelo MUST pasar por `_sanitize_metadata` o ir
  dentro de `<untrusted_content>` mediante `_wrap_untrusted`. Ninguna herramienta puede
  quedar exenta.
- El índice y cualquier fichero derivado de él (JSON, postings) MUST tratarse como entrada
  no confiable, igual que el `.md`.
- Una defensa MUST NOT depender de un dato que controla el mismo atacante. Por ejemplo, la raíz
  contra la que se valida una ruta no puede salir del índice que trae esa ruta.
- Un fichero no confiable MUST NOT deserializarse con un formato que pueda ejecutar código.
- El escáner de patrones es un canario, no una defensa; la defensa es el envoltorio. Un
  patrón `block` que salta con texto legal legítimo es un fallo del patrón.

*Por qué:* una defensa que el atacante puede reconfigurar no protege de nada, solo da la
apariencia de hacerlo.

### III. Una sola fuente de verdad por regla

- Cada regla compartida MUST vivir en un único módulo del que todos sus usuarios dependan:
  dónde acaba el frontmatter (`legalize_frontmatter`), qué es una inyección
  (`legalize_injection`), qué es un término (`legalize_tokenizer`) y qué commit identifica
  a un corpus (`legalize_repo`).
- MUST NOT existir dos implementaciones de la misma decisión, ni siquiera "temporalmente".
- Los filtros de búsqueda y de conteo MUST salir del mismo generador.

*Por qué:* cada agujero real de este proyecto vino de dos copias de una regla que
divergieron, como la franja de texto que se servía sin haberse escaneado.

### IV. Degradar, no fallar, pero nunca en silencio

- Una entrada malformada MUST costar solo esa entrada: no la herramienta, ni el índice, ni las
  demás jurisdicciones.
- Una degradación MUST NOT ser indistinguible de un resultado legítimo. Si el cliente no
  puede separar "no hay resultados" de "no se pudo buscar", hay que señalarlo con un error,
  un aviso o un campo.
- Las degradaciones MUST quedar registradas: en stderr o en `_meta.seguridad`.

*Por qué:* fallar pronto y con estrépito sobre un corpus de doce mil documentos deja al cliente
sin los otros once mil novecientos noventa y nueve. Degradar en silencio, en cambio, convierte
un fallo en una respuesta falsa.

### V. Test primero, y visto fallar (NO NEGOCIABLE)

- Todo arreglo o comportamiento nuevo MUST empezar por un test que falle por el motivo correcto,
  y el fallo MUST observarse antes de escribir el arreglo.
- Los asserts MUST ir en el punto de llamada (las herramientas MCP o los scripts), no en el
  helper, cuando el helper por sí solo no prueba el defecto.
- Los tests MUST NOT medir tiempo transcurrido: se cuenta el trabajo repetido.
- Los tests MUST NOT sobreespecificar lo que no es su asunto.
- Si un test falla, se arregla el código. Un test existente MUST NOT modificarse ni borrarse
  sin explicar por qué en el commit.

*Por qué:* un test escrito después del arreglo puede pasar por el motivo equivocado. Ya ocurrió
dos veces (#14 y #22).

### VI. Medir antes de fijar un número; verificar antes de afirmar

- Toda constante que un corpus real pueda superar (longitudes, límites, umbrales) MUST medirse
  contra el corpus antes de proponerse, y la medición MUST citarse junto a la constante.
- "Funciona" MUST afirmarse solo después de leer la salida real, skips incluidos (`pytest -rs`).
  Que la CI esté en verde no basta.
- Los cambios en el indexador o en el cargador MUST verificarse reindexando un corpus real y
  comparando el resultado.

*Por qué:* el tope de #21 se redactó en 1.000 caracteres y el corpus español tiene un título
legítimo de 1.658. Por otro lado, la defensa contra symlinks pasó toda su vida sin ejecutarse
con la suite en verde.

### VII. Sellos derivados del contenido, no versiones a mano

- Lo que describe con qué reglas se construyó o auditó un artefacto MUST ser una huella
  calculada a partir de esas reglas, como `legalize_injection.huella()` y
  `legalize_tokenizer.huella()`, y nunca un número que alguien tenga que acordarse de
  incrementar.
- Un cambio de huella MUST invalidar de verdad el artefacto afectado: forzar su reconstrucción
  completa, no solo avisar.
- La herramienta que detecta un artefacto caducado MUST proponer un remedio que lo resuelva.

*Por qué:* lo que depende de la memoria de alguien se desincroniza, y un sello que no fuerza
nada solo sirve para dar a un índice viejo una fecha nueva.

## Restricciones técnicas

- Python ≥ 3.10, fijado por `fastmcp` y `mcp`; la CI cubre de la 3.10 a la 3.13.
- Dependencias de ejecución: solo `fastmcp` y `pydantic`. Toda dependencia nueva se propone y
  se registra como ADR.
- Sin empaquetado: módulos sueltos en la raíz, sin tabla `[project]`.
- stdout está reservado al protocolo JSON-RPC; todo lo demás va a stderr.
- La documentación que hace afirmaciones comprobables (README, docstrings, tablas de
  configuración) MUST estar cubierta por un test que falle si deja de ser cierta.
- Idiomas: comentarios y docstrings del código en español con todas sus tildes; README,
  CONTRIBUTING y docstrings de `tests/` en inglés.

## Flujo de desarrollo

- Spec-kit (`/speckit-specify` → `/speckit-clarify` → `/speckit-plan` → `/speckit-tasks` →
  `/speckit-implement`) se reserva para features grandes y decisiones de diseño. Los arreglos
  pequeños y medianos siguen el flujo de PR con TDD descrito en `CONTRIBUTING.md`.
- `main` está protegida: los cuatro jobs de CI (`test (3.10)`–`test (3.13)`) MUST pasar y la
  rama MUST estar al día con `main` antes de fusionar.
- Commits *conventional* con un cuerpo que explique el porqué, una unidad de comportamiento por
  commit y sin `Co-Authored-By` ni atribución a IA.
- El cuerpo de cada PR sigue la estructura qué fallaba → arreglo → cambios → plan de pruebas.
- Las decisiones de arquitectura, de dependencias o de convenciones se registran como ADR en
  `docs/decisiones/`. Ningún plan puede contradecir un ADR aceptado sin proponer otro que lo
  sustituya.

## Governance

- Esta constitución prevalece sobre las specs, los planes y las tareas de spec-kit. En lo
  operativo (comandos, forma de commits y PR, CI) manda `CONTRIBUTING.md`, y `CLAUDE.md`
  resume ese contenido para las sesiones con agentes.
- Las enmiendas se hacen por PR, con versión semántica:
  - MAJOR: se retira un principio o se redefine de forma incompatible.
  - MINOR: se añade un principio o una sección, o se amplía materialmente.
  - PATCH: aclaraciones y redacción.
- Cada `/speckit-plan` MUST comprobar su conformidad con los siete principios y justificar por
  escrito cualquier excepción.

**Version**: 1.0.0 | **Ratified**: 2026-10-16 | **Last Amended**: 2026-10-16
