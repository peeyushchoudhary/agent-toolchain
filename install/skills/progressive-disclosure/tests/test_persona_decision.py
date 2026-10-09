from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SKILL = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL / "scripts"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


validator = load_module("validate_disclosure_test", SCRIPTS / "validate_disclosure.py")
sys.path.insert(0, str(SCRIPTS))
migrator = load_module("migrate_to_standard_test", SCRIPTS / "migrate_to_standard.py")
installer = load_module("install_hooks_test", SCRIPTS / "install_hooks.py")


class PersonaDecisionTest(unittest.TestCase):
    def test_plan_moves_deduplicates_overlapping_runbook_globs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            docs = root / "docs"
            docs.mkdir()
            runbook = docs / "RUNBOOK_data.md"
            runbook.write_text("# Runbook\n", encoding="utf-8")

            moves = migrator.plan_moves(root)

            self.assertEqual(
                moves,
                [(runbook, docs / "runbooks" / "runbook_data.md")],
            )

    def test_invalid_persona_source_is_a_structural_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sources = root / "docs" / "agents" / "personas"
            sources.mkdir(parents=True)
            (sources / "notes.md").write_text("# Not a persona\n", encoding="utf-8")
            report = validator.Report()
            failed = subprocess.CompletedProcess(
                args=[],
                returncode=2,
                stdout="",
                stderr="ERROR overlay notes.md: no frontmatter",
            )

            with mock.patch.object(validator.subprocess, "run", return_value=failed):
                validator.check_personas(root, report)

            self.assertEqual(report.warns, [])
            self.assertEqual(
                [item["kind"] for item in report.errors],
                ["persona-source-invalid"],
            )

    def test_pre_commit_surfaces_warnings_without_failing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            hook = root / ".git" / "hooks" / "pre-commit"
            hook.parent.mkdir(parents=True)
            (root / "docs" / "agents").mkdir(parents=True)
            (root / "docs" / "agents" / "README.md").write_text(
                "# Agent route\n",
                encoding="utf-8",
            )
            home = root / "home"
            validator_path = (
                home
                / ".claude"
                / "skills"
                / "progressive-disclosure"
                / "scripts"
                / "validate_disclosure.py"
            )
            validator_path.parent.mkdir(parents=True)
            validator_path.write_text(
                'print("WARN [orphan] docs/agents/notes.md is not linked")\n',
                encoding="utf-8",
            )
            # Through render_pre_commit, not PRE_COMMIT.format: hand-formatting the template here
            # reimplemented production's composition, and when a fourth placeholder was added this
            # case failed for the wrong reason — a KeyError, not a bad hook. Ask for the flags
            # production is actually installed with and let one function render them.
            installer.write_hook(hook, installer.render_pre_commit())
            self.assertIn("--hook", hook.read_text(encoding="utf-8"))

            checked = subprocess.run(
                [str(hook)],
                cwd=root,
                capture_output=True,
                text=True,
                env={**dict(os.environ), "HOME": str(home)},
            )

            self.assertEqual(checked.returncode, 0)
            self.assertIn("[orphan]", checked.stdout)

    def test_render_pre_commit_covers_every_placeholder(self) -> None:
        """No placeholder may survive rendering, under any flag combination.

        The regression this replaces was a *missing* placeholder argument, so the guard has to be
        that the composition is total — not that one particular key was passed.
        """
        for standard in (False, True):
            for public in (False, True):
                with self.subTest(standard=standard, public=public):
                    text = installer.render_pre_commit(standard=standard, public=public)
                    self.assertNotIn("{", text)
                    self.assertIn(installer.BEGIN, text)
                    self.assertIn(installer.END, text)
                    self.assertIn(
                        " --standard" if standard else " --readme",
                        text,
                    )

    def test_public_and_private_pre_commit_hooks_differ(self) -> None:
        """--public must still be what decides whether the identifier guard is in the hook.

        Routing both callers through one function is only safe if the function has kept the
        distinction; a helper that rendered the same text either way would silently install the
        guard everywhere, or nowhere.
        """
        private = installer.render_pre_commit(public=False)
        public = installer.render_pre_commit(public=True)

        self.assertNotEqual(private, public)
        self.assertNotIn("identifier_guard.py", private)
        self.assertIn("identifier_guard.py", public)
        self.assertIn(installer.PRE_COMMIT_IDENTIFIER, public)
        # The guard is rendered INSIDE the marked block, so dropping --public takes it away again.
        self.assertLess(public.index("identifier_guard.py"), public.index(installer.END))
        # Both keep the route check: --public adds a stanza, it does not replace one.
        for text in (private, public):
            self.assertIn("validate_disclosure.py", text)


if __name__ == "__main__":
    unittest.main()
