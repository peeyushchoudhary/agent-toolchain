# S-7 spec: a test-module map picks task gates and retries only failed modules

**Users and problem.** Chiefs on v7.2 repositories. Hand-picked gates missed shared test support
(`measurements.md`, 2026-10-13). A full gate that fails reruns whole (up to 99 minutes). S-6's
per-test rerun failed review: runner output cannot show which tests ran.

**What changes for the user.** A committed map of test modules (paths, needs, a command each)
picks a task's gate. A full gate can be the map's modules. On the same tree a rerun keeps passed
modules and retries a failed one once.

**Acceptance criteria.**

- AC1 WHEN `docs/goals/modules.json` exists THE SYSTEM SHALL fail `lint` on an unknown `needs`, a
  cycle, a module without paths or command, or two modules sharing a command, and warn about
  unmapped tracked files.
- AC2 WHEN a task has no `gate:` line and the map exists THE SYSTEM SHALL show in `next` and the
  approval page the modules its `writes` reach plus dependents, or all when a write is shared or
  not wholly inside one module.
- AC3 WHEN `gate.py check` or `receipt` runs with `--modules` THE SYSTEM SHALL run each module as
  its own process, record load before, peak load and CPU count, and pass only when all pass.
- AC4 WHEN the plan's `full_gate` is `modules` THE SYSTEM SHALL require the map to name the
  command it replaces and a non-test module, show both on the approval page, protect the map,
  and accept PASS module receipts for every module on HEAD's tree for done row 7.
- AC5 WHEN `receipt --modules` reruns on one tree THE SYSTEM SHALL keep passed modules, run unrun
  ones, retry a failed one once, and refuse a second failure.
- AC6 WHEN a module was retried THE SYSTEM SHALL list both runs and their load readings in the
  packet.
- AC7 WHEN `gate.py coverage` runs THE SYSTEM SHALL report whether the modules' executed tests sum
  to a full-gate command's on one tree.
- AC8 WHEN the skill is read THE SYSTEM SHALL tell the planner to draft the map with the plan.
- AC9 WHEN `e2e_run.sh` runs THE SYSTEM SHALL prove AC2, AC3 and AC5 in both harnesses; this
  repository SHALL ship a map.

**Non-goals.** Per-test reruns; cross-tree reuse; an inferred map; parallel modules; load-gated
retries.

**Constraints.** Standard-library Python 3.10; no downstream names; D29, D30; without a map,
v7.2 is unchanged.
