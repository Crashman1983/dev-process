import os
import subprocess

import yaml

FAKE_GH = r'''#!/usr/bin/env bash
# mock gh: scenario via MOCK_SCENARIO, every call logged to MOCK_LOG
echo "$@" >> "$MOCK_LOG"
case "$*" in
  *"nameWithOwner"*) echo "octo/proj"; exit 0;;
  *"defaultBranchRef"*) echo "main"; exit 0;;
  *"-X POST"*) exit 0;;
  *"-X PUT"*) exit 0;;
  *"api repos/octo/proj/branches/main/protection"*)
    case "$MOCK_SCENARIO" in
      none)         echo '{"message":"Branch not protected"}' >&2; exit 1;;
      reviews_only) echo '{"required_pull_request_reviews":{"required_approving_review_count":1}}'; exit 0;;
      rsc_other)    echo '{"required_status_checks":{"contexts":["other-check"]}}'; exit 0;;
      rsc_present)  echo '{"required_status_checks":{"contexts":["process-gates"]}}'; exit 0;;
      err)          echo '{"message":"Must have admin rights to Repository."}' >&2; exit 1;;
    esac;;
esac
exit 0
'''


def _run_script(out, tmp_path, scenario):
    bin_dir = tmp_path / f"bin-{scenario}"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(FAKE_GH)
    gh.chmod(0o755)
    log = tmp_path / f"calls-{scenario}.log"
    log.write_text("")
    env = dict(os.environ, PATH=f"{bin_dir}:{os.environ['PATH']}",
               MOCK_SCENARIO=scenario, MOCK_LOG=str(log))
    r = subprocess.run(["bash", str(out / "scripts/process/setup_branch_protection.sh")],
                       cwd=out, capture_output=True, text=True, env=env)
    return r, log.read_text()


def test_script_present_with_github_ci(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "ci": {"github": True, "gitlab": False}})
    p = out / "scripts/process/setup_branch_protection.sh"
    assert p.is_file()
    r = subprocess.run(["bash", "-n", str(p)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    text = p.read_text()
    # non-destructive merge path + honest failure guidance are load-bearing
    assert "required_status_checks/contexts" in text
    assert "paid" in text and "Manual path" in text


def test_script_absent_without_github_ci(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "ci": {"github": False, "gitlab": True}})
    assert not (out / "scripts/process/setup_branch_protection.sh").exists()


def _render_on(render, tmp_path):
    return render(tmp_path, {"project_name": "d", "ci": {"github": True, "gitlab": False}})


def test_unprotected_branch_gets_minimal_rule(render, tmp_path):
    out = _render_on(render, tmp_path)
    r, log = _run_script(out, tmp_path, "none")
    assert r.returncode == 0, r.stderr
    assert "-X PUT" in log and "created branch protection" in r.stdout


def test_reviews_only_protection_is_never_rewritten(render, tmp_path):
    # THE destructive case: protection exists without status checks. GitHub
    # 404s the required_status_checks sub-endpoint there too — the script must
    # refuse with instructions, not PUT a fresh rule over the existing one.
    out = _render_on(render, tmp_path)
    r, log = _run_script(out, tmp_path, "reviews_only")
    assert r.returncode == 1
    assert "-X PUT" not in log, f"destructive PUT issued:\n{log}"
    assert "never rewrites an existing rule" in r.stderr


def test_existing_checks_only_gain_the_context(render, tmp_path):
    out = _render_on(render, tmp_path)
    r, log = _run_script(out, tmp_path, "rsc_other")
    assert r.returncode == 0, r.stderr
    assert "-X POST" in log and "-X PUT" not in log
    assert "added 'process-gates'" in r.stdout


def test_already_required_is_a_noop(render, tmp_path):
    out = _render_on(render, tmp_path)
    r, log = _run_script(out, tmp_path, "rsc_present")
    assert r.returncode == 0
    assert "already a required status check" in r.stdout
    assert "-X POST" not in log and "-X PUT" not in log


def test_unreadable_state_touches_nothing(render, tmp_path):
    # a non-404 GET failure (auth/plan/network) must stop, not create-over
    out = _render_on(render, tmp_path)
    r, log = _run_script(out, tmp_path, "err")
    assert r.returncode == 1
    assert "-X PUT" not in log and "-X POST" not in log
    assert "not touching anything" in r.stderr


def test_job_id_matches_required_check_context(render, tmp_path):
    # the Actions job id IS the status-check context; docs and the setup script
    # both say `process-gates`, so the job must be named exactly that (a job
    # named `gates` would make the documented required check never satisfiable).
    out = render(tmp_path, {"project_name": "d", "ci": {"github": True, "gitlab": False}})
    wf = yaml.safe_load((out / ".github/workflows/process-gates.yml").read_text())
    assert "process-gates" in wf["jobs"], wf["jobs"].keys()
    script = (out / "scripts/process/setup_branch_protection.sh").read_text()
    assert 'CONTEXT="process-gates"' in script
