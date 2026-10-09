import unittest

from sanzaru import agents
from sanzaru.cli.core import parser
from sanzaru.protocol import Call, Channel, Senses
from sanzaru.runner import BenchmarkRunner
from sanzaru.tasks import CORE, PLUS, problem


class Waiting:
    def generate(self, messages):
        return 'wait()'


class InfoModeTests(unittest.TestCase):
    def test_symmetric_channels_and_unchanged_actor(self):
        self.assertEqual(agents.roles('info'), agents.roles('norm'))
        self.assertEqual(agents.actors('info'), ('blind',))
        self.assertTrue(all(s == Senses() for s in agents.senses('info').values()))
        routes = agents.communication_matrix('info')
        for sender in agents.roles('info'):
            for receiver in agents.roles('info'):
                if sender != receiver:
                    self.assertEqual(set(routes[sender, receiver]), {'speech', 'gesture'})
        self.assertFalse(agents.senses('norm')['mute'].speaks)
        self.assertFalse(agents.senses('norm')['deaf'].hears)
        self.assertFalse(agents.senses('norm')['blind'].sees)

    def test_private_views_and_order_match_norm_for_every_instance(self):
        for task in (*CORE, *PLUS):
            for n in range(1, 4):
                backends = {r: Waiting() for r in agents.roles()}
                norm = BenchmarkRunner(problem(task.value, n), backends, simultaneous=False)
                info = BenchmarkRunner(problem(task.value, n), backends,
                                       mode='info', simultaneous=False)
                self.assertEqual(norm.order, info.order)
                for role in agents.roles():
                    self.assertEqual(norm._view(role, 1), info._view(role, 1))

    def test_prompts_and_cli(self):
        self.assertEqual(parser('test').parse_args(['--mode', 'info']).mode, 'info')
        for hints in ('', 'weak', 'strong', 'playbook'):
            for role in agents.roles('info'):
                prompt = agents.build(role, Waiting(), mode='info', hints=hints).system_prompt()
                self.assertNotIn('{{', prompt)
                self.assertIn('All three monkeys can speak', prompt)
                self.assertNotIn('You hear nothing', prompt)
                self.assertNotIn('You cannot speak', prompt)
                self.assertNotIn('only road to the hands', prompt)
                self.assertNotIn('listener who cannot see', prompt)
                self.assertNotIn('watcher who cannot hear', prompt)

    def test_actual_delivery_and_action_authority(self):
        endpoints = agents.build_all({r: Waiting() for r in agents.roles('info')}, mode='info')
        actions = []
        def judge(payload):
            actions.append(payload)
            return True, 'done'
        channel = Channel(endpoints, judge)
        for sender in endpoints:
            for verb, payload in (('speak', 'hello'), ('gesture', '👍')):
                for target in ('', *[r for r in endpoints if r != sender]):
                    for agent in endpoints.values():
                        agent.inbox.clear()
                    call = Call(verb, (payload,), {'to': target} if target else {})
                    delivery = channel.dispatch(sender, call, 1)
                    expected = {target} if target else set(endpoints) - {sender}
                    self.assertTrue(delivery.accepted)
                    self.assertEqual(set(delivery.recipients), expected)
                    for receiver, agent in endpoints.items():
                        self.assertEqual(len(agent.inbox), int(receiver in expected))
                        if receiver in expected:
                            self.assertEqual(agent.inbox[0].payload, payload)
            delivery = channel.dispatch(sender, Call('act', ('cut 1',)), 1)
            self.assertEqual(delivery.accepted, sender == 'blind')
        self.assertEqual(actions, ['cut 1'])

    def test_runner_smoke(self):
        for simultaneous in (True, False):
            runner = BenchmarkRunner(problem('base-1', 1),
                {r: Waiting() for r in agents.roles('info')}, mode='info',
                max_rounds=1, simultaneous=simultaneous)
            self.assertEqual(runner.run().rounds, 1)
