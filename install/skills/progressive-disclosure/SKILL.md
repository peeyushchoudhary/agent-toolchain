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
| `persona-decision-missing` (warn) | No project specialists and no explicit reason the base pool is sufficient |
| `persona-route-missing` (error) | Project persona sources exist but their maintained guide is not directly routed |
| `lessons-entries` (note) | A lessons file has accreted past the point of being readable in one sitting |

Exit 1 on any error. Never on a warning or a note: severity is a property of the finding, decided
in the validator, not a strictness level chosen at the call site — so there is no `--strict`.
`--json` for machine use. Wire it into the repo's check gate so the route is verified like any
other invariant.

(`validate_card.py` in the execution-methodology skill *does* keep a `--strict`, deliberately: a
task card is a proposal being gated before work starts, where a caller may reasonably demand a
clean bill, while this validator reports on a repository that already exists. The toolchain is
inconsistent here on purpose, not by accident.)

## The README is a separate deliverable

`AGENTS.md` routes an agent; `README.md` answers a human deciding whether the project is real.
`--readme` enforces seven sections — overview, current state, product requirements, architecture
(with a ```mermaid diagram, never an exported raster), components, run locally, working in this
repository — plus resolvable links, a
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

Exit `0` clean, `1` a finding, `2` **the check could not run** — `gh` missing, logged out or rate
limited, so visibility was never determined. Treat `2` as unanswered, not as clean: the whole point
of the tool is the visibility question, and a report that could not read the remote has not answered
it. (`--hook` always exits 0; session start must never fail on this.)

## Before you trust a gate: preflight

```bash
~/.claude/hooks/preflight.sh <repo>
```

Mechanical checks for the environment-failure class — the machine facts that are identically true in
every repository on day one and are otherwise re-learned one failed gate run at a time: does every
tool the repo's own check scripts name resolve to a real binary, is `JAVA_HOME` sane when there is
actually a Gradle build, was `SIGHUP` inherited-ignored from some ancestor `nohup`.

Reports only: it never writes, scaffolds or fixes anything inside the target, and it runs safely
against repositories that are not ours. Findings are `PREFLIGHT:` lines on stdout; `NOTE:` lines are
coverage, never findings. Exit `0` means the checks ran (whether or not they found anything) and `2`
means a check itself could not be completed. Non-zero never means "found a problem": a preflight
that fails a session because it found something true about the machine gets switched off within a
day.

**Run it two ways, and the second is the one people skip.**

*Automatically, at session start.* It is wired in `~/.claude/settings.json` beside
`disclosure-check.sh`, against whatever directory the session opened in, so the machine facts are in
front of you before you start trusting them. Same pattern as its sibling —
`bash ~/.claude/hooks/preflight.sh "${CLAUDE_PROJECT_DIR:-$PWD}" 2>/dev/null || true` — where the
wrapper is what makes the hook's exit code non-fatal to session start. Worst measured run 0.111s.

*By hand, immediately before a long gate run.* **This is the invocation that matters, and session
start does not cover it.** The environment-failure class bites hardest at the moment you commit an
hour to a gate: a session can be hours old, can have opened in a different repository, and can have
had `JAVA_HOME`, `PATH` or the `SIGHUP` disposition change underneath it since. Run it against the
repository you are about to gate, read the `PREFLIGHT:` lines, and only then start the gate:

```bash
~/.claude/hooks/preflight.sh <repo>     # then read the findings, THEN start the gate
```

Also run it when opening an unfamiliar repository, or when a gate fails in a way that smells like
the machine rather than the code.

Preflight itself is fast; the **gate** you run after it is the slow thing — ~60 minutes, past the
tool-call cap for an agent turn. Launch *the gate* detached (`setsid`, or
`Popen(..., start_new_session=True)`) and poll with `ps -p <pid>`, rather than waiting on it inline.
Not `nohup`: that sets `SIGHUP` to ignored for every descendant, which is the third thing preflight
checks for.

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
migrate_to_standard.py <repo> --product    # plan the docs/product/specs/ migration; writes nothing
```

The migrator refuses to apply to a repository with uncommitted changes, never commits, and rewrites
every markdown link a move invalidated. Read `references/standard.md` before running it.

`--product` is a separate mode for one specific silence. `spec_check.py` binds feature specs by the
single path glob `docs/product/specs/F-*.md`, so a repository that writes
`docs/product/specs/<slug>/spec.md` has every spec walked, matched by no rule, and reported as a
clean exit 0. The mode proposes a RENAME PLUS A FRONT MATTER HEADER and nothing else: it derives
`id`, `title`, `prd`, `status` and `updated` from what each document already says, refuses in
writing where it cannot derive one, and prints the body word count before and after together with a
repository-wide broken-link count so "no prose moved" is checkable rather than asserted. The area
identifier a repository actually cites — `FED-C1` — is kept in the title and in the filename; the
`F-<n>` value exists only because `spec_check.ID_RE` accepts nothing else.

Break-test: `python3 scripts/migrate_to_standard_selftest.py` (exit 0 = every case passes).

## Setting this up in a project

Moved to the `project-onboarding` skill, which owns the end-to-end procedure: migrate, write the
route, wire the gate, install hooks, add specialists. It spans GitHub and personas as well as the
route, so it does not belong here.

This skill owns the *standard* — the layers, the taxonomy, the budgets, and the validator.
`project-onboarding` owns *applying* it to a repository.

Two rules that live here because they are properties of the route, not of onboarding:

- **Git hooks are never shared through git.** `install_hooks.py` runs once per *clone*, not once per
  project. Session start flags a clone that is missing them.
- **Persona need is an explicit project decision.** A standard repository either keeps sources in
  `docs/agents/personas/` and directly routes `docs/agents/personas.md`, or records
  `<!-- agent-personas: {"mode":"base-only","reason":"..."} -->` in
  `docs/agents/README.md`. Missing both is warned; tooling never invents the reason.
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
