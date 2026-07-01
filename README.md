# dev-process

Ein **portables, harness-agnostisches, modulares Muster** für einen stark
automatisierten KI-gestützten Entwicklungsprozess — destilliert aus KenniNext,
einspielbar in **neue (Greenfield)** und **bestehende (Brownfield)** Projekte.

Ausgeliefert als [copier](https://copier.readthedocs.io)-Template. Adapter für
**Claude Code**, **GitHub Copilot** und **AGENTS.md** (Codex / Gemini CLI / Aider …).

> **Status:** SP1 (Foundation) implementiert. Setup-Anleitung: [`BOOTSTRAP.md`](BOOTSTRAP.md).
> Design: [`docs/design/2026-07-01-foundation-design.md`](docs/design/2026-07-01-foundation-design.md).

---

## Idee in einem Absatz

Der Wert eines Entwicklungsprozesses steckt in seiner **Methodik** (Regeln, Risiko-Tiers,
Zyklus, ADRs, Journal) und seiner **harten Durchsetzung** (CI-Gates, git-Hooks) — beides
ist reines Markdown + git und damit tool-unabhängig. Nur die **aktive Automatisierung**
(Slash-Commands, Skills, Subagents, Hooks) ist harness-spezifisch. `dev-process` legt die
Methodik als neutrale SSOT (`docs/process/`) ab, erzwingt sie über CI, und liefert dünne
Adapter je Harness — die schweren Prozess-Bausteine sind zuschaltbare Module.

## Geplante Nutzung (SP1)

**Greenfield oder Brownfield — derselbe Befehl:**

```bash
uvx copier copy gh:Crashman1983/dev-process .
```

copier fragt die gewünschten **Module** und **Harnesses** ab und rendert nur diese.
Bestehende Dateien werden **nicht** überschrieben (additiver Brownfield-Drop-in).
Ein Modul später nachrüsten: Antwort in `.copier-answers.yml` ändern → `copier update`.

**Pull-Mode** (ein KI-Agent richtet es ein): dem Agenten im Zielrepo sagen
*„richte den Entwicklungsprozess aus diesem Repo ein, folge dessen `BOOTSTRAP.md`"* —
der Rest ist self-contained beschrieben.

## Roadmap

| Sub-Projekt | Inhalt | Status |
|---|---|---|
| **SP1** Foundation | Kern + Adapter + copier-Init + additiver Brownfield-Drop-in | ✅ implementiert |
| **SP2** Brownfield-Architektur-Discovery | Architektur-Interview + Verifikation gegen echten Code | 🔜 geplant |
| **SP3** Multi-Repo / Multi-Mensch | Upstream-Governance + Cross-Repo-Contracts + Koordination | 🔜 geplant |
