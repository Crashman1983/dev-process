"""Repeatable pre-adoption gate timings, using the current template tree.

uv run python tools/benchmark_gates.py --runs 5 > /tmp/gate-benchmark.json
This measures template overhead on empty projects, not a downstream product's
history, tests or tracker. All selected gates must exit successfully.
"""
import argparse
import json
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import copier
import yaml

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs', type=int, default=5)
    args = parser.parse_args()
    if args.runs < 1:
        parser.error('--runs must be positive')
    modules = yaml.safe_load((ROOT / 'copier.yml').read_text())['modules']['default']
    modules = yaml.safe_load(modules)
    results = {}
    with tempfile.TemporaryDirectory() as temp:
        d = Path(temp)
        src = d / 'source'
        src.mkdir()
        shutil.copy2(ROOT / 'copier.yml', src / 'copier.yml')
        shutil.copytree(ROOT / 'template', src / 'template',
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        for profile in ('minimal', 'standard'):
            out = d / profile
            data = {'project_name': 'benchmark', 'harness': 'claude'}
            if profile == 'minimal':
                data['modules'] = dict.fromkeys(modules, False)
            copier.run_copy(str(src), str(out), data=data, defaults=True, unsafe=True, quiet=True)
            for argv in (['scripts/process/gate_runner.py'], ['scripts/process/check_review.py', '.']):
                times = []
                for _ in range(args.runs):
                    start = time.perf_counter()
                    r = subprocess.run([sys.executable, *argv], cwd=out, capture_output=True,
                                       text=True, timeout=120)
                    times.append(round(time.perf_counter() - start, 4))
                    if r.returncode:
                        raise SystemExit(r.stdout + r.stderr)
                results[profile + '/' + Path(argv[0]).stem] = {
                    'seconds': times, 'median_seconds': statistics.median(times),
                    'runs': args.runs}
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
