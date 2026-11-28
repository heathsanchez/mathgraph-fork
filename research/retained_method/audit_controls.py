import copy, importlib.util, json, pathlib, shutil, tempfile, sys
spec=importlib.util.spec_from_file_location('audit',pathlib.Path(__file__).with_name('audit.py'));a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
root=pathlib.Path(sys.argv[1]).resolve()
report=a.audit(root)
results=[]
def change(p,fn):
 x=json.loads(p.read_text());fn(x);p.write_text(json.dumps(x))
controls=[
 ('false_qualification',lambda r:change(r/'work/summary.json',lambda x:x['outcomes']['retained-0'].__setitem__('qualified',False))),
 ('lost_author_test',lambda r:change(r/'work/controls.json',lambda x:x['author']['rows'].pop(next(iter(x['author']['rows']))))),
 ('wrong_arm_prompt',lambda r:change(r/'work/responses/conventional-0-0.json',lambda x:x.__setitem__('prompt',x['prompt'].replace('Act as a competent conventional software investigator.','Injected altered treatment.')))),
 ('reused_response_identity',lambda r:change(r/'work/responses/removed-0-0.json',lambda x:x.__setitem__('response_id',a.read(r/'work/responses/retained-0-0.json')['response_id']))),
 ('candidate_replaced_by_original',lambda r:shutil.copyfile(r/'data/original/funcy/decorators.py',r/'work/candidates/retained-0.py')),
 ('missing_baseline_test_pass',lambda r:change(r/'work/judgments/retained-0.json',lambda x:x['rows'].pop(next(iter(x['rows']))))),
 ('altered_native_observation',lambda r:change(r/'work/probes/retained-0-0.json',lambda x:x['native'].__setitem__('diagnostic',x['native']['diagnostic']+' altered'))),
]
for name,mutate in controls:
 with tempfile.TemporaryDirectory(prefix='retained-audit-control-') as d:
  r=pathlib.Path(d)/'copy';shutil.copytree(root,r);mutate(r)
  try:a.semantic(r)
  except (AssertionError,KeyError,ValueError,StopIteration):results.append({'control':name,'rejected':True})
  else:raise AssertionError('corruption accepted: '+name)
assert a.audit(root)==report
out=pathlib.Path(sys.argv[2]).resolve();out.mkdir(parents=True,exist_ok=True)
(out/'independent-audit.json').write_text(json.dumps(report,sort_keys=True,indent=2)+'\n')
(out/'audit-corruption-controls.json').write_text(json.dumps({'controls':results,'original_unchanged':True,'boundary':'Second-implementation semantic checks on altered copies, separately from all manifest checks; no original evidence modified.'},sort_keys=True,indent=2)+'\n')
byarm={arm:{'qualified':sum(s['qualified'] for k,s in report['samples'].items() if k.startswith(arm+'-')),'api_calls':sum(s['api_calls'] for k,s in report['samples'].items() if k.startswith(arm+'-')),'native_probes':sum(s['native_actions'] for k,s in report['samples'].items() if k.startswith(arm+'-')),'api_tokens':sum(s['total_tokens'] for k,s in report['samples'].items() if k.startswith(arm+'-'))} for arm in ('retained','removed','conventional')}
print(json.dumps({'audit':'PASS','semantic_corruption_controls':len(results),'by_arm':byarm,'native_execution_attempts':49,'native_attempt_boundary':'3 authority controls + 10 investigator probe scripts + 9 candidate judges + 18 withdrawal/restorations + 9 fresh-directory replays; not independent tasks'},indent=2))
(out/'costs.json').write_text(json.dumps(byarm,sort_keys=True,indent=2)+'\n')
