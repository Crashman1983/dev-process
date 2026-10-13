# News — what is new, in plain words

A short log of what a project gained: new features, improvements, fixed
problems, a few sentences each, readable without knowing the code. It is for
the owner and for everyone who does not read commits, plans or changelogs.

## One fragment per change

Every change a user notices — a feature, a changed behaviour, a new screen,
a fixed defect — brings a fragment in its own branch:

```
uv run scripts/process/news.py new --type improved --slug reminder-snooze --issue 42 "Reminders can now be snoozed for an hour or until tomorrow morning."
```

This writes `news/<slug>.md`:

```
type: improved
issue: #42

Reminders can now be snoozed for an hour or until tomorrow morning.
```

- `type` is `new`, `improved` or `fixed`; `issue:` is optional; the text is
  one to three sentences, at most 600 characters.
- Write for the user: what they can do now, what works better, what no
  longer goes wrong. No file names, no jargon.
- Internal work — refactoring, tests, process, dependencies without a
  visible effect — has no fragment.
- One file per change instead of one shared file: parallel branches would
  otherwise collide at the same line, and fragments work for every merge
  route.

`/plan` gives such a change a task that writes its fragment; the quick flow
writes it with the change; the review asks for it (`review-checklist.md`,
Completeness). `news.py check` tells whether all fragments are well formed.

## NEWS.md

`uv run scripts/process/news.py render` writes `NEWS.md` from all fragments:
by month, newest first; within a month new, improved, fixed. An entry's date
is the day its fragment reached the integration branch (the merge commit's
date; after a fast-forward, the commit's own committer date, which a rebase
before the merge refreshes), so work from a long branch lands in the month it
shipped; fragments not merged yet stand under "Unreleased". A malformed fragment stops the render and names the file.
Fragments stay where they are; every render rebuilds the whole file.

The steward fetches the integration branch first (the dates come from it;
without a fetch, freshly merged fragments read as unreleased), renders weekly
(`improvement-weekly.md`) and merges the result
the normal way — a branch, then `finish.py` or the train, never a direct
commit to the integration branch. The owner digest shows the last days'
entries (`human_digest.py`); `news.py show --since <date>` prints them
anywhere.

Title and labels come from `docs/process/news.local.json` (optional):

```json
{"title": "Neuigkeiten", "labels": {"new": "Neu", "improved": "Verbessert", "fixed": "Behoben"}, "unreleased": "Noch nicht ausgeliefert"}
```

Without it, the file is in English ("News", "New", "Improved", "Fixed",
"Unreleased").
