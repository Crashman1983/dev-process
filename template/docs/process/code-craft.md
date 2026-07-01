# Code Craft

Concrete practices behind mandatory rule 9 (*code is written to be read*). None of
these are mechanically checked — they are judged at the review gate. Treat them as
defaults, not dogma: match the surrounding code when it already sets a convention.

## Intention-revealing names

- Names state purpose, not type or mechanism: `unpaid_invoices`, not `list1` or `data`.
- A function's name says what it returns or does; a boolean reads as a predicate
  (`is_expired`, `has_access`). Avoid abbreviations that only the author expands.
- The wider the scope, the more descriptive the name: a loop index may be `i`; a
  module-level constant may not.
- Rename as meaning drifts — a stale name is a lie the reader trusts.

## Small, single-purpose units

- A function does one thing at one level of abstraction. If you need "and" to describe
  it, it is two functions.
- Prefer early returns over deep nesting; keep the happy path unindented.
- A unit you cannot hold in your head at once is too big — split by responsibility,
  not by line count.

## No magic numbers or strings

- A literal with meaning gets a named constant at the point it is defined
  (`MAX_RETRIES = 3`), so the reader learns the intent, not just the value.
- The same literal appearing twice is a missing name, not a coincidence.

## Comments explain *why*

- The code says *what*; a comment earns its place by saying *why* — the constraint, the
  trade-off, the non-obvious reason. `# increment i` is noise.
- A comment that restates the code rots the moment the code changes. Delete it or make
  it explain intent.
- Prefer making the code self-explanatory over annotating unclear code.

## Structure serves the reader

- Things that change together live together; unrelated concerns live apart.
- Consistency inside a file beats personal preference — a reader should not have to
  re-learn conventions per screen.
