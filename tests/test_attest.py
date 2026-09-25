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
    shard = next((out / ".process-work/journal").rglob("*.md"))
    assert shard.parent.name == "feature"  # a work branch writes its own shard
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


def test_an_uncomputable_digest_in_a_shallow_clone_is_a_note(render, tmp_path, monkeypatch):
    # a cloud session clones shallow: the three-dot diff lacks history there —
    # unverifiable, not fabricated; outside a shallow clone it stays hard
    out, base, head = _repo(render, tmp_path)
    gate = _load_gate(out)
    record = [(1, {"base": base, "head": head, "diff": "sha256:" + "0" * 64})]
    monkeypatch.setattr(gate, "artifact_digest", lambda *a: None)
    hard, soft = gate._integrity_violations("j.md", out, record)
    assert hard and "could not be computed" in hard[0]
    real = gate._git_bytes
    monkeypatch.setattr(gate, "_git_bytes", lambda root, *a: b"true\n"
                        if a == ("rev-parse", "--is-shallow-repository") else real(root, *a))
    hard, soft = gate._integrity_violations("j.md", out, record)
    assert not hard and soft and "shallow clone" in soft[0]


def test_code_after_the_reviewed_head_is_stale_on_the_merge_push(render, tmp_path):
    # observed downstream: a fix committed after the attested pass merged green
    import os
    out, base, head = _repo(render, tmp_path)
    r = _attest(out, "--base", base, "--head", head, "--note", "Reviewed.")
    assert r.returncode == 0, r.stderr
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "docs: attest")
    gate = [sys.executable, str(out / "scripts/process/check_review.py"), "."]
    env = {**os.environ, "PROCESS_PUSH_TARGETS": "refs/heads/main"}
    r = subprocess.run(gate, cwd=out, capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stdout  # the attestation commit is bookkeeping
    (out / "widget.py").write_text("def widget():\n    return 43\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "fix: after the review")
    r = subprocess.run(gate, cwd=out, capture_output=True, text=True, env=env)
    assert r.returncode == 1 and "code changed after the reviewed head (widget.py)" in r.stdout, r.stdout


def test_a_fellow_passengers_files_are_not_this_works_late_code(render, tmp_path):
    # train 34 downstream: two passengers, each reviewed; the merge push named
    # the other passenger's files as unreviewed code of the first
    import os
    out, base, head = _repo(render, tmp_path)
    assert _attest(out, "--base", base, "--head", head).returncode == 0
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "docs: attest")
    _git(out, "checkout", "-q", "-b", "other", "main")
    (out / "other.py").write_text("x = 1\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "feat: other passenger")
    _git(out, "checkout", "-q", "-b", "train", "main")
    _git(out, "merge", "-q", "--no-ff", "--no-edit", "feature")
    _git(out, "merge", "-q", "--no-ff", "--no-edit", "other")
    gate = [sys.executable, str(out / "scripts/process/check_review.py"), "."]
    env = {**os.environ, "PROCESS_PUSH_TARGETS": "refs/heads/main"}
    r = subprocess.run(gate, cwd=out, capture_output=True, text=True, env=env)
    assert "code changed after the reviewed head" not in r.stdout, r.stdout
    # the work's own fix after the review still counts, merged or not
    _git(out, "checkout", "-q", "feature")
    (out / "widget.py").write_text("def widget():\n    return 45\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "fix: after the review")
    _git(out, "checkout", "-q", "train")
    _git(out, "merge", "-q", "--no-ff", "--no-edit", "feature")
    r = subprocess.run(gate, cwd=out, capture_output=True, text=True, env=env)
    assert "code changed after the reviewed head (widget.py)" in r.stdout, r.stdout

def test_finish_blocks_a_stale_review(render, tmp_path):
    out, base, head = _repo(render, tmp_path)
    assert _attest(out, "--base", base, "--head", head).returncode == 0
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "docs: attest")
    (out / "widget.py").write_text("def widget():\n    return 44\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "fix: after the review")
    r = subprocess.run([sys.executable, str(out / "scripts/process/finish.py")],
                       cwd=out, capture_output=True, text=True)
    assert "code changed after the reviewed head" in r.stdout + r.stderr


def _journal(out):
    return "".join(f.read_text() for f in (out / ".process-work/journal").rglob("*.md"))


def test_the_round_is_counted_from_recorded_blocks_not_claimed(render, tmp_path):
    # downstream: re-checks after a pass and rebases were counted as rounds,
    # and blocking rounds were skipped in the journal
    out, base, head = _repo(render, tmp_path)
    ab = ("--base", base, "--head", head)
    assert _attest(out, *ab, "--verdict", "block").returncode == 0
    r = _attest(out, *ab, "--round", "3")
    assert r.returncode == 1 and "this is round 2" in r.stderr
    # the fix of round 1 names no cause yet
    r = _attest(out, *ab, "--round", "2")
    assert r.returncode == 1 and "no root cause for the fix of blocking round(s) 1" in r.stderr
    plan = out / ".process-work/plans/2026-09-10-widget.md"
    plan.write_text(plan.read_text() + "\nROOT-CAUSE work=widget round=1: the cache key ignored the tenant "
                    "— test_widget_per_tenant failed before the fix\n")
    r = _attest(out, *ab, "--round", "2")
    assert r.returncode == 0, r.stderr
    assert "verdict=pass round=2" in _journal(out)
    # a re-check after the pass (a rebase, a short look) keeps the round
    r = _attest(out, *ab, "--round", "3")
    assert r.returncode == 1 and "this is round 2" in r.stderr
    assert _attest(out, *ab, "--round", "2").returncode == 0


def test_an_exception_is_recorded_and_plan_reviews_count_apart(render, tmp_path):
    out, base, head = _repo(render, tmp_path)
    ab = ("--base", base, "--head", head)
    assert _attest(out, *ab, "--verdict", "block").returncode == 0
    r = _attest(out, *ab, "--round", "2", "--exception", "owner decided: cosmetic fix only")
    assert r.returncode == 0, r.stderr
    j = _journal(out)
    assert "REVIEW-EXCEPTION work=widget round=2: owner decided: cosmetic fix only" in j
    assert "no root cause" in j
    r = _attest(out, *ab, "--plan-review", "--round", "1")
    assert r.returncode == 0, r.stderr
    assert "work=widget-plan" in r.stdout and "round=1" in r.stdout


def test_several_lenses_blocking_one_round_count_once(render, tmp_path):
    out, base, head = _repo(render, tmp_path)
    ab = ("--base", base, "--head", head)
    for reviewer in ("lens-a", "lens-b", "lens-c"):
        assert _attest(out, *ab, "--verdict", "block", "--reviewer", reviewer).returncode == 0
    plan = out / ".process-work/plans/2026-09-10-widget.md"
    plan.write_text(plan.read_text() + "\nROOT-CAUSE work=widget round=1: x — test_x\n")
    r = _attest(out, *ab, "--round", "2")
    assert r.returncode == 0, r.stderr


def test_an_exception_is_written_even_when_no_rule_trips(render, tmp_path):
    # a third round granted by the owner trips no attest rule — still counted
    out, base, head = _repo(render, tmp_path)
    r = _attest(out, "--base", base, "--head", head, "--exception", "owner: third round granted")
    assert r.returncode == 0, r.stderr
    assert ("REVIEW-EXCEPTION work=widget round=1: owner: third round granted "
            "(overrides: no attest rule tripped)") in _journal(out)
