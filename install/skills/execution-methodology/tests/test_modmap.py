"""Tests for modmap.py: loading and checking docs/goals/modules.json, selecting modules for write globs.

Each case writes a map into its own temporary directory and loads it from there.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixtures.goal_fixture import FULL, GOAL, Repo, plan_text  # noqa: E402

sys.path.insert(0, str(GOAL.parent))
import modmap  # noqa: E402


class ModMapTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="modmap-"))
        self.addCleanup(shutil.rmtree, self.root, True)

    def write(self, data):
        path = self.root / modmap.MAP
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data if isinstance(data, str) else json.dumps(data))

    def load(self, modules, shared=()):
        self.write({"modules": modules, "shared": list(shared)})
        return modmap.load(self.root)

    def test_load_rejects_unknown_keys_and_bad_names(self):
        self.assertIsNone(modmap.load(self.root))
        good = {"replaces": "make test", "modules": {"core": {"paths": ["core/**"], "needs": [], "test": "make core"},
                                                     "docs_lint-2": {"paths": ["docs/**"], "test": "make docs",
                                                                     "count": "none"}},
                "shared": ["Makefile"]}
        self.write(good)
        self.assertEqual(modmap.load(self.root), good)
        for bad in ("{not json", {**good, "extra": 1}, {**good, "replaces": ""}, {**good, "replaces": 3},
                    {**good, "modules": {"core": {"paths": ["core/**"], "test": "make core", "owner": "x"}}},
                    {**good, "modules": {"Core": {"paths": ["core/**"], "test": "make core"}}},
                    {**good, "modules": {"-core": {"paths": ["core/**"], "test": "make core"}}},
                    {**good, "modules": {"core": {"paths": ["core/**"], "test": "make core", "count": "zero"}}}):
            self.write(bad)
            with self.assertRaises(modmap.MapError, msg=bad):
                modmap.load(self.root)

    def test_invalid_map_fields_are_diagnosed_without_tracebacks(self):
        ok = {"paths": ["a/**"], "test": "make a"}
        bad = [{"a": {**ok, "test": 42}}, {"a": {"paths": ["a/**"]}}, {"a": {**ok, "needs": 1}},
               {"a": {**ok, "needs": [1]}}, {"a": {**ok, "paths": "a/**"}}]
        for mods in bad:
            self.write({"modules": mods})
            with self.assertRaises(modmap.MapError, msg=mods):
                modmap.load(self.root)
        self.write({"modules": {"a": ok}, "shared": "Makefile"})
        self.assertRaises(modmap.MapError, modmap.load, self.root)
        repo = Repo(plan_text().replace(f"full_gate: {FULL}\n", "full_gate: modules\n"))  # done reads the map
        self.addCleanup(repo.cleanup)
        for mods in bad[:3]:
            repo.write(modmap.MAP, json.dumps({"modules": mods}))
            repo.commit("a broken map")
            for res in (repo.goal("lint"), repo.goal("done"), repo.gate("check", "--goal", "F-9", "--modules", "all")):
                self.assertNotEqual(res.returncode, 0, res.stdout + res.stderr)
                self.assertNotIn("Traceback", res.stdout + res.stderr)
                self.assertIn("module a", res.stdout + res.stderr)

    def test_problems_name_unknown_needs_cycles_missing_fields_and_shared_commands(self):
        m = self.load({"a": {"paths": ["a/**"], "needs": ["b", "ghost"], "test": "make a"},
                       "b": {"paths": ["b/**"], "needs": ["a"], "test": "make b"},
                       "c": {"paths": [], "test": ""},
                       "d": {"paths": ["d/**"], "test": "make b"}})
        self.assertEqual(modmap.problems(m), ["module a needs ghost, which is not a module",
                                              "modules needs cycle: a -> b -> a",
                                              "module c has no test command",
                                              "module c has no paths",
                                              "modules b and d share one test command"])
        self.assertEqual(modmap.problems(self.load({"a": {"paths": ["a/**"], "test": "make a"}})), [])

    def test_select_adds_dependents_transitively_in_file_order(self):
        m = self.load({"app": {"paths": ["app/**"], "needs": ["fees"], "test": "make app"},
                       "core": {"paths": ["core/**"], "test": "make core"},
                       "fees": {"paths": ["fees/**"], "needs": ["core"], "test": "make fees"}})
        self.assertEqual(modmap.select(m, ["core/**"]), ["app", "core", "fees"])
        self.assertEqual(modmap.select(m, ["core/x.py"]), ["app", "core", "fees"])
        self.assertEqual(modmap.select(m, ["app/**"]), ["app"])
        self.assertEqual(modmap.select(m, ["fees/rate.py"]), ["app", "fees"])

    def test_partially_owned_write_glob_selects_every_module(self):
        m = self.load({"a": {"paths": ["src/a/**"], "test": "make a"},
                       "b": {"paths": ["src/b/**"], "test": "make b"},
                       "tools": {"paths": ["tools/**"], "test": "make tools"}})
        self.assertEqual(modmap.select(m, ["src/**"]), ["a", "b", "tools"])
        self.assertEqual(modmap.select(m, ["src/a/**"]), ["a"])

    def test_trailing_slash_write_requires_complete_containment(self):
        m = self.load({"src": {"paths": ["src/*"], "test": "make src"},
                       "tools": {"paths": ["tools/**"], "test": "make tools"}})
        self.assertFalse(modmap.contained("src/", "src/*"))
        self.assertTrue(modmap.contained("src/x.py", "src/*"))
        self.assertTrue(modmap.contained("tools/", "tools/**"))
        self.assertEqual(modmap.select(m, ["src/"]), ["src", "tools"])
        self.assertEqual(modmap.select(m, ["src/x.py"]), ["src"])
        self.assertEqual(modmap.select(m, ["tools/"]), ["tools"])

    def test_trailing_slash_map_globs_preserve_ownership_and_shared_fallback(self):
        m = self.load({"a": {"paths": ["src/**"], "test": "make a"},
                       "b": {"paths": ["tools/**"], "test": "make b"}}, shared=["src/"])
        self.assertEqual(modmap.select(m, ["src/config.py"]), ["a", "b"])
        m = self.load({"a": {"paths": ["src/"], "test": "make a"},
                       "b": {"paths": ["tools/**"], "test": "make b"}})
        self.assertTrue(modmap.contained("src/config.py", "src/"))
        self.assertEqual(modmap.select(m, ["src/config.py"]), ["a"])
        self.assertEqual(modmap.select(m, ["src/**"]), ["a"])
        self.assertEqual(modmap.unmapped(m, ["src/deep/x.py", "README.md"]), ["README.md"])

    def test_select_falls_back_to_every_module_on_shared_or_unowned_paths(self):
        m = self.load({"a": {"paths": ["a/**"], "test": "make a"},
                       "b": {"paths": ["b/**"], "test": "make b"}}, shared=["lib/**", "Makefile"])
        self.assertEqual(modmap.select(m, ["a/x.py"]), ["a"])
        self.assertEqual(modmap.select(m, ["a/x.py", "Makefile"]), ["a", "b"])
        self.assertEqual(modmap.select(m, ["lib/util.py"]), ["a", "b"])
        self.assertEqual(modmap.select(m, ["a/**", "README.md"]), ["a", "b"])

    def test_unmapped_lists_tracked_files_no_glob_covers(self):
        m = self.load({"a": {"paths": ["a/**"], "test": "make a"},
                       "b": {"paths": ["b/*.py"], "test": "make b"}}, shared=["Makefile"])
        files = ["a/x.py", "a/deep/y.py", "b/z.py", "b/sub/w.py", "Makefile", "README.md"]
        self.assertEqual(modmap.unmapped(m, files), ["b/sub/w.py", "README.md"])
        self.assertEqual(modmap.unmapped(m, ["a/x.py"]), [])


class MigrationTest(unittest.TestCase):
    def setUp(self):
        import copy
        import hashlib
        import migrations
        self.migrations = migrations
        self.copy = copy.deepcopy
        self.root = Path(tempfile.mkdtemp(prefix="migration-"))
        self.addCleanup(shutil.rmtree, self.root, True)
        self.body = b"# preserved original\n"
        self.digest = hashlib.sha256(self.body).hexdigest()
        self.before = "python3 -m unittest tests/test_old.py tests/test_keep.py tests/test_last.py"
        self.after = "python3 -m unittest tests/test_keep.py tests/test_last.py tests/test_current.py"
        self.baseline = {"replaces": "make test", "modules": {"legacy": {"test": self.before}}}
        self.entry = {"module": "legacy", "before": self.before, "after": self.after,
                      "originals": [{"path": "tests/test_old.py", "sha256": self.digest}],
                      "successors": ["tests/test_current.py"], "historical_claim": "BYTES_ONLY",
                      "reason": "The old host is unavailable; current behavior has a successor."}
        self.declaration = {"version": 1, "migrations": [self.entry]}
        self.files = {"tests/test_old.py": ("100644", self.body),
                      "tests/test_current.py": ("100755", b"# current\n")}

    def parse(self, data=..., baseline=None):
        return self.migrations.parse(json.dumps(self.declaration if data is ... else data),
                                     self.baseline if baseline is None else baseline, self.files.get)

    def activated(self):
        current = self.copy(self.baseline)
        current["modules"]["legacy"]["test"] = self.after
        return current

    def test_closed_declaration_binds_exact_python_replacement(self):
        import shlex
        entries = self.parse()
        self.assertEqual(self.migrations.parse(text=json.dumps(self.declaration),
                                              baseline_map=self.baseline, read=self.files.get), entries)
        self.assertEqual(self.migrations.allowed(entries, self.baseline, self.files.get), set())
        self.assertEqual(self.migrations.allowed(entries, self.activated(), self.files.get), {"legacy"})
        descriptors = self.migrations.proofs(entries[0])
        self.assertEqual(descriptors[:2], [
            {"kind": "module", "module": "legacy", "command": self.after, "tests": True},
            {"kind": "successor", "module": None,
             "command": "python3 -m unittest tests/test_current.py", "tests": True}])
        preservation = descriptors[2]
        self.assertEqual({k: preservation[k] for k in ("kind", "module", "tests")},
                         {"kind": "preservation", "module": None, "tests": False})
        argv = shlex.split(preservation["command"])
        self.assertEqual(argv, ["python3", "-c", self.migrations.PRESERVE_V1,
                               json.dumps([["tests/test_old.py", self.digest]], separators=(",", ":"))])
        self.assertTrue(argv[2].endswith("\n"))
        self.assertNotIn("assert", argv[2])
        self.assertEqual(self.migrations.proofs(entries[0]), descriptors)
        for prefix in ("./py -m pytest -q", "python3 -m unittest -q"):
            data = self.copy(self.declaration)
            data["migrations"][0]["before"] = self.before.replace("python3 -m unittest", prefix)
            data["migrations"][0]["after"] = self.after.replace("python3 -m unittest", prefix)
            baseline = self.copy(self.baseline)
            baseline["modules"]["legacy"]["test"] = data["migrations"][0]["before"]
            self.assertEqual(self.migrations.proofs(self.parse(data, baseline)[0])[1]["command"],
                             prefix + " tests/test_current.py")

    def test_original_and_successor_declaration_order_is_durable(self):
        import shlex
        data = self.copy(self.declaration)
        entry = data["migrations"][0]
        entry["originals"].append({"path": "tests/test_last.py", "sha256": self.digest})
        entry["successors"].append("tests/test_second.py")
        entry["after"] = "python3 -m unittest tests/test_keep.py tests/test_current.py tests/test_second.py"
        self.files["tests/test_last.py"] = ("100644", self.body)
        descriptors = self.migrations.proofs(self.parse(data)[0])
        self.assertEqual([d["command"] for d in descriptors[1:-1]],
                         ["python3 -m unittest tests/test_current.py", "python3 -m unittest tests/test_second.py"])
        self.assertEqual(json.loads(shlex.split(descriptors[-1]["command"])[-1]),
                         [["tests/test_old.py", self.digest], ["tests/test_last.py", self.digest]])

    def test_historical_claim_other_than_bytes_only_is_rejected(self):
        self.assertEqual(self.parse()[0]["historical_claim"], "BYTES_ONLY")
        for claim in ("REPLAYED", "OTHER", "", None, True, 1, [], {}):
            with self.subTest(claim=claim):
                data = self.copy(self.declaration)
                data["migrations"][0]["historical_claim"] = claim
                self.assertRaises(self.migrations.MigrationError, self.parse, data)

    def test_closed_schema_rejects_unknown_duplicate_and_mistyped_fields(self):
        bad = [None, [], {}, {**self.declaration, "version": True},
               {**self.declaration, "version": 1.0}, {**self.declaration, "version": 2},
               {**self.declaration, "extra": 1}, {**self.declaration, "migrations": []},
               {**self.declaration, "migrations": [True]}]
        for key, value in (("extra", 1), ("module", ""), ("module", "Legacy"),
                           ("reason", ""), ("reason", False), ("originals", []), ("originals", ["file"]),
                           ("successors", []), ("successors", [True]), ("successors", [{}]),
                           ("successors", "tests/test_current.py")):
            data = self.copy(self.declaration)
            data["migrations"][0][key] = value
            bad.append(data)
        data = self.copy(self.declaration)
        data["migrations"][0]["originals"][0]["mode"] = "100644"
        bad.append(data)
        for data in bad:
            with self.subTest(data=data):
                self.assertRaises(self.migrations.MigrationError, self.parse, data)
        text = json.dumps(self.declaration)
        for broken in ("{broken", text.replace('"version": 1', '"version": 1, "version": 1'),
                       text.replace('"module": "legacy"', '"module": "legacy", "module": "legacy"'),
                       text.replace('"sha256":', '"path": "tests/test_old.py", "sha256":')):
            self.assertRaises(self.migrations.MigrationError, self.migrations.parse,
                              broken, self.baseline, self.files.get)

    def test_paths_hashes_and_original_modes_are_validated(self):
        for path in ("/test.py", "./test.py", "a/../test.py", "a//test.py", "a/./test.py",
                     "a\\test.py", "a/$x.py", "a/$(x).py", "a/x;z.py", "a/x|z.py",
                     "a/x&z.py", "a/x`z`.py", "a/x<z.py", "a/x>z.py", "a/x*.py",
                     "a/x?.py", "a/x[1].py", "#x.py", "a/x\x85.py", "a/x\n.py", "a/x\x00.py", "-x.py"):
            for field in ("originals", "successors"):
                with self.subTest(path=path, field=field):
                    data = self.copy(self.declaration)
                    if field == "originals":
                        data["migrations"][0][field][0]["path"] = path
                    else:
                        data["migrations"][0][field] = [path]
                    self.assertRaises(self.migrations.MigrationError, self.parse, data)
        for digest in ("", "a" * 63, "A" * 64, "z" * 64, 1, None):
            data = self.copy(self.declaration)
            data["migrations"][0]["originals"][0]["sha256"] = digest
            self.assertRaises(self.migrations.MigrationError, self.parse, data)
        for value in (None, ("120000", self.body), ("040000", self.body),
                      (100644, self.body), ("100644", b"changed"), ("100644", "text")):
            with self.subTest(value=value):
                self.files["tests/test_old.py"] = value
                self.assertRaises(self.migrations.MigrationError, self.parse)
        self.files["tests/test_old.py"] = ("100755", self.body)
        self.assertTrue(self.parse())

    def test_duplicate_modules_originals_and_successors_are_rejected(self):
        for field in ("migrations", "originals", "successors"):
            data = self.copy(self.declaration)
            values = data[field] if field == "migrations" else data["migrations"][0][field]
            values.append(self.copy(values[0]))
            self.assertRaises(self.migrations.MigrationError, self.parse, data)
        data, baseline = self.copy(self.declaration), self.copy(self.baseline)
        second = self.copy(self.entry)
        second.update(module="other", before=self.before.replace("python3", "./py"),
                      after=self.after.replace("python3", "./py"))
        data["migrations"].append(second)
        baseline["modules"]["other"] = {"test": second["before"]}
        self.assertRaises(self.migrations.MigrationError, self.parse, data, baseline)

    def test_literal_command_delta_retains_file_sequence_and_prefix(self):
        for after in (self.after.replace("test_keep.py ", ""),
                      self.after.replace("test_keep.py tests/test_last.py", "test_last.py tests/test_keep.py"),
                      self.after.replace("python3", "./py"), self.after.replace("unittest", "pytest -q"),
                      self.after + " tests/test_extra.py", self.after + " tests/test_current.py",
                      self.after.replace("test_current.py", "test_old.py"),
                      self.after + " && echo ok", self.after + "\n", self.after + "\r", self.after + "\t",
                      "python3 -m unittest discover", "python3 -m unittest -k current tests/test_current.py",
                      "python3 -m pytest -q tests/test_current.py -k current"):
            with self.subTest(after=after):
                data = self.copy(self.declaration)
                data["migrations"][0]["after"] = after
                self.assertRaises(self.migrations.MigrationError, self.parse, data)
        for before in ("python3 -m pytest tests/test_old.py", "python -m unittest tests/test_old.py",
                       "python3 -m unittest tests/test_old.py;echo ok", self.before + " tests/test_old.py"):
            data, baseline = self.copy(self.declaration), self.copy(self.baseline)
            data["migrations"][0]["before"] = before
            baseline["modules"]["legacy"]["test"] = before
            self.assertRaises(self.migrations.MigrationError, self.parse, data, baseline)
        baseline = self.copy(self.baseline)
        baseline["modules"]["legacy"]["count"] = "none"
        self.assertRaises(self.migrations.MigrationError, self.parse, baseline=baseline)
        baseline["modules"]["legacy"] = {"test": "make other"}
        self.assertRaises(self.migrations.MigrationError, self.parse, baseline=baseline)
        self.assertRaises(self.migrations.MigrationError, self.parse, baseline={"modules": {}})

    def test_pytest_selectors_and_response_files_are_rejected_even_when_tracked(self):
        for field, path in (("originals", "tests/test_old.py::Case.py"),
                            ("successors", "tests/test_current.py::Case.py"),
                            ("originals", "@tests/test_old.py"),
                            ("successors", "@tests/test_current.py")):
            with self.subTest(field=field):
                data, baseline = self.copy(self.declaration), self.copy(self.baseline)
                entry = data["migrations"][0]
                entry["before"] = self.before.replace("unittest", "pytest -q")
                entry["after"] = self.after.replace("unittest", "pytest -q")
                if field == "originals":
                    entry["originals"][0]["path"] = path
                    entry["before"] = entry["before"].replace("tests/test_old.py", path)
                else:
                    entry["successors"] = [path]
                    entry["after"] = entry["after"].replace("tests/test_current.py", path)
                baseline["modules"]["legacy"]["test"] = entry["before"]
                self.files[path] = ("100644", self.body)
                self.assertRaises(self.migrations.MigrationError, self.parse, data, baseline)
        data, baseline = self.copy(self.declaration), self.copy(self.baseline)
        entry = data["migrations"][0]
        entry["successors"] = ["tests/test_current@host.py"]
        entry["after"] = self.after.replace("test_current.py", "test_current@host.py")
        entries = self.parse(data, baseline)
        current = self.copy(baseline)
        current["modules"]["legacy"]["test"] = entry["after"]
        self.files["tests/test_current@host.py"] = ("100644", self.body)
        self.assertEqual(self.migrations.allowed(entries, current, self.files.get), {"legacy"})

    def test_allowed_rejects_third_commands_changed_bindings_and_missing_files(self):
        entries = self.parse()
        for current in ({"modules": {}}, {**self.activated(), "replaces": "make other"}):
            self.assertRaises(self.migrations.MigrationError, self.migrations.allowed,
                              entries, current, self.files.get)
        for key, value in (("test", "make third"), ("count", "none"), ("count", True)):
            current = self.activated()
            current["modules"]["legacy"][key] = value
            self.assertRaises(self.migrations.MigrationError, self.migrations.allowed,
                              entries, current, self.files.get)
        for path in ("tests/test_old.py", "tests/test_current.py"):
            for value in (None, ("120000", self.body)):
                files = {**self.files, path: value}
                self.assertRaises(self.migrations.MigrationError, self.migrations.allowed,
                                  entries, self.activated(), files.get)
        files = {**self.files, "tests/test_old.py": ("100644", b"changed")}
        self.assertRaises(self.migrations.MigrationError, self.migrations.allowed,
                          entries, self.activated(), files.get)
        del self.files["tests/test_current.py"]
        self.assertEqual(self.migrations.allowed(entries, self.baseline, self.files.get), set())

    def test_proofs_require_exact_tree_command_module_and_clean_positive_counts(self):
        descriptors = self.migrations.proofs(self.parse()[0])
        for descriptor in descriptors:
            good = {"tree": "tree", "command": descriptor["command"], "exit": 0,
                    "verdict": "PASS", "executed": 1 if descriptor["tests"] else 0,
                    "failed": 0, "skipped": 0, "failures": [], "new_failures": [],
                    "baseline_failures": [], "reasons": []}
            if descriptor["module"] is not None:
                good["module"] = descriptor["module"]
            self.assertTrue(self.migrations.proof_ok(descriptor, good, "tree"))
            suites = {"unittest": {k: good[k] for k in ("executed", "failed", "skipped")}}
            self.assertTrue(self.migrations.proof_ok(descriptor, {**good, "suites": suites}, "tree"))
            for key in ("executed", "failed", "skipped"):
                for value in (-1, True, 0.0, "0", None):
                    malformed = self.copy(suites)
                    malformed["unittest"][key] = value
                    self.assertFalse(self.migrations.proof_ok(descriptor, {**good, "suites": malformed}, "tree"))
            mutations = [("tree", "other"), ("command", "other"), ("module", "other"),
                         ("exit", 1), ("exit", False), ("verdict", "FAIL"), ("failed", 1),
                         ("skipped", 1), ("failures", ["bad"]), ("baseline_failures", ["bad"]),
                         ("new_failures", ["bad"]), ("reasons", ["bad"]),
                         ("suites", {"unittest": {"executed": 1, "failed": 1, "skipped": 0}})]
            mutations += [(key, value) for key in ("executed", "failed", "skipped")
                          for value in (-1, True, 0.0, "0", None)]
            if descriptor["tests"]:
                mutations.append(("executed", 0))
            for key, value in mutations:
                with self.subTest(kind=descriptor["kind"], key=key, value=value):
                    self.assertFalse(self.migrations.proof_ok(descriptor, {**good, key: value}, "tree"))
            for key in good:
                bad = dict(good)
                del bad[key]
                self.assertFalse(self.migrations.proof_ok(descriptor, bad, "tree"), key)
            for tests in (1, [], None):
                self.assertFalse(self.migrations.proof_ok({**descriptor, "tests": tests}, good, "tree"))
        self.assertFalse(self.migrations.proof_ok(descriptors[0], None, "tree"))

    def test_generated_preservation_command_checks_real_files_without_assertions(self):
        import os
        import shlex
        import subprocess
        descriptor = self.migrations.proofs(self.parse()[0])[-1]
        argv = shlex.split(descriptor["command"])
        original = self.root / "tests/test_old.py"
        original.parent.mkdir()
        original.write_bytes(self.body)
        def run(expected):
            result = subprocess.run(argv, cwd=self.root, capture_output=True, text=True,
                                    env={**os.environ, "PYTHONOPTIMIZE": "1"})
            self.assertEqual(result.returncode, 0 if expected == "PASS" else 1, result.stderr)
            self.assertIn("preservation: " + expected, result.stdout)
        run("PASS")
        original.write_bytes(b"changed")
        run("FAIL")
        original.unlink()
        run("FAIL")
        original.write_bytes(self.body)
        original.chmod(0)
        try:
            run("FAIL")
        finally:
            original.chmod(0o644)
        target = self.root / "target.py"
        target.write_bytes(self.body)
        original.unlink()
        original.symlink_to(target)
        run("FAIL")
        original.unlink()
        original.write_bytes(self.body)
        original.parent.rename(self.root / "actual")
        (self.root / "tests").symlink_to(self.root / "actual", target_is_directory=True)
        run("FAIL")


if __name__ == "__main__":
    unittest.main()
