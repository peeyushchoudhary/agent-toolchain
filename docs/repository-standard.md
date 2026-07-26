# Repository structure standard

Version **1.1**. One layout for every project, so an agent entering any repository finds context in
the same place.

Canonical copy: `~/.claude/skills/progressive-disclosure/references/standard.md`.
Enforced by `validate_disclosure.py --standard`; migrated by `migrate_to_standard.py`.

The names were not invented. Each is the spelling already used in two or more existing projects; the
standard ratifies the majority and retires the synonyms.

## Required

```
README.md                          the human front page (see progressive-disclosure.md)
AGENTS.md                          contract, ≤400 words
CLAUDE.md                          exactly one line: @AGENTS.md
.github/pull_request_template.md   merge checklist — a markdown file, NOT a workflow
docs/README.md                     documentation index (never index.md)
docs/agents/README.md              route index: task → one guide → one command
docs/agents/disclosure.md          how the route works here (carries a version stamp)
docs/agents/lessons.md             cross-agent learning channel
docs/agents/personas/              project persona overlays and specialists
docs/agents/                       + area guides, guardrails.md, workflows.md, handoff-template.md
docs/architecture/                 how the system is built, one page per component
docs/product/                      intent, read through shipped behaviour
docs/decisions/                    accepted decision records
docs/runbooks/                     operational procedures
docs/archive/                      superseded material — NOT authoritative
```

Every directory above carries a `README.md` naming its purpose and authority level. That is what
keeps a required directory from becoming empty ceremony, and what a reader uses to know whether the
contents are current.

Add `<dir>/AGENTS.md` + `CLAUDE.md` (≤40 words, pure routing) to every source directory.

## Optional, when the project has the content

`docs/conventions/` · `docs/security/` · `docs/api/` · `docs/compliance/` · `docs/launch/` ·
`docs/superpowers/` (tool output — tolerated, never authoritative).

## Naming rules

| Rule | Rationale |
|---|---|
| Plural directory names (`agents/`, `decisions/`) | Matches the `AGENTS.md` convention; ends the `agent/` vs `agents/` split |
| `README.md`, never `index.md` | Renders on every forge; three projects already chose it |
| lowercase-kebab filenames | `HANDOFF_TEMPLATE.md` and `handoff-template.md` are the same document |
| History lives in `archive/` | A reader must tell current from superseded by path alone |

## Retired spellings

The migrator moves each automatically:

| Legacy | Standard |
|---|---|
| `docs/agent/` | `docs/agents/` |
| `docs/index.md` | `docs/README.md` |
| `docs/audit/`, `docs/audits/` | `docs/archive/…` |
| `docs/operations/` | `docs/runbooks/` |
| `docs/council/`, `docs/escalations/` | `docs/decisions/…` |
| `docs/founder/` | `docs/product/founder/` |
| `docs/handoffs/` | `docs/archive/handoffs/` |
| `docs/handoff.md` | `docs/agents/handoff.md` |
| `docs/RUNBOOK*.md` | `docs/runbooks/` |

**Domain content is never moved.** A directory holding data rather than documentation — a question
bank, a dataset, generated reports — stays exactly where it is.

## Migrating

```bash
migrate_to_standard.py <repo>            # plan only; writes nothing
migrate_to_standard.py <repo> --apply    # backs up, then executes
validate_disclosure.py <repo> --standard # verify afterwards
```

`--apply` refuses to run on a dirty git tree. Honour that refusal rather than reaching for
`--force`: a directory move landing on another agent's in-flight work is the one failure here that
is genuinely expensive to unpick. It never commits — the staged diff is yours to review.

For a repository with no git, the backup it takes first is the only undo. Confirm the backup path in
the output before continuing.

### Two traps found in real use

- **Creates are computed against the post-move tree.** Otherwise a file arriving via a move — say
  `docs/agent/README.md` landing at `docs/agents/README.md` — still looks missing, and the create
  step overwrites it with a skeleton. This was a data-loss bug, fixed.
- **Content moves can break the build.** Before moving anything, check whether a path is read by
  code. In one real migration six of seven proposed moves turned out to be referenced from a build
  file and two test classes. The migrator cannot know that; grep for the path outside `docs/` first.

## Versioning

Generated per-repo copies carry `<!-- progressive-disclosure standard vN -->`. The validator warns
when a repo's copy predates the current standard, so a fleet cannot drift invisibly. Bump
`STANDARD_VERSION` in `validate_disclosure.py` when the rules change.

**Do not regenerate `disclosure.md` to bump the stamp.** It replaces project-specific content with
the generic template — edit the stamp in place and add what is new.
