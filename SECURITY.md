# Security policy

## Reporting a vulnerability

Report privately through GitHub, not in a public issue:

**[Open a draft security advisory](https://github.com/jccamel/mcp-legalize/security/advisories/new)** — or use the *Security* tab, then *Report a vulnerability*.

Public issues are the wrong place for a security report: the disclosure would be
complete before any fix exists. Ordinary bugs belong there; this does not.

Useful things to include, to whatever extent you have them:

- what an attacker gains, not only what misbehaves;
- a reproduction — a crafted `.md` file, an index fragment, or a tool call;
- which surface it enters through (see the scope table below);
- the commit you tested against, since this project has no releases yet.

**Response.** An acknowledgement within seven days, and an assessment within
thirty. This is a small project with no on-call rotation, so those are honest
figures rather than guarantees. If you have had no reply in seven days, assume
the notification was missed and say so in a new advisory or a public issue that
says only that a private report is waiting — no details.

**Disclosure.** Report privately, then coordinate. There is no bounty. Credit in
the advisory unless you prefer otherwise.

## Scope

The threat model this project defends is stated in the README:

> the threat model is a compromised corpus, not a compromised client

That distinction decides what is a vulnerability here.

| In scope | |
|---|---|
| Prompt injection surviving into a tool response | Body or metadata, any language |
| Reading a file outside the corpus | Path traversal, symlinks, absolute paths, crafted `_ruta` |
| A crafted index breaking a tool or stopping the server | The index is untrusted input |
| Escaping the `<untrusted_content>` wrapper | Closing the tag, attribute injection |
| A quarantine or scan bypass that reaches the model | The scanner is a canary; slipping past it silently still matters |
| Dependency or supply-chain issues affecting the pinned set | See `requirements.lock` |

| Out of scope | Why |
|---|---|
| A jailbreak that works on wrapped, filtered content | The client's robustness, not the server's. Documented as remaining risk. |
| Content of the upstream `legalize-*` corpora | Report those to their maintainers; this server indexes what it is given. |
| A compromised MCP client, or the machine running the server | The threat model assumes both are trusted. |
| Confusable Unicode homoglyphs | A general text-processing problem, documented as not covered. |
| A stale index serving old content | Documented behaviour with a documented mitigation: re-index. |
| False positives in the injection patterns | A bug worth an ordinary issue, not a vulnerability. Include a sample. |

Something already listed under **Limitations and remaining risk** in the README
is documented, not unknown — but if you can show it is materially worse than the
description says, that is worth reporting.

## What is already defended

Read the README's [Security architecture](README.md#security-architecture)
section before reporting. It lists the mitigations, what is covered, and what is
explicitly not, so you can tell a genuine gap from a documented limit.

Two things are verifiable without a corpus:

```bash
python scripts/update_index.py --self-test   # every injection pattern matches its sample
python -m pytest                             # the full suite, security boundaries included
```

## Supported versions

There are no releases. `main` is the only supported version, and a fix lands
there. If you run a pinned commit, say which one in your report.

## Operating this safely

The README's *Operational recommendations* cover the deployment side: auditing
repository sources before cloning, watching `[CUARENTENA]` alerts, using
`--fail-on-quarantine` in CI, and re-indexing on a schedule. A misconfigured
deployment is not a vulnerability in this code, but the recommendations exist
because the code cannot enforce them from the inside.
