import subprocess
import sys

ADR = "docs/process/adr"


def _run(root):
    return subprocess.run(
        [sys.executable, str(root / "scripts/process/check_decisions.py"), "."],
        cwd=root, capture_output=True, text=True,
    )


def _write_adr(root, num, *, status="Accepted", type_="architecture",
               intent="keep", body="Some context.\n", list_it=True):
    p = root / ADR / f"adr-{num}-example.md"
    parts = [f"# ADR-{num}: Example", ""]
    if status is not None:
        parts += ["## Status", "", status, ""]
    if type_ is not None:
        parts += ["## Type", "", type_, ""]
    if intent is not None:
        parts += ["## Intent", "", intent, ""]
    parts += ["## Context", "", body]
    p.write_text("\n".join(parts), encoding="utf-8")
    if list_it:
        readme = root / ADR / "README.md"
        readme.write_text(readme.read_text() + f"\n| {int(num):04d} | Example | {status} |\n")
    return p


def test_seed_tree_passes(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    r = _run(out)
    assert r.returncode == 0, r.stdout
    assert "decision-records: OK" in r.stdout


def test_unlisted_file_hard(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    _write_adr(out, "0002", list_it=False)
    r = _run(out)
    assert r.returncode == 1
    assert "not listed" in r.stdout and "ADR-2" in r.stdout


def test_bad_status_enum_hard(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    _write_adr(out, "0002", status="Acepted")  # typo
    r = _run(out)
    assert r.returncode == 1
    assert "not a valid" in r.stdout and "Status" in r.stdout


def test_bad_intent_enum_hard(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    _write_adr(out, "0002", intent="kept")  # typo
    r = _run(out)
    assert r.returncode == 1
    assert "Intent" in r.stdout and "not one of" in r.stdout


def test_bad_type_enum_hard(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    _write_adr(out, "0002", type_="produkt")  # typo
    r = _run(out)
    assert r.returncode == 1
    assert "Type" in r.stdout


def test_superseded_keep_incoherent_hard(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    _write_adr(out, "0002", status="Superseded by ADR-0003", intent="keep")
    r = _run(out)
    assert r.returncode == 1
    assert "Superseded" in r.stdout and "historical" in r.stdout


def test_superseded_changeplanned_incoherent_hard(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    _write_adr(out, "0002", status="Superseded by ADR-0003", intent="change-planned")
    r = _run(out)
    assert r.returncode == 1
    assert "Superseded" in r.stdout


def test_superseded_tolerated_is_ok(render, tmp_path):
    # a superseded-but-tolerated record is coherent (historical debt), not hard
    out = render(tmp_path, {"project_name": "demo"})
    _write_adr(out, "0002", status="Superseded by ADR-0003", intent="tolerated")
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_unfilled_menu_is_soft(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    _write_adr(out, "0002", status="Proposed | Accepted | Superseded by ADR-MMMM")
    r = _run(out)
    assert r.returncode == 0, r.stdout
    assert "not chosen" in r.stdout


def test_missing_type_is_soft(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    _write_adr(out, "0002", type_=None)
    r = _run(out)
    assert r.returncode == 0, r.stdout
    assert "no '## Type'" in r.stdout


def test_changeplanned_without_link_is_soft(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    _write_adr(out, "0002", intent="change-planned", body="No follow-up here.\n")
    r = _run(out)
    assert r.returncode == 0, r.stdout
    assert "no follow-up linked" in r.stdout


def test_changeplanned_with_link_is_clean(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    _write_adr(out, "0002", intent="change-planned",
               body="Migration tracked in ADR-0003.\n")
    r = _run(out)
    assert r.returncode == 0, r.stdout
    assert "no follow-up linked" not in r.stdout


def test_non_utf8_hard(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    p = out / ADR / "adr-0002-binary.md"
    p.write_bytes(b"# ADR-0002\n\xff\xfe not utf-8\n")
    readme = out / ADR / "README.md"
    readme.write_text(readme.read_text() + "\n| 0002 | Binary | Accepted |\n")
    r = _run(out)
    assert r.returncode == 1
    assert "not valid UTF-8" in r.stdout
