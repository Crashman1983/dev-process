# SP4-④ `security_floor` module — design

**Status:** Accepted · **Target tag:** v0.9.0 · **Date:** 2026-07-01

## 1. Problem / motivation

A mechanical security floor: the grep-able subset of a project's security
invariants, enforced as a blocking gate so a careless regression is caught even
on a review-less path. Kenni's `check_security_floor.py` greps *staged added
lines* for a fixed pair of invariants (`shell=True` in Python; `{@html}` without
a sanitizer in Svelte), excludes tests/self, blocks (exit 1), and is bypassable
with `SKIP_SECURITY_FLOOR=1`.

## 2. Neutralization (what changes for a portable template)

Kenni's patterns are stack-specific. The neutral module ships the **framework**,
not the patterns: a project declares its own forbidden patterns.

**Scan scope — the one deliberate divergence from Kenni.** Kenni scans *staged
added lines* (via `git diff --cached`) so pre-existing debt never blocks a
commit. This module runs through the manifest-aware `gate_runner` at push/CI
time, where there is no staging area. It therefore scans **git-tracked files**
(whole tree). Consequences, all mitigated:
- The default ruleset is **empty → the gate is a no-op** until the project adds a
  rule (mirrors every other module's "empty registry = nothing to check").
- A rule the project adds means "this pattern must not exist anywhere in the
  tree" — whole-tree is the correct semantics for that intent, and a stronger
  floor than added-only (it also catches existing violations).
- `exclude` globs carve out known-debt or legitimate-mention paths; the whole
  gate is bypassable with `SKIP_SECURITY_FLOOR=1`.
This divergence is documented in the module doc.

## 3. Artifact

A single policy file `docs/process/security-floor.json` (a coherent rule set, not
independent entities — so NOT a one-per-file registry). Absent by default. An
inert `security-floor.example.json` seed ships (module-on only) as the template.

```json
{
  "rules": [
    { "id": "no-shell-true", "pattern": "shell\\s*=\\s*True",
      "applies_to": ["*.py"], "message": "use a subprocess argv list, not shell=True" },
    { "id": "no-private-key", "pattern": "-----BEGIN [A-Z ]*PRIVATE KEY-----",
      "message": "committed private key material" }
  ],
  "exclude": ["*test_*", "tests/*"]
}
```

- `rules` (list; each: `id` str, `pattern` str = a Python regex, `applies_to`
  optional list of globs = which files it scans (default: all), `message` str).
- `exclude` (optional list of globs = files never scanned).

**Globs** are `fnmatch` patterns matched against the repo-relative POSIX path OR
the basename (so `*.py` = all Python files, `*test_*` = any test file at any
depth, `src/*` = a path fragment). `*` matches across `/`. Documented in the doc.

## 4. Honest ceiling

**HARD (CI exit 1):**
- the config file exists but is invalid — not JSON / not an object / `rules` not a
  list / a rule missing `id`/`pattern`/`message` or of the wrong type / a
  `pattern` that is not a compilable regex. A broken *policy* must fail loudly,
  not silently no-op (this is the distinguishing HARD case — other modules treat
  malformed *entries* per-entry, but here the whole config is the policy).
- any rule pattern matches a line in an in-scope, non-excluded tracked file →
  hard finding `path:line: message` + a "fix or SKIP_SECURITY_FLOOR=1" hint.

**BEST-EFFORT / no-op (note, exit 0 — never faked):**
- config absent → "no security-floor config yet".
- `git ls-files` unavailable (not a git repo / git absent) → "could not list
  tracked files; scan skipped" — we cannot enumerate, so we do not fake a pass.
- a tracked file that is not valid UTF-8 (binary) → skipped for scanning.
- `SKIP_SECURITY_FLOOR=1` → "skipped" note, exit 0.

**Heuristic caveat (documented):** a line-regex cannot tell real code from the
same text in a comment, string, or fixture. That is why `exclude` and the env
bypass exist; the value is catching the careless real case, not purity.

## 5. Wiring (identical to prior slices)

- `copier.yml`: `modules.default += security_floor: false`.
- `gate_runner.py` GATES += `"security-floor": ("security_floor", [sys.executable, "scripts/process/check_security_floor.py", "."])`.
- `tests/conftest.py` modules dict += `"security_floor": False`.
- Gate `template/scripts/process/{% if modules.security_floor %}check_security_floor.py{% endif %}.jinja`.
- Seed `template/docs/process/{% if modules.security_floor %}security-floor.example.json{% endif %}` (module-off ships nothing — the Finding-D discipline; here the conditional is on the single filename, no dir).
- Module doc `template/docs/process/{% if modules.security_floor %}modules{% endif %}/security-floor.md`.
- README catalog + roadmap + status/tag → v0.9.0.

## 6. Distinctness / Rule 5 / neutrality

No mandatory-rule number is cited (the neutral rule set has no security rule;
security-floor is an optional discipline — lesson from the parity review). It
reads no other module's artifacts; it is the only module that shells out to
`git ls-files` (a repo query, not a cross-module import). No Kenni terms in
shipped files. Real `vcs_ref=HEAD` render on/off; module-off ships nothing.
