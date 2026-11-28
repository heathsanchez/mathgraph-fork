"""Before-inference source admission; author fixes never enter model packets."""
import ast
import collections
import hashlib
import json
import os
from pathlib import Path
import shutil
import tarfile
import tempfile
import time
import admit_legacy as old
from native import HERE, build, dump, digest, stable, inventory, native_test, admit_red_green

ROOT=HERE/'data'
POOL=('mahmoud/boltons','SethMMorton/natsort','pytoolz/toolz',
      'python-jsonschema/referencing','python-jsonschema/jsonschema',
      'more-itertools/more-itertools','pallets/itsdangerous','pallets/markupsafe',
      'jaraco/zipp','mahmoud/glom','jmespath/jmespath.py','python/attrs',
      'python/typing_extensions','python-babel/babel','pallets/click')
TRAIN=('pypa/packaging',1531,'5a7d3386d2777180a381eb947f21293124ce8df5')
TARGET=4
MAX_NATIVE_PER_REPO=3

def graph(source,trace,tests):
    fs=inventory(source);tree=ast.parse(source)
    nodes=[];edges=[]
    for f in fs:
        span=set(range(f['start'],f['end']+1))
        fail=sum(t.get('outcome')=='failed' and bool(span&set(t.get('lines',[]))) for t in trace.values())
        passed=sum(t.get('outcome')=='passed' and bool(span&set(t.get('lines',[]))) for t in trace.values())
        nodes.append({'id':f['id'],'name':f['name'],'start':f['start'],'end':f['end'],
                      'failed_case_hits':fail,'passing_case_hits':passed})
    for n in ast.walk(tree):
        if not isinstance(n,ast.Call):continue
        owner=next((f for f in fs if f['start']<=n.lineno<=f['end']),None)
        target=n.func.id if isinstance(n.func,ast.Name) else n.func.attr if isinstance(n.func,ast.Attribute) else None
        if owner and target:
            for f in fs:
                if f['name'].split('.')[-1]==target:edges.append([owner['id'],f['id']])
    return {'kind':'static-call-and-native-spectrum-graph','nodes':nodes,'edges':sorted({tuple(e) for e in edges}),
            'boundary':'Syntactic potential calls plus measured source-line coverage; not dynamic argument provenance or a causal graph.'}

def prepare(repo,pr,merge,env,cid,phase):
    pair=old.layout(merge.get('files',[]))
    if pair is None:return None,'INELIGIBLE_LAYOUT'
    sf,tf=pair;sp,tp=sf['filename'],tf['filename'];parent=merge['parents'][0]['sha'];head=merge['sha']
    with tempfile.TemporaryDirectory(prefix='applicability-admit-') as d:
        d=Path(d);base,ba=old.safe_archive(repo,parent,d/'base');fixed,ha=old.safe_archive(repo,head,d/'head')
        if not all(p.is_file() and not p.is_symlink() for p in [base/sp,base/tp,fixed/sp,fixed/tp]):return None,'UNKNOWN_MISSING_FILES'
        if old.gitblob(fixed/sp)!=sf['sha'] or old.gitblob(fixed/tp)!=tf['sha']:raise ValueError('head blob mismatch')
        source=(base/sp).read_text();new=(fixed/sp).read_text()
        if len(source)>65000 or len(new)>68000:return None,'INELIGIBLE_SOURCE_BUDGET'
        if source==new:return None,'INELIGIBLE_NO_SOURCE_CHANGE'
        ast.parse(source);ast.parse(new)
        base_blob=old.gitblob(base/sp);base_test_blob=old.gitblob(base/tp)
        shutil.copyfile(fixed/tp,base/tp)
        red=native_test(base,tp,sp,timeout=100)
        green=native_test(fixed,tp,sp,timeout=100)
        proof={'base':red,'author':green}
        if not admit_red_green(red,green):
            dump(ROOT/'rejected'/f'{repo.replace("/","_")}_{pr}.json',proof)
            return {'base_status':red['status'],'head_status':green['status'],
                    'base_counts':dict(collections.Counter(red['tests'].values())),
                    'head_counts':dict(collections.Counter(green['tests'].values()))},'UNKNOWN_NATIVE_AUTHORITY'
        if not red['trace'] or not any(x.get('lines') for x in red['trace'].values()):return None,'UNKNOWN_NO_SPECTRUM'
        private=ROOT/'private'/cid;private.mkdir(parents=True,exist_ok=True)
        with tarfile.open(private/'base.tar.gz','w:gz') as tar:tar.add(base,arcname='base')
        authority={'id':cid,'repo':repo,'pr':pr,'parent':parent,'head':head,'source_path':sp,'test_path':tp,
          'base_blob':base_blob,'head_blob':sf['sha'],'base_test_blob':base_test_blob,'author_test_blob':tf['sha'],
          'source_sha256':digest(base/sp),'test_sha256':digest(base/tp),'base_archive_sha256':ba,'head_archive_sha256':ha,
          'overlay_archive_sha256':digest(private/'base.tar.gz'),'environment':env,'native':proof}
        dump(private/'authority.json',authority)
        public={'id':cid,'source_path':sp,'source':source,'source_sha256':authority['source_sha256'],
          'test_path':tp,'test_sha256':authority['test_sha256'],'tests':red['tests'],
          'diagnostic':red['diagnostic'],'test_excerpt':old.sample_test_text(base/tp,red),
          'graph':graph(source,red['trace'],red['tests'])}
        dump(ROOT/'public'/phase/(cid+'.json'),public)
        return {'id':cid,'repo':repo,'pr':pr,'parent':parent,'head':head,'source_path':sp,'test_path':tp,
          'source_sha256':authority['source_sha256'],'test_sha256':authority['test_sha256'],
          'failure_count':sum(x=='failure' for x in red['tests'].values()),
          'passing_count':sum(x=='pass' for x in red['tests'].values()),'public_sha256':digest(ROOT/'public'/phase/(cid+'.json'))},'ADMITTED'

def main():
    started=time.monotonic();ROOT.mkdir(exist_ok=True)
    for p in ['public/train','public/future','private','rejected']:(ROOT/p).mkdir(parents=True,exist_ok=True)
    env=build(); attempts=[];train=[];future=[]
    def save():dump(ROOT/'admission.json',{'source_sha':os.environ.get('GITHUB_SHA'),'pool':POOL,'train':train,'future':future,
        'attempts':attempts,'environment':env,'elapsed':time.monotonic()-started,
        'scope':'Native author-test regression; published defects; no global pretraining nonexposure guarantee.'})
    save()
    repo,pr,sha=TRAIN
    try:
        r,status=prepare(repo,pr,old.api(repo,'commits/'+sha),env,'train-01','train')
        attempts.append({'repo':repo,'pr':pr,'phase':'train','status':status})
        if status=='ADMITTED':train.append(r)
    except Exception as e:attempts.append({'repo':repo,'pr':pr,'phase':'train','status':'UNKNOWN_EXCEPTION','error':type(e).__name__})
    save()
    if not train:print('ADMISSION_STOP_NO_TRAIN',flush=True);return
    for repo in POOL:
        if len(future)>=TARGET or time.monotonic()-started>1200:break
        try:
            prs=old.api(repo,'pulls?state=closed&sort=updated&direction=desc&per_page=100')
            candidates=sorted([p for p in prs if p.get('merged_at') and p.get('merge_commit_sha') and old.eligible_title(p.get('title',''))],key=lambda p:-p['number'])
        except Exception as e:attempts.append({'repo':repo,'status':'UNKNOWN_LIST','error':type(e).__name__});save();continue
        tested=0
        for p in candidates:
            if tested>=MAX_NATIVE_PER_REPO or time.monotonic()-started>1200:break
            rec={'repo':repo,'pr':p['number'],'phase':'future'}
            try:
                merge=old.api(repo,'commits/'+p['merge_commit_sha'])
                if old.layout(merge.get('files',[])) is None:rec['status']='INELIGIBLE_LAYOUT';attempts.append(rec);save();continue
                tested+=1
                r,status=prepare(repo,p['number'],merge,env,f'future-{len(future)+1:02d}','future')
                rec['status']=status
                if status=='ADMITTED':future.append(r)
                elif r:rec['native_summary']=r
            except Exception as e:rec.update(status='UNKNOWN_EXCEPTION',error=type(e).__name__)
            attempts.append(rec);save();print('ADMISSION',repo,p['number'],rec['status'],flush=True)
            if rec['status']=='ADMITTED':break
    save()
    print('FROZEN_NATIVE_COHORT',json.dumps({'train':train,'future':future,'attempt_counts':dict(collections.Counter(x['status'] for x in attempts))}),flush=True)
    if len(future)<3:print('UNKNOWN_INSUFFICIENT_FUTURE',flush=True)

if __name__=='__main__':main()
