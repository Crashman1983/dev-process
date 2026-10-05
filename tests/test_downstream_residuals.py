"""#142: downstream regressions reproduced on the template itself."""
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / 'template/scripts/process'


def load(name):
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(SCRIPTS))
    try:
        spec = importlib.util.spec_from_file_location(name + '_residual', SCRIPTS / (name + '.py'))
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        return mod
    finally:
        sys.path.remove(str(SCRIPTS))


def git(root, *args):
    return subprocess.run(['git', '-C', str(root), *args], capture_output=True,
                          text=True, check=True).stdout.strip()


def commit(root, path, text):
    dest = root / path
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text)
    git(root, 'add', '-A')
    git(root, 'commit', '-qm', path)
    return git(root, 'rev-parse', 'HEAD')


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, 'init', '-q', '-b', 'main')
    git(tmp_path, 'config', 'user.name', 'Test')
    git(tmp_path, 'config', 'user.email', 'test@example.com')
    commit(tmp_path, 'code.py', 'a = 0\n')
    return tmp_path


def test_main_without_remote_never_has_an_empty_self_base(repo, monkeypatch):
    review = load('check_review')
    commit(repo, '.process-work/plans/2026-10-02-42.md', '# Plan\ntier: 3\nissue: #42\n')
    assert review.merge_base(repo) is None
    assert review.paths_in_flight(repo) is None
    # a presence finding (#161): hard on the merge push, a note elsewhere
    monkeypatch.setenv('PROCESS_PUSH_TARGETS', 'refs/heads/main')
    hard, _ = review.check(repo)
    assert any('integration' in x and 'base' in x for x in hard), hard
    monkeypatch.setenv('PROCESS_PUSH_TARGETS', 'refs/heads/7-work')
    monkeypatch.delenv('PRE_COMMIT_REMOTE_BRANCH', raising=False)
    hard, soft = review.check(repo)
    assert not any('integration' in x and 'base' in x for x in hard), hard
    assert any('no proper integration base' in x and 'note only' in x for x in soft), soft


@pytest.mark.parametrize("default", ["trunk", "release/stable"])
def test_default_branch_is_an_integration_target(repo, default):
    git(repo, 'branch', '-m', default)
    git(repo, 'update-ref', 'refs/remotes/origin/' + default, 'HEAD')
    git(repo, 'symbolic-ref', 'refs/remotes/origin/HEAD', 'refs/remotes/origin/' + default)
    guard = load('merge_route')
    verdict = guard.check(repo, ['refs/heads/' + default], {'PROCESS_PHASE': 'review'})
    assert not verdict.ok and 'review' in verdict.message
    assert guard.hook_check(repo, {'PRE_COMMIT_REMOTE_BRANCH': 'refs/heads/' + default}) == 1
    assert load('train').local_integration(repo) == default
    assert load('finish').check(repo)[0] == [f'on {default} — there is no feature branch to finish']
    attest = load('attest')
    assert attest._journal_target(repo, repo / 'journal').parent == repo / 'journal'
    assert 'refs/heads/stable' not in load('check_review').integration_targets(repo)
    wt = load('dispatch').ensure_worktree(repo, 'feature')
    assert git(wt, 'rev-parse', 'HEAD') == git(repo, 'rev-parse', 'HEAD')


def test_train_accepts_the_same_review_pool_as_the_gate(repo):
    review, train = load('check_review'), load('train')
    base = git(repo, 'rev-parse', 'HEAD')
    git(repo, 'checkout', '-qb', 'work')
    commit(repo, '.process-work/plans/2026-10-02-a.md', '# A\ntier: 2\n')
    commit(repo, '.process-work/plans/2026-10-02-b.md', '# B\ntier: 2\n')
    a = commit(repo, 'code.py', 'a = 1\n')
    b = commit(repo, 'code.py', 'a = 2\n')
    passes = [{'work': 'a', 'tier': '2', 'base': base, 'head': a},
              {'work': 'b', 'tier': '2', 'base': a, 'head': b}]
    pool = review._reviewed_heads(passes, 2, {'a', 'b'})
    assert review.stale_review(repo, passes, {'a'}, 2, set(), pool) is None
    git(repo, 'checkout', 'main')
    assert train._covers(repo, passes, {'a'}, 2, b)
    git(repo, 'checkout', 'work')
    commit(repo, 'code.py', 'a = 3\n')
    assert not train._covers(repo, passes, {'a'}, 2, 'HEAD')


def test_replaced_objects_do_not_change_the_guard_range(repo):
    review = load('check_review')
    base = git(repo, 'rev-parse', 'HEAD')
    tip = commit(repo, '.process-work/journal/42.md',
                 'REVIEW work=42 tier=1 reviewer=x model=m independence=non-implementing '
                 'verdict=block round=1\n')
    tree = git(repo, 'rev-parse', base + '^{tree}')
    replacement = git(repo, 'commit-tree', tree, '-p', base, '-m', 'fake no block')
    git(repo, 'replace', tip, replacement)
    findings = review.standing_block_findings(repo, tip, remote_sha=base)
    assert any('42' in x and 'block' in x for x in findings), findings


def test_push_base_refuses_a_non_fast_forward(repo):
    review = load('check_review')
    base = git(repo, 'rev-parse', 'HEAD')
    remote = commit(repo, 'remote.py', 'remote\n')
    git(repo, 'checkout', '--detach', base)
    tip = commit(repo, 'feature.py', 'feature\n')
    assert review.push_base(repo, tip, remote) is None


def test_contradicting_session_anchors_are_defects(repo, monkeypatch):
    dispatch, guard = load('dispatch'), load('merge_route')
    rec = {'branch': 'work', 'phase': 'review', 'pid': os.getpid(),
           'pid_start': 'live', 'tmux_window': '@stale'}
    path = repo / 'record.json'
    path.write_text(json.dumps(rec))
    # both callers must consult the same owner of liveness
    owner = sys.modules['dispatch']
    monkeypatch.setattr(owner, '_same_process', lambda r: True)
    monkeypatch.setattr(owner, '_pane_state', lambda w: 'gone')
    assert 'contradict' in guard._record_defect(path)
    monkeypatch.setattr(dispatch, '_same_process', lambda r: True)
    monkeypatch.setattr(dispatch, '_pane_state', lambda w: 'gone')
    monkeypatch.setattr(dispatch, '_record_files', lambda r: [rec])
    assert dispatch.records(repo)[0]['state'] == 'unknown'


def test_dead_worker_is_a_tower_finding():
    tower = load('tower')
    table = {'overlaps': [], 'plans': [], 'gates': [], 'worktrees': [], 'reports': [],
             'sessions': [{'branch': 'work', 'state': 'gone', 'alive': False,
                           'report_state': 'pushed', 'phase': 'execute'}]}
    assert any(f['kind'] == 'dead-worker' for f in tower.findings(table, 60))


def test_phase_commands_do_not_override_the_policy(render, tmp_path):
    root = render(tmp_path, {'project_name': 'test'})
    for phase in ('plan', 'brainstorm', 'review'):
        assert '\nmodel:' not in (root / '.claude/commands' / (phase + '.md')).read_text()


def test_brainstorm_has_its_own_prompt_and_never_auto_executes(repo):
    dispatch = load('dispatch')
    assert 'brainstorm' in dispatch.PHASES
    prompt = dispatch.prompt_for('brainstorm', 42, 3, 'work', 'model')
    assert prompt.startswith('/brainstorm') and 'owner' in prompt
    assert 'report `planned`' not in prompt


def test_finish_archive_preflight_preserves_a_clean_tree(repo, monkeypatch, capsys):
    finish = load('finish')
    names = ['2026-10-02-a.md', '2026-10-02-b.md']
    for name in names:
        commit(repo, '.process-work/plans/' + name, '# Plan\ntier: 1\n')
    commit(repo, '.process-work/plans/archive/' + names[1], 'existing history\n')
    git(repo, 'checkout', '-qb', 'feature')
    monkeypatch.setattr(finish, 'ROOT', repo)
    monkeypatch.setattr(finish, 'check', lambda r: ([], []))
    finish.check.last_archive = names
    assert finish.apply(repo, tests=None, tests_passed=False) == 1
    assert not git(repo, 'status', '--porcelain')
    assert (repo / '.process-work/plans' / names[0]).exists()
    assert names[1] in capsys.readouterr().err


@pytest.mark.parametrize("dirty_main", [False, True])
def test_finish_from_a_worktree_with_an_unpublished_branch(render, tmp_path, dirty_main):
    root = render(tmp_path / 'root', {'project_name': 'test'})
    git(root, 'init', '-q', '-b', 'main')
    git(root, 'config', 'user.name', 'Test')
    git(root, 'config', 'user.email', 'test@example.com')
    commit(root, 'base.txt', 'base\n')
    bare = tmp_path / 'remote.git'
    git(root, 'clone', '--bare', str(root), str(bare))
    git(root, 'remote', 'add', 'origin', str(bare))
    git(root, 'fetch', 'origin')
    wt = tmp_path / 'feature'
    git(root, 'worktree', 'add', '-b', 'feature', str(wt))
    tip = commit(wt, 'feature.txt', 'feature\n')
    primary_head = git(root, 'rev-parse', 'HEAD')
    if dirty_main:
        (root / 'base.txt').write_text('local owner work\n')
    result = subprocess.run([sys.executable, str(wt / 'scripts/process/finish.py'),
                             '--apply', '--tests-passed'], cwd=wt, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert git(bare, 'rev-parse', 'main') == tip
    if dirty_main:
        assert git(root, 'rev-parse', 'HEAD') == primary_head
        assert (root / 'base.txt').read_text() == 'local owner work\n'
    else:
        assert git(root, 'rev-parse', 'HEAD') == tip
    assert git(wt, 'symbolic-ref', '--short', 'HEAD') == 'feature'
    assert not git(bare, 'for-each-ref', '--format=%(refname)', 'refs/heads/feature')


def test_attest_commits_a_relative_journal_under_the_explicit_root(render, tmp_path):
    root = render(tmp_path / 'root', {'project_name': 'test'})
    git(root, 'init', '-q', '-b', 'main')
    git(root, 'config', 'user.name', 'Test')
    git(root, 'config', 'user.email', 'test@example.com')
    commit(root, 'base.txt', 'base\n')
    result = subprocess.run([sys.executable, str(root / 'scripts/process/attest.py'),
                             '--work', '42', '--tier', '1', '--reviewer', 'fresh', '--model', 'm',
                             '--independence', 'non-implementing', '--verdict', 'pass',
                             '--journal-dir', 'custom-journal', '--commit', str(root)],
                            cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert git(root, 'ls-tree', '-r', '--name-only', 'HEAD', '--', 'custom-journal')
    assert not (tmp_path / 'custom-journal').exists()


def test_doc_drift_checks_python_definitions_not_comments(render, tmp_path):
    root = render(tmp_path, {'project_name': 'test', 'modules': {'doc_drift_gate': True}})
    code = root / 'code.py'
    code.write_text('class Worker:\n    async def run(self): pass\n# missing exists only in this comment\n')
    doc = root / 'ARCHITECTURE.md'
    doc.write_text('`code.py::Worker.run()`\n`code.py::missing`\n')
    result = subprocess.run([sys.executable, str(root / 'scripts/process/check_doc_drift.py'), str(root)],
                            capture_output=True, text=True)
    assert result.returncode == 1 and 'missing' in result.stdout
    assert 'Worker.run' not in result.stdout
    doc.write_text('`./code.py::Worker.run(self)`\n')
    result = subprocess.run([sys.executable, str(root / 'scripts/process/check_doc_drift.py'), str(root)],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stdout


def test_tower_runs_local_findings_without_replacing_core_findings(render, tmp_path):
    root = render(tmp_path, {'project_name': 'test'})
    git(root, 'init', '-q', '-b', 'main')
    payload = [{'kind': 'orphan-server', 'severity': 'high', 'what': 'port 8211 pid 42',
                'because': 'no active lane claim'}]
    (root / 'local_findings.py').write_text('import json\nprint(json.dumps(' + repr(payload) + '))\n')
    config = root / 'docs/process/tower.local.json'
    config.write_text(json.dumps({'servers': {'command': [sys.executable, 'local_findings.py']}}))
    result = subprocess.run([sys.executable, str(root / 'scripts/process/tower.py'), '--json'],
                            cwd=root, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert any(f['kind'] == 'orphan-server' for f in json.loads(result.stdout)['findings'])
    config.write_text('{broken')
    result = subprocess.run([sys.executable, str(root / 'scripts/process/tower.py'), '--json'],
                            cwd=root, capture_output=True, text=True)
    assert any(f['kind'] == 'local-findings-error' for f in json.loads(result.stdout)['findings'])


def test_delta_excludes_imported_main_and_binds_the_reduced_diff(repo):
    bundle, review = load('make_review_bundle'), load('check_review')
    git(repo, 'checkout', '-qb', 'feature')
    since = commit(repo, 'code.py', 'a = 1\n')
    commit(repo, 'feature.py', 'owned change\n')
    git(repo, 'checkout', 'main')
    commit(repo, 'main.py', 'main-only content\n')
    git(repo, 'checkout', 'feature')
    git(repo, 'merge', '--no-ff', '-m', 'bring main', 'main')
    artifact = bundle._review_artifact(repo, since, delta=True)
    assert 'feature.py' in artifact.text and 'main.py' not in artifact.text
    assert artifact.digest == review.artifact_digest(repo, since, git(repo, 'rev-parse', 'HEAD'), mode='delta')


def test_bundle_ignores_a_design_docs_tier_when_scoping_a_delta(repo):
    bundle = load('make_review_bundle')
    git(repo, 'checkout', '-qb', 'feature')
    since = git(repo, 'rev-parse', 'HEAD')
    plan = repo / '.process-work/plans/design-look.md'
    commit(repo, str(plan.relative_to(repo)), '# Design\ntier: 3\n')
    text = bundle.build(repo, 'main', since=since, plans=[plan], declared_tier=2)
    assert 'REVIEW_SCOPE mode=delta' in text


def test_non_fast_forward_requires_a_logged_owner_override(repo, monkeypatch):
    guard = load('merge_route')
    base = git(repo, 'rev-parse', 'HEAD')
    remote = commit(repo, 'remote.py', 'remote\n')
    git(repo, 'checkout', '--detach', base)
    tip = commit(repo, 'feature.py', 'feature\n')
    line = guard.RefLine('HEAD', tip, 'refs/heads/main', remote)
    monkeypatch.setattr(guard, 'session_phases', lambda r, env: (set(), ''))
    verdict = guard.ref_update_verdict(repo, [line], {'PROCESS_MERGE_ROUTE': 'train'})
    assert not verdict.ok and 'fast-forward' in verdict.message
    verdict = guard.ref_update_verdict(repo, [line], {'PROCESS_OWNER_OVERRIDE': 'restore approved state'})
    assert verdict.ok and verdict.ledger == ('override', 'restore approved state')
    commit(repo, '.process-work/journal/42.md',
           'REVIEW work=42 tier=1 reviewer=x model=m independence=non-implementing verdict=block round=1\n')
    blocked_remote = git(repo, 'rev-parse', 'HEAD')
    git(repo, 'checkout', '--detach', tip)
    verdict = guard.ref_update_verdict(repo, [line._replace(remote_sha=blocked_remote)],
                                      {'PROCESS_OWNER_OVERRIDE': 'restore approved state'})
    assert not verdict.ok and '42' in verdict.message and 'block' in verdict.message


def test_train_push_timeout_covers_long_hooks_and_is_configurable(repo, monkeypatch):
    train = load('train')
    seen = []
    def run(argv, **kw):
        seen.append(kw['timeout'])
        return subprocess.CompletedProcess(argv, 0, '', '')
    monkeypatch.setattr(train.subprocess, 'run', run)
    monkeypatch.delenv('PROCESS_TRAIN_PUSH_TIMEOUT_SECONDS', raising=False)
    train._git(repo, 'push', 'origin', 'HEAD:main')
    assert seen == [1800]
    monkeypatch.setenv('PROCESS_TRAIN_PUSH_TIMEOUT_SECONDS', '2400')
    train._git(repo, 'push', 'origin', 'HEAD:main')
    assert seen[-1] == 2400
    train._git(repo, 'rev-parse', 'HEAD')
    assert seen[-1] == 300
    monkeypatch.setenv('PROCESS_TRAIN_PUSH_TIMEOUT_SECONDS', '0')
    before = len(seen)
    result = train._git(repo, 'push', 'origin', 'HEAD:main')
    assert result.returncode != 0 and len(seen) == before


def test_worker_channel_names_events_and_empty_channel_keeps_the_prompt():
    dispatch = load('dispatch')
    args = ('execute', 42, 2, 'work', 'model')
    plain = dispatch.prompt_for(*args)
    assert dispatch.prompt_for(*args, channel='') == plain
    with_channel = dispatch.prompt_for(*args, channel="SendMessage to 'steward'")
    for event in ('planned', 'pushed', 'blocked', 'review pass', 'review block', 'done',
                  'gate or CI', 'push gate', 'scope or plan conflict'):
        assert event in with_channel, event
    assert 'one line' in with_channel and 'report.py' in with_channel


def test_steward_channel_and_restart_contract_reaches_each_harness(render, tmp_path):
    root = render(tmp_path, {'project_name': 'test',
                            'harnesses': {'claude': True, 'agents_md': True, 'copilot': True}})
    for path in ('.claude/commands/steward.md', 'AGENTS.md', '.github/copilot-instructions.md'):
        text = (root / path).read_text()
        assert 'decision_channel' in text and 'restart' in text and 'reports' in text


@pytest.mark.parametrize('text,expected', [
    ('```\ntier: 3\n```\ntier: 1\n', 1),
    ('<!--\ntier: 3\n-->\ntier: 2\n', 3),
    ('tier: 1\ntier: 3 was considered\n', 1),
])
def test_dispatch_uses_the_owners_tier_grammar(repo, monkeypatch, text, expected):
    dispatch = load('dispatch')
    monkeypatch.setattr(dispatch, '_own_plans_on_origin', lambda r, b: ('tip', ['.process-work/plans/p.md']))
    monkeypatch.setattr(dispatch, '_out', lambda *a: text)
    assert dispatch.plan_tier_on_origin(repo, 'work') == expected


def test_delta_carries_conflict_resolution_and_the_gate_verifies_its_mode(repo):
    bundle, review = load('make_review_bundle'), load('check_review')
    git(repo, 'checkout', '-qb', 'feature')
    since = commit(repo, 'own.py', 'own before review\n')
    commit(repo, 'code.py', 'a = 1\n')
    git(repo, 'checkout', 'main')
    commit(repo, 'code.py', 'a = 2\n')
    commit(repo, 'main.py', 'main-only content\n')
    git(repo, 'checkout', 'feature')
    merged = subprocess.run(['git', '-C', str(repo), 'merge', 'main'], capture_output=True)
    assert merged.returncode != 0
    head = commit(repo, 'code.py', 'a = 3\n')
    artifact = bundle._review_artifact(repo, since, delta=True)
    assert 'a = 3' in artifact.text and 'main-only content' not in artifact.text
    line = (f'REVIEW work=42 tier=2 reviewer=fresh model=m independence=bundle,non-implementing '
            f'verdict=pass round=1 base={since} head={head} diff={artifact.digest} mode=delta')
    records, errors = review.parse_review_lines(line)
    assert not errors
    assert review._integrity_violations('journal', repo, records) == ([], [])
    wrong, _ = review.parse_review_lines(line.replace(' mode=delta', ''))
    assert review._integrity_violations('journal', repo, wrong)[0]
    tier3, errors = review.parse_review_lines(line.replace('tier=2', 'tier=3'))
    assert not errors and review.invalid_deltas(repo, [f for _ln, f in tier3])  # no full round at `since`


def test_delta_refuses_to_hide_an_unreviewed_feature_merge(repo):
    bundle = load('make_review_bundle')
    git(repo, 'checkout', '-qb', 'feature')
    since = git(repo, 'rev-parse', 'HEAD')
    git(repo, 'checkout', '-qb', 'other-feature')
    commit(repo, 'unreviewed.py', 'unreviewed implementation\n')
    git(repo, 'checkout', 'feature')
    commit(repo, 'own.py', 'own implementation\n')
    git(repo, 'merge', '--no-ff', '-m', 'other feature', 'other-feature')
    assert bundle._review_artifact(repo, since, delta=True) is None
    with pytest.raises(SystemExit, match='full review'):
        bundle.build(repo, 'main', since=since, declared_tier=2)


def test_brainstorm_history_requires_explicit_plan_approval_even_after_stop(repo, monkeypatch):
    dispatch = load('dispatch')
    policy = repo / dispatch.POLICY
    policy.parent.mkdir(parents=True, exist_ok=True)
    policy.write_text((SCRIPTS.parents[1] / dispatch.POLICY).read_text())
    history = dispatch._records_dir(repo) / 'phases' / '42.json'
    history.parent.mkdir(parents=True, exist_ok=True)
    history.write_text(json.dumps({'phase': 'brainstorm'}))
    monkeypatch.setattr(dispatch, 'disk_refusal', lambda p: None)
    args = dict(issue=42, tier=2, branch='work', title=None, dry_run=True)
    assert dispatch.start(repo, phase='execute', owner_approved=True, **args) == 3
    assert dispatch.start(repo, phase='plan', **args) == 3
    assert dispatch.start(repo, phase='plan', owner_approved=True, **args) == 0
    assert dispatch.start(repo, phase='brainstorm', **{**args, 'tier': 1}) == 3


def test_replaced_tip_cannot_manufacture_a_standing_block(repo):
    review = load('check_review')
    base = git(repo, 'rev-parse', 'HEAD')
    fake = commit(repo, '.process-work/journal/42.md',
                  'REVIEW work=42 tier=1 reviewer=x model=m independence=non-implementing '
                  'verdict=block round=1\n')
    git(repo, 'reset', '--hard', base)
    tip = commit(repo, 'code.py', 'a = 1\n')
    git(repo, 'replace', tip, fake)
    assert not review.standing_block_findings(repo, tip, remote_sha=base)


def test_archive_rolls_back_an_earlier_move_when_the_next_move_fails(repo, monkeypatch, capsys):
    finish = load('finish')
    names = ['2026-10-02-a.md', '2026-10-02-b.md']
    for name in names:
        commit(repo, '.process-work/plans/' + name, '# Plan\ntier: 1\n')
    git(repo, 'checkout', '-qb', 'feature')
    monkeypatch.setattr(finish, 'ROOT', repo)
    monkeypatch.setattr(finish, 'check', lambda r: ([], []))
    finish.check.last_archive = names
    original = finish._sh
    def fail_second(root, argv, env=None):
        if argv[:2] == ['git', 'mv'] and argv[2].endswith('/' + names[1]):
            return False
        return original(root, argv, env)
    monkeypatch.setattr(finish, '_sh', fail_second)
    assert finish.apply(repo, tests=None, tests_passed=False) == 1
    assert not git(repo, 'status', '--porcelain')
    assert all((repo / '.process-work/plans' / n).is_file() for n in names)
    assert names[1] in capsys.readouterr().err


def test_stop_repairs_a_live_pid_with_a_stale_tmux_anchor(repo, monkeypatch):
    dispatch = load('dispatch')
    path = dispatch._record_path(repo, 'work')
    path.write_text(json.dumps({'branch': 'work', 'pid': 12345, 'pid_start': 'verified',
                                'tmux_window': '@1', 'phase': 'execute'}))
    monkeypatch.setattr(dispatch, '_pane_state', lambda w: 'dead')
    live = [True]
    monkeypatch.setattr(dispatch, '_same_process', lambda r: live[0])
    monkeypatch.setattr(dispatch.os, 'getpgid', lambda pid: pid)
    killed = []
    def terminate(pid, signal):
        killed.append(pid)
        live[0] = False
    monkeypatch.setattr(dispatch.os, 'killpg', terminate)
    assert dispatch.records(repo)[0]['state'] == 'unknown'
    assert dispatch.stop(repo, 'work', force=False, keep_report=True) == 0
    assert killed == [12345] and not path.exists()


def test_three_stacked_reviews_cover_overlapping_files_but_not_a_late_commit(repo, monkeypatch):
    """#132: the complete merge gate checks three real, digest-bound review ranges."""
    review = load('check_review')
    git(repo, 'checkout', '-qb', 'stack')
    records = []
    for name in ['a', 'b', 'c']:
        commit(repo, f'.process-work/plans/{name}.md', '# Plan\ntier: 2\n\n## Decisions\n')
        base = git(repo, 'rev-parse', 'HEAD')
        head = commit(repo, 'code.py', f'value = {name!r}\n')
        digest = review.artifact_digest(repo, base, head)
        records.append(f'REVIEW work={name} tier=2 reviewer=fresh model=same '
                       'independence=bundle,non-implementing verdict=pass round=1 '
                       f'base={base} head={head} diff={digest}')
        commit(repo, '.process-work/journal/stack.md', '\n'.join(records) + '\n')
    monkeypatch.setenv('PROCESS_PUSH_TARGETS', 'refs/heads/main')
    hard, _ = review.check(repo)
    assert not hard, hard
    commit(repo, 'code.py', 'unreviewed = True\n')
    hard, _ = review.check(repo)
    assert sum('code changed after the reviewed head' in h for h in hard) >= 3, hard
    records[-1] = records[-1].split(' diff=')[0] + ' diff=' + '0' * 64
    commit(repo, '.process-work/journal/stack.md', '\n'.join(records) + '\n')
    hard, _ = review.check(repo)
    assert any('digest' in h for h in hard), hard


@pytest.mark.parametrize('spec, plan, want', [
    ('issue: #12\n', 'issue: #7\n', 12),
    ('issue: GH-12\n', 'issue: #7\n', None),          # refute: went to plan's #7
    ('issue: GH-12\n- issue: #3\n', '', None),        # refute: a later line won
    ('issue: none\nissue: #5\n', '', None),
    ('# no issue line\n', 'issue: #7\n', 7),          # no spec decl → plan.md
    ('', '', None),
], ids=['spec', 'unparseable-spec-no-plan-fallback', 'unparseable-first-line',
        'none-first', 'plan-fallback', 'nothing'])
def test_a_spec_dirs_first_issue_line_decides(tmp_path, spec, plan, want):
    """Refute of v2.46: the shared helper took any later or plan.md ref when the
    spec's first `issue:` line was unparseable — a snapshot went to the wrong issue."""
    cr = load('check_review')
    d = tmp_path / '003-x'
    d.mkdir()
    if spec:
        (d / 'spec.md').write_text(spec)
    if plan:
        (d / 'plan.md').write_text(plan)
    assert cr.spec_dir_issue(d) == want
