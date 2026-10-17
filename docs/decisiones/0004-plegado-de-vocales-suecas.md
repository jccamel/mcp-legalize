# 0004 — Se acepta plegar å, ä y ö también en sueco

- **Estado:** Aceptada
- **Fecha:** 2026-08-25
- **Ámbito:** `_NORMALIZE_TABLE` en `mcp_legalize.py`; `legalize_tokenizer.py`

## Contexto

`_normalize` pliega los diacríticos para comparar (`á` → `a`, `å` → `a`). En sueco, å, ä y ö son
letras distintas, no vocales acentuadas, así que el plegado funde palabras sin relación: `får` y
`far`, `ändra` y `andra`. Según la medición de #32, colisiona el 0,7% de los términos, y entre
ellos está el vocabulario legal más frecuente.

## Decisión

Se mantiene una sola tabla de normalización para todo el servidor, sueco incluido.

## Alternativas consideradas

- **Quitar el plegado solo en el tokenizador:** `texto` y `consulta` discreparían sobre el mismo
  documento, que es el tipo de hueco que se cerró al unificar el frontmatter y el vocabulario.
- **Normalización por idioma en todo el servidor:** es un rediseño, no un arreglo, y su
  necesidad depende de si a un lector sueco le resulta inaceptable, cosa que no se puede medir
  desde aquí.

## Consecuencias

- **Positivas:** un único comportamiento, coherente entre título y cuerpo.
- **Negativas / costes:** algunas búsquedas en sueco devuelven falsos positivos.
- **Reglas que se derivan:** la tabla forma parte de `legalize_tokenizer.huella()`, así que si
  cambia, los índices construidos antes quedan invalidados.

## Cómo revertirla

Normalización por idioma en `_normalize` y en el tokenizador a la vez, y reconstrucción de los
índices invertidos afectados.
