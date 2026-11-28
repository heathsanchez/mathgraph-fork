"""Independent common-oracle audit of failure-driven refinement receipts."""
import ast
import hashlib
import json
from pathlib import Path
import sys

root=Path(sys.argv[1]).resolve()
def load(path):return json.loads((root/path).read_text())
def rows(record):
    assert record.get('returncode')==0
    return record['rows']
def sha(b):return hashlib.sha256(b).hexdigest()
def normalized(rr):return [{k:v for k,v in r.items() if k!='elapsed_seconds'} for r in rr]
def verdicts(rr,cases):
    assert len(rr)==len(cases)
    return [r['input']==c['input'] and r.get('status')=='RETURNED' and r.get('output')==c['expected'] for r,c in zip(rr,cases)]
def source_string(record):
    text=record['response'].strip()
    if text.startswith('```'):text=text[text.find('\n')+1:text.rfind('```')]
    return json.loads(text)['source']
def ground(candidate,replayed):
    mapping={r['input']:r['output'] for r in rows(replayed)}
    pairs=[r for row in rows(candidate) for r in row['observations']]
    assert all(mapping.get(r['input'])==r['output'] for r in pairs)
    return len(pairs)

manifest=load('MANIFEST.json')
for path,expected in manifest.items():
    q=(root/path).resolve();assert q.is_relative_to(root) and q.is_file() and not q.is_symlink()
    assert sha(q.read_bytes())==expected,path
parent=load('parent/MANIFEST.json')
for path,expected in parent.items():assert sha((root/'parent'/path).read_bytes())==expected,path
cases=load('parent/data/admitted.json')['cases'];originals=[c for c in cases if not c.get('kind')]
common=[c for c in cases if c.get('kind') or c['original_matches_author']]
failures=[r for r in load('parent/work/c1_qualification.json')['rows'] if not r['matches']]
feedback=load('refinement/feedback.json')
assert [r['failure'] for r in feedback['exposed']]==failures[:4]
assert feedback['concealed']==failures[4:]
source1=(root/'parent/work/c1.py').read_text()
assert sha(source1.encode())==load('refinement/frozen.json')['parent_source_sha256']
restored=rows(load('refinement/parent_restoration.json'))
for r,f in zip(restored,feedback['exposed']):
    assert r['input']==f['failure']['input'] and r['output']==f['failure']['actual'] and r['observations']==f['observations']
ground(load('refinement/parent_restoration.json'),load('refinement/parent_restoration_ground_replay.json'))
calls=load('refinement/acquisition.json');summary=load('refinement/summary.json')
assert set(calls)=={'retained-0','retained-1','reconstruction-0','reconstruction-1'}
prefixes=[r['prompt'].split('\nAdditional native execution observations')[0] for r in calls.values()]
assert len(set(prefixes))==1
for key,record in calls.items():
    payload=json.loads(record['prompt'].split('reconstruct any investigation):\n')[1])
    assert payload==(feedback['exposed'] if key.startswith('retained') else [])
    for hidden in feedback['concealed']:
        assert hidden['input'] not in record['prompt']
out={'manifest_files_verified':len(manifest),'parent_manifest_files_verified':len(parent),
     'shared_prior_prompt_exact':True,'independent_response_ids':len({r.get('response_id') for r in calls.values()}),
     'concealed_regressions_absent_from_prompts':True,'parent_restoration_exact':True,'per_sample':{}}
for key,record in calls.items():
    if not (root/f'refinement/{key}_native.json').exists():
        assert summary['successors'][key]['qualified'] is False
        out['per_sample'][key]={'qualified':False,'status':'NO_NATIVE_PROGRAM'};continue
    source=(root/f'refinement/{key}.py').read_text()
    assert source==source_string(record)
    ast.parse(source)
    native=load(f'refinement/{key}_native.json');rr=rows(native);decisions=verdicts(rr,common)
    assert native['source_sha256']==sha(json.dumps(source,ensure_ascii=False,sort_keys=True).encode())
    count=ground(native,load(f'refinement/{key}_ground_replay.json'))
    recorded=summary['successors'][key]
    assert recorded['qualified']==all(decisions) and recorded['matches']==sum(decisions)
    exposure={r['failure']['input'] for r in feedback['exposed']};hidden={r['input'] for r in feedback['concealed']}
    diagnostic=load(f'refinement/{key}_development_transfer.json')
    dr=rows(diagnostic['native']);dv=verdicts(dr,originals)
    ground(diagnostic['native'],load(f'refinement/{key}_development_ground_replay.json'))
    ledger=load(f'refinement/{key}_ledger_replay.json')
    assert ledger['identical'] and normalized(rows(ledger['native']))==normalized(rr)
    out['per_sample'][key]={'qualified':all(decisions),'gate_matches':sum(decisions),'gate_cases':len(decisions),
        'exposed_correct':sum(v for c,v in zip(common,decisions) if c['input'] in exposure),
        'concealed_correct':sum(v for c,v in zip(common,decisions) if c['input'] in hidden),
        'development_matches':sum(dv),'development_cases':len(dv),
        'new_corrections':sum(v and not c['original_matches_author'] for c,v in zip(originals,dv)),
        'lost_original_matches':sum(not v and c['original_matches_author'] for c,v in zip(originals,dv)),
        'ground_callbacks_replayed':count,'exact_ledger_replay':True,
        'failure_inputs':[c['input'] for c,v in zip(common,decisions) if not v]}
conventional=verdicts(rows(load('refinement/author_control_native.json')),originals)
assert all(conventional)
out['conventional_control']={'matches':sum(conventional),'cases':len(conventional)}
allcalls=[load('parent/work/acquire_c1.json')]+list(calls.values())
out['api_calls_including_parent']=len(allcalls)
for name in ('input_tokens','output_tokens'):
    out[name+'_including_parent']=sum((r.get('usage') or {}).get(name,0) for r in allcalls)
    assert out[name+'_including_parent']==summary[name+'_including_parent']
effect=all(out['per_sample'][f'retained-{i}']['qualified'] for i in range(2)) and all(not out['per_sample'][f'reconstruction-{i}']['qualified'] for i in range(2))
assert (summary['status']=='CANDIDATE_OBSERVATION_ACQUISITION_EFFECT')==effect
out['acquisition_effect_gate']=effect
out['recorded_gate']=summary['status']
out['boundary']='Independent receipt audit only. No API or generated-code execution. All source tasks were previously exposed development.'
events=load('refinement/native_calls.json')
out['refinement_native_attempts']=len(events)
out['refinement_native_recorded_callbacks']=sum(e['callbacks'] for e in events)
print(json.dumps(out,ensure_ascii=False,sort_keys=True,indent=2))
