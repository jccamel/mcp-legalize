# mcp-legalize

Servidor MCP de solo lectura que da a un asistente acceso a legislación consolidada de varias jurisdicciones (corpus con el formato Legalize). El corpus se trata como no confiable de punta a punta: el modelo de amenaza es un corpus comprometido, no un cliente comprometido.

Las normas de trabajo de este repositorio están en `CONTRIBUTING.md` y mandan sobre este fichero. Aquí solo va lo operativo de cada sesión.

## Stack y comandos

- Python ≥ 3.12 (modo defensivo de SQLite, ADR 0009), `fastmcp` + `pydantic`. Sin empaquetado: módulos sueltos en la raíz.
- Entorno: `python3 -m venv .venv && .venv/bin/pip install -r requirements.lock`
- Tests: `.venv/bin/python -m pytest -q` (la salida llega filtrada: solo fallos y resumen; el log completo queda en `.claude/logs/`)
- Autotest del escáner: `.venv/bin/python scripts/update_index.py --self-test`
- Indexar un corpus: `.venv/bin/python scripts/update_index.py --repo repos/legalize-XX`
- Frescura de índices: `.venv/bin/python scripts/check_updates.py`
- Arrancar el servidor: `.venv/bin/python mcp_legalize.py` (stdio; stdout es del protocolo JSON-RPC, todo lo demás va a stderr)

## Estructura

- `mcp_legalize.py` — el servidor y sus siete herramientas
- `legalize_injection.py` — único vocabulario de prompt injection (cuerpo y metadatos)
- `legalize_frontmatter.py` — única regla de dónde acaba el frontmatter
- `legalize_tokenizer.py` — única regla de qué es un término (búsqueda a texto completo)
- `legalize_repo.py` — qué commit identifica a un corpus
- `legalize_estado.py` — única regla de cuándo el título de una ley contradice a su estado
- `scripts/` — indexador (`update_index.py`) y comprobación de frescura (`check_updates.py`)
- `tests/` — una prueba por frontera; varias comprueban la propia documentación
- `repos/legalize-mock/`, `indices/index_legalize-mock.db` — corpus mínimo para tests; los corpus reales no se versionan
- `docs/decisiones/` — decisiones de arquitectura (ADR). Índice en `docs/decisiones/README.md`
- `specs/` — especificaciones de features grandes (spec-kit)
- `.specify/memory/constitution.md` — principios del proyecto (spec-kit)

## Convenciones

- Idiomas: comentarios y docstrings del código en español, con todas sus tildes (`test_prose_style.py` lo comprueba); README, CONTRIBUTING y docstrings de `tests/` en inglés. Claves de respuesta en español; los valores del corpus se reproducen literalmente y nunca se traducen.
- Un solo sitio por regla. Si dos partes del código necesitan la misma decisión, comparten el módulo; no se copia.
- Degradar, no fallar: una entrada malformada del índice cuesta esa entrada, nunca el corpus entero.
- Todo lo que sale del corpus hacia el modelo pasa por `_sanitize_metadata` o va dentro de `_wrap_untrusted`.
- Los comentarios explican el porqué, con la medición o el issue que lo justifica.

## Flujo de trabajo

Yo dirijo y verifico; tú escribes el código.

- Bug o comportamiento nuevo: primero el test, y **míralo fallar** antes de arreglar; enséñame en una línea qué falla y por qué. Asserts en el punto de llamada (las herramientas MCP), no en el helper.
- Si un test falla, arregla el código, no el test. No modifiques ni borres tests existentes sin decírmelo antes. `test_the_timestamp_still_moves_with_the_stamp` falla a propósito al añadir campos a `_meta.seguridad`.
- El pre-commit ejecuta la suite: si falla, no hay commit. No intentes saltártelo (`--no-verify`, `core.hooksPath`, editar `.githooks/`).
- Cambio pequeño (1–2 ficheros, intención clara): hazlo directamente y ejecuta los tests.
- Cambio mediano (3+ ficheros o con decisiones de diseño): propón un plan breve antes de editar.
- Feature grande o decisión de diseño: spec-kit (`/speckit-specify` → `/speckit-clarify` → `/speckit-plan` → `/speckit-tasks` → `/speckit-implement`). No pases a `/speckit-implement` sin mi visto bueno a la spec y al plan.
- Cualquier constante que un corpus real pueda superar se mide contra el corpus antes de proponerla.
- Al terminar: tests y `--self-test`; comprueba que no contradice un ADR aceptado; resume en 3–5 líneas qué cambia y cómo lo pruebo.
- Si el cambio toca rutas, el índice, el escáner o lo que se devuelve al modelo, recuérdame ejecutar `/security-review`.
- Git: `main` está protegida; todo va por rama `tipo/descripcion` y PR. Commits *conventional* con cuerpo que explique el porqué, **sin `Co-Authored-By` ni atribución a IA**. No hagas `git push` ni cambies de rama sin que te lo pida.

## Memoria del proyecto (ADR)

- Antes de un cambio que afecte a la arquitectura, a dependencias o a una convención, lee `docs/decisiones/README.md` y abre solo los ADR relevantes.
- Cuando tomemos una decisión de ese tipo, propón un ADR nuevo con `docs/decisiones/0000-plantilla.md` y añádelo al índice.
- No dupliques aquí lo que ya está en un ADR o en `CONTRIBUTING.md`: enlázalo.

## Economía de contexto

- Para búsquedas amplias (dónde se usa X, qué toca Y), delega en el subagente `explorador` y trabaja con su resumen.
- `mcp_legalize.py` y `scripts/update_index.py` pasan de 750 líneas: busca primero y lee el rango necesario.
- No leas `.venv/`, `requirements.lock`, `.claude/logs/` ni corpus en `repos/` salvo que te lo pida.
- Respuestas breves: lo que has cambiado y por qué, sin repetir el diff.

## Compact instructions

Al compactar, conserva: objetivo de la tarea actual, ficheros modificados, decisiones tomadas, tests que fallan y el siguiente paso. Descarta salidas de comandos ya resueltas y exploraciones que no llevaron a nada.

## Seguridad

- Nunca leas ni muestres `.env*`, claves ni tokens. Si los necesitas, pídeme el valor concreto.
- No instales dependencias nuevas sin proponerlas antes.
- Las vulnerabilidades no van a issues públicos: ver `SECURITY.md`.
