"""Mark a test that reaches the real `Path.home()` on purpose, and say why.

A test that reads `~/.claude` or `~/.codex` on the machine running it answers about that machine,
not about a tree it built. Most tests here pin `HOME` in a child's environment instead. The few
whose job is to reach the real machine carry `@reaches_home(reason)`, so a failure says on which
machine it was measured.
"""

from __future__ import annotations

import functools
import inspect
from pathlib import Path

# `(file name, Class.method)` -> reason. Populated at import of each decorated module.
MARKED: dict[tuple[str, str], str] = {}


def reaches_home(reason: str):
    """Declare that this test reaches `Path.home()`. An empty reason is refused."""
    if not reason.strip():
        raise ValueError("reaches_home() requires a reason; a bare mark is a comment")

    def decorate(function):
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
                    f"machine you meant to judge, this failure is about the wrong tree."
                ) from None
        return wrapper
    return decorate
