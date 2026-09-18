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
SETUP = SKILL.parent / "methodology-management" / "references" / "setup.md"


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
# GUIDE is the public compatibility route. It and the project-onboarding compatibility skill are
# pinned only to the canonical management setup owner, which holds the procedure and its claims.
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


class CompatibilityRoutesToCanonicalSetup(unittest.TestCase):
    """Compatibility routes point to one setup owner; that owner carries the persona decision."""

    def setUp(self) -> None:
        missing = [p for p in (ONBOARDING, SETUP) if not p.is_file()]
        if missing:
            self.skipTest(f"not present in this layout: {', '.join(str(p) for p in missing)}")
        self.onboarding = read(ONBOARDING)
        self.setup = read(SETUP)

    def test_compatibility_skill_routes_to_the_canonical_setup_owner(self) -> None:
        self.assertIn("methodology-management/references/setup.md", self.onboarding)

    def test_public_guide_routes_to_the_canonical_setup_owner_when_present(self) -> None:
        if not GUIDE.is_file():
            self.skipTest(f"public guide is not present in this layout: {GUIDE}")
        guide = read(GUIDE)
        self.assertIn("methodology-management/references/setup.md", guide)
        self.assertIn("does not duplicate the setup", guide.lower())

    def test_setup_binds_persona_configuration_to_its_source_owner(self) -> None:
        self.assertIn("skills/agent-personas/SKILL.md", self.setup)
        self.assertIn("docs/agents/personas/", self.setup)
        self.assertIn("covers:", self.setup)

    def test_setup_reports_unowned_concerns_as_action_output(self) -> None:
        self.assertIn("report relevant concerns owned by nobody as action output",
                      self.setup.lower())

    def test_setup_does_not_claim_the_binding_is_written_automatically(self) -> None:
        self.assertIn("nothing writes that line automatically",
                      " ".join(self.setup.lower().split()))

    def test_setup_treats_no_pool_as_nonfault_when_the_decision_is_explicit(self) -> None:
        setup = self.setup.lower()
        self.assertIn("has not adopted overlays", setup)
        self.assertIn("not itself a fault", setup)
        self.assertIn("base-only or deferral decision is explicit", setup)


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
