"""Additional independent model samples, matched repetition and native control."""
import json
import math
import os
from pathlib import Path
import sys
import pipeline as p
import refine as r

p.WORK=p.HERE/'replication'
ORDERS=[('trace','sham','ordinary'),('ordinary','sham','trace'),
        ('sham','trace','ordinary'),('ordinary','trace','sham'),
        ('trace','ordinary','sham'),('sham','ordinary','trace')]


def prepare():
    r.prepare()
    feedback=p.load(p.WORK/'feedback.json')
    inputs=[item['failure']['input'] for item in feedback['exposed']]
    ordinary=p.native('legacy',inputs)
    p.dump(p.WORK/'ordinary_information_native.json',ordinary)
    if len(p.rows(ordinary))!=4:raise RuntimeError('ordinary control unavailable')
    f=p.load(p.WORK/'frozen.json');f['replication_protocol_sha256']=p.digest(p.HERE/'REPLICATION.md')
    f['orders']=ORDERS;p.dump(p.WORK/'frozen.json',f)
    print('REPLICATION_FROZEN',len(ORDERS),'samples per arm',flush=True)


def guard():
    r.guard()
    if p.load(p.WORK/'frozen.json')['replication_protocol_sha256']!=p.digest(p.HERE/'REPLICATION.md'):
        raise ValueError('replication protocol drift')


def learn():
    guard();feedback=p.load(p.WORK/'feedback.json');prior=p.load(r.PARENT/'work/acquire_c1.json')
    shared=p.INSTRUCTIONS+'\nThe first constructed method was REJECTED: it repaired the obstruction but corrupted some correct outputs.\n'
    shared+='Construct a complete safer successor. Preserve the initial new capability as well as original correctness.\n'
    shared+=json.dumps({'initial_prompt':prior['prompt'],'initial_response':prior['response'],
                       'new_development_failures':[item['failure'] for item in feedback['exposed']]},ensure_ascii=False)
    ordinary=p.rows(p.load(p.WORK/'ordinary_information_native.json'))
    packets={
        'trace':feedback['exposed'],
        'sham':[{'failure':item['failure'],'observations':[]} for item in feedback['exposed']],
        'ordinary':[{'failure':item['failure'],'observations':[{'input':obs['input'],'output':obs['output']}]} for item,obs in zip(feedback['exposed'],ordinary)]}
    calls={}
    for sample,order in enumerate(ORDERS):
        for arm in order:
            prompt=shared+'\nAdditional independently replayed native observations:\n'+json.dumps(packets[arm],ensure_ascii=False)
            record=p.call(prompt);calls[f'{arm}-{sample}']=record;p.dump(p.WORK/'acquisition.json',calls)
            print('REPLICATION_RESPONSE',arm,sample,record['status'],flush=True)


def fisher(success_a,success_b,n=6):
    total=success_a+success_b
    denominator=math.comb(2*n,total)
    return sum(math.comb(n,k)*math.comb(n,total-k)/denominator
               for k in range(success_a,n+1) if 0<=total-k<=n)


def qualify():
    guard();allcases=p.load(p.DATA/'admitted.json')['cases']
    common=[c for c in allcases if c.get('kind') or c['original_matches_author']]
    originals=[c for c in allcases if not c.get('kind')]
    feedback=p.load(p.WORK/'feedback.json');exposed={a['failure']['input'] for a in feedback['exposed']};hidden={a['input'] for a in feedback['concealed']}
    calls=p.load(p.WORK/'acquisition.json');results={}
    for key,record in calls.items():
        source=p.program(record)
        if source is None:
            results[key]={'qualified':False,'status':'REJECTED_PROGRAM_BOUNDARY'};continue
        (p.WORK/(key+'.py')).write_text(source)
        native=p.native('legacy',[c['input'] for c in common],source);p.dump(p.WORK/(key+'_native.json'),native)
        q=p.score(native,common);q['ground_replay']=p.verify_ground(native,key)
        q['qualified']=q['qualified'] and q['ground_replay']['verified']
        q['exposed_correct']=sum(row['matches'] for row in q.get('rows',[]) if row['input'] in exposed)
        q['concealed_correct']=sum(row['matches'] for row in q.get('rows',[]) if row['input'] in hidden)
        full=p.native('legacy',[c['input'] for c in originals],source)
        p.dump(p.WORK/(key+'_development.json'),{'native':full,'score':p.score(full,originals)})
        q['development_ground']=p.verify_ground(full,key+'_development')
        q['qualified']=q['qualified'] and q['development_ground']['verified']
        again=p.native('legacy',[c['input'] for c in common],source)
        norm=lambda result:[{k:v for k,v in row.items() if k!='elapsed_seconds'} for row in p.rows(result)]
        q['ledger_identical']=norm(again)==norm(native)
        p.dump(p.WORK/(key+'_ledger_replay.json'),again)
        if not q['ledger_identical']:raise RuntimeError('compiled method replay differs')
        results[key]=q;p.dump(p.WORK/'qualification_progress.json',results)
        print('REPLICATION_RESULT',key,q.get('matches'),q.get('cases'),q['qualified'],flush=True)
    counts={arm:sum(results.get(f'{arm}-{i}',{}).get('qualified',False) for i in range(6)) for arm in ('trace','sham','ordinary')}
    comparisons={arm:fisher(counts['trace'],counts[arm]) for arm in ('sham','ordinary')}
    ordered=sorted(comparisons,key=comparisons.get)
    holm={ordered[0]:comparisons[ordered[0]]<=0.025}
    holm[ordered[1]]=holm[ordered[0]] and comparisons[ordered[1]]<=0.05
    unknown=any(rec['status']!='RETURNED' for rec in calls.values())
    promoted=not unknown and all(holm.values()) and all(counts['trace']>counts[arm] for arm in ('sham','ordinary'))
    status='BOUNDED_WITHIN_TASK_INFORMATION_EFFECT' if promoted else 'EXPLORATORY_SIGNAL_NOT_CONFIRMED'
    if unknown:status='UNKNOWN_API_TRANSPORT'
    summary={'status':status,'counts':counts,'samples_per_arm':6,'fisher_one_sided':comparisons,'holm_rejected':holm,
             'qualification':results,'api_calls_this_stage':len(calls),
             'input_tokens_this_stage':sum((rec.get('usage') or {}).get('input_tokens',0) for rec in calls.values()),
             'output_tokens_this_stage':sum((rec.get('usage') or {}).get('output_tokens',0) for rec in calls.values()),
             'source_sha':os.environ.get('GITHUB_SHA'),'breakthrough_established':False,
             'boundary':'Same exposed development problem. Model-response sampling assumptions, no cross-domain or economic claim.'}
    events=p.load(p.WORK/'native_calls.json');summary['native_attempts']=len(events);summary['native_recorded_callbacks']=sum(e['callbacks'] for e in events)
    p.dump(p.WORK/'summary.json',summary)
    print('REPLICATION_GATE',status,json.dumps(counts),json.dumps(comparisons),flush=True)


if __name__=='__main__':
    {'prepare':prepare,'learn':learn,'qualify':qualify,'bundle':p.bundle}[sys.argv[1]]()
