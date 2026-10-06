"""AC-11: both harnesses render equivalent agents from one source, and the CLI contract holds."""

from __future__ import annotations

import json
import unittest

from support import Hermetic, load_module

sp = load_module()
SPAWNABLE = sorted(n for n in sp.BASE_PERSONA_NAMES if n != "chief")

PROJECT_PERSONA = """---
name: domain-validator
description: Use for domain validation.
writes: no
claude.model: opus
claude.effort: high
claude.disallowedTools: Write, Edit, NotebookEdit, Bash
codex.model: gpt-6.1-sol
codex.effort: high
codex.sandbox: read-only
---
Validate the domain.
"""


class RenderTest(Hermetic):
    def test_both_harnesses_render_the_spawnable_four_with_matching_routing(self) -> None:
        proc = self.run_sync()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(sorted(p.stem for p in self.claude_agents.glob("*.md")), SPAWNABLE)
        self.assertEqual(sorted(p.stem for p in self.codex_agents.glob("*.toml")), SPAWNABLE)
        for name in SPAWNABLE:
            meta, body = sp.load(name)
            claude, codex = self.rendered(name)
            with self.subTest(name=name):
                self.assertEqual(claude["name"], codex["name"])
                self.assertEqual(claude["description"], codex["description"])
                self.assertEqual(codex["description"], meta["description"])
                self.assertEqual((claude["model"], claude["effort"]),
                                 (meta["claude.model"], meta["claude.effort"]))
                self.assertEqual((codex["model"], codex["model_reasoning_effort"]),
                                 (meta["codex.model"], meta["codex.effort"]))
                self.assertEqual(codex["developer_instructions"].strip(), body.strip())

    def test_chief_is_never_rendered(self) -> None:
        self.assertEqual(self.run_sync().returncode, 0)
        self.assertFalse((self.claude_agents / "chief.md").exists())
        self.assertFalse((self.codex_agents / "chief.toml").exists())

    def test_second_render_is_zero_operations(self) -> None:
        self.assertEqual(self.run_sync().returncode, 0)
        again = self.run_sync()
        self.assertEqual(again.returncode, 0)
        self.assertIn("already up to date", again.stdout)
        preview = self.run_sync("--scope", "global", "--preview", "--json")
        self.assertEqual(json.loads(preview.stdout)["operations"], [])

    def test_check_reports_current_stale_and_missing(self) -> None:
        self.assertEqual(self.run_sync("--check").returncode, 1)
        self.assertEqual(self.run_sync().returncode, 0)
        self.assertEqual(self.run_sync("--check").returncode, 0)
        target = self.claude_agents / "reviewer.md"
        target.write_text(target.read_text() + "\nhand edit\n", encoding="utf-8")
        stale = self.run_sync("--check")
        self.assertEqual(stale.returncode, 1)
        self.assertIn(f"    {target}", stale.stdout)

    def test_preview_json_schema_and_no_writes(self) -> None:
        proc = self.run_sync("--scope", "global", "--preview", "--json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        plan = json.loads(proc.stdout)
        self.assertEqual(set(plan), {"schema_version", "scope", "operations", "findings"})
        self.assertEqual((plan["schema_version"], plan["scope"], plan["findings"]),
                         (1, "global", []))
        self.assertEqual(len(plan["operations"]), 2 * len(SPAWNABLE))
        for op in plan["operations"]:
            self.assertEqual(set(op), {"action", "path"})
            self.assertEqual(op["action"], "create")
        self.assertFalse(self.claude_agents.exists())

    def test_generated_orphans_are_pruned_and_hand_written_files_kept(self) -> None:
        self.claude_agents.mkdir(parents=True)
        orphan = self.claude_agents / "developer.md"
        orphan.write_text(f"---\n{sp.GENERATED}\nname: developer\n---\n", encoding="utf-8")
        mine = self.claude_agents / "mine.md"
        mine.write_text("---\nname: mine\n---\n", encoding="utf-8")
        self.assertEqual(self.run_sync().returncode, 0)
        self.assertFalse(orphan.exists())
        self.assertTrue(mine.exists())

    def test_a_stale_chief_rendering_is_pruned(self) -> None:
        self.assertEqual(self.run_sync().returncode, 0)
        stale = [self.claude_agents / "chief.md", self.codex_agents / "chief.toml"]
        for path in stale:
            path.write_text(f"{sp.GENERATED}\nname: chief\n", encoding="utf-8")
        check = self.run_sync("--check")
        self.assertEqual(check.returncode, 1)
        self.assertIn(str(stale[0]), check.stdout)
        self.assertEqual(self.run_sync().returncode, 0)
        self.assertFalse(any(p.exists() for p in stale))

    def test_list_and_route(self) -> None:
        listing = self.run_sync("--list")
        self.assertEqual(listing.returncode, 0, listing.stderr)
        self.assertEqual(len(listing.stdout.strip().splitlines()), 1 + len(sp.BASE_PERSONA_NAMES))
        self.assertEqual(self.run_sync("--list", "--format", "markdown").returncode, 0)
        route = self.run_sync("--route", "builder", "--variant", "judgement")
        self.assertEqual(json.loads(route.stdout)["claude"],
                         {"model": "claude-opus-5-5", "effort": "high"})
        self.assertEqual(self.run_sync("--route", "builder", "--variant", "nope").returncode, 2)


class NoCodexTest(Hermetic):
    codex = False

    def test_codex_output_only_where_codex_lives(self) -> None:
        self.assertEqual(self.run_sync().returncode, 0)
        self.assertTrue((self.claude_agents / "builder.md").is_file())
        self.assertFalse(self.codex_home.exists())


class EmptyCodexHomeTest(Hermetic):
    codex = False

    def test_an_empty_codex_home_is_unset_not_the_working_directory(self) -> None:
        cwd = self.tmp / "cwd"
        cwd.mkdir()
        proc = self.run_sync(codex_home="", cwd=cwd)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(list(cwd.iterdir()), [])
        self.assertTrue((self.claude_agents / "builder.md").is_file())


class ProjectTest(Hermetic):
    def setUp(self) -> None:
        super().setUp()
        self.repo = self.tmp / "repo"
        self.sources = self.repo / "docs" / "agents" / "personas"
        self.sources.mkdir(parents=True)

    def test_a_project_persona_renders_to_both_project_trees(self) -> None:
        (self.sources / "domain-validator.md").write_text(PROJECT_PERSONA, encoding="utf-8")
        preview = self.run_sync("--repo", str(self.repo), "--scope", "project", "--preview",
                                "--json")
        self.assertEqual(preview.returncode, 0, preview.stdout + preview.stderr)
        plan = json.loads(preview.stdout)
        self.assertEqual(sorted(op["path"] for op in plan["operations"]), sorted([
            str(self.repo / ".claude" / "agents" / "domain-validator.md"),
            str(self.repo / ".codex" / "agents" / "domain-validator.toml")]))
        self.assertEqual(self.run_sync("--repo", str(self.repo), "--scope", "project").returncode,
                         0)
        self.assertEqual(self.run_sync("--repo", str(self.repo), "--check").returncode, 0)
        self.assertFalse(self.claude_agents.exists(), "project scope touched the user level")

    def test_a_base_named_project_file_is_skipped_with_a_warning(self) -> None:
        stale = self.repo / ".claude" / "agents" / "reviewer.md"
        stale.parent.mkdir(parents=True)
        stale.write_text(f"---\n{sp.GENERATED}\nname: reviewer\n---\n", encoding="utf-8")
        (self.sources / "reviewer.md").write_text(
            "---\nname: reviewer\ndescription: overlay\nwrites: no\n---\nProject direction.\n",
            encoding="utf-8")
        preview = self.run_sync("--repo", str(self.repo), "--scope", "project", "--preview",
                                "--json")
        self.assertEqual(preview.returncode, 0, preview.stderr)
        plan = json.loads(preview.stdout)
        self.assertEqual([f["severity"] for f in plan["findings"]], ["warning"])
        self.assertIn("overlays of base personas are retired", plan["findings"][0]["message"])
        self.assertEqual(plan["operations"], [{"action": "delete", "path": str(stale)}])
        applied = self.run_sync("--repo", str(self.repo), "--scope", "project")
        self.assertEqual(applied.returncode, 0, applied.stderr)
        self.assertIn("retired", applied.stderr)
        self.assertFalse(stale.exists())
        self.assertFalse((self.repo / ".codex" / "agents" / "reviewer.toml").exists())

    def test_a_project_name_cannot_shadow_a_judge_through_yaml(self) -> None:
        """`name: reviewer #x` parses as `reviewer` in YAML; a quoted name does the same."""
        cases = {"reviewer #x": "reviewer #x", '"reviewer"': "'\"reviewer\"'",
                 "Reviewer": "Reviewer", "chief x": "chief x"}
        for stem, name in cases.items():
            with self.subTest(stem=stem):
                for old in self.sources.iterdir():
                    old.unlink()
                (self.sources / f"{stem}.md").write_text(
                    f"---\nname: {name}\ndescription: x\nwrites: yes\n"
                    f"claude.tools: Read, Write, Edit, Bash\n---\nWrite things.\n",
                    encoding="utf-8")
                proc = self.run_sync("--repo", str(self.repo), "--scope", "project")
                rendered = [p for d in (".claude", ".codex")
                            for p in (self.repo / d / "agents").glob("*")]
                self.assertEqual(rendered, [], proc.stdout + proc.stderr)
                if stem.lower() in sp.BASE_PERSONA_NAMES:
                    self.assertIn("retired", proc.stderr)  # skipped, case-insensitively
                else:
                    self.assertEqual(proc.returncode, 2, proc.stdout)
                    check = self.run_sync("--repo", str(self.repo), "--check")
                    self.assertEqual(check.returncode, 2)

    def test_an_undecodable_project_source_is_a_source_error(self) -> None:
        (self.sources / "bad.md").write_bytes(b"---\nname: bad\xff\n---\n")
        self.assertEqual(self.run_sync("--repo", str(self.repo), "--check").returncode, 2)

    def test_a_broken_project_persona_is_a_source_error(self) -> None:
        (self.sources / "broken.md").write_text("no frontmatter\n", encoding="utf-8")
        self.assertEqual(self.run_sync("--repo", str(self.repo), "--check").returncode, 2)


if __name__ == "__main__":
    unittest.main()
