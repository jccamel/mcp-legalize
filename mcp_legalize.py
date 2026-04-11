#!/usr/bin/env python3
"""
mcp_legalize.py
===============
Servidor MCP (Model Context Protocol) para consultar legislación
consolidada en el ecosistema "Legalize". 

Permite consultar cualquier país siempre que esté clonado su
repositorio bajo el estándar SPEC.md e indexado.

Configuración (fichero .env o variables de entorno):
  LEGALIZE_INDICES_DIR       — directorio con los índices .json (default: <script_dir>/indices)
  LEGALIZE_DEFAULT_LIMIT     — resultados por defecto en búsquedas (default: 20)
  LEGALIZE_MAX_CONTENT_CHARS — límite de caracteres al leer ley completa (default: 80000)
"""

import json
import os
import re
import sys
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

try:
    from fastmcp import FastMCP
except ImportError:
    print(
        "[ERROR] El paquete 'fastmcp' no está instalado.\n"
        "  Instálalo con:  pip install fastmcp\n",
        file=sys.stderr,
    )
    sys.exit(1)


# ─────────────────────────── Configuración ───────────────────────────────────

_SCRIPT_DIR = Path(__file__).parent

INDICES_DIR = Path(os.environ.get("LEGALIZE_INDICES_DIR", "") or _SCRIPT_DIR / "indices")
DEFAULT_LIMIT = int(os.environ.get("LEGALIZE_DEFAULT_LIMIT", "20"))
MAX_LIMIT = int(os.environ.get("LEGALIZE_MAX_LIMIT", "100"))
MAX_CONTENT_CHARS = int(os.environ.get("LEGALIZE_MAX_CONTENT_CHARS", "80000"))


# ─────────────────────────── Modelos Pydantic ────────────────────────────────

class DocumentoResumen(BaseModel):
    id: str
    pais: str
    titulo: str
    rango: str
    estado: str
    fecha_publicacion: str
    ultima_actualizacion: str
    fuente: str
    bytes: int

class LeyCompleta(BaseModel):
    id: str
    pais: str
    titulo: str
    rango: str
    estado: str
    fecha_publicacion: str
    ultima_actualizacion: str
    fuente: str
    bytes: int
    texto: Optional[str] = None
    texto_truncado: Optional[bool] = None
    chars_totales: Optional[int] = None
    chars_devueltos: Optional[int] = None

class ArticuloResultado(BaseModel):
    id: str
    pais: str
    titulo: str
    articulo_buscado: str
    texto: Optional[str] = None
    posicion_caracter: Optional[int] = None
    error: Optional[str] = None

class RangoConteo(BaseModel):
    rango: str
    total: int

class AnnoConteo(BaseModel):
    anno: str
    total: int

class PaisInfo(BaseModel):
    codigo: str
    nombre: str
    total_documentos: int
    total_megabytes: float
    indice: str

class Estadisticas(BaseModel):
    total_documentos: int
    total_megabytes: float
    paises: list[str]
    estados: dict[str, int]
    top_rangos: list[RangoConteo]
    top_annos_publicacion: list[AnnoConteo]

class ErrorRespuesta(BaseModel):
    error: str
    sugerencias: Optional[list[str]] = None


# ─────────────────────────── Normalización (necesaria antes de cargar índices) ──

_DIACRITICS_SRC = 'áéíóúàèìòùäëïöüñçåæøÄËÏÖÜÑÇÅÆØ'
_DIACRITICS_DST = 'aeiouaeiouaeiouñcaaoaeiouñcaao'
_NORMALIZE_TABLE = str.maketrans(_DIACRITICS_SRC, _DIACRITICS_DST)

def _normalize(text: str) -> str:
    return text.lower().translate(_NORMALIZE_TABLE)


# ─────────────────────────── Carga Dinámica de Índices ────────────────────────

# Almacenamos los documentos como dicts crudos para evitar el coste de construir
# 50k+ objetos Pydantic al arrancar. Pydantic solo se usa al serializar respuestas.
_DOCS_POR_PAIS: dict[str, dict[str, dict]] = {}
_META_POR_PAIS: dict[str, dict] = {}
_INDEX_FILE_POR_PAIS: dict[str, str] = {}


_PAIS_NOMBRE = {
    "es": "Spain",
    "se": "Sweden",
    "fr": "France",
    "lv": "Latvia",
    "at": "Austria",
    "de": "Germany",
    "kr": "South Korea",
    "it": "Italy",
    "pt": "Portugal",
    "nl": "Netherlands",
    "be": "Belgium",
    "fi": "Finland",
    "dk": "Denmark",
    "no": "Norway",
    "pl": "Poland",
    "mock": "Mock (testing)",
}

def _load_indices():
    if not INDICES_DIR.exists() or not INDICES_DIR.is_dir():
        print(f"[AVISO] Directorio de índices no encontrado: {INDICES_DIR}", file=sys.stderr)
        return

    for index_path in sorted(INDICES_DIR.glob("index_*.json")):
        try:
            with index_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                continue

            meta = data.get("_meta", {})
            pais_code = meta.get("pais_predeterminado") or meta.get("pais") or index_path.stem.replace("index_", "")

            if "documentos" in data:
                docs = data["documentos"]
                _DOCS_POR_PAIS[pais_code] = docs
                _META_POR_PAIS[pais_code] = meta
                _INDEX_FILE_POR_PAIS[pais_code] = index_path.stem

                print(
                    f"[Legalize MCP] [{pais_code.upper()}] {len(docs):,} docs "
                    f"desde {index_path.name}",
                    file=sys.stderr,
                )
        except Exception as exc:
            print(f"[ERROR] No se pudo cargar {index_path.name}: {exc}", file=sys.stderr)

_load_indices()
_TOTAL_DOCS = sum(len(d) for d in _DOCS_POR_PAIS.values())
print(f"[Legalize MCP] Total: {_TOTAL_DOCS:,} documentos en {len(_DOCS_POR_PAIS)} jurisdicción(es).", file=sys.stderr)


# ─────────────────────────── Helpers ─────────────────────────────────────────

_ARTICULO_PATTERNS_TEMPLATE = [
    # Español / portugués: "Artículo 3", "Art. 3"
    r"(?im)art[ií]culo\s+{term}\b",
    r"(?im)^\s*Art\.\s*{term}\b",
    # Francés: "Article L135", "Article 3"
    r"(?im)\bArticle\s+{term}\b",
    # Sueco: "##### 3 §" o "3 §" al inicio de línea (número ANTES del §)
    r"(?im)^#{{0,6}}\s*{term}\s*§",
    # Alemán / austriaco moderno: "##### § 3" o "§ 3" al inicio de línea (§ ANTES del número)
    r"(?im)^#{{0,6}}\s*§\s*{term}\b",
    # Austriaco antiguo: "§. 3."
    r"(?im)^§\.\s*{term}\.",
    # Fallback: número solo al inicio de línea (último recurso)
    r"(?im)^{term}\s*$",
]

# Patrón que detecta el inicio de la SIGUIENTE sección para saber dónde cortar el texto extraído.
_NEXT_SECTION_RE = re.compile(
    r"(?im)"
    # Español/portugués
    r"art[ií]culo\s+\d+|"
    # Francés
    r"Article\s+[LRD]?\d+|"
    # Sueco: "3 §" o heading "## 2 kap."
    r"^\d+\s*§|^#{1,6}\s*\d+\s+kap\b|"
    # Alemán/austriaco moderno: "§ 3"
    r"^#{0,6}\s*§\s*\d+|"
    # Austriaco antiguo: "§. 3."
    r"^§\.\s*\d+\.|"
    # Estructuras de sección de nivel superior
    r"^TÍTULO\s+|^CAPÍTULO\s+|^LIVRE\s+|"
    r"^#{1,3}\s*(Buch|Teil|Abschnitt|Titel|Kapitel|Avdelning|Kapitel)\s+",
    re.MULTILINE,
)

def _doc_resumen(doc_id: str, doc: dict, pais: str) -> DocumentoResumen:
    return DocumentoResumen(
        id=doc_id, pais=pais,
        titulo=doc.get("titulo", ""),
        rango=doc.get("rango", ""),
        estado=doc.get("estado", ""),
        fecha_publicacion=doc.get("fecha_publicacion", ""),
        ultima_actualizacion=doc.get("ultima_actualizacion", ""),
        fuente=doc.get("fuente", ""),
        bytes=doc.get("_bytes", 0),
    )

def _resolve_ruta(doc: dict, pais_code: str) -> Path:
    base = Path(doc.get("_ruta") or doc.get("_archivo", ""))
    if base.is_absolute():
        return base

    meta = _META_POR_PAIS.get(pais_code, {})
    dir_base = meta.get("directorio_base")
    if dir_base:
        return _SCRIPT_DIR / dir_base / base
    return _SCRIPT_DIR / base

def _read_file(doc: dict, pais_code: str) -> str:
    ruta_resuelta = _resolve_ruta(doc, pais_code)
    try:
        return ruta_resuelta.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""

_FRONTMATTER_RE = re.compile(r"\A---\s*\n.*?\n---\s*(?:\n|\r\n|\Z)", re.DOTALL)

def _strip_frontmatter(content: str) -> str:
    m = _FRONTMATTER_RE.match(content)
    if m:
        return content[m.end():].lstrip()
    return content

def _iter_docs(pais: str = ""):
    if pais and pais in _DOCS_POR_PAIS:
        for doc_id, doc in _DOCS_POR_PAIS[pais].items():
            yield pais, doc_id, doc
    else:
        for pais_code, docs in _DOCS_POR_PAIS.items():
            for doc_id, doc in docs.items():
                yield pais_code, doc_id, doc

def _resolve_ley(id_ley: str, pais: str = ""):
    """Resuelve un id (exacto o parcial) a (pais_code, doc_id, doc_dict).

    Devuelve (None, None, None, error_msg) en caso de no encontrarse o ambigüedad.
    """
    id_norm = id_ley.strip().upper().replace(".MD", "")
    paises_a_buscar = [pais] if pais and pais in _DOCS_POR_PAIS else list(_DOCS_POR_PAIS.keys())

    for pais_code in paises_a_buscar:
        docs = _DOCS_POR_PAIS[pais_code]
        if id_norm in docs:
            return pais_code, id_norm, docs[id_norm], None

        matches = [(k, v) for k, v in docs.items() if id_norm in k]
        if len(matches) == 1:
            k, v = matches[0]
            return pais_code, k, v, None
        if len(matches) > 1 and len(paises_a_buscar) == 1:
            return None, None, None, f"ID ambiguo. Coincidencias: {[m[0] for m in matches[:10]]}"

    return None, None, None, f"Ley no encontrada: {id_ley}"



# ─────────────────────────── Servidor MCP ────────────────────────────────────

mcp = FastMCP(
    name="Legalize",
    instructions="""
Servidor de legislación bajo el estándar Legalize (multipaís).

Herramientas disponibles:
- listar_paises: jurisdicciones disponibles e info del corpus.
- buscar_ley: buscar leyes por título, rango, estado, país.
- obtener_ley: lee el contenido de una ley.
- obtener_articulo: extrae el texto de un artículo específico de una ley.
- listar_rangos: rangos (tipos de norma) disponibles con conteos.
- estadisticas: información general del dataset.
""",
)

@mcp.tool()
def listar_paises() -> list[PaisInfo] | ErrorRespuesta:
    if not _DOCS_POR_PAIS:
        return ErrorRespuesta(error="No hay índices disponibles.")

    resultado = []
    for pais_code, docs in _DOCS_POR_PAIS.items():
        total_bytes = sum(d.get("_bytes", 0) for d in docs.values())
        resultado.append(PaisInfo(
            codigo=pais_code,
            nombre=_PAIS_NOMBRE.get(pais_code, pais_code.upper()),
            total_documentos=len(docs),
            total_megabytes=round(total_bytes / 1_048_576, 1),
            indice=_INDEX_FILE_POR_PAIS.get(pais_code, f"index_{pais_code}"),
        ))
    return resultado

@mcp.tool()
def buscar_ley(
    consulta: str = "",
    pais: str = "",
    rango: str = "",
    estado: str = "",
    anno: str = "",
    jurisdiccion: str = "",
    fecha_desde: str = "",
    fecha_hasta: str = "",
    limite: int = DEFAULT_LIMIT,
    offset: int = 0,
) -> list[DocumentoResumen] | ErrorRespuesta:
    """
    Busca leyes por múltiples criterios.

    - consulta: texto libre contra el título.
    - pais: código ISO (es, se, at, de, fr…).
    - rango: tipo de norma (ley, forordning, Verordnung…).
    - estado: in_force, repealed, partially_repealed, annulled, expired.
    - anno: año exacto de publicación (e.g. "2001").
    - jurisdiccion: sub-jurisdicción (e.g. "es-an", "es-ct").
    - fecha_desde / fecha_hasta: rango de fechas de publicación (YYYY-MM-DD o YYYY).
    - limite / offset: paginación.
    """
    if not _DOCS_POR_PAIS:
        return ErrorRespuesta(error="No hay índices disponibles.")

    if pais and pais not in _DOCS_POR_PAIS:
        return ErrorRespuesta(error=f"País '{pais}' no reconocido.", sugerencias=list(_DOCS_POR_PAIS.keys()))

    limite = min(max(1, limite), MAX_LIMIT)
    q_norm          = _normalize(consulta)     if consulta     else ""
    rango_norm      = _normalize(rango)        if rango        else ""
    estado_norm     = _normalize(estado)       if estado       else ""
    jurisdiccion_norm = _normalize(jurisdiccion) if jurisdiccion else ""
    anno_clean      = anno.strip()
    fecha_desde_clean = fecha_desde.strip()
    fecha_hasta_clean = fecha_hasta.strip()

    resultados = []
    skipped = 0

    for pais_code, doc_id, doc in _iter_docs(pais):
        if q_norm            and q_norm            not in _normalize(doc.get("titulo", "")):        continue
        if rango_norm        and rango_norm        not in _normalize(doc.get("rango", "")):         continue
        if estado_norm       and estado_norm       not in _normalize(doc.get("estado", "")):        continue
        if anno_clean        and not doc.get("fecha_publicacion", "").startswith(anno_clean):       continue
        if jurisdiccion_norm and jurisdiccion_norm not in _normalize(doc.get("jurisdiccion", "")):  continue
        fp = doc.get("fecha_publicacion", "")
        if fecha_desde_clean and fp and fp < fecha_desde_clean: continue
        if fecha_hasta_clean and fp and fp > fecha_hasta_clean: continue

        if skipped < offset:
            skipped += 1
            continue

        resultados.append(_doc_resumen(doc_id, doc, pais_code))
        if len(resultados) >= limite:
            break

    return resultados

@mcp.tool()
def obtener_ley(id_ley: str, pais: str = "", solo_metadata: bool = False, max_chars: int = MAX_CONTENT_CHARS) -> LeyCompleta | ErrorRespuesta:
    if not _DOCS_POR_PAIS: return ErrorRespuesta(error="No hay índices disponibles.")

    found_pais, found_id, found_doc, err = _resolve_ley(id_ley, pais)
    if err:
        return ErrorRespuesta(error=err)

    resumen = _doc_resumen(found_id, found_doc, found_pais)
    resultado = LeyCompleta(**resumen.model_dump())

    if not solo_metadata:
        body = _strip_frontmatter(_read_file(found_doc, found_pais))  # type: ignore[arg-type]
        if len(body) > max_chars:
            resultado.texto = body[:max_chars]
            resultado.texto_truncado = True
            resultado.chars_totales = len(body)
            resultado.chars_devueltos = max_chars
        else:
            resultado.texto = body
            resultado.texto_truncado = False

    return resultado

@mcp.tool()
def obtener_articulo(id_ley: str, articulo: str, pais: str = "", contexto_chars: int = MAX_CONTENT_CHARS) -> ArticuloResultado:
    if not _DOCS_POR_PAIS:
        return ArticuloResultado(id="", pais="", titulo="", articulo_buscado=articulo, error="No hay índices disponibles.")

    found_pais, found_id, found_doc, err = _resolve_ley(id_ley, pais)
    if err:
        return ArticuloResultado(id=id_ley.strip().upper().replace(".MD", ""), pais=pais, titulo="", articulo_buscado=articulo, error=err)

    content = _strip_frontmatter(_read_file(found_doc, found_pais))
    articulo_clean = articulo.strip()
    term = re.escape(articulo_clean)
    titulo = found_doc.get("titulo", "")

    for pattern_tpl in _ARTICULO_PATTERNS_TEMPLATE:
        m = re.search(pattern_tpl.format(term=term), content)
        if m:
            start = m.start()
            next_art = _NEXT_SECTION_RE.search(content, m.end())
            end = min(next_art.start() if next_art else m.end() + contexto_chars, len(content))
            return ArticuloResultado(
                id=found_id, pais=found_pais, titulo=titulo,
                articulo_buscado=articulo_clean, texto=content[start:end].strip(), posicion_caracter=start,
            )

    return ArticuloResultado(id=found_id, pais=found_pais, titulo=titulo, articulo_buscado=articulo_clean, error="Artículo no encontrado")

@mcp.tool()
def listar_rangos(pais: str = "") -> list[RangoConteo] | ErrorRespuesta:
    if not _DOCS_POR_PAIS: return ErrorRespuesta(error="No índices disponibles")
    if pais and pais not in _DOCS_POR_PAIS: return ErrorRespuesta(error=f"País '{pais}' desconocido")
    conteo = {}
    for _, _, doc in _iter_docs(pais):
        r = doc.get("rango") or "desconocido"
        conteo[r] = conteo.get(r, 0) + 1
    return [RangoConteo(rango=r, total=c) for r, c in sorted(conteo.items(), key=lambda x: -x[1])]

@mcp.tool()
def estadisticas(pais: str = "") -> Estadisticas | ErrorRespuesta:
    if not _DOCS_POR_PAIS: return ErrorRespuesta(error="No índices disponibles")
    estados, rangos, annos, total_bytes, paises_res = {}, {}, {}, 0, set()
    for p_code, _, doc in _iter_docs(pais):
        paises_res.add(p_code)
        e = doc.get("estado") or "desconocido"
        estados[e] = estados.get(e, 0) + 1
        r = doc.get("rango") or "desconocido"
        rangos[r] = rangos.get(r, 0) + 1
        fp = doc.get("fecha_publicacion", "")
        if fp and len(fp) >= 4:
            a = fp[:4]
            annos[a] = annos.get(a, 0) + 1
        total_bytes += doc.get("_bytes", 0)

    return Estadisticas(
        total_documentos=sum(estados.values()),
        total_megabytes=round(total_bytes / 1_048_576, 1),
        paises=sorted(paises_res), estados=estados,
        top_rangos=[RangoConteo(rango=r, total=c) for r, c in sorted(rangos.items(), key=lambda x: -x[1])[:10]],
        top_annos_publicacion=[AnnoConteo(anno=a, total=c) for a, c in sorted(annos.items(), key=lambda x: -x[1])[:10]]
    )

if __name__ == "__main__":
    mcp.run()
