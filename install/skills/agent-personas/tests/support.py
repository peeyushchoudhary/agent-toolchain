"""Shared fixtures: a hermetic HOME and CODEX_HOME, and a disposable copy of the skill."""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import json
import re
import tempfile
import unittest
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    tomllib = None

SKILL = Path(__file__).resolve().parents[1]
SCRIPT = SKILL / "scripts" / "sync_personas.py"

_TABLE = re.compile(r"\[([A-Za-z0-9_-]+)\]")
_KEY = re.compile(r"([A-Za-z0-9_-]+) = (.+)")
_VALUE = re.compile(r'"(?:[^"\\]|\\.)*"|true|false|-?\d+|\[.*\]')


def parse_toml_subset(text: str) -> dict:
    """Exactly the TOML `render_codex` emits: comments, `[table]`, `key = value` with a JSON-style
    string, boolean, integer or array of strings, and one `'''` multi-line literal string. Anything
    else raises rather than being guessed at."""
    root: dict = {}
    table = root
    lines = iter(text.splitlines())
    for line in lines:
        if not line.strip() or line.startswith("#"):
            continue
        if m := _TABLE.fullmatch(line):
            if m[1] in root:
                raise ValueError(f"duplicate table: {line!r}")
            table = root[m[1]] = {}
            continue
        m = _KEY.fullmatch(line)
        if not m or m[1] in table:
            raise ValueError(f"unsupported TOML line: {line!r}")
        raw = m[2]
        if raw == "'''":
            body = []
            for body_line in lines:
                if body_line == "'''":
                    break
                body.append(body_line)
            else:
                raise ValueError("unterminated ''' string")
            table[m[1]] = "\n".join(body) + "\n" if body else ""
        elif _VALUE.fullmatch(raw):
            value = json.loads(raw)
            if isinstance(value, list) and not all(isinstance(v, str) for v in value):
                raise ValueError(f"only arrays of strings are supported: {line!r}")
            table[m[1]] = value
        else:
            raise ValueError(f"unsupported TOML value: {line!r}")
    return root


def toml_loads(text: str) -> dict:
    return tomllib.loads(text) if tomllib else parse_toml_subset(text)


def load_module(script: Path = SCRIPT):
    spec = importlib.util.spec_from_file_location(f"_sp_{abs(hash(script))}", script)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def frontmatter(text: str) -> dict:
    """The rendered Claude frontmatter as plain strings, quotes removed."""
    head = text.split("\n---", 1)[0].lstrip("-\n")
    out = {}
    for line in head.splitlines():
        if line.startswith("#") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        out[key.strip()] = value.strip().strip('"')
    return out


def tools(value: str | None) -> set[str]:
    return {t.strip() for t in (value or "").split(",") if t.strip()}


class Hermetic(unittest.TestCase):
    """Every render goes to a temporary HOME and CODEX_HOME, never the real ones."""

    codex = True

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="personas-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.codex_home = self.tmp / "codex"
        if self.codex:
            self.codex_home.mkdir()
        self.script = SCRIPT

    def copy_skill(self) -> Path:
        """A disposable copy of the skill whose persona sources a test may break."""
        target = self.tmp / "skill"
        shutil.copytree(SKILL, target, ignore=shutil.ignore_patterns("__pycache__", "tests"))
        self.script = target / "scripts" / "sync_personas.py"
        return target / "personas"

    def run_sync(self, *args: str, codex_home: str | None = None,
                 cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        env = {**os.environ, "HOME": str(self.home), "PYTHONDONTWRITEBYTECODE": "1",
               "CODEX_HOME": str(self.codex_home) if codex_home is None else codex_home}
        return subprocess.run([sys.executable, str(self.script), *args], capture_output=True,
                              text=True, timeout=60, env=env, cwd=cwd)

    @property
    def claude_agents(self) -> Path:
        return self.home / ".claude" / "agents"

    @property
    def codex_agents(self) -> Path:
        return self.codex_home / "agents"

    def rendered(self, name: str) -> tuple[dict, dict]:
        claude = frontmatter((self.claude_agents / f"{name}.md").read_text(encoding="utf-8"))
        codex = toml_loads((self.codex_agents / f"{name}.toml").read_text(encoding="utf-8"))
        return claude, codex
