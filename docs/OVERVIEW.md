# Development Process with AI Agents

*How goals, architecture and quality stay secured over time – and what role the human plays*

Principles, mechanics and the path to broad rollout

Process template dev-process v2.25.0 · tested in a real repository in production use (reference project)

Template published on GitHub: [github.com/Crashman1983/dev-process](https://github.com/Crashman1983/dev-process)

The process was built and improved over many iterations in live operation; it has yet to prove itself at scale. One possible next step is a pilot, for example on GitHub with Copilot. This document describes what is implemented today, separates hard-checked rules from those kept soft, shows how the building blocks could be carried over to such a platform, and collects open questions at the end. Operational details of the reference project are examples, not requirements.

> German version: [UEBERBLICK.md](UEBERBLICK.md) · PDF (German): [Entwicklungsprozess-mit-KI-Agenten.pdf](Entwicklungsprozess-mit-KI-Agenten.pdf).
> Setup: [`BOOTSTRAP.md`](../BOOTSTRAP.md) · System requirements (German): [`SYSTEM-REQUIREMENTS.md`](SYSTEM-REQUIREMENTS.md).

---

## 1. The challenge and the answer

> AI agents can write good code, but they work under poor conditions: no memory, no evidence, no independent acceptance. The process changes the conditions, not the agents.

| Agent weakness | What happens without a process | The process's answer |
|---|---|---|
| No long-term memory: after a break or an automatic shortening of the conversation, rules and agreements are gone. | The agent breaks agreements made an hour ago and reopens decisions already taken, possibly deciding differently. | The key rules are in the startup file that every agent reads first; decisions are a list in the plan. After every shortening, a program automatically feeds both back in. |
| Asserting instead of checking: statements about existing code come from memory. | The agent builds on a function that does not exist – or misses an existing one and writes it a second time. The result is duplicate code and dangling references. | Rule 1: every statement needs evidence or is marked as an assumption. For documentation, a Gate (an automatic check before the Merge) also verifies that it only references files that exist. |
| Patching symptoms: a fault is fixed where it becomes visible. | The cause stays; its symptom is patched separately in five places, and the fault rate rises. | Rule 6: after at most two attempts at the symptom, look for the cause. The metrics show where the same spot is corrected again and again. |
| Self-acceptance: the agent that built something also judges whether it is good. | Review becomes a formality; defects only surface in production. | Independent review by an uninvolved instance; the result is recorded as an attestation (a written review record in the journal, the running work log in the repository) and required by the Gate. |
| Parallel work without coordination: several agents change the same files. | The last change overwrites the one before; work is lost. | An overview of all running work items (the situation table) shows overlaps; two efforts on the same problem are coordinated instead of worked on in parallel. |

### The essentials in five sentences

1. **A program checks the rules, so nobody has to keep them in mind.** Sixteen automatic checks (“Gates”), eighteen with the compliance pack, run before every Merge; whatever fails is not merged.
1. **Risk sets the effort.** Four risk tiers – Tier 0 to 3 – decide whether a change may be merged directly or needs a plan, independent review and, at Tier 3, also a refutation review (targeted search for faults).
1. **Review is always independent.** Whoever builds does not accept their own work; from Tier 2 on, an uninvolved instance (a separate agent session) reviews, and its verdict applies only to exactly the code it reviewed.
1. **All knowledge lives in files.** Plans, decisions and journals are in the repository and are automatically shown to every agent again as soon as its memory has been shortened.
1. **The human decides, the agents work.** A coordinator agent hands out work to worker agents; the human prioritises, decides, approves designs and reviews a sample every week.

## 2. How the process is structured

> Five layers, each with a clear responsibility. Humans judge, agents work, programs check, files keep the knowledge.

| Layer | What happens there |
|---|---|
| **Human (Owner)** | prioritises, decides, approves designs, reviews a sample every week, evolves the rules |
| **Coordinator** | gets the overview, assigns work items, starts and stops workers, passes questions to the human, triggers the Merge – writes and reviews no code itself |
| **Workers and reviewers** | a separate session on its own Branch for each work item and phase; the reviewer is always a different instance from the worker |
| **Gates** | sixteen check programs before every Merge (eighteen with the compliance pack): rules intact, decisions taken, attestation present and matching the code, contracts kept, documentation valid |
| **Repository** | rule kernel, plans with decision lists, journal with attestations, situation table, contracts, metrics – the single source every layer reads from |

The process ships as a template (dev-process). From it you get a fully set-up repository: the startup file and phase commands for the chosen Harness (GitHub Copilot, Claude Code or a neutral AGENTS.md), the Gates, and GitHub Actions workflows for Gates, Owner-Digest, metrics and cleanup. A repository pulls later versions of the template with one command; project-specific files stay untouched.

## 3. Rules and risk tiers

> Nine rules always apply; how much procedure a change needs depends on its risk, not its size.

**The nine rules** are in every startup file, and a Gate checks them character by character against the original:

| # | Rule | # | Rule |
|---|---|---|---|
| 1 | Evidence before assertion – every statement about code is backed by evidence or marked as an assumption | 6 | Cause before symptom – after at most two attempts at the symptom, look for the cause |
| 2 | Plan before work – from Tier 2 on, a written plan before any code is written | 7 | Review before Merge – as independent as the risk requires |
| 3 | Contract first – interfaces and user interfaces are specified bindingly before the code | 8 | Small, clearly named changes – exceptions are stated in the commit |
| 4 | One responsible component per behaviour – no copies; decisions that are hard to reverse are documented before code builds on them | 9 | Readable code – written for the next reader |
| 5 | Tests prove acceptance – every criterion has a test |  |  |

**The four tiers.** Risk counts, not size: a ten-line change that other components depend on is Tier 2; a formatting change is Tier 0. The assigned tier may only be corrected upwards. It rises to at least Tier 2 as soon as any of these questions is answered with yes: Is data stored persistently? Does user input leave the process? Is access control involved? Does other code depend on the interface? Is more than one user interface affected? Is data loss possible? Is the same spot changed repeatedly? Tier 3 applies when the change touches access control, data storage and migrations, a security boundary, or a contract across several repositories.

| Tier 0 | Tier 1 | Tier 2 | Tier 3 |
|---|---|---|---|
| No change in behaviour, or local and reversible | Small, self-contained change | Something others depend on: interface, schema | Access control, data storage, security boundary |
| merge directly | Short procedure (goal, files and risk in one sentence, no written plan) plus one test | Plan, implementation, independent review | in addition: approved design, threat question, refutation review, second model (where available) |

**Refutation review** means: at Tier 3, an additional instance reviews the change, and its only job is to find faults. **Second model** means: a model from a different vendor, where one is available; if none is available, the attestation says so explicitly. The Gate does not require the second model, but it does require that its absence is stated openly.

## 4. Review, memory, goals and measurement

> A review verdict only counts if it was reached independently and is bound to exactly the code that was reviewed. What agents need to know – decisions, goals, metrics – is in files and is shown to them again after every shortening.

**Review.** From Tier 2 on, an uninvolved instance receives a read-only Bundle – changes, plan, tests, images – and not the conversation in which the work was done. Its attestation in the journal names the work item, tier, reviewer, model, independence markers, verdict, round and the checksums of the code. The Gate checks whether an attestation exists, whether its markers fit the tier and whether it belongs to the merged code. What it cannot check: whether the reviewer really was a different instance. That rests on the reviewer's own statement – hence the weekly sample by the human.

**Memory.** The plan with its decision list, the journal and the task list are in the repository. A single command pulls from them what is in progress, what comes next, which decisions apply and which question is open. After every shortening of a session, a program automatically feeds the nine rules back in word for word, together with the last twelve decisions. This came from an observation in operation: the plain instruction to reread the rules after a shortening was itself shortened away.

**Goals.** A work item only starts once its type is set and its acceptance criteria exist as testable sentences (“When <trigger>, the system shall <response>”, including negative, edge and permission cases). It is only accepted once every criterion has a passing test, all Gates are green and the documentation is updated. Both conditions are lists in the repository (start checklist and acceptance checklist) and keep growing: if a human says “at the end, X must hold”, X is added.

**Measurement.** A cockpit (an analysis script in the repository) reads the journal, the Git history and reports; every number states how much weight it carries. Four metrics matter:

- **Review rounds to approval.** Target: at most two for 90 % of work items. If a change is still rejected in round 3, a rule is recorded or the work item is split.
- **Correction rate.** Share of features that had to be corrected within seven days; only the trend counts.
- **Correction hotspots.** Spots that are corrected again and again – Rule 6 in numbers.
- **Review rounds per model.** Shows which model works well in which phase.

## 5. Architecture requirements: hard and soft

> Requirements do not hold because someone knows them, but because a Gate checks them (“hard”). Where only a reviewer judges (“soft”), the table says so explicitly.

| Requirement | Mechanism | Hard / soft | Reference project |
|---|---|---|---|
| Decisions before code | Decisions that are hard to reverse are documented before code builds on them; a Gate checks whether required decisions have been taken. Rules that must apply everywhere get one responsible component and a test covering all known cases. | hard: required decisions are taken; soft: whether one is needed at all | 73 decision documents |
| Interfaces first | An interface is specified before anyone uses it; a Gate checks that the specification exists and has not been changed unnoticed since it was fixed. Tests and reviewers check whether the code complies with it. | hard: specification exists; soft: compliance | active |
| User interfaces by contract | A design contract names spacing, colours and states with IDs; reference images are sealed with a checksum. A Gate checks IDs and seals; the reviewer compares the result with the image. | hard: IDs and seals; soft: appearance | active |
| Layers, dependency direction | The architecture description defines which layer must not use which other layer. This is only checked by machine with an architecture linter. | hard only with a linter | linter not set up |
| Security | Tier 3 requires a threat question, a refutation review and – where available – a second model. Optionally, a minimum security standard as a rule set and an SBOM (a list of all third-party components) can be added. | hard: Tier 3 flow; minimum standard only with a rule set | rule set not yet created |
| Performance | The review checklist asks about performance. What is not measured cannot make a check fail. | soft | no target values set |
| Maintainability, documentation | The reviewer judges maintainability against Rules 4, 6 and 9; the metrics show repeated corrections. For documentation, Gates check whether the files and references it names exist. | soft; hard for references | active |
| Legacy | Existing violations are recorded in a Baseline and tolerated; new ones are not. The Baseline may only shrink. | hard as soon as a Baseline exists | procedure in the template |

**Life cycle of a requirement:** A new requirement starts with a decision document. Whatever can be checked by machine becomes a rule in the minimum security standard, a forbidden dependency, or a test covering all known cases; the rest becomes a question in the review checklist. Existing violations go into a Baseline that may only shrink. A new violation makes the Gate fail; an exception exists only as a decision document with an expiry date. New non-functional goals take the same path and also get an item in the acceptance checklist.

## 6. The role of the human

> The human does not write code and does not read every change. What remains is judgement – in five places that no agent may take over.

**Five tasks of the Owner**

- **Prioritise.** The Owner decides what is released next. If an agent creates dozens of work items, work only starts once the Owner has sorted them.
- **Decide.** Every product, architecture or risk question arrives as a choice with options and a recommendation; the answer becomes a decision line in the plan.
- **Approve designs.** At Tier 3, nothing is built before the design is approved. The Merge itself does not need the Owner's approval; Gates and attestation take care of that.
- **Review a sample.** Once a week, read one already merged work item thoroughly; the calendar week determines which one. No agent knows in advance which one will be drawn.
- **Evolve the rules.** The start and acceptance checklists are extended continuously: a requirement from the Owner becomes a permanent part of the process, not a one-off.

The Owner works through the interface of their Harness: on GitHub, for example, through Issues, Pull Requests and the Owner-Digest that a workflow produces; in the reference project, through a chat app, including on mobile. What the Owner no longer does: remind anyone of rules, ask about progress, merge, start sessions (in the reference project; open on GitHub), clean up.

## 7. A work item from start to finish

> Each phase runs in its own session with the model that the model policy (a configuration file) sets for the tier and phase. The phases follow one another without waiting; the only waiting is for the human's decisions.

| Ready | Plan | Implementation | Review | Merge | Deploy |
|---|---|---|---|---|---|
| Owner releases | Plan + decisions | Test first, one commit per task | uninvolved instance, attestation | Merge Queue: Gates and tests once | one deploy per queue run |

**Questions.** If only the Owner can decide, the worker enters the question with options and a recommendation in the plan and reports “blocked”. The coordinator puts it to the Owner as a choice, the answer is recorded as a decision in the plan, and the worker continues.

**Merge.** Approved Branches are collected in a Merge Queue, run together through the Gates and the test suite once, and merged one after the other. If the joint run fails, the Branch that caused it is identified, taken out of the queue and reported back to its worker.

**Coordinator failure.** Nothing is lost: the state is in Git; workers stop when they need a decision; a new coordinator has read in the current state within a minute.

**Example from the reference project:** a Tier 2 work item – plan at 21:18, two questions to the Owner during implementation, Review in three rounds (round 1 Block), Merge at 04:24. Seven hours, two human decisions, no other manual step.

## 8. One option: GitHub with Copilot

> Rules, Gates, journal and metrics are files and scripts based on Git. That is why the process can be carried over to a platform like GitHub: it could run the Gates, track work items as Issues and collect Merges in the Merge Queue; Copilot would read the rules like any other Harness.

The following table shows how the building blocks could be mapped and which of them are already in the template today. It is one way, not a commitment.

| Building block | Possible GitHub means | Status |
|---|---|---|
| Startup file, rule kernel | “copilot-instructions.md” with the checked rule block; path rules under “.github/instructions”. | in the template |
| Phase commands | Prompt files under “.github/prompts” for brainstorm, plan, implementation, review, short procedure, debug, commit, recovery. | in the template |
| Gates | Actions workflow on every Pull Request, registered as a Required Status Check in Branch Protection; a script sets it without overwriting existing rules. | in the template |
| Work items | Issues with type and acceptance criteria; two Gates check whether they are complete and move through their statuses correctly. | in the template |
| Workers | One Copilot session per Issue on its own Branch is conceivable – in the editor or as the Copilot coding agent, which opens a Pull Request. | planned, not tested |
| Review | Uninvolved reviewer with review prompt and Bundle, attestation in the journal; Copilot code review as an additional voice. Since Copilot offers models from several vendors, the second model would only be a configuration entry. | prompt and Gate in the template |
| Merge Queue | The Merge Queue could collect approved Pull Requests, check them together and merge them one after the other. | GitHub feature; not tested (reference project: its own Merge Train) |
| Overview and cleanup | Owner-Digest, metrics and the cleanup of finished Branches run as Actions workflows. | in the template |
| Coordinator | Overview and status reports can run as Actions. It is open who starts and stops the sessions on GitHub. | open (chapter 11) |

**What this would change:** in the reference project the Gates run on a single server; on GitHub they would run in the organisation. With Branch Protection, only an administrator could still bypass the Gates. And for the second model at Tier 3, nobody would have to switch Harness any more. A pilot is meant to show whether this holds up in practice.

## 9. Scaling to an organisation

> The unit of the process is the repository. Machines scale along with it; the limit is the number of decisions an Owner can make.

**What scales along:** every repository gets the template with its own Gates, its own model policy and its own situation table. The template is versioned centrally and contains organisation-wide rules such as layering rules or a minimum security standard; an update arrives as a Pull Request in every repository. Gates run centrally, for example in GitHub Actions, and grow with the organisation. Workers are sessions of the Harness, for example one per Issue, and besides the models the model policy also sets how many of them run at the same time.

**What does not scale by itself:** every repository needs an Owner, and every work item needs on average one or two of that Owner's decisions. How many parallel work items one Owner can carry is the real capacity limit – and it is not measured today. It is also open where the coordinator runs in a larger environment and whether one coordinator can run several repositories.

**What changes for developers:** they take on the Owner role for a repository, review samples, and write acceptance criteria, contracts and decisions. Role profile, training and cover still need to be described (chapter 11).

## 10. Risks and status

> A process that wants evidence for every statement names its own limits. The numbers are a Baseline, not a verdict.

| Risk | What it means | Countermeasure today |
|---|---|---|
| Gates can be bypassed | Without Branch Protection, a Merge can skip the Gates. | Every bypass must be stated in the commit; Branch Protection makes the Gate mandatory; the Owner draws samples. |
| Attestation is self-reported | The Gate cannot verify whether the reviewer was a different instance. | Review sessions are started by a program, not by a human by hand; the attestation is bound to the code; the Owner draws samples. |
| One model family | In the reference project, two thirds of Tier 3 reviews ran without a second model; in that case the Gate only requires an explicit statement. | The refutation review remains; platforms like Copilot offer models from several vendors; whether the Gate should require the second model is open. |
| Model policy is code | The file also contains the start command for the sessions; whoever changes it can run commands on the machine that starts them. | Treated like the configuration of the check environment: every change goes through review. |
| Vendor lock-in | The coordination layer (situation table, coordinator, Merge Train) has so far only been tested with Claude Code. | The process files are vendor-neutral; the template ships adaptations for Copilot, Claude Code and AGENTS.md. |
| A single human | If the Owner is unavailable, decisions are not made. | All knowledge is in files; cover is not yet arranged. |
| Young coordination layer | The situation table, coordinator and Merge Train (the reference project's own Merge Queue) are new and were reworked eight times in quick succession. | Two independent Reviews with 45 findings, all addressed; intention: one week of operation before every extension. |

| Measure (reference project) | Value | Interpretation |
|---|---|---|
| Commits, 14 days | 1,505 | of which 537 documentation and process, 316 corrections, 243 tests, 190 features, 219 other |
| Review verdicts, approx. 4 weeks | 611 Pass / 211 Block | The review finds defects. The Block rate has risen (more recent half of the period 36 %, before that 24 %). |
| Work items with more than 2 rounds | 82 of 396 (21 %) | Target: at most 10 %. From round 3 on, a rule is recorded or the work item is split. |
| Correction rate (features corrected within 7 days) | 44.4 % (20 of 45 features) | DORA band “medium”, close to “low”; only the trend over three periods is meaningful. |
| Correction hotspot | 11 corrections in 5 places | A business rule in the code was patched place by place; it now gets one responsible component and a test. |

The core – Gates, review, rule kernel, journal, design contracts – is stable. The coordination layer is the youngest part. Its eight rapid reworks lead to an intention, not yet a rule: one week of operation before every extension, and changes to the coordination layer go through the same tiers as product code.

## 11. Open questions and outlook

> Whatever is not answered today is listed here as a question with the next step.

| Area | Question | Next step |
|---|---|---|
| Organisation | How many parallel work items can one Owner carry? | Measure decisions per work item and waiting time for the Owner in the pilot; derive the number of repositories per Owner from that. |
| Organisation | Where does the coordinator run, and can one run several repositories? | Run one coordinator per repository in the pilot; then try one for two repositories. |
| Organisation | What becomes of the developers? Who covers for the Owner? | Describe role profile and training; set a cover rule for questions, samples and model policy. |
| Organisation | How does a template change reach many repositories? | Open updates automatically as a Pull Request in every repository; set up a second repository from the template. |
| Architecture | Should the Gate require the second model at Tier 3? | Introduce a rule: if the model policy provides for a second model, the Gate requires it too. |
| Architecture | Is the dependency direction checked by machine? Is there a minimum security standard? How is performance secured? | Set up an architecture linter; create a security rule set; define performance target values as a test and as an item in the acceptance checklist. |
| Architecture | How are exceptions and Legacy handled? | Track every exception as a decision document with an expiry date, with a Gate reporting expired ones; create a Baseline per repository that may only shrink. |
| Process | Does the process hold up on another platform, such as GitHub with Copilot? | Test workers per Issue and the Merge Queue in a pilot repository and compare with the reference project. |
| Process | What kinds of faults occur? | Give every Block verdict a tag, so the cockpit counts kinds of faults, not just quantities. |

What this document does not claim: that the process is finished. What it does claim: that every rule is either checked by a program or explicitly marked as a judgement, that every number states how much weight it carries, and that the open questions are known. That is the point from which a pilot can start.

The process template is public and open for inspection: [github.com/Crashman1983/dev-process](https://github.com/Crashman1983/dev-process)
