# Methodology v7

How a goal runs, and why. The rules are in the
[skill](../../install/skills/execution-methodology/SKILL.md); the decision is
[D29](../decisions/decisions.md#d29--simplified-goal-execution-methodology-v7-one-look-per-artifact-a-mechanical-gate-two-touchpoints).

## Shape

- **One plan.** A goal is `docs/goals/<id>/plan.md`: frontmatter (gates, milestones, `touches`,
  `protected`), Outcome, tasks with `writes`, Decisions, Parked. The tag `goal/<id>/approved`
  freezes frontmatter, Outcome and task headers.
- **Gate receipts.** `gate.py` records PASS or FAIL against the tree that ran.
- **Eight-row done.** `goal.py done`: tasks ticked or parked; clean tree; every commit names a task
  or is plan-only; each task commit inside its `writes` as read at its parent, never in
  `protected`; no test changed outside `tests-may-change`; frozen view unchanged; `full_gate` and
  `e2e` receipts on HEAD's tree; no open blocking review finding, each closed by a named test or by
  removal. It reads no verdict, round or grant.
- **One review by the other vendor**, read-only and adversarial, at design (only when `touches`
  names data, auth or external), plan and merge. One round each, no grant.
- **One guard.** `guard.py`, installed per clone by `git-hooks.sh`: home paths, emails, private
  names and secrets at commit; secrets, files over 10 MB and direct pushes to the default branch at
  push.
- **`run.sh`** restarts fresh sessions until done, parked or stalled; the session is the chief,
  under a scoped allowlist, a deny list and a network-off sandbox, never a blanket allow (`run.sh`
  applies this from S-1's T9).
- **Two founder touchpoints** per milestone: approval and merge. Reversible choices in scope are
  defaulted and logged; scope, data, auth, cost, secrets and external actions park.
- **One instruction source** for both harnesses, at most 1,350 words always loaded.

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
  merge. No new mechanism enters `install/` during the pilot.

Six v6 lessons hold:

- A check this repository ships runs against this repository in `verify.sh`, or is not claimed.
- A printed failure is also a failing exit; the tested tree is rechecked after the run.
- Resume from the branch, its `goal/<id>/` tags and `.runs/<id>/progress.md`, not from main.
- Report each tool's unit separately; a ratio of different units is invented.
- A helper growing machinery while delivery waits is the failure, not the fix.
- Count what actually stopped a run before adding an approval.

## Rollback

```bash
(cd install && ./install.sh --uninstall)                   # on the v7 tree
git checkout methodology/v6-base -- install && (cd install && ./install.sh)
```

A migrated project reverts its migration commit ([migrate-v5.md](../runbooks/migrate-v5.md)).
