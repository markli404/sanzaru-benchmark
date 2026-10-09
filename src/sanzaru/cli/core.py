"""The shared body of every launcher.

A launcher differs only in which flags it adds and how it builds a backend for each
monkey. Everything else — the bomb, the console log, the runner, the trace on disk
and the re-rendered page — is the same run, and lives here once.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Callable

from ..output import next_run, write, write_chats
from ..runner import BenchmarkRunner
from ..tasks import TaskKind, countdown_for, definition, problem, rounds_for, window_for
from ..viewer import block, compile_text, write_page


def parser(model_default: str) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    p.add_argument("--model", default=model_default)
    p.add_argument("--task", default="base-1")
    p.add_argument("--problem", type=int, default=1, help="which numbered bomb, 1-5")
    p.add_argument("--rounds", type=int, default=None,
                   help="override the task's own round budget")
    p.add_argument("--mode", choices=["norm", "hard", "easy", "info"], default="norm",
                   help="classic trio; hard makes Blind voiceless; easy is solo; info removes communication asymmetry")
    p.add_argument("--turns", choices=["simultaneous", "sequential"], default="sequential",
                   help="how a round is taken")
    p.add_argument("--order-seed", type=int, default=None,
                   help="draws the speaking order; defaults to the problem number")
    p.add_argument("--hints", choices=["weak", "strong", "playbook"], default="",
                   help="weak nudges the frame, strong names the tactics, playbook hands over the procedure")
    p.add_argument("--out", default="output", help="root directory for runs")
    return p


def _log(event: dict) -> None:
    print(f"[round {event['turn']} · {event['role']}]")
    print(block("input", compile_text(event["observation"])))
    for attempt in event.get("attempts", []):
        print(block(f"try {attempt['attempt']}", compile_text(attempt["output"])))
        for complaint in attempt["problems"]:
            print(block("reject", complaint))
    print(block("output", compile_text(event["output"])))
    effects = []
    for call in event["calls"]:
        if not call["accepted"]:
            effects.append(f"{call['kind']} blocked: {call.get('reason')}")
        elif call["kind"] == "wait":
            effects.append("waits")
        elif call["kind"] == "act":
            effects.append(f"acts -> judge: {call.get('result')}")
        else:
            effects.append(f"{call['kind']} -> {', '.join(call['recipients'])}")
    print(block("effect", "\n".join(effects) or "nothing"), "\n", flush=True)


def execute(args: argparse.Namespace, make_backends: Callable[[argparse.Namespace, tuple[str, ...]], dict],
            extras: dict | None = None, call_format: str = "", concurrent: bool = True) -> int:
    """Run one bomb end to end and land its trace, chats and page."""
    from ..agents import roles

    label = f"{args.task}#{args.problem}"
    from ..tasks import RETIRED
    if TaskKind(args.task) in RETIRED:
        print(f"note    {args.task} is retired: it stays runnable for reproducibility,"
              " but sits outside the ladder")
    bomb = problem(TaskKind(args.task), args.problem)
    backends = make_backends(args, roles(args.mode))

    print(f"model   {args.model}\ntask    {label}")
    print(f"board   {bomb.face(perceives=True)}".replace("\n", " | "))
    print(bomb.manual(), "\n")

    runner = BenchmarkRunner(
        bomb, backends,
        max_rounds=args.rounds or rounds_for(args.task),
        logger=_log,
        call_format=call_format or "functions",
        concurrent=concurrent,
        simultaneous=args.turns == "simultaneous",
        order_seed=args.order_seed,
        hints=args.hints,
        mode=args.mode,
        window=window_for(args.task),
        countdown=countdown_for(args.task),
    )
    result = runner.run()
    print(f"result  {'SUCCESS' if result.success else 'FAIL'} — {result.reason}")
    print(f"actions {result.actions or 'none'}")
    print(f"stats   rounds={result.rounds} silences={result.silences} "
          f"rejected={result.rejected_calls} repairs={result.repairs}")
    print(f"order   {' -> '.join(runner.order)}"
          + (f" (order seed {runner.order_seed})" if runner.order_seed is not None else ""))

    directory = next_run(Path(args.out), args.model, label, args.hints, args.mode)
    write(directory, result, bomb, definition(bomb), args.model, {
        "turns": args.turns, "problem": args.problem,
        "order_seed": runner.order_seed, "hints": args.hints,
        "mode": args.mode, "mode_roles": list(runner.agents),
        "window": runner.window, "countdown": runner.countdown, **(extras or {}),
    })
    write_chats(directory, runner.agents)
    print(f"saved   {directory}")
    page = Path(args.out) / "rollout.html"
    write_page(Path(args.out), page)
    print(f"page    {page}")
    return 0 if result.success else 1
