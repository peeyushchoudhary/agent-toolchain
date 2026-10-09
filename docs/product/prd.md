---
summary: The methodology as a product. Its users are the founder, who approves a goal and merges its milestones, and the chief session, which carries an approved goal to merged milestones in either Claude Code or Codex. Its jobs: plan a goal in bounded documents, deliver it task by task with isolated builders, decide done mechanically, keep private facts and secrets out of commits, and load only the knowledge a task needs. The principles are those D29 fixes (one look per artifact, a mechanical gate, two founder touchpoints) with D30's documents, pointers and roles. The surface is what `install/` ships: one skill with its scripts, references and agent files, a global instruction file and the installer. Non-goals close the page.
read-when: Deciding whether a change belongs in the methodology, or what `install/` must keep doing
covers: []
last-verified: 2026-10-09
---

# Product: the execution methodology

A methodology for running coding-agent work as goals: a goal is planned in a few bounded documents,
approved once, built task by task and merged by milestone, with done decided by a script rather than
by a model's judgement. It ships from [`install/`](../../install/README.md) into both harnesses'
homes. How it runs and why is [methodology.md](../architecture/methodology.md); the numbers behind
it are in [measurements.md](measurements.md).

## Users

- **The founder.** One person who owns the repositories, approves each goal with the tag
  `goal/<id>/approved` and merges each milestone. Their time is the scarcest input, so the product
  asks for it twice per milestone and otherwise defaults reversible choices and logs them.
- **The chief session.** The session, in Claude Code or Codex, which plans a goal with the
  founder, dispatches builders, runs the gate, commits each task and asks for the review. It is the
  only session that commits. [D30](../decisions/decisions.md#d30) makes it the founder's own
  console session: no launcher, loop or Stop hook.

Builders, the scout and the reviewer are roles the chief dispatches, not users: each is an agent
file with a declared model and effort.

## Jobs

1. **Plan a goal.** Write `spec.md` (what changes for the user, acceptance criteria as observable
   behaviour), `design.md` when the goal touches an interface, data, auth, an external system or
   the UI, and `plan.md`, whose tasks name what they may write and what the builder reads.
2. **Get one approval.** One read-only review by the other vendor at design and at plan, then the
   founder's approval tag, which freezes the spec, the design's interfaces and the plan's shape.
3. **Deliver task by task.** One builder per task in its own worktree; the chief applies its diff,
   runs the gate and commits `[Tn]`. A task that stays red is parked, not argued with.
4. **Decide done mechanically.** `goal.py done` checks eight rows against git and tree-bound gate
   receipts; it reads no verdict, round or grant.
5. **Merge once per milestone.** One review of the whole milestone diff by the other vendor;
   blocking findings close by a named test or by removing the work; the founder merges.
6. **Keep the repository public-safe.** One guard at commit and push blocks home paths, private
   names, emails, secrets and oversized files.
7. **Load only what a task needs.** Exhaustive pages carry a summary, `read-when`, `covers` and
   `last-verified`; the index and pointer files are generated; `reads:` entries resolve to line
   ranges, so a builder opens a section, not a library.

## Principles

[D29](../decisions/decisions.md#d29) fixes three:

- **One look per artifact.** Each document and each milestone diff gets one adversarial review by
  the other vendor, read-only, one round, no grant.
- **A mechanical gate.** Done is what `goal.py done` and the gate receipts say; a printed failure is
  a failing exit, and a check this repository ships runs against this repository.
- **Two touchpoints.** The founder is asked at approval and at merge; scope, data, auth, cost,
  secrets and external actions park for the founder, everything else in scope is defaulted and
  logged.

[D30](../decisions/decisions.md#d30) adds: bounded planning documents that cite exhaustive pages by
section; pointer files generated from `covers`, never hand-written; roles that declare model and
effort; cost recorded, never enforced. One instruction source serves both harnesses, at most 1,350
words always loaded.

## Surface

What `install/` ships is the product; [install/README.md](../../install/README.md) says what
installs where. Its parts:

- `global.md`, installed as each harness's global instruction file.
- The `execution-methodology` skill: `SKILL.md`; `references/` (planning, roles, design, the
  security checklist); `agents/` (builder, reviewer, scout); `scripts/`, chiefly `goal.py` (plan
  lint, status, next, resume, packet, done), `gate.py` (receipts), `docs.py` (page lint, index,
  `reads:` resolution), and `guard.py` with `git-hooks.sh` (the guard).
- `install.sh` (install, dry run, uninstall, retiring v5.1 and v6 leftovers) and `verify.sh`, the
  repository gate.

## Non-goals

- A hosted service, CI, a runtime or a build artifact.
- Agent memory, a graph or a wiki of lessons.
- A model-judged done, a second reviewer or a second review round.
- A dollar budget that stops a goal.
- Hand-written pointer files, or one harness's settings carrying a rule the other must follow.
