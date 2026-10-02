"""Real release renders and Git history: template provenance cannot whitewash project code."""
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / 'template/scripts/process'
sys.path.insert(0, str(SCRIPTS))
sys.dont_write_bytecode = True


def load(name):
    spec = importlib.util.spec_from_file_location('verify_test_' + name, SCRIPTS / (name + '.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def git(root, *args):
    return subprocess.run(['git', *args], cwd=root, check=True,
                          capture_output=True, text=True).stdout.strip()


def write(root, rel, body):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding='utf-8')
    return p


def commit(root):
    git(root, 'add', '-A')
    git(root, 'commit', '-qm', 'fixture')
    return git(root, 'rev-parse', 'HEAD')


def init(root):
    root.mkdir(exist_ok=True)
    git(root, 'init', '-q', '-b', 'main')
    git(root, 'config', 'user.name', 'Test')
    git(root, 'config', 'user.email', 't@example.com')


@pytest.fixture
def update(tmp_path):
    source, root = tmp_path / 'source', tmp_path / 'project'
    init(source)
    write(source, 'copier.yml', '_subdirectory: template\nproject_name:\n  default: demo\n')
    write(source, 'template/.copier-answers.yml.jinja', '{{ _copier_answers|to_nice_yaml }}\n')
    write(source, 'template/docs/process/example.md', 'old template\n')
    write(source, 'CHANGELOG.md', '# Changelog\n\n## 1.0.0\n\nInitial release.\n')
    commit(source)
    git(source, 'tag', 'v1.0.0')
    write(source, 'template/docs/process/example.md', 'new template\n')
    write(source, 'CHANGELOG.md', '# Changelog\n\n## 1.1.0\n\nChanged behavior.\n\n## 1.0.0\n\nInitial release.\n')
    new_release = commit(source)
    git(source, 'tag', 'v1.1.0')
    import copier
    copier.run_copy(str(source), str(root), vcs_ref='v1.0.0', defaults=True, quiet=True)
    init(root)
    base = commit(root)
    git(root, 'checkout', '-qb', 'update')
    copier.run_copy(str(source), str(root), vcs_ref='v1.1.0', defaults=True,
                    overwrite=True, quiet=True)
    commit(root)
    verifier = load('template_verify')
    write(root, verifier.ACK, json.dumps(dict(base=base, release=new_release, owner='steward')))
    write(root, '.process-work/plans/update.md',
          '# Update\n\ntier: 2\ntemplate-update: true\n\n## Decisions\n')
    commit(root)
    return root, source, base, verifier


def check(root, monkeypatch):
    monkeypatch.setenv('PROCESS_PUSH_TARGETS', 'refs/heads/main')
    return load('check_review').check(root)


def test_pure_update_needs_no_review_and_lists_behavior_notes(update, monkeypatch):
    root, _, base, verifier = update
    proof = verifier.verify(root, base)
    assert proof['update'] and not proof['errors'], proof
    assert proof['identical'] == ['.copier-answers.yml', 'docs/process/example.md']
    assert proof['project_delta'] == [] and proof['acknowledged']
    assert 'Changed behavior.' in proof['release_notes']
    assert 'Initial release.' not in proof['release_notes']
    hard, _ = check(root, monkeypatch)
    assert hard == [], hard


@pytest.mark.parametrize('rel', ['docs/process/example.md', 'rule.local.md',
                                 'Makefile', '.githooks/pre-push', 'tests/test_app.py'])
def test_hand_edit_or_local_infrastructure_is_delta_and_requires_review(update, monkeypatch, rel):
    root, _, base, verifier = update
    write(root, rel, 'project change\n')
    commit(root)
    proof = verifier.verify(root, base)
    assert rel in proof['project_delta'], proof
    hard, _ = check(root, monkeypatch)
    assert any('tier 2 digest-bound REVIEW required' in h for h in hard), hard


def test_matching_new_render_does_not_hide_lost_project_customization(update):
    root, _, base, verifier = update
    git(root, 'checkout', '-qb', 'customized', base)
    write(root, 'docs/process/example.md', 'project duty\n')
    customized = commit(root)
    git(root, 'checkout', 'update', '--', '.copier-answers.yml', 'docs/process/example.md')
    commit(root)
    proof = verifier.verify(root, customized)
    assert 'docs/process/example.md' in proof['project_delta']


def test_template_enforcement_change_requires_tier3_even_with_no_plan(update, monkeypatch):
    root, source, base, verifier = update
    write(source, 'template/scripts/process/check_something.py', '# new enforcement\n')
    new = commit(source)
    git(source, 'tag', 'v1.2.0')
    import copier
    copier.run_copy(str(source), str(root), vcs_ref='v1.2.0', defaults=True,
                    overwrite=True, quiet=True)
    shutil.rmtree(root / '.process-work/plans')
    write(root, verifier.ACK, json.dumps(dict(base=base, release=new, owner='owner')))
    commit(root)
    proof = verifier.verify(root, base)
    assert proof['migration']
    hard, _ = check(root, monkeypatch)
    assert any('tier 3 digest-bound REVIEW required' in h for h in hard), hard


def test_forged_report_and_changed_source_never_exempt_code(update, monkeypatch):
    root, _, base, verifier = update
    write(root, 'src/app.py', 'unreviewed = True\n')
    write(root, '.process-work/template-verification.json', '{"identical": ["src/app.py"]}')
    commit(root)
    proof = verifier.verify(root, base)
    assert 'src/app.py' in proof['project_delta']
    hard, _ = check(root, monkeypatch)
    assert any('digest-bound REVIEW required' in h for h in hard), hard
    p = root / '.copier-answers.yml'
    p.write_text(p.read_text().replace(str(update[1]), str(root / 'fake')))
    commit(root)
    proof = verifier.verify(root, base)
    assert proof['errors'] and not proof['identical']


def test_missing_render_and_unpinned_head_fail_closed(update, monkeypatch):
    root, source, base, verifier = update
    monkeypatch.setattr(verifier, 'render', lambda *a: False)
    proof = verifier.verify(root, base)
    assert proof['errors'] and not proof['identical']
    p = root / '.copier-answers.yml'
    p.write_text(p.read_text().replace('v1.1.0', 'HEAD'))
    commit(root)
    proof = verifier.verify(root, base)
    assert proof['errors'] and not proof['identical']


def test_mode_change_and_symlink_target_are_project_delta(update):
    root, _, base, verifier = update
    p = root / 'docs/process/example.md'
    p.chmod(0o755)
    commit(root)
    assert 'docs/process/example.md' in verifier.verify(root, base)['project_delta']
    p.unlink()
    p.symlink_to('../../../outside')
    commit(root)
    assert 'docs/process/example.md' in verifier.verify(root, base)['project_delta']


def test_worktree_cli_ack_binds_to_actual_release_and_edit(update):
    root, _, base, verifier = update
    (root / verifier.ACK).unlink()
    write(root, 'docs/process/example.md', 'uncommitted edit\n')
    proof = verifier.verify(root, base, worktree=True)
    assert not proof['acknowledged'] and 'docs/process/example.md' in proof['project_delta']
    cli_dir = root.parent / 'cli'
    shutil.copytree(SCRIPTS, cli_dir, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    r = subprocess.run([sys.executable, str(cli_dir / 'template_update.py'),
                        '--verify', str(root), '--base', base, '--ack', 'owner'],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert not (cli_dir / '__pycache__').exists()
    proof = json.loads(r.stdout)
    assert proof['acknowledged'] and 'docs/process/example.md' in proof['project_delta']


def test_deletion_of_handwritten_test_is_delta(update):
    root, _, base, verifier = update
    git(root, 'checkout', '-qb', 'tests', base)
    write(root, 'tests/test_app.py', 'assert True\n')
    base = commit(root)
    git(root, 'checkout', 'update', '--', '.copier-answers.yml', 'docs/process/example.md')
    (root / 'tests/test_app.py').unlink()
    commit(root)
    assert 'tests/test_app.py' in verifier.verify(root, base)['project_delta']


def test_project_delta_clears_with_one_exact_review_and_stales_after_another_edit(update, monkeypatch):
    root, _, base, verifier = update
    write(root, 'src/app.py', 'review_me = True\n')
    head = commit(root)
    review = load('check_review')
    digest = review.artifact_digest(root, base, head)
    write(root, '.process-work/journal/review.md',
          'REVIEW work=update tier=2 reviewer=fresh model=same '
          'independence=bundle,non-implementing verdict=pass round=1 '
          f'base={base} head={head} diff={digest}\n')
    commit(root)
    hard, _ = check(root, monkeypatch)
    assert not hard, hard
    write(root, 'src/app.py', 'late_edit = True\n')
    commit(root)
    hard, _ = check(root, monkeypatch)
    assert any('digest-bound REVIEW required' in h for h in hard), hard


def test_pure_update_plan_uses_same_exemption_in_finish_and_train(update, monkeypatch):
    root, _, base, verifier = update
    review = load('check_review')
    text = (root / '.process-work/plans/update.md').read_text()
    assert review.verified_template_plan(root, '.process-work/plans/update.md', text)
    # Finish still runs gates and retains the archive duty.
    write(root, 'scripts/process/gate_runner.py', 'raise SystemExit(0)\n')
    # Test the shared helper on the already verified immutable update, not a
    # hand-written runner as template provenance.
    git(root, 'clean', '-fd')
    finish = load('finish')
    monkeypatch.setattr(finish, 'gate_runner_argv', lambda root: [sys.executable, '-c', 'pass'])
    blockers, tail = finish.check(root)
    assert not blockers, blockers
    assert any('archive' in t for t in tail), tail
    # Train evaluates an un-checked-out passenger using its tree, never HEAD's answers.
    (root / '.process-work/plans/archive').mkdir()
    (root / '.process-work/plans/update.md').rename(root / '.process-work/plans/archive/update.md')
    commit(root)
    git(root, 'checkout', '-q', 'main')
    assert review.verified_template_plan(root, '.process-work/plans/archive/update.md', text, tip='update')
    candidate = next(c for c in load('train').candidates(root, 'main', 'main') if c['branch'] == 'update')
    assert candidate['eligible'], candidate
    assert 'verified template' in candidate['by']


def test_template_deleted_file_is_exempt_only_if_old_project_file_was_unchanged(update):
    root, source, base, verifier = update
    (source / 'template/docs/process/example.md').unlink()
    commit(source)
    git(source, 'tag', 'v1.2.0')
    # Copier's update semantics represented by the committed deletion.
    p = root / '.copier-answers.yml'
    p.write_text(p.read_text().replace('v1.1.0', 'v1.2.0'))
    (root / 'docs/process/example.md').unlink()
    commit(root)
    proof = verifier.verify(root, base)
    assert 'docs/process/example.md' in proof['identical'], proof


def test_missing_answers_cannot_grant_an_exemption(update, monkeypatch):
    root, _, base, verifier = update
    (root / '.copier-answers.yml').unlink()
    commit(root)
    proof = verifier.verify(root, base)
    assert proof['update'] and proof['errors'] and not proof['identical']
    hard, _ = check(root, monkeypatch)
    assert any('recorded template answers were deleted' in h for h in hard), hard


def test_pin_bump_that_skips_a_changed_template_file_is_delta(update):
    root, _, base, verifier = update
    git(root, 'checkout', base, '--', 'docs/process/example.md')
    commit(root)
    proof = verifier.verify(root, base)
    assert 'docs/process/example.md' in proof['project_delta'], proof



def test_missing_yaml_fails_closed_before_rendering(update, monkeypatch):
    import builtins
    root, _, base, verifier = update
    original = builtins.__import__

    def no_yaml(name, *args, **kwargs):
        if name == 'yaml':
            raise ImportError('test isolation')
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', no_yaml)
    proof = verifier.verify(root, base)
    assert proof['update'] and proof['errors'] and not proof['identical']
    assert 'PyYAML required' in proof['errors'][0]


def test_other_copier_metadata_is_project_delta(update):
    root, _, base, verifier = update
    p = root / '.copier-answers.yml'
    p.write_text(p.read_text() + '_project_option: new-value\n')
    commit(root)
    assert '.copier-answers.yml' in verifier.verify(root, base)['project_delta']


def test_migration_clears_only_with_tier3_exact_review(update, monkeypatch):
    root, source, base, verifier = update
    write(source, 'template/scripts/process/check_something.py', '# enforcement\n')
    release = commit(source)
    git(source, 'tag', 'v1.2.0')
    import copier
    copier.run_copy(str(source), str(root), vcs_ref='v1.2.0', defaults=True,
                    overwrite=True, quiet=True)
    write(root, verifier.ACK, json.dumps(dict(base=base, release=release, owner='owner')))
    head = commit(root)
    review = load('check_review')
    digest = review.artifact_digest(root, base, head)
    for tier in (2, 3):
        write(root, '.process-work/journal/review.md',
              f'REVIEW work=update tier={tier} reviewer=fresh model=cross '
              'independence=bundle,non-implementing,cross-model verdict=pass round=1 '
              f'base={base} head={head} diff={digest}\n')
        commit(root)
        hard, _ = check(root, monkeypatch)
        if tier == 2:
            assert any('tier 3 digest-bound REVIEW required' in h for h in hard), hard
        else:
            assert not hard, hard


def test_owned_glob_keeps_even_identical_template_and_answers_as_project_delta(update):
    root, _, base, verifier = update
    write(root, '.process-owned', '*\n')
    commit(root)
    proof = verifier.verify(root, base)
    assert '.copier-answers.yml' in proof['project_delta']
    assert 'docs/process/example.md' in proof['project_delta']
    assert not proof['identical']
