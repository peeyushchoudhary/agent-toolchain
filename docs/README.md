# Documentation index

| Area | Document | Status |
| --- | --- | --- |
| How work is sequenced, and what "done" means | [operating-model.md](operating-model.md) | Current |
| The four disclosure layers and the validator | [progressive-disclosure.md](progressive-disclosure.md) | Current |
| Where files belong; migrating an existing repo | [repository-standard.md](repository-standard.md) | Current, v1.1 |
| Forge rules, the push guard, zero-cost posture | [github.md](github.md) | Current |
| The persona roster and its routing | [agent-personas.md](agent-personas.md) | Current |
| Decisions, each against its rejected alternative | [decisions.md](decisions.md) | Current |
| Measurements the decisions rest on | [measurements.md](measurements.md) | **Dated** — re-derive when prices move |
| The weekly improvement record, newest first | [improvements-weekly.md](improvements-weekly.md) | Current — a record: entries accrete, never rewritten |
| Five steps to onboard a project | [onboarding-a-project.md](onboarding-a-project.md) | Current |
| The long-form adoption walkthrough | [full-adoption.md](full-adoption.md) | Current |
| The Codex side, and what it does not get | [codex.md](codex.md) | Current |
| Every file the installer places, and why | [what-gets-installed.md](what-gets-installed.md) | Current |

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
