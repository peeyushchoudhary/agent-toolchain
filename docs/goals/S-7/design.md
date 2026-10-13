# S-7 design: a test-module map that picks task gates and retries only failed modules

## Structure

One new committed file per repository, one new script module, and changes to two existing
commands and four skill pages.

- **The map.** `docs/goals/modules.json` lists the repository's test modules. Each module has the
  paths it owns, the modules it needs and one test command. It also lists the `shared` paths that
  every module reads. The chief drafts it from the build files at planning, and the founder
  approves it with the plan. After that it is protected like a `protected` path.
- **`scripts/modmap.py`.** Loads and checks the map, selects modules for a set of write globs, and
  lists tracked files no module covers. `glob_re`, `matches` and `overlap` move here from
  `goal.py`, which imports them back, because `gate.py` needs them too and `goal.py` already
  imports `gate.py`.
- **`gate.py`**
  - Runs modules: `--modules` on `check` and `receipt`.
  - Records load readings on every run, as diagnostics.
  - Keeps the modules that passed on the same tree.
  - Retries a failed module once.
  - A `coverage` command compares the modules' test counts with a single full-gate command's, as
    an aid when drafting the map.
- **`goal.py`**
  - Checks the map at `lint`.
  - Derives a task's gate when it has no `gate:` line.
  - Accepts module receipts for done row 7 when the plan's `full_gate` is `modules`.
  - Protects the approved map.
  - Lists retried modules in the PR packet.
- **Words.** `planning.md` drafts the map; `SKILL.md` step 5 runs the derived gate; `close.md`
  states the composed full gate and the retry; D33 records the decision.

## Interfaces

1. **Map file.** JSON, standard library only. Unknown keys are errors.

   ```
   {"replaces": "<the single full-gate command>"?,
    "modules": {"<name>": {"paths": ["<glob>", ...], "needs": ["<name>", ...],
                           "test": "<command>", "count": "none"?}},
    "shared": ["<glob>", ...]}
   ```

   - **`replaces`.** Names the single command the map stands in for. A plan may set
     `full_gate: modules` only when the map has a `replaces` and at least one `count: "none"`
     module (Interface 3).

   - **Names.** `[a-z0-9][a-z0-9_-]*`.
   - **Order.** Modules run in file order.
   - **`count: "none"`.** Marks a module whose command prints no test count, such as a docs lint,
     the way `--count none` does today.
   - **Globs.** They use `glob_re`, as `writes:` does.
2. **`modmap.py`**
   - `load(root)` returns `None` when the file is absent and raises `MapError(text)` on a bad
     file.
   - `problems(m)` lists errors:
     - `module <a> needs <b>, which is not a module`;
     - `modules needs cycle: a -> b -> a`;
     - `module <a> has no test command`;
     - `module <a> has no paths`;
     - `modules <a> and <b> share one test command`.
   - `select(m, write_globs)` returns module names in file order:
     - **Contained.** A write glob `w` is contained by a module glob `g` when either holds:
       - `w` has no wildcard and `glob_re(g)` matches it;
       - `g` ends in `/**` and `w` starts with `g` without its `**`.
     - **All modules** when any write glob overlaps a `shared` glob, or no single module glob
       contains it. This covers a `src/**` write that spans owned and unowned files.
     - **Otherwise** the modules with a glob overlapping any write glob, plus every module that
       needs a selected one. The fixed point is computed over a visited set, which terminates
       because `problems` has already rejected cycles.
   - `unmapped(m, files)` lists tracked files that no module path and no `shared` glob matches.
3. **Lint.** When the map exists, `goal.py lint` adds each `problems` line, and any `MapError`, as
   an error prefixed `modules.json:`. It adds `modules.json: <n> tracked file(s) no module covers,
   first <path>` as a warning, using `git ls-files`. S-6's slow-gate warning is skipped for a task
   whose gate is derived.
   - **`full_gate: modules`.** When the plan sets it, lint fails with
     `full_gate: modules needs the map to name the command it replaces` when `replaces` is
     missing, or with `full_gate: modules needs a count-none module for the non-test checks` when
     no module has `count: "none"`. The design does not claim lint can prove that every check is
     present; Interface 4's approval table and Interface 11's construction rule carry that.
4. **Derived task gate.** For a task without `gate:` when the map exists, the gate is
   `modules: <a>, <b>`.
   - `next` prints ` · gate: modules: a, b`, and the approval page's Gate column shows the same
     text.
   - **Approval table.** When the plan sets `full_gate: modules`, the approval page adds a "Full
     gate" table:
     - first row: the map's `replaces` command;
     - then one row per module: name, command, and "tests" or "non-test checks" for a count-none
       module;
     - above it, the line: "Check that every non-test check the replaced command runs is run by a
       module."

     The founder checks it at approval (founder, 2026-10-13).
   - The chief runs `gate.py check --goal <id> --modules a,b`.
   - A task with a `gate:` line keeps it.
   - With no map, nothing changes.
5. **`gate.py --modules <a,b|all>`.** `check` and `receipt` take either `--cmd` or `--modules`,
   never both.
   - **Order and exit.** Each named module runs its `test` as its own process through
     `evaluate()`, in map order, and every module runs even after a failure. The exit is 0 only
     when every module passes.
   - **Output.** Each module prints `module <name>: ` followed by the usual summary line. A last
     line reads `modules: PASS 4 of 4` or `modules: FAIL 1 of 4 (<names>)`, and then comes the
     budget line over the summed duration.
   - **Receipts.**
     - Written only by `receipt --modules`, at `receipt_path(root, goal, tree, "module:<name>\n" +
       test)`. This key matches no `--cmd` receipt and no other module.
     - The receipt holds `"name": "module"`, `"module": "<name>"` and `"command": test`.
     - `check --modules` writes and supersedes no module receipt.
   - **Gradle.** The `--rerun-tasks` receipt rule applies to module commands, unless the founder
     accepts the Parked Gradle question, in which case a module receipt also accepts `--rerun`.
6. **Load readings (diagnostic).** Each `gate.py` invocation samples `os.getloadavg()[0]` once,
   before its first process starts. That is `load_before`, and every module of a `--modules` run
   carries the invocation's value. While each process runs, a thread samples `os.getloadavg()[0]`
   every 5 s for `load_peak`. Every `checks.jsonl` line and every receipt gains `started_at`,
   `load_before`, `load_peak` and `cpus`. Module lines also gain `module`. No rule reads them: they
   are shown beside a retry so the reviewer can judge it.
7. **Same-tree reuse and one retry.** For `receipt --modules`, each module in turn:
   - **PASS receipt on this tree.** Skipped, printed as `module <name>: PASS on this tree (kept)`.
   - **No receipt.** It runs.
   - **FAIL receipt without `retry_of`.** It reruns once and prints `module <name>: retry after a
     failure on this tree`. The new receipt stores the failed receipt under `"retry_of"`, so the
     retry is spent whatever the new verdict.
   - **FAIL receipt with `retry_of`.** Refused for that module: `module <name> failed twice on this
     tree; diagnose and commit a fix`. The other modules still run, and the exit is 1.
   - **A new tree** has no receipts, so every module runs.
8. **Coverage (advisory).** `gate.py coverage --goal <id> [--cmd "<full gate>"]` runs nothing.
   `--cmd` defaults to the map's `replaces`. On the
   clean HEAD tree it compares two things:
   - the PASS receipt of that exact `--cmd` command;
   - the PASS module receipts of every module.

   It prints `coverage: <n> = <m>` or `coverage: full <n>, modules <m>; <names> missing`, and exits
   0 when they are equal, 1 otherwise. Nothing reads it. Equal counts cannot prove that every
   check runs, because non-test checks are not counted and test sets may overlap. So it is a
   drafting aid, and the founder's review of the map is the equivalence check.
9. **Done rows.**
   - **Row 7.** When the plan's `full_gate` is `modules`, the full gate needs two things:
     - a PASS module receipt on HEAD's tree for every module in the map at HEAD;
     - no tracked file left unmapped, since a test in an unmapped directory would never run.

     The message names the first gap: `no PASS module receipt for <x> on tree <t>`, or `<n>
     tracked file(s) no module covers, first <path>`. Any other `full_gate` value works as today.
   - **Row 4.** When the map exists at the approval commit, `docs/goals/modules.json` counts as a
     `protected` path. A task whose writes reach it fails, as a `protected` path does today, so a
     map change waits for the founder.
10. **Packet.** A `Retried modules:` section lists each module receipt carrying `retry_of`:
    `<module>: failed <started_at> (load <before>/<peak> on <cpus> cpus), retry <verdict> (load
    <before>/<peak>)`. With none, it prints `none`.
11. **Words.**
    - **`planning.md` step 5.** Where no map exists, draft `docs/goals/modules.json` from the build
      files and imports:
      - one module per build module or test directory;
      - `needs` from what each module's tests execute or import;
      - a count-none module for non-test checks, whose command is the replaced full-gate command
        with its tests switched off (for example `./gradlew check -x test`, or this repository's
        `verify.sh --no-suites`), so a check added to the full gate later still runs;
      - `replaces` set to today's full-gate command.

      Then compare it once with `gate.py coverage`, and commit it with the plan. To compose the
      full gate from it, set `full_gate: modules`, and add a Decisions line naming the module that
      runs each non-test check of the replaced command. Prefer derived gates to `gate:` lines.
    - **`SKILL.md` step 5.** Run the task's `gate:`, or the modules `next` names.
    - **`close.md`.** With `full_gate: modules`, the full gate is `receipt --modules all`. After a
      failure, the same command keeps passed modules and retries a failed one once; a second
      failure needs a fix commit.
    - **D33.** Records the decision.

## Data touched

- **New committed file.** `docs/goals/modules.json`, in this repository too.
- **New fields.**
  - `started_at`, `load_before`, `load_peak`, `cpus` and `module` in `checks.jsonl` lines and
    receipts;
  - `retry_of` in module receipts.
- **Unchanged.** Nothing outside the repository is written. Old records without the new fields
  read as before. `full_gate` accepts one new literal value, `modules`.

## Smallest change

- A module run is an ordinary `evaluate()` and receipt under a module-specific key, so the receipt
  code is unchanged.
- Selection is the existing `overlap()`, a containment test and a fixed-point loop.
- Row 7 gains one branch, and row 4 one implicit protected path.
- Coverage reads receipts and runs nothing.

## Rejected options

- **Per-test reruns.** These are S-6's removed `--rerun-failed`. From runner output alone, the
  tool could not prove which tests ran or never ran, or why one failed.
- **A retry gated on load evidence.** The founder dropped it on 2026-10-13 in favour of one retry
  regardless. The design review had found the evidence unsound:
  - a crashed run's registry entry stayed "running" forever;
  - entries collided within one second;
  - readers raced writers;
  - clock changes created false overlap;
  - other local users could plant entries;
  - pruning lost the evidence;
  - one load reading at the start of a long run vouched for failures late in it.

  The readings stay as diagnostics only.
- **A coverage certificate for row 7.** Equal test counts do not show that the modules run every
  check, or the same tests, that the single command runs (design review R4). With
  `full_gate: modules`, the approved map is the full gate, and there is nothing to be equivalent to.
- **Command-keyed module receipts.** Two modules with one command, or a `--cmd` receipt of the same
  command, would share a receipt (design review R2).
- **Reusing a module's PASS across trees.** The founder chose same-tree reuse only (2026-10-13).
- **Inferring the map from imports or the build graph.** That needs one tool per stack. A
  committed map the founder approves is reviewable and works for any stack.
- **YAML or TOML.** YAML needs a dependency. `tomllib` needs Python 3.11, and the installer
  accepts 3.10.
- **Running modules in parallel.** They would load each other.

## Trade-offs for the founder

- **A failure that passes on retry.** It may be a real intermittent bug. It reaches PASS, and the
  packet's Retried modules section lists it with both runs' load readings for review at merge.
- **Missed edges.** A map that misses an edge picks too small a task gate. The full gate at close,
  and every third task where the full gate is fast, still runs every module.
- **The map stands in for the old full-gate command.** With `full_gate: modules`, a check the map
  leaves out never runs, and no tool can prove that every non-test check is present. Three
  things guard it:
  - the count-none module runs the replaced command itself with tests switched off, so the
    checks it already runs, and any added later, stay in;
  - lint refuses `full_gate: modules` without `replaces` and a count-none module;
  - the approval page puts the replaced command beside every module, for the founder to check.

  A check that the replaced command runs only alongside its tests, with no switch to skip them,
  still depends on that review.
- **Slower composed full gate.** In Gradle, one process per module costs Gradle's startup and
  configuration each time, so a composed full gate may take longer than one `./gradlew test`. What
  it buys is that after a failure only the failed modules rerun.
- **Map changes wait for the founder.** Once approved, the map is protected. A new test directory
  needs a Parked line and the founder's approval before its module exists. Until then, its files
  select every module in task gates, and a goal with `full_gate: modules` cannot finish (Parked
  question).
