# 0008 — Plegado genérico de diacríticos, conservando la ñ

- **Estado:** Aceptada
- **Fecha:** 2026-10-18
- **Ámbito:** `legalize_normalizacion.py`, `legalize_tokenizer.py` (patrón de término), `legalize_postings.py` (validación de términos)

## Contexto

El plegado lo decidía una tabla que enumeraba a mano las vocales acentuadas. Lo que no
estaba en ella sobrevivía al plegado, y el patrón de término `[0-9a-z]{3,}` partía la
palabra en fragmentos. Medido el 2026-10-18 sobre muestras de los tres corpus:

| Corpus | Palabras rotas | Ejemplos |
|---|---|---|
| `legalize-fr` | 875 distintas, 1,27% de apariciones | `être` → "tre", `arrêté` → "arr", `contrôle` → "contr", `œuvre` → "uvre" |
| `legalize-es` | 1.864 distintas, 0,48% de apariciones | `año` → ningún término, `España` → "espa", `enseñanza` → "ense" |
| `legalize-se` | 11 distintas | `daß`, `Maßnahmen` |

Los fragmentos chocaban entre sí: `être`, buscado como "tre", encontraba *connaître*,
*paraître* y *maître*. La `ñ` merece un caso aparte: la tabla la conservaba a propósito,
pero el patrón no la admitía, así que la búsqueda por texto española nunca funcionó con
*año*, *España* o *español*.

## Decisión

- Se quitan todas las marcas diacríticas tras la descomposición **canónica** (NFD). Así
  se pliega también un idioma que nadie enumeró.
- La **`ñ` se conserva** como letra: se recompone antes de quitar las marcas, y el patrón
  de término pasa a ser `[0-9a-zñ]{3,}`.
- Una tabla pequeña cubre lo que Unicode no descompone (œ→oe, æ→ae, ß→ss, ø→o, ł→l,
  đ→d) y el punto volado catalán (`col·legi` → `collegi`).
- La huella del tokenizador cubre la función entera, no solo su tabla.
- El formato de postings valida los términos con el patrón del tokenizador y no con una
  copia propia (principio III).

## Alternativas consideradas

| Alternativa | FR rotas | ES rotas | Por qué no |
|---|---|---|---|
| Ampliar la tabla a mano y admitir `ñ` | 35 | 996 | Sigue sin cubrir lo que nadie enumere (ł, ß, ą, č…) |
| NFKD genérico, plegando también la `ñ` | 25 | 547 | Junta *año* con *ano* y *uña* con *una* |
| **NFD genérico conservando la `ñ`** | **28** | **531** | — |

- **NFKD en lugar de NFD:** reescribiría también ordinales y ligaduras (`1º`, `ﬁ`), que
  no son diacríticos.

Lo que queda sin término en ES y FR es casi todo griego y cirílico, de anexos
multilingües de la UE: 496 de 503 en ES y 18 de 22 en FR. Admitir otros alfabetos en el
patrón es otra decisión.

## Consecuencias

- **Positivas:**
  - la búsqueda por texto española encuentra *año* en 14.279 leyes; antes no producía
    ningún término;
  - *forêt* y *foret* dan el mismo resultado;
  - el corpus sueco queda sin palabras rotas;
  - las colisiones bajan en los tres corpus;
  - la búsqueda por título pliega igual, así que `consulta="foret"` encuentra «Forêt».
- **Negativas / costes:**
  - la huella del tokenizador cambia, y cada corpus se reindexa una vez; el indexador lo
    detecta solo y basta con el comando normal;
  - el indexado completo español pasa de 137,6 s a 147,2 s (+7%) y el francés de 16,3 s
    a 16,7 s;
  - el pico de memoria baja de 4,21 GB a 4,15 GB.
- **Reglas que se derivan:**
  - el sueco sigue plegando å ä ö (ADR 0004);
  - nadie más que `legalize_normalizacion` decide cómo se pliega;
  - nadie más que `legalize_tokenizer` decide qué es un término, tampoco el formato de
    postings.

## Cómo revertirla

Volver a una tabla enumerada en `legalize_normalizacion` y al patrón `[0-9a-z]`. La huella
cambiaría de nuevo y los índices se reconstruirían solos.
