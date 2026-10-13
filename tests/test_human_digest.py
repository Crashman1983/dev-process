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
    waiting = r.stdout.split("## 2")[0]
    assert "013-done" not in waiting                    # past the window
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
    assert "by risk, not by count" in r.stdout
    assert "floor AND ceiling" not in r.stdout


def test_digest_points_at_screenshots_to_open(render, tmp_path):
    import subprocess as sp
    out = render(tmp_path, {"project_name": "demo"})
    sp.run(["git", "init", "-q", "-b", "main"], cwd=out, check=True)
    sp.run(["git", "config", "user.email", "t@t"], cwd=out, check=True)
    sp.run(["git", "config", "user.name", "t"], cwd=out, check=True)
    ev = out / ".process-work/reviews/panel"
    ev.mkdir(parents=True)
    (ev / "after-panel-375-dark.png").write_bytes(b"\x89PNG")
    (out / "e2e/shots").mkdir(parents=True)
    (out / "e2e/shots/home.png").write_bytes(b"\x89PNG")
    sp.run(["git", "add", "-A"], cwd=out, check=True)
    sp.run(["git", "commit", "-q", "-m", "feat: screens"], cwd=out, check=True)
    r = _run(out)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "What changed on screen" in r.stdout
    assert "A .process-work/reviews/panel/after-panel-375-dark.png" in r.stdout
    assert "1 in e2e/shots/" in r.stdout


def test_digest_carries_the_residue_report(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    (out / ".process-work/template-delta").mkdir(parents=True)
    r = _run(out)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "Residue" in r.stdout and "template-delta/ left over" in r.stdout
    assert "tidy.py" in r.stdout
    assert not (out / "scripts/process/__pycache__").exists()


def test_digest_lists_the_waiver_of_any_gate(render, tmp_path):
    """A project's own gate (gates.local.json) with its own `<gate>-waived:` grammar:
    the debt belongs on the owner's page as much as a review waiver does."""
    import datetime
    out = render(tmp_path, {"project_name": "demo"})
    adir = out / ".process-work/plans/archive"
    adir.mkdir(parents=True, exist_ok=True)
    today = datetime.date.today().isoformat()
    (adir / f"{today}-ac.md").write_text(
        "# Plan\n\ntier: 2\nissue: #8\nac-waived: AC-3 — measured in the next release\n",
        encoding="utf-8")

    r = _run(out)

    assert f"{today}-ac.md: ac-waived: AC-3 — measured in the next release" in r.stdout, r.stdout


def _news_repo(out, tmp_path, fragments):
    """A clone with an origin; `fragments` = (slug, type, text, landed-on date)."""
    import os
    env = {k: v for k, v in os.environ.items() if k not in ("CI", "PRE_COMMIT_TO_REF")}

    def git(*a, date=None):
        e = {**env, "GIT_COMMITTER_DATE": f"{date}T12:00:00+00:00",
             "GIT_AUTHOR_DATE": f"{date}T12:00:00+00:00"} if date else env
        subprocess.run(["git", *a], cwd=out, check=True, capture_output=True, env=e)

    git("init", "-q", "-b", "main")
    git("config", "user.email", "t@t")
    git("config", "user.name", "t")
    git("add", "-A")
    git("commit", "-qm", "init", date="2020-01-01")
    subprocess.run(["git", "init", "-q", "--bare", str(tmp_path / "origin.git")], check=True)
    git("remote", "add", "origin", str(tmp_path / "origin.git"))
    for slug, kind, text, day in fragments:
        (out / "news").mkdir(exist_ok=True)
        (out / "news" / f"{slug}.md").write_text(f"type: {kind}\n\n{text}\n", encoding="utf-8")
        git("add", "-A")
        git("commit", "-qm", slug, date=day)
    git("push", "-q", "-u", "origin", "main")


def test_digest_lists_the_news_of_the_window(render, tmp_path):
    import datetime
    out = render(tmp_path / "p", {"project_name": "demo"})
    today = datetime.date.today().isoformat()
    _news_repo(out, tmp_path, [("old", "new", "An ancient feature.", "2020-02-01"),
                               ("fresh", "fixed", "Saving no longer loses the title.", today)])
    r = _run(out)
    assert r.returncode == 0, r.stdout + r.stderr
    section = r.stdout.split("## 9 · New and improved")[1]
    assert f"- {today}  Fixed  Saving no longer loses the title." in section
    assert "ancient feature" not in section
    assert not (out / "scripts/process/__pycache__").exists()


def test_digest_says_plainly_when_the_project_keeps_no_news(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    r = _run(out)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "no news/ directory" in r.stdout.split("## 9 · New and improved")[1]


def test_digest_says_so_when_the_window_holds_no_news(render, tmp_path):
    out = render(tmp_path / "p", {"project_name": "demo"})
    _news_repo(out, tmp_path, [("old", "new", "An ancient feature.", "2020-02-01")])
    r = _run(out)
    assert "no news entry in the last 7 days" in r.stdout


def test_digest_names_a_malformed_fragment_and_still_shows_the_rest(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    (out / "news").mkdir()
    (out / "news/good.md").write_text("type: new\n\nA good one.\n", encoding="utf-8")
    (out / "news/broken.md").write_text("no header\n", encoding="utf-8")
    r = _run(out)
    section = r.stdout.split("## 9 · New and improved")[1]
    assert r.returncode == 0 and "A good one." in section
    assert "1 fragment(s) malformed" in section and "news/broken.md" in section


def test_digest_survives_a_failing_news_script_and_names_the_failure(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    (out / "news").mkdir()
    (out / "docs/process/news.local.json").write_text("{not json", encoding="utf-8")
    r = _run(out)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "news.py failed" in r.stdout and "docs/process/news.local.json" in r.stdout
    (out / "scripts/process/news.py").write_text("raise RuntimeError('boom')\n", encoding="utf-8")
    r = _run(out)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "news.py failed: RuntimeError: boom" in r.stdout
