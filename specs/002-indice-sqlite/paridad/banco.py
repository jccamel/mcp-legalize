"""Banco de paridad de la spec 002: las mismas peticiones contra dos versiones del servidor.

Uso:
    python banco.py <raiz_del_codigo> <salida.json>

`raiz_del_codigo` es el directorio con el `mcp_legalize.py` que se quiere medir: un
worktree de `main` para la referencia, o el repositorio para la rama. El servidor
lee los índices de `LEGALIZE_INDICES_DIR` y los documentos de `LEGALIZE_REPOS_DIR`,
como en producción.

Las peticiones salen de los corpus con semilla fija, así que dos ejecuciones sobre
los mismos corpus piden exactamente lo mismo. Los textos largos se guardan como
`sha256:<hex>|<inicio>`: se comparan exactos sin que la referencia ocupe decenas de
megas.

Comparar dos salidas:
    python banco.py --comparar referencia.json rama.json
"""

import hashlib
import json
import random
import re
import sys
from pathlib import Path

CORPUS = ("es", "se", "fr", "eu")
ARTICULO = re.compile(
    r"^#{1,6}[ \t]+\**\s*(?:(?:art[ií]culo|art\.|article)[\s\xa0]+(?P<a>[A-Za-z]{0,2}\*?\d[\w*-]*)"
    r"|(?P<b>\d+(?: ?[a-z])?)\s*§|§\s*(?P<c>\d[\w-]*))",
    re.MULTILINE | re.IGNORECASE,
)


def compactar(valor):
    """Sustituye los textos largos por su huella, recursivamente."""
    if isinstance(valor, str) and len(valor) > 300:
        return f"sha256:{hashlib.sha256(valor.encode()).hexdigest()}|{valor[:60]}"
    if isinstance(valor, list):
        return [compactar(v) for v in valor]
    if isinstance(valor, dict):
        return {k: compactar(v) for k, v in valor.items()}
    return valor


def volcar(resultado):
    if isinstance(resultado, list):
        return [volcar(r) for r in resultado]
    if hasattr(resultado, "model_dump"):
        return {"_tipo": type(resultado).__name__, **compactar(resultado.model_dump())}
    return compactar(resultado)


def peticiones(m, repos: Path):
    """La lista fija de peticiones, construida a partir de lo que el servidor conoce."""
    yield "listar_paises", {}
    for pais in CORPUS:
        yield "listar_rangos", {"pais": pais}
        yield "estadisticas", {"pais": pais}
    filtros = [
        {"consulta": "proteccion"}, {"consulta": "ley"}, {"consulta": "regulation"},
        {"texto": "arrendamiento urbano"}, {"texto": "personal data protection"},
        {"texto": "skatt"}, {"texto": "forêt domaniale"}, {"texto": "año"}, {"texto": "de la"},
        {"estado": "repealed"}, {"estado": "in_force", "rango": "ley"},
        {"anno": "2001"}, {"fecha_desde": "2001", "fecha_hasta": "2001"},
        {"fecha_hasta": "1990-06"}, {"derogada_desde": "2000"}, {"actualizada_desde": "2024"},
        {"departamento": "council"}, {"jurisdiccion": "es-an"},
        {"texto": "data", "estado": "in_force", "fecha_desde": "2015"},
    ]
    for pais in (*CORPUS, ""):
        for f in filtros:
            for limite, offset in ((20, 0), (100, 50)):
                yield "buscar_ley", {"pais": pais, "limite": limite, "offset": offset, **f}
            yield "contar_leyes", {"pais": pais, **f}
    yield "buscar_ley", {"pais": "zz"}
    yield "contar_leyes", {"pais": "zz"}

    azar = random.Random(20261018)
    for pais in CORPUS:
        ids = sorted(_todos_los_ids(m, pais))
        ficheros = {f.stem: f for f in (repos / f"legalize-{pais}").rglob("*.md") if ".git" not in f.parts}
        for id_ley in azar.sample(ids, min(20, len(ids))):
            yield "obtener_ley", {"id_ley": id_ley, "pais": pais, "solo_metadata": True}
            yield "obtener_ley", {"id_ley": id_ley.lower(), "pais": pais}
        pares = []
        for id_ley in azar.sample(ids, min(300, len(ids))):
            ruta = ficheros.get(id_ley)
            if not ruta or ruta.stat().st_size > 5_000_000:
                continue
            numeros = sorted({next(g for g in x.groups() if g) for x in ARTICULO.finditer(
                ruta.read_text(encoding="utf-8", errors="replace"))})
            if numeros:
                pares.append((id_ley, azar.choice(numeros)))
            if len(pares) >= 200:
                break
        for id_ley, numero in pares:
            yield "obtener_articulo", {"id_ley": id_ley, "articulo": numero, "pais": pais}
        for id_ley, numero in pares[:20]:
            yield "obtener_articulo", {"id_ley": id_ley, "articulo": "99999", "pais": pais}
            if "-" in numero:
                yield "obtener_articulo", {"id_ley": id_ley, "articulo": numero.rsplit("-", 1)[0], "pais": pais}
    yield "obtener_ley", {"id_ley": "NO-EXISTE-1"}
    yield "obtener_ley", {"id_ley": "BOE-A-2018"}


def _todos_los_ids(m, pais):
    total = m.contar_leyes.fn(pais=pais).total
    ids = []
    for offset in range(0, total, 100):
        ids += [r.id for r in m.buscar_ley.fn(pais=pais, limite=100, offset=offset)]
    return ids


def ejecutar(raiz: Path, salida: Path):
    sys.path.insert(0, str(raiz))
    import os
    import mcp_legalize as m
    repos = Path(os.environ.get("LEGALIZE_REPOS_DIR", raiz / "repos"))
    resultados = {}
    for herramienta, args in peticiones(m, repos):
        clave = f"{herramienta} {json.dumps(args, sort_keys=True, ensure_ascii=False)}"
        try:
            resultados[clave] = volcar(getattr(m, herramienta).fn(**args))
        except Exception as exc:  # una excepción también es una respuesta a comparar
            resultados[clave] = {"_excepcion": type(exc).__name__, "mensaje": str(exc)[:200]}
    salida.write_text(json.dumps(resultados, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    print(f"{len(resultados):,} peticiones -> {salida}")


def comparar(a: Path, b: Path):
    ra, rb = json.loads(a.read_text(encoding="utf-8")), json.loads(b.read_text(encoding="utf-8"))
    solo_a, solo_b = sorted(set(ra) - set(rb)), sorted(set(rb) - set(ra))
    distintas = [k for k in sorted(set(ra) & set(rb)) if ra[k] != rb[k]]
    print(f"peticiones: {len(ra):,} / {len(rb):,} | solo en la primera: {len(solo_a)} | "
          f"solo en la segunda: {len(solo_b)} | respuestas distintas: {len(distintas)}")
    for k in (solo_a + solo_b)[:5]:
        print("  sin pareja:", k[:160])
    for k in distintas[:15]:
        print("  distinta:", k[:160])
        print("     ref :", json.dumps(ra[k], ensure_ascii=False)[:300])
        print("     rama:", json.dumps(rb[k], ensure_ascii=False)[:300])
    return 1 if distintas or solo_a or solo_b else 0


if __name__ == "__main__":
    if sys.argv[1] == "--comparar":
        sys.exit(comparar(Path(sys.argv[2]), Path(sys.argv[3])))
    ejecutar(Path(sys.argv[1]).resolve(), Path(sys.argv[2]))
