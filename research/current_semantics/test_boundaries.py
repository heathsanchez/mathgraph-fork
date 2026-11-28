import unittest
from base import skill_scope, apply_edits
from worker import observe_equivalent


class Boundaries(unittest.TestCase):
    def test_only_pure_checker_functions_are_admitted(self):
        skill_scope('def equivalent(a, b):\n    return a == b\n')
        for code in ('import os\ndef equivalent(a,b): return True',
                     'def equivalent(a,b): return open("/out/request.json").read()',
                     'def equivalent(a,b=print("effect")): return True',
                     'def equivalent(a,b): return a.__class__',
                     '@print("effect")\ndef equivalent(a,b): return True'):
            with self.assertRaises((ValueError, SyntaxError)):
                skill_scope(code)

    def test_patch_cannot_edit_unadmitted_test_or_overlap(self):
        originals = {'module.py': 'def f(x):\n    return x == 1\n'}
        for edits in ([{'path': 'tests.py', 'replacements': [{'old': 'x', 'new': 'y'}]}],
                      [{'path': 'module.py', 'replacements': [{'old': 'x == 1', 'new': 'x == 2'}, {'old': '== 1', 'new': '== 3'}]}]):
            with self.assertRaises(ValueError): apply_edits(originals, edits)
        result = apply_edits(originals, [{'path': 'module.py', 'replacements': [{'old': 'x == 1', 'new': 'x == 2'}]}])
        self.assertEqual(result['module.py'], 'def f(x):\n    return x == 2\n')

    def test_new_privileged_reference_or_import_is_rejected(self):
        for new in ('return eval("1")', 'import socket\n    return True'):
            with self.assertRaises(ValueError):
                apply_edits({'a.py': 'def f():\n    return True\n'},
                            [{'path': 'a.py', 'replacements': [{'old': 'return True', 'new': new}]}])

    def test_observer_effect_is_detected_without_corrupting_authority(self):
        original = [1, 2]
        def mutating(a, b):
            a.pop()
            return True
        value, error = observe_equivalent(mutating, original, [1, 2])
        self.assertIsNone(value)
        self.assertEqual(error, 'INPUT_MUTATION')
        self.assertEqual(original, [1, 2])
        self.assertEqual(observe_equivalent(lambda a, b: a == b, [1], [1]), (True, None))
        self.assertEqual(observe_equivalent(lambda a, b: 1, 1, 1), (None, 'NON_BOOLEAN_RESULT'))


if __name__ == '__main__': unittest.main()
