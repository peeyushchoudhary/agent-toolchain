# Agent toolchain

The shared standard that every project I work on is held to, and the scripts that enforce it. It is
harness-neutral by construction: the same rules reach Claude Code through skills and Codex through
generated in-repo markdown, because Codex has no Skill tool and prose that only one harness reads is
prose that drifts.

**This repository contains nothing about the projects it serves.** No project names, no paths, no
excerpts, no adoption registry. That is a hard rule and not a stylistic one — the projects are
private and hold health, financial, and personal data. Every example here is invented. A test
asserts it, and the assertion is part of the gate rather than a convention.

The corollary is architectural: because there can be no central list of projects, **every repository
declares its own state**, and every check is evaluated against the one repository it is invoked on.

## What is here

| Skill | What it settles |
| --- | --- |
| `progressive-disclosure` | The route standard: how a repository tells an agent what to read, in what order, and how much. Ships the validator, the git hooks, and the push guard. |
| `execution-methodology` | The pipeline from product spec to merged milestone — its artifacts, its three human gates, the task card, the ledger contract. Rendered into each repository so both harnesses read the same rules. |
| `agent-personas` | The thirteen harness-neutral roles, with model and effort already chosen, generated into `~/.claude/agents/` and `~/.codex/agents/`. |
| `agent-persona-factory` | Deriving project-specific specialists from a repository's own guardrails, architecture, and PRD. |
| `graph-navigation` | Navigating an existing knowledge graph without falling back to prose queries. |
| `project-onboarding` | Bringing a new repository under all of the above, in order, proposing before writing. |

## The two ideas it is built on

**A builder never approves its own work.** There is no second reviewer and no hosted CI, so
independent verification has to be manufactured rather than assumed. Judging roles cannot edit — by
tool restriction, not instruction — and their verdict is a finding to triage, never an
authorization. Deterministic gates are the only gates.

**Local gates are the only gates.** GitHub is storage. Nothing deploys from it, nothing runs on it,
and it is kept at zero cost, so the rules GitHub would charge for — secret scanning, protected
branches — are enforced by `pre-push` instead.

## Installing

```bash
python3 progressive-disclosure/scripts/install_hooks.py <repo>   # hooks, Codex mirror, session check
python3 progressive-disclosure/scripts/check_toolchain.py        # drift between the two harnesses
python3 agent-personas/scripts/sync_personas.py                  # regenerate the persona pool
python3 execution-methodology/scripts/sync_methodology.py --repo <repo>
```

Adoption is staggered and never automatic. A repository that has not adopted the execution
methodology says so at every session start until it either adopts it or records a dated deferral
with a reason. Nothing here will render into a repository on its own.

## Changing it

The scripts have tests; run them before and after, and report real output. Each skill's `SKILL.md`
is its own entry point and outranks this page. A rule that cost a gate run and a rule that was
assumed are not worth the same — `execution-methodology/methodology.md` keeps them separated
deliberately, and anything new should say which it is.
