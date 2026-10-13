---
summary: How a goal runs under methodology v7.3 and why: three bounded documents per goal (`spec.md`, `design.md` when `touches` names anything but `none`, `plan.md` with `reads:` per task) frozen at the approval tag; pages disclosed in layers (frontmatter, the generated index, anchors, generated pointer files, the stale warning); builder, reviewer and scout roles with declared models; the founder's own session as the chief, with cost recorded, never enforced; gate receipts, the eight-row done check, one read-only review by the other vendor per stage, one guard, two founder touchpoints. Also what v6 was and the measurements that retired it, the accepted risks, the ended stop rule, the v6 lessons that still hold, and the rollback.
read-when: Changing anything under `install/`, or asking how a goal runs, what v7 replaced, its risks or its rollback
covers: [install/**]
last-verified: 2026-10-13
---

# Methodology v7.3

How a goal runs, and why. The rules are in the
[skill](../../install/skills/execution-methodology/SKILL.md); the decisions are
[D29](../decisions/decisions.md#d29--simplified-goal-execution-methodology-v7-one-look-per-artifact-a-mechanical-gate-two-touchpoints),
[D30](../decisions/decisions.md#d30--methodology-v71-context-roles-and-planning-documents-s-2),
[D32](../decisions/decisions.md#d32--methodology-v72-each-tasks-gate-chosen-at-planning-builders-dispatched-by-dependency-s-6),
[D33](../decisions/decisions.md#d33--methodology-v73-a-test-module-map-picks-task-gates-composes-the-full-gate-and-retries-a-failed-module-once-s-7),
[D34](../decisions/decisions.md#d34--post-merge-cleanup-the-chief-records-its-worktrees-and-removes-what-originmain-holds-s-8)
and [D35](../decisions/decisions.md#d35--the-pilot-and-its-stop-rule-have-ended-s-9).

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
  one builder per task, at most four at once, one review round per stage, the builder's and the
  scout's `maxTurns`, at most five planning questions.
- **Gates sized at planning (v7.2, D32).** Each task names its `gate:`, at most 600 s alone, and the
  tasks it `needs:`; `goal.py next` lists the ready ones and the chief dispatches a builder per
  ready task, each in a fresh isolated worktree from the goal branch, which carries every committed
  dependency. Task checks run one at a time; the full gate runs every third task commit in the
  background, in a detached worktree, where it takes 600 s or less, else only at close. The chief
  records each builder's worktree and each sample's with `goal.py own` (D34). `gate.py` records
  every run in `.runs/<id>/checks.jsonl`.
- **Module map (v7.3, D33).** A repository may commit `docs/goals/modules.json`: each test module's
  paths, the modules it `needs` and one test command, the `shared` paths, the full-gate command it
  `replaces` and a `count: "none"` module running that command without its tests. The chief drafts
  it at planning and the founder approves it with the plan; it is protected after. A task without
  `gate:` runs the modules its writes reach (`gate.py check --modules`). With `full_gate: modules`
  the full gate is `receipt --modules all`; on the same tree it keeps passed modules, retries a
  failed one once and refuses a second failure. Load readings are diagnostics beside a retry.
- **The session is the chief.** The founder's own open session runs the goal on the founder's word,
  from `goal.py resume`; it loads the skill itself when a plan has an open milestone (D31 dropped the
  2026-08-22 user-invoked gate; the approval tag, placed by the founder or by the chief on the
  founder's explicit word, is the human gate). The chief is never a subagent:
  a Claude Code subagent has no Agent tool, so it could not dispatch builders or reviewers; in both
  harnesses the pre-push guard and the permission prompts answer to the root session; a subagent in
  the root checkout shares its index (the leak behind the builder's `isolation: worktree`) and one in
  its own worktree commits off the goal branch; and v6 measured a nested chief as spend without
  judgement. No launcher starts the session, and no loop or Stop hook restarts it (the installer
  registers none, and drops the one a v7.0 install wrote). Pushes pass the guard's pre-push hook and
  the harness's own permission prompts. `goal.py cost` sums the input and
  output tokens in each harness's local transcripts since the approval tag; the packet records it and
  nothing enforces it.
- **Gate receipts.** `gate.py` records PASS or FAIL against the tree that ran.
- **Eight-row done.** `goal.py done`: tasks ticked or parked; clean tree; every commit names a task
  or is plan-only; each task commit inside its `writes` as read at its parent, never in
  `protected` (the spec and the design's frozen sections included); no test changed outside
  `tests-may-change`; frozen view unchanged; `full_gate` and `e2e` receipts on HEAD's tree; no open
  blocking review finding, each closed by a named test or by removal. It reads no verdict, round or
  grant.
- **The close** ([close.md](../../install/skills/execution-methodology/references/close.md)): the
  `full_gate` and `e2e` receipts, the merge review, `goal.py done` printing DONE, then the chief
  pushes the branch and opens the PR. Once the founder says to merge, the chief runs `gh pr merge
  <n> --merge`, with `--delete-branch` only at the goal's last milestone; tags
  `goal/<id>/<milestone>` at the PR's head commit and pushes it with `goal/<id>/approved`; then
  runs `goal.py cleanup --goal <id> --apply`, which removes only the recorded worktrees, and their
  branches, whose work `origin/main` holds (D34).
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
- **The stop rule, ended.** During the pilot, D29's stop rule with D30's one amendment let only goal
  S-2's mechanism into `install/` (Accepted risks). The pilot and D29's stop rule ended with
  [D35](../decisions/decisions.md#d35--the-pilot-and-its-stop-rule-have-ended-s-9): a change to
  `install/` is an ordinary goal the founder approves.

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
- **Stop rule.** Until D35 ended it, any one of these reverted over four weeks on the pilot
  repository: a blocking escape in two milestones; merges per week below the recomputed baseline
  without a logged external cause; founder decisions above four per milestone twice; more than one
  default in five reversed at merge. No new mechanism was to enter `install/` during the pilot
  except goal S-2
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
(cd install && ./install.sh --uninstall)                   # on the current tree
git rm -r -q install && git checkout methodology/v6-base -- install && (cd install && ./install.sh)
```

`git rm` first: a plain checkout overlays the older tree on the current one and keeps the files
only the current tree has, which the older installer would copy. To return to v7 rather than v6,
check out `goal/S-1/M2` in place of `methodology/v6-base`; to return to v7.2, `goal/S-6/M1`.

A migrated project reverts its migration commit ([migrate-v5.md](../runbooks/migrate-v5.md)).
