# S-10 design: the README's seven questions, the repository rules in the skill, and a shipped link check

## Structure

- **`docs.py`.**
  - A new subcommand, `links`.
  - `pages` excludes `CLAUDE.md`.
  - `pointers` writes a twin for each `AGENTS.md` it creates.
  - `stale` reads a README's `covers` comment.
- **`verify.sh`.** Its links section calls `docs.py links`. `install/tests/link_check.py` and its
  test move into `docs.py` and `test_docs.py`.
- **Words.**
  - New `references/repository.md` in the skill (Interface 7). It ships to every harness home, so
    product-repository agents read it.
  - `repository-standard.md` keeps this repository's own layout and links the reference for the
    rules every repository follows.
  - `planning.md`: the README update in a milestone's last task, and a pointer to the reference.
  - `close.md`: a pointer to the reference's lifecycle rules.
  - `global.md`: the `AGENTS.md` reading rule.
  - D36, plus D17's and D18's status cells.
  - `docs/runbooks/migrate-layout.md`.
  - `methodology.md`: drop the "for Codex" claim and S-9's leftover pilot wording.
  - `measurements.md`: the same pilot wording.
- **This repository.**
  - `README.md` answers the seven questions.
  - `docs/CLAUDE.md` twins `docs/AGENTS.md`.

## Interfaces

1. **`docs.py links [ROOT]`** (durable).
   - **Scope.** `README.md`, `AGENTS.md` and the tracked `docs/**/*.md`; a missing file is skipped.
   - **Links.** For each relative Markdown link outside a code fence and outside inline code:
     - the target path must exist;
     - `#anchor` on a `.md` target, or a bare `#anchor` on the same file, must equal one of the
       target's heading anchors (`docs.anchors`), or be `dNN` where a heading starts `DNN`.
   - **Twins.** Each `AGENTS.md` that `git ls-files --cached --others --exclude-standard` lists
     needs a sibling `CLAUDE.md` holding a line that is exactly `@AGENTS.md`.
   - **Output.**
     - A bad link prints `<file>:<n>: <target>`.
     - A missing twin prints `<dir>/CLAUDE.md: missing; it holds the line @AGENTS.md`.
     - A twin without the line prints `<dir>/CLAUDE.md: no @AGENTS.md line`.
     - Then `docs.py links: PASS` or `FAIL (<n>)`.
     - Exit 0, 1, or 2 when it cannot run.
   - **Gate.** Not part of `lint`: each repository adds it to its gate at its layout migration.
2. **`pages`** (durable). It also excludes every `CLAUDE.md`, so a twin under `docs/` needs no
   frontmatter.
3. **`pointers`** (durable).
   - **Twin.** When it creates an `AGENTS.md` and the directory has no `CLAUDE.md`, it also writes
     `CLAUDE.md` as `@AGENTS.md\n` and prints `<dir>/CLAUDE.md: written`.
   - **`--check`.** It reports nothing new.
4. **The README's `covers` comment** (durable).
   - **Form.** A line of `README.md` that is exactly `<!-- covers: [<glob>, <glob>] -->`, with
     repository-relative globs.
   - **`stale` warning.** When a covered path's last commit is later than the README's own last
     commit, `stale` prints `README.md: <time> after README.md's last commit <time>`.
   - **Without the line.** The README is never stale.
5. **The README's seven sections** (durable words). In order, heading wording free:
   1. **Overview:** what it is and the problem, in a first sentence of at most 120 characters.
   2. **Current state:** the stage and what this tree ships, with a link to `docs/goals/`.
   3. **Product requirements:** a link table, never the PRD's text.
   4. **Architecture:** a Mermaid diagram at system level, or a link to `docs/architecture/`.
   5. **Components:** one row each, with its responsibility, entry point and page.
   6. **Run locally:** from a fresh clone to a running system.
   7. **Working in this repository:** agents read `AGENTS.md`, plus the gate and how work lands.

   The README never states commit hashes, run IDs, goal or approval state, counts the code can
   change, or the methodology version.
6. **The reading rule** (durable words, `global.md`): "Before editing files in a directory, read
   each AGENTS.md between the repository root and it."
7. **`references/repository.md`** (durable words), at most 900 words, with four sections:
   - **The README:** Interfaces 4 and 5.
   - **Layout:**
     - Code goes where the build file declares it. `modules.json` partitions the tests, and each
       module's `test` calls the build tool's own selector.
     - New code and docs paths are lowercase with unique names. Goal ids are exempt; existing names
       are never renamed.
     - One home per kind: decisions, in-flight work in `docs/goals/`, history in `docs/archive/`.
       The home already cited is kept.
     - Tool output and run state are never tracked. What a tool folder holds that is still read is
       moved out first, never re-included with a `!` rule.
     - Generated files the build consumes stay tracked, with a regeneration check in the gate.
   - **Agent files:**
     - `AGENTS.md` is authored; every `AGENTS.md` has a sibling `CLAUDE.md` holding `@AGENTS.md`.
     - The root `AGENTS.md` names the gate within its first 15 lines.
     - A tracked hook names only things that exist.
     - A gate step calls only tooling the repository holds or the skill ships.
   - **Lifecycle:**
     - Records (decisions, measurements, goals, `docs/agents/lessons.md`) are dated, cited by
       anchor and never moved.
     - A finished goal stays in place; its folder holds spec, design, plan and the inputs its
       `reads:` cite, and review output stays in `.runs/`.
     - Supersession goes in a status cell, never by rewriting the text.
     - An archive entry is one row in `docs/archive/README.md` naming a commit on `origin/main`,
       never a copy.
     - Before moving or untracking a path, `git grep` for it outside `*.md`, repoint each reader in
       the same commit, and run the full gate. Code and domain content are never moved.
   - **The product minimum:** moved here from `repository-standard.md`, plus `docs.py links` in
     the gate.

## Data touched

None. `links` and `stale` read only. `pointers` writes one more generated file, and only beside an
`AGENTS.md` it creates.

## Smallest change

- **Code.** One subcommand built from `link_check.py`'s loop and `docs.py`'s `fenced` and
  `anchors`. One more exclusion in `pages`. One file write in `pointers`. One comment parse in
  `stale`.
- **The rest.** Words, and the README.

## Rejected options

- **The link check inside `lint`.** It would turn four product repositories' gates red on install:
  116, 34, 23 and 5 bad links or anchors, measured 2026-10-14.
- **Undefined reference links.** The case found, `[T9]`, is indistinguishable from bracketed text.
- **A section-presence check or word cap.** The founder chose prose. v6's checks caught none of the
  audited defects.
- **A generated root routing table for Codex.** It grows with every page; one sentence suffices.
- **Status generated from tags.** `lint --check` would fail on an unchanged tree once a tag is
  pushed.
- **The rules only in `repository-standard.md`.** It is not installed, so no product-repository
  agent reads it, and one product repository copied 2,337 lines into its archive.
- **Prescribing source layout.** Build files already declare it. One repository has 10 Gradle
  projects and 85 map modules, so "modules are build modules" would be false.
- **v6's full naming rules.** Hundreds of existing docs files break them and no defect traces to
  that. Renaming is a build risk.
- **A `done/` folder or goal status field.** Most product plans cite other goals' folders by path.
- **"A nested `AGENTS.md` only for its own invariants."** `docs.py pointers` creates `AGENTS.md`
  files to carry pointer blocks.
