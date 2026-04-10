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
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple

_SCRIPT_DIR = Path(__file__).parent
_PROJECT_DIR = _SCRIPT_DIR.parent
DEFAULT_INDICES_DIR = _PROJECT_DIR / "indices"

# Non-law markdown files that must never end up in the index.
_SKIP_STEMS = {"readme", "license", "licence", "contributing", "code_of_conduct", "changelog", "authors"}

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

def _build_entry(md_path: Path, stat: _StatInfo, base_dir: Path, fallback_pais: str) -> tuple[str, dict]:
    text = md_path.read_text(encoding="utf-8", errors="replace")
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
    return doc_id, entry

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
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True,
                        help="Directorio del repositorio de un país (ej. repos/legalize-es).")
    parser.add_argument("--index", type=Path,
                        help="Ruta al index JSON a generar. Si no se indica, va a indices/.")
    parser.add_argument("--pais", type=str,
                        help="Código de país a usar como fallback si no se especifica en yaml (ej. es).")
    parser.add_argument("--force-all", action="store_true")
    parser.add_argument("--remove-orphans", action="store_true")
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
    # Procesar nuevos y actualizados
    for rel in nuevos + actualizados:
        md_path = md_files[rel]
        try:
            doc_id, entry = _build_entry(md_path, md_stats[rel], repo_dir, fallback_pais)
            old_doc_id = ruta_a_docid.get(rel)
            if old_doc_id and old_doc_id != doc_id and old_doc_id in documentos:
                del documentos[old_doc_id]
            documentos[doc_id] = entry
        except Exception as exc:
            _warn(f"Error en {rel}: {exc}")
            errores += 1

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

    print(f"\nEscribiendo índice ({len(documentos):,} docs) …", end=" ", flush=True)
    try:
        _write_atomic(index_path, data)
        print("OK")
    except Exception as exc:
        print(f"\n[ERROR] {exc}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
