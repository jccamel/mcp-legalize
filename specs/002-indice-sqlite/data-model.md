# Data Model: Índice en una base de datos por corpus

Un fichero por corpus: `indices/index_<repo>.db`. Lo escribe y lo lee solo
`legalize_indice.py` (principio III). Su SQL canónico es la lista blanca que comprueba
`abrir` (research R2).

## Tablas

```sql
CREATE TABLE meta(
    clave TEXT PRIMARY KEY,
    valor TEXT NOT NULL
);
-- claves: formato, patrones, tokenizador, directorio_base, pais, git_commit,
--         generado_en, seguridad (JSON con las claves de hoy en _meta.seguridad)

CREATE TABLE leyes(
    n INTEGER PRIMARY KEY,               -- orden del corpus: el de inserción del indexador
    id TEXT NOT NULL UNIQUE,             -- distingue mayúsculas; la búsqueda sin ellas va por id_casefold
    titulo TEXT NOT NULL,
    rango TEXT NOT NULL,
    estado TEXT NOT NULL,
    fecha_publicacion TEXT NOT NULL,     -- '' si la fuente no la da
    ultima_actualizacion TEXT NOT NULL,
    fecha_derogacion TEXT NOT NULL,
    fuente TEXT NOT NULL,
    jurisdiccion TEXT NOT NULL,
    departamento TEXT NOT NULL,
    estado_texto TEXT NOT NULL,          -- point_in_time | current | as_enacted (literal)
    ultima_modificacion TEXT NOT NULL,
    derogado_por TEXT NOT NULL,
    ruta TEXT NOT NULL,                  -- _ruta relativa a la raíz del corpus
    bytes INTEGER NOT NULL,
    mtime REAL NOT NULL,
    -- formas plegadas para filtrar, calculadas al indexar con legalize_normalizacion
    titulo_norm TEXT NOT NULL,
    rango_norm TEXT NOT NULL,
    estado_norm TEXT NOT NULL,
    jurisdiccion_norm TEXT NOT NULL,
    departamento_norm TEXT NOT NULL
);
CREATE INDEX leyes_fecha_publicacion ON leyes(fecha_publicacion);
CREATE INDEX leyes_ruta ON leyes(ruta);

CREATE TABLE articulos(
    ley INTEGER NOT NULL REFERENCES leyes(n),
    orden INTEGER NOT NULL,              -- orden de aparición dentro de la ley
    numero TEXT NOT NULL COLLATE NOCASE, -- tal como aparece en el encabezado
    ubicacion TEXT NOT NULL,             -- encabezados superiores unidos con ' › '; '' si no hay
    inicio INTEGER NOT NULL,             -- posiciones en el cuerpo sin frontmatter
    fin INTEGER NOT NULL,                -- donde lo acaba la estructura del documento
    PRIMARY KEY (ley, orden)
) WITHOUT ROWID;
CREATE INDEX articulos_numero ON articulos(ley, numero);

CREATE VIRTUAL TABLE cuerpo USING fts5(
    texto, content='', tokenize='unicode61 remove_diacritics 0'
);
-- rowid = leyes.n; texto = legalize_normalizacion.normalizar(cuerpo sin frontmatter)
```

- **Todas las columnas de texto son `NOT NULL`, con `''` como valor ausente**, para que la
  semántica de "campo vacío" sea la de hoy. `estado_texto` se guarda ya resuelto, con
  `point_in_time` si falta en el frontmatter. Una ley sin él en la base de datos no existe:
  el formato lo exige.
- **Valores inválidos**: un tipo inesperado en el frontmatter (por ejemplo, `_bytes` que no
  es entero) se normaliza al escribir, con las reglas de degradación de hoy (`_bytes_de`,
  `_truncar_metadatos`). El lector valida tipos al leer cada fila y degrada el campo, nunca
  la herramienta (ADR 0002).

## Reglas de validación al abrir (R2)

| Comprobación | Si falla |
|---|---|
| Abre en solo lectura con modo defensivo | `ilegible` |
| `sqlite_master` es exactamente el esquema canónico | `esquema_inesperado` |
| `meta.formato` es el vigente | `formato_distinto` |
| `meta.tokenizador` es el del código | `tokenizador_distinto` (el servidor no busca por texto; el resto funciona) |
| `meta.directorio_base` queda dentro de `LEGALIZE_REPOS_DIR` | el corpus no se sirve (`[SEGURIDAD]`, como hoy) |

Los motivos de `sin_consultar` se reducen a `sin_postings` (no hay base de datos),
`ilegibles`, `tokenizador_distinto` y `consulta_sin_terminos`. `formato_anterior` y
`generacion_distinta` desaparecen: la generación ya no existe, y el formato anterior hace que
el corpus entero no se sirva.

## Transiciones del índice

```text
 indexador ──► ¿existe index_<repo>.db utilizable con las huellas vigentes?
                 │ sí: copia a temporal → pasada INCREMENTAL en una transacción
                 │ no: temporal vacío   → pasada COMPLETA   en una transacción
                 ▼
          VACUUM/optimize → os.replace(temporal, index_<repo>.db)
                 │ éxito: borra index_<repo>.json e inverted_<repo>.* del formato anterior
                 │ fallo: el temporal se borra; la base de datos vigente sigue intacta
```

## Respuesta de `obtener_articulo` (cambios)

Ver [contracts/herramientas-mcp.md](contracts/herramientas-mcp.md).
