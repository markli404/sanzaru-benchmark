"""The agent-to-agent protocol.

Two tables drive everything and neither names a monkey:

* `Senses` — what a role can do and perceive. Declared per role.
* `MODALITIES` — how a channel works: which sense produces it, which receives it.

Routing is derived from those two. Writing the resulting communication matrix by
hand is how it gets wrong, so nothing here does.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
import re
from typing import Callable, Protocol

from .prompts import DEFAULT_FORMAT, phrase, phrases

# --------------------------------------------------------------------------
# Gestures
# --------------------------------------------------------------------------

# Hand-gesture emoji. The benchmark assigns them no meaning: two agents must agree
# on an encoding before a gesture can carry an answer. The final row is
# semantically loaded — pointing hands and thumbs are obvious focal points for
# direction and assent — so it can be dropped to make the channel fully opaque.
# The gesture alphabet. The benchmark supplies the symbols and nothing else: it does
# not name them, define them, or interpret them. Whatever a gesture means is whatever
# the monkeys make it mean.
GESTURES: tuple[str, ...] = (
    "👍", "👎", "👌", "☝", "✌", "🤟", "🖐", "✋",
    "👆", "👇", "👈", "👉", "🫱", "🫲", "🫳", "🫴", "🫷", "🫸", "🤛", "🤜",
    "✊", "👊", "👋", "🤚", "🖖", "🤌", "🤏", "🤞", "🫰", "🤘", "🤙",
    "👏", "🙌", "🫶", "👐", "🤲", "🤝", "🙏", "🫵", "✍", "💅", "🤳",
)

_GESTURE_SET = frozenset(GESTURES)
# Variation selectors, joiners and skin tones are cosmetic: 🖐️ and 🖐🏽 normalize
# to the same gesture as 🖐, so a codebook stays stable.
_MODIFIERS = frozenset("︎️‍") | {chr(point) for point in range(0x1F3FB, 0x1F400)}


# Marks with a shape and no name. They are what an engraving is made of, and the
# one thing a voice cannot carry: whoever meets one has to describe it, because
# no dictionary will do it for them. Symbols with a household name (a star, a
# copyright sign) are banned from this set: naming must cost something.
UNSPEAKABLE: tuple[str, ...] = (
    "ꕥ", "ꖜ", "ꔮ", "ᖉ", "ᘔ", "ꗃ", "ⵘ", "ⳃ", "ꓭ", "ꓕ", "ꙅ", "꩜",
)
_UNSPEAKABLE_SET = frozenset(UNSPEAKABLE)


def unspeakable(payload: str) -> list[str]:
    """The characters in this payload that cannot be said aloud."""
    return sorted({char for char in payload if char in _UNSPEAKABLE_SET})


def is_speech(payload: str) -> bool:
    """Ordinary spoken language, plus any gesture held up while saying it.

    Everything a person can pronounce goes through. A mark with no name does not,
    which is the whole point of engraving one.
    """
    return not unspeakable(payload)


def mask_gestures(payload: str) -> str:
    """The payload as heard by someone who cannot see: the words survive, the gestures
    held up alongside them do not."""
    return "".join(MASK if char in _GESTURE_SET else char for char in payload)


def gestures_in(payload: str) -> list[str]:
    """Every gesture symbol held up inside a sentence, in the order it was raised."""
    return [char for char in payload if char in _GESTURE_SET]


def parse_gestures(payload: str) -> list[str]:
    """Normalized gesture sequence, or [] when the payload holds anything else."""
    gestures = []
    for char in payload:
        if char.isspace() or char in _MODIFIERS:
            continue
        if char not in _GESTURE_SET:
            return []
        gestures.append(char)
    return gestures


# --------------------------------------------------------------------------
# The skill table
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Senses:
    """What a role can do and perceive. Every route in the game follows from these."""

    speaks: bool = True
    hears: bool = True
    gestures: bool = True
    sees: bool = True


@dataclass(frozen=True)
class Modality:
    """A channel: produced by one sense, received by another."""

    name: str
    verb: str
    produce: str
    receive: str
    description: str


MODALITIES: tuple[Modality, ...] = (
    Modality("speech", "speak", "speaks", "hears", "spoken aloud; everyone who can hear it receives it"),
    Modality("gesture", "gesture", "gestures", "sees", "made with the hands; everyone who can see it receives it"),
)
ACT_VERB = "act"
# Saying nothing on purpose is a move, not a failure to produce one. Without this the
# transcript cannot tell a monkey that chose to wait from one that wrote a broken call.
WAIT_VERB = "wait"
MODALITY_BY_VERB = {modality.verb: modality for modality in MODALITIES}
VERBS = tuple(MODALITY_BY_VERB) + (ACT_VERB, WAIT_VERB)


def reaches(senses: dict[str, Senses], sender: str, modality: Modality) -> tuple[str, ...]:
    """Who receives `sender`'s use of `modality`. Derived, never written by hand."""
    if not getattr(senses[sender], modality.produce):
        return ()
    return tuple(
        role for role, sense in senses.items()
        if role != sender and getattr(sense, modality.receive)
    )


def matrix(senses: dict[str, Senses]) -> dict[tuple[str, str], tuple[str, ...]]:
    """(sender, receiver) -> the modalities that get through. The derived artifact."""
    result: dict[tuple[str, str], tuple[str, ...]] = {}
    for sender in senses:
        for receiver in senses:
            if sender == receiver:
                continue
            through = tuple(
                modality.name for modality in MODALITIES
                if receiver in reaches(senses, sender, modality)
            )
            result[(sender, receiver)] = through
    return result


def describe_own_routes(senses: dict[str, Senses], role: str, may_act: bool) -> str:
    """What one role is told about its own reach. Other monkeys' edges are not its
    business, so nothing here describes a channel this role cannot use."""
    can, cannot = [], []
    for modality in MODALITIES:
        if not getattr(senses[role], modality.produce):
            cannot.append(phrase("communication", "cannot_produce", verb=modality.verb))
        else:
            targets = reaches(senses, role, modality)
            can.append(
                phrase("communication", "reach", verb=modality.verb,
                       targets=" and ".join(target.capitalize() for target in targets),
                       receives="receive" if len(targets) > 1 else "receives")
                if targets else phrase("communication", "reach_nobody", verb=modality.verb)
            )
        if not getattr(senses[role], modality.receive):
            cannot.append(phrase("communication", "never_receive", modality=modality.name))
    speech, gesture = (reaches(senses, role, m) for m in MODALITIES)
    beyond = [target for target in gesture if target not in speech]
    if speech and beyond:
        can.append(phrase("communication", "split_channels",
                          hearers=" and ".join(t.capitalize() for t in speech),
                          watchers=" and ".join(t.capitalize() for t in beyond)))
    return "\n".join(can + cannot)


# --------------------------------------------------------------------------
# Calls
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Call:
    """One attempted use of a verb, parsed out of raw model output."""

    verb: str
    args: tuple = ()
    kwargs: dict = field(default_factory=dict)
    raw: str = ""

    def value(self, *names: str) -> object:
        """First matching keyword, else the next positional argument."""
        for index, name in enumerate(names):
            if name in self.kwargs:
                return self.kwargs[name]
            if index < len(self.args):
                return self.args[index]
        return None


def addressee_of(call: Call) -> str:
    """Who the call names as its receiver, or "" when it names nobody."""
    return str(call.kwargs.get("to", "") or "").lower()


def payload_of(call: Call) -> str | None:
    """Flatten a call's arguments into the payload its channel carries."""
    if call.verb == WAIT_VERB:
        return WAIT_VERB
    if call.verb == "speak":
        text = call.value("text", "message")
        return str(text) if text is not None else None
    if call.verb == "gesture":
        symbols = call.kwargs.get("symbols", call.args)
        if isinstance(symbols, str):
            symbols = (symbols,)
        if not symbols:
            return None
        return "".join(str(symbol) for symbol in symbols)
    if call.verb == ACT_VERB:
        first = call.value("op", "action")
        if first is None:
            return None
        first = str(first).strip()
        if " " in first:  # act("cut 2") is accepted as well
            return first
        second = next((call.kwargs[name] for name in
                       ("position", "direction", "code", "digit", "slot")
                       if name in call.kwargs), None)
        if second is None and len(call.args) > 1:
            second = call.args[1]
        return f"{first} {second}".strip() if second is not None else first
    return None


# --- format: XML-like tags -------------------------------------------------

_TAG_BY_NAME = {"SAY": "speak", "GESTURE": "gesture", "ACT": ACT_VERB, "WAIT": WAIT_VERB}
TAG_RE = re.compile(r"<(SAY|GESTURE|ACT|WAIT)>([^<>]*)</\1>")


def parse_tags(text: str) -> list[Call]:
    text = strip_reasoning(text)
    calls = []
    for match in TAG_RE.finditer(text):
        verb = _TAG_BY_NAME[match.group(1)]
        calls.append(Call(verb, (match.group(2).strip(),), raw=match.group(0)))
    return calls


# --- format: function-call syntax ------------------------------------------

FENCE_RE = re.compile(r"```[a-zA-Z0-9_+-]*\n(.*?)```", re.S)
# Reasoning blocks are private by rule, so a call written inside one was never
# uttered. An unclosed block (a model that ran out of budget mid-thought) hides
# everything after it too.
REASONING_RE = re.compile(r"<(think|thinking|reasoning)>.*?(?:</\1>|\Z)", re.S)


def strip_reasoning(text: str) -> str:
    return REASONING_RE.sub("", text)


def private_note(text: str) -> str:
    """Whatever a monkey wrote outside its calls: reasoning nobody else ever receives.

    It reaches no one and changes nothing, which is the point — it is the only window
    onto why a monkey chose what it sent.
    """
    body = FENCE_RE.sub("", strip_reasoning(text))
    return "\n".join(line for line in body.splitlines() if line.strip()).strip()


def _calls_in_source(source: str) -> list[Call]:
    """Top-level literal calls to known verbs. Parsed only — never executed."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    calls = []
    for node in tree.body:
        if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
            continue
        call = node.value
        if not isinstance(call.func, ast.Name) or call.func.id not in VERBS:
            continue
        try:
            args = tuple(ast.literal_eval(argument) for argument in call.args)
            kwargs = {
                keyword.arg: ast.literal_eval(keyword.value)
                for keyword in call.keywords if keyword.arg
            }
        except (ValueError, SyntaxError, TypeError):
            continue
        calls.append(Call(call.func.id, args, kwargs, raw=ast.unparse(call)))
    return calls


def parse_functions(text: str) -> list[Call]:
    text = strip_reasoning(text)
    calls = []
    for block in FENCE_RE.findall(text) or [text]:
        found = _calls_in_source(block)
        if not found:
            # A bare emoji or a stray word makes the whole block a SyntaxError. Read it
            # line by line so one bad line does not discard the good ones beside it.
            for line in block.splitlines():
                found.extend(_calls_in_source(line.strip()))
        calls.extend(found)
    return calls


CALL_FORMATS: dict[str, Callable[[str], list[Call]]] = {
    "tags": parse_tags,
    "functions": parse_functions,
}


def extract_calls(text: str, call_format: str = DEFAULT_FORMAT) -> list[Call]:
    return CALL_FORMATS[call_format](text)


WAIT_TEXT = {"functions": "```\nwait()\n```", "tags": "<WAIT></WAIT>"}


def render_wait(call_format: str) -> str:
    """A round in which nothing was said still has a move in it: waiting."""
    return WAIT_TEXT[call_format]


# What one call of each kind looks like, per surface. A monkey is only ever shown the
# kinds it can make: an example of a verb you do not have is an invitation to waste a
# round on it.
EXAMPLES = {
    "functions": {
        "speak": '    speak(to="mute", text="there are three of them and the middle one is odd")',
        "gesture": '    gesture(to="deaf", symbols=["\u270a", "\u270c"])',
        "wait": "    wait()",
        "act": '    act(op="cut", position=2)',
    },
    "tags": {
        "speak": "    <SAY to=\"mute\">there are three of them and the middle one is odd</SAY>",
        "gesture": "    <GESTURE>\u270a\u270c</GESTURE>",
        "wait": "    <WAIT></WAIT>",
        "act": '    <ACT>cut 2</ACT>',
    },
}


def syntax_doc(call_format: str, kinds: tuple[str, ...] = ("speak", "gesture", "wait")) -> str:
    """How calls are written. World knowledge: the same for every monkey."""
    shown = EXAMPLES[call_format]
    return phrase(f"calls_{call_format}", "syntax",
                  examples="\n".join(shown[kind] for kind in kinds))


# --------------------------------------------------------------------------
# Envelopes and routing
# --------------------------------------------------------------------------


MASK = "?"


@dataclass(frozen=True)
class Message:
    """A delivered envelope. Sender and recipients survive into the saved trace."""

    turn: int
    sender: str
    recipients: tuple[str, ...]
    payload: str
    modality: str = "speech"
    perceived: bool = True
    # Who the sender named, or "" for the whole room. An envelope: a named message is
    # delivered to that one monkey alone, and only what their senses take in arrives.
    to: str = ""

    def perceived_by(self, senses: Senses) -> "Message | None":
        """This event as it reaches one recipient, or None if it never reaches them.

        A symbol written into speech is a gesture held up while talking. A hearer gets
        the words, with each symbol blanked if they cannot see; a watcher who cannot
        hear gets only the gestures that were held up; a gesture alone reaches whoever
        sees, and arrives as blanks for anyone who cannot.
        """
        modality = next(m for m in MODALITIES if m.name == self.modality) if self.modality != "system" else None
        if modality is None:
            return self
        if not getattr(senses, modality.receive):
            if modality.name == "speech":
                held = gestures_in(self.payload) if senses.sees else []
                if not held:
                    return None
                return Message(self.turn, self.sender, self.recipients,
                               " ".join(held), "gesture", True, self.to)
            blanked = " ".join(MASK for _ in self.payload.split()) or MASK
            return Message(self.turn, self.sender, self.recipients, blanked, self.modality, False, self.to)
        if modality.name == "speech" and not senses.sees:
            return Message(self.turn, self.sender, self.recipients,
                           mask_gestures(self.payload), self.modality, False, self.to)
        return self

    def render(self) -> str:
        body = f"[{self.payload}]" if self.modality == "gesture" else self.payload
        verb = {"speech": "says", "gesture": "gestures", "system": ""}.get(self.modality, "sends")
        head = f"{self.sender.capitalize()} {verb}".strip()
        if verb and self.to:
            head += f" to {self.to.capitalize()}"
        return f"{head}: {body}" if verb else f"{self.sender.capitalize()}: {body}"

    def to_json(self) -> dict[str, object]:
        return {
            "turn": self.turn,
            "sender": self.sender,
            "recipients": list(self.recipients),
            "to": self.to,
            "modality": self.modality,
            "payload": self.payload,
            "perceived": self.perceived,
            "text": self.render(),
        }


@dataclass
class Delivery:
    """The audit record for one call: what was attempted and what it caused."""

    call: Call
    accepted: bool
    reason: str = ""
    recipients: tuple[str, ...] = ()
    message: Message | None = None
    result: str | None = None
    terminal: bool = False
    detail: dict[str, object] = field(default_factory=dict)

    def to_json(self) -> dict[str, object]:
        record: dict[str, object] = {
            "kind": self.call.verb,
            "payload": self.call.raw or payload_of(self.call) or "",
            # What the call carried, apart from how it was written. A blocked call
            # never became a message, so this is the only place its words survive.
            "said": payload_of(self.call) or "",
            "accepted": self.accepted,
            "recipients": list(self.recipients),
        }
        if self.reason:
            record["reason"] = self.reason
        if self.message is not None:
            record["message"] = self.message.to_json()
        if self.result is not None:
            record["result"] = self.result
        record.update(self.detail)
        return record


class Endpoint(Protocol):
    """The slice of an agent the channel depends on."""

    role: str
    senses: Senses
    may_act: bool

    def receive(self, message: Message) -> None: ...


class Channel:
    """Routes calls by reading the skill table. It knows no role names."""

    def __init__(self, endpoints: dict[str, Endpoint], judge: Callable[[str], tuple[bool, str]],
                 operations: tuple[str, ...] = ()):
        self.endpoints = endpoints
        self.judge = judge
        # Naming an operation the bomb does not have is a guess about what is built
        # into it, and a guess that lands nowhere should cost a rewrite, not the run.
        self.operations = operations
        self.senses = {role: endpoint.senses for role, endpoint in endpoints.items()}

    def actors(self) -> tuple[str, ...]:
        return tuple(role for role, endpoint in self.endpoints.items() if endpoint.may_act)

    def permitted(self, sender: str, call: Call) -> str:
        """Why the world forbids this call outright, or "" if the sender may make it.

        A monkey with no voice does not produce faulty speech; it produces no speech.
        Such calls are dropped where they are made and never handed back to be
        rewritten, because rewriting implies the monkey could have done it correctly.
        """
        if call.verb == WAIT_VERB:
            return ""
        if call.verb == ACT_VERB:
            return "" if self.endpoints[sender].may_act else phrase("notices", "cannot_act")
        modality = MODALITY_BY_VERB[call.verb]
        if not getattr(self.senses[sender], modality.produce):
            return phrase("notices", "cannot_produce", verb=modality.verb)
        return ""

    def check(self, sender: str, call: Call) -> str:
        """Why a permitted call is malformed, or "" if it is well formed. Pure.

        Only the payload is judged here. A well formed call that is a bad move — cutting
        the wrong wire — is the game's answer, never a thing to be rewritten.
        """
        payload = payload_of(call)
        if payload is None or not str(payload).strip():
            return phrase("notices", "empty_argument", verb=call.verb)
        if call.verb == WAIT_VERB:
            return ""
        if call.verb == ACT_VERB:
            operation = str(payload).split(" ", 1)[0]
            if self.operations and operation not in self.operations:
                return phrase("notices", "no_such_operation", operation=operation)
            return ""
        addressee = addressee_of(call)
        if addressee and addressee not in self.senses:
            return phrase("notices", "unknown_receiver", who=addressee)
        if addressee == sender:
            return phrase("notices", "self_receiver")
        modality = MODALITY_BY_VERB[call.verb]
        if modality.name == "speech" and not is_speech(payload):
            # Name the characters, or a rewrite is a guess about which one offended.
            return phrase("notices", "bad_speech", marks=" ".join(unspeakable(payload)))
        if modality.name == "gesture" and not parse_gestures(payload):
            return phrase("notices", "bad_gesture")
        return ""

    def dispatch(self, sender: str, call: Call, turn: int) -> Delivery:
        forbidden = self.permitted(sender, call) or self.check(sender, call)
        if forbidden:
            return self._bounce(sender, call, forbidden, turn)

        payload = str(payload_of(call))
        if call.verb == WAIT_VERB:
            return Delivery(call, True, reason="waited on purpose")

        if call.verb == ACT_VERB:
            terminal, result = self.judge(payload)
            delivery = Delivery(call, True, recipients=("judge",), result=result, terminal=terminal)
            if not terminal:
                self.announce(result, turn, exclude=sender)
            return delivery

        modality = MODALITY_BY_VERB[call.verb]
        detail: dict[str, object] = {}
        if modality.name == "gesture":
            symbols = parse_gestures(payload)
            payload = " ".join(symbols)
            detail["gestures"] = symbols

        message = Message(turn, sender, (), payload, modality.name, to=addressee_of(call))
        addressee = addressee_of(call)
        received = []
        for role in self.endpoints:
            if role == sender:
                continue
            if addressee and role != addressee:
                continue
            seen = message.perceived_by(self.senses[role])
            if seen is None:
                continue
            self.endpoints[role].receive(seen)
            received.append(role)
        if not received:
            return self._bounce(sender, call, phrase("notices", "nobody_received"), turn, detail)
        message = Message(turn, sender, tuple(received), payload, modality.name,
                          to=addressee_of(call))
        return Delivery(call, True, recipients=tuple(received), message=message, detail=detail)

    def _bounce(self, sender: str, call: Call, reason: str, turn: int, detail=None) -> Delivery:
        """Drop a call and tell its sender, at the start of the round after this one.

        The notice travels like any other message, so a monkey learns that nothing
        landed on the same delay as it learns everything else.
        """
        outcome = phrases("notices")["outcome_act" if call.verb == ACT_VERB else "outcome_message"]
        notice = phrase("notices", "bounce", reason=reason, verb=call.verb, outcome=outcome)
        self.endpoints[sender].receive(Message(turn, "system", (sender,), notice, "system"))
        return Delivery(call, False, reason=reason, detail=detail or {})

    def announce(self, text: str, turn: int, exclude: str = "") -> Message:
        recipients = tuple(role for role in self.endpoints if role != exclude)
        message = Message(turn, "system", recipients, text, modality="system")
        for role in recipients:
            self.endpoints[role].receive(message)
        return message
