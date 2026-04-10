# Legalize Format Spec v0.1

Minimal contract for all country repos. Each country's legal system is different — this spec defines what MUST be consistent, and what each country decides for itself.

## Mandatory (all countries)

### YAML frontmatter

Every law file must have these 8 fields:

```yaml
---
titulo: "Full official title of the law"
identificador: "OFFICIAL-ID-123"
pais: "xx"
rango: "law_type"
fecha_publicacion: "YYYY-MM-DD"
ultima_actualizacion: "YYYY-MM-DD"
estado: "in_force"
fuente: "https://official-source-url"
---
```

| Field | Description | Format |
|-------|-------------|--------|
| `titulo` | Full official title | String |
| `identificador` | Official ID from the source | String (unique per country) |
| `pais` | ISO 3166-1 alpha-2 country code | `es`, `fr`, `se`, `kr`, `de`, ... |
| `rango` | Type of legal text | Free-form string, country-specific |
| `fecha_publicacion` | Original publication date | ISO 8601 date |
| `ultima_actualizacion` | Date of the latest reform included | ISO 8601 date |
| `estado` | Legal status | `in_force`, `repealed`, `partially_repealed`, `annulled`, or `expired` |
| `fuente` | URL to the official source | Valid URL |

Additional fields are welcome. Korea adds law sub-types, Spain adds `jurisdiccion` for autonomous communities, France may add code structure metadata. These are country-specific extensions.

### Commit format

```
[type] Title — articles affected

Source-Id: REFORM-ID
Source-Date: YYYY-MM-DD
Norm-Id: LAW-ID
```

Types: `[bootstrap]`, `[reforma]`, `[nueva]`, `[derogacion]`, `[correccion]`

The commit's author date must be the real publication date of the reform, not the date the commit was created.

### Git identity

- **Author:** whoever runs the pipeline (from `git config user.name` / `user.email`)
- **Committer:** `Legalize <legalize@legalize.dev>` (or the pipeline's configured identity)

### Repository

One repo per country: `legalize-{code}` (e.g., `legalize-es`, `legalize-kr`, `legalize-de`).

Community contributions may live under the contributor's GitHub account (e.g., `9bow/legalize-kr`) and be listed in the hub.

## Flexible (per country)

Each country decides and documents in its own README:

- **Directory structure.** Spain uses flat `es/{id}.md`. Korea groups related laws `kr/{name}/`. France has one file per code `fr/{id}.md`. All valid.
- **What is a "law"?** Each legal system defines its own unit. Spain: individual law (BOE ID). France: consolidated code. Korea: act + decree + ordinance grouped. Sweden: individual statute (SFS number).
- **Rango values.** Free-form string. Spain: `ley`, `constitucion`, `real_decreto`. France: `code`, `loi`, `ordonnance`. Sweden: `lag`, `balk`, `forordning`. Korea: `법률`, `대통령령`, `부령`.
- **Additional frontmatter fields.** Add whatever is useful for your legal system.
- **Language.** Each country's content is in its original language. Code, commit types, and trailer keys are in English/Spanish (as established).

## Versioning

This spec is v0.1. It will evolve as more countries join. Breaking changes will be announced in the hub repo. The `early-stage` notice in each country repo reflects this.
