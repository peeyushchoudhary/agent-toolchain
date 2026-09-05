from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path


SKILL = Path(__file__).resolve().parents[1]
PERSONAS = SKILL.parent / "agent-personas"
GATE_SANDBOX = SKILL.parent / "gate-sandbox"
TARGET_REL = Path("docs/agents/execution/methodology.md")
OVERLAY_REL = Path("docs/agents/execution/overlay.md")
RUNTIME_REL = Path("docs/agents/execution/runtime.json")
SCHEMA = SKILL / "scripts/runtime-status.schema.json"
EXPECTED_COMMAND_ENTRYPOINTS = {
    "execution-methodology/scripts/check_review_budget.py",
    "execution-methodology/scripts/milestone_seal.py",
    "execution-methodology/scripts/plan_waves.py",
    "execution-methodology/scripts/spec_check.py",
    "execution-methodology/scripts/start_junit_run.py",
    "execution-methodology/scripts/trace_check.py",
    "execution-methodology/scripts/validate_card.py",
    "execution-methodology/scripts/verify_junit.py",
    "execution-methodology/scripts/weekly_review.py",
}
EXPECTED_DIRECT_HELPERS = {
    "execution-methodology/scripts/ratio_meter.py",
}


class RuntimeStatusTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.bundle = self.root / "skills"
        shutil.copytree(SKILL, self.bundle / "execution-methodology")
        shutil.copytree(PERSONAS, self.bundle / "agent-personas")
        shutil.copytree(GATE_SANDBOX, self.bundle / "gate-sandbox")
        self.script = self.bundle / "execution-methodology/scripts/sync_methodology.py"
        self.repo = self.root / "project"
        (self.repo / "docs/agents").mkdir(parents=True)
        (self.repo / "docs/agents/README.md").write_text(
            "# Route\n\n[methodology](execution/methodology.md)\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_owner(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(self.script), "--repo", str(self.repo), *args],
                              capture_output=True, text=True)

    def repair_approved(self, authorization: dict) -> subprocess.CompletedProcess:
        return self.run_owner("--repair-approved",
                              json.dumps(authorization, separators=(",", ":")))

    def render(self) -> None:
        result = self.run_owner()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def status(self) -> tuple[subprocess.CompletedProcess, dict]:
        result = self.run_owner("--status-json")
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            self.fail(f"status stdout was not exactly JSON: {exc}\n{result.stdout}{result.stderr}")
        self.assertEqual(result.stdout.count("\n"), 1)
        return result, payload

    def import_owner(self):
        spec = importlib.util.spec_from_file_location("copied_sync_methodology", self.script)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module

    def test_current_is_ready_and_identity_is_exact(self) -> None:
        self.render()
        result, payload = self.status()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(payload["state"], "current")
        self.assertTrue(payload["ready"])
        self.assertEqual(payload["approved"], payload["installed"])
        self.assertTrue(payload["dependencies"])
        self.assertTrue(all(row["status"] == "current" for row in payload["dependencies"]))
        self.assertEqual(payload["repair_candidates"], [])

    def test_importable_runtime_status_matches_cli(self) -> None:
        self.render()
        sys.path.insert(0, str(self.script.parent))
        try:
            spec = importlib.util.spec_from_file_location("copied_sync_methodology", self.script)
            module = importlib.util.module_from_spec(spec)
            assert spec.loader is not None
            spec.loader.exec_module(module)
            imported = module.runtime_status(self.repo)
        finally:
            sys.path.pop(0)
            sys.modules.pop("spec_check", None)
        _, cli = self.status()
        self.assertEqual(imported, cli)

    def test_repairable_only_for_generated_output_damage(self) -> None:
        self.render()
        target = self.repo / TARGET_REL
        target.write_text(target.read_text(encoding="utf-8") + "\nhand edit\n", encoding="utf-8")
        result, payload = self.status()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(payload["state"], "repairable")
        self.assertEqual(payload["repair_candidates"], [
            {"action": "render_approved", "paths": [TARGET_REL.as_posix()]}
        ])

    def test_repair_approved_repairs_only_the_frozen_identity(self) -> None:
        self.render()
        target = self.repo / TARGET_REL
        target.write_text(target.read_text(encoding="utf-8") + "\nhand edit\n", encoding="utf-8")
        _, status = self.status()
        inventory = self.repo / RUNTIME_REL
        inventory_before = inventory.read_bytes()

        authorization = {"identity": status["approved"],
                         "overlay_expected_sha256": status["overlay"]["expected_sha256"]}
        repaired = self.repair_approved(authorization)

        self.assertEqual(repaired.returncode, 0, repaired.stdout + repaired.stderr)
        self.assertIn("repaired approved runtime", repaired.stdout)
        self.assertEqual(inventory.read_bytes(), inventory_before)
        _, current = self.status()
        self.assertEqual(current["state"], "current")
        self.assertEqual(current["approved"], status["approved"])

    def test_repair_refuses_coherent_overlay_inventory_change_after_planning(self) -> None:
        overlay = self.repo / OVERLAY_REL
        overlay.parent.mkdir(parents=True, exist_ok=True)
        overlay.write_text("first approved overlay\n", encoding="utf-8")
        self.render()
        target = self.repo / TARGET_REL
        target.write_text(target.read_text(encoding="utf-8") + "\nhand edit\n", encoding="utf-8")
        _, planned = self.status()
        authorization = {"identity": planned["approved"],
                         "overlay_expected_sha256": planned["overlay"]["expected_sha256"]}
        overlay.write_text("second approved overlay\n", encoding="utf-8")
        inventory_path = self.repo / RUNTIME_REL
        inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
        inventory["overlay_sha256"] = self.import_owner().overlay_sha256("second approved overlay")
        inventory_path.write_text(json.dumps(inventory, indent=2, sort_keys=True) + "\n",
                                  encoding="utf-8")
        before = target.read_bytes()

        refused = self.repair_approved(authorization)

        self.assertEqual(refused.returncode, 2, refused.stdout + refused.stderr)
        self.assertIn("approved identity changed", refused.stderr)
        self.assertEqual(target.read_bytes(), before)

    def test_repair_approved_refuses_source_swap_without_writing_project(self) -> None:
        self.render()
        target = self.repo / TARGET_REL
        target.write_text(target.read_text(encoding="utf-8") + "\nhand edit\n", encoding="utf-8")
        _, status = self.status()
        project_before = {
            path.relative_to(self.repo).as_posix(): path.read_bytes()
            for path in self.repo.rglob("*") if path.is_file()
        }
        source = self.bundle / "execution-methodology/methodology.md"
        source.write_text(source.read_text(encoding="utf-8") + "\nchanged approved source\n",
                          encoding="utf-8")

        refused = self.repair_approved({
            "identity": status["approved"],
            "overlay_expected_sha256": status["overlay"]["expected_sha256"],
        })

        self.assertEqual(refused.returncode, 2, refused.stdout + refused.stderr)
        self.assertIn("approved identity changed", refused.stderr)
        self.assertEqual(project_before, {
            path.relative_to(self.repo).as_posix(): path.read_bytes()
            for path in self.repo.rglob("*") if path.is_file()
        })

    def test_render_rejects_symlinked_output_directory_and_destinations(self) -> None:
        outside = self.root / "outside"
        outside.mkdir()
        execution = self.repo / "docs/agents/execution"
        execution.symlink_to(outside, target_is_directory=True)
        refused = self.run_owner()
        self.assertEqual(refused.returncode, 2, refused.stdout + refused.stderr)
        self.assertEqual(list(outside.iterdir()), [])

        execution.unlink()
        execution.mkdir()
        for relative in (TARGET_REL, RUNTIME_REL):
            with self.subTest(relative=relative):
                for child in execution.iterdir():
                    child.unlink()
                external = outside / relative.name
                external.write_text("outside content\n", encoding="utf-8")
                (self.repo / relative).symlink_to(external)
                refused = self.run_owner()
                self.assertEqual(refused.returncode, 2, refused.stdout + refused.stderr)
                self.assertEqual(external.read_text(encoding="utf-8"), "outside content\n")

    def test_render_swap_at_write_open_cannot_modify_external_or_unmanaged_output(self) -> None:
        self.render()
        target = self.repo / TARGET_REL
        target.write_text(target.read_text(encoding="utf-8") + "\nhand edit\n", encoding="utf-8")
        external = self.root / "external.md"
        external.write_text("external content\n", encoding="utf-8")
        module = self.import_owner()
        original_open = module.os.open
        swapped = False

        def swap_then_open(path, flags, *args, **kwargs):
            nonlocal swapped
            if path == TARGET_REL.name and flags & os.O_RDWR and not swapped:
                swapped = True
                target.unlink()
                target.symlink_to(external)
            return original_open(path, flags, *args, **kwargs)

        with mock.patch.object(module.os, "open", side_effect=swap_then_open):
            rc = module.render_methodology(self.repo, False)

        self.assertEqual(rc, 2)
        self.assertTrue(swapped)
        self.assertEqual(external.read_text(encoding="utf-8"), "external content\n")
        self.assertTrue(target.is_symlink())

    def test_intermediate_repo_ancestor_swap_cannot_redirect_output(self) -> None:
        module = self.import_owner()
        authority = self.root / "authority"
        repo = authority / "parent" / "project"
        output = repo / TARGET_REL.parent
        output.mkdir(parents=True)
        repo = repo.resolve()
        external = self.root / "external"
        redirected = external / "parent" / "project" / TARGET_REL.parent
        redirected.mkdir(parents=True)
        sentinel = redirected / TARGET_REL.name
        sentinel.write_text("outside\n", encoding="utf-8")
        real_open = module.os.open
        swapped = False

        def swap_ancestor(path, flags, *args, **kwargs):
            nonlocal swapped
            if not swapped and (path == "authority" or Path(path) == repo):
                swapped = True
                authority.rename(self.root / "authority-parked")
                authority.symlink_to(external, target_is_directory=True)
            return real_open(path, flags, *args, **kwargs)

        with mock.patch.object(module.os, "open", side_effect=swap_ancestor):
            with self.assertRaises(OSError):
                with module._output_directory(repo, create=False) as output_fd:
                    fd = module._open_output_for_write(output_fd, TARGET_REL.name, lambda _text: True)
                    try:
                        module._write_open_output(fd, "redirected\n")
                    finally:
                        os.close(fd)

        self.assertTrue(swapped)
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "outside\n")

    def test_missing_generated_guide_is_repairable_from_intact_approved_inventory(self) -> None:
        self.render()
        (self.repo / TARGET_REL).unlink()

        result, payload = self.status()

        self.assertEqual(result.returncode, 0)
        self.assertEqual(payload["state"], "repairable")
        self.assertEqual(payload["approved"], payload["installed"])
        self.assertEqual(payload["repair_candidates"][0]["paths"], [TARGET_REL.as_posix()])

    def test_damaged_marker_is_repairable_from_intact_approved_inventory(self) -> None:
        self.render()
        target = self.repo / TARGET_REL
        target.write_text(target.read_text(encoding="utf-8").replace(
            '"runtime_sha256":', '"damaged_runtime_sha256":', 1), encoding="utf-8")

        result, payload = self.status()

        self.assertEqual(result.returncode, 0)
        self.assertEqual(payload["state"], "repairable")
        self.assertEqual(payload["repair_candidates"][0]["paths"], [TARGET_REL.as_posix()])

    def test_legacy_marker_is_read_but_never_upgraded(self) -> None:
        (self.repo / TARGET_REL).parent.mkdir(parents=True, exist_ok=True)
        (self.repo / TARGET_REL).write_text(
            '<!-- GENERATED by execution-methodology/scripts/sync_methodology.py from '
            'execution-methodology/methodology.md — do not hand-edit this file; edit the '
            "methodology, or this repo's docs/agents/execution/overlay.md. -->\n"
            '<!-- execution-methodology: {"v":"5.0","source_sha256":"abc"} -->\n',
            encoding="utf-8")
        result, payload = self.status()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(payload["state"], "legacy")
        self.assertIsNone(payload["approved"])

    def test_unadopted_deferred_and_unmanaged_states(self) -> None:
        with self.subTest("unadopted"):
            result, payload = self.status()
            self.assertEqual(result.returncode, 0)
            self.assertEqual(payload["state"], "unadopted")
        (self.repo / "docs/agents/README.md").write_text(
            '# Route\n<!-- execution-methodology: {"mode":"deferred",'
            '"reason":"finish current milestone","date":"2026-09-05"} -->\n',
            encoding="utf-8")
        with self.subTest("deferred"):
            _, payload = self.status()
            self.assertEqual(payload["state"], "deferred")
        (self.repo / TARGET_REL).parent.mkdir(parents=True, exist_ok=True)
        (self.repo / TARGET_REL).write_text("# Owner-authored rules\n", encoding="utf-8")
        with self.subTest("unmanaged"):
            _, payload = self.status()
            self.assertEqual(payload["state"], "unmanaged")

    def test_source_overlay_route_and_dependency_changes_are_not_silent_repairs(self) -> None:
        cases = ("source", "overlay", "route", "dependency")
        for case in cases:
            with self.subTest(case=case):
                self.tearDown()
                self.setUp()
                if case == "overlay":
                    (self.repo / OVERLAY_REL).parent.mkdir(parents=True, exist_ok=True)
                    (self.repo / OVERLAY_REL).write_text("Gate: make check\n", encoding="utf-8")
                self.render()
                if case == "source":
                    source = self.bundle / "execution-methodology/methodology.md"
                    source.write_text(source.read_text(encoding="utf-8") + "\nchanged rule\n",
                                      encoding="utf-8")
                elif case == "overlay":
                    (self.repo / OVERLAY_REL).write_text("Gate: make verify\n", encoding="utf-8")
                elif case == "route":
                    (self.repo / "docs/agents/README.md").write_text("# no route\n", encoding="utf-8")
                else:
                    dep = self.bundle / "execution-methodology/references/execution-loop.md"
                    dep.write_text(dep.read_text(encoding="utf-8") + "\nchanged\n", encoding="utf-8")
                result, payload = self.status()
                self.assertEqual(result.returncode, 0)
                self.assertEqual(payload["state"], "source_changed")
                self.assertFalse(payload["ready"])
                self.assertEqual(payload["repair_candidates"], [])

    def test_each_declared_file_removal_is_non_ready(self) -> None:
        self.render()
        inventory = json.loads((self.repo / RUNTIME_REL).read_text(encoding="utf-8"))
        for row in inventory["files"]:
            with self.subTest(path=row["path"]):
                original = self.bundle / row["path"]
                parked = original.with_name(original.name + ".parked")
                original.rename(parked)
                try:
                    if row["path"].endswith("/sync_methodology.py"):
                        # The owner cannot emit JSON after its own executable is removed. The
                        # observable is still fail closed: invocation is unavailable/non-zero,
                        # never a stale success from another installation.
                        unavailable = self.run_owner("--status-json")
                        self.assertNotEqual(unavailable.returncode, 0)
                        self.assertEqual(unavailable.stdout, "")
                        continue
                    result, payload = self.status()
                    self.assertEqual(result.returncode, 0)
                    self.assertEqual(payload["state"], "source_changed")
                    match = next(item for item in payload["dependencies"]
                                 if item["path"] == row["path"])
                    self.assertEqual(match["status"], "missing")
                finally:
                    parked.rename(original)

    def test_weekly_review_removal_and_change_are_non_ready(self) -> None:
        relative = "execution-methodology/scripts/weekly_review.py"
        for mutation in ("missing", "changed"):
            with self.subTest(mutation=mutation):
                self.tearDown()
                self.setUp()
                self.render()
                command = self.bundle / relative
                parked = command.with_name(command.name + ".parked")
                if mutation == "missing":
                    command.rename(parked)
                else:
                    command.write_text(command.read_text(encoding="utf-8") + "\n# changed\n",
                                       encoding="utf-8")
                try:
                    result, payload = self.status()
                    self.assertEqual(result.returncode, 0)
                    self.assertEqual(payload["state"], "source_changed")
                    self.assertFalse(payload["ready"])
                    self.assertEqual(payload["repair_candidates"], [])
                    row = next(item for item in payload["dependencies"]
                               if item["path"] == relative)
                    self.assertEqual(row["status"], mutation)
                finally:
                    if parked.exists():
                        parked.rename(command)

    def test_malformed_inventory_fails_closed_with_structured_error(self) -> None:
        self.render()
        (self.repo / RUNTIME_REL).write_text("{bad json\n", encoding="utf-8")
        result, payload = self.status()
        self.assertEqual(result.returncode, 2)
        self.assertEqual(payload["state"], "invalid")
        self.assertEqual(payload["findings"][0]["code"], "inspection_error")

    def test_bundle_root_escape_and_project_symlink_fail_closed(self) -> None:
        self.render()
        runtime = self.repo / RUNTIME_REL
        inventory = json.loads(runtime.read_text(encoding="utf-8"))
        inventory["bundle_root"] = str(self.root.resolve())
        runtime.write_text(json.dumps(inventory), encoding="utf-8")
        result, payload = self.status()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(payload["state"], "source_changed")
        self.assertFalse(payload["ready"])

        self.tearDown()
        self.setUp()
        outside = self.root / "outside"
        outside.mkdir()
        (self.repo / "docs/agents/execution").symlink_to(outside, target_is_directory=True)
        result, payload = self.status()
        self.assertEqual(result.returncode, 2)
        self.assertEqual(payload["findings"][0]["code"], "inspection_error")

    def test_declared_dependency_symlink_is_invalid_and_never_followed(self) -> None:
        self.render()
        dependency = self.bundle / "execution-methodology/references/execution-loop.md"
        parked = dependency.with_suffix(".parked")
        dependency.rename(parked)
        outside = self.root / "outside-loop.md"
        outside.write_text(parked.read_text(encoding="utf-8"), encoding="utf-8")
        dependency.symlink_to(outside)

        result, payload = self.status()

        self.assertEqual(result.returncode, 0)
        self.assertEqual(payload["state"], "source_changed")
        row = next(item for item in payload["dependencies"]
                   if item["path"].endswith("execution-loop.md"))
        self.assertEqual(row["status"], "invalid")
        self.assertIsNone(row["actual_sha256"])

    def test_render_twice_does_not_write_target_or_inventory(self) -> None:
        self.render()
        paths = (self.repo / TARGET_REL, self.repo / RUNTIME_REL)
        before = [(path.stat().st_mtime_ns, path.read_bytes()) for path in paths]
        result = self.run_owner()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("already up to date", result.stdout)
        self.assertEqual(before, [(path.stat().st_mtime_ns, path.read_bytes()) for path in paths])

    def test_source_revision_records_declared_dirty_state_and_ignores_unrelated_commit(self) -> None:
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        subprocess.run(["git", "-C", str(self.root), "config", "user.name", "Runtime Test"],
                       check=True)
        subprocess.run(["git", "-C", str(self.root), "config", "user.email", "runtime@test.invalid"],
                       check=True)
        subprocess.run(["git", "-C", str(self.root), "add", "skills"], check=True)
        subprocess.run(["git", "-C", str(self.root), "commit", "-qm", "runtime baseline"],
                       check=True)
        baseline = subprocess.run(["git", "-C", str(self.root), "rev-parse", "HEAD"], check=True,
                                  capture_output=True, text=True).stdout.strip()
        self.render()
        runtime = self.repo / RUNTIME_REL
        self.assertEqual(json.loads(runtime.read_text(encoding="utf-8"))["source_revision"], baseline)

        unrelated = self.root / "unrelated.txt"
        unrelated.write_text("outside runtime\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.root), "add", "unrelated.txt"], check=True)
        subprocess.run(["git", "-C", str(self.root), "commit", "-qm", "unrelated"], check=True)
        before = (runtime.stat().st_mtime_ns, runtime.read_bytes())
        again = self.run_owner()
        self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
        self.assertEqual(before, (runtime.stat().st_mtime_ns, runtime.read_bytes()))
        self.assertEqual(json.loads(runtime.read_text(encoding="utf-8"))["source_revision"], baseline)

        methodology = self.bundle / "execution-methodology/methodology.md"
        methodology.write_text(methodology.read_text(encoding="utf-8") + "\nchanged\n",
                               encoding="utf-8")
        changed = self.run_owner()
        self.assertEqual(changed.returncode, 0, changed.stdout + changed.stderr)
        current_head = subprocess.run(["git", "-C", str(self.root), "rev-parse", "HEAD"],
                                      check=True, capture_output=True, text=True).stdout.strip()
        self.assertEqual(json.loads(runtime.read_text(encoding="utf-8"))["source_revision"],
                         current_head + "+dirty")

    def test_expected_command_entrypoints_and_direct_helpers_are_declared(self) -> None:
        self.render()
        inventory = json.loads((self.repo / RUNTIME_REL).read_text(encoding="utf-8"))
        commands = {row["path"] for row in inventory["files"] if row["stage"] == "command"}
        helpers = {row["path"] for row in inventory["files"] if row["stage"] == "helper"}
        self.assertEqual(commands, EXPECTED_COMMAND_ENTRYPOINTS)
        self.assertTrue(EXPECTED_DIRECT_HELPERS <= helpers)

    def test_declared_commands_have_real_help_smoke(self) -> None:
        self.render()
        inventory = json.loads((self.repo / RUNTIME_REL).read_text(encoding="utf-8"))
        commands = [row for row in inventory["files"] if row["stage"] == "command"]
        for row in commands:
            with self.subTest(path=row["path"]):
                result = subprocess.run([sys.executable, str(self.bundle / row["path"]), "--help"],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("usage:", result.stdout.lower())

        persona = subprocess.run(
            [sys.executable, str(self.bundle / "agent-personas/scripts/sync_personas.py"),
             "--help"], capture_output=True, text=True)
        self.assertEqual(persona.returncode, 0, persona.stdout + persona.stderr)
        self.assertIn("usage:", persona.stdout.lower())

        for relative in ("gate-sandbox/scripts/gate.sh", "gate-sandbox/scripts/readiness.sh"):
            with self.subTest(path=relative):
                gate = subprocess.run([str(self.bundle / relative), "--help"],
                                      capture_output=True, text=True)
                self.assertEqual(gate.returncode, 2, gate.stdout + gate.stderr)
                self.assertIn("unknown option: --help", gate.stdout + gate.stderr)

        evidence = subprocess.run(
            [sys.executable, str(self.bundle / "gate-sandbox/scripts/evidence_supervisor.py"),
             "--help"], capture_output=True, text=True)
        self.assertEqual(evidence.returncode, 0, evidence.stdout + evidence.stderr)
        self.assertIn("usage:", evidence.stdout.lower())

    def test_frozen_contradictory_current_example_is_rejected(self) -> None:
        self.render()
        _, current = self.status()
        contradictory = json.loads(json.dumps(current))
        contradictory["installed"]["runtime_sha256"] = "0" * 64
        contradictory["route"]["valid"] = False
        contradictory["dependencies"][0]["status"] = "missing"
        contradictory["dependencies"][0]["actual_sha256"] = None
        sys.path.insert(0, str(self.script.parent))
        try:
            spec = importlib.util.spec_from_file_location("runtime_validator", self.script)
            module = importlib.util.module_from_spec(spec)
            assert spec.loader is not None
            spec.loader.exec_module(module)
            module.validate_status_payload(current)
            with self.assertRaises(module.MethodologyError):
                module.validate_status_payload(contradictory)
        finally:
            sys.path.pop(0)
            sys.modules.pop("spec_check", None)

    def test_schema_is_frozen_and_status_has_exact_required_fields(self) -> None:
        self.render()
        _, payload = self.status()
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        self.assertEqual(set(payload), set(schema["required"]))
        self.assertFalse(schema["additionalProperties"])


if __name__ == "__main__":
    unittest.main()
