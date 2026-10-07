# Documentation index

## The six areas

Each directory carries a `README.md` naming its purpose and authority level.

| Directory | Holds | Authority |
| --- | --- | --- |
| [agents/](agents/README.md) | the route: task, one guide, one command | Current |
| [architecture/](architecture/README.md) | how the system is built | Current |
| [product/](product/README.md) | intent, read through shipped behaviour | Current; measurements are dated |
| [decisions/](decisions/README.md) | accepted decision records | Current |
| [runbooks/](runbooks/README.md) | operational procedures | Current |
| [archive/](archive/README.md) | superseded material | **NOT authoritative** |

## Every document, one hop from here

Listed in full and not only through the six indexes above, deliberately: the validator warns
`too-deep` past two hops from an entry file, and an area directory spends one of them. Add a
document by adding its row here in the same commit.

| Area | Document | Status |
| --- | --- | --- |
| How work is sequenced, and what "done" means | [architecture/operating-model.md](architecture/operating-model.md) | Current |
| The four disclosure layers and the validator | [agents/progressive-disclosure.md](agents/progressive-disclosure.md) | Current |
| How the route works in this repository | [agents/disclosure.md](agents/disclosure.md) | Current, standard v1.2 |
| What earlier agents learned here, still applying | [agents/lessons.md](agents/lessons.md) | Current — curated; what stops applying is removed |
| Where files belong; migrating an existing repo | [architecture/repository-standard.md](architecture/repository-standard.md) | Current, v1.1 |
| Forge rules, the push guard, zero-cost posture | [runbooks/github.md](runbooks/github.md) | Current |
| The Codex side, and what it does not get | [runbooks/codex.md](runbooks/codex.md) | Current |
| Updating the private global instruction files for v6 | [runbooks/global-instructions.md](runbooks/global-instructions.md) | Current |
| The persona roster and its routing | [agents/agent-personas.md](agents/agent-personas.md) | Current |
| Every file the installer places, and why | [agents/what-gets-installed.md](agents/what-gets-installed.md) | Current |
| Decisions in force, each against its rejected alternative | [decisions/decisions.md](decisions/decisions.md) | Current — identifiers are stable |
| The numbers the decisions and the v6 design cite | [product/measurements.md](product/measurements.md) | **Dated** — re-derive when prices move |
| The weekly improvement record, newest first | [product/improvements-weekly.md](product/improvements-weekly.md) | Current — a record: entries accrete, never rewritten |
| Front-page diagram description and visual sources | [assets/readme/README.md](assets/readme/README.md) | Current |
| Lean goal execution (methodology v6) definition | [product/specs/F-3-lean-execution.md](product/specs/F-3-lean-execution.md) | Approved 2026-10-06; in implementation |
| Lean goal execution design | [architecture/lean-execution.md](architecture/lean-execution.md) | Approved 2026-10-06; in implementation |
| Lean goal execution plan | [product/plans/F-3-lean-execution.md](product/plans/F-3-lean-execution.md) | Approved 2026-10-06; in implementation |
| Review closure (F-4) | [product/specs/F-4-review-closure.md](product/specs/F-4-review-closure.md), [architecture/review-closure.md](architecture/review-closure.md), [product/plans/F-4-review-closure.md](product/plans/F-4-review-closure.md) | Draft 2026-10-08 |
| Folder routes and graph context (F-5) | [product/specs/F-5-graph-context.md](product/specs/F-5-graph-context.md), [architecture/graph-context.md](architecture/graph-context.md), [product/plans/F-5-graph-context.md](product/plans/F-5-graph-context.md) | Draft 2026-10-08 |

Installation lives in [../install/README.md](../install/README.md). The current state of the
repository is summarised once in [the front page](../README.md#current-state).

## What is published, and what is not

`install/skills/` is the authored source of the published skills; `install/hooks/` holds the session
hooks. Four skills are published: `execution-methodology`, `agent-personas`, `progressive-disclosure`
and `graph-navigation`. The list is enforced by `install/skills/.gitignore`, which ignores its own
directory and then re-includes those four by name, so adding another is a deliberate line in a file
rather than a side effect of a copy.

`execution-methodology` describes a process, not the work it was applied to, and names no project,
path or person, which is what makes it safe to publish. Its tools (`goal.py`, `gate.py`,
`review.py`, `run_goal.py`) carry no project fact: commands, paths and grants arrive from a
project's own plan.

`graphify` is deliberately not published. It is a third-party skill that installs itself on its own
schedule, so a copy here would only go stale, and redistributing it is not this repository's call.
Its absence from `install/skills/` is the recorded decision, not drift.

## Authority order

1. The tooling in `install/` — it is what actually runs.
2. These documents.
3. Any measurement older than the date its section states in `measurements.md`.

When a document and the tooling disagree, the tooling is right.
