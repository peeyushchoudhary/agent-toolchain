---
name: project-onboarding
description: Use when a project is not yet set up for agent work — no docs/agents/README.md, no git hooks installed, no GitHub remote, or the session-start hook reported it as uninitialised. Also use when opening a repository for the first time and you are unsure whether it has been brought under the shared standard.
disable-model-invocation: true
---

# Bringing a project under the standard

Everything machine-global — personas, session-start reporting, both harnesses' directives — is
already installed and applies the moment any directory is opened; ask `check_toolchain.py` what is
there rather than trusting a list here. This skill covers only what is **per project**, and in what
order.

**Propose before writing.** Show the plan and get agreement first. Never create a GitHub repository,
change visibility, or push without being asked — those are the human's call every time.

## What is genuinely per project

| | Why it cannot be global |
|---|---|
| `AGENTS.md`, the route, area guides | Describes *this* codebase |
| `README.md` sections | Describes *this* product |
| Git hooks | Git never clones hooks — once per clone, not once per project |
| A private GitHub remote | One repo per project |
| Persona overlays and specialists | Derived from *this* project's guardrails |

## The six steps

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

### 5 — Record the project-persona decision

This decision is mandatory; specialists are not. Read the current guardrails, architecture, and
product criteria, then stop and propose one of these outcomes:

1. **Project specialists are justified.** Use `agent-persona-factory`; it proposes 2–4 specialists
   citing the invariant justifying each and writes only to `docs/agents/personas/`. Add
   `docs/agents/personas.md`, route it directly from `docs/agents/README.md`, then run:

```bash
python3 "$HOME/.claude/skills/agent-personas/scripts/sync_personas.py" --repo .
```

   Commit the sources, guide, route, and generated `.claude/agents/` + `.codex/agents/`.

2. **The shared base pool is sufficient.** Record one exact marker in
   `docs/agents/README.md`, with a non-empty project-specific reason:

```html
<!-- agent-personas: {"mode":"base-only","reason":"domain-neutral library; base reviewers cover its risks"} -->
```

Never infer or generate a `base-only` reason. Missing both outcomes is an onboarding warning, not a
healthy default.

### 6 — Record the execution-methodology decision

Mandatory like step 5, and the easiest to skip: **adoption is deliberate and per repository —
nothing adopts a repository on its own.** Skip it and the project runs no shared methodology, and
only a conformance run will ever say so.

```bash
sync_methodology.py --list                       # source version and rendered date
sync_methodology.py --repo . --adoption-check    # this repo's state; ALWAYS exits 0 — read the text
```

Read that state, never its exit code, then propose one of two outcomes:

1. **Adopt.** `sync_methodology.py --repo .` renders the in-repo copy both harnesses read; route to
   it. Bindings to *this* repo's real commands go in the hand-authored overlay beside it, never in
   the rendered copy. Gate staleness with `--repo . --check`, which does exit non-zero.
2. **Defer.** Record the `execution-methodology` marker with a real reason and date, exactly as
   `execution-methodology` specifies.

Never invent the reason; never leave both unrecorded.

**Adoption is not finished when the file renders — it also configures this repository's
validators.** The same state report carries the persona half: which personas this repository has in
`docs/agents/personas/`, which of them declare `covers:`, and **which horizontal concerns in its own
specs are owned by nobody**. That last list is the one to act on; it names the invariants this
product writes down and binds to no reader.

Measured across four repositories: a project's own domain validators are cited 100 times at review
time, 5 times on a spec, and zero times on a PRD or a milestone. They arrive after the product is
defined, which is the expensive end. For each unowned concern, decide which validator holds it, then
add ONE line inside that persona's front matter — in the source under `docs/agents/personas/`, never
in the generated `.claude/agents/` copy:

```yaml
covers: [tenancy, money handling]
```

`covers:` is read from the source by `spec_check.py`; the persona renderers do not emit it, so it
changes no harness file and needs no re-render. Once a persona covers a concern, rule F demands that
persona in `reviewed_by:` on every spec, PRD and milestone that says it moves that concern. Until
then rule F reports `RULE F CHECKED NOTHING` — the state all four repositories are in today.

```bash
spec_check.py --root . --personas   # the pool, what each covers, and the concerns it could
```

**Nothing writes that line for you.** Deciding which validator holds which invariant is a judgement;
a binding a script guessed is a binding nobody holds. A repository with no `docs/agents/personas/`
has not adopted overlays (step 5) — a state, not a fault: the base pool applies unchanged and there
is nothing here to bind.

## Verify

Onboarding is done when the repository conforms, and one tool already owns that answer:

```bash
python3 "$HOME/.claude/skills/project-conformance/scripts/check_conformance.py" .
make check
```

Exit 0 is the only pass; exit 2 means a check did not run, so read which one — re-running changes
nothing. **If that script is absent, say so and stop: conformance was NOT CHECKED.** It is optional
and this installer does not ship it. Never skip the line silently, and never call it green.

It replaced six hand-rolled commands that ran five of those checks with weaker flags — no
`--vs HEAD`, no `--json` — and judged them by exit code, which three of the checkers set to 0 while
carrying the finding on stdout or stderr; that is how it reported green over unprotected judges.

**Know what `--fix` reaches before you type it.** It is not confined to the repository you name: the
persona sync writes into *and prunes* both harnesses' machine-global agent directories, every run.
Read the repair plan first — it names every path.

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

## This skill is user-invoked, in both harnesses

This skill creates repositories, installs git hooks, and writes a repository's route. Its own first
rule is **"Propose before writing"** — so it must not start because a model decided a repository
looked uninitialised. A model may choose *how* to work; it may not authorise its own **promotion**,
and onboarding is a promotion: it moves a repository from outside the standard to inside it.

Two switches, one per harness, and **they are not the same mechanism**:

| harness | mechanism | effect |
| --- | --- | --- |
| Claude Code | `disable-model-invocation: true`, in the front matter above | the model cannot load this skill on its own; `/project-onboarding` still works |
| Codex | `agents/openai.yaml` → `policy.allow_implicit_invocation: false` | Codex will not invoke it implicitly; `$project-onboarding` still works |

**The asymmetry is stated, not hidden.** `disable-model-invocation` is a Claude Code extension,
absent from the Agent Skills spec; OpenAI's Claude-to-Codex migration reference lists it as *"No
direct equivalent — Unsupported"* and calls `policy.allow_implicit_invocation` *"similar intent, not
equivalent semantics"*. The front-matter key alone would be enforced in one harness and inert in the
other, so both are set. If a harness ignores its key the gate is inert *there* and no front matter
can say so — there is deliberately no checker, because "the field is present" is green the moment the
field exists and learns nothing.

Nothing is lost when a repository genuinely needs this: the SessionStart reporter still says the
project is uninitialised, and a human runs the skill by name. The full detail of both mechanisms,
and why the packaged-skill front-matter allowlist does not apply to this repository, is in
`execution-methodology/SKILL.md`, "This skill is user-invoked, in both harnesses".

## Related

`progressive-disclosure` — the route standard, the taxonomy, and the validator.
`agent-personas` — the roster and its routing. `agent-persona-factory` — deriving specialists.
`execution-methodology` — the methodology step 6 adopts, its overlay, and its marker.
`project-conformance` — the read-only verifier this skill's Verify step calls. This skill runs
**once**, and writes; that one answers **is it still conforming** any time after, and does not.
