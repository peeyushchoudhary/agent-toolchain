---
id: F-4
title: Review closure that ends in fixes, not in grants
spec: docs/product/specs/F-4-review-closure.md
status: approved
updated: 2026-10-08
---

# F-4 design — review closure

## Structure

There are six small changes, each made where the behaviour lives:

| Gap | Where | Kind |
| --- | --- | --- |
| Keep list in correction packets (AC-1) | `references/run.md`, the dispatch step | rules text |
| Defect family (AC-2) | `scripts/review.py`, the rereview packet; `references/review.md`, the closure rules | one packet sentence, plus rules text |
| Test-closed confirmation (AC-3) | `scripts/review.py`, `--closed-by`, admission and recording; `references/review.md` | code, plus rules text |
| Class correction at the first open-input finding (AC-2) | `references/review.md`, the closure rules | rules text |
| Oracle tests and tested fix commands (AC-6) | `references/planning.md`, Writing tasks | rules text |
| Acceptance packet coverage (AC-7) | `scripts/review.py`, the diff and the packet | code |

`methodology.md` changes by one sentence in its Review paragraph. `docs/architecture/lean-execution.md`,
`docs/decisions/decisions.md` and `docs/product/measurements.md` are updated to current state
(AC-5), and `docs/agents/lessons.md` gains the git hook-location facts.

## Interfaces

**`review.py --closed-by TEST [TEST ...]`.** Each `TEST` is `path` or `path::name`. Only the path
part is checked.

It is valid only with a capped kind (acceptance, design, plan, security, boundary, data). It may
not be combined with `--founder-grant`.

It is admitted only when all of these hold:
1. The subject's current verdict (`verdicts/<key>.md`) exists, and its first line is
   `VERDICT: BLOCK`.
2. The subject has used no confirmation yet (`rounds.json` → `confirmations[key]` is absent).
3. Every named path exists in the working tree, and its SHA-256 differs from its content at the
   subject's last round. That content is:
   - the digest recorded for the path at that round, when the round recorded it;
   - otherwise, the blob at that path in that round's verdict `tree`, because a path the round did
     not record did not differ from the round's base;
   - otherwise, nothing: the path did not exist then, so a new file counts as changed.

   An unchanged tracked test outside the last round's diff is therefore refused.

A refused confirmation exits 1 with the reason and consumes nothing. Like every round, an admitted
confirmation runs under the subject's lock. It is not counted in `rounds[key]`, and it is recorded
as `confirmations[key] = <round number>`.

Round numbers stay sequential, so a confirmation is round n+1 in history and in the verdict.

**Per-round file digests.** Each round of a subject writes `review/<key>-r<n>.files.json`, mapping
every changed path to its SHA-256. The changed paths are those `git diff --name-only` reports for
the round's range, plus every path whose working-tree content differs from the round's verdict
tree, plus untracked files, whatever the range. An unrecorded path is therefore identical to the
verdict tree at that round. A deleted path maps to `null`, so a review of a deletion still
completes. When the comparison cannot be made (the verdict tree is missing, or a git call fails),
`--closed-by` refuses. This is the only new state.

It closes a gap that the verdict's `tree` cannot cover. A task review's work stays uncommitted
across rounds, so every round of a task review records the same HEAD tree.

**Verdict header.** A confirmation adds `confirmation: closed-by <TEST ...>`.

**Packet text.**
- A confirmation's packet names the tests and asks the judge to check that they reproduce the
  findings under rereview.
- Every rereview packet (round > 1) adds one instruction: for each blocking finding, state whether
  it is a new instance of a finding under rereview, written as `family: same as <finding path>`.

**Acceptance diff and coverage.** For acceptance, the diff range stays `<base>..HEAD`. Its path
filter comes only from a declared partition: when the milestone's `acceptance:` list names more
than one partition, the chief passes that partition's paths with `--subject` and `--partition`.
For a single partition (`[all]`), `--subject` paths are reading context and never filter the
diff. The packet adds one line, `diff covers <n> of <m> files changed in <milestone>`, with both
counts from `git diff --name-only`.

**Cap arithmetic.** `admit()` counts only non-confirmation rounds against `cap`. Without a founder
grant, a subject is limited to at most `cap + 1` judge calls. The founder grant still admits
exactly one round past the cap, once per subject.

## Rules text

- **`run.md` dispatch step.** A correction packet adds a **Keep** list. It names the behaviours in
  the code the correction touches that earlier verdicts, Decisions or tests established, each with
  the reason in a few words. A builder who must remove a Keep item stops and reports. The words are
  offset by trimming elsewhere in `run.md`, so the role-load budget holds.
- **`review.md` Closure.**
  - Step 1 becomes executable: a test-closed correction is confirmed with `--closed-by`, once per
    subject, without spending the cap.
  - A new step covers families. When a rereview marks a finding `family: same as …`, the next
    correction targets the family: the mechanism, not the path. It is recorded in Decisions. A
    family fix that changes the design, the scope or a durable interface is queued for the founder.
- **`review.md` Closure, open input.** A new step before the family step. A blocking finding whose
  trigger lies in an open input space (environment or configuration, filesystem paths, an
  external tool's behaviour, concurrency) is corrected at the class on the first round. The packet
  states the invariant, or the narrower claim, that makes the class impossible, and lists the
  sibling triggers the chief considered. The builder tests each of them. Narrowing the claim, for
  example to an honest skip, is a valid class fix.
- **`planning.md` Writing tasks.** Two rules, about 80 words:
  - code that predicts an external tool's behaviour carries an oracle test, which runs the tool
    under the same environment over the setups the code must handle and compares the decisions;
  - a design or task that prints a fix command (in a status line, a refusal or an error) carries a
    test that runs the command and shows that the condition clears.
- **`methodology.md` Review paragraph.** One sentence names both rules, word-neutral across
  `SKILL.md`, `methodology.md` and `run.md`.

## Smallest-sufficient-change trace

- **AC-1:** a correction regressed because its packet lacked the reason for a skip. The smallest
  fix is the packet's content, which is rules text. Nothing needs code, because the chief writes
  packets.
- **AC-2:** two rounds were spent on instances. The judge is best placed to see that a new finding
  shares a mechanism with an old one. One packet sentence makes it say so, and one closure rule
  makes the chief act on it.
- **AC-3:** the existing closure step 1 is unreachable for subjects that need a fresh PASS. A
  confirmation that does not count, bounded at one per subject and admitted only against a
  changed test, makes step 1 real. The loop still terminates.

- **AC-2, open input:** six of F-3's eleven blocking rounds were further instances of a family
  already found, all in open input spaces. Correcting the class on the first finding costs one
  packet paragraph; waiting for the repeat costs a round each time.
- **AC-6:** M4's rounds 2–4 were each a locally reproducible test away, and F-5's three design
  blocks were each a command run away. Two planning rules move that discovery before review.
- **AC-7:** one wasted round came from a `--subject` that silently filtered the acceptance diff.
  Taking the filter from the declared partition and stating the coverage close it in a few lines.

## Rejected options

- **Raise the cap to 3:** it spends the extra round on any correction, not only a test-proven one.
- **Advisor-granted rounds:** v6 deliberately keeps round grants with the founder. An escalation
  that buys rounds is how earlier loops failed to end.
- **Run each test against the pre-fix tree to prove that it failed before:** this needs a checkout
  and a runner per language, which is more machinery than the cap it saves. The judge reads the
  test against the finding.
- **Bind confirmations to the verdict's `tree`:** it is unchanged across the rounds of an
  uncommitted task review, so the check would always pass.
- **Parse `family:` lines in code:** the chief acts on them, and parsing would add a format that
  can drift. Prose suffices.
- **Rate findings by likelihood or impact:** a rare but real correctness finding could then be
  queued instead of fixed. Class correction removes most of the cost, and the founder declined
  it (2026-10-08).
- **Carry a PASS forward when the change misses a partition's paths:** F-3 spent four PASS rounds
  on re-closes, but carrying a verdict across trees needs its own design and a measurement first.
  It is queued.
- **Refuse an empty diff before the judge call:** existing review fixtures judge clean trees, and
  the coverage line already shows `0 of <m>`; the refusal would add a rule for a case the line
  makes visible.
- **Prove the oracle in code (`review.py` runs the tests):** the judge reads the test against the
  finding, as for `--closed-by`; a runner per language is more machinery than it saves.
- **An LLM wiki, or graphify as the primary context:** out of scope here. The route and task packets
  stay; see the spec's Non-goals.
