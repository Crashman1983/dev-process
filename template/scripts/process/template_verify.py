#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["PyYAML>=6"]
# ///
"""Compute template provenance; no saved report grants a review exemption.

The integration baseline chooses the trusted source. Both release renders
must match: losing an old project customization is a project delta too.
Git blobs, executable bits and symlink targets are compared, not decoded text.
"""
from __future__ import annotations

import argparse
import functools
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from process_git import git_environment  # noqa: E402
from template_update import ANSWERS, OWNED_FILE, answers, is_owned, owned_patterns, render as template_render  # noqa: E402


def render(src: str, ref: str, data: dict[str, str], dst: Path) -> bool:
    return template_render(src, ref, data, dst, trusted=False)


ACK = '.process-work/template-update-ack.json'
PIN = re.compile(r'(?:v?\d+\.\d+\.\d+(?:[-+][\w.-]+)?|[0-9a-f]{40})\Z')


def git(root: Path, *args: str) -> bytes:
    r = subprocess.run(['git', '-C', str(root), *args], capture_output=True,
                       timeout=60, env=git_environment())
    if r.returncode:
        raise ValueError(r.stderr.decode(errors='replace').strip())
    return r.stdout


def _source(src: str) -> str:
    if src.startswith('gh:'):
        return 'https://github.com/' + src[3:].removesuffix('.git') + '.git'
    return src


def _release(src: str, ref: str) -> str:
    if not PIN.fullmatch(ref):
        raise ValueError('release must be a version tag or a full Git SHA (not HEAD)')
    if re.fullmatch('[0-9a-f]{40}', ref):
        return ref
    r = subprocess.run(['git', 'ls-remote', _source(src),
                        f'refs/tags/{ref}', f'refs/tags/{ref}^{{}}'],
                       capture_output=True, text=True, timeout=60, env=git_environment())
    lines = r.stdout.splitlines()
    if r.returncode or not lines:
        raise ValueError(f'cannot resolve release {ref}')
    return lines[-1].split()[0]  # annotated tag: its peeled commit


def _entry(root: Path, ref: str, rel: str) -> tuple[str, bytes] | None:
    raw = git(root, '--literal-pathspecs', 'ls-tree', '-z', ref, '--', rel)
    if not raw:
        return None
    mode, kind, oid = raw.split(b'\t', 1)[0].split()
    if kind != b'blob':
        raise ValueError(f'{rel}: unsupported Git object ({kind.decode()})')
    return mode.decode(), git(root, 'cat-file', 'blob', oid.decode())


def _file(root: Path, rel: str) -> tuple[str, bytes] | None:
    p = root / rel
    # A parent symlink could read outside the render/project; never follow it.
    if any(parent.is_symlink() for parent in p.parents if parent != root.parent):
        raise ValueError(f'{rel}: symlink parent')
    if p.is_symlink():
        return '120000', os.fsencode(os.readlink(p))
    if not p.exists():
        return None
    if not p.is_file():
        raise ValueError(f'{rel}: not a regular file')
    return ('100755' if p.stat().st_mode & 0o111 else '100644'), p.read_bytes()


def _reserved(rel: str, owned: list[str]) -> bool:
    parts = Path(rel).parts
    return (any('.local.' in part for part in parts)
            or any(part.lower() in {'tests', 'test', 'hooks', '.githooks', '.hooks'}
                   for part in parts)
            or Path(rel).name.lower() in {'makefile', 'gnumakefile', 'justfile'}
            or rel in {OWNED_FILE, '.pre-commit-config.yaml', '.pre-commit-config.yml'}
            or is_owned(rel, owned))


def _enforcement(rel: str) -> bool:
    # Helpers and configuration can change enforcement transitively too.
    return (rel.startswith('scripts/process/')
            or rel.startswith('.github/workflows/')
            or rel in {'.process-gates.yml', '.process-gates.yaml',
                       'docs/process/kernel.md', 'docs/process/mandatory-rules.md',
                       'docs/process/risk-tiers.md'})


def _verify(root: Path, base: str, tip: str, *, worktree: bool = False) -> dict:
    result = dict(base=base, head=tip, update=False, identical=[], project_delta=[],
                  migration=False, errors=[], release_notes='')
    try:
        before = _entry(root, base, ANSWERS)
        after = _file(root, ANSWERS) if worktree else _entry(root, tip, ANSWERS)
        if before is None or before == after:
            return result
        result['update'] = True
        if after is None:
            raise ValueError('recorded template answers were deleted; no provenance')
        try:
            import yaml
        except ImportError:
            raise ValueError('PyYAML required: uv run --script scripts/process/template_verify.py')
        with tempfile.TemporaryDirectory() as temp:
            d = Path(temp)
            old_answers, new_answers = d / 'old-answers', d / 'new-answers'
            old_answers.mkdir()
            new_answers.mkdir()
            (old_answers / ANSWERS).write_bytes(before[1])
            (new_answers / ANSWERS).write_bytes(after[1])
            try:
                old_record, new_record = yaml.safe_load(before[1]), yaml.safe_load(after[1])
            except yaml.YAMLError as exc:
                raise ValueError(f'invalid recorded answers: {exc}') from exc
            if not all(isinstance(record, dict) and
                       all(isinstance(record.get(key), str) for key in ('_commit', '_src_path'))
                       for record in (old_record, new_record)):
                raise ValueError('recorded answers must be a mapping with string source and pin')
            src, old_ref, old_data = answers(old_answers, migrate=False)
            new_src, new_ref, new_data = answers(new_answers, migrate=False)
            if old_ref == new_ref:
                result['update'] = False
                return result
            result['update'] = True
            if not src or not old_ref or not new_ref or src != new_src:
                raise ValueError('template source changed or release metadata is missing')
            old_sha, new_sha = _release(src, old_ref), _release(src, new_ref)
            result.update(old_release=old_sha, new_release=new_sha)
            old, new = d / 'old', d / 'new'
            if not render(src, old_sha, old_data, old) or not render(src, new_sha, new_data, new):
                raise ValueError('release re-render failed; no exemption')
            changed = set(os.fsdecode(p) for p in git(root, 'diff', '--name-only',
                                                     '--no-renames', '-z', base, tip).split(b'\0') if p)
            rendered_paths = {p.relative_to(folder).as_posix()
                              for folder in (old, new) for p in folder.rglob('*')
                              if p.is_file() or p.is_symlink()}
            # A pin bump that fails to apply a changed template file is a
            # project delta, even when that file is absent from git diff.
            changed |= {rel for rel in rendered_paths if _file(old, rel) != _file(new, rel)}
            if worktree:
                changed |= {os.fsdecode(p) for p in git(root, 'diff', '--name-only', '-z',
                                                        tip).split(b'\0') if p}
                changed |= {os.fsdecode(p) for p in git(root, 'ls-files', '--others',
                                                        '--exclude-standard', '-z').split(b'\0') if p}
            owned = owned_patterns(root)
            old_owned = _entry(root, base, OWNED_FILE)
            if old_owned:
                owned += [ln.strip() for ln in old_owned[1].decode().splitlines()
                          if ln.strip() and not ln.lstrip().startswith('#')]
            for rel in sorted(changed):
                if rel.startswith('.process-work/') and (rel == ACK or
                        rel.startswith(('.process-work/journal/', '.process-work/plans/',
                                        '.process-work/state/'))):
                    continue  # existing review bookkeeping, not template evidence
                actual_old = _entry(root, base, rel)
                actual_new = _file(root, rel) if worktree else _entry(root, tip, rel)
                old_render, new_render = _file(old, rel), _file(new, rel)
                exact = (actual_old == old_render and actual_new == new_render
                         and (old_render is not None or new_render is not None)
                         and not _reserved(rel, owned))
                if rel == ANSWERS:
                    exact = ({k: v for k, v in old_record.items() if k != '_commit'} ==
                             {k: v for k, v in new_record.items() if k != '_commit'}
                             and not is_owned(rel, owned))
                result['identical' if exact else 'project_delta'].append(rel)
                if _enforcement(rel) and (old_render != new_render or actual_old != actual_new):
                    result['migration'] = True
            # Acknowledgment is attested, like reviewer identity; file coverage is computed.
            ack_raw = _file(root, ACK) if worktree else _entry(root, tip, ACK)
            ack = json.loads(ack_raw[1]) if ack_raw else {}
            result['acknowledged'] = (ack.get('base') == base
                                      and ack.get('release') == new_sha
                                      and isinstance(ack.get('owner'), str)
                                      and bool(ack['owner'].strip()))
            # Releases' behavior notes travel in the report even when the render has
            # no changelog. Read them from a separate, pinned template clone.
            notes = d / 'source'
            r = subprocess.run(['git', 'clone', '--quiet', '--no-checkout', _source(src),
                                str(notes)], capture_output=True, timeout=60,
                               env=git_environment())
            if r.returncode:
                raise ValueError('cannot read the release notes')
            # Compare the actual pinned changelog blobs. This also handles this
            # template's bold version entries and chronological/mixed ordering,
            # and never sends an entire historical changelog into the review.
            result['release_notes'] = git(
                notes, 'diff', '--no-ext-diff', '--no-textconv', '--no-color',
                '--unified=0', old_sha, new_sha, '--', 'CHANGELOG.md').decode('utf-8')
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        result['errors'].append(str(exc))
        result['identical'] = []  # any failure withdraws every exemption
    return result


@functools.lru_cache(maxsize=16)
def _committed(root: str, base: str, tip: str) -> dict:
    # Only immutable Git objects are cached, only for this invocation. A report
    # in the project (or Git's common dir) is never an authority.
    return _verify(Path(root), base, tip)


def verify(root: Path, base: str, tip: str = 'HEAD', *, worktree: bool = False) -> dict:
    root = root.resolve()
    base_sha = git(root, 'rev-parse', '--verify', base + '^{commit}').decode().strip()
    tip_sha = git(root, 'rev-parse', '--verify', tip + '^{commit}').decode().strip()
    if worktree:
        return _verify(root, base_sha, tip_sha, worktree=True)
    return _committed(str(root), base_sha, tip_sha)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', nargs='?', default='.')
    parser.add_argument('--base', required=True, help='integration baseline before the update')
    parser.add_argument('--ack', metavar='OWNER', help='record acknowledgment of the behavior notes')
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    try:
        report = verify(root, args.base, worktree=True)
        if args.ack and report['update'] and not report['errors']:
            p = root / ACK
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(dict(base=report['base'], release=report['new_release'],
                                         owner=args.ack), indent=2) + '\n', encoding='utf-8')
            report['acknowledged'] = True
        print(json.dumps(report, indent=2))
        return 1 if report['errors'] else 0
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        parser.exit(2, f'template-verify: {exc}\n')


if __name__ == '__main__':
    raise SystemExit(main())
