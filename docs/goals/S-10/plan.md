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
treats a `CLAUDE.md` holding only `@AGENTS.md` as a page (AC2). A README's `covers` comment puts it under `docs.py stale`
(AC3). `verify.sh` runs `docs.py links` in place of the unshipped `link_check.py` (AC4). The
skill ships `references/repository.md` with the README's seven sections and the layout, agent-file
and lifecycle rules; `planning.md` and `close.md` point to it; `global.md` tells both harnesses to
read the `AGENTS.md` files on the way to a file; D36 records it; a runbook migrates a repository
after grepping each path's readers (AC5). This
repository's README answers the seven questions (AC6). Spec: [spec.md](spec.md). Design:
[design.md](design.md).

## Tasks

### [x] T1 — `docs.py links`, GitHub's fences and anchors, `CLAUDE.md` twins, the README's `covers`
writes: install/skills/execution-methodology/scripts/docs.py, install/skills/execution-methodology/tests/test_docs.py
reads: docs/goals/S-10/design.md#interfaces, install/skills/execution-methodology/scripts/docs.py, install/skills/execution-methodology/scripts/goal.py, install/skills/execution-methodology/tests/test_docs.py, install/skills/execution-methodology/tests/fixtures/goal_fixture.py, install/tests/link_check.py, install/tests/test_install.py
tests-may-change: install/skills/execution-methodology/tests/test_docs.py
AC1, AC2, AC3. Design Interfaces 1–4. Each design-review finding named below gets its test here.

**`fenced(lines)`** (R10, plan review R4). Keep its signature and yield shape.
- It remembers the opening run's character and length: up to three spaces of indent, then at least
  three backticks or tildes.
- A line closes the fence only when it is, apart from up to three spaces of indent and trailing
  whitespace, a run of the same character at least as long:
  `re.fullmatch(rf" {{0,3}}{ch}{{{n},}}[ \t]*", line)`.

**`anchors(heads)`** (R9). Keep its signature. It keeps a set of every anchor already emitted. For
a slug already taken, it tries `-1`, `-2`, and so on, until one is free.

**`links(root)`**, a new module-level function returning findings, wired into `main` beside `lint`
and `stale`. It uses the same verdict line (`docs.py links: PASS` or `FAIL (<n>)`) and exit codes.
- **Files.** `README.md`, `AGENTS.md`, then `git ls-files docs/*.md`, skipping a missing file.
- **Lines.** On each line outside a fence, remove code spans first (R7). A backtick run of length
  n opens a span that closes at the next run of exactly n backticks on that line. Scan run by run;
  an unmatched run is literal text.
- **Destinations** (R6, plan review R5). After each closing bracket followed by an opening
  parenthesis (links and images alike), skip spaces and tabs, then read the destination:
  - `<…>` up to the first `>`; or
  - else characters up to whitespace or the unbalanced `)`, counting nested parentheses.
  - Skip one with a URI scheme (`re.match(r"[A-Za-z][A-Za-z0-9+.-]*:", d)`).
  - Split off `#anchor`, and `urllib.parse.unquote` the path.
- **Reference definitions** (plan review R6). A line outside a fence matching `^ {0,3}\[[^\]]+\]:[
  \t]*(\S.*)$` has its destination read from group 1 by the same rule and checked like a link.
- **Anchors** (R8). An empty path means the same file. When the target is a `.md` file, the anchor
  (lowercased) must be in `anchors(headings(<target lines>))`. There is no `dNN` shorthand here;
  `resolve` (for `reads:`) keeps its own.
- **Twins.** Iterate `git ls-files -z --cached --others --exclude-standard --
  ':(glob)**/AGENTS.md'`. The sibling `CLAUDE.md` must be a regular file (not a symlink), resolve
  inside the root, and hold a line equal to `@AGENTS.md`.
- **Findings.** Links in file order, then twins sorted by path, with Interface 1's texts.

**`pages`** (R5) also excludes a path ending `CLAUDE.md` whose non-blank lines are exactly
`["@AGENTS.md"]`.

**`pointers`** (R11). When it writes an `AGENTS.md` that did not exist (`have is None` and `rel in
blocks`), it checks the directory's `CLAUDE.md`:
- `not os.path.lexists(<dir>/CLAUDE.md)`, and `inside(root, <dir>/CLAUDE.md)`;
- then it writes `@AGENTS.md\n` and prints `<dir>/CLAUDE.md: written`;
- otherwise it writes nothing for the twin.

`--check` is unchanged.

**`stale`** (R12). After the pages, it checks `README.md`.
- **Its declaration** is the first line outside a fence that matches `^<!-- covers: (.*) -->$`.
  Parse group 1 with `goal.flow`; a parse error or non-list is no declaration. Keep the entries
  where `relative()` holds.
- **The finding.** When the covered paths' last commit is later than `README.md`'s own last commit
  (committer timestamps, compared as the pages' same-day rule compares them), add `README.md:
  <last> after README.md's last commit <own>`.

**Docstring.** The first line adds `links [ROOT]`. Add one paragraph for `links`, and one sentence
to `stale`'s paragraph for the README.

Tests in `test_docs.py`, new class **`LinksTest(DocsCase)`** unless named otherwise:
- **`test_links_anchors_and_twins_pass`** (AC1, AC2). `README.md` links the following, and
  `AGENTS.md` sits beside a `CLAUDE.md` holding `@AGENTS.md`. Result: exit 0, `docs.py links:
  PASS`.
  - `docs/record.md#d17--zeta-rule-v2`
  - `docs/record.md#d18-other-thing`
  - `docs/record.md#detail`
  - `<docs/record.md>`
  - `docs/record.md "Title"`
  - an image of `docs/record.md`
- **`test_bad_links_and_anchors_are_listed`** (AC1). In `README.md`:
  - line 1 links `docs/none.md`;
  - line 2 links `docs/record.md#d17--nonexistent`;
  - line 3 links `docs/record.md#d17` (R8);
  - line 4 links `#nowhere`;
  - line 5 holds a link to `docs/none.md` inside a matched one-backtick code span;
  - lines 6–8 are a fenced block holding the same link.

  The output is exactly `README.md:1: docs/none.md`, `README.md:2:
  docs/record.md#d17--nonexistent`, `README.md:3: docs/record.md#d17`, `README.md:4: #nowhere`,
  `docs.py links: FAIL (4)`. Exit 1.
- **`test_rendered_destinations_with_spaces_encoding_titles_and_images`** (R6). `docs/user
  guide.md`, `docs/a(b).md` and a directory `docs/user/` exist.
  - These pass: an angle-bracket link to `docs/user guide.md` with the title `"Guide"`, the link
    `docs/user%20guide.md`, an image of `docs/user%20guide.md`, and the link `docs/a(b).md`
    (balanced parentheses; plan review R9).
  - An angle-bracket link to `docs/user guide2.md` is listed, and so is `docs/a(c).md`.
- **`test_destination_after_opening_whitespace_is_checked`** (plan review R5). A link whose
  parenthesis is followed by a space, then `missing.md`, lists `README.md:1: missing.md`.
- **`test_defined_reference_link_to_missing_target_fails`** (plan review R6). `README.md` holds a
  reference use `[guide][manual]` and the definition `[manual]: missing.md`; the definition's line
  is listed. A definition naming `docs/record.md` passes.
- **`test_decision_shorthand_is_not_a_rendered_anchor`** (R8). A link to `docs/record.md#d17` is
  listed, while `docs.py reads` still resolves the `reads:` entry `docs/record.md#d17`.
- **`test_code_spans_require_matching_complete_backtick_runs`** (R7).
  - A line opening with two backticks, then a link to `docs/none.md`, then one backtick, lists the
    link.
  - A line where the link sits between two-backtick runs does not.
- **`test_duplicate_suffix_collisions_match_rendered_anchors`** (R9).
  - `docs.anchors` of headings `X`, `X`, `X-1` is `["x", "x-1", "x-1-1"]`.
  - Links to all three pass `links`.
- **`test_fence_with_trailing_text_does_not_expose_headings`** (plan review R4). Inside a
  three-backtick fence, a line of three backticks followed by `example`, then `## Hidden`, then the
  real closing fence. A link to `#hidden` is listed.
- **`test_shorter_fence_does_not_expose_example_headings`** (R10). A page has a four-backtick fence
  holding a three-backtick line and `## Inside`, then the real closing fence, then `## After`.
  - A link to `#inside` is listed; one to `#after` passes.
  - `docs.py reads` of the page's `#after` resolves.
- **`test_agents_md_twins`** (AC2).
  - `sub/AGENTS.md` without a `CLAUDE.md` gives `sub/CLAUDE.md: missing; it holds the line
    @AGENTS.md`.
  - `sub/CLAUDE.md` holding `hello\n` gives `sub/CLAUDE.md: no @AGENTS.md line`.
  - The same message is given when `sub/CLAUDE.md` is a symlink to a file holding `@AGENTS.md`,
    and when it is a directory (plan review R9).
- **`PointersTest.test_first_generation_writes_the_rule_file_and_a_new_agents_md`.** The expected
  lines gain `src/a/CLAUDE.md: written` after `src/a/AGENTS.md: written`, and `tests/CLAUDE.md:
  written` after `tests/AGENTS.md: written`. `tests/CLAUDE.md` reads `@AGENTS.md\n`.
- New **`PointersTest.test_twin_symlink_cannot_write_outside_repository`** (R11). `src/a/CLAUDE.md`
  is a dangling symlink to a path in a temporary directory outside the repository. `pointers`
  writes `src/a/AGENTS.md`, does not print a twin line, and the outside path stays absent.
- New **`LintTest.test_install_rollout_with_an_existing_claude_page`** (R5).
  - A `docs/CLAUDE.md` with frontmatter and its index row passes `lint`.
  - Replaced by `@AGENTS.md\n` alone, with its index row removed, it also passes.
- New **`StaleTest.test_a_readme_covers_comment`** (AC3).
  1. `README.md` holds `# R\n\n<!-- covers: [src/a/**] -->\n` and is committed at
     `2026-10-01T10:00:00+02:00`. It is not listed.
  2. A `src/a/y.py` commit at `10:01` lists `README.md: 2026-10-01T10:01:00+02:00 after
     README.md's last commit 2026-10-01T10:00:00+02:00`.
  3. A README without the line is never listed.
- New **`StaleTest.test_readme_covers_preserves_quoted_globs_and_ignores_examples`** (R12).
  - With `<!-- covers: ["src/a,b/**"] -->`, a later commit under `src/a,b/` lists `README.md`.
  - A covers line inside a fence only is no declaration.
  - With two declarations, `[src/z/**]` first and `[src/a/**]` second, a later `src/a/` commit does
    not list the README (plan review R9).
  - `<!-- covers: [src/a/** -->` (unterminated) and `<!-- covers: src/a/** -->` (not a list) are
    no declaration.

Do not change `lint`'s checks beyond `pages`, any other test, the map, or any file outside the
writes.

### [x] T2 — `verify.sh` runs `docs.py links`; `link_check.py` is removed; `docs/CLAUDE.md`
writes: install/verify.sh, install/tests/link_check.py, install/tests/test_install.py, install/tests/test_map.py, install/README.md, docs/CLAUDE.md, docs/product/prd.md
reads: docs/goals/S-10/design.md#interfaces, install/verify.sh, install/tests/test_install.py, install/tests/test_map.py, install/README.md, docs/product/prd.md, docs/decisions/decisions.md#d30--methodology-v71-context-roles-and-planning-documents-s-2
tests-may-change: install/tests/test_install.py, install/tests/test_map.py, install/tests/link_check.py
needs: T1
AC4, AC2. `link_check.py` is in `tests-may-change` because done row 5 counts every file under
`tests/` as a test (plan review R1).
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
- **`docs/product/prd.md`.** Its three links ending `decisions.md#d30` (and any other bare `#dNN`)
  take the decision's full GitHub anchor, as `AGENTS.md`'s links do. `links` has no `dNN`
  shorthand (design review R8).
- New test **`test_install.py::LinksInVerify.test_verify_runs_the_shipped_link_check`** (AC4).
  `install/verify.sh` contains `docs.py" links "$ROOT"` and does not contain `link_check.py`.

### [x] T3 — The repository reference, the reading rule, D36 and the layout runbook
writes: install/skills/execution-methodology/references/repository.md, install/skills/execution-methodology/references/planning.md, install/skills/execution-methodology/references/close.md, docs/architecture/repository-standard.md, install/verify.sh, install/global.md, AGENTS.md, docs/decisions/decisions.md, docs/runbooks/migrate-layout.md, docs/architecture/methodology.md, docs/product/measurements.md, docs/README.md, docs/AGENTS.md, .claude/rules/**, install/tests/test_records.py, install/skills/execution-methodology/tests/test_rules.py
reads: docs/goals/S-10/design.md#interfaces, docs/architecture/repository-standard.md, install/skills/execution-methodology/references/planning.md, install/skills/execution-methodology/references/close.md, install/skills/execution-methodology/references/modules.md, install/global.md, AGENTS.md, docs/decisions/decisions.md, docs/runbooks/migrate-v5.md, docs/architecture/methodology.md, docs/product/measurements.md, install/tests/test_records.py, install/tests/test_size.py, install/verify.sh, install/skills/execution-methodology/tests/test_rules.py, install/skills/execution-methodology/scripts/docs.py
tests-may-change: install/tests/test_records.py, install/skills/execution-methodology/tests/test_rules.py
needs: T2
AC5. Design Interfaces 4–7, with design review R1–R4 and R13–R18.

**New `install/skills/execution-methodology/references/repository.md`.** Design Interface 7, as
prose, at most 900 words. Its rules hold every exemption the design names: the generated files a
gate checks, the conventional filenames, the `count: "none"` module, and the records that keep
removed names.
- Its four sections are `## The README`, `## Layout`, `## Agent files` and `## Lifecycle`.
- The product minimum closes `## Layout`. Move it word for word from `repository-standard.md`'s
  last paragraph, and add `docs.py links` to the gate.
- No frontmatter: it is a skill reference, not a `docs/` page.
- Name no project, and no name `verify.sh`'s dangling-name scan lists.

**`planning.md`** stays within its 400-word ceiling (`test_rules.py` `REFERENCE_WORDS`) and its
rules section within 200 (plan review R2). Today they are 400 and 155.
- **Move the template.** Move the closing `docs/` frontmatter template (its lead-in sentence and
  fenced block, 25 words) into `repository.md`'s `## Layout`.
- **The pointer.** Put in its place the line "Frontmatter, layout, README and records:", then a
  Markdown link whose text and target are both `repository.md`.
- **The MUST rule.** Under "Chief's planning rules", MUST, add: "Give a milestone that changes what
  the repository ships a last task writing `README.md`'s Current state."

**`close.md`.** After step 4, add one line: "Archiving or untracking anything at a close follows",
then a Markdown link with text `repository.md` and target `repository.md#lifecycle`.

**`repository-standard.md`.**
- **Records sentence** (plan review R3). It names `docs/agents/lessons.md` among the records that
  may name removed components, for any repository that has one.
- **Layout block.** The `README.md` row reads "front page for a human: the seven sections of the
  skill's `references/repository.md`".
- **After the block,** one sentence: the rules every repository follows (README, layout, agent
  files, lifecycle, the product minimum) are the skill's `references/repository.md`, and this page
  is how this repository applies them. Link the reference by its relative path.
- **Last paragraph.** Replace the product-minimum paragraph with that link.
- **Enforcement paragraph.** The link check is `docs.py links`.
- **Frontmatter.** Update `summary` (at most 120 words); `last-verified: 2026-10-14`.

**`verify.sh`** (plan review R3). The dangling-name check's `EXCLUDE` gains
`docs/agents/lessons.md`, with a one-line comment that it is a record.

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
product repository at a milestone boundary, on a branch, following the reference's Lifecycle:
1. **Readers first.** For each path to move, archive or untrack, `git grep -n` its path, its
   directory and its basename across all tracked files, Markdown included, and run `docs.py links`.
   A path something reads or cites stays, unless every reader is repointed in the same commit.
   Code, build roots, records and domain content are never moved or renamed.
2. **Move the content.** Move whatever a tool folder holds that is still read into its home,
   repointing its readers, and delete the `!` re-include for it.
3. **Untrack tool output.** Add it to `.gitignore`, then `git rm -r --cached`.
4. **One home per kind.** Bring each kind to one home, keeping the home already cited.
   - Replace copied history with one row in `docs/archive/README.md` naming a commit or tag pushed
     to `origin`.
   - Before deleting the copy, confirm `git cat-file -e <ref>:<path>` for each path.
5. **Retired tooling.** Drop gate steps, Make targets, PR-template lines and tracked hooks that call
   or name tools the skill no longer installs.
6. **Agent files.** Add each missing `CLAUDE.md` twin, and move the gate into the root
   `AGENTS.md`'s first 15 lines.
7. **The README.** Rewrite `README.md` to the seven sections, with its `covers` comment.
8. **Verify.**
   - Add `docs.py links` to the gate, and commit.
   - Run the full gate in a fresh worktree of that commit (`git worktree add --detach <dir>
     HEAD`), not in the working tree, where untracked files still sit on disk.
   - Run `docs.py lint`, `docs.py links` and `docs.py stale` there too.

Rollback: copy the untracked paths aside, `git revert` the migration, then restore them. Name no
project, and no name `verify.sh`'s dangling-name scan lists.

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
- **`test_rules.py` constants.**
  - Add `REPOSITORY = SKILL / "references" / "repository.md"` to `SKILL_FILES`.
  - Add `REPOSITORY: 900` to `REFERENCE_WORDS`, so the retired-name, path and word-ceiling tests
    cover it.
- **`test_rules.py`**, new class `Repository`. Each test reads `references/repository.md`.
  - `test_the_reference_carries_the_readme_layout_and_lifecycle` (AC5). It has the headings `## The
    README`, `## Layout`, `## Agent files` and `## Lifecycle`, is at most 900 words, and contains
    `` `git grep` ``.
  - `test_repository_rules_preserve_required_generated_pointers` (R1). The sentence holding
    `Generated files a gate checks` also names `pointer files`.
  - `test_naming_rule_allows_required_interface_filenames` (R13). The sentence holding
    `lowercase` names `AGENTS.md`, `CLAUDE.md` and `README.md` as kept spellings.
  - `test_module_rule_preserves_non_test_gate_modules` (R14). The text links `modules.md` and does
    not contain `selector`.
  - `test_lessons_record_can_retain_retired_component_rationale` (R15). The sentence naming
    `docs/agents/lessons.md` contains `may name removed components`.
- **`test_records.py::RecordsTest.test_lessons_record_can_retain_retired_component_rationale`**
  (R15, plan review R3).
  - `repository-standard.md` names `docs/agents/lessons.md` in its records sentence.
  - `install/verify.sh`'s `EXCLUDE` lines contain `docs/agents/lessons.md`.
- **`test_records.py`**, new class `LayoutMigrationTest`, reading
  `docs/runbooks/migrate-layout.md`:
  - `test_gate_input_survives_migration_in_a_fresh_checkout` (R2). It contains `git worktree add
    --detach` and `Markdown included`.
  - `test_rollback_preserves_modified_ignored_files` (R3). Its rollback line contains `copy the
    untracked paths aside`.
  - `test_archival_preserves_cited_records_and_verifies_recovery_content` (R4, R18). It contains
    `git cat-file -e`, `pushed` and `records`, and does not contain `:!*.md`.
  - `test_planning_and_close_point_to_the_reference` (AC5).
    - `planning.md` contains `` a last task writing `README.md` `` and `(repository.md)`.
    - `repository.md` contains `last-verified: YYYY-MM-DD`.
    - `close.md` contains `(repository.md#lifecycle)`.

### [ ] T4 — This repository's README answers the seven questions
writes: README.md, install/tests/test_records.py
reads: docs/goals/S-10/design.md#interfaces, install/skills/execution-methodology/references/repository.md, install/tests/test_records.py, README.md, install/README.md, docs/architecture/methodology.md, docs/product/prd.md, install/skills/execution-methodology/references/close.md
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

At T4's commit, `docs.py links .` passes and `docs.py stale .` does not list `README.md`. Pages
covering `install/**` or `docs/**` may be listed; T4's own test and tick touch those paths
(design review R16).

## Decisions

- 2026-10-14: the link check ships as its own subcommand, `docs.py links`, not inside `lint`.
  Inside `lint` it would turn four product gates red on install (116, 34, 23 and 5 findings,
  measured) (default; design Rejected options).
- 2026-10-14: anchors are checked on every `.md` target, not only `decisions.md`, against
  GitHub's rendered anchors only. This repository passes once `prd.md`'s three `#d30` links take
  full anchors (default; design review R8).
- 2026-10-14: the design review returned BLOCK with 16 blocking findings and 2 non-blocking. All
  are resolved in the design and plan before approval:
  - R1, R13–R15 and R17–R18: the reference's exemptions;
  - R2–R4: the runbook's reader grep, fresh-worktree gate, verified archive reference and
    copy-aside rollback;
  - R5: `pages` excludes only an import-only `CLAUDE.md`;
  - R6–R12: the parser, the anchors and fences, the twin boundary and the `covers` parse;
  - R16: T4's stale criterion is narrowed to the README.

  Each blocking finding names its closing test in T1 or T3 (default).
- 2026-10-14: the plan review returned BLOCK with 7 blocking findings and 2 non-blocking. All are
  resolved in the plan, spec and design (default):
  - R1: `link_check.py` is in T2's `tests-may-change`.
  - R2: `planning.md`'s template moves to the reference, keeping its ceiling.
  - R3: the standard and `verify.sh` carry the lessons exemption.
  - R4–R6: closing fences, opening whitespace and reference definitions.
  - R7: AC2 is narrowed to an import-only `CLAUDE.md`.
  - R8: the missing `reads:`.
  - R9: the regression cases.
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
- 2026-10-14 T1: an angle-bracket destination is reported without its brackets; a code span is
  blanked rather than cut, so text either side cannot join into a link; an anchor on a `.md` path
  that is a directory is not checked; a README with no commit is never stale (default).
- 2026-10-14 T2: `LinksInVerify` is a plain `unittest.TestCase` that reads `verify.sh`, like
  `test_map.py`'s text checks; `test_install.py` drops its unused `import sys` (default).
- 2026-10-14 T3: the naming rule is one sentence so its kept spellings sit with `lowercase`;
  D36's Why is in the past tense, as D35's is; the decisions summary shortens D32–D35's clauses to
  fit D36's within 120 words; `methodology.md`'s `last-verified` moves to 2026-10-14, since T3
  re-verified it against `install/` (default).

## Parked

- S-9 merge review R1 (non-blocking): if an earlier milestone already pushed `goal/<id>/approved`
  and a re-approval later moves it, close step 3's push is rejected for that tag. A recovery policy
  waits for the founder (kept parked, founder 2026-10-14).
