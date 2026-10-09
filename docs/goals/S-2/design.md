# S-2 design

Current decisions only. Written because S-2 changes the `plan.md` format and the installed file set,
which are interfaces every later goal depends on.

## Structure

One new script, `scripts/docs.py`, holds everything about the documents under `docs/`: frontmatter
lint, index generation, `reads:` resolution, pointer generation and staleness. `goal.py` grows only
where the plan is concerned: the `reads:` field, the widened `touches:`, spec and design lint,
default protection, acceptance-criteria tracing and the approval page. Three on-demand references
(`planning.md`, `roles.md`, `security-checklist.md`) and three agent files per harness carry the
words. `install.sh` ships the agent files to each harness's `agents/` directory. `run.sh` only
appends a cost line per session; its permission model is untouched.

## Interfaces

1. **`plan.md`.** A task may carry `reads:` after `writes:`: a comma-separated list of repository
   paths, `path#anchor` entries (anchor = the GitHub slug of a heading) or bare terms. `touches:`
   accepts `none`, `data`, `auth`, `external`, `interface`, `ui`; any value but `none` requires
   `docs/goals/<id>/design.md`. `docs/goals/<id>/spec.md` is required for every goal and is
   protected whole from the approval tag; `design.md#Interfaces` and `design.md#Data touched` are
   protected when the page exists. Neither needs listing in `protected:`. Every `ACn` in the spec must
   appear in at least one task section. Durable.
2. **`spec.md`.** ≤400 words with the headings *Users and problem*, *What changes for the user*,
   *Acceptance criteria* (`ACn WHEN … THE SYSTEM SHALL …` bullets), *Non-goals*, *Constraints*; or the
   two-line form `What changes for the user: nothing` plus the criteria as the goal's tests. Durable.
3. **Document frontmatter.** Every tracked `docs/**/*.md` except `docs/README.md` and `docs/goals/**`
   starts with YAML-style frontmatter: `summary` (≤120 words), `read-when` (one line), `covers`
   (a flow list of path globs, may be `[]`), `last-verified` (`YYYY-MM-DD`). `docs/README.md` holds
   the table `docs.py index` prints: one row per page, its link and `read-when`. Durable.
4. **`docs.py` commands.** `lint [ROOT]` (frontmatter, index, generated pointers); `index [ROOT]`;
   `reads <Tn> --goal <id>` printing `path:start-end` per entry, `path` for a whole file, `term:
   <word>` for a term, exit 1 on a missing anchor; `pointers [ROOT] [--check]`; `stale [ROOT]`.
   Exit 0 clean, 1 findings, 2 could not run. Durable.
5. **Pointer files.** For each page with non-empty `covers`: `.claude/rules/<page-slug>.md` with
   frontmatter `paths:` equal to `covers` and a generated body, and a block between the markers
   `<!-- docs.py pointers -->` and `<!-- /docs.py pointers -->` in `<dir>/AGENTS.md`, where `<dir>`
   is the longest literal directory prefix of each glob. The body names the page, its `read-when`
   and its H2 anchors. A file without the markers is created whole; one with them has only the
   block replaced. Committed, never hand-edited. Durable.
6. **Agent files.** Claude: `agents/{builder,reviewer,scout}.md`, frontmatter from the keys
   `name`, `description`, `tools`, `model`, `effort`, `maxTurns`, `permissionMode`, `isolation`,
   body in MUST/SHOULD/AVOID/REPORT sections, installed to `~/.claude/agents/`. Codex:
   `agents/{builder,reviewer,scout}.toml` with `name`, `description`, `developer_instructions`
   (byte-equal to the `.md` body), `model`, `model_reasoning_effort`, `sandbox_mode`, installed to
   `$CODEX_HOME/agents/`. Each installed copy carries a marker line; uninstall removes only marked
   files. The installer sets `worktree.baseRef: "head"` for Claude subagent worktrees. Durable.
7. **Records.** `.runs/<id>/approval.html` from `goal.py packet --approval`; one `cost:` line per
   session in `.runs/<id>/progress.md`, written by `run.sh` when the harness reports cost or tokens;
   `cause: context|logic|spec` on each closed blocking finding in `review.md`. Not durable.

## Data touched

None. Every artefact is a file in git; nothing is migrated, backfilled or deleted outside the
repository. Rollback is the previous tag reinstalled.

## Smallest change

Frontmatter, an index, heading anchors and the harnesses' own path-scoped loading: no new store,
no retrieval, no agent memory. `docs.py` reuses `link_check.py`'s slug rule and `goal.py`'s plan
parser. The installer gains one copy loop and one marker.

## Rejected options

- Agent memory scopes or a graph: no measured catch in v6; fresh context per role is the design.
- A model-judged done: eight mechanical rows are stronger.
- A second reviewer or a dollar budget: yield data does not support one; the founder rejected the other.
- Hand-written pointer files for M1: the founder chose generation from the start.
- Mid-tier builders: the founder chose the frontier tier at high effort.
- Pasting cited sections into packets: identifiers over text, so a builder reads the file.
