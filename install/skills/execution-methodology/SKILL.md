---
name: execution-methodology
description: Use when starting, planning, or executing substantive implementation work — writing a product or feature spec, taking a design to a plan, running an approved plan task by task, or deciding what must be true before work can be called done. Also use when a repository's rendered execution guide is missing or stale.
---

# The execution methodology

One pipeline from product intent to a merged milestone, followed identically by Claude Code and
Codex. The rules live in [methodology.md](methodology.md) — read that; this file is how to run it.

## The shape, in one screen

```
product spec → feature spec → design →│GATE│→ plan →│GATE│→ task cards
                                                              ↓
                     per card, unattended: context → implement → review → fix ×N
                          → full-diff review → validate → commit + distillation
                                                              ↓
                                   milestone: gate → sealed receipt → acceptance →│GATE│→ PR
```

Three human gates: the design, the plan, and the merge. Between the plan gate and the merge gate the
loop runs unattended.

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

**Design and plan** — `architect` for the design, reviewed by whichever domain specialists the
repository defines; `planner` for the plan, with `contract-architect` on anything crossing a durable
boundary. Freeze interfaces in the plan *including payloads*. A plan that freezes route names but
not request and response shapes hands the implementer an invention it will make silently.

**Executing** — hand the approved plan to `chief-of-staff`. It generates task cards, dispatches,
routes reviews, runs fix loops, keeps the ledger, and stops only on a blocker, a genuine ambiguity,
or the fix cap.

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

## The task card

The card is the implementer's entire world — it does not read the plan, and it reads nothing the
card does not name. The schema and a worked example are in
[references/task-card.md](references/task-card.md).

**Validate the card before dispatching it:**

```bash
validate_card.py CARD_PATH --repo REPO_ROOT            # exit 1 on any ERROR
validate_card.py CARD_PATH --repo REPO_ROOT --strict   # exit 1 on warnings too
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

## Spec templates

[references/specs.md](references/specs.md) holds the product-spec and feature-spec skeletons,
including the acceptance-criteria form that turns into test names without translation.

## What this does not decide

Who runs, on which model, with which tools — that is `agent-personas`. Where documents live and how
a repository routes an agent to them — that is `progressive-disclosure` and `project-onboarding`.
This skill owns only the sequence between stages and what must be true to leave one.

Committing, pushing, opening a pull request, and merging are founder decisions. The methodology
prepares them; it never takes them.
