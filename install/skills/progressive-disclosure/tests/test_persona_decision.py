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
    def make_standard_repo(self, root: Path, *, index_extra: str = "") -> None:
        agents = root / "docs" / "agents"
        agents.mkdir(parents=True)
        (root / "AGENTS.md").write_text(
            "# Contract\n\nRead [the route](docs/agents/README.md).\n",
            encoding="utf-8",
        )
        (root / "CLAUDE.md").write_text("@AGENTS.md\n", encoding="utf-8")
        (agents / "README.md").write_text(
            "# Agent route\n\n"
            "| Task | Read next | Verification |\n"
            "| --- | --- | --- |\n"
            "| Routing | [disclosure](disclosure.md) | `true` |\n"
            f"{index_extra}",
            encoding="utf-8",
        )
        (agents / "disclosure.md").write_text(
            "<!-- progressive-disclosure standard v1.2 -->\n"
            "# Disclosure\n",
            encoding="utf-8",
        )

    def test_standard_repo_without_specialists_or_base_only_decision_warns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_standard_repo(root)
            report = validator.Report()

            validator.check_persona_decision(root, {}, report)

            self.assertEqual(
                [item["kind"] for item in report.warns],
                ["persona-decision-missing"],
            )

    def test_unstamped_routed_repo_without_a_decision_warns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_standard_repo(root)
            (root / "docs" / "agents" / "disclosure.md").write_text(
                "# Custom disclosure route\n",
                encoding="utf-8",
            )
            report = validator.Report()

            validator.check_persona_decision(root, {}, report)

            self.assertEqual(
                [item["kind"] for item in report.warns],
                ["persona-decision-missing"],
            )

    def test_base_only_decision_requires_and_accepts_a_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_standard_repo(
                root,
                index_extra=(
                    "\n<!-- agent-personas: "
                    '{"mode":"base-only","reason":"domain-neutral library; '
                    'the base reviewers cover its risks"} -->\n'
                ),
            )
            report = validator.Report()

            validator.check_persona_decision(root, {}, report)

            self.assertEqual(report.warns, [])
            self.assertEqual(report.errors, [])

    def test_empty_base_only_reason_warns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_standard_repo(
                root,
                index_extra=(
                    "\n<!-- agent-personas: "
                    '{"mode":"base-only","reason":""} -->\n'
                ),
            )
            report = validator.Report()

            validator.check_persona_decision(root, {}, report)

            self.assertEqual(report.warns, [])
            self.assertEqual(
                [item["kind"] for item in report.errors],
                ["persona-decision-invalid"],
            )

    def test_malformed_duplicate_and_unknown_decisions_warn(self) -> None:
        cases = {
            "malformed": '<!-- agent-personas: {"mode": -->\n',
            "unknown": (
                '<!-- agent-personas: {"mode":"specialists","reason":"later"} -->\n'
            ),
            "duplicate": (
                '<!-- agent-personas: {"mode":"base-only","reason":"one"} -->\n'
                '<!-- agent-personas: {"mode":"base-only","reason":"two"} -->\n'
            ),
        }
        for name, marker in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                self.make_standard_repo(root, index_extra="\n" + marker)
                report = validator.Report()

                validator.check_persona_decision(root, {}, report)

                self.assertIn(
                    "persona-decision-invalid",
                    [item["kind"] for item in report.errors],
                )

    def test_fenced_marker_is_an_example_not_a_decision(self) -> None:
        for fence in ("```", "~~~"):
            with self.subTest(fence=fence), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                self.make_standard_repo(
                    root,
                    index_extra=(
                        f"\n{fence}markdown\n"
                        '<!-- agent-personas: {"mode":"base-only","reason":"example"} -->\n'
                        f"{fence}\n"
                    ),
                )
                report = validator.Report()

                validator.check_persona_decision(root, {}, report)

                self.assertEqual(
                    [item["kind"] for item in report.warns],
                    ["persona-decision-missing"],
                )
                self.assertEqual(report.errors, [])

    def test_valid_plus_malformed_marker_is_rejected_as_duplicate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_standard_repo(
                root,
                index_extra=(
                    "\n"
                    '<!-- agent-personas: {"mode":"base-only","reason":"one"} -->\n'
                    '<!-- agent-personas: {"mode": -->\n'
                ),
            )
            report = validator.Report()

            validator.check_persona_decision(root, {}, report)

            self.assertEqual(report.warns, [])
            self.assertEqual(
                [item["kind"] for item in report.errors],
                ["persona-decision-invalid"],
            )

    def test_personas_readme_alone_does_not_count_as_a_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_standard_repo(root)
            sources = root / "docs" / "agents" / "personas"
            sources.mkdir()
            (sources / "README.md").write_text("# Notes\n", encoding="utf-8")
            report = validator.Report()

            validator.check_persona_decision(root, {}, report)

            self.assertEqual(
                [item["kind"] for item in report.warns],
                ["persona-decision-missing"],
            )

    def test_specialists_require_a_routed_persona_guide(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_standard_repo(root)
            sources = root / "docs" / "agents" / "personas"
            sources.mkdir()
            (sources / "domain-validator.md").write_text(
                "---\nname: domain-validator\ndescription: Test\n---\nTest.\n",
                encoding="utf-8",
            )
            report = validator.Report()

            validator.check_persona_decision(root, {}, report)

            self.assertEqual(report.warns, [])
            self.assertEqual(
                [item["kind"] for item in report.errors],
                ["persona-route-missing"],
            )

    def test_routed_specialists_satisfy_the_decision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_standard_repo(
                root,
                index_extra=(
                    "| Persona maintenance | [personas](personas.md) | "
                    "`python3 sync_personas.py --repo . --check` |\n"
                ),
            )
            guide = root / "docs" / "agents" / "personas.md"
            guide.write_text("# Project personas\n", encoding="utf-8")
            sources = root / "docs" / "agents" / "personas"
            sources.mkdir()
            (sources / "domain-validator.md").write_text(
                "---\nname: domain-validator\ndescription: Test\n---\nTest.\n",
                encoding="utf-8",
            )
            report = validator.Report()

            validator.check_persona_decision(root, {guide.resolve(): 2}, report)

            self.assertEqual(report.warns, [])
            self.assertEqual(report.errors, [])

    def test_base_only_marker_conflicts_with_specialist_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_standard_repo(
                root,
                index_extra=(
                    "\n<!-- agent-personas: "
                    '{"mode":"base-only","reason":"base reviewers cover the project"} -->\n'
                ),
            )
            sources = root / "docs" / "agents" / "personas"
            sources.mkdir()
            (sources / "domain-validator.md").write_text(
                "---\nname: domain-validator\ndescription: Test\n---\nTest.\n",
                encoding="utf-8",
            )
            report = validator.Report()

            validator.check_persona_decision(root, {}, report)

            self.assertIn(
                "persona-decision-conflict",
                [item["kind"] for item in report.errors],
            )

    def test_hook_mode_is_quiet_when_clean_and_reports_missing_decision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_standard_repo(root)
            command = [
                sys.executable,
                str(SCRIPTS / "validate_disclosure.py"),
                str(root),
                "--hook",
            ]

            missing = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(missing.returncode, 0)
            self.assertIn("[persona-decision-missing]", missing.stdout)
            self.assertNotIn("progressive disclosure:", missing.stdout)

            index = root / "docs" / "agents" / "README.md"
            index.write_text(
                index.read_text(encoding="utf-8")
                + "\n<!-- agent-personas: "
                '{"mode":"base-only","reason":"domain-neutral library; '
                'base reviewers cover its risks"} -->\n',
                encoding="utf-8",
            )
            clean = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(clean.returncode, 0)
            self.assertEqual(clean.stdout, "")

    def test_new_route_scaffold_leaves_an_explicit_persona_choice(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            creates = dict(migrator.plan_creates(root, []))

            index = creates[root / "docs" / "agents" / "README.md"]
            self.assertIn(
                "<!-- agent-personas: TODO choose project specialists "
                "or base-only with a reason -->",
                index,
            )
            disclosure = creates[root / "docs" / "agents" / "disclosure.md"]
            self.assertIn("progressive-disclosure standard v1.2", disclosure)

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
                'print("WARN [persona-decision-missing] choose explicitly")\n',
                encoding="utf-8",
            )
            installer.write_hook(
                hook,
                installer.PRE_COMMIT.format(
                    begin=installer.BEGIN,
                    end=installer.END,
                    flags="",
                ),
            )
            self.assertIn("--hook", hook.read_text(encoding="utf-8"))

            checked = subprocess.run(
                [str(hook)],
                cwd=root,
                capture_output=True,
                text=True,
                env={**dict(os.environ), "HOME": str(home)},
            )

            self.assertEqual(checked.returncode, 0)
            self.assertIn("persona-decision-missing", checked.stdout)


if __name__ == "__main__":
    unittest.main()
