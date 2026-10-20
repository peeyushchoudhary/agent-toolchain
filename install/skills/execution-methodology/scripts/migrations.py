"""Validate approval-bound, literal Python test-file migrations and their proof requirements."""
from __future__ import annotations

import hashlib
import json
import re
import shlex


class MigrationError(ValueError):
    pass


PRESERVE_V1 = """import hashlib, json, pathlib, sys
bad = []
for path, digest in json.loads(sys.argv[1]):
    p = pathlib.Path(path)
    try:
        good = (p.is_file() and not any(q.is_symlink() for q in (p, *p.parents))
                and hashlib.sha256(p.read_bytes()).hexdigest() == digest)
    except OSError:
        good = False
    if not good:
        bad.append(path)
print('preservation: FAIL ' + ', '.join(bad) if bad else 'preservation: PASS')
sys.exit(1 if bad else 0)
"""
ENTRY_KEYS = {"module", "before", "after", "originals", "successors", "historical_claim", "reason"}
UNSAFE = set("\\$`;&|<>(){}*?[]~#")


def closed(value, keys, label):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise MigrationError(f"{label} must contain exactly {', '.join(sorted(keys))}")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise MigrationError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def controls(value):
    return any(ord(c) < 32 or 127 <= ord(c) < 160 for c in value)


def path_ok(path):
    return (nonempty(path) and not controls(path) and not any(c in UNSAFE for c in path)
            and not path.startswith(("/", "-", "@")) and "::" not in path and path.endswith(".py")
            and all(part not in ("", ".", "..") for part in path.split("/")))


def command(value):
    if not nonempty(value) or controls(value) or any(c in UNSAFE for c in value):
        raise MigrationError("test command must be literal Python test files without control characters")
    try:
        args = shlex.split(value)
    except ValueError as exc:
        raise MigrationError(f"invalid test command: {exc}") from None
    if len(args) < 4 or args[0] not in ("python3", "./py") or args[1] != "-m":
        raise MigrationError("test command needs python3 or ./py and a supported -m prefix")
    if args[2:4] == ["pytest", "-q"]:
        size = 4
    elif args[2] == "unittest":
        size = 4 if args[3] == "-q" else 3
    else:
        raise MigrationError("test command needs -m pytest -q or -m unittest [-q]")
    files = args[size:]
    if not files or any(not path_ok(p) for p in files) or len(set(files)) != len(files):
        raise MigrationError("test command needs unique canonical relative .py files")
    return args[:size], files


def regular(path, read, digest=None):
    obj = read(path)
    if (not isinstance(obj, tuple) or len(obj) != 2 or obj[0] not in ("100644", "100755")
            or not isinstance(obj[1], bytes)):
        raise MigrationError(f"{path}: missing tracked regular Git blob")
    if digest is not None and hashlib.sha256(obj[1]).hexdigest() != digest:
        raise MigrationError(f"{path}: original sha256 mismatch")


def parse(text, baseline_map, read):
    """Bind a closed declaration to its baseline commands and original tracked bytes."""
    try:
        data = json.loads(text, object_pairs_hook=unique_object)
    except (TypeError, ValueError) as exc:
        raise MigrationError(f"invalid migration declaration: {exc}") from None
    closed(data, {"version", "migrations"}, "declaration")
    if type(data["version"]) is not int or data["version"] != 1:
        raise MigrationError("migration version must be integer 1")
    if not isinstance(data["migrations"], list) or not data["migrations"]:
        raise MigrationError("migrations must be a nonempty list")
    modules = (baseline_map or {}).get("modules") or {}
    seen_modules, seen_paths, entries = set(), set(), []
    for item in data["migrations"]:
        closed(item, ENTRY_KEYS, "migration")
        name = item["module"]
        if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", name):
            raise MigrationError("migration module must be a canonical module name")
        if name in seen_modules:
            raise MigrationError(f"duplicate migration module {name}")
        seen_modules.add(name)
        spec = modules.get(name)
        if not isinstance(spec, dict) or spec.get("test") != item["before"]:
            raise MigrationError(f"module {name}: before must equal the baseline test command")
        if spec.get("count") == "none":
            raise MigrationError(f"module {name}: count none cannot migrate tests")
        if item["historical_claim"] != "BYTES_ONLY" or not nonempty(item["reason"]):
            raise MigrationError("migration requires historical_claim BYTES_ONLY and a nonempty reason")
        prefix, before = command(item["before"])
        after_prefix, after = command(item["after"])
        originals, successors = item["originals"], item["successors"]
        if not isinstance(originals, list) or not originals or not isinstance(successors, list) or not successors:
            raise MigrationError("originals and successors must be nonempty lists")
        removed = []
        for original in originals:
            closed(original, {"path", "sha256"}, "original")
            path, digest = original["path"], original["sha256"]
            if not path_ok(path) or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise MigrationError("original requires a canonical .py path and lowercase sha256")
            removed.append(path)
            regular(path, read, digest)
        paths = removed + successors
        if any(not path_ok(p) for p in paths) or len(set(paths)) != len(paths) or seen_paths.intersection(paths):
            raise MigrationError("migration source and successor paths must be canonical and unique")
        seen_paths.update(paths)
        if (prefix != after_prefix or any(p not in before or p in after for p in removed)
                or any(p in before for p in successors)
                or after != [p for p in before if p not in removed] + successors):
            raise MigrationError(f"module {name}: after must retain the prefix/file order then append successors")
        entries.append({**item, "_count": spec.get("count"), "_replaces": baseline_map.get("replaces"),
                        "_prefix": prefix})
    return entries


def allowed(entries, current_map, read):
    """Check immutable originals and exact activation; other map shrinkage belongs to the caller."""
    admitted = set()
    for entry in entries:
        name = entry["module"]
        spec = ((current_map or {}).get("modules") or {}).get(name)
        if (not isinstance(spec, dict) or spec.get("count") != entry["_count"]
                or current_map.get("replaces") != entry["_replaces"]):
            raise MigrationError(f"module {name}: missing module or changed count/replaces")
        for original in entry["originals"]:
            regular(original["path"], read, original["sha256"])
        if spec.get("test") == entry["after"]:
            for path in entry["successors"]:
                regular(path, read)
            admitted.add(name)
        elif spec.get("test") != entry["before"]:
            raise MigrationError(f"module {name}: command is neither approved before nor after")
    return admitted


def proofs(entry):
    """Canonical module, independent successor and byte-preservation receipt descriptors."""
    prefix = entry["_prefix"]
    pairs = [[original["path"], original["sha256"]] for original in entry["originals"]]
    return ([{"kind": "module", "module": entry["module"], "command": entry["after"], "tests": True}]
            + [{"kind": "successor", "module": None, "command": shlex.join(prefix + [path]), "tests": True}
               for path in entry["successors"]]
            + [{"kind": "preservation", "module": None, "tests": False,
                "command": shlex.join([prefix[0], "-c", PRESERVE_V1,
                                       json.dumps(pairs, separators=(",", ":"))])}])


def proof_ok(descriptor, receipt, tree):
    """A PASS must describe this command/tree, with typed clean counts and no waived failures."""
    if not isinstance(descriptor, dict) or not isinstance(receipt, dict):
        return False
    kind = descriptor.get("kind")
    module = descriptor.get("module")
    if (kind not in ("module", "successor", "preservation") or type(descriptor.get("tests")) is not bool
            or descriptor["tests"] != (kind != "preservation") or not nonempty(descriptor.get("command"))
            or (not nonempty(module) if kind == "module" else module is not None)):
        return False
    if (receipt.get("tree") != tree or receipt.get("command") != descriptor["command"]
            or receipt.get("module") != module or receipt.get("verdict") != "PASS"
            or type(receipt.get("exit")) is not int or receipt["exit"] != 0):
        return False
    counts = ("executed", "failed", "skipped")
    if any(type(receipt.get(k)) is not int or receipt[k] < 0 for k in counts):
        return False
    if receipt["failed"] or receipt["skipped"] or (descriptor["tests"] and not receipt["executed"]):
        return False
    if any(receipt.get(k) != [] for k in ("failures", "new_failures", "baseline_failures", "reasons")):
        return False
    if "suites" in receipt:
        suites = receipt["suites"]
        if not isinstance(suites, dict) or any(
                not isinstance(s, dict) or any(type(s.get(k)) is not int or s[k] < 0 for k in counts)
                for s in suites.values()):
            return False
        if any(sum(s[k] for s in suites.values()) != receipt[k] for k in counts):
            return False
    return True
