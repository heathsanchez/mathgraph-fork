import unittest
from worker import execute
from pipeline import new_observations, score


class NativeBoundaries(unittest.TestCase):
    def test_later_acquisition_does_not_get_an_oracle(self):
        source = "def investigate(text, operation):\n    return operation(text + '!')\n"
        row = execute(source, str.upper, ['hello'])[0]
        self.assertEqual(row['output'], 'HELLO!')
        self.assertEqual(row['observations'], [{'input': 'hello!', 'output': 'HELLO!'}])
        self.assertNotIn('expected', row)

    def test_callback_budget_is_enforced(self):
        source = 'def investigate(text, operation):\n    for i in range(65):\n        operation(text)\n    return text\n'
        row = execute(source, str.upper, ['hi'])[0]
        self.assertEqual(row['status'], 'UNKNOWN_NATIVE_EXCEPTION')
        self.assertEqual(len(row['observations']), 64)

    def test_method_removal_runs_ordinary_operation(self):
        row = execute(None, str.upper, ['hello'])[0]
        self.assertEqual(row['output'], 'HELLO')
        self.assertEqual(len(row['observations']), 1)

    def test_duplicate_calls_are_not_new_information(self):
        record={'input':'x','output':'X'}
        self.assertEqual(new_observations([record,record],[record]),[])

    def test_common_oracle_binds_input_identity(self):
        forged={'returncode':0,'rows':[{'input':'different','output':'right','status':'RETURNED','observations':[]}]}
        self.assertFalse(score(forged,[{'input':'original','expected':'right'}])['qualified'])


if __name__ == '__main__':
    unittest.main()
