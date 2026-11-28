"""Runs only in a network-disabled, credential-free native container."""
import ast
import builtins
import hashlib
import html
import importlib
import json
from pathlib import Path
import sys
import traceback

sys.path.insert(0,'/harness')
from core import validate_program

def target(spec):
    if spec['kind']=='markupsafe':
        from markupsafe import Markup
        return lambda s:str(Markup(s).striptags())
    if spec['kind']=='ftfy':
        import ftfy
        operation=getattr(ftfy,spec.get('function','fix_text'))
        options=spec.get('options',{})
        return lambda s:operation(s,**options)
    if spec['kind']=='bleach':
        from bleach import clean
        return clean
    if spec['kind']=='w3lib':
        from w3lib import url
        return getattr(url,spec['function'])
    if spec['kind']=='html_unescape':return html.unescape
    if spec['kind']=='url_unquote':
        from urllib.parse import unquote
        return unquote
    raise ValueError('unknown target')

def module(source):
    validate_program(source)
    safe={k:getattr(builtins,k) for k in ('str','bool','int','float','len','range','enumerate','zip','min','max','sum',
      'all','any','isinstance','list','tuple','dict','set','sorted','reversed','abs','next','iter','callable','repr','Exception','ValueError','TypeError','RuntimeError')}
    ns={'__builtins__':safe};exec(compile(source,'<learned-critic>','exec'),ns)
    return ns

def conventional():
    # Strong conventional control: the old, well-known fixed-point pattern.
    return module('''def applies(contract):
    t = contract.lower()
    return "idempotent" in t or "normaliz" in t
def diagnose(observe, seed, contract):
    first = observe(seed)
    second = observe(first)
    return {"trigger": first != second}
def repair(observe, seed, contract):
    current = seed
    for i in range(6):
        result = observe(current)
        if result == current:
            return result
        current = result
    return None
''')

def run_one(ns,fn,seed,contract,scope_supported,expected=None,force_scope=False,disable_diagnostic=False,disable_repair=False):
    observed=[]
    original_applies=ns.get('applies') if ns else None
    def observe(value):
        if not isinstance(value,str) or len(value)>16000:raise ValueError('observation domain')
        if len(observed)>=12:raise ValueError('observation budget')
        result=fn(value)
        if not isinstance(result,str):raise ValueError('not string closed')
        observed.append({'input':value,'output':result})
        return result
    try:
        once=fn(seed)
        if not isinstance(once,str):raise ValueError('not string closed')
        active=bool(ns['applies'](contract)) if ns else False
        use=bool(ns) and (active or force_scope)
        if ns and force_scope:
            # Remove both host selection and the program's internal scope check.
            # Restore the original before the next case to avoid cross-case state.
            ns['applies']=lambda contract:True
        diagnostic=None;output=once;witness=None;status='INACTIVE'
        if use and not disable_diagnostic:
            diagnostic=ns['diagnose'](observe,seed,contract)
            if not isinstance(diagnostic,dict) or type(diagnostic.get('trigger')) is not bool:raise ValueError('diagnostic schema')
            if diagnostic['trigger']:
                # Independently replay the proposed repeat-instability witness.
                second=fn(once)
                witness={'seed':seed,'first':once,'second':second,'scope_supported':scope_supported,'replayed':True}
                status='OBSERVED_REJECTION' if once!=second and scope_supported else 'UNSUPPORTED_REJECTION'
                if not disable_repair:
                    output=ns['repair'](observe,seed,contract)
                    if output is not None and (not isinstance(output,str) or output not in [x['output'] for x in observed]):
                        raise ValueError('repair output not observed from real operation')
                else:output=None
            else:status='NO_OBSERVED_REJECTION'
        elif use:status='DIAGNOSTIC_REMOVED'
        return {'seed':seed,'expected':expected,'original':once,'output':output,'module_applies':active,'scope_forced':force_scope,
          'status':status,'diagnostic':diagnostic,'witness':witness,'observations':observed,
          'original_matches_author':once==expected if expected is not None else None,
          'result_matches_author':output==expected if expected is not None else None,
          'expected_available_to_program':False}
    except Exception as e:
        return {'seed':seed,'expected':expected,'status':'UNKNOWN_NATIVE_EXCEPTION','error_type':type(e).__name__,
          'error':str(e)[:400],'observations':observed,'original_matches_author':False,'result_matches_author':False}
    finally:
        if ns and force_scope:ns['applies']=original_applies

def main():
    request=json.loads(Path('/work/request.json').read_text());fn=target(request['target'])
    mode=request['mode'];out={}
    if mode=='training':
        out={'observations':[{'input':x['input'],'expected':x['expected'],'actual':fn(x['input'])} for x in request['cases']]}
    elif mode=='evaluate':
        programs=request['programs'];rows={}
        for arm in ('retained','cold','conventional','previous','without_critic','without_diagnostic','without_repair','ledger'):
            if arm=='conventional':ns=conventional()
            elif arm=='without_critic':ns=None
            else:
                key=arm if arm in ('cold','previous') else 'retained'
                source=programs.get(key)
                ns=module(source) if source else None
            rows[arm]=[run_one(ns,fn,c['input'],request['contract'],request['scope_supported'],c.get('expected'),
              disable_diagnostic=arm=='without_diagnostic',disable_repair=arm=='without_repair') for c in request['cases']]
        source=programs.get('retained');ns=module(source) if source else None
        rows['force_without_scope']=[run_one(ns,fn,c['input'],request['contract'],request['scope_supported'],c.get('expected'),force_scope=True) for c in request['cases']]
        out={'rows':rows}
    elif mode=='qualify':
        for arm,source in request['programs'].items():
            ns=module(source);rows=[run_one(ns,fn,c['input'],request['contract'],True,c['expected']) for c in request['cases']]
            controls=[]
            for s in ('Decode exactly one layer; escaped literal data may remain.','No specification supplied.'):
                controls.append({'contract':s,'applies':bool(ns['applies'](s))})
            out[arm]={'rows':rows,'scope_controls':controls}
    Path('/out/result.json').write_text(json.dumps(out,ensure_ascii=False,sort_keys=True,indent=2)+'\n')

if __name__=='__main__':
    try:main()
    except Exception as e:
        Path('/out/result.json').write_text(json.dumps({'status':'UNKNOWN_WORKER_EXCEPTION','error':type(e).__name__,'detail':str(e)[:400]})+'\n')
        raise
