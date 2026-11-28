"""Three prospectively frozen strategies, matched budgets, native author tests.

API jobs write data only. Native verification jobs receive no API credential.
Learned guards are finite-qualified heuristics, never universal repair proofs.
"""
import ast
import collections
import difflib
import hashlib
import json
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import time
import zipfile

from native import HERE, build, dump, load, digest, stable, inventory, native_test, repair_green

DATA=HERE/'data'
WORK=HERE/'work'
ARMS=('adaptive','graph','guard')
MODEL='gpt-5.6-sol'
FEATURES=('failed_hits','passing_hits','lines','has_loop','has_branch','has_raise','has_index','has_call','has_boolean')
OPS=('eq','ne','gt','ge','lt','le')
BANNED={'pytest','unittest','sys','os','environ','subprocess','socket','requests','urllib','importlib',
        'inspect','builtins','__import__','exec','eval','compile','open','globals','locals','getattr',
        'setattr','__dict__','__class__','__subclasses__','__globals__','__builtins__','__code__'}

def features(packet):
    spectrum={x['id']:x for x in packet['graph']['nodes']}
    out=[]
    for f in inventory(packet['source']):
        import textwrap
        tree=ast.parse(textwrap.dedent(f['source']))
        nodes=list(ast.walk(tree));s=spectrum.get(f['id'],{})
        out.append({'id':f['id'],'failed_hits':s.get('failed_case_hits',0),'passing_hits':s.get('passing_case_hits',0),
          'lines':f['end']-f['start']+1,'has_loop':int(any(isinstance(n,(ast.For,ast.While,ast.AsyncFor)) for n in nodes)),
          'has_branch':int(any(isinstance(n,(ast.If,ast.IfExp,ast.Match)) for n in nodes)),
          'has_raise':int(any(isinstance(n,ast.Raise) for n in nodes)),
          'has_index':int(any(isinstance(n,ast.Subscript) for n in nodes)),
          'has_call':int(any(isinstance(n,ast.Call) for n in nodes)),
          'has_boolean':int(any(isinstance(n,ast.BoolOp) for n in nodes))})
    return out

def validate_guard(g):
    if not isinstance(g,dict) or set(g)!={'all'} or not isinstance(g['all'],list) or not 1<=len(g['all'])<=4:
        raise ValueError('guard grammar')
    seen=set()
    for a in g['all']:
        if not isinstance(a,dict) or set(a)!={'feature','op','value'}:raise ValueError('atom fields')
        if a['feature'] not in FEATURES or a['op'] not in OPS or type(a['value']) is not int or not 0<=a['value']<=10000:
            raise ValueError('atom value')
        if a['feature'] in seen:raise ValueError('duplicate feature')
        seen.add(a['feature'])
    # Every recommendation must be withdrawn when no failing test covers a node.
    if not any(a['feature']=='failed_hits' and ((a['op']=='gt' and a['value']>=0) or (a['op']=='ge' and a['value']>=1)) for a in g['all']):
        raise ValueError('positive failure evidence required')
    return g

def holds(g,f):
    for a in validate_guard(g)['all']:
        x,y=f[a['feature']],a['value'];op=a['op']
        if not {'eq':x==y,'ne':x!=y,'gt':x>y,'ge':x>=y,'lt':x<y,'le':x<=y}[op]:return False
    return True

def patch(source,edits):
    if not isinstance(edits,list) or not 1<=len(edits)<=4:raise ValueError('edit count')
    result=source;spans=[]
    for e in edits:
        if not isinstance(e,dict) or set(e)!={'old','new'} or not all(isinstance(e[k],str) for k in e):raise ValueError('edit fields')
        a,b=e['old'],e['new']
        if not a or a==b or len(a)>14000 or len(b)>16000 or source.count(a)!=1:raise ValueError('unique bounded original text required')
        start=source.index(a);end=start+len(a)
        if any(start<q and p<end for p,q in spans):raise ValueError('overlapping edits')
        spans.append((start,end))
    for (start,end),e in sorted(zip(spans,edits),reverse=True):result=result[:start]+e['new']+result[end:]
    before=ast.parse(source);after=ast.parse(result)
    def names(t):return {n.id for n in ast.walk(t) if isinstance(n,ast.Name)}|{n.attr for n in ast.walk(t) if isinstance(n,ast.Attribute)}
    if (names(after)-names(before))&BANNED:raise ValueError('privileged new reference')
    def imports(t):return {ast.dump(n) for n in ast.walk(t) if isinstance(n,(ast.Import,ast.ImportFrom))}
    if imports(after)-imports(before):raise ValueError('new imports')
    changes=sum(s[:1] in ('+','-') for s in difflib.ndiff(source.splitlines(),result.splitlines()))
    if changes>100:raise ValueError('100 changed-line budget exceeded')
    if len(result)>80000:raise ValueError('source size')
    return result

def decode(s):
    s=s.strip()
    if s.startswith('```'):s=s[s.find('\n')+1:];s=s[:s.rfind('```')]
    return json.loads(s)

def call(prompt,limit):
    # Caller owns a model-only job. Never execute returned code here.
    from openai import OpenAI
    started=time.monotonic()
    rec={'model':MODEL,'reasoning_effort':'low','max_output_tokens':limit,'prompt':prompt,'prompt_sha256':stable(prompt)}
    try:
        r=OpenAI(api_key=os.environ['OPENAI_API_KEY'],timeout=110,max_retries=0).responses.create(
            model=MODEL,reasoning={'effort':'low'},input=prompt,max_output_tokens=limit)
        rec.update(status='RETURNED',response=r.output_text,usage=r.usage.model_dump() if r.usage else None,
                   response_id=r.id,actual_model=r.model)
        try:rec['parsed']=decode(r.output_text)
        except (ValueError,TypeError):rec['parse_error']='INVALID_JSON'
    except Exception as e:
        # Exception strings may include request headers; retain only type/status.
        rec.update(status='UNKNOWN_API_ERROR',error_type=type(e).__name__,http_status=getattr(e,'status_code',None))
    rec['elapsed_seconds']=time.monotonic()-started
    return rec

def context():
    packets=[packet_view(load(p)) for p in sorted((DATA/'public'/'train').glob('*.json'))]
    records=receipt_view(load(WORK/'training_receipt.json'))
    return {'training_packets':packets,'training_proposal_and_native_receipt':records}

def packet_view(p):
    return {**{k:v for k,v in p.items() if k!='tests'},'test_counts':dict(collections.Counter(p['tests'].values())),
      'failing_test_ids':[k for k,v in p['tests'].items() if v=='failure'],'complete_test_outcomes_sha256':stable(p['tests'])}

def receipt_view(x):
    if isinstance(x,list):return [receipt_view(v) for v in x]
    if not isinstance(x,dict):return x
    out={}
    for k,v in x.items():
        if k=='prompt':out['prompt_omitted_from_repeated_context']=True
        elif k=='trace':out['trace_sha256']=stable(v)
        elif k=='tests':out['test_counts']=dict(collections.Counter(v.values()));out['failing_test_ids']=[n for n,t in v.items() if t=='failure'];out['complete_test_outcomes_sha256']=stable(v)
        else:out[k]=receipt_view(v)
    return out

def contract():
    return ('You repair real Python software. Author-written tests are fixed and cannot be edited. '
      'Return ONLY JSON {"decision":"PATCH"|"ABSTAIN","reason":"brief evidence",'
      '"edits":[{"old":"unique exact literal substring of ORIGINAL source","new":"replacement"}]}. '
      'Use 1-4 nonoverlapping literal replacements, at most 100 changed lines. No new imports, '
      'test introspection, process/network access, or credential access. Preserve passing behavior. '
      'If the packet already has no failing tests, ABSTAIN with empty edits. '
      'A second attempt edits the ORIGINAL source afresh, never the previous candidate. ')

def assert_cohort():
    a=load(DATA/'admission.json')
    return bool(a['train']) and len(a['future'])>=3

def train_propose():
    WORK.mkdir(exist_ok=True)
    if not assert_cohort():dump(WORK/'training_proposals.json',{'status':'UNKNOWN_INSUFFICIENT_COHORT','records':[]});return
    p=load(next((DATA/'public'/'train').glob('*.json')))
    rec=call(contract()+'\nTraining investigation. No author fix is supplied.\n'+json.dumps(packet_view(p),sort_keys=True),2400)
    dump(WORK/'training_proposals.json',{'status':'EXECUTED','records':[{'id':p['id'],'call':rec}]})

def unpack(cid,to):
    private=DATA/'private'/cid
    authority=load(private/'authority.json')
    if digest(private/'base.tar.gz')!=authority['overlay_archive_sha256']:raise ValueError('archive integrity')
    with tarfile.open(private/'base.tar.gz','r:gz') as tar:tar.extractall(to,filter='data')
    base=Path(to)/'base'
    if digest(base/authority['source_path'])!=authority['source_sha256'] or digest(base/authority['test_path'])!=authority['test_sha256']:
        raise ValueError('frozen source/test identity')
    return base,authority

def verify_one(cid,rec):
    payload=rec.get('parsed')
    if not isinstance(payload,dict):return {'status':'UNKNOWN_NO_VALID_PROPOSAL','verified':False}
    if payload.get('decision')=='ABSTAIN':return {'status':'ABSTAIN','verified':False,'reason':payload.get('reason','')}
    if payload.get('decision')!='PATCH':return {'status':'REJECTED_DECISION','verified':False}
    with tempfile.TemporaryDirectory(prefix='applicability-native-') as d:
        base,a=unpack(cid,d);path=base/a['source_path'];source=path.read_text()
        try:modified=patch(source,payload.get('edits'))
        except (ValueError,SyntaxError,TypeError) as e:return {'status':'REJECTED_PATCH_SCOPE','verified':False,'error':str(e)[:200]}
        path.write_text(modified)
        outcome=native_test(base,a['test_path'],a['source_path'],timeout=100)
        if digest(base/a['test_path'])!=a['test_sha256']:raise ValueError('test changed')
        passed=repair_green(a['native']['base'],outcome)
        return {'status':'WARRANTED_NATIVE_REPAIR' if passed else 'REJECTED_NATIVE_REPAIR' if outcome['status']=='EXECUTED' else outcome['status'],
          'verified':passed,'candidate_sha256':digest(path),'test_sha256':a['test_sha256'],'native':outcome}

def train_verify():
    src=load(WORK/'training_proposals.json');out=[]
    if src['records']:build()
    for r in src['records']:out.append({**r,'receipt':verify_one(r['id'],r['call'])})
    dump(WORK/'training_receipt.json',{'status':src['status'],'records':out})

def learn():
    ctx=context();out={}
    if not assert_cohort():dump(WORK/'strategies_raw.json',{});return
    for arm in ARMS:
        common=('From this training failure, proposal and independent native verification, derive a reusable investigation strategy. '
          'Future repositories are withheld. Do not include repository names, paths, line numbers, identifiers, test names, '
          'literal source, benchmark solutions, or case-specific constants. Strategy is advisory; future native tests remain authoritative. ')
        if arm=='adaptive':instr='Return JSON {"guidance":"up to 1600 chars"}. Use ordinary adaptive diagnosis and retry. You may rediscover better methods from raw evidence.'
        elif arm=='graph':instr=('Return JSON {"guidance":"up to 1600 chars"}. Use the supplied static call edges and measured passing/failing coverage to guide diagnosis, '
          'propagate error evidence, and check a proposed correction. This graph is not dynamic tool-argument provenance.')
        else:instr=('Return JSON {"guidance":"up to 1600 chars","guard":{"all":[{"feature":"failed_hits","op":"gt","value":0}, ...]}}. '
          'Learn a finite-checkable applicability guard over function metadata. 1-4 conjunction atoms, unique features from '+str(FEATURES)+
          ', operators '+str(OPS)+', integer values 0..10000. Include failed_hits > 0 or failed_hits >= 1. '
          'Guard must match at least one training function covered by a failing test. It must be false for every function if failing coverage is zero. '
          'Use the guard to choose where guidance applies; abstain from guard guidance outside its scope. No executable code.')
        out[arm]=call(common+instr+'\n'+json.dumps(ctx,sort_keys=True)+'\nTraining function features:\n'+json.dumps(features(ctx['training_packets'][0])),1600)
        dump(WORK/'strategies_raw.json',out)

def qualify():
    raw=load(WORK/'strategies_raw.json');out={};checks=[]
    if not raw:dump(WORK/'strategies.json',{'strategies':{},'controls':[]});return
    p=load(next((DATA/'public'/'train').glob('*.json')));fs=features(p)
    for arm in ARMS:
        r=raw[arm];x=r.get('parsed',{})
        good=isinstance(x,dict) and isinstance(x.get('guidance'),str) and 0<len(x['guidance'])<=1600
        if arm=='guard' and good:
            try:
                g=validate_guard(x.get('guard'))
                hits=[f['id'] for f in fs if holds(g,f)]
                withdrawal=all(not holds(g,{**f,'failed_hits':0}) for f in fs)
                good=bool(hits) and withdrawal
                checks.append({'positive_training_matches':hits,'all_zero_failure_withdrawal':withdrawal,
                  'checked_functions':len(fs),'scope':'Finite supplied features only; no semantic or universal validity theorem.'})
            except (ValueError,TypeError,KeyError):good=False
        out[arm]={'status':'FINITE_QUALIFIED' if good else 'REJECTED_MODULE','strategy':x if good else {},'raw_sha256':stable(r)}
    dump(WORK/'strategies.json',{'strategies':out,'controls':checks,'frozen_before_future_inference':True})
    print('FROZEN_STRATEGIES',json.dumps(out),flush=True)

def proposal_prompt(arm,p,prior=None,healthy=False):
    ctx=context();s=load(WORK/'strategies.json')['strategies'][arm]
    instruction={'adaptive':'Use ordinary adaptive reasoning; you may reconstruct any strategy from the evidence.',
      'graph':'Use graph structure and failure information to diagnose and correct the plan. Edges are static potential calls, not causal provenance.',
      'guard':'Apply the frozen guidance at matching functions. Outside the guard use ordinary adaptive reasoning; failure evidence alone does not authorize changing expected behavior.'}[arm]
    selected=[]
    if arm=='guard' and s['status']=='FINITE_QUALIFIED':selected=[f['id'] for f in features(p) if holds(s['strategy']['guard'],f)]
    return (contract()+'\n'+instruction+'\nAll arms have the same raw training history and case evidence. '
      'Do not infer a candidate is correct from a dependency graph or passing partial tests.\n'+json.dumps({
      'raw_training_history':ctx,'frozen_strategy':s,'guard_matches':selected,'case':packet_view(p),'prior_attempt':receipt_view(prior),
      'note':'Already-healthy withdrawal control; author-fixed source and all-pass evidence.' if healthy else 'Previously withheld repository; external author tests.'},sort_keys=True))

def propose(roundno):
    out={'round':roundno,'records':[],'controls':[]}
    if not assert_cohort():out['status']='UNKNOWN_INSUFFICIENT_COHORT';dump(WORK/f'proposals_{roundno}.json',out);return
    packets=[load(p) for p in sorted((DATA/'public'/'future').glob('*.json'))]
    previous=load(WORK/'receipt_1.json') if roundno==2 else None
    for i,p in enumerate(packets):
        order=ARMS[i%3:]+ARMS[:i%3]
        for arm in order:
            prior=next((r for r in previous['records'] if r['id']==p['id'] and r['arm']==arm),None) if previous else None
            if prior and prior['receipt']['verified']:continue
            # Only a strategy's own previous attempt is revealed; no cross-arm feedback.
            prompt=proposal_prompt(arm,p,prior)
            r={'id':p['id'],'arm':arm,'call':call(prompt,2400)}
            out['records'].append(r);dump(WORK/f'proposals_{roundno}.json',out)
            print('MODEL_RETURN',roundno,p['id'],arm,r['call']['status'],flush=True)
    dump(WORK/f'proposals_{roundno}.json',out)

def verify(roundno):
    src=load(WORK/f'proposals_{roundno}.json');out={'round':roundno,'records':[]}
    if src['records']:out['environment']=build()
    for r in src['records']:
        result=verify_one(r['id'],r['call'])
        out['records'].append({**r,'receipt':result});dump(WORK/f'receipt_{roundno}.json',out)
        native=result.get('native',{});counts=dict(collections.Counter(native.get('tests',{}).values()))
        print('NATIVE_RESULT',roundno,r['id'],r['arm'],result['status'],json.dumps(counts),flush=True)
    dump(WORK/f'receipt_{roundno}.json',out)

def final():
    a=load(DATA/'admission.json');strategies=load(WORK/'strategies.json');raw=load(WORK/'strategies_raw.json')
    rounds=[load(WORK/f'receipt_{i}.json') for i in (1,2)]
    rows=[];scores={arm:{'verified_repairs':0,'future_cases':len(a['future']),'repair_calls':0,'input_tokens':0,'output_tokens':0,'preparation_calls':int(arm in raw)} for arm in ARMS}
    for c in a['future']:
        row={'id':c['id'],'repo':c['repo'],'pr':c['pr'],'authority':c}
        for arm in ARMS:
            rs=[r for rnd in rounds for r in rnd['records'] if r['id']==c['id'] and r['arm']==arm]
            good=any(r['receipt']['verified'] for r in rs)
            scores[arm]['verified_repairs']+=int(good);scores[arm]['repair_calls']+=len(rs)
            row[arm]={'verified':good,'attempts':[r['receipt']['status'] for r in rs]}
            for r in rs:
                u=r['call'].get('usage') or {};scores[arm]['input_tokens']+=u.get('input_tokens',0);scores[arm]['output_tokens']+=u.get('output_tokens',0)
        rows.append(row)
    for arm,r in raw.items():
        u=r.get('usage') or {};scores[arm]['input_tokens']+=u.get('input_tokens',0);scores[arm]['output_tokens']+=u.get('output_tokens',0)
    enough=len(a['future'])>=3
    benefit=enough and scores['guard']['verified_repairs']>max(scores[x]['verified_repairs'] for x in ('adaptive','graph'))
    summary={'status':'CANDIDATE_BOUNDED_ADVANTAGE' if benefit else 'NO_VERIFIED_ADVANTAGE' if enough else 'UNKNOWN_INSUFFICIENT_COHORT',
      'run_id':os.environ.get('GITHUB_RUN_ID'),'source_sha':os.environ.get('GITHUB_SHA'),'rows':rows,'scores':scores,'strategies':strategies,
      'equal_caps':{'preparation_calls_per_arm':1,'preparation_output_tokens':1600,'repair_calls_per_case_per_arm':2,'repair_output_tokens_per_call':2400},
      'limits':['Published defects; model pretraining exposure not ruled out.','Small prospective cohort and one model draw per strategy/case; no population inference.',
        'Only selected author regression files; not complete software correctness.','Static call/coverage graph is not a reproduction of Bundy tool dependency graphs.',
        'Guard restricted to an engineered feature grammar; finite withdrawal checks are not semantic proofs or new concept-language invention.',
        'No independent author-intent evidence beyond test assertions; no specification repair claim.',
        'Equal call/output caps; observed token and runtime consumption may differ. Shared training investigation is common to all arms.']}
    dump(WORK/'summary.json',summary)
    # A separate, deterministic preservation control: no failing evidence implies no admissible guard recommendation.
    if strategies.get('strategies',{}).get('guard',{}).get('status')=='FINITE_QUALIFIED':
        g=strategies['strategies']['guard']['strategy']['guard'];controls=[]
        for p in sorted((DATA/'public'/'future').glob('*.json')):
            packet=load(p);fs=features(packet)
            controls.append({'id':packet['id'],'checked_functions':len(fs),'guard_recommendations_with_failures':sum(holds(g,f) for f in fs),
              'guard_recommendations_if_no_failures':sum(holds(g,{**f,'failed_hits':0}) for f in fs)})
        dump(WORK/'withdrawal_controls.json',controls)
    evidence=HERE/'evidence';evidence.mkdir(exist_ok=True)
    import shutil
    for root in (DATA,WORK):
        for p in root.rglob('*.json'):
            dest=evidence/root.name/p.relative_to(root);dest.parent.mkdir(parents=True,exist_ok=True)
            x=load(p)
            # Portable receipt retains full per-test verdicts, source, proposals,
            # diagnostics and hashes; bulky per-line traces stay in full artifacts.
            def trim(v):
                if isinstance(v,list):return [trim(t) for t in v]
                if not isinstance(v,dict):return v
                return {k:trim(t) for k,t in v.items() if k!='trace'}|({'trace_sha256':stable(v['trace'])} if 'trace' in v else {})
            dump(dest,trim(x))
    for p in HERE.glob('*.py'):shutil.copyfile(p,evidence/p.name)
    for name in ('PROTOCOL.md','Dockerfile'):shutil.copyfile(HERE/name,evidence/name)
    manifest={str(p.relative_to(evidence)):digest(p) for p in sorted(evidence.rglob('*')) if p.is_file()}
    dump(evidence/'MANIFEST.json',manifest)
    with zipfile.ZipFile(HERE/'evidence.zip','w',compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(evidence.rglob('*')):
            if p.is_file():z.write(p,p.relative_to(evidence))
    print('FINAL_SUMMARY',json.dumps(summary,sort_keys=True),flush=True)
    print('EVIDENCE_ZIP_SHA256',digest(HERE/'evidence.zip'),flush=True)
    # Credential-free, checksummed recovery via logs; full source archives remain in the frozen-data artifact.
    import base64
    b64=base64.b64encode((HERE/'evidence.zip').read_bytes()).decode()
    print('EVIDENCE_B64_LENGTH',len(b64),flush=True)
    for i in range(0,len(b64),12000):print('EVIDENCE_B64',i,b64[i:i+12000],flush=True)

if __name__=='__main__':
    command=sys.argv[1]
    {'train_propose':train_propose,'train_verify':train_verify,'learn':learn,'qualify':qualify,
     'propose_1':lambda:propose(1),'verify_1':lambda:verify(1),'propose_2':lambda:propose(2),
     'verify_2':lambda:verify(2),'final':final}[command]()
