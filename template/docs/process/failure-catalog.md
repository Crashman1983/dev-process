# Failure catalog

The input shapes and failure classes that found real defects downstream —
the one list the design's threat and failure question, the build, the refute
and the review draw from (`design-template.md`, `/execute`, `refute.md`,
`review-checklist.md`). Use only the classes the change touches. When a
confirmed finding belongs to a class not listed here, the change that fixes
it adds the class.

Each entry: the shape, how to test it, and the owning helper where the
template has one — a change that meets the class asks that owner instead of
reading the input its own way (mandatory rule 4).

## Inputs

- **Names:** non-UTF-8 bytes, spaces, a newline, a leading `-`, a name that
  looks like an option or a revision. *Test:* create the file or branch with
  that name in a scratch repository and run the real entry point. *Owner:*
  paths from git are read with `-z` through
  `scripts/process/check_review.py::name_status`; a branch's issue through
  `scripts/process/check_review.py::branch_issue`.
- **Git refs and deletion:** a deleted branch, a ref that does not resolve, a
  replaced object, a push that deletes instead of updates, a shallow clone
  without the base. *Test:* push a deletion, `git replace` an object, clone
  with `--depth 1`. *Owner:* `scripts/process/process_git.py::git_environment`
  for every git reader; where a push goes:
  `scripts/process/check_review.py::push_targets`.
- **Empty, missing, equal:** an empty input or range, a missing file versus a
  command that failed, a base equal to the head, a record without the field
  the code expects. *Test:* one case each; a failed command must not read like
  an empty result.
- **Rename, move, mode:** renamed on one side, on both sides, across rounds;
  a directory renamed; a file moved by the tool itself; the executable bit;
  a symlink or submodule in place of a file. *Test:* `git mv` across a
  review round; `chmod +x` alone as the change.
- **Conflicts without markers:** modify/delete, rename/delete, a file where
  the other side has a directory. *Test:* build each conflict and resolve it
  both ways.
- **Filesystem:** a symlink pointing out of the tree, a nested repository or
  another agent's worktree under the checkout, an ignored file in a scanned
  directory. *Test:* create each under the scanned path. *Owner:*
  `.gitignore` decides what belongs to the repository —
  `scripts/process/check_review.py::_gitignored`.
- **Text as rendered:** an example in a code block or comment, a placeholder,
  a mention in backticks — read as a reader sees it. *Test:* the same record
  fenced, commented and in backticks. *Owner:*
  `scripts/process/check_review.py::readable`.

## Environment

- **Environment:** locale (translated tool output), a shallow clone, another
  version of git, make or the interpreter, a missing optional tool — and the
  conditions the change creates itself (`testing.md`,
  "Test under the conditions the change creates").
- **Fresh worktree:** a step that leans on what only a warm tree has —
  `.venv`, `node_modules`, build output, a prepared agent workspace — or a
  consumer that probes a path with `is_file()` / `exists()` and returns
  empty once the path is gone, instead of failing (downstream: two of three
  plan-review rounds of one migration). *Test:* run the steps in a fresh
  `git worktree` without caches; for a deleted or replaced path, search its
  consumers including the probes and test each with the path absent.
  *Owner:* the plan's `## Fresh-worktree dry run` (`design-template.md`);
  the bootstrap contract is `testing.md`, "Gates must survive a fresh
  checkout".
- **Forged environment variables:** a variable the code trusts that a caller
  can set — to add a target, skip a check or claim a context. *Test:* set it
  by hand and check it can widen nothing it should not. *Owner:*
  `scripts/process/check_review.py::push_targets` (a union: a variable can add
  a target, never hide one).
- **Leaked resources:** a test that leaves a process, a port, a file handle
  or a temp directory behind passes alone and fails the run after it —
  under parallel workers, minutes later, in a test nobody touched
  (downstream: "too many open files" in the commit signer of a later
  test). *Test:* run the suite twice in one process with the leak check of
  the runner (`-W error::ResourceWarning`, `--detect-open-handles`), and
  count open descriptors before and after a fixture. *Owner:* the fixture
  that opens it closes it, in its teardown.
- **Fixed waits:** a `sleep` in a teardown or a poll with a fixed count is
  a guess about the host's speed — green on a quiet laptop, red under
  load 10 (`train.md` logs the load for this reason). *Test:* the same
  test with the host loaded (`stress`, parallel workers). *Owner:* the
  test waits for the condition (a status file, a socket, a process exit)
  with a deadline, never for a time.
- **Guessed external-tool behaviour:** an exit code, an output format or a
  default of git, a package manager or an API assumed, not observed. *Test:*
  a probe against the real tool, named in the design's assumption
  (`design-template.md`); the test pins the observed behaviour.

## Facts and state

- **A second reader of the same fact:** two places compute the same fact (an
  issue number, a target, a tier) and disagree on one input. *Test:* a
  differential test — one input, both readers. One fact has one owner; every
  other reader asks it (`/plan`, the rename or move inventory).
- **Fail-open defaults:** a missing, unparseable or unresolved input reads as
  the OK or definite state — "nothing found", "not stale", "no target".
  *Test:* make each input missing and each command fail; the result is
  refused or unknown, never green. *Owner:* strict git reads raise instead
  of returning nothing — `scripts/process/check_review.py::_git_read`; an
  unparseable declaration is None, not a later line —
  `scripts/process/check_review.py::spec_dir_issue`.
- **Stale mapping and expiry:** an assignment derived from a basis (a review
  of a head, a lock of an owner, a mapping of an id) stays live after its
  basis disappeared or changed. *Test:* remove or move the basis and read the
  assignment again. *Owner:* a review's head against the code —
  `scripts/process/check_review.py::stale_review`.
- **Forbidden transitions:** a state reached from a state that should never
  lead there. *Test:* one negative test per forbidden row of the plan's
  transition table (`design-template.md`). *Owner:* a table judged in one
  place — `scripts/process/check_review.py::decide`.
- **Replay parity:** state built by appending events differs from state
  rebuilt by replaying them. *Test:* a property or model test over random
  event sequences (`testing.md`). Append and replay share one function
  (`code-craft.md`).
- **Event ordering:** events arrive late, twice or in another order than
  written. *Test:* the allowed reorderings give the same result; a duplicate
  changes nothing.

## Outputs

- **Confidentiality in outputs:** a secret, a token, a personal datum or
  another tenant's data in a log, an error message, a report, a bundle or a
  published artifact. *Test:* seed a marker value in the input and search
  every output for it.
