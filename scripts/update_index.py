#!/usr/bin/env python3
"""
scripts/update_index.py
=======================
Mantenimiento de los índices `indices/index_<repo>.json`.

Sincroniza el índice de un país con el estado real de los ficheros .md
en su respectivo repositorio (ej. repos/legalize-es).

Soporta subcarpetas arbitrarias usando recursividad (`rglob`).
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple

_SCRIPT_DIR = Path(__file__).parent
_PROJECT_DIR = _SCRIPT_DIR.parent
DEFAULT_INDICES_DIR = _PROJECT_DIR / "indices"

# Non-law markdown files that must never end up in the index.
_SKIP_STEMS = {"readme", "license", "licence", "contributing", "code_of_conduct", "changelog", "authors"}

# Patrones heurísticos multilingües que pueden indicar prompt injection.
# Cubren EN/ES/FR/DE/PT/SE — los idiomas del corpus Legalize.
# IMPORTANTE: esto es un canario, NO una defensa. Un atacante determinado
# puede evadirlo; la defensa real está en _wrap_untrusted (mcp_legalize.py).
_INJECTION_PATTERNS = [
    # ——— Inglés ———
    re.compile(r"ignore\s+(all\s+)?(previous|prior|earlier|above)\s+(instructions?|context|prompts?)", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?(prior|previous|earlier|above)\s+(instructions?|context)", re.IGNORECASE),
    re.compile(r"\byou\s+are\s+now\s+(in\s+)?(maintenance|developer|admin|god|system|debug)\b", re.IGNORECASE),
    re.compile(r"\bnew\s+instructions?\s*:", re.IGNORECASE),
    # ——— Español ———
    re.compile(r"ignora\s+(las\s+|todas\s+las\s+)?instrucciones\s+(previas|anteriores)", re.IGNORECASE),
    re.compile(r"olvida\s+(las\s+|todas\s+las\s+)?instrucciones", re.IGNORECASE),
    re.compile(r"eres\s+ahora\s+(un|una|el|la)\s+", re.IGNORECASE),
    # ——— Francés ———
    re.compile(r"ignorez?\s+(toutes\s+)?(les\s+)?instructions?\s+(précédentes?|antérieures?)", re.IGNORECASE),
    re.compile(r"oubliez?\s+(toutes\s+)?(les\s+)?instructions?", re.IGNORECASE),
    # ——— Alemán ———
    re.compile(r"ignoriere?\s+(alle\s+)?(vorherigen?|vorigen?|früheren?)\s+(anweisungen|befehle)", re.IGNORECASE),
    re.compile(r"vergiss?\s+(alle\s+)?(vorherigen?|vorigen?)\s+", re.IGNORECASE),
    # ——— Portugués ———
    re.compile(r"ignore\s+(todas\s+)?(as\s+)?instru[cç][õo]es\s+(anteriores|pr[ée]vias)", re.IGNORECASE),
    re.compile(r"esque[çc]a\s+(todas\s+)?(as\s+)?instru[cç][õo]es", re.IGNORECASE),
    # ——— Sueco ———
    re.compile(r"ignorera\s+(alla\s+)?(tidigare|föregående)\s+instruktioner", re.IGNORECASE),
    re.compile(r"glöm\s+(alla\s+)?(tidigare|föregående)", re.IGNORECASE),
    # ——— Marcadores de rol genéricos (cualquier idioma) ———
    re.compile(r"^\s*(SYSTEM|ASSISTANT|USER|HUMAN)\s*:\s*", re.IGNORECASE | re.MULTILINE),
    re.compile(r"<\|(im_start|im_end|system|assistant|user)\|>", re.IGNORECASE),
    # ——— Inyección técnica ———
    re.compile(r"<\s*script[\s>]", re.IGNORECASE),
    re.compile(r"<!--|-->", re.IGNORECASE),  # comentarios HTML (pueden esconder instrucciones)
    re.compile(r"\beval\s*\(", re.IGNORECASE),
    re.compile(r"</\s*untrusted_content\s*>", re.IGNORECASE),  # intento de escape del wrap
]

def _normalize_for_scan(text: str) -> str:
    """Normaliza texto para el escaneo de seguridad.

    - NFKC: colapsa ligaduras y formas compatibles (p.ej. ideographic space
      U+3000 → espacio normal, letras matemáticas estilizadas → ASCII).
    - Elimina zero-width joiners y otros caracteres invisibles que suelen
      usarse para ofuscar patrones (ig\u200Bnore → ignore).
    """
    normalized = unicodedata.normalize("NFKC", text)
    # Caracteres invisibles comunes en ataques de ofuscación
    invisible = (
        "\u200b\u200c\u200d\u200e\u200f"  # zero-width space, joiner, marks
        "\u2060\ufeff"                      # word joiner, BOM
        "\u00ad"                            # soft hyphen
    )
    return normalized.translate({ord(c): None for c in invisible})

def _check_injection(md_path: Path, text: str) -> list[str]:
    """Escanea el cuerpo del fichero en busca de patrones de prompt injection.

    Devuelve lista de patrones encontrados (puede estar vacía).
    Emite avisos para cada coincidencia.

    Canario multilingüe: la defensa efectiva está en _wrap_untrusted (mcp_legalize.py).
    """
    # Eliminar frontmatter antes de escanear
    body = text
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            body = text[end + 4:]

    # Normalizar para frustrar ofuscación básica
    body_norm = _normalize_for_scan(body)

    encontrado = []
    for pattern in _INJECTION_PATTERNS:
        m = pattern.search(body_norm)
        if m:
            pattern_name = pattern.pattern[:40]
            snippet = body_norm[max(0, m.start() - 20):m.end() + 20].replace("\n", " ")
            print(
                f"  [AVISO SEGURIDAD] Patrón sospechoso en {md_path.name!r}: "
                f"'{pattern_name}' (pos {m.start()})\n"
                f"    contexto: …{snippet}…",
                file=sys.stderr,
            )
            encontrado.append(pattern_name)
    return encontrado

def _git_head_commit(repo_dir: Path) -> str:
    """Devuelve el hash del commit HEAD del repo git, o '' si no es un repo git."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_dir), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        return ""

def _warn(msg: str) -> None:
    print(f"  [AVISO] {msg}", file=sys.stderr)

def _parse_frontmatter(text: str) -> dict:
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    block = text[3:end].strip()
    result: dict[str, str] = {}
    for line in block.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if len(value) >= 2:
            if (value.startswith('"') and value.endswith('"')) or \
               (value.startswith("'") and value.endswith("'")):
                value = value[1:-1]
        result[key] = value
    return result

class _StatInfo(NamedTuple):
    size: int
    mtime: float

def _get_stat(md_path: Path) -> _StatInfo:
    s = md_path.stat()
    return _StatInfo(size=s.st_size, mtime=s.st_mtime)

def _needs_update(existing: dict, stat: _StatInfo, force: bool) -> bool:
    if force:
        return True
    if existing.get("_bytes", -1) != stat.size:
        return True
    stored_mtime = existing.get("_mtime", 0.0)
    if stored_mtime and stat.mtime > stored_mtime:
        return True
    return False

def _build_entry(md_path: Path, stat: _StatInfo, base_dir: Path, fallback_pais: str) -> tuple[str, dict, list[str]]:
    """Construye una entrada de índice para un documento .md.

    Devuelve (doc_id, entry_dict, security_warnings_list)
    """
    text = md_path.read_text(encoding="utf-8", errors="replace")
    security_warnings = _check_injection(md_path, text)
    meta = _parse_frontmatter(text)

    try:
        ruta_relativa = md_path.relative_to(base_dir).as_posix()
    except ValueError:
        ruta_relativa = str(md_path)

    def _get(*keys: str, default: str = "") -> str:
        for k in keys:
            v = meta.get(k, "")
            if v:
                return v
        return default

    doc_id = _get("identificador", "identifier", default=md_path.stem)
    pais = _get("pais", "country", default=fallback_pais)

    # Prefix purely numerical doc IDs
    if doc_id.isdigit() and pais:
        doc_id = f"{pais}_{doc_id}"

    entry = {
        "titulo":               _get("titulo", "title"),
        "identificador":        doc_id,
        "pais":                 pais,
        "rango":                _get("rango", "rank"),
        "fecha_publicacion":    _get("fecha_publicacion", "publication_date"),
        "ultima_actualizacion": _get("ultima_actualizacion", "last_updated"),
        "estado":               _get("estado", "status"),
        "fuente":               _get("fuente", "source"),
        "_archivo":             md_path.name,
        "_ruta":                ruta_relativa,
        "_bytes":               stat.size,
        "_mtime":               stat.mtime,
    }

    # Campos opcionales: solo se incluyen si están presentes en el frontmatter.
    for field, keys in [
        ("jurisdiccion", ("jurisdiccion", "jurisdiction")),
        ("departamento",  ("departamento", "department")),
        ("fecha_derogacion", ("fecha_derogacion", "repeal_date")),
        ("derogado_por",  ("derogado_por", "repealed_by")),
    ]:
        val = _get(*keys)
        if val:
            entry[field] = val
    return doc_id, entry, security_warnings

def _write_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp", prefix=".index_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

def _load_index(index_path: Path) -> dict:
    if not index_path.exists():
        return {"_meta": {}, "documentos": {}}
    print(f"Cargando índice: {index_path} …")
    try:
        with index_path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:
        print(f"[ERROR] Índice corrupto: {exc}. Reconstruyendo.", file=sys.stderr)
        return {"_meta": {}, "documentos": {}}

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Mantiene índices de repositorios legales Legalize con detección de seguridad."
    )
    parser.add_argument("--repo", type=Path, required=True,
                        help="Directorio del repositorio de un país (ej. repos/legalize-es).")
    parser.add_argument("--index", type=Path,
                        help="Ruta al index JSON a generar. Si no se indica, va a indices/.")
    parser.add_argument("--pais", type=str,
                        help="Código de país a usar como fallback si no se especifica en yaml (ej. es).")
    parser.add_argument("--force-all", action="store_true",
                        help="Reindexar todos los documentos incluso si no han cambiado.")
    parser.add_argument("--remove-orphans", action="store_true",
                        help="Remover documentos del índice que ya no existen en disco.")
    parser.add_argument("--force-index-unsafe", action="store_true",
                        help="Ignorar advertencias de seguridad durante la indexación e indexar todos modos.")
    args = parser.parse_args()

    repo_dir = args.repo.resolve()
    if not repo_dir.is_dir():
        print(f"[ERROR] Directorio del repositorio no encontrado: {repo_dir}", file=sys.stderr)
        sys.exit(1)

    repo_name = repo_dir.name
    fallback_pais = args.pais or (repo_name.replace("legalize-", "") if "legalize-" in repo_name else "")

    index_path = args.index
    if not index_path:
        DEFAULT_INDICES_DIR.mkdir(parents=True, exist_ok=True)
        index_path = DEFAULT_INDICES_DIR / f"index_{repo_name}.json"

    print(f"Indexando repositorio: {repo_dir}")
    print(f"Archivo de índice  : {index_path}")

    data = _load_index(index_path)
    documentos: dict = data.setdefault("documentos", {})
    meta_idx: dict = data.setdefault("_meta", {})

    ruta_a_docid: dict[str, str] = {}
    for k, v in documentos.items():
        ruta = v.get("_ruta", "")
        if ruta:
            ruta_a_docid[ruta] = k

    # Escanear Markdown recursivamente
    md_files = {}
    for p in repo_dir.rglob("*.md"):
        # Evitar repositorios .git internos u ocultos si aplicara
        if ".git" in p.parts:
            continue
        # Skip documentation/meta files that live alongside the corpus.
        if p.stem.lower() in _SKIP_STEMS:
            continue
        try:
            rel_str = p.relative_to(repo_dir).as_posix()
            md_files[rel_str] = p
        except ValueError:
            pass

    md_stats = {rel: _get_stat(p) for rel, p in md_files.items()}

    print(f"Ficheros en disco : {len(md_files):,}")
    print(f"Entradas en índice: {len(documentos):,}")

    nuevos = []
    actualizados = []
    renombrados = []
    docids_validos = set()

    for rel, md_path in md_files.items():
        old_doc_id = ruta_a_docid.get(rel)
        if old_doc_id is not None:
            docids_validos.add(old_doc_id)
            if _needs_update(documentos.get(old_doc_id, {}), md_stats[rel], args.force_all):
                actualizados.append(rel)
        else:
            nuevos.append(rel)

    huerfanos = [d for d in documentos if d not in docids_validos]

    print(f"\nNuevos            : {len(nuevos):,}")
    print(f"Modificados       : {len(actualizados):,}")
    print(f"Huérfanos         : {len(huerfanos):,}")

    if not nuevos and not actualizados and not huerfanos:
        print("\nEl índice ya está al día.")
        return

    errores = 0
    security_warnings_found = {}  # Rastrear avisos de seguridad por fichero

    # Procesar nuevos y actualizados
    for rel in nuevos + actualizados:
        md_path = md_files[rel]
        try:
            doc_id, entry, security_warnings = _build_entry(md_path, md_stats[rel], repo_dir, fallback_pais)
            if security_warnings:
                security_warnings_found[rel] = security_warnings
            old_doc_id = ruta_a_docid.get(rel)
            if old_doc_id and old_doc_id != doc_id and old_doc_id in documentos:
                del documentos[old_doc_id]
            documentos[doc_id] = entry
        except Exception as exc:
            _warn(f"Error en {rel}: {exc}")
            errores += 1

    # Bloqueo de seguridad: si hay avisos y no se pasó --force-index-unsafe, abortar
    if security_warnings_found and not args.force_index_unsafe:
        print(
            f"\n[SECURITY BLOCK] Se detectaron {len(security_warnings_found)} archivo(s) "
            f"con patrones sospechosos. Abortando indexación.\n"
            f"Archivos afectados:",
            file=sys.stderr,
        )
        for fichero in sorted(security_warnings_found.keys()):
            print(f"  - {fichero}", file=sys.stderr)
        print(
            f"\nPara continuar a pesar de las advertencias, usa:\n"
            f"  python scripts/update_index.py --repo {args.repo.name} --force-index-unsafe",
            file=sys.stderr,
        )
        sys.exit(1)

    if args.remove_orphans:
        for doc_id in huerfanos:
            documentos.pop(doc_id, None)

    try:
        base_dir_str = repo_dir.relative_to(_PROJECT_DIR).as_posix()
    except ValueError:
        base_dir_str = str(repo_dir)

    meta_idx["generado_en"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    meta_idx["total_documentos"] = len(documentos)
    meta_idx["directorio_base"] = base_dir_str
    meta_idx["pais_predeterminado"] = fallback_pais
    meta_idx.setdefault("version", "2.0.0")

    # Si se forzó la indexación con advertencias, dejar constancia en el índice
    # para que un revisor posterior sepa que hubo que bypassar el bloqueo.
    if security_warnings_found and args.force_index_unsafe:
        meta_idx["security_warnings_acknowledged"] = {
            "count": len(security_warnings_found),
            "files": sorted(security_warnings_found.keys()),
            "forced_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
        }

    commit = _git_head_commit(repo_dir)
    if commit:
        meta_idx["git_commit"] = commit

    print(f"\nEscribiendo índice ({len(documentos):,} docs) …", end=" ", flush=True)
    try:
        _write_atomic(index_path, data)
        print("OK")
    except Exception as exc:
        print(f"\n[ERROR] {exc}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
