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
`project-conformance` asks whether it still conforms, and is **read-only**. Onboarding's verify step
calls it.

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
