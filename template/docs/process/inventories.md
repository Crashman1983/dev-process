# Generated inventories

Lists of the things a change most often trips over without knowing they
exist: environment variables, background jobs and the process each runs in,
tables, the tools an LLM can call. They are generated from the code, so they
cannot drift, and they reach the plan through its tasks, so they are read.

Why only these, and no prose specification: in a downstream project, the
blocks that came from "the author did not know this existed" were facts at
code level — a variable a test harness set, the process a job ran in, a
timeout on the other side. A list generated from the code holds such facts; a
hand-written specification of the system would duplicate the code and drift
(`docs/process/review-checklist.md`, Completeness, owns the matching rule
for plans).

## Setting it up

The template knows no stack, so the project supplies one small extractor per
list and declares it in `docs/process/inventories.local.json` (project data;
the template never writes it):

```json
{
  "inventories": {
    "env":  {"command": ["uv", "run", "scripts/inventory_env.py"], "timeout": 120},
    "jobs": {"command": ["python3", "scripts/inventory_jobs.py"], "allow_empty": false}
  }
}
```

- A name is `[a-z0-9-]+`; `command` is an argv (no shell) run in the
  repository root; `timeout` defaults to 120 s; the sum of all timeouts stays
  below 540 s, so the check fits the gate runner's limit.
- An extractor prints one JSON object per line: `id` (unique), `source` (a
  path, optionally `path:line`) and any further fields with scalar values. A
  jobs extractor should name the process a job runs in; an environment
  extractor should cover what the test harness and the Makefile set, not only
  the application's settings. `note` is reserved.
- Anything else is an error, never half a result: a non-zero exit, a timeout
  (the whole process group is stopped), more than 5 MB, output that is not
  UTF-8, a line that is no JSON object, a missing `id` or `source`, a
  duplicate `id`, a nested value, no rows at all unless `allow_empty`.

`uv run scripts/process/inventory.py update` writes `docs/inventory/<name>.md`:
one table sorted by `id`, the other fields in alphabetical order, `source`
without its line number (a line number would turn every edit above it into
drift), then `note`. Notes are optional and hand-written in
`docs/inventory/<name>.notes.json` (`{"<id>": "<text>"}`); `update` keeps them
and names notes whose row is gone.

Where a list replaces prose that said the same (a job list in the
architecture doc, a table of variables in a README), the prose becomes a
pointer to the list: one owner per fact.

## The check

`uv run scripts/process/inventory.py check` regenerates every list and
compares bytes; any difference fails and names the command that refreshes
it, as does a configured list without its file or a file under
`docs/inventory/` without a configured list. Without
`inventories.local.json`, `inventory.py` does nothing and says so.

To make it a gate, register it in `docs/process/gates.local.json`:

```json
{"inventory": {"module": null, "command": ["scripts/process/check_inventory.py", "."]}}
```

The gate entry fails when the configuration is missing or lists nothing —
whoever registered it expected lists. Start it observing, like any new node
(`docs/process/optimization.md`, "The process as a check graph"): either
generate the lists green and then register the gate, or first merge the
owner's line `uv run scripts/process/gate_modes.py weaken inventory --to shadow
--observe --decision "owner …"` and register the gate after it — a weakening
counts only once it is on the integration branch. A local gate is no core
gate, so it can be weakened and restored like any other.

## In the plan

`uv run scripts/process/inventory.py for-plan <plan>` lists the rows whose
source is a file the plan names (or lies under a directory it names), with
the line number from a live run of the extractor; `for-paths PATH…` does the
same for given paths. `/plan` puts each listed row a task touches into that
task (`workflow.md`, Plan). It is a planning aid: when an extractor fails, it
names the path without a line and says why.
