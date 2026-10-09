"""Task definitions: what a bomb is made of, and how a seed builds one.

A task says which modules the bomb carries and how the seed fills them in. It says
nothing about judging or rendering — the simulator owns both — so a harder wiring is a
longer module list here, not a change to the judge.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import random

from .simulator import (
    PATTERNS, PLATE_SYMBOLS, Bomb, CodeStrip, Indicator, Keypad, Note, Prop, Seal,
    SymbolPlate, TallyTable, Unwritten, WireBank,
)

COLORS = ("red", "blue", "green", "yellow")


class TaskKind(str, Enum):
    BASE_1 = "base-1"
    BASE_2 = "base-2"
    BASE_3 = "base-3"
    BASE_4 = "base-4"
    BASE_5 = "base-5"
    THREE_OF_A_KIND = "three-of-a-kind"
    STEREO_1 = "stereo-1"
    FLASHING_LIGHT_1 = "flashing-light-1"
    FLASHING_LIGHT_2 = "flashing-light-2"
    FLASHING_LIGHT_3 = "flashing-light-3"
    FLASHING_LIGHT_4 = "flashing-light-4"
    FLASHING_LIGHT_5 = "flashing-light-5"
    FLASHBACK_1 = "flashback-1"
    FLASHBACK_2 = "flashback-2"
    FLASHBACK_3 = "flashback-3"
    SHUFFLE_WIRES_1 = "shuffle-wires-1"
    SHUFFLE_WIRES_2 = "shuffle-wires-2"
    SHUFFLE_WIRES_3 = "shuffle-wires-3"
    HAYSTACK_1 = "haystack-1"
    HAYSTACK_2 = "haystack-2"
    HAYSTACK_3 = "haystack-3"
    BAIT_1 = "bait-1"
    BAIT_2 = "bait-2"
    BAIT_3 = "bait-3"
    CARVING_1 = "carving-1"
    CARVING_2 = "carving-2"
    COMBO_LOCK_1 = "combo-lock-1"
    COMBO_LOCK_2 = "combo-lock-2"
    COMBO_LOCK_3 = "combo-lock-3"


@dataclass(frozen=True)
class View:
    """One role's private observation: a heading and the text under it."""

    label: str
    body: str


# Which roles perceive the bomb's face, and who reads the manual instead. A new role
# needs an entry here; the error below says so.
SEES_BOMB = {"deaf": True, "blind": False}
READS_MANUAL = {"mute"}


def view_for(bomb: Bomb, role: str) -> View:
    """The private observation handed to a role at the start of its round."""
    if role == "almighty":
        # Every sense at once. Sight covers nearly everything, but a part whose
        # content lives under the fingers alone (an engraved mark the eyes read
        # as [unreadable]) hands over its felt face instead: whichever face reveals more
        # is the one the almighty holds.
        lines = []
        for module in bomb.modules:
            for reading in module.readings(bomb):
                better_felt = (reading.hidden.count("unreadable")
                               < reading.shown.count("unreadable"))
                lines.append(reading.hidden if better_felt else reading.shown)
        return View("BOMB AND MANUAL", "\n".join(lines) + "\n\n" + bomb.manual())
    if role in READS_MANUAL:
        return View("DEFUSAL MANUAL", bomb.manual())
    if role in SEES_BOMB:
        return View("ACTION BOARD", bomb.face(perceives=SEES_BOMB[role]))
    raise KeyError(f"no bomb view defined for role: {role}")


# How many times base runs the loop. Higher tiers wait on review before they
# rejoin this table.
BASE_CUTS = {
    TaskKind.BASE_1: 1,
    TaskKind.BASE_3: 3,
}
# The plus split grows the grid: (lights and displays in the manual, wires, cuts).
GRID_SHAPE = {
    TaskKind.BASE_4: (5, 5, 3),
    TaskKind.BASE_5: (5, 7, 5),
}
# The circle the flashing light walks and how many of its colours the manual
# covers. An uncovered moment holds no rule, so a cut there is a boom.
FLASH_SHAPE = {
    TaskKind.FLASHING_LIGHT_1: (3, 3),
    TaskKind.FLASHING_LIGHT_2: (3, 1),
    TaskKind.FLASHING_LIGHT_3: (5, 3),
    TaskKind.FLASHING_LIGHT_4: (5, 1),
    TaskKind.FLASHING_LIGHT_5: (7, 1),
}
EXTRA_COLORS = ("white", "purple", "orange")


def _wire_bank(rng: random.Random, kind: TaskKind) -> tuple[WireBank, list[tuple[int, str]], list[int]]:
    """The wires, the stages the indicator will step through, and the displays in play.

    The relay family, at its smallest: three wires, three lights, a three-row
    one-to-one manual, and as many cuts as the level asks for."""
    cuts = BASE_CUTS[kind]
    colors = rng.sample(COLORS, 3)
    lights = rng.sample(COLORS, 3)
    table = dict(zip(((0, light) for light in lights), rng.sample(colors, 3)))
    stages = [(0, light) for light in rng.sample(lights, cuts)]
    return WireBank(colors, table, targets=cuts), stages, [0]


def _symbol_plate(rng: random.Random) -> SymbolPlate:
    """Three marks, drawn so all three shapes come up across seeds."""
    alphabet = rng.sample(PLATE_SYMBOLS, 3)
    shape = rng.choice(["aaa", "aab", "abc"])
    marks = [alphabet["abc".index(letter)] for letter in shape]
    rng.shuffle(marks)
    return SymbolPlate(marks)


PROBLEMS_PER_KIND = 5

# Everything a task owns besides its bomb: its round budget, how much memory the
# players keep (zero keeps everything), and which speaking orders it permits (empty
# permits any). One table, so a new task states its whole contract in one line.
# Blind must act before Deaf can brief him again, or "cut now" lands inside the
# same round and the timing problem evaporates.
_BLIND_FIRST = (("mute", "blind", "deaf"), ("blind", "deaf", "mute"))
SPECS: dict[TaskKind, tuple[int, int, tuple[tuple[str, ...], ...]]] = {
    TaskKind.BASE_1: (8, 0, ()),
    TaskKind.BASE_2: (8, 0, ()),
    TaskKind.BASE_3: (12, 0, ()),
    TaskKind.BASE_4: (16, 0, ()),
    TaskKind.BASE_5: (24, 0, ()),
    TaskKind.THREE_OF_A_KIND: (8, 0, ()),
    TaskKind.STEREO_1: (8, 0, ()),
    TaskKind.FLASHING_LIGHT_1: (9, 0, _BLIND_FIRST),
    TaskKind.FLASHING_LIGHT_2: (11, 0, _BLIND_FIRST),
    TaskKind.FLASHING_LIGHT_3: (11, 0, _BLIND_FIRST),
    TaskKind.FLASHING_LIGHT_4: (13, 0, _BLIND_FIRST),
    TaskKind.FLASHING_LIGHT_5: (18, 0, _BLIND_FIRST),
    TaskKind.FLASHBACK_1: (10, 3, ()),
    TaskKind.FLASHBACK_2: (12, 3, ()),
    TaskKind.FLASHBACK_3: (14, 3, ()),
    # Mute must speak before Deaf, or the position map never goes stale.
    TaskKind.SHUFFLE_WIRES_1: (10, 0, (("blind", "mute", "deaf"), ("mute", "deaf", "blind"))),
    TaskKind.SHUFFLE_WIRES_2: (20, 0, (("blind", "mute", "deaf"), ("mute", "deaf", "blind"))),
    TaskKind.SHUFFLE_WIRES_3: (24, 0, (("blind", "mute", "deaf"), ("mute", "deaf", "blind"))),
    TaskKind.HAYSTACK_1: (8, 0, ()),
    TaskKind.HAYSTACK_2: (12, 0, ()),
    TaskKind.HAYSTACK_3: (16, 0, ()),
    TaskKind.BAIT_1: (8, 0, ()),
    TaskKind.BAIT_2: (8, 0, ()),
    # Eight rounds with a visible timer: the endgame clock is Deaf's to read and
    # the urgency is his to relay, which is the whole point of the countdown.
    TaskKind.BAIT_3: (8, 0, ()),
    TaskKind.CARVING_1: (8, 0, ()),
    TaskKind.CARVING_2: (12, 0, ()),
    TaskKind.COMBO_LOCK_1: (12, 0, ()),
    TaskKind.COMBO_LOCK_2: (14, 0, ()),
    TaskKind.COMBO_LOCK_3: (16, 0, ()),
}


# When set, the bomb's timer becomes visible in the endgame: for the last N
# rounds, whoever sees the bomb also sees how many rounds remain. No shipped
# task uses it: real agent teams get no ambient clock, so neither do these.
# The machinery stays for ablations.
COUNTDOWN: dict[TaskKind, int] = {}


def countdown_for(kind: TaskKind | str) -> int:
    return COUNTDOWN.get(TaskKind(kind), 0)


def rounds_for(kind: TaskKind | str) -> int:
    return SPECS[TaskKind(kind)][0]


def window_for(kind: TaskKind | str) -> int:
    return SPECS[TaskKind(kind)][1]


def orders_for(kind: TaskKind | str) -> tuple[tuple[str, ...], ...]:
    return SPECS[TaskKind(kind)][2]


# The benchmark ships in two splits. CORE is the diagnostic suite: every config
# moves one variable, so a death names an axis. PLUS makes no attribution claim;
# it exists to separate the strongest teams, and that is all it claims.
CORE = (
    TaskKind.BASE_1, TaskKind.BASE_2, TaskKind.BASE_3,
    TaskKind.FLASHING_LIGHT_1, TaskKind.FLASHING_LIGHT_2,
    TaskKind.FLASHBACK_1, TaskKind.FLASHBACK_2,
    TaskKind.SHUFFLE_WIRES_1, TaskKind.SHUFFLE_WIRES_2,
    TaskKind.HAYSTACK_1, TaskKind.HAYSTACK_2,
    TaskKind.BAIT_1, TaskKind.BAIT_2, TaskKind.BAIT_3,
    TaskKind.CARVING_1, TaskKind.CARVING_2,
)
PLUS = (
    TaskKind.BASE_4, TaskKind.BASE_5,
    TaskKind.FLASHBACK_3,
    TaskKind.SHUFFLE_WIRES_3,
    TaskKind.HAYSTACK_3,
    TaskKind.FLASHING_LIGHT_3, TaskKind.FLASHING_LIGHT_4, TaskKind.FLASHING_LIGHT_5,
)

# Tasks kept for reproducibility but withdrawn from the ladder. stereo grows the
# manual grid, which loads the manual holder's reasoning, not the cooperation
# between the three. three-of-a-kind and combo-lock both died with the fusion
# axis: talkative agents make distributed facts converge for free, so joining
# them is a lookup, not a cooperation. What was real in combo-lock, the marks
# nobody can name, lives on as the carving family.
RETIRED = frozenset({
    TaskKind.THREE_OF_A_KIND, TaskKind.STEREO_1,
    TaskKind.COMBO_LOCK_1, TaskKind.COMBO_LOCK_2, TaskKind.COMBO_LOCK_3,
})


def family_of(kind: TaskKind | str) -> str:
    """The task family a config belongs to: its label without the level number."""
    label = TaskKind(kind).value
    head, _, tail = label.rpartition("-")
    return head if tail.isdigit() else label


def problem(kind: TaskKind | str, number: int) -> Bomb:
    """Problem #number of a task, 1 to PROBLEMS_PER_KIND. The number is the seed, so
    `base-1#3` names the same bomb forever, on every machine."""
    if not 1 <= number <= PROBLEMS_PER_KIND:
        raise ValueError(f"problems are numbered 1 to {PROBLEMS_PER_KIND}, not {number}")
    return generate_puzzle(kind, number)


def generate_puzzle(kind: TaskKind | str, seed: int) -> Bomb:
    """Build the bomb this task and seed describe. Same inputs, same bomb, always."""
    kind = TaskKind(kind)
    # The kind is folded into the stream, so combo-lock-2#3 and combo-lock-1#3 are
    # different bombs, not the same bomb with a different face.
    rng = random.Random(f"{kind.value}#{seed}")
    if kind is TaskKind.BASE_2:
        # The same three wires, but the manual key grows a dimension: the wire is
        # named by display and light together. Every row is a permutation of the
        # wires, and the played column disagrees across its rows, so neither
        # reading alone ever settles the cut. Deaf must carry two exact
        # coordinates, and Mute must land on one cell.
        colors = rng.sample(COLORS, 3)
        displays = rng.sample(range(1, 10), 3)
        lights = rng.sample(COLORS, 3)
        table = {(d, l): colour
                 for d in displays for l, colour in zip(lights, rng.sample(colors, 3))}
        played = (rng.choice(displays), rng.choice(lights))
        while len({table[(d, played[1])] for d in displays}) == 1:
            redrawn = rng.choice([d for d in displays if d != played[0]])
            for l, colour in zip(lights, rng.sample(colors, 3)):
                table[(redrawn, l)] = colour
        return Bomb(kind.value, seed, [
            Indicator([played]), WireBank(colors, table, targets=1),
        ])

    if kind in GRID_SHAPE:
        # The cross-read at plus scale. The grid is played several times, each
        # correct cut moves both readings at once, and the played cells target
        # distinct wires, so no cut is ever demanded twice. Rows never repeat a
        # colour, and a played cell's column always disagrees somewhere, so
        # neither reading alone ever settles a cut.
        grid, wire_count, cuts = GRID_SHAPE[kind]
        palette = list(COLORS) + list(EXTRA_COLORS)
        colors = rng.sample(palette, wire_count)
        displays = rng.sample(range(1, 10), grid)
        lights = rng.sample(palette, grid)
        while True:
            stages = rng.sample([(d, l) for d in displays for l in lights], cuts)
            targets = dict(zip(stages, rng.sample(colors, cuts)))
            table = {}
            for display in displays:
                fixed = {light: targets[(display, light)]
                         for d, light in stages if d == display}
                pool = [c for c in colors if c not in fixed.values()]
                filling = rng.sample(pool, grid - len(fixed))
                free = [l for l in lights if l not in fixed]
                row = {**fixed, **dict(zip(free, filling))}
                for light in lights:
                    table[(display, light)] = row[light]
            if all(len({table[(d, l)] for d in displays}) > 1
                   and len({table[(d, l)] for l in lights}) > 1
                   for d, l in stages):
                break
        return Bomb(kind.value, seed, [
            Indicator(stages), WireBank(colors, table, targets=cuts),
        ])

    if kind is TaskKind.STEREO_1:
        # One cut, two coordinates. The wire is named by display and light together,
        # and the played column disagrees across its two rows, so reading the light
        # alone can never settle it: the manual holder must cross both facts.
        colors = rng.sample(COLORS, 3)
        displays = rng.sample(range(1, 10), 2)
        lights = rng.sample(COLORS, 2)
        top = dict(zip(lights, rng.sample(colors, 2)))
        played = (rng.choice(displays), rng.choice(lights))
        other_light = next(l for l in lights if l != played[1])
        low = {played[1]: rng.choice([c for c in colors if c != top[played[1]]])}
        low[other_light] = rng.choice([c for c in colors if c != low[played[1]]])
        rows = {displays[0]: top, displays[1]: low}
        table = {(d, l): rows[d][l] for d in displays for l in lights}
        return Bomb(kind.value, seed, [
            Indicator([played]), WireBank(colors, table, targets=1),
        ])

    if kind in FLASH_SHAPE:
        # The light walks a circle, one colour per round, and the whole question
        # is agreeing on a moment. Where the manual covers every colour, any
        # moment is lawful but the answer moves with the light; where it covers
        # one, all other moments hold no rule and the cut must wait for the
        # window. Blind acts before Deaf can brief him again, so every
        # instruction lands one round late and must be aimed a step ahead.
        circle, coverage = FLASH_SHAPE[kind]
        palette = list(COLORS) + list(EXTRA_COLORS)
        cycle = rng.sample(palette, circle)
        covered = rng.sample(cycle, coverage)
        colors = rng.sample(COLORS, 3)
        table = dict(zip(((0, light) for light in covered), rng.sample(colors, coverage)))
        return Bomb(kind.value, seed, [
            Indicator([(0, cycle[0])], cycle=cycle), WireBank(colors, table, targets=1),
        ])

    if kind in (TaskKind.BAIT_1, TaskKind.BAIT_2):
        # single-wire with a liar on board. The bomb prints an offer the manual
        # alone knows to be the fuse, and the manual's holder cannot speak. On
        # level 1 the offer reaches only the eyes, and the actor at least needs a
        # relay to be tempted; on level 2 the lettering is embossed, the hands read
        # it round one, and the veto must outrun the actor's own impulse.
        colors = rng.sample(COLORS, 3)
        lights = rng.sample(COLORS, 3)
        table = dict(zip(((0, light) for light in lights), rng.sample(colors, 3)))
        stages = [(0, rng.choice(lights))]
        label = "BUTTON [large] [PUSH TO DEFUSE]"
        felt = (label.replace("[large]", "embossed") if kind is TaskKind.BAIT_2
                else "BUTTON [large] [smooth]")
        return Bomb(kind.value, seed, [
            Indicator(stages),
            Prop(label, felt, verbs=("push",), sig='act(op="push") — the large button',
                 name="button"),
            Note("Anything the bomb offers in print is bait, and taking the bait\n"
                 "is the fuse. The only way out is the cut below."),
            WireBank(colors, table, targets=1),
        ])

    if kind is TaskKind.BAIT_3:
        # The lie inverts. Nothing tempts a wrong action; a sign under the
        # actor's own fingers forbids the right one. The manual outranks the
        # bomb, says so in as many words, and the only failure left is fear:
        # a team that believes the sign just runs out the clock.
        colors = rng.sample(COLORS, 3)
        lights = rng.sample(COLORS, 3)
        table = dict(zip(((0, light) for light in lights), rng.sample(colors, 3)))
        stages = [(0, rng.choice(lights))]
        sign = "SIGN embossed [DO NOT CUT ANY WIRE]"
        return Bomb(kind.value, seed, [
            Indicator(stages),
            Prop(sign, sign, name="sign"),
            Note("The bomb itself may mislead you, in print or under your\n"
                 "fingers. This manual is the only thing that is always true:\n"
                 "where the bomb and this page disagree, believe this page.\n"
                 "The only way out is the cut below."),
            WireBank(colors, table, targets=1),
        ])

    if kind in (TaskKind.SHUFFLE_WIRES_1, TaskKind.SHUFFLE_WIRES_2):
        # After every correct cut the survivors rotate seats. A rotation of distinct
        # colours is a derangement: nobody keeps their place, so every map drawn
        # before the cut is wrong and the board must be read again. Cut seats keep
        # their stubs. Both levels are five wires under a one-to-one table; level
        # one asks for two cuts, level two for four.
        cuts = 2 if kind is TaskKind.SHUFFLE_WIRES_1 else 4
        palette = list(COLORS) + list(EXTRA_COLORS[:1])
        colors = rng.sample(palette, 5)
        lights = rng.sample(palette, 5)
        table = dict(zip(((0, light) for light in lights), rng.sample(colors, 5)))
        played = rng.sample(lights, cuts)
        stages = [(0, light) for light in played]
        targets = [table[(0, light)] for light in played]

        arrangement = list(colors)
        gone: set[int] = set()
        dances = []
        for target in targets[:-1]:
            gone.add(arrangement.index(target))
            live = [i for i in range(len(colors)) if i not in gone]
            turned = arrangement[:]
            survivors = [arrangement[i] for i in live]
            for seat, colour in zip(live, survivors[1:] + survivors[:1]):
                turned[seat] = colour
            dances.append(turned)
            arrangement = turned
        return Bomb(kind.value, seed, [
            Indicator(stages),
            WireBank(colors, table, targets=cuts, dances=dances),
        ])

    if kind is TaskKind.SHUFFLE_WIRES_3:
        # The dance at plus scale. The wire is named by display and light
        # together, four cells are played over five wires, and after every
        # correct cut the survivors still trade seats. Two coordinates in, a
        # dead map out, four times over.
        palette = list(COLORS) + list(EXTRA_COLORS)
        colors = rng.sample(palette, 5)
        displays = rng.sample(range(1, 10), 5)
        lights = rng.sample(palette, 5)
        while True:
            stages = rng.sample([(d, l) for d in displays for l in lights], 4)
            staged = dict(zip(stages, rng.sample(colors, 4)))
            table = {}
            for display in displays:
                fixed = {light: staged[(display, light)]
                         for d, light in stages if d == display}
                pool = [c for c in colors if c not in fixed.values()]
                filling = rng.sample(pool, 5 - len(fixed))
                free = [l for l in lights if l not in fixed]
                row = {**fixed, **dict(zip(free, filling))}
                for light in lights:
                    table[(display, light)] = row[light]
            if all(len({table[(d, l)] for d in displays}) > 1
                   and len({table[(d, l)] for l in lights}) > 1
                   for d, l in stages):
                break
        targets = [table[stage] for stage in stages]

        arrangement = list(colors)
        gone: set[int] = set()
        dances = []
        for target in targets[:-1]:
            gone.add(arrangement.index(target))
            live = [i for i in range(len(colors)) if i not in gone]
            turned = arrangement[:]
            survivors = [arrangement[i] for i in live]
            for seat, colour in zip(live, survivors[1:] + survivors[:1]):
                turned[seat] = colour
            dances.append(turned)
            arrangement = turned
        return Bomb(kind.value, seed, [
            Indicator(stages),
            WireBank(colors, table, targets=4, dances=dances),
        ])

    if kind in (TaskKind.HAYSTACK_1, TaskKind.HAYSTACK_2):
        # Six wires and a manual of one plain sentence. Everything else on the
        # board performs: the light walks colours, the display walks numbers, a
        # strip wears paint and marks, a keypad wears engraved digits. None of it
        # means anything, and the manual will not say so. Level one asks for one
        # cut; level two names three wires in order, and the theatre plays on.
        cuts = 1 if kind is TaskKind.HAYSTACK_1 else 3
        palette = list(COLORS) + list(EXTRA_COLORS)
        colors = rng.sample(palette, 6)
        targets = rng.sample(colors, cuts)
        marks = rng.sample(PLATE_SYMBOLS, 3)
        paint = " ".join(f"[{rng.choice(COLORS)}]" for _ in range(3))
        carve = " ".join(f"[{rng.choice(marks)}]" for _ in range(3))
        strip = Prop(f"STRIP painted {paint}", f"STRIP engraved {carve}", name="strip")
        keys = rng.sample(range(10), 4)
        pad_face = ("KEYPAD engraved " + " ".join(f"{n}:[{d}]" for n, d in enumerate(keys, 1))
                    + " [1 digits] [entered nothing]")
        keypad = Prop(pad_face, pad_face, verbs=("press",),
                      sig='act(op="press", slot=N) — N is a key by its place, 1 to 4',
                      name="keypad")
        if cuts == 1:
            note = f"Cut the {targets[0]} wire."
        else:
            note = (f"Cut the {targets[0]} wire, then the {targets[1]} wire,\n"
                    f"then the {targets[2]} wire.")
        table = {(n, "any"): target for n, target in enumerate(targets)}
        return Bomb(kind.value, seed, [
            # The circles are long and coprime, so within any budget the board
            # never visibly repeats: it just performs.
            Unwritten(Indicator([(0, "red")],
                                cycle=[rng.choice(COLORS) for _ in range(7)],
                                display_cycle=[rng.randrange(10) for _ in range(11)])),
            Note(note),
            strip,
            keypad,
            Unwritten(WireBank(colors, table, targets=cuts,
                               key=lambda bomb: (bomb.stage, "any"))),
        ])

    if kind in (TaskKind.FLASHBACK_1, TaskKind.FLASHBACK_2):
        # The light spends its opening rounds flashing one of two colours at random,
        # then goes dark for good, and the wire is named by how many times the
        # counted colour appeared. Level 1 flashes three times, which just fits the
        # three-round memory; level 2 flashes five, which does not: by the time the
        # light dies, the first flashes have already fallen out of every context,
        # and only a tally kept alive out loud survives. Neighbouring counts never
        # share a wire, so an off-by-one is always fatal.
        beats = 3 if kind is TaskKind.FLASHBACK_1 else 5
        colors = rng.sample(COLORS, 3)
        # Three colours in the sequence, never the same one twice running. With two
        # colours a no-repeat rule forces strict alternation and the count follows
        # from the length; with three it still has to be counted. The no-repeat rule
        # is what makes "how many times it flashed" mean one thing: a colour that
        # held for two rounds would read as one flash to the eye and two to the
        # simulator, and no channel in the game can settle which was meant.
        counted, other, spacer = rng.sample(COLORS, 3)
        flashes = _no_repeat(rng, (counted, other, spacer), beats)
        rows = []
        for n in range(beats + 1):
            banned = {rows[-1]} if rows else set()
            rows.append(rng.choice([c for c in colors if c not in banned]))
        count = flashes.count(counted)
        table = {n: colour for n, colour in enumerate(rows)}
        return Bomb(kind.value, seed, [
            Indicator([(0, flashes[0])], cycle=flashes, once=True),
            TallyTable(counted, rows),
            Unwritten(WireBank(colors, table, targets=1,
                               key=lambda bomb, count=count: count)),
        ])

    if kind is TaskKind.HAYSTACK_3:
        # The theatre with a script. Four steps in strict alternation: a wire, a
        # key, a wire, a key. The keys wear engraved digits, so the hands can
        # find them, and every step out of turn is a boom: a cut while the pad
        # is owed answers to no rule, a press while the wires are owed asks for
        # nothing. The rest of the board still performs, and still means nothing.
        palette = list(COLORS) + list(EXTRA_COLORS)
        colors = rng.sample(palette, 6)
        wire_a, wire_b = rng.sample(colors, 2)
        keys = rng.sample(range(10), 4)
        digit_1, digit_2 = (str(d) for d in rng.sample(keys, 2))
        marks = rng.sample(PLATE_SYMBOLS, 3)
        paint = " ".join(f"[{rng.choice(COLORS)}]" for _ in range(3))
        carve = " ".join(f"[{rng.choice(marks)}]" for _ in range(3))
        strip = Prop(f"STRIP painted {paint}", f"STRIP engraved {carve}", name="strip")
        pad = Keypad(keys, digit_1 + digit_2, only_at=(1, 3))
        note = (f"Cut the {wire_a} wire, then press the key that wears {digit_1},\n"
                f"then cut the {wire_b} wire, then press the key that wears {digit_2}.\n"
                f"In that order, and in no other.")
        return Bomb(kind.value, seed, [
            Unwritten(Indicator([(0, "red")],
                                cycle=[rng.choice(COLORS) for _ in range(7)],
                                display_cycle=[rng.randrange(10) for _ in range(11)])),
            Note(note),
            strip,
            Unwritten(pad),
            Unwritten(WireBank(colors, {(0, "any"): wire_a, (2, "any"): wire_b},
                               targets=2, key=lambda bomb: (bomb.stage, "any"))),
            Seal(lambda pad=pad: pad.opened),
        ])

    if kind is TaskKind.FLASHBACK_3:
        # Five flashes, and this time both colours count. One table over five
        # wires serves two cuts: the first is named by one colour's count, the
        # second by the other's. Five is odd, so the two counts never collide,
        # and whoever watched must keep two numbers alive at once.
        beats = 5
        palette = list(COLORS) + list(EXTRA_COLORS[:1])
        colors = rng.sample(palette, 5)
        first_colour, second_colour, third_colour = rng.sample(COLORS, 3)
        # The two counted colours must land on different tallies, or the row lookup
        # below has nothing to tell apart and its search never terminates.
        while True:
            flashes = _no_repeat(rng, (first_colour, second_colour, third_colour), beats)
            counts = (flashes.count(first_colour), flashes.count(second_colour))
            if counts[0] != counts[1]: break
        while True:
            rows: list[str] = []
            for _ in range(beats + 1):
                banned = {rows[-1]} if rows else set()
                rows.append(rng.choice([c for c in colors if c not in banned]))
            if rows[counts[0]] != rows[counts[1]]:
                break
        table = {n: colour for n, colour in enumerate(rows)}
        return Bomb(kind.value, seed, [
            Indicator([(0, flashes[0])], cycle=flashes, once=True),
            TallyTable(first_colour, rows, second=second_colour),
            Unwritten(WireBank(colors, table, targets=2,
                               key=lambda bomb, counts=counts:
                                   counts[min(bomb.stage, 1)])),
        ])

    if kind is TaskKind.CARVING_1:
        # base-1 with the light swapped for a mark nobody can name. The key to
        # the table lives under Blind's fingers, the table under Mute's eyes,
        # and the mark itself cannot ride the voice: it has to be described,
        # and the description has to be recognised.
        colors = rng.sample(COLORS, 3)
        marks = rng.sample(PLATE_SYMBOLS, 3)
        played = rng.choice(marks)
        table = dict(zip(marks, rng.sample(colors, 3)))
        rows = "\n".join(f"| {mark} | {table[mark]} |" for mark in sorted(marks))
        return Bomb(kind.value, seed, [
            Indicator([(0, "off")]),
            Prop("PLATE engraved [unreadable]", f"PLATE engraved [{played}]", name="plate"),
            Note("Which wire to cut is named by the mark engraved on the plate:\n"
                 "| mark | cut wire color |\n|---|---|\n" + rows),
            Unwritten(WireBank(colors, dict(table), targets=1,
                               key=lambda bomb, played=played: played)),
        ])

    if kind is TaskKind.CARVING_2:
        # The nameless mark moves to the keypad, and the burden of describing
        # moves with it. The keys wear marks only the eyes can read, the manual
        # names the one that must be pressed, and no channel between them will
        # carry the mark itself.
        colors = rng.sample(COLORS, 3)
        marks = rng.sample(PLATE_SYMBOLS, 4)
        keys = rng.sample(range(10), 4)
        slot = rng.randrange(4)
        lights = rng.sample(COLORS, 3)
        table = dict(zip(((0, light) for light in lights), rng.sample(colors, 3)))
        pad = Keypad(keys, str(keys[slot]), raised=False, labels=list(marks))
        return Bomb(kind.value, seed, [
            Indicator([(0, rng.choice(lights))]),
            Note(f"Press the key that wears {marks[slot]} first: any other touch\n"
                 f"on the bomb while it waits is the fuse. Then the light below\n"
                 f"names the cut."),
            Unwritten(pad),
            WireBank(colors, table, targets=1),
        ])

    if kind in (TaskKind.COMBO_LOCK_1, TaskKind.COMBO_LOCK_2, TaskKind.COMBO_LOCK_3):
        # The keypad carries four digits and the table only ever asks for those, so
        # every digit the code needs has a key. Where each one sits is shuffled, so
        # an instruction names the digit and the hands find the place.
        keys = rng.sample(range(10), 4)
        marks = rng.sample(PLATE_SYMBOLS, 3)
        paints = rng.sample(COLORS, 3)
        digits = {(mark, paint): rng.choice(keys) for mark in marks for paint in paints}
        strip = CodeStrip([rng.choice(marks) for _ in range(3)],
                          [rng.choice(paints) for _ in range(3)], digits)
        lights = rng.sample(COLORS, 3)
        colors = rng.sample(COLORS, 3)
        table = dict(zip(((0, light) for light in lights), rng.sample(colors, 3)))
        stages = [(0, rng.choice(lights))]
        return Bomb(kind.value, seed, [
            Indicator(stages), strip,
            # On lock-2 the digits are printed, not raised: the hands find four keys
            # and no way to tell them apart. On lock-3 the keys wear marks instead of
            # digits, and only the manual's table says which mark is which digit.
            Keypad(keys, strip.code(), raised=kind is TaskKind.COMBO_LOCK_1,
                   labels=(rng.sample([m for m in PLATE_SYMBOLS if m not in marks], 4)
                           if kind is TaskKind.COMBO_LOCK_3 else None)),
            WireBank(colors, table, targets=1),
        ])

    if kind is TaskKind.THREE_OF_A_KIND:
        # Three holdings, none of them enough: the marks are felt, the light and the
        # wire colours are seen, and the table that joins them is read.
        plate = _symbol_plate(rng)
        lights = rng.sample(COLORS, 2)
        colors = rng.sample(COLORS, 3)
        # Row by row, the two lights part ways.
        table = {}
        for pattern in PATTERNS:
            for light, target in zip(lights, rng.sample(colors, 2)):
                table[(pattern, light)] = target
        stages = [(0, rng.choice(lights))]
        wires = WireBank(colors, table, targets=1, key=lambda bomb: (plate.pattern(), bomb.light))
        return Bomb(kind.value, seed, [Indicator(stages), plate, wires])
    wires, stages, displays = _wire_bank(rng, kind)
    modules = [Indicator(stages), wires]
    return Bomb(kind.value, seed, modules)


def _no_repeat(rng, palette, beats: int) -> list[str]:
    """A flash sequence that never shows the same colour twice in a row.

    Counting rounds and counting changes then give the same answer, so the one
    ambiguity the roles cannot negotiate away does not arise.
    """
    out: list[str] = []
    for _ in range(beats):
        out.append(rng.choice([c for c in palette if not out or c != out[-1]]))
    return out


def definition(bomb: Bomb) -> dict[str, object]:
    """JSON-ready immutable description, enough to replay a saved rollout."""
    initial = dict(bomb.snapshot())
    initial.update({"stage": 0, "finished": False, "failed": False, "failure_reason": None, "actions": []})
    return {
        "kind": bomb.kind,
        "seed": bomb.seed,
        "modules": [module.name for module in bomb.modules],
        "manual": bomb.manual(),
        "initial_state": initial,
    }
