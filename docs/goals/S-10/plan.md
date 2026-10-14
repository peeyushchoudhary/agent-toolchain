---
goal: S-10
title: The README's seven questions, the repository rules in the skill, and a shipped link check
gate: cd install && ./verify.sh
full_gate: cd install && ./install.sh --dry-run && ./verify.sh
milestones:
  M1: {tasks: [T1, T2, T3, T4], e2e: "install/skills/execution-methodology/tests/e2e_run.sh"}
touches: [interface]
protected: [docs/decisions/decisions.md#D1-D35, docs/goals/S-10/design.md#interfaces, docs/goals/S-10/design.md#data-touched]
---

## Outcome

`docs.py links` ships with the skill. It lists every broken relative link or anchor in
`README.md`, `AGENTS.md` and `docs/`, and every `AGENTS.md` without its `@AGENTS.md` twin (AC1,
AC2). `docs.py pointers` writes that twin with each `AGENTS.md` it creates, and `lint` no longer
treats a `CLAUDE.md` as a page (AC2). A README's `covers` comment puts it under `docs.py stale`
(AC3). `verify.sh` runs `docs.py links` in place of the unshipped `link_check.py` (AC4). The
skill ships `references/repository.md` with the README's seven sections and the layout, agent-file
and lifecycle rules; `planning.md` and `close.md` point to it; `global.md` tells both harnesses to
read the `AGENTS.md` files on the way to a file; D36 records it; a runbook migrates a repository
after grepping each path's readers (AC5). This
repository's README answers the seven questions (AC6). Spec: [spec.md](spec.md). Design:
[design.md](design.md).

## Tasks

### [ ] T1 — `docs.py links`, `CLAUDE.md` twins, and the README's `covers` comment
writes: install/skills/execution-methodology/scripts/docs.py, install/skills/execution-methodology/tests/test_docs.py
reads: docs/goals/S-10/design.md#interfaces, install/skills/execution-methodology/scripts/docs.py, install/skills/execution-methodology/tests/test_docs.py, install/tests/link_check.py, install/tests/test_install.py
tests-may-change: install/skills/execution-methodology/tests/test_docs.py
AC1, AC2, AC3. Design Interfaces 1–4.

**`links(root)`**, a new module-level function returning findings, wired into `main` beside `lint`
and `stale` with the same verdict line (`docs.py links: PASS` or `FAIL (<n>)`) and exit codes.
- Port `install/tests/link_check.py`'s `check_links` loop: the files are `README.md`, `AGENTS.md`
  and `git ls-files docs/*.md`, skipping a missing file. External links (`https:`, `http:`,
  `mailto:`) are skipped.
- Before matching `\]\(<?([^)\s>]+)` on a line outside a fence, remove its inline code spans
  (`re.sub(r"(`+).+?\1", "", line)`).
- **Anchors.** A target with `#anchor` whose path is empty means the same file. When the target is
  a `.md` file, the anchor (lowercased) must be in `anchors(headings(<target lines>))`, or match
  `d(\d+)` with a heading of the target starting `D<number>` (case-insensitive, word boundary).
  Anchors on other files are not checked.
- **Twins.** For each path from `git ls-files -z --cached --others --exclude-standard --
  ':(glob)**/AGENTS.md'`, the sibling `CLAUDE.md` must exist and hold a line equal to
  `@AGENTS.md`.
- Findings, in this order: links in file order, then twins sorted by path. The texts are Interface
  1's.

**`pages`** also excludes paths ending `/CLAUDE.md`.

**`pointers`.** When it writes an `AGENTS.md` that did not exist (`have is None` and `rel in
blocks`), and no `CLAUDE.md` exists in that directory, it writes `CLAUDE.md` with `@AGENTS.md\n`
right after and prints `<dir>/CLAUDE.md: written`. `--check` is unchanged.

**`stale`.** After the pages, `README.md`, if it has a line that is exactly
`<!-- covers: [<globs>] -->`. The globs are split on commas, stripped of spaces and quotes, and
kept when `relative()`. When the covered paths' last commit is later than `README.md`'s own last
commit (committer timestamps, compared as in the pages' same-day rule), add `README.md: <last>
after README.md's last commit <own>`.

**Docstring.** The first line adds `links [ROOT]`. Add one paragraph for `links` and one sentence
to `stale`'s paragraph for the README.

Tests in `test_docs.py`:
- New class **`LinksTest(DocsCase)`**:
  - `test_links_anchors_and_twins_pass` (AC1, AC2). `README.md` links `docs/record.md#d17`,
    `docs/record.md#d17--zeta-rule-v2`, `docs/record.md#d18-other-thing` and
    `docs/record.md#detail`. `AGENTS.md` sits beside a `CLAUDE.md` holding `@AGENTS.md`. Result:
    exit 0, `docs.py links: PASS`.
  - `test_bad_links_and_anchors_are_listed` (AC1). In `README.md`:
    - line 1 links `docs/none.md`;
    - line 2 links `docs/record.md#d17--nonexistent`;
    - line 3 links `docs/record.md#d99`;
    - line 4 links `#nowhere`;
    - line 5 holds a link to `docs/none.md` inside inline code (backticks around the whole link);
    - lines 6–8 are a fenced block holding the same link.

    The output is exactly `README.md:1: docs/none.md`, `README.md:2:
    docs/record.md#d17--nonexistent`, `README.md:3: docs/record.md#d99`, `README.md:4: #nowhere`,
    `docs.py links: FAIL (4)`. Exit 1.
  - `test_agents_md_twins` (AC2). `sub/AGENTS.md` without a `CLAUDE.md` gives `sub/CLAUDE.md:
    missing; it holds the line @AGENTS.md`. Then `sub/CLAUDE.md` holding `hello\n` gives
    `sub/CLAUDE.md: no @AGENTS.md line`.
- **`PointersTest.test_first_generation_writes_the_rule_file_and_a_new_agents_md`.** The expected
  lines gain `src/a/CLAUDE.md: written` after `src/a/AGENTS.md: written`, and `tests/CLAUDE.md:
  written` after `tests/AGENTS.md: written`. `tests/CLAUDE.md` reads `@AGENTS.md\n`.
- New **`PointersTest.test_a_claude_md_under_docs_is_not_a_page`** (AC2). `docs/CLAUDE.md` holding
  `@AGENTS.md\n`, committed, passes `lint`.
- New **`StaleTest.test_a_readme_covers_comment`** (AC3).
  1. `README.md` holds `# R\n\n<!-- covers: [src/a/**] -->\n` and is committed at
     `2026-10-01T10:00:00+02:00`, and `stale` does not list it.
  2. A `src/a/y.py` commit at `10:01` lists `README.md: 2026-10-01T10:01:00+02:00 after
     README.md's last commit 2026-10-01T10:00:00+02:00`.
  3. A README without the comment line is never listed.

Do not change `lint`'s checks beyond `pages`, any other test, the map, or any file outside the
writes.

### [ ] T2 — `verify.sh` runs `docs.py links`; `link_check.py` is removed; `docs/CLAUDE.md`
writes: install/verify.sh, install/tests/link_check.py, install/tests/test_install.py, install/tests/test_map.py, install/README.md, docs/CLAUDE.md
reads: docs/goals/S-10/design.md#interfaces, install/verify.sh, install/tests/test_install.py, install/tests/test_map.py, install/README.md
tests-may-change: install/tests/test_install.py, install/tests/test_map.py
needs: T1
AC4, AC2.
- **`verify.sh`, section 5.** The comment reads "Relative links and anchors in AGENTS.md,
  README.md and docs/**/*.md resolve, and each AGENTS.md has its CLAUDE.md twin (the skill's
  docs.py links)." The command becomes `check links python3
  "$ROOT/install/skills/execution-methodology/scripts/docs.py" links "$ROOT"`. The failure id stays
  `links`.
- Delete `install/tests/link_check.py`, and the class `LinkCheckTest` in `test_install.py`, whose
  case `LinksTest` now carries.
- **`test_map.py`.** In `test_selection_includes_repository_and_docs_consumers`, the entry
  `("install/tests/link_check.py", ["install", "repository"])` becomes
  `("install/tests/tree_scan.py", ["install", "repository"])`.
- **`install/README.md`.** "the docs link check (`tests/link_check.py`)" becomes "the docs link and
  twin check (the skill's `docs.py links`)".
- **`docs/CLAUDE.md`** holds `@AGENTS.md\n`.
- New test **`test_install.py::LinksInVerify.test_verify_runs_the_shipped_link_check`** (AC4).
  `install/verify.sh` contains `docs.py" links "$ROOT"` and does not contain `link_check.py`.

### [ ] T3 — The repository reference, the reading rule, D36 and the layout runbook
writes: install/skills/execution-methodology/references/repository.md, install/skills/execution-methodology/references/planning.md, install/skills/execution-methodology/references/close.md, docs/architecture/repository-standard.md, install/global.md, AGENTS.md, docs/decisions/decisions.md, docs/runbooks/migrate-layout.md, docs/architecture/methodology.md, docs/product/measurements.md, docs/README.md, docs/AGENTS.md, .claude/rules/**, install/tests/test_records.py, install/skills/execution-methodology/tests/test_rules.py
reads: docs/goals/S-10/design.md#interfaces, docs/architecture/repository-standard.md, install/skills/execution-methodology/references/planning.md, install/skills/execution-methodology/references/close.md, install/global.md, AGENTS.md, docs/decisions/decisions.md#d35--the-pilot-and-its-stop-rule-have-ended-s-9, docs/runbooks/migrate-v5.md, docs/architecture/methodology.md, docs/product/measurements.md, install/tests/test_records.py, install/tests/test_size.py, install/verify.sh
tests-may-change: install/tests/test_records.py, install/skills/execution-methodology/tests/test_rules.py
needs: T2
AC5. Design Interfaces 4–7.

**New `install/skills/execution-methodology/references/repository.md`.** Design Interface 7, as
prose, at most 900 words.
- Its four sections are `## The README`, `## Layout`, `## Agent files` and `## Lifecycle`.
- The product minimum closes `## Layout`. Move it word for word from `repository-standard.md`'s
  last paragraph, and add `docs.py links` to the gate.
- No frontmatter: it is a skill reference, not a `docs/` page.
- Name no project, and no name `verify.sh`'s dangling-name scan lists.

**`planning.md`.**
- Under "Chief's planning rules", MUST, add: "Give a milestone that changes what the repository
  ships a last task with `writes: README.md` and a criterion naming the README's new Current
  state."
- After the `docs/` frontmatter template, add one line: "Where files go, what the README answers
  and how records age:", then a Markdown link whose text and target are both `repository.md`.

**`close.md`.** After step 4, add one line: "Archiving or untracking anything at a close follows",
then a Markdown link with text `repository.md` and target `repository.md#lifecycle`.

**`repository-standard.md`.**
- **Layout block.** The `README.md` row reads "front page for a human: the seven sections of the
  skill's `references/repository.md`".
- **After the block,** one sentence: the rules every repository follows (README, layout, agent
  files, lifecycle, the product minimum) are the skill's `references/repository.md`, and this page
  is how this repository applies them. Link the reference by its relative path.
- **Last paragraph.** Replace the product-minimum paragraph with that link.
- **Enforcement paragraph.** The link check is `docs.py links`.
- **Frontmatter.** Update `summary` (at most 120 words); `last-verified: 2026-10-14`.

**`global.md`.** Append design Interface 6's sentence as its own paragraph after the skill
paragraph.

**`AGENTS.md`.** The reference's agent-files rule applies here too (D17).
- Move the `## Verification` section up to follow the opening paragraph, so the gate is within
  the first 15 lines.
- Delete that section's last sentence (from "It includes the link check").
- Add the D36 link after D35.
- The always-loaded total stays at most 1,350 (`test_size.py`). Today it is 1,344, and these edits
  net about −1.

**D36 in `decisions.md`.**
- Append `## D36 — The README answers seven questions again; the repository rules ship with the
  skill; docs.py links (S-10)` after D35, in D35's shape, with one blank line before the heading.
  - **Chose:**
    - Interface 7's reference, shipped in the skill, with no presence check;
    - `docs.py links`, added to each repository's gate at its layout migration;
    - every `AGENTS.md` with its twin;
    - `global.md`'s reading rule.
  - **Over:**
    - the council's five README sections, or a one-paragraph rule;
    - the rules only in `repository-standard.md`;
    - v6's validator and its full naming rules;
    - the link check inside `lint`;
    - a generated routing table.
  - **Why:**
    - Five audits and a structure council on 2026-10-14 found every README's status stale.
    - The standard is not installed.
    - Broken links passed product gates.
    - Six `AGENTS.md` files are never loaded.
    - Product gates and code read files in tool folders.
    - The founder chose the seven sections, the shipped reference, the naming rule and lessons as
      a record (2026-10-14).
  - **Reverses:** D29's removal of the README contract, as prose.
- **Table.**
  - Add a D36 row, dated 2026-10-14 and `standing`.
  - D1's status `superseded by D29` becomes `superseded by D29; its questions restored as prose by
    D36`.
  - D17's status `standing` becomes `standing; its layout and validator superseded by D30 and
    D36`.
  - D18's status `standing` becomes `standing; the README beside it removed at S-1`.
  - Add a D36 clause to `summary`, which stays at most 120 words.
- D1–D35's text stays byte-identical.

**New `docs/runbooks/migrate-layout.md`,** with frontmatter (`covers: []`). Numbered steps for a
product repository at a milestone boundary, on a branch:
1. Before moving, archiving or untracking any path, `git grep -n <path> -- ':!*.md'`. Repoint each
   reader in the same commit; a path that code or the gate reads stays put. Code, build roots and
   domain content are never moved or renamed.
2. Move whatever a tool folder holds that is still read into its home, and delete the `!`
   re-include for it.
3. Untrack tool output: add it to `.gitignore`, then `git rm -r --cached`.
4. Bring each kind to one home, keeping the home already cited. Replace copied history with one
   row in `docs/archive/README.md` that names a commit on `origin/main`.
5. Drop gate steps, Make targets, PR-template lines and tracked hooks that call or name tools the
   skill no longer installs, so the gate passes on a fresh clone.
6. Add each missing `CLAUDE.md` twin, and move the gate into the root `AGENTS.md`'s first 15
   lines.
7. Rewrite `README.md` to the seven sections, with its `covers` comment.
8. Add `docs.py links` to the gate. Run `docs.py lint`, `docs.py links`, `docs.py stale` and the
   full gate.

Rollback: `git revert`. Name no project, and no name `verify.sh`'s dangling-name scan lists.

**`methodology.md`.**
- In the "Disclosure in layers" bullet, "a marked block in the nearest `AGENTS.md` for Codex"
  becomes "a marked block in the nearest `AGENTS.md`, which `global.md`'s reading rule has both
  harnesses read".
- Add that `docs.py links` checks links, anchors and twins, and that `references/repository.md`
  carries the README, layout and lifecycle rules.
- The Accepted risks line "The pilot's sampled follow-up reviews make the comparison." becomes "No
  comparison has run since D35 ended the pilot."

**`measurements.md`.**
- `summary`'s "the pilot's measures with their definitions and its stop rule" becomes "the ended
  pilot's measures, definitions and stop rule".
- The `## Pilot` section gains a first line: "Ended by D35 on 2026-10-13; kept as the record."

Regenerate with `docs.py index .` (into `docs/README.md`'s table) and `docs.py pointers .`.

Tests:
- **`test_records.py::RecordsTest.test_d36_ships_the_repository_rules`** (AC5). Copy
  `test_d35_ends_the_pilot_and_updates_d29`'s shape.
  - `decisions.md` holds D36's heading line.
  - D1's table row contains `restored as prose by D36`, and D17's contains `superseded by D30 and
    D36`.
  - D36's row ends `| standing |`.
  - `install/global.md` contains `read each AGENTS.md between the repository root and it`.
- **`test_rules.py`**, new class `Repository`:
  - `test_the_reference_carries_the_readme_layout_and_lifecycle` (AC5). `references/repository.md`:
    - has the headings `## The README`, `## Layout`, `## Agent files`, `## Lifecycle`;
    - is at most 900 words;
    - contains `` `git grep` ``.
  - `test_planning_and_close_point_to_the_reference` (AC5).
    - `planning.md` contains `` a last task with `writes: README.md` `` and `(repository.md)`.
    - `close.md` contains `(repository.md#lifecycle)`.

### [ ] T4 — This repository's README answers the seven questions
writes: README.md, install/tests/test_records.py
reads: docs/goals/S-10/design.md#interfaces, install/skills/execution-methodology/references/repository.md, README.md, install/README.md, docs/architecture/methodology.md, docs/product/prd.md, install/skills/execution-methodology/references/close.md
tests-may-change: install/tests/test_records.py
needs: T1, T2, T3
gate: python3 -m unittest discover -s install/tests -t install/tests -p 'test_records.py' && cd install && ./install.sh --dry-run && ./verify.sh --no-suites
AC6.

Rewrite `README.md`: `# SWE Agent`, then seven `##` sections with exactly these headings, in
order: `Overview`, `Current state`, `Product requirements`, `Architecture`, `Components`, `Run
locally`, `Working in this repository`.
- **Overview.** Its first sentence is at most 120 characters.
- **Current state.** What `install/` ships today. Link `docs/goals/` for in-flight work and
  `docs/decisions/decisions.md` for history.
- **Product requirements.** A link table: `docs/product/prd.md`, `docs/product/measurements.md`.
- **Architecture.** A Mermaid `flowchart` of at most ten nodes:
  1. The founder's approval tag.
  2. The chief session.
  3. Builders in worktrees.
  4. `gate.py` receipts.
  5. `goal.py done`.
  6. The other vendor's review.
  7. The PR merge.

  Below it, one sentence in words and a link to `docs/architecture/methodology.md`.
- **Components.** A table with one row per component and the columns responsibility, entry point
  and page. The rows are `install.sh`, `verify.sh`, `global.md`, the skill (`SKILL.md` and
  `references/`), `goal.py`, `gate.py`, `modmap.py`, `docs.py`, `guard.py` with `git-hooks.sh`, and
  the agent files.
- **Run locally.** From a fresh clone: `cd install`, then `./install.sh --dry-run`,
  `./install.sh`, `./verify.sh`, and `git-hooks.sh` in a product clone.
- **Working in this repository.**
  - Agents start at `AGENTS.md`; the gate is the repository gate command.
  - Work lands as goals under `docs/goals/`, merged by PR. Describe the merge as `close.md` does:
    the chief merges on the founder's word.
- Keep the MIT license link.
- The last line is `<!-- covers: [install/install.sh, install/verify.sh, install/global.md,
  install/skills/execution-methodology/SKILL.md, install/skills/execution-methodology/scripts/**,
  install/skills/execution-methodology/agents/**] -->`.

The README must not state a commit hash, run ID, goal or approval state, a count the code can
change, or the methodology version.

Test: **`test_records.py::RecordsTest.test_readme_answers_the_seven_questions_in_order`** (AC6).
- The `## ` headings of `README.md`, in order, equal the seven above.
- The last line starts `<!-- covers: [`.
- No word matches `\b[0-9a-f]{7,40}\b`.

At T4's commit, `docs.py stale .` and `docs.py links .` list nothing.

## Decisions

- 2026-10-14: the link check ships as its own subcommand, `docs.py links`, not inside `lint`.
  Inside `lint` it would turn four product gates red on install (116, 34, 23 and 5 findings,
  measured) (default; design Rejected options).
- 2026-10-14: anchors are checked on every `.md` target, not only `decisions.md`. This repository
  passes, with 45 anchors checked (default).
- 2026-10-14: undefined reference links are not checked. The case found, `[T9]`, is plain
  bracketed text (default).
- 2026-10-14: this repository's own README test fixes its seven headings. Product repositories keep
  heading wording free, with no check (default).
- 2026-10-14: S-9's merge-review R2 (a test for D35's Chose paragraph) is dropped, and R1
  (re-approval after a published approval tag) stays parked (founder, 2026-10-14).
- 2026-10-14: the README contract is v6's seven sections, as prose with no presence check. The
  checks gained are `docs.py links` (links, anchors, twins) and the README under `stale`. The Codex
  gap closes with one `global.md` sentence. Product migrations stay the founder's (founder,
  2026-10-14).

- 2026-10-14: the repository rules ship as the skill's `references/repository.md`; new paths are
  lowercase and unique, with goal ids exempt; `lessons.md` is a record cited by anchor; the
  structure work folds into S-10 (founder, 2026-10-14, after the structure council).
- 2026-10-14: the structure council's corrections are adopted. `modules.json` partitions the tests
  rather than naming build modules; there is no "nested `AGENTS.md` only for its own invariants"
  rule; every move or untrack starts with a grep for its readers; generated files the build
  consumes stay tracked (default).

## Parked

- S-9 merge review R1 (non-blocking): if an earlier milestone already pushed `goal/<id>/approved`
  and a re-approval later moves it, close step 3's push is rejected for that tag. A recovery policy
  waits for the founder (kept parked, founder 2026-10-14).
