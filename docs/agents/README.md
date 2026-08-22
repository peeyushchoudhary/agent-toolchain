# Agent route index

**Authority: current.** This is the route an agent takes into this repository. Start here after
`AGENTS.md`; open one guide, run one command, stop.

| Task | Guide | Command |
| --- | --- | --- |
| Understand what the installer places, and where | [what-gets-installed.md](what-gets-installed.md) | `./install/install.sh --dry-run` |
| Understand the route itself and its validator | [progressive-disclosure.md](progressive-disclosure.md) | `python3 install/skills/progressive-disclosure/scripts/validate_disclosure.py . --standard` |
| Route work to a persona, or add one | [agent-personas.md](agent-personas.md) | `python3 install/skills/agent-personas/scripts/sync_personas.py --list` |
| Learn how the route works in THIS repository | [disclosure.md](disclosure.md) | `./install/verify.sh` |
| Find where a document belongs | [../architecture/repository-standard.md](../architecture/repository-standard.md) | `python3 install/skills/progressive-disclosure/scripts/migrate_to_standard.py .` |
| Read a settled decision before re-opening it | [../decisions/decisions.md](../decisions/decisions.md) | — |
| Read what an earlier agent already learned here | [lessons.md](lessons.md) | — |
| Onboard another repository | [../runbooks/onboarding-a-project.md](../runbooks/onboarding-a-project.md) | `./install/install.sh` |

Everything else is one hop further: [../README.md](../README.md) is the documentation index.

## What is NOT here, and why

<!-- agent-personas: {"mode":"base-only","reason":"This repository AUTHORS the base pool (install/skills/agent-personas/personas, 14 sources) and drives no project of its own, so a project overlay here would be a specialist derived from the toolchain for the toolchain. Base-only is the decision, not the default."} -->

No `personas/`. The standard lists it, and it would be empty here: the persona pool is SOURCE
(`install/skills/agent-personas/personas/`, 14 files), not a project overlay, and the decision above
records that in the one form the validator reads. The standard's own rule is that a required
directory must not become "empty ceremony"; a directory created to satisfy a checker that does not
check for it would be exactly that. Create it the day this repository needs a specialist of its own.

`lessons.md` IS here, and it was not created empty — see
[lessons.md](lessons.md). It carries what this migration measured.
