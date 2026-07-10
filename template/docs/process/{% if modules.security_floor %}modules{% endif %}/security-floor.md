# Module: security-floor

Opt-in. Enforces a **mechanical security floor**: the grep-able subset of a
project's security invariants, declared as forbidden regex patterns and enforced
as a blocking gate. It catches the careless regression — a `shell`-injection sink
or a committed private key — even on a review-less path, because the gate runs
through the manifest-aware gate runner at push/CI time.

**This is a pattern floor, not your security review.** A green floor means the
banned patterns are absent — it does **not** mean the change is secure. Runtime
vulnerabilities (open redirect, injection, broken authorization) are not
grep-able and are the review gate's job (`review-checklist.md`, security
questions), never this gate's. Do not read a passing floor as "security
checked".

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
subtree. Unlike shell globbing, `*` crosses `/`. The policy file itself, the
shipped example seed and the gate script are always excluded, so a rule never
flags its own pattern text.

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
- a policy whose `rules` list is empty → "config has no rules".
- `git ls-files` unavailable (not a git repo, or git absent) → "could not list
  tracked files; scan skipped" — enumeration is impossible, so a pass is not faked.
- `git ls-files` returns nothing (nothing committed yet) → "0 tracked files
  scanned — floor not exercised".
- a tracked file that is not valid UTF-8 (binary) is skipped for scanning.
- `SKIP_SECURITY_FLOOR=1` in the environment → "skipped", exit 0.

## Architecture boundaries as floor rules

The pattern floor is concern-agnostic: a scoped rule turns an **architecture
boundary** into a blocking gate with the same mechanism. Declare the forbidden
dependency as a rule whose `applies_to` scopes it to the source side of the
boundary:

    { "id": "arch-ui-no-direct-db",
      "pattern": "from\\s+app\\.db\\b|import\\s+app\\.db\\b",
      "applies_to": ["src/ui/*", "src/ui/**"],
      "message": "architecture floor: the UI reaches the db only through the service layer",
      "adr": "ADR-0002" }

The optional **`adr`** field links the rule to the decision record it enforces
(ADR-0002 above is illustrative — point it at one of *your* records, or omit
it) — the gate hard-fails when the link does not resolve, so a boundary rule
cannot outlive or misquote its decision. Honest ceiling: this is a **regex floor, not
an architecture review** — it catches the literal import the rule names, not a
clever indirection. For semantic layering conformance use a real arch-linter
(the `arch-onboarding` module runs one best-effort when present); the floor is
the portable, always-on backstop for the few boundaries worth defending
unconditionally. Deliberately *not* a separate module: the mechanism has one
owner here (Rule 4), only the rule's concern differs.

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
