"""Time `train.py plan --json` on a synthetic large repo (#398, v2.91 M0).

uv run python tools/bench_train_plan.py --branches 600 --runs 3
uv run python tools/bench_train_plan.py --branches 600 --source <dir with copier.yml + template/>

Renders the template (default: this repo's working tree), then builds a
project history like a busy downstream clone: `--plans` main commits, each
adding one plan (most archived) and a journal shard with REVIEW passes;
`--branches` local branches, one in twelve ahead of main with its own
archived plan and a REVIEW pass, the rest merged; dispatch records for the
ahead branches and for stale merged ones; and a bare origin carrying main.
Prints JSON: the seconds of each `plan --json` run, their median, and how
many candidates the plan saw and found eligible. The time is the runner's;
compare runs on one host, never against a fixed number.
"""
import argparse
import json
import os
import random
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import copier

ROOT = Path(__file__).resolve().parents[1]
ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
       "GIT_COMMITTER_EMAIL": "t@t", "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "commit.gpgsign",
       "GIT_CONFIG_VALUE_0": "false"}
REVIEW = "REVIEW work={work} tier=2 reviewer=fresh model=cross independence=bundle,non-implementing"


def render(source: Path, work: Path) -> Path:
    """The template rendered from a git-free snapshot (as tests/conftest.py does):
    copier copies the tree as it is, not the last release tag."""
    snap = work / "source"
    snap.mkdir()
    shutil.copy2(source / "copier.yml", snap / "copier.yml")
    shutil.copytree(source / "template", snap / "template",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    project = work / "project"
    modules = dict.fromkeys(("speckit", "doc_drift_gate", "arch_onboarding", "feature_registry",
                             "github_issues", "contracts", "git_hooks", "security_floor", "sbom",
                             "telemetry", "arch_docs", "github_master", "design_contracts"), False)
    data = {"project_name": "d", "harnesses": {"claude": True, "copilot": False, "agents_md": False},
            "modules": modules, "ci": {"github": True}}
    copier.run_copy(str(snap), str(project), data=data, defaults=True, unsafe=True, quiet=True)
    return project


def _blob(data: str) -> str:
    return f"data {len(data.encode())}\n{data}\n"


class Builder:
    def __init__(self, root: Path, *, branches: int, plans: int):
        self.root = root
        self.ahead = max(1, round(branches / 12))
        self.merged = branches - self.ahead
        self.plans = plans
        self.archived = round(plans * 230 / 250)
        self.t0 = int(time.time()) - 200 * 86400
        random.seed(398)

    def git(self, *args: str, inp: bytes | None = None) -> str:
        r = subprocess.run(["git", "-C", str(self.root), *args], input=inp, capture_output=True, env=ENV)
        if r.returncode:
            raise SystemExit(f"git {' '.join(args[:3])}: {r.stderr.decode()}")
        return r.stdout.decode().strip()

    def fast_import(self, stream: list[str], marks: Path | None = None) -> dict[int, str]:
        argv = ["fast-import", "--quiet", "--force"] + ([f"--export-marks={marks}"] if marks else [])
        self.git(*argv, inp="".join(stream).encode())
        if marks is None:
            return {}
        return {int(m[1:]): s for m, s in (line.split() for line in marks.read_text().splitlines())}

    def day(self, k: int) -> str:
        return time.strftime("%Y-%m-%d", time.gmtime(self.t0 + k * 3600 * 18))

    def build(self) -> None:
        self.git("init", "-q", "-b", "main")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "base")
        chain = self._main_history()
        self._merged_branches(chain)
        self._ahead_branches(chain)
        self._dispatch_records()
        origin = self.root.parent / "origin.git"
        subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True, env=ENV)
        self.git("remote", "add", "origin", str(origin))
        self.git("push", "-q", "origin", "main")
        self.git("fetch", "-q", "origin")
        self.git("checkout", "-q", "-f", "main")
        self.git("reset", "-q", "--hard", "main")

    def _main_history(self) -> list[str]:
        """One commit per plan (code + plan), then one commit with a journal shard
        per plan, each REVIEW naming the plan's real base and head."""
        base0 = self.git("rev-parse", "HEAD")
        stream = []
        for k in range(1, self.plans + 1):
            slug = f"{k}-feat-{k}"
            where = ".process-work/plans/archive" if k <= self.archived else ".process-work/plans"
            plan = f"# {slug}\n\ntier: 2\nissue: #{k}\n\n## Decisions\n\n- none\n\n## Steps\n\n" + "- [x] step\n" * 20
            stream.append(f"commit refs/heads/main\nmark :{k}\ncommitter t <t@t> {self.t0 + k * 3600} +0000\n"
                          + _blob(f"feat: {slug} (#{k})") + (f"from {base0}\n" if k == 1 else "")
                          + f"M 100644 inline src/mod_{k}.py\n" + _blob(f"VALUE_{k} = {k}\n" * 30)
                          + f"M 100644 inline {where}/{self.day(k)}-{slug}.md\n" + _blob(plan) + "\n")
        sha = {0: base0, **self.fast_import(stream, self.root.parent / "marks_main")}
        stream = [f"commit refs/heads/main\nmark :999999\ncommitter t <t@t> {self.t0 + 300 * 3600} +0000\n"
                  + _blob("docs: journal") + f"from {sha[self.plans]}\n"]
        for k in range(1, self.plans + 1):
            lines = [f"# Journal {self.day(k)}\n", "Some notes about the day. " * 10 + "\n",
                     REVIEW.format(work=f"{k}-feat-{k}") + f" verdict=pass round=1 base={sha[k - 1]} head={sha[k]}\n"]
            if k % 3 == 0:
                lines.append(REVIEW.format(work=k) + f" verdict=block round=1 base={sha[k - 1]} head={sha[k]}\n")
            stream.append(f"M 100644 inline .process-work/journal/{self.day(k)}-s{k}.md\n" + _blob("".join(lines)))
        self.fast_import(stream + ["\n"])
        return [sha[k] for k in range(self.plans + 1)] + [self.git("rev-parse", "main")]

    def _merged_branches(self, chain: list[str]) -> None:
        refs = "".join(f"create refs/heads/{n}-feature-x {random.choice(chain)}\n"
                       for n in range(1, self.merged + 1))
        self.git("update-ref", "--stdin", inp=refs.encode())

    def _ahead_names(self) -> list[str]:
        first = 1001 if self.merged < 1001 else self.merged + 1
        return [f"{first + i}-feature-x" for i in range(self.ahead)]

    def _ahead_branches(self, chain: list[str]) -> None:
        """One commit with code and the branch's archived plan; every other branch
        carries a headless pass in that commit, the rest a second commit with a
        pass naming the first commit as its head."""
        now = int(time.time())
        first, attest = [], []
        for i, b in enumerate(self._ahead_names()):
            n = int(b.split("-")[0])
            fork = random.choice(chain[-40:])
            mark = 20001 + 2 * i
            commit = (f"commit refs/heads/{b}\nmark :{mark}\ncommitter t <t@t> {now - 3600 * (i + 1)} +0000\n"
                      + _blob(f"feat: {b} (#{n})") + f"from {fork}\n"
                      + f"M 100644 inline src/feature_{n}.py\n" + _blob(f"F = {n}\n" * 40)
                      + f"M 100644 inline .process-work/plans/archive/2026-10-20-{b}.md\n"
                      + _blob(f"# {b}\n\ntier: 2\nissue: #{n}\n\n## Decisions\n\n- none\n"))
            if i % 2:
                commit += (f"M 100644 inline .process-work/journal/2026-10-20-{b}.md\n"
                           + _blob(REVIEW.format(work=b) + " verdict=pass round=1\n"))
            else:
                attest.append((b, mark, fork))
            first.append(commit + "\n")
        sha = self.fast_import(first, self.root.parent / "marks_ahead")
        # fast-import cannot put a mark's SHA into content: the attestations come second
        self.fast_import([
            f"commit refs/heads/{b}\ncommitter t <t@t> {now - 60} +0000\n" + _blob(f"chore: attest {b}")
            + f"from {sha[mark]}\nM 100644 inline .process-work/journal/2026-10-21-{b}.md\n"
            + _blob(REVIEW.format(work=b) + f" verdict=pass round=1 base={fork} head={sha[mark]}\n") + "\n"
            for b, mark, fork in attest])

    def _dispatch_records(self) -> None:
        records = Path(self.git("rev-parse", "--absolute-git-dir")) / "process-dispatch"
        records.mkdir(exist_ok=True)
        now = int(time.time())
        issues = {}
        for b in self._ahead_names():
            n = int(b.split("-")[0])
            rec = {"branch": b, "issue": n, "phase": "implement", "tier": 2, "model": "m", "effort": "high",
                   "remote": True, "started": now - 7200, "ts": "2026-11-04T10:00:00", "runner": "remote",
                   "plan_review": False}
            (records / f"{b}.json").write_text(json.dumps(rec, indent=2))
            issues[str(n)] = b
        for n in range(1, min(100, self.merged) + 1):  # stale records of merged branches
            b = f"{n}-feature-x"
            rec = {"branch": b, "issue": n, "phase": "implement", "tier": 2, "remote": True,
                   "started": now - 86400 * 30, "ts": "2026-10-01T10:00:00"}
            (records / f"{b}.json").write_text(json.dumps(rec, indent=2))
            issues[str(n)] = ""
        (records / "issues.json").write_text(json.dumps(issues, indent=2))


def time_plan(project: Path, runs: int) -> tuple[list[float], dict]:
    seconds, result = [], {}
    for _ in range(runs):
        start = time.perf_counter()
        r = subprocess.run([sys.executable, "scripts/process/train.py", "plan", "--json"], cwd=project,
                           capture_output=True, text=True, env=ENV)
        seconds.append(round(time.perf_counter() - start, 2))
        if r.returncode:
            raise SystemExit(f"train.py plan failed ({r.returncode}):\n{r.stdout}{r.stderr}")
        result = json.loads(r.stdout)
    return seconds, result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--branches", type=int, default=600, help="local branches besides main (default 600)")
    parser.add_argument("--plans", type=int, default=250, help="plans and journal shards on main (default 250)")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--source", type=Path, default=ROOT, help="a directory with copier.yml and template/")
    parser.add_argument("--workdir", type=Path, help="build here and keep it (default: a temporary directory)")
    args = parser.parse_args(argv)
    if args.branches < 2 or args.plans < 1 or args.runs < 1:
        parser.error("--branches must be at least 2, --plans and --runs positive")
    with tempfile.TemporaryDirectory() as temp:
        work = args.workdir or Path(temp)
        work.mkdir(parents=True, exist_ok=True)
        project = render(args.source.resolve(), work)
        builder = Builder(project, branches=args.branches, plans=args.plans)
        builder.build()
        seconds, result = time_plan(project, args.runs)
    cands = result.get("candidates") or []
    print(json.dumps({"branches": args.branches, "ahead": builder.ahead, "merged": builder.merged,
                      "plans": args.plans, "seconds": seconds, "median_seconds": statistics.median(seconds),
                      "candidates": len(cands), "eligible": sum(1 for c in cands if c.get("eligible"))},
                     indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
