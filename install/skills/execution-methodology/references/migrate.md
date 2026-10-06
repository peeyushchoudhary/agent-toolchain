# Migrating a project from v5.1 to v6

Migration is manual and done one project at a time, when the founder asks for it. It is not
automated because each v5.1 project carries its own overlay of project-specific rules, and mapping
those into the next goal is a judgement, not a copy.

## Why v6 refuses to run first

v5.1 bound each project to an approved runtime bundle through a pin file and rendered its rules
into the project. v6 has no pin: the installed skill is the methodology, and a project records the
version it follows in one line of its `AGENTS.md`. The two keep different state (task cards,
ledgers and lane records against plan checkboxes, receipts and tags), so running v6 over a v5.1
project would make neither set of checks true.

**Detection.** A project is unmigrated while it contains `docs/agents/execution/runtime.json`.
While that file exists, the skill's first step stops, `goal.py` exits with the migrate-first notice,
the Stop hook stays inactive, and the session hook prints the same notice. v6 runs no part of the
v5.1 lifecycle.

## Steps

1. **Finish or stop the in-flight milestone.** Complete it under v5.1 if it is close; otherwise
   stop it at a clean commit and note what remains. A milestone half-run under two methodologies
   has no trustworthy record.
2. **Map the overlay's invariants.** Read `docs/agents/execution/overlay.md` and any persona
   overlays under `docs/agents/personas/`. Each project-specific rule that still matters becomes a
   criterion or constraint in the next goal's spec or design, or a line in the project's
   `AGENTS.md` if it is a standing repository rule. Commands the overlay named (context scripts,
   area gates) become the next plan's `gate`, `full_gate` and `e2e`.
3. **Remove the runtime pin and overlays.** Delete:
   - `docs/agents/execution/runtime.json`, the pin;
   - `docs/agents/execution/methodology.md`, the rendered v5.1 rules;
   - `docs/agents/execution/overlay.md`, once step 2 has mapped it;
   - persona overlays under `docs/agents/personas/`, once mapped;
   - v5.1 run records the project no longer needs (task cards, ledgers, resume pointers), unless
     the founder wants them kept for reference. Git keeps them either way.

   Leave the approved v5.1 bundle that the pin pointed to untouched; it is the founder's to retire.
4. **Add run state and hooks.**
   - Add `/.runs/` to the project's `.gitignore`; run state is local evidence, not a record.
   - Write the project's Codex hook configuration, registering `goal.py stop-hook` as the Stop hook
     and `goal-session.sh` as the session-start hook. Claude Code gets both hooks from the global
     install, and the driver registers them for headless sessions through its settings file.
5. **Update the route.** In `docs/agents/README.md` (or the project's route index), remove rows
   that pointed to the rendered methodology, the overlay and the runtime status command, and add
   a row for `docs/product/goals/`. Record the methodology version in one line of `AGENTS.md`.
6. **Write the next goal in the v6 layout.** Create `docs/product/goals/<goal-id>/` with `spec.md`,
   `design.md` and `plan.md` as described in [planning.md](planning.md). Existing v5.1 specs and plans stay
   where they are as history; the new goal does not inherit their state.

## Verify

- `docs/agents/execution/runtime.json` no longer exists.
- `python3 <skill>/scripts/goal.py lint --plan docs/product/goals/<goal-id>/plan.md` exits 0.
- `python3 <skill>/scripts/goal.py status --plan docs/product/goals/<goal-id>/plan.md` reports the
  goal instead of the migrate-first notice.
- The project's route check, if it has one, passes, and no route row points to a deleted file.
- `git status` shows only the intended deletions and additions; commit them as one migration
  commit.

## Global v5.1 files

Installing v6 does not remove the v5.1 skills, scripts and personas from the global harness
directories, because a project that is not yet migrated may still need them. After every project
is migrated, the founder runs:

```
install/install.sh --retire-v5
```

It deletes only files matching the known v5.1 set and reports anything else it finds, so an
unexpected file is never removed silently. Nothing else removes global v5.1 files.
