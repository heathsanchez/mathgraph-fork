"""One further learning step from the verified no-transfer result, no retuning.

Only one formerly held-out ftfy example becomes new exposed training. Modern
external entity/Unicode fixtures and Bleach data open after the second freeze.
"""
import ast
import json
import os
from pathlib import Path
import shutil
import time
import zipfile
import pipeline as p
from native import HERE,build,load,dump,digest,stable
from core import validate_program,verified_rejection

PREVIOUS=HERE/'previous'

def source_root(label):
    parent=PREVIOUS/'data/future_sources'/label
    return next(q.parent.parent for q in parent.rglob('ftfy/__init__.py'))

def feedback():
    env=build();p.DATA.mkdir(exist_ok=True);p.WORK.mkdir(exist_ok=True)
    dump(p.DATA/'environment_v3.json',env)
    original=load(p.DATA/'training_public.json')
    previous=load(PREVIOUS/'work/qualified_programs.json')
    failed=load(PREVIOUS/'work/future/ftfy-legacy-under-v3-contract.json')
    row=next(r for r in failed['native']['rows']['retained'] if r['seed']=='&amp;amp;')
    assert row['original']=='&amp;' and row['expected']=='&' and row['status']=='INACTIVE'
    packet={'original_development_evidence':original,'previous_programs':previous['programs'],
      'verified_new_training_failure':{'contract':failed['contract'],'case':row,
        'independent_author_result':'&','prior_verification':'Pinned ftfy author implementation reproduced the expected result.',
        'finding':'The previous executable applicability rule disabled itself on an operation with a real contract violation.'},
      'exposure_boundary':'This one former V2 case is now exposed training, excluded from fresh V3 scoring. No new entity, Unicode or Bleach future cases supplied.'}
    dump(p.DATA/'training_public_v3.json',packet)
    print('VERIFIED_SCOPE_FAILURE_FOR_LEARNING','one example only',flush=True)

def learn():
    packet=load(p.DATA/'training_public_v3.json');out={};p.WORK.mkdir(exist_ok=True)
    prompt=p.PROMPT+('''\nYour previous executable concept failed to transfer: it was too specific to superficial wording of one operation.
Use the independently verified failure below to improve the diagnostic's semantic applicability and repair executor.
Retain correct behavior on the earlier training evidence and on single-layer or unspecified contracts.
Return the complete three-function replacement program. Do not just widen the gate: justify the diagnostic/repair from what the author contract actually promises.
No further adaptive attempts or future feedback will be available.\n''')+json.dumps(packet,sort_keys=True)
    for arm in ('retained','cold'):
        # Identical evidence, prior source and budget: cold can reconstruct freely.
        out[arm]=p.api_call(prompt);dump(p.WORK/'raw_programs.json',out)
        print('REVISED_METHOD',arm,out[arm]['status'],flush=True)

def qualify():
    p.qualify();frozen=load(p.WORK/'qualified_programs.json');programs=frozen['programs'];q=frozen['qualification']
    packet=load(p.DATA/'training_public_v3.json');contract=packet['verified_new_training_failure']['contract']
    cases=[{'input':'&amp;amp;','expected':'&'}]
    for label,oldlabel in [('new_failure','ftfy-legacy'),('new_author','ftfy-author')]:
        tree=source_root(oldlabel)
        r=p.sandbox(tree,{'mode':'qualify','target':{'kind':'ftfy'},'contract':contract,'programs':programs,'cases':cases})
        dump(p.WORK/f'qualification_{label}.json',r)
        for arm in list(programs):q[arm][label]=r.get(arm,{})
    for arm in list(programs):
        bad=q[arm]['new_failure'].get('rows',[]);good=q[arm]['new_author'].get('rows',[])
        passes=bool(bad and good) and verified_rejection(bad[0]) and bad[0].get('result_matches_author') is True and good[0].get('result_matches_author') is True
        q[arm]['second_family_training_qualified']=passes
        if not passes:q[arm]['status']='REJECTED_SECOND_FAMILY_QUALIFICATION';programs.pop(arm)
    old=load(PREVIOUS/'work/qualified_programs.json')['programs'].get('retained')
    if old:programs['previous']=old
    frozen.update(programs=programs,qualification=q,frozen_sha256=stable(programs),future_data_not_opened=True,
      learning_step=2,exposed_former_case='&amp;amp;',no_further_feedback=True)
    dump(p.WORK/'qualified_programs.json',frozen)
    print('SECOND_PROGRAM_FREEZE',json.dumps({a:{k:v for k,v in r.items() if k not in ('incomplete_candidate','author','new_failure','new_author')} for a,r in q.items()}),flush=True)

def decorated_pairs(path,operation):
    tree=ast.parse(path.read_text());rows=[];seen=set()
    for fn in ast.walk(tree):
        if not isinstance(fn,(ast.FunctionDef,ast.AsyncFunctionDef)):continue
        calls=[n for n in ast.walk(fn) if isinstance(n,ast.Call) and ((isinstance(n.func,ast.Name) and n.func.id==operation) or (isinstance(n.func,ast.Attribute) and n.func.attr==operation))]
        if not calls or any(c.keywords or len(c.args)!=1 for c in calls):continue
        for d in fn.decorator_list:
            if not isinstance(d,ast.Call) or not isinstance(d.func,ast.Attribute) or d.func.attr!='parametrize' or len(d.args)<2:continue
            try:names=ast.literal_eval(d.args[0]);pairs=ast.literal_eval(d.args[1])
            except (TypeError,ValueError):continue
            names=[s.strip() for s in names.split(',')] if isinstance(names,str) else list(names)
            if len(names)!=2 or names[1] not in ('expected','expect'):continue
            for item in pairs:
                if not isinstance(item,(list,tuple)) or len(item)!=2:continue
                x,y=item
                if isinstance(x,str) and isinstance(y,str) and len(x)<=2048 and x not in seen:
                    rows.append({'input':x,'expected':y,'author_fixture':f'{path.name}:{d.lineno} {fn.name}'});seen.add(x)
                    if len(rows)>=100:return rows
    return rows

def future():
    env=build();frozen=load(p.WORK/'qualified_programs.json');programs=frozen['programs'];groups=[];attempts=[]
    dump(p.WORK/'future_environment_v3.json',env)
    # These moving references resolve once, after acquisition, to exact commits.
    ftsha=p.git.api('rspeer/python-ftfy','commits/main')['sha']
    modern=p.archive('rspeer/python-ftfy',ftsha,'ftfy-modern-v3')
    legacy=p.archive(p.FTFY_REPO,p.FTFY_OLD,'ftfy-legacy-v3')
    text=(modern/'src/ftfy/__init__.py').read_text() if (modern/'src/ftfy/__init__.py').exists() else (modern/'ftfy/__init__.py').read_text()
    maincontract=ast.get_docstring(next(n for n in ast.parse(text).body if isinstance(n,ast.FunctionDef) and n.name=='fix_text'))
    # Explicit author semantic requirement, present since their version3 change.
    promise=(' Author change e404191fe210acf324bee1beeab5619434488b98 specifies completing all fixing stages until the output is idempotent. '
             'The operation uses NFC normalization in these target invocations.')
    contract=maincontract+promise
    entity=p.literal_assertions(modern/'tests/test_entities.py','fix_text_segment')
    entity=[c for c in entity if c['input']!='&amp;amp;']
    for c in entity:c['author_fixture']='modern tests/test_entities.py:'+str(c.pop('author_test_line'))
    groups.append(('fresh-ftfy-entity-author',modern,{'kind':'ftfy','function':'fix_text_segment'},contract,True,entity))
    groups.append(('fresh-ftfy-entity-legacy',legacy,{'kind':'ftfy','function':'fix_text_segment','options':{'normalization':'NFC'}},contract,True,entity))
    corpus=[]
    for name in ('synthetic.json','negative.json','in-the-wild.json'):
        path=modern/'tests/test-cases'/name
        if not path.exists():attempts.append({'path':name,'status':'UNKNOWN_MISSING_CORPUS'});continue
        for i,r in enumerate(load(path)):
            if not isinstance(r,dict) or r.get('expect')!='pass' or not isinstance(r.get('original'),str) or not isinstance(r.get('fixed'),str):continue
            if len(r['original'])>2048 or r['original']=='&amp;amp;':continue
            corpus.append({'input':r['original'],'expected':r['fixed'],'author_fixture':f'tests/test-cases/{name}:{i}','label':r.get('label','')})
            if len(corpus)>=200:break
        if len(corpus)>=200:break
    groups.append(('fresh-ftfy-corpus-author',modern,{'kind':'ftfy'},contract,True,corpus))
    groups.append(('fresh-ftfy-corpus-legacy',legacy,{'kind':'ftfy','options':{'normalization':'NFC'}},contract,True,corpus))
    try:
        bsha=p.git.api('mozilla/bleach','commits/main')['sha'];bleach=p.archive('mozilla/bleach',bsha,'bleach-modern-v3')
        path=bleach/'tests/test_clean.py';cases=p.literal_assertions(path,'clean')+decorated_pairs(path,'clean')
        unique={}
        for c in cases:
            c['author_fixture']=c.get('author_fixture','tests/test_clean.py:'+str(c.get('author_test_line','?')))
            unique.setdefault(c['input'],c)
        cases=list(unique.values())[:100]
        bc='Author tests/test_clean.py test_clean_idempotent requires that applying the HTML cleaning filter twice does not change anything: clean(clean(data)) == clean(data). This is an idempotent completed cleaning operation.'
        groups.append(('fresh-bleach-author',bleach,{'kind':'bleach'},bc,True,cases))
    except Exception as e:attempts.append({'repo':'mozilla/bleach','status':'UNKNOWN_SOURCE_ADMISSION','error':type(e).__name__})
    controls=p.DATA/'scope_controls_v3';controls.mkdir(exist_ok=True)
    groups.extend([
      ('fresh-single-layer-html-unescape',controls,{'kind':'html_unescape'},'Convert each HTML character reference in exactly one layer. Any encoded literal left after that conversion is data; do not reinterpret it again.',False,
       [{'input':'&amp;gt;','expected':'&gt;','author_fixture':'Python html.unescape layer semantics'}, {'input':'&amp;amp;amp;','expected':'&amp;amp;','author_fixture':'Python html.unescape layer semantics'}, {'input':'safe &amp; sound','expected':'safe & sound','author_fixture':'Python html.unescape'}]),
      ('fresh-single-layer-url-unquote',controls,{'kind':'url_unquote'},'Replace each %xx escape once by its character. Encoded percent data left in the result must not be decoded again.',False,
       [{'input':'%2520','expected':'%20','author_fixture':'Python urllib.parse.unquote layer semantics'},{'input':'%25252F','expected':'%252F','author_fixture':'Python urllib.parse.unquote layer semantics'},{'input':'plain','expected':'plain','author_fixture':'preservation'}])])
    index=[]
    for label,tree,spec,doc,scope,cases in groups:
        request={'mode':'evaluate','target':spec,'contract':doc,'scope_supported':scope,'programs':programs,'cases':cases}
        result=p.sandbox(tree,request,timeout=180)
        dump(p.WORK/'future'/f'{label}.json',{'label':label,'target':spec,'contract':doc,'scope_supported':scope,'cases':cases,
          'source_tree':str(tree.relative_to(HERE)),'programs_sha256':stable(programs),'native':result})
        index.append({'label':label,'cases':len(cases),'status':result.get('status','EXECUTED'),'returncode':result.get('native_returncode')})
        print('NEW_FUTURE_NATIVE',json.dumps(index[-1]),flush=True)
    dump(p.WORK/'future_index.json',{'groups':index,'attempts':attempts,'author_commits':{'ftfy':ftsha,'bleach':bsha if 'bsha' in locals() else None},
      'boundary':'New external entity/Unicode/cleaning fixtures after second program freeze. One former V2 example is development only. Historical library source reused; these are new fixture holdouts, not a wholly unseen repository claim.'})

def report():
    # Generic scorer maps each legacy target to its independently checked author.
    original=p.report
    original()
    summary=load(p.WORK/'summary.json')
    summary.update(learning_step=2,previous_failure_preserved=True,
      further_scope='Fresh externally authored fixtures, including new target function fix_text_segment and independent Bleach preservation cases. No cross-family repair superiority claim.')
    dump(p.WORK/'summary_v3.json',summary)

if __name__=='__main__':
    {'feedback':feedback,'learn':learn,'qualify':qualify,'future':future,'report':report}[__import__('sys').argv[1]]()
