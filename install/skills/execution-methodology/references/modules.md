# Module map

Where no `docs/goals/modules.json` exists, draft it at planning from the build files and imports:

- one module per build module or test directory;
- `needs` from what each module's tests execute or import;
- a `count: "none"` module for the non-test checks, whose command is the replaced full-gate command
  with its tests switched off (for example `./gradlew check -x test`, or this repository's
  `verify.sh --no-suites`), so a check added to the full gate later still runs;
- `replaces` set to today's full-gate command.

Commit it with the plan. Then, on that clean commit, compare once:

- `gate.py receipt --goal <id> --name full_gate --cmd "<replaces>"`;
- `gate.py receipt --goal <id> --modules all`;
- `gate.py coverage --goal <id>`.

Coverage compares counts per suite (unittest, pytest, playwright, vitest, junit); take the
full-gate receipt with the modules' `--junit` glob, or its junit suite reads 0. Record coverage's
line in Decisions. For `full_gate: modules`, add a Decisions line naming the module that runs each
non-test check of the replaced command. Prefer derived gates to `gate:` lines.

An approved map is protected unless a task's approved `writes:` names
`docs/goals/modules.json` exactly; then the goal may grow it, never
shrink it. `protected:` locks it.
