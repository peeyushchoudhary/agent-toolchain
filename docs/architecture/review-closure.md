---
id: F-4
title: Review closure that ends in fixes, not in grants
spec: docs/product/specs/F-4-review-closure.md
status: draft
updated: 2026-10-07
---

# F-4 design — review closure

## Structure

There are three small changes, each made where the behaviour lives:

| Gap | Where | Kind |
| --- | --- | --- |
| Keep list in correction packets (AC-1) | `references/run.md`, the dispatch step | rules text |
| Defect family (AC-2) | `scripts/review.py`, the rereview packet; `references/review.md`, the closure rules | one packet sentence, plus rules text |
| Test-closed confirmation (AC-3) | `scripts/review.py`, `--closed-by`, admission and recording; `references/review.md` | code, plus rules text |

`methodology.md` changes by one sentence in its Review paragraph. `docs/architecture/lean-execution.md`,
`docs/decisions/decisions.md` and `docs/product/measurements.md` are updated to current state
(AC-5).

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
the round's range, plus untracked files for a task review. A deleted path maps to `null`, so a
review of a deletion still completes. This is the only new state.

It closes a gap that the verdict's `tree` cannot cover. A task review's work stays uncommitted
across rounds, so every round of a task review records the same HEAD tree.

**Verdict header.** A confirmation adds `confirmation: closed-by <TEST ...>`.

**Packet text.**
- A confirmation's packet names the tests and asks the judge to check that they reproduce the
  findings under rereview.
- Every rereview packet (round > 1) adds one instruction: for each blocking finding, state whether
  it is a new instance of a finding under rereview, written as `family: same as <finding path>`.

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
- **An LLM wiki, or graphify as the primary context:** out of scope here. The route and task packets
  stay; see the spec's Non-goals.
