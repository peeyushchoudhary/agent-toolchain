# Operating model

Solo founder, several ideas in parallel, one laptop, no team, no hosted CI. Every other decision in
this documentation set follows from those four facts.

Canonical copy: `~/.claude/CLAUDE.md`, mirrored verbatim in `~/.codex/AGENTS.md`.

## The three stages, in order

1. **Local execution quality.** Get the change right on this machine — narrowest production path,
   its adjacent tests, then the area gate. Depth over breadth; a half-finished feature is worth
   less than a small one that holds.
2. **Local end-to-end validation.** Before anything is called pilot- or release-ready, prove the
   whole path locally with real services and the full check gate. A green unit suite is not
   validation, and neither is a green push.
3. **Production deploy.** A separate, deliberate, explicitly authorised step — never a side effect
   of finishing the work.

Do not skip ahead. Stage 2 is the one that gets skipped, because stage 1 feels like finishing.

## What follows from it

**Local gates are the only gates.** Report the command and its real output. Never claim a state you
have not observed. If something is flaky or environmental, say which and prove it by re-running.
This is why `make check` exists as one facade per project and why `test-judge` is forbidden from
paraphrasing a failure.

**There is no second reviewer.** Independent verification has to be manufactured rather than
assumed. That is the entire reason the persona pool exists, and why its judging roles are
structurally unable to edit — see [agent-personas.md](agent-personas.md).

**Design and plan are independently falsified before approval.** A fresh, read-only `reviewer`
receives named artifact paths without the author's conversation or rationale and tries to construct
a counterexample against frozen criteria and invariants. `PASS` is valid; blockers require a
reachable trigger, observable consequence, and artifact evidence. The author gets one correction
and one scoped rereview; recurrence returns the design to Gate 1 or the plan to Gate 2. This catches
expensive mistakes before implementation without creating a flaw quota or an open-ended consensus
loop.

Freshness is operational: Codex uses `fork_turns: "none"`, and another harness uses its equivalent
fresh-thread primitive; telling an inherited context to ignore its history is not isolation. A
scoped rereview receives paths to the persisted original finding, correction or diff, corrected
artifact, and governing frozen artifacts. Post-code review remains backward-compatible by
defaulting to Implementation unless Design or Plan is explicitly named.

**Context switches across projects are constant.** Assume no memory of another project. This is why
every repo carries its own route (`docs/agents/README.md`) and its own `docs/agents/lessons.md`,
rather than relying on an agent's private memory — one agent's memory is invisible to every other
harness.

**GitHub is storage.** Nothing deploys from it, nothing runs on it. See [github.md](github.md).

**Execution is goal-bound.** The approved plan owns one Goal Capsule: the actor outcome, one primary
externally observable outcome, the named safety and regression invariants that make it trustworthy,
non-goals and prohibited claims, the allowed interface/write boundary, known and unknown external
facts, and the stop condition. Cards reference its criteria through the existing card fields; they
do not copy it or invent another authority.

Before implementation or a review repair, classify the finding and name the capsule criterion or
invariant advanced plus the expected observable delta. A vague request produces a proposed capsule
for approval. Ambiguity that changes acceptance, safety, authority, or an irreversible boundary
returns to the appropriate human gate; bounded non-material ambiguity is recorded as an assumption.
The detailed admission and repair rules live in the execution methodology. See
[D14](decisions.md#d14--bounded-repairs-and-review).

## Deliberately not done

These look like gaps and are not. Do not "fix" them.

| Not done | Why |
| --- | --- |
| Hosted CI / GitHub Actions | The founder laptop is the only release runner. A push is not evidence |
| Committed `.claude/settings.json` | Sole-founder mode; machine-local config stays machine-local |
| Committed graph (`graphify-out/`) | 22 MB rewritten wholesale each rebuild; regenerate instead |
| Bulk migration of the other 12 projects | Done per project, when that project is next opened |
| Cross-harness agent dispatch | Measured at 1.7× in-harness cost — [decisions.md](decisions.md) |

## Delegation posture

Substantive work goes to a controller-led multi-agent workflow: contract-bounded tasks, specialist
subagents with isolated context and exclusive write sets, independent file-disjoint tasks in
parallel, one integration owner, and serialised edits to shared interfaces and generated artifacts.

A builder never approves its own work.

Direct single-agent implementation is correct only for genuinely trivial, low-risk changes where
delegation would add no isolation, parallelism, or independent verification.
