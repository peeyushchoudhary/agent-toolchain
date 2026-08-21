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
DECISIONS = SKILL.parents[2] / "docs" / "decisions.md"

# `ap.add_argument("--repo", ...)` — the parser is the only authority on which flags exist.
ADD_ARGUMENT = re.compile(r'add_argument\(\s*"(--[a-z0-9-]+)"')
# A long option written anywhere in the step, in prose or in a fenced command.
LONG_OPTION = re.compile(r'(--[a-z][a-z0-9-]*)')


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

    def test_every_flag_it_attributes_to_the_tool_is_parsed_by_the_tool(self) -> None:
        parsed = set(ADD_ARGUMENT.findall(read(SYNC)))
        self.assertIn("--repo", parsed, "the parser was not read; the rest of this test is vacuous")
        step = section(self.text, "6 ")
        self.assertTrue(step, "no step 6 heading found in the onboarding procedure")
        self.assertIn("sync_methodology.py", step, "step 6 does not name the adoption tool")
        used = set(LONG_OPTION.findall(step))
        unknown = sorted(used - parsed)
        self.assertEqual([], unknown,
                         f"the onboarding procedure documents {unknown} for sync_methodology.py, "
                         f"which parses {sorted(parsed)}")

    def test_it_does_not_present_adoption_as_automatic(self) -> None:
        step = section(self.text, "6 ").lower()
        self.assertIn("deliberate", step,
                      "sync_methodology.py's own docstring says adoption is deliberate and never "
                      "happens on its own; a procedure that omits that invites an unattended run")


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
