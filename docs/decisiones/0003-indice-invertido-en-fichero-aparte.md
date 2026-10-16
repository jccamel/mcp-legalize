# 0003 — Índice invertido en un fichero aparte y cargado bajo demanda

- **Estado:** Sustituida por [0007](0007-postings-en-formato-de-texto-propio.md)
- **Fecha:** 2026-08-24
- **Ámbito:** `scripts/update_index.py` (`_write_invertido`), `mcp_legalize.py` (`_cargar_invertido`)

## Contexto

La búsqueda a texto completo (#31) necesita postings de término a documentos: ~85 MB para el
corpus español y 15 MB para el sueco (8.971 documentos, 146.091 términos). Construirlos al
arrancar el servidor costaría ~9 minutos. El servidor carga al arrancar los 8,7 MB de metadatos
de cada índice JSON.

## Decisión

El indexador construye los postings y los escribe en `inverted_<repo>.bin`, junto al JSON. El
servidor no los carga al arrancar, sino la primera vez que se busca por `texto` en ese país.
Ambos ficheros llevan la huella del tokenizador.

## Alternativas consideradas

- **Una sección dentro del JSON:** `json.load` no puede leer una sección suelta, así que el
  servidor tendría que analizar 85 MB para llegar a los 8,7 MB que necesita, y la carga bajo
  demanda sería imposible.
- **Construirlos en el servidor:** unos 9 minutos de arranque.

## Consecuencias

- **Positivas:** un despliegue que nunca busca por texto no paga ni el tiempo ni la memoria.
- **Negativas / costes:**
  - El `.bin` se escribe con pickle, elegido porque carga 8,9 veces más rápido que el JSON
    equivalente. Esto contradice el principio II de la constitución: el `.bin` es entrada no
    confiable y pickle puede ejecutar código al deserializar. Hace falta un ADR que lo
    sustituya.
  - Una reindexación incremental reescribe el `.bin` solo con los documentos procesados en esa
    pasada.
  - Un cambio de huella del tokenizador no fuerza la reconstrucción.
- **Reglas que se derivan:**
  - Los términos se registran después de la cuarentena y de resolver los ids duplicados.
  - Si no se puede escribir el `.bin`, la pasada no falla.
