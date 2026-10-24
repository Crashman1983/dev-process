# What is new in dev-process

For anyone who wants to know what a new version brings without knowing the
technical details. A few sentences per version: what changes for a project
that uses the template, and what it gains from that. The full technical
details are in the [CHANGELOG](CHANGELOG.md).

Deutsche Fassung: [NEWS-DE.md](NEWS-DE.md).

## v2.77.3 — A pass cannot rest on evidence that never reaches the repository

A review pass could be authorized by a note in an uncommitted journal file from another day, so the evidence stayed outside the repository. Such a note now counts only when it is committed or travels with the attestation; otherwise the pass is refused and names the file. The plan check also rejects a Transitions table whose header and separator row have different numbers of columns.

## v2.77.2 — A bracket in a test parameter no longer hides a real fix

A pytest test whose parameter value contains brackets, such as `test_x[a[b]]`, was read under the wrong name, so a genuine failing-to-passing proof could be refused. The tool that measures the proof now uses the same test-name reading as the review gate, and a parameter may contain brackets, `]`, commas, Unicode or be empty.

## v2.77.1 — A fix is only proven by the test that actually turned green

A test report could make a fix look proven when no single test had gone from failing to passing: two tests with the same name in one file were treated as one. Test reports are now kept apart by file, class and name, and a test reference that another test also claims is refused. The telemetry report no longer crashes on a finding line, a review bundle names the round another reviewer already blocked, and the plan check's description matches the rule it enforces.

## v2.77.0 — Plans decide more up front, fixes close the whole class

Most extra review rounds came from gaps in the plan or from the previous fix. A plan for work with states, lifecycles or parsers now carries a table of states with a test per row, and the plan review asks for what is missing there. After a second blocked round the plan records whether to patch again or rebuild, and every fix names the places it checked and the test that covers them. A new report shows whether this lowers the rounds a piece of work needs.

## v2.76.1 — A Codex review report passes the check, and a cited criterion is no duty

A review written by the Codex reviewer no longer gets refused at the push for
a missing header. A plan that cites another issue's criterion as `#2659/AC-11` no longer has
to prove it with a test of its own. A Codex review of an issue split into
several plans now attests the plan it reviewed.

## v2.76.0 — Checks catch before the review what a rule can catch

A project's plans, reviews and test runs are checked for what a rule or a test can decide on its own: a plan's criteria are checked as they are written, warnings nobody had to follow became duties with a clear way out, and the review list shows only what the change touches. A new report shows whether that really saves review rounds and cost per piece of work, with the defects that still slip through as the guard. A reviewer from another model family now gets read access to the code, not only the change: with it, nine in ten of its findings held instead of one in six.

## v2.75.0 — A template update is reviewed once, even when other work merges in between

A project updating the template acknowledges and reviews the update once;
other work merging in the meantime no longer forces it to start over. The
review records can no longer be fooled by an example quoted in a plan, the
lines that summarize an attack on a change and the proof that a fix turned a
test green are written by tools from what actually ran, and a new report
shows how much of the work runs on which model.

## v2.74.2 — A suite that keeps going after a failure counts again

A project whose test suite runs every stage even after one fails gets its
test certificate again. Since 2.74.0 that mode blocked the merge, although
it hides no failure.

## v2.74.1 — A review recorded with the family name counts again

A project that lets only its own model family approve from a certain tier on
now also accepts reviews recorded with just the family name, as the review
command tells reviewers to write it. Before, such reviews were silently left
out and blocked the merge.

## v2.74.0 — A project adapts the template through answers instead of its own files

A project can now choose at setup whether its plans, journals and notes are
written in English or in the conversation language. Other wishes a project
could only meet with its own versions of template files are now settings:
that from a risk tier on a reviewer of its own model family must agree, that
every plan names its design rules, and which measurements fall due on which
day. Handing work to helper models now says clearly what goes along and what
comes back. Several faults found in use are fixed. The CHANGELOG explains for
each version why something changed and what it leads to, in English and
German.

## v2.73.0 — A second model helps with reviews, and projects without paid CI are supported

If the Codex CLI is installed on the machine, the template can now hand work
and reviews to Codex models as well. Such a review counts in full: it is
checked against the state that was reviewed and only then recorded. A model
from another family counts as an independent reviewer only if it is certain
that it did not also write the code. If Codex cannot be reached, the template
names a way out and records why it was needed. Plans now also say, for each
work package, whether a smaller helper model takes it on, and the template
measures whether that pays off. Projects without paid GitHub CI now choose
`manual`: the checks stay available as a button you start yourself, and the
push is what reliably checks.
A project's own rules for the process documents now live in separate
addition files instead of in the template's documents. If a new version
changes a place that such an addition builds on, the check reports it until
someone has looked at whether the two still fit together.

## v2.72.0 — What a project has learned flows back into the template

Kenni, the first project on this template, had improved a lot on its own
over the last few weeks. Much of that is now in the template, so the project
does not drift away and other projects get it too. This includes a
confirmation that tests have run, which for projects with test groups says
exactly which ones ran; timings for each test group; plans that give every
task its exact location, so a small model has to search less (measured:
about a third of the steps); and lessons from day-to-day operation. After
the update, the tests run once more before the first push. Two larger parts
are still waiting for a decision by the owner.

## v2.71.0 — A review only counts with evidence

A review now counts as passed only once its evidence is in. For every
requirement, a test must be named that would fail if the behavior broke.
Changes to the review tools themselves must have been attacked on purpose
beforehand. Where a second AI model is meant to act as a counter-reader, it
must have run. A plan is never reviewed by a smaller model than the one that
wrote it. Anyone who skips this on purpose writes one sentence giving the
reason; that way it stays visible and countable where corners were cut. The
trigger was a night in which six changes went through smoothly and a
follow-up review found six serious errors.

## v2.70.0 — Knowledge that already exists gets found

Many review rounds fail because an agent did not know about something that
already existed: a setting, a background service, another place that reads
the same data. Projects can now have such things listed automatically from
their code, and every plan gets the entries that concern it delivered right
along. Anyone who changes something that others read must prove that they
searched for all the readers. And there is now a log like this one for
projects too: every change that a user notices gets a few understandable
sentences, collected in a "What is new" file.

## v2.69.0 — Outdated plans stand out

Before an agent starts implementing, the process now checks how old the plan
is: how far has the code moved on since then, and how many of those changes
affect exactly the files the plan names? The trigger was a plan that was more
than 1000 changes old. For now this is only measured; later the process may
warn or stop. In addition, migrations are rehearsed beforehand in a fresh
environment, releases distinguish plain updates from migrations that need
project steps, and a worker that stays silent for a long time wakes the
coordinator.

## v2.68.0 — Every check is measured

Every automatic check now records what it costs and what it finds. This
makes it possible to show which checks are worth it. A check can be put on
trial so that it only observes instead of blocking, but only with the
owner's consent and never for the core checks. A watchdog undoes such a
relaxation on its own as soon as it causes harm. A weekly and a monthly
report are added.

## v2.67.0 — The process can improve itself

Recurring bottlenecks become limited experiments: an assumption, success
criteria set in advance, a trial run with an expiry date, and a decision
that is not made by whoever built the change. At the same time, the process
measures every piece of work from start to delivery: how long it was worked
on, how long it waited, and what it cost.

## v2.66.0 — Fewer mix-ups with plans

The coordinator and the merge train now use the same rule to recognize which
plans belong to a piece of work. Before, a piece of work could get stuck on
someone else's review or miss a review it needed. If a plan review fails or
is unclear, implementation does not start.

## v2.65.0 — A broken machine is recognized

Before every test run, the process checks whether the machine is ready. A
faulty machine now reports itself as such, instead of showing seemingly
failed tests that nobody caused.

## v2.64.0 — One consistent test flow

Which tests a change needs now follows from a mapping in the project instead
of from manual work. Heavy test runs no longer get in each other's way, and
a state that has already been checked is not tested again. This saves
waiting time on every push and every merge.

## v2.63.0 — Fewer unnecessary review rounds

The process now recognizes by itself when a plan needs to be reviewed,
instead of accidentally starting a code review where there is no code. An
objection from a second model only holds up the work if it is serious
enough.

## v2.62.0 — Four everyday gaps closed

Four errors in the automatic checks, noticed in a project's daily
operation, are fixed. Among other things, valid checks no longer got stuck
because of an old line, and security scanners no longer raise an alarm when
a piece of work is finished.

## v2.61.0 — The classification is recalculated

The review first asks whether a change is really as harmless as stated. If a
value is changed, such as a version or a path, every place that uses it must
demonstrably be found. The update helper no longer starts an update by
accident when run with `--help`.

## v2.60.0 — Simple tasks on the small model

Precisely described tasks that need no decision of their own are now handled
by a small, cheap model. Tasks that need judgment stay with the large model.
This lowers costs without touching the quality of the decisions.
