---
name: project-onboarding
description: Use when a project is not yet set up for agent work — no docs/agents/README.md, no git hooks installed, no GitHub remote, or the session-start hook reported it as uninitialised. Also use when opening a repository for the first time and you are unsure whether it has been brought under the shared standard.
---

# Bringing a project under the standard

Everything machine-global is already installed and applies the moment any directory is opened. This
skill covers only what has to be done **per project**, and in what order.

**Propose before writing.** Show the plan and get agreement first. Never create a GitHub repository,
change visibility, or push without being asked — those are the human's call every time.

## What the project already gets for free

No action needed. If someone asks for these, they already have them:

- All personas, in both Claude Code and Codex (see `agent-personas`)
- Session-start reporting: GitHub state, global toolchain drift, route problems, stale graph
- The graphify query advisor and lessons injection
- The operating model, GitHub rules, and persona directive in both harnesses

## What is genuinely per project

| | Why it cannot be global |
|---|---|
| `AGENTS.md`, the route, area guides | Describes *this* codebase |
| `README.md` sections | Describes *this* product |
| Git hooks | Git never clones hooks — once per clone, not once per project |
| A private GitHub remote | One repo per project |
| Persona overlays and specialists | Derived from *this* project's guardrails |

## The five steps

### 1 — Look before touching

```bash
git status --short
check_github.py .
validate_disclosure.py .
```

The tree must be clean before step 2; the migrator refuses a dirty tree and is right to. The
validator's `unscoped-dir` list is the work list for step 3.

### 2 — Migrate the taxonomy

```bash
migrate_to_standard.py <repo>            # plan only, writes nothing
migrate_to_standard.py <repo> --apply    # backs up, then executes
```

**Check whether code reads a path before accepting its move:**
`rg -n "docs/<the-path>" --glob '!docs/**' .` — build files and tests routinely reference doc paths,
and the migrator cannot know. Read the whole plan before applying.

See `progressive-disclosure` for the taxonomy itself and its retired spellings.

### 3 — Write the route — the actual work

The migrator leaves `TODO` skeletons, and the validator treats them as errors: a
bootstrapped-and-abandoned route is worse than none because it looks answered.

1. Run the validator first — `no-entry` plus the unscoped directories is your work list.
2. **`AGENTS.md`** (≤400 words) from what is *actually enforced* — real test gates, real migration
   rules, real invariants. Not aspirations.
3. **`docs/agents/README.md`** (≤600 words) — one row per real area: task → one guide → **one real
   command**. Verify each command exists in the Makefile or `package.json` before writing it.
4. **Area guides** for each real split in the repo.
5. **`<dir>/AGENTS.md` + `CLAUDE.md`** (≤40 words) for every directory the validator named.
   `CLAUDE.md` is exactly `@AGENTS.md`, nothing else.
6. **`README.md`** — the human front page; see `progressive-disclosure` for its required sections.

Draft from evidence. An index documenting an aspiration sends agents to commands that do not exist.

Then wire the gate into the project's check facade, with a skip branch so it degrades cleanly on a
workstation without the tooling:

```make
check-docs:
	@f=$$HOME/.claude/skills/progressive-disclosure/scripts/validate_disclosure.py; \
	if [ -f "$$f" ]; then python3 "$$f" . --readme; \
	else echo "skip: validator not installed at $$f"; fi
check: <existing targets> check-docs
```

### 4 — GitHub and hooks

```bash
gh repo create --private --source=. --push   # ONLY if asked. --private is not optional
check_github.py . --apply-settings           # disables Wiki/Projects/Issues; never touches visibility
install_hooks.py .                           # pre-commit, pre-push, post-commit
```

`install_hooks.py` is idempotent, preserves any hook the project already had, and takes
`--check` / `--uninstall` / `--standard`. It also refreshes the Codex skills mirror and syncs
personas, so running it here repairs global drift as a side effect.

Run it **once per clone** — git hooks live in `.git/hooks` and are never shared through git.

### 5 — Specialists — optional

Only once the project has guardrails worth encoding. Use `agent-persona-factory`; it proposes 2–4
specialists citing the invariant justifying each, writes only to `docs/agents/personas/`, then:

```bash
sync_personas.py --repo .
```

Commit the overlays **and** the generated `.claude/agents/` + `.codex/agents/`.

## Verify

```bash
validate_disclosure.py . --readme --standard
install_hooks.py . --check
check_github.py . --refresh
check_toolchain.py
make check
```

Then start a fresh session in the project. **A healthy project produces a silent session hook** —
anything it reports is real.

Green checks are not proof the guards work. Prove one fires: break a link in
`docs/agents/README.md`, confirm the commit fails, revert.

## What updates automatically afterwards, and what does not

| Trigger | What happens | Automatic? |
|---|---|---|
| Any commit | pre-commit validates the route; a broken link or missing command fails it | yes, per repo |
| Any push | pre-push blocks secrets, files >10 MB, direct pushes to main | yes, per repo |
| Commit touching **code** | post-commit re-extracts changed files into the graph | yes, per repo |
| Commit touching **docs** | nothing rebuilds; session start flags the staleness | flagged, not fixed |
| Session start | route, hooks, stale graph, lessons, GitHub state, global toolchain drift | yes, every project |
| A prose `graphify query` | the advisor injects the symbol-first ladder | yes, every project |
| `install_hooks.py` | mirrors skills to Codex and syncs personas | on each run |

Documentation changes are the hole: after editing guides, refresh the graph yourself with
`graphify extract . --mode deep --backend <backend>`.

Session-start validation matters most where it is the *only* option — a project with no git can
never have a pre-commit hook, so that check is its sole automated integrity gate.

Never run `graphify claude install`: it appends to `CLAUDE.md`, breaking the one-line rule and
making that guidance invisible to every non-Claude agent.

## Related

`progressive-disclosure` — the route standard, the taxonomy, and the validator.
`agent-personas` — the roster and its routing. `agent-persona-factory` — deriving specialists.
