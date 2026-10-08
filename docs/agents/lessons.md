# Lessons

**Authority: current.** The cross-agent learning channel for this repository: what misled an agent
here, each lesson short and stating what was measured rather than what was believed. Add a dated
entry when something in the docs misleads you. When a lesson stops applying, remove it; git holds
it.

## A checker we ship must be aimed at us

`docs/architecture/repository-standard.md` once claimed `validate_disclosure.py --standard`
enforced the layout, yet no gate ran it against this tree, and pointed there it reported seven
errors. Every one was an absent thing, which reading carefully never finds. For each checker the
repository publishes, name the gate that runs it here, or stop claiming enforcement. `verify.sh`
now runs it.

## Complying with a standard turns on dormant checks

Creating `docs/agents/README.md` made `check_persona_decision` reachable for the first time. Expect
checks that had nothing to speak about to start speaking, and close them in the same commit.

## A word-budget exemption can travel by filename

`validate_disclosure.py` exempts accreting records by basename. Renaming `decisions.md` to
`README.md` would have dropped the exemption from a file near the budget. Before renaming a file to
satisfy a structural rule, check what else keys on its name.

## Green suites survive contradictory prose

Two persona bodies once prescribed five fix rounds while the methodology prescribed two, and a
1,070-test suite passed. Agreement between role prose and the procedure it serves needs a read,
because synchronising generated copies preserves a contradiction faithfully. Routing lives only in
persona frontmatter for this reason.

## One number cannot combine different units

A receipt once promised workspace process lines from tools that report committed line churn and
workspace files and bytes. Name each tool's unit and report them separately; a combined ratio is an
invented measurement. Churn alone does not prove faster delivery either.

## A clean main checkout can hide an interrupted candidate

A clean published checkout hid an approved follow-up that lived in separate local checkouts, and an
assessment limited to main proposed unrelated work. Before choosing a continuation, recover the
current branch, its `goal/<id>/` tags and `.runs/<id>/progress.md`.

## A printed failure must also be a failing exit

A gate once printed `GATE DID NOT PASS` and exited zero, and a downstream sealer promoted that zero
to a success receipt. Another gate changed a tracked file and still received a receipt, because
cleanliness was checked only before the run. Bind the exit status to the complete verdict, recheck
the tested tree afterwards, and test the process contract, not only the printed text.

## Efficiency follows the approved delivery objective

A benchmark and cheaper-model route was corrected to put accepted product velocity and quality first
and quota efficiency second. Do not turn research options into rollout prerequisites after the
owner rejects them, and front-load consequential questions into the spec, design and plan.

## Keep proof fixtures out of the reviewed workspace

A filename-based budget checker read copied persona sources as verdicts, and repository files placed
inside the bounded workspace were counted. Keep disposable proof checkouts and fixtures outside the
workspace. A narrower corrected scope never closes a finding the earlier review raised.

## Write sets must be exact, not counted

An arbitrary write-path count made exact boundaries fail while broad globs passed. Bound work by
exact roots, non-empty coverage and actual overlap, and keep a projection of the same change from
needing duplicate ceremony.

## Frozen review inputs stay byte-identical

A frozen input must be the same through its verdict. Prepare mutable probes in separate fixtures and
bind the resulting evidence identity; setup must never mutate the thing under review.

## Prerequisite repair must return to the delivery outcome

A workflow improvement stalled while a temporary proof engine grew its own dispatcher, schemas and
repeated reviews, and core work never started. Passing mock tests showed activity, not delivery.
Before adding a helper or control, name the criterion it serves, why the existing owner is
insufficient, and the outcome it unblocks. When prerequisite repair recurs, decide the approach:
simplify, use the existing route, split independent delivery, or escalate the real choice. Renaming
a fixture does not reset the failure.

## Replacement authority retires the prerequisite, not its evidence

When an approved approach changes, update every current route and plan in place and keep the rejected
path only as labelled rationale. Earlier failed verdicts stay as evidence and are not relabelled.

## Security findings begin with the owner's trust model

A security packet names the existing owner's trust model and explicit exclusions, then classifies
findings against frozen criteria before asking for a substitute isolation system. A real fail-open
defect in that owner still needs repair.

## Persona defaults need one authority

When model routing changes, remove conflicting defaults from persona prose and update the existing
compatibility assertion to the frontmatter authority. Generated agents are never hand-edited. Preview
the render before applying it, so a model rollout does not replace unrelated installed sources.

## Approval frequency must be checked against actual decisions

A session audit found elapsed-time renewals, review-count exceptions and fixture repairs repeatedly
becoming founder transactions, and overlays and narrow grants kept the stops even when the common
prose sounded broader. A failed safety check blocks acceptance, but repairing an unchanged
requirement is not changing it. Count what actually stopped the run before adding an approval.

## Hooks run where `git rev-parse --git-path hooks` says

An installer wrote graph hooks that git never ran, because it read `core.hooksPath` instead of
asking git. M4 acceptance blocked in rounds 2-4 on the variants: an empty value, three path forms
(a trailing space, a missing component, a case-insensitive name), then `GIT_CONFIG`. With
`core.hooksPath` unset, linked worktrees share the main checkout's hooks directory. A relative
`core.hooksPath` resolves inside each worktree. `GIT_CONFIG` changes only what `git config` reads,
so a running git ignores it. Narrow any claim about where hooks run to "`core.hooksPath` is
unset", and test the decision against git itself.

## A hook refreshes only the worktree that ran the command

git runs a hook from the root of the worktree that ran the command, so graphify's hook refreshes
only that worktree's untracked graph. In a worktree without a graph, graphify's post-commit hook
creates one holding only the changed files. A test in a throwaway repository with real git and
graphify showed it, with `built_at_commit` at HEAD. The installer now guards each graphify block
so it refreshes only an existing graph.
