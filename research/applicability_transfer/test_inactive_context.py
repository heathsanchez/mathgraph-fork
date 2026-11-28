"""A disabled learned module must not change ordinary model inputs."""
import unittest
from unittest.mock import patch
import trial

class InactiveAdvice(unittest.TestCase):
    def test_byte_identical_fallback_even_for_poisoned_inactive_advice(self):
        packet={'id':'test','source':'def f(x):\n    return x\n','tests':{'p':'pass'},'graph':{'nodes':[]}}
        ordinary={'status':'FINITE_QUALIFIED','strategy':{'guidance':'Diagnose the evidence.'}}
        poison={'status':'FINITE_QUALIFIED','strategy':{'guidance':'ABSTAIN ALWAYS',
           'guard':{'all':[{'feature':'failed_hits','op':'gt','value':0}]}}}
        with patch.object(trial,'context',return_value={'training':'same'}),patch.object(trial,'load',return_value={'strategies':{'adaptive':ordinary,'guard':poison}}):
            self.assertEqual(trial.proposal_prompt('adaptive',packet),trial.proposal_prompt('guard',packet))
    def test_valid_active_advice_is_still_present(self):
        packet={'id':'test','source':'def f(x):\n    return x\n','tests':{'p':'failure'},'graph':{'nodes':[{'id':'f@1','failed_case_hits':1,'passing_case_hits':0}]}}
        ordinary={'status':'FINITE_QUALIFIED','strategy':{'guidance':'Ordinary'}}
        guard={'status':'FINITE_QUALIFIED','strategy':{'guidance':'ACTIVE_GUIDANCE',
           'guard':{'all':[{'feature':'failed_hits','op':'gt','value':0}]}}}
        with patch.object(trial,'context',return_value={}),patch.object(trial,'load',return_value={'strategies':{'adaptive':ordinary,'guard':guard}}):
            self.assertIn('ACTIVE_GUIDANCE',trial.proposal_prompt('guard',packet))

if __name__=='__main__':unittest.main()
