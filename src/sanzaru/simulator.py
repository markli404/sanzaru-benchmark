"""The bomb simulator.

A bomb is a list of modules. Each module owns its own state, renders its own face,
writes its own page of the manual, and judges the actions addressed to it. The
simulator routes an action to the module that answers for it and asks the bomb
whether it is now defused.

Nothing here knows about wires in particular. Adding a keypad, a timer or a sequence
of switches means writing one more `Module` and listing it in a task, not editing the
judge.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Protocol

from .protocol import UNSPEAKABLE


@dataclass(frozen=True)
class Reading:
    """One line of the bomb's face.

    `shown` is what a monkey who can perceive it reads; `hidden` is what everyone else
    reads instead. Positions are structure and stay visible; colours are content and do
    not, which is why a blind monkey still counts three wires.
    """

    key: str
    shown: str
    hidden: str


@dataclass(frozen=True)
class Action:
    """A physical action, parsed but not yet judged."""

    op: str
    argument: str
    raw: str

    @classmethod
    def parse(cls, text: str) -> "Action":
        text = text.strip().lower()
        op, _, argument = text.partition(" ")
        return cls(op, argument.strip(), text)


@dataclass(frozen=True)
class Outcome:
    """What an action did. `terminal` ends the run either way."""

    message: str
    terminal: bool = False
    failed: bool = False

    @classmethod
    def boom(cls, message: str) -> "Outcome":
        return cls(message, terminal=True, failed=True)


class Module(Protocol):
    """A component of the bomb."""

    name: str
    ops: tuple[str, ...]

    def readings(self, bomb: "Bomb") -> list[Reading]: ...
    def signature(self) -> str: ...
    def manual(self, bomb: "Bomb") -> str: ...
    def solved(self) -> bool: ...
    def apply(self, action: Action, bomb: "Bomb") -> Outcome: ...
    def state(self) -> dict[str, object]: ...


@dataclass
class Indicator:
    """The display and the light. It has no actions; it is what the others are read against.

    Its value comes from the stage the bomb is in, so a module that advances the stage
    changes what everyone reads next round without telling the indicator anything.
    """

    stages: list[tuple[int, str]]
    name: str = "indicator"
    ops: tuple[str, ...] = ()
    # When set, the light never holds still: it walks this circle of colours, one
    # step per round, no matter what anyone does. The display still follows stages.
    cycle: list[str] | None = None
    # The display can walk its own circle of numbers, one step per round, purely to
    # have something to say. It obeys `once` the same way the light does.
    display_cycle: list[int] | None = None
    # With `once`, the circle is a broadcast: it plays through a single time and the
    # light goes dark for good. What it showed survives only in whoever watched.
    once: bool = False

    def value(self, bomb: "Bomb") -> tuple[int, str]:
        display, light = self.stages[min(bomb.stage, len(self.stages) - 1)]
        beat = max(bomb.round, 1) - 1
        if self.display_cycle:
            display = self.display_cycle[beat % len(self.display_cycle)]
        if self.cycle:
            if self.once and beat >= len(self.cycle):
                return (display, "dark")
            light = self.cycle[beat % len(self.cycle)]
        return (display, light)

    def readings(self, bomb: "Bomb") -> list[Reading]:
        display, light = self.value(bomb)
        return [
            Reading("DISPLAY", f"DISPLAY [{display}]", "DISPLAY [unreadable]"),
            Reading("LIGHT", f"LIGHT [{light}]", "LIGHT [unreadable]"),
        ]

    def signature(self) -> str:
        return ""

    def manual(self, bomb: "Bomb") -> str:
        if self.cycle and not self.once:
            count = {3: "three", 5: "five", 7: "seven"}.get(
                len(set(self.cycle)), str(len(set(self.cycle))))
            return (f"The light never holds. It changes every round, and it always walks the\n"
                    f"same circle of {count} colours. What matters is what it shows at the\n"
                    f"moment of the cut.")
        if self.cycle and self.once:
            # No sequence repeats a colour, so counting rounds and counting changes
            # agree and the unit needs no explaining. What does need saying is when
            # the counting stops, since the dark is the only signal for it.
            return ("The light flashes once each round, never the same colour twice\n"
                    "running, and then it stays dark. The dark means the flashing is\n"
                    "over.")
        return ""

    def solved(self) -> bool:
        return True

    def apply(self, action: Action, bomb: "Bomb") -> Outcome:
        return Outcome.boom(f"nothing answers to '{action.raw}'")

    def state(self) -> dict[str, object]:
        return {}


@dataclass
class WireBank:
    """The wires. Which colour to cut is looked up by whatever the indicator reads."""

    colors: list[str]
    table: dict[tuple, str]
    targets: int
    # What the table is indexed by. The default reads it against the indicator; a
    # bomb can hand in something else, and the wires never learn what it was.
    key: "Callable[[Bomb], tuple] | None" = None
    name: str = "wires"
    ops: tuple[str, ...] = ("cut",)
    cut: set[int] = field(default_factory=set)
    # When set, a correct cut is a round of musical chairs: the surviving wires take
    # the arrangement written for the new stage, and every old map is wrong.
    dances: list[list[str]] | None = None

    def readings(self, bomb: "Bomb") -> list[Reading]:
        shown = " ".join(
            f"{position}:[{'CUT' if position in self.cut else color}]"
            for position, color in enumerate(self.colors, 1)
        )
        hidden = " ".join(
            f"{position}:[{'CUT' if position in self.cut else 'unreadable'}]"
            for position in range(1, len(self.colors) + 1)
        )
        return [Reading("WIRES", f"WIRES {shown}", f"WIRES {hidden}")]

    def signature(self) -> str:
        return f'act(op="cut", position=N) — N is a wire position, 1 to {len(self.colors)}'

    def manual(self, bomb: "Bomb") -> str:
        rows_key = sorted({first for first, _ in self.table}, key=str)
        lights = sorted({light for _, light in self.table})
        if all(isinstance(first, str) for first in rows_key):
            head = ["| marks \\ light | " + " | ".join(lights) + " |",
                    "|---|" + "---|" * len(lights)]
            return "\n".join(head + [
                f"| {first} | " + " | ".join(self.table[(first, light)] for light in lights) + " |"
                for first in PATTERNS if first in rows_key
            ])
        displays = rows_key
        if displays == [0]:
            rows = ["| light | cut wire color |", "|---|---|"]
            rows += [f"| {light} | {self.table[(0, light)]} |" for light in lights]
            return "\n".join(rows)
        rows = ["| display \\ light | " + " | ".join(lights) + " |", "|---|" + "---|" * len(lights)]
        rows += [
            f"| {display} | " + " | ".join(self.table[(display, light)] for light in lights) + " |"
            for display in displays
        ]
        return "\n".join(rows)

    def expected(self, bomb: "Bomb") -> str | None:
        """The colour the manual demands right now, or None when it holds no rule."""
        if self.key is not None:
            return self.table.get(self.key(bomb))
        display, light = bomb.display, bomb.light
        return self.table.get((0, light) if (0, light) in self.table else (display, light))

    def solved(self) -> bool:
        return len(self.cut) >= self.targets

    def apply(self, action: Action, bomb: "Bomb") -> Outcome:
        if not action.argument.isdigit():
            return Outcome.boom(f"'{action.raw}' names no wire")
        position = int(action.argument)
        if not 1 <= position <= len(self.colors):
            return Outcome.boom(f"wire position {position} does not exist")
        if position in self.cut:
            return Outcome.boom(f"wire {position} was already cut")
        wanted = self.expected(bomb)
        if wanted is None:
            return Outcome.boom("the manual holds no rule for what the bomb shows now")
        if self.colors[position - 1] != wanted:
            return Outcome.boom(f"cut {self.colors[position - 1]}, expected {wanted}")
        self.cut.add(position)
        bomb.stage += 1
        if self.dances and bomb.stage - 1 < len(self.dances):
            self.colors[:] = self.dances[bomb.stage - 1]
        if self.solved():
            return Outcome("all required wires are cut")
        return Outcome("correct wire cut; the bomb has changed")

    def state(self) -> dict[str, object]:
        return {
            "wires": [
                {"position": position, "color": color, "cut": position in self.cut}
                for position, color in enumerate(self.colors, 1)
            ]
        }


@dataclass
class Prop:
    """Scenery that can be touched. It shows one face to the eyes and another to the
    hands, offers its verbs to the action list, explains nothing, and answers any
    action with the fuse. Buttons, dead keypads and noise strips are all Props."""

    shown: str
    felt: str
    verbs: tuple[str, ...] = ()
    sig: str = ""
    name: str = "prop"

    @property
    def ops(self) -> tuple[str, ...]:
        return self.verbs

    def readings(self, bomb: "Bomb") -> list[Reading]:
        return [Reading(self.name.upper(), self.shown, self.felt)]

    def signature(self) -> str:
        return self.sig

    def manual(self, bomb: "Bomb") -> str:
        return ""

    def solved(self) -> bool:
        return True

    def apply(self, action: Action, bomb: "Bomb") -> Outcome:
        return Outcome.boom("no rule answers to that")

    def state(self) -> dict[str, object]:
        return {}


@dataclass
class Unwritten:
    """A module whose page has been torn out of the manual. Everything else about it
    is untouched; it simply has nothing to say for itself."""

    module: "Module"

    def manual(self, bomb: "Bomb") -> str:
        return ""

    def __getattr__(self, name: str):
        return getattr(self.module, name)


@dataclass
class Note:
    """One line of manual and nothing else. It has no face and takes no action."""

    text: str
    name: str = "note"
    ops: tuple[str, ...] = ()

    def readings(self, bomb: "Bomb") -> list[Reading]:
        return []

    def signature(self) -> str:
        return ""

    def manual(self, bomb: "Bomb") -> str:
        return self.text

    def solved(self) -> bool:
        return True

    def apply(self, action: Action, bomb: "Bomb") -> Outcome:
        return Outcome.boom(f"nothing answers to '{action.raw}'")

    def state(self) -> dict[str, object]:
        return {}


@dataclass
class TallyTable:
    """The one page that decodes the broadcast: how often one colour flashed.

    It reads nothing and does nothing; it is pure manual. The count it asks for
    exists only in whoever watched the light while it was still speaking."""

    colour: str
    rows: list[str]        # rows[n] is the wire to cut after n flashes of `colour`
    name: str = "tally"
    ops: tuple[str, ...] = ()
    # When set, the same table serves a second cut, read by this colour's count.
    second: str = ""

    def readings(self, bomb: "Bomb") -> list[Reading]:
        return []

    def signature(self) -> str:
        return ""

    def manual(self, bomb: "Bomb") -> str:
        if self.second:
            head = (f"The first wire to cut is named by how many times the light flashed\n"
                    f"{self.colour}, and the second wire by how many times it flashed\n"
                    f"{self.second}. Both counts read the same table. When the light goes\n"
                    f"dark, the flashing is over:\n"
                    f"| flashes | cut wire color |\n|---|---|")
        else:
            head = (f"Which wire to cut is named by how many times the light flashed\n"
                    f"{self.colour}. When the light goes dark, the flashing is over:\n"
                    f"| {self.colour} flashes | cut wire color |\n|---|---|")
        body = "\n".join(f"| {n} | {colour} |" for n, colour in enumerate(self.rows))
        return head + "\n" + body

    def solved(self) -> bool:
        return True

    def apply(self, action: Action, bomb: "Bomb") -> Outcome:
        return Outcome.boom(f"nothing answers to '{action.raw}'")

    def state(self) -> dict[str, object]:
        return {}


@dataclass
class Seal:
    """Invisible bookkeeping. It renders nothing and answers nothing; the bomb is
    only done once its test passes, which lets modules that police the order of
    things stay out of the finish line themselves."""

    test: "Callable[[], bool]"
    name: str = "seal"
    ops: tuple[str, ...] = ()

    def readings(self, bomb: "Bomb") -> list[Reading]:
        return []

    def signature(self) -> str:
        return ""

    def manual(self, bomb: "Bomb") -> str:
        return ""

    def solved(self) -> bool:
        return self.test()

    def apply(self, action: Action, bomb: "Bomb") -> Outcome:
        return Outcome.boom(f"nothing answers to '{action.raw}'")

    def state(self) -> dict[str, object]:
        return {}


@dataclass
class Bomb:
    """The simulator. It owns the stage, routes actions, and decides when it is over."""

    kind: str
    seed: int
    modules: list[Module]
    stage: int = 0
    # Which round the world is in. Nobody sets it by hand: the world steps itself.
    round: int = 0

    finished: bool = False
    failed: bool = False
    failure_reason: str | None = None
    actions: list[str] = field(default_factory=list)

    def tick(self) -> None:
        """One round passes. Doing nothing is also a transition: any module reading
        the round moves with it, and no action is required for the world to change."""
        self.round += 1

    @property
    def indicator(self) -> "Module":
        return next(module for module in self.modules if module.name == "indicator")

    @property
    def display(self) -> int:
        return self.indicator.value(self)[0]

    @property
    def light(self) -> str:
        return self.indicator.value(self)[1]

    def face(self, perceives: bool) -> str:
        """The bomb as one monkey reads it: structure always, content only if perceived."""
        lines = []
        for module in self.modules:
            for reading in module.readings(self):
                lines.append(reading.shown if perceives else reading.hidden)
        return "\n".join(lines)

    def operations(self) -> tuple[str, ...]:
        """Every verb some module on this bomb answers to."""
        return tuple(op for module in self.modules for op in module.ops)

    def signatures(self) -> str:
        """Every action this particular bomb accepts. A bomb without buttons has no
        push; a bomb with a pad has a press. The prompt reads this rather than a
        fixed list, so a monkey is never told about a verb that does nothing."""
        lines = [module.signature() for module in self.modules]
        return "\n".join(f"    {line}" for line in lines if line)

    def manual(self) -> str:
        pages = [module.manual(self) for module in self.modules]
        return "\n\n".join(page for page in pages if page)

    def live(self, module: Module) -> bool:
        """A module accepts actions only once everything before it is solved."""
        return all(earlier.solved() for earlier in self.modules[: self.modules.index(module)])

    def apply(self, text: str) -> tuple[bool, str]:
        """Apply an action payload. Returns (terminal, message)."""
        action = Action.parse(text)
        self.actions.append(action.raw)
        if self.finished or self.failed:
            return True, "the bomb is already resolved"

        owner = next((module for module in self.modules if action.op in module.ops), None)
        if owner is None:
            return self._fail(f"nothing on the bomb answers to '{action.raw}'")
        if not self.live(owner):
            return self._fail(f"the {owner.name} cannot be used yet")

        outcome = owner.apply(action, self)
        if outcome.failed:
            return self._fail(outcome.message)
        if all(module.solved() for module in self.modules):
            self.finished = True
            return True, outcome.message
        return False, outcome.message

    def _fail(self, reason: str) -> tuple[bool, str]:
        self.failed = True
        self.failure_reason = reason
        return True, reason

    def snapshot(self) -> dict[str, object]:
        """JSON-ready mutable state captured around every model turn."""
        state: dict[str, object] = {
            "kind": self.kind,
            "stage": self.stage,
            "display": self.display,
            "light": self.light,
            "buttons": [],
            "finished": self.finished,
            "failed": self.failed,
            "failure_reason": self.failure_reason,
            "actions": list(self.actions),
        }
        for module in self.modules:
            state.update(module.state())
        return state


# The engraved alphabet is exactly the set a voice cannot carry.
PLATE_SYMBOLS = UNSPEAKABLE

PATTERNS = ("all the same", "two the same", "all different")


@dataclass
class SymbolPlate:
    """Three marks engraved where only touch can read them.

    Nothing is pressed here. The marks matter only for their shape — whether they
    repeat — and that shape is one of the inputs the wire table is read against. A
    monkey reading by sight sees that the plate is there and nothing more.
    """

    marks: list[str]
    name: str = "plate"
    ops: tuple[str, ...] = ()

    def pattern(self) -> str:
        return PATTERNS[{1: 0, 2: 1, 3: 2}[len(set(self.marks))]]

    def readings(self, bomb: "Bomb") -> list[Reading]:
        return [Reading("PLATE", "PLATE [engraved]",
                        "PLATE engraved " + " ".join(f"[{mark}]" for mark in self.marks))]

    def signature(self) -> str:
        return ""

    def manual(self, bomb: "Bomb") -> str:
        return ""

    def solved(self) -> bool:
        return True

    def apply(self, action: Action, bomb: "Bomb") -> Outcome:
        return Outcome.boom(f"nothing on the plate answers to '{action.raw}'")

    def state(self) -> dict[str, object]:
        return {"plate": list(self.marks), "pattern": self.pattern()}


@dataclass
class CodeStrip:
    """Marks in coloured slots, and the page that turns a pair into a digit.

    A mark is engraved, so touch has it. A colour is printed, so sight has it. The
    page belongs to whoever reads the manual. The code exists only once all three
    have been said aloud, and nowhere on the bomb itself.
    """

    marks: list[str]
    colours: list[str]
    digits: dict[tuple[str, str], int]
    name: str = "strip"
    ops: tuple[str, ...] = ()

    def code(self) -> str:
        return "".join(str(self.digits[pair]) for pair in zip(self.marks, self.colours))

    def readings(self, bomb: "Bomb") -> list[Reading]:
        seen = " ".join(f"[{colour}]" for colour in self.colours)
        felt = " ".join(f"[{mark}]" for mark in self.marks)
        return [Reading("STRIP", f"STRIP painted {seen}", f"STRIP engraved {felt}")]

    def signature(self) -> str:
        return ""

    def manual(self, bomb: "Bomb") -> str:
        colours = sorted({colour for _, colour in self.digits})
        marks = sorted({mark for mark, _ in self.digits})
        rows = ["Each slot on the strip gives one digit, from its mark and its colour:",
                "| mark \\ colour | " + " | ".join(colours) + " |",
                "|---|" + "---|" * len(colours)]
        rows += [f"| {mark} | " + " | ".join(str(self.digits[(mark, colour)]) for colour in colours) + " |"
                 for mark in marks]
        return "\n".join(rows)

    def solved(self) -> bool:
        return True

    def apply(self, action: Action, bomb: "Bomb") -> Outcome:
        return Outcome.boom(f"nothing on the strip answers to '{action.raw}'")

    def state(self) -> dict[str, object]:
        return {"strip_marks": list(self.marks), "strip_colours": list(self.colours)}


@dataclass
class Keypad:
    """Four keys under a lock, with the digits scattered across them.

    The keys and the digits on them are plain to anyone who can perceive the bomb.
    What is not plain is the code, and a key is named by where it sits rather than
    by what it carries — so an instruction has to say the digit, and whoever presses
    has to find where that digit lives.

    A key is committed the moment it is pressed. There is no backspace.
    """

    keys: list[int]
    code: str
    name: str = "keypad"
    ops: tuple[str, ...] = ("press",)
    entered: str = ""
    opened: bool = False
    # Raised digits are read by touch; printed ones are not. Either way the keys
    # themselves, and how many digits the pad wants, are shapes anyone can feel.
    raised: bool = True
    # When set, the keys wear these marks instead of digits. The digits underneath
    # still open the pad; only the manual says which mark is which digit.
    labels: list[str] | None = None
    # When set, press number k is lawful only while the bomb sits in stage
    # only_at[k], and a lawful press advances the stage itself. The pad then locks
    # nothing on its own; a Seal at the end of the bomb collects its debt instead.
    only_at: tuple[int, ...] | None = None


    def slot_of(self, digit: str) -> int:
        return self.keys.index(int(digit)) + 1

    def readings(self, bomb: "Bomb") -> list[Reading]:
        # No LOCKED/OPEN word: how many digits it wants and what it has taken says the
        # same thing, without sounding like a separate lock to be picked first.
        def face(seen: bool) -> str:
            worn = self.labels or self.keys
            keys = " ".join(f"{n}:[{mark if seen else 'unreadable'}]"
                            for n, mark in enumerate(worn, 1))
            entered = (self.entered if seen else "?" * len(self.entered)) or "nothing"
            return f"KEYPAD {keys} [{len(self.code)} digits] [entered {entered}]"
        return [Reading("KEYPAD", face(True), face(self.raised))]

    def signature(self) -> str:
        return f'act(op="press", slot=N) — N is a key by its place, 1 to {len(self.keys)}'

    def manual(self, bomb: "Bomb") -> str:
        page = (f"The keypad locks everything behind it. Enter its {len(self.code)} digits in\n"
                "order first: anything behind it, touched while it is still locked, goes off.")
        if self.labels:
            rows = "\n".join(f"| {mark} | {digit} |"
                             for mark, digit in sorted(zip(self.labels, self.keys), key=str))
            page += "\n\nEvery key wears a mark, and every mark is a digit:\n| mark | digit |\n|---|---|\n" + rows
        return page

    def solved(self) -> bool:
        return True if self.only_at is not None else self.opened

    def apply(self, action: Action, bomb: "Bomb") -> Outcome:
        if not action.argument.isdigit():
            return Outcome.boom(f"'{action.raw}' names no key")
        slot = int(action.argument)
        if not 1 <= slot <= len(self.keys):
            return Outcome.boom(f"key {slot} does not exist")
        if self.only_at is not None and bomb.stage != self.only_at[len(self.entered)]:
            return Outcome.boom("nothing asks for the keypad now")
        self.entered += str(self.keys[slot - 1])
        if not self.code.startswith(self.entered):
            return Outcome.boom(f"entered {self.entered}, the code is {self.code}")
        if self.only_at is not None:
            bomb.stage += 1
        if self.entered == self.code:
            self.opened = True
            return Outcome("the keypad opens" if self.only_at is None
                           else "key accepted; the keypad is satisfied")
        return Outcome(f"key accepted, {len(self.code) - len(self.entered)} digits to go")

    def state(self) -> dict[str, object]:
        return {"keys": list(self.keys), "entered": self.entered, "keypad_open": self.opened}
