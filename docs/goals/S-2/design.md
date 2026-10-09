# S-2 design

Current decisions only. Written because S-2 changes the `plan.md` format and the installed file set,
which every later goal depends on.

## Structure

One new script, `scripts/docs.py`, holds everything about the documents under `docs/`: frontmatter
lint, index generation, `reads:` resolution, pointer generation and staleness. `goal.py` grows only
where the plan is concerned: the `reads:` field, the widened `touches:`, spec and design lint,
default protection, acceptance-criteria tracing and the approval page. Three on-demand references
(`planning.md`, `roles.md`, `security-checklist.md`) and three agent files per harness carry the
words. `install.sh` ships the agent files and one setting. `run.sh` appends a cost line per session
and names the Codex agent files; its permission model is untouched.

## Interfaces

1. **`plan.md`.** A task may carry `reads:` after `writes:`: a comma-separated list of repository
   paths, `path#anchor` entries or bare terms. Like `writes`, it sits outside the frozen view and a
   change needs a Decisions line. `touches:` accepts `none`, `data`, `auth`, `external`,
   `interface`, `ui`; any value but `none` requires `docs/goals/<id>/design.md`. `spec.md` is
   required for every goal whose approved commit contains it and is protected whole from the
   approval tag; `design.md#interfaces` and `design.md#data-touched` are protected when the page
   exists; none needs listing in `protected:`. Anchors in `reads:` and `protected:` are GitHub
   heading slugs; `dNN` and `D1-D19` keep their meaning; a slug in `protected:` protects that
   section only. Every `ACn` in the spec appears in at least one task section. Durable.
2. **`spec.md`.** ≤400 words with the headings *Users and problem*, *What changes for the user*,
   *Acceptance criteria* (`ACn WHEN … THE SYSTEM SHALL …` bullets), *Non-goals*, *Constraints*; or the
   two-line form `What changes for the user: nothing` plus the criteria as the goal's tests. Durable.
3. **Document frontmatter.** Every tracked `docs/**/*.md` except `docs/README.md` and `docs/goals/**`
   starts with YAML-style frontmatter: `summary` (≤120 words), `read-when` (one line), `covers` (a
   flow list of repository-relative globs, no `..` or absolute paths, may be `[]`), `last-verified`
   (`YYYY-MM-DD`; stale when a covered path's last commit is on a later day, or on that day and
   later than the page's own last commit). `docs/README.md` holds the table `docs.py index` prints:
   one row per page, its link and `read-when`. Durable.
4. **`docs.py` commands.** `lint [ROOT]` (frontmatter, index, generated pointers); `index [ROOT]`;
   `reads <Tn> --goal <id>` printing `path:start-end` per entry, `path` for a whole file, `term:
   <word>` for a term, exit 1 on a missing anchor; `pointers [ROOT] [--check]`; `stale [ROOT]`.
   Exit 0 clean, 1 findings, 2 could not run. The slug rule lives here; `link_check.py` imports it.
   Durable.
5. **Pointer files.** For each page with non-empty `covers`: `.claude/rules/<page-slug>.md` with
   frontmatter `paths:` equal to `covers` and a generated body, and a block between the markers
   `<!-- docs.py pointers -->` and `<!-- /docs.py pointers -->` in the nearest existing `AGENTS.md`
   at or above the longest literal directory prefix of each glob, else a new one at that prefix;
   one block per file lists every page mapping to it. The body names the page, its `read-when` and
   its H2 anchors. A file is created only when absent; one with the markers has only the block
   replaced; an existing file without them is left alone and reported. Output whose page no longer
   declares `covers` is removed. Destinations resolve inside the repository. Committed, never
   hand-edited. Durable.
6. **Agent files.** Claude: `agents/{builder,reviewer,scout}.md`, frontmatter from the keys `name`,
   `description`, `tools`, `model`, `effort`, `maxTurns`, `permissionMode`, `isolation`, body in
   MUST/SHOULD/AVOID/REPORT sections, installed to `~/.claude/agents/`. Codex:
   `agents/{builder,reviewer,scout}.toml` with `name`, `description`, `developer_instructions`
   (byte-equal to the `.md` body), `model`, `model_reasoning_effort`, `sandbox_mode`, installed to
   `$CODEX_HOME/agents/`. Each installed copy carries a marker line; uninstall removes only marked
   files. The installer sets `worktree.baseRef: "head"` in `~/.claude/settings.json` only when the
   key is absent, after backing the file up; uninstall removes it only while still `"head"`. Durable.
7. **Records.** `.runs/<id>/approval.html` from `goal.py packet --approval`; one `cost:` line per
   session in `.runs/<id>/progress.md`, written by `run.sh` when the harness reports cost or tokens;
   `cause: context|logic|spec` on each closed blocking finding in `review.md`. Not durable.

## Data touched

Nothing in a store, nothing migrated. In git: every document, pointer file and agent file. Outside
git, on this machine only: the installer writes marked agent files into both harness homes and one
key in `~/.claude/settings.json` after backing that file up; uninstall removes the marked files and
the key only while unchanged. Rollback is `install.sh --uninstall`, then the previous tag's
installer; the backups hold what was there before.

## Smallest change

Frontmatter, an index, heading anchors and the harnesses' own path-scoped loading: no new store, no
retrieval, no agent memory. `docs.py` reuses `goal.py`'s plan parser; `link_check.py` reuses its
slug. The installer gains one copy loop, one marker and one setting.

## Rejected options

- Agent memory scopes or a graph: no measured catch in v6; fresh context per role is the design.
- A model-judged done: eight mechanical rows are stronger.
- A second reviewer or a dollar budget: yield data does not support one; the founder rejected the other.
- Hand-written pointer files: the founder chose generation from the start.
- Mid-tier builders: the founder chose the frontier tier at high effort.
- Pasting cited sections into packets: identifiers over text, so a builder reads the file.
