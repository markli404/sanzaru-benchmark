"""Compile a run into an input/output log.

    python3 -m sanzaru.viewer.log run.json

Whitespace is normalised, reasoning blocks are dropped, and every turn prints as the
input the monkey was given and the output it produced.
"""

from __future__ import annotations

import json
import re
import sys

REASONING_RE = re.compile(r"<(think|thinking|reasoning)>.*?(?:</\1>|\Z)", re.S)
FENCE_RE = re.compile(r"^\s*```[a-zA-Z0-9_+-]*\s*$", re.M)


def compile_text(text: str) -> str:
    """Drop reasoning and fences, collapse blank lines and trailing spaces."""
    text = REASONING_RE.sub("", text)
    text = FENCE_RE.sub("", text)
    lines = [line.rstrip() for line in text.strip().splitlines()]
    return "\n".join(line for line in lines if line.strip())


def block(label: str, body: str, width: int = 8) -> str:
    body = body or "(nothing)"
    lines = body.splitlines() or ["(nothing)"]
    pad = " " * width
    head = f"{label + ':':<{width}}{lines[0]}"
    return "\n".join([head] + [pad + line for line in lines[1:]])


def thinking_of(text: str) -> str:
    """The reasoning the model kept to itself, with blank lines squeezed out."""
    blocks = re.findall(r"<(?:think|thinking|reasoning)>(.*?)(?:</(?:think|thinking|reasoning)>|\Z)", text, re.S)
    lines = [line.rstrip() for block in blocks for line in block.strip().splitlines()]
    return "\n".join(line for line in lines if line.strip())


def render(trace: dict, show_thinking: bool = False, show_context: bool = False) -> str:
    out = []
    puzzle = trace["puzzle"]
    wires = ", ".join(f"{w['position']} {w['color']}" for w in puzzle["initial_state"]["wires"])
    out.append(f"model   {trace.get('model', '?')}")
    out.append(f"task    {trace['task']} seed {trace['seed']}")
    out.append(f"board   {wires} | light {puzzle['initial_state']['light']} | display {puzzle['initial_state']['display']}")
    out.append(block("manual", compile_text(puzzle["manual"])))
    out.append("")

    for event in trace["transcript"]:
        out.append(f"[turn {event['turn']} · {event['role']}]")
        if show_context and event.get("messages"):
            for index, message in enumerate(event["messages"]):
                out.append(block(f"  [{index}] {message['role']}", message["content"].strip()))
        out.append(block("input", compile_text(event["observation"])))
        for attempt in event.get("attempts", []):
            if show_thinking:
                out.append(block(f"think{attempt['attempt']}", thinking_of(attempt["output"])))
            out.append(block(f"try {attempt['attempt']}", compile_text(attempt["output"])))
            for problem in attempt["problems"]:
                out.append(block("reject", problem))
        if show_thinking:
            out.append(block("think", thinking_of(event["output"])))
        out.append(block("output", compile_text(event["output"])))
        effects = []
        for call in event["calls"]:
            if not call["accepted"]:
                effects.append(f"{call['kind']} blocked: {call.get('reason')}")
            elif call["kind"] == "wait":
                effects.append("waits")
            elif call["kind"] == "act":
                effects.append(f"acts -> judge: {call.get('result')}")
            elif call["accepted"]:
                effects.append(f"{call['kind']} -> {', '.join(call['recipients'])}")
            else:
                effects.append(f"{call['kind']} produced nothing")
        out.append(block("effect", "\n".join(effects) or "nothing"))
        out.append("")

    out.append(f"result  {'SUCCESS' if trace['success'] else 'FAIL'} — {trace['reason']}")
    out.append(f"actions {trace['actions'] or 'none'}")
    return "\n".join(out)


if __name__ == "__main__":
    paths = [a for a in sys.argv[1:] if not a.startswith("-")]
    print(render(json.load(open(paths[0], encoding="utf-8")),
                 "--thinking" in sys.argv, "--context" in sys.argv))
