"""Obstruction -> code construction -> native acquisition mediation test."""
import ast
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile

HERE = Path(__file__).resolve().parent
DATA, WORK = HERE/'data', HERE/'work'
IMAGE = 'mathgraph-orbit-constructor:20261128'
PINS = {'legacy': '4f6a2d05ab395a43aad3541bd3571bf2aa701307',
        'author': '74dd0452b48286a3770013b3a02755313bd5575e'}
MODEL = 'gpt-6.2-sol'


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)+'\n')


def load(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stable(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def guard():
    frozen = load(DATA/'freeze.json')
    if frozen['protocol_sha256'] != digest(HERE/'PROTOCOL.md'):
        raise ValueError('protocol changed after source freeze')
    for name, expected in frozen['manifest'].items():
        if digest(DATA/name) != expected:
            raise ValueError('frozen source/input changed: '+name)
    return frozen


def native(which, inputs, source=None):
    if os.environ.get('OPENAI_API_KEY') or os.environ.get('GITHUB_TOKEN'):
        raise RuntimeError('native stage must not have service credentials')
    root = DATA/'sources'/which
    if (root/'src/ftfy').is_dir(): root = root/'src'
    with tempfile.TemporaryDirectory(prefix='constructor-native-') as d:
        temp = Path(d); (temp/'out').mkdir(); (temp/'out').chmod(0o777); temp.chmod(0o755)
        payload = {'inputs': inputs, 'source': source, 'options': {'normalization': 'NFC'}}
        dump(temp/'request.json', payload)
        cmd = ['docker', 'run', '--rm', '--network', 'none', '--read-only',
               '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
               '--pids-limit', '64', '--memory', '700m', '--cpus', '2',
               '--tmpfs', '/tmp:rw,nosuid,nodev,size=64m',
               '-v', str(root.resolve())+':/target:ro',
               '-v', str(temp/'request.json')+':/work/request.json:ro',
               '-v', str(temp/'out')+':/out:rw', IMAGE]
        started = time.monotonic()
        try:
            p = subprocess.run(cmd, text=True, capture_output=True, timeout=180)
            result = {'status': 'EXECUTED', 'returncode': p.returncode,
                      'diagnostic': (p.stdout+'\n'+p.stderr)[-3000:]}
            if (temp/'out/result.json').exists(): result.update(load(temp/'out/result.json'))
            else: result['status'] = 'UNKNOWN_NO_NATIVE_RECEIPT'
        except subprocess.TimeoutExpired:
            result = {'status': 'UNKNOWN_NATIVE_TIMEOUT'}
        result.update(elapsed_seconds=time.monotonic()-started, request_sha256=stable(payload),
                      source_sha256=stable(source), inputs_sha256=stable(inputs))
        events=load(WORK/'native_calls.json') if (WORK/'native_calls.json').exists() else []
        events.append({'phase':sys.argv[1] if len(sys.argv)>1 else 'unknown','target':which,
                       'request_sha256':result['request_sha256'],'source_sha256':result['source_sha256'],
                       'status':result['status'],'inputs':len(inputs),'rows':len(result.get('rows',[])),
                       'callbacks':sum(len(r.get('observations',[])) for r in result.get('rows',[])),
                       'elapsed_seconds':result['elapsed_seconds']})
        dump(WORK/'native_calls.json',events)
        return result


def rows(result):
    return result.get('rows', []) if result.get('returncode') == 0 else []


def verify_ground(result, label):
    observations=[r for row in rows(result) for r in row.get('observations',[])]
    inputs=list(dict.fromkeys(r['input'] for r in observations))
    if not inputs:return {'verified':True,'unique_inputs':0}
    repeated=native('legacy',inputs)
    dump(WORK/(label+'_ground_replay.json'),repeated)
    if len(rows(repeated))!=len(inputs):return {'verified':False,'reason':'incomplete independent ground replay'}
    actual={r['input']:r['output'] for r in rows(repeated)}
    return {'verified':all(actual.get(r['input'])==r['output'] for r in observations),
            'unique_inputs':len(inputs),'callbacks':len(observations)}


def prepare():
    sys.path.insert(0, str(HERE.parent/'applicability_transfer'))
    import admit_legacy as api
    DATA.mkdir(exist_ok=True); WORK.mkdir(exist_ok=True)
    identities = {}
    for label, pin in PINS.items():
        with tempfile.TemporaryDirectory(prefix='constructor-source-') as d:
            root, archive_sha = api.safe_archive('rspeer/python-ftfy', pin, Path(d)/'archive')
            destination = DATA/'sources'/label
            if destination.exists(): raise ValueError('existing source destination')
            shutil.copytree(root, destination)
        commit = api.api('rspeer/python-ftfy', 'commits/'+pin)
        tree = api.api('rspeer/python-ftfy', 'git/trees/'+commit['commit']['tree']['sha']+'?recursive=1')
        if tree.get('truncated'): raise ValueError('truncated source identity')
        verified = {}
        for entry in tree['tree']:
            if entry['type'] == 'blob' and entry['path'].endswith(('.py', '.json')):
                path = destination/entry['path']
                if not path.is_file() or path.is_symlink() or api.gitblob(path) != entry['sha']:
                    raise ValueError('source Git blob mismatch')
                verified[entry['path']] = {'git_blob': entry['sha'], 'sha256': digest(path)}
        identities[label] = {'sha': pin, 'tree': commit['commit']['tree']['sha'],
                             'archive_sha256': archive_sha, 'verified': verified}
    author = DATA/'sources/author'
    cases = []
    for name in ('synthetic.json', 'negative.json', 'in-the-wild.json'):
        path = author/'tests/test-cases'/name
        for index, item in enumerate(load(path)):
            if not isinstance(item, dict) or item.get('expect') != 'pass': continue
            x, y = item.get('original'), item.get('fixed')
            if not isinstance(x, str) or not isinstance(y, str) or len(x)>2048 or x=='&amp;amp;': continue
            cases.append({'input': x, 'expected': y, 'author_fixture': f'tests/test-cases/{name}:{index}'})
            if len(cases) >= 200: break
        if len(cases) >= 200: break
    obstruction = load(HERE/'obstruction.json')
    assert any(c['input']==obstruction['seed'] and c['expected']==obstruction['intended'] for c in cases)
    dump(DATA/'cases.json', cases)
    dump(DATA/'identities.json', identities)
    manifest = {str(p.relative_to(DATA)): digest(p) for p in sorted(DATA.rglob('*')) if p.is_file()}
    dump(DATA/'freeze.json', {'manifest': manifest, 'protocol_sha256': digest(HERE/'PROTOCOL.md'),
                             'obstruction_sha256': digest(HERE/'obstruction.json'), 'source_sha': os.environ.get('GITHUB_SHA')})
    print('ORBIT_SOURCE_FROZEN', len(cases), PINS, flush=True)


def initial():
    guard()
    if os.environ.get('OPENAI_API_KEY') or os.environ.get('GITHUB_TOKEN'):
        raise RuntimeError('unexpected credential')
    p = subprocess.run(['docker','build','-t',IMAGE,str(HERE)],text=True,capture_output=True,timeout=600)
    dump(WORK/'build.json', {'returncode': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr})
    if p.returncode: raise RuntimeError('native image failed')
    image = subprocess.check_output(['docker','image','inspect',IMAGE,'--format','{{.Id}}'],text=True).strip()
    dump(WORK/'environment.json', {'image_id': image, 'host_python': sys.version, 'worker_sha256': digest(HERE/'worker.py')})
    obstruction = load(HERE/'obstruction.json'); cases = load(DATA/'cases.json')
    variants = [{'input': obstruction['seed'], 'expected': obstruction['intended'], 'kind':'original'}]
    variants += [{'input':f'CTX{i}: '+obstruction['seed']+f' :END{i}',
                  'expected':f'CTX{i}: '+obstruction['intended']+f' :END{i}', 'kind':'correlated_ascii_wrapper'} for i in range(16)]
    joined = cases+variants
    for which in PINS:
        result = native(which, [c['input'] for c in joined])
        dump(WORK/(which+'_baseline.json'), result)
        if len(rows(result)) != len(joined): raise RuntimeError('native authority unavailable')
    author_rows, old_rows = rows(load(WORK/'author_baseline.json')), rows(load(WORK/'legacy_baseline.json'))
    authority, excluded = [], []
    for c, good, old in zip(joined, author_rows, old_rows):
        if good.get('output') != c['expected']:
            excluded.append({'case': c, 'author': good}); continue
        authority.append({**c, 'original':old.get('output'), 'original_matches_author':old.get('output')==c['expected']})
    if any(c['case'].get('kind') for c in excluded): raise RuntimeError('wrapper authority mismatch')
    dump(DATA/'admitted.json', {'cases': authority, 'excluded': excluded, 'boundary':'Previously opened development fixtures, not prospective transfer.'})
    # admitted.json is native authority, deliberately stored outside the earlier source manifest.
    replay = native('legacy', obstruction['states'])
    dump(WORK/'closed_orbit_native.json', replay)
    if [r.get('output') for r in rows(replay)] != [obstruction['states'][j] for j in obstruction['successor']]:
        raise RuntimeError('prior closed orbit failed native replay')
    if obstruction['intended'] in obstruction['states']: raise RuntimeError('not an obstruction')
    print('ORBIT_REPRODUCED',len(obstruction['states']), 'PRESERVATIONS',sum(c['original_matches_author'] for c in authority), 'EXCLUDED',len(excluded),flush=True)


def call(prompt):
    from openai import OpenAI
    started = time.monotonic()
    record = {'model': MODEL, 'prompt': prompt, 'prompt_sha256': stable(prompt), 'max_output_tokens':6000,
              'reasoning_effort':'low'}
    try:
        response = OpenAI(api_key=os.environ['OPENAI_API_KEY'],timeout=180,max_retries=0).responses.create(
            model=MODEL,input=prompt,reasoning={'effort':'low'},max_output_tokens=6000)
        record.update(status='RETURNED',response=response.output_text,response_id=response.id,actual_model=response.model,
                      usage=response.usage.model_dump() if response.usage else None)
        text = response.output_text.strip()
        if text.startswith('```'): text=text[text.find('\n')+1:text.rfind('```')]
        try: record['parsed']=json.loads(text)
        except ValueError: record['parse_error']='INVALID_JSON'
    except Exception as exc:
        record.update(status='UNKNOWN_API_ERROR',error_type=type(exc).__name__,http_status=getattr(exc,'status_code',None))
    record['elapsed_seconds']=time.monotonic()-started
    return record


INSTRUCTIONS = '''Construct a reusable executable investigation method from the real native obstruction below.
Return only a JSON object {"source": "complete ordinary Python source", "explanation": "..."}.
The source defines investigate(text, operation) returning the best corrected str, or None when unsupported.
operation(str) calls the unchanged historical normalization function. You can also use ordinary Python,
its standard library, and the pinned historical ftfy module. You are not limited to repeating operation.
No proposed new operation/menu is supplied. Derive the needed representation/operations from the failure.
The same method is used on other text. Preserve legitimate ordinary text and already correct outputs.
Develop an investigation procedure that can make actual diagnostic observations on later inputs, not
just a patch for the one phrase. The operation callback logs its real inputs/outputs, at most 64/input.
Expected answers, the author implementation and scoring data are unavailable in your runtime. Do not
read local files, use network, inspect the harness, embed an answer table, hardcode a development phrase
or silently manufacture acceptance claims. Each invocation is deterministic. The actual function may
be imported as ftfy.fix_text but callback operation should be used for observations. It runs NFC.
This is a later-contract migration assessment; no current-upstream bug is alleged. The later author
requires completed normalization and uses independently collected/synthetic exact expected fixtures.
Convergence by itself is not a semantic authority. Finite qualification includes all prior matching
outputs and ASCII prefix/suffix variants. No adaptive retry follows a qualification failure.
'''


def legacy_source():
    return (DATA/'sources/legacy/ftfy/__init__.py').read_text()


def learn1():
    guard()
    prompt = INSTRUCTIONS+'\nClosed orbit (native replayed; intended outside):\n'+json.dumps(load(HERE/'obstruction.json'),ensure_ascii=False)
    prompt += '\nExact historical source:\n'+legacy_source()
    dump(WORK/'acquire_c1.json',call(prompt))
    print('ORBIT_C1_CONSTRUCTED',load(WORK/'acquire_c1.json')['status'],flush=True)


def program(record):
    source=record.get('parsed',{}).get('source')
    if not isinstance(source,str) or len(source)>45000: return None
    try:
        tree=ast.parse(source)
        if not any(isinstance(n,ast.FunctionDef) and n.name=='investigate' for n in tree.body):return None
        exact={c['input'] for c in load(DATA/'admitted.json')['cases']}|{c['expected'] for c in load(DATA/'admitted.json')['cases']}
        if any(isinstance(n,ast.Constant) and isinstance(n.value,str) and len(n.value)>=16 and n.value in exact for n in ast.walk(tree)):
            return None
    except (SyntaxError,ValueError):return None
    return source


def score(result, cases):
    rr=rows(result)
    if len(rr)!=len(cases):return {'qualified':False,'status':'UNKNOWN_INCOMPLETE_NATIVE','observations':len(rr)}
    outcomes=[{'input':c['input'],'expected':c['expected'],'actual':r.get('output'), 'status':r.get('status'),
               'matches':r.get('input')==c['input'] and r.get('status')=='RETURNED' and r.get('output')==c['expected']} for c,r in zip(cases,rr)]
    return {'qualified':all(r['matches'] for r in outcomes),'matches':sum(r['matches'] for r in outcomes),
            'cases':len(cases),'rows':outcomes,'native_callbacks':sum(len(r['observations']) for r in rr)}


def new_observations(actual, ordinary):
    old={(r['input'],r['output']) for r in ordinary}
    return [r for r in actual if (r['input'],r['output']) not in old]


def qualify1():
    guard();source=program(load(WORK/'acquire_c1.json'))
    if source is None:
        dump(WORK/'gate.json',{'status':'REJECTED_C1_PROGRAM_BOUNDARY'});return
    (WORK/'c1.py').write_text(source)
    cases=load(DATA/'admitted.json')['cases']
    qualification=[c for c in cases if c.get('kind') or c['original_matches_author']]
    result=native('legacy',[c['input'] for c in qualification],source);dump(WORK/'c1_qualification_native.json',result)
    q=score(result,qualification);q['ground_replay']=verify_ground(result,'c1_qualification')
    q['qualified']=q['qualified'] and q['ground_replay']['verified']
    q['source_raw_sha256']=hashlib.sha256(source.encode()).hexdigest()
    dump(WORK/'c1_qualification.json',q)
    if not q['qualified']:
        dump(WORK/'gate.json',{'status':'REJECTED_C1_QUALIFICATION','qualification':q});print('ORBIT_STOP_C1',q['matches'],q['cases'],flush=True);return
    # Search exposed development only; no observations are passed as prior history to the removed arm.
    remaining=[c for c in cases if not c.get('kind') and not c['original_matches_author'] and c['input']!=load(HERE/'obstruction.json')['seed']]
    selection=native('legacy',[c['input'] for c in remaining],source);dump(WORK/'development_residual_search.json',selection)
    if len(rows(selection))!=len(remaining):
        dump(WORK/'gate.json',{'status':'UNKNOWN_RESIDUAL_SEARCH'});return
    ground=verify_ground(selection,'development_residual_search')
    dump(WORK/'development_ground_verification.json',ground)
    if not ground['verified']:
        dump(WORK/'gate.json',{'status':'REJECTED_CHANGED_OPERATION_OBSERVATIONS'});return
    for c,r in zip(remaining,rows(selection)):
        if r.get('output')==c['expected']:continue
        # Both arms receive independent expected development feedback, not a future answer.
        normal=native('legacy',[c['input']]);dump(WORK/'second_residual_ordinary.json',normal)
        seed=c['input'];old=[];seen=set()
        for _ in range(10):
            if seed in seen:break
            seen.add(seed);single=native('legacy',[seed]);rr=rows(single)
            if not rr:raise RuntimeError('ordinary observation unavailable')
            y=rr[0]['output'];old.append({'input':seed,'output':y});seed=y
        actual=r.get('observations',[])
        packet={'case':c,'active':{'output':r.get('output'),'observations':actual},
                'removed':{'output':seed,'observations':old},'new_ground_observations':new_observations(actual,old)}
        dump(WORK/'second_development.json',packet)
        restore=native('legacy',[c['input']],source);dump(WORK/'c1_restoration.json',restore)
        restored=rows(restore)
        parity=bool(restored) and restored[0].get('output')==r.get('output') and restored[0].get('observations')==actual
        if not parity:raise RuntimeError('native method restoration changed observations')
        gate={'status':'READY_SECOND_ACQUISITION' if packet['new_ground_observations'] else 'INSUFFICIENT_ACQUISITION_OBSERVATIONS',
              'c1_qualified':True,'new_ground_observations':len(packet['new_ground_observations']),'restoration_parity':parity}
        dump(WORK/'gate.json',gate);print('ORBIT_C1_GATE',json.dumps(gate),flush=True);return
    dump(WORK/'gate.json',{'status':'NO_SECOND_RESIDUAL','c1_qualified':True})


def learn2():
    guard()
    if load(WORK/'gate.json')['status']!='READY_SECOND_ACQUISITION':return
    packet=load(WORK/'second_development.json');prior=load(WORK/'acquire_c1.json')
    shared=INSTRUCTIONS+'\nConstruct a complete improved successor. All first-stage raw construction evidence and source follow.\n'
    shared+=json.dumps({'first_prompt':prior['prompt'],'first_response':prior.get('response'),
                       'first_qualification':load(WORK/'c1_qualification.json'),
                       'new_development_case':packet['case']},ensure_ascii=False)
    results={}
    # Counterbalanced fixed order, two independent samples/arm; never share inference responses.
    for sample,arm in [(0,'retained'),(0,'removed'),(1,'removed'),(1,'retained')]:
        stream=packet['active' if arm=='retained' else 'removed']
        prompt=shared+'\nNative observations now available for the new development case:\n'+json.dumps(stream,ensure_ascii=False)
        rec=call(prompt);results[f'{arm}-{sample}']=rec;dump(WORK/'acquire_c2.json',results)
        print('ORBIT_C2_CONSTRUCTED',arm,sample,rec['status'],flush=True)


def qualify2():
    guard()
    if load(WORK/'gate.json')['status']!='READY_SECOND_ACQUISITION':return
    cases=load(DATA/'admitted.json')['cases'];new=load(WORK/'second_development.json')['case']
    mandatory=[c for c in cases if c.get('kind') or c['original_matches_author'] or c['input']==new['input']]
    results={}
    for key,record in load(WORK/'acquire_c2.json').items():
        source=program(record)
        if source is None:results[key]={'qualified':False,'status':'REJECTED_PROGRAM_BOUNDARY'};continue
        (WORK/(key+'.py')).write_text(source)
        result=native('legacy',[c['input'] for c in mandatory],source)
        dump(WORK/(key+'_native.json'),result);results[key]=score(result,mandatory)
        results[key]['ground_replay']=verify_ground(result,key)
        results[key]['qualified']=results[key]['qualified'] and results[key]['ground_replay']['verified']
        diagnostic=native('legacy',[c['input'] for c in cases if not c.get('kind')],source)
        dump(WORK/(key+'_development_transfer.json'),{'native':diagnostic,'score':score(diagnostic,[c for c in cases if not c.get('kind')])})
        print('ORBIT_C2_QUALIFIED',key,results[key]['qualified'],results[key].get('matches'),results[key].get('cases'),flush=True)
    # Replay with C1 absent: frozen stream + exact saved response are sufficient; no extra API sample claimed.
    replay={}
    for key in ('retained-0','retained-1'):
        path=WORK/(key+'.py')
        if not path.exists():continue
        repeated=native('legacy',[c['input'] for c in mandatory],path.read_text())
        dump(WORK/(key+'_ledger_replay.json'),repeated)
        original=load(WORK/(key+'_native.json'))
        normalize=lambda r:[{k:v for k,v in x.items() if k!='elapsed_seconds'} for x in rows(r)]
        replay[key]=normalize(repeated)==normalize(original)
    gate=load(WORK/'gate.json')
    promoted=all(results.get(f'retained-{i}',{}).get('qualified') for i in range(2)) and all(not results.get(f'removed-{i}',{}).get('qualified') for i in range(2)) and all(replay.get(f'retained-{i}') for i in range(2))
    gate.update(status='CANDIDATE_ACQUISITION_EFFECT' if promoted else 'INSUFFICIENT_ACQUISITION_EFFECT',successors=results,ledger_replay=replay,
                broader_trial_authorized_by_evidence=promoted,breakthrough_established=False)
    dump(WORK/'gate.json',gate)


def report():
    guard();gate=load(WORK/'gate.json') if (WORK/'gate.json').exists() else {'status':'UNKNOWN_NO_GATE'}
    calls=[]
    if (WORK/'acquire_c1.json').exists():calls.append(load(WORK/'acquire_c1.json'))
    if (WORK/'acquire_c2.json').exists():calls+=list(load(WORK/'acquire_c2.json').values())
    total=lambda key:sum((r.get('usage') or {}).get(key,0) for r in calls)
    summary={'gate':gate,'api_calls':len(calls),'input_tokens':total('input_tokens'),'output_tokens':total('output_tokens'),
             'successful_api_responses':sum(r['status']=='RETURNED' for r in calls),
             'authority_boundary':'Exposed same-project development calibration only; no prospective independent research advantage.',
             'source_sha':os.environ.get('GITHUB_SHA'),'breakthrough_established':False}
    if (WORK/'native_calls.json').exists():
        events=load(WORK/'native_calls.json')
        summary['native_execution_attempts']=len(events)
        summary['native_recorded_callbacks']=sum(e['callbacks'] for e in events)
        summary['native_elapsed_seconds']=sum(e['elapsed_seconds'] for e in events)
    if (DATA/'admitted.json').exists():
        admitted=load(DATA/'admitted.json')['cases']
        summary['author_control_matches']=len([c for c in admitted if not c.get('kind')])
        summary['author_control_boundary']='Same independently authored exposed development fixtures; not an acquisition ablation.'
    dump(WORK/'summary.json',summary)
    print('ORBIT_FINAL',json.dumps({k:v for k,v in summary.items() if k!='gate'}),'GATE',gate['status'],flush=True)


def replay():
    guard()
    if not (WORK/'c1.py').exists():
        dump(HERE/'cold_replay.json',{'status':'NO_ACCEPTED_C1_TO_REPLAY'});return
    cases=load(DATA/'admitted.json')['cases'];qualification=[c for c in cases if c.get('kind') or c['original_matches_author']]
    if hashlib.sha256((WORK/'c1.py').read_bytes()).hexdigest()!=load(WORK/'c1_qualification.json')['source_raw_sha256']:
        raise RuntimeError('constructed source qualification identity mismatch')
    result=native('legacy',[c['input'] for c in qualification],(WORK/'c1.py').read_text())
    expected=load(WORK/'c1_qualification_native.json')
    normalize=lambda r:[{k:v for k,v in x.items() if k!='elapsed_seconds'} for x in rows(r)]
    same=normalize(result)==normalize(expected)
    dump(HERE/'cold_replay.json',{'status':'REPRODUCED' if same else 'REPLAY_MISMATCH','same_rows':same,'native':result})
    if not same:raise RuntimeError('fresh-directory replay mismatch')


def bundle():
    manifest={str(p.relative_to(HERE)):digest(p) for p in sorted(HERE.rglob('*')) if p.is_file() and '__pycache__' not in p.parts and p.name not in ('evidence.zip','MANIFEST.json')}
    dump(HERE/'MANIFEST.json',manifest)
    with zipfile.ZipFile(HERE/'evidence.zip','w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(HERE.rglob('*')):
            if p.is_file() and '__pycache__' not in p.parts and p.name!='evidence.zip':z.write(p,p.relative_to(HERE))
    print('ORBIT_BUNDLE',len(manifest),digest(HERE/'evidence.zip'),flush=True)


if __name__=='__main__':
    {'prepare':prepare,'initial':initial,'learn1':learn1,'qualify1':qualify1,'learn2':learn2,'qualify2':qualify2,
     'report':report,'replay':replay,'bundle':bundle}[sys.argv[1]]()
