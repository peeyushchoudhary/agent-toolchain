# S-2 design

Current decisions only; S-2 changes interfaces every later goal depends on.

## Structure

New `scripts/docs.py` owns the documents under `docs/`: frontmatter lint, index, `reads:`
resolution, pointers, staleness. `goal.py` grows only where the plan is concerned. Three on-demand
references and three agent files per harness carry the words. `install.sh` ships the agent files.
`run.sh` becomes a one-shot console launcher (7).

## Interfaces

1. **`plan.md`.** A task may carry `reads:` after `writes:`: paths, `path#anchor` entries or terms;
   like `writes`, it is outside the frozen view and a change needs a Decisions line. `touches:` accepts `none`, `data`, `auth`, `external`, `interface`, `ui`; any
   value but `none` requires `design.md`. `spec.md` is required when the approved commit contains
   it, protected whole from the tag; `design.md#interfaces` and `design.md#data-touched` are
   protected when the page exists; none needs listing. Anchors are GitHub heading slugs; `dNN`
   and `D1-D19` keep their meaning; a slug in `protected:` protects that section only. Every
   `ACn` appears in a task section. Durable.
2. **`spec.md`.** ≤400 words with the headings *Users and problem*, *What changes for the user*,
   *Acceptance criteria* (`ACn WHEN … THE SYSTEM SHALL …` bullets), *Non-goals*, *Constraints*; or
   the two-line form `What changes for the user: nothing` plus the criteria as the goal's tests.
   Durable.
3. **Document frontmatter.** Every tracked `docs/**/*.md` except `docs/README.md` and
   `docs/goals/**` starts with `summary` (≤120 words), `read-when` (one line), `covers`
   (repository-relative globs, no `..` or absolute paths, may be `[]`) and `last-verified`
   (`YYYY-MM-DD`; stale when a covered path's last commit is on a later day, or on that day after
   the page's own last commit). `docs/README.md` holds prose, then the table `docs.py index`
   prints; lint compares the table. Durable.
4. **`docs.py` commands.** `lint [ROOT]` (frontmatter, index, generated pointers); `index [ROOT]`;
   `reads <Tn> --goal <id>` printing `path:start-end` per entry, `path` for a whole file, `term:
   <word>` for a term, exit 1 on a missing anchor; `pointers [ROOT] [--check]`; `stale [ROOT]`.
   Exit 0 clean, 1 findings, 2 could not run. The slug rule lives here; `link_check.py` imports
   it. Durable.
5. **Pointer files.** For each page with non-empty `covers`: `.claude/rules/<page-slug>.md`
   (frontmatter `paths:` = `covers`, generated body) and a block between
   `<!-- docs.py pointers -->` and `<!-- /docs.py pointers -->` in the nearest existing `AGENTS.md`
   at or above the longest literal directory prefix of each glob, else a new one there; one block
   per file lists every page mapping to it. The body names the page, `read-when` and H2 anchors. Created only when absent; a marked file has only its block replaced; an unmarked one is
   left alone and reported; output whose page dropped `covers` is removed; destinations resolve
   inside the repository. Committed, never hand-edited. Durable.
6. **Agent files.** Claude: `agents/{builder,reviewer,scout}.md`, frontmatter from `name`,
   `description`, `tools`, `model`, `effort`, `maxTurns`, `permissionMode`, `isolation`, body in
   MUST/SHOULD/AVOID/REPORT sections, installed to `~/.claude/agents/`. Codex: the same three as
   `.toml` with `name`, `description`, `developer_instructions` (byte-equal to the `.md` body),
   `model`, `model_reasoning_effort`, `sandbox_mode`, installed to `$CODEX_HOME/agents/`.
   Installed copies carry a marker; uninstall removes one only while it equals the shipped copy,
   else reports it. Durable.
7. **`run.sh <id> --harness claude|codex`** opens one interactive terminal session from
   `goal.py resume` with the scoped allowlist, deny list, sandbox, per-session Stop hook, push
   denial and `worktree.baseRef: "head"`; no loop, no stall detection; the founder relaunches. Durable.
8. **Records**, not durable: `.runs/<id>/approval.html`; a `cost:` line per session in
   `progress.md`, written by the Stop hook from the transcript's usage when the hook payload names
   one; `cause: context|logic|spec` on each closed blocking finding.

## Data touched

Nothing in a store, nothing migrated. Outside git: marked agent files in both harness homes,
removed by uninstall only while unchanged; no settings file. Rollback: `install.sh --uninstall`,
then the previous tag's installer.

## Smallest change

Frontmatter, an index, heading anchors and the harnesses' own path-scoped loading: no store, no
retrieval, no agent memory. `docs.py` reuses `goal.py`'s parser; `run.sh` loses code.

## Rejected options

- Agent memory or a graph: no measured catch in v6; fresh context per role is the design.
- A model-judged done; a second reviewer; a dollar budget: rows are stronger, no yield data,
  founder rejected.
- Hand-written pointers; mid-tier builders; a headless loop: the founder chose otherwise.
- Pasting cited sections into packets: identifiers over text; the builder reads the file.
