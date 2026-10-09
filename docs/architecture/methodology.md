---
summary: How a goal runs under methodology v7.1 and why: three bounded documents per goal (`spec.md`, `design.md` when `touches` names anything but `none`, `plan.md` with `reads:` per task) frozen at the approval tag; pages disclosed in layers (frontmatter, the generated index, anchors, generated pointer files, the stale warning); builder, reviewer and scout roles with declared models; the founder's own session as the chief, with cost recorded, never enforced; gate receipts, the eight-row done check, one read-only review by the other vendor per stage, one guard, two founder touchpoints. Also what v6 was and the measurements that retired it, the accepted risks with the amended stop rule, the v6 lessons that still hold, and the rollback.
read-when: Changing anything under `install/`, or asking how a goal runs, what v7 replaced, its risks or its rollback
covers: [install/**]
last-verified: 2026-10-09
---

# Methodology v7.1

How a goal runs, and why. The rules are in the
[skill](../../install/skills/execution-methodology/SKILL.md); the decisions are
[D29](../decisions/decisions.md#d29--simplified-goal-execution-methodology-v7-one-look-per-artifact-a-mechanical-gate-two-touchpoints)
and [D30](../decisions/decisions.md#d30--methodology-v71-context-roles-and-planning-documents-s-2).

## Shape

- **Three documents.** A goal is `docs/goals/<id>/`: `spec.md` (at most 400 words: users and
  problem, what changes for the user, `ACn WHEN … THE SYSTEM SHALL …` criteria, non-goals,
  constraints; or the two-line form when nothing changes for the user), `design.md` whenever
  `touches:` names anything but `none`, and `plan.md`: frontmatter (gates, milestones, `touches`,
  `protected`), Outcome, tasks with `writes`, `reads:` and `tests-may-change`, Decisions, Parked.
  The tag `goal/<id>/approved` freezes the plan's frontmatter, Outcome and task headers, the spec
  whole, and the design's Interfaces and Data touched. `goal.py lint` fails a task with `writes` and
  no `reads:`, a spec out of shape and a criterion named in no task. A goal approved without a spec
  is a v7 goal and lints as one. Templates: [planning.md](../../install/skills/execution-methodology/references/planning.md).
- **Disclosure in layers.** Every page under `docs/` but the index and `docs/goals/**` starts with
  `summary` (at most 120 words), `read-when`, `covers` and `last-verified`. `docs.py index`
  generates the table in `docs/README.md`; `docs.py reads <Tn>` turns each `reads:` entry into a
  line range by its heading anchor; `docs.py pointers` generates, from `covers`,
  `.claude/rules/<page-slug>.md` for Claude Code and a marked block in the nearest `AGENTS.md` for
  Codex, never over an unmarked file; `docs.py lint` checks the frontmatter, the index and the
  pointers in the gate. `docs.py stale`
  lists pages whose covered paths were committed after `last-verified`: a warning, never a failure.
  Packets carry identifiers, never pasted text.
- **Roles** ([roles.md](../../install/skills/execution-methodology/references/roles.md)): the
  builder on the frontier tier at high effort, in its own worktree; the scout on the cheap tier,
  read-only; the reviewer, the other vendor's strongest reasoning model, read-only. Their agent files
  ship to both harnesses, marked: `agents/*.md` to `~/.claude/agents/`, `agents/*.toml` to
  `$CODEX_HOME/agents/` ([personas.md](personas.md) holds the evidence). The caps are structural:
  one builder per task, one review round per stage, each agent's `maxTurns`, at most five planning
  questions.
- **The session is the chief.** The founder's own open session runs the goal on the founder's word,
  from `goal.py resume`; no launcher starts it, and no loop or Stop hook restarts it. Pushes pass the
  guard's pre-push hook and the harness's own permission prompts. `goal.py cost` sums the input and
  output tokens in each harness's local transcripts since the approval tag; the packet records it and
  nothing enforces it.
- **Gate receipts.** `gate.py` records PASS or FAIL against the tree that ran.
- **Eight-row done.** `goal.py done`: tasks ticked or parked; clean tree; every commit names a task
  or is plan-only; each task commit inside its `writes` as read at its parent, never in
  `protected` (the spec and the design's frozen sections included); no test changed outside
  `tests-may-change`; frozen view unchanged; `full_gate` and `e2e` receipts on HEAD's tree; no open
  blocking review finding, each closed by a named test or by removal. It reads no verdict, round or
  grant.
- **One review by the other vendor** per stage, read-only and adversarial, with `agents/reviewer.md`:
  design whenever `design.md` exists, plan before the approval tag, merge on the milestone diff (with
  the security checklist when `touches` names data, auth or external). One round each, no grant.
  Each closed blocking finding carries `cause: context|logic|spec`, which `goal.py packet` counts;
  `goal.py packet --approval` renders the spec, the design's Structure and Interfaces, the task table
  and the open questions as `.runs/<id>/approval.html` for the approval touchpoint.
- **One guard.** `guard.py`, installed per clone by `git-hooks.sh`: home paths, emails, private
  names and secrets at commit; secrets, files over 10 MB and direct pushes to the default branch at
  push.
- **Two founder touchpoints** per milestone: approval and merge. Reversible choices in scope are
  defaulted and logged; scope, data, auth, cost, secrets and external actions park.
- **One instruction source** for both harnesses, at most 1,350 words always loaded; the references
  and agent files load on demand.
- **The amended stop rule.** D29's stop rule stands with D30's one amendment: goal S-2's mechanism
  entered `install/` during the pilot, and nothing else does (Accepted risks). D30 is judged by the
  `cause:` tags, founder decisions per milestone, review catches by stage and the recorded cost.

## What it replaced

v6 (tag `methodology/v6-base`) had review rounds with grants, a driver and session hooks, a persona
generator, route and GitHub checkers, graph context and two 3,785-line guards. Measured 2026-10-09
across this repository and six product repositories: this repository's diff reviews
found 20 real defects in round one and 2 after; 150 sampled product findings split 64, 9 and 8
across rounds one, two and three-plus; the guards had no real catch in seven repositories; founder
decisions ran 10–13 per milestone against a contract of 2; `install/` carried 5.7 lines of process
policing per line of done-check. See [measurements.md](../product/measurements.md).

## Accepted risks

- **One round can miss what a second would catch.** Real late catches exist (a write-skew
  defect at round three, a fail-open gate found by a whole-diff pass). The merge review reads the
  whole milestone diff, and `e2e` on real services is mandatory: it caught errors every review missed.
- **The evidence is observational**; quota, availability or hosting may explain part of it.
- **The cross-vendor case rests on n=1.** The pilot's sampled follow-up reviews make the comparison.
- **Stop rule.** Over four weeks on the pilot repository, any one reverts: a blocking escape in two
  milestones; merges per week below the recomputed baseline without a logged external cause;
  founder decisions above four per milestone twice; more than one default in five reversed at
  merge. No new mechanism enters `install/` during the pilot except goal S-2
  ([D30](../decisions/decisions.md#d30--methodology-v71-context-roles-and-planning-documents-s-2)).

Six v6 lessons hold:

- A check this repository ships runs against this repository in `verify.sh`, or is not claimed.
- A printed failure is also a failing exit; the tested tree is rechecked after the run.
- Resume from the branch, its `goal/<id>/` tags and `.runs/<id>/progress.md`, not from main.
- Report each tool's unit separately; a ratio of different units is invented.
- A helper growing machinery while delivery waits is the failure, not the fix.
- Count what actually stopped a run before adding an approval.

## Rollback

```bash
(cd install && ./install.sh --uninstall)                   # on the v7.1 tree
git rm -r -q install && git checkout methodology/v6-base -- install && (cd install && ./install.sh)
```

`git rm` first: a plain checkout overlays the older tree on v7.1 and keeps v7.1-only files, which
the older installer would copy. To return to v7 rather than v6, check out `goal/S-1/M2` in place of
`methodology/v6-base`.

A migrated project reverts its migration commit ([migrate-v5.md](../runbooks/migrate-v5.md)).
