"""Tests for goal.py: the plan parser, lint, the eight done rows, the packet, cost from planted transcripts.

Each case builds a throwaway repository (fixtures/goal_fixture.py) holding goal F-9, tagged
goal/F-9/approved, and plants one way a run could fake progress; the matching done row must name it.
"""
from __future__ import annotations

import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixtures.goal_fixture import DESIGN, E2E, FULL, GOAL, SPEC, V71_FILES, Repo, env, plan_text  # noqa: E402

sys.path.insert(0, str(GOAL.parent))
import goal  # noqa: E402
from gate import module_key, receipt_path  # noqa: E402

REAL_PLAN = Path(__file__).resolve().parents[4] / "docs" / "goals" / "S-1" / "plan.md"
S2_PLAN = REAL_PLAN.parents[1] / "S-2" / "plan.md"
PLAN = "docs/goals/F-9/plan.md"
SPEC_PATH, DESIGN_PATH = "docs/goals/F-9/spec.md", "docs/goals/F-9/design.md"
# Assembled so this file does not itself add the marker that row 5 rejects.
SKIP_DECORATOR = "    @unittest." + "skip('later')\n"


class ParseTest(unittest.TestCase):
    def test_parses_this_repositorys_s1_plan(self):
        plan = goal.parse_plan(REAL_PLAN.read_text())
        self.assertEqual(sorted(plan["tasks"], key=lambda t: int(t[1:])), [f"T{n}" for n in range(1, 10)])
        self.assertEqual(plan["milestones"], {
            "M1": {"tasks": ["T1", "T2", "T3", "T4", "T5"], "e2e": "install/tests/e2e_install.sh"},
            "M2": {"tasks": ["T6", "T7", "T8", "T9"],
                   "e2e": "install/skills/execution-methodology/tests/e2e_run.sh"}})
        self.assertEqual(plan["meta"]["protected"], ["docs/decisions/decisions.md#D1-D19"])
        self.assertEqual(plan["meta"]["full_gate"], "cd install && ./install.sh --dry-run && ./verify.sh")
        self.assertIn("install/README.md", plan["tasks"]["T2"]["writes"])
        self.assertIn("install/tests/test_install.py", plan["tasks"]["T2"]["tests-may-change"])
        self.assertEqual(goal.lint(type("C", (), {"plan": plan})()), [])

    def test_parses_this_repositorys_s2_plan(self):
        plan = goal.parse_plan(S2_PLAN.read_text())
        self.assertEqual(sorted(plan["tasks"], key=lambda t: int(t[1:])), [f"T{n}" for n in range(1, 12)])
        self.assertEqual(sorted(plan["milestones"]), ["M1", "M2"])
        self.assertEqual([t for t, task in plan["tasks"].items() if not task["reads"]], [])
        self.assertIn("docs/goals/S-2/spec.md", plan["tasks"]["T2"]["reads"])
        self.assertEqual(goal.lint(goal.find_ctx(goal="S-2", cwd=S2_PLAN.parent)), [])

    def test_flow_values(self):
        self.assertEqual(goal.flow('{tasks: [T1, T2], e2e: "a, b: c"}'), {"tasks": ["T1", "T2"], "e2e": "a, b: c"})
        self.assertEqual(goal.flow("[none]"), ["none"])

    def test_quoted_command_round_trip(self):
        intended = 'true "ignored" && false'
        text = (plan_text().replace(f"gate: {FULL} -q", r'gate: "true \"ignored\" && false"')
                .replace(f'M1: {{tasks: [T1, T2], e2e: "{E2E}"}}',
                         r'M1: {tasks: [T1, T2], e2e: "true \"ignored\" && false"}'))
        plan = goal.parse_plan(text)
        self.assertEqual(plan["meta"]["gate"], intended)
        self.assertEqual(plan["milestones"]["M1"]["e2e"], intended)
        self.assertEqual(plan["milestones"]["M2"]["e2e"], E2E)
        self.assertEqual(goal.flow(r'"a \\ b"'), "a \\ b")
        self.assertEqual(goal.flow("'it''s'"), "it's")
        self.assertEqual(subprocess.run(intended, shell=True).returncode, 1)

    def test_rejects_unconsumed_and_unterminated_flow_values(self):
        for bad in ('"true" && false', "[T1, T2", '{tasks: [T1, T2], e2e: "x"', '{tasks: [T1], e2e: "x" junk}',
                    "[T1] tail"):
            with self.assertRaises(ValueError, msg=bad):
                goal.flow(bad)
        text = (plan_text().replace(f"gate: {FULL} -q", 'gate: "true" && false')
                .replace(f'M1: {{tasks: [T1, T2], e2e: "{E2E}"}}', 'M1: {tasks: [T1, T2], e2e: "true" && false}')
                .replace(f'M2: {{tasks: [T3], e2e: "{E2E}"}}', "M2: {tasks: [T3]"))
        plan = goal.parse_plan(text)
        self.assertNotIn("gate", plan["meta"])
        self.assertEqual(plan["milestones"]["M1"], {"tasks": [], "e2e": ""})
        errs = goal.lint(type("C", (), {"plan": plan})())
        for n in (4, 7, 8):
            self.assertTrue(any(e.startswith(f"line {n}: ") for e in errs), (n, errs))


class RepoCase(unittest.TestCase):
    plan = None

    def setUp(self):
        self.repo = Repo(self.plan)
        self.addCleanup(self.repo.cleanup)

    def done(self):
        res = self.repo.goal("done")
        return res.returncode, {line.split(":")[0].split(" ok")[0]: line for line in res.stdout.splitlines()
                                if line.startswith("row ")}, res

    def assertRow(self, n, text=None):
        code, rows, res = self.done()
        self.assertEqual(code, 1, res.stdout + res.stderr)
        self.assertNotIn("ok", rows[f"row {n}"].split(":")[0], res.stdout)
        if text:
            self.assertIn(text, rows[f"row {n}"], res.stdout)

    def assertRowOk(self, n):
        _code, rows, res = self.done()
        self.assertEqual(rows[f"row {n}"], f"row {n} ok", res.stdout + res.stderr)

    def fix(self, path, text, subject):
        self.repo.write(path, text)
        return self.repo.commit(subject)


class LintTest(RepoCase):
    plan = (plan_text().replace("  M2: {tasks: [T3], e2e: \"" + E2E + "\"}", "  M2: {tasks: [T9]}")
            .replace("touches: [none]\n", "").replace("writes: src/c/**", "writes: docs/**"))

    def test_lint_names_each_planted_defect(self):
        self.repo.edit(PLAN, "writes: src/a/**, tests/**\n", "")
        res = self.repo.goal("lint")
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        for text in ("T3: in no milestone", "M2: names missing task T9", "M2: no e2e", "T1: no writes",
                     "frontmatter: touches is missing", "T3: writes intersect protected"):
            self.assertIn(text, res.stdout)

    def test_the_fixture_plan_lints_clean(self):
        self.repo.write(PLAN, plan_text())
        self.assertEqual(self.repo.goal("lint").returncode, 0)


class TaskFieldTest(RepoCase):
    """Task gate: and needs: lines: next, resume, the lint warnings and the approval page's Gate column."""
    plan = (plan_text().replace("tasks: [T1, T2]", "tasks: [T1, T2, T3]").replace("tasks: [T3]", "tasks: []")
            .replace("writes: src/c/**\n", "writes: src/c/**\nneeds: T1\n"))

    def test_next_lists_every_ready_task(self):
        res = self.repo.goal("next")
        self.assertEqual((res.returncode, res.stdout), (0, "T1 — alpha\nT2 — beta\n"), res.stderr)
        self.repo.tick("T1")
        res = self.repo.goal("next")
        self.assertEqual((res.returncode, res.stdout), (0, "T2 — beta\nT3 — gamma\n"), res.stderr)

    def test_resume_reports_blocked_dependencies_without_suggesting_close(self):
        self.repo.write(PLAN, plan_text().replace("tests-may-change: tests/test_a.py\n",
                                                  "tests-may-change: tests/test_a.py\nneeds: T1\n"))
        self.repo.tick("T1", "!")
        res = self.repo.goal("next")
        self.assertEqual((res.returncode, res.stdout), (1, "no ready task: T2 needs T1 (parked)\n"), res.stderr)
        res = self.repo.goal("resume")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("Next: no ready task; T2 needs T1 (parked).", res.stdout)
        self.assertNotIn("close the milestone", res.stdout)

    def test_a_task_gate_is_parsed_and_shown(self):
        cmd = "python3 -m unittest -k 'a, b' tests/test_a.py # focused"
        self.repo.edit(PLAN, "writes: src/b/**, tests/**\n", f"writes: src/b/**, tests/**\ngate: {cmd}\n")
        plan = goal.parse_plan(self.repo.read(PLAN))
        self.assertEqual((plan["tasks"]["T2"]["gate"], plan["tasks"]["T1"]["gate"]), (cmd, ""))
        self.assertEqual((plan["tasks"]["T3"]["needs"], plan["tasks"]["T2"]["needs"]), (["T1"], []))
        self.assertEqual(self.repo.goal("next").stdout, f"T1 — alpha\nT2 — beta · gate: {cmd}\n")
        self.assertEqual(self.repo.goal("packet", "--approval").returncode, 0)
        page = self.repo.read(".runs/F-9/approval.html")
        self.assertIn("<th>Gate</th>", page)
        self.assertRegex(page, rf"<tr><td>T2 [^\n]*<td>{re.escape(html.escape(cmd))}</td>")
        self.assertRegex(page, r"<tr><td>T1 [^\n]*<td>plan gate</td>")

    def test_needs_and_overlap_warn_without_failing(self):
        self.repo.write(PLAN, plan_text().replace("writes: src/a/**, tests/**\n", "writes: src/a/**, tests/**\nneeds: T9\n")
                        .replace("tests-may-change: tests/test_a.py\n", "tests-may-change: tests/test_a.py\nneeds: T3\n"))
        res = self.repo.goal("lint")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        for text in ("lint: warning: T1 needs T9, which is not an earlier task",
                     "lint: warning: T2 needs T3, which is not an earlier task",
                     "lint: warning: T1 and T2 overlap in writes and neither needs the other"):
            self.assertIn(text, res.stdout)
        self.assertTrue(res.stdout.splitlines()[-1].startswith("lint: PASS"), res.stdout)
        self.repo.edit(PLAN, "needs: T9", "needs: T2")
        self.repo.edit(PLAN, "needs: T3", "needs: T1")  # a cycle: T1 needs T2, T2 needs T1
        res = self.repo.goal("lint")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("lint: warning: T1 needs T2, which is not an earlier task", res.stdout)
        self.assertNotIn("T2 needs T1", res.stdout)
        self.assertNotIn("overlap", res.stdout)

    def test_slow_default_gate_warns(self):
        self.assertNotIn("has no gate line", self.repo.goal("lint").stdout)
        check = {"label": "check", "command": f"{FULL} -q", "tree": self.repo.tree(), "duration_s": 700,
                 "verdict": "PASS", "finished_at": "2026-01-01T00:00:00Z"}
        jsonl(self.repo.path(".runs/F-9/checks.jsonl"), [{**check, "duration_s": 10}, check,
                                                         {**check, "command": "other", "duration_s": 5}])
        self.repo.edit(PLAN, "writes: src/c/**\n", "writes: src/c/**\ngate: make gamma\n")
        res = self.repo.goal("lint")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        for tid in ("T1", "T2"):
            self.assertIn(f"lint: warning: {tid} has no gate line and the plan gate's last check took 700 s "
                          "(budget 600 s)", res.stdout)
        self.assertNotIn("T3 has no gate line", res.stdout)


MAP_PATH = "docs/goals/modules.json"
MODULES = {"replaces": "cd tests && ./verify.sh", "modules": {
    "a": {"paths": ["src/a/**", "tests/test_a.py"], "test": "python3 -m unittest tests.test_a"},
    "b": {"paths": ["src/b/**", "tests/test_b_*.py"], "needs": ["a"], "test": "python3 -m unittest tests.test_b_start"},
    "c": {"paths": ["src/c/**"], "test": "python3 -m unittest tests.test_c"},
    "checks": {"paths": ["emit.py"], "test": "python3 emit.py", "count": "none"}},
    "shared": ["docs/**", ".gitignore", "tests/test_e2e*.py"]}


class ModuleMapTest(RepoCase):
    """docs/goals/modules.json: lint, the derived task gate in next and on the approval page, full_gate: modules."""
    plan = (plan_text().replace("tasks: [T1, T2]", "tasks: [T1, T2, T3]").replace("tasks: [T3]", "tasks: []")
            .replace("writes: src/a/**, tests/**", "writes: src/a/**"))

    def setUp(self):
        self.repo = Repo(self.plan, files={MAP_PATH: json.dumps(MODULES, indent=1)})
        self.addCleanup(self.repo.cleanup)

    def write_map(self, m):
        self.repo.write(MAP_PATH, json.dumps(m, indent=1))

    def test_lint_fails_on_a_broken_map_and_warns_about_unmapped_files(self):
        res = self.repo.goal("lint")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertNotIn("modules.json", res.stdout)
        self.repo.write("tools/x.py", "X = 1\n")
        self.repo.write("tools/y.py", "Y = 1\n")
        self.repo.commit("tools nobody maps")
        res = self.repo.goal("lint")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("lint: warning: modules.json: 2 tracked file(s) no module covers, first tools/x.py\n", res.stdout)
        mods = json.loads(json.dumps(MODULES["modules"]))
        mods["a"]["needs"], mods["c"]["needs"] = ["z", "b"], ["c"]
        mods["c"]["paths"], mods["c"]["test"], mods["checks"]["test"] = [], "", mods["b"]["test"]
        self.write_map({**MODULES, "modules": mods})
        res = self.repo.goal("lint")
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        for text in ("module a needs z, which is not a module", "modules needs cycle: a -> b -> a",
                     "modules needs cycle: c -> c", "module c has no test command", "module c has no paths",
                     "modules b and checks share one test command"):
            self.assertIn(f"lint: modules.json: {text}\n", res.stdout)
        self.repo.write(MAP_PATH, "{not json")
        res = self.repo.goal("lint")
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("lint: modules.json: not valid JSON", res.stdout)

    def test_next_and_approval_show_the_derived_gate(self):
        res = self.repo.goal("next")
        self.assertEqual((res.returncode, res.stdout), (0, "T1 — alpha · gate: modules: a, b\n"
                                                           "T2 — beta · gate: modules: a, b, c, checks\n"
                                                           "T3 — gamma · gate: modules: c\n"), res.stderr)
        self.assertEqual(self.repo.goal("packet", "--approval").returncode, 0)
        page = self.repo.read(".runs/F-9/approval.html")
        self.assertRegex(page, r"<tr><td>T1 [^\n]*<td>modules: a, b</td>")
        self.assertRegex(page, r"<tr><td>T3 [^\n]*<td>modules: c</td>")
        self.assertNotIn("plan gate", page)
        check = {"label": "check", "command": f"{FULL} -q", "tree": self.repo.tree(), "duration_s": 700,
                 "verdict": "PASS", "finished_at": "2026-01-01T00:00:00Z"}
        jsonl(self.repo.path(".runs/F-9/checks.jsonl"), [check])
        self.assertNotIn("has no gate line", self.repo.goal("lint").stdout)
        self.repo.path(MAP_PATH).unlink()
        self.assertEqual(self.repo.goal("next").stdout, "T1 — alpha\nT2 — beta\nT3 — gamma\n")
        self.assertIn("lint: warning: T3 has no gate line", self.repo.goal("lint").stdout)

    def test_a_gate_line_overrides_the_map(self):
        self.repo.edit(PLAN, "writes: src/c/**\n", "writes: src/c/**\ngate: make gamma\n")
        self.assertEqual(self.repo.goal("next").stdout.splitlines()[2], "T3 — gamma · gate: make gamma")
        self.assertEqual(self.repo.goal("packet", "--approval").returncode, 0)
        self.assertRegex(self.repo.read(".runs/F-9/approval.html"), r"<tr><td>T3 [^\n]*<td>make gamma</td>")

    def test_full_gate_modules_needs_replaces_and_a_non_test_module(self):
        bare = {**MODULES, "modules": {k: v for k, v in MODULES["modules"].items() if k != "checks"}}
        del bare["replaces"]
        self.write_map(bare)
        self.assertEqual(self.repo.goal("lint").returncode, 0)
        self.repo.edit(PLAN, f"full_gate: {FULL}\n", "full_gate: modules\n")
        res = self.repo.goal("lint")
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("lint: full_gate: modules needs the map to name the command it replaces\n", res.stdout)
        self.assertIn("lint: full_gate: modules needs a count-none module for the non-test checks\n", res.stdout)
        self.write_map(MODULES)
        res = self.repo.goal("lint")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertNotIn("full_gate", res.stdout)

    def test_approval_page_lists_every_module_under_the_replaced_command(self):
        self.assertEqual(self.repo.goal("packet", "--approval").returncode, 0)
        self.assertNotIn("Full gate", self.repo.read(".runs/F-9/approval.html"))
        self.repo.edit(PLAN, f"full_gate: {FULL}\n", "full_gate: modules\n")
        self.assertEqual(self.repo.goal("packet", "--approval").returncode, 0)
        page = self.repo.read(".runs/F-9/approval.html")
        self.assertIn("<p>Check that every non-test check the replaced command runs is run by a module.</p>", page)
        self.assertIn("<caption>cd tests &amp;&amp; ./verify.sh</caption>", page)
        self.assertNotIn("&& ./verify.sh", page)
        for name, spec in MODULES["modules"].items():
            kind = "non-test checks" if spec.get("count") == "none" else "tests"
            self.assertIn(f"<tr><td>{name}</td><td>{html.escape(spec['test'])}</td><td>{kind}</td></tr>", page)


class ModuleRowTest(RepoCase):
    """full_gate: modules at done row 7, the approved map at row 4, retried modules in the packet; receipts written directly."""
    plan = plan_text().replace(f"full_gate: {FULL}\n", "full_gate: modules\n")

    def setUp(self):
        self.repo = Repo(self.plan, files={MAP_PATH: json.dumps(MODULES, indent=1)})
        self.addCleanup(self.repo.cleanup)
        self.repo.close()

    def plant(self, name, verdict="PASS", **extra):
        tree = self.repo.tree()
        path = receipt_path(self.repo.dir, "F-9", tree, module_key(name, MODULES["modules"][name]))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"tree": tree, "name": "module", "module": name, "verdict": verdict,
                                    "command": MODULES["modules"][name]["test"], **extra}))

    def test_module_receipts_satisfy_row_7_for_full_gate_modules(self):
        self.assertRow(7, f"no PASS module receipt for a on tree {self.repo.tree()[:10]}")
        for name in MODULES["modules"]:
            self.plant(name)
        code, rows, res = self.done()
        self.assertEqual(code, 0, res.stdout + res.stderr)
        self.assertEqual(rows["row 7"], "row 7 ok")
        self.plant("b", "FAIL")
        self.assertRow(7, f"no PASS module receipt for b on tree {self.repo.tree()[:10]}")

    def test_row_7_names_a_missing_module_or_an_unmapped_file(self):
        for name in ("a", "b", "checks"):
            self.plant(name)
        self.assertRow(7, f"no PASS module receipt for c on tree {self.repo.tree()[:10]}")
        self.plant("c", module="a")  # a receipt naming another module does not count
        self.assertRow(7, "no PASS module receipt for c")
        self.fix("tools/x.py", "X = 1\n", "[T1] a tool nobody maps")
        for name in MODULES["modules"]:
            self.plant(name)
        self.assertRow(7, "1 tracked file(s) no module covers, first tools/x.py")

    def test_unapproved_map_change_fails_row_4(self):
        self.assertRowOk(4)
        mods = {**MODULES["modules"], "a": {**MODULES["modules"]["a"], "paths": ["src/**"]}}
        sha = self.fix(MAP_PATH, json.dumps({**MODULES, "modules": mods}, indent=1), "[T1] alpha remaps itself")
        self.assertRow(4, f"{sha[:10]} [T1] changes protected {MAP_PATH}")
        self.repo.edit(PLAN, "writes: src/c/**", f"writes: src/c/**, {MAP_PATH}")
        self.assertIn("lint: T3: writes intersect protected\n", self.repo.goal("lint").stdout)

    def test_packet_lists_retried_modules_with_load_readings(self):
        self.repo.goal("packet")
        self.assertIn("\nRetried modules:\nnone\n", self.repo.read(".runs/F-9/packet.md"))
        failed = {"verdict": "FAIL", "module": "a", "started_at": "2026-10-13T09:00:00+00:00",
                  "load_before": 6.5, "load_peak": 11.25, "cpus": 8}
        self.plant("a", started_at="2026-10-13T09:05:00+00:00", load_before=1.5, load_peak=2.0, cpus=8,
                   retry_of=failed)
        self.plant("b")
        res = self.repo.goal("packet")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        packet = self.repo.read(".runs/F-9/packet.md")
        self.assertRegex(packet, r"\nReceipts:\n(\S+\.json\n)+\nRetried modules:\n"
                                 r"a: failed 2026-10-13T09:00:00\+00:00 \(load 6\.5/11\.25 on 8 cpus\), "
                                 r"retry PASS \(load 1\.5/2\.0\)\n\n")


    def test_packet_preserves_actual_retry_after_superseding_check(self):
        failed = {"verdict": "FAIL", "module": "a", "started_at": "2026-10-13T09:00:00+00:00",
                  "load_before": 6.5, "load_peak": 11.25, "cpus": 8}
        retry = {"verdict": "PASS", "module": "a", "started_at": "2026-10-13T09:05:00+00:00",
                 "load_before": 1.5, "load_peak": 2.0, "cpus": 8, "retry_of": failed}
        self.plant("a", "FAIL", started_at="2026-10-13T09:30:00+00:00", load_before=3.0, load_peak=4.0, cpus=8,
                   superseded=retry, retry_of=failed)
        res = self.repo.goal("packet")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("\nRetried modules:\n"
                      "a: failed 2026-10-13T09:00:00+00:00 (load 6.5/11.25 on 8 cpus), retry PASS (load 1.5/2.0), "
                      "later check FAIL (load 3.0/4.0)\n\n", self.repo.read(".runs/F-9/packet.md"))

class DoneTest(RepoCase):
    def test_all_green_prints_done(self):
        self.repo.close()
        code, rows, res = self.done()
        self.assertEqual(code, 0, res.stdout + res.stderr)
        self.assertEqual(list(rows.values()), [f"row {n} ok" for n in range(1, 9)])
        self.assertIn(f"DONE M1 on tree {self.repo.tree()}", res.stdout)

    def test_unticked_tasks_and_a_dirty_tree(self):
        self.repo.write("src/a/x.py", "A = 1\n")
        self.assertRow(1, "T1 is not [x]")
        self.assertRow(2, "uncommitted")

    def test_parked_task_needs_a_parked_line(self):
        self.repo.tick("T2", "!")
        self.repo.commit("F-9: park T2")
        self.assertRow(1, "T2 is parked without a Parked line")
        self.repo.edit(PLAN, "## Parked\n", "## Parked\n\n- T2: needs the founder.\n")
        self.repo.commit("F-9: park T2 with a line")
        _c, rows, _r = self.done()
        self.assertNotIn("T2", rows["row 1"])

    def test_row3_accepts_a_plan_only_tick_and_rejects_a_prose_edit(self):
        self.repo.tick("T1")
        self.repo.edit(PLAN, "- 2026-01-01: fixture decision.\n", "- 2026-01-01: fixture decision.\n- later.\n")
        self.repo.commit("F-9: tick T1, a decision")
        self.assertRowOk(3)
        self.repo.edit(PLAN, "Do the beta work.", "Do the beta work differently.")
        self.repo.commit("F-9: reword T2")
        self.assertRow(3, "not plan-only")
        self.assertRow(6)

    def test_row4_judges_writes_at_the_parent_despite_a_later_widening(self):
        sha = self.fix("src/b/z.py", "Z = 1\n", "[T1] alpha, reaching into src/b")
        self.repo.edit(PLAN, "writes: src/a/**, tests/**", "writes: src/a/**, src/b/**, tests/**")
        self.repo.edit(PLAN, "- 2026-01-01: fixture decision.\n", "- 2026-01-01: fixture decision.\n- widen T1.\n")
        self.repo.commit("F-9: widen T1 writes")
        self.assertRowOk(3)
        self.assertRow(4, f"{sha[:10]} [T1] src/b/z.py outside writes")

    def test_temporary_widening_cannot_authorize_protected_edits(self):
        self.repo.edit(PLAN, "writes: src/a/**, tests/**", "writes: src/a/**, docs/design.md, tests/**")
        self.repo.edit(PLAN, "- 2026-01-01: fixture decision.\n", "- 2026-01-01: fixture decision.\n- widen T1.\n")
        self.repo.commit("F-9: widen T1 to the design")
        sha = self.fix("docs/design.md", "# design, rewritten\n", "[T1] alpha rewrites the design")
        self.repo.edit(PLAN, "writes: src/a/**, docs/design.md, tests/**", "writes: src/a/**, tests/**")
        self.repo.edit(PLAN, "- widen T1.\n", "- widen T1.\n- narrow T1 again.\n")
        self.repo.commit("F-9: narrow T1 again")
        self.assertRowOk(3)
        self.assertRow(4, f"{sha[:10]} [T1] changes protected docs/design.md")

    def test_plan_only_cannot_expand_test_permissions(self):
        self.repo.edit(PLAN, "tests-may-change: tests/test_a.py", "tests-may-change: **")
        sha = self.repo.commit("F-9: let T2 change every test")
        self.assertRow(3, f"{sha[:10]} changes a task field without adding a Decisions line")
        self.repo.git("reset", "-q", "--hard", "HEAD~1")
        self.repo.edit(PLAN, "tests-may-change: tests/test_a.py", "tests-may-change: **")
        self.repo.edit(PLAN, "- 2026-01-01: fixture decision.\n",
                       "- 2026-01-01: fixture decision.\n- T2 may change every test.\n")
        sha = self.repo.commit("F-9: let T2 change every test, with a decision")
        self.assertRowOk(3)
        self.repo.goal("packet")
        packet = self.repo.read(".runs/F-9/packet.md")
        self.assertIn(f"{sha[:10]} T2 tests-may-change: tests/test_a.py -> **", packet)
        self.assertIn("Widenings", packet)

    def test_changing_a_task_gate_needs_a_decisions_line(self):
        self.repo.edit(PLAN, "tests-may-change: tests/test_a.py\n", "tests-may-change: tests/test_a.py\ngate: make beta\n")
        sha = self.repo.commit("F-9: give T2 its own gate")
        self.assertRow(3, f"{sha[:10]} changes a task field without adding a Decisions line")
        self.repo.git("reset", "-q", "--hard", "HEAD~1")
        self.repo.edit(PLAN, "tests-may-change: tests/test_a.py\n", "tests-may-change: tests/test_a.py\ngate: make beta\n")
        self.repo.edit(PLAN, "- 2026-01-01: fixture decision.\n",
                       "- 2026-01-01: fixture decision.\n- T2 runs its own gate.\n")
        sha = self.repo.commit("F-9: give T2 its own gate, with a decision")
        self.assertRowOk(3)
        self.repo.goal("packet")
        self.assertIn(f"{sha[:10]} T2 gate: (none) -> make beta", self.repo.read(".runs/F-9/packet.md"))

    def test_row5_names_an_added_skip_marker(self):
        text = self.repo.read("tests/test_a.py").replace("    def test_flag", SKIP_DECORATOR + "    def test_flag")
        self.fix("tests/test_a.py", text, "[T2] beta")  # T2 may change tests/test_a.py
        self.assertRow(5, "adds a skip/only/xfail marker in tests/test_a.py")

    def test_row5_rejects_imported_skip_and_spaced_only(self):
        at = "@"  # assembled so this file does not itself add the markers row 5 rejects
        for line in (f"{at}skip('later')", f"{at}skipIf(True, 'x')", f"{at}skipUnless (False, 'x')",
                     f"{at}expectedFailure", "test.only" + " ('case', fn)", "it.skip" + " ('case', fn)",
                     "describe.only" + "\t('suite', fn)"):
            self.assertTrue(goal.SKIP_RE.search(line), line)
        for line in ("def skipper(self):", "only = 1", "x.onlyone(1)"):
            self.assertFalse(goal.SKIP_RE.search(line), line)
        text = ("from unittest import " + "skip\n" + self.repo.read("tests/test_a.py")
                .replace("    def test_flag", f"    {at}skip('later')\n    def test_flag"))
        self.fix("tests/test_a.py", text, "[T2] beta")
        self.assertRow(5, "adds a skip/only/xfail marker in tests/test_a.py")

    def test_row5_rejects_spaced_and_imported_skip_calls(self):
        # Each call is assembled so this file does not itself add the marker row 5 rejects.
        for line in ("pytest.skip" + ' ("later")', "self.skipTest" + ' ("later")', "pytest.xfail" + "\t('x')"):
            self.assertTrue(goal.SKIP_RE.search(line), line)
        base = self.repo.read("tests/test_a.py")
        for head, call in (("", "pytest.skip" + ' ("later")'), ("", "self.skipTest" + ' ("later")'),
                           ("from pytest import " + "skip\n", "skip" + '("later")'),
                           ("from unittest import (\n    " + "skip,\n)\n", "skip" + ' ("later")')):
            text = head + base.replace("        self.assertFalse", f"        {call}\n        self.assertFalse")
            self.fix("tests/test_a.py", text, "[T2] beta")
            self.assertRow(5, "adds a skip/only/xfail marker in tests/test_a.py")
            self.repo.git("reset", "-q", "--hard", "HEAD~1")
        self.fix("tests/test_a.py", base.replace("    def test_flag", "    def skip(self):\n        pass\n\n"
                                                 "    def test_flag"), "[T2] beta, a helper named like a skip")
        self.assertRowOk(5)

    def test_row5_names_a_test_modified_outside_tests_may_change(self):
        self.fix("tests/test_a.py", self.repo.read("tests/test_a.py") + "\n", "[T1] alpha")
        self.assertRow(5, "modifies test tests/test_a.py")

    def test_row6_names_an_outcome_edit(self):
        self.repo.edit(PLAN, "The fixture does two things.", "The fixture does one thing.")
        self.repo.commit("[T1] alpha")
        self.assertRow(6, "changed outside ticks")

    def test_outcome_field_like_lines_remain_frozen(self):
        self.repo.edit(PLAN, "The fixture does two things.\n",
                       "The fixture does two things.\nwrites: must preserve customer records\n")
        self.repo.commit("F-9: approve an outcome with a field-like line")
        self.repo.git("tag", "-f", "goal/F-9/approved")
        self.repo.edit(PLAN, "writes: must preserve", "writes: may erase")
        sha = self.repo.commit("F-9: reword the outcome")
        self.assertRow(3, f"{sha[:10]} names 0 tasks and is not plan-only")
        self.assertRow(6, "changed outside ticks")
        before = goal.frozen_view(plan_text())
        self.assertEqual(goal.frozen_view(plan_text().replace("writes: src/a/**", "writes: src/a/**, src/z/**")),
                         before)

    def test_row7_receipt_must_name_heads_tree(self):
        self.repo.close()
        path = receipt_path(self.repo.dir, "F-9", self.repo.tree(), FULL)
        good = path.read_text()
        path.write_text(json.dumps({**json.loads(good), "tree": "0" * 40}))
        self.assertRow(7, "no PASS full_gate receipt")
        path.write_text(good)
        self.assertRowOk(7)


class SharedReceiptTest(RepoCase):
    """A milestone whose e2e is the full_gate command needs one run: receipts are keyed by command."""
    plan = plan_text().replace(f'M1: {{tasks: [T1, T2], e2e: "{E2E}"}}', f'M1: {{tasks: [T1, T2], e2e: "{FULL}"}}')

    def test_one_full_gate_receipt_satisfies_both_row7_receipts(self):
        self.repo.write("src/a/x.py", "A = 1\n")
        self.repo.tick("T1")
        self.repo.commit("[T1] alpha")
        self.repo.write("src/b/y.py", "B = 1\n")
        self.repo.tick("T2")
        self.repo.commit("[T2] beta")
        self.repo.review("No findings.\n")
        self.assertRow(7, "no PASS full_gate receipt")
        res = self.repo.receipt(FULL, "full_gate")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertRowOk(7)


RECORD = ("# Record\n\n## D1 — first\n\nOne.\n\n### detail\n\nInside D1.\n\n## D2 — second\n\nTwo.\n\n"
          "## D3 — third\n\nThree.\n")


class ProtectedSectionTest(RepoCase):
    plan = (plan_text().replace("protected: [docs/design.md]", "protected: [docs/design.md, docs/record.md#D1-D2]")
            .replace("writes: src/a/**, tests/**", "writes: src/a/**, docs/record.md, tests/**"))

    def setUp(self):
        self.repo = Repo(self.plan, files={"docs/record.md": RECORD})
        self.addCleanup(self.repo.cleanup)

    def test_protected_section_edit_is_rejected(self):
        self.assertEqual(self.repo.goal("lint").returncode, 0)
        self.fix("docs/record.md", RECORD.replace("Three.", "Three, revised."), "[T1] outside the range")
        self.assertRowOk(4)
        sha = self.fix("docs/record.md", self.repo.read("docs/record.md").replace("Inside D1.", "Changed."),
                       "[T1] inside D1")
        self.assertRow(4, f"{sha[:10]} [T1] changes protected docs/record.md#D1-D2")
        self.assertEqual(goal.protected_text(RECORD, "D2"), "## D2 — second\n\nTwo.\n")
        self.assertEqual(goal.protected_text(RECORD, "whole"), RECORD.rstrip("\n"))


class SpecLintTest(RepoCase):
    """A v7.1 goal: the fixture goal with spec.md and design.md, T1 may write the design."""
    plan = plan_text(v71=True).replace("writes: src/a/**, tests/**", f"writes: src/a/**, {DESIGN_PATH}, tests/**")

    def setUp(self):
        self.repo = Repo(self.plan, files=V71_FILES)
        self.addCleanup(self.repo.cleanup)

    def assertLint(self, code, *texts):
        res = self.repo.goal("lint")
        self.assertEqual(res.returncode, code, res.stdout + res.stderr)
        for text in texts:
            self.assertIn(text, res.stdout)
        return res.stdout

    def test_the_v71_fixture_lints_clean_and_prints_reads(self):
        self.assertLint(0, f"T1 reads: {DESIGN_PATH}#interfaces", f"T3 reads: {DESIGN_PATH}#interfaces")

    def test_a_task_without_reads_fails_lint(self):
        self.repo.edit(PLAN, f"writes: src/c/**\nreads: {DESIGN_PATH}#interfaces\n", "writes: src/c/**\n")
        out = self.assertLint(1, "T3: writes and no reads")
        self.assertNotIn("T1: writes and no reads", out)

    def test_a_new_goal_without_a_spec_fails_lint(self):
        self.repo.path(SPEC_PATH).unlink()
        self.repo.git("tag", "-d", "goal/F-9/approved")
        self.assertLint(1, "no spec.md and no approval tag")

    def test_deleting_an_approved_spec_fails_lint(self):
        self.repo.path(SPEC_PATH).unlink()
        self.assertLint(1, f"{SPEC_PATH}: in the approved commit, missing from the tree")

    def test_a_401_word_spec_fails_lint(self):
        pad = " word" * (400 - len(SPEC.split()))
        self.repo.write(SPEC_PATH, SPEC.replace("Standard-library Python.", "Standard-library Python." + pad))
        self.assertLint(0)
        self.repo.write(SPEC_PATH, SPEC.replace("Standard-library Python.", "Standard-library Python. word" + pad))
        self.assertLint(1, "spec.md: 401 words, over 400")

    def test_a_spec_missing_non_goals_fails_lint(self):
        self.repo.write(SPEC_PATH, SPEC.replace("**Non-goals.** Gamma.\n\n", ""))
        out = self.assertLint(1, "spec.md: no Non-goals heading")
        self.assertNotIn("no Constraints heading", out)
        criteria = SPEC[SPEC.index("- AC1"):SPEC.index("\n\n**Non-goals")]
        self.repo.write(SPEC_PATH, f"What changes for the user: nothing\n{criteria}\n")
        self.assertLint(0)

    def test_abbreviated_spec_without_tests_fails_lint(self):
        self.repo.write(SPEC_PATH, "What changes for the user: nothing.\n")
        self.assertLint(1, "spec.md: two-line form with no criteria line")
        self.repo.write(SPEC_PATH, "What changes for the user: nothing\nAcceptance criteria: tests/test_a.py::test_alpha\n")
        self.assertLint(0)

    def test_touches_an_interface_without_a_design_fails_lint(self):
        self.repo.path(DESIGN_PATH).unlink()
        self.assertLint(1, "touches: [interface] without design.md")
        self.repo.edit(PLAN, "touches: [interface]", "touches: [none]")
        self.assertLint(0)
        self.repo.edit(PLAN, "touches: [none]", "touches: [none, sideways]")
        self.assertLint(1, "touches: unknown value 'sideways'")

    def test_mapping_touches_fails_lint(self):
        self.repo.edit(PLAN, "touches: [interface]", "touches: {kind: interface}")
        self.assertLint(1, "touches: {'kind': 'interface'} is not a list")

    def test_an_untraced_ac_fails_lint(self):
        self.repo.write(SPEC_PATH, SPEC.replace("\n\n**Non-goals.**", "\n- AC3 WHEN gamma runs THE SYSTEM SHALL do it."
                                                "\n\n**Non-goals.**"))
        out = self.assertLint(1, "AC3: in no task")
        self.assertNotIn("AC1: in no task", out)

    def test_a_reads_change_in_a_plan_only_commit_needs_a_decision(self):
        old, new = f"reads: {DESIGN_PATH}#interfaces", f"reads: {DESIGN_PATH}#interfaces, src/b/**"
        self.repo.edit(PLAN, old, new)  # the first reads: line is T1's
        sha = self.repo.commit("F-9: T1 reads beta")
        self.assertRow(3, f"{sha[:10]} changes a task field without adding a Decisions line")
        self.repo.git("reset", "-q", "--hard", "HEAD~1")
        self.repo.edit(PLAN, old, new)
        self.repo.edit(PLAN, "- 2026-01-01: fixture decision.\n", "- 2026-01-01: fixture decision.\n- T1 reads beta.\n")
        sha = self.repo.commit("F-9: T1 reads beta, with a decision")
        self.assertRowOk(3)
        self.repo.goal("packet")
        packet = self.repo.read(".runs/F-9/packet.md")
        self.assertIn(f"{sha[:10]} T1 reads: {DESIGN_PATH}#interfaces -> {DESIGN_PATH}#interfaces, src/b/**", packet)
        self.assertIn(f"T1 reads: {DESIGN_PATH}#interfaces, src/b/**\n", packet)

    def test_row4_reports_a_spec_edit_that_protected_does_not_list(self):
        self.assertEqual(goal.parse_plan(self.plan)["meta"]["protected"], ["docs/design.md"])
        sha = self.fix(SPEC_PATH, SPEC.replace("Gamma.", "Gamma and delta."), "[T1] alpha edits the spec")
        self.assertRow(4, f"{sha[:10]} [T1] changes protected {SPEC_PATH}")

    def test_row4_protects_the_designs_interfaces_and_data_touched_sections_only(self):
        self.fix(DESIGN_PATH, DESIGN.replace("One file.", "Two files."), "[T1] outside the protected sections")
        self.assertRowOk(4)
        sha = self.fix(DESIGN_PATH, self.repo.read(DESIGN_PATH).replace("Inside the Interfaces", "Inside, changed,"),
                       "[T1] inside a subsection of Interfaces")
        self.assertRow(4, f"{sha[:10]} [T1] changes protected {DESIGN_PATH}#interfaces")
        self.assertNotIn("#data-touched", self.done()[1]["row 4"])
        self.assertEqual(goal.protected_text(DESIGN, "data-touched"), "## Data touched\n\nNothing in a store.\n")
        self.assertEqual(goal.protected_text(DESIGN, "interfaces"), DESIGN[DESIGN.index("## Interfaces"):
                                                                          DESIGN.index("## Data")].rstrip("\n") + "\n")


    def test_slug_is_docs_pys_rule(self):
        import docs
        self.assertEqual(goal.slug("D18: Other, thing!"), docs.slug("D18: Other, thing!"))
        self.assertNotIn('re.sub(r"[`*_~]"', Path(goal.__file__).read_text(encoding="utf-8"))

    def test_row4_protects_interfaces_after_fenced_heading(self):
        design = DESIGN.replace("1. **alpha.** One function.\n",
                                "1. **alpha.** One function.\n\n~~~\n## Example\n~~~\n\nContract text.\n")
        self.assertIn("Contract text.", goal.protected_text(design, "interfaces"))
        self.fix(DESIGN_PATH, design, "[T1] a fenced example inside Interfaces")
        sha = self.fix(DESIGN_PATH, design.replace("Contract text.", "Changed contract."),
                       "[T1] edits the text after the fenced heading")
        self.assertRow(4, f"{sha[:10]} [T1] changes protected {DESIGN_PATH}#interfaces")


    def test_approval_page_renders_spec_design_tasks_and_questions(self):
        self.repo.write(PLAN, self.plan + "\n- Q: Should gamma <wait> for beta?\n")
        res = self.repo.goal("packet", "--approval")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertEqual(res.stdout.strip(), str(self.repo.path(".runs/F-9/approval.html")))
        self.assertFalse(self.repo.path(".runs/F-9/packet.md").exists())
        page = self.repo.read(".runs/F-9/approval.html")
        self.assertIn("<title>F-9 approval</title>", page)
        self.assertIn("The fixture user has two problems.", page)
        self.assertIn("<li>AC1 WHEN alpha runs THE SYSTEM SHALL do the alpha work.</li>", page)
        self.assertIn("1. **alpha.** One function.", page)
        self.assertIn("Inside the Interfaces section.", page)
        self.assertNotIn("Nothing in a store.", page)
        for tid in ("T1", "T2", "T3"):
            self.assertRegex(page, rf"<tr><td>{tid} [^\n]*{re.escape(DESIGN_PATH)}#interfaces")
        self.assertRegex(page, r"<tr><td>T2 [^\n]*<td>tests/test_a.py</td></tr>")  # no test named: its files
        self.assertIn("touches: interface", page)
        self.assertIn("protected: docs/design.md", page)
        self.assertIn("<li>Q: Should gamma &lt;wait&gt; for beta?</li>", page)
        self.assertNotIn("<wait>", page)


    def test_approval_page_preserves_explicit_named_tests(self):
        plan = self.plan.replace("Do the alpha AC1 work.", "`tests/test_a.py` gains `test_alpha_adds_the_module`.")
        plan = plan.replace("Do the gamma work.", "Named test: tests/test_a.py::ATest.test_gamma_wires_it; see tests/test_b.py.")
        self.repo.write(PLAN, plan)
        res = self.repo.goal("packet", "--approval")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        page = self.repo.read(".runs/F-9/approval.html")
        self.assertRegex(page, r"<tr><td>T1 [^\n]*<td>test_alpha_adds_the_module</td></tr>")
        self.assertRegex(page, r"<tr><td>T3 [^\n]*<td>test_gamma_wires_it</td></tr>")
        self.assertNotRegex(page, r"<td>test_a</td>|<td>test_b</td>")


class ReviewRowTest(RepoCase):
    def setUp(self):
        super().setUp()
        self.repo.close()

    def test_a_non_fix_commit_after_reviewed_is_named(self):
        sha = self.fix("src/b/w.py", "W = 1\n", "[T2] more beta")
        self.assertRow(8, f"{sha[:10]} after reviewed: is neither a fix commit")

    def test_row8_accepts_plan_only_commit_after_review(self):
        self.repo.edit(PLAN, "- 2026-01-01: fixture decision.\n", "- 2026-01-01: fixture decision.\n- reviewed.\n")
        self.repo.commit("F-9: record the review verdict")
        self.assertRowOk(8)
        self.repo.edit(PLAN, "- reviewed.\n", "- reviewed.\n- again.\n")
        self.repo.write("docs/design.md", "# design, edited\n")
        sha = self.repo.commit("F-9: a decision and a design edit")
        self.assertRow(8, f"{sha[:10]} after reviewed: is neither a fix commit named by a closed finding nor plan-only")

    def test_checked_blocker_requires_closure(self):
        self.repo.review("- [x] BLOCKING R1 defect still present\n")
        self.assertRow(8, "R1: checked BLOCKING without a resolved-by or removed-by closure")
        self.repo.write("tests/test_b_value.py", "import unittest\n\n\nclass V(unittest.TestCase):\n"
                        "    def test_beta_value(self):\n        self.assertTrue(True)\n")
        sha = self.fix("src/b/y.py", "B = 2\n", "[T2][R1] fix the beta value")
        self.repo.review(f"- [x] BLOCKING R1 defect fixed\n"
                         f"- [x] R1 resolved-by {sha} closes tests/test_b_value.py::test_beta_value\n", "HEAD~1")
        self.assertRowOk(8)

    def test_a_fix_without_a_changed_closing_test_is_named(self):
        sha = self.fix("src/b/y.py", "B = 2\n", "[T2][R1] fix the beta value")
        self.repo.review(f"- [x] R1 resolved-by {sha} closes tests/test_a.py::test_value\n", "HEAD~1")
        self.assertRow(8, "R1: closes tests/test_a.py::test_value")

    def test_a_fix_whose_closing_test_changed_in_it_passes(self):
        self.repo.write("tests/test_b_value.py", "import unittest\n\n\nclass V(unittest.TestCase):\n"
                        "    def test_beta_value(self):\n        self.assertTrue(True)\n")
        sha = self.fix("src/b/y.py", "B = 2\n", "[T2][R1] fix the beta value")
        self.repo.review(f"- [x] R1 resolved-by {sha} closes tests/test_b_value.py::test_beta_value\n", "HEAD~1")
        self.assertRowOk(8)

    def test_closure_rejects_non_test_text(self):
        self.repo.write("README.md", "# test_security is still TODO\n")
        self.repo.write("tests/test_notes.py", "# test_security is still TODO\n")
        self.repo.write("tests/test_c.js", "test('security holds', () => {});\n")
        sha = self.fix("src/b/y.py", "B = 2\n", "[T2][R1] claim a fix")
        for target in ("README.md::test_security", "tests/test_notes.py::test_security"):
            self.repo.review(f"- [x] R1 resolved-by {sha} closes {target}\n", "HEAD~1")
            self.assertRow(8, f"R1: closes {target}")
        self.repo.review(f"- [x] R1 resolved-by {sha} closes tests/test_c.js::security\n", "HEAD~1")
        self.assertRow(8, "R1: closes tests/test_c.js::security")

    def test_closure_requires_an_exact_discoverable_test(self):
        self.repo.write("tests/test_c.js", "test('security holds', () => {});\n")
        self.repo.write("tests/test_e.js", 'it("exact", () => {});\n')
        self.repo.write("tests/test_d.py", "import unittest\n\n\ndef helper_check():\n    pass\n\n\n"
                        "class Guard(unittest.TestCase):\n    def test_guard(self):\n        helper_check()\n\n\n"
                        "class Other(unittest.TestCase):\n    async def test_other(self):\n        pass\n")
        sha = self.fix("src/b/y.py", "B = 2\n", "[T2][R1] fix with tests")
        for target in ("tests/test_c.js::security", "tests/test_d.py::helper_check",
                       "tests/test_d.py::Other.test_guard", "tests/test_d.py::Guard.test_missing"):
            self.repo.review(f"- [x] R1 resolved-by {sha} closes {target}\n", "HEAD~1")
            self.assertRow(8, f"R1: closes {target}")
        for target in ("tests/test_e.js::exact", "tests/test_d.py::test_guard", "tests/test_d.py::Guard.test_guard",
                       "tests/test_d.py::Other::test_other"):
            self.repo.review(f"- [x] R1 resolved-by {sha} closes {target}\n", "HEAD~1")
            self.assertRowOk(8)

    def test_closure_accepts_an_annotated_junit_method(self):
        off, ign = "@" + "Disabled", "@" + "Ignore"  # assembled so this file adds no marker row 5 rejects
        java = lambda body, head="class Outer": f"import org.junit.jupiter.api.*;\n\n{head} {{\n    {body}\n}}\n"  # noqa: E731
        kotlin = lambda body: f"import org.junit.jupiter.api.Test\n\nclass Outer {{\n    {body}\n}}\n"  # noqa: E731
        accepted = {
            "Plain.java": java("@Test void m() {}"),
            "Qualified.java": java("@org.junit.jupiter.api.Test void m() {}"),
            "JUnit4.java": java("@org.junit.Test public void m() {}"),
            "Params.java": java("@ParameterizedTest @ValueSource(ints = {1, 2})\n    void m(int x) {}"),
            "Between.java": java('@Test @Timeout(5) @DisplayName("a (b)")\n    void m() {}'),
            "Throws.java": java("@Test void m() throws Exception {}"),
            "Factory.java": java("@TestFactory Stream<DynamicTest> m() { return Stream.empty(); }"),
            "Nested.java": java("@Nested\n    class Inner {\n        @Test void m() {}\n    }"),
            "Plain.kt": kotlin("@Test fun m() {}"),
            "Expression.kt": kotlin("@Test fun m() = runTest {}"),
        }
        refused = {
            "Bare.java": java("void m() {}"),
            "Off.java": java(f"@Test {off} void m() {{}}"),
            "OffOnOs.java": java(f"@Test {off}OnOs(OS.WINDOWS) void m() {{}}"),
            "OffClass.java": java("@Test void m() {}", f"{off}\nclass Outer"),
            "Ignored.java": java(f"{ign} @org.junit.Test public void m() {{}}"),
            "OtherNamespace.java": java("@org.testng.annotations.Test public void m() {}"),
            "Abstract.java": java("@Test abstract void m();", "abstract class Outer"),
            "Interface.java": java("@Test void m();", "interface Outer"),
            "Unmarked.java": java("class Inner {\n        @Test void m() {}\n    }"),
            "Private.java": java("@Test private void m() {}"),
            "Static.java": java("@Test static void m() {}"),
            "LineComment.java": java("// @Test void m() {}"),
            "BlockComment.java": java("/* @Test void m() {} */"),
            "String.java": java('String s = "@Test void m() {}";'),
            "TextBlock.java": java('String s = """\n        @Test void m() {}\n        """;'),
            "Raw.kt": kotlin('val s = """@Test fun m() {}"""'),
            "Previous.java": java("@Test void other() {}\n    void m() {}"),
            "Suffix.java": java("@Test void m2() {}"),
            "Prefix.java": java("@Test void xm() {}"),
        }
        for name, text in {**accepted, **refused}.items():
            self.repo.write(f"tests/junit/{name}", text)
        sha = self.fix("src/b/y.py", "B = 2\n", "[T2][R1] fix with JUnit tests")
        for name in accepted:
            self.repo.review(f"- [x] R1 resolved-by {sha} closes tests/junit/{name}::m\n", "HEAD~1")
            self.assertRowOk(8)
        for target in [f"tests/junit/{n}::m" for n in refused] + ["tests/junit/Plain.java::Outer.m",
                                                                   "tests/junit/Plain.java::Outer::m"]:
            self.repo.review(f"- [x] R1 resolved-by {sha} closes {target}\n", "HEAD~1")
            self.assertRow(8, f"R1: closes {target}")

    def assertJunitClosures(self, accepted, refused):
        """Writes each tests/junit/<file> as a JUnit import, then <head> { <body> }: a str value is the body
        of class Outer, a pair is (head, body). A closure naming <file>::m holds for each accepted file only."""
        for name, value in {**accepted, **refused}.items():
            head, body = value if isinstance(value, tuple) else ("class Outer", value)
            imports = "import org.junit.jupiter.api.*" + ("" if name.endswith(".kt") else ";")
            self.repo.write(f"tests/junit/{name}", f"{imports}\n\n{head} {{\n    {body}\n}}\n")
        sha = self.fix("src/b/y.py", "B = 2\n", "[T2][R1] fix with JUnit tests")
        for name in accepted:
            self.repo.review(f"- [x] R1 resolved-by {sha} closes tests/junit/{name}::m\n", "HEAD~1")
            self.assertRowOk(8)
        for name in refused:
            self.repo.review(f"- [x] R1 resolved-by {sha} closes tests/junit/{name}::m\n", "HEAD~1")
            self.assertRow(8, f"R1: closes tests/junit/{name}::m")

    def test_closure_rejects_nested_kotlin_comment(self):
        self.assertJunitClosures(
            {"After.kt": "/* outer /* inner */ still outer */ @Test fun m() {}",
             "Flat.java": "/* outer /* not nested in Java */ @Test void m() {}"},
            {"Inside.kt": "/* outer /* inner */ @Test fun m() {} */"})

    def test_closure_accepts_explicit_kotlin_return_type(self):
        self.assertJunitClosures(
            {"Unit.kt": "@Test fun m(): Unit {}",
             "UnitExpression.kt": "@Test fun m(): Unit = runTest {}",
             "Repeated.kt": "@RepeatedTest(2) fun m(): Unit {}",
             "Params.kt": "@ParameterizedTest @ValueSource(ints = [1, 2])\n    fun m(x: Int): Unit {}",
             "Template.kt": "@TestTemplate fun m(): Unit {}",
             "Factory.kt": "@TestFactory fun m(): Collection<DynamicTest> = listOf()"},
            {"Bodiless.kt": ("abstract class Outer", "@Test abstract fun m(): Unit"),
             "Unannotated.kt": "fun m(): Unit {}"})

    def test_closure_accepts_multiline_kotlin_class_header(self):
        self.assertJunitClosures(
            {"Newline.kt": ("class Outer\n", "@Test fun m() {}"),
             "Colon.kt": ("class Outer\n    : Base()\n", "@Test fun m() {}"),
             "Supertypes.kt": ("class Outer(val x: Int = 1) :\n    Base(),\n    Marker\n", "@Test fun m() {}"),
             "Inner.kt": "@Nested\n    inner class Inner\n    {\n        @Test fun m() {}\n    }",
             "Sibling.kt": "class Data(val x: Int)\n    @Test fun m() {}",
             "Newline.java": ("class Outer\n    extends Base\n    implements Marker\n", "@Test void m() {}")},
            {"Object.kt": ("object Outer\n", "@Test fun m() {}"),
             "Interface.kt": ("interface Outer\n    : Base\n", "@Test fun m() {}")})

    def test_closure_rejects_static_nested_junit_class(self):
        self.assertJunitClosures(
            {"Inner.java": "@Nested final class Inner {\n        @Test void m() {}\n    }",
             "Inner.kt": "@Nested\n    inner class Inner {\n        @Test fun m() {}\n    }"},
            {"Static.java": "@Nested static class Inner {\n        @Test void m() {}\n    }",
             "Deep.java": "@Nested static class A {\n        @Nested class B { @Test void m() {} }\n    }",
             "Static.kt": "@Nested\n    class Inner {\n        @Test fun m() {}\n    }"})

    def test_closure_rejects_unrunnable_junit_class_modifiers(self):
        self.assertJunitClosures(
            {"Public.java": ("public final class Outer", "@Test void m() {}"),
             "Protected.java": "@Nested protected class Inner {\n        @Test void m() {}\n    }",
             "Open.kt": ("open class Outer", "@Nested internal inner class Inner {\n        @Test fun m() {}\n    }")},
            {"Abstract.java": ("abstract class Outer", "@Test void m() {}"),
             "Private.java": "@Nested private class Inner {\n        @Test void m() {}\n    }",
             "Abstract.kt": ("abstract class Outer", "@Test fun m() {}"),
             "Sealed.kt": ("sealed class Outer", "@Test fun m() {}"),
             "Private.kt": ("private class Outer", "@Test fun m() {}"),
             "PrivateInner.kt": "@Nested private inner class Inner {\n        @Test fun m() {}\n    }"})

    def test_closure_rejects_nonvoid_junit_test(self):
        self.assertJunitClosures(
            {"Void.java": "@Test void m() {}",
             "Template.java": "@TestTemplate public void m() {}",
             "Factory.java": "@TestFactory Stream<DynamicTest> m() { return Stream.empty(); }",
             "Unit.kt": "@Test fun m(): Unit {}",
             "Expression.kt": "@Test fun m() = runTest {}",
             "Factory.kt": "@TestFactory fun m(): List<DynamicTest> { return listOf() }"},
            {"Int.java": "@Test int m() { return 1; }",
             "Repeated.java": "@RepeatedTest(2) String m() { return null; }",
             "Params.java": "@ParameterizedTest @ValueSource(ints = {1})\n    Object m(int x) { return x; }",
             "VoidFactory.java": "@TestFactory void m() {}",
             "Both.java": "@Test @TestFactory Stream<DynamicTest> m() { return null; }",
             "Int.kt": "@Test fun m(): Int = 1",
             "UnitFactory.kt": "@TestFactory fun m() {}",
             "UntypedFactory.kt": "@TestFactory fun m() = listOf<DynamicTest>()"})

    def test_closure_requires_a_post_review_ancestor_fix(self):
        old = self.repo.git("rev-parse", "goal/F-9/approved")  # it added tests/test_a.py::test_value
        self.repo.review(f"- [x] BLOCKING R1 defect\n- [x] R1 resolved-by {old} closes tests/test_a.py::test_value\n")
        self.assertRow(8, f"R1: {old} is not a fix made after reviewed:")
        self.repo.git("checkout", "-q", "-b", "side")
        side = self.fix("tests/test_a.py", self.repo.read("tests/test_a.py") + "\n", "[T2][R1] fix on a side branch")
        self.repo.git("checkout", "-q", "main")
        self.repo.review(f"- [x] BLOCKING R1 defect\n- [x] R1 resolved-by {side} closes tests/test_a.py::test_value\n")
        self.assertRow(8, f"R1: {side} is not a fix made after reviewed:")
        head = self.repo.git("rev-parse", "HEAD")
        self.repo.review(f"- [x] BLOCKING R1 defect\n- [x] R1 resolved-by {head} closes tests/test_a.py::test_value\n")
        self.assertRow(8, f"R1: {head} is not a fix made after reviewed:")
        fix = self.fix("tests/test_a.py", self.repo.read("tests/test_a.py") + "\n", "[T2][R1] fix after the review")
        self.repo.review(f"- [x] BLOCKING R1 defect\n- [x] R1 resolved-by {fix} closes tests/test_a.py::test_value\n",
                         "HEAD~1")
        self.assertRowOk(8)

    def test_removed_by_passes_when_the_paths_are_deleted(self):
        self.repo.git("rm", "-q", "src/b/y.py")
        sha = self.repo.commit("[T2][R1] remove the beta file")
        self.repo.review(f"- [x] R1 removed-by {sha[:8]}\n  paths: src/b/y.py\n", "HEAD~1")
        self.assertRowOk(8)
        self.repo.review(f"- [x] R1 removed-by {sha[:8]}\n  paths: src/a/x.py\n", "HEAD~1")
        self.assertRow(8, "does not remove or change")

    def test_removed_by_rejects_addition_only_modification(self):
        sha = self.fix("src/b/y.py", "B = 1\nUNRELATED = 1\n", "[T2][R1] add beside the defect")
        self.repo.review(f"- [x] R1 removed-by {sha[:8]}\n  paths: src/b/y.py\n", "HEAD~1")
        self.assertRow(8, f"R1: {sha[:8]} does not remove or change the finding's paths")
        self.repo.git("reset", "-q", "--hard", "HEAD~1")
        sha = self.fix("src/b/y.py", "", "[T2][R1] remove the defective line")
        self.repo.review(f"- [x] R1 removed-by {sha[:8]}\n  paths: src/b/*.py\n", "HEAD~1")
        self.assertRowOk(8)

    def test_an_open_blocking_finding_is_named(self):
        self.repo.review("- [ ] BLOCKING R2 the beta value is wrong\n")
        self.assertRow(8, "open - [ ] BLOCKING")

    def test_a_missing_review_is_named(self):
        (self.repo.dir / ".runs/F-9/review.md").unlink()
        self.assertRow(8, "no .runs/F-9/review.md")


    def test_packet_counts_causes_over_closed_blocking_findings(self):
        sha = self.repo.git("rev-parse", "HEAD")
        self.repo.review(f"- [x] BLOCKING R1 the alpha value is wrong\n"
                         f"- [x] R1 resolved-by {sha} closes tests/test_a.py::test_value cause: logic\n"
                         f"- [x] BLOCKING R2 the beta file is unneeded\n"
                         f"- [x] R2 removed-by {sha} cause: context\n  paths: src/b/y.py\n"
                         f"- [x] R3 a naming nit\n"
                         f"- [x] R3 resolved-by {sha} closes tests/test_a.py::test_flag cause: spec\n", "HEAD~1")
        res = self.repo.goal("packet")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("cause: context 1, logic 1, spec 0\n", self.repo.read(".runs/F-9/packet.md"))


def jsonl(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


class FixtureTest(unittest.TestCase):
    def test_fixture_runs_use_a_scratch_home(self):
        e = env()
        self.assertNotEqual(Path(e["HOME"]).resolve(), Path.home().resolve())
        self.assertTrue(Path(e["CODEX_HOME"]).is_relative_to(e["HOME"]))
        self.assertNotEqual(e["CODEX_HOME"], os.environ.get("CODEX_HOME"))
        self.assertEqual(env(HOME="/elsewhere")["HOME"], "/elsewhere")


class CostTest(RepoCase):
    """Transcripts planted under a scratch HOME and CODEX_HOME; the numbers are synthetic."""

    def setUp(self):
        super().setUp()
        self.home = Path(tempfile.mkdtemp(prefix="goal-home-"))
        self.addCleanup(shutil.rmtree, self.home, True)
        self.codex = self.home / "codex"
        approved = datetime.fromisoformat(self.repo.git("log", "-1", "--format=%cI", "goal/F-9/approved"))
        self.before, self.after = (
            (approved + timedelta(hours=h)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z") for h in (-24, 1))

    def cost(self, *args):
        return self.repo.goal(*args, HOME=str(self.home), CODEX_HOME=str(self.codex))

    def plant(self):
        slug = re.sub(r"[^A-Za-z0-9]", "-", str(self.repo.dir))
        usage = lambda i, c, r, o: {"input_tokens": i, "cache_creation_input_tokens": c,  # noqa: E731
                                    "cache_read_input_tokens": r, "output_tokens": o}
        msg = lambda t, mid, u: {"type": "assistant", "timestamp": t, "message": {"id": mid, "usage": u}}  # noqa: E731
        jsonl(self.home / ".claude" / "projects" / slug / "s1.jsonl", [
            {"type": "user", "timestamp": self.after, "message": {"role": "user"}},
            msg(self.before, "m0", usage(1000, 1000, 1000, 1000)),
            msg(self.after, "m1", usage(10, 20, 30, 5)),
            msg(self.after, "m1", usage(10, 20, 30, 5)),  # the same response's next content block
            msg(self.after, "m2", usage(1, 2, 3, 4))])
        jsonl(self.home / ".claude" / "projects" / slug / "s1" / "subagents" / "agent-x.jsonl", [
            msg(self.after, "m3", usage(100, 200, 300, 40)),
            msg(self.after, "m2", usage(1, 2, 3, 4))])  # the top-level file's m2 again: counted once
        jsonl(self.home / ".claude" / "projects" / "-elsewhere" / "s2.jsonl", [msg(self.after, "m9", usage(7, 7, 7, 7))])
        meta = lambda cwd: {"type": "session_meta", "timestamp": self.before, "payload": {"cwd": cwd}}  # noqa: E731
        self.count = lambda t, i, o, tin, tout: {"type": "event_msg", "timestamp": t, "payload": {  # noqa: E731
            "type": "token_count", "info": {"last_token_usage": {"input_tokens": i, "cached_input_tokens": 1,
                                                                 "output_tokens": o},
                                            "total_token_usage": {"input_tokens": tin, "output_tokens": tout}}}}
        self.meta, count = meta, self.count
        jsonl(self.codex / "sessions" / "2026" / "01" / "02" / "rollout-a.jsonl", [
            meta(str(self.repo.dir)), count(self.before, 500, 500, 500, 500), count(self.after, 100, 7, 600, 507),
            count(self.after, 200, 8, 800, 515)])
        jsonl(self.codex / "sessions" / "2026" / "01" / "02" / "rollout-b.jsonl", [
            meta(str(self.home)), count(self.after, 9, 9, 9, 9)])

    def test_sums_planted_transcripts_since_the_approval(self):
        self.plant()
        res = self.cost("cost")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(res.stdout.splitlines(), ["claude: input 666 output 49 (2 transcripts)",
                                                   "codex: input 300 output 15 (1 transcripts)"])
        early = subprocess.run(["git", "commit-tree", "HEAD^{tree}", "-m", "early"], cwd=self.repo.dir, check=True,
                               env=env(GIT_COMMITTER_DATE="2000-01-01T00:00:00Z"), capture_output=True, text=True)
        res = self.cost("cost", "--since", early.stdout.strip())
        self.assertEqual(res.stdout.splitlines(), ["claude: input 3666 output 1049 (2 transcripts)",
                                                   "codex: input 800 output 515 (1 transcripts)"])

    def test_repeated_codex_usage_notifications_count_once(self):
        self.plant()
        path = self.codex / "sessions" / "2026" / "01" / "02" / "rollout-a.jsonl"
        rows = [json.loads(l) for l in path.read_text().splitlines()]
        rows += [rows[-1], rows[-1]]  # Codex re-emits a token_count whose totals have not moved
        jsonl(path, rows)
        res = self.cost("cost")
        self.assertEqual(res.stdout.splitlines()[1], "codex: input 300 output 15 (1 transcripts)", res.stderr)

    def test_repository_cost_includes_subdirectory_and_worktree_sessions(self):
        self.plant()
        slug = re.sub(r"[^A-Za-z0-9]", "-", str(self.repo.dir))
        usage = {"input_tokens": 1, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0, "output_tokens": 1}
        for sub in ("install", ".claude/worktrees/agent-1"):  # a session opened in a subdirectory, a builder's worktree
            jsonl(self.home / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(self.repo.dir / sub)) / "s.jsonl",
                  [{"type": "assistant", "timestamp": self.after, "message": {"id": f"m-{sub}", "usage": usage}}])
            jsonl(self.codex / "sessions" / "2026" / "01" / "03" / f"rollout-{len(sub)}.jsonl",
                  [self.meta(str(self.repo.dir / sub)), self.count(self.after, 1, 1, 1, 1)])
        jsonl(self.home / ".claude" / "projects" / f"{slug}2" / "s.jsonl",  # a sibling: its slug is not <slug>-…
              [{"type": "assistant", "timestamp": self.after, "message": {"id": "m-sibling", "usage": usage}}])
        jsonl(self.codex / "sessions" / "2026" / "01" / "03" / "rollout-sibling.jsonl",
              [self.meta(str(self.repo.dir) + "2"), self.count(self.after, 1, 1, 1, 1)])
        res = self.cost("cost")
        self.assertEqual(res.stdout.splitlines(), ["claude: input 668 output 51 (4 transcripts)",
                                                   "codex: input 302 output 17 (3 transcripts)"], res.stderr)

    def test_codex_usage_before_the_session_meta_record_still_counts(self):
        self.plant()
        path = self.codex / "sessions" / "2026" / "01" / "02" / "rollout-a.jsonl"
        rows = [json.loads(l) for l in path.read_text().splitlines()]
        jsonl(path, [self.count(self.after, 1, 1, 1, 1), *rows])  # a usage record ahead of session_meta: in the window
        res = self.cost("cost")
        self.assertEqual(res.stdout.splitlines()[1], "codex: input 301 output 16 (1 transcripts)", res.stderr)

    def test_nothing_planted_prints_unknown_for_each_harness(self):
        res = self.cost("cost")
        self.assertEqual((res.returncode, res.stdout), (0, "claude: unknown\ncodex: unknown\n"), res.stderr)

    def test_packet_reports_the_cost(self):
        self.plant()
        self.cost("packet")
        packet = self.repo.read(".runs/F-9/packet.md")
        self.assertIn("\nCost:\nclaude: input 666 output 49 (2 transcripts)\ncodex: input 300 output 15 (1 transcripts)\n",
                      packet)


class CleanupTest(RepoCase):
    """goal.py own and cleanup against a bare origin; a builder is a linked worktree under .claude/worktrees/."""

    def setUp(self):
        super().setUp()
        self.tmp = Path(os.path.realpath(tempfile.mkdtemp(prefix="goal-cleanup-")))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.origin = self.tmp / "origin.git"
        self.repo.git("init", "-q", "--bare", str(self.origin))
        self.repo.git("remote", "add", "origin", str(self.origin))
        self.repo.write(".gitignore", self.repo.read(".gitignore") + "/.claude/\n")
        self.repo.commit("ignore nested worktrees")
        self.repo.git("branch", "elsewhere")
        self.repo.git("tag", "v-old")
        self.repo.git("push", "-q", "origin", "main", "elsewhere", "v-old")
        self.repo.git("tag", "-d", "v-old")
        self.record = self.repo.path(".runs/F-9/worktrees.jsonl")

    def builder(self, x, change=True):
        """Worktree .claude/worktrees/agent-<x> on branch worktree-agent-<x>, with src/<x>.py staged when change."""
        path = self.repo.dir / ".claude" / "worktrees" / f"agent-{x}"
        self.repo.git("worktree", "add", "-q", "-b", f"worktree-agent-{x}", str(path))
        if change:
            (path / "src").mkdir(exist_ok=True)
            (path / "src" / f"{x}.py").write_text(f"{x.upper()} = 1\n")
            self.repo.git("-C", str(path), "add", f"src/{x}.py")
        return path

    def land(self, x):
        self.repo.write(f"src/{x}.py", f"{x.upper()} = 1\n")
        self.repo.commit(f"[T1] land {x}")
        self.repo.git("push", "-q", "origin", "main")

    def sample(self):
        path = self.tmp / "sample"
        self.repo.git("worktree", "add", "-q", "--detach", str(path), "HEAD")
        return path

    def goal_in(self, cwd, *args):
        return subprocess.run([sys.executable, str(GOAL), *args], cwd=cwd, env=env(), capture_output=True,
                              text=True, timeout=120)

    def own(self, path):
        res = self.repo.goal("own", "--goal", "F-9", str(path))
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        return res

    def cleanup(self, *args, code=0):
        res = self.repo.goal("cleanup", "--goal", "F-9", *args)
        self.assertEqual(res.returncode, code, res.stdout + res.stderr)
        return res.stdout.splitlines()

    def head(self, mode):
        return f"cleanup: {mode} for F-9 against origin/main at {self.repo.git('rev-parse', 'refs/remotes/origin/main')[:10]}"

    def rows(self):
        return [json.loads(l) for l in self.record.read_text().splitlines()]

    def exists(self, ref):
        return subprocess.run(["git", "rev-parse", "-q", "--verify", ref], cwd=self.repo.dir,
                              capture_output=True).returncode == 0

    def test_own_records_only_linked_worktrees_of_this_repository(self):
        a = self.builder("a")
        self.assertEqual(self.own(a).stdout, f"own: {a} (worktree-agent-a)\n")
        rows = self.rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(sorted(rows[0]), ["at", "branch", "head", "path"])
        self.assertEqual((rows[0]["path"], rows[0]["branch"], rows[0]["head"]),
                         (str(a), "worktree-agent-a", self.repo.git("rev-parse", "HEAD")))
        before = self.record.read_text()
        self.own(a)
        self.assertEqual(self.record.read_text(), before)
        other = Repo()
        self.addCleanup(other.cleanup)
        elsewhere = self.tmp / "other-wt"
        other.git("worktree", "add", "-q", "--detach", str(elsewhere))
        plain = self.tmp / "plain"
        plain.mkdir()
        for path in (self.repo.dir, plain, elsewhere):
            res = self.repo.goal("own", "--goal", "F-9", str(path))
            self.assertEqual((res.returncode, res.stdout, res.stderr),
                             (2, "", f"goal.py: {path} is not a linked worktree of this repository\n"))
        res = self.goal_in(a, "own", "--goal", "F-9", ".")  # the worktree holding the current directory
        self.assertEqual((res.returncode, res.stderr), (2, f"goal.py: {a} is not a linked worktree of this repository\n"))
        self.assertEqual(self.record.read_text(), before)

    def test_cleanup_removes_only_recorded_work_main_holds(self):
        a = self.builder("a")
        self.land("a")
        sample = self.sample()
        self.own(a)
        self.own(sample)
        self.repo.git("worktree", "add", "-q", "-b", "other-session", str(self.repo.dir / ".claude/worktrees/other-session"))
        self.repo.git("branch", "old-goal")
        self.repo.git("-C", str(self.origin), "branch", "-q", "-D", "elsewhere")
        tracking = self.repo.git("rev-parse", "refs/remotes/origin/elsewhere")
        self.assertEqual(self.cleanup(), [
            self.head("dry run"),
            "remove worktree .claude/worktrees/agent-a (changes already in origin/main)",
            "remove branch worktree-agent-a (merged)",
            f"remove worktree {sample} (merged)",
            "cleanup: 3 to remove, 0 kept"])
        self.assertEqual(self.repo.git("rev-parse", "refs/remotes/origin/elsewhere"), tracking)
        self.assertEqual(self.repo.git("tag", "-l", "v-old"), "")
        listed = self.repo.git("worktree", "list", "--porcelain")
        for path in (a, sample, self.repo.dir / ".claude/worktrees/other-session"):
            self.assertIn(f"worktree {path}\n", listed)
        for branch in ("worktree-agent-a", "other-session", "old-goal"):
            self.assertTrue(self.exists(f"refs/heads/{branch}"), branch)
        self.assertEqual(self.cleanup("--apply"), [
            self.head("apply"),
            "removed worktree .claude/worktrees/agent-a (changes already in origin/main)",
            "removed branch worktree-agent-a (merged)",
            f"removed worktree {sample} (merged)",
            "cleanup: 3 removed, 0 kept"])
        self.assertFalse(a.exists() or sample.exists())
        self.assertFalse(self.exists("refs/heads/worktree-agent-a"))
        self.assertTrue(self.exists("refs/heads/other-session") and self.exists("refs/heads/old-goal"))
        self.assertTrue((self.repo.dir / ".claude/worktrees/other-session").is_dir())
        self.assertEqual(self.repo.git("rev-parse", "refs/remotes/origin/elsewhere"), tracking)
        self.assertEqual(self.repo.git("tag", "-l", "v-old"), "")
        self.assertEqual(self.cleanup("--apply"), [self.head("apply"), "cleanup: 0 removed, 0 kept"])

    def test_cleanup_from_another_checkout_uses_the_ownership_record(self):
        a = self.builder("a", change=False)
        sample = self.sample()
        self.own(a)
        self.own(sample)
        res = self.goal_in(sample, "cleanup", "--goal", "F-9")
        self.assertEqual((res.returncode, res.stdout.splitlines()), (0, [
            self.head("dry run"),
            f"remove worktree {a} (merged)",
            "remove branch worktree-agent-a (merged)",
            f"keep worktree {sample}: in use here",
            "cleanup: 2 to remove, 1 kept"]), res.stderr)
        self.assertFalse((sample / ".runs").exists())

    def test_cleanup_keeps_recorded_work_main_lacks(self):
        git = lambda wt, *args: self.repo.git("-C", str(wt), *args)  # noqa: E731
        locked = self.builder("locked", change=False)
        (locked / "notes.txt").write_text("untracked\n")
        self.repo.git("worktree", "lock", str(locked))
        untracked = self.builder("untracked", change=False)
        (untracked / "notes.txt").write_text("untracked\n")
        staged = self.builder("staged")
        diff = git(staged, "diff", "--cached")
        commit = self.builder("commit", change=False)
        (commit / "src").mkdir()
        (commit / "src/commit.py").write_text("C = 1\n")
        git(commit, "add", "src/commit.py")
        git(commit, "commit", "-q", "-m", "unpushed")
        sub = self.builder("sub", change=False)
        git(sub, "update-index", "--add", "--cacheinfo", f"160000,{self.repo.git('rev-parse', 'HEAD')},sub")
        unstaged = self.builder("unstaged", change=False)
        (unstaged / "f.txt").write_text("A\n")
        (unstaged / "f.txt").write_text("B\n")
        git(unstaged, "add", "f.txt")
        (unstaged / "f.txt").write_text("A\n")
        paths = (locked, untracked, staged, commit, sub, unstaged)
        for path in paths:
            self.own(path)
        self.assertEqual(self.cleanup("--apply"), [
            self.head("apply"),
            "keep worktree .claude/worktrees/agent-locked: locked",
            "keep worktree .claude/worktrees/agent-untracked: untracked files",
            "keep worktree .claude/worktrees/agent-staged: staged changes not in origin/main",
            "keep worktree .claude/worktrees/agent-commit: 1 commit(s) not in origin/main",
            "keep worktree .claude/worktrees/agent-sub: submodules",
            "keep worktree .claude/worktrees/agent-unstaged: unstaged changes",
            "cleanup: 0 removed, 6 kept"])
        for path in paths:
            self.assertTrue(path.is_dir(), path)
        self.assertEqual(git(staged, "diff", "--cached"), diff)
        self.assertEqual(git(unstaged, "show", ":f.txt"), "B")

    def test_cleanup_keeps_recorded_branches_that_moved(self):
        c, d = self.builder("c", change=False), self.builder("d", change=False)
        self.own(c)
        self.own(d)
        self.repo.git("worktree", "remove", str(c))
        self.repo.git("worktree", "remove", str(d))
        self.repo.git("checkout", "-q", "worktree-agent-c")
        tip = self.repo.git("commit-tree", "worktree-agent-d^{tree}", "-p", "worktree-agent-d", "-m", "unpushed")
        self.repo.git("update-ref", "refs/heads/worktree-agent-d", tip)
        self.assertEqual(self.cleanup("--apply"), [
            self.head("apply"),
            "gone worktree .claude/worktrees/agent-c",
            "keep branch worktree-agent-c: current branch",
            "gone worktree .claude/worktrees/agent-d",
            "keep branch worktree-agent-d: 1 commit(s) not in origin/main",
            "cleanup: 0 removed, 2 kept"])
        self.assertTrue(self.exists("refs/heads/worktree-agent-c") and self.exists("refs/heads/worktree-agent-d"))

    def test_cleanup_retries_a_branch_whose_removal_failed(self):
        b = self.builder("b", change=False)
        self.own(b)
        common = Path(self.repo.git("rev-parse", "--path-format=absolute", "--git-common-dir"))
        lock = common / "refs" / "heads" / "worktree-agent-b.lock"
        lock.write_text("")
        out = self.cleanup("--apply", code=1)
        self.assertEqual(out[:2], [self.head("apply"), "removed worktree .claude/worktrees/agent-b (merged)"])
        self.assertTrue(out[2].startswith("cleanup: could not remove branch worktree-agent-b: "), out)
        self.assertEqual(out[3:], ["cleanup: 1 removed, 0 kept"])
        self.assertFalse(b.exists())
        self.assertFalse(any("branch_removed" in r for r in self.rows()))
        lock.unlink()
        self.assertEqual(self.cleanup("--apply"), [
            self.head("apply"), "removed branch worktree-agent-b (merged)", "cleanup: 1 removed, 0 kept"])
        self.assertFalse(self.exists("refs/heads/worktree-agent-b"))

    def test_cleanup_treats_a_deleted_worktree_directory_as_gone(self):
        e, other = self.builder("e", change=False), self.builder("other", change=False)
        self.own(e)
        shutil.rmtree(e)
        self.assertIn(f"worktree {e}\n", self.repo.git("worktree", "list", "--porcelain"))  # git still lists it
        self.assertEqual(self.cleanup(), [
            self.head("dry run"), "remove worktree .claude/worktrees/agent-e (directory gone)",
            "remove branch worktree-agent-e (merged)", "cleanup: 2 to remove, 0 kept"])
        res = self.repo.goal("cleanup", "--goal", "F-9", "--apply")
        self.assertEqual((res.returncode, res.stdout.splitlines(), res.stderr), (0, [
            self.head("apply"), "removed worktree .claude/worktrees/agent-e (directory gone)",
            "removed branch worktree-agent-e (merged)", "cleanup: 2 removed, 0 kept"], ""))
        listed = self.repo.git("worktree", "list", "--porcelain")
        self.assertNotIn(f"worktree {e}\n", listed)
        self.assertIn(f"worktree {other}\n", listed)
        self.assertFalse(self.exists("refs/heads/worktree-agent-e"))
        self.assertEqual([sorted(r) for r in self.rows()],
                         [["at", "branch", "head", "path"], ["path", "removed"], ["branch_removed", "path"]])

    def test_cleanup_keeps_a_locked_worktree_whose_directory_is_gone(self):
        f = self.builder("f", change=False)
        self.own(f)
        self.repo.git("worktree", "lock", str(f))
        shutil.rmtree(f)  # a locked worktree on a drive that is away: the lock keeps it
        self.assertEqual(self.cleanup("--apply"), [
            self.head("apply"), "keep worktree .claude/worktrees/agent-f: locked", "cleanup: 0 removed, 1 kept"])
        self.assertIn(f"worktree {f}\n", self.repo.git("worktree", "list", "--porcelain"))
        self.assertTrue(self.exists("refs/heads/worktree-agent-f"))

    def test_cleanup_completes_records_and_refuses_without_origin_main(self):
        self.assertEqual(self.cleanup(), [self.head("dry run"), "cleanup: 0 to remove, 0 kept"])
        e = self.builder("e", change=False)
        self.own(e)
        self.repo.git("worktree", "remove", str(e))
        self.repo.git("branch", "-q", "-D", "worktree-agent-e")
        self.assertEqual(self.cleanup("--apply"), [
            self.head("apply"), "gone worktree .claude/worktrees/agent-e", "cleanup: 0 removed, 0 kept"])
        self.assertEqual(self.cleanup("--apply"), [self.head("apply"), "cleanup: 0 removed, 0 kept"])
        bare = Repo()
        self.addCleanup(bare.cleanup)
        res = bare.goal("cleanup", "--goal", "F-9")
        self.assertEqual((res.returncode, res.stdout), (2, ""), res.stderr)
        self.assertTrue(res.stderr.startswith("goal.py: cleanup needs origin/main: "), res.stderr)


    def test_cleanup_keeps_untracked_files_when_status_hides_them(self):
        self.repo.git("config", "status.showUntrackedFiles", "no")
        u = self.builder("u", change=False)
        (u / "notes.txt").write_text("untracked\n")
        self.own(u)
        self.assertEqual(self.cleanup("--apply"), [
            self.head("apply"), "keep worktree .claude/worktrees/agent-u: untracked files", "cleanup: 0 removed, 1 kept"])
        self.assertTrue((u / "notes.txt").is_file())

    def test_failed_cached_diff_prevents_removal(self):
        self.repo.git("config", "diff.external", str(self.tmp / "no-such-diff"))
        x = self.builder("x")
        self.own(x)
        self.assertEqual(self.cleanup("--apply"), [
            self.head("apply"), "keep worktree .claude/worktrees/agent-x: staged changes not in origin/main",
            "cleanup: 0 removed, 1 kept"])
        self.assertEqual(self.repo.git("-C", str(x), "diff-index", "--cached", "--name-only", "HEAD"), "src/x.py")

    def test_cleanup_preserves_changes_hidden_by_textconv(self):
        self.repo.write("f.doc", "one\n")
        self.repo.commit("[T1] land f.doc")
        self.repo.git("push", "-q", "origin", "main")
        info = Path(self.repo.git("rev-parse", "--path-format=absolute", "--git-common-dir")) / "info"
        info.mkdir(exist_ok=True)
        (info / "attributes").write_text("*.doc diff=strip\n")
        self.repo.git("config", "diff.strip.textconv", "true")  # every version converts to the same empty text
        t = self.builder("t", change=False)
        (t / "f.doc").write_text("two\n")
        self.repo.git("-C", str(t), "add", "f.doc")
        w = self.builder("w", change=False)
        (w / "f.doc").write_text("two\n")
        self.own(t)
        self.own(w)
        self.assertEqual(self.cleanup("--apply"), [
            self.head("apply"), "keep worktree .claude/worktrees/agent-t: staged changes not in origin/main",
            "keep worktree .claude/worktrees/agent-w: unstaged changes", "cleanup: 0 removed, 2 kept"])
        self.assertEqual(self.repo.git("-C", str(t), "show", ":f.doc"), "two")
        self.assertEqual((w / "f.doc").read_text(), "two\n")

    def test_cleanup_fetch_preserves_additional_mapped_refs(self):
        self.repo.git("config", "--add", "remote.origin.fetch", "+refs/heads/main:refs/remotes/secondary/main")
        self.assertEqual(self.cleanup(), [self.head("dry run"), "cleanup: 0 to remove, 0 kept"])
        self.assertTrue(self.exists("refs/remotes/origin/main"))
        self.assertFalse(self.exists("refs/remotes/secondary/main"))

    def test_own_handles_newline_paths_without_accepting_their_prefixes(self):
        prefix, odd = self.tmp / "nl", self.tmp / "nl\nwt"
        prefix.mkdir()
        self.repo.git("worktree", "add", "-q", "--detach", str(odd))
        self.assertEqual(self.own(odd).stdout, f"own: {odd} (detached)\n")
        self.assertEqual(self.rows()[0]["path"], str(odd))
        res = self.repo.goal("own", "--goal", "F-9", str(prefix))
        self.assertEqual((res.returncode, res.stderr),
                         (2, f"goal.py: {prefix} is not a linked worktree of this repository\n"))
        res = self.repo.goal("cleanup", "--goal", "F-9")  # raw stdout: the path itself holds a newline
        self.assertEqual((res.returncode, res.stdout), (0, "\n".join([
            self.head("dry run"), f"remove worktree {odd} (merged)", "cleanup: 1 to remove, 0 kept", ""])))

    def test_cleanup_preserves_unrecorded_nested_worktree(self):
        a = self.builder("a", change=False)
        nested = a / ".claude" / "worktrees" / "other-session"  # under a's ignored .claude/
        self.repo.git("worktree", "add", "-q", "-b", "other-session", str(nested))
        (nested / "work.txt").write_text("unsaved\n")
        self.own(a)
        self.assertEqual(self.cleanup("--apply"), [
            self.head("apply"), "keep worktree .claude/worktrees/agent-a: holds another worktree",
            "cleanup: 0 removed, 1 kept"])
        self.assertEqual((nested / "work.txt").read_text(), "unsaved\n")
        self.assertTrue(self.exists("refs/heads/worktree-agent-a") and self.exists("refs/heads/other-session"))

if __name__ == "__main__":
    unittest.main()
