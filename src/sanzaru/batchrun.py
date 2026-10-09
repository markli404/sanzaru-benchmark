"""Many bombs through the OpenAI Batch API at half price.

Every run plays exactly as it would live: same runner, same judge, same files on
disk. Only the transport changes. Each run's next generation request lands in a
shared tray; a gatherer flushes the tray on a timer into a Batch job; each job
polls on its own thread and hands every reply back to the run that asked. Runs
drift apart freely (repairs, early finishes), so nothing waits for a round
barrier, only for its own answer.
"""

from __future__ import annotations

import argparse
import io
import json
import threading
import time
import urllib.request
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from .backends import OpenAICompatibleBackend
from .config import load_env


API = "https://api.openai.com/v1"


def _api(path: str, key: str, data: bytes | None = None,
         content_type: str = "application/json") -> dict:
    request = urllib.request.Request(
        API + path, data=data,
        headers={"Authorization": f"Bearer {key}", "Content-Type": content_type})
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read())


def _api_raw(path: str, key: str) -> bytes:
    request = urllib.request.Request(
        API + path, headers={"Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(request, timeout=300) as response:
        return response.read()


def _upload_jsonl(lines: list[str], key: str) -> str:
    boundary = uuid.uuid4().hex
    body = io.BytesIO()
    def part(text: str) -> None:
        body.write(text.encode())
    part(f"--{boundary}\r\nContent-Disposition: form-data; name=\"purpose\"\r\n\r\nbatch\r\n")
    part(f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
         f"filename=\"requests.jsonl\"\r\nContent-Type: application/jsonl\r\n\r\n")
    part("\n".join(lines) + "\n")
    part(f"\r\n--{boundary}--\r\n")
    return _api("/files", key, body.getvalue(),
                f"multipart/form-data; boundary={boundary}")["id"]


@dataclass
class _Ticket:
    payload: dict
    event: threading.Event = field(default_factory=threading.Event)
    reply: str | None = None
    error: str | None = None
    attempts: int = 0


class BatchCoordinator:
    """The tray, the gatherer, and one polling thread per batch in flight."""

    def __init__(self, key: str, gather_seconds: float = 60, poll_seconds: float = 30,
                 retries: int = 8, log=print):
        self.key = key
        self.gather_seconds = gather_seconds
        self.poll_seconds = poll_seconds
        self.retries = retries
        self.log = log
        self.lock = threading.Lock()
        self.tray: dict[str, _Ticket] = {}
        self.closed = False
        self.batches = 0
        self.jobs: list[threading.Thread] = []
        self.gatherer = threading.Thread(target=self._gather, daemon=True)
        self.gatherer.start()

    def ask(self, payload: dict) -> str:
        """Block until the batch that carries this request comes home."""
        ticket = _Ticket(payload)
        while True:
            ticket.event.clear()
            with self.lock:
                self.tray[uuid.uuid4().hex] = ticket
            ticket.event.wait()
            if ticket.reply is not None:
                return ticket.reply
            ticket.attempts += 1
            self.log(f"[retry] attempt {ticket.attempts}: {ticket.error}")
            if ticket.attempts > self.retries:
                raise RuntimeError(f"batch item failed {ticket.attempts} times: {ticket.error}")

    def close(self) -> None:
        self.closed = True
        for job in self.jobs:
            job.join()

    # -- internals ----------------------------------------------------------

    def _gather(self) -> None:
        while not self.closed:
            time.sleep(self.gather_seconds)
            with self.lock:
                if not self.tray:
                    continue
                taken, self.tray = self.tray, {}
            job = threading.Thread(target=self._fly, args=(taken,), daemon=True)
            self.jobs.append(job)
            job.start()

    def _fly(self, taken: dict[str, _Ticket]) -> None:
        self.batches += 1
        number = self.batches
        try:
            lines = [json.dumps({"custom_id": cid, "method": "POST",
                                 "url": "/v1/chat/completions", "body": t.payload})
                     for cid, t in taken.items()]
            file_id = _upload_jsonl(lines, self.key)
            batch = _api("/batches", self.key, json.dumps({
                "input_file_id": file_id, "endpoint": "/v1/chat/completions",
                "completion_window": "24h"}).encode())
            self.log(f"[batch {number}] {len(taken)} requests -> {batch['id']}")
            while batch["status"] not in ("completed", "failed", "expired", "cancelled"):
                time.sleep(self.poll_seconds)
                batch = _api(f"/batches/{batch['id']}", self.key)
            self.log(f"[batch {number}] {batch['status']}")
            answered = set()
            for fid in (batch.get("output_file_id"), batch.get("error_file_id")):
                if not fid:
                    continue
                for line in _api_raw(f"/files/{fid}/content", self.key).splitlines():
                    row = json.loads(line)
                    ticket = taken.get(row["custom_id"])
                    if ticket is None:
                        continue
                    answered.add(row["custom_id"])
                    response = row.get("response") or {}
                    if response.get("status_code") == 200:
                        body = response["body"]
                        ticket.reply = body["choices"][0]["message"]["content"] or ""
                    else:
                        ticket.error = json.dumps(row.get("error") or response)[:300]
                    ticket.event.set()
            for cid, ticket in taken.items():
                if cid not in answered:
                    ticket.error = f"batch {batch['status']} without an answer"
                    ticket.event.set()
        except Exception as error:
            self.log(f"[batch {number}] transport failed: {error!r}")
            for ticket in taken.values():
                ticket.error = f"batch transport: {error}"
                ticket.event.set()


class BatchBackend:
    """Looks like any backend to the runner; the coordinator does the flying."""

    def __init__(self, coordinator: BatchCoordinator, model: str,
                 max_tokens: int, temperature: float):
        self.coordinator = coordinator
        self.shape = OpenAICompatibleBackend(model, max_tokens=max_tokens,
                                             temperature=temperature)

    def generate(self, messages: list[dict[str, str]]) -> str:
        payload: dict = {"model": self.shape.model, "messages": messages}
        if self.shape.thinks():
            payload["max_completion_tokens"] = self.shape.max_tokens
        else:
            payload["max_tokens"] = self.shape.max_tokens
            payload["temperature"] = self.shape.temperature
        return self.coordinator.ask(payload)


def _play(model: str, task: str, number: int, hints: str, max_tokens: int,
          temperature: float, out: Path, coordinator: BatchCoordinator, log) -> dict:
    from .agents import roles
    from .output import next_run, write, write_chats
    from .runner import BenchmarkRunner
    from .tasks import TaskKind, countdown_for, definition, problem, rounds_for, window_for

    label = f"{task}#{number}"
    bomb = problem(TaskKind(task), number)
    backends = {role: BatchBackend(coordinator, model, max_tokens, temperature)
                for role in roles("norm")}
    runner = BenchmarkRunner(
        bomb, backends, max_rounds=rounds_for(task), logger=None,
        call_format="functions", concurrent=False, simultaneous=False,
        order_seed=None, hints=hints, mode="norm",
        window=window_for(task), countdown=countdown_for(task))
    result = runner.run()
    directory = next_run(out, model, label, hints)
    write(directory, result, bomb, definition(bomb), model, {
        "turns": "sequential", "problem": number, "order_seed": runner.order_seed,
        "hints": hints, "mode": "norm", "mode_roles": list(runner.agents),
        "window": runner.window, "countdown": runner.countdown,
        "temperature": temperature, "max_tokens": max_tokens, "transport": "batch"})
    write_chats(directory, runner.agents)
    verdict = "success" if result.success else "FAIL"
    log(f"[{verdict:7s}] {label} rounds={result.rounds} ({directory})")
    return {"task": label, "success": result.success, "rounds": result.rounds}


def main(argv: list[str] | None = None) -> int:
    from .tasks import CORE, PLUS
    from .viewer import write_page

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", default="gpt-5.6-luna")
    parser.add_argument("--hints", choices=["weak", "strong", "playbook"], default="")
    parser.add_argument("--problems", default="1-3", help="e.g. 1-3 or 1,4")
    parser.add_argument("--max-tokens", type=int, default=8000)
    parser.add_argument("--temperature", type=float, default=0.6)
    parser.add_argument("--gather", type=float, default=60,
                        help="seconds the tray collects before a batch flies")
    parser.add_argument("--tasks", default="",
                        help="comma list of config labels or family names; empty runs all")
    parser.add_argument("--out", default="output")
    args = parser.parse_args(argv)
    load_env()
    import os
    key = os.environ.get("OPENAI_API_KEY", "")

    if "-" in args.problems:
        low, high = args.problems.split("-")
        numbers = list(range(int(low), int(high) + 1))
    else:
        numbers = [int(n) for n in args.problems.split(",")]
    from .tasks import family_of
    tasks = [k.value for k in CORE] + [k.value for k in PLUS]
    if args.tasks:
        wanted = {w.strip() for w in args.tasks.split(",")}
        tasks = [t for t in tasks if t in wanted or family_of(t) in wanted]
    cells = [(t, n) for t in tasks for n in numbers]
    print(f"{len(cells)} runs: {len(tasks)} configs x problems {numbers}, "
          f"model {args.model}, hints {args.hints or 'bare'}")

    log_lock = threading.Lock()
    def log(text: str) -> None:
        with log_lock:
            print(text, flush=True)

    coordinator = BatchCoordinator(key, gather_seconds=args.gather, log=log)
    results: list[dict] = []
    results_lock = threading.Lock()

    def lane(task: str, number: int) -> None:
        try:
            row = _play(args.model, task, number, args.hints, args.max_tokens,
                        args.temperature, Path(args.out), coordinator, log)
        except Exception as error:
            log(f"[crash  ] {task}#{number}: {error}")
            row = {"task": f"{task}#{number}", "success": False, "rounds": 0}
        with results_lock:
            results.append(row)

    threads = [threading.Thread(target=lane, args=cell, daemon=True) for cell in cells]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    coordinator.close()

    wins = sum(1 for r in results if r["success"])
    print(f"\n=== batch sweep done: {wins}/{len(results)} defused, "
          f"{coordinator.batches} batches flown ===")
    write_page(Path(args.out), Path(args.out) / "rollout.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
