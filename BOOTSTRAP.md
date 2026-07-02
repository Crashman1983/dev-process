# BOOTSTRAP — Entwicklungsprozess einrichten / set up the dev-process

**Deutsch:** Diese Datei ist eigenstaendig. Ein LLM oder Coding-Agent kann ihr
in jedem Harness folgen; ein vorinstallierter Adapter ist nicht noetig.

**English:** This file is self-contained. Any LLM or coding agent, in any
harness, can follow it; no pre-installed adapter is required.

## Was installiert wird / What this does

**Deutsch:** Installiert einen portablen Entwicklungsprozess: eine neutrale
Methodik-SSOT unter `docs/process/`, CI-Gates und duenne Adapter fuer Claude
Code, GitHub Copilot und AGENTS.md. Funktioniert in neuen Repositories
(Greenfield) und bestehenden Repositories (Brownfield, additiv; keine
stillschweigenden Ueberschreibungen).

**English:** Installs a portable development process: a neutral methodology SSOT under
`docs/process/`, CI gates, and thin adapters for Claude Code / GitHub Copilot /
AGENTS.md. Works in an empty repo (greenfield) or an existing one (brownfield —
additive; it will not overwrite your files without asking).

## Installation

1. Ensure `uv` is available (https://docs.astral.sh/uv/). The copy step needs
   no other tool. Runtime requirements for rendered gates and hooks are listed
   in [`docs/SYSTEM-REQUIREMENTS.md`](docs/SYSTEM-REQUIREMENTS.md).
   If the template repo is **private**, git needs a credential once —
   `gh auth setup-git` (GitHub CLI) or any git credential helper. Public repos
   need nothing.
2. From the target repository root, run:

       uvx copier copy gh:Crashman1983/dev-process .

3. Answer the prompts:
   - `project_name` — human-readable name.
   - `harnesses` — which adapters to install (`copilot`, `agents_md`); Claude Code
     is always installed.
   - `modules` — which opt-in process modules to enable (e.g. `doc_drift_gate`).
4. Commit the result. Then let the LLM guide the Greenfield or Brownfield setup
   through `docs/process/start-here.md` before further work.

**Deutsch:** Nach dem Kopieren ist der Prozess installiert, aber das Projekt ist
noch nicht fachlich eingerichtet. Das LLM soll mit `docs/process/start-here.md`
brainstorming-artig Greenfield oder Brownfield klaeren, Annahmen bestaetigen
lassen und erst danach echte Projektartefakte schreiben.

**English:** After copying, the process is installed, but the project is not yet
onboarded as a product project. The LLM should use `docs/process/start-here.md`
to clarify Greenfield or Brownfield in a brainstorming-style dialogue, confirm
assumptions, and only then write real project artifacts.

## Agent-Setup ohne Terminal / Headless agent setup

**Deutsch:** copier stellt seine Fragen interaktiv; in Agent-Harnesses (Claude
Code, Codex, Copilot & Co.) gibt es dafuer kein TTY. Uebergib die Antworten
stattdessen vollstaendig auf der Kommandozeile:

    uvx copier copy --defaults \
      --data project_name="<Projektname / project name>" \
      --data 'harnesses={"copilot": false, "agents_md": true}' \
      --data 'modules={"doc_drift_gate": false, "arch_onboarding": false, "feature_registry": false, "github_issues": false, "contracts_drift": false, "git_hooks": false, "contract_first": false, "parity": false, "security_floor": false}' \
      --skip 'CLAUDE.md' --skip 'AGENTS.md' \
      gh:Crashman1983/dev-process .

- `--defaults` beantwortet alles nicht Uebergebene mit dem Default; es darf
  kein interaktiver Prompt uebrig bleiben.
- `--data` erwartet fuer `harnesses` und `modules` das **vollstaendige**
  Dictionary, nicht nur die geaenderten Schluessel.
- `--skip 'CLAUDE.md' --skip 'AGENTS.md'` schuetzt Brownfield-Repos: Ohne TTY
  bricht copier bei einem Inhaltskonflikt sonst mitten im Rendern ab und
  hinterlaesst einen halb installierten Zustand. Mit `--skip` bleibt die
  vorhandene Datei unangetastet und der Lauf schliesst ab. **Niemals**
  `--overwrite` in einem fremden Repo verwenden.

**English:** copier asks its questions interactively; agent harnesses (Claude
Code, Codex, Copilot, and friends) have no TTY for that. Pass all answers on
the command line instead (see above): `--defaults` answers everything not
passed explicitly, `--data` expects the **complete** `harnesses` and `modules`
dictionaries, and `--skip 'CLAUDE.md' --skip 'AGENTS.md'` protects brownfield
repos — without a TTY, a content conflict otherwise aborts mid-render and
leaves a half-installed state, while `--skip` keeps the existing file untouched
and lets the run complete. **Never** use `--overwrite` in a repo you do not own.

**Uebersprungene Adapter mergen / Merge skipped adapters:** Wurde eine
vorhandene `CLAUDE.md`/`AGENTS.md` uebersprungen, kopiere den Block zwischen
`<!-- KERNEL:START -->` und `<!-- KERNEL:END -->` aus einem gerenderten Adapter
in die bestehende Datei und ergaenze einen Verweis auf
`docs/process/start-here.md`. / If an existing `CLAUDE.md`/`AGENTS.md` was
skipped, copy the block between `<!-- KERNEL:START -->` and `<!-- KERNEL:END -->`
from a rendered adapter into your existing file and add a pointer to
`docs/process/start-here.md`.

**Verifikation (Pflicht) / Verification (mandatory):** Behaupte "installiert"
erst nach diesen Checks / claim "installed" only after these checks:

    python scripts/process/gate_runner.py   # Exit-Code 0 / must exit 0
    git status --porcelain                  # Brownfield: nur neue Dateien / added files only

## Empfohlene Reihenfolge / Recommended order

**Deutsch:** Die Modulwahl faellt bei der Installation an; die klaerenden
Fragen stellt aber erst `docs/process/start-here.md` — nach der Installation.
Wenn die Modulwahl noch nicht feststeht, deshalb:

1. Minimal installieren (alle Module `false`, wie oben).
2. Den start-here-Dialog fuehren (Greenfield/Brownfield, Ziel, Stack, Risiken).
3. Die Modulwahl aus den Antworten ableiten — Heuristik: Auth, Persistenz oder
   Security-Invarianten → `security_floor`; mehrere Oberflaechen → `parity`;
   geteilte Schnittstellen oder mehrere Repos → `contract_first`,
   `contracts_drift`; User-Story-Traceability → `feature_registry`;
   Issue-Pflicht → `github_issues`; lokale Durchsetzung → `git_hooks`;
   Architektur als geprueftes Artefakt → `arch_onboarding`; Doc-Hygiene →
   `doc_drift_gate`.
4. Module nachruesten wie unter [Spaeter / Later](#spaeter--later) beschrieben.

Steht die Modulwahl schon fest, setze sie direkt bei der Installation.

**English:** Module choice happens at install time, but the clarifying
questions live in `docs/process/start-here.md` — after the install. If the
module choice is not yet settled: install minimally (all modules `false`), run
the start-here dialogue, derive the module choice from the answers (heuristic
above: auth/persistence/security invariants → `security_floor`; multiple
surfaces → `parity`; shared interfaces or multiple repos → `contract_first`,
`contracts_drift`; story traceability → `feature_registry`; issue discipline →
`github_issues`; local enforcement → `git_hooks`; architecture as a checked
artifact → `arch_onboarding`; doc hygiene → `doc_drift_gate`), then retrofit as
described under [Spaeter / Later](#spaeter--later). If the choice is already
known, set it directly at install time.

## Brownfield-Hinweise / Brownfield notes

- copier never silently overwrites an existing file. On a content conflict it
  prompts you per file (interactive); non-interactive runs abort mid-render
  unless the conflicting files are excluded via `--skip` (safe, see the
  headless setup above) or forced with `--overwrite` (destructive — avoid).
- If you already have a `CLAUDE.md` / `AGENTS.md`, copier will flag the conflict —
  merge the process kernel (the `KERNEL:START`/`KERNEL:END` block) into yours,
  or accept the template's version.

## Spaeter / Later

**Deutsch:** Modul nachruesten oder eine neuere Prozess-Version ziehen — mit
sauberem Arbeitsbaum (`git status --porcelain` leer), dann:

    uvx copier update --defaults \
      --data 'modules={"doc_drift_gate": true, "arch_onboarding": false, "feature_registry": false, "github_issues": false, "contracts_drift": false, "git_hooks": false, "contract_first": false, "parity": false, "security_floor": false}' \
      --skip 'CLAUDE.md' --skip 'AGENTS.md'

`--data` erwartet das **vollstaendige** `modules`-Dictionary mit den neuen
Werten, nicht nur die geaenderten Schluessel. `update` checkt standardmaessig
das neueste **getaggte** Template-Release aus, bewahrt lokale Aenderungen und
markiert Konflikte inline.

**English:** Add a module or pull an updated process version — with a clean
working tree (`git status --porcelain` empty), then run the command above.
`--data` expects the **complete** `modules` dictionary with the new values, not
just the changed keys. `update` checks out the latest **tagged** template
release by default, preserves your local edits, and flags conflicts inline.

**Wichtig / Important:** Do not hand-edit `.copier-answers.yml` to enable a
module. `copier update` reads that file as the *old* state: after a hand edit,
the old and new renders are identical, the missing module files count as
intentional local deletions, and the module is never rendered. Always pass new
answers via `--data`; copier rewrites the answers file itself afterwards.

If you enabled the `git-hooks` module, install the hooks once per clone (they
live in host-local `.git/hooks`, not version control):

    bash scripts/process/install-hooks.sh
