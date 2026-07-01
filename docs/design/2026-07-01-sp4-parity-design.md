# SP4-③ `parity` module — design

**Status:** Accepted · **Target tag:** v0.8.0 · **Date:** 2026-07-01

## 1. Problem / motivation

Mandatory Rule 4 (parity): a living capability×surface matrix prevents silent
capability loss when a UI shell is rewritten (Kenni's inventory exists precisely
because features were silently dropped in a shell rewrite). Rule: no "complete"
without code proof; no "gap" for an existing view; every deliberate gap is linked
to a tracking issue.

## 2. What is mechanically enforceable (honest ceiling)

Kenni keeps parity as a hand-maintained markdown matrix; its only script-level
enforcement is the contract-coverage bridge (owned elsewhere) — the matrix
symbols themselves are review-enforced. A neutral, CI-failable core exists:

**HARD (CI exit 1):**
- valid JSON object; UTF-8/JSON/non-dict hardening arms (mirror the sibling gates).
- `capability` non-empty string == filename stem (uniqueness by construction).
- `surfaces` a non-empty object `{surface-name: status}`; every status ∈
  `{complete, view, code, gap, na}` (the neutral analog of Kenni's ✓/view/code/gap/–).
- every surface whose status is `gap` has a matching entry in `issues`
  (`{surface-name: issue-ref}`) whose value is a valid issue reference — one of
  `#N`, `owner/repo#N`, or a github issue URL. This mechanizes Rule 4's "every
  deliberate gap links to an issue". (Format only; the three regexes are
  duplicated ~3 lines from `github_issues` — modules must not import each other,
  Rule 5.)
- **surface coverage (only when the project declares its surfaces):** if the
  optional `parity_surfaces` answer is a non-empty list, every capability file's
  `surfaces` keys must cover *exactly* that set — a missing surface is a silent
  omission (the exact Rule-4 failure mode), an unknown surface is a typo. When
  `parity_surfaces` is empty (default), coverage is not enforced (surfaces are
  free-form) and only status/gap validity applies.

**BEST-EFFORT (note, exit 0 — never faked):**
- a `complete` status carries no machine-checkable code proof → advisory note
  ("Rule 4: 'complete' claimed; code proof is review-enforced, not machine-checked").
  We do NOT hard-fail this — verifying "implemented + visible + actions complete"
  across arbitrary codebases is not possible.
- issue *existence* for a gap ref is not checked (would need `gh`); format only.
- "no gap for an existing view" is not machine-checkable → out of scope.
- empty/absent registry → "no parity entries yet".

## 3. Artifact

One capability per file `docs/process/parity/<capability>.json`:

```json
{
  "capability": "chat",
  "surfaces": { "web": "complete", "mobile": "gap", "cli": "na" },
  "issues": { "mobile": "#42" },
  "notes": "optional"
}
```

`issues` is required only for surfaces with status `gap`; other entries are
ignored. Unknown top-level fields ignored (forward-compat). Inert `*.example.json`
seed under the conditional dir (learned from contract-first Finding D — seeds ship
ONLY when the module is on).

## 4. `parity_surfaces` copier question

Add a `parity_surfaces` question, `type: yaml`, `default: []`, `when:
"{{ modules.parity }}"` — the project's canonical surface list (e.g.
`[web, mobile, cli]`). The gate reads it from `.copier-answers.yml` at runtime
(same manifest-read pattern `check_issues.py` uses for `github_repo`; reading the
manifest is not a cross-module import). Empty default keeps the gate useful with
zero configuration.

## 5. Wiring (identical to prior slices)

- `copier.yml`: `modules.default += parity: false`; new `parity_surfaces` question.
- `gate_runner.py` GATES += `"parity": ("parity", [sys.executable, "scripts/process/check_parity.py", "."])`.
- `tests/conftest.py` modules dict += `"parity": False`.
- Gate `template/scripts/process/{% if modules.parity %}check_parity.py{% endif %}.jinja`.
- Seed `template/docs/process/{% if modules.parity %}parity{% endif %}/capability.example.json`.
- Module doc `template/docs/process/{% if modules.parity %}modules{% endif %}/parity.md`.
- README catalog + roadmap + status/tag → v0.8.0.

## 6. Distinctness (Rule 5)

Distinct from `feature_registry` (story→acceptance→tests — behavior traceability)
and `contract_first` (capability→interface symbols in spec). `parity` = which
surface can do what, and every deliberate gap is issue-linked. No module reads
another's artifacts; the issue-ref regexes are a deliberate small duplication.

## 7. Neutrality & verification

No Kenni terms in shipped files. Real `vcs_ref=HEAD` render on/off (module off
ships nothing incl. no seed dir — the Finding-D discipline). doc-drift green.
