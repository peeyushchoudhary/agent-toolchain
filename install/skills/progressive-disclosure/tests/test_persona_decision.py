from __future__ import annotations

import importlib.util
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


if __name__ == "__main__":
    unittest.main()
