import json
import subprocess
import sys
from pathlib import Path

KENNI = ["Kenni", "KenniNext", "Seb", "Signal", "SvelteKit", "user_id=1", "surface:ios"]

CONTRACTS = "docs/process/capability-contracts"


def _render(render, tmp_path, **mods):
    m = {"contract_first": True}
    m.update(mods)
    return render(tmp_path, {"project_name": "d", "modules": m})


def _run(out: Path, root: Path | None = None):
    return subprocess.run(
        [sys.executable, str(out / "scripts/process/check_capability_contracts.py"),
         str(root if root is not None else out)],
        capture_output=True, text=True,
    )


def _write_spec(out: Path, rel: str, text: str):
    p = out / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _write_contract(out: Path, name: str, data: dict):
    d = out / CONTRACTS
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(json.dumps(data), encoding="utf-8")


VALID = {
    "capability": "chat",
    "surfaces": ["web", "mobile"],
    "spec": "docs/api/openapi.json",
    "symbols": ["ChatMessage", "ChatSession"],
    "notes": "optional free text",
}


def test_module_on_ships_gate_and_doc(render, tmp_path):
    out = _render(render, tmp_path)
    assert (out / "scripts/process/check_capability_contracts.py").is_file()
    assert (out / "docs/process/modules/contract-first.md").is_file()
    assert (out / CONTRACTS / "capability.example.json").is_file()


def test_module_off_ships_neither(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    assert not (out / "scripts/process/check_capability_contracts.py").exists()
    assert not (out / "docs/process/modules/contract-first.md").exists()
    # module OFF ships nothing — not even the seed dir (mirror the sibling modules)
    assert not (out / CONTRACTS).exists()


def test_answers_records_contract_first(render, tmp_path):
    out = _render(render, tmp_path)
    assert "contract_first: true" in (out / ".copier-answers.yml").read_text()


def test_valid_contract_passes(render, tmp_path):
    out = _render(render, tmp_path)
    _write_spec(out, "docs/api/openapi.json", "openapi spec with ChatMessage and ChatSession dtos")
    _write_contract(out, "chat.json", VALID)
    r = _run(out)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "contract-first: OK" in r.stdout


def test_missing_symbol_hard_fails(render, tmp_path):
    out = _render(render, tmp_path)
    _write_spec(out, "docs/api/openapi.json", "openapi spec with ChatMessage only")
    _write_contract(out, "chat.json", VALID)  # ChatSession absent from spec
    r = _run(out)
    assert r.returncode == 1
    assert "ChatSession" in r.stdout


def test_spec_not_committed_hard_fails(render, tmp_path):
    out = _render(render, tmp_path)
    _write_contract(out, "chat.json", VALID)  # spec file never written
    r = _run(out)
    assert r.returncode == 1
    assert "not committed" in r.stdout


def test_spec_escape_hard_fails(render, tmp_path):
    out = _render(render, tmp_path)
    _write_contract(out, "chat.json", {**VALID, "spec": "../evil"})
    r = _run(out)
    assert r.returncode == 1
    assert "escapes" in r.stdout


def test_capability_stem_mismatch_hard_fails(render, tmp_path):
    out = _render(render, tmp_path)
    _write_spec(out, "docs/api/openapi.json", "ChatMessage ChatSession")
    _write_contract(out, "chatty.json", VALID)  # stem 'chatty' != capability 'chat'
    r = _run(out)
    assert r.returncode == 1
    assert "filename stem" in r.stdout


def test_bad_types_hard_fail(render, tmp_path):
    out = _render(render, tmp_path)
    d = out / CONTRACTS
    d.mkdir(parents=True, exist_ok=True)
    f = d / "chat.json"

    # surfaces not a list
    f.write_text(json.dumps({**VALID, "surfaces": "web"}), encoding="utf-8")
    assert _run(out).returncode == 1

    # symbols empty
    f.write_text(json.dumps({**VALID, "symbols": []}), encoding="utf-8")
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


def test_example_seed_ignored(render, tmp_path):
    out = _render(render, tmp_path)
    d = out / CONTRACTS
    d.mkdir(parents=True, exist_ok=True)
    # a malformed *.example.json must still be skipped
    (d / "broken.example.json").write_text("{ not json", encoding="utf-8")
    r = _run(out)
    assert r.returncode == 0, r.stdout
    assert "no capability contracts yet" in r.stdout


def test_empty_registry_soft(render, tmp_path):
    out = _render(render, tmp_path)  # renders the gate script
    empty = tmp_path / "empty_root"
    empty.mkdir()
    r = _run(out, root=empty)  # contracts dir absent under this root
    assert r.returncode == 0, r.stdout
    assert "no capability contracts yet" in r.stdout


def test_gate_runner_lists_contract_first(render, tmp_path):
    out = _render(render, tmp_path)
    r = subprocess.run(
        [sys.executable, str(out / "scripts/process/gate_runner.py"), "--list"],
        cwd=out, capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    assert "contract-first" in r.stdout


def test_neutral_no_kenni_terms(render, tmp_path):
    out = _render(render, tmp_path)
    for rel in [
        "scripts/process/check_capability_contracts.py",
        "docs/process/modules/contract-first.md",
        f"{CONTRACTS}/capability.example.json",
    ]:
        text = (out / rel).read_text()
        for k in KENNI:
            assert k not in text, f"{k} leaked in {rel}"


def test_docdrift_green_with_module_doc(render, tmp_path):
    out = render(tmp_path, {"project_name": "d",
                            "modules": {"doc_drift_gate": True, "contract_first": True}})
    r = subprocess.run(
        [sys.executable, str(out / "scripts/process/check_doc_drift.py"), str(out)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stdout


def test_short_symbol_needs_word_boundary(render, tmp_path):
    # audit false-green: bare substring let short symbols pass by coincidence —
    # "get" must NOT be satisfied by "getHealth", "p" by "paths", "3.0" by "3.0.0"
    out = _render(render, tmp_path)
    _write_spec(out, "docs/api/openapi.json",
                '{"paths": {"getHealth": {}}, "openapi": "3.0.0"}')
    _write_contract(out, "chat.json", {**VALID, "symbols": ["get", "p", "3.0"]})
    r = _run(out)
    assert r.returncode == 1
    assert "not found in spec" in r.stdout


def test_word_boundary_symbol_still_matches(render, tmp_path):
    out = _render(render, tmp_path)
    _write_spec(out, "docs/api/openapi.json", "components: ChatMessage and ChatSession here")
    _write_contract(out, "chat.json", VALID)
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_short_symbol_get_rejected(render, tmp_path):
    # pin the real closed direction: "get" must NOT be satisfied by "getHealth"
    out = _render(render, tmp_path)
    _write_spec(out, "docs/api/openapi.json", '{"paths": {"getHealth": {}}}')
    _write_contract(out, "chat.json", {**VALID, "symbols": ["get"]})
    r = _run(out)
    assert r.returncode == 1
    assert "get" in r.stdout and "not found in spec" in r.stdout
