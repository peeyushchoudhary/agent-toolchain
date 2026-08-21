---
name: execution-methodology
description: Use when starting, planning, or executing substantive implementation work — writing a product or feature spec, taking a design to a plan, running an approved plan task by task, or deciding what must be true before work can be called done. Also use when a repository's rendered execution guide is missing or stale.
---

# The execution methodology

One pipeline from product intent to a merged milestone, followed identically by Claude Code and
Codex. The rules live in [methodology.md](methodology.md) — read that; this file is how to run it.

## The shape, in one screen

```
product spec → feature spec → design → budgeted review →│GATE│
                                      plan → budgeted review →│GATE│→ tasks
                                                              ↓
              per task, unattended: context → implement → review (2 rounds max)
                   → full-diff review (full lane) → validate → commit + distillation
                                                              ↓
                     milestone: gate → sealed receipt + process metrics → acceptance →│GATE│→ PR
```

Three human gates: the design, the plan, and the merge. Between the plan gate and the merge gate the
loop runs unattended.

## Two lanes

The plan assigns every task a lane by one test: **does it cross a durable boundary** (contract,
schema, migration, queue shape, public interface) **or a declared safety surface** (consent,
authorization, personal or health data, redaction, retention, audit, tokens, money)?

- **Light lane** — the default. No card. The dispatch carries the goal, the capsule criterion, the
  write paths, the tests, and the lane's area check. One implementation review, `test-judge` on
  the gate, commit with distillation. Nothing else.
- **Full lane** — a validated card, the review budget below, one full-diff pass before the commit
  gate, sealed milestone evidence.

A light-lane task that turns out to touch a durable boundary stops and returns to the plan.

## The review budget

One reviewer per round — `security-validator` joins only when a safety surface moves, at most one
other domain specialist only when its invariant moves; never a panel. Two rounds per artifact: one
correction and one scoped rereview, then apply-and-close — the orchestrator applies the final
verdict's named smallest correction and closes; only safety-class findings and principle-7 scope
changes escalate, and every escalation brief names a default action executed after a short founder
wait. A dispatch that never produced a verdict spends no round. An artifact that grows more than 20% in lines
under review escalates immediately — that tripwire, the reviewer count, and the verdict form are
applied by the orchestrator at dispatch construction; the round budget and artifact classes are
enforced by the check. Run it **before every review dispatch**, naming the subject:

```bash
check_review_budget.py WORKSPACE_DIR --next SUBJECT   # exit 1: budget spent, round 3+ recorded,
                                                      # or banned artifact class present
check_review_budget.py WORKSPACE_DIR --json           # machine-readable, for the orchestrator
```

It also rejects banned workspace artifact classes — `.diff` snapshots (name the commit range; git
stores the diff), restatement packets, and files recording failed dispatches (those are one ledger
line each) — and warns when the workspace outgrows its budget, which is a process-regression
signal for the milestone receipt.

## The process-cost budget

Principle 8 says the process is measured and can fail. `ratio_meter.py` is what measures it. It
reads `git log --numstat` over a committed range and splits the churn three ways — **product**
(source, tests, build files, infrastructure), **product thinking** (specs, decision records,
architecture, runbooks, API contracts), and **process** (bookkeeping: cards, verdicts, reports,
workspace, ledger, lessons, receipts, agent instructions). Generated and vendored trees are
excluded and reported separately.

```bash
ratio_meter.py --range main..HEAD        # exit 1: process share over the ceiling
ratio_meter.py --since 2026-08-14        # any date git log accepts
ratio_meter.py --range main..HEAD --json # machine-readable, for the milestone receipt
```

Target model: **product ≥ 70%, process ≤ 10%.** Only the process ceiling reaches the exit code; the
product floor prints as an advisory line, so one number decides the verdict and there is no
argument about which one did. A breach names the five largest process files by churn, because a
budget that only scolds cannot be acted on.

**This one binds, and `check_review_budget.py` does not.** That check was reclassified advisory on
the ruling that the tool is run by the party it binds — it reads a workspace the same party writes.
This meter reads committed history instead, so the product side of the ratio cannot be inflated
without committing product code. Two ways to pass, both of them the thing the budget wants.

A commit that **only deletes** bookkeeping is reported as `cleanup` and can never breach. Removing
bookkeeping is the budget being repaid; a meter that punished it would argue against its own
purpose. Deleting bookkeeping alongside other work is ordinary process churn.

`weekly_review.py` is the cadence, and it is a report rather than a gate — a degrading trend exits
0. The failure principle 8 exists to catch is a slope, not a single bad day: no individual week
breaches while the ratio moves by an order of magnitude.

```bash
weekly_review.py --repo PATH --weeks 8                  # one repository
weekly_review.py --repo PATH --repo PATH --weeks 8      # portfolio roll-up
```

Per ISO week it prints product / product-thinking / process lines, the process share, and a
PASS/BREACH marker; then a trend verdict per repository from the last three weeks against the
previous three. It imports the classifier from `ratio_meter.py` rather than restating it.

## Where it lives, and why in two places

The source is `methodology.md` here. `sync_methodology.py --repo PATH` renders it to
`<repo>/docs/agents/execution/methodology.md`.

Both copies are needed, and for a specific reason: **skills reach one harness; a routed markdown
file in the repository reaches every agent.** Codex has no Skill tool, so anything that lives only
here is invisible to half the fleet — and invisibly so, because the other harness never announces
what it did not read. The rendered file is the one that binds.

```bash
sync_methodology.py --repo PATH          # render into a repository
sync_methodology.py --repo PATH --check  # exit 1 when stale or hand-edited
```

The rendered file carries a version marker; `validate_disclosure.py` reads it and reports drift.
A repository binds the abstract stages to its real commands in
`docs/agents/execution/overlay.md`, which is appended at render time. That overlay is where "run
the lane's area check" becomes an actual command.

## Adoption is staggered, and never automatic

Repositories come under this methodology **one at a time, on purpose**. Nothing here renders into a
repository on its own: a hook that silently wrote the methodology into every project is exactly how
three projects end up running three methodologies, each convinced it is the standard.

Until a repository has adopted it, it says so at every session start:

```bash
sync_methodology.py --repo PATH --adoption-check   # always exits 0 — it informs, it never blocks
```

Four states, and only three of them say anything:

| State | What it prints |
| --- | --- |
| adopted and current | nothing at all |
| adopted but stale | the rendered path and the re-render command |
| deliberately deferred | one line: the reason, and how long it has been deferred |
| unadopted | the adopt command, and how to record a deferral instead |

`--check` remains the gate mode — it is the one that exits non-zero. `--adoption-check` runs from
the SessionStart reporter, wired there by `progressive-disclosure/scripts/install_hooks.py`, so
adopting the shared standard is what turns the warning on.

**Deferring deliberately.** A repository that is not ready records the decision in its own routed
index, `docs/agents/README.md` — the same file, and the same single-line JSON comment shape, that
carries the `agent-personas` base-only decision:

```
<!-- execution-methodology: {"mode":"deferred","reason":"<one line: why not yet>","date":"YYYY-MM-DD"} -->
```

The reason must be non-empty and the date must be a real one. A marker without them is not a
decision, and the check reports the repository as unadopted and says why. The date is what makes a
deferral age visibly instead of quietly becoming permanent.

**There is no registry.** No file anywhere lists which projects have adopted this. Every repository
declares its own state and the check is evaluated against the repository it is invoked on — which is
both a privacy property (this toolchain carries nothing about the repositories it serves) and a
correctness one (a central list is a second source of truth that drifts).

## Running it

**Starting something new** — invoke `product-steward` for the product spec, then the feature spec.
Do not skip to design because the feature seems small; skip to a *short* spec instead. The edge-case
and horizontals sections are where specs are actually incomplete, and they are cheap to write and
expensive to discover.

**Design and plan** — `architect` for the design; `planner` for the plan, with `contract-architect`
on anything crossing a durable boundary. A domain specialist reviews only when the artifact touches
its invariant — at most one, plus `security-validator` on safety surfaces; never a panel. After any
specialist review and before each human gate, cast the existing `reviewer` in design mode before
Gate 1 and plan mode before Gate 2, under the review budget. Freeze interfaces in the plan
*including payloads*. A plan that freezes route names but not request and response shapes hands the
implementer an invention it will make silently. The plan also assigns each task its lane.

**Pre-gate adversarial review** — give a fresh, isolated, read-only `reviewer` only named artifact
paths, never the author conversation or rationale. It actively tries to falsify the artifact against
the frozen criteria and invariants. `PASS` is valid; there is no finding quota. A blocking finding
names the frozen criterion or invariant, a reachable trigger or state sequence, the observable
consequence, artifact evidence, severity, and the smallest correction or human decision.
Preferences, speculative future hardening, and invented requirements are non-blocking.

Freshness is a dispatch property. In Codex, dispatch the pre-gate review and scoped rereview with
`fork_turns: "none"`; another harness must use its equivalent fresh-thread primitive. Prompt wording
alone does not establish isolation. A post-code reviewer dispatch defaults to Implementation unless
Design or Plan is explicitly named, preserving existing implementation-review callers.

The author gets one correction and one scoped rereview. Its dispatch names the persisted original
finding or report path, correction or diff path, corrected artifact path, and governing frozen
artifact paths; it never includes author conversation or rationale. Persisted verdicts are named
`<subject>-r<N>-<kind>.md` — the round marker is what the budget check counts. If a safety-class or scope-change
cause recurs, stop: Design recurrence returns to Gate 1; plan recurrence returns to Gate 2; any
other refusal is closed by applying the final verdict's named smallest correction. The reviewer
never authors or applies its own correction, and the bounded rereview never becomes a consensus
loop. Existing implementation review is unchanged.

**Executing** — hand the approved plan to `chief-of-staff`. It assigns lanes from the plan,
generates cards for full-lane tasks, dispatches, routes reviews under the budget, keeps the ledger,
and stops only on a blocker, a genuine ambiguity, an exhausted review budget, or a writer-failure
escalation (a writer that returns nothing twice is not replaced a third time). A milestone branch
with no commit in 48 hours is a blocker escalation, not silence.

**A report is not a request.** Milestone reports inform; they do not pause the loop. Before
stopping, name the decision — if it is not one of the three gates, a spend, an irreversible or
outward-facing action, or a genuine fork, there is nothing to ask, so proceed and say so in the next
report. "Confirm I should carry on with what we agreed" is not a decision.

Superpowers' `subagent-driven-development` is a good implementation of the same loop and its
workspace scripts are worth using. Two corrections when you do: its prompt templates dispatch
`general-purpose` subagents, which carry every tool — so a "task reviewer" can edit the code it just
judged, which silently destroys the one guarantee the persona pool enforces by restriction. Cast
from the persona pool instead. And its plan workspace is disposable scratch; the program ledger is
not. See the ledger section in `methodology.md`.

## The task card (full lane only)

The card is the implementer's entire world — it does not read the plan, and it reads nothing the
card does not name. The schema and a worked example are in
[references/task-card.md](references/task-card.md).

A card is **150 lines or fewer**, and a `frozen_values` entry longer than ten lines moves to a
committed contract file the card names by path — the validator warns on both, and `--strict` (the
gate mode) fails them. Prerequisites assert tree state, not git history. A wrong card is
regenerated from the plan under a new id — never patched, never versioned by filename.

**Validate the card before dispatching it:**

```bash
validate_card.py CARD_PATH --repo REPO_ROOT            # exit 1 on any ERROR
validate_card.py CARD_PATH --repo REPO_ROOT --strict   # exit 1 on warnings too
validate_card.py CARD_PATH --repo REPO_ROOT --strict --phase post  # after implementation
```

A card asserts that certain paths and tests exist, and everything downstream trusts it. The first
card written under this methodology was wrong three times — most seriously, its `validation` block
named a test class that did not exist, and the build tool silently ignores a filter matching nothing
and reports success. That line claimed to prove an invariant while executing zero tests. None of
those errors is a judgement call; all of them are a script.

Two fields carry most of the value:

- **`context_acquisition`** is a numbered recipe the agent *runs*, not prose it reads. Inline what
  must be verbatim (signatures, payload shapes, event names, formats); retrieve what is stateful
  (branch, ledger head, index freshness).
- **`gate_risk`** names the bookkeeping artifacts the task touches — contracts, manifests,
  taxonomies, inventories, registries. Those are what fail an hour into a full gate run, and naming
  them lets the task check them in thirty seconds instead.

Java tests are declared in `tests` as exact path/class pairs (`Create: path/Test.java :: fqcn` or
`Retain: path/Test.java :: fqcn`). Exact Java Gradle `--tests` class selectors and declarations are
one-to-one; prose cannot substitute for either side.
`--phase pre` (the default) permits an owned `Create` path to be absent; `--phase post` requires the
same declaration to exist, declare the expected package and top-level class, and contain a JUnit
test, so the card is never relabelled during its life. Selectors and rerun protection must occur in
the same direct Gradle `argv`; only `argv[0]` identifies the executable, so another argument cannot
lend Gradle evidence. `--rerun-tasks` is the only accepted Gradle freshness proof. `clean`,
`cleanTest`, qualified clean tasks, exclusions, properties, option operands, and every other token
do not count. An active v2 card that used a clean task as freshness evidence must add the exact
`--rerun-tasks` member; historical cards are not rewritten.
Pre phase also permits an absent `exclusive_writes` entry only when it is a safe, exact,
repository-relative file literal. Post phase requires every write path and every Java declaration
to exist. This deliberately defers an indistinguishable new-file typo to the mandatory post check;
globs, metacharacters, directories, absolute paths, and escapes never receive that exception.
An absent safe exact `forbidden_paths` literal has the opposite meaning: it proves the fenced path
is absent and is clean in both phases. Existing forbidden boundaries are also valid, provided they
do not overlap `exclusive_writes`. When frozen migration text repeats a higher version paired to an
exact forbidden migration path, that repetition is fencing evidence rather than stale intent.

Every `validation` entry is one mapping with exactly `cwd` and `argv`. `cwd` is `.` or an existing,
normalized repository-relative directory with no symlink component; `argv` is a non-empty sequence
of non-empty strings.
There is no shell layer, grouping map, or legacy string form: pipelines, redirects, environment
assignments, and compound commands must be expressed as separate direct validation entries or moved
to a repository script with a shebang. The rejected shell basenames are exactly `sh`, `bash`,
`dash`, `zsh`, `ksh`, `mksh`, `csh`, `tcsh`, `fish`, `ash`, `pwsh`, `powershell`, `cmd`, and
`cmd.exe`. Literal shell-looking arguments remain ordinary data; unlisted wrappers are direct
processes but never lend nested executable evidence.
When `argv[0]` contains `/` and is not absolute, it resolves from `cwd`, must remain inside the
repository, and must name an executable regular file. Direct text scripts must start with a
byte-zero `#!` shebang; executable binary files are accepted. Bare PATH names remain intentionally
unchecked and absolute executable behaviour is unchanged. A command-root failure invalidates that
entry once, before dependent evidence checks run.

Nested Java selectors normalize `$` to `.`, but only an exact member-type chain found in the
containing source after comments and strings are removed establishes existence. Capitalization is
never evidence. An exact owned `Create` declaration may establish the pre-phase expectation; post
phase requires the complete declared chain in source. Nested declarations use the containing outer
source path and the full nested FQCN.

This is **task-card validation contract v2**. v1 cards are invalid under v2 because their validation
items are strings; v2 cards are invalid under v1 because the old validator flattens mappings rather
than decoding processes. Migrate each scalar by moving a leading working-directory change into
`cwd` and writing the executable plus arguments as `argv`; split multiple processes into separate
entries or move their orchestration into a directly invoked repository script. Revalidate the
unchanged card in both phases after migration.

For Gradle/JUnit evidence, use the single-use nonce-receipt protocol in
[references/junit-evidence.md](references/junit-evidence.md): `start_junit_run.py` immediately
before the test task, `verify_junit.py` after, with the canonical invocation in
`references/task-card.md`. The reference also states what the evidence does and does not detect,
and its trust boundary.

A read-only Codex `test-judge` never runs a write-producing gate against the source referent; the
standalone-copy nested-sandbox protocol is in
[references/codex-gate-sandbox.md](references/codex-gate-sandbox.md).

## Spec templates

[references/specs.md](references/specs.md) holds the product-spec and feature-spec skeletons,
including the acceptance-criteria form that turns into test names without translation.

## What this does not decide

Who runs, on which model, with which tools — that is `agent-personas`. Where documents live and how
a repository routes an agent to them — that is `progressive-disclosure` and `project-onboarding`.
This skill owns only the sequence between stages and what must be true to leave one.

Committing, pushing, opening a pull request, and merging are founder decisions. The methodology
prepares them; it never takes them.
