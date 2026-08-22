# Documentation index

## The six areas

Each directory carries a `README.md` naming its purpose and authority level.

| Directory | Holds | Authority |
| --- | --- | --- |
| [agents/](agents/README.md) | the route: task, one guide, one command | Current |
| [architecture/](architecture/README.md) | how the system is built | Current |
| [product/](product/README.md) | intent, read through shipped behaviour | Current; measurements are dated |
| [decisions/](decisions/README.md) | accepted decision records | Current |
| [runbooks/](runbooks/README.md) | operational procedures | Current |
| [archive/](archive/README.md) | superseded material | **NOT authoritative** |

## Every document, one hop from here

Listed in full and not only through the six indexes above, deliberately: the validator warns
`too-deep` past two hops from an entry file, and an area directory spends one of them. Add a
document by adding its row here in the same commit.

| Area | Document | Status |
| --- | --- | --- |
| How work is sequenced, and what "done" means | [architecture/operating-model.md](architecture/operating-model.md) | Current |
| The four disclosure layers and the validator | [agents/progressive-disclosure.md](agents/progressive-disclosure.md) | Current |
| How the route works in this repository | [agents/disclosure.md](agents/disclosure.md) | Current, standard v1.2 |
| What earlier agents learned here, newest last | [agents/lessons.md](agents/lessons.md) | Current — a record: entries accrete |
| Where files belong; migrating an existing repo | [architecture/repository-standard.md](architecture/repository-standard.md) | Current, v1.1 |
| Forge rules, the push guard, zero-cost posture | [runbooks/github.md](runbooks/github.md) | Current |
| The persona roster and its routing | [agents/agent-personas.md](agents/agent-personas.md) | Current |
| Decisions, each against its rejected alternative | [decisions/decisions.md](decisions/decisions.md) | Current — a record: entries accrete |
| Measurements the decisions rest on | [product/measurements.md](product/measurements.md) | **Dated** — re-derive when prices move |
| The weekly improvement record, newest first | [product/improvements-weekly.md](product/improvements-weekly.md) | Current — a record: entries accrete, never rewritten |
| Five steps to onboard a project | [runbooks/onboarding-a-project.md](runbooks/onboarding-a-project.md) | Current |
| The long-form adoption walkthrough | [runbooks/full-adoption.md](runbooks/full-adoption.md) | Current |
| The Codex side, and what it does not get | [runbooks/codex.md](runbooks/codex.md) | Current |
| Every file the installer places, and why | [agents/what-gets-installed.md](agents/what-gets-installed.md) | Current |

Installation lives in [../install/README.md](../install/README.md).

## What is published, and what is not

`install/skills/` is a vendored copy of the installed shared layer. It is not automatically
everything that layer contains — each skill is a decision, and the decisions are recorded here
because a skill that is silently absent is indistinguishable from one that was forgotten.

Six skills are published: `progressive-disclosure`, `agent-personas`, `agent-persona-factory`,
`execution-methodology`, `graph-navigation`, and `project-onboarding`. The list is enforced by
`install/skills/.gitignore`, which ignores its own directory and then re-includes those six by
name, so adding a seventh is a deliberate line in a file rather than a side effect of a copy.

**`execution-methodology` is published.** It is the pipeline this repository describes — the
artifacts, the three human gates, the task card, the ledger contract — and until now it was the one
part of the process that existed only on a single machine. The vendored copy is the only disaster
recovery this toolchain has; an unpublished skill is one disk failure from gone. Against that, the
public-repo invariant costs nothing here: the skill describes a process, not the work it was
applied to, and it names no project, path, or person. Weighed together, the recovery argument wins
uncontested, because the objection it had to beat turned out to be empty rather than merely
smaller.

**`project-conformance` is installed but not yet published, and that is a gap rather than a
settled decision.** It is this repository's own work — it reports whether an onboarded repository
still meets the standard — so the disaster-recovery argument that carried `execution-methodology`
applies to it unchanged, and no counter-argument has been made. It is unpublished only because
publishing it is four coordinated edits (the skill tree, the `.gitignore` allowlist line, the
`install/skills/README.md` row, and the tables in `what-gets-installed.md`) and no task has owned
all four at once. Until one does, it is deliberately absent everywhere rather than half-described:
a skill listed in the docs and shipped by nothing is worse than one that is plainly not here. This
is the whole content of the two top-level entries in the vendored-drift baseline.

**`graphify` is deliberately not published**, and this is the opposite decision on purpose. It is a
third-party vendor skill that installs itself into `~/.claude/skills` on its own schedule, not
something this toolchain authors, versions, or fixes. Every argument for publishing
`execution-methodology` fails for it: republishing it is not disaster recovery, because the vendor
is the recovery path and a stale copy here would be worse than none; and redistributing someone
else's work under this repository's licence is a question this repository has no standing to
answer. `check_toolchain.py` already excludes it from the Codex mirror on the same reasoning —
its presence is not something this toolchain manages. `--vendored` will therefore keep reporting
`graphify` as absent from the vendored copy. That finding is expected and is the recorded decision
above, not drift to be fixed. The checker reports facts and has no published-skills manifest; this
section is that manifest.

## Authority order

1. The tooling in `install/` — it is what actually runs.
2. These documents.
3. Any number older than the date at the top of `measurements.md`.

When a document and the tooling disagree, the tooling is right.
