from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "verify_junit.py"
START_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "start_junit_run.py"


def suite(name: str, classes: list[str], *, failures: int = 0, errors: int = 0,
          skipped: int = 0) -> str:
    cases = []
    for index, fqcn in enumerate(classes):
        child = ""
        if index < failures:
            child = '<failure message="failed" />'
        elif index < failures + errors:
            child = '<error message="errored" />'
        elif index < failures + errors + skipped:
            child = "<skipped />"
        cases.append(f'<testcase name="test{index}" classname="{fqcn}">{child}</testcase>')
    return (f'<testsuite name="{name}" tests="{len(classes)}" failures="{failures}" '
            f'errors="{errors}" skipped="{skipped}">' + "".join(cases) + "</testsuite>")


class VerifyJunitTest(unittest.TestCase):
    def start_run(self, receipt: Path, results: Path) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(START_SCRIPT), "--results", str(results),
             "--output", str(receipt)],
            capture_output=True, text=True,
        )

    def run_verifier(self, results: Path, output: Path, *extra: str,
                     start_receipt: Path | None = None) -> subprocess.CompletedProcess:
        if start_receipt is None:
            start_receipt = Path(str(output) + ".start.json")
            started = self.start_run(start_receipt, results)
            self.assertEqual(started.returncode, 0, started.stdout + started.stderr)
            boundary = json.loads(start_receipt.read_text(encoding="utf-8"))["started_at_unix_ns"]
            # Existing fixtures write XML before calling this helper. Retimestamp them after the
            # newly-created boundary to model the test task creating them; stale-result tests pass
            # an explicit receipt and therefore bypass this fixture-only adaptation.
            fresh = max(time.time_ns(), boundary + 1)
            for xml in results.glob("*.xml") if results.is_dir() else ():
                if xml.stat().st_size:
                    xml.write_text(xml.read_text(encoding="utf-8") + "\n", encoding="utf-8")
                os.utime(xml, ns=(fresh, fresh))
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--results", str(results),
             "--expect", "com.acme.OneTest=1", "--start-receipt", str(start_receipt),
             "--output", str(output), *extra],
            capture_output=True, text=True,
        )

    def test_writes_bound_json_evidence_for_clean_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            results = root / "test-results"
            results.mkdir()
            (results / "TEST-one.xml").write_text(
                suite("com.acme.OneTest", ["com.acme.OneTest", "com.acme.TwoTest"]),
                encoding="utf-8")
            output = root / "evidence.json"
            result = self.run_verifier(results, output, "--expect", "com.acme.TwoTest=1")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["result_directory"], str(results.resolve()))
            self.assertEqual(payload["result_file_count"], 1)
            self.assertEqual(payload["distinct_classes"], ["com.acme.OneTest", "com.acme.TwoTest"])
            self.assertEqual(payload["tests"], 2)
            self.assertEqual(payload["failures"], 0)
            self.assertEqual(payload["errors"], 0)
            self.assertEqual(payload["skipped"], 0)
            self.assertEqual(payload["expected_class_counts"],
                             {"com.acme.OneTest": 1, "com.acme.TwoTest": 1})
            self.assertEqual(payload["observed_class_counts"],
                             {"com.acme.OneTest": 1, "com.acme.TwoTest": 1})
            self.assertEqual(payload["start_receipt"],
                             str((root / "evidence.json.start.json").resolve()))
            self.assertRegex(payload["run_nonce"], r"^[0-9a-f]{64}$")
            self.assertRegex(payload["start_receipt_sha256"], r"^[0-9a-f]{64}$")
            self.assertRegex(payload["verified_at_utc"], r"^\d{4}-\d\d-\d\dT.*Z$")

    def test_pre_existing_valid_xml_is_rejected_even_when_counts_and_class_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            results = root / "results"
            results.mkdir()
            xml = results / "TEST-one.xml"
            xml.write_text(suite("one", ["com.acme.OneTest"]), encoding="utf-8")
            start = root / "start.json"
            self.assertEqual(self.start_run(start, results).returncode, 0)
            result = self.run_verifier(results, root / "evidence.json", start_receipt=start)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("identical to XML present before run start", result.stderr)

    def test_deliberate_local_writer_can_rewrite_stale_xml_after_boundary(self) -> None:
        """Trust-boundary limitation: timestamp/hash evidence is not tamper-resistant."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            results = root / "results"
            results.mkdir()
            xml = results / "TEST-one.xml"
            xml.write_text(suite("one", ["com.acme.OneTest"]), encoding="utf-8")
            start = root / "start.json"
            self.assertEqual(self.start_run(start, results).returncode, 0)
            # A deliberate local writer controlling results can change bytes after the boundary.
            xml.write_text(xml.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            result = self.run_verifier(results, root / "evidence.json", start_receipt=start)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_post_boundary_cache_restore_is_accepted_receipt_limitation(self) -> None:
        """A plausible cache restore after the boundary is not detected by receipt evidence."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            results = root / "results"
            results.mkdir()
            xml = results / "TEST-one.xml"
            xml.write_text(suite("old-cache", ["com.acme.OneTest"]), encoding="utf-8")
            start = root / "start.json"
            self.assertEqual(self.start_run(start, results).returncode, 0)
            # Model the runner restoring different, valid cached XML after the start boundary.
            xml.write_text(suite("restored-cache", ["com.acme.OneTest"]), encoding="utf-8")
            result = self.run_verifier(results, root / "evidence.json", start_receipt=start)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_xml_with_same_or_older_mtime_than_start_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for delta in (0, -1):
                with self.subTest(delta=delta):
                    results = root / f"results-{delta}"
                    results.mkdir()
                    start = root / f"start-{delta}.json"
                    self.assertEqual(self.start_run(start, results).returncode, 0)
                    boundary = json.loads(start.read_text(encoding="utf-8"))["started_at_unix_ns"]
                    xml = results / "TEST-one.xml"
                    xml.write_text(suite("one", ["com.acme.OneTest"]), encoding="utf-8")
                    os.utime(xml, ns=(boundary + delta, boundary + delta))
                    result = self.run_verifier(
                        results, root / f"evidence-{delta}.json", start_receipt=start)
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertIn("mtime is not after run start", result.stderr)

    def test_start_receipt_is_single_use(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            results = root / "results"
            results.mkdir()
            start = root / "start.json"
            self.assertEqual(self.start_run(start, results).returncode, 0)
            (results / "TEST-one.xml").write_text(
                suite("one", ["com.acme.OneTest"]), encoding="utf-8")
            first = self.run_verifier(results, root / "first.json", start_receipt=start)
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            second = self.run_verifier(results, root / "second.json", start_receipt=start)
            self.assertEqual(second.returncode, 2, second.stdout + second.stderr)
            self.assertIn("already consumed", second.stderr)

    def test_failed_verification_consumes_receipt_before_xml_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            results = root / "results"
            results.mkdir()
            xml = results / "TEST-one.xml"
            xml.write_text(suite("one", ["com.acme.OneTest"]), encoding="utf-8")
            start = root / "start.json"
            self.assertEqual(self.start_run(start, results).returncode, 0)
            failed = self.run_verifier(results, root / "failed.json", start_receipt=start)
            self.assertEqual(failed.returncode, 1, failed.stdout + failed.stderr)
            self.assertTrue(Path(str(start) + ".consumed").is_file())

            xml.write_text(suite("one-new", ["com.acme.OneTest"]) + "\n", encoding="utf-8")
            retried = self.run_verifier(results, root / "retry.json", start_receipt=start)
            self.assertEqual(retried.returncode, 2, retried.stdout + retried.stderr)
            self.assertIn("already consumed", retried.stderr)

    def test_rejects_missing_zero_byte_and_unparseable_xml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for body, expected in ((None, "no XML result files"), ("", "zero-byte"),
                                   ("not xml", "unparseable")):
                with self.subTest(expected=expected):
                    results = root / expected
                    results.mkdir()
                    if body is not None:
                        (results / "TEST-one.xml").write_text(body, encoding="utf-8")
                    result = self.run_verifier(results, root / f"{expected}.json")
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertIn(expected, result.stderr)

    def test_rejects_zero_tests_missing_class_and_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cases = (
                (suite("empty", []), "zero tests"),
                (suite("other", ["com.acme.OtherTest"]),
                 "expected class com.acme.OneTest expected exactly 1 testcase(s), observed 0"),
                (suite("one", ["com.acme.OneTest"], failures=1), "failures=1"),
                (suite("one", ["com.acme.OneTest"], errors=1), "errors=1"),
            )
            for index, (body, expected) in enumerate(cases):
                with self.subTest(expected=expected):
                    results = root / str(index)
                    results.mkdir()
                    (results / "TEST.xml").write_text(body, encoding="utf-8")
                    result = self.run_verifier(results, root / f"{index}.json")
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertIn(expected, result.stderr)

    def test_rejects_all_skipped_expected_class_with_consistent_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            results = root / "results"
            results.mkdir()
            (results / "TEST-one.xml").write_text(
                suite("one", ["com.acme.OneTest"], skipped=1), encoding="utf-8")

            result = self.run_verifier(results, root / "evidence.json")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("JUnit results contain skipped tests: skipped=1", result.stderr)

    def test_rejects_skipped_unexpected_class_when_expected_class_passed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            results = root / "results"
            results.mkdir()
            (results / "TEST-one.xml").write_text(
                suite("one", ["com.acme.OneTest", "com.acme.UnexpectedTest"], skipped=1),
                encoding="utf-8")

            result = self.run_verifier(results, root / "evidence.json")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("JUnit results contain skipped tests: skipped=1", result.stderr)

    def test_skipped_count_mismatch_precedes_nonzero_skip_rejection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            results = root / "results"
            results.mkdir()
            body = suite("one", ["com.acme.OneTest"], skipped=1).replace(
                'skipped="1"', 'skipped="2"')
            (results / "TEST-one.xml").write_text(body, encoding="utf-8")

            result = self.run_verifier(results, root / "evidence.json")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("count inconsistency", result.stderr)
            self.assertNotIn("JUnit results contain skipped tests", result.stderr)

    def test_expect_parser_rejects_bad_duplicate_and_nonpositive_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            results = root / "results"
            results.mkdir()
            (results / "a.xml").write_text(suite("one", ["com.acme.OneTest"]), encoding="utf-8")
            for index, extra in enumerate((
                ("--expect", "not-an-expectation"),
                ("--expect", "com.acme.TwoTest=0"),
                ("--expect", "com.acme.TwoTest=-1"),
                ("--expect", "com.acme.OneTest=1"),
            )):
                with self.subTest(extra=extra):
                    result = self.run_verifier(results, root / f"bad-{index}.json", *extra)
                    self.assertEqual(result.returncode, 2, result.stdout + result.stderr)

    def test_obsolete_minimum_and_require_class_cli_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            results = root / "results"
            results.mkdir()
            (results / "a.xml").write_text(suite("one", ["com.acme.OneTest"]), encoding="utf-8")
            result = self.run_verifier(
                results, root / "obsolete.json", "--require-class", "com.acme.OneTest",
                "--minimum-tests", "1")
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("unrecognized arguments", result.stderr)

    def test_expected_class_count_is_exact_not_a_minimum(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            results = root / "results"
            results.mkdir()
            (results / "a.xml").write_text(
                suite("one", ["com.acme.OneTest", "com.acme.OneTest"]), encoding="utf-8")
            result = self.run_verifier(results, root / "count.json")
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("expected exactly 1 testcase(s), observed 2", result.stderr)

    def test_rejects_duplicate_suite_identity_and_count_inconsistency(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            duplicate = root / "duplicate"
            duplicate.mkdir()
            for name in ("a.xml", "b.xml"):
                (duplicate / name).write_text(
                    suite("same", ["com.acme.OneTest"]), encoding="utf-8")
            dup = self.run_verifier(duplicate, root / "dup.json")
            self.assertEqual(dup.returncode, 1, dup.stdout + dup.stderr)
            self.assertIn("duplicate suite identity", dup.stderr)

            inconsistent = root / "inconsistent"
            inconsistent.mkdir()
            body = suite("one", ["com.acme.OneTest"]).replace('tests="1"', 'tests="2"')
            (inconsistent / "a.xml").write_text(body, encoding="utf-8")
            bad = self.run_verifier(inconsistent, root / "bad.json")
            self.assertEqual(bad.returncode, 1, bad.stdout + bad.stderr)
            self.assertIn("count inconsistency", bad.stderr)

            aggregate = root / "aggregate"
            aggregate.mkdir()
            wrapped = ('<testsuites tests="2" failures="0" errors="0" skipped="0">'
                       + suite("one", ["com.acme.OneTest"]) + "</testsuites>")
            (aggregate / "a.xml").write_text(wrapped, encoding="utf-8")
            aggregate_bad = self.run_verifier(aggregate, root / "aggregate.json")
            self.assertEqual(aggregate_bad.returncode, 1,
                             aggregate_bad.stdout + aggregate_bad.stderr)
            self.assertIn("aggregate count inconsistency", aggregate_bad.stderr)

    def test_refuses_existing_output_and_output_inside_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            results = root / "results"
            results.mkdir()
            (results / "a.xml").write_text(suite("one", ["com.acme.OneTest"]), encoding="utf-8")
            existing = root / "evidence.json"
            existing.write_text("stale", encoding="utf-8")
            stale = self.run_verifier(results, existing)
            self.assertEqual(stale.returncode, 2, stale.stdout + stale.stderr)
            self.assertIn("already exists", stale.stderr)
            inside = self.run_verifier(results, results / "evidence.json")
            self.assertEqual(inside.returncode, 2, inside.stdout + inside.stderr)
            self.assertIn("outside the result directory", inside.stderr)


if __name__ == "__main__":
    unittest.main()
