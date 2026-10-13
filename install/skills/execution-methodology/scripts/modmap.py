"""The test-module map docs/goals/modules.json: load and check it, select modules for write globs,
and list tracked files no module covers. Also the glob helpers that goal.py and gate.py share.

{"replaces": "<command>"?, "modules": {"<name>": {"paths": [...], "needs": [...], "test": "<command>",
"count": "none"?}}, "shared": [...]}; unknown keys are errors, and modules keep their file order.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

MAP = "docs/goals/modules.json"
TOP_KEYS = ("replaces", "modules", "shared")
MODULE_KEYS = ("paths", "needs", "test", "count")
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")

class MapError(Exception):
    pass

def glob_re(pattern: str):
    """'**' spans directories, '*' and '?' stay within one segment, anything else is literal."""
    tr = {"**/": "(?:.*/)?", "**": ".*", "*": "[^/]*", "?": "[^/]"}
    parts = re.split(r"(\*\*/|\*\*|\*|\?)", pattern + ("**" if pattern.endswith("/") else ""))
    return re.compile("".join(tr.get(p, re.escape(p)) for p in parts) + r"\Z")

def matches(path, patterns):
    return any(glob_re(p).match(path) for p in patterns)

def overlap(a_globs, b_globs) -> bool:
    """True when two write sets could name a common path (conservative for two globs)."""
    def static(p):
        segs = p.split("/")
        k = next((i for i, s in enumerate(segs) if "*" in s or "?" in s), len(segs))
        return segs[:k], k == len(segs)
    for a in a_globs:
        for b in b_globs:
            (sa, ea), (sb, eb) = static(a), static(b)
            n = min(len(sa), len(sb))
            if (a == b if ea and eb else bool(glob_re(b if ea else a).match(a if ea else b)) if ea or eb
                    else sa[:n] == sb[:n]):
                return True
    return False

def strings(v) -> bool:
    return isinstance(v, list) and all(isinstance(x, str) for x in v)

def load(root) -> dict | None:
    """The map under root, None when the file is absent; MapError(text) when it is malformed: a field of
    the wrong type, or a module without a test string. An empty test or paths list is problems' to name."""
    path = Path(root) / MAP
    if not path.is_file():
        return None
    try:
        m = json.loads(path.read_text())
    except ValueError as exc:
        raise MapError(f"not valid JSON: {exc}") from None
    if not isinstance(m, dict) or not isinstance(m.get("modules", {}), dict):
        raise MapError("the map and its modules must be JSON objects")
    if extra := [k for k in m if k not in TOP_KEYS]:
        raise MapError(f"unknown key {extra[0]!r}")
    if "replaces" in m and not (isinstance(m["replaces"], str) and m["replaces"].strip()):
        raise MapError("replaces must be a non-empty command")
    if "shared" in m and not strings(m["shared"]):
        raise MapError("shared must be a list of globs")
    for name, spec in m.get("modules", {}).items():
        if not NAME_RE.match(name):
            raise MapError(f"module name {name!r} does not match {NAME_RE.pattern}")
        if not isinstance(spec, dict):
            raise MapError(f"module {name} must be a JSON object")
        if extra := [k for k in spec if k not in MODULE_KEYS]:
            raise MapError(f"module {name} has unknown key {extra[0]!r}")
        if not isinstance(spec.get("test"), str):
            raise MapError(f"module {name} needs a test command string")
        if bad := [k for k in ("paths", "needs") if k in spec and not strings(spec[k])]:
            raise MapError(f"module {name} {bad[0]} must be a list of strings")
        if "count" in spec and spec["count"] != "none":
            raise MapError(f"module {name} has count {spec['count']!r}; only \"none\" is allowed")
    return m

def problems(m) -> list[str]:
    """Unknown needs, needs cycles, missing test commands, missing paths and shared test commands."""
    mods = m.get("modules") or {}
    out = [f"module {a} needs {b}, which is not a module" for a, s in mods.items() for b in s.get("needs") or []
           if b not in mods]
    state = {}  # a module's DFS state: 1 while on the path, 2 once finished

    def visit(a, path):
        state[a] = 1
        for b in (n for n in mods[a].get("needs") or [] if n in mods):
            if state.get(b) == 1:
                out.append("modules needs cycle: " + " -> ".join(path[path.index(b):] + [b]))
            elif b not in state:
                visit(b, path + [b])
        state[a] = 2
    for a in mods:
        if a not in state:
            visit(a, [a])
    out += [f"module {a} has no test command" for a, s in mods.items() if not str(s.get("test") or "").strip()]
    out += [f"module {a} has no paths" for a, s in mods.items() if not s.get("paths")]
    names = list(mods)
    out += [f"modules {a} and {b} share one test command" for i, a in enumerate(names) for b in names[i + 1:]
            if mods[a].get("test") and mods[a].get("test") == mods[b].get("test")]
    return out

def tree(g):
    """A glob ending in / names its directory's whole tree, as glob_re reads it."""
    return g + "**" if g.endswith("/") else g

def contained(w, g) -> bool:
    """True when module glob g covers every path write glob w can name (a trailing / reads as /**)."""
    w, g = tree(w), tree(g)
    return ("*" not in w and "?" not in w and bool(glob_re(g).match(w))) or (
        g.endswith("/**") and w.startswith(g[:-2]))

def select(m, write_globs) -> list[str]:
    """Module names in file order: every module when a write glob overlaps shared or no single module
    glob contains it; otherwise the modules a write glob overlaps, plus every module needing a selected one."""
    mods, writes = m.get("modules") or {}, [tree(w) for w in write_globs]
    paths = {a: [tree(g) for g in s.get("paths") or []] for a, s in mods.items()}
    owned = [g for gs in paths.values() for g in gs]
    if (overlap(writes, [tree(g) for g in m.get("shared") or []])
            or not all(any(contained(w, g) for g in owned) for w in writes)):
        return list(mods)
    chosen = {a for a in mods if overlap(paths[a], writes)}
    todo = list(chosen)
    while todo:
        b = todo.pop()
        for a, s in mods.items():
            if b in (s.get("needs") or []) and a not in chosen:
                chosen.add(a)
                todo.append(a)
    return [a for a in mods if a in chosen]

def unmapped(m, files) -> list[str]:
    """The files that no module path and no shared glob matches."""
    globs = [g for s in (m.get("modules") or {}).values() for g in s.get("paths") or []] + list(m.get("shared") or [])
    return [f for f in files if not matches(f, globs)]
