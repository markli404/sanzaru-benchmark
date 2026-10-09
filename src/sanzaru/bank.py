"""The frozen problem bank: the benchmark as files, not as code.

Every config owns a folder holding its contract (config.json) and its five bombs,
each a self-contained definition a runner can replay without touching the
generator. The manifest at the root is an aggregate of the contracts, never a
second place to edit. Regenerating the bank must reproduce it byte for byte; a
test holds the generator to that.
"""

from __future__ import annotations

import json
from pathlib import Path

from .tasks import (
    CORE, PLUS, PROBLEMS_PER_KIND, RETIRED, TaskKind, countdown_for, definition,
    family_of, orders_for, problem, rounds_for, window_for,
)


def split_of(kind: TaskKind) -> str:
    if kind in RETIRED:
        return "retired"
    return "plus" if kind in PLUS else "core"


def contract(kind: TaskKind) -> dict[str, object]:
    """Everything a runner needs to stage this config, besides the bombs."""
    return {
        "label": kind.value,
        "family": family_of(kind),
        "split": split_of(kind),
        "rounds": rounds_for(kind),
        "window": window_for(kind),
        "countdown": countdown_for(kind),
        "orders": [list(order) for order in orders_for(kind)],
        "problems": PROBLEMS_PER_KIND,
    }


def _dump(payload: dict[str, object]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def files(kind: TaskKind) -> dict[str, str]:
    """Relative path -> content for one config, the unit the bank is built from."""
    folder = f"{family_of(kind)}/{kind.value}"
    out = {f"{folder}/config.json": _dump(contract(kind))}
    for number in range(1, PROBLEMS_PER_KIND + 1):
        out[f"{folder}/{kind.value}#{number}.json"] = _dump(definition(problem(kind, number)))
    return out


def shipped() -> tuple[TaskKind, ...]:
    return tuple(CORE) + tuple(PLUS) + tuple(sorted(RETIRED, key=lambda k: k.value))


def build() -> dict[str, str]:
    """The whole bank as relative path -> content, manifest included."""
    out: dict[str, str] = {}
    for kind in shipped():
        out.update(files(kind))
    out["manifest.json"] = _dump({"configs": [contract(kind) for kind in shipped()]})
    return out


def write(root: Path) -> int:
    """Write the bank under root, replacing what was there. Returns file count."""
    tree = build()
    stale = {p for p in root.rglob("*.json")} - {root / rel for rel in tree}
    for path in sorted(stale):
        path.unlink()
    for rel, content in tree.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return len(tree)


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default="bank", help="directory to (re)write")
    args = parser.parse_args(argv)
    root = Path(args.out)
    count = write(root)
    splits = {s: sum(1 for k in shipped() if split_of(k) == s) for s in ("core", "plus", "retired")}
    print(f"{root}: {count} files — "
          + ", ".join(f"{n} {s} configs" for s, n in splits.items()))
    return 0
