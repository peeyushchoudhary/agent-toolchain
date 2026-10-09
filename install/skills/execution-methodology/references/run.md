# Running an approved goal

`<skill>` below is this skill's installed directory. Every command runs from the project root.

```
approve ──► run.sh ──────► session (chief) ──► per task: dispatch → check → guard → [risk review] → commit+tick
                 ▲                │                                                  │
                 │                └── milestone close: receipts (full_gate, e2e, proofs) → acceptance → tag
                 └── fresh session per milestone or envelope, until goal done | all parked | stall | quota
```

## Starting

1. Confirm the project is migrated: no `docs/agents/execution/runtime.json`.
2. Tag the approved commit: `git tag goal/<id>/approved`.
3. Record failures already present on the base commit, once:
   `python3 <skill>/scripts/gate.py baseline --goal <id> --cmd "<full_gate>"`. Later gates do not
   attribute these to the goal, and nothing else may be added to the baseline.
4. Mark the goal active: `python3 <skill>/scripts/goal.py start --goal <id> --plan <plan path>`.
   This writes `.runs/active`, which the Stop hook and the other tools read.

Then either work interactively, with native `/goal` in either harness and the condition
"`goal.py done` exits 0 for the active milestone, or stop after N turns", or start `run.sh` for
unattended runs:

```
<skill>/scripts/run.sh <id> --harness claude|codex [--sessions N]
```

## Unattended runs

`scripts/run.sh` runs one fresh session at a time, prompted with `goal.py resume`: Claude Code via
`claude -p` with a settings file registering the Stop hook, Codex via `codex exec` in the
workspace-write sandbox. It stops on DONE (writing `.runs/<goal>/packet.md`), PARKED, STALLED (two
sessions without a new tick or `[Tn]` commit) or when its sessions run out, one line per session in
`progress.md`.

## Stop hook

`goal.py stop-hook` is the Stop hook in both harnesses. It acts on the goal its `--goal` names
(`run.sh` registers it so), else on the one open plan under `docs/goals/`; with several open plans
and no `--goal` it blocks once per session asking for one. While `goal.py done` is unmet it blocks
the stop, naming the unmet rows, at most three times per session id, then allows it. Claude Code's own cap on consecutive blocks is
a further backstop.

## Per task

1. **Select.** `goal.py next` returns the next ready task: its `needs` are done, it is not parked,
   and its `writes` do not overlap a running task (`--running <T>`, `--limit 2` for two builders).
2. **Dispatch.** Send the builder a compact packet: the goal line, the task block, the criteria
   text, the path of the relevant design section, the gate command and the stop conditions. Pass
   paths rather than pasting content, because pasted context goes stale and costs tokens on every
   turn. A task you can finish in a handful of tool calls, do directly. The `builder:` field
   selects the builder's model through its persona.
3. **Check.** `python3 <skill>/scripts/gate.py check --goal <id> --cmd "<gate>"` runs on the
   working tree and writes no receipt; it only gates the commit.
4. **Guard.** `python3 <skill>/scripts/goal.py guard --task <T>` checks scope, test integrity and
   frozen inputs over the working-tree diff, with the same rules `goal.py done` applies later.
5. **Risk review.** `risk: safety` brings the security reviewer onto the task diff; `boundary` or
   `data` brings the reviewer with the matching lens.
6. **Commit and tick.** One commit carries `[T<n>]` in the subject, the task's changes, the checkbox
   tick and one progress line.

A failed check or guard goes back to the same builder, resumed with the output, and is counted with
`goal.py attempt --task <T>`. After two failed attempts restart the builder fresh once; if that
fails, park the task `[!]`, queue it with a diagnosis, park it for the founder and
continue with other ready work.

## Milestone close

1. Commit everything; the tree must be clean.
2. Run `gate.py receipt --goal <id> --name full_gate --cmd "<full_gate>"`, the same with
   `--name e2e`, and `--name proof` for every automatic proof command.
3. `goal.py evidence --milestone M<n>` writes `.runs/<goal>/M<n>-evidence.md`. The builder never
   writes it.
4. The other vendor reviews the milestone diff once, into `.runs/<goal>/review.md`; a blocking
   finding is closed by a named test or by removing the work.
5. When `goal.py done --milestone M<n>` exits 0, tag `goal/<id>/M<n>`, regenerate the explainer
   and write the founder digest.
6. Continue the next milestone on the same branch, normally in a fresh session. The founder merges
   by tag whenever they choose, possibly several milestones at once.

## Receipts

`gate.py` runs the command itself and records the exit status and the executed, failed and
skipped counts, parsed from unittest, pytest, Gradle or JUnit XML (`--junit <glob>`) produced
during the run. Gradle commands must carry `--rerun-tasks`, or cached results would count as
executed. A run fails on a nonzero exit, an exit status that contradicts the printed verdict, zero
executed tests (unless `--count none` is declared), failures not in the baseline, or a tracked
file changed by the run.

`receipt` additionally requires a clean committed tree, deletes any earlier receipt for the same
(tree, command) before running, and writes the new one. A receipt therefore always describes the
latest run of that exact command on that exact tree, and a failed rerun cannot leave an old PASS
behind. Changing a command in the plan makes old receipts irrelevant, because `done` looks up the
plan's current command.

## `.runs/<goal>/` layout

Gitignored; `/.runs/` is in the project's `.gitignore`.

| Item | Contents |
| --- | --- |
| `progress.md` | one line per event: task, commit, check result, verdict path, default taken, usage |
| `attempts.json` | failed attempts per task, carried across sessions |
| `receipts/` | gate receipts, one per (tree, command) |
| `baseline.json` | failures present on the base commit, recorded once |
| `verdicts/` | reviewer, security, advisor and acceptance verdicts |
| `M<n>-evidence.md` | the milestone evidence record |
| `session.json` | the current session's start and envelope |
| `explainer.html` | the founder explainer, regenerated per approval or merge |

`.runs/active` names the active goal and its plan; `goal.py stop` clears it.
