#!/usr/bin/env python3
"""Tests for the product-definition half of push_guard.py — the pre-push wiring and the seal gate.

Run: python3 -m unittest tests.test_push_guard_product   (from the skill root)
  or python3 -m unittest discover -s tests -t tests

THE ADOPTION GUARD IS THE FIRST THING TESTED AND IT IS TESTED HARDEST. Most repositories on a
machine have no `docs/product/`, so if this half is ever anything other than completely silent
there, the whole guard — credential scan included — gets uninstalled, and then it protects nothing
anywhere. `SilenceTest` asserts empty stdout AND empty stderr AND exit 0, not merely that the push
was allowed: a warning line is a failure of this property just as much as a block is.

Everything else is asserted in BOTH directions. A gate that blocks unconditionally passes every
block-side assertion while making the tool unusable; a gate that never blocks passes every pass-side
assertion while gating nothing. Each pair below is one test that must block and one that must not.

HERMETICITY. `HOME` and `XDG_STATE_HOME` are pinned in every subprocess environment. The guard
itself never reads `Path.home()`, but it spawns milestone_seal.py, whose receipt directory falls
back to it — so an unpinned run could be satisfied, or refused, by a receipt on the developer's own
machine, which is precisely the class of escape `hermetic.py` exists to stop.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
GUARD = SCRIPTS / "push_guard.py"
SKILLS = SCRIPTS.parents[1]
METHODOLOGY = SKILLS / "execution-methodology" / "scripts"
ZERO = "0" * 40

TODAY = time.strftime("%Y-%m-%d")

PRD = f"""---
title: Ledger
status: draft
updated: {TODAY}
---

# Ledger

<!-- features: docs/product/specs/F-*.md -->

F-007 covers the export.
"""

SPEC = f"""---
id: F-007
title: Export
prd: docs/product/prd.md
status: approved
updated: {TODAY}
edge_cases: [empty]
---

# F-007 — Export

## Acceptance criteria

**AC-1** When an operator requests an export, given the ledger has entries, the response is a CSV
file naming every entry.
"""

MILESTONE = f"""---
milestone: M1
title: Launch
status: {{status}}
updated: {TODAY}
---

# M1 — Launch

## Why now
The export is useless until the ledger records entries.

## Cross-feature validation
The journeys no single feature's suite can prove.
{{gate}}
"""


@unittest.skipUnless(METHODOLOGY.is_dir(), "the execution-methodology skill is not vendored here")
class GuardFixture(unittest.TestCase):
    """A real repository, driven through the guard exactly as git drives it."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.state = self.tmp / "state"
        self.root = self.tmp / "repo"
        self.root.mkdir()
        self.git("init", "-q", "-b", "feature")
        self.git("config", "user.email", "guard@example.invalid")
        self.git("config", "user.name", "guard")
        self.write("README.md", "# ledger\n")
        self.commit("init")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def git(self, *args: str) -> str:
        return subprocess.run(["git", "-C", str(self.root), *args], capture_output=True, text=True,
                              check=True).stdout

    def write(self, relative: str, text: str, *, executable: bool = False) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        if executable:
            path.chmod(0o755)
        return path

    def commit(self, message: str = "c") -> str:
        self.git("add", ".")
        self.git("commit", "-qm", message)
        return self.git("rev-parse", "HEAD").strip()

    def adopt(self) -> None:
        """A minimal repository that has opted in AND is clean, so a finding is never ambient."""
        self.write("docs/product/prd.md", PRD)
        self.write("docs/product/specs/F-007-export.md", SPEC)
        self.commit("adopt the product-definition standard")

    def env(self, **extra: str) -> dict:
        """The child environment, with every variable this half reads pinned to the fixture.

        `HOME` IS SPELLED OUT AGAIN AT EVERY CALL SITE BELOW, as a literal key in a dict display,
        and that is not redundancy to be tidied away. `hermetic.py` decides statically whether a
        subprocess pins `HOME`, and it accepts three spellings — a dict display with a `"HOME"` key,
        `dict(os.environ, HOME=...)`, and a name bound to either. A helper call is none of them, so
        a test that pinned HOME only in here would be flagged as reaching the machine, and the
        honest way to clear that is to pin it where the analyser looks rather than to declare the
        test an exception. See the barrier's own note: an analyser that guessed in the reassuring
        direction is how a barrier stops being one.
        """
        return {**os.environ, "XDG_STATE_HOME": str(self.state),
                "PYTHONDONTWRITEBYTECODE": "1", "PD_ALLOW_MAIN_PUSH": "", "PD_SKIP_SPEC_CHECK": "",
                "PD_ALLOW_UNSEALED_MILESTONE": "", **extra}

    def push(self, base: str | None = None, guard: Path = GUARD,
             **extra: str) -> subprocess.CompletedProcess:
        """Drive the guard with git's real argv and a real pre-push payload."""
        head = self.git("rev-parse", "HEAD").strip()
        payload = f"refs/heads/feature {head} refs/heads/feature {base or ZERO}\n"
        environment = {**self.env(**extra), "HOME": str(self.tmp / "home")}
        return subprocess.run([sys.executable, str(guard), "origin", "git@example.invalid:x.git"],
                              cwd=str(self.root), input=payload, capture_output=True, text=True,
                              env=environment)


class SilenceTest(GuardFixture):
    """A repository that never adopted the standard must not be able to tell this half exists."""

    def test_a_repository_with_no_docs_product_is_untouched(self) -> None:
        result = self.push()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout, "", "the guard spoke in a repository that never opted in")
        self.assertEqual(result.stderr, "")

    def test_product_shaped_documents_outside_docs_product_are_not_adoption(self) -> None:
        """The probe is the directory, not a document that happens to look like a spec. A repository
        with `product/specs/F-1.md` at its root has not opted into anything."""
        self.write("product/specs/F-007-export.md", SPEC.replace(f"updated: {TODAY}", "updated: x"))
        self.write("notes/prd.md", "## Changelog\n\n- it used to say something else\n")
        self.commit("documents that are not an adoption")
        result = self.push()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout, "")

    def test_an_empty_docs_product_directory_is_adoption_and_still_passes(self) -> None:
        """The pass-side twin: opting in is not itself a finding. `docs/product/` with nothing in it
        yet is a repository at the start of adoption, and it must push cleanly."""
        (self.root / "docs" / "product").mkdir(parents=True)
        self.write("docs/product/.keep", "")
        self.commit("start adopting")
        result = self.push()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout, "")


class SpecCheckWiringTest(GuardFixture):
    """The current-state lint, at the boundary. Blocks, and does not block."""

    def test_an_adopted_repository_in_current_state_form_pushes_clean(self) -> None:
        self.adopt()
        result = self.push()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout, "")

    def test_a_document_that_describes_its_own_past_blocks_the_push(self) -> None:
        self.adopt()
        self.write("docs/product/specs/F-007-export.md",
                   SPEC + "\n## Changelog\n\n- the export used to be XML\n")
        self.commit("append history instead of updating")
        result = self.push()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("pre-push BLOCKED", result.stdout)
        self.assertIn("A2", result.stdout)
        self.assertIn("docs/product/specs/F-007-export.md", result.stdout)

    def test_a_plan_whose_edges_do_not_schedule_blocks_the_push(self) -> None:
        """The second checker is wired too, and it is wired separately: a `needs:` edge naming a
        task nobody declares is invisible to the lint above."""
        self.adopt()
        self.write("docs/product/plans/F-007-export.md",
                   "# F-007 plan\n\n```task\ntask: T1\ntitle: write the exporter\n"
                   "lane: light\nneeds: [T9]\nwrites: [src/export.py]\ncovers: [AC-1]\n```\n")
        self.commit("a plan with a dangling edge")
        result = self.push()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("W1", result.stdout)

    def test_the_findings_are_capped_so_the_hook_stays_readable(self) -> None:
        self.adopt()
        for index in range(1, 30):
            self.write(f"docs/product/specs/F-{index:03d}-x.md",
                       SPEC.replace("F-007", f"F-{index:03d}") + "\n## Changelog\n\n- old\n")
        self.commit("a corpus of findings")
        result = self.push()
        self.assertEqual(result.returncode, 1)
        self.assertIn("more", result.stdout)
        self.assertIn("Full report: spec_check.py", result.stdout)


class EscapeHatchTest(GuardFixture):
    """The escape exists, it is loud, and it fails closed on anything that is not a yes."""

    def broken(self) -> None:
        self.adopt()
        self.write("docs/product/specs/F-007-export.md",
                   SPEC + "\n## Changelog\n\n- the export used to be XML\n")
        self.commit("append history instead of updating")

    def test_the_escape_allows_the_push_and_says_so(self) -> None:
        self.broken()
        result = self.push(PD_SKIP_SPEC_CHECK="1")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("pre-push SKIPPED", result.stdout)
        self.assertIn("did NOT run", result.stdout)

    def test_a_negative_spelling_leaves_the_check_on(self) -> None:
        """`=0` is a founder being explicit that they do NOT want the escape. Honouring presence
        rather than value would hand them the bypass they were refusing."""
        self.broken()
        for value in ("0", "false", "no", "off", "maybe", " "):
            with self.subTest(value=value):
                result = self.push(PD_SKIP_SPEC_CHECK=value)
                self.assertEqual(result.returncode, 1, f"{value!r} opened the hatch")

    def test_the_escape_is_not_printed_when_it_was_not_used(self) -> None:
        self.adopt()
        self.assertNotIn("SKIPPED", self.push().stdout)


class SealGateTest(GuardFixture):
    """`-> shipped` is the only transition gated, and it is gated on evidence, not on a promise."""

    SEAL = METHODOLOGY / "milestone_seal.py"

    def milestone(self, status: str = "building", gate: str = "Gate: sh gate.sh") -> str:
        self.write("docs/product/milestones/M1-launch.md",
                   MILESTONE.format(status=status, gate=gate))
        self.write("gate.sh", "#!/bin/sh\nexit ${E2E_RC:-0}\n", executable=True)
        return self.commit(f"milestone at {status}")

    def record(self, **extra: str) -> subprocess.CompletedProcess:
        environment = {**self.env(**extra), "HOME": str(self.tmp / "home")}
        return subprocess.run([sys.executable, str(self.SEAL), "--root", str(self.root),
                               "--record", "M1"], capture_output=True, text=True, env=environment)

    def seal(self, gate: str = "Gate: sh gate.sh") -> str:
        self.write("docs/product/milestones/M1-launch.md",
                   MILESTONE.format(status="shipped", gate=gate))
        return self.commit("seal M1")

    def test_a_seal_without_evidence_is_blocked(self) -> None:
        self.adopt()
        base = self.milestone()
        self.seal()
        result = self.push(base)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("without evidence", result.stdout)
        self.assertIn("sh gate.sh", result.stdout)
        self.assertIn("--record M1", result.stdout)

    def test_a_seal_with_evidence_is_allowed(self) -> None:
        self.adopt()
        base = self.milestone()
        self.seal()
        self.assertEqual(self.record().returncode, 0)
        result = self.push(base)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout, "")

    def test_evidence_recorded_against_a_different_tree_does_not_seal(self) -> None:
        """The receipt is named by tree sha for exactly this: recorded, then the content moves, and
        the evidence stops applying without anyone having to remember to delete it."""
        self.adopt()
        base = self.milestone()
        self.seal()
        self.assertEqual(self.record().returncode, 0)
        self.write("README.md", "# ledger\n\nA later edit.\n")
        self.commit("edit after recording")
        result = self.push(base)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("without evidence", result.stdout)

    def test_a_failing_gate_produces_no_evidence_and_the_seal_stays_blocked(self) -> None:
        self.adopt()
        base = self.milestone()
        self.seal()
        failed = self.record(E2E_RC="7")
        self.assertEqual(failed.returncode, 1, failed.stdout + failed.stderr)
        self.assertEqual(self.push(base).returncode, 1)

    def test_a_milestone_that_is_not_being_sealed_is_not_checked(self) -> None:
        """The cost control. A push that merely edits a building milestone — or touches an already
        shipped one — must not re-run the end-to-end gate, or the founder learns --no-verify."""
        self.adopt()
        base = self.milestone()
        self.write("docs/product/milestones/M1-launch.md",
                   MILESTONE.format(status="building", gate="Gate: sh gate.sh")
                   .replace("useless until", "of no use until"))
        self.commit("edit a milestone that is not being sealed")
        result = self.push(base)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout, "")

    def test_an_already_shipped_milestone_is_not_re_gated(self) -> None:
        self.adopt()
        self.milestone()
        self.seal()
        self.assertEqual(self.record().returncode, 0)
        base = self.git("rev-parse", "HEAD").strip()
        self.write("docs/product/milestones/M1-launch.md",
                   MILESTONE.format(status="shipped", gate="Gate: sh gate.sh")
                   .replace("useless until", "of no use until"))
        self.write("README.md", "# ledger\n\nlater\n")
        self.commit("a later push on the same branch")
        result = self.push(base)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout, "")

    def test_sealing_a_milestone_that_declares_no_gate_is_blocked(self) -> None:
        """A seal with nothing to validate against is a claim with no content. Blocked, and the
        message names the section to write rather than a command to run."""
        self.adopt()
        base = self.milestone(gate="Still being decided.")
        self.seal(gate="Still being decided.")
        result = self.push(base)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("declares no cross-feature gate", result.stdout)

    def test_a_milestone_added_already_shipped_is_a_seal(self) -> None:
        """There is no previous status to compare against, and treating that as "no transition"
        would let any seal through by writing the document and the status in one commit."""
        self.adopt()
        base = self.git("rev-parse", "HEAD").strip()
        self.seal()
        result = self.push(base)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("without evidence", result.stdout)

    def test_the_seal_escape_allows_the_push_and_says_so(self) -> None:
        self.adopt()
        base = self.milestone()
        self.seal()
        result = self.push(base, PD_ALLOW_UNSEALED_MILESTONE="1")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("pre-push SKIPPED", result.stdout)
        self.assertIn("NOT verified", result.stdout)

    def test_the_seal_escape_fails_closed_on_a_negative_spelling(self) -> None:
        self.adopt()
        base = self.milestone()
        self.seal()
        self.assertEqual(self.push(base, PD_ALLOW_UNSEALED_MILESTONE="0").returncode, 1)

    def test_the_spec_escape_does_not_open_the_seal(self) -> None:
        """Two hatches, not one. A blanket skip would silently disable the seal gate for a founder
        who only meant to push past a lint finding."""
        self.adopt()
        base = self.milestone()
        self.seal()
        self.assertEqual(self.push(base, PD_SKIP_SPEC_CHECK="1").returncode, 1)


class MissingCheckerTest(GuardFixture):
    """`docs/product/` present and the checker absent is a check that did not run — never a pass.

    The asymmetry against `SilenceTest` is the design: absent `docs/product/` means the repository
    never agreed to the rule, so there is nothing to check and nothing to say. Absent CHECKER means
    it did agree and the answer is unknown, and unknown must not read as clean.
    """

    def replica(self, *, methodology: bool) -> Path:
        """A skills tree holding the guard, so `METHODOLOGY_SCRIPTS` resolves inside it."""
        skills = self.tmp / "skills"
        scripts = skills / "progressive-disclosure" / "scripts"
        scripts.mkdir(parents=True)
        for name in ("push_guard.py", "validate_disclosure.py"):
            shutil.copy2(SCRIPTS / name, scripts / name)
        if methodology:
            shutil.copytree(METHODOLOGY, skills / "execution-methodology" / "scripts")
        return scripts / "push_guard.py"

    def test_an_adopted_repository_with_no_checker_installed_is_exit_2(self) -> None:
        self.adopt()
        result = self.push(guard=self.replica(methodology=False))
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("not a clean result", result.stderr)
        self.assertIn("spec_check.py", result.stderr)

    def test_the_same_replica_with_the_checker_present_passes(self) -> None:
        """The other direction, and it is what proves the test above found the missing checker
        rather than the replica itself being broken."""
        self.adopt()
        result = self.push(guard=self.replica(methodology=True))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout, "")

    def test_an_unadopted_repository_with_no_checker_is_still_silent(self) -> None:
        """The absent checker must not wake the guard up in a repository that never opted in."""
        result = self.push(guard=self.replica(methodology=False))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout, "")


@unittest.skipUnless((METHODOLOGY / "milestone_seal.py").is_file(), "milestone_seal.py absent")
class OneGateReaderTest(unittest.TestCase):
    """Two files read the `Gate:` line, and they may not drift apart in silence.

    A shared import is rejected in push_guard.py's own comments — the guard does not put another
    skill's import graph inside the process that runs the credential scan — so the second copy is
    deliberate, and this is the assertion that pays for it.
    """

    CASES = (
        "## Cross-feature validation\nGate: a\n",
        "## Cross-feature validation\nprose\nGate: a\nmore\nGate: b\n",
        "## Notes\nGate: a\n",
        "## Cross-feature validation\nnothing declared\n",
        "## Cross-feature validation\nGate: a\n## Later\nGate: b\n",
        "## cross-feature validation\nGate: a b && c\n",
        "## Cross-feature validation\nGate:\n",
        "",
    )

    def test_the_two_gate_readers_agree(self) -> None:
        sys.path.insert(0, str(SCRIPTS))
        sys.path.insert(0, str(METHODOLOGY))
        import milestone_seal
        import push_guard
        for text in self.CASES:
            with self.subTest(text=text):
                self.assertEqual(push_guard.gate_command(text), milestone_seal.gate_command(text))


if __name__ == "__main__":
    unittest.main()
