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
