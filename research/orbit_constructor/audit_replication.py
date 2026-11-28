"""Independent receipt/statistical auditor; no model or generated-code execution."""
import ast
import hashlib
import itertools
import json
from pathlib import Path
import sys

root=Path(sys.argv[1]).resolve()
def load(name):return json.loads((root/name).read_text())
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def rr(record):
    assert record.get('returncode')==0,record.get('status')
    return record['rows']
def norm(rows):return [{k:v for k,v in r.items() if k!='elapsed_seconds'} for r in rows]
def correct(rows,cases):
    assert len(rows)==len(cases)
    return [r['input']==c['input'] and r.get('status')=='RETURNED' and r.get('output')==c['expected'] for r,c in zip(rows,cases)]
def ground(candidate,repeated):
    table={r['input']:r.get('output') for r in rr(repeated)}
    observations=[r for row in rr(candidate) for r in row['observations']]
    assert all(table.get(r['input'])==r['output'] for r in observations)
    return len(observations)
def fisher_by_partitions(first,second):
    successes=set(range(first+second));partitions=list(itertools.combinations(range(12),6))
    return sum(len(successes.intersection(p))>=first for p in partitions)/len(partitions)

for prefix in ('','parent/'):
    manifest=load(prefix+'MANIFEST.json')
    for path,h in manifest.items():
        target=(root/prefix/path).resolve();assert target.is_relative_to(root) and target.is_file() and not target.is_symlink()
        assert digest(target)==h,(prefix,path)
identities=load('parent/data/identities.json');blobs=0
for label,identity in identities.items():
    for name,entry in identity['verified'].items():
        path=root/'parent/data/sources'/label/name;b=path.read_bytes()
        assert digest(path)==entry['sha256']
        assert hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()==entry['git_blob']
        blobs+=1
cases=load('parent/data/admitted.json')['cases'];common=[c for c in cases if c.get('kind') or c['original_matches_author']]
originals=[c for c in cases if not c.get('kind')]
feedback=load('replication/feedback.json');calls=load('replication/acquisition.json');summary=load('replication/summary.json')
assert len(calls)==18
ordinary=rr(load('replication/ordinary_information_native.json'))
packets={
    'trace':feedback['exposed'],
    'sham':[{'failure':r['failure'],'observations':[]} for r in feedback['exposed']],
    'ordinary':[{'failure':r['failure'],'observations':[{'input':s['input'],'output':s['output']}]} for r,s in zip(feedback['exposed'],ordinary)]}
prefixes=set();details={}
for key,record in calls.items():
    arm,index=key.split('-');assert arm in packets and 0<=int(index)<6
    prefix,suffix=record['prompt'].split('\nAdditional independently replayed native observations:\n')
    prefixes.add(prefix);assert json.loads(suffix)==packets[arm]
    for hidden in feedback['concealed']:assert hidden['input'] not in record['prompt']
    source_path=root/f'replication/{key}.py'
    if not source_path.exists():
        assert summary['qualification'][key]['qualified'] is False
        details[key]={'qualified':False,'status':'NO_NATIVE_CANDIDATE'};continue
    source=source_path.read_text();ast.parse(source)
    text=record['response'].strip()
    if text.startswith('```'):text=text[text.find('\n')+1:text.rfind('```')]
    assert json.loads(text)['source']==source
    native=load(f'replication/{key}_native.json');rows=rr(native);cv=correct(rows,common)
    assert native['source_sha256']==hashlib.sha256(json.dumps(source,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    callbacks=ground(native,load(f'replication/{key}_ground_replay.json'))
    full=load(f'replication/{key}_development.json');fv=correct(rr(full['native']),originals)
    ground(full['native'],load(f'replication/{key}_development_ground_replay.json'))
    assert norm(rr(load(f'replication/{key}_ledger_replay.json')))==norm(rows)
    q=summary['qualification'][key];assert q['qualified']==all(cv) and q['matches']==sum(cv)
    details[key]={'qualified':all(cv),'gate_matches':sum(cv),'gate_cases':len(cv),
                  'development_matches':sum(fv),'development_cases':len(fv),
                  'new_corrections':sum(v and not c['original_matches_author'] for c,v in zip(originals,fv)),
                  'lost_original_matches':sum(not v and c['original_matches_author'] for c,v in zip(originals,fv)),
                  'exposed_correct':q['exposed_correct'],'concealed_correct':q['concealed_correct'],
                  'native_callbacks_replayed':callbacks,'ledger_identical':True}
assert len(prefixes)==1
counts={arm:sum(details[f'{arm}-{i}']['qualified'] for i in range(6)) for arm in packets}
assert counts==summary['counts']
pvals={arm:fisher_by_partitions(counts['trace'],counts[arm]) for arm in ('sham','ordinary')}
for arm,value in pvals.items():assert abs(value-summary['fisher_one_sided'][arm])<1e-12
order=sorted(pvals,key=pvals.get)
holm={order[0]:pvals[order[0]]<=0.025};holm[order[1]]=holm[order[0]] and pvals[order[1]]<=0.05
assert holm==summary['holm_rejected']
unknown=any(r['status']!='RETURNED' for r in calls.values())
positive=not unknown and all(holm.values()) and all(counts['trace']>counts[a] for a in ('sham','ordinary'))
if not unknown:assert (summary['status']=='BOUNDED_WITHIN_TASK_INFORMATION_EFFECT')==positive
events=load('replication/native_calls.json')
out={'manifest_files_verified':len(load('MANIFEST.json')),'parent_manifest_files_verified':len(load('parent/MANIFEST.json')),
     'source_blobs_verified':blobs,'counts':counts,'samples_per_arm':6,'fisher_one_sided_independent_enumeration':pvals,
     'holm_rejected':holm,'within_task_promotion':positive,'recorded_gate':summary['status'],
     'shared_prompt_prefix_exact':True,'concealed_inputs_absent_from_all_prompts':True,
     'independent_response_ids':len({r.get('response_id') for r in calls.values()}),'per_sample':details,
     'api_calls_this_stage':len(calls),'input_tokens_this_stage':sum((r.get('usage') or {}).get('input_tokens',0) for r in calls.values()),
     'output_tokens_this_stage':sum((r.get('usage') or {}).get('output_tokens',0) for r in calls.values()),
     'native_attempts_this_stage':len(events),'native_recorded_callbacks_this_stage':sum(e['callbacks'] for e in events),
     'boundary':'Same exposed development task; API independence/exchangeability assumptions; no field-level breakthrough or independent-family claim.'}
for k in ('api_calls_this_stage','input_tokens_this_stage','output_tokens_this_stage'):assert out[k]==summary[k]
print(json.dumps(out,ensure_ascii=False,sort_keys=True,indent=2))
