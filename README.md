# SWE Agent

**A local-first operating layer for reliable Claude Code and Codex work. It keeps repository
instructions, roles, and verification evidence from drifting—without becoming a runtime, framework,
or hosted service.**

It is a set of conventions and installable tooling for routing agents, assigning accountable roles,
and proving work locally. Current tooling is authoritative; measured decisions and mistakes stay in
the documentation so the setup can be inspected rather than trusted on faith.

[Quickstart](#quickstart) · [Current state](#current-state) · [Product requirements](#product-requirements) · [Components](#components) · [Architecture](#architecture) · [Working here](#working-in-this-repository) · [Weekly improvements](#weekly-improvements)

If this setup helps, use GitHub's **Star** button to help other builders discover it.

## Quickstart

```bash
cd install && ./install.sh && ./verify.sh
```

Then open a project in Claude Code or Codex and run the **`project-onboarding`** skill. Requirements
and installer behaviour: [install/README.md](install/README.md).

## Current state

The repository currently ships six published skills, thirteen generated personas, local session and
Git guards, a cross-harness installer, and executable verification for the published toolchain. The
execution methodology is at v3.0: work is bound to one approved outcome, tasks default to a
card-free light lane and earn a validated card only when they cross a durable boundary or safety
surface, and review runs under a mechanical budget — one reviewer plus conditional specialists, two
rounds, then escalation to a human gate, enforced by a pre-dispatch check rather than by
instruction. Cards are capped at 150 lines with large frozen payloads held by reference, and every
milestone receipt records what the process cost next to what it shipped. Validation commands remain
direct processes; Gradle evidence must use exact `--rerun-tasks`, and single-use JUnit receipts
verify that post-boundary XML records the expected classes and counts without failures, errors, or
skips. Receipts are not tamper-resistant against a deliberate local writer; the full trust boundary
is stated in the skill's JUnit-evidence reference.

The remaining known publication gap is `project-conformance`: it is installed locally but is not
yet part of the vendored public skill set. Its scope and the coordinated edits still required are
recorded in [What is published, and what is not](docs/README.md#what-is-published-and-what-is-not).
There is no application release, production deployment, or application roadmap behind this
repository. Completed material changes are summarized in the
[weekly improvement record](#weekly-improvements), with settled choices and rejected alternatives
preserved in [decisions.md](docs/decisions.md).

## The problem

Agent setup rots invisibly. An `AGENTS.md` written in month one describes a repository that no
longer exists; a guide gets renamed and every link to it dies silently; the same reviewer role is
re-invented from scratch in every session, with a different model each time. Nothing fails loudly —
the agent just quietly does worse work, and you attribute it to the model.

Three things follow from that:

1. **A route has to be validated like code**, or it decays into confident fiction.
2. **Roles have to be defined once**, or every session re-derives them differently.
3. **Whatever is not checked will drift**, so the checks matter more than the content.

## Product requirements

This repository is tooling and documentation rather than an end-user application, so it does not
invent application PRDs. Its product requirements are the normative contracts below; detailed
behaviour stays in those linked documents instead of being copied into the front page.

| Requirement authority | What it defines |
|---|---|
| [Repository contract](AGENTS.md) | Public-repository boundaries, source authority, goal-bound execution, and required verification. |
| [Operating model](docs/operating-model.md) | Local-first priorities, execution stages, independent judgment, and what “done” means. |
| [Published surface](docs/README.md#what-is-published-and-what-is-not) | Which skills are deliberately vendored and which absences are known or intentional. |
| [GitHub policy](docs/github.md) | Storage-only GitHub posture, local push protection, milestone PRs, and merge history. |

## Components

| Component | What it gives you | Deep dive |
|---|---|---|
| Route, repository taxonomy, and migration | A short, validated task route plus a common repository layout; the migrator plans or applies a link-preserving move into that layout. | [Progressive disclosure](docs/progressive-disclosure.md) · [Repository standard](docs/repository-standard.md) |
| Onboarding and shared skills | A repeatable way to add the route, per-clone hooks, and published workflows to a project; the installer mirrors shared skills to both harnesses. | [Install](install/README.md) · [Onboarding](docs/onboarding-a-project.md) · [`project-onboarding`](install/skills/project-onboarding/SKILL.md) |
| Personas and specialists | Thirteen base personas with deliberate role, model, effort, and write boundaries; project specialists are derived from the repository's guardrails, architecture, and product requirements. | [Agent personas](docs/agent-personas.md) |
| Controlled execution and independent judges | Fresh review falsifies design and plan before approval; a bounded scope → build → review → test loop then uses task cards and a builder who never approves their own work. | [Operating model](docs/operating-model.md) |
| Environment, drift, and learning signals | Preflight catches machine gaps; checks distinguish machine-global Claude/Codex mirror drift from installed-versus-published vendored-layer drift; repository lessons preserve corrections. | [`preflight.sh`](install/hooks/preflight.sh) · [`check_toolchain.py`](install/skills/progressive-disclosure/scripts/check_toolchain.py) · [`verify.sh`](install/verify.sh) |
| Local project proof and Git safety | Focused tests, project gates, and local E2E establish project readiness; identifier and push guards protect commit and push. | [Operating model](docs/operating-model.md) · [`identifier_guard.py`](install/skills/progressive-disclosure/scripts/identifier_guard.py) · [`push_guard.py`](install/skills/progressive-disclosure/scripts/push_guard.py) |

Optional code-graph navigation is available when `graphify` is installed; it is not required for the
route, installer, or local checks.

## Architecture

![SWE Agent architecture and data flow](docs/assets/swe-agent-architecture.png)

Repository knowledge is the durable source of truth. Shared skills accelerate both harnesses;
session signals are Claude-specific. Neither replaces repository knowledge.

| Stage | Core capability and what happens | Repository and tooling entry points | Value created |
|---|---|---|---|
| 1. Repository route | A repository declares its contract and task routes in `AGENTS.md` and `docs/agents/`; the repository standard supplies the common taxonomy and a migrator. | `AGENTS.md`, `docs/agents/`, [`validate_disclosure.py`](install/skills/progressive-disclosure/scripts/validate_disclosure.py), [repository standard](docs/repository-standard.md) | Durable, shared context reduces rediscovery and makes stale links visible. |
| 2. Shared capabilities | The published vendored layer provides reusable skills; the persona pool defines role, model, effort, and write boundaries. Session signals remain Claude-only. | [Published skill declaration](docs/README.md), [persona sources and generator](docs/agent-personas.md), [`verify.sh`](install/verify.sh) | Repeatable work patterns and consistent role routing; the verifier can compare this repository's published layer with installed state. |
| 3. Harness layer | Claude Code and Codex consume the same repository knowledge; skills are mirrored and personas are rendered for each harness. A persona stays in the harness being driven. | [Installation inventory](docs/what-gets-installed.md), [`install_hooks.py`](install/skills/progressive-disclosure/scripts/install_hooks.py), [no cross-harness dispatch](docs/agent-personas.md#no-cross-harness-dispatch) | One repository route works across both harnesses without cross-harness dispatch. |
| 4. Controlled work loop | Fresh, read-only review tries to falsify design and plan before their human gates; approved work then moves through scope → build → review → test using task cards. Judges are independent; a builder does not approve their own work. | [Operating model](docs/operating-model.md), [full adoption walkthrough](docs/full-adoption.md) | Expensive mistakes surface before implementation, while evidence thresholds and one bounded rereview prevent review-driven scope drift. |
| 5. Local proof | Focused and adjacent tests lead to a project's area gate, then full local E2E with real services. Environment preflight and Git hooks protect commit and push; this repository's `verify.sh` proves only its published tooling and installation. | [Operating model](docs/operating-model.md), [`preflight.sh`](install/hooks/preflight.sh), [`identifier_guard.py`](install/skills/progressive-disclosure/scripts/identifier_guard.py), [`push_guard.py`](install/skills/progressive-disclosure/scripts/push_guard.py), [`verify.sh`](install/verify.sh) | Local gates decide readiness; failures and unknowns are reported honestly without mistaking toolchain verification for a project's production-path proof. |
| 6. PR and audit trail | GitHub stores code and configuration; milestone PRs and merge commits preserve the audit trail after local proof. It does not run hosted CI or deploy work. | [GitHub policy](docs/github.md) | Durable backup and history without mistaking a push for validation. |

Lessons and session signals feed corrections back into repository context. They are distinct from
machine-global Claude/Codex mirror drift and from `verify.sh`'s installed-versus-published vendored
layer comparison; all three make a stale assumption visible to the next task.

## Documentation

| Read | For |
|---|---|
| [operating-model.md](docs/operating-model.md) | How work is sequenced, and what counts as done |
| [progressive-disclosure.md](docs/progressive-disclosure.md) | The four layers, the README contract, the validator |
| [repository-standard.md](docs/repository-standard.md) | Where files belong; migrating an existing repo |
| [github.md](docs/github.md) | Storage-only rules, the push guard, zero-cost posture |
| [agent-personas.md](docs/agent-personas.md) | The roster, and why each is routed as it is |
| [decisions.md](docs/decisions.md) | Decisions and rationale, each against what was chosen over |
| [measurements.md](docs/measurements.md) | The numbers those decisions rest on |
| [onboarding-a-project.md](docs/onboarding-a-project.md) | Five steps to bring a project under the standard |
| [full-adoption.md](docs/full-adoption.md) | The long version, with guard-testing |
| [codex.md](docs/codex.md) | The Codex side, and what it does not get |
| [what-gets-installed.md](docs/what-gets-installed.md) | Every file the installer places, and why |

## Working in this repository

Start with [AGENTS.md](AGENTS.md), then use [docs/README.md](docs/README.md) to open only the guide
needed for the task. The executable tooling in `install/` is authoritative. Changes to a vendored
skill or hook originate in its maintained user-level source and are then re-vendored; the exact
inventory and exceptions are documented in [what-gets-installed.md](docs/what-gets-installed.md).

Before review, run the complete local gate:

```bash
cd install && ./install.sh --dry-run && ./verify.sh
```

GitHub stores the resulting code and configuration; it does not validate or deploy them. Changes
land through milestone-sized pull requests, with an honest README, real local-gate output, an
independent review, and a merge commit that preserves the audit trail. See
[github.md](docs/github.md) for the push guard and zero-cost forge rules.

## Weekly improvements

A concise record of one material repository improvement each week, newest first. Current tooling
remains the authority for behaviour; each entry points to the implementation it describes.

### Week of 10 August 2026 — methodology v3.0: the review budget

A two-week audit of actively developed repositories measured the v1.4–v2.1 machinery producing more
process than product: review rounds ran far past the written two-round stop-loss, workspaces filled
with re-serialized diffs of changes git already stored, and milestones stalled on card
preconditions. The numbers are in [measurements.md](docs/measurements.md). v3.0 applies the
methodology's own mechanism-over-intention principle to its review loop:
[`check_review_budget.py`](install/skills/execution-methodology/scripts/check_review_budget.py)
refuses a third review round on any subject and rejects the diff-snapshot and restatement-packet
artifact classes outright, and a 20% growth tripwire ends any review that expands its subject.
Tasks default to a card-free light lane; the card validator now enforces a 150-line card budget and
a ten-line inline limit for frozen values; milestone receipts carry process metrics so a process
regression is triaged like any other. The methodology body shrank from 732 to about 410 lines, with
the JUnit-evidence and Codex-sandbox protocols moved verbatim into reference files and the v1–v2
changelog preserved alongside them.

### Week of 3 August 2026 — goal-bound execution with trustworthy evidence

The [execution methodology](install/skills/execution-methodology/methodology.md) now binds each
implementation and review repair to one approved Goal Capsule, classifies findings before they can
become scope, and returns repeated causal failure to a human plan gate. Contract v2.1 also casts the
existing read-only reviewer in fresh design and plan modes before their approval gates. `PASS` is a
valid outcome; blocking findings need a reachable counterexample and artifact evidence, and one
correction plus one scoped rereview prevents an adversarial pass from becoming an endless debate.

Task-card validation contract v2 replaces shell command strings with direct `{cwd, argv}` processes
and accepts only exact `--rerun-tasks` as Gradle freshness evidence. Single-use JUnit receipts verify
post-boundary XML freshness and consistency and reject pre-existing or same-content XML, replay,
count mismatches, failures, errors, and skips; the exact uncached runner command establishes
execution.

[`verify.sh`](install/verify.sh) executes the published vendored suites and reports what each proved:
tests run, skips or not-tested status, failures, or inability to run. The installer also derives the
published skill roster from its declaration instead of maintaining a second count.

## What this is not

**Not a framework.** There is no runtime, no package, no API. It is a set of markdown conventions,
a handful of skills and session hooks, and Python scripts with no dependencies outside the standard
library. Every file the installer places is enumerated in
[what-gets-installed.md](docs/what-gets-installed.md) rather than counted here — a count restated in
prose is the first thing to go stale, and the published skills are named and enforced in one place:
[docs/README.md](docs/README.md), "What is published, and what is not".

**Not model-agnostic in its details.** The persona roster names specific models at specific effort
levels. Those were chosen from measurements taken in one week of 2026 and will age. The *principles*
— effort tracks reasoning depth, model tracks stakes, frequency decides where saving matters — are
the durable part. Retune the table.

**Not team-tested.** Several decisions are correct *because* this is a one-person, one-laptop
operation and would be wrong with more people: no hosted CI, merge commits over squash, and local
git hooks standing in for branch protection. Those are marked where they appear.

**Not a substitute for reading it.** Installing an agent configuration you have not read is how you
end up with rules you do not understand and cannot debug.

## README design choices

The README contract is applied to the questions readers actually have. *Current state* describes
the shipped toolchain and its known publication gap; *Product requirements* routes to this
repository's normative contracts instead of inventing application PRDs for a project with no
application runtime. The full contract and validator live in
[progressive-disclosure.md](docs/progressive-disclosure.md).

If this local-first setup helps your agent work hold together, use GitHub's **Star** button to help
other builders discover it.

## Licence

MIT. See [LICENSE](LICENSE).
