#!/usr/bin/env python3
"""
`legalize_articulos.py`
=======================
Única fuente de verdad sobre qué es un artículo dentro del cuerpo de una ley y
dónde empieza y acaba.

Lo usan el indexador, que localiza todos los artículos una vez al escribir el
índice (spec 002), y el servidor, que los lee de ahí y recurre a `localizar`
sobre el fichero cuando el índice no los tiene: documentos sin encabezados
Markdown, o un fichero que cambió después de indexarse. Las dos vías aplican las
mismas reglas porque las dos salen de aquí.

Antes se buscaba `artículo N` en cualquier punto del cuerpo y se cortaba en el
siguiente `artículo M` en cualquier punto. La prosa legal está llena de
remisiones, así que las dos búsquedas caían en frases y no en títulos. Medido
sobre el corpus español el 2026-10-17, en 20.473 artículos con encabezado: el
18,2% empezaba en otro sitio y el 26,0% se cortaba antes del siguiente (#44).

Los corpus marcan los artículos como encabezados Markdown —`###### Artículo
N.` en el español, `##### N §` en el sueco—, así que se buscan primero ahí, y
el artículo acaba en el siguiente encabezado de su nivel o de uno superior, o
en el siguiente artículo: nunca en una remisión.
"""

import re

ENCABEZADO_RE = re.compile(r"^(#{1,6})[ \t]+(.*)$", re.MULTILINE)

# Tras el número pedido no puede seguir nada que lo continúe: ni letra ni
# dígito, ni `-` ni `*`. Con `\b`, que encaja justo ante un guion,
# `articulo="L110"` devolvía `Article L110-1`, y un `L123-1` inexistente habría
# devuelto `L123-1-1`. La numeración de los códigos franceses es así
# (`L110-1`, `L123-1-1`, `R*512-9-3`), y se encontró al probar `legalize-fr` el
# 2026-10-18: el cliente pedía un artículo y recibía otro (#49).
#
# `CUALQUIER_NUMERO` es el término que reconoce "otro artículo" para decidir
# dónde acaba uno: además de dígitos admite los prefijos de los códigos
# franceses (`L`, `R`, `D`, `A`, `LO`, `R*`).
CUALQUIER_NUMERO = r"[A-Za-z]{0,2}\*?\d[\w*-]*"

# Formas del TEXTO de un encabezado que lo identifican como el artículo `term`.
# Medidas en `legalize-es`: `Artículo N.`, `Art. N.`, `ARTÍCULO N`, `**Artículo
# N.**`; en `legalize-se`: `N §`.
ARTICULO_EN_ENCABEZADO_TEMPLATE = [
    # Español / portugués: "Artículo 3", "ARTÍCULO 3", "Art. 3", "**Artículo 3.**"
    r"(?i)^\**\s*(?:art[ií]culo|art\.)\s*{term}(?![\w*-])",
    # Francés: "Article L135", "Article 3"
    r"(?i)^\**\s*article\s+{term}(?![\w*-])",
    # Sueco: "3 §" (número ANTES del §)
    r"^{term}\s*§",
    # Alemán / austriaco moderno: "§ 3" (§ ANTES del número)
    r"^§\s*{term}(?![\w*-])",
    # Austriaco antiguo: "§. 3."
    r"^§\.\s*{term}\.",
]

# Para enumerar los artículos al indexar hace falta el número de cada
# encabezado, no comprobar uno dado. Son las mismas plantillas con el término
# capturado. El sueco admite una letra tras el número (`1 a §`), que es como se
# pide: con `term="1 a"` la plantilla de arriba encaja con ese encabezado.
_NUMERO_SUECO = r"\d+(?: ?[a-z])?"
_CAPTURAS = [
    re.compile(tpl.format(term=f"(?P<n>{_NUMERO_SUECO if '§' in tpl and tpl.startswith('^{term}') else CUALQUIER_NUMERO})"))
    for tpl in ARTICULO_EN_ENCABEZADO_TEMPLATE
]
_OTRO_ARTICULO = [re.compile(tpl.format(term=CUALQUIER_NUMERO)) for tpl in ARTICULO_EN_ENCABEZADO_TEMPLATE]

# Recurso para documentos sin encabezados Markdown: los patrones de siempre,
# pero anclados a inicio de línea, que es donde va el título de un artículo y
# no una remisión. Lo que solo aparece en mitad de la prosa ya no se devuelve:
# "artículo no encontrado" es mejor respuesta que una frase presentada como ley.
ARTICULO_EN_LINEA_TEMPLATE = [
    r"(?im)^[ \t]*\**[ \t]*(?:art[ií]culo|art\.)[ \t]*{term}(?![\w*-])",
    r"(?im)^[ \t]*Article[ \t]+{term}(?![\w*-])",
    r"(?im)^{term}[ \t]*§",
    r"(?im)^[ \t]*§[ \t]*{term}(?![\w*-])",
    r"(?im)^§\.[ \t]*{term}\.",
    # Número solo en su línea (último recurso)
    r"(?im)^{term}[ \t]*$",
]

# Dónde acaba un artículo localizado por el recurso de línea: el siguiente
# título de artículo o de sección, también anclado a inicio de línea, o
# cualquier encabezado Markdown.
NEXT_SECTION_RE = re.compile(
    r"(?im)"
    # Español/portugués
    r"^[ \t]*\**[ \t]*(?:art[ií]culo|art\.)[ \t]*\d+|"
    # Francés
    r"^[ \t]*Article[ \t]+[LRD]?\d+|"
    # Sueco: "3 §"
    r"^\d+[ \t]*§|"
    # Alemán/austriaco moderno: "§ 3"
    r"^[ \t]*§[ \t]*\d+|"
    # Austriaco antiguo: "§. 3."
    r"^§\.[ \t]*\d+\.|"
    # Estructuras de sección de nivel superior
    r"^TÍTULO[ \t]+|^CAPÍTULO[ \t]+|^LIVRE[ \t]+|"
    # Cualquier encabezado Markdown
    r"^#{1,6}[ \t]",
)

# Separa los niveles de una ubicación: "TÍTULO I › CAPÍTULO II".
SEPARADOR_UBICACION = " › "

# Un encabezado que es solo un número, como numera sus secciones el corpus del
# Reino Unido (`##### 2`, `##### 2A`). Medido el 2026-10-19 en una muestra de
# 5.000 leyes británicas: 4.940 las numeran así. Cuenta como artículo SOLO en
# una ley sin ningún encabezado de artículo de las formas de arriba, y solo
# limpio, sin punto ni marcas: en el corpus español eso deja dos leyes, un
# apartado de una exposición de motivos y un año en una tabla, documentadas en
# el ADR 0011; en eu, fr y se, ninguna.
_NUMERO_SUELTO = re.compile(r"\d+[A-Z]{0,3}")


def es_otro_articulo(texto_encabezado: str) -> bool:
    """Si el texto de un encabezado nombra un artículo, sea cual sea su número."""
    texto = texto_encabezado.strip()
    return any(p.search(texto) for p in _OTRO_ARTICULO)


def _numeros_sueltos(encabezados) -> bool:
    """Si en este documento un encabezado que es solo un número es un artículo.

    Lo es cuando ningún encabezado nombra un artículo de las formas conocidas.
    Se decide por documento, así que donde ya hay `Artículo N` nada cambia.
    """
    return not any(es_otro_articulo(e.group(2)) for e in encabezados)


def _es_suelto(texto_encabezado: str) -> bool:
    return bool(_NUMERO_SUELTO.fullmatch(texto_encabezado.strip()))


def _inicio(encabezados, i: int, sueltos: bool) -> int:
    """Dónde empieza el artículo del encabezado `i`.

    En una sección numerada solo con su número, el encabezado justo anterior,
    un nivel por encima, es su título (`#### Prescribed processes…` sobre
    `##### 2`): la sección empieza en él, para que el texto diga de qué trata.
    En los demás documentos, en el propio encabezado, como siempre.
    """
    enc = encabezados[i]
    if sueltos and i > 0:
        previo = encabezados[i - 1]
        if (len(previo.group(1)) == len(enc.group(1)) - 1
                and not _es_suelto(previo.group(2))):
            return previo.start()
    return enc.start()


def localizar(content: str, articulo: str, contexto_chars: int) -> tuple[int, int, int] | None:
    """`(inicio, fin, fin_real)` del artículo en `content`, o None si no se encuentra.

    `fin_real` es donde acaba el artículo según el documento; `fin`, donde se
    corta lo que se devuelve. Solo difieren cuando nada marca el final y se
    aplica `contexto_chars`: entonces el artículo llega hasta el final del
    documento y lo devuelto es un trozo. Quien llama lo usa para decirlo.

    Primero entre los encabezados Markdown, en orden de documento: el artículo
    acaba en el siguiente encabezado de igual o menor número de `#`, es decir,
    del mismo nivel o superior, o en el siguiente artículo aunque esté en un
    nivel inferior. Hay documentos con los niveles invertidos —`# Artículo 5` y
    después `###### Artículo 18`— y la regla del nivel por sí sola hacía que el
    5 se tragara el 18. Si ningún encabezado lo nombra, se recurre a los
    patrones anclados a inicio de línea.
    """
    term = re.escape(articulo)
    patrones = [re.compile(tpl.format(term=term)) for tpl in ARTICULO_EN_ENCABEZADO_TEMPLATE]
    encabezados = list(ENCABEZADO_RE.finditer(content))
    sueltos = _numeros_sueltos(encabezados)
    for i, enc in enumerate(encabezados):
        texto_enc = enc.group(2).strip()
        if (any(p.search(texto_enc) for p in patrones)
                or (sueltos and _es_suelto(texto_enc) and texto_enc.casefold() == articulo.casefold())):
            nivel = len(enc.group(1))
            siguiente = next(
                (e for e in encabezados[i + 1:]
                 if len(e.group(1)) <= nivel or es_otro_articulo(e.group(2))
                 or (sueltos and _es_suelto(e.group(2)))),
                None,
            )
            inicio = _inicio(encabezados, i, sueltos)
            if siguiente:
                return inicio, siguiente.start(), siguiente.start()
            return inicio, min(enc.end() + contexto_chars, len(content)), len(content)

    for tpl in ARTICULO_EN_LINEA_TEMPLATE:
        m = re.search(tpl.format(term=term), content)
        if m:
            siguiente = NEXT_SECTION_RE.search(content, m.end())
            if siguiente:
                return m.start(), siguiente.start(), siguiente.start()
            return m.start(), min(m.end() + contexto_chars, len(content)), len(content)
    return None


def _numero(texto_encabezado: str) -> str | None:
    texto = texto_encabezado.strip()
    for captura in _CAPTURAS:
        m = captura.search(texto)
        if m:
            return m.group("n")
    return None


def localizar_todos(cuerpo: str) -> list[tuple[int, str, str, int, int, int, bool]]:
    """Todos los artículos con encabezado: `(orden, numero, ubicacion, inicio, fin_encabezado, fin, abierto)`.

    Una sola pasada lineal con la misma regla de final que `localizar`. Es
    lineal porque esa regla deja como mucho un artículo abierto a la vez:
    cualquier encabezado que sea un artículo cierra el anterior, y uno que no
    lo sea lo cierra si es de su nivel o superior.

    `abierto` dice que nada marca su final: `fin` es entonces el final del
    cuerpo, y quien lo sirve aplica `contexto_chars` desde `fin_encabezado`,
    exactamente como hace `localizar`.

    La ubicación son los encabezados de nivel superior que lo contienen —los
    que no son artículos—, unidos con `SEPARADOR_UBICACION`. Si el documento
    abre con un único encabezado de nivel 1, es el título de la ley y no se
    repite en cada ubicación. Dos apariciones con la misma ubicación se
    distinguen con " (2)", " (3)"…, en orden.
    """
    encabezados = list(ENCABEZADO_RE.finditer(cuerpo))
    sueltos = _numeros_sueltos(encabezados)
    titulos_h1 = [e for e in encabezados if len(e.group(1)) == 1]
    omitir = titulos_h1[0].start() if len(titulos_h1) == 1 else None

    salida: list[list] = []
    abierto: list | None = None
    pila: list[tuple[int, str]] = []
    for i, enc in enumerate(encabezados):
        nivel, texto = len(enc.group(1)), enc.group(2).strip()
        numero = _numero(texto) or (texto if sueltos and _es_suelto(texto) else None)
        # La misma condición de cierre que `localizar`, con la misma función:
        # nivel igual o superior, u otro artículo según `es_otro_articulo` o,
        # en un documento de números sueltos, otro número suelto.
        if abierto is not None and (nivel <= abierto[7] or es_otro_articulo(texto)
                                    or (sueltos and _es_suelto(texto))):
            abierto[5], abierto[6] = enc.start(), False
            abierto = None
        if numero is None:
            while pila and pila[-1][0] >= nivel:
                pila.pop()
            if enc.start() != omitir:
                pila.append((nivel, texto))
            continue
        inicio = _inicio(encabezados, i, sueltos)
        # Si la sección empieza en su título, el título ya va en el texto y no
        # se repite en la ubicación.
        contenedores = [(n, t) for n, t in pila if n < nivel]
        if inicio != enc.start() and contenedores:
            contenedores = contenedores[:-1]
        ubicacion = SEPARADOR_UBICACION.join(t for _, t in contenedores)
        fila = [len(salida), numero, ubicacion, inicio, enc.end(), len(cuerpo), True, nivel]
        salida.append(fila)
        abierto = fila

    vistas: dict[tuple[str, str], int] = {}
    resultado = []
    for orden, numero, ubicacion, inicio, fin_enc, fin, abierto_, _ in salida:
        clave = (numero.casefold(), ubicacion)
        vistas[clave] = vistas.get(clave, 0) + 1
        if vistas[clave] > 1:
            # Sin encabezados por encima, la marca va sola: "(2)", no " (2)".
            ubicacion = f"{ubicacion} ({vistas[clave]})".lstrip()
        resultado.append((orden, numero, ubicacion, inicio, fin_enc, fin, abierto_))
    return resultado
