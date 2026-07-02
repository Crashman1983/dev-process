# SP3 Slice 2 — GitHub-Issues module (design)

Status: proposed · Date: 2026-07-01 · Supersedes: — · Depends on: SP3 Slice 1 (feature-registry, v0.3.0)

## 1. Purpose

Give an adopter an opt-in, portable way to run the proven Kenni issue-backlog
discipline on GitHub: EARS-framed issue templates, a seed helper, a documented
claim/heartbeat workflow, and a gate that makes the *link* between a
feature-registry story and its tracking issue trustworthy — the story's `issue`
field is well-formed, and (best-effort) the referenced issue actually exists.

This is the concrete-by-example slice: GitHub is one backend. The module ships
GitHub artifacts an adopter adapts in their own copier copy; the *neutral*
concepts (issue tracking, EARS, claim discipline) stay in `docs/process/`.

## 2. Scope + honest ceiling

Same philosophy as Slice 1: **existence/location/structure is hard (CI exit 1);
conformance/semantic checks are best-effort (present tool → check; absent →
note, exit 0; never fake-verified).**

| Concern | Ceiling | Mechanism |
|---|---|---|
| Issue-ref **format** in a story's `issue` field | **hard** (exit 1) | regex over three accepted forms |
| Issue templates + seed helper **exist** when module on | **hard** | copier path-conditionals + a render test |
| Issue **existence** on GitHub | **best-effort** (never exit 1) | `gh` if present + repo configured → check; else note |
| Backlog **workflow**, labels, claim/heartbeat, EARS wording | **doc-only** | `github-issues.md`, judged at the review gate |

The existence check is **entirely advisory** — it never returns exit 1. A
definitive 404 stays a note, because the gate cannot distinguish "issue deleted"
from "this token cannot see a private / cross-repo issue," and the accepted
format explicitly allows cross-repo refs. Format is the only hard part of
issue-checking.

Non-goals (scope discipline): no `gh label` sync, no issue creation from the
gate, no PR automation, no requiring every story to carry an issue.

## 3. GitHub configuration at setup (copier interview)

Per the setup requirement: the GitHub configuration is asked **at Ersteinrichtung,
but optional.**

Two levels of optionality:

1. **The module itself is opt-in.** `modules.github_issues` defaults `false`
   (sibling of `doc_drift_gate`, `arch_onboarding`, `feature_registry`). Not
   enabling it means none of these artifacts render — the whole GitHub concern
   is absent.
2. **The repo is optional even when the module is on.** A new copier question:

   ```yaml
   github_repo:
     type: str
     help: >-
       GitHub repo as OWNER/REPO for issue tracking (optional — leave blank to
       skip the best-effort issue-existence check; issue-ref format is still enforced).
     default: ""
     when: "{{ modules.github_issues }}"
   ```

   Asked only when the module is on (`when:`), and blank is a first-class answer.
   The value is persisted in `.copier-answers.yml` and read at runtime by the
   gate (same pattern as `gate_runner.py` reading the module manifest). It is the
   default repo for **bare `#NNN`** refs and the target of the existence check.
   Blank → the gate skips existence with a note; format still runs.

No GitHub-specific content leaks into shared/core docs or a shared README: the
prerequisites (a GitHub repo + the `gh` CLI + `gh auth login`) are documented in
the module doc `github-issues.md`, which only renders when the module is on. The
`github_repo` help text carries the optionality at the point of asking.

## 4. The `issue` field — format is hard, and its one owner

The `issue` field lives on a feature-registry story (Slice 1 seeded it as
"stored, not yet enforced"). Slice 2 is where it gains meaning, so Slice 2 owns
its validation.

**Ownership decision (deliberate, not Rule-4 reflex).** Format validation lives
in `check_issues.py` (the `github_issues` module), **not** in the already-shipped
`check_feature_registry.py`. Rationale:

- The `issue` field only *means* anything when you are tracking issues. Enforcing
  its format under `feature_registry`-on / `github_issues`-off would demand a
  field that has no backend.
- The v0.3.0 feature-registry gate stays **frozen** — no re-patch, no re-tag of
  shipped behavior to enforce a field its own seed documents as not-yet-enforced.
- Rule 4 (one owner per behavior) is *satisfied*, not bent: the behavior "story
  structure is well-formed" is owned solely by `check_feature_registry.py`; the
  behavior "issue references are well-formed and exist" is owned solely by
  `check_issues.py`. They share only a directory glob (data access, not
  behavior).

**Cost:** `check_issues.py` re-globs `docs/process/feature-registry/*.json`
itself (≈5 lines duplicated from the registry gate). This is deliberate: the two
modules are independently installable and must not import each other
(`github_issues` may be installed without `feature_registry`, in which case there
are simply no stories to check). A shared library would couple them; a trivial
glob is the right seam to duplicate.

**Accepted `issue` forms** (validated only when the field is present and
non-empty; absent/empty is allowed):

| Form | Example | Repo resolved from |
|---|---|---|
| bare number | `#412` | configured `github_repo` |
| cross-repo | `octo/billing#77` | the ref itself |
| full URL | `https://github.com/octo/api/issues/412` | the ref itself |

Malformed (`412`, `#`, `octo/billing#`, a non-github URL, a non-string) → **hard
fail (exit 1)**.

Soft (never exit 1): a story with `status` `in-progress` or `done` and **no**
`issue` → a note ("tracked work without an issue link — unverified"), mirroring
the Slice 1 acceptance-coverage note.

## 5. Existence check — best-effort `gh` contract

For each well-formed ref, resolve `(repo, number)` and, best-effort, confirm it
exists. Degradation matrix (the honest-ceiling contract — every row is a note,
none is exit 1):

| Situation | Outcome |
|---|---|
| `gh` not on `PATH` (`shutil.which("gh")` is None) | one note, skip all existence |
| bare `#NNN` but `github_repo` blank/absent | note, skip that ref's existence |
| `gh` present, `gh issue view <n> --repo <o/r> --json number` exits 0 | exists, no note |
| exits non-zero / "not found" / 404 | note "could not confirm issue exists" |
| auth error / network down / **timeout** | note "could not reach GitHub" |

The subprocess call carries an explicit `timeout=` so a hung `gh` in CI cannot
wedge the job; a timeout is caught and downgraded to a note.

The existence check is wired into the gate (`github-issues` in the manifest), so
it runs on every CI push. Because it is notes-only it can never fail a build;
recurring cross-repo 404 notes are acceptable noise for a first cut. If they
become a problem the fix is to run existence separately from CI, not to add a
silent cap.

## 6. Artifacts

All rendered only when `modules.github_issues` is true (copier path-conditional
`{% if modules.github_issues %}…{% endif %}` per segment, matching sibling
modules; a segment that renders empty skips the file).

- **`scripts/process/check_issues.py`** — the gate. Globs registry stories,
  hard-validates `issue` format, best-effort existence via `gh`, reads
  `github_repo` from `.copier-answers.yml`. `main(root)` → exit 1 on any format
  failure, else 0; notes on stdout.
- **`scripts/process/gate_runner.py`** — add
  `"github-issues": ("github_issues", [sys.executable, "scripts/process/check_issues.py", "."])`
  to `GATES`. Runs only when the module is active (manifest-aware, existing
  mechanism).
- **`.github/ISSUE_TEMPLATE/feature.md`** and **`bug.md`** — neutral, EARS-framed
  Markdown templates with YAML frontmatter (`name`, `about`, `labels`). Sections:
  User Story (`As a <role>, I want …`), Context, Acceptance criteria (EARS),
  Scope, Dependencies. No Kenni terms (no "Seb", "Signal", `surface:ios`, …).
- **`scripts/process/new_issue.sh`** — portable POSIX seed helper: `new_issue.sh
  feature|bug` strips the YAML frontmatter from the chosen template, writes a
  temp body (neutral `mktemp` prefix), and prints the path (because `gh issue
  create` ignores `ISSUE_TEMPLATE/`). Documented for invocation as `bash
  scripts/process/new_issue.sh feature` (copier does not preserve the exec bit
  reliably).
- **`docs/process/modules/github-issues.md`** — the module doc: when required,
  the `issue`-ref format, what is hard vs. best-effort, prerequisites (repo + `gh`
  + auth), an **example** label schema (surface/priority/type/status — presented
  as a template to adapt, not enforced), and the claim/heartbeat/EARS-frame
  workflow ported neutrally from Kenni's backlog doc.

`copier.yml` gains `github_issues: false` in `modules.default` and the
`github_repo` question (§3).

## 7. Wiring & degradation

- Module **off**: none of the artifacts render; `gate_runner --list` omits
  `github-issues`. Verified by a render test.
- Module **on**, `feature_registry` **off**: `check_issues.py` finds no stories →
  a single note, exit 0. (An issue module without stories is inert, not an error.)
- Module **on**, `feature_registry` **on**, no stories yet: same inert note.
- The module doc's link to `.github/ISSUE_TEMPLATE/*.md` is inside
  `docs/process/`, so the `doc-drift` gate (when installed) checks that the
  referenced template paths resolve — a free integration check.

## 8. Testing

Mirror `tests/test_arch_onboarding.py` exactly; the fake-binary PATH pattern is
already proven there.

- **Fake `gh`** via a `_stub_gh(bindir, stdout, code)` helper (extends the
  existing `_stub`: controls both stdout and exit code) + `_run(out,
  extra_path)` prepending the stub dir to `PATH`. The suite never touches the
  network.
- Four existence cases, all asserting **exit 0** (advisory): gh-absent (note);
  gh-present exit 0 (no note); gh-present not-found/404 (note); gh-present
  auth/network error (note). Two of these — **gh-absent** and **404** — are
  written as explicit "must-not-hard-fail" guards; they are the honest-ceiling
  contract.
- **Repo forwarding:** an argv-capturing gh stub (like
  `test_depcruise_receives_code_roots`) asserts the check invokes `gh … --repo
  <configured>` for a bare `#NNN`.
- **Format (hard):** valid `#NNN` / cross-repo / URL pass; `412`, `#`,
  `octo/b#`, non-github URL, non-string each exit 1 — each isolated so the
  failure signal is the format check, not a bystander.
- **Empty/absent issue** allowed (exit 0); in-progress/done without issue emits
  the soft note.
- **Wiring:** `gate_runner --list` includes `github-issues` when on, omits it
  when off; artifacts present-when-on / absent-when-off.
- **Neutrality:** a test asserts the rendered `.github/ISSUE_TEMPLATE/*.md` and
  `github-issues.md` contain none of the KENNI-leak terms — `test_core_docs`'s
  scan does **not** cover `.github/`, so these files are otherwise unguarded.
- **Real render (pre-merge, like Slice 1):** `uvx copier … --vcs-ref HEAD
  --trust --defaults` with `doc_drift_gate` + `feature_registry` +
  `github_issues` all on; confirm artifacts render, the module doc's template
  refs resolve under doc-drift, and all gates pass; run `bash
  scripts/process/new_issue.sh feature` against the render.

## 9. Dogfooding

dev-process itself does not run GitHub-Issues as its backlog (it uses
`docs/plans/` + this design flow), so the module is not self-installed. It *is*
exercised by the render-and-run tests above, which is the honest form of
dogfooding for an opt-in module the host repo does not adopt.

## 10. Extension points

- **Other backends** (GitLab, Jira, Kafka-fed queues): the neutral concepts stay
  in `docs/process/`; a sibling module ships that backend's templates + a
  `check_<backend>.py` with the same hard-format / best-effort-existence split.
- **Promoting module flags to individual copier questions** (better Ersteinrichtung
  discoverability than one YAML blob) is a cross-cutting SP change, not part of
  this slice — noted for a future pass.

## 11. Open decisions (resolved)

- **Existence check present?** Yes, best-effort `gh` — maintainer.
- **Template format?** Markdown `.md` with YAML frontmatter — maintainer.
- **GitHub config asked when?** At Ersteinrichtung via copier, optional — maintainer.
- **Issue-format owner?** `check_issues.py`, feature-registry gate frozen —
  advisor-confirmed, adopted.
