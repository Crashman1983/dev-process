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


def test_feature_registry_doc_states_worklog_split(render, tmp_path):
    # lean pass: DoR/DoD live in definition-of-ready-and-done.md and the
    # work log in GitHub Issues — the inventory doc states the split
    out = _render(render, tmp_path)
    t = (out / "docs/process/modules/feature-registry.md").read_text()
    assert "Inventory, not work log" in t
    assert "GitHub" in t


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
    assert (out / "docs/process/modules/github-issues.md").is_file()


def test_artifacts_absent_when_off(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    assert not (out / ".github/ISSUE_TEMPLATE/feature.md").exists()
    assert not (out / "docs/process/modules/github-issues.md").exists()


def test_artifacts_neutral(render, tmp_path):
    out = _render(render, tmp_path)
    for rel in [
        ".github/ISSUE_TEMPLATE/feature.md",
        ".github/ISSUE_TEMPLATE/bug.md",
        "docs/process/modules/github-issues.md",
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
    assert "review" not in r.stdout.lower()  # F8: the old disjunct was near-vacuous


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


def test_a_finding_names_its_reviewer_anywhere_among_its_keys(render, tmp_path):
    """#247: `by=` is a key like the others — parsed wherever it stands among them,
    never swallowed into the title, refused when it is no family word."""
    import importlib.util
    out = _render(render, tmp_path)
    spec = importlib.util.spec_from_file_location("ci_by", out / "scripts/process/check_issues.py")
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    rows = gate.report_findings("FINDING by=codex sev=major action=fix issue=- guard read twice\n"
                                "FINDING sev=minor action=fix issue=- kind=process by=claude late note\n"
                                "FINDING sev=minor action=fix issue=- no reviewer\n")
    assert [(f["by"] if "by" in f else None, f["title"]) for f, _e, _l in rows] == [
        ("codex", "guard read twice"), ("claude", "late note"), (None, "no reviewer")]
    # a title that starts with `by=…` but names no family stays a title: older reports stay valid
    (fields, err, _line), = gate.report_findings("FINDING sev=minor action=accept issue=- by=Reference: aliasing\n")
    assert err is None and "by" not in fields and fields["title"] == "by=Reference: aliasing"
    # but a bad `by=` with keys after it is an error, never a hiding place for them
    (fields, err, _line), = gate.report_findings("FINDING sev=major action=fix issue=- by=Codex kind=bogus Title\n")
    assert fields is None and "no reviewer family" in err
    # only the token right after `by=` decides: a key later in the title is title text
    (fields, err, _line), = gate.report_findings(
        "FINDING sev=minor action=accept issue=- by=Reference: aliasing of issue=42 in the guard\n")
    assert err is None and fields["title"].startswith("by=Reference:")
    _report(out, "2026-07-05-x.md", VALID_REPORT +
            "FINDING sev=minor action=fix issue=- by=codex by=claude twice\n")
    r = _run(out)
    assert r.returncode == 1 and "duplicate key 'by'" in r.stdout


def test_prose_starting_with_finding_ignored(render, tmp_path):
    # prose is not linted: the first token after FINDING must be
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


def test_reports_skip_what_git_ignores(render, tmp_path):
    # #186: the reviewer's bundle lies next to the reports by design; git
    # ignores it, so it is no report — a header-less file git sees still fails
    out = _render(render, tmp_path)
    subprocess.run(["git", "init", "-q", str(out)], check=True)
    _report(out, "2026-10-08-x.bundle.md", "# Review bundle\n\nthe diff\n")
    r = _run(out)
    assert r.returncode == 0, r.stdout
    _report(out, "2026-10-08-notes.md", "# Just some notes\n\nno header here\n")
    r = _run(out)
    assert r.returncode == 1
    assert "2026-10-08-notes.md: no 'review:' or 'audit:' header" in r.stdout
    assert "bundle.md" not in r.stdout


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


def test_module_doc_makes_class_required_on_blockers_and_majors(render, tmp_path):
    """#297 AC-6: the doc states the duty the gate enforces, and what `class=` means."""
    out = _render(render, tmp_path)
    t = " ".join((out / "docs/process/modules/github-issues.md").read_text().split())
    assert "`class` is **required on every blocker and major** and says what could have caught the finding" in t
    assert "not what kind of failure it is" in t
    assert "[class=<mechanical|testable|judgment>] [rule=<check>]" in t
    assert "round: 2" in t and "class=mechanical rule=placeholder-scan" in t
    assert "A blocker or major finding the branch adds without `class=` or `at=` fails" in t
    assert "compared without its `issue=`, `class=`, `rule=` and `at=` fields where the old line has none" in t
    # v2.78: the place is owed like the class
    assert "`at` is **required on every blocker and major** too" in t
    assert "[at=<path>:<line>|<path>:<first>-<last>|<path>|->] <title>" in t and "at=docs/intro.md:12" in t


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
    assert "--template finding.md" in t
    assert "comment on the origin issue" in t


# --- SP32 review findings: header scoping, bullets, edges ---

def test_quoted_issue_in_prose_is_not_publication(render, tmp_path):
    # F1 (MAJOR false-green): a prose 'issue: #61 ...' in Result must not make
    # an unpublished report count as published — headers live before the
    # first ## heading only
    out = _render(render, tmp_path)
    _report(out, "2026-07-05-x.md",
            "review: x\nwork: #1\n\n## Result\n\n"
            "issue: #61 covers the flaky test too.\n")
    r = _run(out)
    assert r.returncode == 1
    assert "invisible review" in r.stdout


def test_prose_campaign_sentence_not_a_header(render, tmp_path):
    # F5 (false-red): 'campaign: overall ...' prose in Result must not trigger
    # the campaign-issue requirement
    out = _render(render, tmp_path)
    _report(out, "2026-07-05-x.md",
            "review: x\nissue: #57\n\n## Result\n\n"
            "campaign: overall the round went well.\n")
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_bulleted_finding_still_linted(render, tmp_path):
    # F2 (MAJOR false-green): '- FINDING ...' is the natural Markdown form and
    # must not escape the lint — same _LEAD lesson as plan tier lines
    out = _render(render, tmp_path)
    _report(out, "2026-07-05-x.md", VALID_REPORT +
            "- FINDING sev=major action=follow-up issue=- forgotten follow-up\n")
    r = _run(out)
    assert r.returncode == 1
    assert "follow-up finding without an issue" in r.stdout


def test_bulleted_malformed_finding_hard(render, tmp_path):
    out = _render(render, tmp_path)
    _report(out, "2026-07-05-x.md", VALID_REPORT +
            "- FINDING sev=bogus action=nope issue=- malformed too\n")
    r = _run(out)
    assert r.returncode == 1
    assert "malformed FINDING" in r.stdout


def test_title_with_equals_token_is_valid(render, tmp_path):
    # F6 (false-red): a title starting with a k=v-shaped token that is not a
    # known key belongs to the title — 'user_id=1 hardcoded' is legitimate
    out = _render(render, tmp_path)
    _report(out, "2026-07-05-x.md", VALID_REPORT +
            "FINDING sev=major action=fix issue=- USER_ID=1 hardcoded in deps\n")
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_unclosed_fence_notes(render, tmp_path):
    # F7: an unclosed fence swallows the rest of the file — disclose it
    out = _render(render, tmp_path)
    _report(out, "2026-07-05-x.md", VALID_REPORT +
            "\n```\nFINDING sev=major action=follow-up issue=- swallowed\n")
    r = _run(out)
    assert r.returncode == 0, r.stdout
    assert "unclosed fence" in r.stdout


# --- SP33 gate hardening (audit findings) ---

def test_h3_first_report_header_bypass_closed(render, tmp_path):
    # audit: header split on \n## let an ###-first report treat the whole file
    # as header — a quoted body issue: counted as publication (false-green)
    out = _render(render, tmp_path)
    _report(out, "2026-07-05-x.md",
            "review: x\nwork: #1\n\n### Result\n\nissue: #123 covers the flaky test\n")
    r = _run(out)
    assert r.returncode == 1
    assert "invisible review" in r.stdout


def test_h4_heading_header_bypass_closed(render, tmp_path):
    out = _render(render, tmp_path)
    _report(out, "2026-07-05-x.md",
            "review: x\nwork: #1\n\n#### Deep\n\nissue: #123 in prose\n")
    r = _run(out)
    assert r.returncode == 1
    assert "invisible review" in r.stdout


def test_same_campaign_issue_two_ref_forms_not_split(render, tmp_path):
    # audit: #5 and octo/api#5 (the configured repo) are the same issue but were
    # string-compared and reported as a split campaign (false-red)
    out = _render(render, tmp_path, repo="octo/api")
    _report(out, "2026-07-05-a.md",
            "review: a\ncampaign: r1\nissue: #57\ncampaign-issue: #5\n\n## Result\n\npass\n")
    _report(out, "2026-07-05-b.md",
            "audit: b\ncampaign: r1\nissue: #58\ncampaign-issue: octo/api#5\n\n## Result\n\npass\n")
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_setext_heading_header_bypass_closed(render, tmp_path):
    # SP33 review MINOR: a setext-underlined section (Result\n======) did not
    # terminate the header block, so a quoted body issue: counted as publication
    out = _render(render, tmp_path)
    _report(out, "2026-07-05-x.md",
            "review: x\nwork: #1\n\nResult\n======\n\nissue: #123 covers the flaky test\n")
    r = _run(out)
    assert r.returncode == 1
    assert "invisible review" in r.stdout


def test_no_space_heading_header_bypass_closed(render, tmp_path):
    # a genuine no-space '##Result' (not a real ATX heading) must also not let
    # the body issue: count — the contiguous-header rule closes it
    out = _render(render, tmp_path)
    _report(out, "2026-07-05-y.md",
            "review: y\nwork: #1\n\n##Result\n\nissue: #123 in prose\n")
    r = _run(out)
    assert r.returncode == 1
    assert "invisible review" in r.stdout


# --- SP34 flow closure (#16) ---

def test_done_story_issue_waived_is_soft(render, tmp_path):
    # tracker-less escape: a done story with issue_waived: <reason> is soft, so
    # a project without a tracker is not permanently stuck below done
    out = _render(render, tmp_path)
    reg = out / "docs/process/feature-registry"
    reg.mkdir(parents=True, exist_ok=True)
    d = {"id": "STORY-0001", "title": "t", "story": "s", "status": "done",
         "acceptance": [{"text": "a"}], "tests": [],
         "issue_waived": "solo project, no issue tracker"}
    (reg / "STORY-0001.json").write_text(json.dumps(d))
    r = _run(out)
    assert r.returncode == 0, r.stdout
    assert "issue waived" in r.stdout


def test_done_story_empty_waiver_still_hard(render, tmp_path):
    # an empty reason does not waive
    out = _render(render, tmp_path)
    reg = out / "docs/process/feature-registry"
    reg.mkdir(parents=True, exist_ok=True)
    d = {"id": "STORY-0001", "title": "t", "story": "s", "status": "done",
         "acceptance": [{"text": "a"}], "tests": [], "issue_waived": "  "}
    (reg / "STORY-0001.json").write_text(json.dumps(d))
    r = _run(out)
    assert r.returncode == 1
    assert "status 'done' but no issue link" in r.stdout


def test_followup_finding_in_publish_waived_report_ok(render, tmp_path):
    # off-tracker: a publish-waived report's follow-up findings can't carry an
    # issue ref; the waiver covers them (no more dishonest accept-downgrades)
    out = _render(render, tmp_path)
    _report(out, "2026-07-07-x.md",
            "review: x\nwork: #1\npublish-waived: offline repo, no tracker\n\n"
            "## Result\n\npass\n\n## Findings\n"
            "FINDING sev=major action=follow-up issue=- track this later\n")
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_followup_finding_published_report_still_needs_issue(render, tmp_path):
    # the waiver is the only escape — a published report's follow-up still binds
    out = _render(render, tmp_path)
    _report(out, "2026-07-07-y.md",
            "review: y\nwork: #1\nissue: #57\n\n## Result\n\npass\n\n## Findings\n"
            "FINDING sev=major action=follow-up issue=- track this later\n")
    r = _run(out)
    assert r.returncode == 1
    assert "follow-up finding without an issue" in r.stdout


def test_followup_in_published_but_waived_report_still_binds(render, tmp_path):
    # SP34-review F2: publish-waived is the off-tracker escape; a report ALSO
    # published (has issue:) is on-tracker, so its follow-ups still bind
    out = _render(render, tmp_path)
    _report(out, "2026-07-07-z.md",
            "review: z\nwork: #1\nissue: #57\npublish-waived: contradictory\n\n"
            "## Result\n\npass\n\n## Findings\n"
            "FINDING sev=major action=follow-up issue=- track this\n")
    r = _run(out)
    assert r.returncode == 1
    assert "follow-up finding without an issue" in r.stdout


# --- SP50 audit: fence length-awareness + unreadable plan shapes ------------


def test_quoted_issue_waiver_in_nested_fence_does_not_clear(render, tmp_path):
    # a 3-backtick run inside a 4-backtick fence must not close it — a QUOTED
    # issue-waived: example never waives issue-before-code
    out = _render(render, tmp_path)
    _plan(out, "2026-07-10-widget.md",
          "# Plan\n\ntier: 2\n\n````md\n```\ncode\n```\n"
          "issue-waived: quoted example, not a waiver\n````\n")
    r = _run(out)
    assert r.returncode == 1, r.stdout
    assert "no 'issue:' link" in r.stdout


def test_unreadable_plan_shapes_diagnosed_not_traceback(render, tmp_path):
    # a directory named *.md or a broken symlink yields a spoken diagnosis
    out = _render(render, tmp_path)
    d = out / ".process-work" / "plans"
    d.mkdir(parents=True, exist_ok=True)
    (d / "2026-07-10-dir.md").mkdir()
    (d / "gone.md").symlink_to(out / "does-not-exist")
    r = _run(out)
    assert "Traceback" not in r.stderr
    assert r.returncode == 1 and "could not read" in r.stdout


# --- the findings ratchet: gate= ---------------------------------------------

def test_gate_possible_is_a_soft_note_never_a_block(render, tmp_path):
    out = _render(render, tmp_path)
    _report(out, "2026-07-05-x.md", VALID_REPORT +
            "FINDING sev=major action=fix issue=- gate=possible unpinned dep version\n")
    r = _run(out)
    assert r.returncode == 0, r.stdout
    assert "1 finding(s) marked gate=possible" in r.stdout


def test_gate_judgement_and_named_gate_produce_no_note(render, tmp_path):
    out = _render(render, tmp_path)
    _report(out, "2026-07-05-x.md", VALID_REPORT +
            "FINDING sev=major action=fix issue=- gate=judgement the model is wrong\n"
            "FINDING sev=minor action=fix issue=- gate=lint secret in log\n")
    r = _run(out)
    assert r.returncode == 0, r.stdout
    assert "gate=possible" not in r.stdout


def test_finding_without_gate_stays_valid(render, tmp_path):
    out = _render(render, tmp_path)
    _report(out, "2026-07-05-x.md", VALID_REPORT)
    r = _run(out)
    assert r.returncode == 0, r.stdout
    assert "gate=possible" not in r.stdout


def test_gate_token_after_title_is_not_a_field(render, tmp_path):
    out = _render(render, tmp_path)
    _report(out, "2026-07-05-x.md", VALID_REPORT +
            "FINDING sev=minor action=fix issue=- config gate=possible is a bad key name\n")
    r = _run(out)
    assert r.returncode == 0, r.stdout
    assert "marked gate=possible" not in r.stdout


def test_finding_origin_is_an_optional_enum(render, tmp_path):
    """Downstream blockers split draft=6 / fix=2 / late=2 only by hand — `origin=` records it
    where the finding is written; absent is fine, an unknown value is refused like sev."""
    cases = (("origin=fix guard re-broken", True),
             ("origin=late missed in round 1", True),
             ("no origin given", True),
             ("origin=review not an origin", False))
    for i, (rest, ok) in enumerate(cases):
        line = f"FINDING sev=blocker action=fix issue=- {rest}\n"
        out = _render(render, tmp_path / str(i))
        _report(out, "2026-07-05-x.md", VALID_REPORT + line)
        r = _run(out)
        assert (r.returncode == 0) is ok, (line, r.stdout)
        if not ok:
            assert "origin='review' not in ['draft', 'fix', 'late']" in r.stdout


def test_finding_kind_is_an_optional_enum(render, tmp_path):
    """`kind=` says what sort of defect a finding is (`knowledge-gap` = the author did not know
    something that existed); absent stays valid, an unknown value is a format error like origin=."""
    cases = (("kind=knowledge-gap reinvented the note reader", True),
             ("origin=fix kind=test-gap no regression test", True),
             ("kind=environment CI image differs", True),
             ("no kind given", True),
             ("kind=cause not a kind", False))
    for i, (rest, ok) in enumerate(cases):
        line = f"FINDING sev=blocker action=fix issue=- {rest}\n"
        out = _render(render, tmp_path / str(i))
        _report(out, "2026-07-05-x.md", VALID_REPORT + line)
        r = _run(out)
        assert (r.returncode == 0) is ok, (line, r.stdout)
        if not ok:
            assert ("kind='cause' not in ['environment', 'implementation', 'knowledge-gap', "
                    "'process', 'requirement', 'test-gap']") in r.stdout


# --- issue-before-spec: the influence window needs a readable home -----------

def test_active_spec_without_issue_ref_is_hard(render, tmp_path):
    out = _render(render, tmp_path)
    d = out / "specs/001-widget"
    d.mkdir(parents=True)
    (d / "spec.md").write_text("# Feature\n\nStories.\n")
    r = _run(out)
    assert r.returncode == 1
    assert "issue-before-spec" in r.stdout


def test_active_spec_with_issue_ref_passes(render, tmp_path):
    out = _render(render, tmp_path)
    d = out / "specs/002-widget"
    d.mkdir(parents=True)
    (d / "spec.md").write_text("# Feature\n\nissue: #7\n\nStories.\n")
    r = _run(out)
    assert r.returncode == 0, r.stdout


# --- #297 AC-6: a blocker or major the branch adds says what could have caught it ---

NO_CLASS = "without class="
OLD = "FINDING sev=major action=fix issue=- the old cache is never invalidated\n"


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t",
                           "-c", "commit.gpgsign=false", *args],
                          check=True, capture_output=True, text=True).stdout.strip()


def _branch(out: Path, report: str | None = None) -> Path:
    """main holding the render (and a report, if given), a feature branch with one commit
    off it: the range a finding is new in."""
    if report is not None:
        _report(out, "2026-10-20-old.md", report)
    _git(out, "init", "-q", "-b", "main")
    _git(out, "add", "-A")
    _git(out, "commit", "-qm", "base")
    _git(out, "checkout", "-qb", "feature")
    _git(out, "commit", "-q", "--allow-empty", "-m", "start")
    return out


def test_a_new_report_owes_class_on_blockers_and_majors(render, tmp_path):
    out = _branch(_render(render, tmp_path))
    _report(out, "2026-10-21-new.md", VALID_REPORT + "FINDING sev=major action=fix issue=- guard read twice\n")
    r = _run(out)
    assert r.returncode == 1 and f"2026-10-21-new.md: major finding {NO_CLASS}" in r.stdout \
        and "'guard read twice'" in r.stdout, r.stdout
    _report(out, "2026-10-21-new.md", VALID_REPORT + "FINDING sev=blocker action=fix issue=- lost write\n")
    assert f"blocker finding {NO_CLASS}" in _run(out).stdout
    for line in ("FINDING sev=major action=fix issue=- class=testable rule=mutation at=src/a.py:3 guard read twice\n",
                 "FINDING sev=blocker action=fix issue=- class=judgment at=- lost write\n",
                 "FINDING sev=minor action=fix issue=- a minor needs no class\n"):
        _report(out, "2026-10-21-new.md", VALID_REPORT + line)
        r = _run(out)
        assert r.returncode == 0 and NO_CLASS not in r.stdout, (line, r.stdout)


NO_AT = "without at="


def test_a_new_major_owes_class_and_at(render, tmp_path):
    """v2.78: a blocker or major the branch adds names its place (`at=`) beside its class;
    the message names every missing field."""
    out = _branch(_render(render, tmp_path))
    cases = {"FINDING sev=major action=fix issue=- guard read twice\n": "without class= and at=",
             "FINDING sev=major action=fix issue=- class=judgment guard read twice\n": NO_AT,
             "FINDING sev=blocker action=fix issue=- at=src/a.py:3-9 lost write\n": NO_CLASS}
    for line, want in cases.items():
        _report(out, "2026-10-21-new.md", VALID_REPORT + line)
        r = _run(out)
        assert r.returncode == 1 and want in r.stdout, (line, r.stdout)
    for place in ("-", "src/a.py", "src/a.py:3", "src/a.py:3-3", "docs/my%20file.md:2"):
        _report(out, "2026-10-21-new.md", VALID_REPORT
                + f"FINDING sev=major action=fix issue=- class=judgment at={place} guard read twice\n")
        r = _run(out)
        assert r.returncode == 0 and NO_AT not in r.stdout, (place, r.stdout)


def test_a_minor_owes_no_at(render, tmp_path):
    out = _branch(_render(render, tmp_path))
    _report(out, "2026-10-21-new.md", VALID_REPORT + "FINDING sev=minor action=fix issue=- a minor needs no place\n")
    r = _run(out)
    assert r.returncode == 0 and NO_AT not in r.stdout, r.stdout


def test_an_old_finding_owes_no_at(render, tmp_path):
    out = _branch(_render(render, tmp_path), VALID_REPORT + OLD)
    r = _run(out)
    assert r.returncode == 0 and NO_AT not in r.stdout and NO_CLASS not in r.stdout, r.stdout


def test_backfilling_an_old_finding_keeps_it_old(render, tmp_path):
    """Classifying or placing an old finding on the branch does not make it new (v2.78
    plan review): it owes nothing the fork point did not owe."""
    out = _branch(_render(render, tmp_path), VALID_REPORT + OLD)
    for fields in ("class=judgment ", "at=src/cache.py:12 ", "class=testable rule=ttl at=src/cache.py:12 "):
        _report(out, "2026-10-20-old.md", VALID_REPORT + OLD.replace("issue=- ", f"issue=- {fields}"))
        r = _run(out)
        assert r.returncode == 0 and NO_AT not in r.stdout and NO_CLASS not in r.stdout, (fields, r.stdout)


def test_a_same_title_recurrence_is_new(render, tmp_path):
    """A second finding with an old one's title is new: it does not hide under the old one
    (v2.78 plan review, round 2)."""
    out = _branch(_render(render, tmp_path), VALID_REPORT + OLD)
    again = OLD.replace("issue=- ", "issue=- at=src/other.py:9 ")
    _report(out, "2026-10-20-old.md", VALID_REPORT + OLD + again)
    r = _run(out)
    assert r.returncode == 1 and r.stdout.count("old cache") == 1 and NO_CLASS in r.stdout, r.stdout
    # order does not decide: the recurrence listed above the old line leaves the old one old
    _report(out, "2026-10-20-old.md", VALID_REPORT + again + OLD)
    r = _run(out)
    assert r.returncode == 1 and r.stdout.count("old cache") == 1 and NO_CLASS in r.stdout \
        and "without class= —" in r.stdout, r.stdout  # the recurrence (it has at=) owes class= only
    # an old finding with its own place: a recurrence elsewhere does not match it
    placed = OLD.replace("issue=- ", "issue=- class=judgment at=src/cache.py:12 ")
    out2 = _branch(_render(render, tmp_path / "two"), VALID_REPORT + placed)
    _report(out2, "2026-10-20-old.md", VALID_REPORT + placed.replace("cache.py:12", "other.py:9"))
    r = _run(out2)
    assert r.returncode == 0, r.stdout  # class and at both present: the new one owes nothing more


def test_a_complete_backfill_keeps_its_old_match(render, tmp_path):
    """A backfilled old line that is complete still takes its old match: a recurrence beside
    it with the same title stays new (v2.78 cross-model review, round 1)."""
    out = _branch(_render(render, tmp_path), VALID_REPORT + OLD)
    backfilled = OLD.replace("issue=- ", "issue=- class=judgment at=src/cache.py:12 ")
    again = OLD.replace("issue=- ", "issue=- at=src/other.py:9 ")
    for body in (backfilled + again, again + backfilled):
        _report(out, "2026-10-20-old.md", VALID_REPORT + body)
        r = _run(out)
        assert r.returncode == 1 and r.stdout.count("old cache") == 1 and "without class= —" in r.stdout, r.stdout


def test_old_matching_is_maximal_not_greedy(render, tmp_path):
    """Two backfills that each fit an old line pass in any order of the old lines (v2.78
    cross-model review and refute, round 1)."""
    t = "FINDING sev=major action=fix issue=- {}the cache is stale\n"
    for old in (t.format("") + t.format("class=judgment "), t.format("class=judgment ") + t.format("")):
        out = _branch(_render(render, tmp_path / str(len(old)) / old[30:40].replace(" ", "_")), VALID_REPORT + old)
        _report(out, "2026-10-20-old.md", VALID_REPORT + t.format("class=judgment rule=r ") + t.format("class=mechanical "))
        r = _run(out)
        assert r.returncode == 0, (old, r.stdout)


def test_the_no_range_note_names_both_fields(render, tmp_path):
    out = _render(render, tmp_path)
    _report(out, "2026-10-21-new.md", VALID_REPORT + "FINDING sev=major action=fix issue=- class=judgment guard read twice\n")
    r = _run(out)
    assert r.returncode == 0 and "`class=` and `at=` are not checked" in r.stdout, r.stdout


def test_an_invalid_at_is_malformed(render, tmp_path):
    """An invalid place with a key after it is a malformed field; with none after it the
    token begins an older report's title."""
    out = _render(render, tmp_path)
    for bad in ("src/a.py:0", "src/a.py:5-3", "src/a.py:x", "src/a.py:3-"):
        _report(out, "2026-10-21-new.md", VALID_REPORT
                + f"FINDING sev=minor action=fix issue=- at={bad} class=judgment the title\n")
        r = _run(out)
        assert r.returncode == 1 and "malformed FINDING line" in r.stdout and "at=" in r.stdout, (bad, r.stdout)
        _report(out, "2026-10-21-new.md", VALID_REPORT + f"FINDING sev=minor action=fix issue=- at={bad} the title\n")
        r = _run(out)
        assert "malformed FINDING line" not in r.stdout, (bad, r.stdout)


def test_an_old_report_owes_class_only_on_its_new_lines(render, tmp_path):
    out = _branch(_render(render, tmp_path), VALID_REPORT + OLD)
    r = _run(out)
    assert r.returncode == 0 and NO_CLASS not in r.stdout, r.stdout
    # publishing writes `issue=#N` into the old line: still the same finding
    _report(out, "2026-10-20-old.md", VALID_REPORT + OLD.replace("issue=-", "issue=#61"))
    assert _run(out).returncode == 0
    _report(out, "2026-10-20-old.md", VALID_REPORT + OLD + "- FINDING sev=major action=fix issue=- new on the branch\n")
    r = _run(out)
    assert r.returncode == 1 and "'new on the branch'" in r.stdout and "old cache" not in r.stdout, r.stdout


def test_a_duplicated_old_finding_owes_class_once(render, tmp_path):
    """Old findings are counted, not a set: two identical lines at the fork stay old, a
    third copy the branch adds is new."""
    out = _branch(_render(render, tmp_path), VALID_REPORT + OLD + OLD)
    r = _run(out)
    assert r.returncode == 0 and NO_CLASS not in r.stdout, r.stdout
    _report(out, "2026-10-20-old.md", VALID_REPORT + OLD + OLD + OLD)
    r = _run(out)
    assert r.returncode == 1 and r.stdout.count(NO_CLASS) == 1 and "old cache" in r.stdout, r.stdout


def test_old_lines_are_judged_at_the_fork_point_not_at_mains_tip(render, tmp_path):
    """A line main changed after the branch forked is still old on the branch."""
    out = _branch(_render(render, tmp_path), VALID_REPORT + OLD)
    _git(out, "checkout", "-q", "main")
    _report(out, "2026-10-20-old.md", VALID_REPORT + OLD.replace("old cache", "stale cache"))
    _git(out, "commit", "-qam", "main rewords the finding")
    _git(out, "checkout", "-q", "feature")
    r = _run(out)
    assert r.returncode == 0 and NO_CLASS not in r.stdout, r.stdout


def test_a_report_renamed_on_the_branch_keeps_its_old_findings(render, tmp_path):
    """A report the branch renames (`git mv`) is judged against its old path at the fork
    point: its old majors stay old, a major added beside them is new."""
    out = _branch(_render(render, tmp_path), VALID_REPORT + OLD)
    _git(out, "mv", ".process-work/reviews/2026-10-20-old.md", ".process-work/reviews/2026-10-20-7-old.md")
    _git(out, "commit", "-qm", "rename")
    r = _run(out)
    assert r.returncode == 0 and NO_CLASS not in r.stdout, r.stdout
    _report(out, "2026-10-20-7-old.md", VALID_REPORT + OLD + "FINDING sev=major action=fix issue=- new here\n")
    r = _run(out)
    assert r.returncode == 1 and "'new here'" in r.stdout and "old cache" not in r.stdout, r.stdout


def test_an_unreadable_head_or_fork_refuses(render, tmp_path):
    report = VALID_REPORT + "FINDING sev=major action=fix issue=- guard read twice\n"
    # unborn HEAD: no commit to fork from
    out = _render(render, tmp_path / "unborn")
    _git(out, "init", "-q", "-b", "main")
    _report(out, "2026-10-21-new.md", report)
    r = _run(out)
    assert r.returncode == 1 and "HEAD cannot be read" in r.stdout, r.stdout
    # HEAD names a commit git does not have
    out = _branch(_render(render, tmp_path / "broken"))
    _report(out, "2026-10-21-new.md", report)
    (out / ".git/refs/heads/feature").write_text("1" * 40 + "\n")
    r = _run(out)
    assert r.returncode == 1 and "HEAD cannot be read" in r.stdout, r.stdout
    # the report at the fork point cannot be read
    out = _branch(_render(render, tmp_path / "fork"), VALID_REPORT + OLD)
    blob = _git(out, "rev-parse", "main:.process-work/reviews/2026-10-20-old.md")
    (out / ".git/objects" / blob[:2] / blob[2:]).unlink()
    r = _run(out)
    assert r.returncode == 1 and "cannot be read at the fork point" in r.stdout, r.stdout


def test_an_ambiguous_fork_point_refuses(render, tmp_path):
    out = _branch(_render(render, tmp_path))
    (out / "feature.md").write_text("a1\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-qm", "a1")
    a1 = _git(out, "rev-parse", "HEAD")
    _git(out, "checkout", "-q", "main")
    (out / "main.md").write_text("b1\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-qm", "b1")
    b1 = _git(out, "rev-parse", "HEAD")
    _git(out, "merge", "-q", "--no-ff", "-m", "main takes feature", a1)
    _git(out, "checkout", "-q", "feature")
    _git(out, "merge", "-q", "--no-ff", "-m", "feature takes main", b1)
    _report(out, "2026-10-21-new.md", VALID_REPORT + "FINDING sev=major action=fix issue=- guard read twice\n")
    r = _run(out)
    assert r.returncode == 1 and "fork point cannot be read" in r.stdout, r.stdout


def test_no_branch_range_is_a_note_and_binds_nothing(render, tmp_path):
    """On the integration ref, or in a readable repo without one (a clone with only a
    feature branch), no finding is new here: a note, as plan-structure does."""
    report = VALID_REPORT + "FINDING sev=major action=fix issue=- guard read twice\n"
    out = _render(render, tmp_path / "nomain")
    _git(out, "init", "-q", "-b", "dev")
    _git(out, "add", "-A")
    _git(out, "commit", "-qm", "base")
    _report(out, "2026-10-21-new.md", report)
    r = _run(out)
    assert r.returncode == 0 and "no branch range against an integration ref" in r.stdout, r.stdout
    out = _branch(_render(render, tmp_path / "onmain"))
    _git(out, "checkout", "-q", "main")
    _report(out, "2026-10-21-new.md", report)
    r = _run(out)
    assert r.returncode == 0 and "no branch range against an integration ref" in r.stdout, r.stdout


def test_an_integration_ref_without_a_fork_point_refuses(render, tmp_path):
    """A shallow clone holds origin/main but not the commit the branch forked from: which
    findings are new is unknown, so the gate fails closed instead of noting no range."""
    src = _branch(_render(render, tmp_path / "src"), VALID_REPORT + OLD)
    _git(src, "checkout", "-q", "main")
    (src / "m.txt").write_text("m\n")
    _git(src, "add", "-A")
    _git(src, "commit", "-qm", "main moves on")
    _git(src, "checkout", "-q", "feature")
    _report(src, "2026-10-21-new.md", VALID_REPORT + "FINDING sev=major action=fix issue=- guard read twice\n")
    _git(src, "add", "-A")
    _git(src, "commit", "-qm", "new report")
    _git(src, "checkout", "-q", "main")  # the remote's default branch is main
    dst = tmp_path / "shallow"
    subprocess.run(["git", "clone", "-q", "--depth", "1", "--no-single-branch", "-b", "feature",
                    f"file://{src}", str(dst)], check=True, capture_output=True)
    r = _run(dst)
    assert r.returncode == 1 and "no fork point with" in r.stdout and "origin/main" in r.stdout \
        and "no branch range" not in r.stdout, r.stdout


def test_the_codex_handoff_writes_class_on_every_finding(render, tmp_path):
    """The dispatched Codex review requires `class` in its result schema and writes it into
    the report line, so its new blockers and majors pass this gate."""
    import importlib
    out = _branch(_render(render, tmp_path))
    sys.path.insert(0, str(out / "scripts/process"))
    try:
        sys.modules.pop("_dispatch_codex", None)
        codex = importlib.import_module("_dispatch_codex")
        required = codex._schema(plan_review=False, gate=False)["properties"]["findings"]["items"]["required"]
        assert "class" in required
        rec = {"binding": {"base": "a" * 40, "head": "b" * 40, "diff_sha256": "c" * 64}, "branch": "7-widget",
               "model": "gpt-6-sol", "invocation": "codex exec", "result_sha256": "d" * 64, "issue": 7}
        result = {"verdict": "block", "criteria": [], "refute": [],
                  "findings": [{"sev": "major", "action": "fix", "kind": "implementation", "issue": "-",
                                "class": "testable", "rule": "mutation", "title": "guard read twice"}]}
        text = codex._report_text(rec, result, work="7", plan_review=False, refute_round=None)
    finally:
        sys.path.remove(str(out / "scripts/process"))
        sys.modules.pop("_dispatch_codex", None)
    assert "class=testable" in text and "at=-" in text  # a result without `at` (a run from before v2.78)
    _report(out, "2026-10-21-7-codex-review.md", text)
    r = _run(out)
    assert r.returncode == 0 and NO_CLASS not in r.stdout and NO_AT not in r.stdout, r.stdout


def test_the_codex_place_is_the_gates_grammar(render, tmp_path):
    """v2.78: the Codex schema requires `at` with the gate's pattern, the copy of `valid_at`
    judges like the original, and a place the gate would not read is written `-` and named."""
    import importlib
    out = _branch(_render(render, tmp_path))
    sys.path.insert(0, str(out / "scripts/process"))
    try:
        for m in ("_dispatch_codex", "check_issues"):
            sys.modules.pop(m, None)
        codex = importlib.import_module("_dispatch_codex")
        gate = importlib.import_module("check_issues")
        item = codex._schema(plan_review=False, gate=False)["properties"]["findings"]["items"]
        assert "at" in item["required"] and item["properties"]["at"]["pattern"] == gate.FINDING_AT_PATTERN
        for value in ("-", "p", "src/a.py", "src/a.py:3", "src/a.py:3-3", "src/a.py:3-9", "a%20b.md:1",
                      "src/a.py:0", "src/a.py:5-3", "src/a.py:3-", "src/my file.py:5", "", "a:b:3"):
            assert codex._valid_at(value) == gate.valid_at(value), value
        rec = {"binding": {"base": "a" * 40, "head": "b" * 40, "diff_sha256": "c" * 64}, "branch": "7-widget",
               "model": "gpt-6-sol", "invocation": "codex exec", "result_sha256": "d" * 64, "issue": 7}
        finding = {"sev": "major", "action": "fix", "kind": "implementation", "issue": "-",
                   "class": "testable", "rule": "mutation", "title": "guard read twice"}
        good = codex._report_text(rec, {"verdict": "block", "criteria": [], "refute": [],
                                        "findings": [{**finding, "at": "src/a.py:3-9"}]},
                                  work="7", plan_review=False, refute_round=None)
        bad = codex._report_text(rec, {"verdict": "block", "criteria": [], "refute": [],
                                       "findings": [{**finding, "at": "src/a.py:9-3"}]},
                                 work="7", plan_review=False, refute_round=None)
    finally:
        sys.path.remove(str(out / "scripts/process"))
        for m in ("_dispatch_codex", "check_issues"):
            sys.modules.pop(m, None)
    assert "at=src/a.py:3-9 guard" in good
    assert "at=- guard" in bad and "at-invalid: src/a.py:9-3" in bad
    # a title that itself begins with a field token stays a title
    sys.path.insert(0, str(out / "scripts/process"))
    try:
        sys.modules.pop("_dispatch_codex", None)
        codex = importlib.import_module("_dispatch_codex")
        odd = codex._report_text(rec, {"verdict": "block", "criteria": [], "refute": [],
                                       "findings": [{**finding, "at": "src/a.py:3", "title": "at=boot the guard"},
                                                    {**finding, "at": "src/a.py:4", "title": "  at=boot the second"}]},
                                 work="7", plan_review=False, refute_round=None)
    finally:
        sys.path.remove(str(out / "scripts/process"))
        sys.modules.pop("_dispatch_codex", None)
    _report(out, "2026-10-21-7-codex-odd.md", odd)
    r = _run(out)
    assert r.returncode == 0 and "malformed" not in r.stdout and "at=boot the guard" in odd, r.stdout
    for text in (good, bad):
        _report(out, "2026-10-21-7-codex-review.md", text)
        r = _run(out)
        assert r.returncode == 0 and NO_AT not in r.stdout, r.stdout
