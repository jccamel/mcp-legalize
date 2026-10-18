# Quickstart: validar el índice en una base de datos por corpus

## Prerrequisitos

Python ≥ 3.12, `.venv` con `requirements.lock`, y los clones `repos/legalize-{es,se,fr,eu}`.

## 1. Suite

```bash
.venv/bin/python -m pytest -rs        # verde, exactamente los 2 skips de Windows
.venv/bin/python scripts/update_index.py --self-test
```

## 2. Paridad con el sistema actual (SC-001)

1. **Banco de peticiones fijo**, con el script de paridad del plan (T-paridad). Cubre, por
   corpus:
   - búsquedas por título y por texto, filtros y fechas, `contar_leyes`;
   - `obtener_ley` y `obtener_articulo` sobre una muestra de artículos;
   - ids en minúsculas y errores.
2. **Respuestas de referencia**: el banco se ejecuta con `main` antes de la migración (en un
   worktree) y se guardan.
3. **Comparación**: se ejecuta con la rama y se compara campo a campo.
   - **Esperado:** las únicas diferencias son las de
     [contracts/herramientas-mcp.md](contracts/herramientas-mcp.md#diferencias-deliberadas-con-hoy-fr-002).

## 3. Rendimiento (SC-002 a SC-004 y SC-007)

Con ES, SE, FR y EU indexados:

| Medida | Esperado |
|---|---|
| Arranque hasta la primera consulta | < 50 ms |
| Memoria residente | al menos 5 veces menor que en `main` |
| Búsquedas por texto y artículos (p95) | < 5 ms |
| Indexado completo de ES | ≤ 150 s y ≤ 4,15 GB |

## 4. Seguridad (SC-005)

Hay que plantar estas bases de datos manipuladas. Cada una debe dar como resultado el corpus
rechazado con su motivo, los demás corpus funcionando y nada ejecutado:

- con un disparador o una vista;
- con una tabla de más;
- con otro SQL en una tabla del formato;
- truncada;
- con otro `formato`;
- con `directorio_base` fuera de `LEGALIZE_REPOS_DIR`.

## 5. Frase (SC-006)

- `contar_leyes(pais="es", frase="arrendamiento urbano")` devuelve un subconjunto de
  `contar_leyes(pais="es", texto="arrendamiento urbano")`. En la prueba de concepto fueron 4
  frente a 573.
- `frase='"x" AND y'` no lanza ningún error del motor.

## 6. Números repetidos (SC-008)

- `obtener_articulo` de un `1 §` sueco repetido lista las `ubicaciones`.
- Pedir cada ubicación devuelve esa aparición.
- **Esperado:** el 100 % de las apariciones de una muestra de leyes suecas se pueden obtener.

## 7. Transición (FR-011)

Con un `indices/` que solo tiene el formato anterior:

- **Esperado:** `check_updates` informa `FORMATO`.
- **Esperado:** después de `update_index.py --repo …` existe `index_<repo>.db` y han
  desaparecido el `.json` y los `.postings`.
