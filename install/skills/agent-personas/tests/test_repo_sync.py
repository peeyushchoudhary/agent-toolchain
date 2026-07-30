from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "sync_personas.py"
BASE_NAMES = {
    "acceptance",
    "architect",
    "chief-of-staff",
    "contract-architect",
    "developer",
    "docs-steward",
    "planner",
    "product-steward",
    "reviewer",
    "scout",
    "security-validator",
    "senior-developer",
    "test-judge",
}
PERSONA = """---
name: domain-validator
description: Use for domain validation.
writes: no
claude.model: opus
claude.effort: high
claude.disallowedTools: Write, Edit, NotebookEdit, Bash
codex.model: gpt-5.6-sol
codex.effort: high
codex.sandbox: read-only
---
Validate the domain.
"""


class RepoSyncTest(unittest.TestCase):
    def run_sync(self, home: Path, repo: Path, *extra: str) -> subprocess.CompletedProcess:
        env = {**os.environ, "HOME": str(home)}
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--repo", str(repo), *extra],
            capture_output=True,
            text=True,
            env=env,
        )

    def make_repo(self, root: Path) -> Path:
        repo = root / "project"
        sources = repo / "docs" / "agents" / "personas"
        sources.mkdir(parents=True)
        (sources / "domain-validator.md").write_text(PERSONA, encoding="utf-8")
        return repo

    def test_repo_check_ignores_stale_global_generated_agents(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            (home / ".codex").mkdir(parents=True)
            repo = self.make_repo(root)
            generated = self.run_sync(home, repo)
            self.assertEqual(generated.returncode, 0, generated.stdout + generated.stderr)
            global_agent = home / ".claude" / "agents" / "reviewer.md"
            global_agent.write_text("stale\n", encoding="utf-8")

            checked = self.run_sync(home, repo, "--check")

            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
            self.assertIn("1 project persona source", checked.stdout)

    def test_repo_check_detects_both_harness_outputs_after_last_source_deleted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            repo = self.make_repo(root)
            generated = self.run_sync(home, repo)
            self.assertEqual(generated.returncode, 0, generated.stdout + generated.stderr)
            (repo / "docs" / "agents" / "personas" / "domain-validator.md").unlink()

            checked = self.run_sync(home, repo, "--check")

            self.assertEqual(checked.returncode, 1)
            self.assertIn(".claude/agents/domain-validator.md", checked.stdout)
            self.assertIn(".codex/agents/domain-validator.toml", checked.stdout)

    def test_repo_codex_artifact_is_rendered_without_global_codex_install(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            home.mkdir()
            repo = self.make_repo(root)

            generated = self.run_sync(home, repo)

            self.assertEqual(generated.returncode, 0, generated.stdout + generated.stderr)
            self.assertTrue((repo / ".claude" / "agents" / "domain-validator.md").is_file())
            self.assertTrue((repo / ".codex" / "agents" / "domain-validator.toml").is_file())
            self.assertFalse((home / ".codex").exists())

    def test_repo_personas_readme_is_not_parsed_as_a_persona(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            home.mkdir()
            repo = root / "project"
            sources = repo / "docs" / "agents" / "personas"
            sources.mkdir(parents=True)
            (sources / "README.md").write_text(
                "# Persona source notes\n",
                encoding="utf-8",
            )

            checked = self.run_sync(home, repo, "--check")

            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
            self.assertIn("0 project persona sources", checked.stdout)

    def test_repo_persona_filename_must_match_its_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            home.mkdir()
            repo = root / "project"
            sources = repo / "docs" / "agents" / "personas"
            sources.mkdir(parents=True)
            (sources / "custom-review.md").write_text(PERSONA, encoding="utf-8")

            generated = self.run_sync(home, repo)

            self.assertEqual(generated.returncode, 2)
            self.assertIn("filename must match", generated.stderr)

    def test_global_pool_rejects_an_extra_project_persona(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            home.mkdir()
            scripts = root / "skill" / "scripts"
            pool = root / "skill" / "personas"
            scripts.mkdir(parents=True)
            pool.mkdir()
            copied_script = scripts / "sync_personas.py"
            copied_script.write_text(SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")
            for name in BASE_NAMES | {"video-outcome-validator"}:
                (pool / f"{name}.md").write_text(
                    PERSONA.replace("domain-validator", name),
                    encoding="utf-8",
                )

            generated = subprocess.run(
                [sys.executable, str(copied_script)],
                capture_output=True,
                text=True,
                env={**os.environ, "HOME": str(home)},
            )

            self.assertEqual(generated.returncode, 2)
            self.assertIn("unexpected: video-outcome-validator", generated.stderr)

    def test_global_pool_list_ignores_a_readme(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            home.mkdir()
            scripts = root / "skill" / "scripts"
            pool = root / "skill" / "personas"
            scripts.mkdir(parents=True)
            pool.mkdir()
            copied_script = scripts / "sync_personas.py"
            copied_script.write_text(SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")
            for name in BASE_NAMES:
                (pool / f"{name}.md").write_text(
                    PERSONA.replace("domain-validator", name),
                    encoding="utf-8",
                )
            (pool / "README.md").write_text("# Source notes\n", encoding="utf-8")

            listed = subprocess.run(
                [sys.executable, str(copied_script), "--list"],
                capture_output=True,
                text=True,
                env={**os.environ, "HOME": str(home)},
            )

            self.assertEqual(listed.returncode, 0, listed.stdout + listed.stderr)
            self.assertIn("acceptance", listed.stdout)

    def test_repo_check_rejects_unsourced_hand_written_agents(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            home.mkdir()
            repo = root / "project"
            claude_agent = repo / ".claude" / "agents" / "custom.md"
            codex_agent = repo / ".codex" / "agents" / "custom.toml"
            claude_agent.parent.mkdir(parents=True)
            codex_agent.parent.mkdir(parents=True)
            claude_agent.write_text("# Custom agent\n", encoding="utf-8")
            codex_agent.write_text('name = "custom"\n', encoding="utf-8")

            checked = self.run_sync(home, repo, "--check")

            self.assertEqual(checked.returncode, 1)
            self.assertIn("custom.md (unmanaged", checked.stdout)
            self.assertIn("custom.toml (unmanaged", checked.stdout)

    # `test-judge` is the single sanctioned exception. Its whole job is running a gate, which
    # requires a shell — without one it was assigned work it could not perform and chained to a
    # sub-subagent rather than say so. It keeps Write/Edit/NotebookEdit disallowed, so it still
    # cannot author a fix; the residual risk is edits through shell redirection, which its body
    # forbids explicitly. Named here rather than inferred, so adding a second exception is a
    # deliberate act with a test to change.
    BASH_EXEMPT = {"test-judge"}

    def test_non_writing_base_personas_disallow_bash(self) -> None:
        pool = SCRIPT.parent.parent / "personas"
        for source in sorted(pool.glob("*.md")):
            text = source.read_text(encoding="utf-8")
            if "\nwrites: no\n" not in text:
                continue
            with self.subTest(persona=source.stem):
                if source.stem in self.BASH_EXEMPT:
                    self.assertIn(
                        "claude.disallowedTools: Write, Edit, NotebookEdit\n", text
                    )
                    self.assertNotIn("Bash", text.split("---")[1])
                    continue
                self.assertIn(
                    "claude.disallowedTools: Write, Edit, NotebookEdit, Bash",
                    text,
                )

    def test_no_persona_may_write_without_declaring_it(self) -> None:
        """A persona that can Write must say `writes:` something other than `no`.

        The inverse of the check above. Granting a judging persona a write tool would silently
        dissolve the one guarantee the pool enforces structurally rather than by instruction, and
        it would do so without any other test noticing.
        """
        pool = SCRIPT.parent.parent / "personas"
        for source in sorted(pool.glob("*.md")):
            text = source.read_text(encoding="utf-8")
            if "\nwrites: no\n" not in text:
                continue
            front = text.split("---")[1]
            with self.subTest(persona=source.stem):
                self.assertIn("Write", front, "non-writing persona must disallow Write")
                self.assertIn("Edit", front, "non-writing persona must disallow Edit")


if __name__ == "__main__":
    unittest.main()
