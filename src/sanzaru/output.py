"""Where a run is written down.

    output/<model>/<task>/<run-id>/
        run.json            the bomb, the verdict, and what each round resolved to
        raw/<n>-<role>.json one request as it was sent, and the reply as it came back
        chat/<role>.json    that monkey's whole conversation, filtered and assembled

The two are different on purpose. `raw` is the record — every request, every raw reply,
every rejected draft. `chat` is what the model was actually shown: the same rounds with
reasoning and drafts removed. Keeping both means the filter can be re-examined later
without re-running anything.
"""

from __future__ import annotations

import json
from pathlib import Path
import re

SAFE = re.compile(r"[^A-Za-z0-9._#-]+")


def slug(text: str) -> str:
    return SAFE.sub("-", str(text)).strip("-").lower() or "unknown"


def next_run(root: Path, model: str, task: str, hints: str = "", mode: str = "norm") -> Path:
    """The next free run directory for this model, condition and task. Conditions
    get their own folders so run numbering never mixes two experiments; the mode
    joins the folder name whenever it is not the classic trio."""
    condition = slug(hints or "bare")
    if mode and mode != "norm":
        condition = f"{slug(mode)}-{condition}"
    parent = root / slug(model) / condition / slug(task)
    parent.mkdir(parents=True, exist_ok=True)
    used = [
        int(match.group(1))
        for child in parent.iterdir()
        if (match := re.fullmatch(r"run-(\d+)", child.name))
    ]
    return parent / f"run-{max(used, default=0) + 1}"


def write(directory: Path, result, bomb, definition, model: str, extra: dict | None = None) -> Path:
    """Lay one finished run out on disk."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "raw").mkdir(exist_ok=True)
    (directory / "chat").mkdir(exist_ok=True)

    for event in result.transcript:
        record = {
            "round": event["turn"],
            "role": event["role"],
            "request": event.get("messages", []),
            "reply": event["output"],
            "note": event.get("note", ""),
            "rejected": event.get("attempts", []),
            "calls": event["calls"],
            "inbox": event["inbox"],
            "private": event["private"],
            "private_label": event["private_label"],
            "bomb_before": event["puzzle_before"],
            "bomb_after": event["puzzle_after"],
        }
        name = f"{event['turn']:02d}-{event['role']}.json"
        _dump(directory / "raw" / name, record)

    summary = {
        "model": model,
        "task": result.task,
        "seed": result.seed,
        # The rota and the draw behind it: two seeds replay a run whole.
        "order": result.roles,
        "order_seed": result.order_seed,
        "success": result.success,
        "reason": result.reason,
        "actions": result.actions,
        "rounds": result.rounds,
        "silences": result.silences,
        "rejected_calls": result.rejected_calls,
        "repairs": result.repairs,
        "call_format": result.call_format,
        "puzzle": definition,
        **(extra or {}),
    }
    _dump(directory / "run.json", summary)
    return directory


def write_chats(directory: Path, agents: dict) -> None:
    """One file per monkey: the conversation exactly as its model was shown it."""
    for role, agent in agents.items():
        _dump(directory / "chat" / f"{role}.json", {
            "role": role,
            "system": agent.system_prompt(),
            "messages": agent.api_messages(),
        })


def _dump(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def read_runs(root: Path) -> list[dict]:
    """Every run under `root`, newest layout only, sorted by model, task and number."""
    runs = []
    for summary in sorted(root.glob("*/*/*/run-*/run.json")):
        directory = summary.parent
        run = json.loads(summary.read_text(encoding="utf-8"))
        run["saved_at"] = summary.stat().st_mtime
        run["id"] = directory.name
        run["number"] = int(directory.name.split("-")[1])
        run["turns"] = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted((directory / "raw").glob("*.json"))
        ]
        run["chats"] = {
            path.stem: json.loads(path.read_text(encoding="utf-8"))
            for path in sorted((directory / "chat").glob("*.json"))
        }
        runs.append(run)
    return sorted(runs, key=lambda run: (run["model"], run["task"], run["number"]))
