# 0013 — Plegado de compatibilidad: ordinales, superíndices y ligaduras se buscan por su base

- **Estado:** Aceptada
- **Fecha:** 2026-11-15
- **Ámbito:** `legalize_normalizacion.py` (descomposición y tabla), y por ella el tokenizador y los filtros de metadatos
- **Amplía:** [0008](0008-plegado-generico-con-enye.md), [0010](0010-griego-y-cirilico.md)

## Contexto

La consulta construye sus términos con `legalize_tokenizer._PATRON_TOKEN`, y el índice es
FTS5 `unicode61`. Una palabra con un carácter fuera del patrón era un solo término en el
índice y la consulta la partía o la descartaba, así que `texto` no podía encontrarla nunca
(#74). El ADR 0008 eligió la descomposición canónica (NFD) y dejó fuera a propósito los
ordinales y las ligaduras, «que no son diacríticos». Medido el 2026-11-15, términos del
índice de tres o más caracteres que el patrón no puede producir:

| Corpus | Términos | Sobre todo |
|---|---|---|
| es | 1.010 | ordinales (`13ª`, `30º`: 639), `ˮ`, ligaduras (`aﬁliacion`), `hm³` |
| eu | 6.927 | georgiano (topónimos de anexos), árabe (1.253 términos) |
| uk | 2.692 | superíndices y subíndices (`cm²`, `co₂` en 161 leyes: 2.331), fracciones |
| se | 129 | ordinales |
| fr | 7 | ligaduras, `nm³` |

## Decisión

- El texto se pliega con la descomposición de compatibilidad (NFKD) en vez de la canónica:
  `º` → `o`, `³` → `3`, `₂` → `2`, `ﬁ` → `fi`. `co2` encuentra `co₂`, y al revés.
- La tabla de letras que Unicode no descompone suma `ð` → `d`, `þ` → `th`, `ı` → `i` y
  `ħ` → `h`, como ya tenía `đ` y `ł`.
- Los apóstrofos y las primas que Unicode clasifica como letras modificadoras (`ʼ`, `ʹ`,
  `ʺ`, `ˮ`) separan palabras, como el apóstrofo ASCII: `bishopʼs` contiene `bishop`.
- No entra ningún alfabeto nuevo. El georgiano y el árabe siguen fuera del patrón.

## Alternativas consideradas

- **Ensanchar el patrón con esos caracteres:** `co₂` sería un término, pero solo lo
  encontraría quien escribiera `co₂`; nadie teclea un subíndice para buscar.
- **Una tabla a mano con los ordinales y los superíndices:** es lo que el ADR 0008 dejó atrás
  para los diacríticos; lo que no se enumera se queda fuera.
- **Incluir también el georgiano y el árabe:** el georgiano no tiene mayúsculas ni plegado que
  decidir, pero el árabe sí (vocales cortas, tatweel, formas del alif), y el ADR 0010 pide
  una decisión propia por alfabeto. Quedan medidos aquí para decidirlos aparte.

## Consecuencias

- **Positivas:** de los términos imposibles, pasan a ser buscables 931 de 1.010 en es, 2.653
  de 2.692 en uk, los 129 de se, los 7 de fr y 607 de 6.927 en eu.
- **Negativas / costes:**
  - la huella del tokenizador cambia, y cada corpus se reescribe una vez: `check_updates` lo
    informa como `TOKENS`; el índice de `mock`, versionado, se regenera;
  - una fracción se pliega pegada a su entero: `10½` queda como `101⁄2`, y se encuentra con
    `10½` pero no con `10`. Son 128 términos en uk;
  - siguen fuera 6.320 términos en eu, casi todos georgianos y árabes.
- **Reglas que se derivan:**
  - un carácter de compatibilidad no necesita entrada en la tabla: NFKD ya lo resuelve;
  - añadir un alfabeto al patrón sigue siendo una decisión con su ADR (0010).

## Cómo revertirla

Volver a `NFD` en `legalize_normalizacion.normalizar` y quitar de `TABLA` las entradas
añadidas. La huella cambiaría de nuevo y los índices se reconstruirían solos.
