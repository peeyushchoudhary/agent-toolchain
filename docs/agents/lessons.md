# Lessons

**Authority: current, additive.** The cross-agent learning channel for this repository: one entry
per lesson, newest last, each stating what was MEASURED rather than what was believed. Entries
accrete and are never rewritten — a lesson that stops being listed stops being findable. Append; do
not edit an entry to make it agree with a later one, add the later one.

Created with content rather than as scaffolding.
[operating-model.md](../architecture/operating-model.md) already asserts that every repository
carries its own route and its own `docs/agents/lessons.md`; this one did not, which is the same
class of gap as the one recorded below.

## A checker we ship was never aimed at us

`docs/architecture/repository-standard.md` opens with "Enforced by `validate_disclosure.py
--standard`". Pointed at this repository, that command reported SEVEN errors and exit 1. The flag
appeared in `install_hooks.py`, in three tests and in four documents, and in no gate that ran
against this tree; `install/verify.sh` invoked the script only through `--help`.

**Why nobody saw it.** Every one of the seven was an ABSENT thing — six missing directories and a
missing route index. A missing `docs/architecture/` is nothing on screen. Enumerable, single-site
and authored, but NOT PRESENT: the exact case where reading carefully buys nothing and a machine
buys everything.

**The general form.** Shipping a checker, and documenting that it enforces a rule, is not the same
as running it. For every checker this repository publishes, ask which gate runs it against THIS
repository, and if the answer is none, either aim it or stop claiming enforcement.

## Complying with a standard turns on checks that were dormant

Creating `docs/agents/README.md` did not only clear an error. It made
`check_persona_decision` reachable for the first time — that check does nothing until a routed index
exists — and it produced a new warning demanding a deliberate `agent-personas` decision marker. A
compliance change is not purely additive: expect checks that had nothing to speak about to start
speaking, and close them in the same commit rather than banking a warning.

## A word-budget exemption can travel by filename, and a move can strip it

`validate_disclosure.py` exempts an accreting RECORD from the word budget by matching the BASENAME
against `^(measurements|benchmarks|decisions|adr|rulings|improvements|changelog|history)…\.md$`.
Moving `docs/decisions.md` to `docs/decisions/README.md` would have satisfied the directory rule and
silently dropped the exemption from a file at 1,185 words of 1,200. Before renaming a file to
satisfy a structural rule, check what the rest of the toolchain keys on its NAME.

## 2026-09-05 — matching generated sources does not establish policy consistency

The maintained and vendored `chief-of-staff` persona bodies match, but prescribe five fix rounds
while `execution-methodology/methodology.md` prescribes two. The execution procedure also requires
card validation despite the methodology's card-free light lane. A fresh read-only review confirmed
both conflicts. The methodology suite reported 1,070 tests with two skip events and no failures in
what ran; these semantic contradictions survived it. Check agreement between persona bodies and the
stage procedure before changing models: synchronization alone preserves contradictory instructions.

## 2026-09-05 — one process number cannot combine different units

The maintained receipt language promised workspace process lines, but the cited tools do not
produce that quantity. `ratio_meter.py` classifies committed line churn; `check_review_budget.py`
reports workspace files and bytes. Combining those outputs into one process ratio would turn a
policy claim into an invented measurement. Name each tool's unit, and evaluate delivery with
accepted outcomes, elapsed time, defects, repairs and founder decisions alongside churn.

## 2026-09-05 — a clean main checkout can hide an interrupted candidate

The published checkout was clean while an approved follow-up remained in separate local source and
public candidate checkouts. Its plan, authorization, implementation handoffs and review findings
survived there; an assessment limited to main missed them and proposed unrelated work. Before
choosing a continuation, recover the current candidate and its last handoff. Keep a local recovery
pointer and backup beside the project so temporary-directory state is not the only resume path.

## 2026-09-23 — a persona pilot can expose installed and vendored drift

Before the architect model change, the installed maintained source named Opus and GPT-5.6 Sol,
while the published copy named Fable 5.1 and GPT-6 Astra. The global sync preview after changing
the maintained architect source listed only the two generated architect agents for update. For a
bounded model rollout, preview the exact generated operations and avoid treating a whole-skill
install as an architect-only activation; it would also replace unrelated installed persona sources.

## 2026-09-30 — printed gate failure can still become a passing receipt

Independent isolated execution of `gate.sh`'s actual terminal branch with child exit zero and a
failed source-integrity check printed `GATE DID NOT PASS` but exited zero. `milestone_seal.py`
promotes a zero command exit to a success receipt. Separately, an isolated fixture whose declared
gate changed a tracked source file received a seal receipt and verified successfully: source
cleanliness is checked only before the gate. No implementation was changed during the assessment.
Bind launcher exit to its complete verdict and recheck the tested referent before certifying it;
tests must exercise the process contract, not only inspect the printed verdict.

## 2026-09-30 — efficiency follows the approved delivery objective

A proposed benchmark and cheaper-model pilot route was corrected to prioritize accepted product
velocity and quality, with quota efficiency as a sustained-execution constraint. Do not turn
research options into rollout prerequisites after the owner rejects them. Front-load consequential
questions in requirements, design and planning; preserve real local validation, then assess the
delivered workflow through existing evidence after one week and regularly.

## 2026-09-30 — disposable proof trees can distort bounded review

A filename-based review-budget checker interpreted copied persona sources as verdicts and also
counted repository files placed inside the bounded review workspace. Keep disposable proof
checkouts and fixtures outside that workspace. If they contaminate it, preserve every actual
verdict, lineage record and cap; have the Git owner move the fixtures; then rerun checks from the
current repository root. A narrower corrected scope never closes a genuine finding surfaced by the
earlier review.

## 2026-09-30 — file-count limits can manufacture broad ownership

An arbitrary write-path count made exact boundaries fail while broad globs passed, then encouraged
duplicate cards and reviews for one logical change. Bound work with normalized exact roots,
nonempty coverage and actual overlap, commit-scope and safety checks. Keep ordinary work Light and
use one Full card and one review only when the logical task really changes a durable or safety
boundary; a projection of the same change needs identity and consumer proof, not duplicated
ceremony.

## 2026-09-30 — review fixtures must not mutate frozen inputs

A frozen review input must remain byte-identical through its verdict. Prepare mutable probes in
separate existing fixture evidence, then bind the resulting evidence identity; do not turn probe
setup into an unreviewed mutation of the referent.

## 2026-10-01 — prerequisite repair must return to the delivery outcome

A workflow improvement stalled while a temporary native proof engine acquired its own dispatcher,
authority packets, model catalog, protocol schemas and repeated reviews. Core implementation never
started. Passing mock tests and fresh verdicts showed activity without delivery. The controller
allowed this dependency to grow; the chief kept repairing it instead of challenging the approach.

Before introducing another helper or control, identify the approved criterion it serves, why its
existing owner is insufficient, and the product outcome it unblocks. A genuine failure blocks the
affected mechanism; establish an actual dependency before it blocks unrelated work. New isolation
or runtime guarantees belong to the change introducing them, rather than becoming prerequisites
for ordinary workflow improvements. Keep failed evidence and do not claim deferred guarantees.

At the existing recovery or handoff boundary, recurring prerequisite repair must trigger an
approach decision: simplify, use the existing route, split independent delivery, or escalate the
real choice. Preserve the original blocked outcome and failure lineage; naming a new fixture or
diagnostic does not reset recovery. Use targeted expert advice when justified, not another routine
council, form, counter or checker. Report delivered outcomes and concrete blockers. These lessons
do not replace independent judgment or the real local gate, and do not prove installed behavior.

## 2026-10-01 — replacement authority retires the prerequisite, not its evidence

The approved core-first replacement reduced M2 to two file-disjoint implementation tasks plus
documentation, existing installation and local closure. The earlier native-first proof engine and
its universal P0 prerequisite are superseded rationale; their failed verdicts remain immutable
evidence and cannot be relabelled. When an approved approach changes, update every current route and
plan in place while preserving the rejected path only where rationale belongs.

## 2026-10-01 — security findings begin with the owner's trust model

Security packets must name the existing owner's actual trust model and explicit exclusions, then
classify findings against frozen criteria before demanding a substitute isolation or attestation
system. A real fail-open defect in that owner still requires repair.
