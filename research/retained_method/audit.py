"""Second-implementation artifact audit; no model calls or native execution."""
import ast, hashlib, json, sys
from pathlib import Path

def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def normalized(r):return {k:r.get(k) for k in ('status','returncode','rows')}
def outcome(r,base,author):
    rows=r.get('rows',{})
    passing={k for k,v in rows.items() if v.get('call')=='passed'}
    required={k for k,v in author['rows'].items() if v.get('call')=='passed'}
    old={k for k,v in base['rows'].items() if v.get('call')=='passed'}
    return r.get('status')=='EXECUTED' and r.get('returncode')==0 and set(rows)==set(author['rows']) and passing==required and old<=passing and all('failed' not in v.values() for v in rows.values())

def semantic(root):
    frozen=read(root/'data/freeze.json');summary=read(root/'work/summary.json')
    controls=read(root/'work/controls.json');original=(root/'data/original/funcy/decorators.py').read_text()
    assert controls['original']['returncode']==0 and controls['author']['returncode']==0 and controls['oracle']['returncode']==1
    assert set(controls['oracle']['rows'])==set(controls['author']['rows'])
    bad={k for k,v in controls['oracle']['rows'].items() if 'failed' in v.values()}
    assert bad==set(frozen['regression_ids']) and bad
    constants={}
    for node in ast.parse((root/'pipeline.py').read_text()).body:
        if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name) and node.targets[0].id in ('COMMON','NOTES','ORDER'):
            constants[node.targets[0].id]=ast.literal_eval(node.value)
    order=constants['ORDER'];assert order==frozen['order'] and len(set(order))==9
    assert len(summary['outcomes'])==9
    counts={k:0 for k in constants['NOTES']};call_count=0;usage={'input_tokens':0,'output_tokens':0};response_ids=[];native_count=0;per_sample={}
    for key in order:
        arm=key.split('-')[0];history=[];tokens=0;probe_count=0;final=None;responded=[]
        paths=sorted((root/'work/responses').glob(key+'-*.json'))
        assert 1<=len(paths)<=4
        for turn,path in enumerate(paths):
            assert path.name==f'{key}-{turn}.json'
            record=read(path)
            prefix=constants['COMMON']+'\n'+constants['NOTES'][arm]+'\nExact original module:\n'+original+'\nYour own earlier actions and native observations:\n'
            assert record['prompt'].startswith(prefix),(key,turn,'prompt isolation/intervention drift')
            assert json.loads(record['prompt'][len(prefix):])==history,(key,turn,'native history drift')
            expected=record['prompt']
            assert record['prompt_sha256']==hashlib.sha256(json.dumps(expected,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
            call_count+=1
            for k in usage:usage[k]+=(record.get('usage') or {}).get(k,0)
            tokens+=(record.get('usage') or {}).get('total_tokens',0)
            if record['status']!='RETURNED':assert turn==len(paths)-1;continue
            response_ids.append(record['response_id']);text=record['response'].strip()
            if text.startswith('```'):text=text[text.find('\n')+1:text.rfind('```')]
            try:action=json.loads(text)
            except ValueError:assert turn==len(paths)-1;continue
            responded.append(action)
            if not isinstance(action,dict):continue
            if action.get('action')=='probe':
                p=root/'work/probes'/f'{key}-{turn}.json'
                if p.exists():
                    row=read(p);assert row['action']==action
                    history.append({'response':action,'observation':row['native']});probe_count+=1
            elif action.get('action')=='final':final=action;assert turn==len(paths)-1
        tr=read(root/'work/trajectories'/f'{key}.json')
        assert tr['api_tokens']==tokens and tr['native_actions']==probe_count and probe_count<=3
        candidate=root/'work/candidates'/f'{key}.py'
        if candidate.exists():
            assert final is not None
            new=ast.parse(final['source']);assert len(new.body)==1 and isinstance(new.body[0],ast.FunctionDef) and new.body[0].name=='arggetter'
            old=next(n for n in ast.parse(original).body if isinstance(n,ast.FunctionDef) and n.name=='arggetter')
            assert ast.dump(new.body[0].args)==ast.dump(old.args)
            lines=original.splitlines(keepends=True)
            expected=''.join(lines[:old.lineno-1])+final['source'].rstrip()+'\n'+''.join(lines[old.end_lineno:])
            assert candidate.read_text()==expected
            verdict=read(root/'work/judgments'/f'{key}.json')
            qualified=outcome(verdict,controls['original'],controls['author'])
            if qualified:
                causal=read(root/'work/causal'/f'{key}.json')
                assert normalized(causal['withdraw'])==normalized(controls['oracle'])
                assert normalized(causal['restore'])==normalized(verdict)
            assert sha(candidate)==summary['outcomes'][key]['candidate_sha256']
        else:qualified=False
        assert bool(summary['outcomes'][key]['qualified'])==bool(qualified),(key,'qualification mismatch')
        assert tokens<=60000 or not qualified
        counts[arm]+=bool(qualified);native_count+=probe_count
        per_sample[key]={'qualified':qualified,'api_calls':len(paths),'native_actions':probe_count,'total_tokens':tokens,'terminal':tr['terminal']}
    assert counts==summary['counts'];assert len(response_ids)==len(set(response_ids))
    assert call_count==summary['api_calls'] and native_count==summary['native_actions']
    assert all(usage[k]==summary[k] for k in usage)
    replay=read(root/'work/fresh-replay.json');assert all(all(v.values()) for v in replay.values())
    return {'counts':counts,'samples':per_sample,'api_calls':call_count,**usage,'native_actions':native_count,'unique_response_ids':len(response_ids),'regression_ids':sorted(bad),'baseline_tests':len(controls['original']['rows']),'oracle_tests':len(controls['author']['rows']),'fresh_replays':len(replay),'prompt_authority_and_isolation':True,'population_advantage':'UNKNOWN','strict_global_nonexposure':'UNKNOWN','autonomous_acquisition':'NOT_TESTED'}

def audit(root):
    manifest=read(root/'MANIFEST.json')
    for name,h in manifest.items():
        p=(root/name).resolve();assert p.is_relative_to(root.resolve()) and p.is_file() and not p.is_symlink()
        assert sha(p)==h,('outer manifest',name)
    f=read(root/'data/freeze.json')
    for name,h in f['code'].items():assert sha(root/name)==h
    for name,h in f['source'].items():assert sha(root/'data'/name)==h
    identity=read(root/'identity.json');n=0
    for label,key in [('original','base'),('author','head')]:
        for entry in identity[key+'_entries']:
            if entry['type']!='blob':continue
            b=(root/'data'/label/entry['path']).read_bytes()
            assert hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()==entry['sha']
            n+=1
    seal=read(root/'work/response-seal.json')
    for name,h in seal['manifest'].items():assert sha(root/'work'/name)==h
    s=read(root/'work/summary.json')
    assert s['source_freeze']==sha(root/'data/freeze.json') and s['response_seal']==sha(root/'work/response-seal.json')
    out=semantic(root)
    out.update(manifest_files=len(manifest),independent_git_blob_checks=n)
    return out
if __name__=='__main__':print(json.dumps(audit(Path(sys.argv[1]).resolve()),sort_keys=True,indent=2))
