import subprocess
import sys
from pathlib import Path

KENNI = ["Kenni", "KenniNext", "Seb", "Signal", "SvelteKit", "user_id=1"]

FRAME = "PRODUCT.md"


def _run(out: Path):
    return subprocess.run(
        [sys.executable, str(out / "scripts/process/check_product_frame.py"), str(out)],
        capture_output=True, text=True,
    )


def _onboarded(out: Path, body: str = ""):
    """A minimal onboarded frame; body is appended after the sections."""
    (out / FRAME).write_text(
        "# demo — Product Frame\n\n"
        "status: onboarded\n\n"
        "## Purpose\n\nA tool that does one thing well.\n\n"
        "## Users\n\nSolo developers.\n\n"
        "## Goals\n\n- Ship the one thing.\n\n"
        "## Non-goals\n\n- Everything else.\n\n"
        "## Constraints\n\n- Offline-capable.\n\n"
        "## Scope now\n\nThe first slice.\n" + body,
        encoding="utf-8",
    )


def test_frame_rendered_in_core(render, tmp_path):
    # core: present with every module off
    out = render(tmp_path, {"project_name": "demo"})
    assert (out / FRAME).is_file()
    assert (out / "scripts/process/check_product_frame.py").is_file()


def test_frame_neutral_and_named(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    text = (out / FRAME).read_text()
    assert "demo — Product Frame" in text  # project name templated in
    for k in KENNI:
        assert k not in text, f"{k} leaked into {FRAME}"
    gate = (out / "scripts/process/check_product_frame.py").read_text()
    for k in KENNI:
        assert k not in gate, f"{k} leaked into the gate"


def test_gate_listed_with_all_modules_off(render, tmp_path):
    # core gate: active regardless of the manifest
    out = render(tmp_path, {"project_name": "demo"})
    r = subprocess.run(
        [sys.executable, str(out / "scripts/process/gate_runner.py"), "--list"],
        cwd=out, capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    assert "product-frame" in r.stdout


def test_seed_is_green_with_not_onboarded_note(render, tmp_path):
    # shipped scaffold: placeholders allowed, honest note, no failure
    out = render(tmp_path, {"project_name": "demo"})
    r = _run(out)
    assert r.returncode == 0, r.stdout
    assert "not onboarded yet" in r.stdout
    assert "product-frame: OK" in r.stdout


def test_missing_frame_hard(render, tmp_path):
    # core artifact: absence is a violation, not pre-adoption
    out = render(tmp_path, {"project_name": "demo"})
    (out / FRAME).unlink()
    r = _run(out)
    assert r.returncode == 1
    assert "core artifact" in r.stdout


def test_onboarded_with_leftover_placeholder_hard(render, tmp_path):
    # flipping the status while sections are placeholder claims direction
    # that is not there — the marker is what buys the hard check
    out = render(tmp_path, {"project_name": "demo"})
    text = (out / FRAME).read_text().replace("status: not-onboarded", "status: onboarded")
    (out / FRAME).write_text(text, encoding="utf-8")
    r = _run(out)
    assert r.returncode == 1
    assert "still hold a placeholder" in r.stdout


def test_onboarded_clean_is_ok_without_note(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    _onboarded(out)
    r = _run(out)
    assert r.returncode == 0, r.stdout
    assert "not onboarded" not in r.stdout
    assert "product-frame: OK" in r.stdout


def test_missing_status_line_hard(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    (out / FRAME).write_text("# demo\n\n## Purpose\n\nReal.\n", encoding="utf-8")
    r = _run(out)
    assert r.returncode == 1
    assert "no 'status:' line" in r.stdout


def test_invalid_status_value_hard(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    (out / FRAME).write_text("# demo\n\nstatus: onbaorded\n\n## Purpose\n\nx\n",
                             encoding="utf-8")
    r = _run(out)
    assert r.returncode == 1
    assert "is not one of" in r.stdout


def test_dead_adr_ref_hard(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    _onboarded(out, "\nGrounded in ADR-0099.\n")
    r = _run(out)
    assert r.returncode == 1
    assert "ADR-0099 referenced but no" in r.stdout  # the specific message, not any 'no'


def test_valid_adr_ref_ok(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    _onboarded(out, "\nGrounded in ADR-0001.\n")  # seed record ships
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_fenced_refs_and_placeholders_ignored(render, tmp_path):
    # a quoted example is not a claim
    out = render(tmp_path, {"project_name": "demo"})
    _onboarded(out, "\n```\nADR-0099 and\n> _Placeholder in a fence\n```\n")
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_story_ref_without_registry_soft(render, tmp_path):
    # feature-registry off: not checkable -> honest note, never a failure
    out = render(tmp_path, {"project_name": "demo"})
    _onboarded(out, "\nScope now includes STORY-0007.\n")
    r = _run(out)
    assert r.returncode == 0, r.stdout
    assert "not checkable" in r.stdout


def test_story_ref_with_registry_dead_hard(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo",
                            "modules": {"feature_registry": True}})
    _onboarded(out, "\nScope now includes STORY-0007.\n")
    r = _run(out)
    assert r.returncode == 1
    assert "STORY-0007" in r.stdout


def test_story_ref_with_registry_resolving_ok(render, tmp_path):
    import json
    out = render(tmp_path, {"project_name": "demo",
                            "modules": {"feature_registry": True}})
    reg = out / "docs/process/feature-registry"
    reg.mkdir(parents=True, exist_ok=True)
    (reg / "STORY-0007.json").write_text(json.dumps(
        {"id": "STORY-0007", "title": "t",
         "story": "As a x, when y, the system shall z.",
         "acceptance": [{"id": "AC1", "text": "a"}], "tests": [],
         "status": "proposed"}), encoding="utf-8")
    _onboarded(out, "\nScope now includes STORY-0007.\n")
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_onboarded_placeholder_before_first_heading_hard(render, tmp_path):
    # SP31 review MAJOR: the section-scoped scan let a placeholder ABOVE the
    # first ## heading pass green on an onboarded frame — a false-green. The
    # whole text is scanned now.
    out = render(tmp_path, {"project_name": "demo"})
    _onboarded(out)
    text = (out / FRAME).read_text().replace(
        "status: onboarded\n", "status: onboarded\n\n> _Placeholder — intro left over._\n")
    (out / FRAME).write_text(text, encoding="utf-8")
    r = _run(out)
    assert r.returncode == 1
    assert "before the first section" in r.stdout


def test_tilde_fence_ignored(render, tmp_path):
    # CommonMark-legal ~~~ fences are quotations too (SP31 review)
    out = render(tmp_path, {"project_name": "demo"})
    _onboarded(out, "\n~~~\nADR-0099 and\n> _Placeholder in a tilde fence\n~~~\n")
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_html_comment_ref_ignored(render, tmp_path):
    # the seed itself establishes HTML comments as an idiom in this file —
    # a commented-out ref is not a claim (SP31 review)
    out = render(tmp_path, {"project_name": "demo"})
    _onboarded(out, "\n<!-- TODO: maybe cite ADR-0099 someday -->\n")
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_story_resolved_by_id_not_filename(render, tmp_path):
    # the registry SSOT resolves stories by their id field, not the filename —
    # the frame gate must agree (SP31 review: false-red on login.json)
    import json
    out = render(tmp_path, {"project_name": "demo",
                            "modules": {"feature_registry": True}})
    reg = out / "docs/process/feature-registry"
    reg.mkdir(parents=True, exist_ok=True)
    (reg / "login.json").write_text(json.dumps(
        {"id": "STORY-0007", "title": "t",
         "story": "As a x, when y, the system shall z.",
         "acceptance": [{"id": "AC1", "text": "a"}], "tests": [],
         "status": "proposed"}), encoding="utf-8")
    _onboarded(out, "\nScope now includes STORY-0007.\n")
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_story_ref_width_normalized(render, tmp_path):
    # STORY-7 is matched and width-normalized like ADR refs — a typo'd width
    # must fail loudly, not pass silently (SP31 review)
    out = render(tmp_path, {"project_name": "demo",
                            "modules": {"feature_registry": True}})
    _onboarded(out, "\nScope now includes STORY-7.\n")
    r = _run(out)
    assert r.returncode == 1
    assert "STORY-7" in r.stdout


def test_annotated_status_message_names_the_problem(render, tmp_path):
    # 'status: onboarded since 2026' is hard either way, but the message must
    # point at the annotation, not claim the line is missing (SP31 review)
    out = render(tmp_path, {"project_name": "demo"})
    (out / FRAME).write_text(
        "# demo\n\nstatus: onboarded since 2026\n\n## Purpose\n\nx\n", encoding="utf-8")
    r = _run(out)
    assert r.returncode == 1
    assert "is not one of" in r.stdout
    assert "no 'status:' line" not in r.stdout


def test_non_utf8_hard(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    (out / FRAME).write_bytes(b"# frame\nstatus: onboarded\n\xff\xfe\n")
    r = _run(out)
    assert r.returncode == 1
    assert "not valid UTF-8" in r.stdout
    assert "Traceback" not in r.stdout and "Traceback" not in r.stderr


def test_full_runner_green_on_seed_tree(render, tmp_path):
    # the always-on gate must not red a fresh render
    out = render(tmp_path, {"project_name": "demo"})
    r = subprocess.run(
        [sys.executable, str(out / "scripts/process/gate_runner.py")],
        cwd=out, capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stdout + r.stderr


def test_bulleted_status_line_is_read(render, tmp_path):
    # audit consistency: '- status: onboarded' must not read as "no status line"
    # (every other grammar tolerates the leading bullet)
    out = render(tmp_path, {"project_name": "demo"})
    _onboarded(out)
    text = (out / FRAME).read_text().replace("status: onboarded", "- status: onboarded")
    (out / FRAME).write_text(text, encoding="utf-8")
    r = _run(out)
    assert r.returncode == 0, r.stdout
    assert "no 'status:' line" not in r.stdout
