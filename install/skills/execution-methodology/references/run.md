# Running an approved goal

`<skill>` below is this skill's installed directory. Every command runs from the project root.

```
approve ──► run_goal.py ──► session (chief) ──► per task: dispatch → check → guard → [risk review] → commit+tick
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
   This writes `.runs/active`, which the Stop hook and other tools read.

Then either work interactively, with native `/goal` in either harness and the condition
"`goal.py done` exits 0 for the active milestone, or stop after N turns", or start the driver for
long runs:

```
python3 <skill>/scripts/run_goal.py --goal <id> --harness claude|codex
```

## Launch profiles

Each session launches with the chief profile's model and effort and a profile that lets the
chief edit, commit and run the declared gates unattended.

| Harness | Command shape | Permissions |
| --- | --- | --- |
| Claude Code | `claude -p --model <m> --effort <e> --permission-mode auto --settings .runs/<goal>/claude-settings.json --output-format json "<resume prompt>"` | The settings file allows `git add`, `git commit`, the plan's gate commands and the skill's scripts, and registers the Stop and SessionStart hooks. It is added on top of normal settings precedence; user, project, local and managed settings stay in effect. Auto mode's reviewer decides the rest. A denial is logged, not retried blindly. |
| Codex | `codex exec --approve-for-me -m <m> -c model_reasoning_effort=<e> --json "<resume prompt>"`, adding `-c sandbox_workspace_write.network_access=true` when `run.network` is true | `--approve-for-me` runs in the workspace-write sandbox, which covers the repository; the CLI rejects an explicit `-s` alongside it. Automatic approval review handles the rest. Hooks come from the project's `.codex/hooks.json`, which migration writes and the founder trusts once in Codex (see [migrate.md](migrate.md), step 4). The driver refuses a Codex run, exit 2, when that file does not register a Stop hook running `goal.py stop-hook` and a SessionStart hook, and warns when `$CODEX_HOME/config.toml` (default `~/.codex`) has no `hooks.state` entry for it. |

What each profile fixes:

| | Claude Code | Codex |
| --- | --- | --- |
| Sandbox | None added; an inherited `sandbox` setting still applies. | The workspace-write sandbox, through `--approve-for-me`. |
| Approval | Auto mode plus the settings file's allow rules (and deny rules when network is off). Inherited rules still apply. | Automatic approval review, through `--approve-for-me`. |
| Writable paths | The working directory; an inherited `permissions.additionalDirectories` still applies. | The repository; no extra roots. |
| Network | When `run.network` is false the settings file denies `WebFetch` and `WebSearch`. Shell network access (`curl`, package managers) is limited only by an inherited sandbox. | Off in the sandbox unless `run.network` is true, which adds `-c sandbox_workspace_write.network_access=true`. |

The session environment sets `GOAL_ROLE=chief`. Judge and advisor calls set `GOAL_ROLE=judge`,
which exempts them from the Stop hook, so they stop freely.

## Driver

`scripts/run_goal.py` is a foreground loop; each iteration:

1. selects the active milestone, the first without a `goal/<id>/M<n>` tag;
2. launches one fresh headless chief session whose resume prompt holds the goal line, the active
   milestone, `goal.py status` and the tail of `progress.md`;
3. ends the session when the envelope, `run.session_hours`, expires.

Progress means newly completed tasks (ticked, committed and guard-clean) or a new milestone tag;
commits, verdicts and `Queue` entries alone are not. The driver stops when the goal is done, every
remaining task is parked or waiting on the `Queue`, two consecutive sessions make no progress, or
exhausted quota outlasts the retry window. It retries quota with backoff, so an overnight reset
continues the run. Session usage is appended to `progress.md`.

## Stop hook

`goal.py stop-hook` is the Stop hook in both harnesses. It acts only when `.runs/active` names a
goal and `GOAL_ROLE` is unset or `chief`.
While the active milestone is not done it blocks the stop with a re-anchoring reason, for example:

> Goal G-3: <outcome>. Not done: T4 unchecked; no full_gate receipt for the candidate tree. Next ready: T4 (covers AC-3).

It allows the stop after three consecutive blocks without progress (logging `STALLED` to
`progress.md`), when every remaining task is parked, or when the session envelope has expired.
Claude Code's own cap on consecutive blocks is a further backstop. The session hook,
`goal-session.sh`, prints the active goal's status at session start, or the migrate-first notice.

## Per task

1. **Select.** `goal.py next` returns the next ready task: its `needs` are done, it is not parked,
   and its `writes` do not overlap a running task (`--running <T>`, `--limit 2` for two builders).
2. **Dispatch.** Send the builder a compact packet: the goal line, the task block, the criteria
   text, the path of the relevant design section, the gate command and the stop conditions. Pass
   paths, not pasted content, which goes stale. A task you can finish in a few tool calls,
   do directly. The `builder:` field picks the builder's model by persona. A correction
   packet also carries a **Keep** list: the behaviours in the code it touches that earlier
   verdicts, Decisions or tests established, each with its reason in a few words. A builder who
   must remove a Keep item stops and reports.
3. **Check.** `python3 <skill>/scripts/gate.py check --goal <id> --cmd "<gate>"` runs on the
   working tree and writes no receipt; it only gates the commit.
4. **Guard.** `python3 <skill>/scripts/goal.py guard --task <T>` checks scope, test integrity and
   frozen inputs over the working-tree diff, with the same rules `goal.py done` applies later.
5. **Risk review.** `risk: safety` brings the security reviewer onto the task diff; `boundary` or
   `data` brings the reviewer with the matching lens. See [review.md](review.md).
6. **Commit and tick.** One commit carries `[T<n>]` in the subject, the task's changes, the checkbox
   tick and a progress line.

A failed check or guard goes back to the same builder, resumed with the output, and is counted
with `goal.py attempt --task <T>`. After two failed attempts restart the builder fresh once; if that
fails, park the task `[!]`, queue it with a diagnosis, escalate it (see [escalation.md](escalation.md)) and
continue with other ready work.

## Milestone close

1. Commit everything; the tree must be clean.
2. Run `gate.py receipt --goal <id> --name full_gate --cmd "<full_gate>"`, the same with
   `--name e2e`, and `--name proof` for every automatic proof command.
3. `goal.py evidence --milestone M<n>` writes `.runs/<goal>/M<n>-evidence.md`; the builder never
   writes it.
4. Run cross-vendor acceptance over the milestone diff, the criteria and the evidence record (see
   [review.md](review.md)); the verdict names the tree it judged.
5. When `goal.py done --milestone M<n>` exits 0, tag `goal/<id>/M<n>`, regenerate the explainer
   and write the founder digest.
6. Continue the next milestone on the same branch, normally in a fresh session. The founder merges
   by tag, possibly several milestones at once.

## Receipts

`gate.py` runs the command itself and records the exit status and the executed, failed and skipped
counts, parsed from unittest, pytest, Gradle or JUnit XML (`--junit <glob>`). Gradle commands must
carry `--rerun-tasks`, or cached results would count as executed. A run fails on a nonzero exit, an
exit status that contradicts the printed verdict, zero executed tests (unless `--count none` is
declared), failures not in the baseline, or a tracked file changed by the run.

`receipt` additionally requires a clean committed tree, deletes any earlier receipt for the same
(tree, command) before running, and writes the new one. A receipt therefore describes the latest run
of that exact command on that exact tree, and a failed rerun leaves no old PASS. Changing a command
in the plan makes old receipts irrelevant, because `done` looks up the plan's current command.

## `.runs/<goal>/` layout

Gitignored (`/.runs/` is in the project's `.gitignore`).

| Item | Contents |
| --- | --- |
| `progress.md` | one line per event: task, commit, check result, verdict path, default taken, usage |
| `attempts.json` | failed attempts per task, carried across sessions |
| `receipts/` | gate receipts, one per (tree, command) |
| `baseline.json` | failures present on the base commit, recorded once |
| `verdicts/` | reviewer, security, advisor and acceptance verdicts |
| `M<n>-evidence.md` | the milestone evidence record |
| `session.json` | session start and envelope |
| `explainer.html` | the founder explainer, regenerated per approval or merge |

`.runs/active` names the active goal and plan; `goal.py stop` clears it.
