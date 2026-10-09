"""Extra pool sources are ignored with a warning; only a missing v6 source is an error.

An installed skill keeps the v5.1 persona sources until `install.sh --retire-v5` (a plain install
removes nothing), so the renderer must render the v6 pool beside them without failing.
"""

from __future__ import annotations

import json
import unittest

from support import Hermetic, load_module

sp = load_module()

OLD_SOURCE = """---
name: old-planner
description: A v5.1 persona source left behind by a plain install.
writes: no
claude.model: opus
---
Plan things.
"""

# Named like a v6 judge variant and declaring writes: yes. If the renderer rendered it, it would be a
# writable agent outside every judge restriction.
VARIANT = """---
name: reviewer-x
description: Not a v6 persona.
writes: yes
claude.model: opus
codex.sandbox: workspace-write
---
Review and edit.
"""


class RetiredSourceTest(Hermetic):
    def setUp(self) -> None:
        super().setUp()
        self.pool = self.copy_skill()
        (self.pool / "old-planner.md").write_text(OLD_SOURCE, encoding="utf-8")
        (self.pool / "reviewer-x.md").write_text(VARIANT, encoding="utf-8")

    def assert_not_rendered(self, *names: str) -> None:
        for name in names:
            self.assertFalse((self.claude_agents / f"{name}.md").exists(), name)
            self.assertFalse((self.codex_agents / f"{name}.toml").exists(), name)

    def test_extra_sources_are_ignored_with_a_warning_and_exit_0(self) -> None:
        proc = self.run_sync()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        for name in ("old-planner", "reviewer-x"):
            self.assertIn(f"WARNING retired persona source {name}", proc.stderr)
        self.assertIn("run install.sh --retire-v5", proc.stderr)
        self.assert_not_rendered("old-planner", "reviewer-x")
        # The v6 pool still renders in both harnesses.
        self.assertTrue((self.claude_agents / "reviewer.md").is_file())
        self.assertTrue((self.codex_agents / "reviewer.toml").is_file())
        self.assertEqual(self.run_sync("--check").returncode, 0)

    def test_check_and_preview_json_report_the_warning_and_do_not_fail(self) -> None:
        self.assertEqual(self.run_sync().returncode, 0)
        check = self.run_sync("--check")
        self.assertEqual(check.returncode, 0, check.stdout + check.stderr)
        self.assertIn("WARNING retired persona source old-planner", check.stderr)
        proc = self.run_sync("--scope", "global", "--preview", "--json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        findings = json.loads(proc.stdout)["findings"]
        self.assertEqual({f["severity"] for f in findings}, {"warning"})
        self.assertEqual(sorted(f["message"].split()[3] for f in findings),
                         ["old-planner", "reviewer-x"])

    def test_a_retired_sources_render_is_kept_and_an_orphan_render_is_pruned(self) -> None:
        kept = {self.claude_agents / "old-planner.md": f"---\n{sp.GENERATED}\nname: old-planner\n---\n",
                self.codex_agents / "old-planner.toml": f'{sp.GENERATED}\nname = "old-planner"\n'}
        orphans = [self.claude_agents / "gone.md", self.codex_agents / "gone.toml"]
        for path, text in kept.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        for path in orphans:
            path.write_text(f"{sp.GENERATED}\n", encoding="utf-8")
        proc = self.run_sync("--scope", "global")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        for path, text in kept.items():
            self.assertEqual(path.read_text(encoding="utf-8"), text, path)
        for path in orphans:
            self.assertFalse(path.exists(), path)
        self.assertEqual(self.run_sync("--check").returncode, 0)

    def test_a_missing_v6_source_is_still_exit_2(self) -> None:
        (self.pool / "builder.md").unlink()
        proc = self.run_sync()
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("missing: builder", proc.stderr)
        self.assertFalse(self.claude_agents.exists())

    def test_a_judge_variant_name_is_not_rendered(self) -> None:
        self.assertEqual(self.run_sync().returncode, 0)
        self.assert_not_rendered("reviewer-x")
        rendered = (self.claude_agents / "reviewer.md").read_text(encoding="utf-8")
        self.assertNotIn("Review and edit.", rendered)


if __name__ == "__main__":
    unittest.main()
