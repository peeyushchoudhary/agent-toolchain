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
| Methodology maintenance entry and compatibility map | [runbooks/methodology-management.md](runbooks/methodology-management.md) | Current |
| Public interface for the management setup procedure | [runbooks/onboarding-a-project.md](runbooks/onboarding-a-project.md) | Current |
| Compatibility route for older adoption links | [runbooks/full-adoption.md](runbooks/full-adoption.md) | Current |
| The Codex side, and what it does not get | [runbooks/codex.md](runbooks/codex.md) | Current |
| Every file the installer places, and why | [agents/what-gets-installed.md](agents/what-gets-installed.md) | Current |
| Front-page imagery, accessible descriptions and regeneration | [assets/readme/README.md](assets/readme/README.md) | Current |

Installation lives in [../install/README.md](../install/README.md).

## What is published, and what is not

`install/skills/` is a vendored copy of the installed shared layer. It is not automatically
everything that layer contains — each skill is a decision, and the decisions are recorded here
because a skill that is silently absent is indistinguishable from one that was forgotten.

Ten skills are published: `progressive-disclosure`, `agent-personas`, `agent-persona-factory`,
`execution-methodology`, `methodology-management`, `graph-navigation`, `project-onboarding`,
`project-conformance`, `project-migration`, and `gate-sandbox`. The list is enforced by
`install/skills/.gitignore`, which ignores its own directory and then re-includes those ten by name,
so adding another is a deliberate line in a file rather than a side effect of a copy.

**`execution-methodology` is published.** It is the pipeline this repository describes — the
three human gates, light and full task lanes, independent evidence, and milestone seal — and until now it was the one
part of the process that existed only on a single machine. The vendored copy is the only disaster
recovery this toolchain has; an unpublished skill is one disk failure from gone. Against that, the
public-repo invariant costs nothing here: the skill describes a process, not the work it was
applied to, and it names no project, path, or person. Weighed together, the recovery argument wins
uncontested, because the objection it had to beat turned out to be empty rather than merely
smaller.

**`methodology-management` is published.** It owns assessment, setup, repair, product-document
migration and upgrade coordination without copying the underlying procedures. `project-onboarding`
and `project-migration` remain explicit compatibility entries; `project-conformance` remains an
implicitly selectable read-only assessment. Requested repair returns to management. Publishing,
global installation, project adoption and model activation remain separate operations. See the
[route map](runbooks/methodology-management.md).

**`gate-sandbox` is published.** It is machinery for running a write-producing gate against a
manifest-equal standalone copy — the executable form of a protocol this repository already
described in prose and had never shipped. Publishing it is only defensible because it contains no
project fact at all: every checkout path, branch, referent, port and image arrives from
configuration outside this repository, and a test asserts the absence rather than trusting it.

It is the first published skill whose configuration is deliberately NOT published. The machinery is
public; the three-layer config it reads lives in the private home repository. That split is the
whole reason a public copy is possible, and collapsing it would be the way this skill stops being
publishable.

Its own break-tests were mutation-tested before they were believed, and one mutation SURVIVED:
deleting `(deny file-write*)` from the profile changed nothing, because the deny-default line is
what denies writes. The behavioural checks could not say which line they depended on. That is
recorded in the profile itself, and the load-bearing line is now asserted structurally — a passing
suite is not evidence that the rule you think you are testing exists.

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
