# 0002 — El índice se carga como dicts crudos, sin validarlo con Pydantic

- **Estado:** Aceptada
- **Fecha:** 2026-08-24
- **Ámbito:** `_load_indices`, `_bytes_de` y `_doc_resumen` en `mcp_legalize.py`

## Contexto

Pydantic ya se usa para serializar las respuestas. Validar al cargar los 12.291 documentos
españoles cuesta 0,17 s y 15 MB sobre un arranque de 2,67 s, así que el coste no es el
problema; el motivo antiguo («es caro») era falso (#38). El problema real es qué hacer con un
documento malformado: un modelo lanzaría `ValidationError` y haría perder el índice entero.

## Decisión

Los documentos se guardan como dicts y cada campo se defiende donde se usa (`isinstance`,
degradación a valor neutro, descarte de la entrada). Pydantic solo interviene al construir la
respuesta.

## Alternativas consideradas

- **Validar con un modelo al cargar:** fallar pronto tiene sentido en una API HTTP. Sobre un
  corpus donde viene torcido un documento de doce mil, deja al cliente sin los otros once mil
  novecientos noventa y nueve.
- **Validar con un modelo y descartar la entrada que falle:** viable, pero reparte la política
  entre el modelo y el código, y sigue haciendo falta degradar campo a campo al servir.

## Consecuencias

- **Positivas:** una entrada malformada cuesta esa entrada y nada más (#14, #18).
- **Negativas / costes:** cada lectura de un campo tiene que defenderse de tipos inesperados.
  Hoy no todas lo hacen: un `titulo` o una `fecha_publicacion` que no sean `str` siguen
  tumbando `buscar_ley`.
- **Reglas que se derivan:** los `isinstance` del servidor son la política, no ruido que
  Pydantic pudiera ahorrar. No hay que quitarlos.
