"""SP63: the owner digest — plain-language inbound edges on one page."""
import subprocess
import sys


def _run(root, *args):
    return subprocess.run(
        [sys.executable, str(root / "scripts/process/human_digest.py"), *args, "."],
        cwd=root, capture_output=True, text=True,
    )


def _spec(root, name, *, brief=True, tasks=False, marker=False):
    d = root / "specs" / name
    d.mkdir(parents=True, exist_ok=True)
    body = ["# Feature Specification: X", "", "issue: #42", ""]
    if brief:
        body += ["## Owner brief — plain language *(mandatory, first)*", "",
                 "1. **What**: a panel that shows documents beside the chat.",
                 "2. **Why**: users lose the thread when a doc opens full-screen.",
                 "3. **Visible change**: documents open beside, not instead.",
                 "4. **Risk**: the mobile layout may feel cramped.",
                 "5. **Your call**: should editing work on phones too?", ""]
    body += ["## User Scenarios & Testing", ""]
    if marker:
        body += ["[NEEDS CLARIFICATION: which formats?]", ""]
    (d / "spec.md").write_text("\n".join(body), encoding="utf-8")
    if tasks:
        (d / "tasks.md").write_text("- [x] T001 done\n", encoding="utf-8")


def test_digest_leads_with_owner_brief(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    _spec(out, "011-doc-panel", brief=True, tasks=False)
    r = _run(out)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "Waiting for you" in r.stdout
    assert "users lose the thread" in r.stdout          # the brief itself
    assert "Your call" in r.stdout


def test_digest_flags_missing_brief_and_open_questions(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    _spec(out, "012-no-brief", brief=False, tasks=True, marker=True)
    r = _run(out)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "no Owner brief" in r.stdout
    assert "open: [NEEDS CLARIFICATION: which formats?]" in r.stdout


def test_digest_planned_and_clean_spec_leaves_the_window(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    _spec(out, "013-done", brief=True, tasks=True, marker=False)
    r = _run(out)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "013-done" not in r.stdout                   # past the window
    assert "nothing waiting" in r.stdout


def test_digest_merged_debts_and_sampling_pick(render, tmp_path):
    import datetime
    out = render(tmp_path, {"project_name": "demo"})
    adir = out / ".process-work/plans/archive"
    adir.mkdir(parents=True, exist_ok=True)
    today = datetime.date.today().isoformat()
    (adir / f"{today}-widget.md").write_text(
        "# Plan\n\ntier: 2\nissue: #7\nreview-waived: tiny rename\n",
        encoding="utf-8")
    (adir / f"{today}-orphan.md").write_text(
        "# Plan\n\ntier: 2\nspec-waived: legacy, no tracker\n",
        encoding="utf-8")
    r = _run(out)
    assert r.returncode == 0, r.stdout + r.stderr
    assert f"{today}-widget.md · tier 2 · issue #7" in r.stdout
    assert "Sampling audit pick" in r.stdout
    # the issue-anchored plan owns its waiver; the tracker-less one does not
    assert f"{today}-widget.md: review-waived: tiny rename\n" in r.stdout
    assert "orphan.md: spec-waived: legacy, no tracker  ← NO OWNER" in r.stdout


def test_digest_counts_the_test_estate(render, tmp_path):
    import subprocess as sp
    out = render(tmp_path, {"project_name": "demo"})
    sp.run(["git", "init", "-q", "-b", "main"], cwd=out, check=True)
    sp.run(["git", "config", "user.email", "t@t"], cwd=out, check=True)
    sp.run(["git", "config", "user.name", "t"], cwd=out, check=True)
    (out / "tests").mkdir(exist_ok=True)
    (out / "tests" / "test_widget.py").write_text("def test_x(): pass\n")
    (out / "e2e").mkdir()
    (out / "e2e" / "flow.spec.ts").write_text("// spec\n")
    sp.run(["git", "add", "-A"], cwd=out, check=True)
    sp.run(["git", "commit", "-q", "-m", "base"], cwd=out, check=True)
    r = _run(out)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "Test estate" in r.stdout
    assert "1 e2e" in r.stdout
    assert "floor AND ceiling" in r.stdout
