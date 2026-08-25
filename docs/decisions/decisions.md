# Decisions

The non-obvious calls, and what they were weighed against. A decision recorded without its
alternative is just an assertion.

Numbers are in [measurements.md](../product/measurements.md).

---

## D1 — The README is a fourth disclosure layer, not part of the agent route

**Chose:** a separate seven-section contract for `README.md`, gated structurally.

**Over:** folding it into `docs/agents/`, or leaving it ungated.

**Why:** `AGENTS.md` routes an agent; `README.md` helps a human judge whether the project is real.
The validator proves structure; a PR-template check owns honesty.

---

## D2 — Secret scanning and branch protection run locally, not on GitHub

**Chose:** a `pre-push` hook.

**Over:** GitHub Secret Protection (~$19/committer/month) and a paid plan for protected branches.

**Why:** both are paid on private repos, and the operating model already says local gates are the
only gates. Zero cost, and it runs where the work happens.

**Consequence:** the guard is per-clone, because git never clones hooks. Session start flags a clone
that is missing it.

---

## D3 — The secret scan reads every commit in the pushed range, not the net diff

**Chose:** `git log -p` over the range.

**Over:** `git diff base..local`.

**Why:** a credential added in one commit and removed in the next still ships to the server and
stays recoverable, but the net diff cancels the two out. **The net-diff version was written first
and verifiably missed exactly that case in testing.**

---

## D4 — Merge commits, never squash

**Chose:** `gh pr merge --merge`, plus a milestone tag.

**Over:** squash (one clean commit per milestone) or rebase.

**Why:** with no CI, the commit history is the only audit trail. The post-commit graph refresh has
already indexed each commit individually, and squashing discards that. Rebase would rewrite SHAs
that tags and notes point at.

---

## D5 — History is link-checked but never crawled

**Chose:** exclude `docs/archive/`, `docs/superpowers/`, `docs/eval-reports/` from the disclosure
crawl while still validating links *into* them.

**Over:** crawling everything reachable.

**Why:** a plan written months ago *should* cite files that have since moved — that is what makes it
history. Crawling it produced 117 correct-by-the-letter stale-path warnings that buried the one
real breakage.

---

## D6 — Budgets and depth apply to the route, not to everything reachable

**Chose:** apply `--max-depth` and the guide budget only to entry files and `docs/agents/`.

**Over:** applying them to every crawled document.

**Why:** a 2,800-word PRD is not a disclosure failure; it is a PRD. Warning about it is correct by
the letter and wrong by the purpose, which is how a report gets ignored.

---

## D7 — Persona definitions are generated, not hand-maintained per harness

**Chose:** one harness-neutral source, rendered to Claude markdown and Codex TOML.

**Over:** maintaining both formats by hand, or a neutral format nobody authors in.

**Why:** two hand-maintained formats drift the first time anyone forgets, and silently — a harness
quietly runs an older persona. More fundamentally, project-level agents **override** a same-named
user agent wholesale, so "base persona plus project direction" *cannot* be expressed by file
placement. Merging must happen before the harness sees it.

---

## D8 — Judges cannot edit, structurally

**Chose:** `disallowedTools` on Claude and `sandbox_mode = read-only` on Codex for every judging
persona.

**Over:** instructing them not to edit.

**Why:** "a builder never approves its own work" is only a guarantee if enforced. It also removes
the failure where a reviewer quietly patches the defect it found, so the defect is never recorded.

**Accepted exception:** `architect` may write, so it can author ADRs. Tool restriction cannot be
scoped to a path, so its "design docs only" limit is an instruction — the roster's single soft
boundary, documented as such wherever it appears.

---

## D9 — Cross-harness dispatch rejected

**Chose:** every persona runs in the harness being driven.

**Over:** Claude implements → Codex reviews, and the reverse.

**Why:** a controlled review cost **$0.367 against $0.212**, about 1.7×: the cold process re-read
186K versus 30K input above a **~23K-token prompt floor**. Cross-family review caught a missing API,
so revisit when context can be shared. An earlier cheaper result compared unequal repository access
and was invalid.

---

## D10 — Implementation split into two tiers

**Chose:** `developer` (sonnet/terra) and `senior-developer` (opus/sol).

**Over:** one `implementer` at opus with "escalate per dispatch".

**Why:** two named personas make escalation explicit and route roughly 70% of bounded work off the
expensive model (**$8.00 → $4.64** per milestone). `developer` must escalate rather than infer on
interfaces, migrations, contracts, security, concurrency, or placement. `senior-developer` uses
the stronger model at medium effort; raising both model and effort would double-charge one tier.

---

## D11 — Only the graph's learnings are committed, not the graph

**Chose:** commit `graphify-out/reflections/` and `graphify-out/memory/` (~36 KB); keep the 22 MB
graph and 65 MB cache ignored.

**Over:** committing all of `graphify-out/` (168 MB), or none of it.

**Why:** every rebuild rewrites a reproducible 22 MB blob; the query lessons do not regenerate and
accumulate from real use.

---

## D12 — Report, never scaffold, at session start

**Chose:** session hooks that describe problems and name the fix command.

**Over:** hooks that create the missing files.

**Why:** they fire in every directory a session starts in, including scratch clones and
repositories that are not yours; files created there are unexplained untracked files in someone
else's tree. The hook tells; the human decides.

---

## D13 — This repository uses a documentation/tooling taxonomy

**Chose:** route work from `AGENTS.md` to `docs/README.md` and the maintained public guides.

**Over:** creating product, architecture, runbook, and `docs/agents/` tiers solely to resemble the
application repositories this tooling serves.

**Why:** installer and verification paths are not an application product or a production
operation, and empty application tiers would imply false authorities. The default route check is
authoritative; revisit if an application runtime or operated service appears.

**SUPERSEDED by [D17](#d17--this-repository-complies-with-the-standard-it-ships).** Kept, not
rewritten: the reasoning was sound and one of its two premises turned out to be false.

---

## D14 — Bounded repairs and review

**Chose:** Goal Capsule, classification, fresh read-only `reviewer` before Design/Plan gates
(`fork_turns: "none"` Codex; equivalent fresh-thread primitive elsewhere, never prompts); `PASS`;
one correction, scoped rereview. Post-code default: Implementation unless Design/Plan named.

**Over:** scope redefinition, quotas, personas, author rationale, cross-harness review, or
consensus loops.

**Why:** blockers need frozen-artifact evidence. Packet: original report/finding, correction/diff,
corrected artifact, frozen artifacts. Same-cause recurrence returns to its gate; budgets never
alter verdicts.

---

## D15 — Read-only judges test writable standalone copies

**Chose:** keep `test-judge` read-only; run write-producing gates in a nested sandbox over a
manifest-equal copy.

**Over:** source write, unsandboxed gates, or hostile-writer receipt claims.

**Why:** a human-approved launcher immediately enters a custom profile with source read, copy write,
and network denied; the gate never runs unsandboxed. Receipts check post-boundary XML consistency,
not execution, cache avoidance, or hostile writers. Exact runner rerun settings own those
guarantees; Gradle requires `--rerun-tasks`.

---

## D16 — project-onboarding and project-conformance stay two skills

**Chose:** `project-onboarding` brings a repository under the standard **once**, and **writes**;
`project-conformance` asks whether it still conforms. It **reports by default and writes nothing**;
`--fix` applies only what the report already named, file by file. Onboarding's verify step calls it.

**Over:** one skill with an onboard mode and a check mode.

**Why:** the checker repairs post-onboarding drift — judges outliving a withdrawn capability — by
hand, where no agent may write. One skill would claim both permissions.

---

## D17 — This repository complies with the standard it ships

**Chose:** create `docs/{agents,architecture,product,decisions,runbooks,archive}/`, file the twelve
flat documents under them, and run `validate_disclosure.py --standard` against this repository from
`install/verify.sh`.

**Over:** [D13](#d13--this-repository-uses-a-documentationtooling-taxonomy), which rejected exactly
these tiers; and over the alternative of amending the standard so a tool repository needs fewer
directories than a product repository.

**Why:** D13's premise was "empty application tiers would imply false authorities", and its warrant
was "the default route check is authoritative". The second premise is FALSE, measured: the default
route check does not evaluate the standard at all — it prints `NOT RUN cross-project structure
standard: not requested` and says in its own summary "Nothing is known about it." D13 rested on a
check that had declined to answer the question. Pointed properly, the same script reported seven
errors and exit 1.

The first premise was true about EMPTY tiers and is not true of these. Every directory received the
documents that already existed and a `README.md` naming its purpose and authority level — including
`archive/`, whose README says in the first line that nothing in it is authoritative. Amending the
standard was the honest alternative and was rejected on one ground: the standard's own words are
"One layout for every project", and a tool repository writing itself an exemption from the layout it
asks every other repository to adopt is the failure mode the exemption would be hiding.

The route cost was measured, not assumed. Each move spends one hop, and the validator warns
`too-deep` past two, so `docs/README.md` links every document DIRECTLY as well as linking the six
area indexes: `routed docs: 25, max depth: 2`, unchanged depth against 18 routed docs before.

---

## D18 — The decisions record stays one file inside `docs/decisions/`

**Chose:** `docs/decisions.md` -> `docs/decisions/decisions.md`, with a short `README.md` beside it
stating purpose and authority.

**Over:** `docs/decisions/README.md` holding the record, and over one file per decision.

**Why:** the word-budget exemption for an accreting RECORD is keyed on the BASENAME.
`validate_disclosure.py` matches
`^(measurements|benchmarks|decisions|adr|rulings|improvements|changelog|history)(?:[-_][a-z0-9]+)?\.md$`
against `doc.name`, so `decisions.md` is exempt and `README.md` is not. Renaming would have handed a
1,185-word file back to the 1,200-word guide budget — two decisions from the wall `measurements.md`
hit first, which is the incident that created the exemption. The class travels with the name, so the
name stays.

One file per decision would escape the budget too, by sharding, which the same source comment names
as gaming the metric rather than answering it; it would also break every `decisions.md#dNN` anchor
cited from the operating model, the measurements and `AGENTS.md`.

Note what is NOT the reason: after `docs/agents/README.md` exists, the budget check narrows to
depth-0 entries and `docs/agents/*`, so nothing under `docs/decisions/` is budgeted whatever it is
called. That protection is an ACCIDENT of where the route index sits, and one commit from
disappearing. The rule is chosen over the accident deliberately.


## D19 — No compression proxy in this repository, and the waste was structural anyway

**Chose:** reject `caveman` and `headroom` as in-repo dependencies; attack token cost by capping
what agents WRITE and by pruning unused MCP servers on the workstation.

**Over:** wrapping the agent in a compression proxy, and over a `--json` mode on `validate_card.py`
proposed for the same purpose.

**Why:** three independent reasons, any one sufficient. LICENCE AND STACK — caveman's engine is
BSL-1.1 with Go binaries and a Node installer; headroom is a proxy plus a HuggingFace model and a
torch tree. Neither enters a python3-stdlib-only public repository whose scripts write nothing.
WORKLOAD — caveman's 33.2% is honestly measured (paired arms, exact-answer oracle, the negative case
left in) but its own `HONEST-NUMBERS.md` records a fixed per-turn overhead and a NET LOSS on terse
coding question-and-answer, which is what this loop is; we are its measured loss case. Its own
paired arm put headroom at 6.7% with a confidence interval crossing zero. EVIDENCE — headroom's
accuracy table is GSM8K and SQuAD at n=100, with no agentic coding quality evidence at all.

**And the finding that made the question smaller:** our waste was structural, not linguistic. Cards
were capped at 150 lines and judge output was capped at nothing, so verdicts ran 7.4 times the bytes
of the cards they answered. Deleting 56 banned diff snapshots removed half a workspace's bytes with
no finding lost, because git regenerates a diff from a commit range. A proxy saving a third of a
bill we should not be paying is worse than not paying it.

**What is still worth doing, and it is not in this repository:** the harness prefix every subagent
re-sends measures roughly 24,000 tokens of tool schema per call before any work — about 6.9 million
tokens across the casts on record. Pruning unused MCP servers is a workstation action with zero
lines and zero quality cost. If it is taken, nothing here should name the tool that measured it: an
unverifiable claim pinned in a reference is how nine inert checkers were written.

**Adopt later, method only:** an unshaped control group, so a future saving is measured rather than
estimated.

**Known-wrong-in-a-month if:** a milestone stalls on a removed tool, or the verdict cap is found to
have made a judge drop a finding rather than cut prose.

---

## D20 — `project-conformance` is published

**Chose:** vendor the whole skill — `SKILL.md`, `scripts/`, and its 989-line `tests/` — declare it
in `install/skills/.gitignore`, and name it in `install/skills/README.md`, `README.md` and
`docs/agents/what-gets-installed.md`.

**Over:** leaving it installed-only, which is what it had been. The objection was never
disagreement; it was that publishing takes several coordinated edits and no task had owned them all.
The record said four. There were five: `MIRRORED_SKILLS` in `check_toolchain.py` governs the Codex
mirror, and the installer began mirroring seven skills while that list watched six. The fifth was
found only because the file had already written down the gap it would leave.

**Why:** the disaster-recovery argument that carried `execution-methodology` applies to it
unchanged, and the public-repo invariant costs nothing — the skill names no project, path or
person, and a grep for all four classes before the commit found only `~/.claude`, `~/.codex` and an
`example.invalid` fixture address.

**Consequence, measured:** the vendored-drift baseline drops from **5 criticals to 3**. Two of the
five were `install/skills/.gitignore` and `install/skills/README.md`, each differing by the one
line this decision adds. The three that remain are the `agent-personas` test files, which are a
different matter — see [what-gets-installed.md](../agents/what-gets-installed.md), "Re-vendoring:
what is left behind on purpose". `install.sh` moves from `6 of 6` to `7 of 7`, derived, with no
edit to `install.sh`.

---

## D21 — the vendored `project-conformance` suite is green only with the layer installed

**Chose:** vendor `tests/` anyway, and publish the empty-`$HOME` numbers beside the green ones.

**Over:** leaving the directory behind the way `agent-personas`' suite is left behind — which would
have swapped two baseline criticals for one, publishing 989 lines of test and then not publishing
them.

**Why:** the `agent-personas` reason does not apply. That suite needs a sibling `docs/` the vendored
layout has no place for; this one needs nothing outside the skill tree, and from the vendored
position, run the way `verify.sh`'s `run_one_suite` runs it, it is `Ran 56 tests ... OK`.

**Consequence:** under `HOME=$(mktemp -d)` it is `Ran 56 ... FAILED (failures=15, errors=7,
skipped=3)`, where `execution-methodology` is `Ran 1070 ... OK` and `progressive-disclosure` is
`Ran 395 ... FAILED (failures=1)`. That is not a defect being tolerated. `check_conformance.py`
orchestrates and reimplements nothing — every judgement comes from the installed checker that owns
it — so its suite drives the real tools under `~/.claude` by construction. `HOME=$(mktemp -d)
./verify.sh` is therefore red on this one suite, and `verify.sh` already attributes it to the
machine rather than to the tree.

---

## D22 — publishing a skill and mirroring it to Codex came apart

**Chose:** publish `project-conformance` without adding it to `MIRRORED_SKILLS`.

**Over:** adding the name to `check_toolchain.py` in this repository as part of the same commit.

**Why:** the copy of `check_toolchain.py` here is a **vendored mirror** of the installed one. A name
added on one side alone is drift — it would have manufactured a sixth vendored-drift critical
against the very file that reports the count. `MIRRORED_SKILLS` is machine state and is changed on
the machine first.

**Consequence:** `install.sh` mirrors seven skills to `~/.codex/skills` while `check_toolchain.py`
watches six, and `verify.sh` reports `project-conformance` absent from `~/.codex/skills` until an
install run. Both are true and both are machine-scope. Until now every published skill was also a
mirrored one, so the two lists had never had to be distinguished.

---

## D23 — the ninth conformance check reports and owns no repair

**Chose:** `product definition` reports three facts — whether `docs/product/` exists, how many
schema-bound documents carry no front matter, how many sit under `docs/product/specs/` in a shape
no rule binds — and creates no `Repair`.

**Over:** repairing what it finds, which is what the other eight checks do and what makes the
asymmetry worth recording.

**Why:** front matter carries `reviewed_by:` and a status enum — claims about a human. Generating
them would forge the review record the product-definition layer exists to hold. Renaming a spec
silently re-points every reference to it. Both are the migrator's work, done once and watched.

**Why it was needed:** the eight checks before it predate the product-definition layer entirely. On
a repository that has not migrated, all eight can be satisfied at once, and the single thing `--fix`
then repairs is the methodology render — the document *describing* the layer — while the layer
itself is absent or unread. Measured on the four repositories that have a `docs/product/specs/`:
red on all four. One of them has 236 documents under `docs/product`, **none** bound by any schema
rule and **233** of them named outside `F-<n>-<slug>.md`; `spec_check.py` exits 0 there.


---

## D24 — the `agent-personas` test directory is not vendored

**Chose:** leave it out of `install/skills/`, and record the three resulting drift criticals as
expected. Superseded in part by [D26](#d26--the-vendored-check-reads-the-installers-preserve-list):
the three are still expected, but they are now reported as *excluded* rather than as criticals,
because `install.sh` already declares this directory preserved.

**Over:** vendoring it like every other suite, or planting a copy of the human record of the judging
roster under `install/docs/` so its preflight resolves.

**Why:** that preflight resolves the record as a **sibling of the skill tree**. In the vendored
layout that lands under `install/`, where no `docs/` exists and none should — this repository's
`docs/` is one level further up. Planting a copy to satisfy a fixture would let a test dictate the
layout. Measured at `a008768`, with the rest of `install/` present, so the record is the only
missing input:

```
IncompleteTree: THE FIXTURE IS WRONG, NOT THE CODE.
  - the human record of the judging roster ... is ABSENT
Ran 26 tests ... FAILED (failures=2, errors=11)
```

Positive control, the same suite installed: `Ran 68 tests ... OK`. Collection itself fails — 26
reached, not 68. `verify.sh` runs vendored suites, so restoring the directory would surface that
collection failure on every run.

**Consequence:** three expected `--vendored` findings, one per test file, and they cannot be
silenced in `install/skills/.gitignore`: exclusion matches anchored rules on their first path
component only, an interior-slash rule is skipped, and an unanchored pattern would exclude every
test directory in both trees — including the `progressive-disclosure` suite `verify.sh` does run.
That last sentence is why D26 reads a different file instead of adding a line here.


## D25 — The vendored-drift baseline names its findings, because the count did not hold

**Chose:** list the three expected criticals individually, in this record, with a reason each.

**Over:** the previous form in `what-gets-installed.md`, which stated a count and one collective
description.

**Why:** the count stayed at 3 while the identity of all three findings changed underneath it. The
entry read "those three test files" and named the `agent-personas` suite; the three actually printed
are a top-level `.gitignore` difference, a top-level `README.md` difference, and
`execution-methodology`'s `ROUND-GRANTS.tsv`. That document's own rule said *a finding not named
here is drift* — so this was drift, and it went unnoticed for as long as only the number was
compared. **A count is a weak hash.**

**The three, and what became of each:**

| critical | why it was expected | now |
|---|---|---|
| top-level `.gitignore` differs | `~/.claude/skills/.gitignore` is a SIXTH allowlist, machine-global and separate from `install/skills/.gitignore`. It governs what the installed tree commits, not what this repository publishes. | TRANSIENT, not invariant — see below |
| top-level `README.md` differs | the installed index is generated for the machine; the vendored one is the published page. | TRANSIENT, not invariant — see below |
| `execution-methodology` `ROUND-GRANTS.tsv` installed, absent vendored | operator data. The vendored copy ships without the ledger by invariant, because a grants row names a real subject on a real machine. | EXCLUDED by [D26](#d26--the-vendored-check-reads-the-installers-preserve-list), along with the three `agent-personas` test files |

**The first two were never invariant, and this record said they were.** Measured immediately after
`./install.sh`, with D26 in place: `--vendored .` is **clean, exit 0**. `install.sh` copies both
files, so the installed and vendored copies are equal the moment it finishes; the difference is
something the machine reintroduces afterwards by regenerating its own index. Whatever this record
was measuring, it was not measuring a fresh install — which is the same defect it was raised to
document, one level up: **a baseline whose measurement conditions are not stated is a weak hash
too.** The condition is now stated. The reproducible baseline is *clean after install*, and any
finding at all is a real answer about a machine that has drifted since.
**Why it lives here and not in the inventory:** that page is a routed guide under a word budget and
sat at 1,199 of 1,200 before the eighth skill was published. This record accretes and carries no
budget by the same validator's ruling, which is where a list that will grow belongs.

**Known-wrong-in-a-month if:** a critical appears immediately after `./install.sh` and this record
is not extended in the same change, which would reproduce the exact failure it documents.


---

## D26 — the vendored check reads the installer's preserve list

**Chose:** teach `check_toolchain.py --vendored` to read `PRESERVE_ACROSS_INSTALLS` from
`install/install.sh` and report the paths it names as **excluded**, in the installed-only direction
only.

**Over:** naming those paths in `install/skills/.gitignore`, adding an exception list inside
`check_toolchain.py`, or leaving four permanent criticals in place and remembering which ones they
were.

**Why:** every one of the four was operator-local state the installer creates BY DESIGN, and the
declaration that creates it already existed — in a different file from the one the check was
reading. `.gitignore` answers "what does this repository publish"; `PRESERVE_ACROSS_INSTALLS`
answers "what does the installer put back after replacing the tree wholesale". Copying names from
the second into the first would be the same fact in two rosters, free to disagree, and false as
well: git is not being asked about those paths. D24 had already established that `.gitignore` is
the wrong instrument here — an interior-slash rule is skipped and an unanchored one would silence
every test directory in both trees.

**Direction-awareness is the load-bearing part.** `install.sh` says of its own list: *"A vendored
copy always WINS: the guard below only restores a path the staged tree does not already have... So
vendoring one of these later needs no edit here — the entry just goes inert."* A symmetric
exclusion would honour that sentence in reverse: vendor `ROUND-GRANTS.tsv` one day and the check
would stop comparing it entirely, trading a loud permanent finding for a silent uncompared one.
`is_preserved` is therefore a separate predicate from `is_excluded`, applied to the
installed-present/vendored-absent category and to nothing else, with the same no-default and
same AST-walking guard that protects `is_excluded`.

**Evidence:** `--vendored .` went from four criticals to zero of that class, with all four named in
the excluded line and their reason naming the file that produced them. Three tests pin the
behaviour, and the third deletes the install.sh line and asserts the critical returns — so nothing
here is a hard-coded name wearing a reader's clothes.

**Known-wrong-in-a-month if:** a preserved path is later vendored and stops being compared, which
`test_a_preserved_path_that_is_vendored_is_compared_normally` exists to catch.
