---
summary: The one decisions record: a table of every decision id with its date, a one-line statement and its status (standing, superseded, removed or archived), then the full text of the decisions that keep it, D1 to D19 among them. A section whose row is not standing is rationale only. D29 sets methodology v7 (one look per artifact, a mechanical gate, two founder touchpoints); D30 adds v7.1's planning documents, generated pointers and declared roles.
read-when: Making or citing a decision, or asking why the methodology is the way it is
covers: []
last-verified: 2026-10-09
---

# Decisions

A **standing** decision is in force; other rows are history. D1–D19 keep their full text because
the S-1 plan protects it, so a section whose row is not standing is rationale only. Removed text is
at commit `7bf35e7`, D28 at `archive/v6-followups-2026-10-09`.

| Id | Date | Decision | Status |
|---|---|---|---|
| [D1](#d1--the-readme-is-a-fourth-disclosure-layer-not-part-of-the-agent-route) | 2026-07-26 | The README is a fourth disclosure layer | superseded by D29 |
| [D2](#d2--secret-scanning-and-branch-protection-run-locally-not-on-github) | 2026-07-26 | Secret scanning and branch protection run locally | standing |
| [D3](#d3--the-secret-scan-reads-every-commit-in-the-pushed-range-not-the-net-diff) | 2026-07-26 | The secret scan reads every commit in the pushed range | standing |
| [D4](#d4--merge-commits-never-squash) | 2026-07-26 | Merge commits, never squash | standing |
| [D5](#d5--history-is-link-checked-but-never-crawled) | 2026-07-26 | History is link-checked but never crawled | superseded by D29 |
| [D6](#d6--budgets-and-depth-apply-to-the-route-not-to-everything-reachable) | 2026-07-26 | Budgets and depth apply to the route only | superseded by D29 |
| [D7](#d7--persona-definitions-are-generated-not-hand-maintained-per-harness) | 2026-07-26 | Persona definitions are generated | superseded by D29 |
| [D8](#d8--judges-cannot-edit-structurally) | 2026-07-26 | Judges cannot edit, structurally | loop half superseded by D29; judges stay read-only |
| D9 | 2026-07-26 | Cross-harness dispatch rejected | removed |
| D10 | 2026-07-26 | Implementation split into two tiers | removed |
| [D11](#d11--only-the-graphs-learnings-are-committed-not-the-graph) | 2026-07-26 | Only the graph's learnings are committed | superseded by D29 |
| [D12](#d12--report-never-scaffold-at-session-start) | 2026-07-26 | Report, never scaffold, at session start | superseded by D29 |
| D13 | 2026-08-08 | A documentation/tooling taxonomy of its own | removed |
| D14 | 2026-08-08 | Bounded repairs and review | removed |
| D15 | 2026-08-08 | Read-only judges test writable copies | removed |
| D16 | 2026-08-21 | Onboarding and conformance stay two skills | removed |
| [D17](#d17--this-repository-complies-with-the-standard-it-ships) | 2026-08-22 | This repository complies with the standard it ships | standing |
| [D18](#d18--the-decisions-record-stays-one-file-inside-docsdecisions) | 2026-08-22 | The decisions record stays one file | standing |
| [D19](#d19--no-compression-proxy-in-this-repository) | 2026-08-22 | No compression proxy in this repository | standing |
| D20 | 2026-08-22 | The conformance skill is published | removed |
| D21 | 2026-08-22 | The vendored conformance suite needs the layer installed | removed |
| D22 | 2026-08-22 | Publishing a skill and mirroring it to Codex came apart | removed |
| D23 | 2026-08-22 | The ninth conformance check reports and owns no repair | removed |
| D24 | 2026-08-22 | The persona test directory is not vendored | removed |
| D25 | 2026-08-22 | The vendored-drift baseline names its findings | removed |
| D26 | 2026-08-25 | The vendored check reads the installer's preserve list | removed |
| D27 | 2026-10-06 | Approved completion and technical recovery | removed |
| D28 | 2026-10-08 | Review closure ends in fixes, not in grants | archived, never merged |
| [D29](#d29--simplified-goal-execution-methodology-v7-one-look-per-artifact-a-mechanical-gate-two-touchpoints) | 2026-10-09 | Simplified goal execution (methodology v7) | standing; pilot clause amended by D30 |
| [D30](#d30--methodology-v71-context-roles-and-planning-documents-s-2) | 2026-10-09 | Methodology v7.1: context, roles and planning documents (S-2) | standing |

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
stays recoverable, but the net diff cancels the two out. The net-diff version was written first and
verifiably missed exactly that case in testing.

---

## D4 — Merge commits, never squash

**Chose:** `gh pr merge --merge`, plus a milestone tag.

**Over:** squash (one clean commit per milestone) or rebase.

**Why:** with no CI, the commit history is the only audit trail. Squashing discards the per-commit
record, and a rebase rewrites the SHAs that tags and notes point at. The milestone tag is also what
the goal tools use to find a milestone's tree.

---

## D5 — History is link-checked but never crawled

**Chose:** exclude `docs/archive/`, `docs/superpowers/`, `docs/eval-reports/` from the disclosure
crawl while still validating links *into* them.

**Over:** crawling everything reachable.

**Why:** a plan written months ago should cite files that have since moved; that is what makes it
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

**Why:** two hand-maintained formats drift the first time anyone forgets, and silently, because a
harness quietly runs an older persona. Project-level agents also override a same-named user agent
wholesale, so "base persona plus project direction" cannot be expressed by file placement. A
project therefore adds whole personas under their own names and does not overlay a base persona.

---

## D8 — Judges cannot edit, structurally

**Chose:** an allow-list of read-only tools on Claude and `sandbox_mode = read-only` on Codex for
every judging persona, enforced by the renderer, which refuses a judging source that declares more.

**Over:** instructing them not to edit.

**Why:** "a builder never approves their own work" is only a guarantee if enforced. It also removes
the failure where a reviewer quietly patches the defect it found, so the defect is never recorded.
Because the renderer fixes the set of judging personas, a persona cannot leave it by editing its
own file.

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

## D17 — This repository complies with the standard it ships

**Chose:** keep `docs/{agents,architecture,product,decisions,runbooks,archive}/`, each with a
`README.md` naming its purpose and authority, and run `validate_disclosure.py --standard` against
this repository from `install/verify.sh`.

**Over:** a documentation/tooling taxonomy of this repository's own, justified by "empty
application tiers would imply false authorities" and by the default route check being
authoritative; and over amending the standard so a tool repository needs fewer directories.

**Why:** the second premise of the own-taxonomy option was false, measured. The default route check
does not evaluate the standard at all; it prints `NOT RUN cross-project structure standard: not
requested`. Pointed at the standard, the same script reported seven errors and exit 1. The first
premise is true only of empty tiers, and every directory here holds real documents. Amending the
standard was rejected because its own words are "One layout for every project", and a tool
repository exempting itself from the layout it asks every other repository to adopt hides the
failure the exemption would cause.

**Consequence:** each move spends one route hop, and the validator warns `too-deep` past two, so
`docs/README.md` links every document directly as well as linking the six area indexes.

---

## D18 — The decisions record stays one file inside `docs/decisions/`

**Chose:** `docs/decisions/decisions.md`, with a short `README.md` beside it stating purpose and
authority.

**Over:** `docs/decisions/README.md` holding the record, and one file per decision.

**Why:** the word-budget exemption for an accreting record is keyed on the basename.
`validate_disclosure.py` matches
`^(measurements|benchmarks|decisions|adr|rulings|improvements|changelog|history)(?:[-_][a-z0-9]+)?\.md$`
against the file name, so `decisions.md` is exempt and `README.md` is not. A rename would have put a
file at 1,185 words under the 1,200-word guide budget. One file per decision would escape the budget
by sharding, which the validator's own source comment calls gaming the metric rather than answering
it, and it would break every `decisions.md#dNN` anchor, such as the one in `AGENTS.md`.

The budget check also narrows to entry files and `docs/agents/` once `docs/agents/README.md` exists,
so nothing under `docs/decisions/` is budgeted whatever it is called. That protection depends on
where the route index sits, so the rule is chosen over it deliberately.

---

## D19 — No compression proxy in this repository

**Chose:** reject `caveman` and `headroom` as in-repo dependencies; cut token cost by capping what
agents write and by pruning unused MCP servers on the workstation.

**Over:** wrapping the agent in a compression proxy.

**Why:** three independent reasons, any one sufficient.
- **Licence and stack.** caveman's engine is BSL-1.1 with Go binaries and a Node installer;
  headroom is a proxy plus a HuggingFace model and a torch tree. Neither enters a
  standard-library-Python public repository whose scripts write nothing.
- **Workload.** caveman's 33.2% is honestly measured, but its own `HONEST-NUMBERS.md` records a
  fixed per-turn overhead and a net loss on terse coding question-and-answer, which is this loop.
  Its paired arm put headroom at 6.7% with a confidence interval crossing zero.
- **Evidence.** headroom's accuracy table is GSM8K and SQuAD at n=100, with no agentic coding
  quality evidence.

**Also found:** the waste was structural, not linguistic. Judge output was uncapped, so verdicts ran
7.4 times the bytes of the cards they answered, and deleting 56 banned diff snapshots halved a
workspace's bytes with no finding lost, because git regenerates a diff from a commit range. A proxy
saving a third of a bill that should not be paid is worse than not paying it.

**Left to the workstation:** the harness prefix every subagent re-sends measures roughly 24,000
tokens of tool schema per call. Pruning unused MCP servers costs no lines and no quality.

**Known-wrong if:** a milestone stalls on a removed tool, or a verdict cap makes a judge drop a
finding rather than cut prose.

---

## D29 — Simplified goal execution (methodology v7): one look per artifact, a mechanical gate, two touchpoints

**Chose:** one `plan.md` per goal; `gate.py` receipts bound to the tree; an eight-row mechanical
`goal.py done` that reads no verdict, round, lock or grant; one adversarial review by the other
vendor (a read-only reviewer: Codex when Claude is the chief, Claude when Codex is) at design, at plan
and at merge, each a single round with no grant, where a blocking finding is closed by a named test
or by removing the work, or resolved in the document before the approval tag; a design page exists
only when a goal touches data, auth or an external interface; two founder touchpoints per milestone, the approval tag and the merge, with an
explicit list of what parks for the founder. One instruction source for both harnesses under a
1,350-word ceiling. The review loop (`review.py`), the driver, the persona generator, the
SessionStart report hooks, the route and GitHub checkers, graph context and the two 3,785-line
guards are removed; one guard of about 150 lines replaces the two after matching their fixtures.

**Over:** v6 as shipped (F-3) with its follow-ups F-4 (review-closure confirmation) and F-5 (graph
context), which are archived under `archive/v6-followups-2026-10-09` and never merged.

**Why:** measured on this repository and six product repositories (2026-10-09, two councils, two
adversarial passes). Founder decisions ran 10–13 per milestone against v6's contract of 2; all 29
rounds past the cap were granted; `install/` carried 5.7 lines of process-policing code per line of
done-check. Real-defect catches by round: this repository's diff reviews 20 at round one, 2 after;
150 sampled product findings 64, 9, 8. Every loop of five or more rounds was on a document and every
best-delivery week had task-sized commits, one round-one review and same-day merges. The guards had
no real catch in seven repositories. Vendor guidance for the current models says the same: short
instructions, done on evidence, one fresh-context reviewer, no verification scaffolding.

**Supersedes:** D7 (personas are hand-written agent files now), the loop half of D8 (judges stay
read-only; there is no round machinery to protect), D11 and D12 (graph and session-start reporting
are removed). D2–D4, D17 and D18 stand.

**Measured by:** a pilot on one product repository, migrated by the founder after S-1 M2, with a
first review after one week and the stop rule applied over four (a blocking escape in two
milestones, merges per week below baseline without external cause, founder decisions above four per
milestone twice, or more than one default in five reversed). Rollback is the tag
`methodology/v6-base` reinstalled.

**Known-wrong if:** the pilot's sampled follow-up reviews find a blocking escape that a second round
would demonstrably have caught, or product-repository merges per week fall below the best measured
periods under the new shape.

## D30 — Methodology v7.1: context, roles and planning documents (S-2)

**Chose:** a bounded document set per goal — `spec.md` (≤400 words, acceptance criteria as
observable behaviour, frozen whole at approval), `design.md` when `touches:` names data, auth,
external, interface or ui (its Interfaces and Data touched sections frozen), `plan.md` with a
`reads:` line per task — citing exhaustive repository documents (`docs/product/prd.md`,
`docs/product/features/*.md`, `docs/architecture/*.md`) by section. Exhaustive documents are
unbounded but addressable: frontmatter `summary` (≤120 words), `read-when`, `covers` and
`last-verified`; a generated index; anchors resolved to line ranges; pointer files for both
harnesses generated from `covers` and never hand-written; stale pages listed mechanically. Roles
declare their model and effort in agent files shipped to both harnesses: builders on the frontier
tier at high effort, scouts on the cheap tier, the reviewer the other vendor's strongest reasoning
model. Cost is recorded per session and never enforced; the caps stay structural. A goal runs in the founder's own console session, which is the chief: no launcher, no loop, no
Stop hook. Acceptance
criteria are traced to task sections by lint; `goal.py packet --approval` renders the approval page.

**Over:** restating product context in every Outcome; agent memory scopes, a graph or wiki; a
model-judged done; a second reviewer; a per-milestone dollar budget; hand-written pointer files;
mid-tier builders with the reviewer as backstop.

**Why:** after S-1 the three measured gaps were thin context delivery (packets with no reading
list), undeclared roles and models, and no planning layer above the Outcome. Vendor guidance
(context engineering: identifiers over pasted text, cheap tiers for reading, specs before
implementation; harness engineering: `AGENTS.md` as a table of contents with the knowledge in
`docs/`, garbage-collected) and the spec-driven tools (constitution, spec, plan, tasks; EARS
criteria) converge on this shape. The v6 lessons wiki and graph had no measured catch, so nothing
heavier is adopted. Founder decisions of 2026-10-09: no dollar budget; pointers generated from the
start; frontier builders; S-2's second milestone runs during the pilot.

**Amends:** D29's stop rule clause "no new mechanism enters `install/` during the pilot" admits
goal S-2; the four reverting conditions stand unchanged. D29 otherwise stands.

**Measured by:** the pilot's first milestones under v7.1: `cause:` tags on closed blocking
findings (whether context is the cause before any heavier mechanism is argued for), founder
decisions per milestone, review catches by stage, and the recorded cost per session.

**Known-wrong if:** `cause: context` stays above half of blocking findings after `reads:` lines
and generated pointers are in use, or the document set raises founder decisions per milestone above
the D29 contract.
