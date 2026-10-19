# 0010 — Griego y cirílico como términos, conservando й, ї y ў

- **Estado:** Aceptada
- **Fecha:** 2026-10-19
- **Ámbito:** `legalize_tokenizer.py` (patrón de término), `legalize_normalizacion.py` (letras que no se pliegan)
- **Amplía:** [0008](0008-plegado-generico-con-enye.md)

## Contexto

El ADR 0008 dejó el patrón de término en `[0-9a-zñ]{3,}` y anotó que lo que quedaba sin
término era casi todo griego y cirílico, «otra decisión». Una palabra en esos alfabetos no
producía ningún término, así que `texto` no la encontraba: una consulta en cirílico
respondía «sin términos buscables». Medido el 2026-10-19 en los cuerpos:

| Corpus | Leyes con cirílico | Palabras | Leyes con griego | Palabras |
|---|---|---|---|---|
| eu | 496 | 125.345 | 431 | 26.167 |
| es | 35 | 2.113 | 37 | 1.804 |
| fr | 1 | 8 | 1 | 22 |
| se | 0 | 0 | 0 | 0 |

Son, sobre todo, los anexos multilingües de los actos de la Unión.

El plegado genérico del 0008 ya actuaba sobre esos alfabetos y fundía letras que no son
variantes: `й` → `и` (`йод`, yodo, se volvía `иод`), `ї` → `і`, `ў` → `у`. En ruso, búlgaro,
ucraniano y bielorruso son letras propias del alfabeto: el mismo caso que la `ñ`.

## Decisión

- El patrón de término admite el griego y el cirílico ya plegados:
  `[0-9a-zñα-ωа-џґ]{3,}`. Los demás alfabetos siguen fuera.
- `й`, `ї` y `ў` se conservan como letras: se recomponen antes de quitar las marcas, igual
  que la `ñ`. La regla vive en `legalize_normalizacion._CONSERVADAS`, que sustituye a la
  constante que solo recogía la `ñ`.
- `ё` se pliega a `е`, que es la equivalencia habitual al buscar en ruso. El griego pierde
  la tilde y la diéresis, como en cualquier buscador griego.
- La huella del tokenizador cubre la tabla de letras conservadas, así que cambiarla
  invalida los índices construidos antes.

## Alternativas consideradas

- **Plegarlo todo, también `й`, `ї` y `ў`:** es lo que se aceptó para å, ä y ö en sueco
  (ADR 0004). Pero aquí no hay ningún motivo que lo justifique, y fundir *йод* con *иод* es
  el mismo error que fundir *año* con *ano*.
- **Admitir cualquier letra Unicode (`\w`):** dejaría entrar alfabetos que nadie ha mirado,
  con reglas de plegado sin decidir, y cambiaría el patrón en silencio para todo lo que el
  corpus traiga mañana.
- **No tocar nada:** casi un millar de leyes europeas con texto que `texto` no encuentra.

## Consecuencias

- **Positivas:**
  - EU pasa a tener 6.015 términos griegos y 12.763 cirílicos buscables, y ES, 671 y 731;
  - 1.531 términos europeos conservan `й`, `ї` o `ў` en lugar de fundirse con otra palabra;
  - por ejemplo, «регламент» aparece en 47 leyes europeas y «Κανονισμός» en 54; antes, las
    dos consultas respondían «sin términos buscables»;
  - el banco de paridad de las specs 002 y 003, todo en alfabeto latino, da 0 diferencias.
- **Negativas / costes:**
  - la huella del tokenizador cambia, y cada corpus se reescribe una vez: `check_updates`
    lo informa como `TOKENS` y basta con el remedio de siempre. El indexado tarda como uno
    completo (ES, 215 s);
  - el índice de `mock`, que está versionado, se regenera.
- **Reglas que se derivan:**
  - añadir otro alfabeto al patrón es una decisión con su ADR, que fija también qué letras
    no se pliegan;
  - nadie más que `legalize_normalizacion` decide qué letras se conservan, ni nadie más que
    `legalize_tokenizer` qué es un término.

## Cómo revertirla

Quitar los rangos griego y cirílico del patrón, y las tres entradas cirílicas de
`_CONSERVADAS`. La huella cambiaría de nuevo y los índices se reconstruirían solos.
