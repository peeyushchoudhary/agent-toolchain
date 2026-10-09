---
goal: S-2
title: Methodology v7.1 — context, roles and planning documents with progressive disclosure (D30)
gate: cd install && ./verify.sh
full_gate: cd install && ./install.sh --dry-run && ./verify.sh
milestones:
  M1: {tasks: [T1, T2, T3, T4, T5], e2e: "install/tests/e2e_install.sh"}
  M2: {tasks: [T6, T7, T8, T9], e2e: "install/skills/execution-methodology/tests/e2e_run.sh"}
touches: [interface]
protected: [docs/decisions/decisions.md#D1-D19, docs/goals/S-2/design.md#Interfaces, docs/goals/S-2/design.md#Data touched]
---

## Outcome

A goal is planned from `spec.md` (AC2), `design.md` when `touches:` names an interface (AC2) and
`plan.md`, whose tasks carry `reads:` (AC1); the spec is frozen at approval and its criteria are
traced to tasks (AC3, AC4). Pages under `docs/` carry a summary, `read-when`, `covers` and
`last-verified`, the index is generated, anchors resolve to line ranges, pointer files for both
harnesses are generated from `covers`, and stale pages are listed (AC5–AC8). Builder, reviewer and
scout agent files with model and effort ship to both harnesses (AC9); `goal.py packet --approval`
writes the approval page (AC10); always-loaded prose stays at or under 1,350 words and cost is
recorded, never enforced (AC11). `verify.sh` is green after every task. Decision record: D30; the
design is [design.md](design.md), the spec [spec.md](spec.md).

## Format notes (frozen with this plan; T2 teaches `goal.py` to read them)

`reads:` lines are prose to `goal.py` until T2 adds the field. `touches: [interface]` is read by
T2's lint; until then the key is carried unread. `spec.md` and the two design sections are listed
in `protected:` or protected by default from T2 on; the approval commit creates both files, so no
task lists them in `writes`. `ACn` references in task sections are the tracing T2 checks.
Every task leaves `verify.sh` green; a task that adds a check to `verify.sh` lands what the check
needs in the same commit.

## Tasks

### [x] T1 — decision record D30, spec, design, this plan, the index rows
writes: docs/decisions/decisions.md, docs/README.md, docs/goals/S-2/plan.md, docs/architecture/methodology.md
reads: docs/decisions/decisions.md#D29, docs/architecture/methodology.md#Accepted risks
D30 amends D29's "no new mechanism during the pilot" for S-2 and records the three founder
decisions; the stop-rule line in `methodology.md` says so; the index gains the three S-2 pages.

### [ ] T2 — `goal.py`: `reads:`, `touches:`, spec and design lint, default protection, AC tracing
writes: install/skills/execution-methodology/scripts/goal.py, install/skills/execution-methodology/tests/test_goal.py, install/skills/execution-methodology/tests/fixtures/**
tests-may-change: install/skills/execution-methodology/tests/test_goal.py, install/skills/execution-methodology/tests/fixtures/**
reads: docs/goals/S-2/design.md#Interfaces, docs/goals/S-2/spec.md, install/skills/execution-methodology/scripts/goal.py, install/skills/execution-methodology/tests/test_goal.py
`FIELD_RE` gains `reads`; a task with `writes:` and no `reads:` is a lint error (AC1). `touches:`
values are validated; any value but `none` without `docs/goals/<id>/design.md` is a lint error, as
is a missing `spec.md`, one over 400 words, or one lacking a required heading unless it uses the
two-line form (AC2). Row 4 and lint treat `spec.md` whole and `design.md#Interfaces` and
`design.md#Data touched` as protected without listing (AC3). Every `ACn` bullet in the spec must
appear in at least one task section, else lint fails (AC4). `lint` and `packet` print the `reads:`
of each task. About 80 lines. Planted tests in `test_goal.py`: a task without `reads:`; a goal
without a spec; `touches: [interface]` without a design; a post-approval `[Tn]` commit editing
`spec.md` reported by row 4 with nothing listed in `protected:`; an untraced `AC3`; this plan parses
(nine tasks, two milestones, every task with `reads:`); the S-1 plan still parses and lints with
its `touches: [none]` and no spec, because closed goals are not relinted (a `spec.md` is required
only when the approval tag is absent or later than this change: state the chosen rule in a comment).

### [ ] T3 — `docs.py`: frontmatter lint, the generated index, `reads` resolution
writes: install/skills/execution-methodology/scripts/docs.py, install/skills/execution-methodology/tests/test_docs.py
tests-may-change: install/skills/execution-methodology/tests/test_docs.py
reads: docs/goals/S-2/design.md#Interfaces, install/tests/link_check.py, install/skills/execution-methodology/scripts/goal.py, install/skills/execution-methodology/tests/fixtures/goal_fixture.py
New `scripts/docs.py` (about 150 lines by T6): `lint [ROOT]` checks every tracked `docs/**/*.md`
except `docs/README.md` and `docs/goals/**` for the four frontmatter keys, `summary` at or under 120
words, `last-verified` a date, `covers` a list, and `docs/README.md`'s table equal to `index`'s
output (AC5); `index [ROOT]` prints the table, one row per page with its link and `read-when`;
`reads <Tn> --goal <id>` resolves each entry of the task's `reads:` line to `path:start-end`
(anchor = the GitHub slug of a heading, `link_check.py`'s rule; the range runs to the next heading
of the same or a higher level), `path` for a whole file, `term: <word>` for a bare term, and exits 1
naming a missing anchor or file (AC6). Exit codes 0, 1, 2 as the design says. `test_docs.py`
plants: a page without `last-verified`; a 121-word summary; an index missing a row; an anchor that
does not exist; a heading with punctuation resolved by slug; a `reads:` line with all three entry
kinds. `verify.sh` is not wired here: T5 does it with the frontmatter.

### [ ] T4 — the instructions: `SKILL.md`, planning, roles, security checklist, design, agents
writes: install/global.md, install/skills/execution-methodology/SKILL.md, install/skills/execution-methodology/references/**, install/skills/execution-methodology/agents/**, install/skills/execution-methodology/tests/test_rules.py, install/tests/test_size.py, AGENTS.md, docs/architecture/personas.md, docs/README.md
tests-may-change: install/skills/execution-methodology/tests/test_rules.py, install/tests/test_size.py
reads: install/skills/execution-methodology/SKILL.md, install/skills/execution-methodology/references/design.md, install/skills/execution-methodology/agents/builder.md, install/skills/execution-methodology/agents/reviewer.md, install/skills/execution-methodology/tests/test_rules.py, docs/goals/S-2/design.md#Interfaces, analysis/councils-2026-10-09/personas/synthesis.md, analysis/councils-2026-10-09/personas/drafts/builder.md, analysis/councils-2026-10-09/personas/drafts/reviewer.md, analysis/councils-2026-10-09/personas/drafts/scout.md, analysis/councils-2026-10-09/personas/drafts/chief-planning.md
`SKILL.md`: loop step 2 names `reads:` and `docs.py reads`; the format block gains `reads:` and
the six `touches:` values; a "Before a goal" paragraph points at `references/planning.md`; the
design-review trigger is widened; a closed blocking finding carries `cause: context|logic|spec`;
one line points at `references/roles.md`. Always-loaded total stays at or under 1,350 words (AC11;
today 1,263), so words are shed elsewhere in `SKILL.md`. New `references/planning.md` ≤400 words:
interview the founder → `spec.md` → scout → `design.md` when `touches:` says so → `plan.md` with
one-session tasks (`writes`, `reads`, `tests-may-change`, the named test) → at most five questions as
`- Q:` lines under Parked, answered into Decisions at approval → the other vendor's review →
approval tag; with the spec, design and frontmatter templates. New `references/roles.md` ≤150
words: builder frontier tier at high effort (Claude `opus`, Codex `gpt-6.1-sol`); scout cheap tier
(`haiku`, `gpt-6-luna`); reviewer the other vendor's strongest reasoning model at high effort;
chief the session; cost recorded, never enforced; the structural caps. New
`references/security-checklist.md` ≤150 words, handed to the merge reviewer when `touches:` names
data, auth or external. `references/design.md`: the widened trigger; builders read Interfaces.
The three Claude agent files are written from the council drafts named in `reads:` (the
2026-10-09 persona council: four experts and an adversarial synthesis, recorded under
`analysis/`, this machine only): `agents/builder.md` (body ≤350 words), `agents/reviewer.md`
(≤350), new `agents/scout.md` (≤200), each with MUST, SHOULD, AVOID and REPORT sections of one
behaviour per line and frontmatter in the keys the Claude Code subagent reference lists (`tools`,
`model`, `effort`, `maxTurns`, `permissionMode`, `isolation`); the builder keeps
`isolation: worktree`, which needs the base setting T7 installs. The chief's planning lines (≤200
words) are the MUST/SHOULD/AVOID block of `references/planning.md`. `references/roles.md` records
the aliases (`opus`, `gpt-6.1-sol`; `haiku`, `gpt-6-luna`), that `high` is the portable effort, and
that `CLAUDE_CODE_EFFORT_LEVEL` overrides frontmatter so `run.sh` never exports it. New
`docs/architecture/personas.md` (frontmatter per T5's standard, `covers:` the agents directory):
what each persona file guards against, the evidence behind each adopted line with its source, and
what was left out and where it lives instead (the public record of the council). `test_rules.py`:
the new files join `SKILL_FILES`, `references/planning.md` leaves `RETIRED`, the scout and the
reviewer are read-only, each agent body is at or under its budget. Root `AGENTS.md` stays a table
of contents under 300 words; `docs/README.md` gains the personas row.

### [ ] T5 — this repository's `docs/` under the standard; `docs.py lint` in the gate; M1's e2e
writes: docs/README.md, docs/architecture/**, docs/product/**, docs/runbooks/**, docs/archive/**, README.md, install/verify.sh, install/tests/e2e_install.sh, install/tests/test_install.py, install/README.md
tests-may-change: install/tests/e2e_install.sh, install/tests/test_install.py
reads: docs/goals/S-2/design.md#Interfaces, docs/architecture/repository-standard.md, install/verify.sh, install/tests/e2e_install.sh
Frontmatter on every page under `docs/` outside `goals/` and the index. New `docs/product/prd.md`
for this repository (summary ≤120 words: the methodology as a product; its users the founder and
the chief session; the jobs; the principles D29 fixes; the surface `install/` ships; the body
unbounded). `methodology.md` gains `covers: [install/**]` and is the area page for `install/`.
`repository-standard.md` lists the new layout: `docs/product/prd.md`, `docs/product/features/`,
`docs/goals/<id>/{spec,design,plan}.md`, the generated pointer files; and the product-repository
minimum gains the PRD summary and `docs.py lint` in the gate. `docs/README.md` is regenerated by
`docs.py index` (its first line and the install link stay as prose above the table). `verify.sh`
runs `docs.py lint` over this repository as check `docs` (AC5). `e2e_install.sh` asserts `docs.py`
and the three Claude agent files are installed and `docs.py --help` runs from each copy (AC9's
Claude half). **M1 ends here**: the other vendor's diff review of `goal/S-2/approved..HEAD`, `done`
for M1, merge.

### [ ] T6 — `docs.py`: pointer generation and staleness
writes: install/skills/execution-methodology/scripts/docs.py, install/skills/execution-methodology/tests/test_docs.py, .claude/rules/**, install/AGENTS.md, install/verify.sh, docs/architecture/repository-standard.md
tests-may-change: install/skills/execution-methodology/tests/test_docs.py
reads: docs/goals/S-2/design.md#Interfaces, install/skills/execution-methodology/scripts/docs.py, install/AGENTS.md
`pointers [ROOT] [--check]`: for each page with non-empty `covers`, writes
`.claude/rules/<page-slug>.md` (frontmatter `paths:` = `covers`; body: the page, its `read-when`,
its H2 anchors as `path#anchor` lines) and the marked block in `<dir>/AGENTS.md` for the longest
literal directory prefix of each glob; `--check` exits 1 when a regeneration would change a file,
and `lint` runs it (AC7). `stale [ROOT]`: for each page with `covers`, the last commit date of the
covered paths (`git log -1 --format=%cI -- <globs>`) against `last-verified`; lists the stale
pages, exit 1 when any (AC8). `verify.sh` runs `pointers --check` inside `docs` and `stale` as a
printed warning that never fails the gate: the milestone close re-verifies the page and bumps the
date. This repository's own pointers are generated and committed: `.claude/rules/methodology.md`
and the block in `install/AGENTS.md` (`.claude/` is not ignored here). `test_docs.py` plants:
a page whose `covers` changed after `last-verified`; a hand-edited pointer caught by `--check`; an
`AGENTS.md` with other content kept around the block; two pages covering the same directory.

### [ ] T7 — roles shipped to both harnesses: Codex agent TOML, the installer
writes: install/skills/execution-methodology/agents/**, install/install.sh, install/verify.sh, install/tests/test_install.py, install/tests/e2e_install.sh, install/README.md, docs/runbooks/codex.md
tests-may-change: install/tests/test_install.py, install/tests/e2e_install.sh
reads: docs/goals/S-2/design.md#Interfaces, install/skills/execution-methodology/references/roles.md, install/skills/execution-methodology/agents/builder.md, install/install.sh, install/tests/test_install.py, docs/runbooks/codex.md, analysis/councils-2026-10-09/personas/drafts/builder.toml, analysis/councils-2026-10-09/personas/synthesis.md#Harness caveats T4 and T7 must handle
New `agents/builder.toml`, `reviewer.toml`, `scout.toml` for Codex custom agents: `name`,
`description`, `developer_instructions` (byte-equal to the matching `.md` body, asserted by a
test in `test_install.py` so the two never drift), `model`, `model_reasoning_effort`,
`sandbox_mode`; the schema was verified against `codex-cli 0.160.0` on 2026-10-09 and the file
header records the version checked. `install.sh` copies the `.md` agents to `~/.claude/agents/`
and the `.toml` agents to `$CODEX_HOME/agents/`, each with a marker line; sets
`worktree.baseRef: "head"` in `~/.claude/settings.json` with its JSON editor, because a subagent
worktree otherwise branches from the default branch rather than the chief's HEAD; `--dry-run`
lists all of it; `--uninstall` removes only marked files and that one key; an unmarked file of
the same name is left alone and reported (AC9). `verify.sh --installed` parity covers the agent
files. `e2e_install.sh` asserts both harnesses' agent files and the setting after install and
their absence after uninstall; a test asserts `run.sh` never exports `CLAUDE_CODE_EFFORT_LEVEL`.
`codex.md` documents the agents, whether `run.sh`'s `--ignore-user-config` session still loads
`$CODEX_HOME/agents/` (verify; if not, `-c agents.<name>.config_file=<path>` per session), and
how a Codex builder gets its own worktree (a Codex-side option if one exists, else the Codex chief
runs `git worktree add` and names the path in the packet).

### [ ] T8 — `goal.py packet --approval`, `cause:` counts, the cost line
writes: install/skills/execution-methodology/scripts/goal.py, install/skills/execution-methodology/scripts/run.sh, install/skills/execution-methodology/tests/test_goal.py, install/skills/execution-methodology/tests/test_run.py
tests-may-change: install/skills/execution-methodology/tests/test_goal.py
reads: docs/goals/S-2/design.md#Interfaces, install/skills/execution-methodology/scripts/goal.py, install/skills/execution-methodology/scripts/run.sh, install/skills/execution-methodology/tests/test_goal.py
`packet --approval` writes `.runs/<id>/approval.html`: the spec, the design's Structure and
Interfaces, the task table (title, `writes`, `reads`, the named test), `touches` and `protected`,
and the `- Q:` lines (AC10); about 60 lines, standard library only, no external script or style.
`packet` counts `cause:` tags across closed blocking findings in `review.md` and prints the `cost:`
lines of `progress.md`. `run.sh` appends one `cost:` line per session to `.runs/<id>/progress.md`:
harness, wall seconds, and the cost or token totals the harness's JSON output carries when present
(Claude `total_cost_usd`; Codex token usage), never a verdict (AC11). Tests: the approval page from
the fixture goal names every task; `cause:` counts; a fake-harness `run.sh` session writes the line
(in `test_run.py`, new, or inside `test_goal.py` where the existing `run.sh` test lives).

### [ ] T9 — end-to-end, measurements, the pages to v7.1
writes: install/skills/execution-methodology/tests/e2e_run.sh, install/skills/execution-methodology/tests/fixtures/**, docs/product/measurements.md, docs/architecture/methodology.md, docs/architecture/repository-standard.md, docs/runbooks/**, docs/README.md, README.md, install/README.md, AGENTS.md
tests-may-change: install/skills/execution-methodology/tests/e2e_run.sh, install/skills/execution-methodology/tests/fixtures/**
reads: install/skills/execution-methodology/tests/e2e_run.sh, docs/product/measurements.md, docs/architecture/methodology.md, docs/goals/S-2/spec.md
`e2e_run.sh`'s scratch goal gains a `spec.md` with two criteria traced to its tasks, `reads:`
lines, one `docs/` page with frontmatter and `covers`, its generated pointer files, and a gate
that runs `docs.py lint`; the run asserts the approval page and a `cost:` line exist and that
`goal.py done` prints DONE for each harness as today. `measurements.md`, dated: `install/` non-test
and test line counts, `goal.py` and `docs.py` sizes, always-loaded words (AC11), on-demand reference
words. `methodology.md` describes v7.1 (the document set, the disclosure layers, the roles, the
amended stop rule) and `last-verified` is bumped; `repository-standard.md`, the runbooks, the
README and `AGENTS.md` say what is true after S-2. **M2 ends here**: the other vendor's diff review,
`done` for M2, merge.

## Decisions

- 2026-10-09 founder: the v7.1 proposal is accepted with three decisions: pointer files are
  generated from the start, never hand-written; builders run on the frontier tier at high effort;
  S-2 M2 runs now, and D29's "no new mechanism during the pilot" is amended by D30. Earlier the same
  day: no per-milestone dollar budget; cost is recorded, never enforced.
- 2026-10-09 chief: a design page is written although v7 requires none for `touches: [interface]`,
  because S-2 is the first goal under the widened trigger it introduces; its review runs with the
  plan review. `docs.py` is a separate script rather than more `goal.py`, so the document checks
  run in a repository with no open goal. `reads:` entries are repository-relative paths.
- 2026-10-09 founder: each persona carries rich instructions researched from the vendors'
  documentation and the field, without over-engineering or drift. A council of four experts
  (Anthropic docs, OpenAI/Codex docs, open-source agent files, engineering craft) and an
  adversarial synthesis ran the same day (`analysis/councils-2026-10-09/personas/`, this machine
  only; the public record is `docs/architecture/personas.md`, T4). Adopted: one behaviour per
  line in MUST/SHOULD/AVOID/REPORT; the scope declaration ("say so in one sentence, then do the
  task as written"; out-of-scope actions 17.1% → 0.0% in the overeager-agents study); copy the
  nearest existing pattern; no speculative abstraction; a wrong test is reported red, never edited
  or skipped; the behaviour, not the test's inputs; the gate line pasted as printed; the reviewer
  reads the diff and distrusts the report, reports every finding classed rather than pre-filtered,
  one scenario-backed finding per defect, no style or pre-existing issues. Rejected as folklore or
  machinery: role preambles, capability lists, confidence scores, status vocabularies, "think step
  by step", "verify your work" lines, 80-character titles. Budgets: builder and reviewer ≤350
  words, scout ≤200, chief planning ≤200. Aliases: `opus`/`gpt-6.1-sol` at `high` (the founder's
  frontier choice), `haiku`/`gpt-6-luna`. `isolation: worktree` is kept with the installer setting
  the worktree base to the chief's HEAD.
- 2026-10-09 chief: the approval commit creates `spec.md` and `design.md`; the plan's `protected:`
  lists the two design sections and D1–D19 explicitly until T2 protects the spec by default, so
  `goal.py lint` as shipped by S-1 passes on this plan (it cannot list `spec.md` whole without a
  `writes` intersection in T1).

## Parked

- Pilot migration by hand after S-2 M1 (founder; `docs/runbooks/migrate-v5.md`), so the pilot
  starts with a PRD summary, a spec and `reads:` lines.
- The stale `verify.sh` dangling-name exclusions from S-1 T8 (T5 or T9 may drop them when the
  named files are confirmed gone).
