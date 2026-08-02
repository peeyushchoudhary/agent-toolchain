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


WRITE_TOOLS = ("Write", "Edit", "NotebookEdit")
# Every `claude.*` key sync_personas.py renders. Anything else in that namespace is dropped
# silently, so a misspelt or invented restriction key (`claude.allowedTools`) reads like a tool
# policy in the source and reaches the harness as nothing at all.
KNOWN_CLAUDE_KEYS = frozenset(
    {"claude.model", "claude.effort", "claude.tools", "claude.disallowedTools"}
)


def frontmatter(source: Path) -> dict[str, str]:
    """Parse a persona's frontmatter into keys.

    Deliberately a second implementation rather than an import of sync_personas.parse: these tests
    are the only independent check on the renderer, and a test that borrows the parser it is
    checking inherits its blind spots.
    """
    text = source.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise AssertionError(f"{source.name}: no frontmatter")
    fm, sep, _ = text[4:].partition("\n---")
    if not sep:
        raise AssertionError(f"{source.name}: unterminated frontmatter")
    meta: dict[str, str] = {}
    for line in fm.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip()
    return meta


def tool_set(value: str | None) -> set[str]:
    return {t.strip() for t in (value or "").split(",") if t.strip()}


def granted_write_tools(meta: dict[str, str]) -> set[str]:
    """The write tools this persona's frontmatter leaves available to it.

    Two mechanisms, and both have to be read: `claude.disallowedTools` denies by name, and
    `claude.tools` — when present — is an allow-list. When neither restricts a tool, the harness
    grants it. Absence of a restriction IS a grant, which is why this cannot be done by looking for
    the presence of a string.
    """
    denied = tool_set(meta.get("claude.disallowedTools"))
    allowed = meta.get("claude.tools")
    return {
        tool
        for tool in WRITE_TOOLS
        if tool not in denied and (allowed is None or tool in tool_set(allowed))
    }


def pool_personas() -> list[Path]:
    pool = SCRIPT.parent.parent / "personas"
    return [p for p in sorted(pool.glob("*.md")) if p.name.lower() != "readme.md"]


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
        # Reads the parsed frontmatter, not the file text. Grepping the whole file let a persona
        # that quotes its own restriction in its prose body pass with nothing denied in the
        # frontmatter at all — the restriction has to be where the harness reads it.
        examined = []
        for source in pool_personas():
            meta = frontmatter(source)
            if meta.get("writes") != "no":
                continue
            examined.append(source.stem)
            denied = tool_set(meta.get("claude.disallowedTools"))
            with self.subTest(persona=source.stem):
                self.assertEqual(
                    set(WRITE_TOOLS) - denied,
                    set(),
                    "non-writing persona must deny every write tool by name",
                )
                if source.stem in self.BASH_EXEMPT:
                    self.assertNotIn(
                        "Bash", denied, "the sanctioned exception is that Bash IS available"
                    )
                    continue
                self.assertIn("Bash", denied, "non-writing persona must disallow Bash")
        self.assertTrue(examined, "no non-writing persona was examined — the filter matched none")

    def test_every_persona_granting_a_write_tool_declares_that_it_writes(self) -> None:
        """A persona whose frontmatter GRANTS a write tool must say `writes:` other than `no`.

        The genuine inverse of the check above: that one examines personas declaring `writes: no`,
        this one examines the complement — every persona the harness will actually let edit. The
        version this replaced applied the *same* `writes: no` filter as its sibling, so it never
        looked at a writing persona at all, and then asserted that the strings `Write` and `Edit`
        appeared somewhere in the frontmatter — satisfied identically by a line denying those tools
        and by a line granting them. A judging persona with `writes: no` and a granted write tool
        passed it.

        Grants are read from the key, not from the presence of a tool name, because the two keys
        carry opposite meanings and a missing key is itself a grant.
        """
        writers = []
        for source in pool_personas():
            meta = frontmatter(source)
            # Its own subTest: an unrenderable key must not mask the grant check below, since the
            # two describe different ways the same persona can end up able to edit.
            with self.subTest(persona=source.stem, check="renderable-keys"):
                self.assertEqual(
                    sorted(
                        k for k in meta
                        if k.startswith("claude.") and k not in KNOWN_CLAUDE_KEYS
                    ),
                    [],
                    "unrenderable claude.* key: sync_personas.py drops it, so a tool policy "
                    "written here would never reach the harness",
                )
            with self.subTest(persona=source.stem, check="write-grant"):
                granted = granted_write_tools(meta)
                if not granted:
                    continue
                writers.append(source.stem)
                self.assertNotEqual(
                    meta.get("writes"),
                    "no",
                    f"declares `writes: no` yet is granted {sorted(granted)} — D8 breached: a "
                    f"judging persona that can edit what it judges",
                )
                self.assertTrue(
                    meta.get("writes"), "a persona granted a write tool must declare `writes:`"
                )
        self.assertTrue(
            writers,
            "no persona in the pool grants a write tool — the population this test exists to "
            "police is empty, which means it proved nothing",
        )


if __name__ == "__main__":
    unittest.main()
