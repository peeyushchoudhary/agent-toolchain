# Decisions

The non-obvious calls that are in force, and what each was weighed against. A decision recorded
without its alternative is just an assertion. Identifiers are stable, so a gap in the numbering
marks a decision that no longer applies; git holds it. The execution design owns the choices about
how goals run, in [lean-execution.md](../architecture/lean-execution.md).

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

## D28 — Review closure ends in fixes, not in grants

**Chose:** correction packets carry a Keep list; a first finding in an open input space and a
repeat marked `family:` are both corrected at the class; and one test-closed rereview per subject
(`review.py --closed-by`) does not count toward the cap.

**Over:** raising the cap to 3, letting an advisor grant rounds, running each test against the
pre-fix tree, and rating findings by likelihood or impact.

**Why:** F-3 took ten founder decisions that admitted 13 rounds past the cap. Six of its 12
blocking rounds found a further instance of a family already found, and one removed an earlier fix
(the M4 regression). Each alternative fails on its own terms.
- **Cap 3** spends the round on any correction, not only a test-proven one.
- **Advisor grants** are how earlier loops stopped ending; the founder keeps the grant.
- **Pre-fix test execution** needs a checkout and a runner per language; the judge reads the test
  against the finding instead.
- **Impact rating** would queue a rare but real correctness defect; class correction removes most of
  the cost, and the founder declined it.

**Known-wrong if:** a subject still reaches the cap on one family, or a confirmation admits a test
that does not reproduce its finding.

Numbers: [F-3 review rounds](../product/measurements.md#f-3-review-rounds--2026-10-08).
