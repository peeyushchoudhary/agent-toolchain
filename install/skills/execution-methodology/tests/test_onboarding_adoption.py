"""Guard the two prose routes that let a repository be onboarded and never adopt anything.

Two defects were found together, and both were silent.

  1. `project-onboarding` never named this skill. A repository could complete every onboarding step
     and still be unadopted for the methodology, with nothing in the onboarding procedure saying so.
     The only thing that ever said so was a conformance run nobody was told to make.
  2. `project-onboarding` verified itself with six hand-rolled commands, five of which re-ran
     conformance checks with weaker flags and were judged by exit code. Three of those callees exit
     0 while carrying the finding on another stream, so that block reported green over a repository
     whose project judges were unprotected. It has been replaced by one call to the conformance
     checker.

Prose is what failed, so prose is what is pinned. The assertions here are deliberately about
routing and interface, never about wording:

  - the onboarding procedure has a step that routes to `sync_methodology.py`;
  - every flag it attributes to that script is a flag that script actually parses, so a renamed or
    removed option is caught here instead of by a reader typing it;
  - it does not claim adoption is automatic, because the module docstring of `sync_methodology.py`
     says the opposite and a procedure that disagrees with its own tool is worse than none;
  - its verification step delegates to the conformance checker and states what happens when that
    checker is absent, so the replaced block cannot quietly grow back.

This suite is the repository's only unittest suite, which is why a test about a sibling skill's
prose lives here. The assertions that need files outside this skill's own tree SKIP rather than
fail: in the installed layout `project-onboarding` is a sibling directory and resolves, while the
repository's `docs/` is not present at all. A skip names what was not checked; it never passes.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
SYNC = SKILL / "scripts" / "sync_methodology.py"
ONBOARDING = SKILL.parent / "project-onboarding" / "SKILL.md"


def first_present(*candidates: Path) -> Path:
    """The first candidate that exists, else the first candidate.

    TWO LAYOUTS RESOLVE HERE, AND NEITHER IS WRONG. In the installed layer the repository documents
    sit flat under `<root>/docs/`; in the repository that publishes this skill they now sit under
    the shared structure standard, in `docs/decisions/` and `docs/runbooks/`. A single hardcoded
    path is correct in one of those and SILENTLY SKIPS in the other — which is what happened: five
    assertions in this file stopped executing the day the documents moved, and nothing went red,
    because the guard below degrades a missing file to a skip. A skip names what was not checked and
    never passes, so the suite was honest; it was simply no longer checking anything.

    Falling back to the first candidate when none exists keeps the skip message pointing at the
    layout this copy expects, rather than at whichever alternative was listed last.
    """
    for c in candidates:
        if c.is_file():
            return c
    return candidates[0]


REPO = SKILL.parents[2]
DECISIONS = first_present(REPO / "docs" / "decisions" / "decisions.md",
                          REPO / "docs" / "decisions.md")
# The same step, written twice for two audiences. Repairing one copy of a duplicated block and not
# the other is exactly how the defective Verify block survived: it stayed reachable through the more
# likely door. Both are pinned, and pinned to each other.
GUIDE = first_present(REPO / "docs" / "runbooks" / "onboarding-a-project.md",
                      REPO / "docs" / "onboarding-a-project.md")

# `ap.add_argument("--repo", ...)` — the parser is the only authority on which flags exist.
ADD_ARGUMENT = re.compile(r'add_argument\(\s*"(--[a-z0-9-]+)"')
# A long option written anywhere in the step, in prose or in a fenced command.
LONG_OPTION = re.compile(r'(--[a-z][a-z0-9-]*)')
# Every script the step may tell a reader to run, and the parser that decides what it accepts.
# Checking the step's flags against ONE script's parser was right while the step named one script.
# It now names three, and a flag checked against the wrong parser is a flag checked by nobody.
TOOLS = {"sync_methodology.py": SYNC,
         "spec_check.py": SKILL / "scripts" / "spec_check.py",
         "sync_personas.py": SKILL.parent / "agent-personas" / "scripts" / "sync_personas.py"}
# A command line naming one of those scripts, up to the end of the line. Prose flags are attributed
# to the nearest preceding script name on the same line, which is where a command is written.
COMMAND = re.compile(r'([a-z_]+\.py)((?:[^\S\n]+[^\s#]+)*)')


def read(path: Path) -> str:
    """Read a file this check depends on, strictly. Never fall back to a partial decode."""
    return path.read_text(encoding="utf-8-sig")


def section(text: str, heading_starts_with: str) -> str:
    """The markdown section whose heading starts with the given text, up to the next heading.

    Matched on a prefix rather than the whole line so renaming the rest of a heading does not
    silently drop the assertion to an empty string — an empty section would satisfy every
    `assertNotIn` in this file.
    """
    out: list[str] = []
    depth = 0
    for line in text.splitlines():
        if out:
            if line.startswith("#") and len(line) - len(line.lstrip("#")) <= depth:
                break
            out.append(line)
        elif line.startswith("#") and line.lstrip("#").strip().startswith(heading_starts_with):
            depth = len(line) - len(line.lstrip("#"))
            out.append(line)
    return "\n".join(out)


class OnboardingRoutesToAdoption(unittest.TestCase):
    def setUp(self) -> None:
        if not ONBOARDING.is_file():
            self.skipTest(f"project-onboarding is not a sibling of this skill at {ONBOARDING}")
        self.text = read(ONBOARDING)

    def test_a_step_routes_to_the_adoption_tool(self) -> None:
        self.assertIn("sync_methodology.py", self.text,
                      "the onboarding procedure never names the adoption tool, so a repository can "
                      "complete every step and stay unadopted with nothing saying so")

    def test_every_flag_it_attributes_to_a_tool_is_parsed_by_that_tool(self) -> None:
        step = section(self.text, "6 ")
        self.assertTrue(step, "no step 6 heading found in the onboarding procedure")
        self.assertIn("sync_methodology.py", step, "step 6 does not name the adoption tool")
        checked = 0
        for script, arguments in COMMAND.findall(step):
            path = TOOLS.get(script)
            if path is None or not path.is_file():
                continue
            parsed = set(ADD_ARGUMENT.findall(read(path)))
            self.assertIn("--repo" if script != "spec_check.py" else "--root", parsed,
                          f"{script}'s parser was not read; this assertion would be vacuous")
            unknown = sorted(set(LONG_OPTION.findall(arguments)) - parsed)
            self.assertEqual([], unknown,
                             f"the onboarding procedure documents {unknown} for {script}, "
                             f"which parses {sorted(parsed)}")
            checked += 1
        self.assertTrue(checked, "no command in step 6 was checked against a parser")

    def test_it_does_not_present_adoption_as_automatic(self) -> None:
        step = section(self.text, "6 ").lower()
        self.assertIn("deliberate", step,
                      "sync_methodology.py's own docstring says adoption is deliberate and never "
                      "happens on its own; a procedure that omits that invites an unattended run")


class BothCopiesOfStepSixSayTheSameThing(unittest.TestCase):
    """The skill and the guide carry the same step for two audiences, and they have drifted once.

    The failing pattern is recorded: a duplicated block was repaired in the skill and left defective
    in the guide, which is the copy more readers reach. So the assertions here are about the CLAIMS
    both copies have to make, never about wording — the two are deliberately written differently.

    Persona configuration is the claim being pinned. Adopting the methodology in a repository has to
    configure that repository's validators too; the measurement that made this a step is that a
    project's own domain validators are cited 100 times at review time and 5 times on a spec.
    """

    def setUp(self) -> None:
        missing = [p for p in (ONBOARDING, GUIDE) if not p.is_file()]
        if missing:
            self.skipTest(f"not present in this layout: {', '.join(str(p) for p in missing)}")
        self.steps = {"skill": section(read(ONBOARDING), "6 "),
                      "guide": section(read(GUIDE), "6 ")}
        for where, step in self.steps.items():
            self.assertTrue(step, f"no step 6 heading in the {where}")

    def test_both_bind_adoption_to_persona_configuration(self) -> None:
        for where, step in self.steps.items():
            with self.subTest(copy=where):
                self.assertIn("docs/agents/personas/", step,
                              "adoption says nothing about this repository's own validators, so a "
                              "repository can adopt the methodology and leave every horizontal "
                              "invariant owned by nobody")
                self.assertIn("covers:", step,
                              "the step never names the one key that binds a validator to a "
                              "concern, so rule F keeps checking nothing")

    def test_both_say_the_unowned_concerns_are_the_output_to_act_on(self) -> None:
        for where, step in self.steps.items():
            with self.subTest(copy=where):
                self.assertIn("owned by nobody", step.lower(),
                              "the useful output is the list of invariants nothing is bound to; a "
                              "step that does not point at it points at nothing")

    def test_neither_claims_the_line_is_written_for_you(self) -> None:
        for where, step in self.steps.items():
            with self.subTest(copy=where):
                self.assertIn("nothing writes that line", step.lower(),
                              "every script in this skill writes nothing, and a binding a script "
                              "guessed is a binding nobody holds")

    def test_both_say_a_repository_without_a_pool_is_not_at_fault(self) -> None:
        for where, step in self.steps.items():
            with self.subTest(copy=where):
                self.assertIn("has not adopted overlays", step,
                              "a repository with no persona pool is in a legitimate state; "
                              "reporting it as a fault is how a check gets muted")


class OnboardingDelegatesItsVerification(unittest.TestCase):
    def setUp(self) -> None:
        if not ONBOARDING.is_file():
            self.skipTest(f"project-onboarding is not a sibling of this skill at {ONBOARDING}")
        self.verify = section(read(ONBOARDING), "Verify")
        self.assertTrue(self.verify, "no Verify section found in the onboarding procedure")

    def test_it_calls_the_conformance_checker(self) -> None:
        self.assertIn("check_conformance.py", self.verify,
                      "the Verify step does not delegate; the block it replaced re-ran five "
                      "conformance checks with weaker flags and judged them by exit code")

    def test_it_does_not_hand_roll_the_checks_again(self) -> None:
        for script in ("check_toolchain.py", "sync_personas.py", "install_hooks.py"):
            self.assertNotIn(script, self.verify,
                             f"{script} is back in the Verify step; the conformance checker already "
                             "runs it, with flags this step cannot get right")

    def test_it_says_what_happens_when_the_checker_is_absent(self) -> None:
        self.assertIn("NOT CHECKED", self.verify,
                      "the conformance checker is optional and this installer does not ship it; "
                      "without this the step either skips in silence or reports a green it did "
                      "not earn")


class TheSplitIsRecorded(unittest.TestCase):
    def setUp(self) -> None:
        if not DECISIONS.is_file():
            self.skipTest(f"the repository decision record is not present at {DECISIONS}")
        self.text = read(DECISIONS)

    def test_both_skills_are_named_in_the_decision_record(self) -> None:
        for name in ("project-onboarding", "project-conformance"):
            self.assertIn(name, self.text,
                          f"{name} is absent from the decision record; an undocumented split "
                          "reads as accretion and gets merged by accident")


if __name__ == "__main__":
    unittest.main()
