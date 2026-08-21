# Contributing

This file records how the project has actually been built, not aspirations. Every
convention below is visible in the commit history and most are enforced by tests
or CI.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt   # ranges
# or, for the exact set the suite is known to pass with:
pip install -r requirements.lock
```

Python 3.10 or later; the floor and its reasoning are in the README.

```bash
python -m pytest                             # 318 tests
python scripts/update_index.py --self-test   # the 24 injection patterns
```

Both run in CI across 3.10–3.13 and must be green before a merge.

## The rule that matters most

**Watch the test fail first.**

Every fix in this repository was written that way, and the pull requests say
which lines failed and why. It is not ceremony. Twice this year a test written
after the fact would have passed for the wrong reason:

- In #14 a malformed `_bytes` was expected to crash. `True` and `3.7` never did —
  Python coerces them in a sum, so the real bug there was a *wrong number*, not
  an exception. A fix that only stopped crashes would have shipped with both
  values silently miscounted.
- In #22 the metadata scan looked safe when probed as the only index in a
  directory, where "all tools still work" actually meant "there is no data to
  serve". The neighbour case is what revealed the cost.

Seeing the failure is what tells you the test tests the right thing.

## Tests

- Assert at the **call site**, not against the helper. If a helper returning the
  right value proves nothing about the defect, the test belongs one level up.
  `tests/test_bytes_degradation.py` asserts through the MCP tools; `test_frontmatter.py`
  asserts at the two delegating call sites so re-adding a private implementation
  to either side fails.
- **Do not assert on elapsed time.** `tests/test_search_normalization_cache.py`
  counts normalization calls instead. The complaint was never "this is slow", it
  was "this work is repeated" — a cache that stops the repetition satisfies the
  count; one that merely got faster would not.
- **Do not over-specify.** Several metadata patterns overlap deliberately, so
  pinning an exact pattern list breaks a test that is not about the vocabulary.
- A test's docstring explains **why it exists** — usually the defect it came
  from. That is why the docstrings are long.

### Tests that check the documentation

These will fail if you change prose without changing code, or the reverse:

| File | Enforces |
|---|---|
| `test_readme_claims.py` | Every tool and every `_meta.seguridad` field is documented; the language count matches the scanner |
| `test_config_docs.py` | The docstring, the README and the code agree on all four environment variables and their defaults |
| `test_prose_style.py` | Spanish comments keep their diacritics; code inside prose is left alone |

Prose that nothing checks drifts. That is the point.

### One test to leave alone

`test_the_timestamp_still_moves_with_the_stamp` pins the **exact** key set of
`_meta.seguridad`. Adding a field fails it on purpose. It has fired three times
(#20, #21, #22) and the right response every time was to update the assertion
with a comment explaining the new field — never to relax it to a subset check.
If you find it in your way, that is it working.

## Commits

Conventional commits: `type: description`, or `type(scope): description`. Types
in use: `fix`, `docs`, `feat`, `chore`, `test`, `perf`, `style`, `refactor`,
`ci`, `build`.

**No `Co-Authored-By` trailers and no AI attribution.**

Write a body, and make it explain **why**. Commits here run 30 to 80 lines
because the diff already shows what changed; what a reader six months from now
needs is the reasoning, the option that was rejected, and what was measured.

Commit by work unit: one deliverable behaviour per commit, with its tests. Not
"add models", then "add services", then "add tests" — none of those works alone.

## Branches and pull requests

`type/description`, matching the commit types: `fix/`, `docs/`, `perf/`,
`test/`, `style/`, `ci/`, `build/`.

Pull request bodies follow a shape:

1. **What was wrong** — with the reproduction, and line numbers
2. **The fix** — including options considered and why this one
3. **Changes** — a file/change table
4. **Test plan** — checked boxes, with the failure you watched first

Link the issue with `Closes #N`. Use `Refs #N — closes item X` when the issue has
several open items, so it does not close prematurely.

## Measure before you propose a number

Any constant that a corpus could exceed must be measured against the corpus
first. This is not hypothetical: the cap in #21 was drafted at 1,000 characters,
and the Spanish corpus has a legitimate title of 1,658 (`BOE-A-2021-20004`). That
limit would have truncated a real consolidated law.

The same applies to a pattern's severity. Blocking on `meta.html_tag` would
delete genuine laws, because real titles carry angle brackets — which is why
metadata findings are recorded rather than quarantined.

## Verify before you claim

CI passing is not the same as your test having run. Before saying something is
fixed, read the actual output: `pytest -rs` shows skip reasons, and the CI log
shows which branch of a conditional executed. A silently skipped test reads as
coverage while providing none — that is how the symlink-escape defense went
unverified for the whole life of the project despite a green suite.

For changes to the indexer or the loader, run a full reindex against a real
corpus and diff the result. Reordering search filters can change which documents
match without breaking anything visibly.

## Security

Do not open a public issue for a vulnerability. See
[SECURITY.md](SECURITY.md).

New injection patterns need a sample, and `--self-test` must pass — it asserts
every pattern still matches its own sample through the path its surface really
uses. A `block` pattern that keeps matching legitimate legal text is a bug in
the pattern, not a reason to force the file.
