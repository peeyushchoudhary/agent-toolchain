# Why each persona is routed the way it is

Measured on 2026-07-26. Re-derive when model prices or benchmarks move.

## The two principles

**Effort tracks reasoning depth. Model tracks stakes. Frequency decides where saving matters.**

Conflating importance with effort is the common mistake. `test-judge` reports whether the release
gate passed — as important as anything in the pipeline — but the task is "run a command and repeat
the output", which needs `low`. Its importance is handled by making it unable to edit, not by making
it think harder.

## Prices and benchmarks

| Model | $/M in | $/M out | Score |
|---|---|---|---|
| Haiku 4.5 | 1 | 5 | — |
| Sonnet 5 | 2 (intro, →3 Sep) | 10 (→15) | 63.2 SWE-bench Pro |
| Opus 5 | 5 | 25 | 79.2 SWE-bench Pro, 96.0 Verified |
| Fable 5 | 10 | 50 | 80.0 SWE-bench Pro |
| GPT-5.6 Luna | 1 | 6 | 82.5 coding index |
| GPT-5.6 Terra | 2.50 | 15 | 84.3 coding index |
| GPT-5.6 Sol | 5 | 30 | 88.8 coding index, 64.6 SWE-bench Pro |

The Anthropic and OpenAI numbers come from different suites. Compare **within** a vendor only;
nothing here ranks Opus against Sol.

## Per-persona reasoning

**`scout` — haiku / gpt-5.4-mini, low.** Highest frequency, lowest stakes, and the task is retrieval
rather than judgement. The whole point is that the caller spends the scout's context instead of
their own, so a cheap model that returns addresses is strictly better than an expensive one that
returns essays.

**`test-judge` — haiku / luna, low.** Runs a gate, reports the output. The failure mode is
dishonesty — calling a cached `UP-TO-DATE` a pass, or paraphrasing a failure into "some tests
failed" — and that is fixed by instruction and by read-only tools, not by reasoning depth.

**`docs-steward` — sonnet / terra, medium.** Prose that has to match code. Needs care, not depth,
and a wrong doc is cheap to correct.

**`developer` — sonnet / terra, medium.** The cheap implementation tier, for work inside one module
where the spec is complete and a pattern already exists. Sonnet 5 at 63.2 SWE-bench Pro is ample for
following an established pattern; it is not ample for inventing one, which is why the persona's
central instruction is to **stop and escalate** rather than infer. A cheap tier is only safe if it
refuses to improvise — the escalation rule is what makes the saving legitimate rather than a gamble.

**`senior-developer` — opus / sol, medium.** Everything needing judgement: cross-cutting work, new
abstractions, concurrency, security and money surfaces, and anything `developer` handed back. The
16-point SWE-bench Pro gap between Opus 5 (79.2) and Sonnet 5 (63.2) justifies 2.5× the price here,
and Anthropic's cost-per-task data puts Opus ahead on accuracy per dollar above medium effort.

Effort stays `medium` rather than `high`: Opus at medium is already strong, and the tier difference
is carried by the model, not by paying twice. Raising both model and effort would double-charge for
one increment of difficulty.

**Why split at all.** The predecessor was a single `implementer` at opus with "escalate per
dispatch" — a judgement made silently, every time, by whoever was orchestrating. Two named personas
make the tier an explicit, auditable choice, and route the ~70% of genuinely bounded work off the
expensive model. At ~40K in / 8K out per run and ~20 runs per milestone, that is about **$8.00 →
$4.64**, a 40% cut on the largest write-side line.

**`planner` — fable / sol, high.** The only place Fable earns $10/$50: a wide design space, run
about three times per milestone. It buys just +0.8 SWE-bench Pro over Opus 5, so it is poor value
for implementation — which is also a standing directive, and now has numbers behind it.

**`architect` — opus / sol, high.** Judges structure: layering, module boundaries, dependency
direction, and whether a change introduces a second way of doing something the codebase already
does. Distinct from `reviewer`, which asks whether code is correct — structurally wrong code usually
works, right up until it has to change. Distinct from `planner`, which decides what to build and in
what order rather than whether the shape is sound. Effort `high` because the reasoning ranges over a
wide context; `xhigh` was not justified by evidence.

Unusually for a judge, it may write — but only under `docs/architecture/` and `docs/decisions/`.
Tool restriction cannot be scoped to a path, so this is the one persona whose boundary is an
instruction rather than a guarantee. Accepted deliberately so it can author ADRs; the risk is that
it edits production code it just judged.

**`contract-architect` — opus / sol, high.** Migrations are append-only after merge and a published
contract has clients generated against it. These changes cannot be undone, so this is one of two
places `sol` is worth double `terra`.

**`reviewer` — opus / sol, high.** Must find what the author missed, which is the task where
reasoning depth actually converts into findings. Measured at ~$0.21 per review in-harness.

**`security-validator` — opus / sol, high.** Adversarial reasoning over consent, authorization and
PHI. Set at `high` rather than `xhigh`: `high` is already deep, and the extra tier did not earn its
cost in testing.

**`acceptance` — opus / sol, xhigh.** Runs once per milestone, so aggregate cost is irrelevant and
being wrong means shipping something unfinished. The one place to over-invest.

## Cross-harness dispatch: measured and rejected

Identical review task, a 34-line class with two planted authorization bugs:

| Run | Uncached in | Cached in | Out | Wall | Cost | Findings |
|---|---|---|---|---|---|---|
| `codex exec` naive | 31,522 | 76,032 | 1,218 | 42s | $0.232 | 2, ungrounded |
| `codex exec` no repo access | 23,746 | 0 | 237 | 15s | $0.126 | 2, shallow |
| `codex exec` matched (repo + scoped) | 48,611 | 138,240 | 1,827 | 66s | $0.367 | 5, grounded |
| Claude subagent, opus, in-harness | 27,232 | 0 | ~3,025 | 80s | $0.212 | 5, grounded |

Only rows 3 and 4 are comparable. Cross-harness costs about **1.7×** for equivalent quality: a cold
subprocess shares no context with the parent, so it re-reads source the parent already holds — 186K
input against 30K — on top of a **~23K-token system-prompt floor** charged on every invocation.
Prompt caching absorbed 138K of it; without caching the matched run would have been ~$0.98.

The quality argument was real — the other family independently caught that a method the first
reviewer's fix depended on did not exist — but not at 1.7× on every review. Revisit if the
system-prompt floor drops or context can be shared across harnesses.

## Scripting notes, if cross-harness is ever revisited

- `codex exec` refuses to run outside a git repo without `--skip-git-repo-check`
- it blocks reading stdin unless given `< /dev/null`
- `-s read-only` enforces at the sandbox level, stronger than tool restriction
- `--output-last-message FILE` captures a clean verdict; `--json` gives token usage
- `claude --fallback-model a,b,c` handles in-family overload automatically
