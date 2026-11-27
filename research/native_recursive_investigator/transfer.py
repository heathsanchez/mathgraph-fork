"""Paired frozen-method transfer on actual upstream defects."""
import argparse
import collections
import hashlib
import json
import os
import pathlib
import shutil
import tarfile
import tempfile
import time
from native import HERE, build, dump, load, digest, stable, native_test, repair_green, patch_source, admit_red_green
import loop
from freeze_transfer import EXPECTED

ROOT=HERE/"transfer-stage"
FROZEN=ROOT/"frozen"
ARMS=("fixed","conventional","O1","O2")
MAX_CALLS=16

def inputs():
    common=load(FROZEN/"common.json")
    assert common["ready"] is True and common["source_sha"]==os.environ["GITHUB_SHA"]
    assert common["admission_count"]>=4 and len(common["case_ids"])==len(set(common["case_ids"]))==4
    ctx=common["prior_context"]
    assert stable(ctx)==common["prior_context_sha256"]
    methods=ctx["methods"]
    for k,expr in EXPECTED.items():
        assert methods[k]["expression"]==expr and methods[k]["status"]=="QUALIFIED_EXECUTABLE_CANDIDATE"
    cases=[]
    for ident in common["case_ids"]:
        p=FROZEN/"public"/(ident+".json")
        assert digest(p)==common["public_sha256"][ident]
        c=load(p)
        assert c["id"]==ident and not {"location","locations","repo","merge","parent"}&set(c)
        cases.append(c)
    return common,ctx["prior"],methods,cases

def plans(case,prior,methods):
    ranks={a:loop.rank(case,a,methods) for a in (*ARMS,"O2_without_O1")}
    assert ranks["O2"]==ranks["O2_without_O1"],"frozen predecessor independence violated"
    out={}
    for arm in ARMS:
        selected=ranks[arm][:2]
        prompt=loop.prompt_repair(case,arm,methods,prior,selected)
        key=hashlib.sha256(prompt.encode()).hexdigest()
        out[arm]={"ranking":ranks[arm],"selected":selected,"prompt":prompt,"key":key}
    return out,ranks["O2_without_O1"]

def propose():
    common,prior,methods,cases=inputs()
    assert os.environ.get("OPENAI_API_KEY"),"stored API key absent"
    out={"source_sha":os.environ["GITHUB_SHA"],"common_sha256":stable(common),"calls":{},"cases":[]}
    for i,case in enumerate(cases):
        p,ablation=plans(case,prior,methods)
        rr={"id":case["id"],"public_digest":stable(case),"arms":{},"ablation_ranking":ablation}
        out["cases"].append(rr)
        # Rotate the arm order to avoid a systematic API order effect.
        order=ARMS[i%len(ARMS):]+ARMS[:i%len(ARMS)]
        for arm in order:
            x=p[arm];key=x["key"]
            if key not in out["calls"]:
                assert len(out["calls"])<MAX_CALLS
                out["calls"][key]=loop.call_model(x["prompt"])
                assert out["calls"][key]["prompt_sha256"]==key
            rr["arms"][arm]={k:v for k,v in x.items() if k!="prompt"}
            dump(ROOT/"proposals.json",out)
            print("FROZEN_PROPOSAL",case["id"],arm,key[:12],out["calls"][key]["status"],flush=True)
    print("ACTUAL_API_CALLS",len(out["calls"]),flush=True)

def blob(p):
    b=p.read_bytes()
    return hashlib.sha1(("blob "+str(len(b))+"\0").encode()+b).hexdigest()

def verify():
    assert not os.environ.get("OPENAI_API_KEY"),"verifier must be credential-free"
    common,prior,methods,cases=inputs()
    gate=load(FROZEN/"gate.json")
    assert gate["status"]=="READY_FOR_FROZEN_TRANSFER" and gate["common_sha256"]==stable(common)
    assert gate["source_sha"]==os.environ["GITHUB_SHA"]
    p=load(ROOT/"proposals.json")
    assert p["source_sha"]==os.environ["GITHUB_SHA"] and p["common_sha256"]==stable(common)
    assert len(p["calls"])<=MAX_CALLS and len(p["cases"])==4
    assert [x["id"] for x in p["cases"]]==common["case_ids"]
    assert set(p["calls"])=={a["key"] for c in p["cases"] for a in c["arms"].values()}
    env=build()
    out={"source_sha":os.environ["GITHUB_SHA"],"common_sha256":stable(common),
         "old_run":common["prior_context"]["old_run"],"methods":methods,"cases":[],
         "api_calls":len(p["calls"]),"api_tokens":sum((v.get("usage") or {}).get("total_tokens",0) for v in p["calls"].values()),
         "unique_native_candidate_runs":0,"strict_G2_G3":"UNKNOWN_NO_PREDECESSOR_DEPENDENCY",
         "scope":"four distinct real author-selected regression test files, exact source identities; not full-repo correctness"}
    for case,rec,row in zip(cases,p["cases"],gate["selected"]):
        assert case["id"]==rec["id"]==row["case"]
        assert rec["public_digest"]==stable(case) and set(rec["arms"])==set(ARMS)
        q,ablation=plans(case,prior,methods)
        assert rec["ablation_ranking"]==ablation
        for arm in ARMS:
            assert rec["arms"][arm]=={k:v for k,v in q[arm].items() if k!="prompt"}
            assert p["calls"][q[arm]["key"]]["prompt_sha256"]==q[arm]["key"]
        d=FROZEN/"private"/case["id"];a=load(d/"authority.json")
        assert a["id"]==case["id"] and a["repo"]==row["repo"] and a["parent"]==row["parent"] and a["merge"]==row["merge"]
        assert a["source_sha256"]==case["source_sha256"] and a["test_sha256"]==case["test_sha256"]
        assert a["overlay_archive_sha256"]==digest(d/"base.tar.gz")
        assert admit_red_green(a["native"]["base"],a["native"]["author"])
        rr={"id":case["id"],"repo":a["repo"],"pr":a["pr"],"parent":a["parent"],"merge":a["merge"],
            "author_locations":a["locations"],"features":loop.features(case),"arms":{}}
        out["cases"].append(rr)
        with tempfile.TemporaryDirectory(prefix="transfer-native-") as tmp:
            tmp=pathlib.Path(tmp)
            with tarfile.open(d/"base.tar.gz","r:gz") as tar:tar.extractall(tmp,filter="data")
            base=tmp/"base";sp=a["source_path"];tp=a["test_path"]
            assert digest(base/sp)==a["source_sha256"] and digest(base/tp)==a["test_sha256"]
            assert blob(base/sp)==a["base_blob"] and blob(base/tp)==a["author_test_blob"]
            old=(base/sp).read_text(encoding="utf-8")
            repeat=native_test(base,tp,sp)
            env_ok=(env==a["environment"] and repeat["status"]=="EXECUTED" and
                    repeat["tests"]==a["native"]["base"]["tests"] and repeat.get("returncode")==1)
            rr["environment_match"]=env==a["environment"]
            rr["base_replay"]=repeat
            rr["base_counts"]=dict(collections.Counter(a["native"]["base"]["tests"].values()))
            rr["author_counts"]=dict(collections.Counter(a["native"]["author"]["tests"].values()))
            tested={}
            for arm in ARMS:
                x=q[arm];call=p["calls"][x["key"]]
                o={"qualified":False,"selected":x["selected"],"author_ranks":[x["ranking"].index(k)+1 for k in a["locations"]],
                   "author_top_two":set(a["locations"])<=set(x["selected"]),"call_key":x["key"],
                   "call_status":call["status"],"attributed_tokens":(call.get("usage") or {}).get("total_tokens",0)}
                rr["arms"][arm]=o
                if not env_ok:
                    o["status"]="UNKNOWN_BASE_REPLAY_OR_ENVIRONMENT";continue
                if call["status"]!="RESPONSE" or call.get("model")!=loop.MODEL:
                    o["status"]="UNKNOWN_API_OR_MODEL";continue
                try:
                    candidate=patch_source(old,call["response"].get("edits"),x["selected"])
                except (ValueError,TypeError,KeyError,SyntaxError,RecursionError) as exc:
                    o["status"]="UNKNOWN_DECLINED_OR_INVALID_EDIT";o["reason"]=str(exc)[:200];continue
                key=hashlib.sha256(candidate.encode("utf-8")).hexdigest()
                o["candidate_sha256"]=key
                if key not in tested:
                    tree=tmp/("candidate-"+arm);shutil.copytree(base,tree)
                    (tree/sp).write_text(candidate,encoding="utf-8")
                    assert digest(tree/sp)==key and digest(tree/tp)==a["test_sha256"]
                    t=time.monotonic();trial=native_test(tree,tp,sp)
                    tested[key]={"trial":trial,"seconds":round(time.monotonic()-t,3),"first_arm":arm}
                    out["unique_native_candidate_runs"]+=1
                    shutil.rmtree(tree)
                t=tested[key];trial=t["trial"]
                o["shared_native_result_from"]=t["first_arm"]
                o["native_seconds"]=t["seconds"];o["native"]=trial
                o["native_counts"]=dict(collections.Counter(trial["tests"].values()))
                o["qualified"]=repair_green(a["native"]["base"],trial)
                o["status"]="WARRANTED_BOUNDED_NATIVE_REPAIR" if o["qualified"] else ("REJECTED_NATIVE_REGRESSION" if trial["status"]=="EXECUTED" else "UNKNOWN_NATIVE")
                print("TRANSFER_NATIVE_SCORE",case["id"],arm,o["status"],o["native_counts"],"AUTHOR_RANKS",o["author_ranks"],flush=True)
            rr["O2_without_O1"]={"ranking_identical":True,"shares_O2_proposal_and_native_result":True,
                                "qualified":rr["arms"]["O2"]["qualified"]}
        dump(ROOT/"transfer-receipt.json",out)
    out["totals"]={arm:{"repairs":sum(c["arms"][arm]["qualified"] for c in out["cases"]),
                         "cases":len(out["cases"]),"top_two":sum(c["arms"][arm]["author_top_two"] for c in out["cases"]),
                         "attributed_tokens":sum(c["arms"][arm]["attributed_tokens"] for c in out["cases"]),
                         "actual_distinct_prompts":len({c["arms"][arm]["call_key"] for c in out["cases"]})} for arm in ARMS}
    out["O2_ablation_identical_on_all_cases"]=all(c["O2_without_O1"]["ranking_identical"] for c in out["cases"])
    out["status"]="COMPLETED_BOUNDED_TRANSFER_COMPARISON"
    dump(ROOT/"transfer-receipt.json",out)
    print("TRANSFER_TOTALS",json.dumps(out["totals"],sort_keys=True),"UNIQUE_API_CALLS",out["api_calls"],"UNIQUE_NATIVE_CANDIDATES",out["unique_native_candidate_runs"],"STRICT_G2_G3_UNKNOWN",flush=True)

if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("mode",choices=["propose","verify"]);globals()[ap.parse_args().mode]()
