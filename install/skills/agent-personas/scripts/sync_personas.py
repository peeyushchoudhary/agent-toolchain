#!/usr/bin/env python3
"""Render one persona pool into the formats Claude Code and Codex each require.

A persona is authored once, harness-neutral, in `personas/<name>.md`. This renders it to:

  ~/.claude/agents/<name>.md      YAML frontmatter + markdown body as the system prompt
  ~/.codex/agents/<name>.toml     TOML with developer_instructions

Generation is not a convenience. Claude Code's project-level agents *override* a same-named user
agent wholesale, so "the base persona plus a project-specific instruction" cannot be expressed by
putting files in two places — the project file would silently replace the base. Merging has to
happen before the harness sees it.

Per-project use: an overlay at `<repo>/docs/agents/personas/<name>.md` is appended to the base
persona and the merged result written into that repo's `.claude/agents/` and `.codex/agents/`.
A project only needs files for personas it actually specialises; the rest resolve to the user-level
copies.

Usage:
  sync_personas.py                       # render the pool to user level
  sync_personas.py --repo PATH           # also render that repo's overlays
  sync_personas.py --repo PATH --check   # exit 1 if generated output is stale (for gates)
  sync_personas.py --list                # show the roster with model and effort
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
POOL = SKILL / "personas"
CLAUDE_AGENTS = Path.home() / ".claude" / "agents"
CODEX_AGENTS = Path.home() / ".codex" / "agents"
BASE_PERSONA_NAMES = frozenset({
    "acceptance",
    "architect",
    "chief-of-staff",
    "contract-architect",
    "developer",
    "docs-steward",
    "migration-validator",
    "planner",
    "product-steward",
    "reviewer",
    "scout",
    "security-validator",
    "senior-developer",
    "test-judge",
})


# The judging roster: the personas whose whole value is that they cannot change what they judge.
#
# This is a ROSTER, not a filter over a self-declared field, and the distinction is the entire point
# of it. `writes: no` is a line a persona writes ABOUT ITSELF in the very file the checks police, so
# deriving the protected set from it means a persona can leave the protected set by editing one line
# about itself — reproduced: reviewer.md with `writes: product specs only`, no `disallowedTools` and
# `codex.sandbox: workspace-write` could edit in both harnesses and every check declined to look at
# it, because it no longer matched the filter that selects who gets checked.
#
# Membership is therefore not the subject's to decide. `writes: no` becomes a claim the roster
# CHECKS (see `restrict_for_roster` and the pool tests) rather than the definition of who is checked.
JUDGING_PERSONA_NAMES = frozenset({
    "acceptance",
    "migration-validator",
    "planner",
    "reviewer",
    "scout",
    "security-validator",
    "test-judge",
})

# THE POLICY IS AN ALLOW-LIST. The deny-list below is the second half of an intersection, not the
# mechanism.
#
# Five successive fixes closed five real holes in one invariant — Write/Edit/NotebookEdit, then the
# Codex harness, then self-declared membership, then Agent/SendMessage, then Monitor (which brought
# EnterWorktree, ExitWorktree and TaskStop with it). Nine names where there were three. Every fix was
# correct and every fix was incomplete, because a deny-list is DEFAULT-OPEN against a tool roster
# that grows without asking. That is not five mistakes; it is one wrong shape.
#
# The decisive evidence: `Monitor` was found by a judge reading its own granted roster, not by
# anything in this repository. No test here detected it and no test here could have, because nothing
# here enumerates the complement of a list. Enumeration cannot close this class.
#
# So a roster member must declare `claude.tools` — an explicit allow-list — and A TOOL NOT NAMED IS
# NOT GRANTED, whether or not anyone thought to deny it. Absence of an allow-list is a FAILURE, never
# a default. See `restrict_for_roster`, and ~/.claude/docs/decisions.md for the classification the lists were
# built from and for the three surfaces (`Skill`, MCP, `WebFetch`/`WebSearch`) that are denied
# because they could not be classified — an unclassified tool is a denied tool.
#
# Denied to every roster member, expressed ONCE. Previously this list was hand-copied into six
# persona files, so a seventh judge inherited nothing and any one of the six could edit its own copy.
#
# `Agent` is here because dispatch capability IS write capability, transitively: a judge denied
# Write/Edit/NotebookEdit that can still dispatch a general-purpose subagent has that subagent carry
# every tool and write on its behalf. The restriction blocked the judge's hand and left its mouth
# open. `test-judge` is the persona that already demonstrated exactly this — it chained to a
# sub-subagent rather than say it could not do the work — so it loses `Agent` along with the rest.
# It keeps `Bash`, declared locally, because running a gate genuinely requires a shell; dispatch has
# no equivalent argument. See ~/.claude/docs/decisions.md.
#
# `SendMessage` is here for the same reason as `Agent` and is a judgement call recorded in
# ~/.claude/docs/decisions.md: it continues an ALREADY-RUNNING agent, which is dispatch without the dispatch
# call. Denying it stops a judge sending instructions to a sibling that holds write tools; it does
# not stop a controller sending instructions TO the judge, because the sender holds the tool.
#
# `Monitor` is ARBITRARY SHELL. Its own schema calls `command` a "Shell command or script" and says
# "the script runs in the same shell environment as Bash", so a judge holding it runs `sed -i`,
# `git checkout`, `git apply`, or an edit to this very file. It was granted to all six judges at the
# moment `Agent` was denied — the long transitive route to a write was closed while a shorter one
# stood open. `Bash` remains the single SANCTIONED shell exception, held only by `test-judge`, with
# an argument behind it and its residual risk recorded. `Monitor` had none of that.
#
# `EnterWorktree`/`ExitWorktree`: `ExitWorktree(action="remove", discard_changes=True)` deletes a
# worktree and its branch. `TaskStop`: a judge that can halt a sibling judge changes a verdict
# without writing a byte.
#
# Every name here is a live tool in this harness. Dead names are deliberately NOT listed — a
# deny-list entry for a tool that does not exist reads as coverage and provides none.
#
# WHY THIS SURVIVES THE INVERSION rather than being deleted. It is BELT AND BRACES: two mechanisms
# that must agree, with `test_the_allow_list_and_the_deny_list_agree_in_every_emitted_artifact`
# asserting they do. The allow-list is only as good as the roster's completeness; the deny-list
# catches a name nobody thought to consider — including a name added to an allow-list by mistake,
# which `restrict_for_roster` rejects outright rather than silently filtering. If the two ever
# disagree that is a FINDING, not something to reconcile silently.
#
# It is still a deny-list and it is still exactly "the names somebody thought of". It is no longer
# load-bearing on its own: what a judge holds is now decided by `claude.tools`.
JUDGE_DENIED_TOOLS = (
    "Write", "Edit", "NotebookEdit",        # direct modification
    "Agent", "SendMessage",                 # dispatch, and dispatch-without-the-dispatch-call
    "Monitor",                              # arbitrary shell, unsanctioned
    "EnterWorktree", "ExitWorktree",        # create and destroy trees and branches
    "TaskStop",                             # silence a sibling judge
)

# THE ALLOW-LIST'S VOCABULARY, CLOSED. Follows BASE_PERSONA_NAMES and KNOWN_WRITES_VALUES: a new
# name requires a deliberate edit here, where the reviewer of that edit is asked what the tool lets a
# judge do.
#
# Without it the allow-list had the deny-list's own disease one level in. `claude.tools: Read, Grep,
# Glob, TodoWrite, mcp__ruflo__agent_spawn` passed every test and `--check` exited 0 — a judge
# holding dispatch again, through the key that was supposed to close dispatch. And `claude.tools:
# Reed` was emitted verbatim: it grants nothing, reads like policy, and nothing objected.
#
# Each name here is granted to at least one judge and carries an argument in ~/.claude/docs/decisions.md:
#   Read, Grep, Glob   a judge must read and search; none of them can modify anything
#   TodoWrite          per-session scratch state, visible only to the agent that writes it; it
#                      touches no file the repository tracks and reaches nothing outside the turn.
#                      Named for the same reason `Bash` is: because a name that looks like a write
#                      tool should be argued for rather than waved through on a table row
#   Bash               `test-judge` only, the single sanctioned shell exception
KNOWN_JUDGE_TOOLS = frozenset({"Read", "Grep", "Glob", "TodoWrite", "Bash"})

# THE `writes:` VOCABULARY, CLOSED — and it has to live here rather than only in the test suite.
#
# It was asserted over `pool_personas()` only, and every project check compared against the literal
# `"no"`. So an overlay declaring `writes: none`, `writes: No` (YAML 1.1 boolean-false, a plausible
# typo) or `writes: never` read as a non-writing persona to every human reviewing it and produced no
# warning whatsoever — the identical rogue the test suite documents as REPRODUCED in the base pool,
# reachable from one directory over, in a branch nothing had tested.
#
# `claims_no_writes()` is the single predicate. Two call sites comparing this field by hand is how
# the filter at one site and the verdict at the other came to disagree in the first place.
KNOWN_WRITES_VALUES = frozenset({
    "no",
    "yes",
    "ledger, task cards, and reports only",
    "product specs only",
})


def claims_no_writes(declared: str | None) -> bool:
    """Whether this value should be READ as a claim not to write.

    Fail-closed on the reader's side: anything outside the vocabulary counts as a claim, because the
    risk being managed is a persona that reads as a judge to a human while inheriting no restriction.
    `writes: none` looks exactly like `writes: no` to the person reviewing that file, so it must
    produce the same warning — the alternative is a typo silently removing a persona from the
    population every check examines.
    """
    return declared is not None and (declared == "no" or declared not in KNOWN_WRITES_VALUES)


# WHAT A PROJECT PERSONA ACTUALLY LACKS — which is NOT "everything the roster would have derived".
#
# The warning below used to say a project judge "receives NO write, dispatch or shell restriction in
# either harness". Two of those three nouns were true and one was not: nothing is DERIVED for such a
# persona, but whatever it DECLARES is still rendered verbatim into the artifact the harness loads,
# and the factory template declares a real tool policy. A partially-true warning is the worst
# available shape — a reader who goes to check it meets the confirming evidence first and cheapest,
# and stops — so the warning now names, per persona, only the restrictions that are genuinely absent,
# and says what is present so nothing is left to inference.
#
# Claude-side only, and deliberately: `claude.tools`/`claude.disallowedTools` are the only keys that
# express tool policy. Codex has no such key at all, so its half is reported separately from
# `codex.sandbox` rather than folded into these three nouns.
#
# THE THREE NOUNS ARE NOT A PARTITION OF JUDGE_DENIED_TOOLS AND MUST NEVER READ AS ONE. They OVERLAP
# it: `Bash` is a noun here and is not denied to `test-judge`, while worktree control and `TaskStop`
# are denied there and are named by no noun here. The first version of this warning closed with a
# parenthetical saying the nouns missed "worktree control and TaskStop" — which is a COMPLETENESS
# SIGNAL, telling a reader the nouns miss exactly two things and everything else is accounted for.
# That is the same defect the old sentence had, one level down: the old one was wrong about a noun,
# that one was wrong about the size of the universe. The message now says the set is open and says
# WHY it is open. The guard is `test_known_key_sets_match_the_renderer` in
# ~/.claude/skills/agent-personas/tests/test_repo_sync.py — it pins this tuple against
# JUDGE_DENIED_TOOLS and fails if a name is added there that neither a noun here nor the message's
# own text accounts for.
# (Cited by the name that resolves in that file. A comment naming a test that does not exist tells a
# maintainer who greps for it that the guard was deleted, which is worse than citing nothing. Cited
# by ABSOLUTE path for the same reason one level up: that suite is not vendored, so in a published
# copy of this file a relative path names a file that is not there — the "deleted guard" reading,
# from a copy where nothing was deleted.)
CLAUDE_RESTRICTIONS = (
    ("write", ("Write", "Edit", "NotebookEdit")),
    ("dispatch", ("Agent", "SendMessage")),
    ("shell", ("Bash", "Monitor")),  # `Monitor` runs a command in the same shell environment as Bash
)


def grants(meta: dict, tool: str) -> bool:
    """Whether this persona's own frontmatter leaves `tool` available in the Claude harness.

    Same doctrine the test suite applies: an allow-list, when present and non-empty, is the policy
    and anything unnamed is withheld; a present-but-empty allow-list is dropped by `render_claude`
    and so is no allow-list at all; and a tool named in BOTH keys counts as GRANTED, because which
    key the harness honours is not established anywhere and that is the safe direction to be wrong.
    """
    allow = _tools(meta.get("claude.tools"))
    if tool in allow:
        return True
    if allow:
        return False
    return tool not in _tools(meta.get("claude.disallowedTools"))


def absent_restrictions(meta: dict) -> list[tuple[str, list[str]]]:
    """The restrictions this persona does NOT have, each with the tools that prove it.

    A restriction counts as present only when every tool expressing it is withheld: denying `Bash`
    while leaving `Monitor` granted is not a shell restriction, and reporting it as one is how a
    hand-written deny-list came to read as policy while granting the capability it named.
    """
    out = []
    for noun, tools in CLAUDE_RESTRICTIONS:
        still_granted = [t for t in tools if grants(meta, t)]
        if still_granted:
            out.append((noun, still_granted))
    return out


def declared_policy(meta: dict) -> list[str]:
    """The persona's EFFECTIVE Claude tool policy, quoted back verbatim rather than summarised.

    "Effective", not "as authored": at the overlay call site this is the MERGED meta, because what
    the harness receives is what the merge produced and that is the only thing a warning may
    describe. `codex.sandbox` is deliberately not in here — it is not a tool policy, it is evaluated
    against JUDGE_SANDBOX and reported as its own clause, because quoting it beside the Claude keys
    let `codex.sandbox: workspace-write` read as a restriction while granting writes.
    """
    return [f"`{key}: {meta[key]}`"
            for key in ("claude.tools", "claude.disallowedTools")
            if meta.get(key)]


def unprotected_judge_warning(name: str, meta: dict) -> str:
    """One warning line, every clause of it true of THIS persona and scoped to a named harness.

    Every claim here is per-harness on purpose. The original sentence's central sin was "in either
    harness" over a fact that is only ever true of one of them, and a branch that silently drops the
    qualifier restores that sin by omission.

    That guarantee includes the persona's OWN WORDS. The head quoted ``writes: no`` at every persona
    it fired for, while `claims_no_writes` fires on `none`, `never` and `No` as well — so the one
    clause a reader could check against the file in front of them was the clause most likely to be a
    misquote, on exactly the personas whose declaration is already suspect. It now quotes what the
    persona actually wrote, and says why an unrecognised value is being read as a claim not to write.
    """
    absent = absent_restrictions(meta)
    allow_list = _tools(meta.get("claude.tools"))
    if absent:
        lacks = ("Still granted in the Claude harness, because nothing withholds it: "
                 + "; ".join(f"{noun} ({', '.join(tools)})" for noun, tools in absent) + ".")
    else:
        lacks = ("In the Claude harness its own declaration does withhold write, dispatch and "
                 "shell — its own, so an edit that removes it is checked by nothing.")

    # THE SIZE OF THE UNIVERSE, which is the part three nouns cannot carry on their own.
    if allow_list:
        scope = ("That allow-list is closed, so a tool it does not name is not granted — including "
                 "tools nobody here has thought of.")
    else:
        scope = ("AND THAT LIST IS NOT THE WHOLE OF WHAT IT HOLDS: with no `claude.tools` "
                 "allow-list the emitted artifact carries no `tools:` key at all, so the harness "
                 "grants every tool outside the deny-list — for example `Artifact`, `Skill`, "
                 "`WebFetch`, `WebSearch` and `ToolSearch`, plus every MCP tool mounted now or "
                 "later. Three nouns cannot enumerate an open set; only an allow-list closes it.")

    policy = declared_policy(meta)
    present = ("Self-declared and rendered verbatim, never derived and never validated: "
               + "; ".join(policy) + ".") if policy else \
              ("It declares no `claude.tools` and no `claude.disallowedTools`, so nothing in the "
               "Claude harness restricts it at all.")

    # Codex, EVALUATED rather than quoted, in THREE cases and not two. `read-only` is the only value
    # that withholds writes; a different value does not. But an ABSENT key is a third thing: what
    # Codex does for an agent TOML declaring no sandbox has not been observed from here, and the
    # suite's own record at `granted_write_capability` says absent is treated as write-capable
    # BECAUSE the default is unknown and that is the safe direction to be wrong in — not because a
    # permissive default was verified. Folding it into the `workspace-write` branch stated that
    # unverified default as an observed effect, in the one artifact a human reads.
    sandbox = meta.get("codex.sandbox")
    if sandbox == JUDGE_SANDBOX:
        # `{sandbox}` rather than `{JUDGE_SANDBOX}` — identical here by construction, and a mutation
        # test showed the hard-coded form reporting `read-only` for a `workspace-write` persona the
        # moment the branch condition was loosened. Quote the value you tested, not the one you hoped
        # for.
        codex = (f"In the Codex harness it declares `codex.sandbox: {sandbox}`, which does "
                 f"withhold writes — its own declaration again, checked by nothing here.")
    elif sandbox is None:
        codex = (f"In the Codex harness it declares no `codex.sandbox` at all. What Codex grants an "
                 f"agent that declares none has not been observed from here, so this is treated as "
                 f"write-capable because that is the safe direction to be wrong in — not because a "
                 f"permissive default was verified. Declare `{JUDGE_SANDBOX}` and the question does "
                 f"not arise.")
    else:
        codex = (f"In the Codex harness it has NO write restriction: `codex.sandbox` is "
                 f"{sandbox or '<empty>'}, and only `{JUDGE_SANDBOX}` withholds writes.")

    # The persona's OWN WORDS in the head, not the vocabulary's. See the docstring.
    declared = meta.get("writes")
    claim = (f"declares `writes: {declared}`" if declared in KNOWN_WRITES_VALUES else
             f"declares `writes: {declared}`, which is not a recognised value and is being READ as "
             f"a claim not to write")

    # The tail says the roster's set and these nouns are DIFFERENT, not that one contains the other:
    # `Bash` is a noun here and is not withheld from `test-judge`. "among other things" is what keeps
    # the roster's side open, and `test_the_unprotected_judge_warning_names_only_what_is_absent`
    # asserts that phrase — without it this sentence is the closed-set parenthetical again.
    return (f"  WARNING {name}: {claim}, but is a PROJECT persona, so it is not on the judging "
            f"roster and NOTHING is derived or validated for it. {lacks} {scope} {present} {codex} "
            f"What the roster withholds from a base judge is a different set from these three nouns "
            f"— worktree control and `TaskStop` among other things — and it covers base personas "
            f"only.")


# Codex expresses the same rule with an OS-level sandbox rather than a tool deny-list. `read-only`
# is the only value that withholds write capability. Codex has NO key that expresses dispatch
# denial; that gap is recorded in ~/.claude/docs/decisions.md rather than papered over with an invented key.
JUDGE_SANDBOX = "read-only"


# THE RECORD A HUMAN READS, AND NOW A LOAD-BEARING INPUT TO THE RENDER.
#
# Nothing detected a roster that had SHRUNK. `JUDGING_PERSONA_NAMES` and the test suite's pinned
# `JUDGING_ROSTER` pin each OTHER, which catches disagreement between two copies and never removal
# from both; `set(JUDGING_ROSTER) <= BASE_NAMES` is an UPPER bound. Shrink both copies, shrink the
# marker, and change that persona's `writes:`, and every check exits 0.
#
# So there is now a LOWER bound, and it lives in ~/.claude/docs/decisions.md as a ratchet that may only ever
# grow. It is read HERE, in the renderer, and not only by the test suite, for one concrete reason:
# `sync_personas.py --check` runs at every session start (settings.json -> disclosure-check.sh ->
# check_toolchain.py), while nothing runs the installed
# ~/.claude/skills/agent-personas/tests/test_repo_sync.py automatically. A guard wired to a
# manually-invoked test is a guard that runs when someone remembers.
#
# WHERE THE FLOOR LIVES, and why it moved. The first version of this read the machine-readable
# floor out of ~/.claude/docs/decisions.md. That made the SKILL depend on a file outside it, and a
# fresh public install ships no such file — `install.sh` runs this script and fails the whole
# installer, so "the record is missing" became the DEFAULT STATE of a new machine rather than the
# alarm it is meant to be.
#
# The founder's requirement is that defection must also edit the record a human reads. That is a
# property of the PIN, not of which file this function happens to open: `ROSTER` here and the marker
# in ~/.claude/docs/decisions.md are asserted equal by
# `test_the_roster_is_pinned_to_the_record_a_human_reads`, so the human record still has to be
# rewritten in the same commit. So the machine-readable floor lives INSIDE the skill and the
# human-readable argument stays in ~/.claude/docs/decisions.md.
#
# Honest about what this is: a coordination cost, not a boundary. Every one of these files is
# writable by an agent holding a shell. The boundary is the harness permission system.
ROSTER_FILE = SKILL / "ROSTER"
RECORD = SKILL.parent.parent / "docs" / "decisions.md"
ROSTER_MARKER = "<!-- JUDGING_ROSTER: "


def recorded_floor() -> frozenset[str]:
    """The roster's lower bound, from the skill's own ROSTER file.

    Every failure mode of reading it is a PersonaError, including the ones that are not this
    module's fault. An OSError or a decode error escaping to the caller was rendered by `sync()`'s
    generic handler as "0 generated agent file(s) do not match" — a security check reporting its own
    inability to run as a clean result.
    """
    try:
        text = ROSTER_FILE.read_text(encoding="utf-8")
    except OSError as e:
        raise PersonaError(
            f"cannot read the judging roster's floor at {ROSTER_FILE}: {e}. It carries the lower "
            f"bound that stops the roster shrinking silently, so an unreadable floor is a failure, "
            f"not an absence."
        ) from e
    names = frozenset(
        line.strip() for line in text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    )
    if not names:
        raise PersonaError(
            f"{ROSTER_FILE} names no personas. An empty floor bounds nothing, which is "
            f"indistinguishable from having no floor at all."
        )
    return names


def _recorded_names(text: str, marker: str) -> frozenset[str]:
    start = text.find(marker)
    if start == -1:
        raise PersonaError(
            f"{RECORD} carries no `{marker.strip()}` marker — the judging roster's record is "
            f"missing from the file a human reads, so the roster has no witness outside the code "
            f"that defines it."
        )
    end = text.find("-->", start)
    if end == -1:
        raise PersonaError(
            f"{RECORD}: the `{marker.strip()}` marker is never closed with `-->`. An unterminated "
            f"marker is not a roster."
        )
    return frozenset(n.strip() for n in text[start + len(marker):end].split(",") if n.strip())


def check_roster_against_the_record() -> tuple[str | None, str | None]:
    """Return `(finding, warning)` describing how the roster departs from its record.

    RETURNS RATHER THAN RAISES, and that is the point. When this was an early `return 2` from
    `sync()`, deleting the record bought TWO disablements for one edit: the roster check failed AND
    the staleness comparison never ran, so a hand-edited ~/.claude/agents/reviewer.md stopped being
    compared against the pool. Both halves were documented; the composition was not, and the
    composition is the attack. Collected as a finding, every other check still runs.

    WHAT FAILS AND WHAT ONLY WARNS, because the two records are not the same kind of thing. The
    FLOOR ships inside the skill and is always present, so anything wrong with it is a hard finding.
    The human record in ~/.claude/docs/decisions.md is NOT shipped by the installer, so its absence is the
    normal state of a fresh machine and cannot be a failure — that was the whole defect of reading
    the floor out of it. Absent: warn. Present and disagreeing: fail, because a record that
    contradicts the code is worse than no record.

    The suite closes the other half: `test_the_roster_is_pinned_to_the_record_a_human_reads` asserts
    the record EXISTS and equals the floor. So deleting it is a hard failure in this repository,
    where the record lives, and a warning on a machine that never had it.
    """
    floor = recorded_floor()
    dropped = sorted(floor - JUDGING_PERSONA_NAMES)
    if dropped:
        return (
            f"the judging roster has SHRUNK below the minimum recorded in {ROSTER_FILE.name}: "
            f"{', '.join(dropped)} no longer protected. That list is a ratchet and may only grow. "
            f"Removing a persona from the protected set is a deliberate reduction of the no-edit "
            f"guarantee and must be argued for in ~/.claude/docs/decisions.md, not performed by deletion."
        ), None
    if not RECORD.is_file():
        return None, (
            f"no human record of the judging roster at {RECORD}. The floor in {ROSTER_FILE.name} "
            f"still holds and is what the renderer enforces, but the argument for it — what the "
            f"guarantee covers and what it does not — is not on this machine."
        )
    recorded = _recorded_names(RECORD.read_text(encoding="utf-8"), ROSTER_MARKER)
    if recorded != JUDGING_PERSONA_NAMES:
        return (
            f"the judging roster in {RECORD.name} disagrees with JUDGING_PERSONA_NAMES — "
            f"recorded only: {sorted(recorded - JUDGING_PERSONA_NAMES) or 'none'}; "
            f"in code only: {sorted(JUDGING_PERSONA_NAMES - recorded) or 'none'}."
        ), None
    if floor - recorded:
        return (
            f"{RECORD.name} no longer records every persona on the floor in {ROSTER_FILE.name}: "
            f"{sorted(floor - recorded)} missing from the record a human reads."
        ), None
    return None, None


def codex_present() -> bool:
    """Only render Codex agents where Codex actually lives.

    Rendering unconditionally creates a ~/.codex tree on a machine that has no Codex — files nothing
    will ever read, in a directory the user did not ask for. Absence of ~/.codex is the only
    reliable signal available here.
    """
    return (Path.home() / ".codex").is_dir()

GENERATED = "# GENERATED by agent-personas/scripts/sync_personas.py — edit the persona, not this."

# Keys read from a persona's frontmatter. Flat and dotted rather than nested, because the format has
# to be parsed without PyYAML (not in the stdlib) and a hand-rolled nested parser is where silent
# misreads come from.
CLAUDE_KEYS = {"claude.model": "model", "claude.effort": "effort",
               "claude.tools": "tools", "claude.disallowedTools": "disallowedTools"}
CODEX_KEYS = {"codex.model": "model", "codex.effort": "model_reasoning_effort",
              "codex.sandbox": "sandbox_mode"}


class PersonaError(Exception):
    pass


def pool_sources() -> list[Path]:
    """Return the canonical base pool or reject global specialist leakage."""
    sources = sorted(
        p for p in POOL.glob("*.md") if p.name.lower() != "readme.md"
    )
    if not sources:
        raise PersonaError(f"no personas in {POOL}")
    actual_names = {p.stem for p in sources}
    if actual_names != BASE_PERSONA_NAMES:
        details = []
        missing = sorted(BASE_PERSONA_NAMES - actual_names)
        unexpected = sorted(actual_names - BASE_PERSONA_NAMES)
        if missing:
            details.append("missing: " + ", ".join(missing))
        if unexpected:
            details.append("unexpected: " + ", ".join(unexpected))
        raise PersonaError(
            "base persona pool must contain exactly the canonical 14 ("
            + "; ".join(details)
            + ")"
        )
    return sources


def parse(path: Path) -> tuple[dict, str]:
    """Split `---` frontmatter from the body. Values are plain strings; no type coercion."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise PersonaError(f"{path.name}: no frontmatter")
    _, _, rest = text.partition("---")
    fm, sep, body = rest.partition("\n---")
    if not sep:
        raise PersonaError(f"{path.name}: unterminated frontmatter")

    meta: dict[str, str] = {}
    for i, line in enumerate(fm.splitlines(), start=2):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            raise PersonaError(f"{path.name}:{i}: not a `key: value` line -> {line!r}")
        k, _, v = line.partition(":")
        meta[k.strip()] = v.strip().strip('"').strip("'")

    for required in ("name", "description"):
        if not meta.get(required):
            raise PersonaError(f"{path.name}: missing required `{required}`")
    if meta["name"] != path.stem:
        raise PersonaError(
            f"{path.name}: filename must match persona name `{meta['name']}.md`"
        )
    return meta, body.lstrip("\n")


def yaml_scalar(v: str) -> str:
    """Quote only when a bare scalar would be misread. Keeps generated frontmatter readable."""
    return f'"{v}"' if any(c in v for c in ':#{}[]&*!|>%@`"') or v != v.strip() else v


def _tools(value: str | None) -> list[str]:
    return [t.strip() for t in (value or "").split(",") if t.strip()]


def restrict_for_roster(meta: dict) -> dict:
    """Apply the judging roster's restrictions to a persona about to be rendered.

    Called by BOTH renderers, so the guarantee reaches both harnesses from this one expression —
    two parallel mechanisms that agree today and drift tomorrow is the defect class this exists to
    remove. Called in the renderer rather than at parse time because the claim that matters is not
    "the source says the right thing", it is "the harness receives the right thing": a project
    overlay that retunes `reviewer` still emits a restricted `reviewer`.

    SCOPE, and do not read it as broader than it is: this protects the personas NAMED IN THE ROSTER,
    which are base personas only. A project specialist derived by agent-persona-factory —
    `privacy-auditor`, `consent-validator` — is not on the roster and is returned UNCHANGED from
    here, with full write and dispatch, however plainly its description says it only judges. That
    gap is open and is stated in ~/.claude/docs/decisions.md; `sync()` warns by name while it stands.

    Derivation, not correction of a copy, for the DENY half: a roster member need declare nothing at
    all and is still denied every write tool and dispatch, so removing a declared line can only ever
    loosen a local exception (`test-judge`'s `Bash`) and never the derived core.

    The ALLOW half cannot be derived and is therefore MANDATORY. What a judge legitimately needs is
    a fact about that judge's job, not about the roster, so it has to be written down per persona —
    and the price of that is that a roster member declaring nothing must FAIL rather than fall back
    to the deny-list. It does.

    CLAUDE-ONLY BY NECESSITY. Codex has no key expressing tool policy at all — its whole model is the
    OS sandbox — so the two harnesses now diverge in MECHANISM as well as in strength. `read-only` is
    still derived here for Codex, and no allow-list key is invented for it. ~/.claude/docs/decisions.md states
    this plainly rather than leaving a reader to assume parity.

    A source that CONTRADICTS the roster is rejected rather than silently corrected. Quietly
    rendering the right thing from a persona file that claims it may write would hide the defection
    in the one artifact a human reads.
    """
    name = meta.get("name")
    if name not in JUDGING_PERSONA_NAMES:
        return meta

    declared_writes = meta.get("writes")
    if declared_writes != "no":
        raise PersonaError(
            f"{name}: on the judging roster (JUDGING_PERSONA_NAMES) but declares "
            f"`writes: {declared_writes}` — a judging persona may not declare itself a writer. "
            f"Membership is not the persona's to decide: remove it from the roster deliberately, "
            f"or fix the declaration."
        )
    sandbox = meta.get("codex.sandbox")
    if sandbox is not None and sandbox != JUDGE_SANDBOX:
        raise PersonaError(
            f"{name}: on the judging roster but declares `codex.sandbox: {sandbox}` — the roster "
            f"requires {JUDGE_SANDBOX!r} in the Codex harness."
        )

    # An unrenderable key on a roster member is rejected here, not merely reported by the tests.
    # `claude.allowedTools: Write` is dropped silently by the renderer, so it reads as policy in the
    # source and reaches the harness as nothing at all. For any other persona that is a lint; on a
    # persona this function is otherwise willing to reject at exit 2, leaving the renderer more
    # permissive than its own test suite made no sense.
    for key in sorted(meta):
        if key.startswith("claude.") and key not in CLAUDE_KEYS:
            raise PersonaError(
                f"{name}: on the judging roster and declares unrenderable key `{key}` — this is "
                f"dropped before the harness sees it, so it reads as a restriction and is none."
            )
        if key.startswith("codex.") and key not in CODEX_KEYS:
            raise PersonaError(
                f"{name}: on the judging roster and declares unrenderable key `{key}` — this is "
                f"dropped before the harness sees it, so it reads as a restriction and is none."
            )

    out = dict(meta)
    extra = [t for t in _tools(meta.get("claude.disallowedTools")) if t not in JUDGE_DENIED_TOOLS]
    out["claude.disallowedTools"] = ", ".join([*JUDGE_DENIED_TOOLS, *extra])

    # THE ALLOW-LIST IS THE POLICY, AND IT IS MANDATORY.
    #
    # Absence of an allow-list is not "no opinion", it is "grant everything the deny-list did not
    # think of" — which is how a judge came to hold `Artifact`, the whole MCP surface, and `Monitor`.
    # A roster member that declares nothing is therefore REJECTED and named, rather than rendered
    # with the derived deny-list and called restricted.
    #
    # It is validated, never filtered. Filtering is what made it dangerous: dropping denied names
    # could leave the list EMPTY, and `render_claude`'s `if meta.get(src)` then omits the key
    # entirely, so the harness receives NO allow-list and grants everything outside the deny-list.
    # Reproduced: `claude.tools: Read` held one tool; `claude.tools: Edit` held every tool except the
    # denied ones. Adding a denied tool to your allow-list made you strictly more capable.
    #
    # So: no silent filtering at all. Any overlap with the deny-list is REJECTED, and a
    # present-but-empty allow-list is rejected too rather than being read as "no allow-list".
    # Rejecting the whole overlap rather than only the case that empties the list is what makes the
    # two mechanisms REQUIRED TO AGREE: silently dropping `Edit` from an author's list would hide an
    # authoring mistake in exactly the file that is now the authority. Disagreement is a finding.
    if "claude.tools" not in meta:
        raise PersonaError(
            f"{name}: on the judging roster and declares NO `claude.tools` allow-list. A judge's "
            f"tool policy is an allow-list, so absence of one is not a default — it grants every "
            f"tool the deny-list did not happen to name, which is the shape that let `Monitor`, "
            f"`Artifact` and the entire MCP surface reach six judges unnoticed. Name the tools this "
            f"persona needs to read, search and report; a tool not named is not granted."
        )
    declared = _tools(meta["claude.tools"])
    if not declared:
        raise PersonaError(
            f"{name}: declares an EMPTY `claude.tools` allow-list. Read literally that is "
            f"maximally restrictive, but the renderer drops an empty key and the harness then "
            f"grants every tool outside the deny-list. Name the tools this persona needs."
        )
    overlap = [t for t in declared if t in JUDGE_DENIED_TOOLS]
    if overlap:
        raise PersonaError(
            f"{name}: `claude.tools` allow-list names denied tool(s) {', '.join(overlap)}. A "
            f"judging persona's allow-list may not re-grant what the roster withholds; the two "
            f"must agree, and this is the channel through which an allow-list could WIDEN."
        )
    # AND against the persona's OWN deny-list extras, not only the derived core. `claude.tools:
    # …, Bash` beside `claude.disallowedTools: Bash` rendered at exit 0 emitting both, so the
    # docstring's claim that this function "refuses to author the contradiction" was false for the
    # one tool the two mechanisms actually treat differently between personas. The emitted-artifact
    # test asserted a state the renderer could produce from source.
    self_contradiction = sorted(set(declared) & set(extra))
    if self_contradiction:
        raise PersonaError(
            f"{name}: names {', '.join(self_contradiction)} in BOTH `claude.tools` and "
            f"`claude.disallowedTools`. The two mechanisms must agree; which one the harness "
            f"honours is not established anywhere, so this is a finding, not a tie to break."
        )
    unknown = [t for t in declared if t not in KNOWN_JUDGE_TOOLS]
    if unknown:
        raise PersonaError(
            f"{name}: `claude.tools` names unrecognised tool(s) {', '.join(unknown)}. The "
            f"vocabulary is closed — see KNOWN_JUDGE_TOOLS. A typo (`Reed`) is emitted verbatim and "
            f"grants nothing while reading like policy; a real tool nobody classified (`Skill`, "
            f"`mcp__…__agent_spawn`) is a capability granted without an argument. Add the name to "
            f"KNOWN_JUDGE_TOOLS only after deciding what it lets a judge do."
        )
    out["claude.tools"] = ", ".join(declared)

    out["codex.sandbox"] = JUDGE_SANDBOX
    return out


def render_claude(meta: dict, body: str) -> str:
    meta = restrict_for_roster(meta)
    # The banner goes inside the frontmatter as a YAML comment, never into the body. The body IS the
    # agent's system prompt, so a note addressed to a human reader — "edit the persona, not this" —
    # would sit there as a stray instruction the agent has to interpret.
    lines = ["---", GENERATED, f"name: {meta['name']}",
             f"description: {yaml_scalar(meta['description'])}"]
    for src, dest in CLAUDE_KEYS.items():
        if meta.get(src):
            lines.append(f"{dest}: {yaml_scalar(meta[src])}")
    lines += ["---", "", body.rstrip(), ""]
    return "\n".join(lines)


def render_codex(meta: dict, body: str) -> str:
    meta = restrict_for_roster(meta)
    if "'''" in body:
        # TOML literal strings take no escapes, which is exactly why they are safe for prose. A body
        # containing the delimiter would silently truncate the instructions.
        raise PersonaError(f"{meta['name']}: body contains ''' which cannot go in a TOML literal")
    out = [GENERATED,
           f'name = "{meta["name"]}"',
           f'description = "{meta["description"]}"',
           "developer_instructions = '''",
           body.rstrip(),
           "'''", ""]
    for src, dest in CODEX_KEYS.items():
        if meta.get(src):
            out.append(f'{dest} = "{meta[src]}"')
    return "\n".join(out) + "\n"


def merge_overlay(base: dict, overlay: dict) -> dict:
    """Merge a project overlay onto a base persona so it can only ever NARROW capability.

    A plain `{**base, **overlay}` let a project overlay REPLACE the base's tool policy, and both
    halves broke. Reproduced against a roster member — an overlay declaring
    `claude.tools: Read, Grep, Glob, TodoWrite, Bash, Skill, WebFetch` with
    `claude.disallowedTools: NotebookEdit` rendered rc=0 and emitted a project `reviewer.md` holding
    `Bash`, `Skill` and `WebFetch`, whose deny-list no longer carried the base's `Bash` because the
    overlay's value replaced it. Claude Code's project agents override same-named user agents
    wholesale, so that artifact IS the reviewer in that repository.

    So the two tool keys are merged by rule rather than by precedence:

      claude.tools           INTERSECTED with the base's. An overlay may drop a tool it does not
                             want; it can never introduce one. A name the base did not grant is
                             rejected outright rather than dropped, because silently discarding it
                             hides an authoring mistake in the file meant to carry the intent.
      claude.disallowedTools UNION with the base's. Extras add; nothing an overlay omits is thereby
                             granted.

    Every other key still takes the overlay's value — model, effort and description are retuning,
    not capability. `writes` and `codex.sandbox` are left to `restrict_for_roster`, which rejects a
    roster member contradicting either.
    """
    merged = {**base, **{k: v for k, v in overlay.items() if v}}
    name = base.get("name", overlay.get("name", "<unknown>"))

    if "claude.tools" in overlay and overlay["claude.tools"]:
        base_allowed = _tools(base.get("claude.tools"))
        over_allowed = _tools(overlay["claude.tools"])
        if base_allowed:
            widened = [t for t in over_allowed if t not in base_allowed]
            if widened:
                raise PersonaError(
                    f"{name}: project overlay's `claude.tools` adds {', '.join(widened)}, which the "
                    f"base persona does not grant. An overlay may narrow a judge's allow-list and "
                    f"may never widen it — the project artifact overrides the user-level one "
                    f"wholesale, so this is the whole tool policy that repository would receive."
                )
            kept = [t for t in base_allowed if t in over_allowed]
            if not kept:
                raise PersonaError(
                    f"{name}: project overlay's `claude.tools` intersects the base allow-list to "
                    f"nothing. An empty allow-list is dropped by the renderer and the harness then "
                    f"grants every tool outside the deny-list, so this fails closed instead."
                )
            merged["claude.tools"] = ", ".join(kept)

    base_denied = _tools(base.get("claude.disallowedTools"))
    over_denied = _tools(overlay.get("claude.disallowedTools"))
    if base_denied or over_denied:
        merged["claude.disallowedTools"] = ", ".join(
            base_denied + [t for t in over_denied if t not in base_denied]
        )
    return merged


def overlay_body(base: str, extra: str, project: str) -> str:
    """Base persona, then the project's additions. Order matters: the general rule is established
    first, so a project instruction reads as a refinement rather than a replacement."""
    return (f"{base.rstrip()}\n\n"
            f"## Project-specific direction — {project}\n\n"
            f"{extra.strip()}\n")


def prune(dirs: list[Path], expected: set[Path], check: bool,
          removed: list, stale: list, *, require_sourced: bool = False) -> None:
    """Delete generated agents whose persona no longer exists.

    Without this, renaming or removing a persona leaves its rendered files behind and they stay
    dispatchable — an agent definition pointing at a role the pool no longer defines, with no
    source to fix. Splitting one persona into two is exactly when this bites.

    Only files carrying our banner are touched. Hand-written agents living in the same directory
    are somebody's work and must survive.
    """
    for d in dirs:
        if not d.is_dir():
            continue
        for f in sorted(list(d.glob("*.md")) + list(d.glob("*.toml"))):
            if f.resolve() in expected:
                continue
            try:
                if GENERATED not in f.read_text(encoding="utf-8", errors="replace"):
                    if check and require_sourced:
                        stale.append(f"{f} (unmanaged — no persona source)")
                    continue          # preserve hand-written files; the check reports them
            except OSError:
                continue
            if check:
                stale.append(f"{f} (orphaned — no persona source)")
            else:
                f.unlink()
                removed.append(str(f))


def write(path: Path, content: str, check: bool, changed: list, stale: list) -> None:
    current = path.read_text(encoding="utf-8") if path.is_file() else None
    if current == content:
        return
    if check:
        stale.append(str(path))
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    changed.append(str(path))


def sync(repo: Path | None, check: bool) -> int:
    if not POOL.is_dir():
        print(f"no persona pool at {POOL}", file=sys.stderr)
        return 2
    # THE ONE HARD EARLY RETURN, and it is deliberate. Every other validation below is collected as
    # a finding so that one failure cannot suppress the others — see `findings`. This one cannot be,
    # because it establishes WHICH personas exist: without a source list there is no expected set,
    # so the staleness comparison has nothing to compare against and `prune` would report every
    # generated file as an orphan. Continuing here would produce a louder wrong answer, not a
    # fuller right one. Named explicitly in ~/.claude/docs/decisions.md rather than hidden behind
    # "every check now runs".
    try:
        sources = pool_sources()
    except PersonaError as e:
        print(f"  ERROR {e}", file=sys.stderr)
        print("  the pool itself is unusable, so nothing else could be checked against it",
              file=sys.stderr)
        return 2

    # Is the protected set still the protected set? The only check in the toolchain that establishes
    # a LOWER bound on the roster, and it is here rather than in the test suite because this is the
    # entry point a hook actually runs.
    #
    # COLLECTED AS A FINDING, NOT RETURNED ON. An early `return 2` here meant one deletion bought two
    # disablements: the roster check failed AND the staleness comparison never ran, so a hand-edited
    # generated agent stopped being compared against the pool for as long as the record was missing.
    # The exit code is still 2 — it is decided at the end, after every other check has had its turn.
    try:
        roster_finding, roster_warning = check_roster_against_the_record()
    except PersonaError as e:
        roster_finding, roster_warning = str(e), None

    changed: list[str] = []
    removed: list[str] = []
    stale: list[str] = []
    declared_no_writes: set[str] = set()
    unprotected_judges: list[tuple[str, dict]] = []
    vocabulary_warnings: list[tuple[str, str]] = []
    expected: set[Path] = set()
    overlays_dir = (repo / "docs" / "agents" / "personas") if repo else None
    project_specific = 0
    check_global = not (check and repo is not None)

    # EVERY VALIDATION FAILURE IS A FINDING, NOT A RETURN.
    #
    # `roster_finding` was made a finding in the last round for a specific reason: one deletion
    # bought two disablements, because the roster check failed AND the staleness comparison never
    # ran. Four other paths still returned early — an unparseable persona, the roster/`writes:`
    # mismatch, a `restrict_for_roster` contradiction, and an overlay rejection — so the same
    # composition survived through a different door. Adding `writes: no` to any non-roster persona
    # source, then hand-editing a generated agent, meant the hand-edit was never compared, and
    # `check_toolchain.py` labels a rc=2 as NOT_RUN.
    #
    # So: collect, keep going, decide the exit code at the end. The one exception is `pool_sources()`
    # above, which cannot be collected because it defines the expected set.
    findings: list[str] = [roster_finding] if roster_finding else []

    def expect(p: Path) -> Path:
        expected.add(p.resolve())
        return p

    # PARSE AND VALIDATE THE WHOLE POOL BEFORE WRITING ANYTHING.
    #
    # Validation used to happen inside the render loop, so a pool containing a defection had already
    # had some artifacts rewritten by the time the run exited 2 — and it exited before the summary
    # and the prune, so it changed what the harness loads and named no files. The half-written state
    # was the *restricted* artifacts, so nothing unsafe shipped, but "failed" and "silently modified
    # your agent definitions" must not be the same run.
    #
    # It also fixes a real coverage hole: under `--repo PATH --check` the renderers are never called
    # for base personas, so `restrict_for_roster` never ran, so a defection that left `writes: no`
    # intact and flipped only `codex.sandbox` passed with rc=0 — in the exact invocation every
    # repository is told to put in its gate.
    parsed: list[tuple[Path, dict, str]] = []
    for src in sources:
        try:
            meta, body = parse(src)
        except PersonaError as e:
            findings.append(str(e))
            # Its generated artifacts are still EXPECTED, so `prune` does not additionally report
            # them as orphaned. The persona has a source; that source is broken. Those are
            # different findings and reporting the second would bury the first.
            expect(CLAUDE_AGENTS / f"{src.stem}.md")
            expect(CODEX_AGENTS / f"{src.stem}.toml")
            continue
        parsed.append((src, meta, body))
        # A FINDING in the base pool, a warning for overlays. The asymmetry is deliberate: this
        # pool is in this repository and can be verified, so an unrecognised value here is a
        # defect to fix now. Overlays live in repositories this card may not touch.
        if meta.get("writes") not in KNOWN_WRITES_VALUES:
            findings.append(
                f"{meta['name']}: `writes: {meta.get('writes')}` is not a recognised value. "
                f"Every check reads this field, and a value none of them recognise reads as a "
                f"judge to a human while matching no filter."
            )
        if claims_no_writes(meta.get("writes")):
            declared_no_writes.add(meta["name"])

    # The roster and the pool's own declarations must agree, in BOTH directions, and disagreement is
    # a failure rather than a skip. A roster member declaring anything but `writes: no` is a
    # defection. A persona declaring `writes: no` that is NOT on the roster is the quieter half: it
    # reads as a judge to every human and to `--list`, and inherits none of the derived restrictions.
    if declared_no_writes != JUDGING_PERSONA_NAMES:
        off_roster = sorted(declared_no_writes - JUDGING_PERSONA_NAMES)
        defected = sorted(JUDGING_PERSONA_NAMES - declared_no_writes)
        why = []
        if defected:
            why.append("on the judging roster but not declaring `writes: no`: "
                       + ", ".join(defected))
        if off_roster:
            why.append("declaring `writes: no` but absent from the judging roster: "
                       + ", ".join(off_roster))
        findings.append("roster mismatch — " + "; ".join(why))

    # Every other roster contradiction — sandbox, allow-list, unrenderable key — asked for here so
    # it is caught in every invocation mode rather than only the ones that happen to render. A
    # persona that fails is recorded and EXCLUDED from the plan below: rendering it would raise the
    # same error again, one layer further in, where it would abort a loop instead of being reported.
    contradicting: set[str] = set()
    for _src, meta, _body in parsed:
        try:
            restrict_for_roster(meta)
        except PersonaError as e:
            findings.append(str(e))
            contradicting.add(meta["name"])

    # PHASE A — RENDER EVERYTHING INTO A PLAN. Nothing is written yet.
    #
    # "The whole pool is parsed and validated before any artifact is written" was FALSE while two
    # validations lived inside the write loop: `merge_overlay`'s rejection and `render_codex`'s `'''`
    # rejection. Measured on this suite's own overlay-widening fixture: NINE global artifacts were
    # written before the loop reached `reviewer` and returned 2, and `prune` never ran, so orphans
    # survived a failed run. The requirement this comment has always stated is that "failed" and
    # "silently modified your agent definitions" must not be the same run.
    #
    # THE GUARANTEE IS THE PLAN-THEN-COMMIT SPLIT. READ THIS BEFORE ADDING A VALIDATION.
    #
    # Phase A renders every artifact into `plan` and may reject. Phase B commits the plan. Nothing
    # touches the filesystem until Phase B, so a run that rejects cannot also have changed what the
    # harness loads.
    #
    # WHERE REJECTIONS ACTUALLY LIVE — derived by AST, stated as function names because line numbers
    # in this file have gone stale twice mid-review:
    #
    #   inside the renderers   `restrict_for_roster` via render_claude() and render_codex();
    #                          render_codex()'s own `'''` check
    #   outside them           parse(); merge_overlay(); restrict_for_roster() called DIRECTLY from
    #                          sync(); pool_sources(); recorded_floor(); the `writes:` vocabulary
    #                          check; and plan_write(), which catches whatever a renderer raises
    #
    # A PREVIOUS VERSION OF THIS COMMENT SAID EVERY REMAINING REJECTION HAPPENS INSIDE THE RENDERERS,
    # AND THAT THE PROPERTY THEREFORE HELD "BY CONSTRUCTION". Do not restore it, and do not be
    # reassured when you check it: the two renderer-internal calls above are real, so the claim
    # CONFIRMS ITSELF on a quick look. The disconfirming half — the direct sync() call, parse(),
    # merge_overlay() — takes longer to find, and nothing prompts you to look. That asymmetry is why
    # the sentence survived four hand corrections. `merge_overlay` is the one whose early return
    # caused the nine-artifact partial write, and it is the site the old wording implied did not
    # exist.
    #
    # WHAT ACTUALLY HOLDS is an ORDERING, not a location: every rejection appends to `findings`, and
    # every append runs before `compare_only` is computed. `compare_only` then gates both mutating
    # functions. The entire filesystem-mutation surface of this module is three calls in two
    # functions — `unlink` in prune(), `mkdir` and `write_text` in write() — and both are called only
    # from sync(), below the gate.
    #
    # ADDING A VALIDATION: append to `findings`, above `compare_only`. Never `return`. Location is
    # free; position is not.
    #
    # Three tests hold this instead of this comment, which is the point — the comment is the thing
    # that was wrong four times, and a test addressed to structure cannot go stale the way a cited
    # line number does:
    #   test_no_filesystem_mutation_is_reachable_before_the_commit_point   pins the three sites
    #   test_findings_are_all_collected_before_compare_only_is_computed    pins the ordering
    #   test_a_validation_failure_does_not_suppress_the_staleness_comparison  drives every door
    plan: list[tuple[Path, str]] = []

    def plan_write(path: Path, render, *args) -> bool:
        """Render into the plan, or record why it could not be rendered. Never writes."""
        expect(path)
        try:
            plan.append((path, render(*args)))
            return True
        except PersonaError as e:
            findings.append(str(e))
            return False

    for src, meta, body in parsed:
        name = meta["name"]

        if check_global:
            if name in contradicting:
                # Still expected, so `prune` does not also call it orphaned.
                expect(CLAUDE_AGENTS / f"{name}.md")
                expect(CODEX_AGENTS / f"{name}.toml")
            else:
                plan_write(CLAUDE_AGENTS / f"{name}.md", render_claude, meta, body)
                if codex_present():
                    plan_write(CODEX_AGENTS / f"{name}.toml", render_codex, meta, body)

        if overlays_dir and (overlays_dir / f"{name}.md").is_file():
            project_specific += 1
            claude_target = expect(repo / ".claude" / "agents" / f"{name}.md")
            codex_target = expect(repo / ".codex" / "agents" / f"{name}.toml")
            try:
                o_meta, o_body = parse(overlays_dir / f"{name}.md")
                # An overlay may retune model/effort for this project and may NARROW capability;
                # `merge_overlay` is what stops it widening. This used to be a plain dict merge, and
                # a project overlay could re-grant a judge everything the roster withholds.
                m = merge_overlay(meta, o_meta)
            except PersonaError as e:
                findings.append(f"overlay {e}")
                continue
            # THE OVERLAY HALF OF THE BIDIRECTIONAL `writes:` CHECK, which did not exist. The
            # standalone branch below warns for a project persona declaring `writes: no`; this
            # branch never looked at the overlay's `writes:` at all, because a name on the base
            # roster routes down here and cannot reach that warning. So an overlay on a base WRITER
            # — `developer` — declaring `writes: no` exited 0, warned nothing, and emitted a fully
            # write- and dispatch-capable agent whose source read `writes: no` to every human and
            # every reviewer. Roster members are already covered: `restrict_for_roster` rejects a
            # merged contradiction outright. This is the non-roster case.
            if o_meta.get("writes") is not None \
                    and o_meta["writes"] not in KNOWN_WRITES_VALUES:
                vocabulary_warnings.append((name, o_meta["writes"]))
            if claims_no_writes(m.get("writes")) and name not in JUDGING_PERSONA_NAMES:
                # The MERGED meta, not the base's and not the overlay's: what the harness receives
                # is what the merge produced, and that is the only thing the warning may describe.
                unprotected_judges.append((name, m))
            merged = overlay_body(body, o_body, repo.name)
            plan_write(claude_target, render_claude, m, merged)
            plan_write(codex_target, render_codex, m, merged)

    # A specialist the factory produced for this repo only: an overlay with no base persona behind
    # it. It is a whole persona, so it renders from itself.
    if overlays_dir and overlays_dir.is_dir():
        base_names = {m["name"] for _s, m, _b in parsed}
        for ov in sorted(overlays_dir.glob("*.md")):
            if ov.name.lower() == "readme.md":
                continue
            try:
                meta, body = parse(ov)
            except PersonaError as e:
                findings.append(f"overlay {e}")
                continue
            if meta["name"] in base_names:
                continue
            if meta.get("writes") is not None \
                    and meta["writes"] not in KNOWN_WRITES_VALUES:
                vocabulary_warnings.append((meta["name"], meta["writes"]))
            if claims_no_writes(meta.get("writes")):
                # A project judge gets NOTHING from the roster, which covers base names only. This
                # is the largest known gap in the guarantee and the personas most likely to hit it
                # are the sensitive ones — a factory derives them from the project's own PRD and
                # guardrails, so a `consent-validator` on a health-data path is exactly the shape.
                # Warned by name, loudly, for as long as the gap is open: a silent gap is how a
                # deferred fix becomes a forgotten one.
                unprotected_judges.append((meta["name"], meta))
            plan_write(repo / ".claude" / "agents" / f"{meta['name']}.md", render_claude, meta, body)
            plan_write(repo / ".codex" / "agents" / f"{meta['name']}.toml", render_codex, meta, body)
            project_specific += 1

    # PHASE B — WRITE OR COMPARE. A run with ANY finding compares and never mutates, so "this run
    # failed" and "this run changed what the harness loads" remain mutually exclusive.
    compare_only = check or bool(findings)
    for path, content in plan:
        write(path, content, compare_only, changed, stale)

    global_targets = []
    if check_global:
        global_targets = [CLAUDE_AGENTS] + ([CODEX_AGENTS] if codex_present() else [])
    prune(global_targets, expected, compare_only, removed, stale)
    if repo:
        project_targets = [repo / ".claude" / "agents", repo / ".codex" / "agents"]
        prune(project_targets, expected, compare_only, removed, stale, require_sourced=True)

    print(f"personas: {len(sources)} in the pool"
          + (f", {project_specific} project persona source"
             f"{'' if project_specific == 1 else 's'} for {repo.name}" if repo else ""))
    if roster_warning:
        print(f"  WARNING {roster_warning}", file=sys.stderr)
    for persona, value in vocabulary_warnings:
        print(f"  WARNING {persona}: `writes: {value}` is not a recognised value "
              f"({', '.join(sorted(KNOWN_WRITES_VALUES))}). It is being READ as a claim not to "
              f"write, because that is the fail-closed direction, but no check matches it "
              f"literally and it reads as a judge to every human.", file=sys.stderr)
    for judge, judge_meta in unprotected_judges:
        print(unprotected_judge_warning(judge, judge_meta), file=sys.stderr)
    # The staleness comparison is reported unconditionally, even when a validation has already
    # failed. One deletion used to buy two disablements — the record went missing, `sync()` returned
    # 2 before ever comparing, and a hand-edited generated agent stopped being caught for as long as
    # that lasted. Nine `return 2` paths in this function had that property; three remain, and the
    # two that fire before this point (no pool directory, unusable pool) are the ones where there is
    # no expected set to compare against at all.
    if stale:
        print(f"  STALE — {len(stale)} generated file(s) do not match the persona source:")
        for s in stale[:12]:
            print(f"    {s}")
        print("  run: sync_personas.py" + (f" --repo {repo}" if repo else ""))
    elif compare_only:
        print("  in sync")

    if findings:
        for f in findings:
            print(f"  ERROR {f}", file=sys.stderr)
        if not check:
            print(f"  NOTHING WAS WRITTEN — {len(findings)} finding(s). A run that reports a "
                  f"failure must not also change what the harness loads.", file=sys.stderr)
        return 2
    if stale:
        return 1
    if check:
        return 0
    for c in changed:
        print(f"  wrote   {c}")
    for r in removed:
        print(f"  removed {r}  (orphaned — persona no longer in the pool)")
    if not changed and not removed:
        print("  already up to date")
    return 0


def show_roster() -> int:
    rows = []
    try:
        sources = pool_sources()
        for src in sources:
            m, _ = parse(src)
            rows.append((m["name"], m.get("writes", "?"), m.get("claude.model", "-"),
                         m.get("claude.effort", "-"), m.get("codex.model", "-")))
    except PersonaError as e:
        print(e, file=sys.stderr)
        return 2
    w = max((len(r[0]) for r in rows), default=4)
    print(f"{'persona':<{w}}  {'writes':<6} {'claude':<10} {'effort':<7} codex")
    for n, wr, cm, ce, xm in rows:
        print(f"{n:<{w}}  {wr:<6} {cm:<10} {ce:<7} {xm}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=None, help="also render this repository's overlays")
    ap.add_argument("--check", action="store_true", help="exit 1 when generated output is stale")
    ap.add_argument("--list", action="store_true", dest="show", help="print the roster")
    args = ap.parse_args()

    if args.show:
        return show_roster()
    repo = Path(args.repo).resolve() if args.repo else None
    if repo and not repo.is_dir():
        print(f"not a directory: {repo}", file=sys.stderr)
        return 2
    try:
        return sync(repo, args.check)
    except PersonaError as e:
        # Renderer-level rejections (roster contradictions, un-renderable bodies) reach here. They
        # are a finding about the pool, not a crash, and must exit 2 rather than traceback.
        print(f"  ERROR {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
