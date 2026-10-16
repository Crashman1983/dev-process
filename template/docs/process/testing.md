# Testing — how to shape a suite

Mandatory rule 5 says *what* a test must do: prove the acceptance it claims.
This document says *how to shape the suite* that does it. It is methodology,
not tooling — pick the runners your stack already uses.

## The shape: many fast, few slow

Order tests by scope, speed and cost — the classic pyramid, read as a
heuristic, not a quota:

- **Unit** (the base): one function/class, milliseconds, no I/O. Most tests
  live here because they run on every edit and localize a failure precisely.
- **Integration** (the middle): components together — a route hitting a real
  (test) database, a parser over real files. Slower, fewer, and the layer
  that catches wiring mistakes units cannot see.
- **End-to-end** (the tip): a handful of whole-workflow proofs, chosen by
  risk. Every changed **critical contract** — a path from input to durable
  state or visible outcome that users or other components depend on —
  needs fitting evidence of its *actual effect*: an end-to-end test, an
  integration test that exercises the real effect, or a manual trace where
  the review checklist's completeness section allows one; unit tests of one
  piece in isolation alone do not show the effect.

Inverting the shape (many E2E, few units) makes the suite slow and flaky and
is the most common failure mode. When an E2E test and a unit test would prove
the same thing, prefer the unit test.

**E2E evidence is risk-based, not counted per feature** — there is no
per-feature floor and no per-feature ceiling:

- **Fitting evidence per changed critical contract.** Name the test (or
  trace) that shows the contract's actual effect.
- **One test may serve several features** when its evidence fits the
  changed contract — name it instead of writing a duplicate.
- **New tests at the cheapest sufficient level.** Add an E2E test only for a
  critical flow that no cheaper test evidences sufficiently.
- **The rule is no reason to delete tests.** Existing E2E tests stay; a
  consolidation pass may retire a double proof only when a named cheaper
  test covers it, never merely deleted.

Two examples. *Already covered:* a change to checkout price rounding — the
existing checkout E2E test already asserts the charged total end to end; a
unit test pins the rounding rule and the existing E2E test is named as the
effect evidence, so no duplicate E2E test is written. *Second independent
flow:* the same feature adds a refund that writes a different ledger and
notifies another service — a second critical flow no existing test
evidences; it gets its own E2E (or real-effect integration) test, and no
count limit excludes it.

A platform variant (mobile/desktop) earns its own E2E test only where the
*behaviour* differs, not merely the rendering (the visual baseline owns
rendering). The suite is a managed asset: growth is reviewed like code
growth, and a periodic consolidation pass that retires double proofs is
maintenance, not loss.

## What earns a test beyond the happy path

Acceptance decomposition (Definition of Ready, R2) already names them: the
**negative** case, the **edge** case, the **authorization** case, and the
**invalidation/cleanup** case. The missing negative twin is
where a bug most often hides. For a change to approval or release, trust,
deletion or concurrency, the first behaviour test covers the critical edge
case — the refusal, the revoked grant, the competing write — through the
path real callers take, at the cheapest level that reaches it. Two patterns worth reaching for:

- **Property-based testing** where the input space is large (parsers,
  serializers, calculations): state an invariant and let the framework
  search for counterexamples (Hypothesis, fast-check, jqwik, proptest …).
  Replay-capable or event-sourced logic gets a property or model test over
  random event sequences: append and replay give the same state, one refresh
  equals two, and the allowed reorderings do not change the result.
- **Regression pins**: every bug fixed — and every finding whose fix changes
  behavior — gets a test that fails on the old behavior; the suite is the
  ratchet that keeps a caught defect caught.

Two tests that pass and prove nothing (adapted from Matt Pocock's `tdd`, MIT):

- **Tautological:** the expected value is computed the way the code computes
  it (`assert add(a, b) == a + b`, a snapshot recorded from the code under
  test), so it can never disagree. Expected values come from a source
  independent of the code: a literal worked out by hand, an example from the
  spec, a known-good output.
- **Coupled to internals:** it mocks the code's own collaborators, calls
  private functions, or checks a side channel (querying the table instead of
  reading through the interface), so it breaks on a refactor and survives a
  real regression. Mock only at the system's boundary — the network, the
  clock, a third-party API — and assert what a caller can observe.

## Coverage numbers — the honest ceiling

Line coverage measures *execution*, not *verification* — a suite can execute
80% of lines and assert nothing (review AI-generated tests for assertion
substance, not test count). The discipline is the same one the telemetry
module applies to its numbers, where installed: **no universal threshold
gate.** A coverage number is useful
only as a within-project trend (falling coverage on changed code is a review
question) and as a map of what is *untested*, never as a target to optimize.
If you want a stronger signal on critical logic, run **mutation testing**
(Stryker, PIT, mutmut …) there — the mutation score asks the right question
("would the suite notice broken code?") at a compute cost that is only worth
paying on the code that matters most.

## Test economy — scoped inner loop, full merge boundary

Not every change pays for the full suite; **selection runs near the edit,
completeness runs near the merge.** The ladder:

- **Per task** (inner loop): the tests the task names plus the tests its
  changed files reach — via the runner's module graph (`vitest related`,
  coverage-based selectors) or an auditable module map (changed
  `src/<pkg>/` → `tests/<pkg>/`). A scoped green is labeled scoped; it is
  evidence, never the verdict.
- **Per push**: the scoped set again — with **honest fallbacks to full**:
  a changed file the map cannot place, and the categories whose effects do
  not travel through imports (config, tokens/theme, global styles, schema/
  migrations, DI registration, fixtures) always run full. With `unmapped:
  skip`, a branch push names what fell outside the map and leaves the full
  run to the merge boundary: a fault only a full run finds then surfaces in
  the train and sends a batch back instead of one branch — bounded, because
  the train bisects, against a full run paid on every branch push
  (downstream: ten minutes per attempt). A push to the integration branch
  always keeps the full fallback.
- **Per merge boundary** (the batch): the FULL suite, exactly once for the
  whole batch of changes a branch or stage carries — this is where several
  changes share one full run and the economics work. `finish.py` names the
  step; a stage-gate task is its speckit twin. Selection is never the last
  net before a merge. "Full" means every stack: a boundary command that runs
  only the backend leaves the frontend proven by selection alone.

Why the ladder is safe: selection fails exactly where dependencies bypass
the import graph — and those categories are enumerated as full-run
triggers, while the merge boundary re-proves everything regardless. Why it
is worth it: an inner loop that pays the full suite per push pays it ten
times per batch for what one boundary run proves.

**Completeness paid once must be transferable.** The boundary full run
should also *write* whatever certificate later gates memoize on — a
coverage tree-cert, a build stamp — so a deploy gate that would re-prove
the same tree becomes a memo hit instead of a second full payment. A
deploy re-running the suite the boundary just ran, on the same tree, is
the same double payment this section exists to remove; conversely, a
cert written by a run that did not actually measure the certified thing
(coverage claimed from a non-coverage run) is a false green — the
boundary run earns the cert by running in the certifying configuration.
A certificate is **keyed by what it certifies** — one entry per tree hash,
never a single slot holding "the" certified tree: parallel worktrees each
earn their own, and the last writer must not be able to erase another's
proof (observed: a slot file let concurrent worktrees invalidate each
other's boundary runs). The same goes for any scratch file the run
writes — per run (`mktemp`), never a fixed shared path.

The transfer works downhill too: **stronger evidence supersedes weaker.**
A push-time full-run trigger may memo-hit on a certificate that covers
the same tree in a configuration that is a strict superset (a coverage
run covers a plain run) — so the order at a coherence point is: boundary
run first (writes the cert), then push (the gate reads it), then review
and merge (the bundle preflight runs the process gates, never the
suite). One full run per batch; every later gate reads the certificate
instead of re-earning it.

**A bookkeeping-only push runs no suite.** A push whose range changes
nothing outside `.process-work/` and the plans — attest lines, review
reports, decisions, root causes — changes no tested code: the project's push
hook runs the process gates for it, not a test suite, and a certificate is
keyed by the tree without those paths, so a bookkeeping commit on a green
tree is a memo hit. Downstream, half the commits of two weeks were
bookkeeping-only, and one docs-only pre-push held the scoped lane for
fifteen minutes while queued sessions waited. Fewer such pushes help too:
a review round's report and its `REVIEW` line are one commit
(`attest.py --commit --with <report>`), a fix's `ROOT-CAUSE` line rides
the fix commit, and a round is pushed once.
Two consequences keep the memo honest. A check that reads the bookkeeping
paths (a journal scanned for client names) is a process gate, not a test:
gates run on every push, a test behind the tree memo would not see a
journal that changed. And a certificate written under a bypass (`SKIP_*`,
`--no-verify`) certifies nothing: no later push may read it as a hit.

**Test lanes are a shared resource — queue, do not thrash.** Several
agents in several worktrees on one host each running "their" scoped suite
at the same time do not finish faster; they crawl together (observed: load
6 on four agents), and a crawling gate is the one that gets bypassed. Two
answers, neither a bypass: the certificate transfer above — a tree the
boundary run already certified needs no scoped run at push — and a
**test lane** — two per host (`lane.py`): `full` for the long runs (the
boundary suite, coverage; run them under `nice`), `scoped` for the short ones
(a push's selected tests, `--certify`). A scoped run never queues behind a
full run; runs within one lane wait their turn. The sum of work is the same;
every single run is fast, and nobody reaches for `--no-verify`.
**A push never waits for tests inside an agent's tool call** (downstream: a
tool call died at 40 minutes with the tests at 96 %, five times in a row): the
lane wait is bounded (the lane's `wait`), and past it the push stops with exit
75 naming the holder. The way out is `test_select.py run --certify` started in
the background; the push then reads its certificate. Never retry the push in a
loop.
A merge commit of already-verified branches is not exempt by itself — the
combination is new — but it is exactly what the boundary run certifies
once, for every later gate to read.

**One test path — shipped, not rewritten per project.** The ladder above is
code. A project supplies data; the template owns the sequence:

- **`docs/process/testing.local.json`** — per stack: the `paths` it owns, a
  `runner` argv with `{paths}`, its `full` command, the test globs (`tests`),
  a `map` (`backend/src/app/{pkg}/{sub}/**` → `backend/tests/{pkg}/{sub}`,
  `backend/tests/{pkg}`: the first target that exists wins, and the run
  names the fallback), `pins` (subject → tests; a deleted subject fires
  too), `unmapped` (`full` by default; `skip` only where every merge runs
  a full suite), an optional local `select` command for what a map cannot
  express (NUL-separated paths on stdin, targets on stdout), a `timeout`.
  Beside the stacks: `merge_suite` (the train's default `--suite`),
  `merge_scope` (an argv whose stdout names the stages `merge_suite` will
  run, for a suite that selects its stages — "Stages" below),
  `preflight` (an argv checking the environment — interpreter, venv, disk,
  logins — once before any test of a push, a `--certify` or the train;
  `preflight_timeout`, default 600 s, for the train's too; on a push the
  process gates run first, so a host that breaks a gate is refused as that
  gate), `lanes`, `lane_dir`,
  `certificate_env`. No file: the gates run, no tests.
  A malformed file refuses the push — a typo in a map must not skip tests.
- **`scripts/process/test_select.py plan|run|check`** — the one selection
  rule, for the hook and by hand. A changed test file selects itself; a
  deleted file counts like a changed one; a path in no stack counts only
  for pins. `check` names stale pins and map
  targets that match nothing.
- **`scripts/process/pre_push.py`** — the one sequence of every push: the
  merge guard; branch updates only (tags and deletions end there); the
  pushed commit is this checkout's HEAD; class `merge` when a branch update
  lands on an integration branch, scope `process-only` when it changes
  nothing outside `.process-work/`; the stamp; the process gates; the
  tests; a stamp. Every installed guard reaches it (`merge_route.py
  --stdin` hands the push over); a project with its own hook calls it
  (`exec uv run scripts/process/pre_push.py "$@"`). Exit 0 may push, 1
  refused, 2 cannot judge (a red preflight among them: the host's failure,
  no test ran, nothing stamped or certified), 75 a lane stayed busy (no
  test ran).
- **`scripts/process/lane.py`** — lanes `scoped` and `full` per host
  (`flock`; without it, unqueued and said once). A push holds one lane once
  for all its stacks — released between stages, another push took the gap
  and the first paid its 30-minute run twice (downstream). A run that
  already holds the lane re-enters it.
- **`scripts/process/certificate.py`** — `push` and `merge` certificates,
  keyed by the evidence tree (without `.process-work/`) and what ran.
  Written only on a clean tree that the run left unchanged, with no
  `MAKEFLAGS` assignment or flag that changes what runs (`-i`, `-n`, `-t`,
  `--eval`, …; `-k` and `-s` pass, they hide nothing) and no
  `certificate_env` variable set.
  `test_select.py run --certify` writes `push`; the train and `finish.py
  --tests <merge_suite>` write `merge`; `finish --tests-passed` is a claim
  and writes nothing. A branch push accepts either; a merge push only
  `merge` — without one it runs `merge_suite`, else every stack's `full`,
  else it is refused.
- **Skipping** is the owner's: `PROCESS_SKIP=gates` is the guard's logged
  bypass, `PROCESS_SKIP=tests` keeps the standing block; both are refused
  from a dispatched session and write no stamp and no certificate.

What the data must get right, from downstream measurements: map to the
**closest test package** (a top-level mapping selected 61 % of all test
files for a one-file change); let the runner run **parallel, bounded**
(pytest-xdist `-n`, the runner's own pool — set in the stack's `runner` argv,
never in the runner's shared config (`addopts`), where it reaches the merge
suite and collides with a CI run's `-p no:xdist`); give each parallel worker
its own port range and temp directory (the runner names the worker:
`PYTEST_XDIST_WORKER`); and **measure** — lane hold
time per push, and the train's phases (`process_kpis.py train-phases`) —
before and after changing a selection. Limits: a server-side PR merge
passes no push hook; a clone without any integration ref (single-branch)
bounds a branch push by the remote's side of the update, so code that
reached the remote branch past the hook is not selected again; whether `merge_suite` covers every stack is the
project's duty; a file git ignores is invisible to the clean-tree check.

**Stages.** A merge suite that runs in stages (a backend and a frontend
stage, say) and may select them leaves two things in the git directory of
the checkout it ran in — `git rev-parse --absolute-git-dir` from the suite's
working directory, the worktree's own, never the common directory —
`<git-dir>/merge-suite/`: `stages`, the names of the stages this run chose
(space-separated), and per stage that ran `<stage>.time` with `<start> <end>
<exit code>` (epoch seconds). Each run deletes `stages` and every `*.time`
before it selects, then writes `stages` before its first stage, so a file
left by an earlier run never names this one. `merge_scope` must give the same
answer for one tree wherever it runs (the train's worktree, the merge push):
a selector that answers differently makes every certificate miss — safe, but
the suite runs twice. The train
folds the times into `phases.jsonl` (`stages`: seconds, runs, green, red or
skipped; `process_kpis.py train-phases` shows them per stage), and with
`merge_scope` configured the merge certificate names the stages: the
certificate's evidence is the suite plus `scope=<stages>`, so a run that
skipped a stage never satisfies a merge push whose selector wants it, and a
run whose `stages` file is missing or empty certifies nothing — the scope is
read from the run, never recomputed after it (`certificate.run_evidence`). A
suite without stages writes neither file; nothing changes for it.

## Ratchets — a threshold that only ever tightens

Some qualities cannot be gated with one universal number on day one because
the existing tree already violates them a hundred times (a token-reuse rule,
a layout budget, a lint category adopted late). The pattern that works is a
**ratchet**: the current findings are pinned as a *baseline* (a tracked
file, exact identities not a count), and the gate fails on any finding
**not in the baseline** and on any baseline entry that **no longer occurs**
(a stale exception is debt that has been paid and must be struck, or the
baseline silently becomes an allowlist). Legacy is tolerated, new debt is
not, and the baseline can only shrink. A ratchet is a gate, not a score: it
needs no target and cannot be gamed by adding volume.

A shipped instance: `scripts/process/check_baseline_duplicates.py` — byte-
identical screenshots under different names inside the baseline directories
are a finding (at most one of them is evidence of what its name claims;
observed: desktop renders minted under mobile names, an error state
identical to a partially-loaded one). `--write-baseline` pins the groups a
tree already carries; from then on a new group fails and a stale pin fails,
so the file only ever shrinks.

## Unmeasurable is not red

A measurement gate (performance budget, timing-sensitive E2E, resource
limits) can only speak when its precondition holds — a quiet host, a warm
cache, the fixture service up. When it does not, the gate **refuses to
measure** and says so with its own exit code (a temporary-failure code such
as `75`, `EX_TEMPFAIL`, distinct from a failing assertion), and the caller
reports "not measured" rather than "failed". A refusal is a launch problem
with a different owner than a regression; conflating them sends people
hunting for a defect in the branch that lives in the machine. The same rule
covers the process gates: `finish.py` and the review bundle name a runner
that cannot start apart from a runner that ran red.

## Suite discipline

- A **flaky test is a defect**, not weather: fix it or quarantine it the same
  day with an issue (or an inbox entry, tracker-less) — a suite people retry is a suite people ignore.
  Where a project quarantines (the template ships none), the quarantine is
  data, not a skip marker: one entry per test with its issue
  and an expiry at most 14 days out. Only the branch-push runner honours it;
  the merge boundary always runs the test, and the switch that enables the
  quarantine must not be inheritable by the merge suite. An entry without
  issue or date, dated too far out, past its date, or whose issue is closed
  skips nothing and says why. The owner or the steward adds an entry, never
  the author of the branch it would unblock.
- A **viewport or device matrix multiplies the whole E2E run**: every extra
  width runs every spec again. Keep the per-push run on the widths the change
  needs (one desktop, one mobile) and run the full matrix nightly.
- **Stability proofs run scoped × N, full × 1.** Proving a fix is not flaky
  means repeating the *affected files* N times plus one full run — never N
  consecutive full runs; five full suites for one stability claim is the
  repetition cost the scoped set exists to carry.
- The **scoped set** must stay fast enough to run before every push,
  alongside the pre-push process gates (test economy, above); the full suite
  must stay fast enough to run at every merge boundary — split a slow tier
  behind an explicit marker rather than letting either run grow past
  patience.
- Test code is code: mandatory rule 9 (written to be read) applies — a test
  nobody understands proves nothing when it fails.

## Test under the conditions the change creates

A test run in the author's shell tests the author's environment. A change
that sets an environment variable, starts a subprocess, writes where a
hook or the merge train later reads, or only runs on a push path is
proven only by one run under the conditions it creates itself: the
variables it sets present, the real entry point (the make target, the
hook, the push, the train's worktree), not a direct call of the function.
Downstream, a variable a gate set for its own run leaked into the test
suite it started, and every test that passed in the author's shell failed
under the hook.

For gate, train, finish and hook code this run is required before
`pushed` (`/execute`). The refuter attacks the same rule from the other
side — the *environment* class of the failure catalog
(`docs/process/failure-catalog.md`).

## Gates must survive a fresh checkout

A project-level gate is trustworthy only if a fresh checkout can bootstrap and
run it from tracked inputs. Local caches such as `.venv`, `node_modules`, build
outputs, or a previously prepared agent workspace are conveniences, not part
of the gate contract. The documented gate command must provide a
reproducible bootstrap from lockfiles or an equivalent pinned environment (for example
`uv run`, the project's package-manager install, or a versioned container).

Exercise that contract in CI or a disposable checkout. Report a missing cache
or bootstrap defect separately from a product failure: both block a trustworthy
gate, but they have different owners and fixes. A command that passes only in a
warm development tree is not a reproducible gate.

Review binding: the review checklist's "Tests prove acceptance" section is
where this document is enforced — mapping per criterion, the effect evidence for changed critical contracts, and the
negative/edge/authorization/invalidation cases are review questions, not
suggestions.
