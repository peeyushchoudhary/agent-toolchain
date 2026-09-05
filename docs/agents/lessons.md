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
