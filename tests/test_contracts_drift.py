import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

KENNI = ["Kenni", "KenniNext", "Seb", "Signal", "SvelteKit", "user_id=1", "surface:ios"]


def _render(render, tmp_path, **mods):
    m = {"contracts_drift": True}
    m.update(mods)
    return render(tmp_path, {"project_name": "d", "modules": m})


def _run(out: Path, path=None, prepend=None):
    env = dict(os.environ)
    if path is not None:
        env["PATH"] = path
    elif prepend:
        env["PATH"] = f"{prepend}{os.pathsep}" + env["PATH"]
    return subprocess.run(
        [sys.executable, str(out / "scripts/process/check_contracts.py"), str(out)],
        capture_output=True, text=True, env=env,
    )


def _sha256(b: bytes) -> str:
    return "sha256:" + hashlib.sha256(b).hexdigest()


def _contract(out: Path, cid="orders-api", kind="rest", artifact="contracts/api.json",
              pin="registry:v1", verify=None, artifact_bytes=b"{}", fname=None, drop=None):
    """Write a contract declaration (+ its artifact file) into a render."""
    if artifact is not None and artifact_bytes is not None:
        ap = out / artifact
        ap.parent.mkdir(parents=True, exist_ok=True)
        ap.write_bytes(artifact_bytes)
    d = {"id": cid, "kind": kind, "artifact": artifact, "pin": pin}
    if verify is not None:
        d["verify"] = verify
    for k in (drop or []):
        d.pop(k, None)
    reg = out / "docs/process/contracts"
    reg.mkdir(parents=True, exist_ok=True)
    (reg / f"{fname or cid}.json").write_text(json.dumps(d))
    return d


def test_no_contracts_note(render, tmp_path):
    out = _render(render, tmp_path)
    r = _run(out)
    assert r.returncode == 0, r.stdout
    assert "no contracts yet" in r.stdout


def test_valid_opaque_pin_ok(render, tmp_path):
    out = _render(render, tmp_path)
    _contract(out, pin="registry:v1")
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_missing_required_field_is_hard(render, tmp_path):
    out = _render(render, tmp_path)
    _contract(out, drop=["kind"])
    r = _run(out)
    assert r.returncode == 1
    assert "'kind'" in r.stdout


def test_malformed_json_is_hard(render, tmp_path):
    out = _render(render, tmp_path)
    reg = out / "docs/process/contracts"
    reg.mkdir(parents=True, exist_ok=True)
    (reg / "broken.json").write_text("{not json")
    r = _run(out)
    assert r.returncode == 1
    assert "invalid JSON" in r.stdout


def test_id_must_equal_filename_stem(render, tmp_path):
    out = _render(render, tmp_path)
    _contract(out, cid="not-the-stem", fname="orders-api")
    r = _run(out)
    assert r.returncode == 1
    assert "filename stem" in r.stdout


def test_missing_artifact_is_hard(render, tmp_path):
    out = _render(render, tmp_path)
    _contract(out, artifact="contracts/gone.json", artifact_bytes=None)  # declaration but no file
    r = _run(out)
    assert r.returncode == 1
    assert "artifact" in r.stdout


def test_artifact_escaping_repo_is_hard(render, tmp_path):
    out = _render(render, tmp_path)
    _contract(out, artifact="../escape.json", artifact_bytes=None)
    r = _run(out)
    assert r.returncode == 1
    assert "escapes" in r.stdout


def test_sha256_pin_match_is_clean(render, tmp_path):
    out = _render(render, tmp_path)
    body = b'{"openapi": "3.1.0"}'
    _contract(out, pin=_sha256(body), artifact_bytes=body)
    r = _run(out)
    assert r.returncode == 0, r.stdout
    assert "opaque pin" not in r.stdout
    assert "changed but pin" not in r.stdout


def test_sha256_pin_mismatch_is_hard(render, tmp_path):
    out = _render(render, tmp_path)
    _contract(out, pin=_sha256(b"OLD"), artifact_bytes=b"NEW-the-artifact-was-edited")
    r = _run(out)
    assert r.returncode == 1
    assert "changed but pin not updated" in r.stdout


def test_opaque_pin_is_soft(render, tmp_path):
    out = _render(render, tmp_path)
    _contract(out, pin="registry:v3")
    r = _run(out)
    assert r.returncode == 0, r.stdout
    assert "opaque pin" in r.stdout


def test_sha512_pin_match_is_clean(render, tmp_path):
    out = _render(render, tmp_path)
    body = b"schema-bytes"
    pin = "sha512:" + hashlib.sha512(body).hexdigest()
    _contract(out, pin=pin, artifact_bytes=body)
    r = _run(out)
    assert r.returncode == 0, r.stdout
    assert "opaque pin" not in r.stdout


def _stub_cmd(bindir: Path, name: str, code: int):
    bindir.mkdir(parents=True, exist_ok=True)
    p = bindir / name
    p.write_text(f"#!/bin/sh\nexit {code}\n")
    p.chmod(0o755)


def test_verify_absent_notes(render, tmp_path):
    out = _render(render, tmp_path)
    _contract(out, pin=_sha256(b"{}"), artifact_bytes=b"{}")  # clean pin, no verify
    r = _run(out)
    assert r.returncode == 0, r.stdout
    assert "no verify command" in r.stdout


def test_verify_zero_no_note(render, tmp_path):
    out = _render(render, tmp_path)
    _contract(out, pin=_sha256(b"{}"), artifact_bytes=b"{}", verify="okcheck")
    bindir = tmp_path / "bin"
    _stub_cmd(bindir, "okcheck", 0)
    r = _run(out, prepend=str(bindir))
    assert r.returncode == 0, r.stdout
    assert "no verify command" not in r.stdout
    assert "nonconformance" not in r.stdout


def test_verify_nonzero_is_soft(render, tmp_path):
    # load-bearing must-not-hard-fail guard: a verify that reports drift -> note, exit 0
    out = _render(render, tmp_path)
    _contract(out, pin=_sha256(b"{}"), artifact_bytes=b"{}", verify="failcheck")
    bindir = tmp_path / "bin"
    _stub_cmd(bindir, "failcheck", 1)
    r = _run(out, prepend=str(bindir))
    assert r.returncode == 0, r.stdout
    assert "nonconformance" in r.stdout


def test_verify_unlaunchable_is_soft(render, tmp_path):
    # load-bearing must-not-hard-fail guard: a command not on PATH -> note, exit 0
    out = _render(render, tmp_path)
    _contract(out, pin=_sha256(b"{}"), artifact_bytes=b"{}", verify="definitely-not-a-real-cmd-xyz")
    r = _run(out)
    assert r.returncode == 0, r.stdout
    assert "could not run verify" in r.stdout


def _runner_list(out: Path):
    return subprocess.run(
        [sys.executable, str(out / "scripts/process/gate_runner.py"), "--list"],
        cwd=out, capture_output=True, text=True,
    )


def test_runner_lists_contracts_when_on(render, tmp_path):
    out = _render(render, tmp_path)
    r = _runner_list(out)
    assert r.returncode == 0, r.stderr
    assert "contracts-drift" in r.stdout


def test_runner_skips_contracts_when_off(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    r = _runner_list(out)
    assert r.returncode == 0, r.stderr
    assert "contracts-drift" not in r.stdout
