import copy
import unittest
from core import (check_probe, qualify_method, available, selected_methods, context,
                  stable, legacy, payload, native, choose_candidate)


def packet(failures=1, loop=True):
    source = 'def f(xs):\n    for x in xs:\n        return x\n' if loop else 'def f(xs):\n    return xs\n'
    return {'source': source, 'graph': {'nodes': [{'id': 'f@1', 'failed_case_hits': failures,
                                                  'passing_case_hits': 3}], 'edges': []}}


def method():
    return {'guidance': 'Preserve nearby valid behavior.', 'probe_recipe': 'Test boundaries and the ordinary interior.',
            'guard': {'all': [{'feature': 'failed_hits', 'op': 'gt', 'value': 0},
                              {'feature': 'has_loop', 'op': 'eq', 'value': 1}]}}


class Boundaries(unittest.TestCase):
    def test_probe_rejects_source_and_environment_inspection(self):
        for code in ('import os\ndef test_x():\n assert os.environ\n',
                     'def test_x():\n assert open("test.py").read()\n',
                     'def test_x():\n assert eval("True")\n',
                     'def test_x():\n assert object.__subclasses__()\n'):
            with self.assertRaises(ValueError):
                check_probe(code)
        check_probe('from h11 import Request\ndef test_x():\n assert Request is not None\n')

    def test_missing_or_changed_support_withdraws_only_dependents(self):
        a = qualify_method(method(), packet(), {'a': '1'})
        b = qualify_method(method(), packet(), {'b': '2'})
        self.assertEqual(available([a, b], {'a': 'bad', 'b': '2'}), [b])
        self.assertEqual(available([a, b], {}), [])
        self.assertEqual(available([a, b], {'a': '1', 'b': '2'}), [a, b])

    def test_inactive_guidance_noninterference(self):
        registry = [qualify_method(method(), packet(), {'a': '1'})]
        healthy = packet(failures=0)
        history = [{'failure': 'retained'}]
        empty = context('engine', healthy, [], {'a': '1'}, history)
        self.assertEqual(context('engine', healthy, registry, {'a': '1'}, history), empty)
        self.assertEqual(context('removal', healthy, registry, {'a': '1'}, history), empty)

    def test_removal_preserves_history_and_only_removes_last_active_method(self):
        a = qualify_method(method(), packet(), {'a': '1'})
        altered = method(); altered['guidance'] = 'Check repeated boundary inputs.'
        b = qualify_method(altered, packet(), {'b': '2'})
        ev = {'a': '1', 'b': '2'}
        self.assertEqual(selected_methods('engine', packet(), [a, b], ev), [a, b])
        self.assertEqual(selected_methods('removal', packet(), [a, b], ev), [a])
        self.assertEqual(selected_methods('memory', packet(loop=False), [a, b], ev), [a, b])
        self.assertEqual(selected_methods('cold', packet(), [a, b], ev), [])
        history = [{'actual_failure': True}]
        self.assertEqual(context('removal', packet(), [a], ev, history)['completed_history'], history)

    def test_zero_method_inputs_share_one_draw(self):
        p = packet()
        values = [context(a, p, [], {}, []) for a in ('engine', 'memory', 'removal', 'cold')]
        self.assertEqual(len({stable(x) for x in values}), 1)

    def test_no_match_and_invalid_guard_are_rejected(self):
        self.assertEqual(qualify_method(method(), packet(loop=False), {})['status'], 'REJECTED_METHOD')
        m = method(); m['guard']['all'][0]['value'] = 0; m['guard']['all'][0]['op'] = 'eq'
        self.assertEqual(qualify_method(m, packet(), {})['status'], 'REJECTED_METHOD')
        self.assertEqual(payload({'parsed': []}), {})

    def test_author_success_never_follows_from_test_loss(self):
        baseline = {'status': 'EXECUTED', 'returncode': 1, 'tests': {'a': 'pass', 'b': 'failure'}}
        bad = {'status': 'EXECUTED', 'returncode': 0, 'tests': {'a': 'pass'}}
        self.assertFalse(native.repair_green(baseline, bad))

    def test_failed_second_attempt_does_not_erase_qualified_first(self):
        good = {'author_verified': True, 'probe_verified': False}
        bad = {'author_verified': False, 'probe_verified': True}
        self.assertEqual(choose_candidate(good, bad), (1, good))
        better = {'author_verified': True, 'probe_verified': True}
        self.assertEqual(choose_candidate(good, better), (2, better))


if __name__ == '__main__':
    unittest.main()
