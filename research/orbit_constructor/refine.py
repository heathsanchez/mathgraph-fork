"""A preregistered continuation from the rejected parent's native failures."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile
import pipeline as p

PARENT=p.HERE/'parent'
p.DATA=PARENT/'data'
p.WORK=p.HERE/'refinement'


def prepare():
    archive=p.HERE/'download/evidence.zip'
    if p.digest(archive)!='60b014d6a38218eca5daddb08867c378e980b8e7c65b01a7864760340fff5785':
        raise ValueError('parent artifact identity')
    if PARENT.exists():raise ValueError('parent destination exists')
    with zipfile.ZipFile(archive) as z:
        if z.testzip():raise ValueError('parent CRC')
        for name in z.namelist():
            path=Path(name)
            if path.is_absolute() or '..' in path.parts:raise ValueError('parent path')
        z.extractall(PARENT)
    for name,sha in p.load(PARENT/'MANIFEST.json').items():
        if p.digest(PARENT/name)!=sha:raise ValueError('parent manifest')
    p.guard();p.WORK.mkdir(exist_ok=True)
    q=p.load(PARENT/'work/c1_qualification.json')
    if q['qualified'] or q['matches']!=72 or q['cases']!=80:raise ValueError('wrong parent result')
    failures=[r for r in q['rows'] if not r['matches']]
    if len(failures)!=8:raise ValueError('wrong failure count')
    native=p.rows(p.load(PARENT/'work/c1_qualification_native.json'))
    ground={r['input']:r for r in native}
    exposed=failures[:4];hidden=failures[4:]
    packets=[{'failure':r,'observations':ground[r['input']]['observations']} for r in exposed]
    p.dump(p.WORK/'feedback.json',{'exposed':packets,'concealed':hidden,'selection':'first four native preservation failures in saved order',
                                 'protocol_sha256':p.digest(p.HERE/'REFINEMENT.md')})
    result=subprocess.run(['docker','build','-t',p.IMAGE,str(p.HERE)],text=True,capture_output=True,timeout=600)
    p.dump(p.WORK/'build.json',{'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
    if result.returncode:raise RuntimeError('native image failed')
    source=(PARENT/'work/c1.py').read_text()
    replay=p.native('legacy',[r['input'] for r in exposed],source)
    p.dump(p.WORK/'parent_restoration.json',replay)
    normalized=[{'input':r['input'],'output':r.get('output'),'observations':r['observations']} for r in p.rows(replay)]
    expected=[{'input':r['input'],'output':r['actual'],'observations':ground[r['input']]['observations']} for r in exposed]
    if normalized!=expected:raise RuntimeError('parent restoration mismatch')
    groundcheck=p.verify_ground(replay,'parent_restoration')
    if not groundcheck['verified']:raise RuntimeError('parent observations changed native operation')
    p.dump(p.WORK/'parent_restoration_check.json',groundcheck)
    p.dump(p.WORK/'frozen.json',{'protocol_sha256':p.digest(p.HERE/'REFINEMENT.md'),
                               'feedback_sha256':p.digest(p.WORK/'feedback.json'),
                               'parent_source_sha256':hashlib.sha256(source.encode()).hexdigest(),
                               'source_sha':os.environ.get('GITHUB_SHA')})
    print('REFINEMENT_FROZEN',len(exposed),'exposed',len(hidden),'concealed',flush=True)


def guard():
    p.guard();f=p.load(p.WORK/'frozen.json')
    if f['protocol_sha256']!=p.digest(p.HERE/'REFINEMENT.md') or f['feedback_sha256']!=p.digest(p.WORK/'feedback.json'):
        raise ValueError('refinement freeze drift')


def learn():
    guard();feedback=p.load(p.WORK/'feedback.json');prior=p.load(PARENT/'work/acquire_c1.json')
    shared=p.INSTRUCTIONS+'\nThe first constructed method was REJECTED: it repaired the obstruction but corrupted some correct outputs.\n'
    shared+='Construct a complete safer successor. Preserve the initial new capability as well as original correctness.\n'
    shared+=json.dumps({'initial_prompt':prior['prompt'],'initial_response':prior['response'],
                       'new_development_failures':[r['failure'] for r in feedback['exposed']]},ensure_ascii=False)
    calls={}
    for sample,arm in [(0,'retained'),(0,'reconstruction'),(1,'reconstruction'),(1,'retained')]:
        observation=feedback['exposed'] if arm=='retained' else []
        prompt=shared+'\nAdditional native execution observations (empty means ordinary reconstruction; you may reconstruct any investigation):\n'+json.dumps(observation,ensure_ascii=False)
        record=p.call(prompt);calls[f'{arm}-{sample}']=record;p.dump(p.WORK/'acquisition.json',calls)
        print('REFINEMENT_RESPONSE',arm,sample,record['status'],flush=True)


def qualify():
    guard();cases=p.load(p.DATA/'admitted.json')['cases']
    common=[c for c in cases if c.get('kind') or c['original_matches_author']]
    originals=[c for c in cases if not c.get('kind')]
    feedback=p.load(p.WORK/'feedback.json');exposed={r['failure']['input'] for r in feedback['exposed']};hidden={r['input'] for r in feedback['concealed']}
    summary={}
    for key,record in p.load(p.WORK/'acquisition.json').items():
        source=p.program(record)
        if source is None:
            summary[key]={'qualified':False,'status':'REJECTED_PROGRAM_BOUNDARY'};continue
        (p.WORK/(key+'.py')).write_text(source)
        result=p.native('legacy',[c['input'] for c in common],source);p.dump(p.WORK/(key+'_native.json'),result)
        q=p.score(result,common);q['ground_replay']=p.verify_ground(result,key)
        q['qualified']=q['qualified'] and q['ground_replay']['verified']
        q['exposed_regressions']={r['input']:r['matches'] for r in q.get('rows',[]) if r['input'] in exposed}
        q['concealed_regressions']={r['input']:r['matches'] for r in q.get('rows',[]) if r['input'] in hidden}
        summary[key]=q
        result_all=p.native('legacy',[c['input'] for c in originals],source)
        p.dump(p.WORK/(key+'_development_transfer.json'),{'native':result_all,'score':p.score(result_all,originals)})
        ground=p.verify_ground(result_all,key+'_development')
        p.dump(p.WORK/(key+'_development_ground_check.json'),ground)
        again=p.native('legacy',[c['input'] for c in common],source)
        normalize=lambda r:[{k:v for k,v in x.items() if k!='elapsed_seconds'} for x in p.rows(r)]
        parity=normalize(again)==normalize(result)
        p.dump(p.WORK/(key+'_ledger_replay.json'),{'identical':parity,'native':again,'parent_file_available_to_program':False})
        if not parity:raise RuntimeError('complete compiled successor replay differs')
        print('REFINEMENT_RESULT',key,q.get('matches'),q.get('cases'),q['qualified'],flush=True)
    author=p.native('author',[c['input'] for c in originals]);p.dump(p.WORK/'author_control_native.json',author)
    conventional=p.score(author,originals)
    effect=all(summary.get(f'retained-{i}',{}).get('qualified') for i in range(2)) and all(not summary.get(f'reconstruction-{i}',{}).get('qualified') for i in range(2))
    calls=p.load(p.WORK/'acquisition.json');parent=p.load(PARENT/'work/acquire_c1.json');allcalls=[parent]+list(calls.values())
    usage=lambda name:sum((c.get('usage') or {}).get(name,0) for c in allcalls)
    result={'status':'CANDIDATE_OBSERVATION_ACQUISITION_EFFECT' if effect else 'INSUFFICIENT_ACQUISITION_EFFECT',
            'parent_remains_rejected':True,'successors':summary,'author_control':conventional,
            'api_calls_including_parent':len(allcalls),'input_tokens_including_parent':usage('input_tokens'),
            'output_tokens_including_parent':usage('output_tokens'),'breakthrough_established':False,
            'boundary':'Exposed development calibration and inference-only withheld regressions. Not independent multi-family transfer.',
            'source_sha':os.environ.get('GITHUB_SHA')}
    events=p.load(p.WORK/'native_calls.json');result['native_attempts']=len(events);result['native_callbacks']=sum(e['callbacks'] for e in events)
    p.dump(p.WORK/'summary.json',result)
    print('REFINEMENT_GATE',result['status'],'API_CALLS',len(allcalls),flush=True)


def bundle():
    # Includes the unchanged original failed gate and all refinement outcomes.
    p.bundle()


if __name__=='__main__':
    {'prepare':prepare,'learn':learn,'qualify':qualify,'bundle':bundle}[sys.argv[1]]()
