"""The simulator's contract: what it shows, what it accepts, and when it is over."""

import unittest

from sanzaru.simulator import (
    Unwritten,
    PATTERNS, Action, Bomb, CodeStrip, Indicator, Keypad, Outcome, Reading, SymbolPlate,
    WireBank,
)
from sanzaru.tasks import COLORS, TaskKind, definition, generate_puzzle, view_for


def bare(module):
    """A module as itself, whether or not its manual page was torn out."""
    return module.module if isinstance(module, Unwritten) else module


def wires_of(bomb):
    return next(bare(m) for m in bomb.modules if isinstance(bare(m), WireBank))


def keypad_of(bomb):
    return next((bare(m) for m in bomb.modules
                 if isinstance(bare(m), Keypad)), None)


def solve(bomb, limit=8):
    """Play the bomb the way a perfect team would, whatever it is made of.

    A perfect team also knows when not to act: a moment the manual is silent
    about is spent waiting, and the round passes like any other."""
    def owed(module):
        inner = bare(module)
        if not module.ops:
            return False
        if isinstance(inner, Keypad) and inner.only_at is not None:
            return not inner.opened
        return not module.solved()

    for _ in range(limit):
        candidates = [m for m in bomb.modules if owed(m)]
        if not candidates:
            break
        move = next((mv for m in candidates if (mv := perfect_move(bomb, m))), None)
        if move is None:
            bomb.tick()
            continue
        terminal, _ = bomb.apply(move)
        if terminal:
            break
    return bomb.actions


def perfect_move(bomb, module):
    """The one action that module would accept right now."""
    module = bare(module)
    if isinstance(module, WireBank):
        wanted = module.expected(bomb)
        if wanted is None:
            return None   # the manual is silent right now: the only move is patience
        position = next(
            index for index, color in enumerate(module.colors, 1)
            if color == wanted and index not in module.cut
        )
        return f"cut {position}"
    if isinstance(module, Keypad):
        if module.only_at is not None and bomb.stage != module.only_at[len(module.entered)]:
            return None   # a stage-gated pad that is not owed a press right now
        # One key at a time, found by where the digit it needs happens to sit.
        return f"press {module.slot_of(module.code[len(module.entered)])}"

    raise AssertionError(f"no perfect move known for {module.name}")


class ActionTests(unittest.TestCase):
    def test_parsing_splits_op_from_argument(self):
        self.assertEqual((Action.parse("  CUT 2 ").op, Action.parse("CUT 2").argument), ("cut", "2"))
        self.assertEqual(Action.parse("push left").argument, "left")
        self.assertEqual(Action.parse("wave").argument, "")


class GenerationTests(unittest.TestCase):
    def test_same_seed_builds_the_same_bomb(self):
        for kind in TaskKind:
            with self.subTest(kind=kind):
                a, b = generate_puzzle(kind, 42), generate_puzzle(kind, 42)
                self.assertEqual(a.face(True), b.face(True))
                self.assertEqual(a.manual(), b.manual())

    def test_different_seeds_build_different_bombs(self):
        faces = {generate_puzzle(TaskKind.BASE_1, seed).manual() for seed in range(12)}
        self.assertGreater(len(faces), 1)

    def test_every_task_carries_the_modules_it_needs(self):
        self.assertIsNone(keypad_of(generate_puzzle(TaskKind.BASE_1, 1)))
        self.assertIsNone(keypad_of(generate_puzzle(TaskKind.THREE_OF_A_KIND, 1)))
        self.assertIsNotNone(keypad_of(generate_puzzle(TaskKind.COMBO_LOCK_1, 1)))

    def test_played_stages_target_distinct_wires(self):
        # A destructive cut must never make a later stage unsolvable.
        for seed in range(30):
            bomb = generate_puzzle(TaskKind.SHUFFLE_WIRES_1, seed)
            indicator, wires = bomb.modules[0], wires_of(bomb)
            targets = [wires.table[stage] for stage in indicator.stages]
            self.assertEqual(len(set(targets)), len(targets), f"seed {seed}")


class FaceTests(unittest.TestCase):
    def test_structure_survives_what_perception_removes(self):
        bomb = generate_puzzle(TaskKind.COMBO_LOCK_1, 3)
        seen, unseen = bomb.face(True), bomb.face(False)
        self.assertEqual(len(seen.splitlines()), len(unseen.splitlines()))
        self.assertIn("1:[", unseen)                       # positions are structure
        # A colour is content, so it never appears as a value. Bare substrings would
        # match by accident: "entered" contains "red".
        self.assertNotIn(f"[{bomb.light}]", unseen)
        self.assertIn("DISPLAY [unreadable]", unseen)
        self.assertIn("[3 digits] [entered nothing]", unseen)  # its appetite is structure

    def test_cut_wires_are_visible_to_everyone(self):
        bomb = generate_puzzle(TaskKind.BASE_1, 17)
        solve(bomb, limit=1)
        self.assertIn("CUT", bomb.face(False))

    def test_views_are_routed_by_role(self):
        bomb = generate_puzzle(TaskKind.BASE_1, 3)
        self.assertEqual(view_for(bomb, "mute").body, bomb.manual())
        self.assertEqual(view_for(bomb, "deaf").body, bomb.face(True))
        self.assertEqual(view_for(bomb, "blind").body, bomb.face(False))
        with self.assertRaises(KeyError):
            view_for(bomb, "nobody")


class ProgressionTests(unittest.TestCase):
    def test_every_task_can_be_defused(self):
        for kind in TaskKind:
            for seed in range(6):
                with self.subTest(kind=kind, seed=seed):
                    bomb = generate_puzzle(kind, seed)
                    solve(bomb)
                    self.assertTrue(bomb.finished, bomb.failure_reason)
                    self.assertFalse(bomb.failed)

    def test_the_bomb_changes_after_a_correct_cut(self):
        bomb = generate_puzzle(TaskKind.SHUFFLE_WIRES_1, 17)
        before = bomb.face(True)
        terminal, message = bomb.apply(f"cut {next(i for i, c in enumerate(wires_of(bomb).colors, 1) if c == wires_of(bomb).expected(bomb))}")
        self.assertFalse(terminal)
        self.assertNotEqual(before, bomb.face(True))
        self.assertIn("changed", message)

    def test_the_manual_is_recomputed_not_cached(self):
        bomb = generate_puzzle(TaskKind.COMBO_LOCK_1, 17)
        self.assertEqual(bomb.manual(), bomb.manual())
        solve(bomb, limit=1)
        self.assertIn("|", bomb.manual())

    def test_a_finished_bomb_accepts_nothing_further(self):
        bomb = generate_puzzle(TaskKind.BASE_1, 17)
        solve(bomb)
        terminal, message = bomb.apply("cut 1")
        self.assertTrue(terminal)
        self.assertIn("already resolved", message)


class FailureTests(unittest.TestCase):
    def test_wrong_colour_detonates(self):
        bomb = generate_puzzle(TaskKind.BASE_1, 17)
        wires = wires_of(bomb)
        wrong = next(i for i, c in enumerate(wires.colors, 1) if c != wires.expected(bomb))
        terminal, message = bomb.apply(f"cut {wrong}")
        self.assertTrue(terminal and bomb.failed)
        self.assertIn("expected", message)

    def test_missing_position_detonates(self):
        bomb = generate_puzzle(TaskKind.BASE_1, 17)
        self.assertTrue(bomb.apply("cut 9")[1].endswith("does not exist"))
        self.assertTrue(bomb.failed)

    def test_repeat_cut_detonates(self):
        bomb = generate_puzzle(TaskKind.SHUFFLE_WIRES_1, 17)
        first = bomb.actions or solve(bomb, limit=1)
        terminal, message = bomb.apply(first[0])
        self.assertTrue(terminal and bomb.failed)
        self.assertIn("already cut", message)

    def test_a_later_module_is_locked_until_the_earlier_ones_are_solved(self):
        bomb = generate_puzzle(TaskKind.COMBO_LOCK_1, 17)
        terminal, message = bomb.apply("cut 1")
        self.assertTrue(terminal and bomb.failed)
        self.assertIn("cannot be used yet", message)

    def test_an_unknown_verb_detonates_rather_than_passing_silently(self):
        bomb = generate_puzzle(TaskKind.BASE_1, 17)
        terminal, message = bomb.apply("defuse everything")
        self.assertTrue(terminal and bomb.failed)
        self.assertIn("nothing on the bomb answers", message)

    def test_a_task_without_buttons_has_nothing_to_push(self):
        bomb = generate_puzzle(TaskKind.BASE_1, 17)
        self.assertIn("nothing on the bomb answers", bomb.apply("push left")[1])


class ExtensionTests(unittest.TestCase):
    """A new component is a module, never a change to the judge."""

    def make_switch(self):
        class Switch:
            name, ops = "switch", ("flip",)
            def __init__(self): self.flipped = False
            def readings(self, bomb): return [Reading("SWITCH", "SWITCH [off]", "SWITCH [?]")]
            def manual(self, bomb): return "Flip the switch last."
            def solved(self): return self.flipped
            def apply(self, action, bomb):
                if action.argument != "on":
                    return Outcome.boom(f"flipped {action.argument}, expected on")
                self.flipped = True
                return Outcome("switch flipped")
            def state(self): return {"switch": self.flipped}
        return Switch()

    def test_a_new_module_needs_no_change_to_the_bomb(self):
        bomb = generate_puzzle(TaskKind.BASE_1, 17)
        bomb.modules.append(self.make_switch())

        self.assertIn("SWITCH [off]", bomb.face(True))
        self.assertIn("SWITCH [?]", bomb.face(False))
        self.assertIn("Flip the switch last.", bomb.manual())

        # Locked while the wires are unsolved, routed by its own op once they are.
        self.assertIn("cannot be used yet", bomb.apply("flip on")[1])

        bomb = generate_puzzle(TaskKind.BASE_1, 17)
        bomb.modules.append(self.make_switch())
        solve(bomb, limit=1)
        self.assertFalse(bomb.finished, "the bomb is not done while a module is unsolved")
        terminal, message = bomb.apply("flip on")
        self.assertTrue(terminal and bomb.finished and not bomb.failed)
        self.assertEqual(message, "switch flipped")
        self.assertTrue(bomb.snapshot()["switch"])


class SymbolPlateTests(unittest.TestCase):
    """The plate holds one of three inputs the wire table is read against, and it is
    the only one a monkey reading by touch can supply."""

    def parts(self, seed):
        bomb = generate_puzzle(TaskKind.THREE_OF_A_KIND, seed)
        return bomb, bomb.modules[1], wires_of(bomb)

    def test_the_marks_are_felt_and_never_seen(self):
        bomb, plate, _ = self.parts(11)
        felt = " ".join(f"[{mark}]" for mark in plate.marks)
        self.assertIn(felt, bomb.face(False))
        self.assertNotIn(felt, bomb.face(True))
        self.assertIn("PLATE [engraved]", bomb.face(True))

    def test_the_plate_answers_to_nothing(self):
        bomb, _, _ = self.parts(11)
        self.assertIn("nothing on the bomb answers", bomb.apply("press 1")[1])

    def test_every_shape_appears_across_seeds(self):
        self.assertEqual({self.parts(seed)[1].pattern() for seed in range(60)}, set(PATTERNS))

    def test_the_answer_needs_the_marks_and_the_light_together(self):
        bomb, plate, wires = self.parts(11)
        self.assertEqual(wires.expected(bomb), wires.table[(plate.pattern(), bomb.light)])
        # Same light, a different shape of marks: a different wire.
        others = {wires.table[(shape, bomb.light)] for shape in PATTERNS}
        self.assertGreater(len(others), 1, "the marks would not matter")

    def test_the_manual_is_a_table_of_shapes_against_lights(self):
        bomb, _, _ = self.parts(11)
        manual = bomb.manual()
        self.assertIn("marks \\ light", manual)
        for shape in PATTERNS:
            self.assertIn(shape, manual)
        self.assertIn(bomb.light, manual)

    def test_only_the_wires_can_be_acted_on(self):
        bomb, _, _ = self.parts(11)
        self.assertEqual(bomb.signatures().strip(),
                         'act(op="cut", position=N) — N is a wire position, 1 to 3')


class TraceTests(unittest.TestCase):
    def test_snapshot_carries_every_module_state(self):
        bomb = generate_puzzle(TaskKind.COMBO_LOCK_1, 17)
        state = bomb.snapshot()
        for key in ("kind", "stage", "display", "light", "wires", "finished", "failed", "actions"):
            self.assertIn(key, state)
        self.assertEqual(len(state["wires"]), 3)

    def test_definition_describes_the_bomb_before_anything_happened(self):
        bomb = generate_puzzle(TaskKind.COMBO_LOCK_1, 17)
        solve(bomb)
        spec = definition(bomb)
        self.assertEqual(spec["initial_state"]["actions"], [])
        self.assertEqual(spec["initial_state"]["stage"], 0)
        self.assertFalse(spec["initial_state"]["finished"])
        self.assertEqual(spec["modules"], ["indicator", "strip", "keypad", "wires"])
        self.assertIn("|", spec["manual"])


if __name__ == "__main__":
    unittest.main()


class BaseFamilyTests(unittest.TestCase):
    CUTS = {TaskKind.BASE_1: 1, TaskKind.BASE_3: 3}

    def test_every_level_is_the_same_bomb_but_for_the_cuts(self):
        for kind, cuts in self.CUTS.items():
            for number in range(1, 6):
                bomb = generate_puzzle(kind, number)
                wires = wires_of(bomb)
                self.assertEqual(len(wires.colors), 3, kind.value)
                self.assertEqual(len(wires.table), 3, kind.value)
                self.assertEqual(wires.targets, cuts, kind.value)
                seen_lights = []
                for _ in range(cuts):
                    seen_lights.append(bomb.light)
                    colour = wires.expected(bomb)
                    terminal, note = bomb.apply(f"cut {wires.colors.index(colour) + 1}")
                    self.assertFalse(bomb.failed, f"{kind.value}#{number}: {note}")
                self.assertTrue(bomb.finished and not bomb.failed)
                self.assertEqual(len(set(seen_lights)), cuts)
                self.assertEqual(bomb.face(True).count("[CUT]"), cuts)

class ComboLock2Tests(unittest.TestCase):
    def test_printed_digits_are_for_the_eyes_alone(self):
        for number in range(1, 6):
            bomb = generate_puzzle(TaskKind.COMBO_LOCK_2, number)
            keypad = keypad_of(bomb)
            self.assertIn("KEYPAD 1:[unreadable] 2:[unreadable] 3:[unreadable] 4:[unreadable]", bomb.face(False))
            self.assertIn(f"1:[{keypad.keys[0]}]", bomb.face(True))
            bomb.apply(f"press {keypad.slot_of(keypad.code[0])}")
            self.assertIn("[entered ?]", bomb.face(False))
            self.assertIn(f"[entered {keypad.code[0]}]", bomb.face(True))

    def test_lock_1_digits_stay_raised(self):
        bomb = generate_puzzle(TaskKind.COMBO_LOCK_1, 3)
        keypad = keypad_of(bomb)
        self.assertIn(f"1:[{keypad.keys[0]}]", bomb.face(False))


class ComboLock3Tests(unittest.TestCase):
    def test_keys_wear_marks_and_the_manual_translates(self):
        for number in range(1, 6):
            bomb = generate_puzzle(TaskKind.COMBO_LOCK_3, number)
            keypad = keypad_of(bomb)
            # the eyes get marks, not digits; the hands get neither
            self.assertIn(f"1:[{keypad.labels[0]}]", bomb.face(True))
            self.assertNotIn(f"1:[{keypad.keys[0]}]", bomb.face(True))
            self.assertIn("KEYPAD 1:[unreadable]", bomb.face(False))
            # the manual carries the mark-to-digit table for all four keys
            for mark, digit in zip(keypad.labels, keypad.keys):
                self.assertIn(f"| {mark} | {digit} |", bomb.manual())
            # key marks never collide with the strip's own marks
            strip = bomb.modules[1]
            self.assertFalse(set(keypad.labels) & set(strip.marks))
            # and the lock still opens by position
            for digit in keypad.code:
                terminal, note = bomb.apply(f"press {keypad.slot_of(digit)}")
            self.assertTrue(keypad.opened, note)


class CarvingTests(unittest.TestCase):
    def test_the_mark_is_felt_and_never_seen(self):
        for number in range(1, 6):
            bomb = generate_puzzle(TaskKind.CARVING_1, number)
            self.assertIn("PLATE engraved [unreadable]", bomb.face(True))
            felt = next(l for l in bomb.face(False).splitlines() if l.startswith("PLATE"))
            self.assertNotIn("?", felt)
            self.assertEqual(len(bomb.manual().splitlines()), 6)
            wires = wires_of(bomb)
            colour = wires.expected(bomb)
            terminal, note = bomb.apply(f"cut {wires.colors.index(colour) + 1}")
            self.assertTrue(bomb.finished and not bomb.failed, note)

    def test_the_almighty_holds_the_felt_face_too(self):
        from sanzaru.tasks import view_for
        bomb = generate_puzzle(TaskKind.CARVING_1, 1)
        felt_line = next(l for l in bomb.face(False).splitlines() if l.startswith("PLATE"))
        view = view_for(bomb, "almighty")
        self.assertIn(felt_line, view.body)
        self.assertNotIn("PLATE engraved [unreadable]", view.body)

    def test_level_two_marks_are_for_the_eyes_and_the_pad_goes_first(self):
        from sanzaru.simulator import Keypad
        for number in range(1, 6):
            bomb = generate_puzzle(TaskKind.CARVING_2, number)
            pad = next(bare(m) for m in bomb.modules if isinstance(bare(m), Keypad))
            self.assertIn(f"1:[{pad.labels[0]}]", bomb.face(True))
            self.assertIn("1:[unreadable]", bomb.face(False))
            self.assertIn(pad.labels[pad.keys.index(int(pad.code))], bomb.manual())
            early = generate_puzzle(TaskKind.CARVING_2, number)
            terminal, note = early.apply("cut 1")
            self.assertTrue(early.failed, note)
            wires = wires_of(bomb)
            bomb.apply(f"press {pad.slot_of(pad.code)}")
            terminal, note = bomb.apply(f"cut {wires.colors.index(wires.expected(bomb)) + 1}")
            self.assertTrue(bomb.finished and not bomb.failed, note)


class FlashingLightTests(unittest.TestCase):
    def test_the_light_walks_its_circle_one_step_per_round(self):
        bomb = generate_puzzle(TaskKind.FLASHING_LIGHT_1, 1)
        cycle = bomb.indicator.cycle
        self.assertEqual(len(cycle), 3)
        seen = []
        for _ in range(6):
            bomb.tick()
            seen.append(bomb.light)
        self.assertEqual(seen, cycle * 2)

    def test_doing_nothing_is_also_a_transition(self):
        bomb = generate_puzzle(TaskKind.FLASHING_LIGHT_1, 2)
        before = bomb.face(perceives=True)
        bomb.tick(); bomb.tick()
        self.assertNotEqual(before, bomb.face(perceives=True))

    def test_the_cut_is_judged_by_the_light_of_its_moment(self):
        for number in range(1, 6):
            bomb = generate_puzzle(TaskKind.FLASHING_LIGHT_1, number)
            wires = wires_of(bomb)
            for _ in range(5):
                bomb.tick()
            colour = wires.expected(bomb)
            terminal, note = bomb.apply(f"cut {wires.colors.index(colour) + 1}")
            self.assertTrue(bomb.finished and not bomb.failed, note)

    def test_cutting_at_the_wrong_moment_detonates(self):
        bomb = generate_puzzle(TaskKind.FLASHING_LIGHT_1, 1)
        wires = wires_of(bomb)
        bomb.tick()
        right_now = wires.expected(bomb)
        while wires.expected(bomb) == right_now:
            bomb.tick()
        terminal, note = bomb.apply(f"cut {wires.colors.index(right_now) + 1}")
        self.assertTrue(bomb.failed, note)


class FlashingLight2Tests(unittest.TestCase):
    def test_every_shape_walks_its_circle_and_covers_its_share(self):
        from sanzaru.tasks import FLASH_SHAPE
        for kind, (circle, coverage) in FLASH_SHAPE.items():
            for number in range(1, 6):
                bomb = generate_puzzle(kind, number)
                wires = wires_of(bomb)
                cycle = bomb.indicator.cycle
                self.assertEqual(len(cycle), circle, kind.value)
                self.assertEqual(len(set(cycle)), circle, kind.value)
                ruled = {light for _, light in wires.table}
                self.assertEqual(len(ruled), coverage, kind.value)
                self.assertTrue(ruled <= set(cycle), kind.value)
                targets = list(wires.table.values())
                self.assertEqual(len(set(targets)), len(targets), kind.value)
                self.assertIn("circle of", bomb.manual())

    def test_cutting_during_the_lawless_light_detonates(self):
        bomb = generate_puzzle(TaskKind.FLASHING_LIGHT_2, 1)
        wires = wires_of(bomb)
        while True:
            bomb.tick()
            if wires.expected(bomb) is None:
                break
        terminal, note = bomb.apply("cut 1")
        self.assertTrue(bomb.failed)
        self.assertIn("no rule", note)

    def test_the_ruled_moments_still_solve(self):
        for number in range(1, 6):
            bomb = generate_puzzle(TaskKind.FLASHING_LIGHT_2, number)
            wires = wires_of(bomb)
            while True:
                bomb.tick()
                colour = wires.expected(bomb)
                if colour is not None:
                    break
            terminal, note = bomb.apply(f"cut {wires.colors.index(colour) + 1}")
            self.assertTrue(bomb.finished and not bomb.failed, note)


class TableDisciplineTests(unittest.TestCase):
    def test_two_lights_never_name_the_same_wire(self):
        """Within any row of any table, a different light means a different wire."""
        for kind in TaskKind:
            for number in range(1, 6):
                bomb = generate_puzzle(kind, number)
                wires = wires_of(bomb)
                if any(isinstance(m, Unwritten) and bare(m) is wires
                       for m in bomb.modules):
                    # A silent bank is explained by another module and keyed by its
                    # structures; its discipline is that module's own tests.
                    continue
                rows = {}
                for first, light in wires.table:
                    rows.setdefault(first, {})[light] = wires.table[(first, light)]
                for first, row in rows.items():
                    self.assertEqual(len(set(row.values())),
                                     min(len(row), len(wires.colors)),
                                     f"{kind.value}#{number} row {first}: {row}")


class Base2Tests(unittest.TestCase):
    def test_neither_reading_alone_settles_the_played_cell(self):
        for number in range(1, 6):
            bomb = generate_puzzle(TaskKind.BASE_2, number)
            wires = wires_of(bomb)
            display, light = bomb.display, bomb.light
            displays = {d for d, _ in wires.table}
            lights = {l for _, l in wires.table}
            self.assertEqual((len(displays), len(lights), len(wires.table)), (3, 3, 9))
            column = {wires.table[(d, light)] for d in displays}
            self.assertGreater(len(column), 1, f"#{number}: the display is decoration")
            row = {wires.table[(display, l)] for l in lights}
            self.assertGreater(len(row), 1, f"#{number}: the light is decoration")

    def test_one_cross_read_one_cut(self):
        for number in range(1, 6):
            bomb = generate_puzzle(TaskKind.BASE_2, number)
            wires = wires_of(bomb)
            colour = wires.expected(bomb)
            terminal, note = bomb.apply(f"cut {wires.colors.index(colour) + 1}")
            self.assertTrue(bomb.finished and not bomb.failed, note)


class GridShapeTests(unittest.TestCase):
    def test_the_plus_grids_hold_their_shape_and_never_demand_a_wire_twice(self):
        from sanzaru.tasks import GRID_SHAPE
        for kind, (grid, wire_count, cuts) in GRID_SHAPE.items():
            for number in range(1, 6):
                bomb = generate_puzzle(kind, number)
                wires = wires_of(bomb)
                displays = {d for d, _ in wires.table}
                lights = {l for _, l in wires.table}
                self.assertEqual((len(displays), len(lights)), (grid, grid), kind.value)
                self.assertEqual((len(wires.colors), wires.targets), (wire_count, cuts))
                stages = bomb.modules[0].stages
                targets = [wires.table[stage] for stage in stages]
                self.assertEqual(len(set(targets)), cuts, f"{kind.value}#{number}")
                for d, l in stages:
                    self.assertGreater(len({wires.table[(o, l)] for o in displays}), 1)
                    self.assertGreater(len({wires.table[(d, o)] for o in lights}), 1)

    def test_the_full_walk_defuses(self):
        from sanzaru.tasks import GRID_SHAPE
        for kind, (_, _, cuts) in GRID_SHAPE.items():
            for number in range(1, 6):
                bomb = generate_puzzle(kind, number)
                wires = wires_of(bomb)
                for _ in range(cuts):
                    colour = wires.expected(bomb)
                    terminal, note = bomb.apply(f"cut {wires.colors.index(colour) + 1}")
                    self.assertFalse(bomb.failed, f"{kind.value}#{number}: {note}")
                self.assertTrue(bomb.finished and not bomb.failed)


class StereoTests(unittest.TestCase):
    def test_the_light_alone_never_settles_the_played_cell(self):
        for number in range(1, 6):
            bomb = generate_puzzle(TaskKind.STEREO_1, number)
            wires = wires_of(bomb)
            display, light = bomb.display, bomb.light
            other_display = next(d for d, _ in wires.table if d != display)
            self.assertNotEqual(wires.table[(display, light)],
                                wires.table[(other_display, light)],
                                f"#{number}: the display is decoration")

    def test_one_cross_read_one_cut(self):
        for number in range(1, 6):
            bomb = generate_puzzle(TaskKind.STEREO_1, number)
            wires = wires_of(bomb)
            colour = wires.expected(bomb)
            terminal, note = bomb.apply(f"cut {wires.colors.index(colour) + 1}")
            self.assertTrue(bomb.finished and not bomb.failed, note)


class FlashbackTests(unittest.TestCase):
    BEATS = {TaskKind.FLASHBACK_1: 3, TaskKind.FLASHBACK_2: 5}

    def test_the_light_flashes_its_beats_then_dies_for_good(self):
        for kind, beats in self.BEATS.items():
            for number in range(1, 6):
                bomb = generate_puzzle(kind, number)
                seen = []
                for _ in range(beats + 3):
                    bomb.tick()
                    seen.append(bomb.light)
                self.assertNotIn("dark", seen[:beats], f"{kind.value}#{number}")
                self.assertEqual(seen[beats:], ["dark"] * 3, f"{kind.value}#{number}")
                self.assertTrue(set(seen[:beats]) <= set(COLORS))

    def test_the_right_count_solves_and_neighbours_never_share(self):
        for kind, beats in self.BEATS.items():
            for number in range(1, 6):
                bomb = generate_puzzle(kind, number)
                tally = bomb.modules[1]
                self.assertEqual(len(tally.rows), beats + 1)
                for a, b in zip(tally.rows, tally.rows[1:]):
                    self.assertNotEqual(a, b, f"{kind.value}#{number}: {tally.rows}")
                wires = wires_of(bomb)
                count = bomb.indicator.cycle.count(tally.colour)
                colour = tally.rows[count]
                terminal, note = bomb.apply(f"cut {wires.colors.index(colour) + 1}")
                self.assertTrue(bomb.finished and not bomb.failed,
                                f"{kind.value}#{number}: {note}")

    def test_an_off_by_one_detonates(self):
        for kind in self.BEATS:
            bomb = generate_puzzle(kind, 1)
            tally = bomb.modules[1]
            wires = wires_of(bomb)
            count = bomb.indicator.cycle.count(tally.colour)
            wrong = tally.rows[count - 1] if count else tally.rows[1]
            terminal, note = bomb.apply(f"cut {wires.colors.index(wrong) + 1}")
            self.assertTrue(bomb.failed, note)

    def test_level_one_just_fits_the_window_and_level_two_outlives_it(self):
        from sanzaru.tasks import window_for
        self.assertEqual(self.BEATS[TaskKind.FLASHBACK_1], window_for("flashback-1"))
        self.assertGreater(self.BEATS[TaskKind.FLASHBACK_2], window_for("flashback-2"))


class Flashback3Tests(unittest.TestCase):
    def test_one_table_serves_both_counts_and_the_walk_defuses(self):
        for number in range(1, 6):
            bomb = generate_puzzle(TaskKind.FLASHBACK_3, number)
            tallies = [bare(m) for m in bomb.modules if getattr(bare(m), "rows", None)]
            self.assertEqual(len(tallies), 1)
            tally = tallies[0]
            self.assertTrue(tally.second and tally.second != tally.colour)
            flashes = bomb.indicator.cycle
            self.assertEqual(len(flashes), 5)
            # Three colours now, so the sequence is not confined to the two counted
            # ones; what must hold is that both are present to be told apart, and
            # that no colour repeats, which is what makes the count unambiguous.
            self.assertIn(tally.colour, flashes)
            self.assertIn(tally.second, flashes)
            self.assertFalse(any(a == b for a, b in zip(flashes, flashes[1:])))
            wires = wires_of(bomb)
            self.assertEqual((len(wires.colors), wires.targets), (5, 2))
            first = tally.rows[flashes.count(tally.colour)]
            second = tally.rows[flashes.count(tally.second)]
            self.assertNotEqual(first, second, f"#{number}: both cuts share a wire")
            for colour in (first, second):
                terminal, note = bomb.apply(f"cut {wires.colors.index(colour) + 1}")
                self.assertFalse(bomb.failed, f"#{number}: {note}")
            self.assertTrue(bomb.finished and not bomb.failed)

    def test_the_manual_orders_the_two_cuts_from_one_table(self):
        manual = generate_puzzle(TaskKind.FLASHBACK_3, 1).manual()
        self.assertIn("The first wire to cut", manual)
        self.assertIn("the second wire", manual)
        self.assertIn("same table", manual)
        self.assertEqual(manual.count("| 5 |"), 1)

    def test_neighbouring_counts_never_share_a_wire(self):
        for number in range(1, 6):
            bomb = generate_puzzle(TaskKind.FLASHBACK_3, number)
            tally = next(bare(m) for m in bomb.modules if getattr(bare(m), "rows", None))
            for a, b in zip(tally.rows, tally.rows[1:]):
                self.assertNotEqual(a, b, f"#{number}: {tally.rows}")


class ShuffleWiresTests(unittest.TestCase):
    LEVELS = {TaskKind.SHUFFLE_WIRES_1: (5, 2), TaskKind.SHUFFLE_WIRES_2: (5, 4)}

    def test_every_cut_moves_every_survivor(self):
        for kind, (size, cuts) in self.LEVELS.items():
            for number in range(1, 6):
                bomb = generate_puzzle(kind, number)
                wires = wires_of(bomb)
                self.assertEqual((len(wires.colors), wires.targets), (size, cuts))
                for _ in range(cuts):
                    before = list(wires.colors)
                    colour = wires.expected(bomb)
                    terminal, note = bomb.apply(f"cut {wires.colors.index(colour) + 1}")
                    self.assertFalse(bomb.failed, f"{kind.value}#{number}: {note}")
                    if terminal:
                        break
                    for i, (old, new) in enumerate(zip(before, wires.colors), 1):
                        if i not in wires.cut:
                            self.assertNotEqual(old, new,
                                                f"{kind.value}#{number}: seat {i} kept {old}")
                self.assertTrue(bomb.finished and not bomb.failed)

    def test_a_stale_map_detonates(self):
        for kind in self.LEVELS:
            for number in range(1, 6):
                bomb = generate_puzzle(kind, number)
                wires = wires_of(bomb)
                colour = wires.expected(bomb)
                bomb.apply(f"cut {wires.colors.index(colour) + 1}")
                bomb.tick()
                next_colour = wires.expected(bomb)
                stale = generate_puzzle(kind, number)
                stale_pos = wires_of(stale).colors.index(next_colour) + 1
                self.assertNotEqual(wires.colors[stale_pos - 1], next_colour)


class ShuffleWires3Tests(unittest.TestCase):
    def test_the_grid_holds_and_every_cut_still_moves_every_survivor(self):
        for number in range(1, 6):
            bomb = generate_puzzle(TaskKind.SHUFFLE_WIRES_3, number)
            wires = wires_of(bomb)
            displays = {d for d, _ in wires.table}
            lights = {l for _, l in wires.table}
            self.assertEqual((len(displays), len(lights), len(wires.table)), (5, 5, 25))
            self.assertEqual((len(wires.colors), wires.targets), (5, 4))
            stages = bomb.modules[0].stages
            targets = [wires.table[stage] for stage in stages]
            self.assertEqual(len(set(targets)), 4, f"#{number}")
            for d, l in stages:
                self.assertGreater(len({wires.table[(o, l)] for o in displays}), 1)
                self.assertGreater(len({wires.table[(d, o)] for o in lights}), 1)
            for _ in range(4):
                before = list(wires.colors)
                colour = wires.expected(bomb)
                terminal, note = bomb.apply(f"cut {wires.colors.index(colour) + 1}")
                self.assertFalse(bomb.failed, f"#{number}: {note}")
                if terminal:
                    break
                for i, (old, new) in enumerate(zip(before, wires.colors), 1):
                    if i not in wires.cut:
                        self.assertNotEqual(old, new, f"#{number}: seat {i} kept {old}")
            self.assertTrue(bomb.finished and not bomb.failed)


class BaitTests(unittest.TestCase):
    def test_the_offer_is_printed_for_eyes_only(self):
        bomb = generate_puzzle(TaskKind.BAIT_1, 1)
        self.assertIn("BUTTON [large] [PUSH TO DEFUSE]", bomb.face(True))
        self.assertIn("BUTTON [large] [smooth]", bomb.face(False))
        self.assertIn('act(op="push")', bomb.signatures())

    def test_only_the_manual_calls_it_bait(self):
        for number in range(1, 6):
            manual = generate_puzzle(TaskKind.BAIT_1, number).manual()
            self.assertIn("bait", manual)
            self.assertIn("the fuse", manual)

    def test_level_two_puts_the_offer_under_the_fingers(self):
        bomb = generate_puzzle(TaskKind.BAIT_2, 1)
        self.assertIn("BUTTON embossed [PUSH TO DEFUSE]", bomb.face(False))
        self.assertNotIn("smooth", bomb.face(False))

    def test_both_levels_read_from_a_full_table(self):
        for kind in (TaskKind.BAIT_1, TaskKind.BAIT_2):
            for number in range(1, 6):
                wires = wires_of(generate_puzzle(kind, number))
                self.assertEqual(len(wires.table), 3, f"{kind.value}#{number}")

    def test_level_three_forbids_the_cut_under_the_fingers_and_the_cut_still_solves(self):
        for number in range(1, 6):
            bomb = generate_puzzle(TaskKind.BAIT_3, number)
            self.assertIn("SIGN embossed [DO NOT CUT ANY WIRE]", bomb.face(False))
            self.assertIn("SIGN embossed [DO NOT CUT ANY WIRE]", bomb.face(True))
            manual = bomb.manual()
            self.assertIn("always true", manual)
            self.assertIn("believe this page", manual)
            wires = wires_of(bomb)
            colour = wires.expected(bomb)
            terminal, note = bomb.apply(f"cut {wires.colors.index(colour) + 1}")
            self.assertTrue(bomb.finished and not bomb.failed, note)

    def test_taking_the_bait_detonates_and_the_cut_still_solves(self):
        bomb = generate_puzzle(TaskKind.BAIT_1, 1)
        terminal, note = bomb.apply("push")
        self.assertTrue(bomb.failed)
        clean = generate_puzzle(TaskKind.BAIT_1, 1)
        wires = wires_of(clean)
        colour = wires.expected(clean)
        terminal, note = clean.apply(f"cut {wires.colors.index(colour) + 1}")
        self.assertTrue(clean.finished and not clean.failed, note)


class HaystackTests(unittest.TestCase):
    def test_the_manual_is_one_line(self):
        for number in range(1, 6):
            manual = generate_puzzle(TaskKind.HAYSTACK_1, number).manual()
            self.assertEqual(len(manual.splitlines()), 1, manual)
            self.assertTrue(manual.startswith("Cut the "), manual)

    def test_one_cut_solves_and_the_target_is_unique(self):
        for number in range(1, 6):
            bomb = generate_puzzle(TaskKind.HAYSTACK_1, number)
            wires = wires_of(bomb)
            target = bomb.manual().removeprefix("Cut the ").removesuffix(" wire.")
            self.assertEqual(wires.colors.count(target), 1)
            terminal, note = bomb.apply(f"cut {wires.colors.index(target) + 1}")
            self.assertTrue(bomb.finished and not bomb.failed, note)

    def test_level_two_wants_its_three_wires_in_order(self):
        for number in range(1, 6):
            bomb = generate_puzzle(TaskKind.HAYSTACK_2, number)
            wires = wires_of(bomb)
            words = bomb.manual().replace(",", "").replace("\n", " ").split()
            targets = [words[i + 1] for i, w in enumerate(words) if w == "the"]
            self.assertEqual(len(set(targets)), 3)
            # the second wire refuses to go first
            early = generate_puzzle(TaskKind.HAYSTACK_2, number)
            terminal, note = early.apply(f"cut {wires_of(early).colors.index(targets[1]) + 1}")
            self.assertTrue(early.failed, note)
            for target in targets:
                terminal, note = bomb.apply(f"cut {wires.colors.index(target) + 1}")
                self.assertFalse(bomb.failed, f"#{number}: {note}")
            self.assertTrue(bomb.finished and not bomb.failed)

    def test_the_performance_never_repeats_within_budget(self):
        bomb = generate_puzzle(TaskKind.HAYSTACK_1, 1)
        seen = []
        for _ in range(8):
            bomb.tick()
            seen.append((bomb.display, bomb.light))
        # not a short loop: no period of 1, 2 or 3 fits what was shown
        for period in (1, 2, 3):
            self.assertTrue(any(seen[i] != seen[i - period]
                                for i in range(period, len(seen))), f"period {period}")

    def test_level_three_alternates_wire_and_key_and_punishes_any_other_order(self):
        from sanzaru.simulator import Keypad
        def pad_of(bomb):
            return next(bare(m) for m in bomb.modules if isinstance(bare(m), Keypad))
        for number in range(1, 6):
            bomb = generate_puzzle(TaskKind.HAYSTACK_3, number)
            wires, pad = wires_of(bomb), pad_of(bomb)
            self.assertNotIn("keypad locks", bomb.manual())
            steps = [("cut", wires.table[(0, "any")]), ("press", pad.code[0]),
                     ("cut", wires.table[(2, "any")]), ("press", pad.code[1])]
            for op, arg in steps:
                n = (wires.colors.index(arg) + 1) if op == "cut" else pad.slot_of(arg)
                terminal, note = bomb.apply(f"{op} {n}")
                self.assertFalse(bomb.failed, f"#{number}: {note}")
            self.assertTrue(bomb.finished and not bomb.failed)
        early_press = generate_puzzle(TaskKind.HAYSTACK_3, 1)
        pad = pad_of(early_press)
        terminal, note = early_press.apply(f"press {pad.slot_of(pad.code[0])}")
        self.assertTrue(early_press.failed, note)
        early_cut = generate_puzzle(TaskKind.HAYSTACK_3, 1)
        wires = wires_of(early_cut)
        early_cut.apply(f"cut {wires.colors.index(wires.table[(0, 'any')]) + 1}")
        terminal, note = early_cut.apply(f"cut {wires.colors.index(wires.table[(2, 'any')]) + 1}")
        self.assertTrue(early_cut.failed, note)

    def test_the_props_answer_to_nothing(self):
        bomb = generate_puzzle(TaskKind.HAYSTACK_1, 1)
        terminal, note = bomb.apply("press 1")
        self.assertTrue(bomb.failed, note)


class RetirementTests(unittest.TestCase):
    def test_the_retired_stay_runnable(self):
        from sanzaru.tasks import RETIRED
        self.assertIn(TaskKind.THREE_OF_A_KIND, RETIRED)
        bomb = generate_puzzle(TaskKind.THREE_OF_A_KIND, 1)
        solve(bomb)
        self.assertTrue(bomb.finished and not bomb.failed)
