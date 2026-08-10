#!/usr/bin/env python3
import argparse, collections, hashlib, json, math
from pathlib import Path
CONDS=["A_ONE_SHOT","B_RAW_RETRY","C_STRUCTURED_RESIDUAL","D_MACHINE_INSIGHT","SHUFFLED_RESIDUAL","RANDOM_REPAIR"]
def mcnemar_exact(b_only,x_only):
    n=b_only+x_only
    if n==0:return 1.0
    k=min(b_only,x_only); return min(1.0,2*sum(math.comb(n,i) for i in range(k+1))/(2**n))
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--input-dir',required=True); ap.add_argument('--manifest',required=True); ap.add_argument('--out-dir',required=True); a=ap.parse_args(); indir=Path(a.input_dir); out=Path(a.out_dir); out.mkdir(parents=True,exist_ok=True); tasks=json.loads(Path(a.manifest).read_text()); ids=[t['id'] for t in tasks]
    recs=[]
    for p in sorted(indir.glob('group_*.jsonl')): recs += [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
    seen=set(); clean=[]
    for r in recs:
        k=(r['task_id'],r['condition'],r['attempt'])
        if k not in seen: seen.add(k); clean.append(r)
    recs=clean; status={t:{c:'FAILED' for c in CONDS} for t in ids}; infra={t:False for t in ids}; attempts={t:{c:0 for c in CONDS} for t in ids}; tokens={t:{c:0 for c in CONDS} for t in ids}
    for r in recs:
        t,c=r['task_id'],r['condition']
        if t not in status or c not in CONDS:continue
        if r.get('infra_error'): infra[t]=True; status[t][c]='INFRA_ERROR'; continue
        attempts[t][c]=max(attempts[t][c],int(r.get('attempt') or 0)); tokens[t][c]+=int(r.get('total_tokens') or 0)
        if r.get('verified'):status[t][c]='VERIFIED'
    evaluable=[t for t in ids if not infra[t]]; result={'development_n_frozen':len(ids),'development_n_evaluable':len(evaluable),'infra_error_tasks':sorted([t for t in ids if infra[t]]),'conditions':{},'comparisons':{}}
    for c in CONDS:
        solved=sum(status[t][c]=='VERIFIED' for t in evaluable); result['conditions'][c]={'verified':solved,'n':len(evaluable),'rate':solved/len(evaluable) if evaluable else None,'logical_tokens':sum(tokens[t][c] for t in evaluable),'logical_attempts':sum(attempts[t][c] for t in evaluable)}
    for c in ['C_STRUCTURED_RESIDUAL','D_MACHINE_INSIGHT','SHUFFLED_RESIDUAL','RANDOM_REPAIR']:
        both=b_only=x_only=neither=0
        for t in evaluable:
            b=status[t]['B_RAW_RETRY']=='VERIFIED'; x=status[t][c]=='VERIFIED'
            if b and x:both+=1
            elif b:b_only+=1
            elif x:x_only+=1
            else:neither+=1
        rb=result['conditions']['B_RAW_RETRY']['rate']; rx=result['conditions'][c]['rate']; result['comparisons'][f'{c}_vs_B']={'both':both,'B_only':b_only,'comparison_only':x_only,'neither':neither,'absolute_uplift':None if rb is None else rx-rb,'mcnemar_exact_p':mcnemar_exact(b_only,x_only)}
    first_failed=[]
    for t in evaluable:
        arows=[r for r in recs if r['task_id']==t and r['condition']=='A_ONE_SHOT' and r['attempt']==1]
        if arows and not arows[0].get('verified'):first_failed.append(t)
    for c in ['B_RAW_RETRY','C_STRUCTURED_RESIDUAL','D_MACHINE_INSIGHT']:
        result['conditions'][c]['recovery_after_first_failure']=sum(status[t][c]=='VERIFIED' for t in first_failed)/len(first_failed) if first_failed else None
    if first_failed:
        result['recovery_lift_C_vs_B']=result['conditions']['C_STRUCTURED_RESIDUAL']['recovery_after_first_failure']-result['conditions']['B_RAW_RETRY']['recovery_after_first_failure']; result['recovery_lift_D_vs_B']=result['conditions']['D_MACHINE_INSIGHT']['recovery_after_first_failure']-result['conditions']['B_RAW_RETRY']['recovery_after_first_failure']
    rr=collections.defaultdict(lambda:[0,0]); fam=collections.defaultdict(lambda:collections.defaultdict(lambda:[0,0]))
    for r in recs:
        if r['condition']=='D_MACHINE_INSIGHT' and r['attempt']>=2 and r.get('residual') and r.get('repair_family'):
            k=(r['residual']['family'],r['repair_family']); rr[k][1]+=1; rr[k][0]+=int(bool(r.get('verified'))); x=fam[r['residual']['family']][r['repair_family']]; x[1]+=1; x[0]+=int(bool(r.get('verified')))
    result['residual_repair_recovery']=[{'residual_family':k[0],'repair_family':k[1],'verified':v[0],'attempts':v[1],'rate':v[0]/v[1]} for k,v in sorted(rr.items())]
    policy={}
    for residual,opts in sorted(fam.items()):
        candidates=[]
        for repair,(succ,n) in opts.items():
            if succ>0:candidates.append((succ/n,succ,n,repair))
        if candidates:
            candidates.sort(key=lambda x:(-x[0],-x[1],x[3])); rate,succ,n,repair=candidates[0]; policy[residual]={'repair_family':repair,'development_verified':succ,'development_attempts':n,'development_rate':rate}
    pobj={'version':'1.0.0-frozen-after-development','source_condition':'D_MACHINE_INSIGHT_ONLY','rule':'highest observed D recovery rate per residual family; require >=1 verified recovery; ties: successes then lexical repair','policy':policy}; ptext=json.dumps(pobj,indent=2,sort_keys=True,ensure_ascii=False)+'\n'; ph=hashlib.sha256(ptext.encode()).hexdigest(); (out/'DEVELOPMENT_RESULTS.json').write_text(json.dumps(result,indent=2,sort_keys=True,ensure_ascii=False)+'\n'); (out/'FROZEN_TRANSFER_POLICY.json').write_text(ptext); (out/'FROZEN_TRANSFER_POLICY.sha256').write_text(ph+'  FROZEN_TRANSFER_POLICY.json\n')
    with (out/'development_traces.jsonl').open('w') as f:
        for r in sorted(recs,key=lambda x:(x['task_id'],x['condition'],x['attempt'])):f.write(json.dumps(r,sort_keys=True,ensure_ascii=False)+'\n')
    print(json.dumps(result,indent=2,sort_keys=True)); print('FROZEN_TRANSFER_POLICY_SHA256',ph)
if __name__=='__main__':main()
