import unittest
from core import validate_program,choose_context,verified_rejection

class CriticBoundary(unittest.TestCase):
    def test_inactive_program_has_no_effect(self):
        baseline={'task':'ordinary','evidence':[1,2]}
        for code in ('ABSTAIN ALWAYS','arbitrary invalid source',''):
            self.assertIs(choose_context(baseline,code,False),baseline)
        self.assertNotEqual(choose_context(baseline,'active',True),baseline)
    def test_terminal_rejection_requires_replay_and_scope(self):
        r={'status':'OBSERVED_REJECTION','witness':{'seed':'x','first':'a','second':'b','scope_supported':True,'replayed':True}}
        self.assertTrue(verified_rejection(r))
        for key,value in [('scope_supported',False),('replayed',False),('second','a')]:
            self.assertFalse(verified_rejection({**r,'witness':{**r['witness'],key:value}}))
    def test_program_grammar_rejects_host_access(self):
        valid='def applies(contract):\n    return False\ndef diagnose(observe, seed, contract):\n    return {"trigger": False}\ndef repair(observe, seed, contract):\n    return None\n'
        self.assertEqual(len(validate_program(valid)),64)
        for source in ('import os\n'+valid,valid.replace('return False','return open("secret")'),valid.replace('return None','return observe.__globals__')):
            with self.assertRaises(ValueError):validate_program(source)

if __name__=='__main__':unittest.main()
