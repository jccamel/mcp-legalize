#!/usr/bin/env python3
"""
legalize_frontmatter.py
=======================
Única fuente de verdad sobre dónde termina el frontmatter de un documento.

Antes existían tres implementaciones: una en el servidor (regex), otra en el
escáner de seguridad y otra en el parser de metadatos del indexador. Las dos
primeras decidían respectivamente qué se sirve al LLM y qué se escanea en busca
de inyecciones, y no compartían código. Cuando discrepaban quedaba una franja de
texto entregada al modelo que el escáner nunca había mirado — un agujero
demostrable, no teórico.

Reglas del formato (ninguna de las tres implementaciones anteriores las cumplía
por completo):

- El documento debe ABRIR con una línea que sea exactamente ``---``.
- El bloque CIERRA en la primera línea posterior que sea exactamente ``---``.
  Se admite espacio en blanco al final de la línea, pero nada más: ``----------``
  es una regla horizontal de Markdown, no un delimitador.
- Un bloque vacío (``---`` seguido de ``---``) es válido y produce metadatos
  vacíos.
- Sin línea de cierre no hay frontmatter: el documento entero es cuerpo. Es la
  lectura conservadora, y la única segura — así el escáner nunca ve menos texto
  del que el servidor entrega.
"""

_DELIMITADOR = "---"


def separar(texto: str) -> tuple[str, str]:
    """Divide el documento en (bloque_frontmatter, cuerpo).

    Si no hay frontmatter válido devuelve ("", texto): el documento completo es
    cuerpo. El bloque se devuelve sin las líneas delimitadoras.
    """
    if not texto.startswith(_DELIMITADOR):
        return "", texto

    fin_primera = texto.find("\n")
    if fin_primera == -1:
        # Un fichero que es solo "---" no tiene bloque que cerrar.
        return "", texto
    if texto[:fin_primera].rstrip() != _DELIMITADOR:
        return "", texto

    inicio_bloque = fin_primera + 1
    pos = inicio_bloque

    while pos <= len(texto):
        fin_linea = texto.find("\n", pos)
        if fin_linea == -1:
            linea, siguiente = texto[pos:], len(texto)
        else:
            linea, siguiente = texto[pos:fin_linea], fin_linea + 1

        if linea.rstrip() == _DELIMITADOR:
            return texto[inicio_bloque:pos], texto[siguiente:]

        if fin_linea == -1:
            break
        pos = siguiente

    return "", texto


def cuerpo(texto: str) -> str:
    """Devuelve solo el cuerpo, sin el espacio en blanco inicial.

    Es lo que el servidor entrega al LLM y lo que el escáner inspecciona. Que
    ambos llamen aquí es justamente el punto de este módulo.
    """
    return separar(texto)[1].lstrip()


def parsear(texto: str) -> dict[str, str]:
    """Extrae los metadatos del frontmatter como pares clave/valor.

    Formato deliberadamente mínimo (no es YAML): una clave por línea, el primer
    ``:`` separa, y se retiran las comillas simples o dobles que envuelvan el
    valor completo. Las líneas sin ``:`` se ignoran.
    """
    bloque = separar(texto)[0]
    if not bloque:
        return {}

    resultado: dict[str, str] = {}
    for linea in bloque.splitlines():
        if ":" not in linea:
            continue
        clave, _, valor = linea.partition(":")
        clave = clave.strip()
        if not clave:
            continue
        valor = valor.strip()
        if len(valor) >= 2:
            if (valor.startswith('"') and valor.endswith('"')) or \
               (valor.startswith("'") and valor.endswith("'")):
                valor = valor[1:-1]
        resultado[clave] = valor
    return resultado
