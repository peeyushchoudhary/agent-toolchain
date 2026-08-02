"""Every read in validate_disclosure.py, and the one thing none of them may do: pass quietly.

THE DEFECT THESE TESTS PIN. `crawl` ended its read in `except OSError: continue`, so an entry file
the checker could not open was skipped and the route was then declared clean. Measured on the
fixture rebuilt in `RedFixtureTest` below:

    readable AGENTS.md, two broken links   ->  rc=1, both links named
    the same file at chmod 000             ->  rc=0, "0 error(s), 1 warning(s)"

A failing route was made to pass by making a file unreadable, and the summary line said nothing
about the file it had not read. This script is the pre-commit hook in every project repository and
runs at every session start, so that is the widest-reach fail-open in the toolchain.

WHAT IS ACTUALLY BEING TESTED, and it is not "line 262 was patched". The remedy was removal: all
reading goes through `read_doc`, which raises `Unexaminable`, and nothing between there and `main`
catches it. So the tests come in two layers, and the second is the one that will still be here in a
year:

  1. Behavioural — each read site, exercised end to end through the real CLI, exits 2.
  2. Structural — `SwallowAbsenceTest` asserts that no swallow has been reintroduced anywhere in
     the file, by source inspection. A behavioural test only covers the reads someone thought to
     test; this one covers the read added next month by someone who never read this file.

Run: python3 skills/progressive-disclosure/tests/test_validate_disclosure_reads.py
"""

from __future__ import annotations

import ast
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL / "scripts"
VALIDATOR = SCRIPTS / "validate_disclosure.py"
HOOKS = Path.home() / ".claude" / "hooks"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


validator = load_module("validate_disclosure_reads_test", VALIDATOR)


def run(root: Path, *flags: str) -> tuple[int, str]:
    """Invoke the real CLI and return (exit code, combined output).

    A subprocess rather than a call into `main`, because the exit CODE is the thing under test and
    it is the thing a hook sees. Output is combined and the code is captured from the process
    itself — never from the tail of a pipeline, which reports the last command's status and not
    this one's.
    """
    proc = subprocess.run(
        [sys.executable, str(VALIDATOR), str(root), *flags],
        capture_output=True, text=True, timeout=120,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    return proc.returncode, proc.stdout + proc.stderr


class FixtureMixin:
    """A minimal repository with a real route, and knobs to break one thing at a time."""

    def repo(self, *, broken_links: int = 0) -> Path:
        root = Path(tempfile.mkdtemp(prefix="pd-reads-"))
        self.addCleanup(self._restore, root)
        (root / "docs" / "agents").mkdir(parents=True)
        body = ["# Fixture contract", "", "Route: [index](docs/agents/README.md)"]
        for i in range(broken_links):
            body.append(f"Broken {i}: [gone](docs/agents/nope-{i}.md)")
        (root / "AGENTS.md").write_text("\n".join(body) + "\n", encoding="utf-8")
        (root / "docs" / "agents" / "README.md").write_text(
            '# Agents index\n\n<!-- agent-personas: {"mode":"base-only","reason":"fixture"} -->\n',
            encoding="utf-8",
        )
        return root

    @staticmethod
    def _restore(root: Path) -> None:
        # chmod 000 files defeat rmtree, and a test that leaves unreadable temp files behind
        # poisons the next run rather than this one.
        for p in root.rglob("*"):
            try:
                p.chmod(0o755)
            except OSError:
                pass
        import shutil
        shutil.rmtree(root, ignore_errors=True)


class RedFixtureTest(FixtureMixin, unittest.TestCase):
    """The exact reproduction, both halves, in one test so neither can drift from the other."""

    def test_readable_route_with_broken_links_is_a_finding(self):
        root = self.repo(broken_links=2)
        rc, out = run(root)
        self.assertEqual(rc, 1, out)
        self.assertIn("nope-0.md", out)
        self.assertIn("nope-1.md", out)
        self.assertIn("2 error(s)", out)

    def test_the_same_file_unreadable_does_not_become_clean(self):
        """The whole defect. Before the fix this was rc=0 and '0 error(s), 1 warning(s)'."""
        root = self.repo(broken_links=2)
        (root / "AGENTS.md").chmod(0o000)
        if os.access(root / "AGENTS.md", os.R_OK):
            self.skipTest("running as a user who can read mode-000 files (root?)")
        rc, out = run(root)
        self.assertEqual(rc, 2, out)
        self.assertIn("CHECK COULD NOT RUN", out)
        self.assertIn("AGENTS.md", out)
        # The verdict sentence itself must carry the caveat, not a line above it.
        self.assertIn("no verdict", out)
        self.assertNotIn("0 error(s)", out)
        self.assertNotIn("clean —", out)      # the clean verdict, not the word "clean"

    def test_unreadable_beats_the_clean_verdict_too(self):
        """Not only a broken route: a genuinely clean one must not report clean either."""
        root = self.repo()
        (root / "docs" / "agents" / "README.md").chmod(0o000)
        if os.access(root / "docs" / "agents" / "README.md", os.R_OK):
            self.skipTest("running as a user who can read mode-000 files (root?)")
        rc, out = run(root)
        self.assertEqual(rc, 2, out)
        self.assertNotIn("clean —", out)


class ReadSiteTest(FixtureMixin, unittest.TestCase):
    """One case per read site, because the audit found one instance and there were fifteen."""

    def assert_cannot_run(self, root: Path, needle: str, *flags: str) -> None:
        rc, out = run(root, *flags)
        self.assertEqual(rc, 2, out)
        self.assertIn("CHECK COULD NOT RUN", out)
        self.assertIn(needle, out)

    def test_unreadable_routed_guide(self):
        root = self.repo()
        guide = root / "docs" / "agents" / "guide.md"
        guide.write_text("# Guide\n", encoding="utf-8")
        (root / "AGENTS.md").write_text(
            "# C\n\n[index](docs/agents/README.md) [guide](docs/agents/guide.md)\n",
            encoding="utf-8")
        guide.chmod(0o000)
        if os.access(guide, os.R_OK):
            self.skipTest("cannot make a file unreadable as this user")
        self.assert_cannot_run(root, "guide.md")

    def test_unreadable_makefile(self):
        root = self.repo()
        (root / "Makefile").write_text("build:\n\techo hi\n", encoding="utf-8")
        (root / "Makefile").chmod(0o000)
        if os.access(root / "Makefile", os.R_OK):
            self.skipTest("cannot make a file unreadable as this user")
        self.assert_cannot_run(root, "Makefile")

    def test_unreadable_readme_under_readme_contract(self):
        root = self.repo()
        (root / "README.md").write_text("# R\n", encoding="utf-8")
        (root / "README.md").chmod(0o000)
        if os.access(root / "README.md", os.R_OK):
            self.skipTest("cannot make a file unreadable as this user")
        self.assert_cannot_run(root, "README.md", "--readme")

    def test_unparseable_package_json_does_not_silently_disable_script_checks(self):
        """`except (JSONDecodeError, OSError): pass` left `scripts` empty, and an empty `scripts`
        set turns the whole missing-script check off — every documented `pnpm x` then passes."""
        root = self.repo()
        (root / "package.json").write_text('{"scripts": {oops}', encoding="utf-8")
        (root / "AGENTS.md").write_text(
            "# C\n\n[index](docs/agents/README.md)\n\nRun `pnpm nonexistent-script`.\n",
            encoding="utf-8")
        self.assert_cannot_run(root, "package.json")

    def test_undecodable_entry_file(self):
        """`errors='replace'` read a UTF-16 file as a wall of nothing in which no link matches."""
        root = self.repo(broken_links=2)
        (root / "AGENTS.md").write_bytes(
            (root / "AGENTS.md").read_text(encoding="utf-8").encode("utf-16"))
        rc, out = run(root)
        self.assertEqual(rc, 2, out)
        self.assertIn("not valid UTF-8", out)
        self.assertNotIn("0 error(s)", out)

    def test_a_bom_does_not_break_the_first_line(self):
        """utf-8-sig, so a BOM is stripped rather than glued to `^@` — and it is not exit 2."""
        root = self.repo()
        (root / "AGENTS.md").write_bytes(
            b"\xef\xbb\xbf" + (root / "AGENTS.md").read_bytes())
        rc, out = run(root)
        self.assertEqual(rc, 0, out)

    def test_directory_where_a_document_is_expected(self):
        """A link to a directory named `*.md` resolved, so `exists()` passed and it was silently
        not queued — link-to-doc and link-to-directory produced identical output."""
        root = self.repo()
        (root / "docs" / "agents" / "area.md").mkdir()
        (root / "AGENTS.md").write_text(
            "# C\n\n[index](docs/agents/README.md) [area](docs/agents/area.md)\n",
            encoding="utf-8")
        rc, out = run(root)
        self.assertEqual(rc, 1, out)
        self.assertIn("link-not-a-file", out)

    def test_symlink_to_nothing(self):
        root = self.repo()
        (root / "docs" / "agents" / "dangling.md").symlink_to(root / "docs" / "agents" / "absent.md")
        (root / "AGENTS.md").write_text(
            "# C\n\n[index](docs/agents/README.md) [d](docs/agents/dangling.md)\n",
            encoding="utf-8")
        rc, out = run(root)
        self.assertEqual(rc, 1, out)
        self.assertIn("broken-link", out)


class RegressionTest(FixtureMixin, unittest.TestCase):
    """The fix must not move any exit code it was not aimed at."""

    def test_clean_route_still_exits_zero(self):
        rc, out = run(self.repo())
        self.assertEqual(rc, 0, out)
        self.assertIn("clean", out)

    def test_broken_route_still_exits_one_with_the_same_findings(self):
        rc, out = run(self.repo(broken_links=3))
        self.assertEqual(rc, 1, out)
        self.assertEqual(out.count("broken-link"), 3, out)

    def test_hook_mode_is_silent_on_a_clean_route(self):
        rc, out = run(self.repo(), "--hook")
        self.assertEqual(rc, 0, out)
        self.assertEqual(out.strip(), "", out)

    def test_json_mode_stays_a_single_valid_object(self):
        rc, out = run(self.repo(), "--json")
        self.assertEqual(rc, 0, out)
        data = json.loads(out)
        self.assertEqual(data["status"], "ok")

    def test_json_mode_on_a_could_not_run_omits_the_counts_it_never_established(self):
        root = self.repo()
        (root / "AGENTS.md").chmod(0o000)
        if os.access(root / "AGENTS.md", os.R_OK):
            self.skipTest("cannot make a file unreadable as this user")
        rc, out = run(root, "--json")
        self.assertEqual(rc, 2, out)
        data = json.loads(out)
        self.assertEqual(data["status"], "could-not-run")
        # Absent, not empty. An empty list reads as "checked, nothing found".
        for key in ("errors", "warnings", "notes"):
            self.assertNotIn(key, data)

    def test_help_still_works(self):
        rc, out = run(Path("."), "--help")
        self.assertEqual(rc, 0, out)


class DisclosureHookTest(FixtureMixin, unittest.TestCase):
    """disclosure-check.sh fires at every session start in every directory. Malformed JSON there
    is not a validator bug, it is every session broken."""

    hook = HOOKS / "disclosure-check.sh"

    def emit(self, root: Path) -> str:
        if not self.hook.is_file():
            self.skipTest(f"{self.hook} is not installed")
        proc = subprocess.run(["bash", str(self.hook)], capture_output=True, text=True,
                              timeout=180, cwd=str(root),
                              env={**os.environ, "CLAUDE_PROJECT_DIR": str(root)})
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return proc.stdout

    def test_emits_one_valid_json_object_when_the_route_is_unexaminable(self):
        root = self.repo(broken_links=1)
        (root / "package.json").write_text('{"name":"x"}', encoding="utf-8")  # looks like a project
        (root / "AGENTS.md").chmod(0o000)
        if os.access(root / "AGENTS.md", os.R_OK):
            self.skipTest("cannot make a file unreadable as this user")
        out = self.emit(root)
        self.assertTrue(out.strip(), "hook produced no output for an unexaminable route")
        payload = json.loads(out)          # raises if it is not ONE object
        self.assertIn("hookSpecificOutput", payload)
        self.assertIn("CHECK COULD NOT RUN",
                      payload["hookSpecificOutput"]["additionalContext"])

    def test_emits_valid_json_on_an_ordinary_broken_route(self):
        root = self.repo(broken_links=1)
        (root / "package.json").write_text('{"name":"x"}', encoding="utf-8")
        out = self.emit(root)
        json.loads(out)


class SwallowAbsenceTest(unittest.TestCase):
    """The durable half. Asserted against the source, not against behaviour.

    A behavioural suite pins the reads that exist today. This pins the RULE, so the read someone
    adds next year is covered by a test written before it. Two properties:

      1. No `read_text`/`read_bytes`/`open` outside `read_doc`.
      2. No handler in the file catches OSError and then continues, passes, or returns a
         placeholder — the shape that produced the defect.
    """

    def setUp(self):
        self.source = VALIDATOR.read_text(encoding="utf-8")
        self.tree = ast.parse(self.source)

    def test_every_read_goes_through_read_doc(self):
        offenders = []
        for node in ast.walk(self.tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr not in ("read_text", "read_bytes"):
                continue
            fn = self._enclosing_function(node)
            if fn == "read_doc":
                continue
            offenders.append(f"{fn}() line {node.lineno}: .{node.func.attr}()")
        self.assertEqual(offenders, [], "reads bypassing read_doc:\n  " + "\n  ".join(offenders))

    # A handler that catches a read failure must raise. The only way not to raise is to appear
    # here, with a reason — so adding a swallow means editing this list, in a diff a reviewer sees,
    # rather than adding four quiet characters at the bottom of a `try`. That is the whole
    # difference between a rule enforced by absence and a rule enforced by remembering.
    NON_READ_HANDLERS = {
        "_display": "formats a path for display; reads no file and gates no verdict",
        "tracked_files": "git absent falls back to walk_files — both branches produce a real file "
                         "list, neither produces a quiet clean",
    }

    def test_no_oserror_handler_swallows(self):
        offenders = []
        for node in ast.walk(self.tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            names = self._exception_names(node.type)
            if not ({"OSError", "IOError", "UnicodeDecodeError", "Exception"} & names):
                continue
            if any(isinstance(n, ast.Raise) for n in ast.walk(node)):
                continue
            fn = self._enclosing_function(node)
            if fn in self.NON_READ_HANDLERS:
                continue
            offenders.append(f"{fn}() line {node.lineno}: catches {sorted(names)} without "
                             f"re-raising, and is not in NON_READ_HANDLERS")
        self.assertEqual(offenders, [], "OSError swallows:\n  " + "\n  ".join(offenders))

    def test_there_is_no_opt_out(self):
        """No flag, no environment variable. 'Ignore files I cannot read' is a request to be told
        the route is fine when nobody knows whether it is."""
        lowered = self.source.lower()
        for forbidden in ("--allow-unreadable", "--skip-unreadable", "--ignore-unreadable",
                          "pd_allow_unreadable", "pd_skip_unreadable"):
            self.assertNotIn(forbidden, lowered)
        self.assertNotIn("os.environ", self.source)

    def _is_docstring(self, stmt) -> bool:
        return isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant)

    def _exception_names(self, node) -> set[str]:
        if node is None:
            return {"Exception"}
        out = set()
        for n in ast.walk(node):
            if isinstance(n, ast.Name):
                out.add(n.id)
        return out

    def _enclosing_function(self, target) -> str:
        best = "<module>"
        for node in ast.walk(self.tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            end = getattr(node, "end_lineno", node.lineno)
            if node.lineno <= target.lineno <= end:
                best = node.name
        return best


if __name__ == "__main__":
    unittest.main(verbosity=2)
