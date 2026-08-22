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

Eight skills are published: `progressive-disclosure`, `agent-personas`, `agent-persona-factory`,
`execution-methodology`, `graph-navigation`, `project-onboarding`, `project-conformance`, and
`project-migration`. The list is enforced by `install/skills/.gitignore`, which ignores its own
directory and then re-includes those eight by name, so adding a ninth is a deliberate line in a
file rather than a side effect of a copy.

**`execution-methodology` is published.** It is the pipeline this repository describes — the
artifacts, the three human gates, the task card, the ledger contract — and until now it was the one
part of the process that existed only on a single machine. The vendored copy is the only disaster
recovery this toolchain has; an unpublished skill is one disk failure from gone. Against that, the
public-repo invariant costs nothing here: the skill describes a process, not the work it was
applied to, and it names no project, path, or person. Weighed together, the recovery argument wins
uncontested, because the objection it had to beat turned out to be empty rather than merely
smaller.

**`project-conformance` is published.** It reports whether an onboarded repository still meets the
standard, and repairs the part of that answer that is mechanical. The disaster-recovery argument
that carried `execution-methodology` applied to it unchanged and no counter-argument was ever made:
it was unpublished only because publishing it is a set of coordinated edits and no task had owned
them all at once. One now has: the skill tree, the `.gitignore` allowlist line, the
`install/skills/README.md` row, the tables in `what-gets-installed.md` — and a FIFTH this paragraph
did not name, `MIRRORED_SKILLS` in `check_toolchain.py`, which governs the Codex mirror. The
installer began mirroring the seventh skill while that list still watched six, so it was installed
on the Codex side and guarded by nothing there for exactly as long as it took to notice. A roster
that lives in five places is repaired in five commits or not at all, and a document that counts
four is how the fifth gets missed. Those four edits
were the whole content of the two top-level entries in the vendored-drift baseline, so that
baseline is now three findings and not five; the three that remain are the `agent-personas` test
files, which are a different decision entirely. See
[agents/what-gets-installed.md](agents/what-gets-installed.md), "Re-vendoring: what is left behind
on purpose".

Two things about it are worth stating here, because both are consequences of what it is rather than
defects. It **orchestrates and reimplements nothing** — every judgement comes from the installed
checker that already owns it — so its vendored suite drives the real tools under `~/.claude` and is
green only on a machine that has the layer installed. And it is **not in `MIRRORED_SKILLS`**: that
list is machine state held in a file this repository only mirrors, so it is changed on the machine
first. Publishing a skill and mirroring it to Codex are separate acts, and this is the first skill
where they have come apart.

**`project-migration` is published**, and the count below was tested rather than trusted. It moves
an already-onboarded repository's product documents onto the bound schema — the opposite
precondition to `project-onboarding`, which is for a repository that has nothing yet. It is its own
skill for that reason: one description cannot honestly name both states, and a reader holding a
conforming repository does not open a page that says the repository is not set up.

Its publication landed all five edits in one commit, including `MIRRORED_SKILLS` — the paragraph
above is what made that possible, and the register earning its keep once is the argument for
keeping it. Two things the five-edit count still does not capture, both found by running it. FIRST,
the edits are ORDERED: `git add` of a new `SKILL.md` is refused as ignored until the allowlist line
exists, so edit 2 precedes edit 1 whatever order a list puts them in. SECOND, this paragraph is a
SIXTH site, and nothing derives it — `verify.sh`'s `check_prose_agrees` reads the allowlist as the
roster and greps the TOP-LEVEL `README.md`, never this file. It asserts that a published name is
PRESENT somewhere on the front page. It cannot tell whether a sentence about that name is true.

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
