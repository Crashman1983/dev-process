"""Overlays (Kenni backport II, owner 2026-10-15): a project's notes on a template doc
live in an anchored `*.local.md`; the core `overlays` gate turns red when a central
change removes or changes a section an overlay builds on — a possible breaking change
until someone re-read both and re-stamped the overlay."""
import subprocess
import sys

OVERLAY = ('overlay-of: docs/process/testing.md\n'
           'extends: "{heading}" @new\n\n## Our notes\n\nThe project runs its merge suite in stages.\n')


def _run(out, *args):
    return subprocess.run([sys.executable, str(out / "scripts/process/check_overlays.py"), *args], cwd=out,
                          capture_output=True, text=True)


def _heading(out):
    text = (out / "docs/process/testing.md").read_text()
    return next(ln for ln in text.splitlines() if ln.startswith("## "))


def test_an_overlay_is_checked_stamped_and_breaks_on_a_central_change(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    assert _run(out).returncode == 0  # no overlay: nothing to fit
    heading = _heading(out)
    ov = out / "docs/process/testing.local.md"
    ov.write_text(OVERLAY.format(heading=heading))
    r = _run(out)
    assert r.returncode == 1 and "not stamped yet" in r.stdout
    assert _run(out, "--stamp", str(ov)).returncode == 0
    assert "@new" not in ov.read_text()
    r = _run(out)
    assert r.returncode == 0 and "1 overlay fit" in r.stdout
    # the template changes the anchored section: a possible breaking change
    doc = out / "docs/process/testing.md"
    doc.write_text(doc.read_text().replace(heading, heading + "\n\nA new central rule.", 1))
    r = _run(out)
    assert r.returncode == 1 and "changed this section" in r.stdout and "testing.local.md" in r.stdout
    assert _run(out, "--stamp", str(ov)).returncode == 0 and _run(out).returncode == 0
    # the template renames the section: breaking, and stamping cannot paper over it
    doc.write_text(doc.read_text().replace(heading, heading + " (renamed)", 1))
    r = _run(out)
    assert r.returncode == 1 and "section is gone" in r.stdout
    assert _run(out, "--stamp", str(ov)).returncode == 1


def test_an_overlay_without_anchor_or_template_file_is_refused(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    ov = out / "docs/process/commands/quick.local.md"
    ov.parent.mkdir(parents=True)
    ov.write_text("overlay-of: .claude/commands/quick.md\n\nproject escalation rules\n")
    r = _run(out)
    assert r.returncode == 1 and "no anchor line" in r.stdout
    ov.write_text('overlay-of: docs/process/gone.md\nextends: "## X" @new\n')
    r = _run(out)
    assert r.returncode == 1 and "is gone" in r.stdout
    # a local note that names no template file is no overlay (review.local.md and the like)
    ov.unlink()
    (out / "docs/process/review.local.md").write_text("# project review notes\n")
    assert _run(out).returncode == 0


def test_a_heading_inside_a_code_fence_is_no_section(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    sys.path.insert(0, str(out / "scripts/process"))
    try:
        import check_overlays
        secs = check_overlays.sections("## A\ntext\n```\n## B\n```\nmore\n## C\nc\n")
        assert list(secs) == ["## A", "## C"] and "## B" in secs["## A"]
    finally:
        sys.path.remove(str(out / "scripts/process"))
        sys.modules.pop("check_overlays", None)


def test_the_gate_runs_in_core_and_sessions_see_the_overlays(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    runner = (out / "scripts/process/gate_runner.py").read_text()
    assert '"overlays": (None,' in runner
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=out, check=True)
    (out / "docs/process/testing.local.md").write_text(OVERLAY.format(heading=_heading(out)))
    ctx = subprocess.run([sys.executable, str(out / "scripts/process/rehydrate.py")], cwd=out,
                         capture_output=True, text=True, check=True).stdout
    assert "`docs/process/testing.md` → `docs/process/testing.local.md`" in ctx
    assert "docs/process/overlays.md" in (out / "docs/process/start-here.md").read_text()


def _mod(out):
    sys.path.insert(0, str(out / "scripts/process"))
    import importlib
    sys.modules.pop("check_overlays", None)
    return importlib.import_module("check_overlays")


def test_no_false_green_from_lines_that_do_not_parse(render, tmp_path):
    """Refute round 2: a malformed anchor or head was skipped, so a changed section stayed green."""
    out = render(tmp_path, {"project_name": "d"})
    heading = _heading(out)
    ov = out / "docs/process/testing.local.md"
    for bad in (f'overlay-of: docs/process/testing.md\nreplaces: "{heading}" @NEW\n',
                f"overlay-of: docs/process/testing.md\nextends: '{heading}' @new\n",
                f'overlay-of: docs/process/testing.md\nreplace: "{heading}" @new\n',
                f'overlay-of: docs/process/testing.md  # note\nextends: "{heading}" @new\n',
                f'﻿overlay-of: docs/process/testing.md # x\nextends: "{heading}" @new\n'):
        ov.write_text(bad, encoding="utf-8")
        r = _run(out)
        assert r.returncode == 1 and "does not parse" in r.stdout, bad


def test_fences_and_closing_hashes_follow_commonmark(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    co = _mod(out)
    try:
        secs = co.sections("## A\n```bash\n## setup\n```\nall tests run\n## B\nb\n")
        assert "all tests run" in secs["## A"] and "## setup" not in secs
        secs = co.sections("## A\n````\n```\n## x\n````\ntail\n")  # a shorter fence does not close
        assert "tail" in secs["## A"] and "## x" not in secs
        secs = co.sections("## C#\nsharp\n## C\nplain\n")
        assert secs["## C#"] == "## C#\nsharp" and secs["## C"] == "## C\nplain"
        assert co._norm("## Title ##") == "## Title"
    finally:
        sys.path.remove(str(out / "scripts/process"))
        sys.modules.pop("check_overlays", None)


def test_an_overlay_names_a_file_of_this_repository_only(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    ov = out / "docs/process/x.local.md"
    for target in ("/dev/zero", "/etc/hostname", "../../../../etc/passwd", "docs/process"):
        ov.write_text(f'overlay-of: {target}\nextends: "## A" @new\n')
        r = subprocess.run([sys.executable, str(out / "scripts/process/check_overlays.py")], cwd=out,
                           capture_output=True, text=True, timeout=30)
        assert r.returncode == 1 and "outside the repository" in r.stdout, target


def test_stamp_refuses_what_the_gate_does_not_check(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=out, check=True)
    stray = out / "notes/x.local.md"
    stray.parent.mkdir()
    stray.write_text(OVERLAY.format(heading=_heading(out)))
    r = _run(out, "--stamp", str(stray))
    assert r.returncode == 1 and "not an overlay the gate checks" in r.stderr
    r = _run(out, "--stamp", str(out / "docs/process/missing.local.md"))
    assert r.returncode == 1 and "Traceback" not in r.stderr
    # from a subdirectory: the repository root is git's, not the cwd
    ov = out / "docs/process/testing.local.md"
    ov.write_text(OVERLAY.format(heading=_heading(out)))
    r = subprocess.run([sys.executable, str(out / "scripts/process/check_overlays.py"), "--stamp", str(ov)],
                       cwd=out / "docs", capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_an_overlay_of_the_rules_reaches_the_session_whole(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=out, check=True)
    rules = (out / "docs/process/mandatory-rules.md").read_text()
    heading = next(ln for ln in rules.splitlines() if ln.startswith("#"))
    (out / "docs/process/mandatory-rules.local.md").write_text(
        f'overlay-of: docs/process/mandatory-rules.md\nextends: "{heading}" @new\n\nProse follows the operator.\n')
    ctx = subprocess.run([sys.executable, str(out / "scripts/process/rehydrate.py")], cwd=out,
                         capture_output=True, text=True, check=True).stdout
    assert "Prose follows the operator." in ctx
    codex = subprocess.run([sys.executable, str(out / "scripts/process/rehydrate.py"), "--codex"], cwd=out,
                           capture_output=True, text=True, check=True).stdout
    assert "Prose follows the operator." in codex


def test_the_kernel_takes_no_overlay(render, tmp_path):
    """Code review round 2 (M2): the kernel is copied byte for byte into the anchors — an
    overlay of it would never reach the always-on block; the project keeps its own copy."""
    out = render(tmp_path, {"project_name": "d"})
    kernel = (out / "docs/process/kernel.md").read_text()
    heading = next(ln for ln in kernel.splitlines() if ln.startswith("#"))
    (out / "docs/process/kernel.local.md").write_text(
        f'overlay-of: docs/process/kernel.md\nreplaces: "{heading}" @new\n\nProse follows the operator.\n')
    r = _run(out)
    assert r.returncode == 1 and "takes no overlay" in r.stdout and ".process-owned" in r.stdout
    # the same file under another spelling of its path (delta review round 3)
    (out / "docs/process/kernel.local.md").write_text(
        f'overlay-of: ./docs/process/kernel.md\nreplaces: "{heading}" @new\n')
    r = _run(out)
    assert r.returncode == 1 and "takes no overlay" in r.stdout
    assert _run(out, "--stamp", str(out / "docs/process/kernel.local.md")).returncode == 1


def test_every_command_sends_the_session_to_its_overlay(render, tmp_path):
    """Code review round 2 (M1): the context hook runs only after a compaction or resume —
    a fresh or headless session learns of a command's overlay from the command itself."""
    out = render(tmp_path, {"project_name": "d"})
    out = render(tmp_path / "all", {"project_name": "d", "harnesses": {"claude": True, "copilot": True}})
    commands = sorted((out / ".claude/commands").glob("*.md"))
    prompts = sorted((out / ".github/prompts").glob("*.prompt.md"))  # Copilot runs these headless
    assert commands and prompts
    for cmd in commands + prompts:
        text = cmd.read_text()
        name = cmd.name.split(".")[0]
        assert f"`docs/process/commands/{name}.local.md`" in text, cmd.name
        assert "docs/process/overlays.md" in text, cmd.name


def test_an_example_inside_a_fence_is_no_head_or_anchor(render, tmp_path):
    """Code review round 2 (m7): an overlay that shows an anchor in a code block claims nothing."""
    out = render(tmp_path, {"project_name": "d"})
    heading = _heading(out)
    ov = out / "docs/process/testing.local.md"
    example = '```\nreplaces: "## Z" @new\noverlay-of: docs/process/gone.md\n```\n'
    ov.write_text(OVERLAY.format(heading=heading) + "\nFor example:\n\n" + example)
    assert _run(out, "--stamp", str(ov)).returncode == 0
    assert example in ov.read_text()  # the stamp leaves the example as written
    r = _run(out)
    assert r.returncode == 0, r.stdout
    # an overlay that only shows a head in a fence is no overlay at all
    (out / "docs/process/notes.local.md").write_text("# notes\n\n" + example)
    assert _run(out).returncode == 0
    # a fence never closed would swallow the anchors after it: red, never a silent skip
    ov.write_text(OVERLAY.format(heading=heading) + '\n```\nforgot to close\n\nreplaces: "## Z" @new\n')
    r = _run(out)
    assert r.returncode == 1 and "never closed" in r.stdout


def test_template_update_names_the_overlays_to_re_check(render, tmp_path, monkeypatch, capsys):
    out = render(tmp_path, {"project_name": "d"})
    (out / "docs/process/testing.local.md").write_text(OVERLAY.format(heading=_heading(out)))
    for args in (["init", "-q", "-b", "main"], ["add", "-A"],
                 ["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "base"]):
        subprocess.run(["git", *args], cwd=out, check=True)
    sys.path.insert(0, str(out / "scripts/process"))
    try:
        import importlib
        sys.modules.pop("template_update", None)
        tu = importlib.import_module("template_update")
        monkeypatch.setattr(tu, "answers", lambda *a, **k: ("gh:x/dev-process", "v1.0.0", {}))
        monkeypatch.setattr(tu, "_copier", lambda *a, **k: subprocess.CompletedProcess(a, 0, "", ""))
        monkeypatch.setattr(tu, "render", lambda *a, **k: True)
        monkeypatch.setattr(tu, "write_deltas", lambda *a, **k: [])
        assert tu.main([str(out), "--ref", "v1.0.1"]) == 0
    finally:
        sys.path.remove(str(out / "scripts/process"))
        for name in ("template_update", "check_overlays", "template_verify"):
            sys.modules.pop(name, None)
    printed = capsys.readouterr().out
    assert "re-check an overlay" in printed and "testing.local.md" in printed
