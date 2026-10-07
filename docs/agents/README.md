# Agent route index

**Authority: current.** This is the route an agent takes into this repository. Start here after
`AGENTS.md`; open one guide, run one command, stop.

| Task | Guide | Command |
| --- | --- | --- |
| Understand what the installer places, and where | [what-gets-installed.md](what-gets-installed.md) | `./install/install.sh --dry-run` |
| Understand the route itself and its validator | [progressive-disclosure.md](progressive-disclosure.md) | `python3 install/skills/progressive-disclosure/scripts/validate_disclosure.py . --standard` |
| Route work to a persona, or add one | [agent-personas.md](agent-personas.md) | `python3 install/skills/agent-personas/scripts/sync_personas.py --list --format markdown` |
| Move a project off v5.1 | [migrate.md](../../install/skills/execution-methodology/references/migrate.md) | `python3 install/skills/execution-methodology/scripts/goal.py --help` |
| Learn how the route works in THIS repository | [disclosure.md](disclosure.md) | `./install/verify.sh` |
| Find where a document belongs | [../architecture/repository-standard.md](../architecture/repository-standard.md) | `python3 install/skills/progressive-disclosure/scripts/migrate_to_standard.py .` |
| Read a settled decision before re-opening it | [../decisions/decisions.md](../decisions/decisions.md) | — |
| Read what an earlier agent already learned here | [lessons.md](lessons.md) | — |
| Execute approved v6 lean goal execution (F-3) | [spec](../product/specs/F-3-lean-execution.md), [design](../architecture/lean-execution.md), [plan](../product/plans/F-3-lean-execution.md) | `git tag -l 'goal/F-3/*'` |

Everything else is one hop further: [../README.md](../README.md) is the documentation index. The
current state has one public summary in [the front page](../../README.md#current-state).

## What is NOT here, and why

No `personas/`. The standard lists it, and it would be empty here: the persona pool is SOURCE
(`install/skills/agent-personas/personas/`), not a project overlay. The standard's own rule is that a
required directory must not become "empty ceremony". Create it the day this repository needs a
specialist of its own.

`lessons.md` IS here, and it was not created empty — see [lessons.md](lessons.md). It carries what
this migration measured.
