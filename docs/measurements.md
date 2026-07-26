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

Identical task: a 34-line Java class with two planted authorization bugs — a caller-supplied
`familyId` trusted without checking, and a `get()` with no authorization at all.

| Run | Uncached in | Cached in | Out | Shell | Wall | Cost | Findings |
|---|---|---|---|---|---|---|---|
| 1 `codex exec` naive | 31,522 | 76,032 | 1,218 | 6 | 42s | $0.232 | 2, ungrounded |
| 2 `codex exec` no repo access | 23,746 | 0 | 237 | 0 | 15s | $0.126 | 2, shallow |
| 3 `codex exec` matched (repo + scoped prompt) | 48,611 | 138,240 | 1,827 | 4 | 66s | **$0.367** | 5, grounded |
| 4 Claude subagent, `opus`, in-harness | 27,232 | 0 | ~3,025 | 7 | 80s | **$0.212** | 5, grounded |

**Only rows 3 and 4 are comparable.** Rows 1–2 were not quality-matched; row 2 had no repo access at
all, which is why it found less.

Findings:

- **~23K input tokens is the floor** for any `codex exec` call — the Codex base system prompt, paid
  before your content.
- **A naive call costs 84% more than a disciplined one.** Run 1 burned 76K re-reading `AGENTS.md`
  and both graphify `SKILL.md` files, then ran 6 shell commands rediscovering context the parent
  already had.
- **At matched quality, cross-harness costs ~1.7×.** 186K input against 30K, because a cold
  subprocess shares nothing. Caching absorbed 138K at 10% rate; uncached, run 3 would be ~$0.98.
- **The families found different defect classes.** Both caught the planted bugs. Codex/Sol
  additionally caught that `ConsentLedger.hasActiveConsent()` **does not exist** — an API-existence
  error the Claude subagent reasoned right past while proposing a fix built on it.

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
