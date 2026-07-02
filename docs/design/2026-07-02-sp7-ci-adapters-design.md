# Design: ci-adapters (SP7) + install fallbacks

**Date:** 2026-07-02
**Status:** approved (scope agreed with Seb: review items 4 + 5)
**Slice:** GitLab CI as a second enforcement transport, honest degradation
without any CI, and installation fallbacks for environments without `uv`.

## Gap

The enforcement pillar has exactly one transport: a GitHub Actions workflow,
rendered unconditionally. A GitLab-hosted repo silently loses CI enforcement —
the worst failure mode for a process whose selling point is "holds even when
nobody is looking". Separately, `BOOTSTRAP.md` hard-requires `uv`; agent
sandboxes without `uv` (or without the `gh:` shorthand resolving) have no
documented path at all.

## Decision 1 — new `ci` namespace, not a module and not a harness

CI providers are the *transport* of enforcement, orthogonal to both process
capabilities (`modules.*`) and LLM ergonomics (`harnesses.*`). They get their
own copier question:

```yaml
ci:
  github: true    # default — preserves current behavior byte-for-byte
  gitlab: false
```

`github: true` by default means existing rendered repos see no change on
`copier update` (the answers file gains the key with today's behavior). A gate
never gates on `ci.*`: the gate set is decided by `modules.*`; `ci.*` only
decides which pipeline file invokes `gate_runner.py`.

## Decision 2 — GitLab renders as include-file + thin root shim

GitLab has exactly one root `.gitlab-ci.yml`, and brownfield repos already own
it. The job therefore lives in an includable file that never collides:

- `.gitlab/ci/process-gates.gitlab-ci.yml` — the actual job (mirrors the
  GitHub workflow: python 3.11, `pip install pyyaml`, run `gate_runner.py`).
- `.gitlab-ci.yml` — a thin `include: local:` shim for greenfield.

Brownfield with an existing `.gitlab-ci.yml`: copier flags the conflict (or
the headless recipe skips it via `--skip '.gitlab-ci.yml'`); the user merges
one `include:` line — the same merge model as the `KERNEL` block for adapter
files. The GitHub workflow moves behind `{% if ci.github %}` with an otherwise
unchanged path and content.

## Decision 3 — degradation is documented, never implied away

With `ci: {github: false, gitlab: false}` the enforcement pillar is local git
hooks only (`modules.git_hooks`) — and without that module, nothing enforces.
README, BOOTSTRAP and SYSTEM-REQUIREMENTS say this explicitly. The honest
ceiling applies to the process itself, not just to its gates.

## Decision 4 — install fallbacks are docs, not tooling

`BOOTSTRAP.md` gains a fallback ladder, each step verified:

1. `uvx copier copy …` (unchanged default),
2. `pipx run copier copy …` (same isolation, different runner),
3. `python3 -m venv` + `pip install copier` (bare python),
4. `git clone <https-url>` + `copier copy ./dev-process .` when the `gh:`
   shorthand cannot resolve (note: a local clone renders the latest *tag*;
   `--vcs-ref=HEAD` overrides).

No wrapper script: every rung is one standard command, and a script would be
one more thing to keep honest.

## Out of scope

A `language: de/en/both` option (review item 5, "langfristig") — touches every
bilingual file and deserves its own slice.
