"""Secrets come from the environment, and .env is how the environment gets them.

Kept deliberately small: a key belongs in a file git ignores, never in a flag that
lands in shell history and never in a constant that lands in a commit.
"""

from __future__ import annotations

import os
from pathlib import Path


def load_env(path: str | Path = ".env") -> list[str]:
    """Read KEY=VALUE lines into the environment. Returns the names it set.

    An existing environment variable always wins, so an explicit `export` overrides
    the file. Blank lines and `#` comments are skipped; quotes around a value are
    stripped; anything already set is left alone.
    """
    path = Path(path)
    if not path.is_file():
        return []
    loaded = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        name, value = name.strip(), value.strip().strip("'\"")
        if name and name not in os.environ:
            os.environ[name] = value
            loaded.append(name)
    return loaded
