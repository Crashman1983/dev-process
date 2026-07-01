# Module: security-floor

Opt-in. Enforces a **mechanical security floor**: the grep-able subset of a
project's security invariants, declared as forbidden regex patterns and enforced
as a blocking gate. It catches the careless regression — a `shell`-injection sink
or a committed private key — even on a review-less path, because the gate runs
through the manifest-aware gate runner at push/CI time.

## When required

Enable when the project has security invariants that are expressible as "this
pattern must not appear in the tree" — a forbidden call, a hard-coded secret
shape, a banned sink. The gate ships with **no rules**, so it is a no-op until you
declare your own: copy the seed `docs/process/security-floor.example.json`, drop
the `.example`, and edit the resulting `security-floor.json`.

## The policy file

One policy file at `security-floor.json` (a single coherent rule set, not a
one-per-file registry). Absent by default; the gate is a no-op until it exists.

```json
{
  "rules": [
    { "id": "no-shell-true", "pattern": "shell\\s*=\\s*True",
      "applies_to": ["*.py"], "message": "use a subprocess argv list, not shell=True" },
    { "id": "no-committed-private-key", "pattern": "-----BEGIN [A-Z ]*PRIVATE KEY-----",
      "message": "private key material must not be committed" }
  ],
  "exclude": ["*test_*", "tests/*"]
}
```

| field | required | meaning |
|---|---|---|
| `rules` | yes | list of rules; each is scanned line-by-line against in-scope files |
| `rules[].id` | yes | short stable identifier, printed with every finding |
| `rules[].pattern` | yes | a Python regex; must compile |
| `rules[].message` | yes | the remediation shown on a match |
| `rules[].applies_to` | no | list of globs; the rule scans only matching files (default: all) |
| `exclude` | no | list of globs; matching files are never scanned by any rule |

### Glob semantics

`applies_to` and `exclude` are `fnmatch` globs matched against the repo-relative
POSIX path **or** the basename — so `*.py` scans every Python file, `*test_*`
matches a test file at any depth, and a path fragment like `src/*` targets a
subtree. Unlike shell globbing, `*` crosses `/`. The policy file itself and the
gate script are always excluded, so a rule never flags its own pattern text.

## Scan scope — whole tree, not added-only

The gate scans **git-tracked files** (the whole tree), enumerated via
`git ls-files`. This is a deliberate choice: the gate runs at push/CI time where
there is no staging area, so "added lines only" is not available. The consequences
are all mitigated:

- The default ruleset is empty, so the gate is a no-op until the project opts in.
- A rule then means "this pattern must not exist anywhere in the tree" — a
  stronger floor than added-only, since it also catches pre-existing violations.
- `exclude` globs carve out known-debt or legitimate-mention paths; the whole gate
  is bypassable with `SKIP_SECURITY_FLOOR=1`.

## Hard vs. best-effort (no false-green)

**Hard (CI fails):** a **broken policy** — the file is not JSON, not a UTF-8 file,
not a JSON object, `rules` is not a list, or a rule is missing / mis-typing its
`id`, `pattern` or `message`, or carries a `pattern` that is not a compilable
regex. A broken policy fails loudly rather than silently degrading to a pass. And
any rule pattern that matches a line in an in-scope, non-excluded tracked file
yields a hard finding `path:line: message [id]` plus a fix-or-bypass hint.

**Best-effort (advisory note, exit 0 — never faked):**

- no policy file yet → "no security-floor config yet".
- `git ls-files` unavailable (not a git repo, or git absent) → "could not list
  tracked files; scan skipped" — enumeration is impossible, so a pass is not faked.
- a tracked file that is not valid UTF-8 (binary) is skipped for scanning.
- `SKIP_SECURITY_FLOOR=1` in the environment → "skipped", exit 0.

## Heuristic caveat

A line regex cannot tell real code from the same text in a comment, a string, or a
fixture. That is exactly why `exclude` and the `SKIP_SECURITY_FLOOR=1` bypass
exist. The value is catching the careless real case, not purity — treat a finding
as a prompt to look, not an infallible verdict.

## One owner per behavior (Rule 4)

This module owns only the pattern floor. It reads no other module's artifacts; it
is the only module that queries `git ls-files`, which is a repo enumeration, not a
cross-module import. Byte-level artifact drift is the `contracts-drift` module's
job, capability×surface coverage is `parity`'s — security-floor composes with them
without coupling. The gate itself is `scripts/process/check_security_floor.py`.
