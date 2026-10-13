---
goal: S-7
title: Methodology v7.3 — a test-module map picks task gates, can compose the full gate, and retries a failed module once
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

A plan whose `full_gate` is `modules` is done on PASS module receipts for every module on HEAD's
tree, and its approved map is protected (AC4). A second `receipt --modules` on the same tree keeps
passed modules, runs unrun ones, retries a failed one once, and refuses a second failure (AC5).
The packet lists every retried module with both runs' load readings (AC6). `gate.py coverage`
compares the modules' test counts with a full-gate command's (AC7). The skill tells the planner to
draft the map with the plan (AC8). The e2e proves AC2, AC3 and AC5 in both harnesses, and this
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
  - raises `MapError` on invalid JSON, a top-level key other than `replaces`, `modules` or
    `shared`, a `replaces` that is not a non-empty string, or a module key other than `paths`,
    `needs`, `test` or `count`;
  - also raises `MapError` on a name not matching `^[a-z0-9][a-z0-9_-]*$`, or a `count` other
    than `"none"`.
- `problems(m) -> list[str]` returns the five texts of Interface 2, in that order.
- `contained(w, g) -> bool` follows Interface 2.
- `select(m, write_globs) -> list[str]` follows Interface 2 and returns names in file order.
- `unmapped(m, files) -> list[str]`.

**Move from `goal.py`.** `glob_re`, `matches` and `overlap` move into `modmap.py` unchanged.
`goal.py` imports them with `from modmap import glob_re, matches, overlap  # noqa: E402`, next to
its `gate` import, and nothing else in `goal.py` changes.

**Tests: new `tests/test_modmap.py`.** Class `ModMapTest`, using a temporary directory per test:
- `test_load_rejects_unknown_keys_and_bad_names`;
- `test_problems_name_unknown_needs_cycles_missing_fields_and_shared_commands`;
- `test_select_adds_dependents_transitively_in_file_order`:
  - `core`, `fees` needs `core`, `app` needs `fees`;
  - a write under `core/**` selects all three;
  - a write under `app/**` selects `app` alone;
- `test_partially_owned_write_glob_selects_every_module`: with modules owning `src/a/**` and
  `src/b/**` and a third owning `tools/**`, a write of `src/**` selects all three (design review
  R1);
- `test_select_falls_back_to_every_module_on_shared_or_unowned_paths`;
- `test_unmapped_lists_tracked_files_no_glob_covers`.

Do not change `gate.py` or any existing test.

### [ ] T2 — `gate.py`: load readings on every run, as diagnostics
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
- No rule reads the readings.

**Tests in `test_gate.py`.** Copy `ReceiptTest.test_receipt_bound_to_tree_and_command`:
- `test_every_record_and_receipt_carries_load_readings` (AC3);
- `test_load_peak_is_at_least_load_before`.

In `ReceiptTest.test_receipt_omits_removed_load_rerun_metadata`, remove `"cpus"` from the
asserted-absent set. Do not change `goal.py`.

### [ ] T3 — `gate.py --modules`: module runs, same-tree reuse and one retry
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
- `receipt` writes the module's receipt at the Interface 5 key, `"module:<name>\n" + test`, with
  the fields Interface 5 names. The receipt's `command` stays the module's test command.
- `check --modules` writes no receipt and supersedes none.
- Output, exit code and the Interface 7 rules follow the design exactly.

**Tests in `test_gate.py`, new class `ModulesTest`.** It writes a three-module map whose commands
use the existing fixture emitter, and switches the emitter's mode per module through a file the
test writes:
- `test_modules_run_each_command_and_pass_only_when_all_pass` (AC3);
- `test_receipt_keeps_passed_modules_on_the_same_tree` (AC5);
- `test_failed_module_is_retried_once_then_refused` (AC5): it fails, then passes on retry with
  `retry_of`; in a second scenario it fails twice and the third run is refused while the other
  modules run;
- `test_module_receipts_do_not_alias_commands_or_other_modules` (design review R2): a `--cmd`
  receipt of the same command leaves the module receipt alone;
- `test_check_modules_writes_no_module_receipt` (design review R3);
- `test_a_new_tree_reruns_every_module`.

Do not change `goal.py` or `modmap.py`.

### [ ] T4 — `gate.py coverage`, advisory
writes: install/skills/execution-methodology/scripts/gate.py, install/skills/execution-methodology/tests/test_gate.py
reads: docs/goals/S-7/design.md#interfaces, install/skills/execution-methodology/scripts/gate.py, install/skills/execution-methodology/tests/test_gate.py
tests-may-change: install/skills/execution-methodology/tests/test_gate.py
needs: T3
gate: python3 -m unittest discover -s install/skills/execution-methodology/tests -t install/skills/execution-methodology/tests -p 'test_gate.py'
Design Interface 8.

**The command.** `gate.py coverage --goal <id> [--cmd "<full gate>"] [--runs DIR]`:
- `--cmd` defaults to the map's `replaces`, and exits 2 when neither is given;
- refuses a dirty tree, with the same message as `receipt`;
- runs nothing and writes nothing;
- prints the Interface 8 line, and exits 0 when the counts are equal, 1 otherwise.

It reads the receipt of `--cmd` and each module's receipt at the Interface 5 key, so it never
parses the plan (design review R15).

**Tests in `test_gate.py`, class `CoverageTest`:**
- `test_coverage_reports_equal_counts` (AC7);
- `test_coverage_names_missing_module_receipts_and_short_sums` (AC7);
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
- `KEYS` validation accepts the literal `full_gate: modules`.
- When the plan sets `full_gate: modules`, `lint` adds Interface 3's two errors, with their exact
  texts.

**Derived gate.**
- New `task_gate(ctx, task) -> str` returns:
  - the task's `gate:` line when it has one;
  - otherwise, with a map, `modules: a, b` from `select(map, task["writes"])`;
  - otherwise `""`.
- `cmd_next` and the approval page's Gate column use it. The column shows `plan gate` when it is
  empty.

**Approval table.** When the plan sets `full_gate: modules`, `approval_page` adds Interface 4's
"Full gate" table and its instruction line, with every value through `html.escape`.

**Tests in `test_goal.py`, class `ModuleMapTest`, copying `TaskFieldTest`:**
- `test_lint_fails_on_a_broken_map_and_warns_about_unmapped_files` (AC1);
- `test_next_and_approval_show_the_derived_gate` (AC2);
- `test_a_gate_line_overrides_the_map`;
- `test_full_gate_modules_needs_replaces_and_a_non_test_module` (AC4);
- `test_approval_page_lists_the_replaced_command_beside_every_module` (AC4).

### [ ] T6 — `goal.py`: `full_gate: modules` at done row 7, the protected map at row 4, retried modules in the packet
writes: install/skills/execution-methodology/scripts/goal.py, install/skills/execution-methodology/tests/test_goal.py
reads: docs/goals/S-7/design.md#interfaces, install/skills/execution-methodology/scripts/goal.py, install/skills/execution-methodology/tests/test_goal.py
tests-may-change: install/skills/execution-methodology/tests/test_goal.py
needs: T5
gate: python3 -m unittest discover -s install/skills/execution-methodology/tests -t install/skills/execution-methodology/tests -p 'test_goal.py'
Design Interfaces 9 and 10.

**`done_rows`.**
- When the plan's `full_gate` is `modules`, row 7 applies Interface 9 with its exact messages. Each
  module's receipt is read at `receipt_path(root, goal, tree, "module:<name>\n" + test)` and must
  have `module == name` and `verdict == "PASS"`.
- `protected_entries` adds `docs/goals/modules.json` when that file exists at the approval tag, so
  row 4 rejects a task whose writes reach it (design review R12).

**Packet.** `cmd_packet` adds the `Retried modules:` section after `Receipts:`, with lines exactly
as Interface 10 gives them.

**Tests in `test_goal.py`, class `ModuleRowTest`.** Fixtures write receipts directly:
- `test_module_receipts_satisfy_row_7_for_full_gate_modules` (AC4);
- `test_row_7_names_a_missing_module_or_an_unmapped_file` (AC4);
- `test_unapproved_map_change_fails_row_4` (AC4, design review R12);
- `test_packet_lists_retried_modules_with_load_readings` (AC6).

### [ ] T7 — v7.3 in words: D33, the skill's step 5, planning's map, close's composed gate and retry
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
- `planning.md` step 5 carries Interface 11's map-drafting text, including:
  - the count-none module that runs the replaced command with its tests switched off;
  - `replaces`;
  - the Decisions line naming the module that runs each non-test check.
- `close.md` carries Interface 11's composed full gate and the one-retry rule.

**D33.** Add it directly after D32's last line, with no blank line between, because the protected
range `D1-D32` counts a trailing blank line. It records:
- what changes;
- the founder's answers of 2026-10-13: a committed map, same-tree reuse, and one retry regardless,
  which replaced the load-gated retry the founder first chose;
- S-6 R24's removal of the end-of-run load reading, and the diagnostic readings that replace it;
- the rejected options.

**Methodology page and `AGENTS.md`.** `docs/architecture/methodology.md` gets the v7.3 title, a
D33 link and a "Module map" bullet. `AGENTS.md` says v7.3 and links D33.

**Tests in `test_rules.py`:**
- `Loop.test_step_5_names_the_modules_next_derives`;
- `Close.test_close_composes_the_full_gate_from_modules_and_states_the_retry`;
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

**The map.** `docs/goals/modules.json`, with `"replaces": "cd install && ./install.sh --dry-run &&
./verify.sh"`, and these modules in this order:

| Module | Paths | Needs | Test |
|---|---|---|---|
| `modmap` | `scripts/modmap.py`, `tests/test_modmap.py` | none | `-p 'test_modmap.py'` |
| `gate` | `scripts/gate.py`, `tests/test_gate.py` | `modmap` | `-p 'test_gate.py'` |
| `goal` | `scripts/goal.py`, `tests/test_goal.py` | `gate`, `modmap` | `-p 'test_goal.py'` |
| `docs` | `scripts/docs.py`, `tests/test_docs.py` | `goal` | `-p 'test_docs.py'` |
| `guard` | `scripts/guard.py`, `scripts/git-hooks.sh`, `tests/test_guard.py`, `tests/test_git_hooks.py` | none | `-p 'test_g*.py'` |
| `rules` | `SKILL.md`, `references/**`, `agents/**`, `tests/test_rules.py` | none | `-p 'test_rules.py'` |
| `install` | `install/install.sh`, `install/tests/**`, `install/*.md` | `guard`, `rules`, `docs` | see below |
| `repository` | `docs/**`, `*.md`, `install/verify.sh`, `.claude/**`, `.github/**`, `LICENSE`, `.gitignore`, `install/skills/.gitignore` | `guard`, `docs`, `install` | see below |

- Paths and tests in the `modmap` to `rules` rows are relative to
  `install/skills/execution-methodology/`.
- Each of those tests is `python3 -m unittest discover -s
  install/skills/execution-methodology/tests -t install/skills/execution-methodology/tests`
  followed by the row's `-p` argument. The `guard` row's pattern is chosen so that `test_gate.py`
  and `test_goal.py` stay out; if it does not, use two commands joined with `&&`.
- `install` runs `python3 -m unittest discover -s install/tests -t install/tests`.
  - It needs `guard`, because its tests run `git-hooks.sh` and `tree_scan.py` with the guard.
  - It needs `rules`, because `test_size.py` counts `SKILL.md`.
  - It needs `docs`, because `link_check.py` imports `docs.py`.
- `repository` has `"count": "none"` and runs `cd install && ./install.sh --dry-run && ./verify.sh
  --no-suites`. It needs the modules whose scripts that command executes (design review R11).
- `shared` is `install/skills/execution-methodology/tests/fixtures/**`,
  `install/skills/execution-methodology/tests/e2e_run.sh` and `install/global.md`.

**Tests: new `install/tests/test_map.py`**, class `RepositoryMapTest`:
- `test_map_loads_with_no_problems` (AC9);
- `test_every_tracked_file_is_covered` (AC9);
- `test_selection_includes_repository_and_docs_consumers`: a write to `install/tests/link_check.py`
  selects `install` and `repository`, and a write to `scripts/goal.py` selects `goal`, `docs`,
  `install` and `repository` (design review R11);
- `test_no_suites_skips_both_run_suite_lines`, which reads `verify.sh`'s text.

S-7 keeps its single `full_gate` command; the map is built during it. At close the chief runs
`gate.py coverage` on this repository once and records the result in a Decisions line.

### [ ] T9 — `e2e_run.sh`: derived gates, module runs and the retry in both harnesses
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
- a `receipt --modules all` whose module `b` fails once is followed by a second `receipt --modules
  all`, which prints `module a: PASS on this tree (kept)` and the retry of `b` passing (AC5).

**Output.** The summary line gains `module map → derived gate → kept and retried modules`.

## Decisions

- 2026-10-13 planning: the founder chose:
  - a committed map file that the chief drafts and the founder approves with the plan;
  - same-tree reuse only;
  - S-6 merged first, without the per-test rerun;
  - after the first design draft, one retry of a failed module regardless of load, in place of a
    retry gated on load evidence (founder).
- 2026-10-13 design review (BLOCK, 12 blocking findings), resolved in the design:
  - **Removed with the load-gated retry.** R5 to R10 and R14 concerned the load evidence and the
    registry, which the founder's one-retry rule removed.
  - **Partially owned writes.** R1: a write glob not wholly inside one module selects every module.
  - **Receipt keys.** R2: module receipts use a key per module, and two modules sharing a command
    is a lint error.
  - **Supersession.** R3: `check --modules` writes and supersedes no module receipt, so the retry
    state lives only in module receipts.
  - **Coverage.** R4, R13, R15 and R16: coverage is advisory and takes `--cmd`. Row 7 accepts module
    receipts only when the plan's `full_gate` is `modules`, so no count certificate stands in for
    equivalence.
  - **This repository's map.** R11: `needs` corrected and guard and hooks merged into one module,
    because their tests use each other.
  - **Approval of map changes.** R12: the approved map counts as a protected path (default).
- 2026-10-13 planning: with `full_gate: modules`, a non-test check missing from the map would stop
  running unflagged (founder). The map therefore names the command it `replaces`. Lint requires
  `replaces` and a count-none module, and that module runs the replaced command with its tests
  switched off, so checks added later stay in. The approval page puts the replaced command beside
  every module for the founder to check (founder).
- 2026-10-13 planning: the load readings stay, as diagnostics shown beside a retry. S-6 R24 had
  removed the end-of-run reading, which mostly measured the run itself, and the founder flagged
  that removal (default).
- 2026-10-13 planning: the map is JSON at `docs/goals/modules.json`. `tomllib` needs Python 3.11
  and the installer accepts 3.10, and YAML needs a dependency (default; Parked question).
- 2026-10-13 planning: `glob_re`, `matches` and `overlap` move to `modmap.py`, because `gate.py`
  needs them and `goal.py` already imports `gate.py` (default).
- 2026-10-13 planning: the plan gate `cd install && ./verify.sh` took 270 to 362 s in S-6's last
  receipts, under the 600 s budget, so it was not timed again (default).
- 2026-10-13 planning: this plan's own tasks carry `gate:` lines, because the map they build does
  not exist until T8 (default).

## Parked

- Q: A module receipt for Gradle with `--rerun` rather than `--rerun-tasks`. `--rerun` forces that
  module's test task and keeps compilation incremental; with `--rerun-tasks`, a composed full gate
  recompiles once per module. This revises the 2026-10-13 approval answer for module receipts only.
- Q: Once approved, the map is protected: a new test directory mid-goal waits for the founder, and
  a goal with `full_gate: modules` cannot finish until the map covers it. The alternative is that
  a task may change the map with a Decisions line, which the merge review then judges.
- Q: The map at `docs/goals/modules.json`, beside the goals. The alternative is the repository
  root.
