"""Fail-closed cohort freeze. No model SDK or OpenAI credentials."""
import json
import os
import pathlib
import shutil
from native import HERE, dump, load, digest, stable, admit_red_green

ROOT=HERE/"transfer-stage"
OLD_SOURCE="fa24f0dd2a8e5bd37531a671c19dd171ad34d6f7"
OLD_RUN=45935059870
EXPECTED={
 "O1":'20*s["ochiai"]+s["fail_rate"]-s["pass_rate"]+s["test_overlap"]+0.25*s["trace_match"]',
 "O2":'100*s["ochiai"]+s["fail_rate"]-s["pass_rate"]+s["test_overlap"]',
}

def previous():
    prior=ROOT/"old"
    r1=load(prior/"receipt-1"/"receipt.json")
    r2=load(prior/"receipt-2"/"receipt.json")
    m1=load(prior/"method-1"/"method.json")
    m2=load(prior/"method-2"/"method.json")
    for x in (r1,r2,m1,m2):assert x["source_sha"]==OLD_SOURCE
    assert len(r1["history"])==1 and len(r1["history"][0]["cases"])==2
    assert len(r2["history"])==2 and r2["history"][0]==r1["history"][0] and not r2["history"][1]["cases"]
    assert r2["methods"]["O1"]==m1
    assert m1["prior_digest"]==stable(r1) and m2["prior_digest"]==stable(r2)
    for k,m,n in (("O1",m1,1),("O2",m2,2)):
        assert m["after_stage"]==n and m["status"]=="QUALIFIED_EXECUTABLE_CANDIDATE"
        assert m["expression"]==EXPECTED[k] and not m["uses_predecessor"]
    return {"old_run":OLD_RUN,"old_source":OLD_SOURCE,"prior":r1,"methods":{"O1":m1,"O2":m2}}

def main():
    pool=load(HERE/"transfer_pool.json")
    context=previous()
    assert not os.environ.get("OPENAI_API_KEY"),"gate must not receive model secret"
    source=os.environ["GITHUB_SHA"]
    ledgers=[];admitted=[];seen=set()
    for shard in range(8):
        root=ROOT/"shards"/f"native-transfer-admit-{shard}"
        ledger=load(root/"admission.json")
        assert ledger["source_sha"]==source and ledger["shard"]==shard
        assert ledger["repository_order"]==pool[shard*4:shard*4+4]
        ledgers.append(ledger)
        assert len(ledger["selected"])<=2
        for row in ledger["selected"]:
            assert row["repo"] in ledger["repository_order"] and row["repo"] not in seen
            seen.add(row["repo"])
            ident=row["case"]
            private=root/"private-candidate"/ident
            public=root/"public-candidate"/(ident+".json")
            a=load(private/"authority.json");c=load(public)
            assert a["id"]==ident==c["id"] and a["repo"]==row["repo"]
            assert a["parent"]==row["parent"] and a["merge"]==row["merge"]
            assert a["environment"]==ledger["environment"]
            assert a["source_sha256"]==c["source_sha256"] and a["test_sha256"]==c["test_sha256"]
            assert digest(private/"base.tar.gz")==a["overlay_archive_sha256"]
            assert admit_red_green(a["native"]["base"],a["native"]["author"])
            assert 1<=len(a["locations"])<=2 and set(a["locations"])<={f["id"] for f in c["functions"]}
            assert "location" not in c and "locations" not in c and "repo" not in c
            admitted.append((pool.index(row["repo"]),row,private,public))
    admitted.sort(key=lambda t:t[0])
    chosen=admitted[:4] if len(admitted)>=4 else []
    ready=len(chosen)==4
    common={"source_sha":source,"ready":ready,"case_ids":[x[1]["case"] for x in chosen],
            "prior_context":context,"prior_context_sha256":stable(context),"admission_count":len(admitted),
            "public_sha256":{x[1]["case"]:digest(x[3]) for x in chosen}}
    frozen={"source_sha":source,"status":"READY_FOR_FROZEN_TRANSFER" if ready else "UNKNOWN_INSUFFICIENT_ADMISSION",
            "pool":pool,"ledgers":ledgers,"all_admitted":[x[1] for x in admitted],
            "selected":[x[1] for x in chosen],"common_sha256":stable(common),"old_run":OLD_RUN}
    dump(ROOT/"frozen"/"gate.json",frozen)
    if ready:
        for _,row,private,public in chosen:
            target=ROOT/"frozen"/"private"/row["case"]
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copytree(private,target)
            target=ROOT/"frozen"/"public"/public.name
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(public,target)
        dump(ROOT/"frozen"/"common.json",common)
    print("TRANSFER_ADMISSION",json.dumps({"status":frozen["status"],"admitted":len(admitted),"selected":frozen["selected"]},sort_keys=True),flush=True)
    with open(os.environ["GITHUB_OUTPUT"],"a") as f:f.write("ready="+str(ready).lower()+"\n")

if __name__=="__main__":main()
