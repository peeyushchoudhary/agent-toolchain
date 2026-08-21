#!/usr/bin/env python3
"""Review-budget check (methodology v3.1) — AN ADVISORY INSTRUMENT.

THIS TOOL MAKES ROUND SPEND VISIBLE. IT DOES NOT BIND THE PARTY THAT RUNS IT.
Read that sentence before you read anything else in this file, because the filename says `check`
and three earlier versions of this docstring claimed otherwise, in three registers, and every
one of them was falsified by execution inside a week.

The tool is run BY the orchestrator, on inputs the orchestrator controls: the filenames in the
workspace, then the process environment, then the ledger itself. **No in-process control can bind
its own operator.** Founder gate ruling 2026-08-20, after the FOURTH occurrence of one mechanism
across four rounds of hardening. Hardening stopped. What the tool is FOR, stated exactly:

  * it COUNTS what the workspace shows and prints a receipt a human can read;
  * it FAILS LOUDLY on the shapes it can see, so that drift costs a deliberate act rather than an
    oversight — the exit code is a tripwire against forgetting, not a gate against intent;
  * THE BINDING CONTROL IS A HUMAN READING THE RECEIPT AT THE MERGE GATE. That is where round
    spend is actually adjudicated. Nothing below changes that, and no future edit to this file
    can, because the seam is the design and not a defect awaiting a fifth repair.

An RC of 0 therefore means "nothing this instrument can see is wrong". It is not a certificate.

Run by the orchestrator BEFORE every review dispatch, against the plan workspace, naming the
subject about to be dispatched:

    check_review_budget.py WORKSPACE_DIR --next SUBJECT [--grants ROUND-GRANTS.tsv] [--json]

=======================================================================================
KNOWN-OPEN — bypasses that are REAL, REPRODUCED BY EXECUTION, and DELIBERATELY NOT FIXED
=======================================================================================
Stated here rather than in a report, because the next reader inherits the old claim from the
filename alone. Nothing in this list was closed quietly; nothing in it is a TODO.

THE SHARED ROOT (gate ruling, not to be re-argued): the tool derives both IDENTITY and AUTHORITY
from inputs the bound party controls. Every repair so far has closed the reported SPELLING and
left the CLASS open. The four occurrences, one mechanism:
  1. `full-diff` in a filename bought an exemption outright.
  2. The repair RELOCATED the exemption; a suffix filter jumped the bookkeeping.
  3. The second repair relocated it again; the terminal record jumped `charged`.
  4. `.txt` on three verdict names bought three review rounds — a suppression running ahead of
     bookkeeping it did not intend to skip, for the fourth time. (Closed HERE, as an error; the
     class it belongs to is not.)

THE CEILING ON THE WHOLE DESIGN, which is why hardening stopped: the DEFAULT ledger is never
git-queried at all (`read_grants`, deliberate, for harness parity — the Codex mirror of this skill
is git-ignored, so a tracked-ness test would make two byte-identical copies disagree). **Appending
one row to the shipped ROUND-GRANTS.tsv costs nothing and prints no NON_DEFAULT_GRANTS.** Every
hardening in this file concerns caller-named ledgers only. The cheapest route was never forged
because it never needed to be. Anything below is a fence beside an open gate, and is worth having
only because it makes the open gate the one route, and that route is one line in a tracked,
diffable, reviewable file.

F-A, NARROWED AND OPEN — git's environment answers "which repository". `is_a_committed_authority`
asks git where it is. A caller who sets GIT_DIR/GIT_WORK_TREE answered that question themselves and
had a forged ledger honoured (reproduced: RC=1 refused -> RC=0 GRANT_APPLIED). Those variables are
now scrubbed and the script asserts it is contained in the toplevel it resolved. THAT NARROWS IT.
It does NOT close it: a caller may run a COPY of this script beside their own committed ledger, and
the tests themselves ship that recipe. The resolved script path is printed so a receipt can show
which copy ran.

F-C, OPEN AND NOT ADDRESSED — a `terminal` row is never consumed by USE, only by an artifact NAME
that the bound party writes. `terminals` is built from the scanned workspace only, so dispatching
once and then filing the verdict as `SUBJ-r3-reviewer.md`, or deleting/moving the artifact, or
passing a narrower workspace, is excused again, unboundedly. Reproduced: one founder row, three
consecutive RC=0 TERMINAL_PASS_APPLIED. What is done here is smaller and is NOT a fix: on
TERMINAL_PASS_APPLIED the tool prints the exact `terminal-spent` ledger line to append, and honours
such a row by granting nothing. **A human must append it.** The tool cannot.

THE TERMINAL ROW IS MORE PERMISSIVE THAN THE GRANT IT WAS MODELLED ON, and the docstring that said
it got "exactly the validation a round grant gets" was comparing the wrong thing. It gets the same
ATTRIBUTION validation. But a round grant authorises NO DISPATCH AT ALL — it only suppresses a
standing scan — while a terminal row authorises a dispatch. They are not equivalent instruments and
the ledger comment should not be read as saying they are.

THE ROUND-MARKED TERMINAL ARTIFACT (reviewer F1, reproduced) — a terminal verdict filed WITH a
round marker never enters `terminals`, so TERMINAL_PASS_SPENT cannot see it. That is a consequence
of "a round marker makes it a scoped round", which is deliberate, and it is the mechanism behind
F-C above. Not separately fixed.

Errors (exit 1) — the dispatch must not proceed:
  * ROUND_BUDGET_EXHAUSTED — a subject named by --next has already spent its round budget. This
                    is the pre-dispatch refusal: round three is refused before it exists.
  * ROUND_CAP     — any subject in the workspace carries a round marker above --max-round, and no
                    grant line names that exact (subject, round). The standing scan: it catches a
                    budget already breached, whoever breached it.
  * BANNED_CLASS  — a banned artifact class is present: diff/patch snapshots, restatement
                    packets, or files recording a dispatch that produced nothing
                    (invalid-attempt / no-verdict / no-progress). Those are ledger lines.
                    (The founder-facing escalation *brief* is a different, permitted artifact.)
  * TERMINAL_PASS_SPENT — a --next naming the terminal whole-diff pass for a subject whose
                    terminal artifact is ALREADY IN THIS SCANNED DIRECTORY and carries no round
                    marker. It reports the pass it can SEE. It does not bound the pass to one per
                    subject: see F-C and the round-marked terminal artifact under KNOWN-OPEN.
  * NON_PROSE_VERDICT — a round-marked artifact that reads as a JUDGE VERDICT but carries a
                    non-prose suffix. It is still NOT CHARGED (evidence must not spend rounds),
                    and it is an ERROR rather than a warning because a warning changes no exit
                    code: `SUBJ-r1/-r2/-r3-reviewer.txt` bought three rounds at RC=0 while
                    printing three warnings, which is occurrence four of the mechanism above.
                    Rename it `.md` if it is a verdict, or give it a work kind if it is evidence.
                    THE ERROR IS THE WHOLE REPAIR: the round is not charged, so this does not
                    silently spend a budget either.

THE ROUND GRANT IS DATA THIS TOOL READS (council ruling 2026-08-20, `bdcb7369`). A founder may
grant one subject one round beyond the cap. That decision used to have no representation the
instrument could see, so a legitimately granted artifact left the workspace in standing ROUND_CAP
and blocked every later dispatch in it forever. The grant is now an INPUT: a tab-separated line in
a TRACKED file outside every dated workspace (`.gitignore` excludes `sdd/20??-??-??-*/`, so a
grants file living in scratch would be untracked and forgeable).

    SUBJECT<TAB>r<N>|terminal<TAB><granting-commit><TAB><date><TAB><reason>

THE TERMINAL WHOLE-DIFF PASS IS A LEDGER ROW TOO (founder gate ruling 2026-08-20, option 3,
`7a15264b`). It used to be an EXEMPTION keyed on the token `full-diff` appearing in a filename —
a name written by the very party the control binds — and that one exemption produced all three
occurrences of a single mechanism: a suppression running ahead of bookkeeping it did not intend to
skip. Two repairs each RELOCATED it rather than removing it, so it is removed. The token now only
IDENTIFIES a terminal pass; a row whose round field is the word `terminal` authorises such a
dispatch past a spent budget, for as long as the row stands and no terminal artifact is visible to
the scan (F-C). It gets the same ATTRIBUTION validation a round grant gets — attribution required,
and one subject named exactly. It is NOT otherwise equivalent to a round grant, and the earlier
claim that it "gets the SAME validation" was comparing the wrong thing: a round grant authorises no
dispatch at all. It is the MORE PERMISSIVE instrument of the two. A `terminal-spent` row for the
same subject withdraws it. A name carrying a round marker is a SCOPED ROUND whatever other token it
contains: `SUBJ-r3-full-diff-reviewer.md` spends r3, and `--next SUBJ-r4-full-diff-reviewer` is
refused.

SUBJECT is the DERIVED key — `subject_of()` of the artifact name, lower-cased — never a label the
dispatcher invents. A grant marker typed into a filename was considered and REJECTED by three
independent lenses: the kind discriminator reads names written by the very party the control
binds, so a marker encodes an orchestrator's claim rather than a founder's decision, and it is
rename-to-reset with a nicer token. Keying on the derived subject does not fix that (the ledger is
writable too) but it makes the grant countable, greppable, diffable and versioned, which argv
never was.

WHAT A GRANT MAY DO, EXHAUSTIVELY: suppress ROUND_CAP for the ONE (subject, round) pair it names
exactly. It may not raise a cap, may not create a round, may not clear ROUND_BUDGET_EXHAUSTED,
TERMINAL_PASS_SPENT or BANNED_CLASS, and has no effect on any pair it does not name. A granted
subject therefore still refuses its next dispatch — the grant unblocks the WORKSPACE, never the
SUBJECT. `--max-round` keeps its default of 2 and is RETIRED AS THE GRANT VEHICLE: it is global,
applied at the `--next` refusal and the standing scan alike, so every past `--max-round 3` silently
handed a third round to every subject in that invocation rather than to the one being discussed.

A REVIEW ROUND IS SPENT BY A REVIEW, NOT BY AN ARTIFACT (founder ruling 2026-08-20). The budget
exists to bound how many times a subject may be *judged*; the fix a judgement provokes is not
itself a judgement. Counting every round-marked file made a fix round consume the budget its own
re-review needed, so a subject that fixed twice could never have its second fix reviewed — the cap
forbidding exactly the review it exists to protect. The round marker therefore decides WHEN, and
the KIND suffix after it decides WHETHER: a judge verdict (`-reviewer`,
`-security-validator`, `-*-validator`, `-*-architect`, `-acceptance`, `-review`, `-rereview`)
spends a round; a fix brief, fix report, implementation report, scout sweep or analysis does not.
Nor does a NON-PROSE artifact: a JUnit XML, a probe log, a diff or a source file carried into the
workspace as evidence is not a judgement whatever its name says.

AND NEITHER DOES `-test-judge`, WHICH USED TO. A judge that runs a command and reports its exit
code is collecting evidence, not adjudicating. Measured across the four real repositories: 124
`-test-judge` artifacts, 114 PASS / 2 FAIL / 1 with no verdict — a 0.02 block rate against 0.16
for `reviewer`. It is the same rule the non-prose suffixes already apply to a JUnit XML, applied
to the prose file that reports that XML. The check that had to pass before this shipped: BOTH
failing test-judges have a sibling REVIEW verdict at the same (subject, round), so neither round
loses its charge. Across all 59 workspaces the reclassification drops 124 artifacts from the
charge, moves 496 charged subjects to 488 and 783 charged (subject, round) pairs to 775, and
CHANGES NO WORKSPACE EXIT CODE. The 8 vanished pairs are 3 distinct artifacts, each read: a
baseline, an explicit `UNDECIDED`, and one with no verdict line at all. No BLOCK goes silent.
See EVIDENCE_KIND_TOKENS.

Warnings (exit 0, reported) — process-regression signals for the milestone receipt:
  * UNCLASSIFIED_ROUND_ARTIFACT — a file carries a round marker but no kind this tool recognises.
                    It is CHARGED AS A REVIEW (fail closed: never lose a round) and named, because
                    the silent drop is the failure mode this check was repaired for — a real judge
                    verdict, `D185D-r1fix-test-judge.md`, once vanished from the counter entirely
                    because one hyphen was not typed, and nothing said so.
  * MISSING_ROUND_MARKER — a file whose name identifies it as a JUDGE VERDICT (a persona suffix,
                    or the word `verdict`) but which carries no round marker at all. It is NOT
                    charged — the round it belongs to is unknowable from the name — but it is
                    named, because until now an unrecognised KIND warned while a missing ROUND
                    MARKER did not, so a live architect verdict counted as zero rounds in silence.
                    That asymmetry was the louder failure being the safe one.
  * STALE_GRANT   — a grant whose SUBJECT is present in this workspace but which matches no
                    artifact at the granted ROUND. It suppresses nothing, which is the same class
                    of defect as a forbidden path that forbids nothing: it reads as protection and
                    is not. Scoped to subjects the workspace actually contains — the ledger spans
                    milestones, so a grant for a subject sealed out of this workspace is out of
                    scope here, not stale. A grant key MISTYPED into a separator variant of a live
                    subject is caught by COLLIDING_SUBJECT_KEYS below, which reads grant keys too.
  * COLLIDING_SUBJECT_KEYS — two distinct subject keys that differ only in `-`, `_` and `.`.
                    `KIND_SPLIT_RE` equates those separators for KINDS; nothing equates them for
                    SUBJECTS, so `AUTHZ_B3P1` and `AUTHZ-B3P1` are two subjects with two budgets.
                    Reported ONLY. Subject derivation is not changed here: re-keying it would
                    silently re-key every grant line written against the old derivation.
  * GRANT_LINE_MALFORMED — a line in the grants file that does not parse. It grants nothing (fail
                    closed) and is named rather than dropped.
  * GRANTS_FILE_MISSING — an explicitly passed --grants path that does not exist. No grant is in
                    force; the check runs at full strength.
  * TERMINAL_PASS_APPLIED — a --next naming a terminal pass whose subject has spent its round
                    budget, suppressed because the ledger records a `terminal` row for that
                    subject. Reported with the row's attribution, and reported SEPARATELY from
                    GRANT_APPLIED so a receipt can count terminal passes and round grants apart.
  * UNRECORDED_TERMINAL_PASS — a terminal artifact is in the workspace for a subject the ledger
                    names no `terminal` row for. It is not an error: the ledger spans milestones
                    and this scan is one directory. It is named because a terminal pass that no
                    founder decision records is exactly what the removed exemption used to permit
                    silently and without limit.
  * NON_PROSE_UNCLASSIFIED — a round-marked artifact with a non-prose suffix whose kind this tool
                    does not recognise. It is NOT charged (the suffix rule), and unlike the prose
                    case it cannot fail closed by charging, so it is NAMED. Its prose twin is
                    charged as UNCLASSIFIED_ROUND_ARTIFACT. It stays a WARNING while its sibling
                    NON_PROSE_VERDICT is an error, because this one cannot be read as a verdict at
                    all — erroring on every probe log would be noise, and noise is how the
                    previous four warnings came to change nothing.
  * TERMINAL_SPEND_UNRECORDED — printed WITH every TERMINAL_PASS_APPLIED: the exact ledger line to
                    append so the spend survives the deletion of the artifact. It is advice a
                    human must act on; the tool cannot write it and does not pretend to.
  * TERMINAL_PASS_ALREADY_SPENT — the ledger carries BOTH a `terminal` row and a `terminal-spent`
                    row for one subject. The row grants nothing; the pass has been taken.
  * DUPLICATE_TERMINAL_PASS — two `terminal` rows for one subject. The FIRST stands, as for a
                    duplicate round grant: two lines for one decision make the ledger disagree
                    with itself about which one is in force. Reported, not resolved.
  * FAMILY_SPEND  — two or more subject keys are ONE lineage by token prefix (`<subj>`,
                    `<subj>-contract`, `<subj>-contract-prerequisite`), and together they spend
                    more than the budget. RENAMING A SUBJECT RESETS ITS BUDGET and no per-subject
                    line can state the total, so this one does. Measured: a code-formatter
                    prerequisite in one real workspace holds 13 subject keys, 51 charged
                    artifacts and rounds r1..r15 for ONE artifact under review. ADVISORY — it
                    raises no error, changes no exit code, and the `--next` refusal does not
                    consult it. Subject derivation is UNCHANGED, so no grant key is re-keyed.
  * WORKSPACE_BUDGET — workspace exceeds ~50 files or ~500 KB.

Scope, stated plainly: the check keys on the --next subject the orchestrator declares and on
filename lineage (round markers are stripped before grouping, so `S2-01-R18.md`,
`S2-01-round18.md` and `S2-01-fixround3-rereview.md` are one subject). The methodology therefore
mandates that persisted verdicts are named `<subject>-r<N>-<kind>.md` — a marker-free verdict
filename starves this counter and is itself a violation. It is protection against drift, not
against an adversarial orchestrator: renaming a subject to dodge the counter is not REFUSED from
filenames alone — FAMILY_SPEND now makes the commonest shape of it VISIBLE (a qualifier appended
to a live subject key), which is a report and not a refusal, and a rename to an unrelated stem
still leaves no trace this tool can read. Nor is it protection against a party that means to spend a round it was not
given: see KNOWN-OPEN at the top. It is an instrument that reports, and a receipt a human reads.

What the kind discriminator CANNOT see, stated plainly. It reads the filename and nothing else —
not the file's contents, not which persona actually wrote it, not the containing directory. The
directory is deliberately NOT used: in this repository's own workspaces `reports/` holds judge
verdicts (`AUTHZ-A3-r1-reviewer.md`) and implementer reports (`D185D-r1-fix-report.md`) side by
side, so a directory rule would misclassify both halves of a mixed folder and would let a wrong
folder override a correct filename. So: a verdict misnamed as a report is undercounted, a fix
brief misnamed `-reviewer` is overcounted, and a kind this tool has never heard of is charged as a
review and reported rather than dropped. The methodology's mandated `<subject>-r<N>-<kind>.md` is
what makes this readable; UNCLASSIFIED_ROUND_ARTIFACT is what makes a departure from it visible.
"""

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
from pathlib import Path

# Git answers "which repository am I in" from the ENVIRONMENT before it answers it from the
# filesystem, so a caller who exports these has answered it for us — reproduced 2026-08-20:
# a ledger committed in a caller-made /tmp repo was refused (RC=1), and the SAME file with
# GIT_DIR/GIT_WORK_TREE set was honoured (RC=0, GRANT_APPLIED). Both `subprocess.run` calls below
# pass a scrubbed env. THIS NARROWS THE HOLE; IT DOES NOT CLOSE IT — see F-A under KNOWN-OPEN.
GIT_ENV_SCRUB = (
    "GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_CEILING_DIRECTORIES",
    "GIT_OBJECT_DIRECTORY", "GIT_INDEX_FILE",
)


def _scrubbed_env() -> dict:
    """`os.environ` without the variables that let a caller nominate git's repository."""
    return {k: v for k, v in os.environ.items() if k not in GIT_ENV_SCRUB}

# `(?![0-9])` rather than `(?=[-_.]|$)`: the digits must simply be maximal. The old lookahead
# required a separator or end-of-name after the round number, so `D185D-r1fix-test-judge.md` — a
# real test-judge verdict — matched NOTHING and was dropped without a word. Version tokens stay
# safe because the alternation itself never matches a bare `v`.
ROUND_RE = re.compile(
    r"[-_.](?:r|round|fixround|rereview[-_.]?r|attempt)0*(\d+)(?![0-9])", re.IGNORECASE
)
# The KIND suffix after the round marker. A round is spent by a JUDGEMENT; the work that a
# judgement provokes is not a judgement. Tokens, not whole strings, so `fix-test-judge` (the tail
# of `-r1fix-test-judge`) still reads as a judge verdict and `tenancy-rls-validator` still reads as
# a validator. A review token anywhere in the tail wins: over-counting keeps the cap biting, while
# under-counting is the defect being repaired.
REVIEW_KIND_TOKENS = frozenset({
    "acceptance", "architect", "audit", "critique", "crosscheck", "judge", "judgement",
    "provider", "rereview", "reviewer", "review", "security", "tenancy", "validator", "verdict",
})
WORK_KIND_TOKENS = frozenset({
    "analysis", "brief", "card", "census", "design", "diagnosis", "escalation", "fix", "fixes",
    "handoff", "impl", "implementation", "ledger", "measurement", "notes", "plan", "report",
    "scout", "spec", "status", "summary",
})
# EVIDENCE COLLECTION WEARING A JUDGE'S NAME. This is the ONE place the "a review token anywhere
# in the tail wins" rule is inverted, so the inversion is named, bounded to one token, and
# justified by measurement rather than by argument.
#
# `test-judge` runs a command and reports its exit code. MEASURED across the four real repositories
# (59 review workspaces, 1,093 round-marked artifacts): 124 artifacts carry `test` in the kind
# position, ALL 124 are `-test-judge`, and their prose verdicts are 114 PASS / 2 FAIL / 1 with no
# VERDICT line — a 0.02 block rate against 0.16 for `reviewer`. A command's exit code is evidence,
# and evidence must not spend a round: that is the same rule NON_PROSE_SUFFIXES already applies to
# a JUnit XML, applied to the artifact that reports the same XML in prose.
#
# THE OBJECTION THAT HAD TO BE ANSWERED BEFORE THIS SHIPPED, because reclassifying a judge is
# exactly how a real blocking verdict goes silent: do the 2 FAILs disappear from the counter? They
# do NOT. Both were checked by name in the corpus, and each has a sibling REVIEW verdict at the
# SAME (subject, round) — `D185D-r1-test-judge.md` beside `D185D-r1-reviewer.md` and
# `-r1-security-validator.md`; `D201-BYPASS-SHAPE-HYGIENE-r1-test-judge.md` beside
# `-r1-reviewer.md` and `-r1-tenancy-rls-validator.md`. Every round a failing test-judge belongs to
# is still charged by an adjudicating verdict standing next to it. Nothing is hidden.
#
# WHAT THIS DOES NOT CLAIM, and the first draft of this comment claimed it wrongly. The
# discriminator reads the filename and nothing else, so a test-judge that is the SOLE charge at a
# (subject, round) stops that round being counted at all. THAT SHAPE DOES OCCUR: measured over the
# 59 workspaces, 124 artifacts stop charging and 8 (subject, round) pairs disappear entirely —
# THREE distinct artifacts, each the only verdict its round had. They were read. None is a BLOCK:
# one is a named baseline, one states `VERDICT ... UNDECIDED` in its own words, and the third
# carries NO verdict line at all — it prints a command, an exit code and a findings tally, which is
# the definition being applied here. So no blocking verdict goes silent ON THIS CORPUS. On another
# corpus it could, and the honest repair then is to name the artifact for the judgement it made
# (`-reviewer`, `-acceptance`), not to widen this set: the counter cannot read prose and must not
# start. FAMILY_SPEND and the artifact's own presence in the workspace remain visible either way.
EVIDENCE_KIND_TOKENS = frozenset({"test"})
# The subset of REVIEW_KIND_TOKENS that names a JUDGE unambiguously even with no round marker to
# mark off a suffix. With no marker there is no tail, so the WHOLE stem is searched, and only
# tokens that cannot appear innocently in a subject name belong here.
# EXACTLY TWO are excluded, and this list is the whole difference from REVIEW_KIND_TOKENS:
#   `review` — an ordinary noun; `reviews/T1-review.md` names a directory of them, not a verdict.
#   `audit`  — an ordinary noun; an access-audit note is not a judgement.
# The four short forms this repository actually writes (`security`, `tenancy`, `provider`,
# `crosscheck`) ARE included: `verdicts/ENTRY53-security.md` is a real marker-free judge verdict,
# and leaving it out made 27 of them invisible to both the counter and the warning.
JUDGE_NAME_TOKENS = frozenset({
    "acceptance", "architect", "critique", "crosscheck", "judge", "judgement", "provider",
    "rereview", "reviewer", "security", "tenancy", "validator", "verdict",
})
KIND_SPLIT_RE = re.compile(r"[-_.]+")
# Every token that names a KIND, on any side of the union. Used only by `trailing_kind_tokens`,
# which reads the kind that sits BEFORE a round marker rather than after it. `test` is included
# here after MEASURING that it re-keys NOTHING: across the 1,093 real round-marked artifacts there
# are ZERO `<subject>-test-r<N>.md` shapes, so adding it changes no subject key and no grant key,
# and it is present only so the kind-first form would classify if a project ever writes it.
KIND_TOKENS = REVIEW_KIND_TOKENS | WORK_KIND_TOKENS | EVIDENCE_KIND_TOKENS
# Non-prose artifacts are EVIDENCE, not judgements. A JUnit XML named `T4-R3-GREEN-*.xml`, a probe
# log, a captured diff or a source file dropped in the workspace carries a round marker only
# because it belongs to a round — reading it as a verdict charged 27 phantom rounds.
NON_PROSE_SUFFIXES = frozenset({".xml", ".txt", ".diff", ".tsx"})
# The TERMINAL pre-commit whole-diff pass. THIS PATTERN IDENTIFIES; IT NO LONGER AUTHORISES.
# What it does, exactly, in the two places that read it:
#   1. `subject_of` strips the marker, so `SUBJ-full-diff-reviewer.md` groups under `subj` instead
#      of becoming a phantom subject showing zero rounds spent. THIS IS THE LOAD-BEARING READER —
#      30 terminal-marked artifacts exist across the live workspaces and 7 ledger keys were written
#      against this derivation, so deleting the strip would re-key every one of them.
#   2. The walk and the --next branch recognise a terminal NAME — and a terminal name is one that
#      matches this pattern AND carries NO round marker, because a round marker makes it a scoped
#      round however it is spelled.
# What it no longer does: nothing is skipped, charged differently, or permitted because of it. The
# exemption that used to hang here was keyed on a token in a filename written by the party this
# control binds, it produced three occurrences of one mechanism, and two repairs relocated that
# mechanism rather than removing it. Founder gate ruling 2026-08-20, option 3: it is removed. A
# terminal pass beyond a spent budget is now permitted only by a `terminal` row in the grants
# ledger — data this tool reads, carrying attribution, greppable and versioned.
# THERE IS NO ONCE-PER-SUBJECT BOUND. This comment claimed one twice, in two different registers,
# and both claims were false — the second one ("no suffix, kind or token can keep an artifact out
# of it") was falsified by execution on the day it was written: a ROUND MARKER keeps it out, which
# is the very next clause of this same comment. What is true, exactly: `terminals` records the
# terminal artifacts THIS SCAN CAN SEE — unmarked ones, in the directory named on the command line,
# at the moment it ran. `--next` reports a second pass when the first is still visible. Deleting,
# renaming, moving or out-scoping the artifact makes it invisible, and the report goes quiet. See
# F-C under KNOWN-OPEN. The `terminal-spent` ledger row exists because a LEDGER LINE a human
# appends is the only record here that an artifact deletion cannot erase.
TERMINAL_RE = re.compile(r"[-_.]full[-_.]?diff(?=[-_.]|$)", re.IGNORECASE)
BANNED_PATTERNS = (
    (re.compile(r"\.(diff|patch)(\.[A-Za-z0-9]+)?$", re.IGNORECASE),
     "diff snapshot — name the commit range instead"),
    (re.compile(r"(^|[-_.])packet\.md$", re.IGNORECASE),
     "restatement packet — re-dispatch with the original paths"),
    (re.compile(r"invalid[-_]?attempt", re.IGNORECASE), "failed dispatch — one ledger line"),
    (re.compile(r"no[-_]?verdict", re.IGNORECASE), "failed dispatch — one ledger line"),
    (re.compile(r"no[-_]?progress", re.IGNORECASE), "failed dispatch — one ledger line"),
    (re.compile(r"\.raw$", re.IGNORECASE),
     "raw dump — the structured verdict beside it is the record (v3.1)"),
    (re.compile(r"(^|[-_.])prompt\.(md|txt)$", re.IGNORECASE),
     "persisted prompt — the ledger line names the dispatch recipe (v3.1)"),
)
GRANT_ROUND_RE = re.compile(r"^r0*(\d+)$", re.IGNORECASE)
# The round field of a row that authorises a TERMINAL pass instead of a numbered round. A word
# rather than a sentinel number: `r0` would sort and print as a round, and the receipt has to be
# able to count terminal passes apart from round grants.
GRANT_TERMINAL_TOKEN = "terminal"
# The row that records a terminal pass ALREADY TAKEN. It exists because the artifact-based record
# is erased by deleting the artifact (F-C, KNOWN-OPEN), and a ledger line is not. It is written BY
# A HUMAN — the tool prints the exact line and cannot append it, which is the honest shape of a
# control that cannot bind its own operator.
GRANT_TERMINAL_SPENT_TOKEN = "terminal-spent"
# The audit trail is the grant's whole claim to authority. A line missing any of the three is a
# bare assertion wearing the ledger's clothes, so it grants nothing.
GRANT_COMMIT_RE = re.compile(r"^[0-9a-fA-F]{7,40}$")
SEPARATOR_RE = re.compile(r"[-_.]+")
DEFAULT_GRANTS = Path(__file__).resolve().parent.parent / "ROUND-GRANTS.tsv"
FILE_BUDGET = 50
BYTE_BUDGET = 500 * 1024
# The width at which a round stops looking like coverage. See the WIDE_ROUND block in `main` for
# the measurement, and for why the STAGE half of the same rule is deliberately left in prose.
PANEL_WIDTH_WARN = 4


def trailing_kind_tokens(head: str) -> list[str]:
    """The recognised KIND tokens at the END of `head`, longest run first, never all of them.

    MEASURED, not supposed. The methodology mandates `<subject>-r<N>-<kind>.md`, and the kind
    reader below only ever looked AFTER the marker. Across 59 real review workspaces the tool
    emitted 264 UNCLASSIFIED_ROUND_ARTIFACT warnings; **129 of them carry a round marker that ENDS
    the name** — the projects write `<subject>-<kind>-r<N>.md`, kind FIRST. 70 of those 129 end in
    a token these very sets already recognise (`-review-r5` x50, `-security-r15` x15, `-fix-`,
    `-design-`, `-plan-`). The tool held the right vocabulary and read it in the wrong position:
    a WORD test where a STRUCTURE test was needed, which is the failure this repository has now
    recorded seven times.

    Two consequences, and the second is the load-bearing one:
      1. the kind is classifiable, so a judge verdict stops being charged as an unknown; and
      2. `subject_of` can take the kind OUT of the subject. Without that, one artifact reviewed by
         six kinds becomes six subjects each spending its own budget. This is not hypothetical:
         one real workspace shows `<subj>-spotless-amendment-{architecture,builder,contract,
         general,methodology,security}-rN`, six pseudo-subjects, 51 artifacts, rounds to r14.

    NEVER consumes the whole head. A subject that IS a kind word (`review-r1.md`) keeps its name;
    an empty subject key would collapse unrelated lineages into one bucket, which is the opposite
    of failing closed.
    """
    tokens = [t for t in KIND_SPLIT_RE.split(head.strip("-_.").lower()) if t]
    cut = len(tokens)
    while cut > 1 and tokens[cut - 1] in KIND_TOKENS:
        cut -= 1
    return tokens[cut:]


def subject_of(name: str) -> str:
    """Everything before the first round marker is the subject.

    Real lineages name the round then qualify it (`S2-01-R18-R1`, `T6b-round5-rereview`), so the
    tail after the first marker is round-specific and must not split the subject.

    When the marker ENDS the name the kind sits before it instead, and it is stripped too — see
    `trailing_kind_tokens`. Stripping can only MERGE subjects, never split one, so it can only
    raise a subject's spent count. It fails closed by construction.
    """
    stem = Path(name).stem
    m = ROUND_RE.search(stem)
    if m:
        head = stem[: m.start()]
        if not ROUND_RE.search(stem[m.end():]) and not stem[m.end():].strip("-_."):
            trailing = trailing_kind_tokens(head)
            for _ in trailing:
                head = SEPARATOR_RE.split(head.strip("-_."))
                head = "-".join(head[:-1])
        stem = head
    t = TERMINAL_RE.search(stem)
    if t:
        # A terminal pass belongs to its subject, not to a subject of its own. Without this,
        # `<subject>-full-diff-reviewer.md` would group as a separate subject showing zero rounds
        # spent — which is precisely the loophole the once-only rule below has to close.
        stem = stem[: t.start()]
    return stem.strip("-_.").lower()


def subject_families(keys) -> dict:
    """{root: sorted members} for every subject key that is a proper TOKEN-PREFIX of another.

    THE HOLE THIS ANSWERS: RENAMING A SUBJECT RESETS ITS BUDGET, and the per-subject counter cannot
    see it because it has only ever had one key per name. The real shape, from the corpus rather
    than from a hypothesis — a CODE FORMATTER prerequisite in one workspace:

        <card>-spotless-r15-dispatch-blocker
        <card>-spotless-amendment-{architecture,builder,contract,general,methodology}-r11..r14
        <card>-spotless-amendment-contract-{review-r1..r7, full-r7..r8, prerequisite-r9..r10}
        <card>-spotless-amendment-{plan,security}-{full,prerequisite,review}-r1..r10

    THIRTEEN subject keys, 51 artifacts, rounds spanning r1 to r15, ONE artifact being judged. Each
    key showed a small spend and the counter had no line that said 51.

    THE RULE, and why it is a STRUCTURE test and not a word test — the failure this repository has
    now recorded seven times is a checker that matched a WORD and saw nothing real. There is no
    vocabulary here at all. A lineage is renamed by APPENDING a qualifier, so:

        a subject key is a MEMBER of the family rooted at any subject key that is a proper prefix
        of it AT TOKEN BOUNDARIES, and that root must ITSELF be a subject key present in this scan.

    Requiring the root to be a live key is what keeps this conservative: `f009-static-plan` and
    `f009-static-sites` are NOT merged under an invented `f009`, because no artifact is named
    `f009` alone. Measured over all 59 real workspaces this produces 16 multi-member families, and
    the widest is the formatter card itself — it does not collapse the corpus into a few buckets.

    NESTED ROOTS ARE ALL REPORTED, not just the outermost. `<card>` is a family, `<card>-spotless`
    is a family inside it, `<card>-spotless-amendment-contract` is a family inside that. Eliding
    the inner ones would hide exactly the number the audit needed: 51 artifacts / 14 rounds sits at
    `<card>-spotless`, while the outermost root reports 76 / 16. This module's receipt does not
    summarise or threshold its findings, and this is the same commitment.

    NO KIND VOCABULARY IS WIDENED HERE. `prerequisite` is still not a kind and is still not
    stripped from a subject key — that pin is right and this works around it rather than through
    it, because the escape being measured is not confined to kind words: `full`, `builder`,
    `authority` and `methodology` are not kinds either and they reset the budget just as well.
    """
    tokens = {k: tuple(t for t in SEPARATOR_RE.split(k) if t) for k in keys}
    by_tokens = {}
    for key, tk in tokens.items():
        # Two keys cannot share a token tuple: the tuple is derived from the key. `setdefault`
        # only guards against a caller passing duplicates.
        by_tokens.setdefault(tk, key)
    families: dict[str, set] = {}
    for key, tk in tokens.items():
        for i in range(1, len(tk)):
            root = by_tokens.get(tk[:i])
            if root is not None and root != key:
                families.setdefault(root, {root}).add(key)
    return {root: sorted(members) for root, members in families.items()}


def kind_of(stem: str, mark: re.Match) -> str | None:
    """Classify the artifact from the kind suffix that follows its LAST round marker.

    Returns "review" (spends a round), "work" (does not), or None (kind unrecognised — the caller
    charges it as a review and reports it, because silence here is the defect this check carries).
    """
    tail = stem[mark.end():]
    tokens = {t for t in KIND_SPLIT_RE.split(tail.strip("-_.").lower()) if t}
    if not tokens:
        # The marker ENDS the name: the kind is written BEFORE it. 129 of the 264 unclassified
        # artifacts across the real workspaces have this shape. Reading the head here is the same
        # test on the same vocabulary, applied at the position the corpus actually uses.
        tokens = set(trailing_kind_tokens(stem[: mark.start()]))
    if tokens & EVIDENCE_KIND_TOKENS:
        # THE ONE PRECEDENCE INVERSION, and it is deliberately FIRST rather than folded into
        # WORK_KIND_TOKENS: a `test-judge` tail carries BOTH `test` and `judge`, and the
        # review-token-wins rule below would return "review" for it forever. Placing the test here
        # is the only way the reclassification actually takes effect, and putting it at the top of
        # the function is the only way a reader can see that it overrides the fail-closed default.
        # It is bounded to ONE token whose whole justification is measured; see EVIDENCE_KIND_TOKENS.
        return "work"
    if tokens & REVIEW_KIND_TOKENS:
        return "review"
    if tokens & WORK_KIND_TOKENS:
        return "work"
    return None


def looks_like_a_verdict(stem: str) -> bool:
    """True when a marker-free name identifies a judge verdict beyond reasonable doubt.

    Only the LAST token is consulted. The methodology mandates `<subject>-r<N>-<kind>.md`, so the
    kind is the trailing token, and a judge word appearing anywhere else belongs to the SUBJECT:
    `D206-CARD-VALIDATOR-DRIFT-AND-LOCATOR.yaml` is a card about validators, not a verdict. Reading
    the whole stem made this warning fire on it, and a warning that misreads its first real
    workspace is the defect this same review found in STALE_GRANT.
    """
    tokens = [t for t in KIND_SPLIT_RE.split(stem.strip("-_.").lower()) if t]
    return bool(tokens) and tokens[-1] in JUDGE_NAME_TOKENS


def _repo_toplevel(start: Path) -> Path | None:
    """The git toplevel containing `start`, or None if git cannot answer or there is no repo."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(start), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=10, env=_scrubbed_env(),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    return Path(proc.stdout.strip()).resolve()


def is_a_committed_authority(path: Path) -> tuple[bool, str]:
    """True only if `path` is committed inside THE SCRIPT'S OWN repository. Reason on failure.

    THIS REPLACED AN INDEX-MEMBERSHIP TEST THAT A `git init` DEFEATED. The old check ran
    `git ls-files --error-unmatch` in THE FILE'S OWN DIRECTORY, which asks whether the file sits in
    SOME index — a question the caller answers for themselves:

        mkdir /tmp/f && cd /tmp/f && git init -q && printf ... > g.tsv && git add g.tsv

    and `--grants /tmp/f/g.tsv` was honoured at exit 0 although the file existed in no commit at
    all. That mattered little while a filename token could buy the same thing for free; now that a
    terminal pass is a ledger row, THE LEDGER IS THE SOLE AUTHORITY FOR IT, and shipping the
    removal on a forgeable ledger would have traded a filename token for a `git init`.

    WHAT THIS IS WORTH, SAID BEFORE THE MECHANICS. It raises the price of a forged ledger from
    `git init` to "put your file in this repository and get it committed". It does not make one
    impossible, and it is a fence beside an open gate: the DEFAULT ledger is never git-queried at
    all, so the cheap route runs past this function entirely. See KNOWN-OPEN, F-A.

    Three questions, and all three must answer yes:
      * WHICH REPOSITORY. The ledger must resolve inside the toplevel containing THIS SCRIPT. A
        repository the caller creates around their own file is not the authority this control
        claims to consult; it is the caller, wearing git. This is the load-bearing half — the other
        can be satisfied with one more command.
      * ASKED OF THE RIGHT GIT. `GIT_DIR` and `GIT_WORK_TREE` let the caller answer "which
        repository" from the environment — reproduced, RC=1 became RC=0 with two variables. They
        are scrubbed from both subprocess calls, and the script asserts it is itself contained in
        the toplevel git named. STILL OPEN: a COPY of this script beside a caller's own committed
        ledger passes honestly, and `track()` in the tests ships that recipe.
      * COMMITTED, NOT MERELY STAGED. The path must exist at HEAD. An index is a private scratch
        space; review happens on commits, and "unreviewable is not an authority" is the whole
        argument for requiring git at all.

    WHAT THIS DELIBERATELY DOES NOT CHECK: that the working-tree CONTENT matches HEAD. An
    uncommitted edit to a committed ledger inside this repository still applies. That is the same
    exposure the DEFAULT ledger has by design (it is never git-queried at all, see read_grants),
    the barrier here is location rather than content, and a content test would refuse the ordinary
    flow of appending a grant line and running the check before committing it. Stated rather than
    implied, because a comment claiming a barrier the code does not raise is how the real one gets
    deleted later.

    HARNESS NOTE. Under a harness whose copy of this skill is not inside a git repository, no
    caller-named ledger can be resolved at all and every one of them is refused. That is
    fail-closed and it is confined to a path THE CALLER NAMED; the default ledger is never
    git-queried in any harness, so two byte-identical copies still agree about it.
    """
    top = _repo_toplevel(Path(__file__).resolve().parent)
    if top is None:
        return False, ("this copy of the skill is not inside a git repository that can be asked, "
                       "so a ledger named on the command line cannot be resolved against any "
                       "authority")
    # The containment `:298-301` asserted in PROSE and tested nowhere, now asserted in code. With
    # GIT_DIR/GIT_WORK_TREE scrubbed above, `top` should already be the toplevel that physically
    # holds this script; if it is not, git answered from somewhere this script does not live and
    # the answer is not usable. NARROWING, NOT A FIX — a caller who copies this script next to
    # their own committed ledger satisfies both halves honestly, and `tests` ship that recipe.
    if not Path(__file__).resolve().is_relative_to(top):
        return False, (f"git named {top} as the repository, but this script "
                       f"({Path(__file__).resolve()}) is not inside it — the repository was "
                       "answered from somewhere other than where this script lives")
    resolved = path.resolve()
    try:
        rel = resolved.relative_to(top)
    except ValueError:
        return False, (f"it resolves to {resolved}, outside the repository that holds this script "
                       f"({top}) — a repository the CALLER creates around their own file answers "
                       "`is this tracked` for itself, which is what `git init` buys")
    try:
        proc = subprocess.run(
            ["git", "-C", str(top), "cat-file", "-e", f"HEAD:{rel.as_posix()}"],
            capture_output=True, text=True, timeout=10, env=_scrubbed_env(),
        )
    except (OSError, subprocess.SubprocessError):
        return False, "git could not be asked whether it exists at HEAD"
    if proc.returncode != 0:
        return False, (f"`{rel.as_posix()}` does not exist at HEAD in {top} — `git add` alone "
                       "leaves it in an index, and an index is not a review")
    return True, ""


def read_grants(path: Path, is_default: bool, errors: list,
                warnings: list) -> tuple[dict, dict, dict]:
    """Parse the ledger into ({(subject, round): rec}, {subject: rec}, {subject: rec}).

    The THIRD map is the `terminal-spent` rows, and it is returned rather than kept local for one
    reason: it is the only durable record correction 3 creates, and a row whose subject key matches
    no `terminal` row would otherwise appear NOWHERE — not in the ledger counts, not in the receipt,
    and with no warning. A human who appended the printed line with a mistyped key (the keys are
    lower-cased and `-_.`-sensitive; see COLLIDING_SUBJECT_KEYS) would believe the spend was
    recorded, and the receipt could not contradict them.

    THREE ROW TYPES, ONE ATTRIBUTION VALIDATION. A round grant suppresses ROUND_CAP for the one
    (subject, round) pair it names. A `terminal` row authorises the terminal whole-diff pass for the
    one subject it names. A `terminal-spent` row records a pass already taken and withdraws the
    `terminal` row for that subject. All three are returned in SEPARATE MAPS so the receipt can
    report them apart, and all three pass through the identical attribution and duplicate checks
    below. (There is no wildcard CHECK: no row type has ever had wildcard syntax, so there is
    nothing to reject. The docstring used to name one, which read as a barrier and was not.)
    The terminal pass used
    to be authorised by a token in a filename, and the point of moving it here is that it now costs
    a REVIEWABLE LINE rather than a rename. It does not cost what a round grant costs: it authorises
    a dispatch and a round grant authorises none. A third row type, `terminal-spent`, records a pass
    already taken and withdraws the `terminal` row for that subject.

    FAIL CLOSED IS THE PARSER'S CONTRACT, and it is a contract about MALFORMED INPUT only. Every
    failure below — absent, unreadable, untracked, unparsable, unattributed, duplicated — yields NO
    grant for the affected pair, so a broken ledger never widens anything. That says nothing at all
    about a WELL-FORMED ledger line, which is trivially appendable: the DEFAULT ledger is never
    git-queried (see below), so a row added to the shipped file parses, applies, and prints no
    NON_DEFAULT_GRANTS. That is the ceiling on this whole design and it is stated in KNOWN-OPEN at
    the top of the module rather than defended against here.

    WHY THE COMMITTED-AUTHORITY TEST IS REQUIRED OF A NON-DEFAULT PATH ONLY. The threat is
    substitution: `--grants /tmp/forged.tsv` restores exactly the untracked, forgeable file the
    tracked-file design existed to rule out. The DEFAULT path cannot be substituted — it is resolved from the script's own
    location, not from anything a caller says — and its authority comes from shipping with the
    skill. It must NOT be git-queried at runtime, because the Codex mirror of this skill is
    git-ignored by that repository (`~/.codex/.gitignore`), so a tracked-ness test on the default
    would make two BYTE-IDENTICAL copies of this control return DIFFERENT verdicts on the same
    workspace. A control whose answer depends on which harness invoked it is not a control.
    """
    grants: dict[tuple[str, int], dict] = {}
    terminal_passes: dict[str, dict] = {}
    terminal_spent: dict[str, dict] = {}
    if not path.is_file():
        # Zero grants is already the strict state, so an absent ledger cannot widen anything.
        # An absent DEFAULT is silent: the ledger is operator data — founder decisions made on one
        # machine — and the vendored copy of this skill ships without it by invariant, so warning
        # on absence would make every machine without operator history noisy. An absent
        # CALLER-NAMED path still warns, because naming a path that is not there is a mistake.
        # The ERROR below is reserved for the one case that is an attempt to SUBSTITUTE an
        # authority rather than to name a missing one.
        if not is_default:
            warnings.append({
                "kind": "GRANTS_FILE_MISSING", "path": str(path),
                "why": "no grant is in force; the round cap runs at full strength",
            })
        return grants, terminal_passes, terminal_spent
    if not is_default:
        ok, why = is_a_committed_authority(path)
        if not ok:
            errors.append({
                "kind": "GRANTS_FILE_UNTRACKED", "path": str(path),
                "why": f"this ledger is not a committed authority: {why}. It is unreviewable and "
                       "is therefore not an authority — the untracked, forgeable file the "
                       "committed-file design was chosen to rule out, reached one flag further "
                       "away. NO GRANT OR TERMINAL PASS FROM THIS FILE IS IN FORCE; commit the "
                       "ledger inside this skill's own repository, or use the default one",
            })
            return grants, terminal_passes, terminal_spent
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        errors.append({
            "kind": "GRANTS_FILE_UNREADABLE", "path": str(path),
            "why": f"{type(exc).__name__}: {exc} — no grant is in force; reported as a finding "
                   "rather than a traceback so a --json caller still gets parsable output",
        })
        return grants, terminal_passes, terminal_spent

    for lineno, raw in enumerate(text.splitlines(), 1):
        line = f"{path}:{lineno}"
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        fields = raw.split("\t")
        bad = None
        rnd = None
        terminal_row = False
        spent_row = False
        if len(fields) < 5:
            bad = "expected SUBJECT<TAB>r<N>|terminal<TAB>commit<TAB>date<TAB>reason"
        elif not fields[0].strip():
            bad = "empty subject key"
        elif fields[1].strip().lower() == GRANT_TERMINAL_SPENT_TOKEN:
            spent_row = True
        elif fields[1].strip().lower() == GRANT_TERMINAL_TOKEN:
            terminal_row = True
        elif GRANT_ROUND_RE.match(fields[1].strip()):
            rnd = int(GRANT_ROUND_RE.match(fields[1].strip()).group(1))
        else:
            bad = (f"round token {fields[1].strip()!r} is not `r<N>`, `terminal` or "
                   "`terminal-spent`")
        if bad:
            pass
        elif not GRANT_COMMIT_RE.match(fields[2].strip()):
            bad = (f"commit field {fields[2].strip()!r} is not a git hash (7-40 hex); a grant "
                   "with no verifiable recording commit is a bare assertion")
        elif not fields[3].strip():
            bad = "empty date field; the audit trail is the grant's claim to authority"
        elif not fields[4].strip():
            bad = "empty reason field; the audit trail is the grant's claim to authority"
        if bad:
            warnings.append({
                "kind": "GRANT_LINE_MALFORMED", "path": line,
                "why": f"{bad} — this line grants nothing",
            })
            continue
        subj_key = fields[0].strip().lower()
        record = {
            "subject": subj_key, "commit": fields[2].strip(),
            "date": fields[3].strip(), "reason": fields[4].strip(), "line": line,
        }
        if spent_row:
            # The RECORD OF A PASS ALREADY TAKEN. It authorises nothing; it withdraws a `terminal`
            # row for the same subject, wherever in the file that row sits (the withdrawal is
            # applied after the whole file is parsed, below, so line order carries no meaning).
            # Duplicates are harmless here — spent twice is spent — so the first simply stands.
            record["round"] = None
            terminal_spent.setdefault(subj_key, record)
            continue
        if terminal_row:
            # The SUBJECT is the whole key, so the ledger can express at most one standing
            # `terminal` row per subject — a property of this dict, NOT a bound on how many
            # terminal dispatches happen (see F-C). A second row is the same defect a second
            # round-grant line is: two records disagreeing about one decision.
            if subj_key in terminal_passes:
                warnings.append({
                    "kind": "DUPLICATE_TERMINAL_PASS", "path": line, "subject": subj_key,
                    "why": f"a terminal pass for `{subj_key}` is already recorded at "
                           f"{terminal_passes[subj_key]['line']}; the FIRST line stands and this "
                           "one is ignored — two lines for one decision make the ledger disagree "
                           "with itself about which one is in force",
                })
                continue
            record["round"] = None
            terminal_passes[subj_key] = record
            continue
        key = (subj_key, rnd)
        if key in grants:
            # Keep the FIRST. Last-wins let a second line silently replace the real grant, so
            # `grep -c` on the ledger disagreed with what actually fired.
            warnings.append({
                "kind": "DUPLICATE_GRANT", "path": line, "subject": key[0], "round": key[1],
                "why": f"({key[0]}, r{key[1]}) is already granted at {grants[key]['line']}; the "
                       "FIRST line stands and this one is ignored — two lines for one pair make "
                       "the ledger disagree with itself about which decision is in force",
            })
            continue
        record["round"] = rnd
        grants[key] = record

    # CORRECTION 3, the withdrawal. A `terminal` row for a subject the ledger already records as
    # `terminal-spent` grants NOTHING. This is the only part of the terminal record that survives
    # a caller deleting the artifact — and it survives only because a HUMAN appended the line.
    for subj_key in sorted(set(terminal_passes) & set(terminal_spent)):
        row, spent = terminal_passes.pop(subj_key), terminal_spent[subj_key]
        # Recorded AT THE POP. Deriving it later as `subj not in terminal_passes` reads True for an
        # ORPHAN spend row as well — the exact row this map was returned to make visible.
        spent["withdrew_a_row"] = True
        warnings.append({
            "kind": "TERMINAL_PASS_ALREADY_SPENT", "path": spent["line"], "subject": subj_key,
            "commit": spent["commit"],
            "why": f"the terminal pass on `{subj_key}` authorised at {row['line']} is recorded as "
                   f"ALREADY SPENT at {spent['line']} ({spent['commit']}, {spent['date']}): "
                   f"{spent['reason']} — the `terminal` row grants nothing further IN THIS "
                   "LEDGER, ON THIS RUN. That is the whole of the claim: this row is the record "
                   "an artifact deletion cannot erase, and it is not a bound. The default ledger "
                   "is never git-queried, so the party this reports on can delete the line, name "
                   "another ledger, or run another copy of the script",
        })
    return grants, terminal_passes, terminal_spent


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("workspace", type=Path)
    ap.add_argument("--max-round", type=int, default=2,
                    help="the round budget (default 2). NOT the grant vehicle: it is global, so "
                         "raising it here raises it for every subject in the invocation. Record a "
                         "founder grant in the grants file instead.")
    ap.add_argument("--next", action="append", default=[], metavar="SUBJECT",
                    help="subject about to be dispatched; refused if its round budget is spent")
    ap.add_argument("--grants", type=Path, default=None, metavar="PATH",
                    help=f"tracked round-grant ledger (default {DEFAULT_GRANTS}). A line may only "
                         "SUPPRESS ROUND_CAP for the exact (subject, round) pair it names.")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if not args.workspace.is_dir():
        print(f"ERROR: not a directory: {args.workspace}", file=sys.stderr)
        return 2

    errors, warnings = [], []
    grants_path = (args.grants or DEFAULT_GRANTS).expanduser()
    is_default = grants_path.resolve() == DEFAULT_GRANTS.resolve()
    if not is_default:
        warnings.append({
            "kind": "NON_DEFAULT_GRANTS", "path": str(grants_path),
            "why": "the round grants were read from a ledger this invocation named, not from the "
                   "one that ships with the skill — the authority was chosen by the caller",
        })
    grants, terminal_passes, terminal_spent = read_grants(
        grants_path, is_default, errors, warnings)
    # charged[subject][round] = path — EVERY charged round, not only the highest. Keying the grant
    # lookup on a per-subject MAXIMUM let one grant line at the top round absorb every lower
    # ungranted over-cap round on the same key, which is precisely "a pair the line does not name".
    charged: dict[str, dict[int, str]] = {}
    # HOW MANY JUDGEMENTS, not how many (subject, round) PAIRS. `charged` keeps ONE path per pair,
    # so summing its lengths counts pairs and would report the 51-artifact formatter family as 50.
    # A number that is off by one against the corpus it claims to measure is how a receipt stops
    # being checkable, so the count is kept separately and counts files.
    charged_files: dict[str, int] = {}
    # EVERY charged review artifact filed against one (subject, round), not just the first. The
    # `charged` map above keeps one path per round because that is all a CAP needs; the WIDTH of a
    # round is a different question about the same walk and needs the whole list.
    round_width: dict[tuple[str, int], list[str]] = {}
    seen_rounds: dict[str, set[int]] = {}
    seen_subjects: set[str] = set()
    terminals: dict[str, str] = {}
    n_files, n_bytes = 0, 0

    for path in sorted(args.workspace.rglob("*")):
        if not path.is_file():
            continue
        rel = str(path.relative_to(args.workspace))
        n_files += 1
        n_bytes += path.stat().st_size

        banned = False
        banned_why = None
        if "prompts" in path.relative_to(args.workspace).parts[:-1]:
            banned_why = "persisted prompt — the ledger line names the dispatch recipe (v3.1)"
        else:
            for pattern, why in BANNED_PATTERNS:
                if pattern.search(path.name):
                    banned_why = why
                    break
        if banned_why:
            errors.append({"kind": "BANNED_CLASS", "path": rel, "why": banned_why})
            banned = True

        stem = Path(path.name).stem
        subj = subject_of(path.name)
        seen_subjects.add(subj)

        marks = list(ROUND_RE.finditer(stem))

        # THE TERMINAL RECORD. Note what this is NOT: there is no `continue` here, no branch, no
        # suppression of any kind. A terminal artifact is recorded and then classified by exactly
        # the same code as every other file — it may be charged, warned about, or ignored on its
        # own merits. The rule this obeys, stated so it survives the next edit: a suppression must
        # never run before the bookkeeping it does not intend to skip. THE PREVIOUS TWO ATTEMPTS
        # OBEYED IT BY REORDERING, and reordering is what moved the defect each time — first the
        # suffix filter jumped the record, then the record jumped `charged`.
        #
        # THE SCOPE OF THAT, STATED TRUTHFULLY, because this comment used to end "the only    [retracted-quote]
        # version of this that cannot recur" and OCCURRENCE FOUR WAS WRITTEN FIFTEEN LINES BELOW   [retracted-quote]
        # IT. What
        # is true: nothing orders ahead of `terminals`, so the TERMINAL record cannot be jumped.
        # `charged` is a different matter and still sits behind three `continue`s further down —
        # the non-prose branch, the marker-free branch and the work-kind branch — and the non-prose
        # one is exactly where occurrence four lived. This ordering is settled for one of the two
        # records, not for the mechanism, and the mechanism is open by ruling.
        #
        # A terminal name is one that carries the marker AND NO ROUND MARKER. A round marker makes
        # the artifact a scoped round however it is spelled, so `SUBJ-r3-full-diff-reviewer.md`
        # falls straight through to be charged as r3 — which is the whole of the defect where a
        # substring in three filenames spent three rounds and the tool printed the word `clean`.
        terminal_artifact = bool(TERMINAL_RE.search(stem)) and not marks
        if terminal_artifact:
            terminals.setdefault(subj, rel)
            if subj not in terminal_passes:
                warnings.append({
                    "kind": "UNRECORDED_TERMINAL_PASS", "path": rel, "subject": subj,
                    "why": "a terminal whole-diff pass for this subject is in the workspace, and "
                           "the ledger records no `terminal` row for it. Not an error — the "
                           "ledger spans milestones and this scan is one directory — but a "
                           "terminal pass no founder decision records is precisely what the "
                           "removed filename exemption used to permit, silently and unlimited",
                })
        # Evidence of the round exists on disk whatever the file's kind or suffix, and a BANNED
        # artifact still charges its round below — so both must reach `seen_rounds`, or a grant
        # that is genuinely needed reads as stale and the tool advises removing it.
        if marks:
            seen_rounds.setdefault(subj, set()).add(max(int(m.group(1)) for m in marks))

        if path.suffix.lower() in NON_PROSE_SUFFIXES:
            # Evidence, not a judgement: a JUnit XML, a probe log or a source file is not charged.
            # But it is not dropped in SILENCE either — dropping it silently made the budget
            # evadable by choosing a suffix, which is the self-certifying class frozen as dead.
            # FAIL-CLOSED POLARITY, the one already used for charging at UNCLASSIFIED_ROUND_
            # ARTIFACT below: everything that is not positively identified as WORK is named. The
            # earlier `== "review"` test covered only kinds already recognised, so an unrecognised
            # kind on a non-prose suffix — `AUTHZ-B7b-r1-opinion.txt`, the case charged in the
            # prose branch PRECISELY to fail closed — went uncharged AND unwarned. Two messages
            # rather than one, because the two cases are genuinely different findings: one reads
            # as a verdict, the other cannot be read at all.
            # An UNMARKED non-prose file belongs to no round and is not classified at all —
            # only a round-marked one raises the question this branch answers.
            kind = kind_of(stem, marks[-1]) if marks else "work"
            if kind == "review":
                # CORRECTION 1 (occurrence FOUR). This was a `warnings.append`, and warnings do
                # not change the exit code: `SUBJ-r1/-r2/-r3-reviewer.txt` returned RC=0 with
                # three of these printed, while the identical files as `.md` returned RC=1. Three
                # review rounds bought with a file extension, announced each time.
                #
                # IT IS PROMOTED TO AN ERROR AND DELIBERATELY NOT CHARGED. Charging it instead was
                # considered and rejected by the bypass lens: `T-r2-provider.tsx` and
                # `-security.tsx` are SOURCE FILES carried in as evidence, and charging would have
                # spent real rounds on them. So the round is not spent and the dispatch stops —
                # the reader decides which of the two the file actually is.
                errors.append({
                    "kind": "NON_PROSE_VERDICT", "path": rel,
                    "why": "reads as a judge verdict at a round but carries a non-prose suffix, "
                           f"so it is NOT charged ({', '.join(sorted(NON_PROSE_SUFFIXES))} are "
                           "evidence, not judgements) — and an uncharged verdict is a free round, "
                           "so it stops the dispatch instead. Rename it `.md` if it is a verdict; "
                           "give it a work kind (`-evidence`, `-notes`) if it is evidence",
                })
            elif kind is None:
                warnings.append({
                    "kind": "NON_PROSE_UNCLASSIFIED", "path": rel,
                    "why": "carries a round marker and a non-prose suffix but no recognised kind, "
                           "so this tool cannot tell a judge verdict from a probe log. It is NOT "
                           "charged, and unlike its prose twin it CANNOT fail closed by charging "
                           "— the suffix rule exists to stop evidence spending rounds. So it is "
                           "named instead: rename it `<subject>-r<N>-<kind>.md` if it is a "
                           "verdict, or give it a recognised work kind if it is evidence",
                })
            continue

        if not marks:
            # A banned artifact is already an error; do not also report it as a naming drift.
            # A terminal pass carries no round marker BY DESIGN, and has already been reported
            # above on its own terms. Naming it here too would hand it the one piece of advice
            # that is actually wrong for it — "rename it `<subject>-r<N>-<kind>.md`" would convert
            # a terminal pass into a scoped round. This picks the accurate message; it is not an
            # exemption, and it skips no bookkeeping: MISSING_ROUND_MARKER charges nothing and
            # records nothing, and `terminals` was populated before any of this ran.
            if not banned and not terminal_artifact:
                if looks_like_a_verdict(stem):
                    warnings.append({
                        "kind": "MISSING_ROUND_MARKER", "path": rel,
                        "why": "names a judge verdict but carries no round marker, so the counter "
                               "cannot tell which round it belongs to and charges it NOTHING — "
                               "rename it `<subject>-r<N>-<kind>.md`; an unrecognised kind has "
                               "always warned and a missing marker used not to, which made the "
                               "silent failure the costly one",
                    })
            continue
        rnd = max(int(m.group(1)) for m in marks)
        kind = kind_of(stem, marks[-1])
        if kind == "work":
            continue  # a fix brief or an implementer's report is not a review round
        if kind is None:
            warnings.append({
                "kind": "UNCLASSIFIED_ROUND_ARTIFACT", "path": rel,
                "why": "carries a round marker but no recognised kind suffix; charged as a REVIEW "
                       "round to fail closed — rename it `<subject>-r<N>-<kind>.md` so the counter "
                       "can tell a judge verdict from the fix it provoked",
            })
        charged.setdefault(subj, {}).setdefault(rnd, rel)
        charged_files[subj] = charged_files.get(subj, 0) + 1
        round_width.setdefault((subj, rnd), []).append(rel)

    for raw in args.next:
        subj = subject_of(raw)
        next_stem = Path(raw).stem
        # A terminal DISPATCH, on the same definition the walk uses: the marker and no round
        # marker. `--next SUBJ-r4-full-diff-reviewer` is a fourth scoped round wearing the token
        # and is refused below like any other.
        is_terminal = bool(TERMINAL_RE.search(next_stem)) and not ROUND_RE.search(next_stem)
        # NO ROUND GRANT IS CONSULTED HERE, deliberately. A round grant suppresses the standing
        # scan so the WORKSPACE is not blocked by a round already granted and already taken; it
        # never hands the granted subject another dispatch. Reading round grants here would turn a
        # suppression into a cap raise, which is the one thing the ruling forbids. A `terminal`
        # row is different in kind and is read: it authorises a DISPATCH and nothing else, which
        # is why it is read only for a name carrying no round marker. How often it is taken is
        # F-C, and this comment used to answer that question wrongly — five lines above the
        # message that answered it wrongly too, and was corrected while this was not.
        spent = max(charged.get(subj, {0: ""}), default=0)
        rel = charged.get(subj, {}).get(spent, "")
        excused = False
        if is_terminal:
            spent_terminal = terminals.get(subj)
            if spent_terminal:
                errors.append({
                    "kind": "TERMINAL_PASS_SPENT", "subject": subj, "round": 0,
                    "path": spent_terminal,
                    # THIS STRING IS READ BY AN OPERATOR AND CARRIED INTO THE RECEIPT, so it
                    # must not assert a bound the module retracts 700 lines above it. It said
                    # "permitted ONCE per subject", which is exactly the claim KNOWN-OPEN   [retracted-quote]
                    # F-C withdraws — refile the verdict with a round marker, delete it, move it, or
                    # name a narrower workspace, and this error does not fire at all.
                    "why": "a terminal whole-diff artifact for this subject is ALREADY IN THIS "
                           "SCANNED DIRECTORY, so a further review is a scoped round and must "
                           "respect --max-round. This reports the pass it can SEE; the bound is "
                           "NOT once-per-subject (see F-C under KNOWN-OPEN) — the artifact this "
                           "reads is written, named and deletable by the dispatching party",
                })
                excused = True
            elif subj in terminal_passes:
                row = terminal_passes[subj]
                warnings.append({
                    "kind": "TERMINAL_PASS_APPLIED", "path": row["line"], "subject": subj,
                    "commit": row["commit"],
                    "why": f"the terminal whole-diff pass on `{subj}` is authorised by the row "
                           f"recorded at {row['commit']} ({row['date']}): {row['reason']} — the "
                           "round budget is not consulted for this dispatch, and this is the only "
                           "thing that row may do",
                })
                # CORRECTION 3. The only record of this pass is the artifact it will produce, and
                # an artifact is deleted, renamed or scanned around by the same party this control
                # is meant to report on (F-C, reproduced: three consecutive RC=0 on one row). A
                # LEDGER LINE is not. The tool prints the exact line and CANNOT append it — it has
                # no business writing to the authority it reads, and the whole point of the ledger
                # is that a human recorded the decision. So this is advice, and it is advice the
                # receipt carries to the merge gate where the actual control lives.
                spend_line = "\t".join([
                    subj, GRANT_TERMINAL_SPENT_TOKEN, row["commit"],
                    datetime.date.today().isoformat(),
                    f"terminal pass taken against {args.workspace.resolve()}; authorised by the "
                    f"row at {row['line']}",
                ])
                warnings.append({
                    "kind": "TERMINAL_SPEND_UNRECORDED", "path": row["line"], "subject": subj,
                    "append_line": spend_line,
                    "why": "this pass is now spent, and the only thing recording it is an "
                           "artifact the dispatched party writes and can delete. APPEND THIS "
                           f"LINE TO {grants_path} SO THE SPEND SURVIVES:  {spend_line}",
                })
                excused = True
            # NO `else`. A terminal name with no row buys NOTHING: the ordinary refusal below
            # runs, which is the entire point of removing the exemption.
        if not excused and spent >= args.max_round:
            errors.append({
                "kind": "ROUND_BUDGET_EXHAUSTED", "subject": subj, "round": spent, "path": rel,
                "why": f"subject has spent {spent} of {args.max_round} round(s); refuse this "
                       "dispatch and escalate to the owning gate with the escalation brief",
            })

    for subj, by_round in sorted(charged.items()):
        over = sorted(r for r in by_round if r > args.max_round)
        if not over:
            continue
        # EVERY over-cap round must be named, or the subject still blocks. A grant suppresses the
        # pair it names and nothing else, so a subject carrying r3 and r4 with only r4 granted is
        # still capped — otherwise one line at the top round would confer a pass on lower rounds
        # no founder decision ever mentions, and under the known subject MERGE it would confer it
        # across a lineage the line cannot even see.
        ungranted = [r for r in over if (subj, r) not in grants]
        for rnd in over:
            grant = grants.get((subj, rnd))
            if grant:
                warnings.append({
                    "kind": "GRANT_APPLIED", "path": grant["line"], "subject": subj, "round": rnd,
                    "commit": grant["commit"], "artifact": by_round[rnd],
                    "why": f"round {rnd} on `{subj}` is over the budget of {args.max_round} and is "
                           f"suppressed by the grant recorded at {grant['commit']} "
                           f"({grant['date']}): {grant['reason']}",
                })
        if not ungranted:
            continue
        top = max(over)
        errors.append({
            "kind": "ROUND_CAP", "subject": subj, "round": top,
            "path": by_round[max(ungranted)], "ungranted": ungranted,
            "why": f"round(s) {', '.join(f'r{r}' for r in ungranted)} exceed the budget of "
                   f"{args.max_round} and are named by no grant; "
                   "escalate to the owning gate — do not dispatch",
        })

    # ------------------------------------------------------------------ THE FAMILY VIEW
    # ADVISORY BY CONSTRUCTION, and that is not an accident of implementation. Founder gate ruling
    # 2026-08-20 (module docstring, first line): this instrument makes spend VISIBLE and does not
    # bind its operator. So the family spend is a WARNING and appears in the receipt; it raises no
    # error, changes no exit code, and is NOT consulted by the `--next` refusal above. Measured
    # over the 59 real workspaces: NO workspace changes its exit code because of this block.
    #
    # Making the true number visible is the whole job. The per-subject `rounds_charged` map is left
    # exactly as it was — the family is reported ALONGSIDE it, never instead of it, because the
    # per-subject line is what a grant key is written against and re-keying it would silently
    # re-key every grant line in the ledger (the same reason COLLIDING_SUBJECT_KEYS reports only).
    next_subjects = {subject_of(raw) for raw in args.next}
    families = []
    for root, members in sorted(subject_families(set(charged)).items()):
        rounds = sorted({r for m in members for r in charged[m]})
        n_artifacts = sum(charged_files.get(m, 0) for m in members)
        families.append({
            "root": root, "members": members, "rounds": rounds,
            "distinct_rounds": len(rounds), "max_round": max(rounds),
            "charged_artifacts": n_artifacts,
            "next": sorted(next_subjects & set(members)),
        })
    for fam in families:
        # TWO METRICS, because one of them is blind to the escape the other one catches.
        #   `charged_artifacts` counts JUDGEMENTS and is RESET-PROOF: a rename that restarts the
        #      numbering at r1 leaves the round span unchanged and this count still climbs.
        #   `distinct_rounds` counts the ROUND SPAN and is RENAME-PROOF in the other direction: a
        #      lineage that keeps counting up under new names shows its true reach here.
        # The formatter family scores 51 and 14 on these two. Either exceeding the budget is the
        # finding; requiring both would have missed whichever escape was used.
        if fam["distinct_rounds"] <= args.max_round and fam["charged_artifacts"] <= args.max_round:
            continue
        warnings.append({
            "kind": "FAMILY_SPEND", "path": fam["root"], "subject": fam["root"],
            "members": fam["members"], "rounds": fam["rounds"],
            "charged_artifacts": fam["charged_artifacts"],
            "why": f"`{fam['root']}` and {len(fam['members']) - 1} longer name(s) built on it are "
                   f"ONE lineage by token prefix, and together they carry "
                   f"{fam['charged_artifacts']} charged review artifact(s) across "
                   f"{fam['distinct_rounds']} distinct round(s) "
                   f"({', '.join(f'r{r}' for r in fam['rounds'])}), against a budget of "
                   f"{args.max_round}: {', '.join(fam['members'])}. Renaming a subject gives it a "
                   "fresh budget, so no per-subject line above states this total. ADVISORY — this "
                   "changes no exit code and does not refuse a dispatch; it is the number the "
                   "merge gate needs in order to see one long loop instead of several short ones"
                   + (f". THE --next SUBJECT(S) {', '.join(fam['next'])} ARE IN THIS FAMILY."
                      if fam["next"] else ""),
        })

    # THE WIDTH OF A ROUND, reported because the methodology's review rule changed under it.
    #
    # The rule used to be "one reviewer, never a panel" at every stage. It is now scoped by STAGE:
    # a panel of up to three DIFFERENT LENSES at design and plan, one reviewer plus `test-judge` at
    # implementation. The half of that rule this tool can honestly see is the CEILING, and it can
    # see it because width is a fact about a directory — how many charged review artifacts carry
    # one subject and one round — rather than a claim by the party filing them.
    #
    # MEASURED ON THE REAL CORPUS BEFORE THIS WAS WRITTEN, which is the only reason it is here.
    # 1,203 round-marked prose artifacts across four repositories group into 672 (subject, round)
    # groups under THIS MODULE'S OWN `subject_of`. 78 of those groups are four or more wide, and
    # they produced a blocking verdict in 8 of the 78 (0.10). The 594 groups at three or fewer
    # produced one in 190 (0.32) — a fourth lens is three times less likely to return a block than
    # the lenses already on the artifact. So this fires 78 times on the real fleet. It is not a
    # check that only its own fixtures can trip.
    #
    # WHAT IT DELIBERATELY DOES NOT DO, and this is the load-bearing part of the comment. It does
    # NOT infer the STAGE. Stage is the stronger half of the finding — design/plan blocks at 0.74
    # per artifact against 0.09 at implementation — and it is exactly the half this tool cannot
    # read. There is no stage on disk. Deriving it means testing filenames for the words `design`,
    # `plan` or `spec`, and this repository has now shipped NINE checkers that tested a WORD where
    # a STRUCTURE was needed and were inert or wrong against the real corpus. It was measured
    # rather than assumed here too: two reasonable spellings of the same stage word-test, run over
    # the same 1,203 artifacts, disagreed about 31 groups and moved the design bucket by 13%. A
    # classifier that moves 13% between two honest spellings of one rule is not a foundation for an
    # exit code, so the stage rule stays PROSE — a human reading this receipt at the merge gate is
    # what acts on it, with `test_the_two_documents_do_not_contradict_each_other_on_review_width`
    # doing the one mechanical thing available: stopping the two documents drifting apart again.
    #
    # A WARNING, never an error. The threshold is a yield observation and not a boundary: a
    # four-wide DESIGN round is correct under the new rule and blocked in 3 of the 7 measured, so
    # promoting this to an exit code would refuse the very panel the rule now asks for.
    for (subj, rnd), paths in sorted(round_width.items()):
        if len(paths) < PANEL_WIDTH_WARN:
            continue
        warnings.append({
            "kind": "WIDE_ROUND", "subject": subj, "round": rnd,
            "path": sorted(paths)[0], "width": len(paths), "artifacts": sorted(paths),
            "why": f"{len(paths)} charged review artifacts are filed against `{subj}` r{rnd}. "
                   f"Measured across four repositories, a round {PANEL_WIDTH_WARN} or more wide "
                   "returned a blocking verdict in 8 of 78 (0.10) against 190 of 594 (0.32) at "
                   "three or fewer. Review WIDTH is scoped by STAGE: a panel belongs at design "
                   "and plan, and implementation takes one reviewer plus `test-judge`. This tool "
                   "cannot read the stage off a filename and does not try, so this is a receipt "
                   "line for the merge gate and never an exit code",
        })

    for subj, rnd in sorted(grants):
        # Only for a subject this workspace actually holds. The ledger spans milestones; a grant
        # for a subject sealed elsewhere is out of scope here, and warning about it in every
        # unrelated workspace would make the signal worthless.
        if subj not in seen_subjects or rnd in seen_rounds.get(subj, set()):
            continue
        g = grants[(subj, rnd)]
        warnings.append({
            "kind": "STALE_GRANT", "path": g["line"], "subject": subj, "round": rnd,
            "why": f"subject `{subj}` is present but carries no artifact at round {rnd} IN THIS "
                   "WORKSPACE, so the grant suppresses nothing here. This is a scope report, NOT "
                   "a defect: the ledger is global and the scan is one directory, so a sealed or "
                   "sibling artifact reads the same way. DO NOT DELETE THE LINE — it records a "
                   "founder decision, and removing it re-arms ROUND_CAP wherever the artifact "
                   "actually lives",
        })

    buckets: dict[str, set[str]] = {}
    for key in seen_subjects | {subj for subj, _ in grants} | set(terminal_passes):
        buckets.setdefault(SEPARATOR_RE.sub("-", key), set()).add(key)
    for norm, keys in sorted(buckets.items()):
        if len(keys) > 1:
            warnings.append({
                "kind": "COLLIDING_SUBJECT_KEYS", "path": norm, "keys": sorted(keys),
                "why": f"{sorted(keys)} differ only in -_. and are therefore {len(keys)} separate "
                       "subjects with separate budgets and separate grant keys; reported only, "
                       "because re-keying subject derivation would silently re-key every grant",
            })

    if n_files > FILE_BUDGET or n_bytes > BYTE_BUDGET:
        warnings.append({
            "kind": "WORKSPACE_BUDGET", "files": n_files, "bytes": n_bytes,
            "why": f"workspace at {n_files} files / {n_bytes // 1024} KB exceeds "
                   f"~{FILE_BUDGET} files / {BYTE_BUDGET // 1024} KB — record as a "
                   "process regression in the milestone receipt",
        })

    # Terminal passes are counted APART from round grants, so a milestone receipt can say how
    # many of each were spent. They used to cost a filename token and therefore could not be
    # counted at all.
    # `terminal_passes` counts rows still IN FORCE — a row withdrawn by a `terminal-spent` row was
    # popped. `terminal_spent` is counted separately and is never popped, so a spend recorded
    # against a subject with no matching `terminal` row (a mistyped key, most likely) is still
    # visible here rather than silently absent.
    ledger = {"path": str(grants_path), "default": is_default,
              "entries": len(grants) + len(terminal_passes) + len(terminal_spent),
              "round_grants": len(grants), "terminal_passes": len(terminal_passes),
              "terminal_spent": len(terminal_spent)}
    # THE RECEIPT. This is the point of the tool. The exit code is a tripwire against forgetting;
    # THE BINDING CONTROL IS A HUMAN READING THIS BLOCK AT THE MERGE GATE, which is why nothing
    # here is summarised, thresholded or elided. Every warning appears VERBATIM — a receipt that
    # aggregates its warnings reproduces the failure that made four of them change nothing.
    #
    # `script` and `workspace` are here because both are chosen by the caller and neither was
    # reportable before: the ledger is resolved against the SCRIPT's repository (so which copy ran
    # decides which ledgers are authorities, F-A) and every count below is scoped to the WORKSPACE
    # argument (so naming a subdirectory silences findings). A receipt that cannot say which
    # script judged which directory cannot be audited.
    receipt = {
        "script": str(Path(__file__).resolve()),
        "workspace": str(args.workspace.resolve()),
        "max_round": args.max_round,
        "next": list(args.next),
        "rounds_charged": {subj: {str(r): p for r, p in sorted(by_round.items())}
                           for subj, by_round in sorted(charged.items())},
        # EVERY family, not only the ones that warn. A family under budget is the evidence that the
        # clustering is not merging unrelated lineages, and a receipt that printed only the
        # families it complained about could not be checked against the workspace it read.
        "families": families,
        "grants_applied": [
            {"subject": w["subject"], "round": w["round"], "commit": w["commit"],
             "artifact": w.get("artifact", ""), "line": w["path"],
             "reason": grants[(w["subject"], w["round"])]["reason"]}
            for w in warnings if w["kind"] == "GRANT_APPLIED"
        ],
        "terminal_passes_applied": [
            {"subject": w["subject"], "commit": w["commit"], "line": w["path"],
             "reason": terminal_passes[w["subject"]]["reason"]}
            for w in warnings if w["kind"] == "TERMINAL_PASS_APPLIED"
        ],
        "terminal_spend_to_record": [
            w["append_line"] for w in warnings if w["kind"] == "TERMINAL_SPEND_UNRECORDED"
        ],
        # Spends the ledger ALREADY records. Reported whether or not a `terminal` row matches, so
        # a mistyped subject key shows up as a spend against a subject nobody granted.
        "terminal_spend_recorded": [
            {"subject": subj, "commit": rec["commit"], "date": rec["date"],
             "reason": rec["reason"], "line": rec["line"],
             "withdraws_a_terminal_row": rec.get("withdrew_a_row", False)}
            for subj, rec in sorted(terminal_spent.items())
        ],
        "terminal_artifacts_seen": dict(sorted(terminals.items())),
        "ledger": ledger,
        "warnings": warnings,
        "errors": errors,
        "advisory": "this instrument reports round spend; it does not bind the party that runs "
                    "it. RC=0 means nothing it can see is wrong, not that nothing is wrong. The "
                    "binding control is a human reading this receipt at the merge gate. Known-open "
                    "bypasses are named in the module docstring and are not defects awaiting a fix",
    }
    if args.json:
        print(json.dumps({"errors": errors, "warnings": warnings, "grants": ledger,
                          "files": n_files, "bytes": n_bytes, "receipt": receipt}, indent=2))
    else:
        # ALWAYS name the authority that was consulted. A control that reads a grant ledger
        # without saying which one cannot be audited, and it was exactly that silence that let a
        # forged `--grants` path return the word `clean`.
        print(f"grants: {ledger['path']} "
              f"({'default' if is_default else 'NON-DEFAULT'}, {ledger['entries']} entr"
              f"{'y' if ledger['entries'] == 1 else 'ies'}: "
              f"{ledger['round_grants']} round, {ledger['terminal_passes']} terminal, "
              f"{ledger['terminal_spent']} terminal-spent)")
        # Which COPY of this script ran decides which ledgers count as authorities, and the
        # workspace argument decides what was looked at at all. Both are the caller's choice and
        # neither was reportable before. See F-A under KNOWN-OPEN.
        print(f"script: {receipt['script']}")
        print(f"workspace: {receipt['workspace']}")
        for f in errors:
            print(f"ERROR   {f['kind']:22} {f.get('path', '')}  {f['why']}")
        for f in warnings:
            print(f"WARNING {f['kind']:28} {f.get('path', '')}  {f['why']}")
        if not errors and not warnings:
            print(f"nothing visible: {n_files} files, {n_bytes // 1024} KB, no subject past "
                  f"round {args.max_round} in what this scan could see. NOT a certificate — this "
                  "instrument reports; the merge gate decides")

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
