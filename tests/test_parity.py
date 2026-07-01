import json
import subprocess
import sys
from pathlib import Path

KENNI = ["Kenni", "KenniNext", "Seb", "Signal", "SvelteKit", "user_id=1", "surface:ios"]

PARITY = "docs/process/parity"


def _render(render, tmp_path, surfaces=None, **mods):
    m = {"parity": True}
    m.update(mods)
    data = {"project_name": "d", "modules": m}
    if surfaces is not None:
        data["parity_surfaces"] = surfaces
    return render(tmp_path, data)


def _run(out: Path, root: Path | None = None):
    return subprocess.run(
        [sys.executable, str(out / "scripts/process/check_parity.py"),
         str(root if root is not None else out)],
        capture_output=True, text=True,
    )


def _write(out: Path, name: str, data: dict):
    d = out / PARITY
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(json.dumps(data), encoding="utf-8")


VALID = {
    "capability": "chat",
    "surfaces": {"web": "complete", "mobile": "gap", "cli": "na"},
    "issues": {"mobile": "#42"},
    "notes": "optional free text",
}


def test_module_on_ships_gate_doc_seed(render, tmp_path):
    out = _render(render, tmp_path)
    assert (out / "scripts/process/check_parity.py").is_file()
    assert (out / "docs/process/modules/parity.md").is_file()
    assert (out / PARITY / "capability.example.json").is_file()


def test_module_off_ships_nothing(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    assert not (out / "scripts/process/check_parity.py").exists()
    assert not (out / "docs/process/modules/parity.md").exists()
    # module OFF ships nothing — not even the seed dir (Finding-D discipline)
    assert not (out / PARITY).exists()


def test_answers_records_parity(render, tmp_path):
    out = _render(render, tmp_path)
    assert "parity: true" in (out / ".copier-answers.yml").read_text()


def test_valid_matrix_passes(render, tmp_path):
    out = _render(render, tmp_path)
    _write(out, "chat.json", VALID)
    r = _run(out)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "parity: OK" in r.stdout


def test_gap_without_issue_hard_fails(render, tmp_path):
    out = _render(render, tmp_path)
    _write(out, "chat.json", {"capability": "chat", "surfaces": {"web": "gap"}, "issues": {}})
    r = _run(out)
    assert r.returncode == 1
    assert "gap" in r.stdout
    assert "issue ref" in r.stdout


def test_gap_with_bad_ref_hard_fails(render, tmp_path):
    out = _render(render, tmp_path)
    _write(out, "chat.json", {"capability": "chat", "surfaces": {"web": "gap"}, "issues": {"web": "not-a-ref"}})
    r = _run(out)
    assert r.returncode == 1
    assert "gap" in r.stdout


def test_gap_with_cross_and_url_refs_pass(render, tmp_path):
    out = _render(render, tmp_path)
    _write(out, "chat.json", {
        "capability": "chat",
        "surfaces": {"web": "gap", "mobile": "gap"},
        "issues": {
            "web": "owner/repo#7",
            "mobile": "https://github.com/owner/repo/issues/8",
        },
    })
    r = _run(out)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "parity: OK" in r.stdout


def test_invalid_status_hard_fails(render, tmp_path):
    out = _render(render, tmp_path)
    _write(out, "chat.json", {"capability": "chat", "surfaces": {"web": "bogus"}})
    r = _run(out)
    assert r.returncode == 1
    assert "not in" in r.stdout


def test_capability_stem_mismatch_hard_fails(render, tmp_path):
    out = _render(render, tmp_path)
    # stem 'chatty' != capability 'chat'; surfaces valid so the stem check is reached
    _write(out, "chatty.json", {"capability": "chat", "surfaces": {"web": "na"}})
    r = _run(out)
    assert r.returncode == 1
    assert "filename stem" in r.stdout


def test_bad_types_hard_fail(render, tmp_path):
    out = _render(render, tmp_path)
    d = out / PARITY
    d.mkdir(parents=True, exist_ok=True)
    f = d / "chat.json"

    # surfaces not a dict
    f.write_text(json.dumps({"capability": "chat", "surfaces": ["web"]}), encoding="utf-8")
    assert _run(out).returncode == 1

    # surfaces empty
    f.write_text(json.dumps({"capability": "chat", "surfaces": {}}), encoding="utf-8")
    assert _run(out).returncode == 1

    # non-object
    f.write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")
    r = _run(out)
    assert r.returncode == 1
    assert "JSON object" in r.stdout

    # invalid JSON
    f.write_text("{ not json", encoding="utf-8")
    r = _run(out)
    assert r.returncode == 1
    assert "invalid JSON" in r.stdout

    # non-UTF-8
    f.write_bytes(b"\xff\xfe not utf8")
    r = _run(out)
    assert r.returncode == 1
    assert "UTF-8" in r.stdout


def test_complete_emits_soft_note_not_failure(render, tmp_path):
    out = _render(render, tmp_path)
    _write(out, "chat.json", {"capability": "chat", "surfaces": {"web": "complete"}})
    r = _run(out)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "parity: note:" in r.stdout
    assert "complete" in r.stdout


def test_declared_surfaces_missing_hard_fails(render, tmp_path):
    out = _render(render, tmp_path, surfaces=["web", "mobile", "cli"])
    # covers only web + mobile — cli is a silent omission
    _write(out, "chat.json", {"capability": "chat", "surfaces": {"web": "complete", "mobile": "na"}})
    r = _run(out)
    assert r.returncode == 1
    assert "missing" in r.stdout


def test_declared_surfaces_extra_hard_fails(render, tmp_path):
    out = _render(render, tmp_path, surfaces=["web", "mobile"])
    # 'cli' is not in the declared surface list
    _write(out, "chat.json", {"capability": "chat", "surfaces": {"web": "na", "mobile": "na", "cli": "na"}})
    r = _run(out)
    assert r.returncode == 1
    assert "unknown" in r.stdout


def test_no_declared_surfaces_skips_coverage(render, tmp_path):
    out = _render(render, tmp_path)  # default parity_surfaces == [] -> coverage off
    _write(out, "chat.json", {"capability": "chat", "surfaces": {"foo": "na", "bar": "complete"}})
    r = _run(out)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "parity: OK" in r.stdout


def test_declared_surfaces_non_string_element_no_crash(render, tmp_path):
    # a hand-edited manifest could carry a non-string element; set(declared) would
    # raise TypeError. A malformed list must disable coverage, never crash.
    out = _render(render, tmp_path, surfaces=["web", {"a": "b"}])
    _write(out, "chat.json", {"capability": "chat", "surfaces": {"web": "complete"}})
    r = _run(out)
    assert r.returncode == 0, r.stdout + r.stderr


def test_example_seed_ignored(render, tmp_path):
    out = _render(render, tmp_path)
    d = out / PARITY
    d.mkdir(parents=True, exist_ok=True)
    # a malformed *.example.json must still be skipped
    (d / "broken.example.json").write_text("{ not json", encoding="utf-8")
    r = _run(out)
    assert r.returncode == 0, r.stdout
    assert "no parity entries yet" in r.stdout


def test_empty_registry_soft(render, tmp_path):
    out = _render(render, tmp_path)  # renders the gate script
    empty = tmp_path / "empty_root"
    empty.mkdir()
    r = _run(out, root=empty)  # parity dir absent under this root
    assert r.returncode == 0, r.stdout
    assert "no parity entries yet" in r.stdout


def test_gate_runner_lists_parity(render, tmp_path):
    out = _render(render, tmp_path)
    r = subprocess.run(
        [sys.executable, str(out / "scripts/process/gate_runner.py"), "--list"],
        cwd=out, capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    assert "parity" in r.stdout


def test_neutral_no_kenni_terms(render, tmp_path):
    out = _render(render, tmp_path)
    for rel in [
        "scripts/process/check_parity.py",
        "docs/process/modules/parity.md",
        f"{PARITY}/capability.example.json",
    ]:
        text = (out / rel).read_text()
        for k in KENNI:
            assert k not in text, f"{k} leaked in {rel}"


def test_docdrift_green_with_module_doc(render, tmp_path):
    out = render(tmp_path, {"project_name": "d",
                            "modules": {"doc_drift_gate": True, "parity": True}})
    r = subprocess.run(
        [sys.executable, str(out / "scripts/process/check_doc_drift.py"), str(out)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stdout
