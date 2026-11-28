"""Verifier boundaries and guard withdrawal, using independent expectations."""
import unittest
from trial import patch,validate_guard,holds,features,receipt_view
from native import admit_red_green,repair_green

class ScopeTests(unittest.TestCase):
    def test_exact_multiple_edits(self):
        s='a = 1\nb = 2\n'
        self.assertEqual(patch(s,[{'old':'a = 1','new':'a = 3'},{'old':'b = 2','new':'b = 4'}]),'a = 3\nb = 4\n')
    def test_ambiguous_and_overlapping_rejected(self):
        for source,edits in [('x=1\nx=1\n',[{'old':'x=1','new':'x=2'}]),('abc=123\n',[{'old':'abc=123','new':'abc=4'},{'old':'123','new':'5'}])]:
            with self.assertRaises(ValueError):patch(source,edits)
    def test_introspection_and_import_rejected(self):
        for replacement in ('x=eval("1")','import socket\nx=2','x=globals()'):
            with self.assertRaises(ValueError):patch('x=1\n',[{'old':'x=1','new':replacement}])
    def test_unchanged_rejected(self):
        with self.assertRaises(ValueError):patch('x=1\n',[{'old':'x=1','new':'x=1'}])
    def test_guard_cannot_trigger_without_failure(self):
        g={'all':[{'feature':'failed_hits','op':'gt','value':0},{'feature':'has_loop','op':'eq','value':1}]}
        for failed in range(10):
            for loop in (0,1):self.assertEqual(holds(g,{'failed_hits':failed,'has_loop':loop}),failed>0 and loop==1)
        for malformed in ({'all':[]},{'all':[{'feature':'__import__','op':'eq','value':1}]},{'all':[{'feature':'failed_hits','op':'eq','value':0}]}):
            with self.assertRaises(ValueError):validate_guard(malformed)
    def test_false_green_and_changed_authority_rejected(self):
        base={'status':'EXECUTED','returncode':1,'tests':{'a':'pass','b':'pass','c':'pass','d':'failure'}}
        fixed={'status':'EXECUTED','returncode':0,'tests':{k:'pass' for k in base['tests']}}
        self.assertTrue(admit_red_green(base,fixed));self.assertTrue(repair_green(base,fixed))
        for bad in ({**fixed,'tests':{'a':'pass'}},{**fixed,'tests':{**fixed['tests'],'a':'skipped'}},{**fixed,'returncode':1},{**fixed,'status':'UNKNOWN_TIMEOUT'}):
            self.assertFalse(admit_red_green(base,bad));self.assertFalse(repair_green(base,bad))
    def test_raw_failure_preserved_in_compaction(self):
        x=receipt_view({'native':{'tests':{'a':'pass','b':'failure'},'trace':{'x':[1,2]}},'prompt':'large'})
        self.assertEqual(x['native']['failing_test_ids'],['b']);self.assertEqual(x['native']['test_counts'],{'pass':1,'failure':1})
        self.assertIn('trace_sha256',x['native'])

if __name__=='__main__':unittest.main()
