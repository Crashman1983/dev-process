# SP54 Review Artifact Binding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bind Tier-2+ review passes to the exact integrated diff, document a three-case governance-economics pilot without activating it, and make fresh-worktree requirements explicit for project gates.

**Architecture:** `make_review_bundle.py` owns the canonical binary-diff fingerprint; `check_review.py` owns the legacy/v2 grammar, certificate validation, and candidate comparison. A tree-empty commit carries the v2 certificate without changing the reviewed diff. Git hooks and CI adapters only provide neutral candidate-base/target context; the gate remains provider-neutral.

**Tech Stack:** Python 3.11+ stdlib, Git CLI, Copier/Jinja templates, pytest, GitHub Actions YAML, GitLab CI YAML, Markdown.

---

**Design:** `docs/design/2026-07-18-sp54-review-binding-governance-pilot.md`

**Tier:** 2

**Issue:** waived by direct user instruction; no GitHub-side mutation requested.

**Baseline:** `uv run pytest -q` -> `671 passed` on commit `ff13d60`'s parent plus the approved design commit.

## File responsibilities

- `make_review_bundle.py`: resolve merge base and head, hash the exact binary diff, render fingerprint plus v2 grammar.
- `check_review.py`: parse legacy and v2 records, validate certificate commits, enforce bound plans and candidate equality.
- `run_hook.py`: transport Git's remote SHA/ref into the detached gate worktree for protected-target pushes.
- CI adapters: transport provider event base/target and fetch enough history; no review policy lives here.
- Review/process docs: define finalise -> review -> empty certificate commit -> integrate.
- Testing/hook docs: define cache-independent project-gate bootstrap.
- Pilot file: record case 1/3 and the exact decision fields for cases 2/3 without changing template routing.

## Task 1: Canonical bundle fingerprint

**Files:**

- Modify: `tests/test_review_bundle.py`
- Modify: `template/scripts/process/make_review_bundle.py`

- [x] **Step 1: Add failing fingerprint tests**

Add tests that extract this exact bundle block and independently recompute the digest:

```python
import hashlib
import re


def _artifact(text: str) -> dict[str, str]:
    match = re.search(
        r"^REVIEW_ARTIFACT base=(?P<base>[0-9a-f]{40,64}) "
        r"head=(?P<head>[0-9a-f]{40,64}) diff=(?P<diff>[0-9a-f]{64})$",
        text,
        re.MULTILINE,
    )
    assert match, text
    return match.groupdict()


def test_bundle_fingerprint_matches_binary_diff(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    text = _run(out, "--base", "main").stdout
    artifact = _artifact(text)
    merge_base = _git(out, "merge-base", "main", "HEAD").stdout.strip()
    head = _git(out, "rev-parse", "HEAD").stdout.strip()
    diff = subprocess.run(
        ["git", "diff", "--binary", f"{merge_base}...{head}"],
        cwd=out,
        capture_output=True,
        check=True,
    ).stdout
    assert artifact == {
        "base": merge_base,
        "head": head,
        "diff": hashlib.sha256(diff).hexdigest(),
    }


def test_bundle_fingerprint_changes_with_committed_content(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    first = _artifact(_run(out, "--base", "main").stdout)["diff"]
    (out / "widget.py").write_text("def widget():\n    return 43\n")
    _git(out, "add", "widget.py", check=True)
    _git(out, "commit", "-q", "-m", "fix: change widget", check=True)
    second = _artifact(_run(out, "--base", "main").stdout)["diff"]
    assert first != second
```

- [x] **Step 2: Run RED**

Run:

```bash
uv run pytest tests/test_review_bundle.py -q
```

Expected: the new tests fail because `REVIEW_ARTIFACT` is absent.

- [x] **Step 3: Implement byte-exact fingerprinting**

Add `hashlib`, a bytes-returning Git helper, and a single owner for artifact creation:

```python
def _git_bytes(root: Path, *args: str) -> bytes | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout if result.returncode == 0 else None


def _review_artifact(root: Path, base_ref: str) -> tuple[str, str, str, bytes] | None:
    base = _git(root, "merge-base", base_ref, "HEAD")
    head = _git(root, "rev-parse", "HEAD")
    if not base or not head:
        return None
    base_sha = base.strip()
    head_sha = head.strip()
    diff = _git_bytes(root, "diff", "--binary", f"{base_sha}...{head_sha}")
    if diff is None:
        return None
    return base_sha, head_sha, hashlib.sha256(diff).hexdigest(), diff
```

Render `REVIEW_ARTIFACT base=... head=... diff=...` immediately before the diff fence. Decode only for Markdown display with UTF-8 replacement; hash the original bytes. Keep empty-diff and unavailable-base diagnostics explicit.

- [x] **Step 4: Run GREEN and regressions**

Run:

```bash
uv run pytest tests/test_review_bundle.py -q
```

Expected: all bundle tests pass.

- [x] **Step 5: Commit Task 1**

```bash
git add tests/test_review_bundle.py template/scripts/process/make_review_bundle.py
git commit -m "feat: fingerprint review bundles"
```

## Task 2: Bound REVIEW certificate and candidate gate

**Files:**

- Modify: `tests/test_review.py`
- Modify: `template/scripts/process/check_review.py`

- [x] **Step 1: Add failing grammar and certificate tests**

Extend the test helper without changing legacy defaults:

```python
def _review(
    work="42",
    tier="2",
    reviewer="fresh",
    model="cross",
    independence="bundle,non-implementing",
    verdict="pass",
    rnd="1",
    artifact: tuple[str, str, str] | None = None,
):
    line = (
        f"REVIEW work={work} tier={tier} reviewer={reviewer} model={model} "
        f"independence={independence} verdict={verdict} round={rnd}"
    )
    if artifact:
        base, head, diff = artifact
        line += f" base={base} head={head} diff={diff}"
    return line
```

Add real-Git tests covering:

- a legacy record still clears a legacy plan;
- `review-binding: artifact-v1` rejects a journal-only legacy or v2 record;
- a commit-message v2 record with wrong SHA length is malformed;
- a valid tree-empty certificate whose only parent is `head` clears the bound plan;
- non-empty certificate, wrong parent, unknown commit and wrong digest fail;
- with `DEV_PROCESS_CANDIDATE_BASE` and target `main`, a changed candidate diff fails;
- the exact candidate diff passes;
- more than one newly archived bound plan in one candidate fails explicitly.

Use a helper that initializes a rendered repo, commits a base, commits and archives one bound plan, calculates `sha256(git diff --binary base...head)`, then creates the certificate with:

```python
_git(out, "commit", "--allow-empty", "-q", "-m", "chore: attest review", "-m", review_line, check=True)
```

- [x] **Step 2: Run RED**

Run:

```bash
uv run pytest tests/test_review.py -q
```

Expected: bound-record and certificate tests fail; existing legacy tests remain green.

- [x] **Step 3: Implement migration-safe v2 parsing**

Keep the legacy required set and accept exactly one of two shapes:

```python
LEGACY_REQUIRED = {
    "work", "tier", "reviewer", "model", "independence", "verdict", "round"
}
ARTIFACT_REQUIRED = LEGACY_REQUIRED | {"base", "head", "diff"}
REQUIRED = ARTIFACT_REQUIRED
REVIEW_BINDING_DECL = re.compile(
    _LEAD + r"review-binding[*_]*\s*:\s*[*_]*\s*(\S+)",
    re.IGNORECASE | re.MULTILINE,
)
GIT_SHA = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
```

`parse_review_lines()` accepts `LEGACY_REQUIRED` or `ARTIFACT_REQUIRED`, rejects every partial/extra shape, and validates artifact formats. `_grammar_section()` continues importing `REQUIRED`, so new bundles demand v2 output.

- [x] **Step 4: Collect and validate commit certificates**

Add stdlib-only Git helpers and a certificate record carrying source commit, parents and tree. Parse commit bodies from one NUL/record-separated `git log` call. A certificate is valid only when:

```python
len(parents) == 1
and parents[0] == fields["head"]
and certificate_tree == _git_text(root, "rev-parse", f"{fields['head']}^{{tree}}")
and _sha256_diff(root, fields["base"], fields["head"]) == fields["diff"]
```

Journal records continue through the old path. Only valid commit certificates enter `bound_passes`; all validation failures are hard findings naming the source commit.

- [x] **Step 5: Enforce artifact-v1 presence and candidate equality**

For each archived plan, parse `review-binding`. Values other than `artifact-v1` are hard. A bound plan is cleared only by `bound_passes`; a legacy plan may use either legacy or valid bound passes.

When both `DEV_PROCESS_CANDIDATE_BASE` and a protected target are present:

1. resolve the candidate base commit;
2. list added/modified/renamed files under `.process-work/plans/archive` in `base...HEAD`;
3. retain only plans declaring `artifact-v1`;
4. hard-fail if there is more than one;
5. compute the binary candidate digest;
6. require the clearing certificate's `diff` to equal it.

Do not infer candidate binding without explicit context.

- [x] **Step 6: Run GREEN and full review-gate tests**

Run:

```bash
uv run pytest tests/test_review.py tests/test_review_bundle.py -q
```

Expected: all review and bundle tests pass.

- [x] **Step 7: Commit Task 2**

```bash
git add tests/test_review.py template/scripts/process/check_review.py template/scripts/process/make_review_bundle.py
git commit -m "feat: bind reviews to certified diffs"
```

## Task 3: Transport candidate context through hooks and CI

**Files:**

- Modify: `tests/test_git_hooks.py`
- Modify: `tests/test_ci_adapters.py`
- Modify: `template/scripts/process/{% if modules.git_hooks %}run_hook.py{% endif %}`
- Modify: `template/.github/{% if ci.github %}workflows{% endif %}/process-gates.yml.jinja`
- Modify: `template/{% if ci.gitlab %}.gitlab{% endif %}/ci/process-gates.gitlab-ci.yml`

- [x] **Step 1: Add failing transport tests**

In `tests/test_git_hooks.py`, commit a tiny executable probe as the rendered `gate_runner.py` that writes `DEV_PROCESS_CANDIDATE_BASE` and `DEV_PROCESS_CANDIDATE_TARGET` to a tracked-test temporary path. Feed the hook:

```text
refs/heads/main <local_sha> refs/heads/main <remote_sha>
```

Assert the detached invocation receives the remote SHA and `refs/heads/main`. Add negative tests for feature branches and all-zero deletion/new-ref SHAs.

In `tests/test_ci_adapters.py`, assert:

```python
assert "fetch-depth: 0" in github_text
assert "DEV_PROCESS_CANDIDATE_BASE" in github_text
assert "github.event.pull_request.base.sha" in github_text
assert "github.event.before" in github_text
assert 'GIT_DEPTH: "0"' in gitlab_text
assert "CI_MERGE_REQUEST_DIFF_BASE_SHA" in gitlab_text
assert "CI_COMMIT_BEFORE_SHA" in gitlab_text
```

- [x] **Step 2: Run RED**

Run:

```bash
uv run pytest tests/test_git_hooks.py tests/test_ci_adapters.py -q
```

Expected: candidate-context assertions fail.

- [x] **Step 3: Implement hook transport**

Change `_gate_commit()` to receive remote ref/SHA. Copy the clean environment and set neutral variables only when the target is `refs/heads/main` or `refs/heads/master` and the SHA is not all zeroes:

```python
gate_env = dict(env)
if remote_ref in {"refs/heads/main", "refs/heads/master"} and remote_sha != ZERO_SHA:
    gate_env["DEV_PROCESS_CANDIDATE_BASE"] = remote_sha
    gate_env["DEV_PROCESS_CANDIDATE_TARGET"] = remote_ref
```

Pass `gate_env` to worktree creation and the gate runner. Preserve new-feature-branch behavior.

- [x] **Step 4: Implement CI transport and full-history checkout**

GitHub Actions uses `fetch-depth: 0` and provider expressions selecting PR base SHA/target or push-before SHA/ref. GitLab sets `GIT_DEPTH: "0"` and invokes the runner with shell-fallback variables:

```yaml
- DEV_PROCESS_CANDIDATE_BASE="${CI_MERGE_REQUEST_DIFF_BASE_SHA:-$CI_COMMIT_BEFORE_SHA}"
  DEV_PROCESS_CANDIDATE_TARGET="${CI_MERGE_REQUEST_TARGET_BRANCH_NAME:-$CI_COMMIT_BRANCH}"
  uv run scripts/process/gate_runner.py
```

- [x] **Step 5: Run GREEN**

Run:

```bash
uv run pytest tests/test_git_hooks.py tests/test_ci_adapters.py tests/test_cross_platform_runtime.py -q
```

Expected: all hook, CI, and cross-platform tests pass.

- [x] **Step 6: Commit Task 3**

```bash
git add tests/test_git_hooks.py tests/test_ci_adapters.py \
  'template/scripts/process/{% if modules.git_hooks %}run_hook.py{% endif %}' \
  'template/.github/{% if ci.github %}workflows{% endif %}/process-gates.yml.jinja' \
  'template/{% if ci.gitlab %}.gitlab{% endif %}/ci/process-gates.gitlab-ci.yml'
git commit -m "feat: pass review candidate context"
```

## Task 4: Workflow, portability contract, and pilot evidence

**Files:**

- Create: `docs/pilots/2026-07-19-governance-economics.md`
- Modify: `template/docs/process/verification-independence.md`
- Modify: `template/docs/process/journal-state-plans.md`
- Modify: `template/docs/process/workflow.md.jinja`
- Modify: `template/docs/process/testing.md`
- Modify: `template/docs/process/{% if modules.git_hooks %}modules{% endif %}/git-hooks.md`
- Modify: `tests/test_core_docs.py`
- Modify: `tests/test_git_hooks.py`
- Create: `tests/test_governance_pilot.py`

- [x] **Step 1: Add failing rendered-document assertions**

Assert the rendered docs contain these invariant phrases or equivalent exact sentences:

```python
assert "review-binding: artifact-v1" in verification_text
assert "empty certificate commit" in workflow_text
assert "final rebase" in workflow_text
assert "fresh checkout" in testing_text
assert ".venv" in testing_text and "node_modules" in testing_text
assert "reproducible bootstrap" in hook_text
```

Also assert no active `governance-only` routing token is added to rendered
`risk-tiers.md`, `workflow.md`, or command adapters.

- [x] **Step 2: Run RED**

Run:

```bash
uv run pytest tests/test_review_bundle.py tests/test_git_hooks.py -q
```

Expected: new documentation assertions fail.

- [x] **Step 3: Document the bound workflow**

Update the three review owners in English:

1. final fetch/rebase and all content commits, including plan archival;
2. build bundle and run independent review;
3. record the exact v2 line in a tree-empty certificate commit;
4. push/PR candidate gate recomputes the digest;
5. any later tree mutation invalidates the certificate and returns to review.

State that journal copies are human-readable but do not clear `artifact-v1`.

- [x] **Step 4: Document the fresh-worktree project-gate contract**

Add one compact section to `testing.md` and one adapter note to the Git-hook
module: protected-path project gates must start from a fresh checkout without
ignored caches, bootstrap via a lockfile-backed command such as `uv run`, and
must diagnose missing bootstrap separately from product failure.

- [x] **Step 5: Create the non-active pilot ledger**

Create the meta-repo file with case 1/3 populated from the Kenni observation:

```markdown
# Governance economics pilot

Status: 1/3 observed; no template routing change authorised.

| Field | Case 1 — Kenni product direction |
|---|---|
| intent_mode | documentation |
| semantic_impact | high |
| mutation_class | governance-only |
| terminal_state | review-complete, merge not authorised at observation time |
| claim_delta | stale meeting capability claim corrected against inventory owner |
| process_cost | 363 plan lines, 15 acceptance criteria, 10 commits, 3 review rounds |
| repeated_decision_question | yes |
| outcome | pending cases 2 and 3 |
```

Below the table, define the same fields for cases 2/3 and the final
`adopt | revise | reject` decision. State explicitly that this file has no
template or gate effect.

- [x] **Step 6: Run GREEN**

Run:

```bash
uv run pytest tests/test_review_bundle.py tests/test_git_hooks.py -q
```

Expected: rendered-document assertions pass.

- [x] **Step 7: Commit Task 4**

```bash
git add docs/pilots/2026-07-19-governance-economics.md \
  template/docs/process/verification-independence.md \
  template/docs/process/journal-state-plans.md \
  template/docs/process/workflow.md.jinja \
  template/docs/process/testing.md \
  'template/docs/process/{% if modules.git_hooks %}modules{% endif %}/git-hooks.md' \
  tests/test_review_bundle.py tests/test_git_hooks.py
git commit -m "docs: define bound review workflow"
```

## Task 5: Final verification and review preparation

**Files:**

- Modify: `docs/plans/2026-07-19-sp54-review-binding-governance-pilot.md` (checkboxes only before freeze)
- Review: every changed file since `origin/main`

- [x] **Step 1: Run scoped tests**

```bash
uv run pytest tests/test_review.py tests/test_review_bundle.py \
  tests/test_git_hooks.py tests/test_ci_adapters.py \
  tests/test_cross_platform_runtime.py -q
```

- [x] **Step 2: Run full verification**

```bash
uv run pytest -q
uv run ruff check .
git diff --check origin/main...HEAD
```

Expected: all commands exit zero.

- [x] **Step 3: Validate a rendered target manually**

Render a default target through the existing pytest fixture path, initialize
Git, create one `artifact-v1` plan and certificate, then prove:

- exact candidate -> `check_review.py` exits zero;
- one post-review content commit -> exits non-zero with digest mismatch;
- deleting the content commit restores green.

Use only a temporary directory; do not commit rendered artifacts.

- [ ] **Step 4: Freeze the candidate and build its review bundle**

After checklist updates are committed, build the read-only bundle from
`origin/main` and run the required independent review. The meta-repo owns plans
under `docs/plans`; do not create a duplicate `.process-work/plans` copy merely
to self-host the newly rendered contract. The temporary rendered-target proof
from Step 3 is the v2 certificate acceptance test for this slice; the meta diff
keeps its normal repository review record.

- [ ] **Step 5: Report terminal state**

Report implementation, verification, review, branch cleanliness and whether
merge/push remain pending. Do not merge or push without a separate user order.

## Plan self-review

- Design coverage: fingerprint, self-reference-free certificate, candidate
  transport, legacy migration, CI history, portability contract and 1/3 pilot
  each have an owning task and proof.
- Scope: one Core review-integrity slice; governance routing remains excluded.
- Placeholders: none; schema metavariables are concrete grammar examples.
- Type consistency: artifact fields are consistently `base`, `head`, `diff`;
  candidate context is consistently `DEV_PROCESS_CANDIDATE_BASE` and
  `DEV_PROCESS_CANDIDATE_TARGET`.
