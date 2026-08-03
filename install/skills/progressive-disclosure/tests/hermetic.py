"""What stops a test in this directory from answering about a machine it is not running on.

WHY THIS FILE EXISTS, as measured rather than as a principle. TC-48 made a HALF-tree
unconstructible: a replica missing files produced three confident, specific, wrong failures against
a green HEAD. The barrier it built asks "is this tree complete?" — and a COMPLETE `git archive HEAD`
of this repository, unpacked under a redirected `HOME`, STILL fails:

    FAIL: test_unknown_severity_is_loud_but_not_fatal
    AssertionError: 2 != 1
      NOT-RUN  ... `$HOME/.claude/plugins/installed_plugins.json` ...
      NOT-RUN  ... `$HOME/.codex/config.toml` is absent ...

Nothing was missing from the tree. The test reached PAST the tree, past the redirected `HOME`, to
whatever `Path.home()` happened to be when `check_toolchain.py` was imported — and on the developer's
own machine that read a real `~/.claude/plugins` and a real `~/.codex/config.toml` and passed. So
COMPLETENESS IS NOT THE PROPERTY THAT MATTERS. Hermeticity is. Adding more files to the replica
cannot fix a test that is not looking at the replica.

WHAT AN ESCAPE IS, stated narrowly enough to be decidable from the source. A test escapes when it
can read `~/.claude` or `~/.codex` **on the machine running it** rather than a tree the test itself
built. Three mechanisms, all statically visible:

  1. IN-PROCESS. It reads a `check_toolchain` module global derived from `Path.home()` — directly,
     or transitively through a function of that module — without first rebinding it. `main()` is the
     worst of these: it reaches SEVEN such globals, and `test_unknown_severity_is_loud_but_not_fatal`
     replaced `DEFAULT_CHECKS` with a synthetic pair and never noticed that `collect()` also calls
     `check_plugins()` and `check_tracking()` unconditionally, outside that table.
  2. SUBPROCESS. It launches a `scripts/*.py` that calls `Path.home()`, without pinning `HOME` in the
     child's environment — so the child inherits the parent's.
  3. DIRECTLY. The test, or a helper it calls, evaluates `Path.home()` itself.

WHAT IS DELIBERATELY NOT AN ESCAPE. `git`, `bash` and every other subprocess that is not one of this
skill's own HOME-reading scripts. `git` does read `$HOME/.gitconfig`, and a rule broad enough to
catch that flags 40-odd tests whose only sin is calling `git init` — a derivation that names
everything names nothing. The scope here is `~/.claude` and `~/.codex`, which is the family that
produced the failure.

TWO WAYS OUT, AND BOTH ARE ENFORCED. A test either becomes hermetic — `synthetic_home()` rebinds
every home-derived global at once, or the subprocess pins `HOME` — or it is marked
`@reaches_home(reason)` because reaching the real machine IS its job. `ReachesHomeTest` in
`test_check_toolchain.py` asserts the derived set and the marked set are EQUAL, in both directions:
an unmarked escape fails, and so does a mark left behind on a test that stopped escaping. That is
what makes the mark enforced rather than written.

THE DERIVATION IS ONLY AS TRUE AS THE WALK, and this programme has a matcher that missed `ast.IfExp`
heads for three rounds and a grep-derived list that was wrong on three of seven entries the day it
was committed. So `test_the_walk_sees_every_shape_it_claims_to` runs the analyser over a SYNTHETIC
module written in the test, carrying one assignment per shape — including an `IfExp` — and
`test_a_planted_escape_is_caught` plants each of the three mechanisms in a temporary test file and
requires the derivation to name it. The plants live in files this analyser has never seen, which is
also how the self-measurement trap is avoided: this module's own text is not in the search space,
because the analyser looks only at FUNCTIONS WHOSE NAME STARTS WITH `test` INSIDE A CLASS, and
everything here is a module-level function.

AND THE PLANTS THEMSELVES WERE SHAPE-BIASED THE FIRST TIME, which is the correction this file
carries rather than hides. The subprocess arm originally recognised a launch only when the script's
FILE NAME appeared as a string constant inside argv — and all four plants were written
`str(SCRIPTS / "check_toolchain.py")`, the one spelling that worked. Two real sites in this
directory are spelled `str(CHECKER)` against a module-level binding and carry no string constant at
all, so both were invisible while the two-way equality below reported a clean directory; one of them
launches `check_github.py`, which does `CACHE_DIR.mkdir(parents=True, exist_ok=True)` under
`Path.home()` and so was CREATING A DIRECTORY IN THE REAL `$HOME`. A planted mutation only ever
proves the detector sees the shapes that were planted. The argv arm now resolves a `Name`/
`Attribute` through its binding — the same resolution `_pins_home` always did for `env` — and FAILS
CLOSED: an interpreter launch whose script slot cannot be resolved to a `*.py` at all is reported as
an escape, because "the walk did not understand this" and "this is hermetic" are different answers.

NO SECOND REPLICA BUILDER, and nothing here builds a tree at all. TC-48's `complete_tree.build()`
materialises a replica of THIS REPOSITORY for the agent-personas suite; `plant_allowlisted_home()`
and `green_home()` in `test_check_toolchain.py` build synthetic HOMEs. This file plants no files. It
reads source and rebinds module globals, and the two tests made hermetic below reuse `green_home`
and `synthetic_home` rather than constructing anything new.
"""

from __future__ import annotations

import ast
import contextlib
import functools
import inspect
from pathlib import Path


TESTS = Path(__file__).resolve().parent
SKILL = TESTS.parent
SCRIPTS = SKILL / "scripts"
CHECKER = SCRIPTS / "check_toolchain.py"


class NotHermetic(AssertionError):
    """A test can read this machine. Deliberately not `SkipTest`: see `reaches_home`."""


# --------------------------------------------------------------------------------------------
# The walk.

def _reads_home(node: ast.AST, known: frozenset[str] | set[str]) -> bool:
    """Does this expression reach `Path.home()`, directly or through an already-known name?

    `ast.walk` rather than a shape match, on purpose. The shape a matcher forgets is the one that
    gets used: `X = Path.home() / "a" if flag else Path("/b")` hides the call in an `ast.IfExp`
    head, and a matcher that only understood `BinOp` and `Attribute` chains missed exactly that for
    three rounds elsewhere in this programme. Walking descends every node type there is.

    `.expanduser()` is NOT a trigger. `Path(args.reviews).expanduser()` expands a path the CALLER
    chose; it is only HOME-dependent if the caller passed `~`, and treating it as a machine read
    would flag every argument-parsing script in `scripts/`.
    """
    for child in ast.walk(node):
        if (isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute)
                and child.func.attr == "home"):
            return True
        if isinstance(child, ast.Name) and child.id in known:
            return True
    return False


def home_derived_globals(source: Path) -> frozenset[str]:
    """Every module-level name in `source` whose value comes from `Path.home()`.

    A FIXED POINT, not a single pass: `CLAUDE_SKILLS = HOME / ".claude" / "skills"` and then
    `SYNC = CLAUDE_SKILLS / ... ` and then `INSTALLED_PLUGINS = CLAUDE_PLUGINS / ...`. A one-pass
    scan in source order happens to get these three right today and would silently miss a name
    defined above the name it derives from.
    """
    module = ast.parse(source.read_text(encoding="utf-8"))
    known: set[str] = set()
    changed = True
    while changed:
        changed = False
        for statement in module.body:
            targets = (statement.targets if isinstance(statement, ast.Assign)
                       else [statement.target] if isinstance(statement, ast.AnnAssign) else [])
            if len(targets) != 1 or not isinstance(targets[0], ast.Name):
                continue
            name = targets[0].id
            if name in known or statement.value is None:
                continue
            if _reads_home(statement.value, known):
                known.add(name)
                changed = True
    return frozenset(known)


def home_reading_scripts() -> frozenset[str]:
    """The file names under `scripts/` that call `Path.home()` anywhere.

    File NAMES rather than paths, because that is what a test's argv carries as a literal.
    """
    reading = set()
    for script in sorted(SCRIPTS.glob("*.py")):
        tree = ast.parse(script.read_text(encoding="utf-8"))
        if _reads_home(tree, frozenset()):
            reading.add(script.name)
    return frozenset(reading)


def _checker_functions() -> tuple[dict[str, ast.FunctionDef], frozenset[str]]:
    module = ast.parse(CHECKER.read_text(encoding="utf-8"))
    functions = {s.name: s for s in module.body if isinstance(s, ast.FunctionDef)}
    return functions, home_derived_globals(CHECKER)


def checker_reach() -> dict[str, frozenset[str]]:
    """For every function in `check_toolchain.py`, the home-derived globals it can reach.

    TRANSITIVE and deliberately an OVER-approximation at function granularity: `main()` is credited
    with everything `collect()` touches even when the mode under test returns before `collect()` is
    called. That is the safe direction for a barrier — the alternative is a path-sensitive analysis
    whose bugs are silent — and the cost is that two tests are made hermetic that could have argued
    they did not need to be. Both are cheaper to fix than to argue about.
    """
    functions, home_names = _checker_functions()
    resolved: dict[str, frozenset[str]] = {}

    def walk(name: str, stack: tuple[str, ...]) -> frozenset[str]:
        if name in resolved:
            return resolved[name]
        if name in stack:              # recursion: the caller already accounts for this frame
            return frozenset()
        found: set[str] = set()
        for node in ast.walk(functions[name]):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                if node.id in home_names:
                    found.add(node.id)
                elif node.id in functions:
                    found |= walk(node.id, stack + (name,))
        result = frozenset(found)
        if not stack:
            resolved[name] = result
        return result

    return {name: walk(name, ()) for name in functions}


# --------------------------------------------------------------------------------------------
# The analysis of one test file.

def _pins_home(call: ast.Call, scope: ast.AST) -> bool:
    """Does this `subprocess.run` pin `HOME` in the child's environment?

    Three spellings are accepted because all three are in use here: a dict display with a `"HOME"`
    key, `dict(os.environ, HOME=...)`, and a name bound to either of those earlier in the same
    function. Anything else is treated as NOT pinned — an analyser that guessed in the reassuring
    direction is how a barrier stops being one.
    """
    env = next((kw.value for kw in call.keywords if kw.arg == "env"), None)
    if env is None:
        return False

    def pinned(node: ast.AST) -> bool:
        if isinstance(node, ast.Dict):
            return any(isinstance(k, ast.Constant) and k.value == "HOME" for k in node.keys)
        if isinstance(node, ast.Call):
            return any(kw.arg == "HOME" for kw in node.keywords)
        return False

    if pinned(env):
        return True
    if isinstance(env, ast.Name):
        for node in ast.walk(scope):
            if isinstance(node, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id == env.id for t in node.targets):
                if pinned(node.value):
                    return True
    return False


def _binding(name: str, scope: ast.AST, module: ast.Module) -> ast.AST | None:
    """The expression `name` was last assigned, looked for in `scope` first and then module level.

    The same name resolution `_pins_home` already does for `env`, lifted out so the argv arm can
    use it too. That asymmetry — `env` resolved through a name and argv did not — is exactly the
    hole this function closes: `run([sys.executable, str(CHECKER), ...])` carries no string
    constant at all, so a walk that only collected `ast.Constant` saw an empty argv and recorded
    nothing.
    """
    found = None
    for node in ast.walk(scope):
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == name for t in node.targets):
            found = node.value
    if found is not None:
        return found
    for statement in module.body:
        targets = (statement.targets if isinstance(statement, ast.Assign)
                   else [statement.target] if isinstance(statement, ast.AnnAssign) else [])
        if any(isinstance(t, ast.Name) and t.id == name for t in targets):
            found = statement.value
    return found


def _is_interpreter(node: ast.AST) -> bool:
    return (isinstance(node, ast.Attribute) and node.attr == "executable"
            and isinstance(node.value, ast.Name) and node.value.id == "sys")


def _argv_elements(argv: ast.AST | None, scope: ast.AST,
                   module: ast.Module) -> list[ast.AST] | None:
    """`argv` as a list of element nodes, resolving one level of name binding.

    `command = [sys.executable, ...]` followed by `subprocess.run(command)` is in this directory
    and is otherwise invisible for the same reason `str(CHECKER)` was.
    """
    if isinstance(argv, (ast.List, ast.Tuple)):
        return list(argv.elts)
    if isinstance(argv, ast.Name):
        bound = _binding(argv.id, scope, module)
        if isinstance(bound, (ast.List, ast.Tuple)):
            return list(bound.elts)
    return None


def _script_slot(elements: list[ast.AST]) -> ast.AST | None:
    """In `[sys.executable, <here>, ...]`, the element that names what will be run.

    Leading flag constants are skipped, so `-X faulthandler` is not mistaken for the script. That
    also means `-m mod` and `-c code` land on an element that resolves to no `.py`, which is
    treated as unresolvable and therefore fails closed; there is no such call in this directory
    today, and pinning `HOME` clears it if one appears.
    """
    for index, element in enumerate(elements):
        if not _is_interpreter(element):
            continue
        for later in elements[index + 1:]:
            if (isinstance(later, ast.Constant) and isinstance(later.value, str)
                    and later.value.startswith("-")):
                continue
            return later
        return None                     # `[sys.executable]` alone runs nothing
    return None


def _resolved_script(node: ast.AST | None, scope: ast.AST, module: ast.Module,
                     seen: tuple[str, ...] = ()) -> str | None:
    """The `*.py` file name this element denotes, or `None` if the walk cannot tell.

    `None` is the FAIL-CLOSED answer, not the reassuring one: the caller treats an unresolvable
    script slot as an escape unless `HOME` is pinned. An analyser that guessed "probably fine" for
    the spelling it did not understand is precisely what let two real sites through.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return Path(node.value).name if node.value.endswith(".py") else None
    if isinstance(node, ast.Call):                       # `str(X)`, `os.fspath(X)`
        return _resolved_script(node.args[0], scope, module, seen) if node.args else None
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        return _resolved_script(node.right, scope, module, seen)
    if isinstance(node, (ast.Name, ast.Attribute)):
        key = node.id if isinstance(node, ast.Name) else node.attr
        if key in seen:
            return None
        bound = _binding(key, scope, module)
        return _resolved_script(bound, scope, module, seen + (key,)) if bound is not None else None
    return None


def _escapes_in(node: ast.AST, *, scope: ast.AST, module: ast.Module,
                helpers: dict[str, ast.FunctionDef],
                methods: dict[str, ast.FunctionDef], module_home_names: frozenset[str],
                reach: dict[str, frozenset[str]], checker_home_names: frozenset[str],
                scripts: frozenset[str], stack: tuple[str, ...]) -> tuple[set[str], set[str], set[str]]:
    """(globals read, globals rebound, other reasons) reachable from `node`.

    Follows module-level helper functions and `self.<method>` calls — including through `with`
    items, which is how `CodexMirrorRemedyTest.mirror` (a `@contextmanager` METHOD that rebinds
    `CLAUDE_SKILLS`) is credited with its patch. An earlier version of this walk resolved only
    module-level functions and reported six tests as escaping that were already hermetic.
    """
    reads: set[str] = set()
    rebound: set[str] = set()
    other: set[str] = set()

    for child in ast.walk(node):
        if isinstance(child, ast.Assign):
            for target in child.targets:
                for element in (target.elts if isinstance(target, ast.Tuple) else [target]):
                    if (isinstance(element, ast.Attribute)
                            and isinstance(element.value, ast.Name)
                            and element.value.id == "toolchain"
                            and element.attr in checker_home_names):
                        rebound.add(element.attr)

        if (isinstance(child, ast.Attribute) and isinstance(child.value, ast.Name)
                and child.value.id == "toolchain"):
            if child.attr in checker_home_names:
                reads.add(child.attr)
            elif child.attr in reach:
                reads |= reach[child.attr]

        if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load):
            if child.id in module_home_names:
                other.add(f"reads the module constant `{child.id}`, which comes from Path.home()")

        if isinstance(child, ast.Call):
            function = child.func
            if (isinstance(function, ast.Attribute) and function.attr == "home"):
                other.add("calls Path.home() itself")

            target = None
            if isinstance(function, ast.Name) and function.id in helpers:
                target = (function.id, helpers[function.id])
            elif (isinstance(function, ast.Attribute) and isinstance(function.value, ast.Name)
                  and function.value.id == "self" and function.attr in methods):
                target = (function.attr, methods[function.attr])
            if target and target[0] not in stack:
                inner = _escapes_in(
                    target[1], scope=target[1], module=module, helpers=helpers, methods=methods,
                    module_home_names=module_home_names, reach=reach,
                    checker_home_names=checker_home_names, scripts=scripts,
                    stack=stack + (target[0],))
                reads |= inner[0]
                rebound |= inner[1]
                other |= inner[2]

            # The named escape hatch: `synthetic_home` rebinds EVERY home-derived global at once,
            # and `test_synthetic_home_rebinds_every_home_derived_global` is what stops that claim
            # from becoming a lie the day an eighth global is added.
            if ((isinstance(function, ast.Name) and function.id == "synthetic_home")
                    or (isinstance(function, ast.Attribute) and function.attr == "synthetic_home")):
                rebound |= set(checker_home_names)

            if (isinstance(function, ast.Attribute) and function.attr == "run"
                    and isinstance(function.value, ast.Name) and function.value.id == "subprocess"):
                argv = child.args[0] if child.args else None
                elements = _argv_elements(argv, scope, module)
                searchable = elements if elements is not None else ([argv] if argv else [])
                named = {a.value for e in searchable for a in ast.walk(e)
                         if isinstance(a, ast.Constant) and isinstance(a.value, str)}
                launched = set(named & scripts)

                # The interpreter arm. `named` only ever sees a script whose FILE NAME is spelled
                # as a string constant inside argv; `[sys.executable, str(CHECKER), ...]` carries
                # no string constant at all, so the whole mechanism was silent for it. Resolve the
                # script slot through its binding instead, and fail closed when that fails.
                unresolved: str | None = None
                if elements is not None:
                    slot = _script_slot(elements)
                    if slot is not None:
                        resolved = _resolved_script(slot, scope, module)
                        if resolved is None:
                            unresolved = ast.unparse(slot)
                        elif resolved in scripts:
                            launched.add(resolved)

                if (launched or unresolved) and not _pins_home(child, scope):
                    if launched:
                        other.add(f"launches {', '.join(sorted(launched))} (which calls "
                                  f"Path.home()) without pinning HOME in the child's env, "
                                  f"line {child.lineno}")
                    if unresolved:
                        other.add(f"launches the interpreter on `{unresolved}`, which this walk "
                                  f"cannot resolve to a script file, without pinning HOME in the "
                                  f"child's env, line {child.lineno}")

    return reads, rebound, other


def escaping_tests(directory: Path | None = None) -> dict[tuple[str, str], list[str]]:
    """Every test in `directory` that can read this machine, keyed by `(file name, Class.method)`.

    The value is the list of reasons, so a failure names the mechanism rather than only the test.
    """
    directory = TESTS if directory is None else directory
    reach = checker_reach()
    _, checker_home_names = _checker_functions()
    scripts = home_reading_scripts()
    found: dict[tuple[str, str], list[str]] = {}

    for path in sorted(directory.glob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        helpers = {s.name: s for s in tree.body if isinstance(s, ast.FunctionDef)}
        classes = {c.name: c for c in tree.body if isinstance(c, ast.ClassDef)}
        module_home_names = home_derived_globals(path)

        def methods_of(cls: ast.ClassDef) -> dict[str, ast.FunctionDef]:
            inherited: dict[str, ast.FunctionDef] = {}
            for base in cls.bases:
                if isinstance(base, ast.Name) and base.id in classes:
                    inherited.update(methods_of(classes[base.id]))
            inherited.update({f.name: f for f in cls.body if isinstance(f, ast.FunctionDef)})
            return inherited

        for cls in classes.values():
            methods = methods_of(cls)
            for method in [f for f in cls.body
                           if isinstance(f, ast.FunctionDef) and f.name.startswith("test")]:
                reads, rebound, other = _escapes_in(
                    method, scope=method, module=tree, helpers=helpers, methods=methods,
                    module_home_names=module_home_names, reach=reach,
                    checker_home_names=checker_home_names, scripts=scripts, stack=())
                reasons = sorted(other)
                unpatched = sorted(reads - rebound)
                if unpatched:
                    reasons.append("reads check_toolchain's " + ", ".join(unpatched)
                                   + " without rebinding them")
                if reasons:
                    found[(path.name, f"{cls.name}.{method.name}")] = reasons
    return found


# --------------------------------------------------------------------------------------------
# The two ways out.

@contextlib.contextmanager
def synthetic_home(toolchain, root: Path):
    """Point every home-derived global of `toolchain` at `root`, then put them back.

    DERIVED, NOT LISTED. The set comes from `home_derived_globals(CHECKER)` and each new value is
    computed as `root / old.relative_to(old_HOME)`, so an eighth global added to the checker
    tomorrow is rebound by the commit that adds it rather than by a later one. A hand-written list
    here would be an annotation, and an annotation is only as true as whatever checks it.

    It asserts the rebind LANDED before yielding — a context manager that silently rebound nothing
    would leave every test inside it reading the real machine while reading as hermetic, which is
    precisely the failure this file exists to remove.
    """
    root = Path(root)
    names = sorted(home_derived_globals(CHECKER))
    original = {name: getattr(toolchain, name) for name in names}
    base = original["HOME"]
    try:
        for name in names:
            if name == "HOME":
                setattr(toolchain, name, root)
                continue
            setattr(toolchain, name, root / Path(original[name]).relative_to(base))
        still_real = [n for n in names if base in Path(getattr(toolchain, n)).parents
                      or Path(getattr(toolchain, n)) == base]
        if still_real:
            raise NotHermetic(
                f"synthetic_home({root}) did not rebind {still_real}; the block it guards would "
                f"read the real machine while reading as hermetic.")
        yield root
    finally:
        for name, value in original.items():
            setattr(toolchain, name, value)


# `(file name, Class.method)` -> reason. Populated at import of each decorated module.
MARKED: dict[tuple[str, str], str] = {}


def reaches_home(reason: str):
    """Declare that this test reaches `Path.home()`, and say what for.

    TWO KINDS OF REASON, and the mark does not pretend they are the same. Most of the marked tests
    READ the real machine because that is their job — a drift detector comparing the committed
    literals against the live `~/.claude/.gitignore` cannot be given a synthetic one without
    becoming a tautology. One reaches `Path.home()` for ARITHMETIC ONLY: it computes
    `p.relative_to(Path.home())` to compare against what the installer returns, and opens nothing.
    The reason string is where that distinction lives, which is why an empty one is refused.

    Not `skipIf` and not a comment. The test still runs and still means what it meant; what changes
    is that its dependence is DECLARED, that `ReachesHomeTest` requires the declared set and the
    derived set to be equal, and that a failure says on which machine it was measured. A complete
    replica under a redirected `HOME` is not the tree these tests are about, and a failure there
    that reads like an ordinary defect is how three implementers were nearly filed against.
    """
    if not reason.strip():
        raise ValueError("reaches_home() requires a reason; a bare mark is a comment")

    def decorate(function):
        # A function defined INSIDE another function is a probe, not a suite declaration — the
        # analyser only ever looks at classes at module level, so registering one would put a key
        # in `MARKED` that the derivation can never produce and every run would report it stale.
        if "<locals>" not in function.__qualname__:
            MARKED[(Path(inspect.getfile(function)).name, function.__qualname__)] = reason

        @functools.wraps(function)
        def wrapper(self, *args, **kwargs):
            try:
                return function(self, *args, **kwargs)
            except AssertionError as failure:
                raise type(failure)(
                    f"{failure}\n\n"
                    f"-- THIS TEST IS @reaches_home: {reason}\n"
                    f"-- It was measured against Path.home() = {Path.home()}. If that is not the "
                    f"machine whose ~/.claude and ~/.codex you meant to judge — a replica, a "
                    f"redirected HOME, a container — this failure is about the wrong tree and "
                    f"says nothing about the code."
                ) from None
        return wrapper
    return decorate
