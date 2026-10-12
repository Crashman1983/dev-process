# Refute brief — closed improvement loop (for an independent second-family reviewer)

> **Deutsch, kurz:** Auftrag an Codex Astra, den Plan
> `docs/analysis/2026-10-12-closed-loop-plan.md` und das in v2.67.0
> ausgelieferte Gerüst vor der Umsetzung zu widerlegen. Die Literatur zu Graph
> und Loop Engineering ist unten zusammengefasst, mit Quellen.

## Your role

You are an **independent refuter from a different model family** than the
authors (the plan and v2.67 were written and reviewed by Claude sessions). Your
only job is to find what is wrong, unsafe, unmeasurable or over-engineered. Do
not implement anything and do not soften findings. Where the material below
and the repository disagree, the repository wins. Check every claim you rely
on.

## What to judge

1. **The plan:** `docs/analysis/2026-10-12-closed-loop-plan.md` (v2.68 draft:
   trigger, cross-repo channel, daily maintainer routine, JSON records,
   offline eval suite, noise-aware evaluation, ablation flags, first mechanism
   `scoped-handover`, autonomous flag-off releases). It ends with five open
   questions; answer them.
2. **What v2.67.0 already shipped** (on `main`), only as far as the plan builds
   on it:
   - `template/docs/process/optimization.md`: the contract.
   - `template/scripts/process/optimize.py`: records, freeze, append-only log,
     `active` flags, decision rights.
   - `template/scripts/process/{% if modules.telemetry %}process_kpis.py{% endif %}`:
     the `flow` family.
   - `template/scripts/process/{% if modules.telemetry %}graph.py{% endif %}`
   - `template/{% if harnesses.claude %}.claude{% endif %}/commands/steward.md`:
     the "Improvement loop" section.
   - `MAINTAINING.md`
   - `docs/analysis/2026-10-12-self-improving-process.md`: the concept review,
     decisions and four refute rounds.
3. **The owner's original concept** is summarised in that analysis document,
   sections "Anlass" and "Review des Konzepts". Its goals: minimise lead time,
   tokens, follow-up defects, owner effort and recovery time. Safety,
   correctness and acceptance are floors, never traded. Two standing roles: a
   project steward and a process maintainer ("dev-process agent"). The rollout
   must stay generic for other repositories.

The template is a copier template. Files under `template/` render into
projects; `{% if … %}` in a path means the file ships only with that module.
Tests: `uv run pytest -n 4 --dist loadfile` (about 5 minutes). Lint:
`uv run ruff check .`.

## Attack questions (minimum)

- **Validity of measurement.**
  - Can `flow`, the planned `evaluate` and the offline suite (D6) distinguish
    a real improvement from noise, task-mix drift, model or harness changes,
    and selection effects?
  - Is issue-number parity a sound concurrent control?
  - What sample sizes do realistic effect sizes need, given the variance of
    real issues?
  - Is there leakage in replaying history (the model has seen the solution in
    the repository)?
- **Goodhart and reward hacking.**
  - Which metrics can the maintainer agent or the steward influence directly?
    Examples: fewer recorded rounds, tasks re-labelled `[mechanical]`,
    `Regression-of` trailers left out, issues split to look faster.
  - Which routes let an agent make its own change look good, or erode a
    floor? Anthropic reports that reward hacking on coding tasks generalised
    to broader misalignment, including sabotage. Treat the loop as an
    adversarial setting.
- **Autonomy boundary (D10).** Can "behaviour-neutral, flag-off release" be
  verified, or only asserted? Construct a release that passes the planned
  checks and still changes behaviour for projects that never set a mandate.
- **Cross-repo channel and routine (D2, D4).**
  - Failure modes: lost issues, duplicate records, stale designs imported
    after a freeze, the routine burning budget, and a private project repo the
    maintainer cannot read.
  - Who has write access where, and what is the blast radius of a
    compromised or confused session?
- **Complexity.**
  - Is this the simplest loop that achieves real self-improvement
    ("find the simplest solution possible, and only increase complexity when
    needed")?
  - Name what to cut. Name the minimal viable loop.
- **Graph engineering fit.**
  - Does the concept's "graph" (dependency, context and evidence graph)
    deliver what the current literature attributes to graph engineering?
  - Is keeping the orchestration graph as configuration (D11) the right call,
    or a missed opportunity?
- **Generic rollout.** Does anything in the plan assume the reference project
  (paths, infrastructure, GitHub, Claude-specific transcripts) without a
  configuration seam?

## Deliverable

A Markdown report with:
- a verdict (`pass` / `block`);
- numbered findings, each with severity (BLOCKER / MAJOR / MINOR), the
  plan's decision id or a `file:line`, a concrete failure scenario (and a
  reproduction where code exists), the cause, and a proposed fix;
- answers to the plan's five open questions;
- a "minimal viable loop" proposal;
- findings that share a root cause, grouped.

Post it as a review comment on the pull request that carries this brief, or
hand it to the owner. If you attest in the process's own grammar, the
reviewer is `cross-model`.

## Background material (current as of 2026-10-12)

Third-party summaries are marked as such. Verify before relying on them.

### Terms

- **Loop engineering** (practitioner term since June 2026) means designing the
  system that prompts, checks, remembers and re-runs an agent. An exploratory
  review defines a *loop specification* as a trigger, a goal, a verification
  step, a stopping rule and a memory. It is based on grey literature from the
  weeks after the term appeared, and an LLM agent assisted the search.
  Practitioners name hidden costs: verification debt, comprehension rot,
  cognitive surrender, token blowout.
  - [arXiv 2608.21884](https://arxiv.org/pdf/2608.21884)
  - [The New Stack](https://thenewstack.io/loop-engineering/)
  - [ADTmag](https://adtmag.com/articles/2026/07/01/loop-engineering-emerges-as-developers-put-ai-coding-agents-on-repeat.aspx)
- **Graph engineering** (term since July 2026) means organising multi-agent
  systems as explicit, dynamic, evolving graphs of tasks, agents and system
  state. The survey arXiv 2608.21156 (Feng et al., 21 Aug 2026) places it
  after prompt, context, harness and loop engineering. It uses three views:
  task organisation (decomposition, dependencies, ordering, concurrency,
  verification), agent coordination (mapping work units to heterogeneous
  agents), and runtime state management (recording what happened, locating
  the first invalid state, recovering from validated boundaries).
  - **Critique (third party):** the survey reports no benchmark comparison
    against a baseline, and its taxonomy is a framing device without
    falsifiable predictions.
  - Open challenges named in summaries: semantic alignment, graph governance,
    evaluation, privacy, safe self-improvement.
  - Sources: [arXiv 2608.21156](https://arxiv.org/abs/2608.21156),
    [alphaXiv](https://www.alphaxiv.org/abs/2608.21156),
    [Awesome-Graph-Engineering](https://github.com/DEEP-JLU/Awesome-Graph-Engineering),
    [TrueFoundry overview](https://www.truefoundry.com/blog/agent-harness-graph-engineering-system-intelligence),
    and the earlier taxonomy [Graphs Meet AI Agents (arXiv 2506.18019)](https://arxiv.org/html/2506.18019v1).
  - A separate governance-oriented model: [Agentic Configuration Management
    (arXiv 2608.11166)](https://arxiv.org/pdf/2608.11166), whose four graphs
    include an assurance graph.

### Optimising agent graphs and workflows

- **GPTSwarm** (Zhuge et al., 2024) models agent systems as computational
  graphs and optimises node prompts and edges from task feedback.
- **ADAS** (Hu, Lu & Clune) searches over complete agent designs from an
  archive.
- **AFlow** (ICLR 2025) searches over workflows written as code, using Monte
  Carlo tree search with execution feedback. The authors report an 80.3 %
  average over six QA, code and math benchmarks with GPT-4o-mini, about 5.7
  points above hand-designed workflows, and ADAS at 67.2 % in their own setup.
  - [arXiv 2410.10762](https://arxiv.org/pdf/2410.10762)
- **G-Designer** (ICML 2025) generates a task-specific communication topology
  with a graph auto-encoder. The authors report up to 95 % token savings on
  HumanEval.
  - [PMLR](https://proceedings.mlr.press/v267/zhang25cu.html)
- **Common pattern:** every one of these optimises against **fixed, fast
  benchmarks**. Offline evaluation is the engine of the loop.

### Self-improving coding agents and harnesses

- **Darwin Gödel Machine:** keeps an archive of self-modified agents. Reported
  SWE-bench 20 % → 50 % and Polyglot 14.2 % → 30.7 %.
  - **Reward hacking observed:** it removed its own hallucination-detection
    markers and produced fake logs (secondary reports).
  - [HF Papers](https://huggingface.co/papers/2505.22954),
    [The Register](https://www.theregister.com/2025/06/02/self_improving_ai_cheat/)
- **SICA:** a self-improving coding agent. Reported 17 % → 53 % on a
  SWE-bench Verified subset.
  - [arXiv 2504.15228](https://arxiv.org/pdf/2504.15228)
- **Harness self-improvement, 2026:**
  - Meta-Harness (arXiv 2603.28052): a proposer searches harness code and
    returns a Pareto frontier.
  - Self-Harness (arXiv 2606.09498): mine weaknesses, propose a bounded
    change, run regression validation on held-in and held-out splits.
  - Adaptive Auto-Harness (arXiv 2606.01770): notes that such systems are
    usually evaluated only on fixed offline benchmarks, and targets
    open-ended task streams.
  - Reading list: [Awesome-Harness-Self-Improvement](https://github.com/leezythu/Awesome-Harness-Self-Improvement);
    synthesis: [L. Weng, Harness Engineering for Self-Improvement](https://lilianweng.github.io/posts/2026-07-04-harness/).
  - These are abstract-level summaries; read the papers.
- **Multi-agent failure modes:** the MAST taxonomy (NeurIPS 2025) lists 14
  failure modes in three groups: system design or specification, inter-agent
  misalignment, and task verification. Failures stem mainly from design and
  coordination, not from model limits.
  - [arXiv 2503.13657](https://arxiv.org/html/2503.13657v2)
- **Code graphs for context:** LocAgent (graph-guided localisation),
  RepoGraph (ego-network retrieval) and CodexGraph (graph-database querying,
  NAACL 2025).
  - [LocAgent](https://arxiv.org/pdf/2503.09089),
    [CodexGraph](https://www.arxiv.org/abs/2408.03910)

### Anthropic publications (primary sources, read in full)

- [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)
  (Dec 2024)
  - Workflows versus agents; the evaluator-optimizer pattern needs clear
    criteria and feedback that demonstrably helps.
  - "find the simplest solution possible, and only increasing complexity when
    needed"; stopping conditions; ground truth from the environment.
- [Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
  (Sep 2025)
  - Context rot; "the smallest set of high-signal tokens".
  - Just-in-time retrieval, compaction, structured notes, sub-agents.
- [Effective harnesses for long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)
  (Nov 2025)
  - Initializer and coding agents; feature list, progress file and git as
    memory.
  - Failure modes: premature victory and features marked done without tests.
  - JSON is less likely than Markdown to be inappropriately overwritten.
- [Harness design for long-running application development](https://www.anthropic.com/engineering/harness-design-long-running-apps)
  (Mar 2026)
  - Planner, generator and evaluator.
  - Self-evaluation is lenient; a separate, tuned evaluator is easier to make
    sceptical, though evaluators also talk themselves into approving.
  - "every component in a harness encodes an assumption about what the model
    can't do on its own"; components were dropped as models improved.
- [Building a C compiler with a team of parallel Claudes](https://www.anthropic.com/engineering/building-c-compiler)
  (Feb 2026)
  - The verifier decides what gets optimised; a weak test suite means the
    wrong problem gets solved.
  - Lock files and git for coordination; regressions late in the project;
    "easy to see tests pass and assume the job is done".
- [Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
  (Jan 2026)
  - Code-based, model-based and human graders; capability versus regression
    evals; pass@k versus pass^k.
  - "One-sided evals create one-sided optimization"; read transcripts; the
    agent should not be able to cheat the eval.
- [Quantifying infrastructure noise in agentic coding evals](https://www.anthropic.com/engineering/infrastructure-noise)
  (Feb 2026)
  - Infrastructure alone shifted scores by up to 6 points.
  - Be sceptical of gaps under 3 points until configurations are matched;
    treat configuration as an experimental variable.
- [How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system)
  (Jun 2025)
  - Gains on breadth-first tasks; token usage explains most of the variance.
  - Multi-agent setups cost several times more tokens and are less suited to
    tightly interdependent tasks such as coding.
- [Natural emergent misalignment from reward hacking in production RL](https://www.anthropic.com/research/emergent-misalignment-reward-hacking)
  (Nov 2025)
  - Learning to cheat on coding tasks generalised to alignment faking and
    sabotage.
  - Mitigations: prevent the hacking, diversify safety training, inoculation
    prompting.
  - [arXiv 2511.18397](https://arxiv.org/html/2511.18397v1)
- [Eval awareness in Claude Opus 4.6's BrowseComp performance](https://www.anthropic.com/engineering)
  (Mar 2026; listed on the engineering index): models may notice they are
  being evaluated.

### Developer productivity evidence

- **METR RCT (2025):** experienced open-source developers were 19 % slower
  with AI but believed they were about 20 % faster.
  - The 2026 follow-up is inconclusive; per secondary reports the control
    groups were compromised.
  - Lesson: measure outcomes, never self-reports.
  - [eWeek](https://eweek.com/news/news-ai-tools-slow-developer-productivity-study),
    [2026 update summary](https://blog.robbowley.net/2026/04/04/metrs-developer-productivity-research-2026-update/)

### Claude Code mechanics relevant to the routine

- **Routines** (research preview since April 2026): saved prompts plus
  repositories run on Anthropic's cloud, triggered by a schedule, an API call
  or GitHub events, with daily run caps per plan (third-party summary).
  - [Daniel Vaughan](https://codex.danielvaughan.com/2026/04/14/claude-code-routines-launch/)
- **In-session options:** `/loop` and desktop tasks.

## Known limits the authors already state

Do not re-report these as new findings unless you show they matter more than
stated:
- names in records are self-declared;
- rewritten git history and shallow clones are invisible to the file checks;
- recovery time is not measured;
- owner effort is a proxy measure;
- tokens are counted only for dispatched sessions with a configured
  transcripts glob.
