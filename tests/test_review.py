import subprocess
import sys

JOURNAL = ".process-work/journal"
ARCHIVE = ".process-work/plans/archive"


def _run(root):
    return subprocess.run(
        [sys.executable, str(root / "scripts/process/check_review.py"), "."],
        cwd=root, capture_output=True, text=True,
    )


def _review(work="42", tier="2", reviewer="fresh", model="cross",
            independence="bundle,non-implementing", verdict="pass", rnd="1"):
    return (f"REVIEW work={work} tier={tier} reviewer={reviewer} model={model} "
            f"independence={independence} verdict={verdict} round={rnd}")


def _journal(root, *lines, name="2026-07-04.md"):
    d = root / JOURNAL
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text("\n".join(lines) + "\n", encoding="utf-8")


def _archived_plan(root, name, body):
    d = root / ARCHIVE
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(body, encoding="utf-8")


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


# --- fenced quotations ignored ---

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
    assert "active Tier 2+ plan(s)" in r.stdout
