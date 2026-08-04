from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate_card.py"

# A card that is correct in every way the validator checks. Every test below starts from this and
# breaks exactly one thing, so a finding can only come from the thing that was broken.
CLEAN_CARD = """\
id: EX-01
title: Widget dispatch is idempotent
goal: The widget cannot be dispatched twice.
persona: senior-developer

exclusive_writes:
  - backend/core/src/main/java/com/acme/core/**
  - backend/core/src/test/java/com/acme/core/**

forbidden_paths:
  - backend/app/**

context_acquisition:
  - "./scripts/agent-context.sh backend"
  - "Read nothing else unless this card names it. Do not read the plan."

frozen_values:
  - "Money is an integer count of minor units."

gate_risk: none

validation:
  - "cd backend && ./gradlew :core:test --tests 'com.acme.core.tenancy.TenantIsolationTest' --rerun-tasks"

stop_conditions:
  - "a migration is required"

commit_subject: "feat(core): close the duplicate window"
"""


def card_with(**overrides: str) -> str:
    """Replace whole top-level blocks of CLEAN_CARD. Keys are matched at column zero."""
    text = CLEAN_CARD
    for key, block in overrides.items():
        lines = text.splitlines(keepends=True)
        out: list[str] = []
        i = 0
        while i < len(lines):
            if lines[i].startswith(f"{key}:"):
                i += 1
                while i < len(lines) and (not lines[i].strip() or lines[i][:1].isspace()):
                    i += 1
                out.append(block if block.endswith("\n") else block + "\n")
                continue
            out.append(lines[i])
            i += 1
        text = "".join(out)
    return text


class ValidateCardTest(unittest.TestCase):
    def import_parser(self):
        sys.path.insert(0, str(SCRIPT.parent))
        try:
            from validate_card import as_list, parse_card  # type: ignore
        finally:
            sys.path.pop(0)
        return parse_card, as_list

    def make_repo(self, root: Path) -> Path:
        repo = root / "repo"
        files = {
            "backend/core/build.gradle.kts": "plugins { java }\n",
            "backend/app/build.gradle.kts": "plugins { java }\n",
            "backend/core/src/main/java/com/acme/core/Widget.java":
                "package com.acme.core;\nclass Widget {}\n",
            "backend/core/src/test/java/com/acme/core/tenancy/TenantIsolationTest.java":
                "package com.acme.core.tenancy;\nclass TenantIsolationTest {}\n",
            "backend/app/src/main/java/com/acme/app/App.java":
                "package com.acme.app;\nclass App {}\n",
            "backend/app/src/main/resources/db/migration/V187__emergency_stop.sql": "-- x\n",
        }
        for rel, body in files.items():
            path = repo / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding="utf-8")
        return repo

    def run_validator(self, card_text: str, repo: Path, *extra: str,
                      name: str = "card.yaml") -> subprocess.CompletedProcess:
        card = repo.parent / name
        card.write_text(card_text, encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(SCRIPT), str(card), "--repo", str(repo), *extra],
            capture_output=True, text=True, env={**os.environ},
        )

    def findings(self, result: subprocess.CompletedProcess, severity: str) -> list[str]:
        return [line.strip() for line in result.stdout.splitlines()
                if line.strip().startswith(severity)]

    # --- the headline check ------------------------------------------------------------------ #

    def test_clean_card_passes_with_no_findings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))

            result = self.run_validator(CLEAN_CARD, repo, "--strict")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("no findings", result.stdout)

    def test_missing_test_class_is_an_error_with_the_right_suggestion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            card = card_with(validation=textwrap.dedent("""\
                validation:
                  - "cd backend && ./gradlew :app:test --tests 'com.acme.app.TenantIsolationTest' --rerun-tasks"
                """))

            result = self.run_validator(card, repo)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            errors = self.findings(result, "ERROR")
            self.assertEqual(len(errors), 1, result.stdout)
            self.assertIn("com.acme.app.TenantIsolationTest not found", errors[0])
            self.assertIn("did you mean com.acme.core.tenancy.TenantIsolationTest "
                          "(backend/core)?", errors[0])
            self.assertIn("BUILD SUCCESSFUL", errors[0])

    def test_unknown_test_class_with_no_namesake_still_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            card = card_with(validation=textwrap.dedent("""\
                validation:
                  - "cd backend && ./gradlew :core:test --tests 'com.acme.core.NoSuchTest' --rerun-tasks"
                """))

            result = self.run_validator(card, repo)

            self.assertEqual(result.returncode, 1)
            self.assertIn("no class named NoSuchTest exists", result.stdout)

    def test_class_in_another_module_than_the_test_task_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            card = card_with(validation=textwrap.dedent("""\
                validation:
                  - "cd backend && ./gradlew :app:test --tests 'com.acme.core.tenancy.TenantIsolationTest' --rerun-tasks"
                """))

            result = self.run_validator(card, repo, "--strict")

            self.assertEqual(result.returncode, 1)
            self.assertIn("but the command runs :app:test", result.stdout)

    # --- pytest node-id resolution ----------------------------------------------------------- #

    def test_missing_pytest_retain_selector_is_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            card = card_with(
                validation=textwrap.dedent("""\
                    validation:
                      - ".venv/bin/python -m pytest tests/test_widget.py::test_missing"
                    """),
            ) + "tests:\n  - Retain tests/test_widget.py::test_missing\n"

            result = self.run_validator(card, repo)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("Retain tests/test_widget.py::test_missing", result.stdout)
            self.assertIn("does not exist", result.stdout)

    def test_existing_pytest_retain_selector_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            test_file = repo / "tests/test_widget.py"
            test_file.parent.mkdir(parents=True)
            test_file.write_text("def test_widget():\n    pass\n", encoding="utf-8")
            card = card_with(
                validation=textwrap.dedent("""\
                    validation:
                      - ".venv/bin/python -m pytest tests/test_widget.py::test_widget"
                    """),
            ) + "tests:\n  - Retain tests/test_widget.py::test_widget\n"

            result = self.run_validator(card, repo, "--strict")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("no findings", result.stdout)

    def test_owned_missing_pytest_create_selector_warns_pre_dispatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            card = card_with(
                exclusive_writes=textwrap.dedent("""\
                    exclusive_writes:
                      - backend/core/src/main/java/com/acme/core/**
                      - backend/core/src/test/java/com/acme/core/**
                      - tests/test_widget.py
                    """),
                validation=textwrap.dedent("""\
                    validation:
                      - ".venv/bin/python -m pytest tests/test_widget.py::test_created"
                    """),
            ) + "tests:\n  - Create tests/test_widget.py::test_created\n"

            result = self.run_validator(card, repo)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("WARNING", result.stdout)
            self.assertIn("Create tests/test_widget.py::test_created", result.stdout)

    def test_owned_missing_pytest_create_selector_fails_strict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            card = card_with(
                exclusive_writes=textwrap.dedent("""\
                    exclusive_writes:
                      - backend/core/src/main/java/com/acme/core/**
                      - backend/core/src/test/java/com/acme/core/**
                      - tests/test_widget.py
                    """),
                validation=textwrap.dedent("""\
                    validation:
                      - ".venv/bin/python -m pytest tests/test_widget.py::test_created"
                    """),
            ) + "tests:\n  - Create tests/test_widget.py::test_created\n"

            result = self.run_validator(card, repo, "--strict")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("Create tests/test_widget.py::test_created", result.stdout)

    def test_unowned_missing_pytest_create_selector_is_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            card = card_with(
                validation=textwrap.dedent("""\
                    validation:
                      - ".venv/bin/python -m pytest tests/test_widget.py::test_created"
                    """),
            ) + "tests:\n  - Create tests/test_widget.py::test_created\n"

            result = self.run_validator(card, repo)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("outside exclusive_writes", result.stdout)

    def test_missing_pytest_retain_overrides_create_regardless_of_order(self) -> None:
        declarations = [
            ("Retain tests/test_widget.py::test_missing",
             "Create tests/test_widget.py::test_missing"),
            ("Create tests/test_widget.py::test_missing",
             "Retain tests/test_widget.py::test_missing"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            for first, second in declarations:
                with self.subTest(first=first):
                    card = card_with(
                        exclusive_writes=textwrap.dedent("""\
                            exclusive_writes:
                              - backend/core/src/main/java/com/acme/core/**
                              - backend/core/src/test/java/com/acme/core/**
                              - tests/test_widget.py
                            """),
                        validation=textwrap.dedent("""\
                            validation:
                              - ".venv/bin/python -m pytest tests/test_widget.py::test_missing"
                            """),
                    ) + f"tests:\n  - {first}\n  - {second}\n"

                    result = self.run_validator(card, repo)

                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertIn("Retain tests/test_widget.py::test_missing", result.stdout)
                    self.assertNotIn("permitted before implementation", result.stdout)

    def test_pytest_selector_is_resolved_by_ast_without_import(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            test_file = repo / "tests/test_widget.py"
            marker = repo.parent / "imported"
            test_file.parent.mkdir(parents=True)
            test_file.write_text(
                f"from pathlib import Path\nPath({str(marker)!r}).write_text('imported')\n"
                "def test_widget():\n    pass\n",
                encoding="utf-8",
            )
            card = card_with(
                validation=textwrap.dedent("""\
                    validation:
                      - ".venv/bin/python -m pytest tests/test_widget.py::test_widget"
                    """),
            ) + "tests:\n  - Retain tests/test_widget.py::test_widget\n"

            result = self.run_validator(card, repo, "--strict")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertFalse(marker.exists(), "validator imported or executed the candidate module")

    def test_unsupported_pytest_selectors_are_errors(self) -> None:
        selectors = [
            "tests/test_widget.py::WidgetTests::test_nested",
            "tests/test_widget.py::test_param[value]",
            "/tests/test_widget.py::test_absolute",
            "../tests/test_widget.py::test_traversal",
        ]
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            for selector in selectors:
                with self.subTest(selector=selector):
                    card = card_with(validation=textwrap.dedent(f"""\
                        validation:
                          - ".venv/bin/python -m pytest {selector}"
                        """))

                    result = self.run_validator(card, repo)

                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertIn("unsupported pytest selector", result.stdout)

    def test_dynamic_pytest_selectors_fail_closed(self) -> None:
        commands = [
            'TARGET=tests/test_widget.py; TEST=test_missing; '
            '.venv/bin/python -m pytest "$TARGET::$TEST"',
            'NODE=tests/test_widget.py::test_missing; '
            '.venv/bin/python -m pytest "$NODE"',
        ]
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            for command in commands:
                with self.subTest(command=command):
                    card = card_with(validation=(
                        "validation:\n"
                        f"  - '{command}'\n"
                    ))

                    result = self.run_validator(card, repo)

                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertIn("dynamic pytest selector", result.stdout)

    def test_every_pytest_shell_segment_is_scanned(self) -> None:
        controls = (";", "&&", "||")
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            test_file = repo / "tests/test_widget.py"
            test_file.parent.mkdir(parents=True)
            test_file.write_text("def test_widget():\n    pass\n", encoding="utf-8")
            for control in controls:
                with self.subTest(control=control):
                    command = (
                        ".venv/bin/python -m pytest "
                        f"tests/test_widget.py::test_widget {control} "
                        '.venv/bin/python -m pytest "$NODE"'
                    )
                    card = card_with(validation=(
                        "validation:\n"
                        f"  - '{command}'\n"
                    ))

                    result = self.run_validator(card, repo)

                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertIn("dynamic pytest selector", result.stdout)

    def test_attached_shell_controls_delimit_literal_pytest_selector(self) -> None:
        controls = (";", "&&", "||")
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            test_file = repo / "tests/test_widget.py"
            test_file.parent.mkdir(parents=True)
            test_file.write_text("def test_widget():\n    pass\n", encoding="utf-8")
            for control in controls:
                with self.subTest(control=control):
                    command = (
                        ".venv/bin/python -m pytest "
                        f"tests/test_widget.py::test_widget{control} true"
                    )
                    card = card_with(validation=(
                        "validation:\n"
                        f"  - '{command}'\n"
                    ))

                    result = self.run_validator(card, repo, "--strict")

                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn("no findings", result.stdout)

    def test_pytest_response_files_are_rejected_in_every_segment(self) -> None:
        commands = [
            ".venv/bin/python -m pytest @missing-args.txt",
            ".venv/bin/python -m pytest tests/test_widget.py::test_widget "
            "&& .venv/bin/python -m pytest @missing-args.txt",
        ]
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            test_file = repo / "tests/test_widget.py"
            test_file.parent.mkdir(parents=True)
            test_file.write_text("def test_widget():\n    pass\n", encoding="utf-8")
            for command in commands:
                with self.subTest(command=command):
                    card = card_with(validation=(
                        "validation:\n"
                        f"  - '{command}'\n"
                    ))

                    result = self.run_validator(card, repo)

                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertIn("pytest response-file argument", result.stdout)
                    self.assertIn("@missing-args.txt", result.stdout)

    def test_unparseable_pytest_invocations_fail_closed(self) -> None:
        commands = [
            'pytest "$NODE',
            '.venv/bin/python -m pytest "$NODE',
            'true | pytest "$NODE',
            'true | python -m pytest "$NODE',
        ]
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            for command in commands:
                with self.subTest(command=command):
                    card = card_with(validation=(
                        "validation:\n"
                        f"  - '{command}'\n"
                    ))

                    result = self.run_validator(card, repo)

                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertIn("cannot parse command invoking pytest", result.stdout)

    def test_non_pytest_double_colon_token_is_not_a_pytest_selector(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            card = card_with(
                validation="validation:\n  - \"cargo test module::test_name\"\n")

            result = self.run_validator(card, repo, "--strict")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("no findings", result.stdout)

    # --- cache-satisfiable validation -------------------------------------------------------- #

    def test_gradle_test_without_rerun_is_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            card = card_with(validation=textwrap.dedent("""\
                validation:
                  - "cd backend && ./gradlew :core:test --tests 'com.acme.core.tenancy.TenantIsolationTest'"
                """))

            result = self.run_validator(card, repo)

            self.assertEqual(result.returncode, 0, "a dirtyable module is a warning, not an error")
            self.assertIn("neither --rerun-tasks nor cleanTest", result.stdout)
            self.assertEqual(self.findings(result, "ERROR"), [])

    def test_cleantest_satisfies_the_rerun_requirement(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            card = card_with(validation=textwrap.dedent("""\
                validation:
                  - "cd backend && ./gradlew :core:cleanTest :core:test --tests 'com.acme.core.tenancy.TenantIsolationTest'"
                """))

            result = self.run_validator(card, repo, "--strict")

            self.assertEqual(result.returncode, 0, result.stdout)

    def test_unrerunnable_test_of_a_module_the_card_cannot_write_is_an_error(self) -> None:
        """Nothing this task does can invalidate :app, so the task is UP-TO-DATE by construction."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            card = card_with(
                forbidden_paths="forbidden_paths:\n  - backend/app/src/main/**\n",
                validation=textwrap.dedent("""\
                    validation:
                      - "cd backend && ./gradlew :app:test"
                    """),
            )

            result = self.run_validator(card, repo)

            self.assertEqual(result.returncode, 1)
            self.assertIn("exclusive_writes cannot dirty that module", result.stdout)

    # --- path coherence ---------------------------------------------------------------------- #

    def test_overlapping_write_and_forbidden_paths_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            card = card_with(
                forbidden_paths="forbidden_paths:\n  - backend/core/src/main/**\n")

            result = self.run_validator(card, repo)

            self.assertEqual(result.returncode, 1)
            self.assertIn("permits and forbids the same file", result.stdout)

    def test_a_card_that_creates_new_files_does_not_error(self) -> None:
        """The regression that would get this validator switched off within a week."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            card = card_with(exclusive_writes=textwrap.dedent("""\
                exclusive_writes:
                  - backend/core/src/main/java/com/acme/core/**
                  - backend/core/src/test/java/com/acme/core/**
                  - backend/core/src/main/java/com/acme/core/brandnew/Dispatcher.java
                """))

            result = self.run_validator(card, repo)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(self.findings(result, "ERROR"), [])

    def test_stale_forbidden_paths_glob_is_a_warning_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            card = card_with(forbidden_paths=textwrap.dedent("""\
                forbidden_paths:
                  - backend/app/**
                  - backend/gonemodule/**
                """))

            result = self.run_validator(card, repo)

            self.assertEqual(result.returncode, 0)
            self.assertIn("backend/gonemodule/** matches nothing", result.stdout)

    def test_manifest_writable_but_its_pinning_test_is_not_is_an_error(self) -> None:
        """Card defect 3: a write set that cannot be satisfied, found through the loader class."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            (repo / "backend/core/src/main/resources").mkdir(parents=True, exist_ok=True)
            (repo / "backend/core/src/main/resources/export-manifest.tsv").write_text(
                "table\tscope\n", encoding="utf-8")
            (repo / "backend/core/src/main/java/com/acme/core/ExportManifest.java").write_text(
                'package com.acme.core;\n'
                'class ExportManifest { static final String R = "/export-manifest.tsv"; }\n',
                encoding="utf-8")
            (repo / "backend/app/src/test/java/com/acme/app").mkdir(parents=True, exist_ok=True)
            (repo / "backend/app/src/test/java/com/acme/app/ManifestPinTest.java").write_text(
                "package com.acme.app;\n"
                "class ManifestPinTest { void t() { new ExportManifest(); } }\n",
                encoding="utf-8")
            card = card_with(exclusive_writes=textwrap.dedent("""\
                exclusive_writes:
                  - backend/core/src/main/java/com/acme/core/**
                  - backend/core/src/test/java/com/acme/core/**
                  - backend/core/src/main/resources/export-manifest.tsv
                """))

            result = self.run_validator(card, repo)

            self.assertEqual(result.returncode, 1)
            self.assertIn("unsatisfiable write set", result.stdout)
            self.assertIn("ManifestPinTest.java", result.stdout)

    def test_a_javadoc_mention_of_a_manifest_is_not_a_coupling(self) -> None:
        """The false positive that would make the previous check unusable."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            (repo / "backend/core/src/main/resources").mkdir(parents=True, exist_ok=True)
            (repo / "backend/core/src/main/resources/export-manifest.tsv").write_text(
                "table\tscope\n", encoding="utf-8")
            (repo / "backend/app/src/test/java/com/acme/app").mkdir(parents=True, exist_ok=True)
            (repo / "backend/app/src/test/java/com/acme/app/UnrelatedTest.java").write_text(
                "package com.acme.app;\n"
                "/**\n * Unlike export-manifest.tsv, this is a genuine parser test.\n */\n"
                "class UnrelatedTest {}\n",
                encoding="utf-8")
            card = card_with(exclusive_writes=textwrap.dedent("""\
                exclusive_writes:
                  - backend/core/src/main/java/com/acme/core/**
                  - backend/core/src/test/java/com/acme/core/**
                  - backend/core/src/main/resources/export-manifest.tsv
                """))

            result = self.run_validator(card, repo)

            self.assertEqual(self.findings(result, "ERROR"), [], result.stdout)
            self.assertEqual(result.returncode, 0)

    # --- required fields --------------------------------------------------------------------- #

    def test_missing_required_field_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            card = "\n".join(line for line in CLEAN_CARD.splitlines()
                             if not line.startswith("commit_subject:"))

            result = self.run_validator(card, repo)

            self.assertEqual(result.returncode, 1)
            self.assertIn("[commit_subject] required field is missing", result.stdout)

    def test_unknown_persona_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))

            result = self.run_validator(CLEAN_CARD.replace("persona: senior-developer",
                                                           "persona: junior"), repo)

            self.assertEqual(result.returncode, 1)
            self.assertIn("[persona] must be one of developer | senior-developer", result.stdout)

    def test_missing_persona_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            card = "\n".join(line for line in CLEAN_CARD.splitlines()
                             if not line.startswith("persona:"))

            result = self.run_validator(card, repo)

            self.assertEqual(result.returncode, 1)
            self.assertIn("[persona] required field is missing", result.stdout)

    # --- title: the card's name --------------------------------------------------------------- #
    #
    # Two controllers minted a card numbered TC-60 within minutes of each other and one clobbered
    # the other. A bare integer collides silently and carries no meaning: `TC-52, TC-53, TC-54`
    # needs a translation table every time it is read. The id stays the stable key; the title is
    # what prose and dispatches lead with.

    def test_a_card_with_no_title_warns_rather_than_failing(self) -> None:
        """~50 sealed cards predate this field. Failing them would fail closed on history."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            card = "\n".join(line for line in CLEAN_CARD.splitlines()
                             if not line.startswith("title:"))

            result = self.run_validator(card, repo)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(self.findings(result, "ERROR"), [], result.stdout)
            self.assertIn("[title] required field is missing", result.stdout)

    def test_a_card_with_no_title_fails_under_strict(self) -> None:
        """`--strict` is the invocation available to a caller that wants a titleless card refused.
        Nothing in this toolchain runs it automatically, so this pins the flag's behaviour and NOT
        a claim that a titleless card cannot be dispatched — it can."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            card = "\n".join(line for line in CLEAN_CARD.splitlines()
                             if not line.startswith("title:"))

            result = self.run_validator(card, repo, "--strict")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("[title] required field is missing", result.stdout)

    def test_an_empty_title_is_an_error_not_a_warning(self) -> None:
        """Absent means "written before the rule". Blank means "written now, and broken"."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))

            result = self.run_validator(CLEAN_CARD.replace(
                "title: Widget dispatch is idempotent", 'title: ""'), repo)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("[title] required field is present but empty", result.stdout)

    def test_a_multi_line_title_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            card = card_with(title=textwrap.dedent("""\
                title: |
                  Widget dispatch is idempotent
                  and also the invoice totals are fixed
                """))

            result = self.run_validator(card, repo)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("[title] must be a single line", result.stdout)

    def test_a_wrapped_plain_title_is_one_line_and_passes(self) -> None:
        """YAML plain-scalar folding makes this one logical line; it must not be a finding."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            card = card_with(title="title: Widget dispatch\n  is idempotent\n")

            result = self.run_validator(card, repo, "--strict")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("no findings", result.stdout)

    def test_title_length_bound_is_enforced_on_both_sides(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            for length, expected_rc in ((72, 0), (73, 1)):
                with self.subTest(length=length):
                    card = card_with(title="title: " + "w" * length + "\n")

                    result = self.run_validator(card, repo, "--strict")

                    self.assertEqual(result.returncode, expected_rc,
                                     result.stdout + result.stderr)
                    if expected_rc:
                        self.assertIn("[title] is 73 characters; the bound is 72",
                                      result.stdout)

    def test_a_title_that_merely_restates_the_id_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            for restatement in ("EX-01", "ex 01", "EX-01:", "[EX-01]"):
                with self.subTest(restatement=restatement):
                    card = card_with(title=f'title: "{restatement}"\n')

                    result = self.run_validator(card, repo)

                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertIn("restates the id", result.stdout)

    def test_a_title_that_carries_the_id_plus_real_words_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            card = card_with(title='title: "EX-01: widget dispatch is idempotent"\n')

            result = self.run_validator(card, repo, "--strict")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("no findings", result.stdout)

    def test_a_title_that_is_a_list_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            card = card_with(title="title:\n  - one name\n  - another name\n")

            result = self.run_validator(card, repo)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("[title] must be a single line", result.stdout)

    # --- cross-card uniqueness ----------------------------------------------------------------- #
    #
    # The failure this section exists for: two controllers each minted TC-60 minutes apart, one
    # overwrote the other, and it was recovered only because a human noticed. The sibling set is
    # read off the directory, never off anything the card under test declares — a uniqueness check
    # whose denominator comes from the card it is checking proves nothing.

    def sibling(self, repo: Path, name: str, text: str) -> Path:
        """Write another card beside the one under test. `repo.parent` is the card directory."""
        path = repo.parent / name
        path.write_text(text, encoding="utf-8")
        return path

    def header(self, result: subprocess.CompletedProcess) -> str:
        return result.stdout.splitlines()[0]

    def test_a_lone_card_with_no_siblings_still_validates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))

            result = self.run_validator(CLEAN_CARD, repo, "--strict")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("0 sibling card(s) compared", self.header(result))

    def test_a_card_does_not_collide_with_itself(self) -> None:
        """Including when the same file is reached by another spelling, or by a symlink beside it —
        the two traps of comparing by path rather than by identity."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            card_path = repo.parent / "card.yaml"
            card_path.write_text(CLEAN_CARD, encoding="utf-8")
            (repo.parent / "alias.yaml").symlink_to(card_path)

            result = subprocess.run(
                [sys.executable, str(SCRIPT), f"{repo.parent}/./card.yaml",
                 "--repo", str(repo), "--strict"],
                capture_output=True, text=True)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("0 sibling card(s) compared", self.header(result))

    def test_a_duplicate_id_in_a_sibling_card_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            self.sibling(repo, "other.yaml",
                         CLEAN_CARD.replace("title: Widget dispatch is idempotent",
                                            "title: A different piece of work"))

            result = self.run_validator(CLEAN_CARD, repo)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("[id] EX-01 is also used by other.yaml", result.stdout)

    def test_a_duplicate_title_in_a_sibling_card_is_an_error(self) -> None:
        """Same name, different id: nothing is clobbered, but the name stops naming anything."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            self.sibling(repo, "other.yaml", CLEAN_CARD.replace("id: EX-01", "id: EX-02"))

            result = self.run_validator(CLEAN_CARD, repo)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("[title] Widget dispatch is idempotent", result.stdout)
            self.assertIn("also used by other.yaml", result.stdout)
            self.assertNotIn("[id] EX-01 is also used", result.stdout)

    def test_title_collision_ignores_case_and_whitespace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            self.sibling(repo, "other.yaml",
                         CLEAN_CARD.replace("id: EX-01", "id: EX-02").replace(
                             "title: Widget dispatch is idempotent",
                             "title: 'WIDGET   dispatch is Idempotent'"))

            result = self.run_validator(CLEAN_CARD, repo)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("also used by other.yaml", result.stdout)

    def test_two_untitled_sealed_cards_do_not_collide_on_an_absent_title(self) -> None:
        """The regression that would make every one of ~50 sealed cards a duplicate of the rest."""
        untitled = "\n".join(line for line in CLEAN_CARD.splitlines()
                             if not line.startswith("title:"))
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            self.sibling(repo, "other.yaml", untitled.replace("id: EX-01", "id: EX-02"))

            result = self.run_validator(untitled, repo)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(self.findings(result, "ERROR"), [], result.stdout)

    def test_an_unparseable_sibling_is_reported_and_skipped_not_fatal(self) -> None:
        """Failing card A because card B is malformed is failing closed on the wrong file — and it
        must not disarm the check against the siblings that DID parse."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            self.sibling(repo, "broken.yaml", CLEAN_CARD + "defaults: &base\n  persona: developer\n")
            self.sibling(repo, "zzz-clash.yaml",
                         CLEAN_CARD.replace("title: Widget dispatch is idempotent",
                                            "title: A different piece of work"))

            result = self.run_validator(CLEAN_CARD, repo)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("[siblings] broken.yaml could not be parsed", result.stdout)
            self.assertIn("anchors/aliases", result.stdout)
            self.assertIn("[id] EX-01 is also used by zzz-clash.yaml", result.stdout)
            self.assertIn("1 sibling card(s) compared, 1 not read", self.header(result))

    def test_an_unparseable_sibling_alone_is_a_warning_not_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            self.sibling(repo, "broken.yaml", "id: EX-09\nnote: !!str hello\n")

            result = self.run_validator(CLEAN_CARD, repo)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(self.findings(result, "ERROR"), [], result.stdout)
            self.assertIn("[siblings] broken.yaml could not be parsed", result.stdout)

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root can read anything")
    def test_an_unreadable_sibling_is_reported_and_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            path = self.sibling(repo, "locked.yaml", CLEAN_CARD)
            os.chmod(path, 0o000)
            try:
                result = self.run_validator(CLEAN_CARD, repo)
            finally:
                os.chmod(path, 0o600)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("[siblings] locked.yaml could not be read", result.stdout)
            self.assertIn("0 sibling card(s) compared, 1 not read", self.header(result))

    def test_a_skipped_sibling_does_not_fail_the_card_even_under_strict(self) -> None:
        """The module docstring promises a skipped sibling is "never a reason to fail the card being
        validated". Under `--strict` that promise used to break: a `[siblings]` WARNING is a finding,
        and an otherwise perfect card exited 1 because a DIFFERENT file — one its author did not
        write and cannot fix — was unreadable. `[siblings]` is therefore exempt from the strict
        exit. The warning is still printed and still counted; only the exit code is exempt."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            self.sibling(repo, "broken.yaml", "id: EX-09\nnote: !!str hello\n")

            result = self.run_validator(CLEAN_CARD, repo, "--strict")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("[siblings] broken.yaml could not be parsed", result.stdout)
            self.assertIn("0 error(s), 1 warning(s)", result.stdout)

    def test_the_strict_sibling_exemption_does_not_excuse_any_other_warning(self) -> None:
        """The exemption is scoped to `[siblings]`, not a blanket way to survive `--strict`. A card
        carrying its own warning still fails, even when a skipped sibling sits beside it."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            self.sibling(repo, "broken.yaml", "id: EX-09\nnote: !!str hello\n")
            card = "\n".join(line for line in CLEAN_CARD.splitlines()
                             if not line.startswith("title:"))

            result = self.run_validator(card, repo, "--strict")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("[siblings] broken.yaml could not be parsed", result.stdout)
            self.assertIn("[title] required field is missing", result.stdout)

    def test_the_sibling_set_is_the_directory_and_is_neither_recursive_nor_all_files(self) -> None:
        """Scope is the card's own directory: one plan's workspace, which is exactly the unit two
        concurrent controllers share. A nested directory is a different plan, and a .md is not a
        card. The count in the header is computed from the listing, not from the card."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            self.sibling(repo, "notes.md", "id: EX-01\ntitle: Widget dispatch is idempotent\n")
            nested = repo.parent / "nested"
            nested.mkdir()
            (nested / "deep.yaml").write_text(CLEAN_CARD, encoding="utf-8")
            self.sibling(repo, "peer.yaml", CLEAN_CARD.replace("id: EX-01", "id: EX-02").replace(
                "title: Widget dispatch is idempotent", "title: Another job entirely"))

            result = self.run_validator(CLEAN_CARD, repo)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(self.findings(result, "ERROR"), [], result.stdout)
            on_disk = sorted(p.name for p in repo.parent.iterdir() if p.suffix == ".yaml")
            self.assertEqual(on_disk, ["card.yaml", "peer.yaml"])
            self.assertIn(f"{len(on_disk) - 1} sibling card(s) compared", self.header(result))

    def test_every_colliding_sibling_is_named(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            for name in ("a-twin.yaml", "b-twin.yaml"):
                self.sibling(repo, name, CLEAN_CARD)

            result = self.run_validator(CLEAN_CARD, repo)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("a-twin.yaml, b-twin.yaml", result.stdout)

    # --- the deprecated `tier` alias --------------------------------------------------------- #

    def test_tier_is_accepted_as_a_deprecated_alias_and_warned_about(self) -> None:
        """An in-flight card written before the rename must still validate, loudly."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            card = CLEAN_CARD.replace("persona: senior-developer", "tier: senior-developer")

            result = self.run_validator(card, repo)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(self.findings(result, "ERROR"), [], result.stdout)
            self.assertIn("[tier] `tier` is the former name of `persona`", result.stdout)
            self.assertNotIn("[persona] required field is missing", result.stdout)

    def test_a_bad_value_under_the_tier_alias_is_still_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            card = CLEAN_CARD.replace("persona: senior-developer", "tier: junior")

            result = self.run_validator(card, repo)

            self.assertEqual(result.returncode, 1)
            self.assertIn("[persona] must be one of developer | senior-developer", result.stdout)

    # --- fields the card no longer carries ---------------------------------------------------- #

    def test_allowed_reads_is_reported_obsolete_and_never_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            card = CLEAN_CARD + textwrap.dedent("""\
                allowed_reads:
                  - backend/core/**
                  - backend/gonemodule/**
                """)

            result = self.run_validator(card, repo)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(self.findings(result, "ERROR"), [], result.stdout)
            self.assertIn("[allowed_reads] `allowed_reads` is no longer part of the card and is "
                          "ignored", result.stdout)
            # The removed logic must be gone, not merely quiet: a stale read glob says nothing now.
            self.assertNotIn("backend/gonemodule/** matches nothing", result.stdout)

    def test_adversarial_probes_is_reported_obsolete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            card = CLEAN_CARD + textwrap.dedent("""\
                adversarial_probes:
                  - "replay the same request twice"
                """)

            result = self.run_validator(card, repo)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("[adversarial_probes] `adversarial_probes` is no longer part of the "
                          "card and is ignored", result.stdout)

    def test_a_write_set_no_read_set_covers_is_no_longer_a_finding(self) -> None:
        """The other half of the removed logic: exclusive_writes stands on its own now."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))

            result = self.run_validator(CLEAN_CARD, repo, "--strict")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertNotIn("allowed_reads", result.stdout)

    # --- frozen migration version ------------------------------------------------------------ #

    def test_frozen_migration_ahead_of_the_tree_is_a_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            card = card_with(frozen_values='frozen_values:\n  - "migration version: V190"\n')

            result = self.run_validator(card, repo)

            self.assertEqual(result.returncode, 0)
            self.assertIn("names V190 but the repository's highest is V187", result.stdout)
            self.assertIn("next free version is V188", result.stdout)

    def test_frozen_migration_that_already_exists_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            card = card_with(frozen_values='frozen_values:\n  - "migration version: V187"\n')

            result = self.run_validator(card, repo)

            self.assertEqual(result.returncode, 1)
            self.assertIn("names V187 but V187 already exists", result.stdout)

    def test_exclusive_writes_anchors_the_intended_migration_version(self) -> None:
        """frozen_values may cite the stale plan value while correcting it; the write set decides."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            card = card_with(
                exclusive_writes=textwrap.dedent("""\
                    exclusive_writes:
                      - backend/core/src/main/java/com/acme/core/**
                      - backend/core/src/test/java/com/acme/core/**
                      - backend/app/src/main/resources/db/migration/V188__*.sql
                    """),
                forbidden_paths="forbidden_paths:\n  - backend/app/src/test/**\n",
                frozen_values=('frozen_values:\n'
                               '  - "Migration version is V188. The plan says V190; V187 is the '
                               'current highest."\n'),
            )

            result = self.run_validator(card, repo)

            self.assertEqual(self.findings(result, "ERROR"), [], result.stdout)
            self.assertIn("also names V190, above the V188 this card creates", result.stdout)

    def test_unrelated_v6_label_is_not_a_migration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            card = card_with(
                frozen_values='frozen_values:\n  - "Use the V6 design package label."\n')

            result = self.run_validator(card, repo, "--strict")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertNotIn("migration", result.stdout.lower())

    def test_explicit_migration_wording_checks_all_versions_in_the_value(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            card = card_with(frozen_values=(
                'frozen_values:\n'
                '  - "This database migration is constrained by prior decisions. '
                'The required version is V187."\n'
            ))

            result = self.run_validator(card, repo)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("names V187 but V187 already exists", result.stdout)

    def test_unrelated_v6_label_beside_migration_wording_is_not_a_migration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            card = card_with(frozen_values=(
                'frozen_values:\n'
                '  - "Migration detection remains explicit, but unrelated V6 design/package '
                'label alone is not a migration."\n'
            ))

            result = self.run_validator(card, repo, "--strict")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertNotIn("names V6", result.stdout)

    def test_unrelated_v6_exclusion_does_not_hide_other_migration_versions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            card = card_with(frozen_values=(
                'frozen_values:\n'
                '  - "This migration requires V187, while unrelated V6 design/package label '
                'remains non-migration metadata."\n'
            ))

            result = self.run_validator(card, repo)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("names V187 but V187 already exists", result.stdout)
            self.assertNotIn("names V6", result.stdout)

    # --- parser ------------------------------------------------------------------------------ #

    def test_a_hash_inside_a_quoted_command_is_not_a_comment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            card = card_with(validation=textwrap.dedent("""\
                validation:
                  - "cd backend && ./gradlew :core:test --rerun-tasks --tests 'com.acme.core.Missing#one'   # only if a DTO changed"
                """))

            result = self.run_validator(card, repo)

            self.assertEqual(result.returncode, 1)
            self.assertIn("com.acme.core.Missing", result.stdout)

    # --- nesting ----------------------------------------------------------------------------- #
    #
    # These replace `test_nested_mapping_fails_loudly_rather_than_being_skipped`, which asserted
    # that `review:\n  reviewer:\n    model: opus` exited 2. That was the limitation, not the
    # contract: a card needing a structured block got REJECTED rather than checked, and a validator
    # that blocks legitimate work gets switched off. The half of it worth keeping — that syntax the
    # parser cannot represent fails loudly instead of being skipped — is now pinned by
    # `test_anchors_aliases_and_tags_still_fail_loudly` and its neighbours below.

    def test_nested_mapping_parses_and_every_leaf_still_reaches_the_checks(self) -> None:
        """Grouping `validation` by module must parse — and must not hide a bogus filter.

        This is the check that matters. Parsing nesting is easy; parsing it and then quietly
        handing the checks an empty list would turn the whole validator into theatre.
        """
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            card = card_with(validation=textwrap.dedent("""\
                validation:
                  core:
                    - "cd backend && ./gradlew :core:test --tests 'com.acme.core.tenancy.TenantIsolationTest' --rerun-tasks"
                  app:
                    - "cd backend && ./gradlew :core:test --tests 'com.acme.core.NoSuchTest' --rerun-tasks"
                """))

            result = self.run_validator(card, repo)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("no class named NoSuchTest exists", result.stdout)

    def test_a_nested_mapping_card_with_nothing_wrong_is_clean(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            card = CLEAN_CARD + textwrap.dedent("""\
                review:
                  reviewer:
                    model: opus
                    effort: high
                """)

            result = self.run_validator(card, repo, "--strict")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("no findings", result.stdout)

    def test_list_of_mappings_parses(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            card = CLEAN_CARD + textwrap.dedent("""\
                review:
                  - persona: reviewer
                    because: always
                  - persona: tenancy-rls-validator
                    because: new tenant tables
                """)

            result = self.run_validator(card, repo, "--strict")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("no findings", result.stdout)

    def test_nested_shapes_project_to_their_leaves_without_dropping_any(self) -> None:
        parse_card, as_list = self.import_parser()
        card = parse_card(textwrap.dedent("""\
            validation:
              backend:
                unit:
                  - "gradlew :core:test"
                integration:
                  - "gradlew :app:test"
            review:
              - persona: reviewer
                because: always
            frozen_values:
              - event: fees.payment.recorded
              - *.sql is a glob, not an alias
            gate_risk: [openapi.json, "a, b"]
            limits: {cpu: 2, note: "x, y"}
            """))

        self.assertEqual(card["validation"],
                         {"backend": {"unit": ["gradlew :core:test"],
                                      "integration": ["gradlew :app:test"]}})
        self.assertEqual(card["review"], [{"persona": "reviewer", "because": "always"}])
        self.assertEqual(card["frozen_values"][0], {"event": "fees.payment.recorded"})
        self.assertEqual(card["frozen_values"][1], "*.sql is a glob, not an alias")
        self.assertEqual(card["limits"], {"cpu": "2", "note": "x, y"})
        # A quoted comma inside a flow collection is one item, not two.
        self.assertEqual(card["gate_risk"], ["openapi.json", "a, b"])

        # Every leaf survives the projection the checks consume.
        self.assertEqual(as_list(card["validation"]), ["gradlew :core:test", "gradlew :app:test"])
        self.assertEqual(as_list(card["review"]), ["persona: reviewer", "because: always"])
        self.assertEqual(as_list(card["frozen_values"]),
                         ["event: fees.payment.recorded", "*.sql is a glob, not an alias"])
        self.assertEqual(as_list(card["limits"]), ["cpu: 2", "note: x, y"])

    def test_anchors_aliases_and_tags_still_fail_loudly(self) -> None:
        """The half of the old limitation that must never be relaxed: syntax whose meaning this
        parser cannot reproduce fails, rather than being resolved wrongly or dropped."""
        cases = [
            ("defaults: &base\n  persona: developer\n", "anchors/aliases"),
            ("handoff2: *base\n", "anchors/aliases"),
            ("note: !!str hello\n", "tags"),
            ("weird:\n  ? complex\n  : key\n", "complex mapping keys"),
            ("merge:\n  <<: other\n", "merge keys"),
            ("flow:\n  - [a, [b, c]]\n", "nested flow collections"),
            ("wrapped: [a,\n  b]\n", "multi-line flow sequences"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            for suffix, expected in cases:
                with self.subTest(suffix=suffix):
                    result = self.run_validator(CLEAN_CARD + suffix, repo)

                    self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                    self.assertIn(expected, result.stderr)

    def test_multi_document_still_fails_loudly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))

            result = self.run_validator(CLEAN_CARD + "---\nid: EX-02\n", repo)

            self.assertEqual(result.returncode, 2)
            self.assertIn("multi-document YAML is not supported", result.stderr)

    def test_a_required_field_that_nests_to_nothing_is_reported_not_ignored(self) -> None:
        """A nested block with no scalar leaf must read as empty and fail the required-field
        check. The failure mode this forbids is a `validation:` that parses to a shape the checks
        cannot see and therefore never complain about."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            card = card_with(validation="validation:\n  core:\n    unit: \"\"\n")

            result = self.run_validator(card, repo)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("[validation] required field is present but empty", result.stdout)

    def test_duplicate_key_fails_loudly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))

            result = self.run_validator(CLEAN_CARD + 'id: EX-02\n', repo)

            self.assertEqual(result.returncode, 2)
            self.assertIn("duplicate key `id`", result.stderr)

    def test_block_scalar_and_multiline_quoted_item_round_trip(self) -> None:
        sys.path.insert(0, str(SCRIPT.parent))
        try:
            from validate_card import parse_card  # type: ignore
        finally:
            sys.path.pop(0)
        card = parse_card(textwrap.dedent("""\
            goal: >
              An exact retry cannot
              produce a duplicate.
            instructions: |
              line one
              line two
            frozen_values:
              - "Migration version is V188. The plan text
                 says V190; that assumed 04D landed."
              - bare item   # with a comment
            gate_risk: [openapi.json, test-taxonomy.tsv]
            """))
        self.assertEqual(card["goal"], "An exact retry cannot produce a duplicate.")
        self.assertEqual(card["instructions"], "line one\nline two")
        self.assertEqual(card["frozen_values"][0],
                         "Migration version is V188. The plan text says V190; that assumed "
                         "04D landed.")
        self.assertEqual(card["frozen_values"][1], "bare item")
        self.assertEqual(card["gate_risk"], ["openapi.json", "test-taxonomy.tsv"])

    def test_build_output_is_not_indexed_as_a_source_of_truth(self) -> None:
        """A stale .class under build/ must never satisfy a --tests filter."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            ghost = repo / "backend/app/build/classes/java/test/com/acme/app"
            ghost.mkdir(parents=True)
            (ghost / "GhostTest.java").write_text("package com.acme.app;\n", encoding="utf-8")
            card = card_with(validation=textwrap.dedent("""\
                validation:
                  - "cd backend && ./gradlew :app:test --tests 'com.acme.app.GhostTest' --rerun-tasks"
                """))

            result = self.run_validator(card, repo)

            self.assertEqual(result.returncode, 1)
            self.assertIn("no class named GhostTest exists", result.stdout)

    def test_missing_card_or_repo_exits_two(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            missing = subprocess.run(
                [sys.executable, str(SCRIPT), str(repo / "nope.yaml"), "--repo", str(repo)],
                capture_output=True, text=True)

            self.assertEqual(missing.returncode, 2)
            self.assertIn("not a file", missing.stderr)


if __name__ == "__main__":
    unittest.main()
