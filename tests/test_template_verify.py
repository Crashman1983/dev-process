"""Real release renders and Git history: template provenance cannot whitewash project code."""
import importlib.util
import json
import os
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
    assert 'scripts/process/template_verify.py' in proof['errors'][0]  # names the tool to run


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



def test_release_notes_use_pinned_changes_with_the_templates_bold_version_format(update):
    root, source, base, verifier = update
    p = source / 'CHANGELOG.md'
    p.write_text('**v1.2.0 — New behavior.**\n\nOwner must know this.\n\n' + p.read_text())
    commit(source)
    git(source, 'tag', 'v1.2.0')
    p = root / '.copier-answers.yml'
    p.write_text(p.read_text().replace('v1.1.0', 'v1.2.0'))
    commit(root)
    proof = verifier.verify(root, base)
    assert not proof['errors'], proof
    assert 'Owner must know this.' in proof['release_notes']
    assert 'Changed behavior.' in proof['release_notes']
    assert 'Initial release.' not in proof['release_notes']


@pytest.mark.parametrize('rel,worktree', [
    ('scripts/process/local_gate.py', False),
    ('.process-gates.yml', False),
    ('scripts/process/local_helper.py', True),
])
def test_doc_release_with_project_enforcement_delta_requires_tier3(update, monkeypatch, rel, worktree):
    root, _, base, verifier = update
    write(root, rel, '# project enforcement change\n')
    if not worktree:
        commit(root)
    proof = verifier.verify(root, base, worktree=worktree)
    assert not proof['errors'], proof
    assert rel in proof['project_delta'] and proof['migration'], proof
    if not worktree:
        hard, _ = check(root, monkeypatch)
        assert any('tier 3 digest-bound REVIEW required' in h for h in hard), hard


@pytest.mark.parametrize('trusted', [False, True])
def test_automatic_render_skips_tasks_but_explicit_update_retains_operator_contract(update, tmp_path, trusted):
    import yaml
    _, source, _, verifier = update
    marker = tmp_path / 'task-ran'
    config = yaml.safe_load((source / 'copier.yml').read_text())
    config['_tasks'] = [[sys.executable, '-c', f'from pathlib import Path; Path({str(marker)!r}).write_text("ran")']]
    write(source, 'copier.yml', yaml.safe_dump(config))
    sha = commit(source)
    target = tmp_path / 'task-render'
    if trusted:
        assert verifier.template_render(str(source), sha, {}, target)
    else:
        assert verifier.render(str(source), sha, {}, target)
    assert marker.exists() is trusted


def test_automatic_render_ignores_local_settings_trust_for_extensions(update, tmp_path, monkeypatch):
    import yaml
    _, source, _, verifier = update
    marker = tmp_path / 'extension-imported'
    extension = tmp_path / 'probe_extension.py'
    extension.write_text('from pathlib import Path\nfrom jinja2.ext import Extension\n'
                         f'Path({str(marker)!r}).write_text("imported")\n'
                         'class Probe(Extension):\n    pass\n')
    config = yaml.safe_load((source / 'copier.yml').read_text())
    config['_jinja_extensions'] = ['probe_extension.Probe']
    write(source, 'copier.yml', yaml.safe_dump(config))
    sha = commit(source)
    settings = write(tmp_path, 'settings.yml', yaml.safe_dump({'trust': [str(source)]}))
    monkeypatch.setenv('COPIER_SETTINGS_PATH', str(settings))
    monkeypatch.setenv('PYTHONPATH', str(tmp_path))
    assert not verifier.render(str(source), sha, {}, tmp_path / 'automatic')
    assert not marker.exists()
    # Prove the settings and extension form a real executable fixture.
    operator = load('template_update')
    assert operator.render(str(source), sha, {}, tmp_path / 'explicit')
    assert marker.exists()


def test_second_gate_run_in_one_process_reuses_release_lookups(update, monkeypatch):
    """Kenni #2375: a dirty tree re-verified on every gate run re-fetched the template each time."""
    root, _, _, _ = update
    review = load('check_review')
    import template_verify as shared
    calls = []
    real_run, real_render = shared.subprocess.run, shared.render

    def run(argv, *a, **kw):
        if any(word in argv for word in ('clone', 'fetch', 'ls-remote')):
            calls.append(argv)
        return real_run(argv, *a, **kw)

    def render(*a, **kw):
        calls.append('render')
        return real_render(*a, **kw)

    monkeypatch.setattr(shared.subprocess, 'run', run)
    monkeypatch.setattr(shared, 'render', render)
    write(root, 'scratch.txt', 'tracked\n')
    commit(root)
    write(root, 'scratch.txt', 'dirty\n')
    monkeypatch.setenv('PROCESS_PUSH_TARGETS', 'refs/heads/main')
    review.check(root)
    first = len(calls)
    assert first and sum('clone' in c for c in calls if c != 'render') == 1, calls
    review.check(root)
    assert len(calls) == first, calls[first:]
    write(root, 'scratch.txt', 'edited\n')
    review.check(root)
    assert len(calls) == first, 'the gate verifies the committed tip, never the worktree'


def test_gate_ignores_an_uncommitted_answers_edit_until_it_is_committed(update, monkeypatch):
    """#161: a dirty tree switched the gate to the worktree — it judged what is not pushed."""
    root, _, _, _ = update
    hard, _ = check(root, monkeypatch)
    assert hard == [], hard
    p = root / '.copier-answers.yml'
    p.write_text(p.read_text() + '_project_option: new-value\n')
    hard, _ = check(root, monkeypatch)
    assert hard == [], hard
    commit(root)
    hard, _ = check(root, monkeypatch)
    assert any('tier 2 digest-bound REVIEW required' in h for h in hard), hard


def test_unreachable_source_names_source_and_ref_and_fails_closed(update, monkeypatch):
    """An offline run said only 'cannot resolve release'; the operator needs the source."""
    root, source, base, verifier = update
    missing = str(source)
    source.rename(source.with_name('gone'))
    proof = verifier.verify(root, base)
    assert not proof['identical'], proof
    assert any(missing in e and 'v1.0.0' in e and 'fails closed' in e
               for e in proof['errors']), proof['errors']
    hard, _ = check(root, monkeypatch)
    assert any('template verification failed' in h and missing in h for h in hard), hard


def test_worktree_memo_rereads_an_ignored_rendered_file(update, monkeypatch):
    """Refute: an ignored file that is also a rendered path is read from disk but sits in
    no dirty set; editing it must not be answered from the memo."""
    root, _, base, verifier = update
    git(root, 'rm', '-q', '--cached', 'docs/process/example.md')
    write(root, '.gitignore', 'docs/process/example.md\n')
    commit(root)
    renders = []
    real = verifier.render
    monkeypatch.setattr(verifier, 'render', lambda *a: renders.append(a) or real(*a))
    first = verifier.verify(root, base, worktree=True)
    assert renders and 'docs/process/example.md' in first['project_delta'] + first['identical']
    seen = len(renders)
    verifier.verify(root, base, worktree=True)
    assert len(renders) == seen  # unchanged: answered from the memo
    write(root, 'docs/process/example.md', 'edited, ignored\n')
    verifier.verify(root, base, worktree=True)
    assert len(renders) > seen


# --- the fork point: one owner (process_git.fork_point), callers pass the ref ---

def criss_cross(root):
    """main and feature merged each other: two merge bases (Kenni #2352)."""
    init(root)
    write(root, 'README.md', 'base\n')
    commit(root)
    git(root, 'checkout', '-qb', 'feature')
    write(root, 'feature.md', 'a1\n')
    a1 = commit(root)
    git(root, 'checkout', '-q', 'main')
    write(root, 'main.md', 'b1\n')
    b1 = commit(root)
    git(root, 'merge', '-q', '--no-ff', '-m', 'main takes feature', a1)
    git(root, 'checkout', '-q', 'feature')
    git(root, 'merge', '-q', '--no-ff', '-m', 'feature takes main', b1)
    tip = git(root, 'rev-parse', 'HEAD')
    assert len(git(root, 'merge-base', '--all', 'main', tip).split()) == 2
    return tip


def recording(module, monkeypatch):
    calls = []
    real = module.verify

    def record(*args, **kwargs):
        calls.append(args)
        return real(*args, **kwargs)

    monkeypatch.setattr(module, 'verify', record)
    return calls


def move_main(root):
    git(root, 'checkout', '-q', 'main')
    write(root, 'unrelated/main-only.md', 'later on main\n')
    commit(root)
    git(root, 'checkout', '-q', 'update')


def test_verify_refuses_an_ambiguous_fork_point(tmp_path):
    tip = criss_cross(tmp_path / 'p')
    with pytest.raises(ValueError, match='merge bases'):
        load('template_verify').verify(tmp_path / 'p', 'main', tip)


def test_verify_names_a_missing_fork_point(tmp_path):
    root = tmp_path / 'p'
    init(root)
    write(root, 'README.md', 'main\n')
    commit(root)
    git(root, 'checkout', '-q', '--orphan', 'other')
    write(root, 'other.md', 'other\n')
    tip = commit(root)
    with pytest.raises(ValueError, match='no common ancestor'):
        load('template_verify').verify(root, 'main', tip)


def test_gate_finish_and_history_refuse_a_criss_cross(tmp_path, monkeypatch):
    """Ambiguity is a finding, never 'no base' (Kenni #2381: None turned the arms off)."""
    root = tmp_path / 'p'
    tip = criss_cross(root)
    review = load('check_review')
    calls = recording(review, monkeypatch)
    monkeypatch.delenv('PROCESS_PUSH_TARGETS', raising=False)
    hard, _ = review.check(root)
    assert any('merge bases' in h and 'rebase onto the integration branch' in h for h in hard), hard
    with pytest.raises(review.GitReadError, match='merge bases'):
        review.merge_base(root)
    # the hook's own standing-block check refuses the range instead of crashing
    assert any('merge bases' in f for f in review.standing_block_findings(root)), \
        review.standing_block_findings(root)
    # _history grants no template coverage, and never binds a picked SHA
    review._history(root, git(root, 'rev-parse', 'feature~1'), tip)
    assert all(c[1] == 'main' for c in calls), calls
    finish = load('finish')
    monkeypatch.setattr(finish, 'gate_runner_argv', lambda root: [sys.executable, '-c', 'pass'])
    blockers, _ = finish.check(root)
    assert any('merge bases' in b for b in blockers), blockers


def test_a_tip_the_integration_ref_contains_never_reads_a_fallback(tmp_path, monkeypatch):
    """Refute: on main (origin/main == HEAD) a criss-crossed upstream/main made main red."""
    root = tmp_path / 'p'
    tip = criss_cross(root)
    git(root, 'update-ref', 'refs/remotes/origin/main', tip)
    git(root, 'update-ref', 'refs/remotes/upstream/main', git(root, 'rev-parse', 'main'))
    review = load('check_review')
    assert review.merge_base(root) is None
    monkeypatch.setenv('PROCESS_PUSH_TARGETS', 'refs/heads/main')
    hard, _ = review.check(root)
    assert not any('merge bases' in h for h in hard), hard


def test_a_forged_primary_ref_at_the_tip_does_not_switch_the_base_off(tmp_path, monkeypatch):
    """Refute 2: origin/main forged to HEAD made the base None and every base-scoped arm
    (the template verification among them) silent; local main still forks the tip."""
    root = tmp_path / 'p'
    init(root)
    write(root, 'README.md', 'base\n')
    fork = commit(root)
    git(root, 'checkout', '-qb', 'feature')
    write(root, 'feature.md', 'x\n')
    tip = commit(root)
    git(root, 'update-ref', 'refs/remotes/origin/main', tip)
    review = load('check_review')
    assert review.merge_base(root) == fork and review.integration_ref(root) == 'main'
    calls = recording(review, monkeypatch)
    monkeypatch.setenv('PROCESS_PUSH_TARGETS', 'refs/heads/main')
    review.check(root)
    assert calls and calls[0][1] == 'main', calls  # the template arm ran


def test_callers_hand_verify_the_integration_ref(update, monkeypatch):
    """Gate, finish, _history and the plan exemption pass the ref; verify forks it."""
    root, _, base, _ = update
    move_main(root)
    review = load('check_review')
    calls = recording(review, monkeypatch)
    monkeypatch.setenv('PROCESS_PUSH_TARGETS', 'refs/heads/main')
    hard, _ = review.check(root)
    assert hard == [], hard
    text = (root / '.process-work/plans/update.md').read_text()
    assert review.verified_template_plan(root, '.process-work/plans/update.md', text)
    review._history(root, base, 'HEAD')
    assert calls and all(c[1] == 'main' for c in calls), calls
    import template_verify as shared
    finish_calls = recording(shared, monkeypatch)
    finish = load('finish')
    monkeypatch.setattr(finish, 'gate_runner_argv', lambda root: [sys.executable, '-c', 'pass'])
    finish.check(root)
    assert finish_calls and all(c[1] == 'main' for c in finish_calls), finish_calls


def test_verify_binds_the_fork_point_when_integration_moved_on(update):
    root, _, base, verifier = update
    move_main(root)
    tip = git(root, 'rev-parse', 'HEAD')
    report = verifier.verify(root, 'main', tip)
    assert report['errors'] == [] and report['base'] == base
    assert report['acknowledged'] is True
    assert 'unrelated/main-only.md' not in report['project_delta']
    assert load('check_review').template_review_findings(root, report, [], tip=tip) == []


def test_template_findings_never_drop_errors_before_the_update(tmp_path):
    report = dict(base='x', head='y', update=False, identical=[], project_delta=[],
                  migration=False, errors=['cannot read base'], release_notes='')
    assert load('check_review').template_review_findings(tmp_path, report, []) == [
        'template verification failed: cannot read base']


def test_gate_reports_verification_errors_without_an_update(update, monkeypatch):
    root, _, _, _ = update
    review = load('check_review')
    failed = dict(base='x', head='y', update=False, identical=[], project_delta=[],
                  migration=False, errors=['cannot read base'], release_notes='')
    monkeypatch.setattr(review, 'verify', lambda *a, **k: dict(failed))
    monkeypatch.setenv('PROCESS_PUSH_TARGETS', 'refs/heads/main')
    hard, _ = review.check(root)
    assert 'template verification failed: cannot read base' in hard, hard


def test_gate_without_the_integration_ref_never_falls_back_to_the_sha(update, monkeypatch):
    root, _, _, _ = update
    review = load('check_review')
    calls = recording(review, monkeypatch)
    monkeypatch.setattr(review, 'integration_ref', lambda *a, **k: None)
    monkeypatch.setenv('PROCESS_PUSH_TARGETS', 'refs/heads/main')
    hard, _ = review.check(root)
    assert any('integration ref behind the merge base disappeared' in h for h in hard), hard
    # the plan exemption resolves its own ref; nothing ever verifies a fork SHA
    assert all(c[1] == 'main' for c in calls), calls


# --- _file: below the root, whatever the path flavour; host symlinks above it are fine ---

def test_verification_tolerates_a_symlinked_temp_ancestor(update, tmp_path, monkeypatch):
    """macOS puts temp under /var (a symlink); that is no render-path error."""
    import tempfile
    root, _, base, verifier = update
    real = tmp_path / 'real-tmp'
    real.mkdir()
    link = tmp_path / 'linked-tmp'
    link.symlink_to(real, target_is_directory=True)
    monkeypatch.setattr(tempfile, 'tempdir', str(link))
    proof = verifier.verify(root, base, worktree=True)
    assert proof['errors'] == [], proof
    assert 'docs/process/example.md' in proof['identical']


@pytest.mark.parametrize('rel', ['inner/escape/file', '../outside/file', 'inner/../../outside/file',
                                 '\\outside\\file', 'C:x', 'C:\\x', 'C:/x'])
def test_file_refuses_every_escape_below_the_root(tmp_path, rel):
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'file').write_text('secret', encoding='utf-8')
    root = tmp_path / 'render'
    (root / 'inner').mkdir(parents=True)
    (root / 'inner' / 'escape').symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        load('template_verify')._file(root, rel)


@pytest.mark.parametrize('src', ['--upload-pack=touch pwned', '-u x', 'ext::sh -c touch% pwned'])
def test_an_option_shaped_template_source_never_reaches_git_or_copier(update, monkeypatch, src):
    """`_src_path` comes from the project's answers; as an option it would run a command."""
    root, source, base, verifier = update
    answers = root / '.copier-answers.yml'
    git(root, 'checkout', '-qb', 'injected', base)
    answers.write_text(answers.read_text().replace(str(source), src))
    forged_base = commit(root)
    answers.write_text(answers.read_text().replace('v1.0.0', 'v1.1.0'))
    commit(root)
    ran = []
    monkeypatch.setattr(verifier, 'render', lambda *a, **k: ran.append(a) or False)
    monkeypatch.setattr(verifier, '_clone', lambda *a, **k: ran.append(a) or root)
    proof = verifier.verify(root, forged_base)
    assert any('unsupported template source' in e for e in proof['errors']), proof
    assert not proof['identical'] and ran == []
    with pytest.raises(ValueError, match='unsupported template source'):
        verifier._source(src)
    assert load('template_update').render(src, 'v1.0.0', {}, root.parent / 'never') is False


def test_without_copier_or_uvx_the_render_names_copier(update, monkeypatch):
    """#161: no Copier and no uvx was a FileNotFoundError deep in a gate run."""
    root, _, base, verifier = update
    updater = sys.modules['template_update']
    monkeypatch.setattr(updater.shutil, 'which', lambda _name: None)
    with pytest.raises(ValueError, match='copier required'):
        updater._copier('--version')
    proof = verifier.verify(root, base)
    assert any('copier required' in e for e in proof['errors']), proof
    assert not proof['identical']


def test_only_template_verify_declares_pyyaml_the_gates_import_it_lazily():
    """The gate and finish reach PyYAML only through template_verify's lazy import,
    whose error names the tool; a header on them would make every gate run `uv run`."""
    for script, declared in (('template_verify.py', True), ('check_review.py', False),
                             ('finish.py', False)):
        head = (SCRIPTS / script).read_text(encoding='utf-8').split('"""', 1)[0]
        assert ('# /// script' in head) is declared, script


@pytest.mark.parametrize('src', ['-a@h:p', 'gh:-x/y', 'git@host:-x', 'https://-x/y', 'ext::sh -c x',
                                 'https://h/a::b', 'relative/dir', '.', '--x'])
def test_template_source_refuses_every_option_or_helper_form(src):
    with pytest.raises(ValueError, match='unsupported template source'):
        load('template_update').template_source(src)


@pytest.mark.parametrize('src', ['gh:owner/repo', 'https://github.com/o/r.git', 'ssh://git@host/o/r.git',
                                 'git@github.com:o/r.git', 'user@h:~/r', 'git@h:/abs/r.git'])
def test_template_source_accepts_the_supported_forms(src, tmp_path):
    updater = load('template_update')
    assert updater.template_source(src) == src
    assert updater.template_source(str(tmp_path)) == str(tmp_path)


def test_copier_gets_the_source_after_an_end_of_options_marker(monkeypatch, tmp_path):
    updater = load('template_update')
    seen = []
    monkeypatch.setattr(updater, '_copier', lambda *a, **k: seen.append(a) or
                        subprocess.CompletedProcess(a, 0, '', ''))
    assert updater.render(str(tmp_path), 'v1', {}, tmp_path / 'dst', trusted=False)
    argv = list(seen[0])
    assert argv[argv.index('--') + 1] == str(tmp_path), argv


def test_the_shared_clone_works_under_safe_bare_repository_explicit(tmp_path, monkeypatch):
    """macOS downstream: `safe.bareRepository=explicit` refused `git -C <bare clone>`,
    so the review gate failed before it read a single release."""
    src = tmp_path / 'src'
    src.mkdir()
    git(src, 'init', '-q', '-b', 'main')
    git(src, 'config', 'user.email', 't@example.invalid')
    git(src, 'config', 'user.name', 'T')
    write(src, 'CHANGELOG.md', 'v1\n')
    commit(src)
    git(src, 'tag', 'v1.0.0')
    cfg = tmp_path / 'gitconfig'
    cfg.write_text('[safe]\n\tbareRepository = explicit\n', encoding='utf-8')
    monkeypatch.setenv('GIT_CONFIG_GLOBAL', str(cfg))
    verifier = load('template_verify')
    sha = git(src, 'rev-parse', 'HEAD')
    assert verifier._fetched(str(src), 'v1.0.0', 'v1.0.0') == sha


@pytest.mark.parametrize('src', ['ext::x', 'git+ext::x', '--upload-pack=x', 'ssh://-oProxyCommand=x',
                                 'file:///x', 'relative/x'])
def test_template_update_refuses_an_unsupported_source_before_copier_runs(tmp_path, src):
    """#167: main() ran `copier update` on whatever `_src_path` the answers named."""
    root, bin_dir, log = tmp_path / 'project', tmp_path / 'bin', tmp_path / 'copier.log'
    init(root)
    write(root, '.copier-answers.yml', f"_src_path: '{src}'\n_commit: v1.0.0\n")
    commit(root)
    stub = write(bin_dir, 'copier', f'#!/bin/sh\necho "$@" >> {log}\nexit 0\n')
    stub.chmod(0o755)
    env = {**os.environ, 'PATH': f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
           'PYTHONDONTWRITEBYTECODE': '1'}
    r = subprocess.run([sys.executable, str(SCRIPTS / 'template_update.py'), str(root)],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 2, r.stdout + r.stderr
    assert 'unsupported template source' in r.stderr
    assert not log.exists()
