# /finish

**Project overlay:** if `docs/process/commands/finish.local.md` exists, read it
before you start — the project's own rules for this command, binding over
this file where it says so; a template doc this command sends you to may
have one beside it (`<doc>.local.md`), read with the doc
(`docs/process/overlays.md`).

Where a steward runs the merge train (`docs/process/train.md`), stop after the archive step (`finish.py --apply` without `--tests`), push, and `report.py review-pass` — the train merges the batch behind one full suite. Without a train, this command is the merge tail:

Close a feature branch cleanly — the merge tail as one verdict instead of a
ritual scattered over four docs. Without a train, run the whole tail at once:

    uv run scripts/process/finish.py --apply --tests                         # merge_suite, then merge, push, delete branch
    uv run scripts/process/finish.py --apply --tests "<CMD>"                 # without a merge_suite: name the full suite
    uv run scripts/process/finish.py --apply --tests-passed                  # without a merge_suite only: a claim, certifies nothing

With a train, the archive step alone:

    uv run scripts/process/finish.py --apply            # archive commit + rebase, stops before the merge

`--apply` checks first: the branch is actually done (clean worktree,
clearing REVIEW pass for every active tier-2+ plan, gate suite green). When
something blocks, it prints the blockers and applies nothing. Otherwise it
executes the deterministic tail in order — archive the plan(s) on the
branch, rebase, merge, delete the branch — and prints what is left by hand:
the worktree, the `publish_and_prune.py` line of each finished spec dir of
this branch, the issue. Do not improvise the order
(`docs/process/commits.md`, Merging — the plan archives BEFORE the merge,
and merge leaves no residue). `finish.py` without `--apply` stays a
read-only preview: the same verdict and the remaining steps, printed.

A push whose hook may run tests for minutes is never waited out inside a
tool call: produce the evidence in the background first (the project's
certify step, where one exists), then push; on a busy-lane abort do other
work and push again later — never a retry loop (the `git-hooks` module doc).

`--tests` alone runs the `merge_suite` of `testing.local.json`; only that run
writes the merge certificate the merge push reads, and a `--certify` push
certificate is not accepted by a merge push. While `merge_suite` is set,
`--tests-passed` is refused — the push would run the suite again anyway.

A repository without any remote merges locally: no fetch (a local default
branch ahead of yours is rebased in), the gates run with the merge target
before the fast-forward, nothing is pushed, no certificate is written, and
the merged branch is deleted. `--tests-passed` is refused there — no pre-push
runs the suite behind the claim; pass `--tests <command>`. When the default branch is checked out in
another worktree, that checkout is fast-forwarded and your branch stays, with
the command to delete it. A left-over tracking ref such as `origin/main`
without a remote is BLOCKED until you remove it (`git branch -r -d <ref>`):
the gates would judge against it.

Every step prints its command; the first failure stops the run in a state
git explains. The merge only happens behind the batch's FULL suite (test
economy, `docs/process/testing.md`). `--tests` runs one command without a
shell: several stages (`&&`, a pipe) belong in one make target or script.

BLOCKED means exactly one thing: the tail is not reachable yet — most often
a missing clearing pass (run `/review`) or red gates. Do not merge around a
BLOCKED verdict; the production failures this command exists for were all
merges past an unfinished tail.
