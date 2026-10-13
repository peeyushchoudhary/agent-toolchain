# S-7 design: a test-module map that picks task gates and reruns only failed modules

## Structure

One new committed file per repository, one new script module, and changes to two existing
commands and four skill pages.

- **The map.** `docs/goals/modules.json` lists the repository's test modules. Each module has the
  paths it owns, the modules it needs and one test command. It also lists the `shared` paths that
  every module reads. The chief drafts it from the build files at planning, and the founder
  approves it with the plan.
- **`scripts/modmap.py`.** Loads and checks the map, selects modules for a set of write globs, and
  lists tracked files no module covers. `glob_re`, `matches` and `overlap` move here from
  `goal.py`, which imports them back, because `gate.py` needs them too and `goal.py` already
  imports `gate.py`.
- **`gate.py`**
  - Runs modules: `--modules` on `check` and `receipt`.
  - Records load readings on every run.
  - Skips modules that already passed on the same tree.
  - Reruns a failed module once, and only with load evidence.
  - A new `coverage` command checks that the modules add up to the full gate.
- **`goal.py`**
  - Checks the map at `lint`.
  - Derives a task's gate when it has no `gate:` line.
  - Accepts module receipts for done row 7 when coverage holds.
  - Lists load reruns in the PR packet.
- **Words.** `planning.md` drafts the map; `SKILL.md` step 5 runs the derived gate; `close.md`
  composes the full gate and states the rerun rule; D33 records the decision.

## Interfaces

1. **Map file.** JSON, standard library only. Unknown keys are errors.

   ```
   {"modules": {"<name>": {"paths": ["<glob>", ...], "needs": ["<name>", ...],
                           "test": "<command>", "count": "none"?}},
    "shared": ["<glob>", ...]}
   ```

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
     - `module <a> has no paths`.
   - `select(m, write_globs)` returns module names in file order. It starts with the modules whose
     `paths` overlap any write glob, adds every module that needs a selected one until nothing
     changes, and returns every module when a write glob overlaps `shared` or overlaps no module's
     paths.
   - `unmapped(m, files)` lists tracked files that no module path and no `shared` glob matches.
   - `digest(m)` is the SHA-256 of the file's bytes.
3. **Lint.** When the map exists, `goal.py lint` adds each `problems` line as an error prefixed
   `modules.json:`. It adds `modules.json: <n> tracked file(s) no module covers, first <path>` as a
   warning, using `git ls-files`. S-6's slow-gate warning is skipped for a task whose gate is
   derived.
4. **Derived task gate.** For a task without `gate:` when the map exists, the gate is
   `modules: <a>, <b>`.
   - `next` prints ` · gate: modules: a, b`, and the approval page's Gate column shows the same
     text.
   - The chief runs `gate.py check --goal <id> --modules a,b`.
   - A task with a `gate:` line keeps it.
   - With no map, nothing changes.
5. **`gate.py --modules <a,b|all>`.** `check` and `receipt` take either `--cmd` or `--modules`,
   never both.
   - **Order and exit.** Each named module runs its `test` as its own process through
     `evaluate()`, in map order, and every module runs even after a failure. The exit is 0 only
     when every module passes.
   - **Output.** Each module prints `module <name>: ` followed by the usual summary line. A last line
     reads `modules: PASS 4 of 4` or `modules: FAIL 1 of 4 (<names>)`, and then comes the budget
     line over the summed duration.
   - **Receipts.** A module receipt is the ordinary receipt for the module's command on the tree,
     with `"name": "module"` and `"module": "<name>"`.
   - **`--rerun`.** `receipt --modules` keeps the `--rerun-tasks` rule unless the founder accepts
     the Parked Gradle question, in which case a module receipt also accepts `--rerun`.
6. **Load readings.** Each `gate.py` invocation samples `os.getloadavg()[0]` once, before its
   first process starts. That is `load_before`, and every module of a `--modules` run carries the
   invocation's value, because a later module's own reading would still hold the previous module's
   work. While each process runs, a thread samples `os.getloadavg()[0]` every 5 s for `load_peak`.
   Every record in `checks.jsonl` and every receipt gains `started_at`, `load_before`, `load_peak`
   and `cpus`. Module records also gain `module`.
   - **Machine registry.** Each run also writes `<tmp>/gate-runs/<pid>-<started>.json` holding
     `{"started_at", "finished_at"}`, with `finished_at` filled in at the end. `<tmp>` is
     `tempfile.gettempdir()`. The file holds no path or command, and entries older than a day are
     pruned. The registry shows runs in other repositories and sessions on the same machine.
7. **Same-tree reuse and the load rerun.** For `receipt --modules`, each module in turn:
   - **PASS receipt on this tree.** Skipped, printed as `module <name>: PASS on this tree (kept)`.
   - **No receipt.** It runs.
   - **FAIL receipt, with load evidence.** It reruns once, prints `module <name>: rerun under load
     evidence: <evidence>`, and stores the failed run under `"load_rerun_of"`. Load evidence means
     either of these:
     - the failed run's `load_before`, its invocation's reading, was at least its `cpus`;
     - a registry entry other than the failed run's own overlapped its
       `started_at`..`finished_at`.
   - **FAIL receipt, no evidence, or a load rerun already spent.** Refused for that module:
     `module <name> failed on this tree without load evidence; diagnose and commit a fix`. The
     other modules still run, and the exit is 1.
   - `check --modules` always runs every named module.
8. **Coverage.** `gate.py coverage --goal <id>` runs nothing. It compares two things on the clean
   HEAD tree:
   - the PASS receipt of the plan's `full_gate` command;
   - the PASS module receipts of every module.

   It passes when the full gate's `executed` equals the sum over counted modules. It writes
   `.runs/<id>/coverage.json` as `{"digest", "tree", "full", "modules": {name: n}, "verdict"}` and
   prints `coverage: PASS 225 = 225` or `coverage: FAIL full 225, modules 219 (<n> missing)`.
   - **When coverage holds.** A PASS whose `digest` equals the current map's, with no unmapped
     tracked file at HEAD.
9. **Done row 7.** A `full_gate` is accepted in either of two ways:
   - its PASS receipt on HEAD's tree, as today;
   - when the map exists and coverage holds, a PASS module receipt on HEAD's tree for every module.

   The e2e receipt rule is unchanged.
10. **Packet.** A `Load reruns:` section lists each module receipt carrying `load_rerun_of`:
    `<module>: failed <started_at> (<evidence>), passed on rerun`. With none, it prints `none`.
11. **Words.**
    - **`planning.md` step 5.** Where no map exists, draft `docs/goals/modules.json` from the build
      files, one module per build module or test directory, with `needs` from the build's
      dependencies. Commit it with the plan. Prefer derived gates to `gate:` lines.
    - **`SKILL.md` step 5.** Run the task's `gate:`, or the modules `next` names.
    - **`close.md`.** Where coverage holds, the full gate is `receipt --modules all`. After a
      failure, the same command keeps passed modules and reruns a failed one once with load
      evidence. Prove coverage once per map version with `coverage`.
    - **D33.** Records the decision.

## Data touched

- **New committed file.** `docs/goals/modules.json`, in this repository too.
- **New fields.** `started_at`, `load_before`, `load_peak`, `cpus` and `module` in `checks.jsonl`
  lines and receipts; `load_rerun_of` in module receipts.
- **New `.runs` file.** `.runs/<id>/coverage.json`.
- **Outside the repository.** A registry directory under the system temporary directory, holding
  timestamps only.

Old records without the new fields read as no load evidence. No location moves.

## Smallest change

- A module run is an ordinary `evaluate()` and receipt keyed by the module's command, so reuse,
  supersede and history come from S-6's receipt code unchanged.
- Coverage reads receipts and runs nothing.
- Selection is the existing `overlap()` plus a fixed-point loop over `needs`.
- Row 7 gains one alternative.
- The map is plain JSON with a five-rule check.

## Rejected options

- **Per-test reruns.** These are S-6's removed `--rerun-failed`. From runner output alone, the
  tool could not prove which tests ran or never ran, or why one failed. Three review rounds
  blocked it.
- **The end-of-run load reading S-6 recorded (R24).** It mostly measures the run itself: a suite
  that fills every core shows load near the CPU count on an idle machine. Load before the start,
  the peak, and overlap with other runs replace it.
- **Load before each module as evidence inside one composed run.** The previous module's own work
  is still in the 1-minute average. Only the invocation's single reading before its first process,
  or an overlapping run in the registry, points at other work. The registry exists for load that
  starts mid-run.
- **Reusing a module's PASS across trees.** The founder chose same-tree reuse only (2026-10-13).
  A changed tree reruns every module, because a selection rule could miss an edge.
- **Rerunning any failed module without evidence (the "flaky" option).** The founder chose
  evidence-gated reruns.
- **Inferring the map from imports or the build graph.** That needs one tool per stack. A
  committed map the founder approves is reviewable and works for any stack.
- **YAML or TOML.** YAML needs a dependency. `tomllib` needs Python 3.11, and the installer
  accepts 3.10.
- **Coverage on every close.** It costs one more full run per close (see Q3).
- **Running modules in parallel.** They would load each other, which is the cause this goal
  measures.

## Trade-offs for the founder

- **Missed edges.** A map that misses an edge picks too small a task gate. The every-third and
  closing full gates still run every module, and the coverage count catches a module that runs
  fewer tests than its share.
- **Slower composed full gate.** In Gradle, one process per module costs Gradle's startup and
  configuration each time, so a composed full gate may take longer than one `./gradlew test`. What
  it buys is that after a load failure only the failed modules rerun.
- **A regression that shows only under load.** It passes on its single rerun, and the packet lists
  it under Load reruns for review, never silently.
- **The registry sees only gate.py runs.** Another program loading the machine shows only through
  `load_before` at the run's start.
