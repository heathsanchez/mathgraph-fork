"""Frozen one-task prospective transfer diagnostic. No inference retries."""
import ast, hashlib, json, os, shutil, subprocess, sys, tarfile, tempfile, time, urllib.request, zipfile
from pathlib import Path
HERE=Path(__file__).resolve().parent
DATA=HERE/'data'; WORK=HERE/'work'
IMAGE='retained-method-funcy:20261129'
MODEL='gpt-6.2-sol'
ORDER=['retained-0','removed-0','conventional-0','conventional-1','removed-1','retained-1','removed-2','retained-2','conventional-2']
COMMON='''Investigate and repair a real historical Python library regression. You have the same native probe interface and budget as other independently run investigators; do not assume any particular solution or claim a result before testing.
Problem: When a Funcy decorator wraps an already-bound instance or class method, named argument access counts the supplied receiver again. Reading call.x from a decorated instance.method(1) can raise AttributeError or return the next argument instead. Preserve the library's other call-argument behavior.
You receive the exact original funcy/decorators.py below. You can execute ordinary Python to inspect/probe the original package. All stdlib and funcy source under /target/funcy are available; no test, author fix, network or service credentials are available. Probes may build examples, compare hypotheses and try possible implementations in memory. Use print for observations.
Return ONLY JSON, either {"action":"probe","source":"complete Python diagnostic script"}, {"action":"final","source":"complete replacement def arggetter(func, _cache={}): ..."}, or {"action":"decline","reason":"..."}. Final source must define ONLY arggetter, with the original signature. Existing module globals (including inspect, unwrap and omit) remain. Use nested helpers if needed. No external I/O, process/network access, dynamic eval/exec/compile in final code, test/pytest manipulation or answer tables. Model-written probe scripts can use exec for legitimate runtime examples.
At most four model calls and three bounded probe scripts, each 20 seconds. At most 4500 output tokens per call and 60000 total API tokens. You may finalize immediately. A final or invalid response terminates this trajectory. Hidden maintainer tests and preservation checks are run only after all investigators have finished; no retry after hidden results.
'''
NOTES={
'retained':'''Retained investigation recipe distilled from a previously qualified, different-library correction: keep the original input and its surrounding context available; before composing a local intervention, use contrast probes to determine how the unchanged operation interprets that context. Check that the intervention preserves already-correct cases. This is a fallible reusable recipe, not evidence of the answer to this task.''',
'removed':'',
'conventional':'''Act as a competent conventional software investigator. Use the source, Python semantics and any ordinary debugging, inspection, hypothesis testing or reconstruction you find effective. Check regressions and preservation. You have full freedom to invent or rediscover methods; no method is reserved for another arm.'''}
def dump(path,obj,exclusive=False):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x' if exclusive else 'w') as f:json.dump(obj,f,ensure_ascii=False,sort_keys=True,indent=2);f.write('\n')
def load(path):return json.loads(path.read_text())
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def stable(obj):return hashlib.sha256(json.dumps(obj,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
def binding():return {p.name:digest(p) for p in HERE.iterdir() if p.is_file() and p.name in ('pipeline.py','worker.py','identity.json','PROTOCOL.md','Dockerfile','test_guards.py')}
def guard():
    f=load(DATA/'freeze.json');assert binding()==f['code']
    for p,h in f['source'].items():assert digest(DATA/p)==h,p
    return f
def native(root,mode,source=None,timeout=120):
    with tempfile.TemporaryDirectory(prefix='retained-native-') as d:
        temp=Path(d);temp.chmod(0o755);out=temp/'out';out.mkdir();out.chmod(0o777)
        dump(temp/'request.json',{'mode':mode,'source':source})
        cmd=['docker','run','--rm','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges','--pids-limit','64','--memory','700m','--cpus','1','--tmpfs','/tmp:rw,nosuid,nodev,size=64m','-v',str(root.resolve())+':/target:ro','-v',str(temp/'request.json')+':/request.json:ro','-v',str(out)+':/out:rw',IMAGE]
        start=time.monotonic()
        try:
            p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=timeout,env={k:v for k,v in os.environ.items() if k not in ('OPENAI_API_KEY','GITHUB_TOKEN')})
            result=load(out/'result.json') if (out/'result.json').exists() else {'status':'UNKNOWN_NO_RECEIPT','returncode':p.returncode,'diagnostic':(p.stdout+p.stderr)[-12000:]}
        except subprocess.TimeoutExpired:result={'status':'UNKNOWN_TIMEOUT'}
        result['elapsed_seconds']=time.monotonic()-start
        return result

def unpack(pin,label,expected):
    target=DATA/label
    if target.exists():raise ValueError('source destination already exists')
    archive=DATA/(label+'.tar.gz')
    with urllib.request.urlopen('https://codeload.github.com/Suor/funcy/tar.gz/'+pin,timeout=60) as r:archive.write_bytes(r.read())
    with tarfile.open(archive) as tf:
        members=tf.getmembers();prefix=members[0].name.split('/')[0]
        for m in members:
            rel=Path(m.name).relative_to(prefix)
            if '..' in rel.parts or m.issym() or m.islnk() or not(m.isdir() or m.isfile()):raise ValueError('unsafe source archive')
            p=target/rel
            if m.isdir():p.mkdir(parents=True,exist_ok=True)
            elif m.isfile():p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(tf.extractfile(m).read())
    checked={}
    for e in expected:
        if e['type']!='blob':continue
        p=target/e['path'];b=p.read_bytes()
        assert hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()==e['sha'],e['path']
        checked[e['path']]={'git_blob':e['sha'],'sha256':digest(p)}
    actual={str(p.relative_to(target)) for p in target.rglob('*') if p.is_file()}
    assert actual==set(checked),'unexpected source files'
    return {'source_sha':pin,'archive_sha256':digest(archive),'files':checked}

def prepare():
    DATA.mkdir();WORK.mkdir()
    identity=load(HERE/'identity.json');identities={}
    for label,key in [('original','base'),('author','head')]:identities[label]=unpack(identity[key],label,identity[key+'_entries'])
    dump(DATA/'authenticated.json',identities)
    built=subprocess.run(['docker','build','-t',IMAGE,str(HERE)],text=True,capture_output=True)
    dump(WORK/'docker-build.json',{'returncode':built.returncode,'stdout':built.stdout,'stderr':built.stderr})
    assert built.returncode==0,'native image unavailable'
    image=subprocess.check_output(['docker','image','inspect',IMAGE,'--format','{{.Id}}'],text=True).strip()
    shutil.copytree(DATA/'original',DATA/'oracle')
    shutil.copyfile(DATA/'author/tests/test_decorators.py',DATA/'oracle/tests/test_decorators.py')
    controls={name:native(DATA/name,'tests') for name in ('original','oracle','author')}
    dump(WORK/'controls.json',controls)
    assert controls['original'].get('returncode')==0,'original baseline not clean'
    assert controls['author'].get('returncode')==0,'author control not clean'
    assert controls['oracle'].get('returncode')==1,'no original regression established'
    basepass={k for k,v in controls['original']['rows'].items() if v.get('call')=='passed'}
    authorpass={k for k,v in controls['author']['rows'].items() if v.get('call')=='passed'}
    bad={k for k,v in controls['oracle']['rows'].items() if 'failed' in v.values()}
    assert bad and not(bad&basepass) and basepass<=authorpass
    assert set(controls['oracle']['rows'])==set(controls['author']['rows'])
    # Probe runtime contains package bytes only, never either test tree or author source.
    probe=DATA/'probe';probe.mkdir();shutil.copytree(DATA/'original/funcy',probe/'funcy')
    source={str(p.relative_to(DATA)):digest(p) for p in DATA.rglob('*') if p.is_file()}
    frozen={'code':binding(),'source':source,'identity':identity,'image':image,'host_python':sys.version,'baseline_passes':sorted(basepass),'required_ids':sorted(controls['author']['rows']),'required_cases':sorted(authorpass),'regression_ids':sorted(bad),'order':ORDER,'boundaries':{'one_task_only':True,'recipe_distilled_by_investigator':True,'global_unopened':'UNKNOWN'}}
    dump(DATA/'freeze.json',frozen,True)
    print('TASK_ADMITTED',len(basepass),len(authorpass),len(bad),'FREEZE',digest(DATA/'freeze.json'),flush=True)


def parse_action(text):
    t=text.strip()
    if t.startswith('```'):t=t[t.find('\n')+1:t.rfind('```')]
    action=json.loads(t)
    assert isinstance(action,dict) and action.get('action') in ('probe','final','decline')
    if action['action']!='decline':assert isinstance(action.get('source'),str) and len(action['source'])<=40000
    return action

def patch(original,source):
    tree=ast.parse(source)
    assert len(tree.body)==1 and isinstance(tree.body[0],ast.FunctionDef) and tree.body[0].name=='arggetter','one function only'
    f=tree.body[0];old=next(n for n in ast.parse(original).body if isinstance(n,ast.FunctionDef) and n.name=='arggetter')
    assert ast.dump(f.args)==ast.dump(old.args),'signature changed'
    forbidden={'open','eval','exec','compile','__import__','setattr','globals','locals','breakpoint'}
    allowed_import={'inspect','functools','collections','types'}
    for n in ast.walk(f):
        if isinstance(n,ast.Name):assert n.id not in forbidden,n.id
        if isinstance(n,ast.Attribute):assert not n.attr.startswith('__') or n.attr in ('__code__','__defaults__','__kwdefaults__','__original__','__func__','__self__','__name__','__wrapped__'),n.attr
        if isinstance(n,(ast.Import,ast.ImportFrom)):
            names=[a.name.split('.')[0] for a in n.names] if isinstance(n,ast.Import) else [(n.module or '').split('.')[0]]
            assert set(names)<=allowed_import,'external import'
        if isinstance(n,ast.Constant) and isinstance(n.value,str):assert not any(t in n.value.lower() for t in ('pytest','/out','/target/tests','test_decorators','request.json'))
    lines=original.splitlines(keepends=True)
    return ''.join(lines[:old.lineno-1])+source.rstrip()+'\n'+''.join(lines[old.end_lineno:])

def call(prompt):
    from openai import OpenAI
    start=time.monotonic();record={'model':MODEL,'prompt':prompt,'prompt_sha256':stable(prompt),'max_output_tokens':4500,'reasoning_effort':'low'}
    try:
        r=OpenAI(api_key=os.environ['OPENAI_API_KEY'],timeout=180,max_retries=0).responses.create(model=MODEL,input=prompt,reasoning={'effort':'low'},max_output_tokens=4500)
        record.update(status='RETURNED',response=r.output_text,response_id=r.id,actual_model=r.model,usage=r.usage.model_dump() if r.usage else None)
    except Exception as e:record.update(status='UNKNOWN_API',error_type=type(e).__name__,http_status=getattr(e,'status_code',None))
    record['elapsed_seconds']=time.monotonic()-start
    return record

def learn():
    guard();source=(DATA/'original/funcy/decorators.py').read_text()
    assert not (WORK/'response-seal.json').exists(),'already completed'
    for key in ORDER:
        arm=key.split('-')[0];history=[];used=0;total=0;terminal='BUDGET_STOP'
        for turn in range(4):
            prompt=COMMON+'\n'+NOTES[arm]+'\nExact original module:\n'+source+'\nYour own earlier actions and native observations:\n'+json.dumps(history,ensure_ascii=False)
            if len(prompt.encode())>65000:terminal='UNKNOWN_INPUT_BUDGET';break
            path=WORK/'responses'/f'{key}-{turn}.json'
            if path.exists():raise ValueError('no trajectory resampling')
            r=call(prompt);dump(path,r,True)
            print('MODEL_RESPONSE',key,turn,r['status'],flush=True)
            total+=int((r.get('usage') or {}).get('total_tokens',0))
            if r['status']!='RETURNED':terminal='UNKNOWN_API';break
            if total>60000:terminal='UNKNOWN_TOKEN_CAP';break
            try:a=parse_action(r['response'])
            except (ValueError,AssertionError,KeyError,TypeError):terminal='INVALID_RESPONSE';break
            if a['action']=='decline':terminal='DECLINED';break
            if a['action']=='final':
                try:replacement=patch(source,a['source'])
                except (SyntaxError,AssertionError,ValueError) as e:terminal='REJECTED_PATCH_BOUNDARY';break
                (WORK/'candidates').mkdir(exist_ok=True)
                (WORK/'candidates'/f'{key}.py').write_text(replacement)
                terminal='FINAL_SEALED';break
            if used>=3:terminal='PROBE_BUDGET_STOP';break
            result=native(DATA/'probe','probe',a['source'],20);used+=1
            dump(WORK/'probes'/f'{key}-{turn}.json',{'action':a,'native':result},True)
            history.append({'response':a,'observation':result})
        dump(WORK/'trajectories'/f'{key}.json',{'key':key,'terminal':terminal,'api_tokens':total,'native_actions':used},True)
        print('TRAJECTORY',key,terminal,total,used,flush=True)
    seal={str(p.relative_to(WORK)):digest(p) for folder in ('responses','candidates','probes','trajectories') for p in (WORK/folder).glob('*') if p.is_file()}
    dump(WORK/'response-seal.json',{'manifest':seal,'order':ORDER,'before_hidden_judging':True},True)
    print('ALL_RESPONSES_SEALED',digest(WORK/'response-seal.json'),flush=True)

def score(r):
    frozen=guard();expected=set(frozen['required_cases']);rows=r.get('rows',{})
    passed={k for k,v in rows.items() if v.get('call')=='passed'}
    return {'qualified':r.get('status')=='EXECUTED' and r.get('returncode')==0 and set(rows)==set(frozen['required_ids']) and passed==expected and not any('failed' in v.values() for v in rows.values()),'status':r.get('status'),'required':len(expected),'passed':len(passed),'missing':sorted(expected-passed),'new':sorted(passed-expected),'baseline_preserved':set(frozen['baseline_passes'])<=passed}

def normalized(r):return {k:r.get(k) for k in ('status','returncode','rows')}
def qualify():
    guard();seal=load(WORK/'response-seal.json')
    assert seal['order']==ORDER
    for p,h in seal['manifest'].items():assert digest(WORK/p)==h
    outcomes={}
    for key in ORDER:
        tr=load(WORK/'trajectories'/f'{key}.json');candidate=WORK/'candidates'/f'{key}.py'
        if not candidate.exists():outcomes[key]={**tr,'qualified':False,'operational_status':tr['terminal']};continue
        with tempfile.TemporaryDirectory(prefix='retained-judge-') as d:
            root=Path(d)/'target';shutil.copytree(DATA/'oracle',root)
            target=root/'funcy/decorators.py';target.write_bytes(candidate.read_bytes())
            r=native(root,'tests');dump(WORK/'judgments'/f'{key}.json',r,True)
            verdict=score(r)
            if verdict['qualified']:
                target.write_bytes((DATA/'original/funcy/decorators.py').read_bytes());withdraw=native(root,'tests')
                target.write_bytes(candidate.read_bytes());restore=native(root,'tests')
                dump(WORK/'causal'/f'{key}.json',{'withdraw':withdraw,'restore':restore},True)
                verdict['withdrawal_reproduces_baseline']=normalized(withdraw)==normalized(load(WORK/'controls.json')['oracle'])
                verdict['restoration_identical']=normalized(restore)==normalized(r)
                verdict['qualified'] &= verdict['withdrawal_reproduces_baseline'] and verdict['restoration_identical']
            outcomes[key]={**tr,**verdict,'candidate_sha256':digest(candidate)}
            print('QUALIFIED',key,verdict['qualified'],verdict['passed'],verdict['required'],flush=True)
    responses=[load(p) for p in (WORK/'responses').glob('*.json')]
    summary={'outcomes':outcomes,'counts':{a:sum(v['qualified'] for k,v in outcomes.items() if k.startswith(a+'-')) for a in NOTES},'api_calls':len(responses),'input_tokens':sum((r.get('usage') or {}).get('input_tokens',0) for r in responses),'output_tokens':sum((r.get('usage') or {}).get('output_tokens',0) for r in responses),'model_seconds':sum(r['elapsed_seconds'] for r in responses),'native_actions':sum(v['native_actions'] for v in outcomes.values()),'one_task_only':True,'population_advantage':'UNKNOWN','autonomous_acquisition':'NOT_TESTED','scope':'investigator-distilled textual recipe transfer; scoped nonexposure only','source_freeze':digest(DATA/'freeze.json'),'response_seal':digest(WORK/'response-seal.json')}
    dump(WORK/'summary.json',summary,True);print('TRIAL_SUMMARY',json.dumps(summary),flush=True)

def replay():
    guard();source=load(WORK/'summary.json');verdicts={}
    for key in ORDER:
        if not source['outcomes'][key].get('candidate_sha256'):continue
        with tempfile.TemporaryDirectory(prefix='retained-cold-') as d:
            root=Path(d)/'target';shutil.copytree(DATA/'oracle',root)
            (root/'funcy/decorators.py').write_bytes((WORK/'candidates'/f'{key}.py').read_bytes())
            r=native(root,'tests');old=load(WORK/'judgments'/f'{key}.json')
            verdicts[key]={'verdict_same':score(r)['qualified']==score(old)['qualified'],'rows_same':r.get('rows')==old.get('rows'),'status_same':r.get('status')==old.get('status') and r.get('returncode')==old.get('returncode')}
            assert all(verdicts[key].values()),key
    dump(WORK/'fresh-replay.json',verdicts,True);print('FRESH_REPLAY',len(verdicts),flush=True)

def bundle():
    manifest={str(p.relative_to(HERE)):digest(p) for p in HERE.rglob('*') if p.is_file() and p.name not in ('evidence.zip','MANIFEST.json') and '__pycache__' not in p.parts}
    dump(HERE/'MANIFEST.json',manifest)
    with zipfile.ZipFile(HERE/'evidence.zip','w',zipfile.ZIP_DEFLATED) as z:
        for p in [HERE/k for k in manifest]+[HERE/'MANIFEST.json']:z.write(p,p.relative_to(HERE))
    print('EVIDENCE',len(manifest),digest(HERE/'evidence.zip'),flush=True)

if __name__=='__main__':{'prepare':prepare,'learn':learn,'qualify':qualify,'replay':replay,'bundle':bundle}[sys.argv[1]]()
