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


if __name__ == "__main__":
    unittest.main()
