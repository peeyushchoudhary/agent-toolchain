# The shared repository structure standard

One layout for every project, so an agent entering any repository finds context in the same place.
Enforced by `validate_disclosure.py --standard`; migrated by `migrate_to_standard.py`.

The names below were not invented. Each is the spelling already used in two or more existing
projects; the standard ratifies the majority and retires the synonyms.

## Required

```
README.md                      the human front page — see "The README contract" below
AGENTS.md                      contract, ≤400 words
CLAUDE.md                      exactly one line: @AGENTS.md
.github/pull_request_template.md   the merge checklist (a markdown file, NOT a workflow)
docs/README.md                 documentation index (never index.md)
docs/agents/README.md          route index: task → one guide → one verification command
docs/agents/disclosure.md      how the route works here (carries a standard version stamp)
docs/agents/lessons.md         cross-agent learning channel — see below
docs/agents/                   + area guides, guardrails.md, workflows.md, handoff.md
docs/architecture/             how the system is built
docs/product/                  intent, read through shipped behaviour
docs/decisions/                accepted decision records
docs/runbooks/                 operational procedures
docs/archive/                  superseded and point-in-time material — NOT authoritative
```

Every directory above carries a `README.md` naming its purpose and authority level. That is what
keeps a required directory from becoming empty ceremony, and it is what an agent reads to know
whether the contents are current.

## The project-persona decision

Every standard repository makes the decision explicit; zero project personas is not silently
treated as proof that the shared base pool is sufficient.

- **Project personas:** keep their canonical sources in `docs/agents/personas/*.md`, maintain
  `docs/agents/personas.md`, and link that guide directly from `docs/agents/README.md`.
- **Base pool only:** put this exact single-line marker in `docs/agents/README.md`, with a real
  project-specific reason:

```html
<!-- agent-personas: {"mode":"base-only","reason":"domain-neutral library; base reviewers cover its risks"} -->
```

The validator warns when neither decision exists, rejects malformed/duplicate/conflicting
decisions, and errors when persona sources are not directly routed. The warning permits a gradual
fleet migration; onboarding must still stop until the choice is recorded. Never generate a
`base-only` reason automatically.

Add `<dir>/AGENTS.md` + `CLAUDE.md` (≤40 words, pure routing) to every source directory. This is
the layer that fires without the agent choosing to read anything, because both harnesses load the
nearest entry file by proximity.

## Optional, when the project has the content

`docs/conventions/` · `docs/security/` · `docs/api/` · `docs/compliance/` · `docs/superpowers/`
(tool output — tolerated, never authoritative).

## Naming rules

| Rule | Rationale |
|---|---|
| Plural directory names (`agents/`, `decisions/`) | Matches the `AGENTS.md` convention; ends the `agent/` vs `agents/` split |
| `README.md`, never `index.md` | Renders on every forge; three projects already chose it |
| lowercase-kebab filenames | `HANDOFF_TEMPLATE.md` and `handoff-template.md` are the same document |
| History lives in `archive/` | A reader must be able to tell current from superseded by path alone |

## Retired spellings

The migrator moves each of these automatically:

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

Domain content is never moved. A directory that holds data rather than documentation — a question
bank, a dataset, generated reports — stays exactly where it is.

## The learning channel

`docs/agents/lessons.md` is where an agent records something that misled it. It exists in the repo,
not in an agent's private memory, because that is the only place every harness can read *and*
write: one agent's memory directory is invisible to the others, and generated caches are usually
gitignored. A lesson in the wrong place teaches exactly one agent.

Entries are dated, two lines — what misled, what is actually true — newest first. If the correction
belongs in a guide, fix the guide instead; prune a lesson once its guide is fixed.

## The README contract

`AGENTS.md` routes an agent. `README.md` answers a human who has never seen the project and is
deciding whether it is real. They are different documents for different readers, and collapsing
either into the other loses one of them.

Seven sections, enforced by `validate_disclosure.py --readme`. Heading wording is flexible — the
check accepts the common synonyms — but each question must be answered somewhere:

| Section | The question it answers |
|---|---|
| Overview | What is this, and what problem does it solve? |
| Current state | What ships today, what is left, and where is the plan of record? |
| Product requirements | Where are the PRDs? (a table with links, never the PRD text itself) |
| Architecture | How is it built? **Must contain a diagram** in this section |
| Components | One row per component: responsibility, entry point, deep-dive link |
| Run locally | How do I start it? |
| Working in this repository | The agent route, and how work lands |

**The README indexes; it does not duplicate.** Low-level design lives in
`docs/architecture/<component>.md`, one file per component, linked from the component table. A
README that inlines every component's design grows past the point where anyone updates it, and then
it is worse than absent — it is confidently wrong.

**Prefer Mermaid to an exported image.** GitHub renders ```mermaid natively, it diffs line by line,
and an agent can edit it. A PNG satisfies the check but nobody will ever update it.

**Update it with the change, not after.** The validator proves the sections exist; only a person can
say whether they are still true. That question is asked in the PR template, at merge time.

## GitHub

GitHub stores code and config. Nothing deploys from it, nothing runs on it, and no gate lives there.

| Rule | Why |
|---|---|
| Every project has a GitHub repo | One laptop is not a backup. Session start flags a project that has none |
| **Private, always** | Verified on every session. Public is treated as a critical finding, never a default |
| Actions disabled, no workflows | Nothing should run on a push. `.github/pull_request_template.md` is a markdown file, not a workflow — do not delete it as a violation |
| No LFS, Packages, or Codespaces | The only GitHub features that bill on a personal account |
| Wiki, Projects, Issues off | Not a cost — each is a place documentation or work tracking lives *outside* the repository route |
| PRs at milestone granularity | Unless a change is explicitly scoped smaller |
| Merge commits, not squash | With no CI, the commit history is the audit trail; the per-commit graph refresh already indexed each one |

**Two rules GitHub would charge for are enforced locally instead**, by the `pre-push` hook that
`install_hooks.py` installs — secret scanning on a private repo needs paid Secret Protection, and
protected branches need a paid plan. The hook blocks credentials in the pushed range, files over
10 MB, and direct pushes to the default branch. It costs nothing and it runs where the work happens.

The secret scan reads every commit in the pushed range, not the net diff: a credential added in one
commit and removed in the next still ships to the server and stays recoverable there.

```bash
check_github.py <repo>              # is this project stored, private, and quiet?
check_github.py --sweep <dir>       # one line per project — the fleet view
check_github.py <repo> --apply-settings   # disable Wiki/Projects/Issues (never touches visibility)
```

Nothing in this toolkit creates a repository, changes visibility, or pushes. Those are the human's
call, every time.

## Versioning

Generated per-repo copies carry `<!-- progressive-disclosure standard vN -->`. The validator warns
when a repo's copy predates the current standard, so a fleet of repos cannot drift invisibly.
Bump `STANDARD_VERSION` in `validate_disclosure.py` when the rules change.

## Migrating

```bash
migrate_to_standard.py <repo>            # plan only; writes nothing
migrate_to_standard.py <repo> --apply    # backs up, then executes
validate_disclosure.py <repo> --standard # verify afterwards
```

`--apply` refuses to run on a repository with uncommitted changes. Honour that refusal rather than
reaching for `--force`: a directory move landing on top of another agent's in-flight work is the
one failure here that is genuinely expensive to unpick. It never commits — the staged diff is
yours to review.

For a repository with no git, the backup it takes first is the only undo. Confirm the backup path
in the output before continuing.
