# 0001 — Las claves son del servidor; los valores, de la ley

- **Estado:** Aceptada
- **Fecha:** 2026-08-20
- **Ámbito:** respuestas de todas las herramientas de `mcp_legalize.py`; `scripts/update_index.py`

## Contexto

El corpus sigue la Legalize Format Spec, cuyo frontmatter usa claves en inglés (`title`, `rank`,
`status`, `source`). Los valores son otra cosa: `estado` trae vocabulario genérico en inglés
(`in_force`, `repealed`…) y `rango` trae términos jurídicos españoles (`real_decreto`,
`ley_organica`) que no tienen equivalente en inglés. Este servidor sirve texto legal.

## Decisión

Las claves de la respuesta son de este servidor y van en español (`titulo`, `rango`, `estado`).
Los valores se reproducen literalmente de la fuente: nunca se traducen ni se normalizan para
servirlos.

## Alternativas consideradas

- **Traducir los valores:** devolver algo distinto de lo que dice la fuente es justo lo que un
  servidor legal no puede hacer, y la mitad del vocabulario no admite traducción.
- **Claves en inglés, como el upstream:** obligaría a cambiar el contrato con los clientes
  existentes sin ganar nada a cambio.

## Consecuencias

- **Positivas:** fidelidad a la fuente (principio I de la constitución).
- **Negativas / costes:** una misma respuesta mezcla idiomas, y el cliente no puede deducir el
  idioma del contenido a partir del de la clave. Las instrucciones del servidor lo advierten.
- **Reglas que se derivan:** literal no significa sin revisar. Los valores son texto del corpus y
  pasan por `_sanitize_metadata` antes de llegar al modelo.
