# Measurements

Measured 2026-07-26 on this workstation. Re-derive when prices or benchmarks move — several
decisions in [../decisions.md](decisions.md) depend on these numbers, not on intuition.

## Prices and benchmarks

| Model | $/M in | $/M out | Score |
|---|---|---|---|
| Haiku 4.5 | 1 | 5 | — |
| Sonnet 5 | 2 (intro, →3 Sep 2026) | 10 (→15) | 63.2 SWE-bench Pro |
| Opus 5 | 5 | 25 | 79.2 SWE-bench Pro, 96.0 Verified |
| Fable 5 | 10 | 50 | 80.0 SWE-bench Pro |
| GPT-5.6 Luna | 1 | 6 | 82.5 coding index |
| GPT-5.6 Terra | 2.50 | 15 | 84.3 coding index |
| GPT-5.6 Sol | 5 | 30 | 88.8 coding index, 64.6 SWE-bench Pro |

**The Anthropic and OpenAI numbers come from different suites.** Compare within a vendor only.
Nothing in the routing ranks Opus against Sol.

Two vendor claims that shaped decisions:

- Anthropic's cost-per-task data: **above medium effort, Opus delivers more accuracy per dollar than
  Sonnet.** This is why `senior-developer` is Opus.
- OpenAI ships Sol at default reasoning `low`, advising to start low and turn up. Effort defaults
  were lowered across the roster partly on this.

Opus 5 released 2026-07-24 at unchanged Opus pricing. Against Opus 4.8 (69.2 SWE-bench Pro) the gap
over Sonnet 5 widened from 6 points to **16** — which is what settled the implementer question.

## Cross-harness review experiment

One task: a 34-line Java class with two planted authorization bugs — `familyId` trusted
unchecked, and a `get()` with no authorization.

| Run | Uncached in | Cached in | Out | Shell | Wall | Cost | Findings |
|---|---|---|---|---|---|---|---|
| 1 `codex exec` naive | 31,522 | 76,032 | 1,218 | 6 | 42s | $0.232 | 2, ungrounded |
| 2 `codex exec` no repo access | 23,746 | 0 | 237 | 0 | 15s | $0.126 | 2, shallow |
| 3 `codex exec` matched (repo + scoped prompt) | 48,611 | 138,240 | 1,827 | 4 | 66s | **$0.367** | 5, grounded |
| 4 Claude subagent, `opus`, in-harness | 27,232 | 0 | ~3,025 | 7 | 80s | **$0.212** | 5, grounded |

**Only rows 3–4 are comparable**; rows 1–2 were not quality-matched.

- **~23K input tokens is the floor** for any `codex exec` call — the Codex base system prompt.
- **A naive call costs 84% more.** Run 1 burned 76K re-reading `AGENTS.md` and two `SKILL.md`
  files, then 6 shell commands rediscovering context the parent already had.
- **At matched quality, cross-harness costs ~1.7×.** 186K input against 30K — a cold subprocess
  shares nothing. Caching absorbed 138K at 10% rate; uncached, run 3 would be ~$0.98.
- **The families found different defect classes.** Both caught the planted bugs; Codex/Sol also
  caught that `ConsentLedger.hasActiveConsent()` **does not exist** — an API-existence error the
  Claude subagent reasoned right past.

## Per-milestone cost model

Derived from the two measured anchors ($0.212 in-harness review) and the run counts in
[../agent-personas.md](agent-personas.md). Implementation assumed at ~40K in / 8K out per run.

| Line | Before the tier split | After |
|---|---|---|
| Implementation, ~20 runs | 20 × opus ≈ $8.00 | 14 × sonnet ($0.16) + 6 × opus ($0.40) ≈ **$4.64** |
| Review, ~20 runs | ~$4.24 | ~$4.24 |
| `architect`, ~4 runs | — | ~$1.20 |

The tier split takes ~40% off the largest write-side line. Cross-harness review on all 20 reviews
would have added ~$3/milestone.

## Graph rebuild

Extraction is always incremental and cache-backed; clustering is always recomputed in full.

```
1st deep build: 1141 cached/unchanged,  624 re-extracted, 632 deleted →  55 files to the LLM
2nd deep build: 1762 cached/unchanged,    4 re-extracted, 630 deleted →   4 files to the LLM
after docs work: 1758 cached/unchanged,  17 re-extracted, 630 deleted →  16 files to the LLM
```

Final graph: 12,528 nodes, 47,571 edges, 518 communities, 22 MB. Cache index: 1,834 entries.

The four entry points differ: `post-commit` is scoped to `git diff HEAD~1 HEAD`; `post-checkout` and
`make graph-update` do a full tree scan with incremental extraction; `make graph-build` adds the
semantic LLM pass on changed files only. Approximately 3 minutes for a warm semantic rebuild.

## Session-start hook latency

0.22s with the GitHub cache warm, in a repo with a full route and a graph. The remote half is one
`gh` call cached for 24h; hook mode drops the timeout to 6s so a slow network never holds a session
open.

## Process overhead under methodology v1.4–v2.1

Measured 2026-08-10 over 2026-07-27 → 2026-08-10, three private repositories, every commit and
working-tree artifact classified as product (production code and tests) or process (specs, plans,
cards, review reports, ledgers, receipts, workspaces). These numbers are why v3.0 exists;
identities withheld by this repository's boundary rules.

| Metric | Repo A | Repo B | Repo C |
|---|---|---|---|
| Process:product line ratio, governed period | 10.9:1 | 15.5:1 | 2.5:1 (6:1 active stage) |
| Max review rounds on one subject (cap: 2) | 15 | 8, plus a 6th milestone attempt | 18 |
| Merges shipping zero product code | 0 merges in the final 5 days | 12 of 14 merged in <90s | 6 of 11 |
| Longest zero-commit stall, active milestone | 4 days | 4 days (card deadlock, 5 to clear) | 24h+, 327 artifacts, 0 commits |
| Largest waste class | 135 review reports in 4 days vs 1 commit | 144 `.diff` snapshots, 10.3 MB | 37 `.diff` snapshots, 68,447 lines — 4.8× stage product |

Control, same fortnight, lighter pre-v1.4 process: 10 PRs merged in 3 days at 1:2.6
process:product in one repository; plan-to-merge under a day in another. The
contrast between those rows is the v3.0 evidence base.

Validating v3.0's script against the worst workspace (327 files, 5.6 MB): `check_review_budget.py`
reported 6 subjects past the cap, 90 banned artifacts, the budget warning, exit 1 — one process
invocation, no LLM involved.

## Process overhead under methodology v3.0

Measured 2026-08-20 over the preceding eight days, four private repositories, classified as above,
session transcripts as an effort proxy.

| Shape | Commits | Prod:proc ins. | Sessions / MB | Merges to main |
|---|---|---|---|---|
| Warm controller, wave PRs, same-day gates | 46 | 42.7K:24.2K | few / 3.9 | 7 PRs, 7 tags |
| Warm controller, heavy narration | 151 | 22.9K:37.3K | 2 / 82 | 1 PR |
| Cold per-dispatch sessions | 5 | 8.7K:0.7K | 150 / 359 | 2 PRs, then frozen 6 d |
| Cold per-dispatch sessions | 34 (all refs) | 15.6K:22.8K | 438 / 419 | 0; main stale 10 d |

The round cap held: no post-adoption subject exceeded two rounds. Exposed instead: capped reviews
escalated to a human gate that did not drain (two briefs unanswered six days); one ledger grew
12,220 lines in a week, 94 of 150 commits carrying no product; 588 cold sessions (~133 KB boot
each) landed 9 commits beside two warm sessions landing 151. Hence v3.1: apply-and-close, default actions,
five-line distillations, long-lived controller.
