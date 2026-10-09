"""The turn loop. It knows about turns, transcripts and the judge — not about roles."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from threading import Lock
from typing import Callable

import random

from .agents import Agent, build_all, roles
from .backends import Backend
from .prompts import DEFAULT_FORMAT, phrase, phrases
from .protocol import WAIT_VERB, Call, Channel, extract_calls
from .protocol import private_note
from .simulator import Bomb
from .tasks import View, orders_for, view_for

TRACE_VERSION = 2


def _speaking_order(seed: int, mode: str = "norm",
                    allowed: tuple[tuple[str, ...], ...] = ()) -> tuple[str, ...]:
    """Who speaks first is drawn once from its own seed and then never changes.

    It is a seed of its own so the same bomb can be replayed under a different rota,
    and the same rota tried against a different bomb. A task may restrict the draw
    to the rotas its mechanics need.
    """
    if allowed:
        return tuple(random.Random(seed).choice(list(allowed)))
    order = list(roles(mode))
    random.Random(seed).shuffle(order)
    return tuple(order)
# A malformed call is handed back with the reason and rewritten. Past this many
# rewrites the run ends: a monkey that cannot produce a legal call is not playing.
MAX_REPAIRS = 3


@dataclass
class RunResult:
    success: bool
    reason: str
    rounds: int
    actions: list[str]
    transcript: list[dict[str, object]]
    seed: int
    task: str
    roles: list[str] = field(default_factory=list)
    call_format: str = DEFAULT_FORMAT
    # The draw behind `roles` when they speak one at a time; unused when they all answer
    # at once, since then the order carries no meaning.
    order_seed: int | None = None
    # Rounds in which a monkey produced no call and was defaulted to wait().
    silences: int = 0
    rejected_calls: int = 0
    repairs: int = 0


class BenchmarkRunner:
    """Synchronous rounds. Every monkey generates before anything is delivered."""

    def __init__(
        self,
        puzzle: Bomb,
        backends: dict[str, Backend],
        max_rounds: int = 10,
        logger: Callable[[dict], None] | None = None,
        call_format: str = DEFAULT_FORMAT,
        concurrent: bool = True,
        simultaneous: bool = True,
        order_seed: int | None = None,
        hints: str = "",
        mode: str = "norm",
        window: int = 0,
        countdown: int = 0,
    ):
        self.puzzle = puzzle
        self.max_rounds = max_rounds
        self.logger = logger
        self.call_format = call_format
        # Falls back to the bomb's seed, so one seed still reproduces a whole run.
        self.order_seed = None if simultaneous else (
            puzzle.seed if order_seed is None else order_seed)
        self.mode = mode
        allowed = orders_for(puzzle.kind) if mode != "easy" else ()
        self.order = (roles(mode) if simultaneous
                      else _speaking_order(self.order_seed, mode, allowed))
        self.hints = hints
        self.window = window
        # When positive, the last `countdown` rounds print a timer line on the
        # bomb's face, and only the role that sees the bomb reads it.
        self.countdown = countdown
        self.agents: dict[str, Agent] = build_all(backends, call_format, puzzle.signatures(),
                                                  () if simultaneous else self.order,
                                                  hints, mode, window)
        self.channel = Channel(self.agents, puzzle.apply, puzzle.operations())
        self.transcript: list[dict[str, object]] = []
        # Two ways a round can run. Simultaneous: everyone answers before anything is
        # delivered, so every message costs a round of delay. Sequential: each monkey
        # speaks in turn and whoever follows hears it at once, with the order drawn
        # from the seed and then fixed for the whole run.
        self.simultaneous = simultaneous
        self.concurrent = concurrent and simultaneous
        self.tally = Lock()
        self.silences = 0
        self.rejected_calls = 0
        self.repairs = 0

    def run(self) -> RunResult:
        if not self.simultaneous:
            return self._run_in_turn()
        for round_number in range(1, self.max_rounds + 1):
            self.puzzle.tick()
            # Phase one: everyone generates. Nothing is delivered, so no monkey can see
            # what another said this round. Generation order cannot matter, which is why
            # it can run concurrently: the barrier is what the round means, not the loop.
            asked = []
            for role in self.order:
                agent = self.agents[role]
                view = self._view(role, round_number)
                prompt, delivered = agent.observe(round_number, view.label, view.body)
                asked.append((role, agent, prompt, {
                    "turn": round_number,
                    "role": role,
                    "rules": agent.system_prompt(),
                    "private": view.body,
                    "private_label": view.label,
                    "inbox": [message.to_json() for message in delivered],
                    "observation": prompt,
                    "output": "",
                    "attempts": [],
                    "calls": [],
                    "puzzle_before": self.puzzle.snapshot(),
                }))

            if self.concurrent and len(asked) > 1:
                with ThreadPoolExecutor(max_workers=len(asked)) as pool:
                    results = list(pool.map(
                        lambda item: self._attempt(item[1], round_number, item[2], item[3]), asked))
            else:
                results = [self._attempt(agent, round_number, prompt, event)
                           for _, agent, prompt, event in asked]

            pending = []
            for (role, _, _, event), (output, calls) in zip(asked, results):
                event["output"] = output
                event["note"] = private_note(output)
                pending.append((role, calls, event))

            # Phase two: the barrier has passed. Deliver, then judge.
            terminal = False
            for role, calls, event in pending:
                if calls is not None and not terminal:
                    terminal = self._dispatch(role, calls, round_number, event)
                event["puzzle_after"] = self.puzzle.snapshot()
                self.transcript.append(event)
                if self.logger:
                    self.logger(event)
            if terminal:
                return self._result(round_number)
        return self._result(self.max_rounds, "round limit reached")

    def _run_in_turn(self) -> RunResult:
        """One monkey at a time. What is said lands before the next one is asked."""
        for round_number in range(1, self.max_rounds + 1):
            self.puzzle.tick()
            for role in self.order:
                agent = self.agents[role]
                view = self._view(role, round_number)
                prompt, delivered = agent.observe(round_number, view.label, view.body)
                event = self._event(round_number, role, agent, view, prompt, delivered)
                output, calls = self._attempt(agent, round_number, prompt, event)
                event["output"] = output
                event["note"] = private_note(output)
                terminal = calls is not None and self._dispatch(role, calls, round_number, event)
                event["puzzle_after"] = self.puzzle.snapshot()
                self.transcript.append(event)
                if self.logger:
                    self.logger(event)
                if terminal:
                    return self._result(round_number)
        return self._result(self.max_rounds, "round limit reached")

    def _view(self, role: str, round_number: int) -> View:
        """A role's view this round, with the timer on it when the endgame shows one."""
        view = view_for(self.puzzle, role)
        remaining = self.max_rounds - round_number + 1
        if (self.countdown and remaining <= self.countdown
                and role in ("deaf", "almighty")):
            noun = "round" if remaining == 1 else "rounds"
            view = View(view.label,
                        f"{view.body}\nTIMER [{remaining} {noun} until detonation]")
        return view

    def _event(self, round_number, role, agent, view, prompt, delivered) -> dict:
        return {
            "turn": round_number,
            "role": role,
            "rules": agent.system_prompt(),
            "private": view.body,
            "private_label": view.label,
            "inbox": [message.to_json() for message in delivered],
            "observation": prompt,
            "output": "",
            "attempts": [],
            "calls": [],
            "puzzle_before": self.puzzle.snapshot(),
        }

    def _attempt(self, agent: Agent, round_number: int, prompt: str, event: dict):
        """Generate until every payload is well formed, handing back each reason.

        Only malformed payloads are handed back. A call the world forbids — a mute
        monkey speaking, a monkey without hands acting — is not a mistake that could
        have been written better, so it passes through untouched and is bounced back
        to its sender at the start of the next round instead.

        Returns (output, calls). Once the rewrites run out the turn resolves to a
        wait, so a badly formatted call costs its own turn and nothing more. Only
        the accepted exchange reaches the agent's history; every rejected attempt and
        the note that followed it is recorded in the trace and then dropped, so the
        next round's prefix is exactly what it would have been without any repair.
        """
        repair: list[dict[str, str]] = []
        output = ""
        for attempt in range(MAX_REPAIRS + 1):
            messages = agent.compose(prompt, repair)
            if attempt == 0:
                # What was actually sent, so the assembled context can be audited
                # without replaying the run. The system text is already in "rules".
                event["messages"] = [
                    {"role": m["role"], "content": "<system prompt: see rules>"
                     if m["role"] == "system" else m["content"]}
                    for m in messages
                ]
            output = agent.backend.generate(messages)
            calls = extract_calls(output, self.call_format)
            if not calls:
                # Producing nothing is not an error. It is this round's move: silence.
                with self.tally:
                    self.silences += 1
                agent.commit(round_number, prompt, output, drafts=event["attempts"], silent=True)
                return output, [Call(WAIT_VERB)]
            problems = [
                f"{call.raw or call.verb}: {problem}"
                for call, problem in (
                    (c, self.channel.check(agent.role, c))
                    for c in calls if not self.channel.permitted(agent.role, c)
                )
                if problem
            ]
            if not problems:
                agent.commit(round_number, prompt, output, drafts=event["attempts"])
                return output, calls
            event["attempts"].append({"attempt": attempt + 1, "output": output, "problems": problems})
            with self.tally:
                self.repairs += 1
            repair = repair + [
                {"role": "assistant", "content": output},
                {"role": "user", "content": self._repair_note(problems, MAX_REPAIRS - attempt)},
            ]
        # Four bad drafts is a lost turn, not a lost run. What is being measured is
        # coordination, not whether a model can keep a call well formed.
        with self.tally:
            self.silences += 1
        agent.commit(round_number, prompt, output, accepted=False,
                     drafts=event["attempts"], silent=True)
        return output, [Call(WAIT_VERB)]

    @staticmethod
    def _repair_note(problems: list[str], left: int) -> str:
        listed = "\n".join(f"- {problem}" for problem in problems)
        tail = (phrase("notices", "rewrite_left", left=left) if left
                else phrases("notices")["rewrite_last"])
        header = phrases("notices")["rewrite_header"]
        return f"{header}\n{listed}\n\n{tail}"

    def _dispatch(self, role: str, calls: list, turn: int, event: dict) -> bool:
        for call in calls:
            delivery = self.channel.dispatch(role, call, turn)
            event["calls"].append(delivery.to_json())
            if not delivery.accepted:
                self.rejected_calls += 1
            if delivery.terminal:
                return True
        return False

    def _result(self, rounds: int, timeout: str = "") -> RunResult:
        success = self.puzzle.finished and not self.puzzle.failed
        reason = timeout or ("success" if success else (self.puzzle.failure_reason or "failed"))
        return RunResult(
            success and not timeout,
            reason,
            rounds,
            list(self.puzzle.actions),
            self.transcript,
            self.puzzle.seed,
            self.puzzle.kind,
            list(self.order),
            self.call_format,
            self.order_seed,
            self.silences,
            self.rejected_calls,
            self.repairs,
        )
