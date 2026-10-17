# 0005 — Búsqueda por presencia e intersección, sin ranking

- **Estado:** Aceptada
- **Fecha:** 2026-08-24
- **Ámbito:** `legalize_tokenizer.py`; `_docs_con_texto` y `_filtrar_docs` en `mcp_legalize.py`

## Contexto

`texto` tiene que encontrar normas cuyo cuerpo contenga unos términos. Hay dos diseños
posibles: guardar presencia (si el documento contiene el término) o frecuencia (para poder
ordenar por relevancia).

## Decisión

Los postings registran solo presencia. Una consulta devuelve los documentos que contienen
**todos** sus términos, en cualquier orden. Los resultados salen en el orden del corpus.

## Alternativas consideradas

- **Unión de términos:** sobre este corpus devolvería casi todos los documentos.
- **Ranking por frecuencia (TF-IDF, BM25):** duplica el tamaño de los postings y supone opinar
  sobre qué norma importa más, y este servidor no opina.

## Consecuencias

- **Positivas:** postings de ~85 MB en lugar del doble; resultados reproducibles.
- **Negativas / costes:** los primeros `limite` resultados son arbitrarios. Por eso existe
  `contar_leyes`: un cliente tiene que poder saber que ha visto 100 de 1.092. Los términos de
  menos de 3 caracteres se descartan, también en la consulta.
- **Reglas que se derivan:** si algún día se guarda la frecuencia, el modo forma parte de la
  huella del tokenizador e invalida los índices de presencia.
