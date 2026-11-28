"""Independent receipt auditor: no model calls and no generated-code execution."""
import ast
import hashlib
import json
from pathlib import Path
import sys

root=Path(sys.argv[1]).resolve()
def load(name):return json.loads((root/name).read_text())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def native_rows(name):
    r=load(name)
    assert r.get('returncode')==0,(name,r.get('status'))
    return r['rows']
def normalized(rr):return [{k:v for k,v in r.items() if k!='elapsed_seconds'} for r in rr]
def matches(rr,cases):
    assert len(rr)==len(cases)
    return [r.get('input')==c['input'] and r.get('status')=='RETURNED' and r.get('output')==c['expected'] for r,c in zip(rr,cases)]
def verify_ground(candidate,ground):
    expected={r['input']:r['output'] for r in ground}
    checks=[expected.get(r['input'])==r['output'] for row in candidate for r in row['observations']]
    assert all(checks)
    return len(checks)

manifest=load('MANIFEST.json')
for name,h in manifest.items():
    p=(root/name).resolve();assert p.is_relative_to(root) and p.is_file() and not p.is_symlink()
    assert sha(p)==h,name
identities=load('data/identities.json');blobs=0
for label,identity in identities.items():
    for name,record in identity['verified'].items():
        p=root/'data/sources'/label/name;b=p.read_bytes()
        assert sha(p)==record['sha256']
        assert hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()==record['git_blob']
        blobs+=1

out={'manifest_files_verified':len(manifest),'source_blobs_verified':blobs,
     'boundary':'Independent hash/outcome audit; generated programs and target libraries not executed here.'}
obstruction=load('obstruction.json')
if (root/'work/closed_orbit_native.json').exists():
    orbit=native_rows('work/closed_orbit_native.json');states=obstruction['states']
    assert obstruction['seed'] in states and obstruction['intended'] not in states
    assert [r['input'] for r in orbit]==states
    assert [r['output'] for r in orbit]==[states[i] for i in obstruction['successor']]
    out['closed_orbit_states_verified']=len(states)
if (root/'data/admitted.json').exists():
    admitted=load('data/admitted.json')['cases'];base_cases=load('data/cases.json')
    authored=native_rows('work/author_baseline.json');legacy=native_rows('work/legacy_baseline.json')
    author_map={r['input']:r['output'] for r in authored}
    legacy_map={r['input']:r['output'] for r in legacy}
    for c in admitted:
        assert author_map[c['input']]==c['expected']
        assert c['original']==legacy_map[c['input']]
        assert c['original_matches_author']==(c['original']==c['expected'])
    out.update(independent_author_admitted=len(admitted),original_fixtures=sum(not c.get('kind') for c in admitted),
               correlated_french_inputs=sum(bool(c.get('kind')) for c in admitted),
               original_matching_inputs=sum(c['original_matches_author'] for c in admitted))
    if (root/'work/c1_qualification_native.json').exists():
        qualification=[c for c in admitted if c.get('kind') or c['original_matches_author']]
        rr=native_rows('work/c1_qualification_native.json');verdicts=matches(rr,qualification)
        out['c1_qualification']={'matches':sum(verdicts),'total':len(verdicts),'all_correct':all(verdicts),
                                'failures':[{'case':c,'actual':r.get('output'),'status':r['status']} for c,r,v in zip(qualification,rr,verdicts) if not v]}
        ground=native_rows('work/c1_qualification_ground_replay.json')
        out['c1_callbacks_independently_replayed']=verify_ground(rr,ground)
        q=load('work/c1_qualification.json')
        assert q['matches']==sum(verdicts)
        assert q['qualified']==all(verdicts)
        assert sha(root/'work/c1.py')==q['source_raw_sha256']
        # Source is inspected as data only.
        ast.parse((root/'work/c1.py').read_text())
        if (root/'cold_replay.json').exists():
            cold=load('cold_replay.json')
            assert normalized(cold['native']['rows'])==normalized(rr)
            out['cold_replay_identical']=True
    if (root/'work/second_development.json').exists():
        second=load('work/second_development.json');old={(r['input'],r['output']) for r in second['removed']['observations']}
        fresh=[r for r in second['active']['observations'] if (r['input'],r['output']) not in old]
        assert fresh==second['new_ground_observations']
        out['new_ground_observations']=len(fresh)
        restore=native_rows('work/c1_restoration.json')[0]
        assert restore['output']==second['active']['output']
        assert restore['observations']==second['active']['observations']
        out['restore_identical']=True
        if (root/'work/acquire_c2.json').exists():
            common=[c for c in admitted if c.get('kind') or c['original_matches_author'] or c['input']==second['case']['input']]
            per_arm={}
            for key,record in load('work/acquire_c2.json').items():
                if not (root/f'work/{key}_native.json').exists():
                    per_arm[key]={'qualified':False,'status':'NO_NATIVE_CANDIDATE'};continue
                rr=native_rows(f'work/{key}_native.json');vv=matches(rr,common)
                verify_ground(rr,native_rows(f'work/{key}_ground_replay.json'))
                per_arm[key]={'qualified':all(vv),'matches':sum(vv),'total':len(vv)}
                if (root/f'work/{key}_ledger_replay.json').exists():
                    assert normalized(native_rows(f'work/{key}_ledger_replay.json'))==normalized(rr)
            out['successor_qualification']=per_arm
            out['acquisition_effect_gate']=all(per_arm[f'retained-{i}']['qualified'] for i in range(2)) and all(not per_arm[f'removed-{i}']['qualified'] for i in range(2))
if (root/'work/gate.json').exists():
    out['recorded_gate']=load('work/gate.json')['status']
if (root/'work/acquire_c1.json').exists():
    calls=[load('work/acquire_c1.json')]
    if (root/'work/acquire_c2.json').exists():calls+=list(load('work/acquire_c2.json').values())
    out.update(api_calls=len(calls),input_tokens=sum((c.get('usage') or {}).get('input_tokens',0) for c in calls),
               output_tokens=sum((c.get('usage') or {}).get('output_tokens',0) for c in calls))
    if (root/'work/summary.json').exists():
        summary=load('work/summary.json')
        for key in ('api_calls','input_tokens','output_tokens'):assert summary[key]==out[key]
print(json.dumps(out,ensure_ascii=False,sort_keys=True,indent=2))
