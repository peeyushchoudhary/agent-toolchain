# Measurements

The numbers that the decisions in [decisions.md](../decisions/decisions.md) and the
[v6 design](../architecture/lean-execution.md) cite, each with its date and source. A number older
than its date describes the system that existed then; re-derive prices and model comparisons when
vendor terms or local results move.

## Methodology v5.1 baseline — 2026-10-06

Taken on this repository at HEAD `3bd256d` and in sampled run workspaces of private projects, whose
identities this repository's boundary rules withhold. These are the figures behind the v6 design and
[F-3 spec](specs/F-3-lean-execution.md).

| Measure | Value |
|---|---|
| Instruction and script load | about 47,500 words of prose, 25,500 lines of scripts, 46,000 lines of tests |
| Chief's load before reading any task | about 15,800 words |
| A six-task milestone | 70–90 agent steps, 30+ fresh model contexts, 4–7 founder transactions |
| Task reviews blocking in the first round | 11 of 13; 6 of 6 acceptances passed |
| Review yield | 0.74 blockers per design artifact; 0.09 per implementation artifact |
| Out-of-scope edits | 116 of 558 files historically |
| Task card machinery | 2,256 lines for 18 keys |
| Review-budget checker | 1,630 lines to count to two |
| Controller share of spend, one three-week project | 68% (a root session above a chief subagent) |
| Tool calls that were coordination polling | 31% |
| Builders on the expensive tier | 99% |
| Test-judge failures sampled | every one environmental or pre-existing |

## Criterion-id carriers — August 2026

Across four sibling product repositories, three Java/JUnit and one Python, 1,073 Java test files
held 5,866 `@Test` methods and none carried a criterion id. The criterion-trace checker was inert,
which is why v6 binds criteria to proof commands in the plan instead.

## Cross-harness review experiment — 2026-07-26

One task: a 34-line Java class with two planted authorization bugs, `familyId` trusted unchecked and
a `get()` with no authorization. Costs are at July prices.

| Run | Uncached in | Cached in | Out | Shell | Wall | Cost | Findings |
|---|---|---|---|---|---|---|---|
| 1 `codex exec` naive | 31,522 | 76,032 | 1,218 | 6 | 42s | $0.232 | 2, ungrounded |
| 2 `codex exec` no repo access | 23,746 | 0 | 237 | 0 | 15s | $0.126 | 2, shallow |
| 3 `codex exec` matched (repo + scoped prompt) | 48,611 | 138,240 | 1,827 | 4 | 66s | $0.367 | 5, grounded |
| 4 Claude subagent, `opus`, in-harness | 27,232 | 0 | ~3,025 | 7 | 80s | $0.212 | 5, grounded |

Only rows 3 and 4 are comparable; rows 1 and 2 were not quality-matched.

- About 23K input tokens is the floor for any `codex exec` call, the Codex base system prompt.
- A naive call costs 84% more: run 1 spent 76K re-reading `AGENTS.md` and two `SKILL.md` files, then
  six shell commands rediscovering context the parent already had.
- At matched quality a cold cross-harness call cost about 1.7×, with 186K input against 30K.
- The two families found different defect classes. Both caught the planted bugs; Codex also found
  that `ConsentLedger.hasActiveConsent()` does not exist, an API-existence error the Claude subagent
  reasoned past.

The design re-prices this experiment at the rates below and puts a one-shot cross-vendor review at
about 0.77× the in-harness cost.

## Model prices for that re-pricing — 2026-09-23

Standard API rates per million tokens: Claude Opus 5.5 is $4 uncached input, $0.20 cached input and
$20 output; GPT-6 Sol is $2, $0.20 and $10. For an illustrative 40K uncached input and 8K output
call, Opus 5.5 costs $0.32 and Sol $0.16. These are token-mix estimates, not observed cost per
accepted review. Sources: [Opus 5.5](https://platform.claude.com/docs/en/models/opus-5-5/overview),
[GPT-6 Sol](https://developers.openai.com/api/docs/models/gpt-6-sol).
