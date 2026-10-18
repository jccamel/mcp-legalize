# Decisiones de arquitectura (ADR)

Registro de las decisiones que condicionan el proyecto. Cada decisión vive en su propio fichero, numerado y en markdown, versionado con el código.

**Cuándo escribir un ADR:** al elegir o cambiar una dependencia importante, un patrón de arquitectura, un formato de datos, una convención que afecte a varios ficheros o cualquier decisión que alguien (o Claude) podría deshacer sin saber por qué se tomó.

**Cómo:** copia `0000-plantilla.md` como `NNNN-titulo-corto.md` con el siguiente número libre, rellénalo y añade una línea a la tabla.

**Estados:** Propuesta · Aceptada · Sustituida por NNNN · Descartada

| Nº | Título | Estado | Fecha |
| --- | --- | --- | --- |
| 0001 | [Las claves son del servidor; los valores, de la ley](0001-claves-del-servidor-valores-de-la-ley.md) | Aceptada | 2026-08-20 |
| 0002 | [El índice se carga como dicts crudos, sin validarlo con Pydantic](0002-indice-sin-validacion-pydantic.md) | Aceptada | 2026-08-24 |
| 0003 | [Índice invertido en un fichero aparte y cargado bajo demanda](0003-indice-invertido-en-fichero-aparte.md) | Sustituida por 0007 | 2026-08-24 |
| 0004 | [Se acepta plegar å, ä y ö también en sueco](0004-plegado-de-vocales-suecas.md) | Aceptada | 2026-08-25 |
| 0005 | [Búsqueda por presencia e intersección, sin ranking](0005-busqueda-por-presencia-sin-ranking.md) | Aceptada | 2026-08-24 |
| 0006 | [Cuarentena por fichero; los metadatos se registran pero no bloquean](0006-cuarentena-por-fichero.md) | Aceptada | 2026-08-21 |
| 0007 | [Postings en un formato de texto propio, atados a su índice JSON](0007-postings-en-formato-de-texto-propio.md) | Sustituida por 0009 | 2026-10-16 |
| 0008 | [Plegado genérico de diacríticos, conservando la ñ](0008-plegado-generico-con-enye.md) | Aceptada | 2026-10-18 |
| 0009 | [El índice de cada corpus es una base de datos SQLite, abierta como entrada no confiable](0009-indice-en-base-de-datos.md) | Aceptada | 2026-10-18 |
