# S-10 design: the README's seven questions, the repository rules in the skill, and a shipped link check

## Structure

- **`docs.py`.**
  - A new subcommand, `links`.
  - `fenced` and `anchors` follow GitHub's fence and anchor rules.
  - `pages` excludes a `CLAUDE.md` that is only the import line.
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
   - **Code** (design review R7, R10), in `fenced` itself, so headings and `reads:` agree with links.
     - A fence opens on a run of three or more backticks or tildes, indented at most three spaces.
       It closes on a line holding only a run of the same character at least as long, indented at
       most three spaces, with nothing after it but whitespace (plan review R4).
     - On a line outside a fence, a backtick run of length n opens a code span. The span closes at
       the next run of exactly n backticks on that line; a run left unmatched is literal.
     - A span running across lines is not recognised. A link inside it is checked, so the error is
       a false failure, never a false pass.
   - **Destinations** (R6). For each inline link or image, the destination (what follows the
     closing bracket's opening parenthesis, after any spaces or tabs; plan review R5) is:
     - `<…>` up to the first `>`; or
     - else a run without spaces, with balanced parentheses.
     - A title after whitespace is ignored, and percent-encoding is decoded before the path is
       checked.
     - A destination with a URI scheme, such as `https:`, is skipped.
     - A link reference definition (`[label]: destination`, at most three spaces of indent, outside
       a fence) has its destination checked the same way (plan review R6). A reference use with no
       definition stays unchecked.
   - **Targets.** The path must exist.
   - **Anchors** (R8, R9).
     - `#anchor` on a `.md` target, or alone for the same file, must equal one of the target's
       GitHub anchors.
     - `docs.anchors` reserves every anchor it emits, so a colliding slug takes the next free
       suffix. For headings `X`, `X`, `X-1`, the anchors are `x`, `x-1`, `x-1-1`.
     - There is no `dNN` shorthand in links, since GitHub renders none; `reads:` keeps it. The
       three `#d30`-style links in `docs/product/prd.md` become full anchors.
   - **Twins.** Each `AGENTS.md` that `git ls-files --cached --others --exclude-standard` lists
     needs a sibling `CLAUDE.md`: a regular file inside the repository, holding a line that is
     exactly `@AGENTS.md`.
   - **Output.**
     - A bad link prints `<file>:<n>: <destination as written>`.
     - A missing twin prints `<dir>/CLAUDE.md: missing; it holds the line @AGENTS.md`.
     - Any other bad twin prints `<dir>/CLAUDE.md: no @AGENTS.md line`.
     - Then `docs.py links: PASS` or `FAIL (<n>)`.
     - Exit 0, 1, or 2 when it cannot run.
   - **Gate.** Not part of `lint`: each repository adds it to its gate at its layout migration.
2. **`pages`** (durable; R5). It excludes a `CLAUDE.md` whose only non-blank line is
   `@AGENTS.md`. A `CLAUDE.md` with other content, such as frontmatter, stays a page, so no gate
   that passes today changes verdict on install.
3. **`pointers`** (durable; R11).
   - **Twin.** It creates an `AGENTS.md` only where none existed. When no entry named `CLAUDE.md`
     exists in that directory (`os.path.lexists`, so a dangling symlink counts as existing), and
     the destination resolves inside the repository, it also writes `CLAUDE.md` as `@AGENTS.md\n`
     and prints `<dir>/CLAUDE.md: written`.
   - **Otherwise** it never writes a `CLAUDE.md`, and `--check` reports nothing new.
4. **The README's `covers` comment** (durable; R12).
   - **Form.** The first line of `README.md`, outside a fence, that matches `<!-- covers: <flow
     list> -->`, read with `goal.flow`, so quoted globs keep their commas. Later matching lines are
     ignored. The globs are repository-relative.
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
     - Code goes where the build file declares it. `modules.json` is as `modules.md` says (R14).
     - New paths are lowercase with unique names. Goal ids, and names a tool or convention fixes
       (`README.md`, `AGENTS.md`, `CLAUDE.md`, `LICENSE`, `Makefile`, build files), keep their
       spelling. Existing names are never renamed (R13).
     - One home per kind: decisions, in-flight work in `docs/goals/`, history in `docs/archive/`.
       The home already cited is kept.
     - Tool output means a tool's working files and run state: a plugin's plans and specs,
       code-graph output, scratch workspaces, `.runs/`. It is never tracked; what it holds that is
       still read is moved out first, never re-included with a `!` rule.
     - Generated files a gate checks are not tool output and stay tracked. These include
       `docs.py`'s pointer files and generated types or schemas (R1).
   - **Agent files:**
     - `AGENTS.md` is authored; every `AGENTS.md` has a sibling `CLAUDE.md` holding `@AGENTS.md`.
     - The root `AGENTS.md` names the gate within its first 15 lines.
     - A tracked hook names only things that exist.
     - A gate step calls only tooling the repository holds or the skill ships.
   - **Lifecycle:**
     - **Records.** Decisions, measurements, goals and `docs/agents/lessons.md` are dated, cited by
       anchor, and may name removed components as rationale. Every other page states what is true
       now (R15). Records are never moved.
     - **Finished goals.** A finished goal stays in place, and nothing is copied into it. Review
       output stays in `.runs/` (R17).
     - **Supersession** goes in a status cell, never by rewriting the text.
     - **Archive entries.** An archive entry is one row in `docs/archive/README.md`, never a copy.
       The row names a commit or tag pushed to `origin` whose tree holds the removed content, which
       `git cat-file -e <ref>:<path>` confirms (R4, R18).
     - **Moving or untracking a path** (R2, R4).
       - First, `git grep` across all tracked files, Markdown included, for the path, its
         directory and its basename, and run `docs.py links`.
       - A path something reads or cites stays, unless every reader is repointed in the same
         commit.
       - Then run the full gate in a fresh worktree of the commit (`git worktree add --detach`),
         never in the working tree, where an untracked file still sits on disk.
       - Code and domain content are never moved.
     - **Rollback after untracking** (R3). Copy the untracked paths aside, `git revert`, then
       restore them.
   - **The product minimum:** moved here from `repository-standard.md`, plus `docs.py links` in
     the gate.
   - **The page frontmatter template:** moved here from `planning.md`, which keeps a pointer and
     stays within its 400-word ceiling (plan review R2).

## Data touched

- **The scripts.** `links` and `stale` only read. `pointers` writes one more generated file, and
  only beside an `AGENTS.md` it creates, inside the repository.
- **`fenced` and `anchors`.** These change what `reads:` resolves to only where they were wrong:
  a shorter fence inside a longer one, or a colliding suffix.
- **The runbook.** It is where data could be lost, so Interface 7 guards it with the reader grep,
  the fresh-worktree gate, the verified archive reference and the copy-aside rollback.

## Smallest change

- **Code.**
  - One subcommand built from `link_check.py`'s loop.
  - A corrected `fenced` and `anchors`.
  - One narrow exclusion in `pages` and one guarded write in `pointers`.
  - One comment parse in `stale`, through `goal.flow`.
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
- **Excluding every `CLAUDE.md` from `pages`.** One product repository indexes a `docs/CLAUDE.md`
  with frontmatter, and its gate would turn red on install (design review R5).
- **Keeping `dNN` as a link anchor.** GitHub renders no such anchor (R8).
- **A full CommonMark parser.** It is not in the standard library. The two cases left are a code
  span running across lines and reference-style links. The first fails safe; the second is not
  checked.
