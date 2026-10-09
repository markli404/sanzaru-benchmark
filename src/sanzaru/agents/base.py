"""Shared agent behaviour. Role specifics live in the sibling role modules."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..backends import Backend
from ..protocol import Message, Senses, render_wait, strip_reasoning
from .. import prompts
from . import registry


@dataclass
class Exchange:
    """One round as it really happened, before anything is filtered out of it.

    This is the record. It keeps the raw output — reasoning and all — and every draft
    that was rejected on the way, because that is what the run actually was.
    """

    round: int
    prompt: str
    output: str
    move: str = ""
    accepted: bool = True
    drafts: list[dict[str, object]] = field(default_factory=list)


class Agent:
    """One monkey: a complete record of its turns, a transient inbox, declared senses.

    The record and the messages sent to the model are two different things. The record
    is everything; the message list is a projection of it, computed fresh on every
    request by `api_messages`. Filtering there rather than at write time means the
    policy can change without the run having thrown anything away.
    """

    role: str = ""
    order: int = 0
    senses: Senses = Senses()
    may_act: bool = False

    # Which prompt sheet this role reads; the role name unless a variant overrides it.
    sheet = ""

    def __init__(self, backend: Backend, call_format: str = "", actions: str = "",
                 order: tuple[str, ...] = (), hints: str = "", mode: str = "norm",
                 window: int = 0):
        self.backend = backend
        self.call_format = call_format or prompts.DEFAULT_FORMAT
        # The actions this particular bomb is built with. A verb it does not have is
        # never named, so nobody spends a round on one.
        self.actions = actions
        # Empty when every monkey answers at once; the fixed rota otherwise.
        self.order = order
        self.hints = hints
        self.mode = mode
        # 0 keeps everything. Otherwise only the last `window` rounds travel with the
        # model: older words are gone unless somebody says them again.
        self.window = window
        self.record: list[Exchange] = []
        self.inbox: list[Message] = []

    # -- what the model is shown -------------------------------------------

    def system_prompt(self) -> str:
        return prompts.render(
            self.sheet or self.role,
            **registry.protocol_context(self.call_format, self.role, self.actions,
                                        self.order, self.hints, self.mode),
        )

    def api_messages(self) -> list[dict[str, str]]:
        """The whole conversation so far, assembled: every round this monkey took, in
        order, as alternating user and assistant messages.

        Each assistant message is the full text the round settled on, visible
        thinking included: an agent remembers what it wrote, and many protocols
        live in that private notebook (a cipher table, a running tally). What is
        absent is transient scaffolding: tag-wrapped reasoning from local models,
        rejected drafts, and repair chatter. A round that produced no call shows
        the wait it was taken to be. The window, where a task sets one, fades
        whole rounds at a time, notebook and all.
        """
        kept = self.record[-self.window:] if self.window else self.record
        messages: list[dict[str, str]] = []
        for exchange in kept:
            messages.append({"role": "user", "content": exchange.prompt})
            messages.append({"role": "assistant", "content": exchange.move})
        return messages

    def compose(self, prompt: str, repair: list[dict[str, str]] | None = None) -> list[dict[str, str]]:
        """The messages for one attempt. `repair` is transient and never recorded."""
        return (
            [{"role": "system", "content": self.system_prompt()}]
            + self.api_messages()
            + [{"role": "user", "content": prompt}]
            + list(repair or [])
        )

    # -- what actually happened --------------------------------------------

    def commit(self, round_number: int, prompt: str, output: str, accepted: bool = True,
               drafts: list[dict[str, object]] | None = None, silent: bool = False) -> Exchange:
        """Record the round. `silent` means no call was found, so the move was a wait."""
        move = render_wait(self.call_format) if silent else strip_reasoning(output).strip()
        exchange = Exchange(round_number, prompt, output, move, accepted, list(drafts or []))
        self.record.append(exchange)
        return exchange

    # -- receiving ----------------------------------------------------------

    def observe(self, turn: int, label: str, body: str) -> tuple[str, list[Message]]:
        """Build this round's user message and drain the inbox that fed it."""
        delivered = list(self.inbox)
        self.inbox.clear()
        inbox_text = "\n".join(message.render() for message in delivered) or "(empty)"
        fading = (f"(Only your last {self.window} turns stay with you. Anything older is\n"
                  f"gone, unless someone says it again.)\n" if self.window else "")
        prompt = f"TURN {turn}\n{fading}{label}:\n{body}\n\nVIEWABLE CONTEXT (new arrivals):\n{inbox_text}"
        return prompt, delivered

    def receive(self, message: Message) -> None:
        self.inbox.append(message)
