# Module map

Draft missing `docs/goals/modules.json` at planning from build files and imports:

- one module per build module/test directory;
- `needs` from what each module's tests execute or import;
- a `count: "none"` module for the non-test checks, running the replaced full-gate command
  with tests switched off (for example `./gradlew check -x test`, or this repository's
  `verify.sh --no-suites`), preserving future full-gate checks;
- `replaces` set to today's full-gate command.

Commit it with the plan. On that clean commit, compare once:

- `gate.py receipt --goal <id> --name full_gate --cmd "<replaces>"`;
- `gate.py receipt --goal <id> --modules all`;
- `gate.py coverage --goal <id>`.

Coverage compares counts per suite (unittest, pytest, playwright, vitest, junit); take the
full-gate receipt with the modules' `--junit` glob, or junit reads 0. Record coverage's
line in Decisions. For `full_gate: modules`, add a Decisions line naming the module that runs each
non-test check of the replaced command. Prefer derived gates to `gate:` lines.

An approved map is protected unless a task's approved `writes:` names `docs/goals/modules.json`
exactly; then grow, never shrink. `protected:` locks it. Sole substitution exception:
approval-frozen [test migrations](test-migrations.md).
