import unittest
from worker import execute
from pipeline import new_observations, score
from replicate import fisher


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

    def test_exact_model_sample_tail_at_complete_separation(self):
        self.assertAlmostEqual(fisher(6,0),1/924)

    def test_exact_model_sample_tail_at_five_against_one(self):
        self.assertAlmostEqual(fisher(5,1),37/924)

    def test_equal_or_reversed_success_does_not_support_positive_effect(self):
        self.assertEqual(fisher(0,6),1)
        self.assertGreater(fisher(3,3),0.05)


if __name__ == '__main__':
    unittest.main()
