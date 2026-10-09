"""The benchmark's contract: who reaches whom, what a round is, and what is recorded."""

import unittest
from pathlib import Path
import tempfile

from sanzaru import agents, prompts
from sanzaru.agents import Agent, roles
from sanzaru.backends import OllamaBackend, OpenAICompatibleBackend
from sanzaru.protocol import (
    GESTURES, MASK, Senses, extract_calls, matrix,
    payload_of, strip_reasoning,
)
from sanzaru.runner import MAX_REPAIRS, TRACE_VERSION, BenchmarkRunner
from sanzaru.tasks import TaskKind, generate_puzzle


def block(*calls):
    return "```\n" + "\n".join(calls) + "\n```"


class Waiting:
    def generate(self, messages): return block("wait()")


class Fixed:
    def __init__(self, output): self.output = output
    def generate(self, messages): return self.output


class Scripted:
    """Plays back one output per call, repeating the last one forever."""
    def __init__(self, *outputs): self.outputs, self.n = outputs, 0
    def generate(self, messages):
        output = self.outputs[min(self.n, len(self.outputs) - 1)]
        self.n += 1
        return output


def run(backends, kind=TaskKind.BASE_1, seed=9, max_rounds=2):
    return BenchmarkRunner(generate_puzzle(kind, seed), backends, max_rounds).run()


def only(role, backend):
    return {name: (backend if name == role else Waiting()) for name in roles()}


class CallParsingTests(unittest.TestCase):
    def test_functions_are_read_never_executed(self):
        parsed = extract_calls(block(
            'speak(text="the light is green")', 'gesture(symbols=["✊"])', 'act(op="cut", position=2)'
        ), "functions")
        self.assertEqual([c.verb for c in parsed], ["speak", "gesture", "act"])
        self.assertEqual(payload_of(parsed[2]), "cut 2")

        hostile = block("import os", "x = act(op='cut', position=1)", "os.system('rm -rf /')")
        self.assertEqual(extract_calls(hostile, "functions"), [])

    def test_act_accepts_keywords_or_positions(self):
        for text in ('act(op="push", direction="left")', 'act("push", "left")', 'act("push left")'):
            with self.subTest(text=text):
                self.assertEqual(payload_of(extract_calls(block(text), "functions")[0]), "push left")

    def test_a_broken_line_does_not_discard_its_neighbours(self):
        parsed = extract_calls(block("gesture(✊)", 'act(op="cut", position=3)'), "functions")
        self.assertEqual([c.verb for c in parsed], ["act"])

    def test_reasoning_is_private_even_when_it_contains_a_call(self):
        self.assertEqual(extract_calls("<think>speak(text='leak')</think>", "functions"), [])
        # An unclosed block means the budget ran out mid-thought: all of it is private.
        self.assertEqual(extract_calls("<think>speak(text='leak') and on and on", "functions"), [])
        self.assertEqual(strip_reasoning("<think>x</think>after").strip(), "after")

    def test_tags_are_an_alternative_surface_for_the_same_calls(self):
        parsed = extract_calls("<SAY>hello</SAY> <ACT>cut 2</ACT> <SAY bad>no</SAY>", "tags")
        self.assertEqual([(c.verb, payload_of(c)) for c in parsed], [("speak", "hello"), ("act", "cut 2")])


class SkillTableTests(unittest.TestCase):
    def test_the_communication_matrix_is_derived_from_senses(self):
        # Golden. If a sense flips, this names the exact edge that changed.
        self.assertEqual(
            {pair: list(through) for pair, through in agents.communication_matrix().items()},
            {
                ("deaf", "mute"): ["speech", "gesture"],
                ("deaf", "blind"): ["speech"],
                ("mute", "deaf"): ["gesture"],
                ("mute", "blind"): [],
                ("blind", "deaf"): ["gesture"],
                ("blind", "mute"): ["speech", "gesture"],
            },
        )

    def test_flipping_one_sense_changes_only_its_own_edges(self):
        table = {"deaf": Senses(hears=False), "mute": Senses(speaks=False), "blind": Senses(sees=False)}
        before = matrix(table)
        table["blind"] = Senses()
        changed = {pair for pair, through in matrix(table).items() if before[pair] != through}
        self.assertEqual(changed, {("deaf", "blind"), ("mute", "blind")})

    def test_the_routing_prose_is_generated_from_the_same_table(self):
        self.assertIn("When you speak, Mute and Blind receive it.",
                      agents.protocol_context("functions", "deaf")["my_routes"])
        self.assertIn("You cannot speak.", agents.protocol_context("functions", "mute")["my_routes"])
        self.assertIn("You are the hands.",
                      agents.protocol_context("functions", "blind", "act(...)")["my_actions"])

    def test_only_blind_may_act(self):
        self.assertEqual(agents.actors(), ("blind",))


class PerceptionTests(unittest.TestCase):
    """What leaves a monkey is one event; what arrives depends on who is receiving."""

    def inboxes(self, result, turn=2):
        return {e["role"]: [m["text"] for m in e["inbox"]] for e in result.transcript if e["turn"] == turn}

    def test_a_gesture_in_speech_is_seen_by_the_sighted_and_blanked_for_the_rest(self):
        result = run(only("deaf", Fixed(block('speak(text="\U0001f44d is one")'))))
        seen = self.inboxes(result)
        self.assertIn("Deaf says: \U0001f44d is one", seen["mute"])
        self.assertIn(f"Deaf says: {MASK} is one", seen["blind"])

    def test_a_gesture_in_speech_reaches_a_watcher_who_cannot_hear(self):
        result = run(only("blind", Fixed(block('speak(text="the mark is \u270c shaped")'))))
        seen = self.inboxes(result)
        self.assertIn("Blind says: the mark is \u270c shaped", seen["mute"])
        self.assertIn("Blind gestures: [\u270c]", seen["deaf"])

    def test_a_named_message_reaches_its_receiver_and_nobody_else(self):
        result = run(only("blind", Fixed(block('speak(to="mute", text="the mark is \u270c shaped")'))))
        seen = self.inboxes(result)
        self.assertIn("Blind says to Mute: the mark is \u270c shaped", seen["mute"])
        # Deaf would have seen the \u270c held up, had this been said to the room.
        self.assertEqual([t for t in seen["deaf"] if "Blind" in t], [])

    def test_naming_yourself_is_malformed(self):
        result = run(only("blind", Fixed(block('speak(to="blind", text="hello me")'))))
        self.assertGreater(result.repairs, 0)

    def test_naming_someone_who_does_not_exist_is_malformed(self):
        result = run(only("blind", Fixed(block('speak(to="bob", text="hello")'))))
        self.assertGreater(result.repairs, 0)

    def test_speech_never_reaches_a_monkey_who_cannot_hear(self):
        result = run(only("blind", Fixed(block('speak(text="I am ready")'))))
        arrived = [m for e in result.transcript if e["role"] == "deaf" for m in e["inbox"]]
        self.assertEqual([m for m in arrived if m["sender"] == "blind"], [])

    def test_a_gesture_reaches_the_unsighted_as_blanks(self):
        result = run(only("mute", Fixed(block('gesture(symbols=["☝", "✌"])'))))
        seen = self.inboxes(result)
        self.assertIn("Mute gestures: [☝ ✌]", seen["deaf"])
        self.assertIn(f"Mute gestures: [{MASK} {MASK}]", seen["blind"])




class ChannelTests(unittest.TestCase):
    def test_a_call_the_world_forbids_is_dropped_without_a_rewrite(self):
        result = run(only("mute", Fixed(block('speak(text="cut position one")'))))
        turn = result.transcript[1]
        self.assertEqual(turn["attempts"], [], "a mute monkey cannot be asked to speak more carefully")
        self.assertEqual([(c["kind"], c["accepted"]) for c in turn["calls"]], [("speak", False)])
        self.assertEqual(result.repairs, 0)

    def test_the_sender_is_told_next_round_that_nothing_landed(self):
        result = run(only("mute", Fixed(block('speak(text="cut position one")'))))
        notices = [m["text"] for e in result.transcript
                   if e["role"] == "mute" and e["turn"] == 2 for m in e["inbox"]]
        self.assertIn("System: You cannot speak, so your speak reached nobody.", notices)

    def test_only_the_monkey_who_can_reach_the_bomb_is_judged(self):
        result = run(only("deaf", Fixed(block('act(op="cut", position=1)'))))
        call = result.transcript[0]["calls"][0]
        self.assertFalse(call["accepted"])
        self.assertEqual(call["reason"], "You cannot reach the bomb")
        self.assertEqual(result.actions, [])

    def test_a_malformed_gesture_is_handed_back_to_be_rewritten(self):
        mute = Scripted(block('gesture(symbols=["1"])'), block('gesture(symbols=["☝"])'))
        turn = run(only("mute", mute)).transcript[1]
        self.assertEqual(len(turn["attempts"]), 1)
        self.assertIn("gesture alphabet", turn["attempts"][0]["problems"][0])
        self.assertTrue(turn["calls"][0]["accepted"])

    def test_a_monkey_that_never_writes_a_legal_call_spends_the_turn_waiting(self):
        result = run(only("mute", Fixed(block('gesture(symbols=["1"])'))), max_rounds=3)
        self.assertFalse(result.success)
        self.assertEqual(result.reason, "round limit reached")
        turn = next(e for e in result.transcript if e["role"] == "mute")
        self.assertEqual(len(turn["attempts"]), MAX_REPAIRS + 1)
        self.assertEqual(turn["calls"][0]["kind"], "wait")


class RoundTests(unittest.TestCase):
    def test_nothing_sent_in_a_round_is_visible_inside_that_round(self):
        result = run({role: Fixed(block(f'speak(text="I am {role}")')) for role in roles()})
        first = [e for e in result.transcript if e["turn"] == 1]
        self.assertTrue(all(e["inbox"] == [] for e in first), "the barrier leaked")
        second = {e["role"]: sorted(m["sender"] for m in e["inbox"] if m["sender"] != "system")
                  for e in result.transcript if e["turn"] == 2}
        self.assertEqual(second["mute"], ["blind", "deaf"])

    def test_a_round_numbers_every_monkey_the_same(self):
        result = run({role: Waiting() for role in roles()})
        self.assertEqual([(e["turn"], e["role"]) for e in result.transcript],
                         [(1, "deaf"), (1, "mute"), (1, "blind"), (2, "deaf"), (2, "mute"), (2, "blind")])

    def test_producing_no_call_is_a_deliberate_silence(self):
        result = run(only("blind", Fixed("I have nothing to say")), max_rounds=1)
        self.assertEqual([c["kind"] for c in result.transcript[2]["calls"]], ["wait"])
        self.assertEqual(result.silences, 1)

    def test_the_run_ends_the_moment_the_bomb_resolves(self):
        bomb = generate_puzzle(TaskKind.BASE_1, 9)
        wires = bomb.modules[1]
        right = next(i for i, c in enumerate(wires.colors, 1) if c == wires.expected(bomb))
        result = BenchmarkRunner(bomb, only("blind", Fixed(block(f'act(op="cut", position={right})'))), 5).run()
        self.assertTrue(result.success)
        self.assertEqual(result.rounds, 1)

    def test_a_wrong_cut_ends_the_run_as_a_failure(self):
        bomb = generate_puzzle(TaskKind.BASE_1, 9)
        wires = bomb.modules[1]
        wrong = next(i for i, c in enumerate(wires.colors, 1) if c != wires.expected(bomb))
        result = BenchmarkRunner(bomb, only("blind", Fixed(block(f'act(op="cut", position={wrong})'))), 5).run()
        self.assertFalse(result.success)
        self.assertIn("expected", result.reason)


class HistoryTests(unittest.TestCase):
    def test_reasoning_and_rejected_drafts_stay_out_of_the_context(self):
        draft = "<think>" + "thinking. " * 300 + "</think>\n" + block('gesture(symbols=["1"])')
        good = "<think>" + "more thinking. " * 300 + "</think>\n" + block('gesture(symbols=["☝"])')
        runner = BenchmarkRunner(generate_puzzle(TaskKind.BASE_1, 9), only("mute", Scripted(draft, good)), 1)
        result = runner.run()
        agent = runner.agents["mute"]
        # The record is complete: the raw output, reasoning and rejected draft included.
        self.assertEqual(len(agent.record), 1)
        self.assertEqual(agent.record[0].output, good)
        self.assertEqual(len(agent.record[0].drafts), 1)

        # What the API is shown is the same conversation with the reasoning removed.
        messages = agent.api_messages()
        self.assertEqual([m["role"] for m in messages], ["user", "assistant"])
        self.assertEqual(messages[1]["content"], block('gesture(symbols=["☝"])'))
        self.assertEqual(result.transcript[1]["output"], good, "the trace still keeps the raw output")

    def test_the_next_round_repeats_this_round_prefix_exactly(self):
        runner = BenchmarkRunner(generate_puzzle(TaskKind.BASE_1, 9), {r: Waiting() for r in roles()}, 2)
        result = runner.run()
        first, second = (e["messages"] for e in result.transcript if e["role"] == "deaf")
        self.assertEqual(second[: len(first)], first, "a changed prefix invalidates the cache behind it")

    def test_a_silent_round_is_written_down_as_the_wait_it_amounted_to(self):
        runner = BenchmarkRunner(generate_puzzle(TaskKind.BASE_1, 9),
                                 only("blind", Fixed("I am thinking out loud and never call anything")), 2)
        runner.run()
        agent = runner.agents["blind"]
        self.assertIn("thinking out loud", agent.record[0].output, "the record keeps the raw text")
        self.assertEqual(agent.api_messages()[1]["content"], block("wait()"))

    def test_the_trace_records_what_was_actually_sent(self):
        result = run({role: Waiting() for role in roles()}, max_rounds=1)
        messages = result.transcript[0]["messages"]
        self.assertEqual([m["role"] for m in messages], ["system", "user"])
        self.assertEqual(messages[1]["content"], result.transcript[0]["observation"])


class PromptTests(unittest.TestCase):
    def test_every_monkey_is_given_the_whole_rulebook(self):
        result = run({role: Waiting() for role in roles()}, max_rounds=1)
        for event in result.transcript:
            rules = event["rules"]
            for heading in ("# Game rules", "## The room", "## The three monkeys",
                            "## Speech", "## Gestures", "## Turns", "## Calls",
                            "## Your channels", "## Your reach"):
                self.assertIn(heading, rules)
            self.assertIn(f"# Your role: {event['role'].upper()}", rules)
            for gesture in GESTURES:
                self.assertIn(gesture, rules)

    def test_an_unfilled_placeholder_never_reaches_a_model(self):
        with self.assertRaises(KeyError):
            prompts.render("mute", gestures="only one of four")


class RegistryTests(unittest.TestCase):
    def test_a_new_role_needs_no_change_to_the_runner(self):
        class Observer(Agent):
            role, order = "observer", 99
            senses = Senses(hears=False, sees=False)

        agents.register(Observer)
        try:
            self.assertEqual(roles()[-1], "observer")
            self.assertIn("When you speak, Mute and Blind receive it.",
                          agents.protocol_context("functions", "observer")["my_routes"])
            self.assertIsInstance(agents.build("observer", Waiting()), Observer)
        finally:
            agents.registry._REGISTRY.pop("observer")
        self.assertNotIn("observer", roles())

    def test_a_missing_backend_is_refused_up_front(self):
        with self.assertRaises(ValueError):
            BenchmarkRunner(generate_puzzle(TaskKind.BASE_1, 1), {"deaf": Waiting()})


class BackendTests(unittest.TestCase):
    def test_defaults_are_bounded_and_deterministic(self):
        api = OpenAICompatibleBackend("model")
        self.assertEqual((api.max_tokens, api.temperature, api.extra_body), (256, 0.0, {}))
        self.assertFalse(OllamaBackend("model").think)




class WindowTests(unittest.TestCase):
    def test_flashback_owns_a_three_round_memory(self):
        from sanzaru.tasks import window_for
        self.assertEqual(window_for("flashback-1"), 3)
        self.assertEqual(window_for("base-1"), 0)

    def test_old_rounds_fall_out_of_the_context(self):
        result = None
        runner = BenchmarkRunner(generate_puzzle("flashback-1", 1),
                                 {role: Fixed(block("wait()")) for role in agents.roles()},
                                 max_rounds=6, window=3)
        runner.run()
        deaf = runner.agents["deaf"]
        history = deaf.api_messages()
        self.assertEqual(len(history), 6)          # three kept rounds, two messages each
        self.assertIn("TURN 4", history[0]["content"])
        self.assertNotIn("TURN 1", " ".join(m["content"] for m in history))
        self.assertIn("Only your last 3 turns stay with you", deaf.record[-1].prompt)

    def test_an_unwindowed_agent_keeps_everything(self):
        runner = BenchmarkRunner(generate_puzzle("base-1", 1),
                                 {role: Fixed(block("wait()")) for role in agents.roles()},
                                 max_rounds=4)
        runner.run()
        deaf = runner.agents["deaf"]
        self.assertEqual(len(deaf.api_messages()), 8)
        self.assertNotIn("stay with you", deaf.record[-1].prompt)


class CountdownTests(unittest.TestCase):
    def test_the_timer_reaches_only_the_eyes_and_only_in_the_endgame(self):
        from sanzaru.tasks import countdown_for
        self.assertEqual(countdown_for("bait-3"), 0)
        self.assertEqual(countdown_for("base-1"), 0)
        runner = BenchmarkRunner(generate_puzzle(TaskKind.BAIT_3, 1),
                                 {r: Waiting() for r in roles()},
                                 max_rounds=5, countdown=3)
        runner.run()
        for event in runner.transcript:
            timed = "TIMER [" in event["private"]
            remaining = 5 - event["turn"] + 1
            if event["role"] == "deaf" and remaining <= 3:
                self.assertTrue(timed, f"round {event['turn']}: deaf missed the timer")
                self.assertIn(f"TIMER [{remaining} round", event["private"])
            else:
                self.assertFalse(timed, f"round {event['turn']} {event['role']} saw a timer")

    def test_a_task_without_a_countdown_never_shows_one(self):
        runner = BenchmarkRunner(generate_puzzle(TaskKind.BASE_1, 1),
                                 {r: Waiting() for r in roles()}, max_rounds=4)
        runner.run()
        for event in runner.transcript:
            self.assertNotIn("TIMER [", event["private"])
