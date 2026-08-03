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
import shutil
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

# The claim/uniqueness AST helpers live next door and are deliberately NOT copied here. Two copies
# of a rule are two rules, and they drift; this whole card exists because something stated in more
# than one place ended up stating more than one thing. Importing the sibling only defines its test
# classes — nothing runs, because it is guarded by `__main__`.
_shared = load_module("check_toolchain_ast_helpers",
                      Path(__file__).resolve().parent / "test_check_toolchain.py")
claim_strings = _shared.claim_strings
printed_nodes = _shared.printed_nodes
find_function = _shared.find_function


def run(root: Path, *flags: str) -> tuple[int, str]:
    """Invoke the real CLI and return (exit code, combined output).

    A subprocess rather than a call into `main`, because the exit CODE is the thing under test and
    it is the thing a hook sees. Output is combined and the code is captured from the process
    itself — never from the tail of a pipeline, which reports the last command's status and not
    this one's.

    `HOME` IS REDIRECTED to an empty scratch directory. `validate_disclosure.py` reaches
    `Path.home()`, and `installed_methodology_version()` runs BEFORE the early return, so every
    one of these fixture runs otherwise stats the real `~/.claude/skills/execution-methodology/`
    and the answer depends on what this machine happens to have installed. Every assertion here is
    about the FIXTURE ROOT, so an empty home is the honest input; the alternative is a suite whose
    result changes when an unrelated skill is installed.
    """
    home = Path(tempfile.mkdtemp(prefix="pd-reads-home-"))
    try:
        proc = subprocess.run(
            [sys.executable, str(VALIDATOR), str(root), *flags],
            capture_output=True, text=True, timeout=120,
            env={**os.environ, "HOME": str(home), "PYTHONDONTWRITEBYTECODE": "1"},
        )
    finally:
        shutil.rmtree(home, ignore_errors=True)
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
        """Exit 0 is unchanged. The WORD `clean` is not, and that is the point.

        This test used to assert `clean` in the output of a run that had not looked at the README
        contract or the structure standard, which is exactly the false claim being removed. The
        exit code must not move — a check nobody requested is not a defect in the repository — so
        the assertion splits into the two things it was conflating.
        """
        rc, out = run(self.repo())
        self.assertEqual(rc, 0, out)
        self.assertIn("NOT A CLEAN RESULT", out)
        self.assertNotIn("clean —", out)
        self.assertIn("README contract", out)

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
        # `ok` was a constant, so it said the same thing about a run that checked everything and a
        # run that checked part of it. A consumer must be able to tell those apart.
        self.assertEqual(data["status"], "partial")
        self.assertTrue(data["not_run"], data)

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


class NotRunStateTest(FixtureMixin, unittest.TestCase):
    """FACE 2. `clean — every route resolves, every documented command exists`, printed over a
    README contract the run never opened.

    The same tell as every other instance of this class: the failure path and the success path
    produce the same output. `--readme`, `--standard` and `--vs` each gate a whole family of
    ERROR-producing checks at the CALL SITE, and skipping them produced no output whatsoever — so
    a run that checked five things and a run that checked eight printed the identical last line.
    """

    def repo_with_a_bad_readme(self) -> Path:
        """A repository whose ROUTE is clean and whose README violates the contract.

        Both halves matter. If the route were broken the summary would not say `clean` anyway and
        the test would pass for the wrong reason.
        """
        root = self.repo()
        (root / "README.md").write_text("# Fixture\n\nNo required sections at all.\n",
                                        encoding="utf-8")
        return root

    def test_the_same_tree_is_clean_or_five_errors_depending_only_on_a_flag(self):
        """The reproduction, both halves, against ONE tree that does not change between them."""
        root = self.repo_with_a_bad_readme()
        before = (root / "README.md").read_bytes()

        rc_default, out_default = run(root)
        rc_readme, out_readme = run(root, "--readme")

        self.assertEqual((root / "README.md").read_bytes(), before,
                         "the tree changed between the two runs; the comparison proves nothing")

        # The flagged run finds real errors...
        self.assertEqual(rc_readme, 1, out_readme)
        self.assertIn("readme-missing-section", out_readme)

        # ...and the unflagged run, on the identical tree, may no longer call itself clean.
        self.assertEqual(rc_default, 0, out_default)
        self.assertNotIn("clean —", out_default)
        self.assertIn("NOT RUN", out_default)
        self.assertIn("README contract", out_default)
        self.assertIn("--readme", out_default)

    def test_every_opt_in_family_is_named_when_it_does_not_run(self):
        rc, out = run(self.repo(), "--json")
        data = json.loads(out)
        self.assertEqual(rc, 0, out)
        self.assertEqual({item["check"] for item in data["not_run"]},
                         {"cross-project structure standard", "README contract",
                          "README freshness against a git ref"})
        for item in data["not_run"]:
            self.assertIn("not requested", item["why"])

    def test_requesting_a_family_removes_it_from_the_not_run_list(self):
        """Guard the guard: a `not_run` list that is constant would satisfy the test above."""
        rc, out = run(self.repo(), "--readme", "--json")
        data = json.loads(out)
        self.assertNotIn("README contract", {item["check"] for item in data["not_run"]})
        self.assertIn("cross-project structure standard",
                      {item["check"] for item in data["not_run"]})

    def test_a_run_that_evaluated_everything_may_still_say_clean(self):
        """The word is not banned, it is earned. Unit-level, because assembling a fixture that
        satisfies the full structure standard would test the fixture, not the rule."""
        report = validator.Report()
        status, code, summary = report.verdict()
        self.assertEqual((status, code), ("clean", 0))
        self.assertIn("clean — every route resolves", summary)

        report.not_evaluated("README contract", "not requested")
        status, code, summary = report.verdict()
        self.assertEqual(status, "partial")
        self.assertEqual(code, 0, "a family nobody requested is not a failure")
        self.assertNotIn("clean —", summary)

    def test_a_partial_run_with_an_error_exits_one(self):
        """R1. The docstring said "partial deliberately keeps exit 0". It does not, and never did.

        This assertion is what makes that sentence unwriteable. The default-flag path — which is
        every pre-commit run and every SessionStart run, since disclosure-check.sh passes only
        `--readme --hook` — reports `partial` because `--standard` and `--vs` did not run, AND
        exits 1 because the checks that did run found an ERROR. Both at once.

        Load-bearing, not cosmetic: TC-37 consumes this payload, and a maintainer who mapped
        `status == "partial"` to non-blocking would swallow every ERROR on the fleet.
        """
        rc, out = run(self.repo(broken_links=1), "--json")
        data = json.loads(out)
        self.assertEqual((data["status"], data["exit"], rc), ("partial", 1, 1), out)
        self.assertTrue(data["errors"], "fixture produced no ERROR, so this proves nothing")
        self.assertTrue(data["not_run"], "fixture ran every family, so it is not partial")

    def test_not_evaluated_never_changes_the_exit_code(self):
        """The claim that IS true, asserted so that it stays the one being made.

        A family nobody requested must not fail a run and must not rescue one either. Exhaustive
        over the combinations that matter, each built twice — with and without a not-run family —
        so the property is a comparison rather than a restatement of the implementation.
        """
        for errors, warns, notes in ((0, 0, 0), (1, 0, 0), (0, 1, 1), (2, 1, 1)):
            with self.subTest(errors=errors, warns=warns, notes=notes):
                def build():
                    report = validator.Report()
                    for i in range(errors):
                        report.error("broken-link", "AGENTS.md", f"-> gone-{i}.md")
                    for i in range(warns):
                        report.warn("orphan", f"doc-{i}.md", "nothing links here")
                    for i in range(notes):
                        report.note("lessons-entries", f"n-{i}.md", "long")
                    return report

                without = build()
                with_gap = build()
                with_gap.not_evaluated("README contract", "not requested")

                self.assertEqual(without.verdict()[1], with_gap.verdict()[1],
                                 "a family that did not run moved the exit code")
                self.assertEqual(with_gap.verdict()[1], 1 if errors else 0,
                                 "the exit code must be decided by errors alone")

    def test_a_not_run_cannot_be_out_voted_by_having_no_findings(self):
        """The precise absorption being prevented: zero errors must not buy back the word."""
        report = validator.Report()
        report.not_evaluated("README contract", "not requested")
        self.assertEqual(report.errors, [])
        self.assertEqual(report.warns, [])
        self.assertEqual(report.verdict()[0], "partial")

    def test_hook_mode_names_the_gap_whenever_it_speaks_at_all(self):
        """Silent on a healthy project (it fires every session, everywhere); honest when it talks."""
        rc, quiet = run(self.repo(), "--hook")
        self.assertEqual((rc, quiet.strip()), (0, ""))

        rc, loud = run(self.repo(broken_links=1), "--hook")
        self.assertEqual(rc, 1, loud)
        self.assertIn("NOT RUN [README contract]", loud)


class OptInFamilyDeclarationTest(unittest.TestCase):
    """Structural. One chokepoint, and nothing may bypass it.

    The behavioural tests above cover the three opt-in families that exist today. This covers the
    fourth one, added next year by someone who has not read any of this: a flag-gated check with no
    `else` branch would silently restore the defect and every test above would stay green.
    """

    def setUp(self):
        self.tree = ast.parse(VALIDATOR.read_text(encoding="utf-8"))
        self.collect = find_function(self, self.tree, "collect")

    def test_every_flag_gated_check_declares_its_absence(self):
        """Walks the WHOLE of `collect`, not just its top level.

        The first version iterated `collect.body`, so a family gated inside a nested block — a
        `for`, a `with`, another `if` — bypassed the rule entirely. `ast.walk` closes that at no
        cost in machinery.
        """
        offenders = []
        for node in ast.walk(self.collect):
            if not isinstance(node, ast.If):
                continue
            flags = {n.attr for n in ast.walk(node.test)
                     if isinstance(n, ast.Attribute)
                     and isinstance(n.value, ast.Name) and n.value.id == "args"}
            if not flags:
                continue
            # A CHECK FAMILY, not any use of a setting in a condition. Walking the whole function
            # also reaches `if d > args.max_depth: report.warn(...)`, which is a finding condition
            # inside a loop — it decides a finding, not whether a family of checks runs, and
            # demanding a `not_evaluated` there would be noise that gets the rule switched off.
            gates_a_family = any(isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
                                 and c.func.id.startswith("check_")
                                 for stmt in node.body for c in ast.walk(stmt))
            if not gates_a_family:
                continue
            declares = any(isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)
                           and c.func.attr == "not_evaluated"
                           for stmt in node.orelse for c in ast.walk(stmt))
            if not declares:
                offenders.append(f"line {node.lineno}: gated on {sorted(flags)} with no "
                                 f"report.not_evaluated(...) in its else branch")
        self.assertEqual(offenders, [],
                         "a check family may not be skipped silently:\n  " + "\n  ".join(offenders))

    def test_no_check_is_handed_args_to_gate_itself_with(self):
        """The second bypass: move the gate INSIDE the callee and this file sees nothing.

        `check_readme(root, files, report)` receives settled values. A `check_x(root, args, report)`
        could return early on `args.readme` with no `If` here at all, and the rule above would pass
        serenely over a silently skipped family. Individual `args.<flag>` values are fine — those
        are gated at this level, which is where the declaration lives.
        """
        offenders = []
        for node in ast.walk(self.collect):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", "?")
            for argument in list(node.args) + [kw.value for kw in node.keywords]:
                if isinstance(argument, ast.Name) and argument.id == "args":
                    offenders.append(f"line {node.lineno}: `{name}` is handed the whole `args`, so "
                                     f"it can gate itself where no declaration is visible")
        self.assertEqual(offenders, [], "\n  ".join(offenders))

    def test_the_clean_sentence_exists_in_exactly_one_place(self):
        """Existence AND uniqueness. Twin of the test in test_check_toolchain.py.

        The first version asserted only that no success sentence lived outside `Report.verdict` —
        which deleting the sentence from `Report.verdict` as well also satisfied. It matched a
        single literal prefix, so a reworded claim escaped it too.
        """
        claims = claim_strings(self.tree)
        printed = printed_nodes(self.tree)
        verdict = find_function(self, self.tree, "verdict")
        inside_ids = {id(n) for n in ast.walk(verdict)}

        emitted = [f"line {n.lineno}: {n.value!r}" for n in claims
                   if id(n) in printed and id(n) not in inside_ids]
        self.assertEqual(emitted, [], "a success claim printed without passing Report.verdict:\n  "
                                      + "\n  ".join(emitted))

        # The existence half, and it is WEAKER HERE THAN IT LOOKS — said plainly, because the twin
        # in test_check_toolchain.py says so and this one used to imply otherwise. `Report.verdict`
        # holds two claim-matching constants ("no findings in what ran" also matches), so deleting
        # the success sentence still leaves `len(inside) >= 1` and this assertion would not fire.
        # What actually carries existence end to end is
        # `test_a_run_that_evaluated_everything_may_still_say_clean`, which asserts the rendered
        # sentence contains "clean — every route resolves" and fails the moment it is deleted.
        # This half is a coarse backstop for total removal of the vocabulary, nothing more.
        inside = [n for n in claims if id(n) in inside_ids]
        self.assertGreaterEqual(len(inside), 1,
                                "Report.verdict contains no success vocabulary at all — see "
                                "test_a_run_that_evaluated_everything_may_still_say_clean, which "
                                "is the test that really pins the sentence's existence")

    def test_the_verdict_is_the_only_thing_main_returns_to_the_shell(self):
        """F8. `return 1 if report.errors else 0` was a second, independent decision site.

        Nothing held it consistent with the sentence `Report.verdict` had just composed, and two
        decision sites free to disagree is this card's defect class one level up. One function
        decides; `main` reports what it decided.
        """
        main = find_function(self, self.tree, "main")
        returned = set()
        for node in ast.walk(main):
            if not isinstance(node, ast.Return) or node.value is None:
                continue
            if isinstance(node.value, ast.Name):
                returned.add(node.value.id)
            elif isinstance(node.value, ast.Constant):
                returned.add(repr(node.value.value))
            elif isinstance(node.value, ast.Call) and getattr(node.value.func, "id", "") \
                    == "report_could_not_run":
                # Not a second decision: that function IS the "no verdict was reached" chokepoint,
                # it prints its own caveat, and it returns 2 unconditionally.
                returned.add("report_could_not_run()")
            else:
                returned.add(f"a computed expression at line {node.value.lineno}")
        self.assertEqual(returned, {"code", "2", "report_could_not_run()"}, returned)


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
