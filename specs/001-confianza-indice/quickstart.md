# Quickstart: validar Confianza en el índice

Guía para comprobar de punta a punta que la feature funciona. Los detalles de formato y
contratos están en [data-model.md](data-model.md) y [contracts/](contracts/).

## Prerrequisitos

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.lock
git clone --depth 1 https://github.com/legalize-dev/legalize-se repos/legalize-se
git clone --depth 1 https://github.com/legalize-dev/legalize-es repos/legalize-es   # ~1,9 GiB
```

## 1. Suite y autotest

```bash
.venv/bin/python -m pytest -rs        # verde, exactamente los 2 skips de Windows
.venv/bin/python scripts/update_index.py --self-test
```

## 2. Historia 1: la reindexación incremental no pierde documentos (SC-001, SC-006)

```bash
.venv/bin/python scripts/update_index.py --repo repos/legalize-es
# modificar el 1-5% de los ficheros (p. ej. con os.utime) y volver a indexar, cronometrando:
time .venv/bin/python scripts/update_index.py --repo repos/legalize-es
```

- **Esperado:** con hasta un 5% de cambios, la pasada incremental tarda ≤ 20 s.
- **Esperado:** `contar_leyes(pais="es", texto=...)` da la misma cifra, para un conjunto fijo de
  consultas, que después de un indexado con `--force-all`. Un test automatiza la comparación
  sobre un corpus sintético.

## 3. Historia 2: un índice manipulado no lee fuera del corpus (SC-002)

Con un `indices/index_evil.json` que declare `directorio_base: "/"` y una entrada con
`_ruta: "etc/hosts"`:

- **Esperado:** al arrancar aparece `[SEGURIDAD] … fuera de LEGALIZE_REPOS_DIR …; índice ignorado`.
- **Esperado:** `obtener_ley("X")` no devuelve el contenido de `/etc/hosts`, y los demás países
  responden con normalidad.

## 4. Historia 3: cargar los postings no puede ejecutar código (SC-003)

- Si se coloca un `inverted_legalize-se.bin` (pickle, incluido uno que ejecutaría código) y se
  borra el `.postings`, una búsqueda con `texto` en `se` no ejecuta nada. `contar_leyes`
  informa `sin_consultar=[{pais: "se", motivo: "formato_anterior"}]`.
- Si se corrompe el `.postings` (cabecera falsa, deltas negativos, índices fuera de rango),
  `contar_leyes` informa `motivo: "ilegibles"` y el resto de países no se ve afectado.

## 5. Historia 4: "no se pudo buscar" frente a "sin coincidencias" (SC-004)

| Llamada | Esperado |
|---|---|
| `contar_leyes(texto="zzzz")` con todos los postings bien | `total=0`, `sin_consultar=[]` |
| `contar_leyes(texto="ley")` con `se` sin postings | total de `es`, `sin_consultar=[se: sin_postings]` |
| `buscar_ley(pais="se", texto="ley")` con `se` sin postings | `ErrorRespuesta` que nombra `se` |
| `buscar_ley(texto="de la")` | `ErrorRespuesta`: la consulta no tiene términos buscables |

## 6. Historia 5: el remedio del tokenizador funciona (SC-005)

Se altera `_meta.tokenizador` del índice sueco y luego:

```bash
.venv/bin/python scripts/check_updates.py       # → [SE] TOKENS, propone update_index.py
.venv/bin/python scripts/update_index.py --repo repos/legalize-se
.venv/bin/python scripts/check_updates.py       # → [SE] sin TOKENS
```

- **Esperado:** la segunda orden no responde "ya está al día", sino que reconstruye los postings.

## 7. Arranque sin búsquedas (SC-007)

Se arranca el servidor con los índices de ES y SE y no se busca por texto:

- **Esperado:** no se carga ningún `.postings`.
- **Esperado:** el tiempo de arranque y la memoria residente no empeoran respecto a `main`.
