"""SP70: evidence is computed, never typed — attest.py writes the REVIEW line
with the gate's own digest; the gate names a digest no formula produces."""
import hashlib
import importlib.util
import subprocess
import sys

sys.dont_write_bytecode = True


def _git(root, *args, **kw):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                          check=True, **kw)


def _repo(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    _git(out, "init", "-q", "-b", "main")
    _git(out, "config", "user.email", "t@t")
    _git(out, "config", "user.name", "t")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "base")
    _git(out, "checkout", "-q", "-b", "feature")
    (out / ".process-work/plans").mkdir(parents=True, exist_ok=True)
    (out / ".process-work/plans/2026-09-10-widget.md").write_text("# Plan\n\ntier: 2\n\n## Decisions\n")
    (out / "widget.py").write_text("def widget():\n    return 42\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "feat: widget")
    base = _git(out, "merge-base", "main", "HEAD").stdout.strip()
    head = _git(out, "rev-parse", "HEAD").stdout.strip()
    return out, base, head


def _load_gate(root):
    spec = importlib.util.spec_from_file_location("check_review", root / "scripts/process/check_review.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _attest(root, *extra):
    return subprocess.run([sys.executable, str(root / "scripts/process/attest.py"),
                           "--work", "widget", "--tier", "2", "--reviewer", "fresh",
                           "--model", "cross", "--independence", "bundle,non-implementing",
                           "--verdict", "pass", "--round", "1", *extra, "."],
                          cwd=root, capture_output=True, text=True)


def _gate(root):
    return subprocess.run([sys.executable, str(root / "scripts/process/check_review.py"), "."],
                          cwd=root, capture_output=True, text=True)


def test_attest_computes_digest_and_gate_verifies_it(render, tmp_path):
    out, base, head = _repo(render, tmp_path)
    r = _attest(out, "--base", base, "--head", head, "--note", "Reviewed from the bundle.")
    assert r.returncode == 0, r.stdout + r.stderr
    gate = _load_gate(out)
    assert f"diff={gate.artifact_digest(out, base, head)}" in r.stdout
    shard = next((out / ".process-work/journal").glob("*.md"))
    assert "Reviewed from the bundle." in shard.read_text()
    assert _gate(out).returncode == 0, _gate(out).stdout


def test_attest_refuses_a_stale_bundle(render, tmp_path):
    out, base, head = _repo(render, tmp_path)
    bundle = out / ".process-work/bundle.md"
    bundle.write_text(f"# Review bundle\n\nREVIEW_ARTIFACT base={base} head={head} diff={'a' * 64}\n")
    r = _attest(out, "--bundle", str(bundle))
    assert r.returncode == 1 and "REFUSED" in r.stderr and "stale" in r.stderr
    assert not list((out / ".process-work/journal").glob("*.md"))


def test_attest_takes_base_head_from_a_fresh_bundle(render, tmp_path):
    out, base, head = _repo(render, tmp_path)
    b = subprocess.run([sys.executable, str(out / "scripts/process/make_review_bundle.py"),
                        "--base", "main", "--skip-preflight"], cwd=out, capture_output=True, text=True)
    assert b.returncode == 0, b.stderr
    bundle = out / ".process-work/bundle.md"
    bundle.write_text(b.stdout)
    r = _attest(out, "--bundle", str(bundle))
    assert r.returncode == 0, r.stderr
    assert f"head={head}" in r.stdout
    assert _gate(out).returncode == 0


def test_fabricated_digest_is_named_and_hard(render, tmp_path):
    out, base, head = _repo(render, tmp_path)
    (out / ".process-work/journal").mkdir(parents=True, exist_ok=True)
    (out / ".process-work/journal/2026-09-10.md").write_text(
        f"REVIEW work=widget tier=2 reviewer=fresh model=cross "
        f"independence=bundle,non-implementing verdict=pass round=1 "
        f"base={base} head={head} diff={'b' * 64}\n")
    r = _gate(out)
    assert r.returncode == 1
    assert "FABRICATED" in r.stdout and "matches no formula" in r.stdout


def test_legacy_unpinned_digest_still_verifies(render, tmp_path):
    out, base, head = _repo(render, tmp_path)
    raw = subprocess.run(["git", "diff", "--binary", f"{base}...{head}"], cwd=out,
                         capture_output=True, check=True).stdout
    (out / ".process-work/journal").mkdir(parents=True, exist_ok=True)
    (out / ".process-work/journal/2026-09-10.md").write_text(
        f"REVIEW work=widget tier=2 reviewer=fresh model=cross "
        f"independence=bundle,non-implementing verdict=pass round=1 "
        f"base={base} head={head} diff={hashlib.sha256(raw).hexdigest()}\n")
    assert _gate(out).returncode == 0


def test_canonical_digest_survives_git_config_drift(render, tmp_path):
    # the other clone: patience diff, no prefix, short abbrev, renames on
    out, base, head = _repo(render, tmp_path)
    r = _attest(out, "--base", base, "--head", head)
    assert r.returncode == 0, r.stderr
    for k, v in (("diff.algorithm", "patience"), ("diff.noprefix", "true"),
                 ("diff.mnemonicPrefix", "true"), ("core.abbrev", "7"),
                 ("diff.renames", "true"), ("diff.context", "5")):
        _git(out, "config", k, v)
    g = _gate(out)
    assert g.returncode == 0, g.stdout
