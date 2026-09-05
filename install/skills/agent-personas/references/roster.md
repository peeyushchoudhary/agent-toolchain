# Historical model-routing record (2026-07-26)

This file preserves the measurements and reasoning used for the previous roster. It is dated
history, not current model authority and not evidence for the current pilot defaults. Generate the
current source-derived roster with `sync_personas.py --list --include-retired --format markdown`.
Re-measure before using any price, benchmark, quality, frequency, or savings claim below.

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
failed" — and that is fixed by instruction and by tool restriction, not by reasoning depth.

It is the only non-writing persona with `Bash`, added after it was observed being assigned gate
execution it could not perform and chaining to a sub-subagent instead of reporting the problem. A
persona that cannot do its one job does not fail loudly; it improvises. Every other tool the roster
denies stays denied — see `~/.claude/docs/decisions.md`'s "What it withholds" for the current names, not a
restatement here, which is exactly what went stale before — so it still cannot author a fix. Codex
remains `read-only`; a write-producing gate runs against a controller-prepared, manifest-bound
standalone copy inside a nested sandbox, never against writable source. The judge requests approval
for the **exact sandbox-launch** only. The approved nested launch is
`env CODEX_HOME=<temporary-home> codex sandbox -p gate -P copy-write -C <copy> -- <exact gate argv>`.
Approval moves only the launcher outside the outer boundary; it immediately enters the custom inner
profile granting source read, copy write, and network disabled. The gate never runs unsandboxed.
Exact `--rerun-tasks` is the sole Gradle freshness evidence; `cleanTest` does not qualify.

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

**`reviewer` — opus / sol, high.** Independently tries to falsify design before Gate 1, plan before
Gate 2, and implementation before it lands. The pre-gate modes require fresh, artifact-only context
so the author's rationale cannot anchor the review; the implementation mode retains its existing
checks. This is the task where reasoning depth actually converts into findings. Measured at ~$0.21
per review in-harness. `PASS` is valid: paying for adversarial reasoning does not create a flaw
quota, and preferences or invented requirements cannot block an approved outcome.

**`security-validator` — opus / sol, high.** Adversarial reasoning over consent, authorization and
PHI. Set at `high` rather than `xhigh`: `high` is already deep, and the extra tier did not earn its
cost in testing.

**`migration-validator` — opus / sol, high.** Same tier and the same argument as
`security-validator`: adversarial reasoning over an irreversible surface, at `high` rather than
`xhigh` because the extra tier did not earn its cost anywhere else on this roster. It runs about
three times per milestone, at DESIGN, so the aggregate is a rounding error against the review line.

Two things about it are deliberate and neither is a cost decision.

It holds **no `Bash`**, and that is the whole design rather than an inherited default. The seat was
added because three improvised reviews — `syntax`, `nullcheck`, `blocker` — landed on one 386-line
migration that nobody owned. **Two of the three were work a tool does for free**: two missing
closing parentheses, which a statement-level parenthesis scan finds, and a `CHECK` predicate that
evaluates to UNKNOWN, which a dry run against a scratch database exposes. Granting this persona a
shell would let it re-derive both by hand at model prices, which is the over-engineering the seat
was created to remove. Denied the shell, it must demand the parse, the dry run and the migration's
contract test as **inputs**, and refuse the review when they are absent. That refusal is the
cheapest verdict on the roster and the one it should return most often.

It is cast at **design**, not at implementation review, and that is measured. Project-local domain
validators cast at implementation time returned 66 reviews and **zero** blocking verdicts across
four repositories; the same validator names cast inside a design workspace returned 6 blocks in 14
reviews. By implementation the migration has already been frozen into a card, so the only correction
available is an expensive one.

**`acceptance` — opus / sol, xhigh.** Runs once per milestone, so aggregate cost is irrelevant and
being wrong means shipping something unfinished. The one place to over-invest.

**`product-steward` — opus / sol, high.** Runs about twice per milestone, so cost barely registers.
The work is finding what a specification does not say — the empty case, the concurrent case, the
horizontal obligation nobody remembered — which is the same adversarial completeness reasoning that
puts `reviewer` at `high`. A cheap tier here writes a spec that reads well and is missing the
sections that cause rework.

**`chief-of-staff` — opus / sol, high.** The one persona whose cost is dominated by its *own*
context rather than by its run count, because it is a long-running loop that pays its accumulated
conversation as input on every turn.

Modelled over a 20-task plan, its cost is almost entirely a function of discipline, not of model:

| Orchestrator discipline | Cost per 20-task plan |
|---|---|
| Reports read inline | ~$114 |
| Reports to file, verdicts returned | ~$46 |
| + 1-hour prompt cache | ~$14 |
| + compaction every 5 tasks | ~$11 |

For comparison, all 156 worker runs in a milestone total about $22. So an undisciplined orchestrator
costs five times the entire fleet it manages, and a disciplined one costs half of it. That is why
the context rules in its body are written as hard requirements rather than advice — they are worth
more than every model-selection decision in this document combined.

The honest accounting: a chief-of-staff **cannot** pay for itself in tokens or in avoided fix
rounds. Pure token payback would need it to prevent ~26 fix rounds per milestone when only about
eight occur. It pays for itself in founder attention — roughly 160 dispatch decisions, about four
hours per milestone — and only if disciplined. Adding one without the file-and-verdict rule does not
replace an expensive accumulating context; it adds a second one.

Effort `high` rather than `medium` because tier escalation, adjudicating findings at the fix cap,
and detecting that a plan's shape is wrong are genuine judgement. A cheaper driver is viable once
the plan's task cards reliably settle the tier decision — that is a measurement worth taking, and it
would save roughly $7 per milestone.

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
