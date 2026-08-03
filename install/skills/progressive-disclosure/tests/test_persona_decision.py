from __future__ import annotations

import importlib.util
import os
import shutil
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
            # `HOME` redirected, and to a directory OUTSIDE `root`, which is the repository under
            # validation. `validate_disclosure.py` reaches `Path.home()` in two places that run
            # before it can return, so an unpinned run reads whatever this machine has installed —
            # and `assertEqual(clean.stdout, "")` is precisely the assertion one machine-dependent
            # extra line breaks.
            #
            # PINNING IT ALONE MADE THE TEST FAIL, which is the point: `check_personas()` warns
            # `persona-tool-missing` when `~/.claude/skills/agent-personas/scripts/sync_personas.py`
            # is absent, and the empty-stdout assertion was only ever true because THIS machine has
            # that tool installed. So the fixture supplies it — a stub that exits 0, i.e. "the tool
            # is installed and finds no drift", which is the state the real machine was silently
            # providing. The assertion is unchanged; only its input stopped being ambient.
            home = Path(tempfile.mkdtemp(prefix="pd-persona-home-"))
            self.addCleanup(shutil.rmtree, home, True)
            sync = home / ".claude" / "skills" / "agent-personas" / "scripts" / "sync_personas.py"
            sync.parent.mkdir(parents=True)
            sync.write_text("raise SystemExit(0)\n", encoding="utf-8")
            env = {**os.environ, "HOME": str(home)}

            missing = subprocess.run(command, capture_output=True, text=True, env=env)
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
            clean = subprocess.run(command, capture_output=True, text=True, env=env)
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
            self.assertIn("persona-decision-missing", checked.stdout)

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
