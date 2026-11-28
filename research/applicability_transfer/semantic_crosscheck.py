"""Exploratory independent semantic probes, frozen after primary proposals.

Never alter or rescore the precommitted primary evaluation. Native, no model API.
"""
import base64
import collections
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import zipfile
import admit_legacy as upstream
from native import HERE, build, digest, dump, load, native_test, stable
from trial import patch, features, holds

SOURCE_RUN=46103184004
CASES=[
 ('A <b> </b> B','A B'),
 ('A <!-- x --> B','A B'),
 (' A <b> B </b> C ','A B C'),
 ('A<b>\t</b>B','A B'),
 ('A<!-- \nignored --> \n B','A B'),
 ('A <b></b> B','A B'),
 ('A B','A B'),
 (' A  \t B ','A B'),
 ('A<b>B</b>C','ABC'),
 ('A &amp; B','A & B'),
 ('A<br>B','AB'),
 ('A<!--ignored-->B','AB'),
]
PROVENANCE={
 'purpose':'Test the documented remove-tags-and-normalize-whitespace contract beyond the primary author regression file.',
 'external_intent':'Original striptags docstring: unescape markup, remove tags, normalize whitespace to single spaces; author PR418 explains operation-order restoration.',
 'source_run':SOURCE_RUN,'phase':'Exploratory, authored after reading primary proposals; never an unseen holdout or primary-score replacement.',
 'case_design':'Twelve manually specified input/expected-output pairs; no implementation-derived expected results. Six deletion-created whitespace witnesses and six plain/tag/entity controls.',
 'controls':'Unmodified parent (negative) and pinned author-fixed source (positive), plus each strategy native-accepted candidate.',
 'boundaries':['Finite whitespace examples, not a full HTML parser specification.','No inference of causal learning advantage.','Primary 179 executable author tests and 5 skips remain the original declared boundary.'],
}

def main():
    data=HERE/'data';work=HERE/'work';out=HERE/'crosscheck';out.mkdir(exist_ok=True)
    packet=load(data/'public/future/future-04.json');authority=load(data/'private/future-04/authority.json')
    proposals=load(work/'proposals_1.json');env=build()
    raw=upstream.api(authority['repo'],'git/blobs/'+authority['head_blob'])
    author=base64.b64decode(raw['content'])
    assert hashlib.sha1(('blob '+str(len(author))+'\0').encode()+author).hexdigest()==authority['head_blob']
    variants={'parent':packet['source'],'author':author.decode()}
    for arm in ('adaptive','graph','guard'):
        rec=next(r for r in proposals['records'] if r['id']=='future-04' and r['arm']==arm)
        variants[arm]=patch(packet['source'],rec['call']['parsed']['edits'])
    test=('import pytest\nfrom markupsafe import Markup\n\nCASES = '+repr(CASES)+
          '\n\n@pytest.mark.parametrize("source, expected", CASES)\ndef test_documented_normalization(source, expected):\n    assert Markup(source).striptags() == expected\n')
    (out/'semantic_probe.py').write_text(test)
    dump(out/'PROBE_PROTOCOL.json',{**PROVENANCE,'cases':CASES,'test_sha256':hashlib.sha256(test.encode()).hexdigest(),
      'frozen_source_sha':os.environ.get('GITHUB_SHA'),'environment':env})
    import tarfile
    rows=[]
    for label,source in variants.items():
        with tempfile.TemporaryDirectory(prefix='semantic-probe-') as d:
            with tarfile.open(data/'private/future-04/base.tar.gz','r:gz') as tar:tar.extractall(d,filter='data')
            tree=Path(d)/'base';path=tree/authority['source_path'];path.write_text(source)
            (tree/'metalogic_semantic_probe.py').write_text(test)
            result=native_test(tree,'metalogic_semantic_probe.py',authority['source_path'],timeout=100)
            assert digest(tree/authority['test_path'])==authority['test_sha256']
            row={'variant':label,'candidate_sha256':digest(path),'result':result,'counts':dict(collections.Counter(result['tests'].values()))}
            rows.append(row);dump(out/(label+'_receipt.json'),row)
            print('SEMANTIC_PROBE',label,json.dumps(row['counts']),flush=True)
    s=load(work/'strategies.json')['strategies']['guard']
    guard=s['strategy']['guard'];scope=[]
    for p in sorted((data/'public/future').glob('*.json')):
        x=load(p);matched=[f['id'] for f in features(x) if holds(guard,f)]
        # A disabled module must have zero influence on a selected context.
        base={'case_sha256':digest(p),'mode':'ordinary'}
        def select(module,matches):return {**base,'module':module,'matches':matches} if matches else dict(base)
        check=(select(s,matched)==base) if not matched else True
        poisoned={'strategy':{'guidance':'ABSTAIN ALWAYS'},'status':'INVALID_FOR_THIS_CASE'}
        no_match_invariance=stable(select(s,[]))==stable(select(poisoned,[]))==stable(base)
        scope.append({'id':x['id'],'matches':matched,'hard_selection_baseline_identity_when_inactive':check,
          'inactive_module_substitution_invariance':no_match_invariance,
          'original_protocol_boundary':'Primary prompts displayed the module even with zero matches; this new hard selection is a proposed apparatus correction, not a primary rerun.'})
    dump(out/'inactive_module_controls.json',scope)
    summary={'source_run':SOURCE_RUN,'probe_run':os.environ.get('GITHUB_RUN_ID'),'probe_source_sha':os.environ.get('GITHUB_SHA'),
      'rows':[{k:v for k,v in r.items() if k!='result'} for r in rows],
      'parent_negative_control_failed':any(r['variant']=='parent' and r['counts'].get('failure',0)>0 for r in rows),
      'author_positive_control_passed':any(r['variant']=='author' and r['counts']=={'pass':len(CASES)} for r in rows),
      'inactive_module_controls':scope,'primary_outcome_unmodified':True,'epistemic_state':'WARRANTED_ONLY_FOR_ENUMERATED_NATIVE_PROBES'}
    dump(out/'SUMMARY.json',summary)
    dump(out/'MANIFEST.json',{str(p.relative_to(out)):digest(p) for p in sorted(out.rglob('*')) if p.is_file()})
    with zipfile.ZipFile(HERE/'semantic-crosscheck.zip','w',compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(out.rglob('*')):
            if p.is_file():z.write(p,p.relative_to(out))
    print('PROBE_SUMMARY',json.dumps(summary,sort_keys=True),flush=True)
    print('PROBE_ZIP_SHA256',digest(HERE/'semantic-crosscheck.zip'),flush=True)

if __name__=='__main__':main()
