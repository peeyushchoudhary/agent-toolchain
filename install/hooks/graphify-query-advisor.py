#!/usr/bin/env python3
"""PreToolUse(Bash) advisor: catch prose `graphify query` calls.

graphify's query CLI seeds BFS from *literal* case-folded substring matches with no stemming,
synonyms, or cross-language mapping. A prose question therefore seeds on weak tokens and floods
the result with unrelated nodes. This hook does not block — it injects the symbol-first ladder
so the next call is well-formed.

Advisory by design: the heuristic can misjudge, and a false positive must never cost a round-trip.
"""

import json
import re
import sys

# Question words and stopwords that signal prose rather than a symbol seed.
PROSE_TOKENS = {
    "where", "how", "what", "why", "when", "which", "who", "does", "do", "did", "is", "are",
    "was", "were", "can", "should", "the", "and", "for", "from", "into", "with", "that", "this",
    "enter", "persist", "handle", "handled", "work", "works", "happen", "happens",
}

# A symbol-shaped token: CamelCase, snake_case, dotted call, or ALLCAPS identifier.
SYMBOL_RE = re.compile(r"[a-z][A-Z]|_|\.\w|^[A-Z]{2,}$")


def extract_query(command: str) -> str | None:
    """Return the query argument of a `graphify query` invocation, or None."""
    m = re.search(
        r"""\bgraphify\s+query\s+(?:--\S+(?:\s+\S+)?\s+)*(?P<q>"[^"]*"|'[^']*'|\S+)""",
        command,
    )
    if not m:
        return None
    q = m.group("q")
    if len(q) >= 2 and q[0] in "\"'" and q[-1] == q[0]:
        q = q[1:-1]
    return q


def is_prose(query: str) -> bool:
    if query.startswith("-"):  # a flag, not a query (e.g. the `--help` trap)
        return True
    if query.rstrip().endswith("?"):
        return True
    words = re.findall(r"[\w.]+", query)
    if not words:
        return False
    lowered = {w.lower() for w in words}
    if lowered & PROSE_TOKENS:
        return True
    # Long, with no symbol-shaped token anywhere: almost certainly prose.
    return len(words) >= 5 and not any(SYMBOL_RE.search(w) for w in words)


GUIDANCE = """\
graphify query seeds BFS from LITERAL token matches — no stemming, no synonyms. \
The prose query above will return noise, not an answer.

Use the symbol-first ladder instead:
  1. graphify explain "<Symbol>"                  — exact node, source line, ranked neighbors
  2. graphify affected "<Symbol>" --depth 1       — blast radius before editing
  3. graphify path "<A>" "<B>"                    — how A reaches B
  4. graphify query "<Symbol> <Symbol>" --context calls --context imports --budget 800

explain/affected/path only READ graphify-out/graph.json — they write nothing, so a read-only
task is not a reason to skip them or to abandon the graph for grep.

If you must use `query` with a concept rather than a symbol, first do the REQUIRED vocab
expansion in ~/.claude/skills/graphify/references/query.md (Step 0): read graphify-out/.vocab.txt
and seed ONLY with tokens that appear in it.

Two traps:
  - The truncation hint prints `context_filter=['call']` — that is the PYTHON API form.
    The CLI flag is `--context calls`, repeatable.
  - `graphify query --help` is parsed as a QUERY FOR THE WORD "Help". Only `graphify --help` works.

Treat every result as a navigation hint and confirm at the cited source line before acting."""


def extract_command(payload: dict) -> str:
    """Pull the shell command out of a hook payload.

    Claude Code sends {"tool_input": {"command": "..."}}. Codex hooks use the same overall shape
    but are not guaranteed to nest it identically, so try the plausible spellings and accept an
    argv list as well as a string. Unknown shape yields "" and the hook stays silent.
    """
    containers = [
        payload.get("tool_input"),
        payload.get("input"),
        payload.get("arguments"),
        payload.get("params"),
        payload,
    ]
    for c in containers:
        if not isinstance(c, dict):
            continue
        for key in ("command", "cmd", "shell_command", "script"):
            v = c.get(key)
            if isinstance(v, str) and v.strip():
                return v
            if isinstance(v, list) and all(isinstance(x, str) for x in v) and v:
                return " ".join(v)
    return ""


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0  # never obstruct on malformed input
    if not isinstance(payload, dict):
        return 0

    command = extract_command(payload)
    query = extract_query(command)
    if query is None or not is_prose(query):
        return 0

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": GUIDANCE,
        },
        "systemMessage": "graphify: prose query detected — symbol-first ladder suggested.",
        "suppressOutput": True,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
