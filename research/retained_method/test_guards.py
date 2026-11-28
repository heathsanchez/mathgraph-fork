import ast, copy, hashlib, json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch as mockpatch
import pipeline as p

ORIGINAL='''import inspect

def arggetter(func, _cache={}):
    return func

def other(x):
    return x
'''
GOOD='''def arggetter(func, _cache={}):
    original = getattr(func, '__original__', None) or func
    return original
'''
class Guards(unittest.TestCase):
    def test_patch_preserves_other_source(self):
        result=p.patch(ORIGINAL,GOOD)
        self.assertEqual(result[:len('import inspect\n\n')],'import inspect\n\n')
        self.assertTrue(result.endswith('def other(x):\n    return x\n'))
    def test_signature_is_protected(self):
        with self.assertRaises(AssertionError):p.patch(ORIGINAL,'def arggetter(func):\n return func')
    def test_no_other_module_edit(self):
        with self.assertRaises(AssertionError):p.patch(ORIGINAL,GOOD+'\nopen=print')
    def test_no_file_reads(self):
        with self.assertRaises(AssertionError):p.patch(ORIGINAL,"def arggetter(func, _cache={}):\n return open('/target/tests/x').read()")
    def test_no_process_import(self):
        with self.assertRaises(AssertionError):p.patch(ORIGINAL,"def arggetter(func, _cache={}):\n import subprocess\n return func")
    def test_no_hidden_authority_reference(self):
        with self.assertRaises(AssertionError):p.patch(ORIGINAL,"def arggetter(func, _cache={}):\n return 'pytest'")
    def test_no_dynamic_eval(self):
        with self.assertRaises(AssertionError):p.patch(ORIGINAL,"def arggetter(func, _cache={}):\n return eval('1')")
    def test_native_replay_uses_identities_not_time(self):
        a={'status':'EXECUTED','returncode':0,'rows':{'x':{'call':'passed'}},'diagnostic':'1 passed in 0.2s','elapsed_seconds':1}
        b={**a,'diagnostic':'1 passed in 0.9s','elapsed_seconds':2}
        self.assertEqual(p.normalized(a),p.normalized(b))
        b['rows']={'x':{'call':'failed'}}
        self.assertNotEqual(p.normalized(a),p.normalized(b))
    def test_incomplete_or_extra_tests_never_qualify(self):
        f={'required_ids':['a','b'],'required_cases':['a','b'],'baseline_passes':['a']}
        with mockpatch.object(p,'guard',return_value=f):
            for rows,code in [({'a':{'call':'passed'}},0),({'a':{'call':'passed'},'b':{'call':'failed'}},1),({'a':{'call':'passed'},'b':{'call':'passed'},'c':{'call':'passed'}},0)]:
                self.assertFalse(p.score({'status':'EXECUTED','returncode':code,'rows':rows})['qualified'])
            self.assertTrue(p.score({'status':'EXECUTED','returncode':0,'rows':{'a':{'call':'passed'},'b':{'call':'passed'}}})['qualified'])
    def test_no_unknown_pass(self):
        with mockpatch.object(p,'guard',return_value={'required_ids':[],'required_cases':[],'baseline_passes':[]}):
            self.assertFalse(p.score({'status':'UNKNOWN_TIMEOUT','returncode':0,'rows':{}})['qualified'])
    def test_source_withdrawal_is_detected_by_binding(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'source').write_text('v1')
            f={'code':{},'source':{'source':p.digest(root/'source')}}
            p.dump(root/'freeze.json',f)
            with mockpatch.object(p,'DATA',root),mockpatch.object(p,'binding',return_value={}):
                p.guard();(root/'source').write_text('v2')
                with self.assertRaises(AssertionError):p.guard()
                (root/'source').write_text('v1');p.guard()
    def test_retained_and_removed_share_common_prompt(self):
        self.assertEqual(p.NOTES['removed'],'')
        self.assertIn('reconstruct',p.NOTES['conventional'])
        self.assertEqual(len(p.ORDER),9)
        self.assertEqual(len(set(p.ORDER)),9)
if __name__=='__main__':unittest.main()
