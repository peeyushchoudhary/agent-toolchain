#!/usr/bin/env python3
"""Pin references/execution-loop.md to the interfaces of the scripts it tells an operator to run.

Run: python3 -m unittest tests.test_execution_loop   (from the skill root)
  or python3 -m unittest discover -s tests -t tests

WHY THIS FILE EXISTS. The operating loop was one sentence of prose in SKILL.md for the whole life
of the methodology, and the dispatch primitives it now names were merged without an operator. Prose
that names a flag drifts silently: the flag is renamed, the paragraph is not, and a reader types a
command that no longer exists. Worse, and measured seven times in this toolchain, a flag can be
ACCEPTED and never wired — `--milestone M<n> --commit REV` parsed the argument and never called the
check, and every test of that script passed.

So this suite asserts two different things, and the second is the point:

  * STATIC — every command in the document is a script that exists, spelled with options that
    script's own parser defines, with a value where the parser takes one. The parser is the only
    authority; nothing here hard-codes a flag list.
  * WIRED — the document's own command lines are RUN, against a two-feature milestone fixture with
    real commits, and each one is asserted to produce its documented EFFECT. Not its exit code
    alone: the stray-write run must name the other task that owns the path, the mid-phase run must
    name the uncommitted file, the trace run must say what T7 judged. A step that is accepted and
    inert fails here.

The command lines are read out of the document rather than repeated here. Editing a command in the
document therefore changes what this suite executes, which is what stops the two from parting.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL / "scripts"
LOOP = SKILL / "references" / "execution-loop.md"
SKILL_MD = SKILL / "SKILL.md"
POOL = SKILL.parent / "agent-personas" / "personas"

# Placeholders the document is allowed to use, and what this suite substitutes for each. A token in
# a documented command that is not a real value and not a key here fails: an unrunnable command is
# how a procedure becomes decorative.
PLACEHOLDERS = ("M<n>", "<seal-rev>", "<rev>", "<range>", "<ids>", "<card>", "<receipt>",
                "<tree>", "<gate>", "<workspace>", "<subject>", "N")
# The steps the loop cannot lose. Each entry is a script and an option that must appear in the
# document at least once, so a deleted step is a failure rather than a quiet omission.
REQUIRED = (
    ("plan_waves.py", "--milestone"), ("plan_waves.py", "--since"), ("plan_waves.py", "--ready"),
    ("plan_waves.py", "--in-flight"), ("plan_waves.py", "--limit"), ("plan_waves.py", "--commit"),
    ("plan_waves.py", "--json"),
    ("validate_card.py", "--phase"), ("validate_card.py", "--repo"),
    ("trace_check.py", "--evidence"), ("trace_check.py", "--commit"),
    ("spec_check.py", "--deferred"),
    ("milestone_seal.py", "--record"), ("milestone_seal.py", "--gate"),
    ("milestone_seal.py", "--verify"),
    ("check_review_budget.py", "--next"),
)
# Named in the document because the loop has to cast them somewhere. Five of these were previously
# reachable only through one row of one table in methodology.py — including both implementers.
# `docs-steward` and `planner` were folded into `product-steward` and `chief-of-staff`, and
# `contract-architect` was retired as a review seat. Their persona files remain so that 425 existing
# citations across the fleet still resolve, but the loop must cast the SUCCESSOR — a procedure that
# still names a superseded seat is how a merge becomes cosmetic.
CAST = ("chief-of-staff", "developer", "senior-developer", "scout", "test-judge", "reviewer",
        "security-validator", "acceptance", "product-steward")
SUPERSEDED = ("docs-steward", "planner", "contract-architect")

BASH_FENCE = re.compile(r"^```bash\s*$")
FENCE_END = re.compile(r"^```\s*$")
BACKTICKED = re.compile(r"`([a-z][a-z-]+)`")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def commands(text: str) -> list[list[str]]:
    """Every command line inside a ```bash fence, tokenised. Comment lines are not commands."""
    out, inside = [], False
    for line in text.splitlines():
        if not inside and BASH_FENCE.match(line):
            inside = True
            continue
        if inside and FENCE_END.match(line):
            inside = False
            continue
        if inside and line.strip() and not line.strip().startswith("#"):
            out.append(shlex.split(line.strip()))
    return out


def add_argument_calls(source: str) -> list[str]:
    """The text of each `add_argument(...)` call, parenthesis-balanced rather than line-based."""
    calls, start = [], 0
    while True:
        found = source.find("add_argument(", start)
        if found == -1:
            return calls
        depth, i = 0, found + len("add_argument")
        while i < len(source):
            if source[i] == "(":
                depth += 1
            elif source[i] == ")":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        calls.append(source[found:i + 1])
        start = i + 1


def options(script: Path) -> dict[str, bool]:
    """Long option -> does it take a value. The script's parser is the only authority here."""
    table = {}
    for call in add_argument_calls(read(script)):
        for name in re.findall(r'"(--[a-z0-9-]+)"', call):
            table[name] = "store_true" not in call
    return table


def choices(script: Path, option: str) -> list[str]:
    for call in add_argument_calls(read(script)):
        if f'"{option}"' in call and "choices=" in call:
            return re.findall(r'"([a-z]+)"', call.split("choices=", 1)[1])
    return []


def section(text: str, starts_with: str) -> str:
    """One paragraph, from the line that starts with the marker to the next blank line."""
    out, taking = [], False
    for line in text.splitlines():
        if line.startswith(starts_with):
            taking = True
        elif taking and not line.strip():
            break
        if taking:
            out.append(line)
    return "\n".join(out)


class DocumentedInterfaceTest(unittest.TestCase):
    """Static: what the document says you can type, against what the parsers accept."""

    def setUp(self) -> None:
        self.text = read(LOOP)
        self.commands = commands(self.text)

    def test_the_document_holds_commands_at_all(self) -> None:
        """The guard on every other assertion here: an empty list satisfies every loop below."""
        self.assertGreaterEqual(len(self.commands), 12, "the loop must be written as commands")

    def test_every_command_names_a_script_that_exists(self) -> None:
        for command in self.commands:
            with self.subTest(command=command):
                self.assertTrue((SCRIPTS / command[0]).is_file(),
                                f"{command[0]} is not a script in {SCRIPTS.name}/")

    def test_every_documented_option_is_one_its_script_parses(self) -> None:
        for command in self.commands:
            table = options(SCRIPTS / command[0])
            for token in command[1:]:
                if token.startswith("--"):
                    with self.subTest(command=command[0], option=token):
                        self.assertIn(token, table,
                                      f"{command[0]} does not parse {token}")

    def test_an_option_that_takes_a_value_is_documented_with_one(self) -> None:
        """And a flag that takes none is never documented with an argument stuck to it."""
        for command in self.commands:
            table = options(SCRIPTS / command[0])
            for index, token in enumerate(command[1:], start=1):
                if not token.startswith("--") or token not in table:
                    continue
                following = command[index + 1] if index + 1 < len(command) else None
                with self.subTest(command=command[0], option=token):
                    if table[token]:
                        self.assertIsNotNone(following, f"{token} takes a value")
                        self.assertFalse(following.startswith("--"),
                                         f"{token} takes a value, not {following}")
                    elif following is not None:
                        self.assertTrue(following.startswith("--"),
                                        f"{token} takes no value, but {following!r} follows it")

    def test_every_placeholder_is_one_this_suite_can_substitute(self) -> None:
        """An unrunnable placeholder is a command nobody can execute, documented as if they could."""
        for command in self.commands:
            for token in command[1:]:
                if token.startswith("--") or token in (".", "0", "1", "2"):
                    continue
                if re.fullmatch(r"[a-z0-9_./-]+", token):
                    continue                       # a real, literal value
                with self.subTest(command=command[0], token=token):
                    self.assertIn(token, PLACEHOLDERS, f"{token!r} cannot be run by anyone")

    def test_the_phase_values_are_the_ones_the_validator_defines(self) -> None:
        allowed = choices(SCRIPTS / "validate_card.py", "--phase")
        self.assertTrue(allowed, "validate_card.py no longer declares --phase choices")
        used = [command[index + 1]
                for command in self.commands if command[0] == "validate_card.py"
                for index, token in enumerate(command) if token == "--phase"]
        self.assertTrue(used, "the loop must name a phase")
        for value in used:
            self.assertIn(value, allowed)

    def test_no_step_of_the_loop_is_missing(self) -> None:
        pairs = {(command[0], token) for command in self.commands for token in command}
        for script, option in REQUIRED:
            with self.subTest(script=script, option=option):
                self.assertIn((script, option), pairs,
                              f"the loop no longer runs {script} {option}")

    def test_the_loop_casts_a_persona_at_every_step(self) -> None:
        for persona in CAST:
            with self.subTest(persona=persona):
                self.assertIn(f"`{persona}`", self.text,
                              f"{persona} is cast nowhere in the loop")

    def test_the_loop_does_not_cast_a_superseded_seat(self) -> None:
        """Measured before merging: these three drew 0, 0 and 6 blocking verdicts as review seats.
        Their files stay so existing references resolve; dispatching to them is what stops."""
        for persona in SUPERSEDED:
            with self.subTest(persona=persona):
                self.assertNotIn(f"`{persona}`", self.text,
                                 f"{persona} was merged away but the loop still casts it")

    @unittest.skipUnless(POOL.is_dir(), "the persona pool is not installed beside this skill")
    def test_every_base_persona_the_loop_names_exists_in_the_pool(self) -> None:
        """A misspelled persona does not fail loudly; it falls back to a general-purpose agent."""
        present = {path.stem for path in POOL.glob("*.md")}
        named = {name for name in BACKTICKED.findall(self.text) if name in present or
                 name in CAST}
        self.assertTrue(named)
        for name in sorted(named):
            with self.subTest(persona=name):
                self.assertIn(name, present, f"no persona named {name} in the pool")

    def test_the_skill_points_here_and_does_not_hold_the_loop_itself(self) -> None:
        skill = read(SKILL_MD)
        self.assertIn("references/execution-loop.md", skill)
        paragraph = section(skill, "**Executing**")
        self.assertIn("execution-loop.md", paragraph)
        self.assertLessEqual(len(paragraph.splitlines()), 8,
                             "the pointer has grown back into a procedure")
        for detail in ("--ready", "--phase mid", "--in-flight", "--record"):
            self.assertNotIn(detail, paragraph,
                             f"{detail} belongs in the reference, not in two places")

    def test_the_two_documents_do_not_contradict_each_other_on_review_width(self) -> None:
        """The rule lives in SKILL.md; this document was written against the OLD one.

        MEASURED, and this is why a prose pin is here rather than a checker. Across 1,051
        round-marked review artifacts the decisive cut is STAGE: design/plan blocks at 0.74 per
        artifact, implementation at 0.09. The old rule -- "at most one, plus `security-validator`
        on safety surfaces; never a panel" -- was written once in SKILL.md and then ASSUMED by
        section 4 of this document, which routes exactly one model reviewer. When the rule became
        stage-scoped, section 4 stopped being a consequence of it and became a contradiction of it
        unless it says which stage it governs.

        Nothing executable can catch that. The contradiction is not a flag, a path, or an exit
        code; it is two English sentences that disagree, in two files, one of which a reader
        reaches without the other. This session has now found NINE checkers that passed their own
        tests and were inert against the real corpus, every one of them a WORD test standing in
        for a STRUCTURE that was not there. There is no structure here to test. So the honest
        enforcement is the smallest one that cannot go inert: assert the falsified clause is in
        NEITHER file, and that BOTH carry the stage word that replaced it. This test reads the two
        shipped documents, so it has no fixture to pass against and no corpus to miss.
        """
        skill = read(SKILL_MD)
        for name, text in (("the skill", skill), ("the loop", self.text)):
            with self.subTest(document=name):
                self.assertNotIn(
                    "never a panel", text,
                    f"{name} still carries the falsified rule; design/plan blocks at 0.74")
                self.assertIn(
                    "stage", text.lower(),
                    f"{name} does not say which stage its review width applies to")
        self.assertIn("PANEL", self.text.upper(),
                      "section 4 must say a panel belongs at design, not here")
        self.assertIn("IMPLEMENTATION STAGE ONLY", self.text.upper(),
                      "section 4 must declare the stage it governs")
        self.assertIn("test-judge", self.text,
                      "the implementation width is one reviewer plus test-judge")

    def test_the_public_repository_rule_still_holds_for_this_document(self) -> None:
        """Assembled from parts on purpose: the repository's own identifier guard reads this file
        too, and a literal home prefix written here is the very thing it refuses."""
        for forbidden in ("/Us" + "ers/", "/ho" + "me/", "C:" + chr(92)):
            self.assertNotIn(forbidden, self.text, "a personal path reached a public document")


class WiredTest(unittest.TestCase):
    """Live: the document's own commands, run against a fixture, asserted on their EFFECT.

    The fixture is two features in one milestone, because that is the only scope in which a commit
    landing inside ANOTHER feature's declared write set is visible at all.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "repo"
        self.state = Path(self._tmp.name) / "state"
        (self.root / "docs" / "product" / "specs").mkdir(parents=True)
        (self.root / "docs" / "product" / "plans").mkdir(parents=True)
        (self.root / "docs" / "product" / "milestones").mkdir(parents=True)
        self.write("docs/product/prd.md",
                   "---\ntitle: A product\nstatus: approved\nupdated: 2026-01-01\n---\n\n# A product\n")
        for ident, slug in (("F-7", "one"), ("F-8", "two")):
            self.write(f"docs/product/specs/{ident}-{slug}.md",
                       f"---\nid: {ident}\ntitle: feature {ident}\nprd: docs/product/prd.md\n"
                       f"status: approved\nmilestone: M1\nupdated: 2026-01-01\n---\n\n"
                       f"# {ident} — feature\n")
        for ident, slug, area in (("F-7", "one", "7"), ("F-8", "two", "8")):
            self.write(f"docs/product/plans/{ident}-{slug}.md",
                       f"---\nid: {ident}\n---\n\n# {ident} — plan\n\n```task\ntask: T1\n"
                       f"title: build {ident}\nlane: full\nwrites: [src/{area}/**]\n"
                       f"covers: [AC-1]\n```\n")
        self.write("docs/product/milestones/M1-first.md",
                   "---\nmilestone: M1\ntitle: the milestone\nstatus: building\n"
                   "updated: 2026-01-01\n---\n\n# M1 — the milestone\n\n"
                   "## Cross-feature validation\nGate: true\n\n"
                   "## Deferred\n\n- **D-1** a stray finding nobody owns yet\n"
                   "   found_by: F-7/T1\n   site: src/7/a.txt\n   threatens: AC-1\n"
                   "   trigger: none\n   owner: M2\n   raised: 2026-01-01\n")
        self.write("card.yaml", CARD)
        self.git("init", "-q", ".")
        self.git("config", "user.email", "a@b.c")
        self.git("config", "user.name", "t")
        self.git("add", ".")
        self.git("commit", "-q", "-m", "the plans")
        self.base = self.git("rev-parse", "HEAD")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write(self, relative: str, text: str) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def git(self, *args: str) -> str:
        done = subprocess.run(["git", *args], cwd=self.root, capture_output=True, text=True)
        return done.stdout.strip()

    def commit(self, subject: str, *paths: str) -> str:
        for relative in paths:
            self.write(relative, subject + "\n")
        self.git("add", ".")
        self.git("commit", "-q", "-m", subject)
        return self.git("rev-parse", "HEAD")

    def documented(self, script: str, *must_contain: str) -> list[str]:
        """The document's own command line for a step, chosen by the flags it must carry."""
        for command in commands(read(LOOP)):
            if command[0] == script and all(token in command for token in must_contain):
                return list(command)
        self.fail(f"the loop no longer documents {script} {' '.join(must_contain)}")

    def run_documented(self, command: list[str],
                       **values: str) -> subprocess.CompletedProcess:
        """Substitute the document's placeholders and run it, with the repo as the cwd.

        Not named `run`: `TestCase.run` is the runner entry point, and shadowing it makes every
        test in the class abort with an attribute error rather than fail with a reason.
        """
        table = {"M<n>": "M1", "<seal-rev>": self.base, "<rev>": "HEAD", "N": "2",
                 "<range>": f"{self.base}..HEAD", "<ids>": "F-7/T1",
                 "<card>": str(self.root / "card.yaml"), "<workspace>": str(self.root / ".work"), "<subject>": "F-7-T1"}
        table.update(values)
        argv = [sys.executable, str(SCRIPTS / command[0])]
        argv += [table.get(token, token) for token in command[1:]]
        env = {**os.environ, "XDG_STATE_HOME": str(self.state), "HOME": str(self.state / "home")}
        return subprocess.run(argv, cwd=self.root, capture_output=True, text=True, env=env)

    # --- step 0: resume ---------------------------------------------------------------------

    def test_the_resume_command_rebuilds_the_whole_status_from_git(self) -> None:
        result = self.run_documented(self.documented("plan_waves.py", "--since", "--json"))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(sorted(payload["status"]), ["F-7/T1", "F-8/T1"])
        self.assertFalse(payload["complete"], "nothing is committed yet")
        self.commit("feat(F-7/T1): the work", "src/7/a.txt")
        again = json.loads(self.run_documented(self.documented("plan_waves.py", "--since", "--json")).stdout)
        self.assertEqual(again["status"]["F-7/T1"]["state"], "done")

    def test_a_repository_that_never_adopted_the_layout_refuses_to_report_a_status(self) -> None:
        """Measured on four real repositories: none has `docs/product/plans/`. Step 0 must exit 2
        and say why there, because an empty exit-0 status reads as `that milestone is clean`."""
        for path in sorted((self.root / "docs" / "product" / "plans").iterdir()):
            path.unlink()
        result = self.run_documented(self.documented("plan_waves.py", "--since", "--json"))
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("nothing to derive status for", result.stderr)
        payload = json.loads(self.run_documented(["plan_waves.py", "--root", ".",
                                                  "--milestone", "M<n>", "--json"]).stdout)
        self.assertEqual(payload["features"], ["F-7", "F-8"],
                         "the specs still declare the milestone; only the plans are gone")

    def test_an_unfinished_milestone_is_not_an_error(self) -> None:
        """`complete` is a key. Overloading exit 1 with `not done yet` gets a check switched off."""
        payload = json.loads(self.run_documented(self.documented("plan_waves.py", "--since", "--json")).stdout)
        self.assertIn("complete", payload)

    # --- step 1: select ---------------------------------------------------------------------

    def test_the_dispatch_command_returns_a_set_that_excludes_what_is_in_flight(self) -> None:
        command = self.documented("plan_waves.py", "--ready")
        result = self.run_documented(command)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["ready"], ["F-8/T1"], "F-7/T1 was given as in flight")
        self.assertEqual(payload["in_flight"], ["F-7/T1"])

    def test_an_in_flight_id_no_task_declares_is_exit_two_and_not_a_finding(self) -> None:
        result = self.run_documented(self.documented("plan_waves.py", "--ready"), **{"<ids>": "F-9/T9"})
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("F-9/T9", result.stderr)

    # --- step 3: mid-task drift -------------------------------------------------------------

    def test_the_mid_phase_command_names_the_uncommitted_file_outside_the_write_set(self) -> None:
        """The card allows src/7; the working tree holds an edit to src/8."""
        self.write("src/8/stray.txt", "written by the wrong task\n")
        result = self.run_documented(self.documented("validate_card.py", "--phase", "mid"))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("src/8/stray.txt", result.stdout)
        self.assertIn("uncommitted path(s) compared", result.stdout)

    def test_the_pre_phase_command_does_not_look_at_the_working_tree(self) -> None:
        """The two phases must not be the same run under two names."""
        self.write("src/8/stray.txt", "written by the wrong task\n")
        result = self.run_documented(self.documented("validate_card.py", "--phase", "pre"))
        self.assertNotIn("src/8/stray.txt", result.stdout)

    # --- step 6: the commit check -----------------------------------------------------------

    def test_the_post_commit_command_names_the_task_that_owns_the_stray_path(self) -> None:
        """The regression this whole file exists for: the milestone scope accepted `--commit` and
        never called the check, so a commit into another feature's set read as clean."""
        self.commit("feat(F-7/T1): strays into the other feature", "src/7/a.txt", "src/8/b.txt")
        result = self.run_documented(self.documented("plan_waves.py", "--commit"))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("src/8/b.txt", result.stdout)
        self.assertIn("F-8/T1", result.stdout)

    def test_a_commit_inside_the_declared_set_is_clean(self) -> None:
        self.commit("feat(F-7/T1): stays home", "src/7/a.txt")
        result = self.run_documented(self.documented("plan_waves.py", "--commit"))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    # --- step 7: deferrals ------------------------------------------------------------------

    def test_the_deferral_queue_lists_the_register_and_exits_zero(self) -> None:
        """A queue view, not a gate. The gate is rule E in the ordinary run, at the seal."""
        result = self.run_documented(self.documented("spec_check.py", "--deferred"))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("D-1", result.stdout)

    # --- step 8: coverage -------------------------------------------------------------------

    def test_the_trace_command_reports_what_t7_judged(self) -> None:
        receipt = self.evidence()
        result = self.run_documented(self.documented("trace_check.py", "--evidence", "--commit"),
                          **{"<receipt>": str(receipt)})
        self.assertIn(result.returncode, (0, 1), result.stdout + result.stderr)
        self.assertIn("T7", result.stdout, "the range was accepted and never used")

    # --- step 9: the seal -------------------------------------------------------------------

    def test_the_gate_command_is_read_from_the_milestone_document(self) -> None:
        result = self.run_documented(self.documented("milestone_seal.py", "--gate"))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.strip(), "true")

    def test_recording_a_seal_needs_a_clean_tree_and_then_verifies_against_it(self) -> None:
        self.write("src/7/a.txt", "uncommitted\n")
        dirty = self.run_documented(self.documented("milestone_seal.py", "--record"))
        self.assertEqual(dirty.returncode, 2, dirty.stdout + dirty.stderr)
        self.commit("feat(F-7/T1): the work", "src/7/a.txt")
        recorded = self.run_documented(self.documented("milestone_seal.py", "--record"))
        self.assertEqual(recorded.returncode, 0, recorded.stdout + recorded.stderr)
        tree = self.git("rev-parse", "HEAD^{tree}")
        verified = self.run_documented(self.documented("milestone_seal.py", "--verify"),
                            **{"<tree>": tree, "<gate>": "true"})
        self.assertEqual(verified.returncode, 0, verified.stdout + verified.stderr)

    def test_a_receipt_does_not_survive_a_change_to_the_tree(self) -> None:
        self.run_documented(self.documented("milestone_seal.py", "--record"))
        self.commit("feat(F-8/T1): more work", "src/8/a.txt")
        verified = self.run_documented(self.documented("milestone_seal.py", "--verify"),
                            **{"<tree>": self.git("rev-parse", "HEAD^{tree}"), "<gate>": "true"})
        self.assertEqual(verified.returncode, 1, verified.stdout)

    # --- the loop writes nothing ------------------------------------------------------------

    def test_no_documented_command_writes_inside_the_repository(self) -> None:
        """Every step of the loop reads. The one that executes anything is the seal, and its
        receipt is written outside the tree on purpose."""
        self.commit("feat(F-7/T1): the work", "src/7/a.txt")
        receipt = self.evidence()
        tree = self.git("rev-parse", "HEAD^{tree}")
        before = self.snapshot()
        for command in commands(read(LOOP)):
            self.run_documented(command, **{"<receipt>": str(receipt), "<tree>": tree,
                                            "<gate>": "true"})
        self.assertEqual(before, self.snapshot())

    def snapshot(self) -> dict:
        """Every tracked-side file and its mtime. `.git` is excluded because reading a repository
        legitimately refreshes the index; what is asserted is that no CONTENT file moves."""
        return {path: path.stat().st_mtime_ns for path in sorted(self.root.rglob("*"))
                if path.is_file() and ".git" not in path.parts}

    def evidence(self) -> Path:
        """A real receipt, produced by the real scripts, exactly as the card protocol says."""
        results = self.root / "build" / "test-results" / "test"
        results.mkdir(parents=True, exist_ok=True)
        work = self.root / ".work"
        work.mkdir(exist_ok=True)
        start, receipt = work / "start.json", work / "evidence.json"
        subprocess.run([sys.executable, str(SCRIPTS / "start_junit_run.py"),
                        "--results", str(results), "--output", str(start)],
                       capture_output=True, text=True, check=True)
        (results / "TEST-com.x.OneTest.xml").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<testsuite name="com.x.OneTest" tests="1" skipped="0" failures="0" errors="0">\n'
            '  <testcase classname="com.x.OneTest" name="works__F7_AC1" time="0.01"/>\n'
            '</testsuite>\n', encoding="utf-8")
        subprocess.run([sys.executable, str(SCRIPTS / "verify_junit.py"),
                        "--results", str(results), "--start-receipt", str(start),
                        "--output", str(receipt), "--expect", "com.x.OneTest=1"],
                       capture_output=True, text=True, check=True)
        return receipt


CARD = """\
id: EX-01
title: Build the first feature
goal: The first feature exists.
persona: senior-developer

prerequisites: []

exclusive_writes:
  - src/7/**

forbidden_paths:
  - src/8/**

context_acquisition:
  - "Read nothing else unless this card names it."

frozen_values:
  - "Ids are qualified, as F-7/T1."

invariants:
  - "The other feature's paths are not this task's."

instructions:
  - "Write the first feature."

tests:
  - "Retain: src/7/a.txt :: none"

gate_risk: none

validation:
  - cwd: .
    argv:
      - /bin/echo
      - ok

stop_conditions:
  - "a file outside exclusive_writes must change"

record_to: docs/product/milestones/M1-first.md

handoff: chief-of-staff

commit_subject: "feat(F-7/T1): the work"
"""


if __name__ == "__main__":
    unittest.main()
