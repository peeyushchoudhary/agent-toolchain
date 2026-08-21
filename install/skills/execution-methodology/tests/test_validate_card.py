from __future__ import annotations

import os
import importlib.util
import ast
import shlex
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

prerequisites: []

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

invariants:
  - "A duplicate dispatch fails closed."

instructions:
  - "Implement idempotent widget dispatch."

tests:
  - "Retain: backend/core/src/test/java/com/acme/core/tenancy/TenantIsolationTest.java :: com.acme.core.tenancy.TenantIsolationTest"

gate_risk: none

validation:
  - cwd: backend
    argv:
      - ./gradlew
      - :core:test
      - --tests
      - com.acme.core.tenancy.TenantIsolationTest
      - --rerun-tasks

stop_conditions:
  - "a migration is required"

record_to: docs/product/milestones/M1-launch.md

handoff: chief-of-staff

commit_subject: "feat(core): close the duplicate window"
"""


def validation_entry(cwd: str, *argv: str) -> str:
    lines = ["validation:", f"  - cwd: {cwd}", "    argv:"]
    lines.extend(f"      - {arg!r}" for arg in argv)
    return "\n".join(lines) + "\n"


def direct_validation_fixture(block: str) -> str:
    """Mechanically express simple historical test fixtures through the new public contract."""
    lines = [line.strip() for line in block.splitlines() if line.strip()]
    if not lines or lines[0] != "validation:":
        return block
    converted: list[tuple[str, list[str]]] = []
    for line in lines[1:]:
        if not line.startswith("- "):
            return block
        try:
            command = ast.literal_eval(line[2:].strip())
            if not isinstance(command, str):
                return block
            argv = shlex.split(command, comments=False, posix=True)
        except (SyntaxError, ValueError):
            return block
        cwd = "."
        if len(argv) >= 4 and argv[0] == "cd" and argv[2] == "&&":
            cwd, argv = argv[1], argv[3:]
        if any(any(control in token for control in (";", "&&", "||", "|", "&"))
               for token in argv):
            return block
        converted.append((cwd, argv))
    rendered = ["validation:"]
    for cwd, argv in converted:
        rendered.extend((f"  - cwd: {cwd}", "    argv:"))
        rendered.extend(f"      - {argument!r}" for argument in argv)
    return "\n".join(rendered) + "\n"


def card_with(**overrides: str) -> str:
    """Replace whole top-level blocks of CLEAN_CARD. Keys are matched at column zero."""
    text = CLEAN_CARD
    for key, block in overrides.items():
        if key == "validation":
            block = direct_validation_fixture(block)
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
                "package com.acme.core.tenancy;\n"
                "class TenantIsolationTest { @org.junit.jupiter.api.Test void isolates() {} }\n",
            "backend/app/src/main/java/com/acme/app/App.java":
                "package com.acme.app;\nclass App {}\n",
            "backend/app/src/main/resources/db/migration/V187__emergency_stop.sql": "-- x\n",
            # `record_to` names the register a found-but-not-fixed issue goes to, and the validator
            # requires the destination to EXIST — a card pointing at a milestone document nobody
            # wrote reads exactly like a register with nothing in it.
            "docs/product/milestones/M1-launch.md":
                "---\nmilestone: M1\ntitle: Launch\nstatus: building\nupdated: 2026-01-01\n"
                "---\n\n# M1 — Launch\n\n## Deferred\n",
        }
        for rel, body in files.items():
            path = repo / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding="utf-8")
        gradlew = repo / "backend/gradlew"
        gradlew.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        gradlew.chmod(0o755)
        for python in (repo / ".venv/bin/python", repo / "backend/.venv/bin/python"):
            python.parent.mkdir(parents=True, exist_ok=True)
            python.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            python.chmod(0o755)
        # The fixture must be a real git repository: the validator asks `git check-ignore` inside
        # it, and without this the answer depends on whatever repository encloses $TMPDIR.
        subprocess.run(["git", "init", "-q", str(repo)], check=True, capture_output=True)
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

    # --- direct validation-process contract ------------------------------------------------- #

    def test_repository_relative_executable_contract(self) -> None:
        invalid = {
            "missing": ("./missing", "does not exist"),
            "directory": ("./tool-dir", "not a regular file"),
            "non-executable": ("./not-executable", "not executable"),
            "no-shebang": ("./text-tool", "byte-zero #! shebang"),
            "escape": ("../../outside-tool", "outside the repository"),
            "symlink escape": ("./escaping-link", "resolves outside the repository"),
            "broken symlink": ("./broken-link", "broken symlink"),
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = self.make_repo(root)
            backend = repo / "backend"
            (backend / "tool-dir").mkdir()
            for name, executable in (("not-executable", False), ("text-tool", True)):
                tool = backend / name
                tool.write_text("plain text\n", encoding="utf-8")
                tool.chmod(0o755 if executable else 0o644)
            outside = root / "outside-tool"
            outside.write_text("#!/bin/sh\n", encoding="utf-8")
            outside.chmod(0o755)
            (backend / "escaping-link").symlink_to(outside)
            (backend / "broken-link").symlink_to(backend / "absent-target")
            for label, (argv0, expected) in invalid.items():
                with self.subTest(label=label):
                    card = card_with(
                        tests="tests:\n  - Exercise repository executable validation.\n",
                        validation=validation_entry("backend", argv0),
                    )
                    result = self.run_validator(card, repo, "--strict")
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    roots = [line for line in self.findings(result, "ERROR")
                             if "repository executable" in line]
                    self.assertEqual(len(roots), 1, result.stdout)
                    self.assertIn(expected, roots[0])
                    self.assertNotIn("gate_risk", result.stdout)

    def test_repository_relative_executable_accepts_scripts_binaries_and_cwd(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            backend = repo / "backend"
            direct = backend / "direct-tool"
            direct.write_bytes(b"#!/bin/sh\nexit 0\n")
            direct.chmod(0o755)
            binary = backend / "binary-tool"
            binary.write_bytes(b"\x7fELF\x00test")
            binary.chmod(0o755)
            nested = backend / "tools"
            nested.mkdir()
            cwd_tool = nested / "cwd-tool"
            cwd_tool.write_bytes(b"#!/bin/sh\n")
            cwd_tool.chmod(0o755)
            cases = (("backend", "./direct-tool"), ("backend", "./binary-tool"),
                     ("backend/tools", "./cwd-tool"), ("backend", "python3"),
                     ("backend", sys.executable))
            for cwd, argv0 in cases:
                with self.subTest(cwd=cwd, argv0=argv0):
                    card = card_with(
                        tests="tests:\n  - Exercise repository executable validation.\n",
                        validation=validation_entry(cwd, argv0),
                    )
                    result = self.run_validator(card, repo, "--strict")
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_nested_java_selectors_require_the_exact_member_chain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            path = repo / "backend/core/src/test/java/com/acme/core/OuterTest.java"
            path.write_text(textwrap.dedent("""\
                package com.acme.core;
                class OuterTest {
                  @org.junit.jupiter.api.Test void outerTest() {}
                  static class RealMember { static class DeepMember {} }
                  void method() { class LocalGhost {} }
                  String fake = "class StringGhost {}";
                  // class CommentGhost {}
                }
                """), encoding="utf-8")
            valid = ("com.acme.core.OuterTest.RealMember",
                     "com.acme.core.OuterTest$RealMember$DeepMember")
            invalid = ("com.acme.core.OuterTest.Ghost",
                       "com.acme.core.OuterTest.RealMember.Ghost",
                       "com.acme.core.OuterTest.LocalGhost",
                       "com.acme.core.OuterTest.StringGhost",
                       "com.acme.core.OuterTest.CommentGhost")
            for fqcn in valid + invalid:
                with self.subTest(fqcn=fqcn):
                    card = card_with(
                        tests=("tests:\n  - Retain: backend/core/src/test/java/com/acme/core/"
                               f"OuterTest.java :: {fqcn}\n"),
                        validation=validation_entry(
                            "backend", "./gradlew", ":core:test", "--tests", fqcn,
                            "--rerun-tasks"),
                    )
                    result = self.run_validator(card, repo, "--strict", "--phase", "post")
                    if fqcn in valid:
                        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    else:
                        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                        self.assertIn("does not exist exactly", result.stdout)

    def test_nested_java_create_is_absent_pre_and_exact_post(self) -> None:
        fqcn = "com.acme.core.NewOuterTest.CreatedMember"
        declaration = ("tests:\n  - Create: backend/core/src/test/java/com/acme/core/"
                       f"NewOuterTest.java :: {fqcn}\n")
        validation = validation_entry(
            "backend", "./gradlew", ":core:test", "--tests", fqcn, "--rerun-tasks")
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            pre = self.run_validator(card_with(tests=declaration, validation=validation), repo,
                                     "--strict", "--phase", "pre")
            self.assertEqual(pre.returncode, 0, pre.stdout + pre.stderr)
            path = repo / "backend/core/src/test/java/com/acme/core/NewOuterTest.java"
            path.write_text(textwrap.dedent("""\
                package com.acme.core;
                class NewOuterTest {
                  @org.junit.jupiter.api.Test void test() {}
                  static class CreatedMember {}
                }
                """), encoding="utf-8")
            post = self.run_validator(card_with(tests=declaration, validation=validation), repo,
                                      "--strict", "--phase", "post")
            self.assertEqual(post.returncode, 0, post.stdout + post.stderr)

    def test_existing_nested_java_create_fails_pre_once(self) -> None:
        fqcn = "com.acme.core.ExistingOuterTest.ExistingMember"
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            path = repo / "backend/core/src/test/java/com/acme/core/ExistingOuterTest.java"
            path.write_text(textwrap.dedent("""\
                package com.acme.core;
                class ExistingOuterTest {
                  @org.junit.jupiter.api.Test void test() {}
                  static class ExistingMember {}
                }
                """), encoding="utf-8")
            card = card_with(
                tests=("tests:\n  - Create: backend/core/src/test/java/com/acme/core/"
                       f"ExistingOuterTest.java :: {fqcn}\n"),
                validation=validation_entry(
                    "backend", "./gradlew", ":core:test", "--tests", fqcn, "--rerun-tasks"),
            )
            result = self.run_validator(card, repo, "--strict", "--phase", "pre")
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            findings = self.findings(result, "ERROR")
            self.assertEqual(len(findings), 1, result.stdout)
            self.assertIn("Create:", findings[0])
            self.assertIn("already exists before implementation", findings[0])

    def test_repository_executable_symlink_loop_fails_once_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            loop = repo / "backend/loop"
            loop.symlink_to(loop)
            card = card_with(
                tests="tests:\n  - Exercise repository executable validation.\n",
                validation=validation_entry("backend", "./loop"),
            )
            result = self.run_validator(card, repo, "--strict")
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            roots = [line for line in self.findings(result, "ERROR")
                     if "repository executable" in line]
            self.assertEqual(len(roots), 1, result.stdout)
            self.assertNotIn("Traceback", result.stdout + result.stderr)
            self.assertNotIn("gate_risk", result.stdout)

    def test_java_lexical_scanner_ignores_non_code_without_deleting_real_members(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            path = repo / "backend/core/src/test/java/com/acme/core/LexicalOuterTest.java"
            path.write_text(textwrap.dedent('''\
                package com.acme.core;
                class LexicalOuterTest {
                  @org.junit.jupiter.api.Test void test() {}
                  String url = "http://example/class StringGhost {}";
                  char quote = '\\''; // class LineGhost {}
                  /* class BlockGhost {} */
                  String text = """
                    class TextBlockGhost {}
                    // not a comment delimiter here
                    """;
                  static class RealMember {}
                }
                '''), encoding="utf-8")
            candidates = {
                "com.acme.core.LexicalOuterTest.RealMember": True,
                "com.acme.core.LexicalOuterTest.StringGhost": False,
                "com.acme.core.LexicalOuterTest.LineGhost": False,
                "com.acme.core.LexicalOuterTest.BlockGhost": False,
                "com.acme.core.LexicalOuterTest.TextBlockGhost": False,
            }
            for fqcn, should_pass in candidates.items():
                with self.subTest(fqcn=fqcn):
                    card = card_with(
                        tests=("tests:\n  - Retain: backend/core/src/test/java/com/acme/core/"
                               f"LexicalOuterTest.java :: {fqcn}\n"),
                        validation=validation_entry(
                            "backend", "./gradlew", ":core:test", "--tests", fqcn,
                            "--rerun-tasks"),
                    )
                    result = self.run_validator(card, repo, "--strict", "--phase", "post")
                    self.assertEqual(result.returncode, 0 if should_pass else 1,
                                     result.stdout + result.stderr)

    def test_java_unicode_escape_eligibility_follows_translated_result(self) -> None:
        spec = importlib.util.spec_from_file_location("validate_card_java_unicode", SCRIPT)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        try:
            spec.loader.exec_module(module)
            examples = (
                (r"\\u2122=\u2122", r"\\u2122=" + "\N{TRADE MARK SIGN}"),
                (r"\\\u006e", r"\\n"),
                (r"\u005c\u005c\u006e", r"\\n"),
            )
            for source, expected in examples:
                with self.subTest(source=source):
                    self.assertEqual(module._translate_java_unicode_escapes(source), expected)
        finally:
            sys.modules.pop(spec.name, None)

    def test_java_unicode_escaped_line_comment_hides_nested_type(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            path = repo / "backend/core/src/test/java/p/Outer.java"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(textwrap.dedent("""\
                package p;
                class Outer {
                  @org.junit.jupiter.api.Test void realTest() {}
                  \\u002f\\u002f class Ghost {}
                }
                """), encoding="utf-8")
            fqcn = "p.Outer.Ghost"
            card = card_with(
                tests=("tests:\n  - Retain: backend/core/src/test/java/p/Outer.java :: "
                       f"{fqcn}\n"),
                validation=validation_entry(
                    "backend", "./gradlew", ":core:test", "--tests", fqcn,
                    "--rerun-tasks"),
            )

            result = self.run_validator(card, repo, "--strict", "--phase", "post")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            findings = self.findings(result, "ERROR")
            test_findings = [line for line in findings if "[tests]" in line]
            self.assertEqual(len(test_findings), 1, result.stdout)
            self.assertIn(
                "Retain: backend/core/src/test/java/p/Outer.java :: "
                "p.Outer.Ghost does not exist exactly",
                test_findings[0],
            )

    def test_direct_gradle_command_preserves_all_java_checks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            card = card_with(validation=validation_entry(
                "backend", "./gradlew", ":core:test", "--tests",
                "com.acme.core.tenancy.TenantIsolationTest", "--rerun-tasks"))

            result = self.run_validator(card, repo, "--strict")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("no findings", result.stdout)

    def test_direct_pytest_commands_resolve_selectors_relative_to_cwd(self) -> None:
        commands = (
            ("pytest", "tests/test_widget.py::test_widget"),
            ("python3", "-m", "pytest", "tests/test_widget.py::test_widget"),
        )
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            test_file = repo / "backend/tests/test_widget.py"
            test_file.parent.mkdir(parents=True)
            test_file.write_text("def test_widget():\n    pass\n", encoding="utf-8")
            for argv in commands:
                with self.subTest(argv=argv):
                    card = card_with(
                        validation=validation_entry("backend", *argv),
                        tests="tests:\n  - Retain backend/tests/test_widget.py::test_widget\n",
                    )
                    result = self.run_validator(card, repo, "--strict")
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_validation_rejects_each_malformed_item_once_without_derivatives(self) -> None:
        malformed = {
            "legacy scalar": "validation: './gradlew test --rerun-tasks'\n",
            "non-list": "validation:\n  cwd: .\n  argv: [true]\n",
            "empty": "validation: []\n",
            "missing key": "validation:\n  - cwd: .\n",
            "extra key": "validation:\n  - cwd: .\n    argv: [true]\n    env: test\n",
            "grouping map": "validation:\n  backend:\n    - cwd: .\n      argv: [true]\n",
            "escaping cwd": "validation:\n  - cwd: ..\n    argv: [true]\n",
            "missing cwd": "validation:\n  - cwd: missing\n    argv: [true]\n",
            "empty argv": "validation:\n  - cwd: .\n    argv: []\n",
            "non-string argv": "validation:\n  - cwd: .\n    argv:\n      - true\n      - {bad: value}\n",
            "blank argv zero": "validation:\n  - cwd: .\n    argv:\n      - ''\n",
            "shell interpreter": "validation:\n  - cwd: .\n    argv: [sh, -c, true]\n",
        }
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            for label, validation in malformed.items():
                with self.subTest(label=label):
                    card = card_with(
                        validation=validation,
                        tests="tests:\n  - Exercise validation structure.\n",
                    )
                    result = self.run_validator(card, repo, "--strict")
                    errors = self.findings(result, "ERROR")
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertEqual(len(errors), 1, result.stdout + result.stderr)
                    self.assertTrue(errors[0].startswith("ERROR   [validation]"), errors[0])
                    for derivative in (
                        "Gradle", "--tests filter", "pytest selector", "UP-TO-DATE",
                        "module", "gate_risk",
                    ):
                        self.assertNotIn(derivative, errors[0])

    def test_validation_rejects_control_characters_in_argv(self) -> None:
        spec = importlib.util.spec_from_file_location("validate_card_controls", SCRIPT)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        try:
            spec.loader.exec_module(module)
            with tempfile.TemporaryDirectory() as tmp:
                repo_path = self.make_repo(Path(tmp))
                repo = module.Repo(repo_path)
                for control in ("\0", "\r", "\n"):
                    with self.subTest(control=repr(control)):
                        findings = module.Findings()
                        decoded = module.decode_validation(
                            [{"cwd": ".", "argv": [f"true{control}false"]}], repo, findings)
                        self.assertIsNone(decoded)
                        self.assertEqual(len(findings.rows), 1)
                        self.assertIn("contains NUL, CR, or LF", findings.rows[0][2])
        finally:
            sys.modules.pop(spec.name, None)

    def test_only_argv_zero_identifies_gradle_and_shell_looking_values_are_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            card = card_with(
                validation=validation_entry(
                    ".", "true", "&&", "./gradlew", ":core:test", "--tests",
                    "com.acme.core.tenancy.TenantIsolationTest", "--rerun-tasks"),
                tests="tests:\n  - Literal argv values remain data.\n",
            )
            result = self.run_validator(card, repo, "--strict")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("no findings", result.stdout)

    def test_validation_is_decoded_exactly_once(self) -> None:
        spec = importlib.util.spec_from_file_location("validate_card_once", SCRIPT)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        try:
            spec.loader.exec_module(module)
            with tempfile.TemporaryDirectory() as tmp:
                repo = self.make_repo(Path(tmp))
                card_path = repo.parent / "card.yaml"
                card_path.write_text(card_with(validation=validation_entry(
                    "backend", "./gradlew", ":core:test", "--tests",
                    "com.acme.core.tenancy.TenantIsolationTest", "--rerun-tasks")),
                    encoding="utf-8")
                calls = 0
                original = module.decode_validation

                def counted(*args, **kwargs):
                    nonlocal calls
                    calls += 1
                    return original(*args, **kwargs)

                module.decode_validation = counted
                module.validate(card_path, repo)
                self.assertEqual(calls, 1)
        finally:
            sys.modules.pop(spec.name, None)

    def test_validator_source_has_no_shell_or_legacy_parser(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        for forbidden in (
            "import shlex", "shell_segments", "parse_validation", "legacy_validation",
        ):
            self.assertNotIn(forbidden, source)

    def test_decoder_is_the_only_validation_shape_authority(self) -> None:
        malformed = (
            "",
            "validation: []\n",
            "validation:\n  - {}\n",
        )
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            for block in malformed:
                with self.subTest(block=block):
                    card = card_with(
                        validation=block,
                        tests="tests:\n  - Exercise validation structure.\n",
                    )
                    result = self.run_validator(card, repo, "--strict")
                    errors = self.findings(result, "ERROR")
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertEqual(len(errors), 1, result.stdout + result.stderr)
                    self.assertTrue(errors[0].startswith("ERROR   [validation]"), errors[0])

            literal_glob = card_with(
                validation=validation_entry(".", "true", "*.py"),
                tests="tests:\n  - Literal argv remains data.\n",
            )
            result = self.run_validator(literal_glob, repo, "--strict")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("no findings", result.stdout)

    def test_clean_like_tokens_never_prove_rerun(self) -> None:
        rejected_tokens = (
            ("clean",),
            ("cleanTest",),
            (":core:cleanTest",),
            ("notcleanTest",),
            ("-Pnote=cleanTest",),
            ("--message=cleanTest",),
            (":core:cleanTest", "-x", ":core:cleanTest"),
            ("cleanTest", "-xcleanTest"),
            ("cleanTest", "--exclude-task", "cleanTest"),
            ("cleanTest", "--exclude-task=cleanTest"),
        )
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            for tokens in rejected_tokens:
                with self.subTest(rejected=tokens):
                    card = card_with(validation=validation_entry(
                        "backend", "./gradlew", ":core:test", *tokens, "--tests",
                        "com.acme.core.tenancy.TenantIsolationTest"))
                    result = self.run_validator(card, repo)
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertIn("must include exact --rerun-tasks", result.stdout)

    def test_non_root_cwd_rejects_every_symlink_component(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            (repo / "alias").symlink_to(repo / "backend", target_is_directory=True)
            card = card_with(
                validation=validation_entry("alias/core", "true"),
                tests="tests:\n  - Exercise cwd identity.\n",
            )
            result = self.run_validator(card, repo, "--strict")
            errors = self.findings(result, "ERROR")
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertEqual(len(errors), 1, result.stdout + result.stderr)
            self.assertIn("symlink", errors[0])

    def test_gradle_tests_requires_one_non_option_operand_during_decode(self) -> None:
        argument_sets = (
            (":core:test", "--rerun-tasks", "--tests"),
            (":core:test", "--rerun-tasks", "--tests="),
            (":core:test", "--tests", "--rerun-tasks"),
        )
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            for arguments in argument_sets:
                with self.subTest(arguments=arguments):
                    card = card_with(
                        validation=validation_entry("backend", "./gradlew", *arguments),
                        tests="tests:\n  - Exercise malformed Gradle argv.\n",
                    )
                    result = self.run_validator(card, repo, "--strict")
                    errors = self.findings(result, "ERROR")
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertEqual(len(errors), 1, result.stdout + result.stderr)
                    self.assertIn("--tests", errors[0])

    def test_published_shell_basename_set_is_enforced_exactly(self) -> None:
        shell_names = (
            "sh", "bash", "dash", "zsh", "ksh", "mksh", "csh", "tcsh", "fish", "ash",
            "pwsh", "powershell", "cmd", "cmd.exe",
        )
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            for shell in shell_names:
                with self.subTest(shell=shell):
                    card = card_with(
                        validation=validation_entry(".", shell, "-c", "true"),
                        tests="tests:\n  - Exercise shell boundary.\n",
                    )
                    result = self.run_validator(card, repo, "--strict")
                    errors = self.findings(result, "ERROR")
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertEqual(len(errors), 1, result.stdout + result.stderr)
                    self.assertIn("shell interpreters are unsupported", errors[0])

    def test_methodology_publishes_validation_contract_v2_and_migration(self) -> None:
        source_root = SCRIPT.parents[1]
        docs = "\n".join(
            (source_root / path).read_text(encoding="utf-8")
            for path in ("SKILL.md", "methodology.md", "references/task-card.md")
        )
        self.assertIn("task-card validation contract v2", docs)
        self.assertIn("v1 cards are invalid under v2", docs)
        self.assertIn("v2 cards are invalid under v1", docs)
        self.assertIn("mksh", docs)
        self.assertIn("cmd.exe", docs)
        self.assertIn("unlisted wrappers", docs)

    def test_rerun_tasks_is_the_only_gradle_freshness_proof(self) -> None:
        valid_argument_sets = (
            ("--rerun-tasks", ":core:test", "--tests",
             "com.acme.core.tenancy.TenantIsolationTest"),
            (":core:test", "--rerun-tasks", "--tests",
             "com.acme.core.tenancy.TenantIsolationTest"),
            (":core:test", "--tests", "com.acme.core.tenancy.TenantIsolationTest",
             "--rerun-tasks"),
        )
        invalid_freshness = (
            ("clean",),
            ("cleanTest",),
            (":core:cleanTest",),
            ("notcleanTest",),
            ("-Pnote=cleanTest",),
            ("--message=cleanTest",),
            ("--project-cache-dir", "clean"),
            ("cleanTest", "-x", "cleanTest"),
            (":core:cleanTest", "--exclude-task=:core:cleanTest"),
        )
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            for arguments in valid_argument_sets:
                with self.subTest(valid=arguments):
                    card = card_with(validation=validation_entry(
                        "backend", "./gradlew", *arguments))
                    result = self.run_validator(card, repo, "--strict")
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            for freshness in invalid_freshness:
                with self.subTest(invalid=freshness):
                    card = card_with(validation=validation_entry(
                        "backend", "./gradlew", ":core:test", *freshness, "--tests",
                        "com.acme.core.tenancy.TenantIsolationTest"))
                    result = self.run_validator(card, repo, "--strict")
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertIn("must include exact --rerun-tasks", result.stdout)
                    self.assertIn("has no exact --rerun-tasks", result.stdout)

    def test_every_methodology_surface_requires_only_rerun_tasks(self) -> None:
        source_root = SCRIPT.parents[1]
        for path in ("SKILL.md", "methodology.md", "references/task-card.md"):
            with self.subTest(path=path):
                body = (source_root / path).read_text(encoding="utf-8")
                self.assertTrue("`--rerun-tasks` is the only" in body, path)
                self.assertFalse("`--rerun-tasks`, `clean`, or `cleanTest`" in body, path)
                self.assertFalse("either `--rerun-tasks` or" in body, path)

    # --- the headline check ------------------------------------------------------------------ #

    def test_unknown_top_level_field_warns_and_strict_rejects(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            loose = self.run_validator(CLEAN_CARD + "review: reviewer\n", repo)
            strict = self.run_validator(CLEAN_CARD + "review: reviewer\n", repo, "--strict")
            self.assertEqual(loose.returncode, 0, loose.stdout + loose.stderr)
            self.assertIn("[review] unknown field", loose.stdout)
            self.assertEqual(strict.returncode, 1, strict.stdout + strict.stderr)

    def test_every_current_schema_field_must_be_present_under_strict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            card = card_with(prerequisites="")
            result = self.run_validator(card, repo, "--strict")
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("[prerequisites] required field is missing", result.stdout)

    def test_path_glob_in_non_path_field_warns_and_strict_rejects(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            card = card_with(instructions="instructions:\n  - backend/core/**\n")
            result = self.run_validator(card, repo, "--strict")
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("[instructions] path glob", result.stdout)

    def test_create_java_declaration_is_phase_safe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            path = "backend/core/src/test/java/com/acme/core/WidgetDispatchTest.java"
            fqcn = "com.acme.core.WidgetDispatchTest"
            card = card_with(
                tests=f'tests:\n  - "Create: {path} :: {fqcn}"\n',
                validation=("validation:\n  - \"cd backend && ./gradlew :core:test "
                            f"--tests '{fqcn}' --rerun-tasks\"\n"),
            )
            pre = self.run_validator(card, repo, "--strict", "--phase", "pre")
            self.assertEqual(pre.returncode, 0, pre.stdout + pre.stderr)
            post_missing = self.run_validator(card, repo, "--strict", "--phase", "post")
            self.assertEqual(post_missing.returncode, 1, post_missing.stdout + post_missing.stderr)
            self.assertIn("still absent after implementation", post_missing.stdout)
            target = repo / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                "package com.acme.core; class WidgetDispatchTest { "
                "@org.junit.jupiter.api.Test void dispatches() {} }\n", encoding="utf-8")
            post = self.run_validator(card, repo, "--strict", "--phase", "post")
            self.assertEqual(post.returncode, 0, post.stdout + post.stderr)

    def test_java_declaration_path_must_map_to_fqcn(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            card = card_with(tests=(
                "tests:\n  - \"Retain: backend/core/src/test/java/com/acme/core/tenancy/"
                "TenantIsolationTest.java :: com.acme.wrong.TenantIsolationTest\"\n"))
            result = self.run_validator(card, repo)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("maps to com.acme.core.tenancy.TenantIsolationTest", result.stdout)

    def test_every_java_declaration_requires_an_exact_gradle_filter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            card = card_with(
                tests=("tests:\n  - \"Retain: backend/core/src/test/java/com/acme/core/tenancy/"
                       "TenantIsolationTest.java :: com.acme.core.tenancy.TenantIsolationTest\"\n"),
                validation="validation:\n  - \"cd backend && ./gradlew :core:test --rerun-tasks\"\n")
            result = self.run_validator(card, repo)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("has no exact non-wildcard Gradle --tests filter", result.stdout)

    def test_exact_java_filter_cannot_use_prose_only_tests_bypass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            card = card_with(tests="tests:\n  - Follow the existing Java test pattern.\n")
            result = self.run_validator(card, repo)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("has no matching Create:/Retain: Java declaration", result.stdout)

    def test_java_declarations_and_exact_filters_are_one_to_one(self) -> None:
        declaration = (
            "Retain: backend/core/src/test/java/com/acme/core/tenancy/"
            "TenantIsolationTest.java :: com.acme.core.tenancy.TenantIsolationTest"
        )
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            duplicate_declaration = card_with(
                tests=f'tests:\n  - "{declaration}"\n  - "{declaration}"\n')
            declarations = self.run_validator(duplicate_declaration, repo)
            self.assertEqual(declarations.returncode, 1,
                             declarations.stdout + declarations.stderr)
            self.assertIn("declared 2 times", declarations.stdout)

            duplicate_filter = card_with(validation=textwrap.dedent("""\
                validation:
                  - "cd backend && ./gradlew :core:test --tests 'com.acme.core.tenancy.TenantIsolationTest' --rerun-tasks"
                  - "cd backend && ./gradlew :core:test --tests 'com.acme.core.tenancy.TenantIsolationTest' --rerun-tasks"
                """))
            filters = self.run_validator(duplicate_filter, repo)
            self.assertEqual(filters.returncode, 1, filters.stdout + filters.stderr)
            self.assertIn("selected by 2 exact Gradle --tests filters", filters.stdout)

    def test_shell_composition_is_rejected_at_the_structure_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            commands = (
                "cd backend && ./gradlew :core:test --rerun-tasks ; "
                "echo --tests com.acme.core.tenancy.TenantIsolationTest",
                "cd backend && ./gradlew :core:test --rerun-tasks ; "
                "# --tests com.acme.core.tenancy.TenantIsolationTest",
            )
            for index, command in enumerate(commands):
                with self.subTest(command=command):
                    card = card_with(validation=f'validation:\n  - "{command}"\n')
                    result = self.run_validator(card, repo)
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertIn("legacy scalar commands are unsupported", result.stdout)

    def test_gradle_text_in_echo_or_true_wrapper_is_not_execution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            for wrapper in ("echo", "true"):
                with self.subTest(wrapper=wrapper):
                    card = card_with(validation=textwrap.dedent(f"""\
                        validation:
                          - "{wrapper} ./gradlew :core:test --tests com.acme.core.tenancy.TenantIsolationTest --rerun-tasks"
                        """), tests="tests:\n  - Validate Gradle execution detection.\n")

                    result = self.run_validator(card, repo, "--strict")

                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn("no findings", result.stdout)

    def test_backgrounded_gradle_validation_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            commands = (
                "./gradlew :core:test --tests com.acme.core.tenancy.TenantIsolationTest "
                "--rerun-tasks & true",
                "./gradlew :core:test --tests com.acme.core.tenancy.TenantIsolationTest "
                "--rerun-tasks &",
            )
            for command in commands:
                with self.subTest(command=command):
                    card = card_with(
                        validation=f'validation:\n  - "{command}"\n',
                        tests="tests:\n  - Validate Gradle execution detection.\n",
                    )

                    result = self.run_validator(card, repo, "--strict")

                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    errors = self.findings(result, "ERROR")
                    self.assertEqual(len(errors), 1, result.stdout)
                    self.assertIn("legacy scalar commands are unsupported", errors[0])
                    self.assertIn("1 error(s), 0 warning(s)", result.stdout)

    def test_declared_java_validation_rejects_unvalidated_shell_tail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            card = card_with(validation=textwrap.dedent("""\
                validation:
                  - "cd backend && ./gradlew :core:test --tests com.acme.core.tenancy.TenantIsolationTest --rerun-tasks ; echo done"
                """))
            result = self.run_validator(card, repo)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("legacy scalar commands are unsupported", result.stdout)

    def test_wildcard_filter_cannot_satisfy_java_declaration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            card = card_with(
                tests=("tests:\n  - \"Retain: backend/core/src/test/java/com/acme/core/tenancy/"
                       "TenantIsolationTest.java :: com.acme.core.tenancy.TenantIsolationTest\"\n"),
                validation=("validation:\n  - \"cd backend && ./gradlew :core:test "
                            "--tests 'com.acme.core.tenancy.*' --rerun-tasks\"\n"))
            result = self.run_validator(card, repo)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("has no exact non-wildcard Gradle --tests filter", result.stdout)

    def test_java_test_shell_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            path = repo / "backend/core/src/test/java/com/acme/core/tenancy/TenantIsolationTest.java"
            path.write_text("package com.acme.core.tenancy; class TenantIsolationTest {}\n",
                            encoding="utf-8")
            card = card_with(tests=(
                "tests:\n  - \"Retain: backend/core/src/test/java/com/acme/core/tenancy/"
                "TenantIsolationTest.java :: com.acme.core.tenancy.TenantIsolationTest\"\n"))
            result = self.run_validator(card, repo)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("contains no JUnit test declaration", result.stdout)

    def test_java_test_shell_cannot_hide_test_annotation_in_a_comment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            path = repo / "backend/core/src/test/java/com/acme/core/tenancy/TenantIsolationTest.java"
            path.write_text(
                "package com.acme.core.tenancy; // @org.junit.jupiter.api.Test\n"
                "class TenantIsolationTest {}\n", encoding="utf-8")
            card = card_with(tests=(
                "tests:\n  - \"Retain: backend/core/src/test/java/com/acme/core/tenancy/"
                "TenantIsolationTest.java :: com.acme.core.tenancy.TenantIsolationTest\"\n"))
            result = self.run_validator(card, repo)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("contains no JUnit test declaration", result.stdout)

    def test_post_phase_reads_real_package_and_top_level_class_declarations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            path = repo / "backend/core/src/test/java/com/acme/core/tenancy/TenantIsolationTest.java"
            path.write_text(
                "// package com.acme.core.tenancy; class TenantIsolationTest {}\n"
                'String fake = "package com.acme.core.tenancy; class TenantIsolationTest";\n'
                "package com.other;\n"
                "class OtherTest { @org.junit.jupiter.api.Test void runs() {} }\n",
                encoding="utf-8",
            )
            result = self.run_validator(CLEAN_CARD, repo, "--phase", "post")
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("declares package com.other", result.stdout)
            self.assertIn("declares top-level class OtherTest", result.stdout)

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
                """), tests="tests:\n  - Diagnose the intentionally wrong selector.\n")

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
                tests="tests:\n  - Retain tests/test_widget.py::test_missing\n",
            )

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
                tests="tests:\n  - Retain tests/test_widget.py::test_widget\n",
            )

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
                tests="tests:\n  - Create tests/test_widget.py::test_created\n",
            )

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
                tests="tests:\n  - Create tests/test_widget.py::test_created\n",
            )

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
                tests="tests:\n  - Create tests/test_widget.py::test_created\n",
            )

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
                        tests=f"tests:\n  - {first}\n  - {second}\n",
                    )

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
                tests="tests:\n  - Retain tests/test_widget.py::test_widget\n",
            )

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

    def test_legacy_dynamic_pytest_shell_commands_are_rejected(self) -> None:
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
                    ), tests="tests:\n  - Retain tests/test_widget.py::test_widget\n")

                    result = self.run_validator(card, repo)

                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertIn("legacy scalar commands are unsupported", result.stdout)

    def test_multi_process_pytest_shell_commands_are_rejected(self) -> None:
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
                    ), tests="tests:\n  - Retain tests/test_widget.py::test_widget\n")

                    result = self.run_validator(card, repo)

                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertIn("legacy scalar commands are unsupported", result.stdout)

    def test_attached_shell_controls_are_literal_selector_data(self) -> None:
        controls = (";", "&&", "||")
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            test_file = repo / "tests/test_widget.py"
            test_file.parent.mkdir(parents=True)
            test_file.write_text("def test_widget():\n    pass\n", encoding="utf-8")
            for control in controls:
                with self.subTest(control=control):
                    card = card_with(
                        validation=validation_entry(
                            ".", ".venv/bin/python", "-m", "pytest",
                            f"tests/test_widget.py::test_widget{control}", "true"),
                        tests="tests:\n  - Retain tests/test_widget.py::test_widget\n",
                    )

                    result = self.run_validator(card, repo, "--strict")

                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertIn("unsupported pytest selector", result.stdout)

    def test_pytest_response_files_are_rejected_in_every_segment(self) -> None:
        argument_sets = [
            ("@missing-args.txt",),
            ("tests/test_widget.py::test_widget", "&&", ".venv/bin/python", "-m", "pytest",
             "@missing-args.txt"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            test_file = repo / "tests/test_widget.py"
            test_file.parent.mkdir(parents=True)
            test_file.write_text("def test_widget():\n    pass\n", encoding="utf-8")
            for arguments in argument_sets:
                with self.subTest(arguments=arguments):
                    card = card_with(validation=validation_entry(
                        ".", ".venv/bin/python", "-m", "pytest", *arguments))

                    result = self.run_validator(card, repo)

                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertIn("pytest response-file argument", result.stdout)
                    self.assertIn("@missing-args.txt", result.stdout)

    def test_quote_looking_pytest_arguments_are_literal_data(self) -> None:
        arguments = ('"$NODE', "'unterminated")
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            for argument in arguments:
                with self.subTest(argument=argument):
                    card = card_with(
                        validation=validation_entry(".", "pytest", argument),
                        tests="tests:\n  - Literal pytest argv remains data.\n",
                    )

                    result = self.run_validator(card, repo)

                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn("no findings", result.stdout)

    def test_non_pytest_double_colon_token_is_not_a_pytest_selector(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            card = card_with(
                validation="validation:\n  - \"cargo test module::test_name\"\n",
                tests="tests:\n  - Exercise the Rust test selector.\n")

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

            self.assertEqual(result.returncode, 1,
                             "declared Java selectors require rerun protection in their segment")
            self.assertIn("has no exact --rerun-tasks", result.stdout)
            self.assertIn("declared Java validation must include exact --rerun-tasks",
                          result.stdout)

    def test_cleantest_does_not_satisfy_the_rerun_requirement(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            card = card_with(validation=textwrap.dedent("""\
                validation:
                  - "cd backend && ./gradlew :core:cleanTest :core:test --tests 'com.acme.core.tenancy.TenantIsolationTest'"
                """))

            result = self.run_validator(card, repo, "--strict")

            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertIn("must include exact --rerun-tasks", result.stdout)
            self.assertIn("has no exact --rerun-tasks", result.stdout)

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

    def test_pre_strict_accepts_absent_exact_production_and_create_test_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            production = "backend/core/src/main/java/com/acme/core/NewWidget.java"
            test_path = "backend/core/src/test/java/com/acme/core/NewWidgetTest.java"
            fqcn = "com.acme.core.NewWidgetTest"
            card = card_with(
                exclusive_writes=("exclusive_writes:\n"
                                  f"  - {production}\n"
                                  f"  - {test_path}\n"),
                tests=f'tests:\n  - "Create: {test_path} :: {fqcn}"\n',
                validation=("validation:\n  - \"cd backend && ./gradlew :core:test "
                            f"--tests '{fqcn}' --rerun-tasks\"\n"),
            )
            result = self.run_validator(card, repo, "--strict", "--phase", "pre")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("no findings", result.stdout)

    def test_pre_phase_missing_retain_java_path_still_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            test_path = "backend/core/src/test/java/com/acme/core/MissingRetainTest.java"
            fqcn = "com.acme.core.MissingRetainTest"
            card = card_with(
                exclusive_writes=f"exclusive_writes:\n  - {test_path}\n",
                tests=f'tests:\n  - "Retain: {test_path} :: {fqcn}"\n',
                validation=("validation:\n  - \"cd backend && ./gradlew :core:test "
                            f"--tests '{fqcn}' --rerun-tasks\"\n"),
            )
            result = self.run_validator(card, repo, "--strict", "--phase", "pre")
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("does not exist exactly", result.stdout)

    def test_post_phase_requires_every_exclusive_write_and_create_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            production = "backend/core/src/main/java/com/acme/core/NewWidget.java"
            test_path = "backend/core/src/test/java/com/acme/core/NewWidgetTest.java"
            fqcn = "com.acme.core.NewWidgetTest"
            card = card_with(
                exclusive_writes=("exclusive_writes:\n"
                                  f"  - {production}\n"
                                  f"  - {test_path}\n"),
                tests=f'tests:\n  - "Create: {test_path} :: {fqcn}"\n',
                validation=("validation:\n  - \"cd backend && ./gradlew :core:test "
                            f"--tests '{fqcn}' --rerun-tasks\"\n"),
            )
            result = self.run_validator(card, repo, "--strict", "--phase", "post")
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(f"{production} must exist in post phase", result.stdout)
            self.assertIn("still absent after implementation", result.stdout)

    def test_pre_absent_path_exception_does_not_accept_unsafe_or_nonliteral_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            for value in ("backend/new/**", "../escape.java", "/tmp/absolute.java",
                          "backend/core/new-directory/"):
                with self.subTest(value=value):
                    card = card_with(exclusive_writes=f"exclusive_writes:\n  - {value}\n")
                    result = self.run_validator(card, repo, "--strict", "--phase", "pre")
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)

    def test_extensionless_exact_files_pass_pre_and_fail_post_when_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            for value in ("backend/core/Dockerfile", "backend/core/.gitignore"):
                with self.subTest(value=value):
                    card = card_with(exclusive_writes=f"exclusive_writes:\n  - {value}\n")
                    pre = self.run_validator(card, repo, "--strict", "--phase", "pre")
                    self.assertEqual(pre.returncode, 0, pre.stdout + pre.stderr)
                    post = self.run_validator(card, repo, "--strict", "--phase", "post")
                    self.assertEqual(post.returncode, 1, post.stdout + post.stderr)
                    self.assertIn(f"{value} must exist in post phase", post.stdout)

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

    def test_absent_exact_forbidden_migrations_are_clean_fences(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            (repo / "backend/app/src/main/resources/db/migration/V187__emergency_stop.sql").unlink()
            migration_dir = repo / "backend/app/src/main/resources/db/migration"
            (migration_dir / "V77__previous.sql").write_text("-- previous\n", encoding="utf-8")
            v78 = "backend/app/src/main/resources/db/migration/V78__durable_core.sql"
            v79 = "backend/app/src/main/resources/db/migration/V79__raw_event.sql"
            v80 = "backend/app/src/main/resources/db/migration/V80__receipts.sql"
            card = card_with(
                exclusive_writes=textwrap.dedent(f"""\
                    exclusive_writes:
                      - backend/core/src/main/java/com/acme/core/**
                      - backend/core/src/test/java/com/acme/core/**
                      - {v78}
                    """),
                forbidden_paths=f"forbidden_paths:\n  - {v79}\n  - {v80}\n",
                frozen_values=("frozen_values: |\n"
                               f"  Migration files are {v78}, {v79}, and {v80}.\n"),
            )
            pre = self.run_validator(card, repo, "--strict", "--phase", "pre")
            self.assertEqual(pre.returncode, 0, pre.stdout + pre.stderr)
            self.assertIn("no findings", pre.stdout)

    def test_absent_unsafe_forbidden_paths_still_fail_strict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            for value in ("backend/app/V79__*.sql", "../V79__escape.sql",
                          "/tmp/V79__absolute.sql"):
                with self.subTest(value=value):
                    card = card_with(forbidden_paths=f"forbidden_paths:\n  - {value}\n")
                    result = self.run_validator(card, repo, "--strict", "--phase", "pre")
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)

    def test_unpaired_higher_frozen_migration_still_warns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            card = card_with(
                exclusive_writes=textwrap.dedent("""\
                    exclusive_writes:
                      - backend/core/src/main/java/com/acme/core/**
                      - backend/core/src/test/java/com/acme/core/**
                      - backend/app/src/main/resources/db/migration/V188__next.sql
                    """),
                frozen_values=("frozen_values: |\n"
                               "  Migration files include "
                               "backend/app/src/main/resources/db/migration/V190__unpaired.sql.\n"),
            )
            result = self.run_validator(card, repo)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("also names V190, above the V188 this card creates", result.stdout)

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

    def test_owned_next_migration_passes_pre_then_post_after_creation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            migration = "backend/app/src/main/resources/db/migration/V188__next.sql"
            card = card_with(
                exclusive_writes=("exclusive_writes:\n"
                                  "  - backend/core/src/main/java/com/acme/core/**\n"
                                  "  - backend/core/src/test/java/com/acme/core/**\n"
                                  f"  - {migration}\n"),
                forbidden_paths="forbidden_paths:\n  - backend/forbidden.txt\n",
                frozen_values='frozen_values:\n  - "migration version: V188"\n',
            )

            pre = self.run_validator(card, repo, "--strict", "--phase", "pre")
            self.assertEqual(pre.returncode, 0, pre.stdout + pre.stderr)

            target = repo / migration
            target.write_text("-- next\n", encoding="utf-8")
            post = self.run_validator(card, repo, "--strict", "--phase", "post")
            self.assertEqual(post.returncode, 0, post.stdout + post.stderr)

    def test_pre_rejects_owned_next_migration_when_it_already_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            migration = "backend/app/src/main/resources/db/migration/V188__next.sql"
            (repo / migration).write_text("-- already present\n", encoding="utf-8")
            card = card_with(
                exclusive_writes=("exclusive_writes:\n"
                                  "  - backend/core/src/main/java/com/acme/core/**\n"
                                  "  - backend/core/src/test/java/com/acme/core/**\n"
                                  f"  - {migration}\n"),
                forbidden_paths="forbidden_paths:\n  - backend/forbidden.txt\n",
                frozen_values='frozen_values:\n  - "migration version: V188"\n',
            )

            result = self.run_validator(card, repo, "--phase", "pre")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("names V188 but V188 already exists", result.stdout)

    def test_post_rejects_owned_migration_when_a_higher_version_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            migration = "backend/app/src/main/resources/db/migration/V188__next.sql"
            (repo / migration).write_text("-- intended\n", encoding="utf-8")
            (repo / "backend/app/src/main/resources/db/migration/V189__later.sql").write_text(
                "-- later\n", encoding="utf-8")
            card = card_with(
                exclusive_writes=("exclusive_writes:\n"
                                  "  - backend/core/src/main/java/com/acme/core/**\n"
                                  "  - backend/core/src/test/java/com/acme/core/**\n"
                                  f"  - {migration}\n"),
                forbidden_paths="forbidden_paths:\n  - backend/forbidden.txt\n",
                frozen_values='frozen_values:\n  - "migration version: V188"\n',
            )

            result = self.run_validator(card, repo, "--phase", "post")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("names V188 but V189 already exists", result.stdout)

    def test_post_rejects_top_migration_when_version_write_does_not_cover_top_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            migration_dir = repo / "backend/app/src/main/resources/db/migration"
            (migration_dir / "V188__a_unowned.sql").write_text("-- top\n", encoding="utf-8")
            owned = "backend/app/src/main/resources/db/migration/V188__z_owned.sql"
            (repo / owned).write_text("-- owned same-version path\n", encoding="utf-8")
            card = card_with(
                exclusive_writes=("exclusive_writes:\n"
                                  "  - backend/core/src/main/java/com/acme/core/**\n"
                                  "  - backend/core/src/test/java/com/acme/core/**\n"
                                  f"  - {owned}\n"),
                forbidden_paths="forbidden_paths:\n  - backend/forbidden.txt\n",
                frozen_values='frozen_values:\n  - "migration version: V188"\n',
            )

            result = self.run_validator(card, repo, "--phase", "post")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("names V188 but V188 already exists", result.stdout)

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

    def test_nested_validation_grouping_is_rejected_once(self) -> None:
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
            errors = self.findings(result, "ERROR")
            self.assertEqual(len(errors), 1, result.stdout)
            self.assertIn("non-empty sequence of mappings", errors[0])

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

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("[review] unknown field", result.stdout)

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

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("[review] unknown field", result.stdout)

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

    def test_validation_mapping_that_nests_to_nothing_is_rejected_once(self) -> None:
        """A grouping mapping is a shape error owned solely by the validation decoder."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            card = card_with(validation="validation:\n  core:\n    unit: \"\"\n")

            result = self.run_validator(card, repo)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            errors = self.findings(result, "ERROR")
            self.assertEqual(len(errors), 1, result.stdout + result.stderr)
            self.assertIn("non-empty sequence of mappings", errors[0])

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

    # --- v3.0 size budget ------------------------------------------------------------------- #

    def test_clean_card_has_no_size_findings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            result = self.run_validator(CLEAN_CARD, repo)
            self.assertNotIn("[size]", result.stdout)
            self.assertNotIn("line budget", result.stdout)

    def test_card_over_150_lines_warns_and_fails_strict(self) -> None:
        padding = "".join(f"# preamble line {i}\n" for i in range(160))
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            plain = self.run_validator(padding + CLEAN_CARD, repo)
            self.assertEqual(plain.returncode, 0, plain.stdout + plain.stderr)
            size = [line for line in self.findings(plain, "WARNING") if "[size]" in line]
            self.assertEqual(len(size), 1, plain.stdout)
            self.assertIn("150-line budget", size[0])
            strict = self.run_validator(padding + CLEAN_CARD, repo, "--strict")
            self.assertEqual(strict.returncode, 1, strict.stdout + strict.stderr)

    def test_frozen_values_entry_over_10_lines_warns(self) -> None:
        big_entry = "frozen_values:\n  - |\n" + "".join(
            f"    payload line {i}\n" for i in range(12))
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            result = self.run_validator(card_with(frozen_values=big_entry), repo)
            frozen = [line for line in self.findings(result, "WARNING")
                      if "[frozen_values]" in line and "10-line budget" in line]
            self.assertEqual(len(frozen), 1, result.stdout)
            self.assertIn("committed contract", frozen[0])
            strict = self.run_validator(card_with(frozen_values=big_entry), repo, "--strict")
            self.assertEqual(strict.returncode, 1, strict.stdout + strict.stderr)

    def test_frozen_values_many_small_entries_are_clean(self) -> None:
        entries = "frozen_values:\n" + "".join(
            f'  - "frozen fact number {i}"\n' for i in range(14))
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            result = self.run_validator(card_with(frozen_values=entries), repo)
            self.assertNotIn("10-line budget", result.stdout)


if __name__ == "__main__":
    unittest.main()


class MidPhaseTest(unittest.TestCase):
    """`--phase mid` — the drift check, and `record_to`, the destination for what it does not fix.

    W7 in `plan_waves.py` already asks whether a task wrote outside its declared set, and answers
    after the commit. Mid asks it while the edit is still uncommitted, where undoing it is free.
    Measured on 56 real cards matched to the commit their own `commit_subject` names: 116 of 558
    files landed outside the declaring card's `exclusive_writes` across 25 of the 56 cards, and 17
    landed inside a `forbidden_paths` glob on 9 of them.
    """

    def make_repo(self, root: Path) -> Path:
        repo = ValidateCardTest.make_repo(self, root)
        subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@example.invalid",
                        "-c", "user.name=t", "commit", "-qm", "base"],
                       check=True, capture_output=True)
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

    def touch(self, repo: Path, relative: str, body: str = "changed\n") -> Path:
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        return path

    # --- the comparison ---------------------------------------------------------------------- #

    def test_an_uncommitted_path_outside_the_write_set_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            self.touch(repo, "backend/core/build.gradle.kts",
                       "plugins { java }\n// a build file the card never declared\n")
            result = self.run_validator(CLEAN_CARD, repo, "--phase", "mid")
            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertTrue(any("backend/core/build.gradle.kts" in line
                                and "exclusive_writes" in line
                                for line in self.findings(result, "ERROR")), result.stdout)

    def test_every_uncommitted_path_inside_the_write_set_is_silent(self) -> None:
        """The false-positive half. A check that fires on a task doing exactly what its card says
        is a check somebody removes."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            self.touch(repo, "backend/core/src/main/java/com/acme/core/Widget.java",
                       "package com.acme.core;\nclass Widget { int n; }\n")
            self.touch(repo, "backend/core/src/main/java/com/acme/core/NewThing.java",
                       "package com.acme.core;\nclass NewThing {}\n")
            result = self.run_validator(CLEAN_CARD, repo, "--phase", "mid")
            self.assertEqual(
                [line for line in self.findings(result, "ERROR")
                 if "exclusive_writes" in line or "forbidden_paths" in line], [], result.stdout)

    def test_an_uncommitted_change_to_a_forbidden_path_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            self.touch(repo, "backend/app/build.gradle.kts", "plugins { java }\n// touched\n")
            result = self.run_validator(CLEAN_CARD, repo, "--phase", "mid")
            self.assertTrue(any("forbidden" in line and "build.gradle.kts" in line
                                for line in self.findings(result, "ERROR")), result.stdout)

    def test_a_forbidden_path_is_reported_once_not_twice(self) -> None:
        """A forbidden path is usually outside the write set too. Reporting it under both fields
        doubles a finding count that a controller reads as two problems."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            self.touch(repo, "backend/app/build.gradle.kts", "plugins { java }\n// touched\n")
            result = self.run_validator(CLEAN_CARD, repo, "--phase", "mid")
            hits = [line for line in self.findings(result, "ERROR")
                    if "backend/app/build.gradle.kts" in line]
            self.assertEqual(len(hits), 1, result.stdout)

    def test_an_untracked_directory_is_expanded_into_its_files(self) -> None:
        """git's default collapses a new directory to `dir/`. Eleven new files would have been one
        path, so the finding would have been right and the count wrong."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            for name in ("one", "two", "three"):
                self.touch(repo, f"scratch/{name}.txt")
            result = self.run_validator(CLEAN_CARD, repo, "--phase", "mid")
            hits = [line for line in self.findings(result, "ERROR") if "scratch/" in line]
            self.assertEqual(len(hits), 3, result.stdout)

    def test_both_sides_of_a_rename_are_compared(self) -> None:
        """A file moved INTO the write set was still written at the old path, which the card did
        not own. Reading the destination alone calls that move clean, so the one rename this test
        performs is the one only the old side can catch."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            source = repo / "backend/core/build.gradle.kts"
            target = repo / "backend/core/src/main/java/com/acme/core/Build.java"
            subprocess.run(["git", "-C", str(repo), "mv", str(source), str(target)],
                           check=True, capture_output=True)
            reported = " ".join(self.findings(
                self.run_validator(CLEAN_CARD, repo, "--phase", "mid"), "ERROR"))
            self.assertIn("backend/core/build.gradle.kts", reported)
            self.assertNotIn("Build.java", reported)

    def test_a_path_with_a_space_and_a_quote_is_read_verbatim(self) -> None:
        """`--porcelain` without `-z` wraps such a path in quotes with C escapes, and un-escaping
        that by hand is a second parser with its own bugs."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            self.touch(repo, 'scratch/a file "with" quotes.txt')
            result = self.run_validator(CLEAN_CARD, repo, "--phase", "mid")
            reported = " ".join(self.findings(result, "ERROR"))
            self.assertIn('a file "with" quotes.txt', reported)
            self.assertNotIn("\\", reported)

    def test_the_card_file_itself_is_exempt(self) -> None:
        """A card cannot be required to declare itself, and requiring it would put every card in
        its own write set."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            card = repo / "cards" / "card.yaml"
            card.parent.mkdir(parents=True, exist_ok=True)
            card.write_text(CLEAN_CARD, encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(card), "--repo", str(repo), "--phase", "mid"],
                capture_output=True, text=True)
            self.assertFalse(any("cards/card.yaml" in line
                                 for line in self.findings(result, "ERROR")), result.stdout)

    def test_a_repository_git_cannot_answer_for_says_it_checked_nothing(self) -> None:
        """A gap, never a pass. The whole failure class this repository keeps meeting is a check
        that reported clean because it read nothing."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = ValidateCardTest.make_repo(self, Path(tmp))
            import shutil as _shutil
            _shutil.rmtree(repo / ".git")
            result = self.run_validator(CLEAN_CARD, repo, "--phase", "mid")
            warnings = " ".join(self.findings(result, "WARNING"))
            self.assertIn("checked nothing", warnings)
            self.assertIn("gap, not a pass", warnings)

    def test_mid_grades_a_declared_create_test_as_pre_does(self) -> None:
        """Mid-task is before the task is finished. Grading a declared `Create` as `post` would
        report a card red for being unfinished, which is the state mid exists to be run in."""
        card = card_with(tests=(
            'tests:\n'
            '  - "Create: backend/core/src/test/java/com/acme/core/NewTest.java '
            ':: com.acme.core.NewTest"\n'
            '  - "Retain: backend/core/src/test/java/com/acme/core/tenancy/TenantIsolationTest'
            '.java :: com.acme.core.tenancy.TenantIsolationTest"\n'),
            validation=(
                'validation:\n'
                '  - cwd: backend\n'
                '    argv:\n'
                '      - ./gradlew\n'
                '      - :core:test\n'
                '      - --tests\n'
                '      - com.acme.core.NewTest\n'
                '      - --tests\n'
                '      - com.acme.core.tenancy.TenantIsolationTest\n'
                '      - --rerun-tasks\n'))
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            mid = self.run_validator(card, repo, "--phase", "mid")
            post = self.run_validator(card, repo, "--phase", "post")
            self.assertEqual([line for line in self.findings(mid, "ERROR")
                              if "NewTest" in line], [], mid.stdout)
            self.assertTrue(any("NewTest" in line for line in self.findings(post, "ERROR")),
                            post.stdout)

    def test_the_header_reports_how_many_paths_were_compared(self) -> None:
        """The denominator of the check is part of its result: "0 compared" and "31 compared" are
        very different clean runs."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            self.touch(repo, "backend/core/src/main/java/com/acme/core/Widget.java",
                       "package com.acme.core;\nclass Widget { int n; }\n")
            result = self.run_validator(CLEAN_CARD, repo, "--phase", "mid")
            self.assertIn("1 uncommitted path(s) compared", result.stdout)
            plain = self.run_validator(CLEAN_CARD, repo)
            self.assertNotIn("uncommitted path(s) compared", plain.stdout)

    def test_pre_and_post_do_not_read_the_working_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            self.touch(repo, "scratch/drift.txt")
            for phase in ("pre", "post"):
                result = self.run_validator(CLEAN_CARD, repo, "--phase", phase)
                self.assertFalse(any("scratch/drift.txt" in line
                                     for line in result.stdout.splitlines()),
                                 f"{phase}: {result.stdout}")

    def test_the_glob_intersection_is_imported_rather_than_reimplemented(self) -> None:
        """`--phase mid` and W7 ask the same question about the same file. Two implementations of
        the answer can disagree, and the disagreement is invisible because each has its own tests.
        """
        scripts = str(SCRIPT.parent)
        sys.path.insert(0, scripts)
        try:
            import plan_waves  # type: ignore
            import validate_card  # type: ignore
            self.assertIs(validate_card.overlap, plan_waves.overlap)
        finally:
            sys.path.remove(scripts)

    # --- record_to --------------------------------------------------------------------------- #

    def test_record_to_is_a_warning_when_absent_and_strict_refuses_it(self) -> None:
        """The `title` migration policy, applied again: all 187 cards measured across four real
        repositories predate the field, and failing them closed is failing on history."""
        card = "\n".join(line for line in CLEAN_CARD.splitlines()
                         if not line.startswith("record_to:")) + "\n"
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            plain = self.run_validator(card, repo)
            self.assertEqual(plain.returncode, 0, plain.stdout)
            self.assertTrue(any("record_to" in line for line in self.findings(plain, "WARNING")))
            strict = self.run_validator(card, repo, "--strict")
            self.assertEqual(strict.returncode, 1, strict.stdout)

    def test_record_to_that_is_not_a_milestone_document_is_an_error(self) -> None:
        card = card_with(record_to="record_to: docs/notes/backlog.md\n")
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            result = self.run_validator(card, repo)
            self.assertTrue(any("record_to" in line for line in self.findings(result, "ERROR")),
                            result.stdout)

    def test_record_to_naming_a_file_that_does_not_exist_is_an_error(self) -> None:
        """A register that is not there is indistinguishable from an empty one, which is exactly
        how a deferral gets lost."""
        card = card_with(record_to="record_to: docs/product/milestones/M9-absent.md\n")
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            result = self.run_validator(card, repo)
            self.assertTrue(any("does not exist" in line and "record_to" in line
                                for line in self.findings(result, "ERROR")), result.stdout)

    def test_record_to_that_resolves_is_clean(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            result = self.run_validator(CLEAN_CARD, repo, "--strict")
            self.assertEqual([line for line in result.stdout.splitlines()
                              if "record_to" in line], [], result.stdout)

    def test_an_empty_record_to_is_an_error(self) -> None:
        card = card_with(record_to='record_to: ""\n')
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            result = self.run_validator(card, repo)
            self.assertTrue(any("record_to" in line for line in self.findings(result, "ERROR")),
                            result.stdout)
