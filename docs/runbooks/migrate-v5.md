# Migrating a v5.1 project

A project is unmigrated while it holds `docs/agents/execution/runtime.json`; the skill does nothing
there. Migrate by hand, one project at a time, at a milestone boundary, in one commit:

1. Map the overlay (`docs/agents/execution/overlay.md`, persona overlays): each rule that still
   matters becomes a line in `AGENTS.md` or a constraint in the first plan; its commands become the
   plan's `gate`, `full_gate` and `e2e`.
2. Remove `docs/agents/execution/**`, including `runtime.json`.
3. Remove rendered personas (files carrying the renderer's `GENERATED` marker, overlays under
   `docs/agents/personas/`) and the project's registrations of v5 hook scripts.
4. Add `/.runs/` to `.gitignore`.
5. Write `docs/goals/<id>/plan.md`; `goal.py lint` must pass.
6. Commit, then run `git-hooks.sh` in the clone (hooks are local, not committed).

Rollback: `git revert` the migration commit, then `git-hooks.sh --uninstall`.

Once no project holds a `runtime.json`, `install/install.sh --retire-v5` removes the global v5.1
and v6 files.
