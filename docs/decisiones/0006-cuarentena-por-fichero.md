# 0006 — Cuarentena por fichero; los metadatos se registran pero no bloquean

- **Estado:** Aceptada
- **Fecha:** 2026-08-21
- **Ámbito:** `scripts/update_index.py`; `legalize_injection.py`

## Contexto

El escáner encuentra patrones de inyección en el cuerpo y en el frontmatter. Antes, un solo
hallazgo abortaba la indexación entera. En los metadatos, `meta.html_tag` salta con títulos
legítimos que llevan corchetes angulares.

## Decisión

- **Cuerpo:** un hallazgo `block` excluye ese fichero del índice (y lo retira si ya estaba
  indexado). El resto del corpus se indexa con normalidad.
- **Metadatos:** los hallazgos se registran en `_meta.seguridad.metadatos` y el documento se
  indexa. El servidor sustituye la coincidencia por `[filtered]` al servirla.

## Alternativas consideradas

- **Abortar la pasada:** unos pocos ficheros sospechosos dejarían sin índice a los otros doce
  mil, lo que equivale a una denegación de servicio autoinfligida.
- **Poner en cuarentena por metadatos:** borraría del corpus leyes reales por un falso positivo
  que el servidor ya neutraliza al servir.

## Consecuencias

- **Positivas:** el corpus sigue disponible aunque haya hallazgos, y cada uno queda registrado
  en el índice.
- **Negativas / costes:** hay que revisar `_meta.seguridad` y los avisos de stderr. En CI,
  `--fail-on-quarantine` convierte una cuarentena nueva en un fallo del build.
- **Reglas que se derivan:**
  - Un patrón `block` que salta con texto legal legítimo se corrige en el patrón; no se fuerza
    el fichero.
  - `--force-index-unsafe` deja constancia en `forzados`.
