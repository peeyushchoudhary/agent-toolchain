# Per-project initialisation

The short version of [setup-existing-project.md](full-adoption.md): what to run when you
open one of the twelve remaining projects, and roughly how long it takes.

Everything machine-global is already installed and verified. **The only work left is per project.**

On a workstation with the tooling installed, this same procedure is available to both harnesses as
the **`project-onboarding` skill**, and the session-start hook names it whenever it detects an
uninitialised project. This document is the standalone version: it explains the approach for a
reader who does not have the skill, and stays readable on its own.

## What every project already has, for free

No action needed — these come from user level and apply the moment you open any directory:

- All 11 personas, in both Claude and Codex
- Session-start reporting: GitHub state, global toolchain drift, route problems, stale graph
- The graphify query advisor and lessons injection
- The operating model, GitHub rules, and persona directive in both harnesses

## What is per project

| | Why it cannot be global |
|---|---|
| `AGENTS.md`, the route, area guides | Describes *this* codebase |
| `README.md` seven sections | Describes *this* product |
| Git hooks (pre-commit, pre-push, post-commit) | Git never clones hooks |
| A GitHub remote, private | One repo per project |
| Persona overlays and specialists | Derived from *this* project's guardrails |

## The six steps

Run in order. Steps 1–2 are mechanical; step 3 is the real work; step 6 is the one that
gets forgotten.

### 1 — Look before touching · 2 min

```bash
cd <project>
git status --short
python3 ~/.claude/skills/progressive-disclosure/scripts/check_github.py .
python3 ~/.claude/skills/progressive-disclosure/scripts/validate_disclosure.py .
```

The validator's `unscoped-dir` list is your work list for step 3. The tree must be clean before
step 2 — the migrator refuses a dirty tree, and it is right to.

### 2 — Migrate the taxonomy · 5 min + review

```bash
python3 ~/.claude/skills/progressive-disclosure/scripts/migrate_to_standard.py .          # plan
python3 ~/.claude/skills/progressive-disclosure/scripts/migrate_to_standard.py . --apply  # execute
```

**Before accepting a move, check whether code reads that path:**
`rg -n "docs/<the-path>" --glob '!docs/**' .` — in the reference project, six of seven proposed
content moves were referenced from build files and tests.

### 3 — Write the route · 30–90 min, the actual work

The migrator leaves `TODO` skeletons and the validator treats them as errors. Fill in:

`AGENTS.md` (≤400 words, only what is enforced) → `docs/agents/README.md` (≤600, one real command
per row) → area guides → `<dir>/AGENTS.md` + `CLAUDE.md` (≤40 words each, `CLAUDE.md` is exactly
`@AGENTS.md`) → `README.md` (the seven sections).

Then wire the gate into the project's check facade:

```make
check-docs:
	@f=$$HOME/.claude/skills/progressive-disclosure/scripts/validate_disclosure.py; \
	if [ -f "$$f" ]; then python3 "$$f" . --readme; \
	else echo "skip: progressive-disclosure validator not installed at $$f"; fi
check: <existing> check-docs
```

### 4 — GitHub and hooks · 3 min

```bash
gh repo create --private --source=. --push        # only if asked, and only --private
python3 ~/.claude/skills/progressive-disclosure/scripts/check_github.py . --apply-settings
python3 ~/.claude/skills/progressive-disclosure/scripts/install_hooks.py .
```

`install_hooks.py` also refreshes the Codex skills mirror and syncs personas, so running it here
fixes global drift too.

### 5 — Specialists · 15 min, optional

Only once the project has guardrails worth encoding. Invoke the `agent-persona-factory` skill; it
proposes 2–4 specialists citing the invariant justifying each, writes to `docs/agents/personas/`,
then:

```bash
python3 ~/.claude/skills/agent-personas/scripts/sync_personas.py --repo .
```

Commit overlays **and** the generated `.claude/agents/` + `.codex/agents/`.

### 6 — Adopt or defer the execution methodology · 10 min, mandatory

The easiest step to skip and the one nothing else catches: **adoption is deliberate and per
repository — nothing adopts a repository on its own.** Skip it and the project runs no shared
methodology, and only a conformance run will ever say so.

```bash
python3 ~/.claude/skills/execution-methodology/scripts/sync_methodology.py --repo . --adoption-check
```

That command **always exits 0** — read the text, not the status. Then record one of two outcomes:

- **Adopt.** `sync_methodology.py --repo .` renders the copy both harnesses read, and the route
  points at it. Bindings to this repository's real commands go in the hand-authored overlay beside
  the rendered file, never inside it. `--repo . --check` gates staleness and does exit non-zero.
- **Defer.** Record the marker with a real reason and a date.

Leaving both unrecorded is the failure mode. It looks identical to a project nobody has reached yet.

**The same report also configures this repository's validators**, because adoption is not finished
when the file renders. It names the personas in `docs/agents/personas/`, which of them declare
`covers:`, and **which horizontal concerns in this repository's own specs are owned by nobody** —
the invariants the product writes down and binds to no reader.

Measured across four repositories: a project's own domain validators are cited 100 times at review
time, 5 times on a spec, and zero times on a PRD or a milestone. They arrive after the product is
defined. For each unowned concern, decide which validator holds it and add ONE line to that
persona's front matter — in the source under `docs/agents/personas/`, never in the generated
`.claude/agents/` copy:

```yaml
covers: [tenancy, money handling]
```

`covers:` is read from the source by `spec_check.py`; the persona renderers do not emit it, so it
changes no harness file and needs no re-render. Once a persona covers a concern, spec_check's rule F
demands that persona in `reviewed_by:` on every spec, PRD and milestone that says it moves that
concern; until then rule F reports `RULE F CHECKED NOTHING`, which is the state all four
repositories are in today.

```bash
python3 ~/.claude/skills/execution-methodology/scripts/spec_check.py --root . --personas
```

Nothing writes that line for you: a binding a script guessed is a binding nobody holds. A repository
with no `docs/agents/personas/` has not adopted overlays (step 5) — a state, not a fault. The base
pool applies unchanged and there is nothing to bind.

## Verify

```bash
python3 "$HOME/.claude/skills/project-conformance/scripts/check_conformance.py" .
make check
```

One call, not a hand-rolled list. The list that used to sit here ran five of the same checks with
weaker flags and judged them by **exit code** — which three of those checkers set to 0 while
carrying the finding on stdout. It printed green over unprotected judges.

Exit 0 is the only pass; exit 2 means a check did not run, so read which one. **That skill is
optional and this installer does not ship it — if it is absent, say conformance was NOT CHECKED and
stop.** Never substitute the old commands, never call the result green.

**Know what `--fix` reaches before you type it.** It is not confined to the repository you name: the
persona sync writes into and prunes both harnesses' machine-global agent directories on every run.

Then start a fresh session in the project. **A healthy project produces a silent session hook.**
Anything it reports is real.

Do not stop at green checks — prove one guard actually fires. Break a link in
`docs/agents/README.md` and confirm the commit fails, then revert.

## Tracking a fleet

Keep a table of where each project stands, so the next session does not re-derive it. Refresh the
raw state with `check_github.py --sweep <projects-dir>`. An example shape:

| Project | Git | Remote | Route | Remaining |
|---|---|---|---|---|
| reference-app | yes | private | full | done — the worked example |
| service-a | yes | private | partial | steps 3–6 |
| service-b | yes | none | none | all six; has unpushed commits — push first |
| scratch-tool | no | none | none | `git init`, then all six |
| notes-and-data | no | none | none | not a software project — judge whether any of this applies |

**Do the unpushed ones first.** A missing route is an inconvenience; a few hundred commits existing
only on one laptop is a risk.

Not every directory needs this. A folder of documents with one utility script is not a project, and
data you would not want on a remote should not get a remote just to satisfy a rule.
