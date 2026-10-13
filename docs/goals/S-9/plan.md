---
goal: S-9
title: S-8's follow-ups, and the pilot's end
gate: cd install && ./verify.sh
full_gate: cd install && ./install.sh --dry-run && ./verify.sh
milestones:
  M1: {tasks: [T1, T2, T3, T4], e2e: "install/skills/execution-methodology/tests/e2e_run.sh"}
touches: [interface]
protected: [docs/decisions/decisions.md#D1-D34, docs/goals/S-9/design.md#interfaces, docs/goals/S-9/design.md#data-touched]
---

## Outcome

A decision appended after the last protected one passes done row 4, while a changed protected
line still fails it (AC1). Cleanup's fetch refusal quotes git's `fatal:` line (AC2). `gate.py`'s
usage names its `--modules` refusals (AC3). The skill removes a builder's branch with its worktree
after the task's commit, and the close pushes `goal/<id>/approved` with the milestone tag (AC4).
D35 ends the pilot and D29's stop rule (AC5). `methodology.md` and `repository-standard.md` state
what is true now, and no page is stale after the last commit (AC6). Spec: [spec.md](spec.md).
Design: [design.md](design.md).

## Tasks

### [ ] T1 — Row 4 ignores a protected section's trailing blank lines; cleanup quotes git's `fatal:` line
writes: install/skills/execution-methodology/scripts/goal.py, install/skills/execution-methodology/tests/test_goal.py
reads: docs/goals/S-9/design.md#interfaces, install/skills/execution-methodology/scripts/goal.py, install/skills/execution-methodology/tests/test_goal.py
tests-may-change: install/skills/execution-methodology/tests/test_goal.py
AC1, AC2. Design Interfaces 1 and 2.
- **Row 4.** In `done_rows`, the anchored comparison (`protected_text(file_at(ctx.root, parent,
  path) …, anchor) != protected_text(file_at(ctx.root, c, path), anchor)`) compares both sides
  after a module-level helper `settled(text)`, which returns `re.sub(r"(\n[ \t]*)+\Z", "",
  text or "")`: trailing empty or whitespace-only lines dropped, every other byte kept. Leave
  `protected_text` and the whole-file comparison unchanged.
- **Cleanup.** In `cmd_cleanup`, the failed-fetch reason becomes the first line of `proc.stderr`
  that starts `fatal:`, stripped, falling back to `last_line(proc.stderr)`. The timeout reason and
  every other message stay unchanged.

Add tests only; do not change an existing test, the map, or any other row.

Tests:
- **`ProtectedSectionTest`** (its plan protects `#D1-D2`, and the unprotected D3 follows). New
  test `test_whitespace_before_an_unprotected_section_remains_protected` (AC1, design review R1):
  a `[T1]` commit changing `Two.` to `Two.  ` (two trailing spaces) is reported by row 4 as
  `<sha10> [T1] changes protected docs/record.md#D1-D2`.
- **New class `ProtectedLastSectionTest(RepoCase)`.** Its plan and `setUp` copy
  `ProtectedSectionTest`'s, except that it protects `docs/record.md#D1-D3`. Its tests:
  - `test_appending_after_the_last_protected_section_passes` (AC1):
    1. A `[T1]` commit appends `"\n## D4 — fourth\n\nFour.\n"` to `RECORD`, and row 4 is ok.
    2. A later `[T1]` commit changes `Three.` to `Three, revised.`, and row 4 reports `<sha10> [T1]
       changes protected docs/record.md#D1-D3`.
  - `test_last_content_line_whitespace_remains_protected` (AC1, design review R1): a `[T1]` commit
    changing `Three.` to `Three.  ` at the end of the file is reported by row 4.

  Copy `test_protected_section_edit_is_rejected`'s use of `self.fix`, `assertRowOk` and
  `assertRow`.
- **`CleanupTest.test_cleanup_refusal_quotes_gits_fatal_line`** (AC2). In a `Repo()` without a
  remote, `goal.py cleanup --goal F-9` exits 2. Its stderr is exactly `goal.py: cleanup needs
  origin/main: fatal: 'origin' does not appear to be a git repository\n`.

### [ ] T2 — `gate.py`'s usage names the `--modules` refusals
writes: install/skills/execution-methodology/scripts/gate.py, install/skills/execution-methodology/tests/test_gate.py
reads: docs/goals/S-9/design.md#interfaces, install/skills/execution-methodology/scripts/gate.py, install/skills/execution-methodology/tests/test_gate.py
tests-may-change: install/skills/execution-methodology/tests/test_gate.py
AC3. Design Interface 3. In the module docstring's `--modules` paragraph (it begins "`--modules`
runs each named module"), add after its last sentence:

"An empty selection, or a selected module whose test command is blank, is refused with exit 2
before anything runs."

Change no code. Test in class `ModulesTest`, `test_usage_names_the_modules_refusals` (AC3):
`gate.__doc__` contains `An empty selection, or a selected module whose test command is blank,
is refused with exit 2`.

### [ ] T3 — Loop step 4 removes the builder's branch; the close pushes the approval tag; D35
writes: install/skills/execution-methodology/SKILL.md, install/skills/execution-methodology/references/close.md, install/skills/execution-methodology/tests/test_rules.py, docs/decisions/decisions.md, AGENTS.md
reads: docs/goals/S-9/design.md#interfaces, install/skills/execution-methodology/SKILL.md, install/skills/execution-methodology/references/close.md, install/skills/execution-methodology/tests/test_rules.py, install/tests/test_size.py, docs/decisions/decisions.md#d34--post-merge-cleanup-the-chief-records-its-worktrees-and-removes-what-originmain-holds-s-8
tests-may-change: install/skills/execution-methodology/tests/test_rules.py
needs: T1
AC4, AC5. Design Interfaces 4 and 5.

**`SKILL.md`.** In loop step 4, "remove its worktree after the commit" becomes "remove its
worktree and branch after the commit". Nothing else in `SKILL.md` changes. The always-loaded files
are 1,341 of 1,350 words today, and this edit and `AGENTS.md`'s link add at most 3.

**`close.md`, "Milestone close".**
- **Step 1** becomes "The PR's head is the commit `done` passed; it is the milestone's."
- **Step 3's push** becomes `` `git push origin goal/<id>/approved goal/<id>/<milestone>` ``.
- Nothing else changes.

**D35 in `docs/decisions/decisions.md`.**
- Append `## D35 — The pilot and its stop rule have ended (S-9)` after D34, in D34's shape: Chose,
  Over, Why, Reverses. Its content is Interface 5.
- Put one blank line before the heading, as the other sections have it. This is AC1's live case:
  T1 makes row 4 accept it.
- Add a D35 table row dated 2026-10-13, `standing`.
- D29's row status, `standing; pilot clause amended by D30`, becomes `standing; pilot clause
  amended by D30, ended by D35`.
- Add a D35 clause to the frontmatter `summary`, which `docs.py` caps at 120 words. Shorten other
  clauses if needed.
- D1–D34 stay byte-identical.

**`AGENTS.md`.** Add the D35 link after D34 in the Decisions line.

**Tests in class `Close`.**
- In `test_close_merges_tags_the_head_then_cleans_up`, the expected push string becomes `` `git
  push origin goal/<id>/approved goal/<id>/<milestone>` ``; the order assertions stay.
- New: `test_the_loop_removes_the_builders_worktree_and_branch` (AC4). `loop_step(4)` contains
  `remove its worktree and branch after the commit`.

Run `docs.py lint .` and `docs.py index .` if the index is out of date. The generated
`docs/README.md` is outside this task's writes, so report it and stop rather than edit it.

### [ ] T4 — Pages: the stop rule as ended rationale; `modules.json` as a current-state file
writes: docs/architecture/methodology.md, docs/architecture/repository-standard.md, docs/product/measurements.md, docs/README.md, .claude/rules/**
reads: docs/goals/S-9/design.md#interfaces, docs/architecture/methodology.md, docs/architecture/repository-standard.md, docs/product/measurements.md, install/skills/execution-methodology/SKILL.md, install/skills/execution-methodology/references/close.md
tests-may-change: none
needs: T1, T2, T3
gate: python3 -m unittest discover -s install/skills/execution-methodology/tests -t install/skills/execution-methodology/tests -p 'test_docs.py' && cd install && ./install.sh --dry-run && ./verify.sh --no-suites
AC6.

**`methodology.md`.**
- **The amended stop rule** (the Shape bullet) becomes ended rationale. The pilot and D29's stop
  rule ended with D35, and a change to `install/` is an ordinary goal the founder approves.
- **The Accepted risks** "Stop rule" bullet keeps its triggers, introduced as "Until D35 ended
  it".
- **The intro.** Add the missing comma after the D29 link and a D35 link after D34.
- **The close bullet.** It says the close pushes `goal/<id>/approved` with the milestone tag.
- **`summary`.** "the accepted risks with the amended stop rule" becomes "the accepted risks, the
  ended stop rule".

**`repository-standard.md`.** In "Records and pages", the records become `decisions.md`,
`measurements.md` and `docs/goals/<id>/**`. Then add: "`docs/goals/modules.json` states the
current map." Check that the dangling-name check in `install/verify.sh` still passes.

**`measurements.md`.** `read-when` becomes "Citing a number or recording a measurement". The body
is a record and stays.

Set `last-verified: 2026-10-13` on `methodology.md` and `repository-standard.md`. Then run
`docs.py index .` and `docs.py pointers .` and include their output. Change no `install/` file.

After the commit, the chief runs `python3 install/skills/execution-methodology/scripts/docs.py
stale .`. It must print `docs.py stale: PASS`, and the chief records its output in a Decisions
line. That plan-only commit and any merge-review fix may make a page stale again; AC6 is judged at
T4's commit (design review R2).

## Decisions

- 2026-10-13 planning:
  - **The founder's answers.**
    - The pilot ended; nothing replaces the stop rule.
    - Row 4 is fixed, not warned about.
    - One small goal.
    - S-8's leftovers were removed by hand after PR 59.
    - The builder's worktree and branch are removed after the task commit.
    - The close pushes both tags (founder).
- 2026-10-13 planning: loop step 4 already says to remove the builder's worktree after the
  commit. S-8 kept T4's on purpose, to exercise cleanup, so only "and branch" is added (default).
- 2026-10-13 planning:
  - **`touches: [interface]`.** Done row 4's judgement and the skill's words are durable
    interfaces, so the goal has a design and a design review.
  - **T3 needs T1.** D35 is then appended with a normal blank line, as AC1's live case (default).
- 2026-10-13 planning: T1–T3 carry no `gate:` and run the modules `goal.py next` derives. T4's gate
  is S-8 T5's (default).
- 2026-10-13 planning: the plan's `gate` was not timed again. S-8's last full-gate receipt, a
  superset of it, took 279 s, within the 600 s budget (default).
- 2026-10-13 design review (BLOCK, 3 blocking), resolved in the spec, design and plan:
  - **R1.** `settled` drops only trailing empty or whitespace-only lines, not `.rstrip()`. T1 adds
    `test_last_content_line_whitespace_remains_protected` for a range at end of file and one
    followed by an unprotected section.
  - **R2.** AC6 is judged at T4's commit, as S-8's AC8 was. `repository-standard.md` covers
    `docs/**`, so later plan-only and fix commits can make it stale again (default).
  - **R3.** T1 and T2 list their test files under `tests-may-change`; row 5 judges test files, not
    test methods.

## Parked
