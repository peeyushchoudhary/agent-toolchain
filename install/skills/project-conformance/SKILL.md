---
name: project-conformance
description: Use when a project is already under the standard and you want to know whether it still is — before a milestone, after a long gap, or when a session hook reported something and you want the whole picture. Also use to repair the drift that is safe to repair mechanically. Not for setting a project up; that is project-onboarding.
---

# Does this project still conform?

`project-onboarding` brings a repository under the standard **once**. This asks whether it still
does, and repairs the part of the answer that is mechanical.

**Report before repair.** The default writes nothing and ends with a plan naming every file `--fix`
would touch. Run it, read the plan, then decide. You run this by hand, in repositories holding
health and financial data — a tool that surprises you there is worse than no tool.

**No agent runs this against a project repository.** Those repositories are no-write for every
agent, and nothing here is wired to a hook or a session-start path.

```bash
python3 "$HOME/.claude/skills/project-conformance/scripts/check_conformance.py" .          # report
python3 ".../check_conformance.py" . --json                                                 # machine-readable
python3 ".../check_conformance.py" . --fix                                                  # apply the plan
python3 ".../check_conformance.py" . --only personas                                        # one check
```

## Three states, and the third is the point

| exit | verdict | means |
|---|---|---|
| 0 | CONFORMS | every check ran and every check was satisfied |
| 1 | DOES NOT CONFORM | every check ran; at least one was not satisfied |
| 2 | **COULD NOT BE CHECKED** | at least one check did not run |

`2` outranks `1`: the exit code answers *can you trust this report* before it answers *did it find
anything*. A repository with one broken checker and seven clean ones has not been checked. `--json`
carries `not_run` as its own array so nothing is lost — only the single integer is lossy, and it is
lossy in the safe direction.

**Never read the exit code alone from anything here, including this tool.** Three of its eight
callees deliberately exit 0 while carrying the answer elsewhere: `sync_personas --check` names
unprotected project judges on **stderr**, `sync_methodology --adoption-check` **always** exits 0,
and `check_toolchain` exits 0 on `warn`.

## What it checks, and who owns each answer

It orchestrates. It reimplements nothing — every judgement comes from the checker that already owns
it, and an AST test holds that structurally.

| check | owner |
|---|---|
| **personas** | `sync_personas.py --repo R --check`, plus that module's own `absent_restrictions()` applied to the **emitted** artifact |
| **route** | `validate_disclosure.py R --readme --standard --vs HEAD --json` |
| **hooks** | `install_hooks.py R --check` |
| **identifier guard** | `identifier_guard.py`, liveness-probed; only where the repo declares itself public |
| **methodology** | `sync_methodology.py --repo R --adoption-check` |
| **github** | `check_github.py R --json` |
| **plugin surface** | `check_toolchain.py --json`, the `plugins` key — **machine-global** |
| **preflight** | `hooks/preflight.sh R` |

If a conformance question you need has no owner, **stop and add it to the owning checker**, not
here. A conformance tool carrying its own copy of what conforming means becomes the next thing that
drifts.

## The finding this exists for: an unprotected project judge

A project specialist derived by `agent-persona-factory` is **off the judging roster** — the roster
covers base personas only — so `restrict_for_roster` returns its metadata untouched and nothing is
derived or validated for it. Whatever it declares is rendered verbatim.

The common shape, `disallowedTools: Write, Edit, NotebookEdit[, Bash]`, is a deny-list against a
tool roster that grows. It reads as a judge to every human while still granting `Agent`,
`SendMessage` and `Monitor` — dispatch and a shell.

**The remedy is an allow-list in the persona source, then a re-render.** A bare re-render fixes
nothing: it emits exactly the same open artifact and exits 0. `--fix` writes the allow-list into
`docs/agents/personas/<name>.md` — derived from the intersection of what the base judging personas
already declare, never a list typed into this skill — and re-renders. It **narrows**; widening it
is a deliberate edit you make yourself. A judge that already declares an allow-list is reported and
never overwritten, because a human wrote that policy.

## The remedy that does not work, and the one that does

`validate_disclosure.py`'s `persona-drift` ERROR, and `sync_personas.py`'s own `run:` line, both
tell you to run `sync_personas.py --repo .`. Against an **unmanaged** `<repo>/.claude/agents/<x>.md`
— a generated-agents file with no persona source — that command prints `already up to date`, exits
0, **leaves the file**, and the identical error fires again next session.

Run the prescribed fix, see success, see the error again, and you will conclude the *check* is
broken. That is how a true finding gets switched off, in exactly the hostile case this matters.

**What works:** delete the file, or give it a persona source at `docs/agents/personas/<name>.md` and
re-render. This tool states that remedy, drops the validator's `persona-drift` text so the no-op
advice never reaches you, and **will not delete the file for you** — deleting something a human
wrote is your call.

## Scope of a finding is not always scope of the run

Two checks report `[machine-global]` findings: the **plugin surface** (`~/.claude/plugins`,
`~/.codex`) and the machine-global half of **personas** (`~/.claude/agents`, `~/.codex/agents`). The
same finding appears in every repository on this machine and fixing it in one changes nothing
anywhere. The tag is always printed.

## What a `--fix` run can reach — read this before your first one

**`--fix` is not confined to the repository you point it at.** `sync_personas.py --repo R` writes
every base persona into `~/.claude/agents` and `~/.codex/agents` and **prunes both**;
`install_hooks.py` refreshes the Codex skill mirror and re-renders the persona pool. The repair plan
names those directories. Nothing else would have told you.

**Orphans are never repaired here.** A generated file whose persona has left the pool is one the
renderer *deletes*. This tool reports it, names it, says plainly that a write run would `unlink()`
it, and stops — running that command is your call. It also re-checks immediately before any render
and abandons the run if an orphan appeared since you read the report.

**`--fix` stops when it cannot see everything.** If the callee truncated its stale list, or printed
a line this tool could not classify, no mechanical repair is offered at all: the report says so and
hands you the command. `sync_personas.py` caps its printed list at twelve, and because deletions are
appended last, the entries that fall off the end are exactly the unmanaged and orphaned ones.

**One known limit, and it is the callee's.** `sync_personas.py` offers no read-only invocation whose
scope equals the write's — `--repo R --check` sees the project trees, `--check` the machine-global
ones, `--repo R` writes both. The enumeration is therefore the union of two reads, and a test
measures that union against what a real write actually touches. The durable fix is one line in
`agent-personas`: make `--check` honour the write's scope, or add a `--dry-run`.

## One more thing the report tells you that nothing else will

**`post-commit graph refresh: ABSENT` is often not a hole.** `install_hooks.py` skips that hook when
the repository has no `graphify-out/graph.json`, and its `--check` output cannot say so. Re-running
the installer will not install it. So it is reported with that condition stated and is **never**
offered as a mechanical repair — a repair that cannot succeed, offered forever, is the same
disablement as bad advice. Build the graph first, or accept its absence: graphify is optional and
the core never requires it. The real fix belongs in `install_hooks.py --check`, which should
distinguish *absent* from *not applicable*.

## What `--fix` refuses

- **Delete an agent file, or any file** — enforced by a guard that re-checks both scopes and
  abandons the render, not by intention. A deletion that somehow reaches the output is parsed,
  reported, and fails the run.
- Adopt a repository into the execution methodology — adoption is deliberate and staggered.
  Already-adopted-and-drifted is re-rendered; a hand-written `methodology.md` is reported with the
  callee's own *move it aside* remedy, because a re-render refuses to clobber it and returns 2.
- Overwrite a tool policy a human wrote by hand.
- Create a remote, push, change visibility, declare a repository public, or touch forge settings.
- Repair the route. That is authoring, not mechanics.
- Run at all under `--json`; the report has to be read before the repair.

Running `--fix` twice changes nothing the second time and says so.

A **deliberately deferred** methodology and an **approved public-exception waiver** are conforming
outcomes, not findings. Reporting either as non-conformance would tell you to undo a decision you
recorded on purpose, on every run, with no remedy that could clear it.

## Verify the tool itself

```bash
/opt/homebrew/bin/python3 "$HOME/.claude/skills/project-conformance/tests/test_conformance.py"
```

Use the 3.14 interpreter. `/usr/bin/python3` is 3.9 and crashes several scripts in this toolchain.

## Related

`project-onboarding` — bringing a project under the standard the first time.
`agent-personas` — the roster, the judging allow-list, and `sync_personas.py`.
`progressive-disclosure` — the route standard and its validator, hooks, and GitHub check.
