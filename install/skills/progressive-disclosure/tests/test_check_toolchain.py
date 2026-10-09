"""check_toolchain.py: persona renderer parity and the shared instruction block.

Every run is a subprocess with `HOME` pinned to a temporary directory, so no test reads the real
`~/.claude` or `~/.codex`.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
CHECKER = SKILL / "scripts" / "check_toolchain.py"
RUNBOOK = SKILL.parents[2] / "docs" / "runbooks" / "global-instructions.md"

BLOCK = ("# GitHub\n\nPrivate repos only.\n\n# Execution and maintenance route\n\nRules.\n\n"
         "User authority, privacy, local verification and deployment boundaries remain in force "
         "throughout.\n")


class ToolchainCase(unittest.TestCase):
    def setUp(self) -> None:
        self.home = Path(tempfile.mkdtemp(prefix="toolchain-home-"))
        self.addCleanup(shutil.rmtree, self.home, ignore_errors=True)
        self.claude_md = self.home / ".claude" / "CLAUDE.md"
        self.codex_md = self.home / ".codex" / "AGENTS.md"
        self.write(self.claude_md, "# Operating model\n\nI do things.\n\n" + BLOCK)
        self.write(self.codex_md, "# Operating model\n\nIt does things.\n\n" + BLOCK)
        self.sync(0)

    def write(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def sync(self, code: int, stdout: str = "") -> None:
        self.write(self.home / ".claude" / "skills" / "agent-personas" / "scripts" /
                   "sync_personas.py",
                   f"import sys\nassert sys.argv[1:] == ['--check']\n"
                   f"print({stdout!r})\nsys.exit({code})\n")

    def run_checker(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = {**os.environ, "HOME": str(self.home), "PYTHONDONTWRITEBYTECODE": "1"}
        return subprocess.run([sys.executable, str(CHECKER), *args], env=env,
                              capture_output=True, text=True, timeout=60)


class VerdictTest(ToolchainCase):
    def test_clean_machine_exits_zero_and_names_both_checks(self):
        r = self.run_checker()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("clean — personas in sync; instructions mirrored", r.stdout)

    def test_hook_mode_is_silent_when_clean(self):
        r = self.run_checker("--hook")
        self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_a_differing_route_block_is_critical(self):
        self.write(self.codex_md, BLOCK.replace("Rules.", "Other rules."))
        r = self.run_checker()
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("CRITICAL", r.stdout)
        self.assertIn("# Execution and maintenance route", r.stdout)

    def test_a_differing_github_block_is_critical(self):
        self.write(self.codex_md, BLOCK.replace("Private repos only.", "Public is fine."))
        r = self.run_checker("--hook")
        self.assertEqual(r.returncode, 1)
        self.assertIn("[critical] section `# GitHub` differs", r.stdout)
        self.assertIn("NOT A CLEAN RESULT", r.stdout)

    def test_voice_outside_the_blocks_may_differ(self):
        self.write(self.codex_md, "# Operating model\n\nEntirely different.\n\n" + BLOCK)
        self.assertEqual(self.run_checker().returncode, 0)

    def test_stale_generated_agents_are_critical(self):
        self.sync(1, "/x/.claude/agents/reviewer.md STALE")
        r = self.run_checker()
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("1 generated agent file(s) do not match", r.stdout)


class NotRunTest(ToolchainCase):
    def assert_not_run(self, r: subprocess.CompletedProcess[str], check: str) -> None:
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertNotIn("clean —", r.stdout)
        self.assertIn(f"NOT RUN: {check}", r.stdout)

    def test_missing_sync_tool_is_not_run_not_clean(self):
        (self.home / ".claude" / "skills" / "agent-personas" / "scripts" /
         "sync_personas.py").unlink()
        self.assert_not_run(self.run_checker(), "personas")

    def test_sync_tool_without_a_verdict_is_not_run(self):
        self.sync(3)
        self.assert_not_run(self.run_checker(), "personas")

    def test_missing_codex_file_is_not_run(self):
        self.codex_md.unlink()
        self.assert_not_run(self.run_checker(), "instruction mirror")

    def test_a_block_missing_from_one_side_is_not_compared(self):
        self.write(self.codex_md, "# Operating model\n")
        r = self.run_checker()
        self.assert_not_run(r, "instruction mirror")
        self.assertIn("missing from ~/.codex/AGENTS.md", r.stdout)

    def test_an_undecodable_file_is_not_run_without_a_traceback(self):
        self.codex_md.write_bytes(b"\xff\xfe\x00bad")
        r = self.run_checker()
        self.assert_not_run(r, "instruction mirror")
        self.assertNotIn("Traceback", r.stderr)

    def test_not_run_outranks_a_critical(self):
        self.sync(1, "/x STALE")
        self.codex_md.unlink()
        self.assertEqual(self.run_checker().returncode, 2)


class JsonTest(ToolchainCase):
    def test_json_is_one_object_carrying_status_and_exit(self):
        self.sync(3)
        r = self.run_checker("--json")
        payload = json.loads(r.stdout)
        self.assertEqual((payload["status"], payload["exit"], r.returncode), ("not-run", 2, 2))
        self.assertEqual(payload["evaluated"], ["instruction mirror"])
        self.assertEqual([n["check"] for n in payload["not_evaluated"]], ["personas"])


class RunbookAgreementTest(unittest.TestCase):
    def test_the_runbooks_replacement_section_carries_the_markers_the_checker_finds(self):
        sys.path.insert(0, str(CHECKER.parent))
        import check_toolchain
        text = RUNBOOK.read_text(encoding="utf-8")
        block = re.search(r"```markdown\n(.*?)```", text, re.DOTALL)
        self.assertIsNotNone(block, "the runbook lost its replacement section")
        self.assertTrue(block.group(1).startswith(check_toolchain.ROUTE_HEADING))
        self.assertIn(check_toolchain.ROUTE_END, block.group(1))


if __name__ == "__main__":
    unittest.main()
