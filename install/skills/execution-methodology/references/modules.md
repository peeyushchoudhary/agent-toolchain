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

Record the line coverage prints in a Decisions line. To compose the full gate from the map, set
`full_gate: modules` and add a Decisions line naming the module that runs each non-test check of
the replaced command. Prefer derived gates to `gate:` lines.
