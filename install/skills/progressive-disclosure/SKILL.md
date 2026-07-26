---
name: progressive-disclosure
description: Use when setting up, auditing, or repairing how a repository routes a coding agent to the right context — authoring AGENTS.md / CLAUDE.md entry files, building or fixing an agent-docs index, deciding what belongs in an area guide, or when agent instructions have grown into a dump nobody can follow. Also use when a repo has no agent docs at all and needs them.
---

# Progressive disclosure for coding agents

A coding agent should read a short route, not a library. The goal is that any task loads **one
entry file, one index row, and one guide** before touching code — and that the route stays true as
the repository changes.

Disclosure fails in two directions. Too little: the agent explores blindly and rediscovers the
codebase every session. Too much: a 4,000-word instruction file that gets skimmed, so its
invariants may as well not exist.

## The three layers

| Layer | File | Budget | Job |
|---|---|---|---|
| 1. Contract | root `AGENTS.md` (+ `CLAUDE.md` importing it) | ≤ 400 words | Invariants that are true everywhere: safety rules, what must never break, where to go next |
| 2. Index | `docs/agents/README.md` | ≤ 600 words | A routing table: task → **one** guide → **one** verification command |
| 3. Scoped | `<dir>/AGENTS.md` (+ `CLAUDE.md`) | ≤ 40 words | "You are in `web/`. Follow root `AGENTS.md`, then read `../docs/agents/web.md`." |

Layer 3 is the highest-leverage and the most often missing. Harnesses load the nearest entry file
automatically as an agent works in a subtree, so it is the only layer that fires **without the
agent choosing to read anything**. Every top-level source directory should have one.

Keep both filenames per directory: `AGENTS.md` holds the content, `CLAUDE.md` is one line —
`@AGENTS.md` — so Claude Code and Codex read the same text and cannot drift.

## Authoring rules

**Route, don't restate.** A scoped file that explains the architecture has become a fourth copy of
the truth. It should say where you are, what to read next, and nothing else.

**One verification command per row.** An index row that ends in "run the tests" is not routing. It
should name the exact command an agent can run for that area.

**State an authority order.** When the code, the guides, and old plans disagree, the agent needs a
rule, not a judgement call. Name which wins — normally: current code and tests > maintained guides
> product docs > historical plans and reports.

**Demote history explicitly.** Old plans, handoffs, screenshots, and session reports are rationale,
not truth. Say so in layer 1, by path, or agents will cite a superseded plan as current behavior.

**Write budgets down, then check them.** Every layer above has a word budget because disclosure
degrades silently — files only ever grow.

## Validate the route

A route nobody checks is a route that rots. Renaming a guide breaks it silently, and the failure
surfaces as an agent that "didn't follow instructions."

```bash
python3 ~/.claude/skills/progressive-disclosure/scripts/validate_disclosure.py .
```

It crawls the disclosure graph from the root entry files, following markdown links and `@imports`,
and reports:

| Signal | Meaning |
|---|---|
| `broken-link` (error) | A link or `@import` that does not resolve — the route is broken now |
| `missing-make-target` / `missing-script` / `missing-just-recipe` / `missing-task` (error) | A documented command that does not exist; an agent will run it and fail. Covers `make`, `pnpm`/`npm`/`yarn` scripts, `just` recipes, and `Taskfile` tasks |
| `orphan-doc` (warn) | A guide in an agent-docs directory that nothing routes to |
| `unscoped-dir` (warn) | A source directory with no layer-3 entry file |
| `over-budget` / `too-deep` (warn) | Disclosure decaying into a dump, or too many hops before real work |
| `stale-path` (warn) | A guide cites a code path that resolves nowhere — the docs describe a world that moved |
| `standard-placeholder` (error) | Generated scaffolding still contains TODOs; the repo was bootstrapped and never finished |
| `standard-version-drift` (warn) | This repo's generated copies predate the current standard |
| `readme-*` (error, under `--readme`) | The human front page is missing a section, a diagram, a PRD link, or a component |
| `readme-stale` (warn, under `--vs REF`) | Source changed since REF but the README did not |

Exit 1 on any error, or on warnings with `--strict`. `--json` for machine use. Wire it into the
repo's check gate so the route is verified like any other invariant.

## The README is a separate deliverable

`AGENTS.md` routes an agent; `README.md` answers a human deciding whether the project is real.
`--readme` enforces seven sections — overview, current state, product requirements, architecture
(with a diagram), components, run locally, working in this repository — plus resolvable links, a
link to every PRD, and a mention of every source directory.

The README **indexes**; it does not duplicate. Low-level design belongs in
`docs/architecture/<component>.md`, one file per component, linked from the component table. Full
rules in `references/standard.md`.

## Is the project actually stored anywhere?

```bash
check_github.py <repo>          # stored, private, and nothing running or billing?
check_github.py --sweep <dir>   # one line per project — the fleet view
```

GitHub is storage for code and config; nothing deploys from it. The checks that matter are: does a
remote exist at all, is it **private**, is any work unpushed, and is anything enabled that runs or
bills. Session start reports this in every project.

It reports. It never creates a repository, changes visibility, or pushes — those are the human's
call. Remote data is cached for 24h so session start stays fast.

## The shared cross-project standard

One layout for every repository, so an agent entering any project finds context in the same place:
`AGENTS.md` + `CLAUDE.md` + `docs/README.md` + `docs/agents/README.md`, with
`docs/{agents,architecture,product,decisions,runbooks,archive}/` each carrying a README that states
its authority level. Full rules, naming decisions, and the table of retired spellings are in
`references/standard.md`.

```bash
validate_disclosure.py <repo> --standard   # enforce it
migrate_to_standard.py <repo>              # plan a migration; writes nothing
migrate_to_standard.py <repo> --apply      # back up, move with git mv, rewrite links
```

The migrator refuses to apply to a repository with uncommitted changes, never commits, and rewrites
every markdown link a move invalidated. Read `references/standard.md` before running it.

## Setting this up in a project

Moved to the `project-onboarding` skill, which owns the end-to-end procedure: migrate, write the
route, wire the gate, install hooks, add specialists. It spans GitHub and personas as well as the
route, so it does not belong here.

This skill owns the *standard* — the layers, the taxonomy, the budgets, and the validator.
`project-onboarding` owns *applying* it to a repository.

Two rules that live here because they are properties of the route, not of onboarding:

- **Git hooks are never shared through git.** `install_hooks.py` runs once per *clone*, not once per
  project. Session start flags a clone that is missing them.
- **Never run `graphify claude install`.** It appends a section to `CLAUDE.md`, which breaks the
  standard's one-line rule and makes that guidance invisible to every non-Claude agent.

## Cross-agent portability

Decide deliberately where each piece lives, because the layers have different reach:

| Mechanism | Reach |
|---|---|
| `AGENTS.md` / scoped entry files / routed guides | **Every agent.** `AGENTS.md` is the shared convention; both Claude Code and Codex load the nearest one by proximity |
| A validator script + a `make` target | **Every agent** — anything that can run a shell command |
| Skills in `~/.claude/skills/` | Claude Code only. Codex reads its own skills directory |
| Hooks in `~/.claude/settings.json` | Claude Code only. Codex has its own hooks file |

So put the *knowledge* in the repo and treat skills and hooks as accelerators for one harness.
Guidance that exists only in a skill silently does not apply to the other agent working in the same
repository — and that failure is invisible, because the other agent never announces what it did not
read. When a rule matters, it belongs in a routed guide.

## Reading discipline

On the agent side, the route only helps if it is followed:

- Read layer 1 and the one routed guide. Do not preload the whole `docs/agents/` directory.
- Prefer current code, tests, and generated contracts over any prose that describes them.
- Do not treat reports, handoffs, or generated output as current truth without checking source.
- If the repo has a code graph, navigate it rather than reading trees — see `graph-navigation`.
