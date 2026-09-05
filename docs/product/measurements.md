# Measurements

Current model and verification evidence updated 2026-09-05. Older measurements retain their own
dates and describe the system that existed then. Re-derive current prices and model comparisons
when vendor terms or locally observed results move.

## Current model economics and pilot status — 2026-09-05

Standard API prices per million tokens:

| Model | Uncached input | Cached input | Output |
|---|---:|---:|---:|
| GPT-6 Astra | $10 | $1 | $50 |
| GPT-5.6 Sol | $4 | $0.40 | $20 |
| GPT-5.6 Terra | $2 | $0.20 | $12 |
| GPT-5.6 Luna | $0.20 | $0.02 | $1.20 |
| GPT-5.4 mini | $0.75 | $0.075 | $4.50 |
| Claude Fable 5.1 | $10 | $0.25 | $50 |
| Claude Opus 5 | $5 | $0.50 | $25 |
| Claude Sonnet 5 | $2 | $0.20 | $10 |
| Claude Haiku 4.5 | $1 | $0.10 | $5 |

OpenAI rows use short-context Standard rates; prompts over 272K tokens have different prices.
Cache creation, optional service tiers and subscription allowances are separate. Sol's promotional
price is documented through at least 2026-11-21. Sources: [OpenAI pricing](https://developers.openai.com/api/docs/pricing),
[Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing).

The selective persona assignments are an **unmeasured pilot**, not a model ranking. No matched
Astra/Fable task comparison has run on this workload. Fable 5.1 requires Claude Code 2.1.255 or
newer before local evaluation; unsupported environments remain unmeasured. Native per-dispatch
effort overrides may be used only where the harness exposes them, with the resolved model and
effort recorded. Acceptance remains at `xhigh`. No persona defaults to `max` or `ultra`.

Illustrative arithmetic, not observed workload cost: 40K uncached input plus 8K output is $0.80
on Astra and $0.32 on Sol. At that mix, Astra costs 2.5 times as much and must earn the difference
through better outcomes, fewer tokens, less rework or saved founder time. A call with 200K cached
input and 2K output is $0.15 on either Fable 5.1 or Opus 5, excluding cache creation.

Subscription economics need their own evidence. Record accepted tasks per weekly allowance and
quota delay rather than projecting subscription value from API prices. Sources: [Claude plan guidance](https://support.claude.com/en/articles/15424964-claude-fable-models-on-your-plan),
[Codex usage and pricing](https://learn.chatgpt.com/docs/pricing).

## Historical cross-harness review experiment — 2026-07-26

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

## Historical per-milestone cost model — 2026-07-26

This historical estimate was derived from the two measured anchors ($0.212 in-harness review) and the run counts in
[../agent-personas.md](../agents/agent-personas.md). Implementation assumed at ~40K in / 8K out per run.

| Line | Before the tier split | After |
|---|---|---|
| Implementation, ~20 runs | 20 × opus ≈ $8.00 | 14 × sonnet ($0.16) + 6 × opus ($0.40) ≈ **$4.64** |
| Review, ~20 runs | ~$4.24 | ~$4.24 |
| `architect`, ~4 runs | — | ~$1.20 |

The tier split takes ~40% off the largest write-side line. Cross-harness review on all 20 reviews
would have added ~$3/milestone.

These estimates use the July roster and July prices. They remain as decision history and must not
be used as current pilot economics.

## What the current process counters actually measure

`ratio_meter.py` classifies **committed line churn** by repository path. Its 15% warning, 30%
failure threshold and 500-line floor are policy thresholds; they do not measure reasoning tokens,
elapsed time, founder attention, ignored workspace work, test adequacy or accepted outcomes.

`check_review_budget.py` reports **workspace files and bytes** for the artifact classes it checks.
It does not report workspace process lines. Receipts must keep these units separate instead of
combining them into a single process ratio.

### Bounded Codex reasoning smoke test — 2026-09-05

Twelve frozen public-toolchain cases were answered in the active Codex harness with identical
supplied inputs. An independent read-only reviewer scored blinded outputs.

| Requested model and effort | Semantic outcomes | Raw decision labels |
|---|---:|---:|
| GPT-5.6 Sol, high | 12/12 | 12/12 |
| GPT-6 Astra, medium | 12/12 | 11/12 |
| GPT-6 Astra, high | 12/12 | 11/12 |

One case was ambiguous about whether the judged object was a help-string change or a review that
invented requirements. All three candidates rejected the invented blocker; the two raw label
mismatches remain recorded. The test did not separate the candidates on semantic quality.

These were evaluation workers, not generated production personas. The test did not exercise an
implementation workflow, full permission resolution, long-context control, velocity, token or
subscription efficiency, or rare defects. Runtime token, cache and cost telemetry were unavailable,
and parallel receipt times are not comparable model latencies. Fable 5.1 was not run. Real-task
outcomes and usage remain prerequisites to any model ranking or broader adoption.

The pre-revision 2026-09-05 assessment observed a repository verdict of PASS with skipped checks
and a machine verdict of FAIL. Focused reruns attributed failures to sandbox execution being denied
and fixtures attempting machine-global mirror writes outside the assessment boundary. That is a
baseline limitation, not final evidence for this revision. Final suite counts belong here only
after the integrated candidate is run.

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

## Product-definition and planning checks (methodology v4.2)

Measured 2026-08-21 on this workstation, against a repository holding 204 documents under
`docs/product/`.

| check | median | range |
|---|---|---|
| `spec_check.py` whole tree | 107 ms | 105–139 |
| `plan_waves.py` whole tree | 41 ms | 38–47 |
| pre-push guard, product half | +154 ms | — |
| `trace_check.py`, receipt-scoped | 40 ms | — |

The guard runs both over the whole tree rather than the pushed range: at a tenth of the 1.5 s
threshold, range-scoping saves nothing a human feels and would let a spec broken by an edit outside
`docs/product/` push clean.

`trace_check.py` reads only the results directory a receipt names. A full pass over that
repository's 51,604 XML files and 267,943 testcases through the same parser takes 5.5 s, which is
the cost the receipt scope avoids on every run. `--commit RANGE` keeps that bound: measured against
a real repository over a commit renaming 400 test methods across 64 files, the whole run took
96 ms, because the diff is read once and only the files a carrier appears in are read back.

Wave scheduling, measured on a real 51-task graph: 8 waves from the dependency edges alone, and 37
task pairs inside those waves declaring overlapping write sets. Across a 5-feature milestone the
per-plan view reported zero findings while six cross-feature pairs collided. Glob overlap is decided
without touching the filesystem; a differential check over 14,706 random pattern pairs missed no
real overlap and reported 26% without a witness at four segments deep.

## T7, the coverage-by-rename check — corpus note

No checker here merges without the repositories it was run against, the denominator, the hit count
and a hand audit of every hit. Six checkers in one week passed their own fixtures and were inert or
wrong against real work; each would have been caught by this note.

**Repositories scanned:** four sibling product repositories, three of them Java/JUnit and one
Python. **Adoption of the carrier T3 depends on: 1,073 Java test files, 5,866 `@Test` methods, 0
carrying a criterion id.** T3 is unarmed everywhere today, so a bulk rename is the cheapest possible
green and T7 is the check that has to hold.

**False positives — does T7 fire on honest work?** Over the last 60 test-touching commits of each
Java repository, every test method in every touched file was classified independently by comparing
its pre- and post-image body text, and that classification was compared to T7's verdict.

| repository | methods T7 judged | T7 fired | disagreements |
|---|---|---|---|
| A | 580 | 0 | 0 |
| B | 303 | 0 | 0 |
| C | 473 | 1 | 1 |
| total | **1,356** | 1 | **1 (0.07%)** |

The one hit was hand-audited: `void unrelatedGreenProbe() {}`, a deliberately empty bait test added
in that commit. It has no body, so no body line changed, and T7 firing on it is the rule working —
`void ac2() {}` is the exact case this toolchain has always said T3 cannot see. **The audited
false-positive rate is 0 of 1,356.** A further 2,201 methods whose bodies the range did not change
produced no finding at all.

**False negatives — does T7 catch the attack it exists for?** 400 real `@Test` methods in a clone of
a Java repository and 400 real `test_*` functions in a clone of the Python one were renamed to carry
`__F1_AC1` and committed, changing nothing else. **T7 fired on 800 of 800**, and the Python half
fired under the same rule, with no language-specific code.

Two earlier revisions were measured and rejected rather than tuned. Triggering on "the name appears
on an added line" fired on 18 of 494 methods (3.6%) in one repository, because its pinned-defect
registry names test methods in string literals; deciding arrival against the left side of the range
removed all 18. Ignoring deleted lines misread a commit that moved a test's assertions elsewhere as
a rename. Both fixes were made against the CLASS of accident, not against the file that broke.

**What T7 still cannot see:** a rename that landed outside the range; an honest rename, which looks
identical to a coverage-farming one; and whether the changed body asserts anything at all. The last
of those was deliberately left alone — the assertion-token idea flags 0.55% of 5,866 Java test
methods but 4.30% of 32,141 Python test functions in 1,537 files, and shipping one regex across that
gap is the same "matched a WORD not a STRUCTURE" failure this file already records three times.

## Adoption cost of the product-definition layer, measured on four repositories

Measured 2026-08-21 by running the shipped checkers against four private repositories that had not
adopted the layer, and by transcribing one repository's specs into the bound layout to price the
migration rather than estimate it.

| repository | product docs | findings | specs the checker could not read |
|---|---|---|---|
| A | 204 | 1 | 0 |
| B | 24 | 22 | 1 |
| C | — | 21 | 0 |
| D | 236 | 0 | **233** |

Repository D is the important row and it was misread three times before the count existed. It
reports zero findings because it names every feature spec `specs/<slug>/spec.md` while the schema
rules bind `docs/product/specs/F-*.md`. Nothing was wrong with it and nothing had been checked.
A checker that inspects none of a repository's specs and exits 0 is indistinguishable from one that
inspected them all, which is why the unread count is now printed on every run.

**The migration was priced, not guessed.** Transcribing repository D's 64 nested specs into the
bound layout — a rename, with no content edited — produces 40 findings, all of ONE class: the
absence of a `---` block. Adding minimal front matter clears all 40 and leaves only a parent-link
finding, because that repository names its top-level product document something other than
`prd.md`. So the cost is one mechanical pass over 64 files, not 40 distinct defects.

That result generalises to the fleet: across all four repositories 27 feature specs exist and NONE
carries front matter. The front-matter contract is the single largest adoption cost in the layer,
and it is mechanical.

Repository B's 22 findings are the same class. Repository C's 21 are a backlog accumulating dated
sections, which is the drift the current-state rule exists to name.
