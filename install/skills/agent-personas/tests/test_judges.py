"""AC-8 negative capability: a rendered judge can neither write, edit, run a shell nor dispatch."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import unittest

from support import Hermetic, load_module, tools

sp = load_module()
JUDGES = sorted(sp.JUDGING_PERSONA_NAMES)
WRITE_OR_DISPATCH = {"Write", "Edit", "NotebookEdit", "Agent", "SendMessage", "Monitor",
                     "EnterWorktree", "ExitWorktree", "TaskStop", "Bash"}


class RenderedJudgeTest(Hermetic):
    def test_rendered_judges_hold_no_write_shell_or_dispatch_tool(self) -> None:
        self.assertEqual(self.run_sync().returncode, 0)
        for name in JUDGES:
            claude, codex = self.rendered(name)
            with self.subTest(name=name):
                granted = tools(claude.get("tools"))
                self.assertTrue(granted, "a judge must render an allow-list")
                self.assertLessEqual(granted, {"Read", "Grep", "Glob", "TodoWrite"})
                self.assertFalse(granted & WRITE_OR_DISPATCH)
                self.assertLessEqual(WRITE_OR_DISPATCH, tools(claude.get("disallowedTools")))
                self.assertEqual(codex["sandbox_mode"], "read-only")
                self.assertEqual(codex["approval_policy"], "never")
                self.assertIs(codex["features"]["multi_agent"], False)

    def test_the_builder_is_not_restricted_as_a_judge(self) -> None:
        self.assertEqual(self.run_sync().returncode, 0)
        claude, codex = self.rendered("builder")
        self.assertNotIn("tools", claude)
        self.assertNotIn("sandbox_mode", codex)
        self.assertNotIn("features", codex)

    def test_restrictions_are_forced_not_copied_from_the_source(self) -> None:
        """Drop the sandbox line and scramble the allow-list spacing: the output must not change."""
        pool = self.copy_skill()
        path = pool / "reviewer.md"
        text = path.read_text(encoding="utf-8")
        text = text.replace("codex.sandbox: read-only\n", "")
        text = text.replace("claude.tools: Read, Grep, Glob, TodoWrite",
                            "claude.tools: Read ,\tGrep,Glob ,  TodoWrite")
        path.write_text(text, encoding="utf-8")
        self.assertEqual(self.run_sync().returncode, 0)
        claude, codex = self.rendered("reviewer")
        self.assertEqual(codex["sandbox_mode"], "read-only")
        self.assertEqual(claude["tools"], "Read, Grep, Glob, TodoWrite")

    @unittest.skipUnless(shutil.which("codex"), "codex CLI not installed")
    def test_codex_accepts_the_rendered_judge_role_files(self) -> None:
        """The installed Codex rejects unknown role-file fields; it must load ours cleanly."""
        self.assertEqual(self.run_sync().returncode, 0)
        doctor = subprocess.run(["codex", "doctor"], capture_output=True, text=True, timeout=120,
                                cwd=self.tmp, env={**os.environ, "HOME": str(self.home),
                                                   "CODEX_HOME": str(self.codex_home)})
        self.assertNotIn("malformed agent role", doctor.stdout + doctor.stderr)
        self.assertIn("CODEX_HOME", doctor.stdout)


class RejectedSourceTest(Hermetic):
    """A judging source that would widen a judge is a hard error, never silently fixed."""

    def assert_rejected(self, persona: str, old: str, new: str) -> None:
        pool = self.copy_skill()
        path = pool / f"{persona}.md"
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text)
        path.write_text(text.replace(old, new, 1), encoding="utf-8")
        for args in ((), ("--check",)):
            proc = self.run_sync(*args)
            self.assertEqual(proc.returncode, 2, f"{args}: {proc.stdout}{proc.stderr}")
        self.assertFalse(self.claude_agents.exists(), "a rejected run wrote agents")
        preview = self.run_sync("--scope", "global", "--preview", "--json")
        self.assertEqual(preview.returncode, 2)
        plan = json.loads(preview.stdout)
        self.assertEqual(plan["operations"], [])
        self.assertTrue(any(f["severity"] == "error" for f in plan["findings"]))

    def test_judge_declaring_writes_yes(self) -> None:
        self.assert_rejected("reviewer", "writes: no", "writes: yes")

    def test_judge_holding_bash(self) -> None:
        self.assert_rejected("security-reviewer", "claude.tools: Read,",
                             "claude.tools: Bash, Read,")

    def test_judge_holding_an_unknown_tool(self) -> None:
        self.assert_rejected("advisor", "claude.tools: Read,", "claude.tools: Skill, Read,")

    def test_judge_holding_a_write_tool(self) -> None:
        self.assert_rejected("reviewer", "claude.tools: Read,", "claude.tools: Edit, Read,")

    def test_judge_without_an_allow_list(self) -> None:
        self.assert_rejected("reviewer", "claude.tools: Read, Grep, Glob, TodoWrite\n", "")

    def test_judge_with_a_writable_codex_sandbox(self) -> None:
        self.assert_rejected("advisor", "codex.sandbox: read-only",
                             "codex.sandbox: workspace-write")

    def test_writer_claiming_not_to_write(self) -> None:
        self.assert_rejected("builder", "writes: yes", "writes: no")

    def test_unknown_frontmatter_key(self) -> None:
        self.assert_rejected("reviewer", "writes: no", "writes: no\nclaude.allowedTools: Write")

    def test_retired_writes_vocabulary(self) -> None:
        self.assert_rejected("builder", "writes: yes", "writes: product specs only")


if __name__ == "__main__":
    unittest.main()
