---
goal: S-7
title: Methodology v7.3 — a test-module map picks task gates, composes the full gate and reruns only failed modules with load evidence
gate: cd install && ./verify.sh
full_gate: cd install && ./install.sh --dry-run && ./verify.sh
milestones:
  M1: {tasks: [T1, T2, T3, T4, T5, T6, T7, T8, T9], e2e: "install/skills/execution-methodology/tests/e2e_run.sh"}
touches: [interface]
protected: [docs/decisions/decisions.md#D1-D32, docs/goals/S-7/design.md#interfaces, docs/goals/S-7/design.md#data-touched]
---

## Outcome

A repository may commit `docs/goals/modules.json`, a map of its test modules. Each module has the
paths it owns, the modules it needs and one test command. `lint` fails on a broken map and warns
about tracked files no module covers (AC1). A task without a `gate:` line shows the modules its
writes reach in `next` and on the approval page (AC2). `gate.py check` and `receipt` take
`--modules`, run each module as its own process and record its load readings (AC3).

Module receipts on HEAD's tree stand in for the `full_gate` receipt once `gate.py coverage` has
shown that the modules' tests add up to the full gate's (AC4, AC7). A second `receipt --modules`
on the same tree keeps passed modules, runs unrun ones, and reruns a failed one once, only with
load evidence (AC5). The packet lists every load rerun (AC6). The skill tells the planner to draft
the map with the plan (AC8). The e2e proves AC2, AC3 and AC5 in both harnesses, and this
repository ships its own map (AC9).

Decision record: D33. Design: [design.md](design.md). Spec: [spec.md](spec.md).

## Tasks

### [ ] T1 — `modmap.py`: load, check and select modules; the glob helpers move from `goal.py`
writes: install/skills/execution-methodology/scripts/modmap.py, install/skills/execution-methodology/scripts/goal.py, install/skills/execution-methodology/tests/test_modmap.py
reads: docs/goals/S-7/design.md#interfaces, install/skills/execution-methodology/scripts/goal.py, install/skills/execution-methodology/tests/test_goal.py, install/skills/execution-methodology/tests/fixtures/goal_fixture.py
tests-may-change: install/skills/execution-methodology/tests/test_modmap.py
gate: python3 -m unittest discover -s install/skills/execution-methodology/tests -t install/skills/execution-methodology/tests -p 'test_modmap.py' && python3 -m unittest discover -s install/skills/execution-methodology/tests -t install/skills/execution-methodology/tests -p 'test_goal.py'
Design Interfaces 1 and 2.

**New file `scripts/modmap.py`.** Standard library only.
- `MAP = "docs/goals/modules.json"`.
- `class MapError(Exception)`.
- `load(root) -> dict | None`:
  - returns `None` when the file is absent;
  - raises `MapError` on invalid JSON, a top-level key other than `modules` or `shared`, or a
    module key other than `paths`, `needs`, `test` or `count`;
  - also raises `MapError` on a name not matching `^[a-z0-9][a-z0-9_-]*$`, or a `count` other
    than `"none"`.
- `problems(m) -> list[str]` returns, in this order, these exact texts:
  - `module <a> needs <b>, which is not a module`;
  - `modules needs cycle: <a> -> <b> -> <a>`;
  - `module <a> has no test command`;
  - `module <a> has no paths`.
- `select(m, write_globs) -> list[str]` follows Interface 2 and returns names in file order.
- `unmapped(m, files) -> list[str]`.
- `digest(root) -> str` is the SHA-256 hex of the file's bytes.

**Move from `goal.py`.** `glob_re`, `matches` and `overlap` move into `modmap.py` unchanged.
`goal.py` imports them with `from modmap import glob_re, matches, overlap  # noqa: E402`, next to
its `gate` import, and nothing else in `goal.py` changes.

**Tests: new `tests/test_modmap.py`.** Class `ModMapTest`, using a temporary directory per test:
- `test_load_rejects_unknown_keys_and_bad_names`;
- `test_problems_name_unknown_needs_cycles_and_missing_fields`;
- `test_select_adds_dependents_transitively_in_file_order`:
  - `core`, `fees` needs `core`, `app` needs `fees`;
  - a write under `core/**` selects all three;
  - a write under `app/**` selects `app` alone;
- `test_select_falls_back_to_every_module_on_shared_or_unowned_paths`;
- `test_unmapped_lists_tracked_files_no_glob_covers`.

Do not change `gate.py` or any existing test.

### [ ] T2 — `gate.py`: load readings on every run and the machine registry
writes: install/skills/execution-methodology/scripts/gate.py, install/skills/execution-methodology/tests/test_gate.py
reads: docs/goals/S-7/design.md#interfaces, install/skills/execution-methodology/scripts/gate.py, install/skills/execution-methodology/tests/test_gate.py
tests-may-change: install/skills/execution-methodology/tests/test_gate.py
gate: python3 -m unittest discover -s install/skills/execution-methodology/tests -t install/skills/execution-methodology/tests -p 'test_gate.py'
Design Interface 6.

**`run()` and its callers.**
- `run(root, cmd, goal, label, runs=None, load_before=None)` returns
  `(code, out, log, duration_s, readings)`.
- `readings` is `{"started_at", "load_before", "load_peak", "cpus"}`:
  - `load_before` is the argument when given, otherwise `os.getloadavg()[0]` taken before `Popen`;
  - `load_peak` is the highest of `load_before` and the samples a daemon thread takes every 5 s
    with `os.getloadavg()[0]` until the process exits;
  - all three loads are rounded to 2 places.
- `evaluate()` merges `readings` into its result.
- `record(...)` gains `readings=None` and writes them into the `checks.jsonl` line.
- `cmd_check`, `cmd_receipt`, `cmd_baseline` and `refuse_receipt` pass them through. A refused
  receipt records `load_before` only.

**Registry.**
- `registry_dir() = Path(tempfile.gettempdir()) / "gate-runs"`.
- `run()` writes `<pid>-<started_at with ':' replaced by '-'>.json` holding `{"started_at"}`
  before `Popen`, and rewrites it with `"finished_at"` after `wait()`.
- Files whose `finished_at` is more than 86400 s old are deleted at each start.
- No command, path or tree is written.
- `overlapping(entry_name, started_at, finished_at) -> list[str]` lists the other entries whose
  interval intersects that window. An entry with no `finished_at` counts as running now.

**Tests in `test_gate.py`.** Copy `ReceiptTest.test_receipt_bound_to_tree_and_command`, with
`TMPDIR` set to a scratch directory through the fixture's environment:
- `test_every_record_and_receipt_carries_load_readings` (AC3);
- `test_registry_entry_is_written_and_finished_without_paths`;
- `test_overlapping_lists_only_other_runs_in_the_window`.

In `ReceiptTest.test_receipt_omits_removed_load_rerun_metadata`, remove `"cpus"` from the
asserted-absent set. Do not change `goal.py`.

### [ ] T3 — `gate.py --modules`: module runs, same-tree reuse and the load rerun
writes: install/skills/execution-methodology/scripts/gate.py, install/skills/execution-methodology/tests/test_gate.py
reads: docs/goals/S-7/design.md#interfaces, install/skills/execution-methodology/scripts/gate.py, install/skills/execution-methodology/scripts/modmap.py, install/skills/execution-methodology/tests/test_gate.py
tests-may-change: install/skills/execution-methodology/tests/test_gate.py
needs: T1, T2
gate: python3 -m unittest discover -s install/skills/execution-methodology/tests -t install/skills/execution-methodology/tests -p 'test_gate.py'
Design Interfaces 5 and 7.

**Arguments.**
- `check` and `receipt` take a mutually exclusive required group: `--cmd` or
  `--modules <a,b|all>`.
- An unknown module name exits 2 with `gate.py: no module <x> in docs/goals/modules.json`, and so
  does a missing map.

**Running modules.**
- The invocation takes one `load_before` and passes it to every module's `run`.
- Each module goes through `evaluate()` with `count_none` taken from its `count`.
- `receipt` writes the module's receipt at `receipt_path(root, goal, tree, test)` with
  `"name": "module"` and `"module": "<name>"`.
- Output and exit code follow Interface 5 exactly.

**Interface 7 rules for `receipt --modules`.**
- The evidence text is `load <x> before start on <n> cpus` or `overlapped <k> other run(s)`.
- The receipt rule `--rerun-tasks` applies to module commands as to `--cmd`, unless the
  founder's answer to the Gradle question allows `--rerun` for module receipts.

**Tests in `test_gate.py`, new class `ModulesTest`.** It writes a three-module map whose commands
use the existing fixture emitter:
- `test_modules_run_each_command_and_pass_only_when_all_pass` (AC3);
- `test_receipt_keeps_passed_modules_on_the_same_tree` (AC5);
- `test_failed_module_reruns_once_with_load_evidence` (AC5). It plants a registry entry
  overlapping the failed run;
- `test_failed_module_without_evidence_is_refused_and_others_still_run` (AC5);
- `test_a_new_tree_reruns_every_module`.

Do not change `goal.py` or `modmap.py`.

### [ ] T4 — `gate.py coverage`
writes: install/skills/execution-methodology/scripts/gate.py, install/skills/execution-methodology/tests/test_gate.py
reads: docs/goals/S-7/design.md#interfaces, install/skills/execution-methodology/scripts/gate.py, install/skills/execution-methodology/tests/test_gate.py
tests-may-change: install/skills/execution-methodology/tests/test_gate.py
needs: T3
gate: python3 -m unittest discover -s install/skills/execution-methodology/tests -t install/skills/execution-methodology/tests -p 'test_gate.py'
Design Interface 8.

**The command.** `gate.py coverage --goal <id> [--runs DIR]`:
- refuses a dirty tree, with the same message as `receipt`;
- reads the plan's `full_gate` from `docs/goals/<id>/plan.md` frontmatter with a minimal line read
  of `full_gate:`, because `gate.py` must not import `goal.py`;
- runs nothing;
- writes `<runs>/<id>/coverage.json` exactly as Interface 8 says;
- prints the Interface 8 line and exits 0 on PASS, 1 otherwise.

A missing receipt is a FAIL naming it: `coverage: FAIL no PASS receipt for module <x> on this
tree`.

**Tests in `test_gate.py`, class `CoverageTest`:**
- `test_coverage_passes_when_module_counts_sum_to_the_full_gate` (AC7);
- `test_coverage_fails_on_a_missing_module_receipt_or_a_short_sum` (AC7);
- `test_coverage_skips_count_none_modules`.

### [ ] T5 — `goal.py`: the map at `lint`, and the derived task gate in `next` and the approval page
writes: install/skills/execution-methodology/scripts/goal.py, install/skills/execution-methodology/tests/test_goal.py
reads: docs/goals/S-7/design.md#interfaces, install/skills/execution-methodology/scripts/goal.py, install/skills/execution-methodology/scripts/modmap.py, install/skills/execution-methodology/tests/test_goal.py
tests-may-change: install/skills/execution-methodology/tests/test_goal.py
needs: T1
gate: python3 -m unittest discover -s install/skills/execution-methodology/tests -t install/skills/execution-methodology/tests -p 'test_goal.py'
Design Interfaces 3 and 4.

**`lint`.**
- When `modmap.load` returns a map, `lint` adds each `problems()` line as an error prefixed
  `modules.json: `.
- A `MapError` becomes the error `modules.json: <text>`.
- `lint_warnings` adds `modules.json: <n> tracked file(s) no module covers, first <path>`, from
  `git ls-files`.
- `lint_warnings` skips the slow-gate warning for a task whose gate is derived.

**Derived gate.**
- New `task_gate(ctx, task) -> str` returns:
  - the task's `gate:` line when it has one;
  - otherwise, with a map, `modules: a, b` from `select(map, task["writes"])`;
  - otherwise `""`.
- `cmd_next` and the approval page's Gate column use it. The column shows `plan gate` when it is
  empty.

**Tests in `test_goal.py`, class `ModuleMapTest`, copying `TaskFieldTest`:**
- `test_lint_fails_on_a_broken_map_and_warns_about_unmapped_files` (AC1);
- `test_next_and_approval_show_the_derived_gate` (AC2);
- `test_a_gate_line_overrides_the_map`.

### [ ] T6 — `goal.py`: module receipts satisfy done row 7 when coverage holds; the packet lists load reruns
writes: install/skills/execution-methodology/scripts/goal.py, install/skills/execution-methodology/tests/test_goal.py
reads: docs/goals/S-7/design.md#interfaces, install/skills/execution-methodology/scripts/goal.py, install/skills/execution-methodology/tests/test_goal.py
tests-may-change: install/skills/execution-methodology/tests/test_goal.py
needs: T5
gate: python3 -m unittest discover -s install/skills/execution-methodology/tests -t install/skills/execution-methodology/tests -p 'test_goal.py'
Design Interfaces 9 and 10.

**Done row 7.** In `done_rows`, when the `full_gate` receipt is missing and the map exists, row 7
accepts the full gate when all three of these hold:
- `.runs/<id>/coverage.json` has `verdict` PASS and `digest == modmap.digest(root)`;
- `modmap.unmapped` is empty for `git ls-files`;
- every module has a PASS receipt on HEAD's tree at `receipt_path(root, goal, tree, test)`.

Otherwise the message stays `no PASS full_gate receipt for tree <t>`, with the first missing
condition after it: `; coverage does not hold`, or `; no PASS receipt for module <x>`.

**Packet.** `cmd_packet` adds the `Load reruns:` section after `Receipts:`, with lines exactly as
Interface 10 gives them.

**Tests in `test_goal.py`, class `ModuleRowTest`.** Fixtures write receipts and `coverage.json`
directly:
- `test_module_receipts_satisfy_row_7_when_coverage_holds` (AC4);
- `test_row_7_names_why_module_receipts_do_not_count` (AC4);
- `test_packet_lists_load_reruns` (AC6).

### [ ] T7 — v7.3 in words: D33, the skill's step 5, planning's map, close's composed gate and rerun rule
writes: install/skills/execution-methodology/SKILL.md, install/skills/execution-methodology/references/planning.md, install/skills/execution-methodology/references/close.md, install/skills/execution-methodology/tests/test_rules.py, docs/decisions/decisions.md, docs/architecture/methodology.md, AGENTS.md
reads: docs/goals/S-7/design.md#interfaces, install/skills/execution-methodology/SKILL.md, install/skills/execution-methodology/references/planning.md, install/skills/execution-methodology/references/close.md, install/skills/execution-methodology/tests/test_rules.py, docs/decisions/decisions.md#d32--methodology-v72-each-tasks-gate-chosen-at-planning-builders-dispatched-by-dependency-s-6
tests-may-change: install/skills/execution-methodology/tests/test_rules.py
gate: python3 -m unittest discover -s install/skills/execution-methodology/tests -t install/skills/execution-methodology/tests -p 'test_rules.py' && python3 -m unittest discover -s install/tests -t install/tests -p 'test_size.py' && python3 install/skills/execution-methodology/scripts/docs.py lint .
Design Interface 11.

**Word budgets.** The always-loaded files total 1317 of 1350 words, and `planning.md` is at 399 of
400, so tighten its existing lines to make room.

**Edits.**
- `SKILL.md` step 5 reads: "Run the task's gate yourself: its `gate:`, the modules `goal.py next`
  names (`--modules a,b`), or the plan's, one check at a time."
- `planning.md` step 5 says:
  - draft `docs/goals/modules.json` from the build files where none exists;
  - give one module per build module or test directory, with `needs` from build dependencies;
  - add a count-none module for non-test checks;
  - commit the map with the plan;
  - prefer derived gates to `gate:` lines.
- `close.md` states:
  - where coverage holds, the full gate is `gate.py receipt --goal <id> --name full_gate --modules
    all`;
  - after a failure the same command keeps passed modules and reruns a failed module once, only
    with load evidence;
  - prove coverage once per map version: the single `full_gate` receipt and the module receipts on
    one tree, then `gate.py coverage`.

**D33.** Add it directly after D32's last line, with no blank line between, because the protected
range `D1-D32` counts a trailing blank line. It records:
- what changes;
- the founder's four answers of 2026-10-13;
- S-6 R24's removal of the end-of-run load reading, and why S-7 reads load before the start, the
  peak and the registry instead;
- the rejected options.

**Methodology page and `AGENTS.md`.** `docs/architecture/methodology.md` gets the v7.3 title, a
D33 link and a "Module map" bullet. `AGENTS.md` says v7.3 and links D33.

**Tests in `test_rules.py`:**
- `Loop.test_step_5_names_the_modules_next_derives`;
- `Close.test_close_composes_the_full_gate_from_modules_and_states_the_rerun_rule`;
- `Planning.test_planning_drafts_the_map_with_the_plan` (AC8).

Do not change scripts.

### [ ] T8 — This repository's own map and `verify.sh --no-suites`
writes: docs/goals/modules.json, install/verify.sh, install/tests/test_map.py
reads: docs/goals/S-7/design.md#interfaces, install/verify.sh, install/tests/test_size.py, install/skills/execution-methodology/scripts/modmap.py
tests-may-change: install/tests/test_map.py
needs: T1
gate: python3 -m unittest discover -s install/tests -t install/tests -p 'test_map.py' && cd install && ./verify.sh --no-suites
**`verify.sh --no-suites`.** It skips steps 1 and 2, the two `run_suite` lines, and runs every
other check. Its help text gains the option.

**The map.** `docs/goals/modules.json`, in this order:

| Module | Paths | Needs | Test |
|---|---|---|---|
| `modmap` | `scripts/modmap.py`, `tests/test_modmap.py` | none | `-p 'test_modmap.py'` |
| `gate` | `scripts/gate.py`, `tests/test_gate.py` | `modmap` | `-p 'test_gate.py'` |
| `goal` | `scripts/goal.py`, `tests/test_goal.py` | `gate`, `modmap` | `-p 'test_goal.py'` |
| `docs` | `scripts/docs.py`, `tests/test_docs.py` | none | `-p 'test_docs.py'` |
| `guard` | `scripts/guard.py`, `tests/test_guard.py` | none | `-p 'test_guard.py'` |
| `hooks` | `scripts/git-hooks.sh`, `tests/test_git_hooks.py` | `guard` | `-p 'test_git_hooks.py'` |
| `rules` | `SKILL.md`, `references/**`, `agents/**`, `tests/test_rules.py` | none | `-p 'test_rules.py'` |
| `install` | `install/install.sh`, `install/tests/**`, `install/*.md` | none | see below |
| `repository` | `docs/**`, `*.md`, `install/verify.sh`, `.claude/**`, `.github/**`, `LICENSE`, `.gitignore`, `install/skills/.gitignore` | none | see below |

- Paths and tests in the `modmap` to `rules` rows are relative to
  `install/skills/execution-methodology/`.
- Each of those tests is `python3 -m unittest discover -s
  install/skills/execution-methodology/tests -t install/skills/execution-methodology/tests`
  followed by the row's `-p` argument.
- `install` runs `python3 -m unittest discover -s install/tests -t install/tests`.
- `repository` has `"count": "none"` and runs `cd install && ./install.sh --dry-run && ./verify.sh
  --no-suites`.
- `shared` is `install/skills/execution-methodology/tests/fixtures/**`,
  `install/skills/execution-methodology/tests/e2e_run.sh` and `install/global.md`.

**Tests: new `install/tests/test_map.py`**, class `RepositoryMapTest`:
- `test_map_loads_with_no_problems` (AC9);
- `test_every_tracked_file_is_covered` (AC9);
- `test_no_suites_skips_both_run_suite_lines`, which reads `verify.sh`'s text.

Coverage on this repository is proven at close by the chief.

### [ ] T9 — `e2e_run.sh`: derived gates, module runs and the load rerun in both harnesses
writes: install/skills/execution-methodology/tests/e2e_run.sh
reads: install/skills/execution-methodology/tests/e2e_run.sh, docs/goals/S-7/design.md#interfaces
tests-may-change: install/skills/execution-methodology/tests/e2e_run.sh
needs: T3, T5
gate: install/skills/execution-methodology/tests/e2e_run.sh
**Fixture.** The E-1 fixture gains a two-module map, `a` and `b`, where `b` needs `a`, with
emitter commands. T1 writes `src/a/**` and has no `gate:` line.

**What the run proves, in both harnesses:**
- `next` prints `T1 — <title> · gate: modules: a, b` (AC2);
- `gate.py check --modules a,b` prints two `module` lines and `modules: PASS 2 of 2` (AC3);
- a `receipt --modules all` whose module `b` fails is followed by a planted overlapping registry
  entry and a second `receipt --modules all`, which prints `module a: PASS on this tree (kept)`
  and a load rerun of `b` (AC5).

**Output.** The summary line gains `module map → derived gate → kept and rerun modules`.

## Decisions

- 2026-10-13 planning: the founder chose:
  - a committed map file that the chief drafts and the founder approves with the plan;
  - same-tree reuse only;
  - a module rerun only with load evidence (over "one rerun, flagged flaky");
  - S-6 merged first, without the per-test rerun (founder).
- 2026-10-13 planning: S-6 R24 removed the receipts' end-of-run `load`/`cpus` reading before this
  goal. That reading mostly measured the run itself. S-7 reads load once before an invocation's
  first process, the peak during each run, and other runs from a machine-wide registry. The
  founder flagged the removal (founder; design: default).
- 2026-10-13 planning: the map is JSON at `docs/goals/modules.json`. `tomllib` needs Python 3.11
  and the installer accepts 3.10, and YAML needs a dependency (default; Q4).
- 2026-10-13 planning: `glob_re`, `matches` and `overlap` move to `modmap.py`, because `gate.py`
  needs them and `goal.py` already imports `gate.py` (default).
- 2026-10-13 planning: the plan gate `cd install && ./verify.sh` took 270 to 362 s in S-6's last
  receipts, under the 600 s budget, so it was not timed again (default).
- 2026-10-13 planning: this plan's own tasks carry `gate:` lines, because the map they build does
  not exist until T8 (default).

## Parked

- Q: Load evidence is the invocation's 1-minute load before its first process at or above the CPU
  count, or another `gate.py` run on the machine overlapping the failed module. Confirm, or name
  a threshold such as 0.75 × CPUs.
- Q: A module receipt for Gradle with `--rerun` rather than `--rerun-tasks`. `--rerun` forces that
  module's test task and keeps compilation incremental; with `--rerun-tasks`, a composed full gate
  recompiles once per module. This revises the 2026-10-13 approval answer for module receipts only.
- Q: Coverage proven once per map version, at the first close that uses module receipts: the
  single full gate and every module on one tree, then `gate.py coverage`. The alternative is at
  every close.
- Q: The map at `docs/goals/modules.json`, beside the goals. The alternative is the repository
  root.
- Q: The machine registry under the system temporary directory, outside the repository, holding
  start and end times only.
