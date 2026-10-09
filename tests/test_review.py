import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

JOURNAL = ".process-work/journal"
ARCHIVE = ".process-work/plans/archive"


def _run(root, env=None):
    return subprocess.run(
        [sys.executable, str(root / "scripts/process/check_review.py"), "."],
        cwd=root,
        capture_output=True,
        text=True,
        env=env,
    )


def _review(work="42", tier="2", reviewer="fresh", model="cross",
            independence="bundle,non-implementing", verdict="pass", rnd="1",
            artifact=None):
    line = (f"REVIEW work={work} tier={tier} reviewer={reviewer} model={model} "
            f"independence={independence} verdict={verdict} round={rnd}")
    if artifact:
        base, head, *legacy = artifact
        line += f" base={base} head={head}" + (f" diff={legacy[0]}" if legacy else "")
    return line


def _journal(root, *lines, name="2026-07-04.md"):
    d = root / JOURNAL
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text("\n".join(lines) + "\n", encoding="utf-8")


def _archived_plan(root, name, body):
    d = root / ARCHIVE
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(body, encoding="utf-8")


def _git(root: Path, *args: str, text: bool = True):
    return subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=text, check=True
    )


def _init_git_repo(root: Path, *, work: str = "bound") -> tuple[str, str, str]:
    """A repo with one reviewed feature commit; returns (base, head, digest)."""
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "Test")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    _git(root, "checkout", "-q", "-b", "feature")
    _archived_plan(root, f"2026-07-19-{work}.md", "# Plan\n\ntier: 2\n")
    (root / "payload.txt").write_text("reviewed\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "feat: payload")
    base = _git(root, "merge-base", "main", "HEAD").stdout.strip()
    head = _git(root, "rev-parse", "HEAD").stdout.strip()
    raw = _git(root, "diff", "--binary", f"{base}...{head}", text=False).stdout
    digest = hashlib.sha256(raw).hexdigest()
    return base, head, digest


def test_seed_tree_passes(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    r = _run(out)
    assert r.returncode == 0, r.stdout
    assert "review: OK" in r.stdout or "review: note:" in r.stdout


# --- grammar / enum hard ---

def test_malformed_missing_keys_hard(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    _journal(out, "REVIEW work=1 tier=3 verdict=pass")
    r = _run(out)
    assert r.returncode == 1 and "malformed" in r.stdout


def test_bad_verdict_hard(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    _journal(out, _review(verdict="maybe"))
    r = _run(out)
    assert r.returncode == 1 and "verdict" in r.stdout


def test_bad_independence_token_hard(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    _journal(out, _review(independence="bundle,telepathy"))
    r = _run(out)
    assert r.returncode == 1 and "independence" in r.stdout


def test_nonnumeric_tier_hard(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    _journal(out, _review(tier="high"))
    r = _run(out)
    assert r.returncode == 1 and "integer" in r.stdout


# --- independence arithmetic hard ---

def test_selfreview_pass_tier2_hard(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    _journal(out, _review(tier="2", independence="bundle"))  # no non-implementing
    r = _run(out)
    assert r.returncode == 1 and "non-implementing" in r.stdout


def test_tier1_pass_needs_no_independence(render, tmp_path):
    # SP34: Tier 0-1 is the self-check band (Quick flow reviews its own work);
    # the bundle/non-implementing floor is Tier 2. A Tier 1 pass carrying an
    # insufficient independence (non-implementing alone, no bundle — which WOULD
    # fail at Tier 2+) is clean.
    out = render(tmp_path, {"project_name": "demo"})
    _journal(out, _review(tier="1", independence="non-implementing"))
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_tier0_pass_needs_no_independence(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    _journal(out, _review(tier="0", independence="non-implementing"))
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_no_bundle_pass_tier2_hard(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    _journal(out, _review(tier="2", independence="non-implementing"))  # no bundle
    r = _run(out)
    assert r.returncode == 1 and "bundle" in r.stdout


def test_tier3_without_crossmodel_hard(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    _journal(out, _review(tier="3", independence="bundle,non-implementing"))
    r = _run(out)
    assert r.returncode == 1 and "tier 3" in r.stdout


def test_tier3_single_family_ok(render, tmp_path):
    # honest single-family acknowledgment clears the arithmetic (SP12's rule)
    out = render(tmp_path, {"project_name": "demo"})
    _journal(out, _review(work="p", tier="3",
                          independence="bundle,non-implementing,single-family"))
    _archived_plan(out, "2026-07-04-p.md", "tier: 3\n")
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_tier3_single_family_alone_hard(render, tmp_path):
    # the riskiest escape: single-family must NOT waive the tier>=1 bundle +
    # non-implementing requirements — it only excuses the missing cross-model
    out = render(tmp_path, {"project_name": "demo"})
    _journal(out, _review(tier="3", independence="single-family"))
    r = _run(out)
    assert r.returncode == 1
    assert "non-implementing" in r.stdout or "bundle" in r.stdout


def test_duplicate_key_hard(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    _journal(out, _review() + " tier=1")  # second tier= key
    r = _run(out)
    assert r.returncode == 1 and "duplicate" in r.stdout


def test_block_verdict_not_arithmetic_checked(render, tmp_path):
    # a block verdict doesn't clear anything, so its flags aren't arithmetic-gated
    out = render(tmp_path, {"project_name": "demo"})
    _journal(out, _review(tier="3", independence="bundle", verdict="block"))
    r = _run(out)
    # no archived tier>=2 plan requiring presence, so this is clean
    assert r.returncode == 0, r.stdout


# --- presence (post-merge, archived plans) ---

def test_presence_archived_tier2_without_review_hard(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    _archived_plan(out, "2026-07-04-feature.md", "# Plan\n\ntier: 2\n")
    r = _run(out)
    assert r.returncode == 1 and "no clearing REVIEW" in r.stdout


def test_a_missing_review_names_both_ways_out(render, tmp_path):
    """The archived-plan finding named only the waiver; attest is the other way out."""
    out = render(tmp_path, {"project_name": "demo"})
    _archived_plan(out, "2026-07-04-feature.md", "# Plan\n\ntier: 2\n")
    r = _run(out)
    line = next(ln for ln in r.stdout.splitlines() if "2026-07-04-feature.md" in ln
                and "no clearing REVIEW" in ln)
    assert "attest.py --work feature --tier 2" in line and "--verdict pass" in line, line
    assert "review-waived: <reason> #<issue>" in line and "journal-state-plans.md" in line, line


def test_a_missing_review_hint_names_a_tier_attest_accepts(render, tmp_path):
    """A plan above the 0-3 scale is cleared at tier 3 — the hint must not suggest --tier 4."""
    out = render(tmp_path, {"project_name": "demo"})
    _archived_plan(out, "2026-07-04-feature.md", "# Plan\n\ntier: 4\n")
    line = next(ln for ln in _run(out).stdout.splitlines()
                if "2026-07-04-feature.md" in ln and "no clearing REVIEW" in ln)
    assert "attest.py --work feature --tier 3 " in line and "tier>=3" in line and "--tier 4" not in line, line


def test_presence_cleared_by_matching_review(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    _archived_plan(out, "2026-07-04-feature.md", "# Plan\n\ntier: 2\n")
    _journal(out, _review(work="feature", tier="2"))
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_presence_review_lower_tier_does_not_clear_hard(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    _archived_plan(out, "2026-07-04-feature.md", "tier: 3\n")
    _journal(out, _review(work="feature", tier="2",
                          independence="bundle,non-implementing,cross-model"))
    r = _run(out)
    assert r.returncode == 1 and "no clearing REVIEW" in r.stdout


def test_presence_waiver_clears(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    _archived_plan(out, "2026-07-04-feature.md",
                   "tier: 2\nreview-waived: solo project, no second agent available\n")
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_tier_only_in_fenced_example_is_soft(render, tmp_path):
    # a plan whose only `tier:` occurrence is inside a fenced example is a
    # quotation, not a declaration — must be soft (no tier), not a hard presence
    # failure. Matches the journal parser's fence-skipping.
    out = render(tmp_path, {"project_name": "demo"})
    _archived_plan(out, "2026-07-04-feature.md",
                   "# Plan\n\nExample of the grammar:\n\n```\ntier: 3\n```\n")
    r = _run(out)
    assert r.returncode == 0, r.stdout
    assert "no 'tier:' declaration" in r.stdout


def test_dedated_slug_collision_not_cross_cleared(render, tmp_path):
    # two archived plans with the same de-dated slug on different dates: one
    # REVIEW must not silently clear both — the second, unreviewed, stays hard.
    out = render(tmp_path, {"project_name": "demo"})
    _archived_plan(out, "2026-01-01-foo.md", "tier: 2\n")
    _archived_plan(out, "2026-02-02-foo.md", "tier: 2\n")
    _journal(out, _review(work="foo", tier="2"))  # ambiguous short slug
    r = _run(out)
    assert r.returncode == 1 and "no clearing REVIEW" in r.stdout


def test_dedated_slug_unique_still_clears(render, tmp_path):
    # the convenience still works when the de-dated slug is unique
    out = render(tmp_path, {"project_name": "demo"})
    _archived_plan(out, "2026-01-01-foo.md", "tier: 2\n")
    _journal(out, _review(work="foo", tier="2"))
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_bulleted_tier_still_enforced_in_review(render, tmp_path):
    # F1 guard (review gate side): a bulleted archived-plan tier must not escape
    # the presence check either
    out = render(tmp_path, {"project_name": "demo"})
    _archived_plan(out, "2026-07-04-feature.md", "# Plan\n\n- tier: 2\n")
    r = _run(out)
    assert r.returncode == 1 and "no clearing REVIEW" in r.stdout


def test_presence_no_tier_is_soft(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    _archived_plan(out, "2026-07-04-feature.md", "# Plan\n\nNo tier here.\n")
    r = _run(out)
    assert r.returncode == 0, r.stdout
    assert "no 'tier:' declaration" in r.stdout


def test_presence_tier1_not_enforced(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    _archived_plan(out, "2026-07-04-feature.md", "tier: 1\n")
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_archived_design_doc_exempt_from_presence(render, tmp_path):
    # a design-*.md is a decision artifact, not a plan that ships behavior —
    # the review-presence check skips it even at tier 2 (audit coverage: the
    # design- prefix skip had no regression test)
    out = render(tmp_path, {"project_name": "demo"})
    _archived_plan(out, "design-2026-07-04-spine.md", "# Design\n\ntier: 2\n")
    r = _run(out)
    assert r.returncode == 0, r.stdout
    assert "no clearing REVIEW" not in r.stdout


def test_presence_matches_by_issue(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    _archived_plan(out, "2026-07-04-feature.md", "tier: 2\nissue: #99\n")
    _journal(out, _review(work="99", tier="2"))
    r = _run(out)
    assert r.returncode == 0, r.stdout


# --- digest binding (opt-in per REVIEW line) ---


def test_valid_digest_record_clears_plan(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    base, head, digest = _init_git_repo(out, work="bound")
    _journal(out, _review(work="bound", artifact=(base, head, digest)))
    r = _run(out)
    assert r.returncode == 0, r.stdout


@pytest.mark.parametrize("form", [("diff", "--binary", "--full-index"),
                                  ("-c", "core.abbrev=11", "diff", "--binary"),
                                  ("-c", "core.abbrev=4", "diff", "--binary"),
                                  ("-c", "core.abbrev=16", "diff", "--binary")],
                         ids=["full-index", "abbrev-11", "abbrev-4", "abbrev-16"])
def test_a_legacy_record_of_any_abbrev_stays_verifiable(render, tmp_path, form):
    # git abbreviates index lines by the clone's object count: a record
    # attested at abbrev=9 red-ed a fresh clone at 7 (observed downstream);
    # the union of the old forms keeps every one of them verifiable
    out = render(tmp_path, {"project_name": "demo"})
    base, head, _digest = _init_git_repo(out, work="bound")
    raw = _git(out, *form, f"{base}...{head}", text=False).stdout
    _journal(out, _review(work="bound", artifact=(base, head, hashlib.sha256(raw).hexdigest())))
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_retired_review_binding_is_note_not_silent(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    _archived_plan(out, "2026-07-04-old.md",
                   "tier: 2\nreview-binding: artifact-v1\n")
    _journal(out, _review(work="old", tier="2"))
    r = _run(out)
    assert r.returncode == 0, r.stdout
    assert "retired" in r.stdout


def test_partial_artifact_record_is_malformed(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    _journal(out, _review() + f" base={'a' * 40}")
    r = _run(out)
    assert r.returncode == 1
    assert "malformed" in r.stdout


def test_bad_artifact_sha_is_malformed(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    bad = ("a" * 39, "b" * 40, "c" * 64)
    _journal(out, _review(artifact=bad))
    r = _run(out)
    assert r.returncode == 1
    assert "base" in r.stdout and "Git SHA" in r.stdout











def test_fenced_review_line_ignored(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    _journal(out, "```", "REVIEW work=1 tier=3 verdict=pass", "```")  # malformed but fenced
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_non_utf8_journal_hard(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    d = out / JOURNAL
    d.mkdir(parents=True, exist_ok=True)
    (d / "2026-07-04.md").write_bytes(b"REVIEW \xff\xfe\n")
    r = _run(out)
    assert r.returncode == 1 and "not valid UTF-8" in r.stdout


# --- SP33 gate hardening (audit findings) ---

def test_tier_out_of_range_is_malformed(render, tmp_path):
    # audit: tier=4 on the 0-3 scale skipped the cross-model check AND cleared
    # a Tier-3 plan via >= tier — over-declaring must be malformed
    out = render(tmp_path, {"project_name": "demo"})
    _journal(out, _review(tier="4", independence="bundle,non-implementing"))
    r = _run(out)
    assert r.returncode == 1
    assert "outside the 0-3 scale" in r.stdout


def test_tier_over_declaration_does_not_clear_plan(render, tmp_path):
    # the full bypass: an archived Tier-3 plan must not be cleared by a tier=4
    # self-review that dodges the cross-model requirement
    out = render(tmp_path, {"project_name": "demo"})
    _archived_plan(out, "2026-07-01-auth.md", "tier: 3\n")
    _journal(out, _review(work="auth", tier="4", independence="bundle,non-implementing"))
    r = _run(out)
    assert r.returncode == 1
    # malformed tier line + unmet presence — both must bite
    assert "outside the 0-3 scale" in r.stdout


def test_bulleted_review_line_is_parsed(render, tmp_path):
    # audit: '- REVIEW ...' silently vanished — not parsed, not flagged
    out = render(tmp_path, {"project_name": "demo"})
    _archived_plan(out, "2026-07-04-feature.md", "tier: 2\n")
    _journal(out, "- " + _review(work="feature", tier="2"))
    r = _run(out)
    assert r.returncode == 0, r.stdout  # the bulleted pass clears the plan


def test_bulleted_malformed_review_is_flagged(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    _journal(out, "- REVIEW work=1 tier=2 verdict=pass")  # missing keys
    r = _run(out)
    assert r.returncode == 1 and "malformed" in r.stdout


def test_tilde_fenced_review_ignored(render, tmp_path):
    # audit false-green: a ~~~-fenced verdict=pass really cleared a Tier-3 plan
    out = render(tmp_path, {"project_name": "demo"})
    _archived_plan(out, "2026-07-01-auth.md", "tier: 3\n")
    _journal(out, "~~~", _review(work="auth", tier="3",
                                 independence="bundle,non-implementing,cross-model"), "~~~")
    r = _run(out)
    assert r.returncode == 1 and "no clearing REVIEW" in r.stdout


def test_unicode_digit_tier_fails_clean(render, tmp_path):
    # SP33 review MAJOR: the new range check called int() on a tier that passed
    # only isdigit() — unicode digits (²) raise ValueError → traceback. Must be
    # the clean malformed message instead.
    out = render(tmp_path, {"project_name": "demo"})
    _journal(out, _review(tier="²"))  # superscript two: isdigit True, int() raises
    r = _run(out)
    assert r.returncode == 1
    assert "integer" in r.stdout
    assert "Traceback" not in r.stdout and "Traceback" not in r.stderr


# --- SP50 audit: fence length-awareness, work-id validation, unreadable files


def test_quoted_waiver_in_nested_fence_does_not_clear(render, tmp_path):
    # a ``` run inside a ````-fenced example must not close the outer fence —
    # a QUOTED review-waived:/tier: line is a quotation, never a declaration
    out = render(tmp_path, {"project_name": "demo"})
    _archived_plan(out, "2026-07-10-widget.md",
                   "# Plan\n\ntier: 3\n\n````md\nexample:\n```\ncode\n```\n"
                   "review-waived: quoted example, not a waiver\n````\n")
    r = _run(out)
    assert r.returncode == 1, r.stdout
    assert "no clearing REVIEW" in r.stdout


def test_quoted_review_line_in_nested_fence_not_malformed(render, tmp_path):
    # the same length-awareness must not flag a QUOTED (fenced) REVIEW example
    out = render(tmp_path, {"project_name": "demo"})
    _journal(out,
             "notes",
             "````md",
             "```",
             "inner",
             "```",
             "REVIEW this quoted prose would be malformed outside a fence",
             "````")
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_non_issue_token_is_not_a_clearing_work_id(render, tmp_path):
    # `issue: v2.0` is not an issue ref — a REVIEW of unrelated work (work=0)
    # must not clear the plan (SP50 adversarial regression)
    out = render(tmp_path, {"project_name": "demo"})
    _archived_plan(out, "2026-07-10-widget.md", "# P\n\ntier: 2\nissue: v2.0\n")
    _journal(out, _review(work="0"))
    r = _run(out)
    assert r.returncode == 1, r.stdout
    assert "no clearing REVIEW" in r.stdout


def test_sentinel_issue_token_cannot_clear_two_plans(render, tmp_path):
    # two plans both declaring `issue: none` + one REVIEW work=none must not
    # both clear — `none` is not a ref and never becomes a work-id
    out = render(tmp_path, {"project_name": "demo"})
    _archived_plan(out, "2026-07-01-alpha.md", "# A\n\ntier: 2\nissue: none\n")
    _archived_plan(out, "2026-07-02-beta.md", "# B\n\ntier: 2\nissue: none\n")
    _journal(out, _review(work="none"))
    r = _run(out)
    assert r.returncode == 1, r.stdout
    assert r.stdout.count("no clearing REVIEW") == 2


def test_cross_repo_and_url_refs_still_clear(render, tmp_path):
    # the intended capability survives the validation: real refs resolve to
    # their number and `work=42` clears
    out = render(tmp_path, {"project_name": "demo"})
    _archived_plan(out, "2026-07-01-alpha.md", "# A\n\ntier: 2\nissue: owner/repo#42\n")
    _archived_plan(out, "2026-07-02-beta.md",
                   "# B\n\ntier: 2\nissue: https://github.com/o/r/issues/42\n")
    _journal(out, _review(work="42"))
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_directory_named_md_is_diagnosed_not_traceback(render, tmp_path):
    # a directory matching *.md (or a broken symlink) must yield a spoken
    # diagnosis, never a Python traceback
    out = render(tmp_path, {"project_name": "demo"})
    (out / JOURNAL / "2026-07-10.md").mkdir(parents=True)
    (out / ARCHIVE).mkdir(parents=True, exist_ok=True)
    (out / ARCHIVE / "2026-07-10-x.md").mkdir()
    (out / ARCHIVE / "gone.md").symlink_to(out / "does-not-exist")
    r = _run(out)
    assert "Traceback" not in r.stderr
    assert r.returncode == 1 and "could not read" in r.stdout


def test_active_tier2_plan_gets_visibility_note(render, tmp_path):
    # SP52: "forgot to archive" must not be perfectly silent — a soft note
    # names the gap; exit stays 0 (no red CI mid-development)
    out = render(tmp_path, {"project_name": "demo"})
    d = out / ".process-work/plans"
    d.mkdir(parents=True, exist_ok=True)
    (d / "2026-07-11-wip.md").write_text("# WIP\n\ntier: 2\n")
    r = _run(out)
    assert r.returncode == 0, r.stdout
    assert "active Tier 2 plan(s)" in r.stdout


# --- SP65: push-anchored presence — Tier 3 proof is due on the merge push ---

def _feature_repo_with_active_plan(render, tmp_path, *, tier=3, issue="#77",
                                   subject="feat: widget"):
    out = render(tmp_path, {"project_name": "demo"})
    _git(out, "init", "-q", "-b", "main")
    _git(out, "config", "user.email", "t@example.com")
    _git(out, "config", "user.name", "Test")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "base")
    _git(out, "checkout", "-q", "-b", "feature")
    d = out / ".process-work/plans"
    d.mkdir(parents=True, exist_ok=True)
    (d / "2026-09-07-widget.md").write_text(
        f"# Plan\n\ntier: {tier}\nissue: {issue}\n", encoding="utf-8")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", subject)
    return out


def test_tier3_active_plan_in_flight_is_note_without_push_target(render, tmp_path):
    out = _feature_repo_with_active_plan(render, tmp_path)
    r = _run(out)
    assert r.returncode == 0, r.stdout
    assert "proof is due before the merge" in r.stdout
    assert "[note only:" in r.stdout


def test_tier3_active_plan_in_flight_is_hard_on_merge_push(render, tmp_path):
    import os
    out = _feature_repo_with_active_plan(render, tmp_path)
    env = {**os.environ, "PROCESS_PUSH_TARGETS": "refs/heads/main"}
    r = _run(out, env=env)
    assert r.returncode == 1, r.stdout
    assert "proof is due before the merge" in r.stdout
    assert "[note only:" not in r.stdout


def test_a_tier3_plan_whose_name_git_quotes_is_in_flight(render, tmp_path):
    # a non-ASCII plan name, quoted by git without -z, read as not in flight:
    # the merge push passed without the proof (downstream refutation)
    import os
    out = _feature_repo_with_active_plan(render, tmp_path)
    _git(out, "mv", ".process-work/plans/2026-09-07-widget.md", ".process-work/plans/2026-09-07-größe.md")
    _git(out, "commit", "-q", "-m", "rename the plan")
    r = _run(out, env={**os.environ, "PROCESS_PUSH_TARGETS": "refs/heads/main"})
    assert r.returncode == 1, r.stdout
    assert "proof is due before the merge" in r.stdout


def test_pre_commit_remote_branch_is_read_without_wiring(render, tmp_path):
    # the pre-commit framework sets PRE_COMMIT_REMOTE_BRANCH for its pre-push
    # stage — the gate reads it, so the rendered config needs no hook script
    import os
    out = _feature_repo_with_active_plan(render, tmp_path)
    env = {**os.environ, "PRE_COMMIT_REMOTE_BRANCH": "refs/heads/master"}
    assert _run(out, env=env).returncode == 1
    env = {**os.environ, "PRE_COMMIT_REMOTE_BRANCH": "refs/heads/feature"}
    r = _run(out, env=env)
    assert r.returncode == 0 and "no integration branch" in r.stdout


def test_tier3_plan_not_carried_by_this_push_is_ignored(render, tmp_path):
    # somebody else's decision paper, committed on main before the branch:
    # not this push's proof to produce (the unscoped arm blocked an unrelated
    # branch in production)
    import os
    out = render(tmp_path, {"project_name": "demo"})
    _git(out, "init", "-q", "-b", "main")
    _git(out, "config", "user.email", "t@example.com")
    _git(out, "config", "user.name", "Test")
    d = out / ".process-work/plans"
    d.mkdir(parents=True, exist_ok=True)
    (d / "2026-09-01-foreign.md").write_text("# Plan\n\ntier: 3\nissue: #5\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "base with foreign plan")
    _git(out, "checkout", "-q", "-b", "feature")
    (out / "payload.txt").write_text("mine\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "feat: unrelated work, see #5")
    env = {**os.environ, "PROCESS_PUSH_TARGETS": "refs/heads/main"}
    r = _run(out, env=env)
    assert r.returncode == 0, r.stdout
    assert "proof is due" not in r.stdout and "claims #5" not in r.stdout  # a bare mention claims nothing


def test_commit_claiming_issue_of_tier3_plan_is_hard_on_merge_push(render, tmp_path):
    import os
    out = render(tmp_path, {"project_name": "demo"})
    _git(out, "init", "-q", "-b", "main")
    _git(out, "config", "user.email", "t@example.com")
    _git(out, "config", "user.name", "Test")
    d = out / ".process-work/plans"
    d.mkdir(parents=True, exist_ok=True)
    (d / "2026-09-01-claimed.md").write_text("# Plan\n\ntier: 3\nissue: #5\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "base with plan")
    _git(out, "checkout", "-q", "-b", "feature")
    (out / "payload.txt").write_text("mine\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "feat: implement it (#5)")
    env = {**os.environ, "PROCESS_PUSH_TARGETS": "refs/heads/main"}
    r = _run(out, env=env)
    assert r.returncode == 1, r.stdout
    assert "claims #5" in r.stdout and "2026-09-01-claimed.md" in r.stdout
    # the clearing pass lifts it
    _journal(out, _review(work="5", tier="3",
                          independence="bundle,non-implementing,cross-model"))
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "docs: attest")
    assert _run(out, env=env).returncode == 0


def test_commit_claiming_issue_of_a_spec_plan_is_hard_on_merge_push(render, tmp_path):
    """Kenni #2399: the commit arm joined only on .process-work plans — a
    specs/<dir>/plan.md declaring the issue was "no plan declares", a note."""
    import os
    out = render(tmp_path, {"project_name": "demo"})
    _git(out, "init", "-q", "-b", "main")
    _git(out, "config", "user.email", "t@example.com")
    _git(out, "config", "user.name", "Test")
    d = out / "specs/7-x"
    d.mkdir(parents=True, exist_ok=True)
    (d / "plan.md").write_text("# Plan\n\ntier: 2\nissue: #7\n\n## Decisions\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "base with spec plan")
    _git(out, "checkout", "-q", "-b", "feature")
    (out / "payload.txt").write_text("mine\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "feat: implement it (#7)")
    env = {**os.environ, "PROCESS_PUSH_TARGETS": "refs/heads/main"}
    r = _run(out, env=env)
    assert r.returncode == 1, r.stdout
    assert "claims #7" in r.stdout and "specs/7-x/plan.md" in r.stdout, r.stdout
    assert "no plan declares" not in r.stdout
    _journal(out, _review(work="7", tier="2"))
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "docs: attest")
    assert _run(out, env=env).returncode == 0


def test_tier2_active_plan_is_hard_on_merge_push(render, tmp_path):
    # observed downstream: a Tier 2 plan merged to main without a review, every
    # gate green — from Tier 2 on the proof is due at the merge push
    import os
    out = _feature_repo_with_active_plan(render, tmp_path, tier=2)
    r = _run(out)  # a feature push: visible, not blocking
    assert r.returncode == 0 and "[note only:" in r.stdout, r.stdout
    env = {**os.environ, "PROCESS_PUSH_TARGETS": "refs/heads/main"}
    r = _run(out, env=env)
    assert r.returncode == 1, r.stdout
    assert "from Tier 2 on the proof is due before the merge" in r.stdout


def test_tier3_plan_merged_past_the_process_is_hard_after_the_fact(render, tmp_path):
    # a bypassed hook or a platform merge button leaves the plan active while
    # its issue is already claimed on main — nothing else would ever see it
    out = render(tmp_path, {"project_name": "demo"})
    _git(out, "init", "-q", "-b", "main")
    _git(out, "config", "user.email", "t@example.com")
    _git(out, "config", "user.name", "Test")
    d = out / ".process-work/plans"
    d.mkdir(parents=True, exist_ok=True)
    plan = d / "2026-09-01-risky.md"
    plan.write_text("# Plan\n\ntier: 3\nissue: #9\n\n## Decisions\n")
    (out / "risky.py").write_text("x = 1\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "feat: risky change (#9)")
    r = _run(out)
    assert r.returncode == 1 and "tier 3 work already merged" in r.stdout, r.stdout
    plan.write_text(plan.read_text() + "\nreview-waived: hotfix under incident, reviewed after\n")
    r = _run(out)
    assert "tier 3 work already merged" not in r.stdout


# --- unhomed plans: a tier-declaring plan outside .process-work/specs is loud ---

def test_unhomed_tier2_plan_is_hard(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    (out / "docs/plans").mkdir(parents=True)
    (out / "docs/plans/2026-08-07-rogue.md").write_text(
        "# Plan\n\ntier: 2\n\nSteps.\n")
    r = _run(out)
    assert r.returncode == 1
    assert "outside the plan home" in r.stdout


def test_unhomed_tier1_and_fenced_quote_are_ignored(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    (out / "notes.md").write_text("tier: 1\n")  # not a gated plan
    (out / "howto.md").write_text("```\ntier: 3\n```\n")  # quotation
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_homed_and_archived_plans_are_not_unhomed(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    p = out / ".process-work/plans"
    p.mkdir(parents=True, exist_ok=True)
    (p / "2026-08-07-fine.md").write_text("tier: 2\nissue: #1\n")
    (out / "old/archive").mkdir(parents=True)
    (out / "old/archive/hist.md").write_text("tier: 3\n")  # archives are history
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_a_gitignored_plan_is_not_unhomed_but_an_untracked_one_is(render, tmp_path):
    # another agent's worktree nested under the checkout: ignored, in no
    # commit — it failed the push of whoever pushed next (observed downstream)
    out = render(tmp_path, {"project_name": "d"})
    _git(out, "init", "-q", "-b", "main")
    (out / ".gitignore").write_text((out / ".gitignore").read_text() + "\n.worktrees/\n"
                                    if (out / ".gitignore").is_file() else ".worktrees/\n")
    nested = out / ".worktrees/other-agent"
    nested.mkdir(parents=True)
    _git(nested, "init", "-q")
    (nested / "notes").mkdir()
    (nested / "notes/2026-08-10-their-plan.md").write_text("# Plan\n\ntier: 5\n")
    r = _run(out)
    assert "their-plan" not in r.stdout, r.stdout
    # a plan just written to the wrong place is untracked, not ignored: caught
    (out / "notes").mkdir()
    (out / "notes/2026-08-10-stray-plan.md").write_text("# Plan\n\ntier: 3\n")
    r = _run(out)
    assert r.returncode == 1 and "notes/2026-08-10-stray-plan.md: declares 'tier: 3' outside" in r.stdout
    assert "their-plan" not in r.stdout


def test_without_git_nothing_counts_as_ignored(render, tmp_path):
    # fail open: a broken ignore check must not silence the scan
    out = render(tmp_path, {"project_name": "d"})
    sys.path.insert(0, str(out / "scripts/process"))
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("check_review_ign", out / "scripts/process/check_review.py")
        gate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gate)
    finally:
        sys.path.pop(0)
    (out / "notes").mkdir()
    (out / "notes/stray.md").write_text("tier: 4\n")
    assert gate._gitignored(out, ["notes/stray.md"]) == set()
    assert len(gate._unhomed_plans(out)) == 1


def test_prose_tier_without_declaration_is_a_loud_note(render, tmp_path):
    # third-party plan writers know tiers, not the grammar — a plan saying
    # "Tier 4" in prose but declaring nothing sits outside every tier-keyed gate
    out = render(tmp_path, {"project_name": "d"})
    p = out / ".process-work/plans"
    p.mkdir(parents=True, exist_ok=True)
    (p / "2026-08-08-rogue.md").write_text(
        "# Plan\n\n- Issue: #7. Tier 4 — full review path.\n\nSteps.\n")
    r = _run(out)
    # SP70: off by omission is closed — an active plan without `tier: N` is hard
    assert r.returncode == 1, r.stdout
    assert "off by omission" in r.stdout and "rogue.md" in r.stdout


# --- SP62: a waiver is a debt with an owner --------------------------------

def test_waiver_without_issue_ref_notes_debt(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    _archived_plan(out, "2026-07-04-widget.md",
                   "# Plan\n\ntier: 2\nreview-waived: trivial rename\n")
    r = _run(out)
    assert r.returncode == 0, r.stdout
    assert "debt with an owner" in r.stdout


def test_waiver_with_issue_ref_stays_quiet(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    _archived_plan(out, "2026-07-04-widget.md",
                   "# Plan\n\ntier: 2\nreview-waived: trivial rename, tracked #12\n")
    r = _run(out)
    assert r.returncode == 0, r.stdout
    assert "debt with an owner" not in r.stdout


def test_speckit_done_dir_without_pass_notes(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    d = out / "specs" / "009-widget"
    d.mkdir(parents=True)
    (d / "plan.md").write_text("# Plan\n\ntier: 3\nissue: #9\n", encoding="utf-8")
    (d / "tasks.md").write_text("- [x] T001 done\n", encoding="utf-8")
    r = _run(out)
    assert r.returncode == 0, r.stdout
    assert "specs/009-widget" in r.stdout and "finish.py blocks" in r.stdout


def test_speckit_done_dir_with_pass_stays_quiet(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    d = out / "specs" / "009-widget"
    d.mkdir(parents=True)
    (d / "plan.md").write_text("# Plan\n\ntier: 3\nissue: #9\n", encoding="utf-8")
    (d / "tasks.md").write_text("- [x] T001 done\n", encoding="utf-8")
    _journal(out, "REVIEW work=9 tier=3 reviewer=fresh model=cross "
                  "independence=bundle,non-implementing,cross-model "
                  "verdict=pass round=1")
    r = _run(out)
    assert r.returncode == 0, r.stdout
    assert "finish.py blocks" not in r.stdout


def test_waiver_in_issue_anchored_plan_is_owned(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    _archived_plan(out, "2026-07-04-widget.md",
                   "# Plan\n\ntier: 2\nissue: #12\n"
                   "review-waived: trivial rename\n")
    _journal(out, "REVIEW work=12 tier=2 reviewer=fresh model=same "
                  "independence=bundle,non-implementing verdict=pass round=1")
    r = _run(out)
    assert r.returncode == 0, r.stdout
    assert "debt with an owner" not in r.stdout


def test_extended_scale_plan_clears_at_gated_ceiling(render, tmp_path):
    # a downstream 6-tier matrix may write `tier: 4` into a plan; the REVIEW
    # grammar caps at 3, so the plan clears at the gated ceiling instead of
    # an unmeetable bar
    out = render(tmp_path, {"project_name": "demo"})
    d = out / "specs" / "020-widget"
    d.mkdir(parents=True)
    (d / "plan.md").write_text("# Plan\n\ntier: 4\nissue: #20\n", encoding="utf-8")
    (d / "tasks.md").write_text("- [x] T001 done\n", encoding="utf-8")
    _journal(out, "REVIEW work=20 tier=3 reviewer=fresh model=cross "
                  "independence=bundle,non-implementing,cross-model "
                  "verdict=pass round=1")
    r = _run(out)
    assert r.returncode == 0, r.stdout
    assert "finish.py blocks" not in r.stdout


# --- SP69: the decisions ledger is a visible gap, never a silent one ---------

def test_tier2_plan_without_decisions_section_gets_a_note(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    d = out / ".process-work/plans"
    d.mkdir(parents=True, exist_ok=True)
    (d / "2026-09-10-bare.md").write_text("# Plan\n\ntier: 2\n")
    (d / "2026-09-10-kept.md").write_text("# Plan\n\ntier: 2\n\n## Decisions\n")
    (d / "2026-09-10-tiny.md").write_text("# Plan\n\ntier: 1\n")
    r = _run(out)
    assert r.returncode == 0, r.stdout
    assert "2026-09-10-bare.md: no '## Decisions' section" in r.stdout
    assert "2026-09-10-kept.md: no '## Decisions'" not in r.stdout
    assert "2026-09-10-tiny.md: no '## Decisions'" not in r.stdout


def test_spec_plan_without_decisions_section_gets_a_note(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    d = out / "specs/012-widget"
    d.mkdir(parents=True)
    (d / "plan.md").write_text("# Plan\n\ntier: 3\nissue: #12\n")
    r = _run(out)
    assert r.returncode == 0, r.stdout
    assert "specs/012-widget/plan.md: no '## Decisions' section" in r.stdout


# --- integrity scope: verified once per clone, in-flight shards always fresh ---

def _run_args(root, *args, env=None):
    return subprocess.run(
        [sys.executable, str(root / "scripts/process/check_review.py"), ".", *args],
        cwd=root, capture_output=True, text=True, env=env)


def test_a_missing_integration_base_is_a_presence_finding(render, tmp_path):
    """#161: no base is hard on the merge push and a note on a branch push, as
    verification-independence.md promises for every presence finding."""
    import os
    out = render(tmp_path, {"project_name": "demo"})
    plans = out / ".process-work/plans"
    plans.mkdir(parents=True, exist_ok=True)
    (plans / "2026-10-05-work.md").write_text("# Plan\n\ntier: 2\n\n## Decisions\n",
                                              encoding="utf-8")
    _git(out, "init", "-q", "-b", "main")
    _git(out, "config", "user.email", "t@example.com")
    _git(out, "config", "user.name", "Test")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "base")  # HEAD is main: no ref bounds the range
    env = {k: v for k, v in os.environ.items()
           if k not in ("PROCESS_PUSH_TARGETS", "PRE_COMMIT_REMOTE_BRANCH")}
    branch = _run(out, env)
    failed = branch.stdout.split("review: FAILED:")[-1] if "FAILED" in branch.stdout else ""
    assert "no proper integration base" in branch.stdout, branch.stdout
    assert "no proper integration base" not in failed, branch.stdout
    merge = _run(out, {**env, "PROCESS_PUSH_TARGETS": "refs/heads/main"})
    assert merge.returncode == 1
    assert "no proper integration base" in merge.stdout.split("review: FAILED:")[-1], merge.stdout


# --- #160 gate side: a full round vouching for the pushed range starts at the fork point ---

_CR = Path(__file__).resolve().parents[1] / "template/scripts/process/check_review.py"
_T3 = "bundle,non-implementing,cross-model"


def _cr():
    # loaded straight from the template tree: no __pycache__ may land there
    import importlib.util
    before = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec = importlib.util.spec_from_file_location("cr_fork_point", _CR)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = before
    return module


def _commit_file(root, rel, body):
    (root / rel).parent.mkdir(parents=True, exist_ok=True)
    (root / rel).write_text(body, encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", f"add {rel}")
    return _git(root, "rev-parse", "HEAD").stdout.strip()


def _fork_repo(root, work="forked"):
    """main at the fork, `feature` with the archived plan and two commits:
    (fork, first, head)."""
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "Test")
    fork = _commit_file(root, "README.md", "base\n")
    _git(root, "checkout", "-q", "-b", "feature")
    _archived_plan(root, f"2026-07-19-{work}.md", "# Plan\n\ntier: 2\n")
    first = _commit_file(root, "a.py", "a = 1\n")
    head = _commit_file(root, "b.py", "b = 1\n")
    return fork, first, head


def _full(cr, root, base, head, work="forked", tier="2", independence="bundle,non-implementing"):
    return _review(work=work, tier=tier, independence=independence,
                   artifact=(base, head))


def _merge_check(cr, root, monkeypatch):
    monkeypatch.setenv("PROCESS_PUSH_TARGETS", "refs/heads/main")
    return cr.check(root)


def test_a_delta_line_the_push_carries_is_judged_at_the_fork_point(tmp_path, monkeypatch):
    """Refutation of v2.53: with the anchor chain gone, a `mode=delta` line skipped the
    fork-point check and cleared a plan on a slice. Every ranged record is a full round."""
    cr, root = _cr(), tmp_path / "p"
    _fork, first, head = _fork_repo(root)
    _journal(root, _review(work="forked", artifact=(first, head)) + " mode=delta")
    hard, _ = _merge_check(cr, root, monkeypatch)
    assert any("malformed REVIEW line" in h and "is not the fork point" in h for h in hard), hard
    assert any("no clearing REVIEW" in h and "forked" in h for h in hard), hard


def test_an_unmerged_full_round_off_the_fork_point_is_hard_and_clears_nothing(tmp_path, monkeypatch):
    cr, root = _cr(), tmp_path / "p"
    _fork, first, head = _fork_repo(root)
    _journal(root, _full(cr, root, first, head))
    hard, _ = _merge_check(cr, root, monkeypatch)
    assert any("malformed REVIEW line" in h and "is not the fork point" in h for h in hard), hard
    assert any("no clearing REVIEW" in h and "forked" in h for h in hard), hard


def test_a_full_round_at_the_fork_point_clears_the_plan(tmp_path, monkeypatch):
    cr, root = _cr(), tmp_path / "p"
    fork, _first, head = _fork_repo(root)
    _journal(root, _full(cr, root, fork, head))
    hard, _ = _merge_check(cr, root, monkeypatch)
    assert hard == [], hard


def test_a_merged_legacy_full_round_stands_as_main_judged_it(tmp_path, monkeypatch):
    cr, root = _cr(), tmp_path / "p"
    _fork, first, head = _fork_repo(root)
    _git(root, "checkout", "-q", "main")
    _git(root, "merge", "-q", "--no-ff", "-m", "merge feature", "feature")
    _git(root, "checkout", "-q", "-b", "next")
    _journal(root, _full(cr, root, first, head))  # base = the previous head, pre-#160
    _commit_file(root, ".process-work/journal/2026-07-04.md",
                 (root / JOURNAL / "2026-07-04.md").read_text())
    hard, soft = _merge_check(cr, root, monkeypatch)
    assert hard == [], hard
    assert not any("legacy full-round" in s for s in soft), soft


def _merged_main_repo(root):
    """Downstream #2396: round 1 at the fork, a pre-v2.53 delta line off it,
    then main moved and was merged in: (fork, first, head, merge, main_tip)."""
    fork, first, head = _fork_repo(root)
    _git(root, "checkout", "-q", "main")
    main_tip = _commit_file(root, "c.py", "c = 1\n")
    _git(root, "checkout", "-q", "feature")
    _git(root, "merge", "-q", "--no-ff", "-m", "merge main", "main")
    merge = _git(root, "rev-parse", "HEAD").stdout.strip()
    return fork, first, head, merge, main_tip


def test_an_off_fork_line_superseded_by_a_valid_round_is_a_note(tmp_path, monkeypatch):
    """#199: a later valid full round of the same work reviewed everything from the
    fork point on — the old delta line no longer stops every push."""
    cr, root = _cr(), tmp_path / "p"
    fork, first, head, merge, main_tip = _merged_main_repo(root)
    _journal(root, _review(work="forked", artifact=(fork, first), rnd="1", verdict="block"),
             _review(work="forked", artifact=(first, head), rnd="2") + " mode=delta",
             _review(work="forked", artifact=(main_tip, merge), rnd="3"))
    hard, soft = _merge_check(cr, root, monkeypatch)
    assert hard == [], hard
    assert any("clears nothing" in s and "superseded by the valid round=3" in s for s in soft), soft


def test_an_off_fork_line_without_a_later_valid_round_stays_hard(tmp_path, monkeypatch):
    cr, root = _cr(), tmp_path / "p"
    fork, first, head, _merge, _main_tip = _merged_main_repo(root)
    _journal(root, _review(work="forked", artifact=(fork, first), rnd="1", verdict="block"),
             _review(work="forked", artifact=(first, head), rnd="2") + " mode=delta")
    hard, _ = _merge_check(cr, root, monkeypatch)
    assert any("malformed REVIEW line" in h and "is not the fork point" in h for h in hard), hard


@pytest.mark.parametrize("later", ["off-fork", "other-work", "lower-round"])
def test_an_off_fork_line_is_not_superseded_by_an_unfit_round(tmp_path, monkeypatch, later):
    cr, root = _cr(), tmp_path / "p"
    _fork, first, head, merge, main_tip = _merged_main_repo(root)
    third = {"off-fork": _review(work="forked", artifact=(head, merge), rnd="3"),
             "other-work": _review(work="other", artifact=(main_tip, merge), rnd="3"),
             "lower-round": _review(work="forked", artifact=(main_tip, merge), rnd="1")}[later]
    _journal(root, _review(work="forked", artifact=(first, head), rnd="2") + " mode=delta", third)
    hard, _ = _merge_check(cr, root, monkeypatch)
    assert any("malformed REVIEW line" in h and f"base {first[:12]}" in h for h in hard), hard


def test_a_superseded_off_fork_pass_still_clears_nothing(tmp_path, monkeypatch):
    """The later round is a block: the old pass may not stand in for it."""
    cr, root = _cr(), tmp_path / "p"
    _fork, first, head, merge, main_tip = _merged_main_repo(root)
    _journal(root, _review(work="forked", artifact=(first, head), rnd="2") + " mode=delta",
             _review(work="forked", artifact=(main_tip, merge), rnd="3", verdict="block"))
    hard, soft = _merge_check(cr, root, monkeypatch)
    assert not any("malformed REVIEW line" in h for h in hard), hard
    assert any("forked" in h for h in hard), hard
    assert any("superseded" in s for s in soft), soft


def test_a_round_whose_head_does_not_descend_supersedes_nothing(tmp_path, monkeypatch):
    """Refute #199: the later round must have reviewed the old line's head."""
    cr, root = _cr(), tmp_path / "p"
    fork, first, head, _merge, _main_tip = _merged_main_repo(root)
    _git(root, "checkout", "-q", "-b", "elsewhere", fork)
    other = _commit_file(root, "o.py", "o = 1\n")
    _git(root, "checkout", "-q", "feature")
    _journal(root, _review(work="forked", artifact=(first, head), rnd="2") + " mode=delta",
             _review(work="forked", artifact=(fork, other), rnd="3"))
    hard, _ = _merge_check(cr, root, monkeypatch)
    assert any("malformed REVIEW line" in h and f"base {first[:12]}" in h for h in hard), hard


def test_an_issue_work_id_supersedes_in_any_spelling(tmp_path, monkeypatch):
    cr, root = _cr(), tmp_path / "p"
    _fork, first, head, merge, main_tip = _merged_main_repo(root)
    _archived_plan(root, "2026-07-19-forked.md", "# Plan\n\ntier: 2\nissue: #26\n")
    _journal(root, _review(work="26", artifact=(first, head), rnd="2") + " mode=delta",
             _review(work="#26", artifact=(main_tip, merge), rnd="3"))
    hard, soft = _merge_check(cr, root, monkeypatch)
    assert not any("malformed REVIEW line" in h for h in hard), hard
    assert any("superseded" in s for s in soft), soft


def test_an_off_fork_record_of_a_stale_branch_is_one_note_and_still_clears(tmp_path, monkeypatch):
    """Downstream: records of stale branches whose plans are archived on main —
    their heads are no part of this push; judging them would red every push."""
    cr, root = _cr(), tmp_path / "p"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "Test")
    _commit_file(root, "README.md", "base\n")
    _git(root, "checkout", "-q", "-b", "stale")
    first = _commit_file(root, "s1.py", "s = 1\n")
    head = _commit_file(root, "s2.py", "s = 2\n")
    _git(root, "checkout", "-q", "main")
    _archived_plan(root, "2026-07-19-stale.md", "# Plan\n\ntier: 2\n")
    _journal(root, _full(cr, root, first, head, work="stale"))
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "archive stale")
    _git(root, "checkout", "-q", "-b", "next")
    _commit_file(root, "docs/notes.md", "unrelated\n")
    hard, soft = _merge_check(cr, root, monkeypatch)
    assert not any("fork point" in h or "stale" in h for h in hard), hard
    assert any(s.startswith("1 legacy full-round record(s) not checked against the fork point: "
                            "head not in this push's history") for s in soft), soft


def test_a_criss_cross_head_names_the_ambiguous_fork_point(tmp_path):
    cr, root = _cr(), tmp_path / "p"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "Test")
    base = _commit_file(root, "README.md", "base\n")
    _git(root, "checkout", "-q", "-b", "feature")
    a1 = _commit_file(root, "feature.md", "a1\n")
    _git(root, "checkout", "-q", "main")
    b1 = _commit_file(root, "main.md", "b1\n")
    _git(root, "merge", "-q", "--no-ff", "-m", "main takes feature", a1)
    _git(root, "checkout", "-q", "feature")
    _git(root, "merge", "-q", "--no-ff", "-m", "feature takes main", b1)
    tip = _git(root, "rev-parse", "HEAD").stdout.strip()
    records = [f for _ln, f in cr.parse_review_lines(_review(
        work="x", artifact=(base, tip, "0" * 64)) + "\n")[0]]
    why = cr.invalid_full_rounds(root, records, tip)[id(records[0])]
    assert "one fork point" in why and "merge bases" in why, why


@pytest.mark.parametrize("shape", ["ff-main", "forged-master"])
def test_a_local_ref_at_the_tip_does_not_hide_the_pushed_range(tmp_path, monkeypatch, shape):
    """finish.py fast-forwards local main to the branch before the push; a
    local ref containing the tip bounds nothing — origin/main, behind, does."""
    cr, root = _cr(), tmp_path / "p"
    fork, first, head = _fork_repo(root)
    _git(root, "update-ref", "refs/remotes/origin/main", fork)  # fetched, behind the push
    if shape == "ff-main":
        _git(root, "checkout", "-q", "main")
        _git(root, "merge", "-q", "--ff-only", "feature")
    else:
        _git(root, "update-ref", "refs/heads/master", head)
    _journal(root, _full(cr, root, first, head))
    hard, _ = _merge_check(cr, root, monkeypatch)
    assert any("malformed REVIEW line" in h and "is not the fork point" in h for h in hard), hard


def test_a_stale_local_main_behind_an_integrated_tip_reopens_nothing(tmp_path, monkeypatch):
    """Kenni main push: HEAD == origin/main, local main far behind — main's
    own history is integrated, its legacy records are not this push's."""
    cr, root = _cr(), tmp_path / "p"
    fork, first, head = _fork_repo(root)
    _journal(root, _full(cr, root, first, head))  # pre-#160 base: the previous head
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "attest")
    tip = _git(root, "rev-parse", "HEAD").stdout.strip()
    _git(root, "update-ref", "refs/remotes/origin/main", tip)  # the tip is merged upstream
    assert _git(root, "rev-parse", "main").stdout.strip() == fork  # local main stale
    hard, soft = _merge_check(cr, root, monkeypatch)
    assert not any("fork point" in h for h in hard), hard
    assert not any("legacy full-round" in s for s in soft), soft


@pytest.mark.parametrize("target,hard_side", [("refs/heads/main", True), ("refs/heads/7-x", False)])
def test_without_any_integration_ref_one_finding_not_one_per_record(tmp_path, monkeypatch,
                                                                    target, hard_side):
    cr, root = _cr(), tmp_path / "p"
    root.mkdir()
    _git(root, "init", "-q", "-b", "trunk")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "Test")
    fork = _commit_file(root, "README.md", "base\n")
    _git(root, "checkout", "-q", "-b", "feature")
    first = _commit_file(root, "a.py", "a = 1\n")
    head = _commit_file(root, "b.py", "b = 1\n")
    _journal(root, _full(cr, root, fork, first, work="one"), _full(cr, root, first, head, work="two"))
    monkeypatch.setenv("PROCESS_PUSH_TARGETS", target)
    hard, soft = cr.check(root)
    assert not any("integration ref resolves" in h and "malformed" in h for h in hard), hard
    found = [f for f in (hard if hard_side else soft) if cr.NO_INTEGRATION_REF in f]
    assert len(found) == 1, (hard, soft)
