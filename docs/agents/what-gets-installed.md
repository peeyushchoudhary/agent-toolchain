# What gets installed

Every file the installer places outside a project, what each does, and how they interact. The
vendored sources live in `../install/`.

The installed files are the authority; when this document disagrees, they win.

## Re-vendoring: what is left behind on purpose

**The `agent-personas` test directory is not vendored. Do not restore it.** Its preflight resolves
the human record of the judging roster as a sibling of the skill tree, which under `install/` does
not exist and should not. Measured, and weighed against the alternative, in
[D24](../decisions/decisions.md).

`check_toolchain.py --vendored <repo>` is **clean immediately after `./install.sh`**, with five
paths excluded. The condition matters as much as the number: the count sat at 3 while all three
findings changed underneath it, and two were a drifted machine, not an invariant. Any finding is
real. [D25](../decisions/decisions.md) carries the history, [D26](../decisions/decisions.md) the
exclusions.

**`project-conformance` ships tests and they ARE vendored**, and it is **not** in
`MIRRORED_SKILLS`. Its suite is `Ran 56 tests ... OK` from the vendored position and red under
`HOME=$(mktemp -d)`, by construction rather than by defect. Both, with their numbers, are
[D21](../decisions/decisions.md) and [D22](../decisions/decisions.md).

## Claude Code — `~/.claude/`

### Skills

| Path | Purpose |
|---|---|
| `skills/progressive-disclosure/` | The route standard, validator, migrator, hook installer, GitHub checker, push guard |
| `skills/agent-personas/` | The 13-persona pool and its generator |
| `skills/agent-persona-factory/` | Derives project specialists from PRD + architecture + guardrails |
| `skills/execution-methodology/` | The pipeline from product spec to sealed milestone, and its renderer |
| `skills/project-onboarding/` | The end-to-end procedure for bringing a project under the standard. Named by the session hook when a project is uninitialised |
| `skills/graph-navigation/` | The symbol-first ladder for querying a graphify graph |
| `skills/project-conformance/` | Whether an onboarded repository still meets the standard. Reports; repairs only what it named, under `--fix`. Run by hand, never by a hook |
| `skills/project-migration/` | Moving an onboarded repository's product documents onto the bound schema. Two read-only steps, then `--apply`. Run by hand, never by a hook |
| `skills/graphify/` | Vendor skill, not published by this repository. Hidden from model-initiated listing (see below) |

`install.sh` installs the eight published ones, deriving that set from `install/skills/.gitignore`
rather than carrying its own list. `graphify` is listed because the installed layer has it.

### Scripts

| Script | Does |
|---|---|
| `progressive-disclosure/scripts/validate_disclosure.py` | Route, README, taxonomy, and persona-drift checks |
| `progressive-disclosure/scripts/migrate_to_standard.py` | Plans and applies the taxonomy migration |
| `progressive-disclosure/scripts/install_hooks.py` | Installs per-repo git hooks; syncs skills to Codex; syncs personas |
| `progressive-disclosure/scripts/check_github.py` | Repo stored / private / pushed / quiet; `--sweep` for the fleet |
| `progressive-disclosure/scripts/push_guard.py` | pre-push: secrets, oversized files, direct main pushes |
| `progressive-disclosure/scripts/check_toolchain.py` | Machine-global drift: persona pool vs generated agents, mirrored instruction blocks, Codex skills copy |
| `agent-personas/scripts/sync_personas.py` | Renders the pool into both harnesses; prunes orphans |
| `execution-methodology/scripts/sync_methodology.py` | Renders the methodology into a repository as `docs/agents/execution/methodology.md` |
| `execution-methodology/scripts/check_review_budget.py` | Bans workspace debris classes; the round count is advisory |
| `project-conformance/scripts/check_conformance.py` | Nine checks against one onboarded repository, each owned by the checker that already answers it. Exit 0/1/2, where 2 is "could not be checked" |

### Session hooks — wired in `~/.claude/settings.json`

| Event | Script | Behaviour |
|---|---|---|
| `SessionStart` | `hooks/disclosure-check.sh` | Reports GitHub state, **global toolchain drift**, a broken route, a missing pre-commit hook, a stale graph, and the presence of `lessons.md`. **Reports, never writes** |
| `SessionStart` | `hooks/graphify-session-lessons.sh` | Runs `graphify reflect --if-stale`, injects `LESSONS.md` (4,000 char cap) |
| `PreToolUse` (Bash) | `hooks/graphify-query-advisor.py` | Advisory: injects the symbol-first ladder when a prose `graphify query` is about to run |
| `SessionStart` | `hooks/preflight.sh` | Machine-fact checks for the environment-failure class, run against the session's directory; also standalone before a long gate. **Reports, never writes** |

`skillOverrides: {"graphify": "user-invocable-only"}` — the vendor skill is hidden from
model-initiated invocation so `graph-navigation` owns queries. `/graphify` still works for the user.

Session hooks report and never create files: they fire in every directory a session starts in,
including repositories that are not yours.

### Generated agents

`~/.claude/agents/` — 14 `.md` files, one per persona. Generated by `sync_personas.py`. Do not edit.

### Instructions

`~/.claude/CLAUDE.md` — operating model, GitHub rules, persona directive, cross-project delegation
posture. The GitHub and persona sections are byte-identical to their Codex counterparts.

## Codex — `~/.codex/`

| Path | Purpose |
|---|---|
| `AGENTS.md` | Mirror of `~/.claude/CLAUDE.md`'s shared sections |
| `agents/` | 15 `.toml` files — 14 generated personas plus the hand-written `grok_worker.toml` |
| `skills/` | The seven skills `MIRRORED_SKILLS` names — the eighth, `project-conformance`, is published but not watched here ([D22](../decisions/decisions.md)). `project-migration` IS watched: it was added to that list in its own publication commit, because publishing is five coordinated edits and this is the fifth. Refreshed by `install_hooks.py` or `install.sh`. `graphify` is there too, put by the vendor |
| `config.toml` | `[agents]` block: `enabled = true`, default subagent `gpt-5.6-terra` at `medium`, max 6 concurrent threads |

The `[agents]` block leaves parent session settings untouched; it sets only what spawned agents
default to when a persona file specifies neither. `config.toml` is backed up before editing.
`grok_worker.toml` is hand-written — `sync_personas.py` leaves it alone, lacking the banner.

## Per-repository (not global, but installed by these tools)

Git hooks are never cloned, so each clone needs `install_hooks.py` run once:

| Hook | Behaviour |
|---|---|
| `pre-commit` | Validates the route; fails the commit when broken. Bypass: `git commit --no-verify` |
| `pre-push` | Blocks secrets, files >10 MB, direct pushes to main |
| `post-commit` | Re-extracts changed **code** into the graph (installed by `graphify hook install`) |

All three skip silently when their tool is absent, so they install safely anywhere.

## Verifying the installation

```bash
cd install && ./verify.sh
```

Piecemeal:

```bash
python3 ~/.claude/skills/agent-personas/scripts/sync_personas.py --list
python3 ~/.claude/skills/progressive-disclosure/scripts/check_github.py --sweep <projects-dir>
python3 ~/.claude/skills/progressive-disclosure/scripts/install_hooks.py <repo> --check
```

## Keeping it in sync

Three pieces of machine-global state have no per-repo owner; `check_toolchain.py` watches them and
the session hook runs in **every** project:

| State | Drifts when | Fix |
|---|---|---|
| Persona pool → `~/.claude/agents` + `~/.codex/agents` | A persona is edited without a sync | `sync_personas.py` |
| Mirrored instruction blocks | One harness's global file is edited alone | Edit the other to match |
| `~/.codex/skills/` | A skill is added, or edited without an install run | `install_hooks.py <any-repo>` |

A new skill goes in **one** list to be watched and mirrored: `MIRRORED_SKILLS` in
`check_toolchain.py`, which `sync_codex()` imports rather than restating. The second copy that once
lived there is how `execution-methodology` came to be checked but never copied.

Before this check existed, all three were invisible. Persona drift was caught only in a repository
with overlays — one in thirteen — so an unsynced pool edit ran stale everywhere else, silently.

Two sections are **deliberately not** byte-identical across harnesses and must not be "fixed":
`# Operating model` and the prose of `# Cross-project implementation strategy`. They differ in
person (first for Claude, third for Codex) and point at each harness's own skills directory. Only
blocks carrying rules are required to match.

```bash
python3 ~/.claude/skills/progressive-disclosure/scripts/check_toolchain.py
```
