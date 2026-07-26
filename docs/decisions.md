# Decisions

The non-obvious calls, and what they were weighed against. A decision recorded without its
alternative is just an assertion.

Numbers cited here are in [evidence/measurements.md](measurements.md).

---

## D1 — The README is a fourth disclosure layer, not part of the agent route

**Chose:** a separate seven-section contract for `README.md`, gated structurally.

**Over:** folding it into `docs/agents/`, or leaving it ungated.

**Why:** `AGENTS.md` routes an agent; `README.md` answers a human deciding whether the project is
real. Different reader, different failure mode. A validator can prove sections exist; only a person
can say whether the prose is still true — so structure is gated by `make check-docs` and honesty by
a PR-template checkbox.

**Rejected explicitly:** inlining low-level design per component into the README. Seven components
at design depth would have tripled it into something nobody updates, and a confidently-wrong front
page is worse than a thin one. Design lives in `docs/architecture/<component>.md`.

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
and verifiably missed exactly that case in testing.** This is the one decision here that was caught
by a test rather than by reasoning.

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
history. Crawling it produced 117 stale-path warnings that were all correct-by-the-letter and
useless, burying the one real breakage. The project's own authority order already says these are
rationale, never behaviour; the validator now matches.

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

**Why:** two formats hand-maintained drift the first time anyone forgets, and the failure is silent
— Codex quietly runs an older persona. More fundamentally, Claude Code's project-level agents
**override** a same-named user agent wholesale, so "base persona plus project direction" *cannot* be
expressed by file placement. Merging has to happen before the harness sees it.

---

## D8 — Judges cannot edit, structurally

**Chose:** `disallowedTools` on Claude and `sandbox_mode = read-only` on Codex for every judging
persona.

**Over:** instructing them not to edit.

**Why:** "a builder never approves its own work" is only a guarantee if it is enforced. It also
removes the failure where a reviewer finds a defect and quietly patches it, so the defect is never
recorded.

**Accepted exception:** `architect` may write, so it can author ADRs. Tool restriction cannot be
scoped to a path, so its "design docs only" limit is an instruction. This is the single soft
boundary in the roster and is documented as such wherever it appears.

---

## D9 — Cross-harness dispatch rejected

**Chose:** every persona runs in the harness being driven.

**Over:** Claude implements → Codex reviews, and the reverse.

**Why:** measured at **$0.367 against $0.212** for a quality-matched review — about 1.7×. A cold
subprocess shares no context with the parent, so it re-reads source the parent already holds (186K
input against 30K), on top of a **~23K-token system-prompt floor** charged every invocation.

**What was given up:** a real benefit. The other family independently caught that a method the first
reviewer's fix depended on **did not exist** — an API-existence check rather than logic reasoning.
Worth revisiting if the floor drops or context can be shared.

**Note on an earlier wrong conclusion:** the first comparison showed cross-harness as *cheaper*. It
compared a reviewer with no repo access against one with full access — 2 findings against 5. Not
apples to apples. The controlled re-run reversed it.

---

## D10 — Implementation split into two tiers

**Chose:** `developer` (sonnet/terra) and `senior-developer` (opus/sol).

**Over:** one `implementer` at opus with "escalate per dispatch".

**Why:** the escalation judgement was made silently, every time, and recorded nowhere. Two named
personas make the tier explicit and auditable, and route the ~70% of genuinely bounded work off the
expensive model — roughly **$8.00 → $4.64** per milestone.

**The condition that makes it safe:** `developer` is instructed to stop and escalate rather than
infer anything about interfaces, migrations, contracts, security, concurrency, or placement. A cheap
tier that improvises is not a saving.

**`senior-developer` is Opus at medium, not high.** Opus at medium is already strong and the tier
difference is carried by the model; raising both would double-charge for one increment of
difficulty.

---

## D11 — Only the graph's learnings are committed, not the graph

**Chose:** commit `graphify-out/reflections/` and `graphify-out/memory/` (~36 KB); keep the 22 MB
graph and 65 MB cache ignored.

**Over:** committing all of `graphify-out/` (168 MB), or none of it.

**Why:** the graph is rewritten wholesale on every rebuild, so committing it adds a fresh 22 MB blob
to history each time for something `make graph-build` regenerates in minutes. The query lessons do
**not** regenerate — they accumulate from real use, and every harness can read them.

Required changing the ignore pattern from `graphify-out/` to `graphify-out/*` with negations: git
cannot re-include a path underneath an excluded *directory*.

---

## D12 — Report, never scaffold, at session start

**Chose:** session hooks that describe problems and name the fix command.

**Over:** hooks that create the missing files.

**Why:** they fire in every directory a session starts in, including repositories that are not yours
and scratch clones. Creating files there would put unexplained untracked files in someone's tree.
The hook tells; the human decides.
