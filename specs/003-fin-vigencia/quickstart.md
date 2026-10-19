# Quickstart: validar el fin de vigencia

## Prerrequisitos

`.venv` con `requirements.lock` y los clones `repos/legalize-{es,se,fr,eu}` indexados.

## 1. Suite

```bash
.venv/bin/python -m pytest -rs        # verde, exactamente los 2 skips de Windows
.venv/bin/python scripts/update_index.py --self-test
```

## 2. Paridad (SC-004)

Reindexar los cuatro corpus (el formato cambia) y comparar con la referencia de `main` de la
spec 002:

```bash
.venv/bin/python scripts/check_updates.py           # los cuatro, FORMATO
for c in es eu fr se; do .venv/bin/python scripts/update_index.py --repo repos/legalize-$c; done
LEGALIZE_INDICES_DIR=$PWD/indices LEGALIZE_REPOS_DIR=$PWD/repos \
  .venv/bin/python specs/002-indice-sqlite/paridad/banco.py . rama.json
.venv/bin/python specs/002-indice-sqlite/paridad/banco.py --comparar \
  specs/002-indice-sqlite/paridad/referencia-main.json rama.json
```

**Esperado**: 0 diferencias fuera de `fecha_fin_vigencia`, salvo peticiones con filtros de
derogación que ahora encuentran leyes europeas `repealed` (Q1). Cada una se comprueba.

## 3. El dato (SC-001, SC-002)

Sobre el índice europeo:

- 2.267 leyes con `fecha_fin_vigencia`; ninguna sin `end_of_validity` la tiene.
- `contar_leyes(pais="eu", estado="expired", derogada_desde="1900")` → 0.
- `contar_leyes(pais="eu", estado="repealed", derogada_desde="1900")` → 1.061.

## 4. Los filtros (SC-003)

- `contar_leyes(pais="eu", estado="expired", fin_vigencia_desde="2010", fin_vigencia_hasta="2010")`
  coincide con el número de leyes `expired` cuyo `end_of_validity` empieza por `2010`, contado
  directamente sobre los ficheros.
- El mismo filtro en `buscar_ley` con `limite=100` devuelve ese número de resultados (si no
  pasa de 100).

## 5. Operador (SC-005)

Con un índice de formato 1, `check_updates.py` informa `FORMATO`; una ejecución de
`update_index.py --repo <repo>`, sin flags, lo deja al día.
