> **Deutsch:** [README-DE.md](README-DE.md)

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/logo-dark.svg">
    <img alt="dev-process — gates, risk tiers, independent review" src="docs/assets/logo-light.svg" width="560">
  </picture>
</p>

# dev-process

A development process for AI coding agents, delivered as a
[copier](https://copier.readthedocs.io) template for new and existing
repositories. It does not change the agents; it changes the conditions they
work under: a program checks the rules, the effort follows the risk, nobody
signs off their own work, and memory lives in files instead of the context
window.

> **Status:** `v2.32.1` — sub-projects SP1–SP75. History (German): [`CHANGELOG.md`](CHANGELOG.md).

## Where to start

| For | Document |
|---|---|
| What the process is, why it works this way, what is still open | **[Overview](docs/OVERVIEW.md)** · [Überblick (German)](docs/UEBERBLICK.md) · [PDF (German)](docs/Entwicklungsprozess-mit-KI-Agenten.pdf) |
| Setting it up, headless or in a dialogue, and updating it | [`BOOTSTRAP.md`](BOOTSTRAP.md) |
| What the machine and CI need (German) | [`docs/SYSTEM-REQUIREMENTS.md`](docs/SYSTEM-REQUIREMENTS.md) |
| This repository's dependencies (generated, also as CycloneDX) | [`docs/SBOM.md`](docs/SBOM.md) · [`docs/sbom.cdx.json`](docs/sbom.cdx.json) |
| Why the standard stack (Spec Kit comparison and design, German) | [`docs/analysis/`](docs/analysis/) |

## The essentials

- **Gates instead of memory.** Before every merge, 15 automatic checks run.
  What fails does not merge. The set was cut to what demonstrably carries
  weight in the reference project.
- **Risk sets the effort.** Tier 0 to 3 decide whether a change merges
  directly or needs a plan, an independent review and, at Tier 3, a
  refutation review. Scope decides the tier, not diff size.
- **Independent review.** Whoever builds does not sign off. The verdict is an
  attestation in the journal and holds only for exactly the reviewed code.
- **Memory in files.** Rule kernel, plans with their decisions and the journal
  live in the repository and are re-injected after every context compaction.
- **Specification with [Spec Kit](https://github.com/github/spec-kit).** From
  Tier 2 on, work goes through Spec Kit, pinned and with its own overrides.
- **Parallel agents, optional.** A steward assigns issues, starts one agent
  session per phase with the model from the model policy, puts questions to
  the owner as a choice, and merges finished branches as a batch.
- **Three harnesses.** Claude Code, GitHub Copilot or a neutral `AGENTS.md`;
  methodology and gates are the same in all of them.

## Installation

Greenfield and brownfield, the same command in the target repository:

```bash
uvx copier copy gh:Crashman1983/dev-process .
```

copier asks four things: project name, harness (`claude` | `copilot` |
`agents_md`), CI (GitHub Actions, on by default) and, optionally, the GitHub
repository for the issue check. Existing
files are not overwritten. Afterwards

```bash
uv run scripts/process/gate_runner.py
```

must be green. Without GitHub CI, the `git-hooks` module is the only
enforcement pillar; nothing enforces the gates remotely then.

**Let an AI agent set it up:** in the target repository, say *"set up the
development process from Crashman1983/dev-process, follow its
`BOOTSTRAP.md`"*. It holds the headless recipe and the mandatory check.

**Updating:** run `uv run scripts/process/template_update.py` in the target
repository. It re-asserts every recorded answer and leaves files the project
lists as its own in `.process-owned` untouched. With plain copier it is
`uvx copier update --defaults --data 'modules={…}'` with the complete module
dictionary (recipe in [`BOOTSTRAP.md`](BOOTSTRAP.md)). Do not hand-edit
`.copier-answers.yml`.

**When it does not pay off:** for throwaway prototypes, one-off scripts and
single-session work, the overhead outweighs the benefit.

## Origin

The process grew over many iterations in a private repository in production
use (the "reference project" in the documents). The history of that growth
is in [`CHANGELOG.md`](CHANGELOG.md) and the git log; everything the template
ships is independent of that project and neutral.

## License

[Apache-2.0](LICENSE): use, modification and redistribution are free,
commercial use included. Every set-up repository receives the license text
as `docs/process/LICENSE`, plus `docs/process/NOTICE.md`: the license covers
the process files, not the project's own code and content. Two specification
templates derive from GitHub Spec Kit (MIT, © GitHub, Inc.); details and the
MIT text in [`THIRD-PARTY-NOTICES.md`](THIRD-PARTY-NOTICES.md), which every
set-up repository receives too. The repository's own dependencies are listed
in the generated [SBOM](docs/SBOM.md) ([CycloneDX](docs/sbom.cdx.json)).
