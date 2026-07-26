# Handoff — adopt this in an existing project

For a repository that already has code and history. Roughly 30–60 minutes, most of it reading the
generated diff rather than typing.

**Read [../repository-standard.md](repository-standard.md) before running the migrator.** It
moves directories.

## Before you start

```bash
cd <repo>
git status --short          # must be clean; the migrator refuses a dirty tree, and it is right to
git log --oneline -3
```

Concurrent changes belong to their author. Never discard or rewrite unrelated work.

If the repo is not on GitHub yet, decide that first — see
[setup-existing-project.md § step 6](#6-github) below. Do not create a repo without being asked.

---

## 1. See what the route looks like today

```bash
python3 ~/.claude/skills/progressive-disclosure/scripts/validate_disclosure.py .
```

On a repo with no route this reports `no-entry` and lists every unscoped source directory. **That
list is your work list.**

## 2. Plan the taxonomy migration

```bash
python3 ~/.claude/skills/progressive-disclosure/scripts/migrate_to_standard.py .
```

Dry run — writes nothing. Read every line of the plan.

**Before accepting any move, check whether the path is read by code:**

```bash
rg -n "docs/<the-path>" --glob '!docs/**' .
```

In the reference project, six of seven proposed content moves were referenced from
a build file and two test classes. Moving them would have broken the build. The migrator does
not know about code references — that check is yours.

## 3. Apply

```bash
python3 ~/.claude/skills/progressive-disclosure/scripts/migrate_to_standard.py . --apply
```

Backs up first, uses `git mv` so history follows, rewrites every markdown link a move invalidated.
It never commits — review the staged diff yourself.

Confirm the backup path in the output. For a repo without git, that backup is the only undo.

## 4. Fill in the scaffolding

The migrator writes skeletons containing `TODO`. The validator treats those as **errors** — a
bootstrapped-and-abandoned route is worse than none, because it looks answered.

Write, in this order:

1. **`AGENTS.md`** (≤400 words) — from what is actually enforced: real test gates, real migration
   rules, real invariants. Not aspirations.
2. **`docs/agents/README.md`** (≤600 words) — one row per area: task → one guide → **one real
   command**. Verify each command exists in the Makefile or `package.json`.
3. **Area guides** for each real split in the repo.
4. **`<dir>/AGENTS.md` + `CLAUDE.md`** (≤40 words) for every directory the validator named.
   `CLAUDE.md` is exactly `@AGENTS.md`, nothing else.
5. **`README.md`** — the seven sections in [../progressive-disclosure.md](progressive-disclosure.md).

## 5. Wire the gate

Add a docs target to whatever the repo's check facade is:

```make
check-docs:
	@f=$$HOME/.claude/skills/progressive-disclosure/scripts/validate_disclosure.py; \
	if [ -f "$$f" ]; then python3 "$$f" . --readme; \
	else echo "skip: progressive-disclosure validator not installed at $$f"; fi
check: <existing targets> check-docs
```

The skip branch matters: it degrades cleanly on a workstation without the tool.

## 6. GitHub

```bash
python3 ~/.claude/skills/progressive-disclosure/scripts/check_github.py .
```

Fix what it reports. If there is no remote and you have been asked to create one:

```bash
gh repo create --private --source=. --push     # --private is not optional
python3 ~/.claude/skills/progressive-disclosure/scripts/check_github.py . --apply-settings
```

`--apply-settings` disables Wiki, Projects, and Issues. It never touches visibility.

## 7. Install the hooks

```bash
python3 ~/.claude/skills/progressive-disclosure/scripts/install_hooks.py .
```

Installs `pre-commit`, `pre-push`, and the graph `post-commit`; syncs skills to Codex; syncs
personas. **Once per clone** — git never clones hooks.

## 8. Personas

Base personas are already available from user level; nothing per-project is needed unless you want
specialisation. When you do:

```
# invoke the agent-persona-factory skill
```

It reads guardrails → architecture → PRD, proposes 2–4 specialists with the invariant justifying
each, and writes only to `docs/agents/personas/`. Then:

```bash
python3 ~/.claude/skills/agent-personas/scripts/sync_personas.py --repo .
```

Commit the overlays **and** the generated `.claude/agents/` + `.codex/agents/`.

---

## Validation — do all of these

```bash
# 1. Route, README, taxonomy all clean
python3 ~/.claude/skills/progressive-disclosure/scripts/validate_disclosure.py . --readme --standard

# 2. Hooks armed
python3 ~/.claude/skills/progressive-disclosure/scripts/install_hooks.py . --check

# 3. GitHub clean
python3 ~/.claude/skills/progressive-disclosure/scripts/check_github.py . --refresh

# 4. Personas in sync (if the repo has overlays)
python3 ~/.claude/skills/agent-personas/scripts/sync_personas.py --repo . --check

# 5. The repo's own gate
make check
```

### Prove the guards actually fire

Structural checks passing is not proof the guards work. Test each, then undo:

```bash
# pre-commit catches a broken route
echo "[dead](docs/agents/nope.md)" >> docs/agents/README.md
git add -A && git commit -m test        # must FAIL
git restore --staged . && git checkout docs/agents/README.md

# pre-push blocks a direct main push
git commit --allow-empty -m test && git push origin main   # must FAIL
git reset --hard HEAD~1

# persona drift is caught
echo "x" >> .claude/agents/<any>.md
make check-docs                          # must FAIL with persona-drift
python3 ~/.claude/skills/agent-personas/scripts/sync_personas.py --repo .
```

### Confirm a fresh session sees it

Start a new session in the repo. The session-start hook should be **silent** if everything is
healthy. If it reports a broken route, a missing hook, a stale graph, or a GitHub problem, that is
real — fix it rather than ignoring it.

---

## Commit and land

```bash
git switch -c milestone/<name>
git add -A && git commit          # conventional commit; state the checks you ran and their output
git push -u origin HEAD
gh pr create --fill
gh pr merge --merge               # merge commit, never squash
git tag -a milestone/<name> -m "…" && git push origin milestone/<name>
```

## If something is wrong

- **Migrator refuses (dirty tree)** — commit or stash. Do not use `--force`; a directory move
  landing on in-flight work is genuinely expensive to unpick.
- **Validator reports paths that do exist** — they may be cited imprecisely. It stays quiet when a
  basename exists anywhere; if it still fires, the citation is genuinely wrong.
- **`make check-docs` says "skip"** — the tool is not installed at the expected path.
- **Personas not dispatchable** — run the sync; definitions load without a session restart.
- **A guide misled you** — append a dated two-line entry to `docs/agents/lessons.md`. That is the
  only channel every harness can both read and write.
