# S-7 spec: a test-module map picks task gates and reruns only failed modules

**Users and problem.** Chiefs on v7.2 repositories. Hand-picked gates missed shared
test support (`measurements.md`, 2026-10-13). A full gate failing under load reruns whole (up
to 99 minutes). S-6's per-test rerun failed review: runner output cannot show which tests ran.

**What changes for the user.** A committed map of test modules (paths, needs, a command
each) picks a task's gate. A full gate runs module by module; on the same tree a rerun
skips passed modules, and a failed module reruns only with evidence the machine was busy.

**Acceptance criteria.**

- AC1 WHEN `docs/goals/modules.json` exists THE SYSTEM SHALL fail `lint` on an unknown `needs`, a
  cycle, or a module without paths or command, and warn about unmapped tracked files.
- AC2 WHEN a task has no `gate:` line and the map exists THE SYSTEM SHALL show in `next` and the
  approval page the modules its `writes` overlap plus dependents, or all on a `shared` or unowned
  path.
- AC3 WHEN `gate.py check` or `receipt` runs with `--modules` THE SYSTEM SHALL run each module as
  its own process, record load before, peak load and CPU count, and pass only when
  all pass.
- AC4 WHEN every module has a PASS receipt on HEAD's tree and coverage holds THE SYSTEM SHALL
  accept them as the `full_gate` receipt for done row 7.
- AC5 WHEN `receipt --modules` reruns on one tree THE SYSTEM SHALL keep passed modules, run unrun
  ones, and rerun a failed one once only when load before it reached the CPU count or another
  `gate.py` run overlapped it; otherwise refuse.
- AC6 WHEN a module passed on a load rerun THE SYSTEM SHALL list it and its evidence in the
  packet.
- AC7 WHEN `gate.py coverage` runs THE SYSTEM SHALL pass only when the modules' executed tests sum
  to the `full_gate` receipt's on one tree, for that map's digest.
- AC8 WHEN the skill is read THE SYSTEM SHALL tell the planner to draft the map with the plan.
- AC9 WHEN `e2e_run.sh` runs THE SYSTEM SHALL prove AC2, AC3 and AC5 in both harnesses; this
  repository SHALL ship a map whose coverage holds.

**Non-goals.** Per-test reruns; cross-tree reuse; an inferred map; parallel modules.

**Constraints.** Standard-library Python 3.10; no downstream names; D29, D30; without a map,
v7.2 is unchanged.
