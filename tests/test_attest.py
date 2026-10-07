"""SP70: evidence is written, never typed — attest.py writes the REVIEW line
with the reviewed range (base, head); the gate reads what is committed after it."""
import importlib.util
import subprocess

import pytest
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


def test_attest_writes_the_range_and_the_gate_accepts_it(render, tmp_path):
    out, base, head = _repo(render, tmp_path)
    r = _attest(out, "--base", base, "--head", head, "--note", "Reviewed from the bundle.")
    assert r.returncode == 0, r.stdout + r.stderr
    assert f"base={base} head={head}" in r.stdout and "diff=" not in r.stdout
    shard = next((out / ".process-work/journal").rglob("*.md"))
    assert shard.parent.name == "feature"  # a work branch writes its own shard
    assert "Reviewed from the bundle." in shard.read_text()
    assert _gate(out).returncode == 0, _gate(out).stdout



def test_a_full_round_is_written_only_against_the_fork_point(render, tmp_path):
    """#160: base=head^ reviews a slice and recorded it as the whole branch."""
    out, base, head = _repo(render, tmp_path)
    (out / "widget.py").write_text("def widget():\n    return 43\n")
    _git(out, "commit", "-qam", "fix: widget")
    head = _git(out, "rev-parse", "HEAD").stdout.strip()
    slice_base = _git(out, "rev-parse", "HEAD^").stdout.strip()
    r = _attest(out, "--base", slice_base, "--head", head)
    assert r.returncode == 1 and "is not the fork point" in r.stderr, r.stderr
    assert not any("REVIEW work=widget" in p.read_text()
                   for p in (out / ".process-work/journal").rglob("*.md"))
    bundle = out / ".process-work/bundle.md"
    bundle.write_text(f"REVIEW_ARTIFACT base={slice_base} head={head}\n")
    r = _attest(out, "--bundle", str(bundle))
    assert r.returncode == 1 and "is not the fork point" in r.stderr, r.stderr
    r = _attest(out, "--base", base, "--head", head)
    assert r.returncode == 0, r.stderr
    assert f"base={base}" in r.stdout



def test_a_full_round_of_an_integrated_head_is_an_audit_and_stands(render, tmp_path):
    """Refute: a head main already contains (an audit of a merged range) has no fork to bind."""
    out, base, head = _repo(render, tmp_path)
    _git(out, "branch", "-f", "main", head)
    r = _attest(out, "--base", base, "--head", head)
    assert r.returncode == 0, r.stderr


def test_a_forged_integration_ref_at_the_head_is_no_audit(render, tmp_path):
    """Refute 2: origin/main forged to the head read as 'merged'; local main still forks it."""
    out, _base, _head = _repo(render, tmp_path)
    (out / "widget.py").write_text("def widget():\n    return 43\n")
    _git(out, "commit", "-qam", "fix: widget")
    head = _git(out, "rev-parse", "HEAD").stdout.strip()
    _git(out, "update-ref", "refs/remotes/origin/main", head)
    r = _attest(out, "--base", _git(out, "rev-parse", "HEAD^").stdout.strip(), "--head", head)
    assert r.returncode == 1 and "is not the fork point" in r.stderr, r.stderr


def test_a_full_round_without_an_integration_ref_names_set_head(render, tmp_path):
    out, base, head = _repo(render, tmp_path)
    _git(out, "branch", "-m", "main", "trunk")  # no main, no origin/HEAD
    r = _attest(out, "--base", base, "--head", head)
    assert r.returncode == 1 and "git remote set-head origin -a" in r.stderr, r.stderr


def test_a_stacked_branch_is_told_to_rebase_onto_the_integration_branch(render, tmp_path):
    out, _base, lower = _repo(render, tmp_path)
    _git(out, "checkout", "-q", "-b", "stacked")
    (out / "more.py").write_text("x = 1\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-qm", "feat: more")
    head = _git(out, "rev-parse", "HEAD").stdout.strip()
    r = _attest(out, "--base", lower, "--head", head)
    assert r.returncode == 1 and "is not the fork point" in r.stderr, r.stderr
    assert "stacked branch rebases onto" in r.stderr and "Tier 3" in r.stderr, r.stderr


def test_attest_reads_an_older_bundle_line_and_refuses_an_older_delta(render, tmp_path):
    """v2.53: a bundle's line carries base and head; an older line's `diff=` is read
    past. An older delta bundle named the last round's head as its base — a slice."""
    out, base, head = _repo(render, tmp_path)
    bundle = out / ".process-work/bundle.md"
    bundle.write_text(f"# Review bundle\n\nREVIEW_ARTIFACT base={base} head={head} diff={'a' * 64}\n")
    r = _attest(out, "--bundle", str(bundle), "--dry-run")
    assert r.returncode == 0 and f"base={base} head={head}" in r.stdout, r.stderr
    bundle.write_text(f"REVIEW_ARTIFACT base={base} head={head} diff={'a' * 64} mode=delta\n")
    r = _attest(out, "--bundle", str(bundle))
    assert r.returncode == 1 and "older delta bundle" in r.stderr, r.stderr
    missing = "f" * 40
    r = _attest(out, "--base", base, "--head", missing)
    assert r.returncode == 1 and "does not exist in this clone" in r.stderr, r.stderr
    assert not list((out / ".process-work/journal").rglob("*.md"))



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


def test_an_older_record_with_a_digest_stays_valid(render, tmp_path):
    """v2.53: the digest is read and ignored — it was a function of base and head.
    No record written before turns invalid; a wrong one no longer reds the gate."""
    out, base, head = _repo(render, tmp_path)
    (out / ".process-work/journal").mkdir(parents=True, exist_ok=True)
    (out / ".process-work/journal/2026-09-10.md").write_text(
        f"REVIEW work=widget tier=2 reviewer=fresh model=cross "
        f"independence=bundle,non-implementing verdict=pass round=1 "
        f"base={base} head={head} diff={'b' * 64} mode=full\n")
    r = _gate(out)
    assert r.returncode == 0, r.stdout
    assert "FABRICATED" not in r.stdout



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
    # a merge train with two reviewed passengers: the merge push named
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
    _git(out, "checkout", "-q", "-b", "train/a", "main")
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
    _git(out, "checkout", "-q", "train/a")
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


def test_a_number_no_plan_names_is_refused_as_a_likely_pr_number(render, tmp_path):
    """Rounds attested as work=<PR number> matched no plan, so no gate counted them."""
    out, base, head = _repo(render, tmp_path)
    r = _attest(out, "--base", base, "--head", head, "--work", "26")
    assert r.returncode == 1, r.stdout + r.stderr
    assert "work=26 names no plan or issue — it looks like a PR number" in r.stderr
    assert "Active plans: 2026-09-10-widget, widget" in r.stderr
    assert not (out / ".process-work/journal").exists() or "work=26" not in _journal(out)
    r = _attest(out, "--base", base, "--head", head, "--work", "gizmo")  # a slug: a note only
    assert r.returncode == 0 and "work=gizmo names no plan" in r.stderr, r.stderr
    _git(out, "checkout", "-q", "-b", "26-fix")  # the branch leads with the issue
    r = _attest(out, "--base", base, "--head", head, "--work", "26")
    assert r.returncode == 0, r.stderr
    assert "REVIEW work=26 " in _journal(out)


_BLOCK = ("REVIEW work={w} tier=2 reviewer=r model=m independence=bundle,non-implementing "
          "verdict=block round=1\n")


def test_rounds_of_another_plan_of_the_same_issue_do_not_count(render, tmp_path):
    """Refute: expanding `--work 26` over every plan of issue 26 lent an archived plan's
    blocked round (and its ROOT-CAUSE) to the active plan."""
    out, base, head = _repo(render, tmp_path)
    plans = out / ".process-work/plans"
    (plans / "archive").mkdir(exist_ok=True)
    (plans / "archive/2026-08-01-alpha.md").write_text("# Plan\n\ntier: 2\nissue: #26\n")
    widget = plans / "2026-09-10-widget.md"
    widget.write_text(widget.read_text().replace("tier: 2\n", "tier: 2\nissue: #26\n"))
    (out / ".process-work/journal").mkdir(parents=True, exist_ok=True)
    (out / ".process-work/journal/old.md").write_text(
        _BLOCK.format(w="alpha") + "ROOT-CAUSE work=alpha round=1: x — test_x failed before\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-qm", "two plans of #26")
    # a claimed round 2 is written as round 1: no round of THIS work blocked
    r = _attest(out, "--base", base, "--head", head, "--work", "26", "--round", "2", "--dry-run")
    assert r.returncode == 0 and "written as round 1" in r.stderr and "round=1" in r.stdout, r.stdout + r.stderr
    # two ACTIVE plans of #26: the branch's slug picks one, else the literal id alone
    (plans / "2026-09-11-gizmo.md").write_text("# Plan\n\ntier: 2\nissue: #26\n")
    (out / ".process-work/journal/old.md").write_text(_BLOCK.format(w="widget"))
    _git(out, "add", "-A")
    _git(out, "commit", "-qm", "gizmo")
    r = _attest(out, "--base", base, "--head", head, "--work", "26", "--round", "2", "--dry-run")
    assert r.returncode == 0 and "written as round 1" in r.stderr, r.stderr  # ambiguous: literal
    _git(out, "checkout", "-q", "-b", "26-widget")
    r = _attest(out, "--base", base, "--head", head, "--work", "26", "--round", "2", "--dry-run")
    assert r.returncode == 0 and "written as round" not in r.stderr, r.stderr
    assert "no root cause for the fix of blocking round(s) 1" in r.stderr and "round=2" in r.stdout, r.stderr


def test_an_owner_exception_attests_planless_issue_work(render, tmp_path):
    out, base, head = _repo(render, tmp_path)
    r = _attest(out, "--base", base, "--head", head, "--work", "26")
    assert r.returncode == 1 and '--exception "<reason>"' in r.stderr, r.stderr
    r = _attest(out, "--base", base, "--head", head, "--work", "26",
                "--exception", "hotfix issue without a plan")
    assert r.returncode == 0, r.stderr
    journal = _journal(out)
    assert "REVIEW-EXCEPTION work=26 round=1: hotfix issue without a plan (overrides: work=26 " in journal
    assert "REVIEW work=26 " in journal


@pytest.mark.parametrize("decl", ["**#42**", "[#42](https://github.com/o/r/issues/42)", "#42,"])
def test_a_decorated_issue_line_is_a_work_id(render, tmp_path, decl):
    out, base, head = _repo(render, tmp_path)
    plan = out / ".process-work/plans/2026-09-10-widget.md"
    plan.write_text(plan.read_text().replace("tier: 2\n", f"tier: 2\nissue: {decl}\n"))
    _git(out, "commit", "-qam", "issue line")
    r = _attest(out, "--base", base, "--head", head, "--work", "42")
    assert r.returncode == 0, r.stderr
    assert "42" in _load_gate(out)._plan_work_ids("2026-09-10-widget", plan.read_text(), include_dedated=True)


def test_the_round_is_counted_from_recorded_blocks_not_claimed(render, tmp_path):
    # downstream: re-checks after a pass and rebases were counted as rounds,
    # and blocking rounds were skipped in the journal
    out, base, head = _repo(render, tmp_path)
    ab = ("--base", base, "--head", head)
    assert _attest(out, *ab, "--verdict", "block").returncode == 0
    r = _attest(out, *ab, "--round", "3", "--dry-run")
    assert r.returncode == 0 and "written as round 2" in r.stderr and "round=2" in r.stdout, r.stderr
    # the fix of round 1 names no cause yet: a note, never a refusal
    r = _attest(out, *ab, "--round", "2", "--dry-run")
    assert r.returncode == 0 and "no root cause for the fix of blocking round(s) 1" in r.stderr
    plan = out / ".process-work/plans/2026-09-10-widget.md"
    plan.write_text(plan.read_text() + "\nROOT-CAUSE work=widget round=1: the cache key ignored the tenant "
                    "— test_widget_per_tenant failed before the fix\n")
    r = _attest(out, *ab, "--round", "2")
    assert r.returncode == 0 and "note —" not in r.stderr, r.stderr
    assert "verdict=pass round=2" in _journal(out)
    # a re-check after the pass (a rebase, a short look) keeps the round
    r = _attest(out, *ab, "--round", "3")
    assert r.returncode == 0 and "written as round 2" in r.stderr
    assert "round=3" not in _journal(out)


def test_a_mislabelled_cause_after_a_pass_costs_no_round(render, tmp_path):
    """Downstream (#2396 R6): two families passed, the fix was closed, and attest
    refused the record because the ROOT-CAUSE line said round=6 instead of 5 —
    a fix session and a re-check for a label. The verdict is written; the note
    names what is off."""
    out, base, head = _repo(render, tmp_path)
    ab = ("--base", base, "--head", head)
    assert _attest(out, *ab, "--verdict", "block").returncode == 0
    plan = out / ".process-work/plans/2026-09-10-widget.md"
    plan.write_text(plan.read_text() + "\nROOT-CAUSE work=widget round=2: the cache key ignored the tenant "
                    "— test_widget_per_tenant failed before the fix\n")
    r = _attest(out, *ab, "--round", "2", "--reviewer", "codex")
    assert r.returncode == 0, r.stderr
    assert "no root cause for the fix of blocking round(s) 1" in r.stderr
    assert "verdict=pass round=2" in _journal(out)
    assert _gate(out).returncode == 0, _gate(out).stdout


def test_a_late_pass_of_an_old_round_is_refused_not_promoted(render, tmp_path):
    """Refutation of the round correction: a second reviewer of round 1 passing after
    round 2 blocked, written as round 3, would outrank every block since and clear
    a head no pass ever saw. A claim below the last blocked round stays refused."""
    out, base, head = _repo(render, tmp_path)
    ab = ("--base", base, "--head", head)
    assert _attest(out, *ab, "--verdict", "block").returncode == 0
    plan = out / ".process-work/plans/2026-09-10-widget.md"
    plan.write_text(plan.read_text() + "\nROOT-CAUSE work=widget round=1: x — test_x\n")
    assert _attest(out, *ab, "--verdict", "block", "--round", "2").returncode == 0
    r = _attest(out, *ab, "--round", "1", "--dry-run")
    assert r.returncode == 1 and "this is round 3" in r.stderr and "REFUSED" in r.stderr, r.stderr


def test_a_round_is_one_commit_with_its_report_and_never_with_code(render, tmp_path):
    """Downstream half the commits of two weeks were bookkeeping, each pushed on its
    own; `--with` puts a round's report into the attest commit. Code never rides it."""
    out, base, head = _repo(render, tmp_path)
    ab = ("--base", base, "--head", head)
    report = out / ".process-work/reviews/2026-09-10-widget-r1.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("work: widget\n\nFINDING sev=blocker action=fix issue=- gate=judgement x\n")
    (out / "widget.py").write_text("def widget():\n    return 0\n")
    r = _attest(out, *ab, "--verdict", "block", "--commit", "--with", "widget.py")
    assert r.returncode == 1 and "is not a process record" in r.stderr, r.stderr
    r = _attest(out, *ab, "--verdict", "block", "--commit", "--with", str(report.relative_to(out)))
    assert r.returncode == 0, r.stderr
    shown = _git(out, "show", "--name-only", "--format=%s", "HEAD").stdout
    assert "docs: attest widget round 1" in shown and "reviews/2026-09-10-widget-r1.md" in shown
    assert "widget.py" not in shown and "journal/" in shown


def test_a_root_cause_in_a_spec_kit_plan_counts(render, tmp_path):
    # Spec Kit keeps its plan in specs/<dir>/plan.md — a cause recorded there
    # is recorded; a REVIEW line quoted in two homes is still one round
    out, base, head = _repo(render, tmp_path)
    ab = ("--base", base, "--head", head)
    assert _attest(out, *ab, "--verdict", "block").returncode == 0
    block = next(ln for ln in _journal(out).splitlines() if ln.startswith("REVIEW "))
    spec = out / "specs/001-widget"
    spec.mkdir(parents=True)
    (spec / "plan.md").write_text(f"# Plan\n\ntier: 2\n\n{block}\n\nROOT-CAUSE work=widget round=1: the "
                                  "cache key ignored the tenant — test_widget_per_tenant failed before\n")
    r = _attest(out, *ab, "--round", "2", "--dry-run")
    assert r.returncode == 0 and "note —" not in r.stderr, r.stderr
    r = _attest(out, *ab, "--round", "3", "--dry-run")
    assert r.returncode == 0 and "written as round 2" in r.stderr


def test_a_quoted_or_placeholder_root_cause_is_no_cause(render, tmp_path):
    # A5/A6/A7: a fenced, a commented and the brief's placeholder line each
    # let round 2 pass
    out, base, head = _repo(render, tmp_path)
    ab = ("--base", base, "--head", head)
    assert _attest(out, *ab, "--verdict", "block").returncode == 0
    plan = out / ".process-work/plans/2026-09-10-widget.md"
    original = plan.read_text()
    real = "ROOT-CAUSE work=widget round=1: the cache key ignored the tenant — test_x failed before\n"
    for quoted in ("```\n" + real + "```\n",
                   "<!--\n" + real + "-->\n",
                   "Note <!-- " + real + "--> end.\n",
                   "ROOT-CAUSE work=widget round=1: <cause> — <the test that failed before the fix>\n",
                   "ROOT-CAUSE work=<id> round=1: the cache key — test_x\n",
                   "    " + real):
        plan.write_text(original + "\n" + quoted)
        r = _attest(out, *ab, "--round", "2", "--dry-run")
        assert r.returncode == 0 and "no root cause" in r.stderr, quoted
    plan.write_text(original + "\n- " + real)
    r = _attest(out, *ab, "--round", "2", "--dry-run")
    assert r.returncode == 0 and "no root cause" not in r.stderr, r.stderr


def test_attest_counts_blocks_the_way_the_gate_does(render, tmp_path):
    # refutation: attest read REVIEW lines as rendered while the gate counts
    # them raw — a block behind an unclosed comment was a round for the gate
    # and none for attest, so the next pass skipped its root cause
    out, base, head = _repo(render, tmp_path)
    ab = ("--base", base, "--head", head)
    line = ("REVIEW work=widget tier=2 reviewer=fresh model=cross independence=bundle,non-implementing "
            "verdict=block round=1")
    j = out / ".process-work/journal"
    j.mkdir(parents=True, exist_ok=True)
    (j / "2026-09-10.md").write_text(f"<!-- reviewer notes follow\n{line}\n")
    r = _attest(out, *ab, "--round", "2", "--dry-run")
    assert r.returncode == 0 and "no root cause" in r.stderr, r.stderr


def test_every_record_home_is_read_from_one_owner(render, tmp_path):
    out, base, head = _repo(render, tmp_path)
    gate = _load_gate(out)
    homes = {".process-work/journal/b/2026-09-10.md": "journal",
             ".process-work/plans/2026-09-10-widget.md": "plan",
             ".process-work/plans/archive/2026-09-01-old.md": "plan-archive",
             "specs/001-widget/plan.md": "spec-plan"}
    for rel in homes:
        (out / rel).parent.mkdir(parents=True, exist_ok=True)
        (out / rel).write_text(f"record in {rel}\n")
    for rel in ("specs/001-widget/spec.md", "specs/plan.md", "docs/plan.md"):
        assert gate.record_kind(rel) is None, rel
    assert {rel: gate.record_kind(rel) for rel in homes} == homes
    now = dict(gate.record_texts(out))
    assert set(homes) <= set(now) and now["specs/001-widget/plan.md"] == "record in specs/001-widget/plan.md\n"
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "records")
    assert dict(gate.record_texts(out, ref="HEAD")) == now
    assert gate.record_texts(out, ref="no-such-ref") is None
    assert [rel for rel, _t in gate.record_texts(out, gate.PLAN_KINDS)] == [
        ".process-work/plans/2026-09-10-widget.md", "specs/001-widget/plan.md"]


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
    assert r.returncode == 0 and "note —" not in r.stderr, r.stderr



def test_an_exception_is_written_even_when_no_rule_trips(render, tmp_path):
    # a third round granted by the owner trips no attest rule — still counted
    out, base, head = _repo(render, tmp_path)
    r = _attest(out, "--base", base, "--head", head, "--exception", "owner: third round granted")
    assert r.returncode == 0, r.stderr
    assert ("REVIEW-EXCEPTION work=widget round=1: owner: third round granted "
            "(overrides: no attest rule tripped)") in _journal(out)


def test_a_conflict_resolution_after_the_review_is_unreviewed_code(render, tmp_path):
    # a merge of main whose result differs from both parents (a hand-resolved
    # conflict, an evil merge) carries code the review never saw
    import os
    out, base, head = _repo(render, tmp_path)
    assert _attest(out, "--base", base, "--head", head).returncode == 0
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "docs: attest")
    _git(out, "checkout", "-q", "main")
    (out / "main_only.py").write_text("m = 1\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "main moves on")
    _git(out, "checkout", "-q", "feature")
    gate = [sys.executable, str(out / "scripts/process/check_review.py"), "."]
    env = {**os.environ, "PROCESS_PUSH_TARGETS": "refs/heads/main"}
    _git(out, "merge", "-q", "--no-ff", "--no-edit", "main")  # clean: main's file is not ours
    r = subprocess.run(gate, cwd=out, capture_output=True, text=True, env=env)
    assert "code changed after the reviewed head" not in r.stdout, r.stdout
    _git(out, "reset", "-q", "--hard", "HEAD~1")
    _git(out, "merge", "-q", "--no-ff", "--no-commit", "main")
    (out / "widget.py").write_text("def widget():\n    return 99\n")  # resolved in the merge
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "--no-edit")
    r = subprocess.run(gate, cwd=out, capture_output=True, text=True, env=env)
    assert "code changed after the reviewed head (widget.py)" in r.stdout, r.stdout


def test_appended_journal_lines_of_two_branches_merge_without_conflict(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    assert (out / ".process-work/journal/.gitattributes").read_text().strip().endswith("*.md merge=union")
    _git(out, "init", "-q", "-b", "main")
    _git(out, "config", "user.email", "t@t")
    _git(out, "config", "user.name", "t")
    day = out / ".process-work/journal/2026-09-24.md"
    day.write_text("# 2026-09-24\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "base")
    for name in ("a", "b"):
        _git(out, "checkout", "-q", "-b", name, "main")
        with day.open("a") as fh:
            fh.write(f"REVIEW work={name}\n")
        _git(out, "commit", "-q", "-am", name)
    _git(out, "merge", "-q", "--no-edit", "a")  # on b
    text = day.read_text()
    assert "REVIEW work=a" in text and "REVIEW work=b" in text


def _stale_gate(out):
    import os
    env = {**os.environ, "PROCESS_PUSH_TARGETS": "refs/heads/main"}
    return subprocess.run([sys.executable, str(out / "scripts/process/check_review.py"), "."],
                          cwd=out, capture_output=True, text=True, env=env)


def test_an_amended_reviewed_commit_is_a_stale_review(render, tmp_path):
    # downstream review finding: after `commit --amend` the reviewed head is not
    # in the history at all — there is no later code to diff, and it passed
    out, base, head = _repo(render, tmp_path)
    assert _attest(out, "--base", base, "--head", head).returncode == 0
    journal = [str(p.relative_to(out)) for p in (out / ".process-work/journal").rglob("*.md")]
    (out / "widget.py").write_text("def widget():\n    return 7\n")  # unreviewed change
    _git(out, "add", "widget.py", *journal)
    _git(out, "commit", "-q", "--amend", "--no-edit")
    r = _stale_gate(out)
    assert "is not in the history of what is pushed" in r.stdout, r.stdout


def test_a_rebased_and_amended_review_is_stale(render, tmp_path):
    out, base, head = _repo(render, tmp_path)
    assert _attest(out, "--base", base, "--head", head).returncode == 0
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "docs: attest")
    _git(out, "checkout", "-q", "main")
    (out / "main_only.py").write_text("m = 1\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "main moves on")
    _git(out, "checkout", "-q", "feature")
    _git(out, "rebase", "-q", "main")
    (out / "widget.py").write_text("def widget():\n    return 8\n")
    _git(out, "commit", "-q", "-a", "--amend", "--no-edit")
    r = _stale_gate(out)
    assert "is not in the history of what is pushed" in r.stdout, r.stdout


def test_the_reviewed_head_in_the_history_is_not_stale(render, tmp_path):
    out, base, head = _repo(render, tmp_path)
    assert _attest(out, "--base", base, "--head", head).returncode == 0
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "docs: attest")
    r = _stale_gate(out)
    assert "reviewed head" not in r.stdout and "code changed after" not in r.stdout, r.stdout


def _merged_widget_then_later(render, tmp_path, *, touch_plan=True):
    out, base, head = _repo(render, tmp_path)
    assert _attest(out, "--base", base, "--head", head).returncode == 0
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "docs: attest")
    _git(out, "checkout", "-q", "main")
    _git(out, "merge", "-q", "--no-ff", "--no-edit", "feature")
    plan = out / ".process-work/plans/2026-09-10-widget.md"
    if not touch_plan:  # the plan names its issue on main; the push only claims it
        plan.write_text(plan.read_text().replace("tier: 2", "tier: 2\nissue: #5"))
        _git(out, "commit", "-q", "-am", "plan names its issue")
    _git(out, "checkout", "-q", "-b", "later")
    (out / "widget.py").write_text("def widget():\n    return 43\n")
    if touch_plan:
        plan.write_text(plan.read_text() + "- a note from later work\n")
    _git(out, "commit", "-q", "-am", "later work" if touch_plan else "fix: widget\n\nCloses #5")
    return out


def _main_push_gate(out):
    import os
    env = {**os.environ, "PROCESS_PUSH_TARGETS": "refs/heads/main"}
    return subprocess.run([sys.executable, str(out / "scripts/process/check_review.py"), "."],
                          cwd=out, capture_output=True, text=True, env=env)


def test_later_reviewed_work_is_not_blamed_on_a_merged_plan(render, tmp_path):
    # the later work carries its own plan and review: the merged plan left
    # active is named as residue, the later code is covered by its review
    out = _merged_widget_then_later(render, tmp_path)
    (out / ".process-work/plans/2026-09-11-later.md").write_text("# Later\n\ntier: 2\n\n## Decisions\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "later plan")
    later_base = _git(out, "merge-base", "main", "HEAD").stdout.strip()
    later_head = _git(out, "rev-parse", "HEAD").stdout.strip()
    r = subprocess.run([sys.executable, str(out / "scripts/process/attest.py"), "--work", "later", "--tier", "2",
                        "--reviewer", "fresh", "--model", "cross", "--independence", "bundle,non-implementing",
                        "--verdict", "pass", "--round", "1", "--base", later_base, "--head", later_head, "."],
                       cwd=out, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "docs: attest later")
    r = _main_push_gate(out)
    assert "code changed after the reviewed head" not in r.stdout, r.stdout
    assert "belongs to work already merged" in r.stdout, r.stdout


@pytest.mark.parametrize("touch_plan", [True, False])
def test_unreviewed_follow_up_under_a_merged_plan_is_still_refused(render, tmp_path, touch_plan):
    # refutation: a skip for "merged work" let unreviewed follow-up code through
    out = _merged_widget_then_later(render, tmp_path, touch_plan=touch_plan)
    r = _main_push_gate(out)
    assert r.returncode != 0 and "code changed after the reviewed head" in r.stdout, r.stdout


def test_a_plan_review_of_a_plan_named_plan_does_not_clear_its_code(render, tmp_path):
    out, base, head = _repo(render, tmp_path)
    r = subprocess.run([sys.executable, str(out / "scripts/process/attest.py"), "--work", "deploy-plan", "--tier", "2",
                        "--reviewer", "fresh", "--model", "cross", "--independence", "bundle,non-implementing",
                        "--verdict", "pass", "--round", "1", "--plan-review", "--base", base, "--head", head,
                        "--dry-run", "."], cwd=out, capture_output=True, text=True)
    assert "work=deploy-plan-plan" in r.stdout + r.stderr, r.stdout + r.stderr


def test_a_commented_block_in_a_plan_is_no_round(render, tmp_path):
    out, base, head = _repo(render, tmp_path)
    line = ("REVIEW work=widget tier=2 reviewer=fresh model=cross independence=bundle,non-implementing "
            "verdict=block round=1")
    plan = out / ".process-work/plans/2026-09-10-widget.md"
    plan.write_text(plan.read_text() + f"\n<!-- example:\n{line}\n-->\n")
    r = _attest(out, "--base", base, "--head", head, "--round", "2", "--dry-run")
    assert r.returncode == 0 and "written as round 1" in r.stderr, r.stderr


# --- #130 R2 / D1: one shard per issue, archive and commit with the pass ---


def _branch(out, name):
    _git(out, "checkout", "-q", "-b", name)


@pytest.mark.parametrize("name, shard", [
    ("7-login", "issue-7"), ("issue-7", "issue-7"), ("7", "issue-7"),
    ("feat/login", "feat-login"), ("70s-look", "70s-look"),
])
def test_a_numbered_branch_writes_its_issues_shard(render, tmp_path, name, shard):
    """D1: a numbered branch writes issue-<N>/ — two branches of one issue share their
    shard, and a reader can find an issue's record without knowing its slug."""
    out, base, head = _repo(render, tmp_path)
    _branch(out, name)

    r = _attest(out, "--base", base, "--head", head)

    assert r.returncode == 0, r.stderr
    assert [p.parent.name for p in (out / ".process-work/journal").rglob("*.md")] == [shard]


def test_a_note_must_not_carry_a_review_line(render, tmp_path):
    """Only the validated line is a REVIEW writer: a note could smuggle a typed one in."""
    out, base, head = _repo(render, tmp_path)

    r = _attest(out, "--base", base, "--head", head,
                "--note", "fine\n  REVIEW work=widget verdict=pass diff=abc")

    assert r.returncode == 1 and "REVIEW-looking" in r.stderr, r.stderr
    assert not list((out / ".process-work/journal").rglob("*.md"))


def test_archive_moves_the_plan_with_the_pass_and_commits_once(render, tmp_path):
    out, base, head = _repo(render, tmp_path)
    plan = ".process-work/plans/2026-09-10-widget.md"

    r = _attest(out, "--base", base, "--head", head, "--archive", plan, "--commit")

    assert r.returncode == 0, r.stderr
    assert not (out / plan).exists()
    assert (out / ".process-work/plans/archive/2026-09-10-widget.md").is_file()
    assert _git(out, "status", "--porcelain").stdout == ""
    assert _git(out, "log", "-1", "--format=%s").stdout.strip() == \
        "docs: attest widget round 1 and archive the plan"
    assert _gate(out).returncode == 0, _gate(out).stdout


def test_archive_refuses_a_block(render, tmp_path):
    """A plan is archived when its work merges, not in a review round."""
    out, base, head = _repo(render, tmp_path)
    r = subprocess.run([sys.executable, str(out / "scripts/process/attest.py"),
                        "--work", "widget", "--tier", "2", "--model", "cross",
                        "--independence", "bundle,non-implementing", "--verdict", "block",
                        "--base", base, "--head", head,
                        "--archive", ".process-work/plans/2026-09-10-widget.md", "."],
                       cwd=out, capture_output=True, text=True)

    assert r.returncode == 1 and "only with verdict=pass" in r.stderr, r.stderr
    assert not list((out / ".process-work/journal").rglob("*.md"))


@pytest.mark.parametrize("case", ["missing", "taken"])
def test_archive_refuses_before_writing_anything(render, tmp_path, case):
    """Every precondition before the first write: a late failure left a written line,
    and the corrected rerun doubled it."""
    out, base, head = _repo(render, tmp_path)
    plan = ".process-work/plans/2026-09-10-widget.md"
    if case == "missing":
        plan = ".process-work/plans/nope.md"
    else:
        (out / ".process-work/plans/archive").mkdir(parents=True, exist_ok=True)
        (out / ".process-work/plans/archive/2026-09-10-widget.md").write_text("# other\n")

    r = _attest(out, "--base", base, "--head", head, "--archive", plan)

    assert r.returncode == 1 and "REFUSED" in r.stderr, r.stderr
    assert not list((out / ".process-work/journal").rglob("*.md"))


def test_a_spec_kit_plan_is_archived_under_its_feature_name(render, tmp_path):
    """Every Spec Kit plan is plan.md: named alone, they would collide in the archive."""
    out, base, head = _repo(render, tmp_path)
    spec = out / "specs/003-login/plan.md"
    spec.parent.mkdir(parents=True)
    spec.write_text("# Plan\n\ntier: 2\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "spec")

    r = subprocess.run([sys.executable, str(out / "scripts/process/attest.py"),
                        "--work", "003-login", "--tier", "2", "--model", "cross",
                        "--independence", "bundle,non-implementing", "--verdict", "pass",
                        "--base", base, "--head", head, "--archive", "specs/003-login/plan.md", "."],
                       cwd=out, capture_output=True, text=True)

    assert r.returncode == 0, r.stderr
    assert (out / ".process-work/plans/archive/003-login.md").is_file()
    assert "git commit" in r.stdout  # staged, the commit is named


def test_without_archive_or_commit_nothing_is_staged(render, tmp_path):
    out, base, head = _repo(render, tmp_path)

    assert _attest(out, "--base", base, "--head", head).returncode == 0
    assert _git(out, "diff", "--cached", "--name-only").stdout == ""


# --- refute of #130 ---


@pytest.mark.parametrize("name, issue", [
    ("7-login", "7"), ("issue-7", "7"), ("7", "7"), ("feat/7-login", "7"),
    ("7/x", None), ("70s-look", None), ("2026-09-30-login", None), ("process-v2.28.0", None),
])
def test_one_owner_names_a_branchs_issue(render, tmp_path, name, issue):
    """F10: attest and the train read `feat/7-login` and `7/x` differently, and every
    date-prefixed branch shared the shard `issue-2026`."""
    out = render(tmp_path, {"project_name": "d"})
    gate = _load_gate(out)
    sys.path.insert(0, str(out / "scripts/process"))
    try:
        import importlib

        import train
        importlib.reload(train)
        assert gate.branch_issue(name) == issue
        assert (issue in train._branch_work_ids(name)) if issue else not (
            train._branch_work_ids(name) - {name, name.rsplit("/", 1)[-1]})
    finally:
        sys.path.pop(0)
        for m in ("train", "check_review", "dispatch", "report"):
            sys.modules.pop(m, None)


def test_commit_carries_only_the_attestation(render, tmp_path):
    """F7: a staged unrelated file rode along into the attest commit."""
    out, base, head = _repo(render, tmp_path)
    (out / "widget.py").write_text("def widget():\n    return 43\n")
    _git(out, "add", "widget.py")

    r = _attest(out, "--base", base, "--head", head, "--commit")

    assert r.returncode == 0, r.stderr
    assert "widget.py" not in _git(out, "show", "--name-only", "--format=", "HEAD").stdout
    assert _git(out, "diff", "--cached", "--name-only").stdout.strip() == "widget.py"


def test_archive_refuses_an_untracked_plan_before_writing(render, tmp_path):
    """F8: git mv failed after the line was written."""
    out, base, head = _repo(render, tmp_path)
    (out / ".process-work/plans/2026-09-11-widget.md").write_text("# Plan\n\ntier: 2\n")

    r = _attest(out, "--base", base, "--head", head,
                "--archive", ".process-work/plans/2026-09-11-widget.md")

    assert r.returncode == 1 and "not tracked" in r.stderr, r.stderr
    assert not list((out / ".process-work/journal").rglob("*.md"))


@pytest.mark.parametrize("target", ["PRODUCT.md", ".process-work/plans/2026-09-10-other.md"])
def test_archive_takes_only_this_works_plan(render, tmp_path, target):
    """F9: `--archive PRODUCT.md` moved the product frame; another work's plan went too."""
    out, base, head = _repo(render, tmp_path)
    (out / ".process-work/plans/2026-09-10-other.md").write_text("# Plan\n\ntier: 3\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "other plan")

    r = _attest(out, "--base", base, "--head", head, "--archive", target)

    assert r.returncode == 1 and "REFUSED" in r.stderr, r.stderr
    assert (out / target).is_file()
