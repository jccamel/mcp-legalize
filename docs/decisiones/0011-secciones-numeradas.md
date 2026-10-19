# 0011 — Una sección numerada solo con su número es un artículo, si la ley no tiene otros

- **Estado:** Aceptada
- **Fecha:** 2026-10-19
- **Ámbito:** `legalize_articulos.py` (`localizar` y `localizar_todos`)

## Contexto

El corpus del Reino Unido (86.671 leyes, incorporado el 2026-10-19) numera cada sección con un
encabezado que contiene solo su número, normalmente bajo otro con el título de la sección:

```markdown
#### Prescribed processes and prescribed substances.
##### 2
```

Las reglas de artículo reconocían `Artículo N`, `Article N`, `N §` y `§ N`, así que
`obtener_articulo` no encontraba ninguna sección británica. Medido el 2026-10-19 sobre una
muestra de 5.000 leyes británicas, 4.940 numeran así sus secciones (70.928 encabezados).

Reconocer cualquier número suelto en todos los corpus tocaría 144 leyes españolas que también
los tienen, 132 de ellas con artículos que ya funcionan.

## Decisión

- Un encabezado que es **solo un número limpio** (`2`, `2A`; no `2.` ni `**2**`) es un artículo
  **solo en una ley sin ningún encabezado de artículo de las formas conocidas**. Se decide por
  documento: donde hay `Artículo N`, nada cambia.
- En esas leyes, otro número suelto cierra el artículo anterior, igual que otro `Artículo M`.
- Si el encabezado justo anterior está un nivel por encima, es el **título de la sección**, y la
  sección se sirve desde él; el título no se repite entonces en su ubicación.
- La regla vive en `legalize_articulos.py` y la aplican igual el indexador
  (`localizar_todos`) y el servidor (`localizar`).

## Alternativas consideradas

| Alternativa | Reino Unido | Leyes españolas afectadas | Por qué no |
|---|---|---|---|
| Número suelto en todos los corpus | sí | 144 (132 con artículos que ya funcionan) | Cambia respuestas que hoy son correctas |
| Solo en el corpus `uk` | sí | 0 | El módulo de artículos pasaría a depender del país |
| Exigir además el título justo encima | 13,5 % de las secciones | 0 | Los reglamentos británicos numeran sin título |
| **Número limpio, en leyes sin otros artículos** | **99 % de las leyes** | **2** | — |

## Consecuencias

- **Positivas:**
  - las secciones del Reino Unido se pueden pedir por número, también las que llevan letra
    (`2A`), y los números que se repiten en los anexos son alcanzables con `capitulo`;
  - el texto de una sección empieza en su título, así que el asistente sabe de qué trata;
  - el banco de paridad da 0 diferencias en es, eu, fr y se.
- **Negativas / costes:** dos leyes españolas sin artículos reconocibles ganan «artículos» que
  no lo son, y se aceptan como coste conocido:
  - en `BOE-A-1997-26034`, los dos apartados numerados de la exposición de motivos (`### 1`,
    `### 2`);
  - en `BOE-A-2025-22252`, un año dentro de una tabla (`### 2024`).

  Solo se alcanzan pidiendo esos números en esas leyes.
- **Reglas que se derivan:**
  - otra forma de numerar artículos entra en `legalize_articulos.py`, con su medición sobre
    todos los corpus;
  - el servidor y el indexador siguen compartiendo la misma función de inicio y la misma
    condición de cierre.
- **Sin cambio de formato:** las leyes afectadas son justo las que antes no tenían filas de
  artículos, y para ellas el servidor ya recurría a localizar sobre el texto, que aplica la regla
  nueva. Reindexar da además las `ubicaciones` de los números repetidos.

## Cómo revertirla

Quitar `_NUMERO_SUELTO` y sus usos en `localizar`, `localizar_todos` e `_inicio`. Las secciones
británicas volverían a ser inalcanzables.
