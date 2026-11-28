import unittest
from urllib.parse import unquote
from worker import module,run_one

SOURCE='''def applies(contract):
    return False
def diagnose(observe, seed, contract):
    if not applies(contract):
        return {"trigger": False}
    first = observe(seed)
    return {"trigger": observe(first) != first}
def repair(observe, seed, contract):
    if not applies(contract):
        return None
    return observe(observe(seed))
'''

class ScopeIntervention(unittest.TestCase):
    def test_forcing_scope_removes_internal_gate_and_restores_it(self):
        ns=module(SOURCE);seed='%252F';contract='Decode one layer.'
        ordinary=run_one(ns,unquote,seed,contract,False,'%2F')
        forced=run_one(ns,unquote,seed,contract,False,'%2F',force_scope=True)
        again=run_one(ns,unquote,seed,contract,False,'%2F')
        self.assertEqual(ordinary['output'],'%2F');self.assertEqual(again,ordinary)
        self.assertEqual(forced['status'],'UNSUPPORTED_REJECTION');self.assertEqual(forced['output'],'/')
        self.assertFalse(ns['applies'](contract))

if __name__=='__main__':unittest.main()
