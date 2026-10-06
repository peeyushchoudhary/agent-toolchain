---
name: execution-methodology
description: Drive an approved goal (spec, design and plan) to completion — milestone by milestone, with executed checks deciding "done", cross-vendor review at the high-yield points, and the founder touched only at goal approval and merge.
disable-model-invocation: true
---

# Drive an approved goal

**First step.** If the project contains `docs/agents/execution/runtime.json`, it still follows the
previous methodology. Stop, tell the founder it must be migrated first, and point to
[references/migrate.md](references/migrate.md). Running two lifecycles in one project would leave
neither one's checks true.

Then read [methodology.md](methodology.md), which every role shares, and exactly one reference for
the work in hand. Loading only what the step needs keeps the rules short enough to follow.

| Work in hand | Reference |
| --- | --- |
| Writing or revising a goal's spec, design and plan; sizing milestones | [references/planning.md](references/planning.md) |
| Running an approved goal: start, driver, per-task loop, milestone close | [references/run.md](references/run.md) |
| Reviewing, or preparing a review packet; acceptance | [references/review.md](references/review.md) |
| A decision the plan does not settle; advisor or council | [references/escalation.md](references/escalation.md) |
| Moving a project off the previous methodology | [references/migrate.md](references/migrate.md) |

Builders do not load this skill. They work from the dispatch packet the chief sends, which names
the paths they need.

The founder explainer is filled from
[references/explainer-template.html](references/explainer-template.html); it is a template, not
rules.

Tools live in `scripts/`: `goal.py` and `gate.py` compute state and run gates; `review.py` runs
read-only judges; `run_goal.py` drives multi-session runs. Each prints its usage with `--help`. For
Gradle, `--rerun-tasks` is the only freshness proof `gate.py` accepts, because a cached task reports
success without executing anything.
