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
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple

_SCRIPT_DIR = Path(__file__).parent
_PROJECT_DIR = _SCRIPT_DIR.parent
DEFAULT_INDICES_DIR = _PROJECT_DIR / "indices"

# Este script se ejecuta como `python scripts/update_index.py`, así que sys.path
# arranca en scripts/ y la raíz del proyecto no es importable. Sin esto no se
# puede compartir el parser de frontmatter con el servidor — y compartirlo es
# precisamente lo que impide que escáner y servidor vuelvan a discrepar.
if str(_PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(_PROJECT_DIR))

import legalize_frontmatter  # noqa: E402  (requiere el sys.path de arriba)
import legalize_injection  # noqa: E402  (idem)
import legalize_repo  # noqa: E402  (idem)

# Non-law markdown files that must never end up in the index.
_SKIP_STEMS = {"readme", "license", "licence", "contributing", "code_of_conduct", "changelog", "authors"}

# --- Escaneo de prompt injection ---
#
# El vocabulario vive en legalize_injection: un solo sitio declara qué texto
# parece una inyección, y cada superficie decide qué hacer al encontrarlo. Aquí
# la decisión es cuarentena (BLOCK) o aviso (WARN); en el servidor es sustituir
# el metadato por "[filtered]". Antes había dos tablas independientes, y la de
# los metadatos se había quedado en EN/ES mientras esta crecía a seis idiomas:
# el título de una ley podía decir "Ignoriere alle vorherigen Anweisungen" y
# llegar intacto al modelo en cada resultado de búsqueda.
#
# Sigue siendo un canario, NO una defensa: la defensa real es _wrap_untrusted
# (mcp_legalize.py). Lo que se gana al compartir la tabla es que el canario no
# cante en un idioma distinto según por dónde entre el texto.

SEVERITY_BLOCK = legalize_injection.SEVERITY_BLOCK
SEVERITY_WARN = legalize_injection.SEVERITY_WARN

_Finding = legalize_injection.Finding

def _strip_frontmatter_for_scan(text: str) -> str:
    """Delega en legalize_frontmatter: ver el módulo para las reglas.

    Antes esto buscaba el primer "\\n---" con str.find, que trataba una regla
    horizontal de Markdown como delimitador de cierre y descartaba todo lo que
    hubiera encima. El servidor no cortaba ahí, así que el texto descartado se
    servía igual: un payload colocado en esa franja llegaba al modelo sin haber
    pasado nunca por los patrones de inyección.
    """
    return legalize_frontmatter.cuerpo(text)

def _check_injection(text: str) -> list[_Finding]:
    """Escanea el cuerpo del fichero en busca de patrones de prompt injection.

    Devuelve la lista de hallazgos (puede estar vacía). No imprime nada: quien
    llama decide qué reportar y qué bloquear según la severidad.

    El escaneo cubre el documento COMPLETO, sin techo de tamaño: obtener_articulo
    (mcp_legalize.py) puede extraer texto desde cualquier posición del fichero,
    así que truncar el escaneo abriría un hueco en las normas largas.
    """
    return legalize_injection.escanear(
        _strip_frontmatter_for_scan(text), legalize_injection.SURFACE_BODY,
    )

def _self_test() -> int:
    """Verifica que cada patrón detecta su muestra por el camino REAL.

    Cubre las dos superficies. En el cuerpo el riesgo es el pre-filtro de gates,
    que es lo que hace viable escanear un corpus de ~1 GB y también lo que puede
    dejar un regex mudo sin que nada falle visiblemente. En los metadatos el
    riesgo equivalente son los flags al fundir todos los patrones en un único
    regex de sustitución. Los dos caminos se prueban de punta a punta.
    """
    fallos = legalize_injection.autotest()
    for fallo in fallos:
        print(f"[FALLO] {fallo}", file=sys.stderr)

    total = len(legalize_injection.PATTERNS)
    n_cuerpo = len(legalize_injection.patrones(legalize_injection.SURFACE_BODY))
    n_meta = len(legalize_injection.patrones(legalize_injection.SURFACE_METADATA))
    if fallos:
        print(f"\nself-test: {len(fallos)} fallo(s) sobre {total} patrones.",
              file=sys.stderr)
        return 1
    print(f"self-test OK - {total} patrones detectan su muestra por el camino "
          f"real ({n_cuerpo} en cuerpo, {n_meta} en metadatos).")
    print(f"huella del ruleset de cuerpo: {legalize_injection.huella()}")
    return 0

def _warn(msg: str) -> None:
    print(f"  [AVISO] {msg}", file=sys.stderr)

def _parse_frontmatter(text: str) -> dict:
    """Delega en legalize_frontmatter: ver el módulo para las reglas.

    Comparte la localización del bloque con el escáner y con el servidor, de
    modo que los metadatos indexados salgan siempre de la misma región que los
    otros dos consideran frontmatter.
    """
    return legalize_frontmatter.parsear(text)

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

def _build_entry(md_path: Path, stat: _StatInfo, base_dir: Path, fallback_pais: str) -> tuple[str, dict, list[_Finding]]:
    """Construye una entrada de índice para un documento .md.

    Devuelve (doc_id, entry_dict, hallazgos_de_seguridad)
    """
    text = md_path.read_text(encoding="utf-8", errors="replace")
    hallazgos = _check_injection(text)
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
    return doc_id, entry, hallazgos

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

class _Progress:
    """Reporta avance a stderr durante el escaneo.

    Escanear el corpus completo lleva decenas de segundos. Sin esto el script
    queda mudo el tiempo suficiente para que parezca colgado y alguien lo mate
    con Ctrl+C — que es exactamente lo que pasaba antes.
    """

    def __init__(self, total_files: int, total_bytes: int, cada: float = 0.5):
        self.total_files = total_files
        self.total_bytes = max(total_bytes, 1)
        self.cada = cada
        self.files = 0
        self.bytes = 0
        self.inicio = time.monotonic()
        self._ultimo = 0.0
        self._activo = sys.stderr.isatty()

    def avanzar(self, nbytes: int) -> None:
        self.files += 1
        self.bytes += nbytes
        ahora = time.monotonic()
        if ahora - self._ultimo < self.cada and self.files < self.total_files:
            return
        self._ultimo = ahora
        transcurrido = ahora - self.inicio
        frac = self.bytes / self.total_bytes
        eta = (transcurrido / frac - transcurrido) if frac > 0.01 else 0.0
        linea = (
            f"  escaneando {self.files:,}/{self.total_files:,} "
            f"({frac * 100:5.1f}%)  {self.bytes / 1_048_576:,.0f} MiB  "
            f"ETA {eta:4.0f}s"
        )
        if self._activo:
            print(f"\r{linea:<78}", end="", file=sys.stderr, flush=True)
        elif self.files == self.total_files or self.files % 2000 == 0:
            print(linea, file=sys.stderr, flush=True)

    def cerrar(self) -> None:
        transcurrido = time.monotonic() - self.inicio
        if self._activo:
            print("\r" + " " * 78 + "\r", end="", file=sys.stderr)
        mibs = self.bytes / 1_048_576 / max(transcurrido, 0.001)
        print(
            f"Escaneados        : {self.files:,} ficheros, "
            f"{self.bytes / 1_048_576:,.0f} MiB en {transcurrido:.1f}s ({mibs:,.0f} MiB/s)"
        )

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
    # No es `required` para que --self-test pueda correr sin repositorio.
    parser.add_argument("--repo", type=Path,
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
                        help="Indexar también los ficheros en cuarentena por seguridad.")
    parser.add_argument("--fail-on-quarantine", action="store_true",
                        help="Salir con código 3 si algún fichero quedó en cuarentena. "
                             "El índice se escribe igualmente; pensado para CI.")
    parser.add_argument("--show-warnings", action="store_true",
                        help="Mostrar también los hallazgos informativos (severidad warn), "
                             "que por defecto solo se cuentan en el resumen.")
    parser.add_argument("--self-test", action="store_true",
                        help="Verificar los patrones de seguridad y salir.")
    args = parser.parse_args()

    if args.self_test:
        sys.exit(_self_test())

    # El progreso y los avisos van a stderr (sin buffer) y el resto a stdout.
    # Sin esto, al redirigir la salida a un fichero o a un log de CI, stdout
    # queda en buffer de bloque y el informe aparece desordenado.
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except (AttributeError, OSError):
        pass

    if args.repo is None:
        parser.error("se requiere --repo (salvo con --self-test)")

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

    # Una pasada incremental solo escanea lo que cambió en disco, así que si el
    # ruleset cambia los documentos intactos conservan una auditoría hecha con
    # reglas que ya no existen — y `escaneado_en` se refresca igual, con lo que
    # la fecha pasa a mentir. Cuando la huella no coincide se reescanea todo.
    huella_actual = legalize_injection.huella()
    huella_previa = (meta_idx.get("seguridad") or {}).get("patrones")
    ruleset_cambiado = bool(documentos) and huella_previa != huella_actual
    if ruleset_cambiado:
        if huella_previa:
            print(f"\nReglas de escaneo : {huella_previa} -> {huella_actual} (cambiaron)")
        else:
            print(f"\nReglas de escaneo : {huella_actual} "
                  f"(el índice no registra con cuáles se escaneó)")
        print("                    Se reescanea el corpus completo: la auditoría "
              "anterior ya no es\n                    comparable.")

    forzar = args.force_all or ruleset_cambiado

    nuevos = []
    actualizados = []
    renombrados = []
    docids_validos = set()

    for rel, md_path in md_files.items():
        old_doc_id = ruta_a_docid.get(rel)
        if old_doc_id is not None:
            docids_validos.add(old_doc_id)
            if _needs_update(documentos.get(old_doc_id, {}), md_stats[rel], forzar):
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
    # Ficheros excluidos del índice por hallazgos de severidad `block`.
    cuarentena: dict[str, list[str]] = {}
    # Ficheros con hallazgos `block` que se indexaron por --force-index-unsafe.
    forzados: dict[str, list[str]] = {}
    # Ficheros con hallazgos `warn`: se indexan igual, solo se registran.
    avisos: dict[str, list[str]] = {}

    pendientes = nuevos + actualizados
    progreso = _Progress(len(pendientes), sum(md_stats[r].size for r in pendientes))

    for rel in pendientes:
        md_path = md_files[rel]
        progreso.avanzar(md_stats[rel].size)
        try:
            doc_id, entry, hallazgos = _build_entry(md_path, md_stats[rel], repo_dir, fallback_pais)
        except Exception as exc:
            _warn(f"Error en {rel}: {exc}")
            errores += 1
            continue

        bloqueantes = [h for h in hallazgos if h.severity == SEVERITY_BLOCK]
        informativos = [h for h in hallazgos if h.severity == SEVERITY_WARN]

        if informativos:
            avisos[rel] = [h.label for h in informativos]
            if args.show_warnings:
                for h in informativos:
                    print(f"  [aviso] {rel}: {h.label} (pos {h.pos}) …{h.snippet}…",
                          file=sys.stderr)

        if bloqueantes:
            etiquetas = [h.label for h in bloqueantes]
            if args.force_index_unsafe:
                # Se indexa igualmente, pero queda constancia en el índice de
                # que alguien bypasseó el bloqueo y de qué se bypasseó.
                forzados[rel] = etiquetas
                print(f"  [FORZADO] {rel}: {', '.join(etiquetas)}", file=sys.stderr)
            else:
                cuarentena[rel] = etiquetas
                for h in bloqueantes:
                    print(f"  [CUARENTENA] {rel}: {h.label} (pos {h.pos})\n"
                          f"      contexto: …{h.snippet}…", file=sys.stderr)
                # Si el fichero ya estaba indexado y ahora resulta sospechoso,
                # se retira: dejarlo servido sería peor que no tenerlo.
                old_doc_id = ruta_a_docid.get(rel)
                if old_doc_id:
                    documentos.pop(old_doc_id, None)
                continue

        old_doc_id = ruta_a_docid.get(rel)
        if old_doc_id and old_doc_id != doc_id and old_doc_id in documentos:
            del documentos[old_doc_id]
        documentos[doc_id] = entry

    progreso.cerrar()

    # La cuarentena es por fichero, nunca global: un puñado de documentos
    # sospechosos no puede dejar sin índice a los otros doce mil.
    if cuarentena:
        print(
            f"\n[SEGURIDAD] {len(cuarentena)} fichero(s) en cuarentena "
            f"(excluidos del índice, el resto se indexa igualmente).",
            file=sys.stderr,
        )
        for fichero in sorted(cuarentena):
            print(f"  - {fichero}: {', '.join(cuarentena[fichero])}", file=sys.stderr)
        repo_arg = args.repo.as_posix()
        print(
            f"\nSi revisaste los ficheros y son legítimos, indéxalos con:\n"
            f"  python scripts/update_index.py --repo {repo_arg} --force-index-unsafe",
            file=sys.stderr,
        )

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

    # Estado de seguridad del índice, para que un revisor posterior sepa qué
    # quedó fuera y por qué — o qué se forzó a entrar.
    #
    # Se fusiona con la corrida anterior: una pasada incremental solo escanea
    # los ficheros nuevos o modificados, así que los hallazgos de los que no se
    # tocaron siguen siendo válidos y no pueden desaparecer del registro. Solo
    # se purgan los ficheros que ya no están en disco.
    previo = meta_idx.get("seguridad") or {}
    escaneados = set(pendientes)

    def _fusionar(clave: str, nuevos: dict[str, list[str]]) -> dict[str, list[str]]:
        conservados = {
            f: v for f, v in (previo.get(clave) or {}).items()
            if f in md_files and f not in escaneados
        }
        conservados.update({f: sorted(labels) for f, labels in nuevos.items()})
        return dict(sorted(conservados.items()))

    meta_idx["seguridad"] = {
        "escaneado_en": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
        # Con QUE se auditó, no solo cuándo. Sin esto un cambio de patrón deja
        # el índice con fecha fresca y hallazgos calculados con reglas viejas.
        "patrones": huella_actual,
        "cuarentena": _fusionar("cuarentena", cuarentena),
        "forzados": _fusionar("forzados", forzados),
        "avisos": _fusionar("avisos", avisos),
    }
    # El esquema anterior guardaba esto bajo otra clave; se retira para no dejar
    # dos fuentes de verdad sobre el mismo hecho.
    meta_idx.pop("security_warnings_acknowledged", None)

    commit = legalize_repo.head_commit(repo_dir)
    if commit:
        meta_idx["git_commit"] = commit
    else:
        # Un corpus que no es su propio repositorio no tiene commit que lo
        # identifique. Conservar el anterior sería sellar el índice con el HEAD
        # de otro repositorio, que es justo lo que hacía antes.
        meta_idx.pop("git_commit", None)

    print(f"\nEscribiendo índice ({len(documentos):,} docs) …", end=" ", flush=True)
    try:
        _write_atomic(index_path, data)
        print("OK")
    except Exception as exc:
        print(f"\n[ERROR] {exc}", file=sys.stderr)
        sys.exit(1)

    seguridad = meta_idx["seguridad"]
    print(f"Indexados         : {len(documentos):,}")
    if seguridad["avisos"]:
        print(f"Avisos            : {len(seguridad['avisos']):,} (informativos, indexados)")
    if seguridad["forzados"]:
        print(f"Forzados          : {len(seguridad['forzados']):,} (indexados pese al bloqueo)")
    if seguridad["cuarentena"]:
        print(f"Cuarentena        : {len(seguridad['cuarentena']):,} (excluidos del índice)")
    if errores:
        print(f"Errores           : {errores:,}")

    if cuarentena and args.fail_on_quarantine:
        sys.exit(3)

if __name__ == "__main__":
    main()
