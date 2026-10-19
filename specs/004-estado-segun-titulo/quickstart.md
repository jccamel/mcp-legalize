# Quickstart: validar el aviso de estado

## Prerrequisitos

`.venv` con `requirements.lock` y los clones `repos/legalize-{es,se,fr,eu,uk}` indexados.

## 1. Suite

```bash
.venv/bin/python -m pytest -rs        # verde, exactamente los skips de siempre
.venv/bin/python scripts/update_index.py --self-test
```

## 2. Operador (historia 3)

```bash
.venv/bin/python scripts/check_updates.py     # los cinco, FORMATO
for c in es eu fr se uk; do .venv/bin/python scripts/update_index.py --repo repos/legalize-$c; done
.venv/bin/python scripts/check_updates.py     # ninguno desfasado
```

## 3. Paridad (SC-003)

```bash
LEGALIZE_INDICES_DIR=$PWD/indices LEGALIZE_REPOS_DIR=$PWD/repos \
  .venv/bin/python specs/002-indice-sqlite/paridad/banco.py . rama.json
.venv/bin/python specs/002-indice-sqlite/paridad/banco.py --comparar \
  specs/002-indice-sqlite/paridad/referencia-main.json rama.json
```

**Esperado**: 0 diferencias en es, eu, fr y se fuera de `aviso_estado` (siempre vacío) y de
las diferencias ya aceptadas en las specs anteriores.

## 4. UK (SC-001, SC-002)

- `contar_leyes(pais="uk", estado="repealed")` → 594, y `buscar_ley` con el mismo filtro y
  `limite` suficiente devuelve 594.
- `contar_leyes(pais="uk", estado="in_force")` → 86.077.
- `estadisticas()` → `avisos_estado` 594; `estados["in_force"]` sigue en 86.671.
- `obtener_ley("ukpga-1963-36", pais="uk")` → `estado: in_force`,
  `aviso_estado: "(Repealed 25.10.1991)"`.
- Ninguna ley sin marca trae `aviso_estado`.

## 5. Rendimiento (SC-005)

p95 de `buscar_ley(pais="uk", estado="repealed")` y de `contar_leyes` igual, con su margen de
ruido, que en `main`.
