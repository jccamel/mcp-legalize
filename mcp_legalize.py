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

from pydantic import BaseModel, Field

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

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

if load_dotenv is not None:
    # Local .env (cwd) takes precedence over the one next to the script.
    load_dotenv(".env", override=False)
    load_dotenv(_SCRIPT_DIR / ".env", override=False)

INDICES_DIR = Path(os.environ.get("LEGALIZE_INDICES_DIR", "") or _SCRIPT_DIR / "indices")
DEFAULT_LIMIT = int(os.environ.get("LEGALIZE_DEFAULT_LIMIT", "20"))
MAX_LIMIT = int(os.environ.get("LEGALIZE_MAX_LIMIT", "100"))
MAX_CONTENT_CHARS = int(os.environ.get("LEGALIZE_MAX_CONTENT_CHARS", "80000"))


# ─────────────────────────── Modelos Pydantic ────────────────────────────────

class DocumentoMeta(BaseModel):
    titulo: str = ""
    rango: str = ""
    estado: str = ""
    fecha_publicacion: str = ""
    ultima_actualizacion: str = ""
    fuente: str = ""
    pais: str = ""
    archivo: str = Field(default="", alias="_archivo")
    ruta: str = Field(default="", alias="_ruta")
    bytes_size: int = Field(default=0, alias="_bytes")
    model_config = {"extra": "allow", "populate_by_name": True}

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


# ─────────────────────────── Carga Dinámica de Índices ────────────────────────

_DOCS_POR_PAIS: dict[str, dict[str, DocumentoMeta]] = {}
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

    for index_path in sorted(INDICES_DIR.glob("*.json")):
        try:
            with index_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                continue
            
            meta = data.get("_meta", {})
            pais_code = meta.get("pais_predeterminado") or meta.get("pais") or index_path.stem.replace("index_", "")

            if "documentos" in data:
                _DOCS_POR_PAIS[pais_code] = {
                    doc_id: DocumentoMeta.model_validate(doc)
                    for doc_id, doc in data["documentos"].items()
                }
                _META_POR_PAIS[pais_code] = meta
                _INDEX_FILE_POR_PAIS[pais_code] = index_path.stem
                
                print(
                    f"[Legalize MCP] [{pais_code.upper()}] {len(_DOCS_POR_PAIS[pais_code]):,} docs "
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
    r"(?im)art[ií]culo\s+{term}\b",
    r"(?im)\bArt\.\s*{term}\b",
    r"(?im)\bArticle\s+{term}\b",
    r"(?im)^{term}\s*§",
    r"(?im)^{term}\s*$",
]
_NEXT_SECTION_RE = re.compile(
    r"(?i)art[ií]culo\s+\d+|^\d+\s*§|Article\s+[LRD]?\d+|^TÍTULO\s+|^CAPÍTULO\s+|^Kapitel\s+|^LIVRE\s+",
    re.MULTILINE,
)

def _doc_resumen(doc_id: str, doc: DocumentoMeta, pais: str) -> DocumentoResumen:
    return DocumentoResumen(
        id=doc_id, pais=pais, titulo=doc.titulo, rango=doc.rango,
        estado=doc.estado, fecha_publicacion=doc.fecha_publicacion,
        ultima_actualizacion=doc.ultima_actualizacion, fuente=doc.fuente,
        bytes=doc.bytes_size,
    )

def _resolve_ruta(doc: DocumentoMeta, pais_code: str) -> Path:
    base = Path(doc.ruta) if doc.ruta else Path(doc.archivo)
    if base.is_absolute():
        return base
    
    meta = _META_POR_PAIS.get(pais_code, {})
    dir_base = meta.get("directorio_base")
    if dir_base:
        return _SCRIPT_DIR / dir_base / base
    return _SCRIPT_DIR / base

def _read_file(doc: DocumentoMeta, pais_code: str) -> str:
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

def _normalize(text: str) -> str:
    _DIACRITICS = {
        'á':'a','é':'e','í':'i','ó':'o','ú':'u',
        'à':'a','è':'e','ì':'i','ò':'o','ù':'u',
        'ä':'a','ë':'e','ï':'i','ö':'o','ü':'u',
        'ñ':'n','ç':'c','å':'a','æ':'a','ø':'o',
        'Ä':'a','Ë':'e','Ï':'i','Ö':'o','Ü':'u','Ñ':'n','Ç':'c','Å':'a','Æ':'a','Ø':'o'
    }
    _src = ''.join(_DIACRITICS.keys())
    _dst = ''.join(_DIACRITICS.values())
    return text.lower().translate(str.maketrans(_src, _dst))

def _iter_docs(pais: str = ""):
    if pais and pais in _DOCS_POR_PAIS:
        for doc_id, doc in _DOCS_POR_PAIS[pais].items():
            yield pais, doc_id, doc
    else:
        for pais_code, docs in _DOCS_POR_PAIS.items():
            for doc_id, doc in docs.items():
                yield pais_code, doc_id, doc

def _resolve_ley(id_ley: str, pais: str = ""):
    """Resuelve un id (exacto o parcial) a (pais_code, doc_id, DocumentoMeta).

    Devuelve (None, None, None, error_msg|None) en caso de no encontrarse o
    ambigüedad. Si se especifica `pais`, solo busca en esa jurisdicción.
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
        total_bytes = sum(d.bytes_size for d in docs.values())
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
    limite: int = DEFAULT_LIMIT,
    offset: int = 0,
) -> list[DocumentoResumen] | ErrorRespuesta:
    if not _DOCS_POR_PAIS:
        return ErrorRespuesta(error="No hay índices disponibles.")
    
    if pais and pais not in _DOCS_POR_PAIS:
        return ErrorRespuesta(error=f"País '{pais}' no reconocido.", sugerencias=list(_DOCS_POR_PAIS.keys()))

    limite = min(max(1, limite), MAX_LIMIT)
    q_norm = _normalize(consulta) if consulta else ""
    rango_norm = _normalize(rango) if rango else ""
    estado_norm = _normalize(estado) if estado else ""
    anno_clean = anno.strip()

    resultados = []
    skipped = 0

    for pais_code, doc_id, doc in _iter_docs(pais):
        if q_norm and q_norm not in _normalize(doc.titulo): continue
        if rango_norm and rango_norm not in _normalize(doc.rango): continue
        if estado_norm and estado_norm not in _normalize(doc.estado): continue
        if anno_clean and not doc.fecha_publicacion.startswith(anno_clean): continue

        if skipped < offset:
            skipped += 1
            continue

        resultados.append(_doc_resumen(doc_id, doc, pais_code))
        if len(resultados) >= limite: break

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
        body = _strip_frontmatter(_read_file(found_doc, found_pais))
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

    for pattern_tpl in _ARTICULO_PATTERNS_TEMPLATE:
        m = re.search(pattern_tpl.format(term=term), content)
        if m:
            start = m.start()
            next_art = _NEXT_SECTION_RE.search(content, m.end())
            end = min(next_art.start() if next_art else m.end() + contexto_chars, len(content))
            return ArticuloResultado(
                id=found_id, pais=found_pais, titulo=found_doc.titulo,
                articulo_buscado=articulo_clean, texto=content[start:end].strip(), posicion_caracter=start,
            )

    return ArticuloResultado(id=found_id, pais=found_pais, titulo=found_doc.titulo, articulo_buscado=articulo_clean, error="Artículo no encontrado")

@mcp.tool()
def listar_rangos(pais: str = "") -> list[RangoConteo] | ErrorRespuesta:
    if not _DOCS_POR_PAIS: return ErrorRespuesta(error="No índices disponibles")
    if pais and pais not in _DOCS_POR_PAIS: return ErrorRespuesta(error=f"País '{pais}' desconocido")
    conteo = {}
    for _, _, doc in _iter_docs(pais):
        r = doc.rango or "desconocido"
        conteo[r] = conteo.get(r, 0) + 1
    return [RangoConteo(rango=r, total=c) for r, c in sorted(conteo.items(), key=lambda x: -x[1])]

@mcp.tool()
def estadisticas(pais: str = "") -> Estadisticas | ErrorRespuesta:
    if not _DOCS_POR_PAIS: return ErrorRespuesta(error="No índices disponibles")
    estados, rangos, annos, total_bytes, paises_res = {}, {}, {}, 0, set()
    for p_code, _, doc in _iter_docs(pais):
        paises_res.add(p_code)
        estados[doc.estado or "desconocido"] = estados.get(doc.estado or "desconocido", 0) + 1
        rangos[doc.rango or "desconocido"] = rangos.get(doc.rango or "desconocido", 0) + 1
        if doc.fecha_publicacion and len(doc.fecha_publicacion) >= 4:
            a = doc.fecha_publicacion[:4]
            annos[a] = annos.get(a, 0) + 1
        total_bytes += doc.bytes_size

    return Estadisticas(
        total_documentos=sum(estados.values()),
        total_megabytes=round(total_bytes / 1_048_576, 1),
        paises=sorted(paises_res), estados=estados,
        top_rangos=[RangoConteo(rango=r, total=c) for r, c in sorted(rangos.items(), key=lambda x: -x[1])[:10]],
        top_annos_publicacion=[AnnoConteo(anno=a, total=c) for a, c in sorted(annos.items(), key=lambda x: -x[1])[:10]]
    )

if __name__ == "__main__":
    mcp.run()
