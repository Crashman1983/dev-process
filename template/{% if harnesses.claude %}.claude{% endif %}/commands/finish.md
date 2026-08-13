# /finish

Close a feature branch cleanly — the merge tail as one verdict instead of a
ritual scattered over four docs. Run:

    uv run scripts/process/finish.py

The checker is read-only: it verifies the branch is actually done (clean
worktree, clearing REVIEW pass for every active tier-2+ plan, gate suite
green) and then prints the exact remaining steps in order — archive the
plan(s) on the branch, merge, delete the branch, remove the worktree,
publish/prune. Execute the printed steps; do not improvise the order
(`docs/process/commits.md`, Merging — the plan archives BEFORE the merge,
and merge leaves no residue).

BLOCKED means exactly one thing: the tail is not reachable yet — most often
a missing clearing pass (run `/review`) or red gates. Do not merge around a
BLOCKED verdict; the production failures this command exists for were all
merges past an unfinished tail.
