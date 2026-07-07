import json
import os
import subprocess
import sys
from pathlib import Path

KENNI = ["Kenni", "KenniNext", "Seb", "Signal", "SvelteKit", "user_id=1", "surface:ios"]


def _render(render, tmp_path, repo="", **mods):
    m = {"github_issues": True, "feature_registry": True}
    m.update(mods)
    data = {"project_name": "d", "modules": m}
    if repo:
        data["github_repo"] = repo
    return render(tmp_path, data)


def _run(out: Path, path=None, prepend=None):
    env = dict(os.environ)
    if path is not None:
        env["PATH"] = path
    elif prepend:
        env["PATH"] = f"{prepend}{os.pathsep}" + env["PATH"]
    return subprocess.run(
        [sys.executable, str(out / "scripts/process/check_issues.py"), str(out)],
        capture_output=True, text=True, env=env,
    )


def _story(out: Path, issue=None, status="proposed", sid="STORY-0001"):
    d = {"id": sid, "title": "t", "story": "s", "status": status,
         "acceptance": [{"text": "a"}], "tests": []}
    if issue is not None:
        d["issue"] = issue
    reg = out / "docs/process/feature-registry"
    reg.mkdir(parents=True, exist_ok=True)
    (reg / f"{sid}.json").write_text(json.dumps(d))


def test_valid_bare(render, tmp_path):
    out = _render(render, tmp_path)
    _story(out, issue="#412")
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_valid_crossrepo(render, tmp_path):
    out = _render(render, tmp_path)
    _story(out, issue="octo/billing#77")
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_valid_url(render, tmp_path):
    out = _render(render, tmp_path)
    _story(out, issue="https://github.com/octo/api/issues/412")
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_malformed_number_only(render, tmp_path):
    out = _render(render, tmp_path)
    _story(out, issue="412")
    r = _run(out)
    assert r.returncode == 1
    assert "malformed" in r.stdout


def test_malformed_hash_only(render, tmp_path):
    out = _render(render, tmp_path)
    _story(out, issue="#")
    r = _run(out)
    assert r.returncode == 1
    assert "malformed" in r.stdout  # fails for the right reason, not by accident


def test_malformed_crossrepo_no_number(render, tmp_path):
    out = _render(render, tmp_path)
    _story(out, issue="octo/billing#")
    r = _run(out)
    assert r.returncode == 1
    assert "malformed" in r.stdout


def test_malformed_non_github_url(render, tmp_path):
    out = _render(render, tmp_path)
    _story(out, issue="https://example.com/octo/api/issues/1")
    r = _run(out)
    assert r.returncode == 1
    assert "malformed" in r.stdout


def test_issue_non_string_is_hard(render, tmp_path):
    out = _render(render, tmp_path)
    _story(out, issue=412)
    r = _run(out)
    assert r.returncode == 1
    assert "string" in r.stdout


def test_no_issue_ok(render, tmp_path):
    out = _render(render, tmp_path)
    _story(out, status="proposed")  # no issue field
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_tracked_without_issue_notes(render, tmp_path):
    out = _render(render, tmp_path)
    _story(out, status="in-progress")  # no issue field
    r = _run(out)
    assert r.returncode == 0, r.stdout
    assert "no issue link" in r.stdout


def test_done_without_issue_is_hard(render, tmp_path):
    # C: a finished story must trace to an issue (was soft, now hard)
    out = _render(render, tmp_path)
    _story(out, status="done")  # no issue field
    r = _run(out)
    assert r.returncode == 1
    assert "status 'done' but no issue link" in r.stdout


def test_in_progress_without_issue_still_soft(render, tmp_path):
    # C: in-progress stays soft — its issue may still be forthcoming
    out = _render(render, tmp_path)
    _story(out, status="in-progress")
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_bad_json_skipped(render, tmp_path):
    out = _render(render, tmp_path)
    reg = out / "docs/process/feature-registry"
    reg.mkdir(parents=True, exist_ok=True)
    (reg / "STORY-0002.json").write_text("{not json")
    r = _run(out)
    assert r.returncode == 0, r.stdout  # registry gate owns JSON validity


def test_no_stories_note(render, tmp_path):
    out = _render(render, tmp_path, feature_registry=False)  # no registry dir
    r = _run(out)
    assert r.returncode == 0, r.stdout
    assert "no stories" in r.stdout


def _plan(out: Path, name: str, body: str, archived: bool = False):
    d = out / ".process-work" / "plans"
    if archived:
        d = d / "archive"
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(body)


def test_active_tier2_plan_without_issue_hard(render, tmp_path):
    out = _render(render, tmp_path)
    _plan(out, "2026-07-04-feature.md", "# Plan\n\ntier: 2\n")
    r = _run(out)
    assert r.returncode == 1
    assert "issue-before-code" in r.stdout


def test_active_tier2_plan_with_issue_clean(render, tmp_path):
    out = _render(render, tmp_path)
    _plan(out, "2026-07-04-feature.md", "# Plan\n\ntier: 2\nissue: #7\n")
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_active_tier2_plan_malformed_issue_hard(render, tmp_path):
    out = _render(render, tmp_path)
    _plan(out, "2026-07-04-feature.md", "tier: 2\nissue: 7\n")  # bare number, invalid
    r = _run(out)
    assert r.returncode == 1
    assert "malformed issue ref" in r.stdout


def test_active_plan_issue_waived_clears(render, tmp_path):
    out = _render(render, tmp_path)
    _plan(out, "2026-07-04-feature.md",
          "tier: 2\nissue-waived: spike, will file the issue if it graduates\n")
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_active_tier1_plan_not_enforced(render, tmp_path):
    out = _render(render, tmp_path)
    _plan(out, "2026-07-04-feature.md", "tier: 1\n")  # below the threshold
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_plan_without_tier_not_enforced(render, tmp_path):
    out = _render(render, tmp_path)
    _plan(out, "2026-07-04-feature.md", "# Plan\n\nNo tier declared.\n")
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_fenced_tier_in_plan_ignored(render, tmp_path):
    # a tier: inside a fenced example is a quotation, not a declaration
    out = _render(render, tmp_path)
    _plan(out, "2026-07-04-feature.md", "# Plan\n\n```\ntier: 2\n```\n")
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_archived_tier2_plan_not_issue_checked(render, tmp_path):
    # issue-before-code is a start-of-work rule: archived (merged) plans are the
    # review gate's business, not this one's
    out = _render(render, tmp_path)
    _plan(out, "2026-07-04-feature.md", "tier: 2\n", archived=True)
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_active_design_doc_exempt_from_issue_check(render, tmp_path):
    # a design-*.md carries a tier for routing but is a decision artifact, not a
    # unit of shippable work — issue-before-code does not apply (audit coverage:
    # the design- prefix skip had no regression test)
    out = _render(render, tmp_path)
    _plan(out, "design-2026-07-04-spine.md", "# Design\n\ntier: 3\n")
    r = _run(out)
    assert r.returncode == 0, r.stdout
    assert "issue-before-code" not in r.stdout


def test_bulleted_tier_still_enforced(render, tmp_path):
    # F1 guard: a bulleted `- tier: 2` must not silently escape enforcement
    out = _render(render, tmp_path)
    _plan(out, "2026-07-04-feature.md", "# Plan\n\n- tier: 2\n")
    r = _run(out)
    assert r.returncode == 1 and "issue-before-code" in r.stdout


def test_bold_tier_still_enforced(render, tmp_path):
    out = _render(render, tmp_path)
    _plan(out, "2026-07-04-feature.md", "**tier:** 3\n")
    r = _run(out)
    assert r.returncode == 1 and "issue-before-code" in r.stdout


def test_annotated_issue_accepted(render, tmp_path):
    # F2 guard: a trailing note after the ref must not false-red
    out = _render(render, tmp_path)
    _plan(out, "2026-07-04-feature.md", "tier: 2\nissue: #7 (tracking the rollout)\n")
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_bulleted_issue_accepted(render, tmp_path):
    out = _render(render, tmp_path)
    _plan(out, "2026-07-04-feature.md", "- tier: 2\n- issue: octo/api#7\n")
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_plan_enforced_even_without_feature_registry(render, tmp_path):
    out = _render(render, tmp_path, feature_registry=False)
    _plan(out, "2026-07-04-feature.md", "tier: 3\n")
    r = _run(out)
    assert r.returncode == 1
    assert "issue-before-code" in r.stdout


def test_feature_registry_doc_has_dor_dod(render, tmp_path):
    out = _render(render, tmp_path)
    t = (out / "docs/process/modules/feature-registry.md").read_text()
    assert "## Definition of Ready / Done" in t
    assert "Ready to start" in t and "Done:" in t


def test_module_doc_names_issue_before_code(render, tmp_path):
    out = _render(render, tmp_path)
    t = (out / "docs/process/modules/github-issues.md").read_text()
    assert "## Issue before code" in t
    assert "issue-waived" in t
    assert "not gated" in t  # the claim workflow is convention, honestly labeled


def _stub_gh(bindir: Path, code: int, stdout: str = ""):
    bindir.mkdir(parents=True, exist_ok=True)
    p = bindir / "gh"
    p.write_text(f'#!/bin/sh\nprintf "%s" "{stdout}"\nexit {code}\n')
    p.chmod(0o755)


def _stub_gh_capture(bindir: Path, argfile: Path, code: int = 0):
    bindir.mkdir(parents=True, exist_ok=True)
    p = bindir / "gh"
    p.write_text(f'#!/bin/sh\nprintf "%s" "$*" > "{argfile}"\nexit {code}\n')
    p.chmod(0o755)


def test_existence_gh_absent_is_soft(render, tmp_path):
    # must-not-hard-fail guard: gh not on PATH -> note, exit 0
    out = _render(render, tmp_path, repo="octo/api")
    _story(out, issue="#412")
    empty = tmp_path / "empty"
    empty.mkdir()
    r = _run(out, path=str(empty))
    assert r.returncode == 0, r.stdout
    assert "gh not on PATH" in r.stdout


def test_existence_ok_no_note(render, tmp_path):
    out = _render(render, tmp_path, repo="octo/api")
    _story(out, issue="#412")
    bindir = tmp_path / "bin"
    _stub_gh(bindir, 0)
    r = _run(out, prepend=str(bindir))
    assert r.returncode == 0, r.stdout
    assert "could not confirm" not in r.stdout


def test_existence_404_is_soft(render, tmp_path):
    # must-not-hard-fail guard: a non-zero gh (404 / not visible) -> note, exit 0
    out = _render(render, tmp_path, repo="octo/api")
    _story(out, issue="#412")
    bindir = tmp_path / "bin"
    _stub_gh(bindir, 1)
    r = _run(out, prepend=str(bindir))
    assert r.returncode == 0, r.stdout
    assert "could not confirm" in r.stdout


def test_existence_forwards_configured_repo(render, tmp_path):
    out = _render(render, tmp_path, repo="octo/api")
    _story(out, issue="#412")
    bindir = tmp_path / "bin"
    argfile = out / "gh-args.txt"
    _stub_gh_capture(bindir, argfile, code=0)
    r = _run(out, prepend=str(bindir))
    assert r.returncode == 0, r.stdout
    args = argfile.read_text()
    assert "--repo octo/api" in args
    assert "412" in args


def test_existence_bare_without_repo_notes(render, tmp_path):
    out = _render(render, tmp_path)  # no github_repo configured
    _story(out, issue="#412")
    bindir = tmp_path / "bin"
    _stub_gh(bindir, 0)
    r = _run(out, prepend=str(bindir))
    assert r.returncode == 0, r.stdout
    assert "no github_repo configured" in r.stdout


def test_existence_crossrepo_uses_own_repo(render, tmp_path):
    out = _render(render, tmp_path)  # no default repo, ref carries its own
    _story(out, issue="octo/billing#77")
    bindir = tmp_path / "bin"
    argfile = out / "gh-args.txt"
    _stub_gh_capture(bindir, argfile, code=0)
    r = _run(out, prepend=str(bindir))
    assert r.returncode == 0, r.stdout
    assert "--repo octo/billing" in argfile.read_text()


def _runner_list(out: Path):
    return subprocess.run(
        [sys.executable, str(out / "scripts/process/gate_runner.py"), "--list"],
        cwd=out, capture_output=True, text=True,
    )


def test_runner_lists_issues_when_on(render, tmp_path):
    out = _render(render, tmp_path)
    r = _runner_list(out)
    assert r.returncode == 0, r.stderr
    assert "github-issues" in r.stdout


def test_runner_skips_issues_when_off(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    r = _runner_list(out)
    assert r.returncode == 0, r.stderr
    assert "github-issues" not in r.stdout


def test_artifacts_present_when_on(render, tmp_path):
    out = _render(render, tmp_path)
    assert (out / ".github/ISSUE_TEMPLATE/feature.md").is_file()
    assert (out / ".github/ISSUE_TEMPLATE/bug.md").is_file()
    assert (out / "scripts/process/new_issue.sh").is_file()
    assert (out / "docs/process/modules/github-issues.md").is_file()


def test_artifacts_absent_when_off(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    assert not (out / ".github/ISSUE_TEMPLATE/feature.md").exists()
    assert not (out / "scripts/process/new_issue.sh").exists()
    assert not (out / "docs/process/modules/github-issues.md").exists()


def test_artifacts_neutral(render, tmp_path):
    out = _render(render, tmp_path)
    for rel in [
        ".github/ISSUE_TEMPLATE/feature.md",
        ".github/ISSUE_TEMPLATE/bug.md",
        "docs/process/modules/github-issues.md",
        "scripts/process/new_issue.sh",
    ]:
        text = (out / rel).read_text()
        for k in KENNI:
            assert k not in text, f"{k} leaked in {rel}"


def test_feature_template_has_ears_and_story(render, tmp_path):
    out = _render(render, tmp_path)
    t = (out / ".github/ISSUE_TEMPLATE/feature.md").read_text()
    assert "User story" in t
    assert "shall" in t  # EARS phrasing
    assert "<role>" in t


def test_seed_script_strips_frontmatter(render, tmp_path):
    out = _render(render, tmp_path)
    r = subprocess.run(
        ["bash", str(out / "scripts/process/new_issue.sh"), "feature"],
        cwd=out, capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    body_path = Path(r.stdout.strip())
    assert body_path.is_file()
    body = body_path.read_text()
    assert "User story" in body
    assert "labels:" not in body  # YAML frontmatter removed
    assert not body.lstrip().startswith("---")


def test_docdrift_resolves_module_doc_refs(render, tmp_path):
    out = render(
        tmp_path,
        {"project_name": "d", "modules": {"doc_drift_gate": True, "github_issues": True}},
    )
    r = subprocess.run(
        [sys.executable, str(out / "scripts/process/check_doc_drift.py"), str(out)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stdout  # module-doc refs resolve; feature_registry off


# --- review/audit reports (SP32) ---

def _report(out: Path, name: str, body: str):
    d = out / ".process-work" / "reviews"
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(body, encoding="utf-8")


VALID_REPORT = (
    "review: sp-test\n"
    "work: #42\n"
    "issue: #57\n\n"
    "## Prompt\n\nthe prompt\n\n"
    "## Result\n\npass\n\n"
    "## Findings\n\n"
    "FINDING sev=minor action=fix issue=- tightened a message\n"
)


def test_no_reports_dir_is_silent(render, tmp_path):
    # binding is opt-in by artifact existence — no perpetual "no audits yet" noise
    out = _render(render, tmp_path)
    r = _run(out)
    assert r.returncode == 0, r.stdout
    assert "review" not in r.stdout.lower() or "reviews/" not in r.stdout


def test_valid_published_report_ok(render, tmp_path):
    out = _render(render, tmp_path)
    _report(out, "2026-07-05-sp-test.md", VALID_REPORT)
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_report_without_header_hard(render, tmp_path):
    out = _render(render, tmp_path)
    _report(out, "2026-07-05-x.md", "# Just some notes\n\nno header here\n")
    r = _run(out)
    assert r.returncode == 1
    assert "no 'review:' or 'audit:' header" in r.stdout


def test_unpublished_report_without_waiver_hard(render, tmp_path):
    out = _render(render, tmp_path)
    _report(out, "2026-07-05-x.md", "review: x\nwork: #1\n\n## Result\n\npass\n")
    r = _run(out)
    assert r.returncode == 1
    assert "invisible review" in r.stdout


def test_publish_waived_clears(render, tmp_path):
    out = _render(render, tmp_path)
    _report(out, "2026-07-05-x.md",
            "review: x\nwork: #1\npublish-waived: offline repo, no issue tracker\n\n"
            "## Result\n\npass\n")
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_report_malformed_issue_ref_hard(render, tmp_path):
    out = _render(render, tmp_path)
    _report(out, "2026-07-05-x.md", "review: x\nissue: 57\n\n## Result\n\npass\n")
    r = _run(out)
    assert r.returncode == 1
    assert "malformed issue ref" in r.stdout


def test_followup_finding_without_issue_hard(render, tmp_path):
    out = _render(render, tmp_path)
    _report(out, "2026-07-05-x.md", VALID_REPORT +
            "FINDING sev=major action=follow-up issue=- needs work later\n")
    r = _run(out)
    assert r.returncode == 1
    assert "follow-up finding without an issue" in r.stdout


def test_followup_finding_with_issue_ok(render, tmp_path):
    out = _render(render, tmp_path)
    _report(out, "2026-07-05-x.md", VALID_REPORT +
            "FINDING sev=major action=follow-up issue=#61 tracked follow-up\n")
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_malformed_finding_sev_hard(render, tmp_path):
    out = _render(render, tmp_path)
    _report(out, "2026-07-05-x.md", VALID_REPORT +
            "FINDING sev=huge action=fix issue=- bad severity\n")
    r = _run(out)
    assert r.returncode == 1
    assert "malformed FINDING" in r.stdout


def test_finding_without_title_hard(render, tmp_path):
    out = _render(render, tmp_path)
    _report(out, "2026-07-05-x.md", VALID_REPORT +
            "FINDING sev=minor action=fix issue=-\n")
    r = _run(out)
    assert r.returncode == 1
    assert "no title" in r.stdout


def test_prose_starting_with_finding_ignored(render, tmp_path):
    # the telemetry GRADE lesson applied: first token after FINDING must be
    # key=value, else it is prose
    out = _render(render, tmp_path)
    _report(out, "2026-07-05-x.md", VALID_REPORT +
            "\nFINDING one was bad, severity=high overall.\n")
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_fenced_finding_ignored(render, tmp_path):
    out = _render(render, tmp_path)
    _report(out, "2026-07-05-x.md", VALID_REPORT +
            "\n```\nFINDING sev=bogus action=nope issue=- quoted example\n```\n"
            "\n~~~\nFINDING sev=bogus action=nope issue=- tilde quoted\n~~~\n")
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_blocker_accepted_is_soft_note(render, tmp_path):
    out = _render(render, tmp_path)
    _report(out, "2026-07-05-x.md", VALID_REPORT +
            "FINDING sev=blocker action=accept issue=- accepted with cause\n")
    r = _run(out)
    assert r.returncode == 0, r.stdout
    assert "blocker finding consciously accepted" in r.stdout


def test_campaign_published_without_parent_hard(render, tmp_path):
    out = _render(render, tmp_path)
    _report(out, "2026-07-05-x.md",
            "review: x\ncampaign: round-1\nissue: #57\n\n## Result\n\npass\n")
    r = _run(out)
    assert r.returncode == 1
    assert "campaign" in r.stdout and "campaign-issue" in r.stdout


def test_campaign_split_across_parents_hard(render, tmp_path):
    out = _render(render, tmp_path)
    _report(out, "2026-07-05-a.md",
            "review: a\ncampaign: round-1\nissue: #57\ncampaign-issue: #50\n\n## Result\n\npass\n")
    _report(out, "2026-07-05-b.md",
            "review: b\ncampaign: round-1\nissue: #58\ncampaign-issue: #51\n\n## Result\n\npass\n")
    r = _run(out)
    assert r.returncode == 1
    assert "split across parent issues" in r.stdout


def test_campaign_consistent_ok(render, tmp_path):
    out = _render(render, tmp_path)
    _report(out, "2026-07-05-a.md",
            "review: a\ncampaign: round-1\nissue: #57\ncampaign-issue: #50\n\n## Result\n\npass\n")
    _report(out, "2026-07-05-b.md",
            "audit: b\ncampaign: round-1\nissue: #58\ncampaign-issue: #50\n\n## Result\n\npass\n")
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_report_non_utf8_hard(render, tmp_path):
    out = _render(render, tmp_path)
    d = out / ".process-work" / "reviews"
    d.mkdir(parents=True, exist_ok=True)
    (d / "2026-07-05-x.md").write_bytes(b"review: x\n\xff\xfe\n")
    r = _run(out)
    assert r.returncode == 1
    assert "not valid UTF-8" in r.stdout


def test_publish_tool_present_when_on_absent_when_off(render, tmp_path):
    on = _render(render, tmp_path / "on")
    assert (on / "scripts/process/publish_review.sh").is_file()
    off = render(tmp_path / "off", {"project_name": "d"})
    assert not (off / "scripts/process/publish_review.sh").exists()


def test_publish_tool_and_doc_neutral(render, tmp_path):
    out = _render(render, tmp_path)
    for rel in ["scripts/process/publish_review.sh",
                "docs/process/modules/github-issues.md"]:
        text = (out / rel).read_text()
        for k in KENNI:
            assert k not in text, f"{k} leaked in {rel}"


def test_module_doc_names_review_visibility(render, tmp_path):
    out = _render(render, tmp_path)
    t = (out / "docs/process/modules/github-issues.md").read_text()
    assert "## Review and audit visibility" in t
    assert "FINDING sev=" in t
    assert "publish_review.sh" in t
    assert "campaign" in t


def test_docs_wire_report_duty(render, tmp_path):
    out = _render(render, tmp_path)
    vi = (out / "docs/process/verification-independence.md").read_text()
    assert "report file" in vi and ".process-work/reviews/" in vi
    wf = (out / "docs/process/workflow.md").read_text()
    review = wf.split("## Review")[1].split("## Quick")[0]
    assert ".process-work/reviews/" in review
    jsp = (out / "docs/process/journal-state-plans.md").read_text()
    assert "## Review reports" in jsp


# --- discovered work: form + trail (SP32 addendum) ---

def test_finding_template_present_with_ears_and_origin(render, tmp_path):
    out = _render(render, tmp_path)
    p = out / ".github/ISSUE_TEMPLATE/finding.md"
    assert p.is_file()
    t = p.read_text()
    assert "## Origin" in t
    assert "Discovered during" in t
    assert "EARS" in t and "shall" in t          # the normal form, not prose
    assert "comment on the origin issue" in t.lower() or "comment on" in t.lower()


def test_bug_template_gains_origin_section(render, tmp_path):
    out = _render(render, tmp_path)
    t = (out / ".github/ISSUE_TEMPLATE/bug.md").read_text()
    assert "## Origin" in t
    assert "Discovered during" in t
    assert "EARS" in t                            # form kept


def test_finding_template_seedable(render, tmp_path):
    # new_issue.sh must serve the new template like the others
    out = _render(render, tmp_path)
    r = subprocess.run(
        ["bash", str(out / "scripts/process/new_issue.sh"), "finding"],
        cwd=out, capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    body = Path(r.stdout.strip()).read_text()
    assert "## Origin" in body and "labels:" not in body


def test_finding_template_neutral(render, tmp_path):
    out = _render(render, tmp_path)
    t = (out / ".github/ISSUE_TEMPLATE/finding.md").read_text()
    for k in KENNI:
        assert k not in t, f"{k} leaked in finding.md"


def test_module_doc_names_discovered_work_form(render, tmp_path):
    out = _render(render, tmp_path)
    t = (out / "docs/process/modules/github-issues.md").read_text()
    assert "## Discovered work keeps the form and the trail" in t
    assert "normal work and gets the normal form" in t
    assert "comment on" in t and "Origin" in t


def test_inbox_doc_routes_through_templates(render, tmp_path):
    out = _render(render, tmp_path)
    t = (out / "docs/process/journal-state-plans.md").read_text()
    assert "normal form" in t
    assert "Origin" in t


def test_publish_tool_hints_finding_form(render, tmp_path):
    out = _render(render, tmp_path)
    t = (out / "scripts/process/publish_review.sh").read_text()
    assert "new_issue.sh finding" in t
    assert "comment on the origin issue" in t
