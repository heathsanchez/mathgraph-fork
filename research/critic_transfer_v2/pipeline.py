"""Acquire, independently qualify, freeze, and causally reuse a real critic.

The executable programs are candidates, not proofs. Future gold observations
are withheld from programs; a conventional method may tie or beat acquisition.
"""
import ast
import base64
import collections
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import zipfile
import admit_legacy as git
from native import HERE, IMAGE, build, dump, load, digest, stable
from core import validate_program,choose_context,verified_rejection

DATA=HERE/'data';WORK=HERE/'work';PRIOR=HERE/'prior'
MODEL='gpt-5.6-sol'
TRAIN_CONTRACT='Unescape the markup, remove tags, and normalize whitespace to single spaces. The result is the completed plain text.'
TRAIN_CASES=[('A <b> </b> B','A B'),('A <!-- x --> B','A B'),(' A <b> B </b> C ','A B C'),
 ('A<b>\t</b>B','A B'),('A<!-- \nignored --> \n B','A B'),('A <b></b> B','A B'),
 ('A B','A B'),(' A  \t B ','A B'),('A<b>B</b>C','ABC'),('A &amp; B','A & B'),('A<br>B','AB'),('A<!--ignored-->B','AB')]
FTFY_REPO='rspeer/python-ftfy'
FTFY_OLD='4f6a2d05ab395a43aad3541bd3571bf2aa701307'
FTFY_AUTHOR='e404191fe210acf324bee1beeab5619434488b98'
W3_REPO='scrapy/w3lib';W3_AUTHOR='1e4960e9a6494d8c5192744c6cdda28401b1fb8a'
W3_OLD_REFS=('v2.1.2','2.1.2')

def sandbox(tree,request,timeout=120):
    """No credentials, network, writable source, or host code execution."""
    dump(tree/'request.json',request)
    with tempfile.TemporaryDirectory(prefix='critic-out-') as d:
        out=Path(d);out.chmod(0o777)
        command=['docker','run','--rm','--network','none','--cap-drop','ALL','--security-opt','no-new-privileges',
          '--pids-limit','128','--memory','1400m','--cpus','2','--read-only','--user','65534:65534',
          '--tmpfs','/tmp:rw,nosuid,nodev,size=256m','-v',str(tree.resolve())+':/work:ro','-v',str(out.resolve())+':/out:rw',
          '-e','HOME=/tmp','-e','PYTHONDONTWRITEBYTECODE=1','-e','PYTHONPATH=/harness:/work/src:/work',
          '-w','/work',IMAGE,'python','/harness/worker.py']
        started=time.monotonic()
        try:p=subprocess.run(command,capture_output=True,text=True,timeout=timeout)
        except subprocess.TimeoutExpired:return {'status':'UNKNOWN_TIMEOUT','elapsed':time.monotonic()-started}
        q=out/'result.json'
        result=load(q) if q.exists() else {'status':'UNKNOWN_MISSING_RECEIPT'}
        return {**result,'native_returncode':p.returncode,'elapsed':time.monotonic()-started,
          'stderr':p.stderr[-1200:],'request_sha256':stable(request)}

def apply_edits(source,edits):
    spans=[]
    for e in edits:
        assert source.count(e['old'])==1
        spans.append((source.index(e['old']),len(e['old']),e['new']))
    for i,n,new in sorted(spans,reverse=True):source=source[:i]+new+source[i+n:]
    ast.parse(source);return source

def train():
    DATA.mkdir(exist_ok=True);env=build()
    a=load(PRIOR/'frozen/private/future-04/authority.json');p=load(PRIOR/'frozen/public/future/future-04.json')
    proposals=load(PRIOR/'proposals/proposals_1.json')
    bad=next(r for r in proposals['records'] if r['id']=='future-04' and r['arm']=='graph')
    author=base64.b64decode(git.api(a['repo'],'git/blobs/'+a['head_blob'])['content']).decode()
    badsrc=apply_edits(p['source'],bad['call']['parsed']['edits'])
    observations={};variants={'incomplete_candidate':badsrc,'author':author}
    for name,source in variants.items():
        d=DATA/'training'/name;d.mkdir(parents=True,exist_ok=True)
        with tarfile.open(PRIOR/'frozen/private/future-04/base.tar.gz','r:gz') as t:t.extractall(d,filter='data')
        tree=d/'base';(tree/a['source_path']).write_text(source)
        req={'mode':'training','target':{'kind':'markupsafe'},'cases':[{'input':x,'expected':y} for x,y in TRAIN_CASES]}
        r=sandbox(tree,req);dump(DATA/'training'/name/'observations.json',r)
        if r.get('native_returncode')!=0 or not r.get('observations'):raise RuntimeError('training native authority unavailable')
        observations[name]=r['observations']
    def method(source):
        i=source.index('    def striptags');end=source.index('\n    @classmethod',i)
        return source[i:end]
    packet={'source_sha':os.environ.get('GITHUB_SHA'),'contract':TRAIN_CONTRACT,
      'native_observations':observations,'incomplete_method':method(badsrc),'author_method':method(author),
      'legacy_boundary':'Both candidates passed the original 25 author tests, with 5 skips. Additional semantic cases reveal four remaining mistakes.',
      'environment':env,'scope':'Exposed prior MarkupSafe development evidence only; future source/test cases withheld.'}
    dump(DATA/'training_public.json',packet);dump(DATA/'environment.json',env)
    print('TRAINING_NATIVE_READY',len(TRAIN_CASES),flush=True)

PROMPT='''You are constructing an executable diagnostic and repair method from a verified failure, not writing advice.
The training repair passed its original test suite but violates its documented contract on some additional cases.
Infer a reusable failure mechanism. You will later receive a black-box callable observe(string)->string, a seed string,
and the future operation's author contract as plain text. Future libraries, inputs and answers are withheld.

Return ONLY JSON {"description":"what you learned and its limits", "source":"Python source"}.
The source must contain exactly these three top-level functions with no imports, annotations, decorators, defaults or classes:
def applies(contract):
    ... return bool
def diagnose(observe, seed, contract):
    ... return {"trigger": bool}
def repair(observe, seed, contract):
    ... return repaired_string_or_None

Use normal pure Python loops, comparisons and string operations, with at most 12 total observe calls per seed across diagnosis and repair.
You may compose existing operation calls to construct a new executor, but any returned repair must be one of the actual observe outputs.
The diagnostic must justify a contract-supported failure using black-box observations; absence of a counterexample is UNKNOWN, not proof of correctness.
Apply the method only where the contract supports its semantic assumptions. For a single-layer decoder or missing specification, applies must be false.
An inapplicable method is disabled by the host and ordinary execution continues. Never stop unrelated work.
Do not hardcode names of packages, functions, cases, expected answers, particular letters, separators, or MarkupSafe-specific whitespace edits.
Use the contract and observed behavior to generalize. This is a bounded method-construction test; a conventional method may reconstruct the same idea.
'''

def api_call(prompt):
    from openai import OpenAI
    start=time.monotonic();r={'prompt':prompt,'prompt_sha256':stable(prompt),'model':MODEL,'max_output_tokens':6000,'reasoning_effort':'low'}
    try:
        x=OpenAI(api_key=os.environ['OPENAI_API_KEY'],timeout=120,max_retries=0).responses.create(model=MODEL,reasoning={'effort':'low'},input=prompt,max_output_tokens=6000)
        text=x.output_text.strip();r.update(status='RETURNED',response=text,usage=x.usage.model_dump() if x.usage else {},response_id=x.id,actual_model=x.model)
        if text.startswith('```'):text=text[text.index('\n')+1:text.rfind('```')]
        try:r['parsed']=json.loads(text)
        except ValueError:r['parse_error']='INVALID_JSON'
    except Exception as e:r.update(status='UNKNOWN_API_ERROR',error_type=type(e).__name__,http_status=getattr(e,'status_code',None))
    r['elapsed']=time.monotonic()-start;return r

def learn():
    WORK.mkdir(exist_ok=True);packet=load(DATA/'training_public.json');out={}
    # Same raw evidence and one equal-budget acquisition call. The cold control
    # never sees the retained method; later outcomes cannot alter either program.
    prompt=PROMPT+'\nVerified exposed training evidence:\n'+json.dumps(packet,sort_keys=True)
    for arm in ('retained','cold'):
        out[arm]=api_call(prompt);dump(WORK/'raw_programs.json',out)
        print('METHOD_CONSTRUCTED',arm,out[arm]['status'],flush=True)

def qualify():
    build();raw=load(WORK/'raw_programs.json');programs={};q={}
    for arm,r in raw.items():
        try:
            src=r['parsed']['source'];sha=validate_program(src);programs[arm]=src;q[arm]={'source_sha256':sha}
        except (ValueError,KeyError,TypeError,SyntaxError) as e:q[arm]={'status':'REJECTED_PROGRAM','error':type(e).__name__}
    for variant in ('incomplete_candidate','author'):
        req={'mode':'qualify','target':{'kind':'markupsafe'},'contract':TRAIN_CONTRACT,'programs':programs,
             'cases':[{'input':x,'expected':y} for x,y in TRAIN_CASES]}
        r=sandbox(DATA/'training'/variant/'base',req);dump(WORK/f'qualification_{variant}.json',r)
        for arm in programs:q[arm][variant]=r.get(arm,{'status':'UNKNOWN_NATIVE_QUALIFICATION'})
    valid={}
    for arm,src in programs.items():
        b=q[arm]['incomplete_candidate'];g=q[arm]['author']
        br=b.get('rows',[]);gr=g.get('rows',[])
        reject=any(verified_rejection(x) for x in br)
        preserve=len(gr)==len(TRAIN_CASES) and all(x.get('result_matches_author') is True for x in gr)
        no_false=all(x['status']!='OBSERVED_REJECTION' for x in gr)
        scope=bool(g.get('scope_controls')) and all(not x['applies'] for x in g['scope_controls'])
        q[arm].update(status='FINITE_QUALIFIED' if reject and preserve and no_false and scope else 'REJECTED_QUALIFICATION',
          detects_exposed_failure=reject,preserves_author_cases=preserve,scope_withdrawal=scope,
          boundary='Finite native qualification only; no universal applicability or repair theorem.')
        if q[arm]['status']=='FINITE_QUALIFIED':valid[arm]=src
    dump(WORK/'qualified_programs.json',{'source_sha':os.environ.get('GITHUB_SHA'),'programs':valid,'qualification':q,
      'future_data_not_opened':True,'frozen_sha256':stable(valid)})
    print('PROGRAM_FREEZE',json.dumps({a:{k:v for k,v in r.items() if k not in ('incomplete_candidate','author')} for a,r in q.items()}),flush=True)

def archive(repo,sha,label):
    dest=DATA/'future_sources'/label;dest.mkdir(parents=True,exist_ok=True)
    root,h=git.safe_archive(repo,sha,dest)
    dump(dest/'source_identity.json',{'repo':repo,'sha':sha,'tar_sha256':h})
    return root

def literal_assertions(path,name):
    tree=ast.parse(path.read_text());rows=[];seen=set()
    for n in ast.walk(tree):
        if not isinstance(n,ast.Assert) or not isinstance(n.test,ast.Compare) or len(n.test.comparators)!=1 or not isinstance(n.test.ops[0],ast.Eq):continue
        c=n.test.left;rhs=n.test.comparators[0]
        if not isinstance(c,ast.Call) or c.keywords or len(c.args)!=1:continue
        called=c.func.id if isinstance(c.func,ast.Name) else c.func.attr if isinstance(c.func,ast.Attribute) else None
        if called!=name:continue
        try:x=ast.literal_eval(c.args[0]);y=ast.literal_eval(rhs)
        except (ValueError,TypeError):continue
        if not isinstance(x,str) or not isinstance(y,str) or len(x)>2048 or len(y)>4096 or x in seen:continue
        rows.append({'input':x,'expected':y,'author_test_line':n.lineno});seen.add(x)
        if len(rows)>=100:break
    return rows

def future():
    build();frozen=load(WORK/'qualified_programs.json');programs=frozen['programs']
    DATA.mkdir(exist_ok=True);attempts=[];groups=[]
    # Opening future sources occurs only after the executable critic is frozen.
    ftfy_author=archive(FTFY_REPO,FTFY_AUTHOR,'ftfy-author');ftfy_old=archive(FTFY_REPO,FTFY_OLD,'ftfy-legacy')
    rawtests=(ftfy_author/'tests/test_real_tweets.py').read_text();parsed=ast.parse(rawtests);pairs=None
    for n in parsed.body:
        if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='TEST_CASES' for t in n.targets):pairs=ast.literal_eval(n.value)
    assert pairs
    ftcases=[]
    for x,y in pairs:
        ftcases.append({'input':x,'expected':y,'author_fixture':'tests/test_real_tweets.py TEST_CASES'})
        ftcases.append({'input':x.encode('utf-8').decode('latin-1'),'expected':y,'author_fixture':'test_real_tweets extra_bad transformation'})
    # This explicit example is in the author fix_text contract, not an invented bug.
    ftcases.append({'input':'&amp;amp;','expected':'&','author_fixture':'fix_text author docstring explicit example'})
    ftcontract=ast.get_docstring(next(n for n in ast.parse((ftfy_author/'ftfy/__init__.py').read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='fix_text'))
    for label,tree in [('ftfy-legacy-under-v3-contract',ftfy_old),('ftfy-author',ftfy_author)]:
        groups.append((label,tree,{'kind':'ftfy'},ftcontract,True,ftcases))
    try:
        w3head=archive(W3_REPO,W3_AUTHOR,'w3lib-author');oldsha=None
        for ref in W3_OLD_REFS:
            try:oldsha=git.api(W3_REPO,'commits/'+ref)['sha'];break
            except Exception as e:attempts.append({'ref':ref,'status':'UNKNOWN_REF','error':type(e).__name__})
        w3old=archive(W3_REPO,oldsha,'w3lib-legacy') if oldsha else None
        for name in ('safe_url_string','canonicalize_url'):
            cases=literal_assertions(w3head/'tests/test_url.py',name)
            contract=('The independent author property Test'+('SafeUrlString' if name=='safe_url_string' else 'CanonicalizeUrl')+
              'Properties.test_idempotent requires: once = '+name+'(url); assert '+name+'(once) == once. '+
              'This is an idempotent normalization operation. The intended outputs are separately asserted in the author test file.')
            if not cases:attempts.append({'function':name,'status':'UNKNOWN_NO_LITERAL_AUTHOR_CASES'});continue
            groups.append(('w3lib-author-'+name,w3head,{'kind':'w3lib','function':name},contract,True,cases))
            if w3old:groups.append(('w3lib-legacy-'+name,w3old,{'kind':'w3lib','function':name},contract,True,cases))
    except Exception as e:attempts.append({'repo':W3_REPO,'status':'UNKNOWN_SOURCE_ADMISSION','error':type(e).__name__})
    controls=DATA/'scope_controls';controls.mkdir(exist_ok=True)
    groups.extend([
      ('single-layer-html-unescape',controls,{'kind':'html_unescape'},
       'Convert HTML character references into their corresponding Unicode characters in one layer. Encoded literal references may remain; do not reinterpret them again.',False,
       [{'input':'&amp;lt;','expected':'&lt;','author_fixture':'Python html.unescape one-layer semantics'}, {'input':'A &amp; B','expected':'A & B','author_fixture':'Python html.unescape'}, {'input':'plain','expected':'plain','author_fixture':'preservation control'}]),
      ('single-layer-url-unquote',controls,{'kind':'url_unquote'},
       'Replace each %xx escape by its single-character equivalent once. Percent-encoded literal data must not be decoded again.',False,
       [{'input':'%252F','expected':'%2F','author_fixture':'Python urllib.parse.unquote one-layer semantics'},{'input':'A%20B','expected':'A B','author_fixture':'Python urllib.parse.unquote'},{'input':'plain','expected':'plain','author_fixture':'preservation control'}])])
    index=[]
    for label,tree,spec,contract,scope,cases in groups:
        req={'mode':'evaluate','target':spec,'contract':contract,'scope_supported':scope,'programs':programs,'cases':cases}
        result=sandbox(tree,req,timeout=180)
        dump(WORK/'future'/f'{label}.json',{'label':label,'target':spec,'contract':contract,'scope_supported':scope,
          'cases':cases,'source_tree':str(tree.relative_to(HERE)),'programs_sha256':stable(programs),'native':result})
        index.append({'label':label,'cases':len(cases),'status':result.get('status','EXECUTED'),'native_returncode':result.get('native_returncode')})
        print('FUTURE_NATIVE',label,json.dumps(index[-1]),flush=True)
    dump(WORK/'future_index.json',{'groups':index,'attempts':attempts,'frozen_programs_sha256':stable(programs),
      'boundary':'Historical public independently authored fixtures; inference holdout only; legacy ftfy assessed under v3 contract as migration candidate, not a claim of a v2 violated promise.'})

def report():
    qualified=load(WORK/'qualified_programs.json');index=load(WORK/'future_index.json');scores=collections.defaultdict(collections.Counter);groups=[];witnesses=[]
    all_results={load(p)['label']:load(p) for p in sorted((WORK/'future').glob('*.json'))}
    def authority_key(label):
        if label.startswith('ftfy-'):return 'ftfy-author'
        if '-legacy' in label:return label.replace('-legacy','-author',1)
        return label
    authority={}
    for label,x in all_results.items():
        ref=all_results.get(authority_key(label),{})
        authority[label]={(r['seed'],r.get('expected')) for r in ref.get('native',{}).get('rows',{}).get('without_critic',[]) if r.get('original_matches_author') is True}
    for p in sorted((WORK/'future').glob('*.json')):
        x=load(p);rows=x['native'].get('rows',{});label=x['label'];g={'label':label,'counts':{},'scope_supported':x['scope_supported']}
        for arm,rs in rows.items():
            count=collections.Counter()
            for r in rs:
                if (r['seed'],r.get('expected')) not in authority[label]:
                    count['UNKNOWN_AUTHOR_ORACLE']+=1
                    continue
                count['cases']+=1;count['original_matches_author']+=r.get('original_matches_author') is True
                count['result_matches_author']+=r.get('result_matches_author') is True
                count['verified_rejections']+=verified_rejection(r)
                count['unsupported_rejections']+=r.get('status')=='UNSUPPORTED_REJECTION'
                count['native_observations']+=len(r.get('observations',[]))
                corrected=r.get('original_matches_author') is False and r.get('result_matches_author') is True
                damaged=r.get('original_matches_author') is True and r.get('result_matches_author') is False
                count['corrected']+=corrected;count['damaged']+=damaged
                if arm=='retained' and (corrected or verified_rejection(r)):
                    witnesses.append({'group':label,'corrected':corrected,'record':r})
            g['counts'][arm]=dict(count);scores[arm].update(count)
        # Ledger parity means identical code and every recorded native decision.
        g['ledger_parity']=rows.get('retained')==rows.get('ledger')
        groups.append(g)
    correction_count=scores['retained']['corrected'];reject_count=scores['retained']['verified_rejections']
    # Component ablations leave the same real operation/source/seed/contract.
    causal=correction_count>scores['without_diagnostic']['corrected'] and correction_count>scores['without_repair']['corrected']
    program_ok=qualified['qualification'].get('retained',{}).get('status')=='FINITE_QUALIFIED'
    summary={'source_sha':os.environ.get('GITHUB_SHA'),'run_id':os.environ.get('GITHUB_RUN_ID'),
      'learning_step':qualified.get('learning_step',1),
      'status':'BOUNDED_EXECUTABLE_CRITIC_TRANSFER' if program_ok and reject_count and causal else 'UNKNOWN_OR_NO_CAUSAL_TRANSFER',
      'qualification':{a:{k:v for k,v in q.items() if k not in ('author','incomplete_candidate')} for a,q in qualified['qualification'].items()},
      'scores':{a:dict(c) for a,c in scores.items()},'groups':groups,'causal_component_effect_observed':causal,
      'ledger_parity_all':all(g['ledger_parity'] for g in groups),
      'performance_superiority_not_implied':True,'no_future_feedback_retraining':True,
      'limits':['Historical public fixtures; no guarantee against model pretraining exposure.',
       'Method generation from MarkupSafe is an exposed development case. Future operation families and native gold are withheld from generation.',
       'The normal-form/fixed-point pattern is established prior art and a conventional baseline is included. No thirty-year novelty claim.',
       'No failure found is not a soundness proof. Verdicts are finite witness/case statements.',
       'ftfy legacy version is an actual migration candidate under the newer author contract, not an allegation against its original contract.',
       'Single acquisition sample per generated program; resource comparison must include construction and qualification.',
       'A successful construction/reuse mechanism is distinct from outperforming equally informed reconstruction.']}
    dump(WORK/'summary.json',summary);dump(WORK/'causal_witnesses.json',witnesses)
    evidence=HERE/'evidence';evidence.mkdir(exist_ok=True)
    for root in (DATA,WORK):
        for p in root.rglob('*'):
            if p.is_file() and (p.suffix in ('.json','.py') or p.name=='Dockerfile'):
                dest=evidence/root.name/p.relative_to(root);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dest)
    for p in HERE.iterdir():
        if p.is_file() and (p.suffix in ('.py','.md') or p.name=='Dockerfile'):shutil.copyfile(p,evidence/p.name)
    dump(evidence/'MANIFEST.json',{str(p.relative_to(evidence)):digest(p) for p in sorted(evidence.rglob('*')) if p.is_file()})
    with zipfile.ZipFile(HERE/'evidence.zip','w',compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(evidence.rglob('*')):
            if p.is_file():z.write(p,p.relative_to(evidence))
    print('FINAL_SUMMARY',json.dumps(summary,sort_keys=True),flush=True)
    print('EVIDENCE_SHA256',digest(HERE/'evidence.zip'),flush=True)

if __name__=='__main__':
    {'train':train,'learn':learn,'qualify':qualify,'future':future,'report':report}[sys.argv[1]]()
