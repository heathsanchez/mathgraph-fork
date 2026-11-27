"""Real native defect investigation. Data-only model proposals; separate native verifier."""
import argparse
import ast
import collections
import hashlib
import json
import math
import os
import pathlib
import re
import shutil
import sys
import tarfile
import tempfile
import time
from native import HERE, build, dump, load, digest, stable, native_test, repair_green, patch_source
sys.path.insert(0,str(HERE.parent/"gap_conditional_cell"))
from structural import _eval

MODEL="gpt-5.6-sol"
MAX_OUTPUT=2400
ARMS={1:("fixed",),2:("fixed","O1"),3:("fixed","O1","O2","O2_without_O1")}
FEATURES=("fail_hits","pass_hits","fail_rate","pass_rate","ochiai","trace_match","name_overlap",
          "test_overlap","diag_overlap","fail_lines","pass_lines","line_count","call_count",
          "branch_count","return_count","raise_count","oldscore")
ROOT=HERE/"stage"
def sha():return os.environ.get("GITHUB_SHA","LOCAL")
def words(s):
    s=re.sub(r"([a-z0-9])([A-Z])",r"\1 \2",s)
    return set(re.findall(r"[a-z][a-z0-9]+",s.lower()))
def bounded_ratio(a,b):return a/max(1,b)
def features(case):
    trace=case["trace"]; failed=[x for x in trace.values() if x["outcome"]=="failed"]
    passed=[x for x in trace.values() if x["outcome"]=="passed"]
    failure_names=" ".join(k.split("::")[-1].split("[")[0] for k,v in case["tests"].items() if v=="failure")
    test_tokens=words(case["test_excerpt"]+" "+failure_names)
    diag_tokens=words(case["diagnostic"])
    name_tokens=words(failure_names)
    source_path=case["source_path"]
    base_name=pathlib.PurePosixPath(source_path).name
    line_matches=set(int(x) for x in re.findall(r"(?:"
        +re.escape(source_path)+"|"+re.escape(base_name)+r"):(\d+)",case["diagnostic"]))
    out=[]
    for f in case["functions"]:
        span=set(range(f["start"],f["end"]+1))
        fail_inter=[set(t["lines"])&span for t in failed]
        pass_inter=[set(t["lines"])&span for t in passed]
        ef=sum(bool(x) for x in fail_inter);ep=sum(bool(x) for x in pass_inter)
        ff=len(set().union(*fail_inter)) if fail_inter else 0
        pp=len(set().union(*pass_inter)) if pass_inter else 0
        name=words(f["name"]);src=words(f["source"])
        import textwrap
        nodes=list(ast.walk(ast.parse(textwrap.dedent(f["source"]))))
        q={"fail_hits":ef,"pass_hits":ep,"fail_rate":bounded_ratio(ef,len(failed)),
            "pass_rate":bounded_ratio(ep,len(passed)),"ochiai":ef/math.sqrt(max(1,len(failed)*(ef+ep))),
            "trace_match":int(bool(span&line_matches)),"name_overlap":bounded_ratio(len(name&name_tokens),len(name)),
            "test_overlap":bounded_ratio(len(src&test_tokens),math.sqrt(max(1,len(src)*len(test_tokens)))),
            "diag_overlap":bounded_ratio(len(src&diag_tokens),math.sqrt(max(1,len(src)*len(diag_tokens)))),
            "fail_lines":bounded_ratio(ff,len(span)),"pass_lines":bounded_ratio(pp,len(span)),
            "line_count":len(span),"call_count":sum(isinstance(n,ast.Call) for n in nodes),
            "branch_count":sum(isinstance(n,(ast.If,ast.For,ast.While,ast.Try,ast.Match)) for n in nodes),
            "return_count":sum(isinstance(n,ast.Return) for n in nodes),
            "raise_count":sum(isinstance(n,ast.Raise) for n in nodes),"oldscore":0.0}
        out.append({"id":f["id"],"features":{k:round(v,7) if isinstance(v,float) else v for k,v in q.items()}})
    return out
def baseline(s):
    return 4*s["trace_match"]+3*s["ochiai"]+2*s["name_overlap"]+s["test_overlap"]+s["diag_overlap"]
def conventional(s):
    return 3*s["ochiai"]+s["fail_rate"]-s["pass_rate"]+s["name_overlap"]+s["test_overlap"]+s["trace_match"]
def safe_expr(expr):
    if not isinstance(expr,str) or not expr.strip() or len(expr)>300:
        raise ValueError("expression size")
    tree=ast.parse(expr,mode="eval")
    if sum(1 for _ in ast.walk(tree))>80:raise ValueError("expression complexity")
    legal=(ast.Expression,ast.BinOp,ast.UnaryOp,ast.BoolOp,ast.Compare,ast.Call,ast.Name,
           ast.Load,ast.Subscript,ast.Constant,ast.Add,ast.Sub,ast.Mult,ast.Mod,
           ast.USub,ast.UAdd,ast.Not,ast.And,ast.Or,ast.Eq,ast.NotEq,ast.Gt,ast.GtE,ast.Lt,ast.LtE)
    for n in ast.walk(tree):
        if not isinstance(n,legal):raise ValueError("unsupported syntax")
        if isinstance(n,ast.Name) and n.id not in ("s","abs"):raise ValueError("name")
        if isinstance(n,ast.Subscript) and not (isinstance(n.value,ast.Name) and n.value.id=="s" and
            isinstance(n.slice,ast.Constant) and n.slice.value in FEATURES):raise ValueError("field")
        if isinstance(n,ast.Call) and not (isinstance(n.func,ast.Name) and n.func.id=="abs" and len(n.args)==1 and not n.keywords):
            raise ValueError("call")
        if isinstance(n,ast.Constant) and type(n.value) in (float,int) and (not math.isfinite(n.value) or abs(n.value)>10000):
            raise ValueError("constant")
    return tree
def eval_score(expr,s):
    v=_eval(safe_expr(expr),s)
    if type(v) not in (int,float,bool) or not math.isfinite(float(v)) or abs(v)>1e18:
        raise ValueError("score must be finite bounded scalar")
    return float(v)
def method_score(arm,s,methods):
    if arm=="fixed":return baseline(s)
    if arm=="conventional":return conventional(s)
    m1=methods.get("O1",{})
    if m1.get("status")!="QUALIFIED_EXECUTABLE_CANDIDATE":
        raise ValueError("O1 not admitted")
    first=eval_score(m1["expression"],s)
    if arm=="O1":return first
    m2=methods.get("O2",{})
    if m2.get("status")!="QUALIFIED_EXECUTABLE_CANDIDATE":
        raise ValueError("O2 not admitted")
    return eval_score(m2["expression"],dict(s,oldscore=0.0 if arm=="O2_without_O1" else first))
def rank(case,arm,methods):
    scores=[(method_score(arm,x["features"],methods),x["id"]) for x in features(case)]
    return [i for _,i in sorted(scores,key=lambda x:(-x[0],x[1]))]
def earlier(stage):
    if stage==1:return {"source_sha":sha(),"history":[],"methods":{}}
    p=load(ROOT/"prior"/"receipt.json")
    assert p["source_sha"]==sha() and len(p["history"])==stage-1
    return p
def active_methods(stage,prior):
    methods=dict(prior["methods"])
    if stage>1:
        q=load(ROOT/"method"/"method.json")
        assert q["source_sha"]==sha() and q["after_stage"]==stage-1 and q["prior_digest"]==stable(prior)
        methods["O"+str(stage-1)]=q
    return methods
def compact_history(prior):
    out=[]
    for h in prior["history"]:
        for c in h["cases"]:
            out.append({"id":c["id"],"author_location":c["author_location"],
              "arms":{a:{"qualified":r["qualified"],"selected":r.get("selected"),"author_rank":r.get("author_rank"),
                         "failure":r.get("failure_summary","")} for a,r in c["arms"].items()}})
    return out
def prompt_repair(case,arm,methods,prior,selected):
    bodies={f["id"]:f["source"] for f in case["functions"] if f["id"] in selected}
    inventory=features(case)
    return "\n".join([
      "You are diagnosing a genuine upstream software defect. The exact maintainer regression test failed on this original source.",
      "Return one JSON object with key edits, value an array of 1 or 2 objects {id,replacement}; or {\"edits\":[]} if insufficient evidence.",
      "Each replacement must be the complete function or method source, same name, correctly indented or dedented. Edit ONLY supplied selected function bodies. No imports, test detection, test edits, output forgery, unrelated changes, external actions or network. Prefer smallest general semantic repair; do not hardcode failing examples.",
      "Only the original source and test-side observations are provided; the maintainer fix, PR title and changed location are withheld.",
      "Source path: "+case["source_path"],
      "Exact author regression test excerpts: "+case["test_excerpt"],
      "Native failure diagnostics: "+case["diagnostic"][-10000:],
      "Module header: "+case["module_header"],
      "Complete shared function inventory with measured failing/passing coverage and lexical features: "+json.dumps(inventory,separators=(",",":")),
      "Earlier verified investigation evidence (same in every arm): "+json.dumps(compact_history(prior),separators=(",",":")),
      "Earlier learned method expressions (same in every arm): "+json.dumps({k:v.get("expression") for k,v in methods.items()}),
      "Selected full function bodies: "+json.dumps(bodies,ensure_ascii=False),
      "Output JSON only. Independent native tests decide success."
    ])
def call_model(prompt):
    from openai import OpenAI
    rec={"prompt_sha256":hashlib.sha256(prompt.encode()).hexdigest(),"prompt_chars":len(prompt)}
    if not os.environ.get("OPENAI_API_KEY"):
        rec["status"]="UNKNOWN_MISSING_CREDENTIAL";return rec
    t=time.monotonic()
    try:
        response=OpenAI(api_key=os.environ["OPENAI_API_KEY"],timeout=90,max_retries=0).responses.create(
            model=MODEL,reasoning={"effort":"low"},input=prompt,max_output_tokens=MAX_OUTPUT)
        rec["model"]=response.model
        rec["usage"]=response.usage.model_dump() if response.usage else None
        raw=(response.output_text or "").strip()
        rec["response_sha256"]=hashlib.sha256(raw.encode()).hexdigest()
        try:
            p=json.loads(raw)
            if not isinstance(p,dict):raise ValueError("non object")
            rec["response"]=p;rec["status"]="RESPONSE"
        except (ValueError,TypeError):
            rec["status"]="INVALID_RESPONSE"
    except Exception as exc:
        rec["status"]="API_ERROR";rec["error_type"]=type(exc).__name__;rec["http_status"]=getattr(exc,"status_code",None)
    rec["seconds"]=round(time.monotonic()-t,3)
    return rec
def cases():
    return [load(p) for p in sorted((ROOT/"public").glob("case-*.json"))]
def propose(stage):
    prior=earlier(stage);methods=active_methods(stage,prior)
    rows=[];out={"source_sha":sha(),"stage":stage,"prior_digest":stable(prior),"methods":methods,"rows":rows}
    for c in cases():
        arms=list(ARMS[stage])
        if int(c["id"].split("-")[-1])%2==0:arms.reverse()
        for arm in arms:
            rec={"id":c["id"],"arm":arm,"public_digest":stable(c)}
            try:
                ranking=rank(c,arm,methods);selected=ranking[:2]
                rec.update({"selected":selected,"ranking":ranking})
                rec["call"]=call_model(prompt_repair(c,arm,methods,prior,selected))
            except (ValueError,TypeError,KeyError,ArithmeticError,RecursionError,SyntaxError) as exc:
                rec["call"]={"status":"UNKNOWN_METHOD_INVALID","error_type":type(exc).__name__}
            rows.append(rec);dump(ROOT/"proposals.json",out)
            print("PROPOSE",stage,c["id"],arm,rec["call"]["status"],flush=True)
    dump(ROOT/"proposals.json",out)
def verify(stage):
    prior=earlier(stage);methods=active_methods(stage,prior)
    p=load(ROOT/"proposals.json");assert p["source_sha"]==sha() and p["stage"]==stage
    assert p["prior_digest"]==stable(prior) and p["methods"]==methods
    assert len(p["rows"])==len(cases())*len(ARMS[stage])
    assert len({(r["id"],r["arm"]) for r in p["rows"]})==len(p["rows"])
    env=build() if cases() else None
    history=[]
    for c in cases():
        case_dir=ROOT/"private"/c["id"];a=load(case_dir/"authority.json")
        assert a["id"]==c["id"] and a["source_sha256"]==c["source_sha256"] and a["test_sha256"]==c["test_sha256"]
        assert a["overlay_archive_sha256"]==digest(case_dir/"base.tar.gz")
        rr={"id":c["id"],"repo":a["repo"],"pr":a["pr"],"parent":a["parent"],"merge":a["merge"],"author_location":a["location"],
            "features":features(c),"native_base_counts":dict(collections.Counter(a["native"]["base"]["tests"].values())),
            "conventional_rank":rank(c,"conventional",methods).index(a["location"])+1,"arms":{}}
        with tempfile.TemporaryDirectory(prefix="verify-native-") as tmp:
            tmp=pathlib.Path(tmp)
            with tarfile.open(case_dir/"base.tar.gz","r:gz") as tar:tar.extractall(tmp,filter="data")
            base=tmp/"base";sp=a["source_path"];tp=a["test_path"]
            assert digest(base/sp)==a["source_sha256"] and digest(base/tp)==a["test_sha256"]
            old=(base/sp).read_text(encoding="utf-8")
            # Recheck exact base with verifier's environment before scoring.
            repeat=native_test(base,tp,sp)
            env_ok=env==a["environment"] and repeat["status"]=="EXECUTED" and repeat["tests"]==a["native"]["base"]["tests"] and repeat.get("returncode")==1
            rr["base_replay"]=repeat;rr["environment_match"]=env==a["environment"]
            for arm in ARMS[stage]:
                r=next(x for x in p["rows"] if x["id"]==c["id"] and x["arm"]==arm)
                assert r["public_digest"]==stable(c)
                o={"qualified":False,"call":r["call"],"selected":r.get("selected",[])}
                rr["arms"][arm]=o
                if "ranking" not in r:
                    o["status"]="UNKNOWN_METHOD";continue
                ranking=rank(c,arm,methods)
                assert ranking==r["ranking"] and ranking[:2]==r["selected"]
                o["author_rank"]=ranking.index(a["location"])+1
                o["author_top_two"]=a["location"] in r["selected"]
                assert r["call"]["prompt_sha256"]==hashlib.sha256(prompt_repair(c,arm,methods,prior,r["selected"]).encode()).hexdigest()
                if not env_ok:
                    o["status"]="UNKNOWN_BASE_REPLAY_OR_ENVIRONMENT";continue
                call=r["call"]
                if call["status"]!="RESPONSE" or call.get("model")!=MODEL:
                    o["status"]="UNKNOWN_API_OR_MODEL";continue
                edits=call["response"].get("edits")
                try:
                    candidate=patch_source(old,edits,r["selected"])
                except (ValueError,TypeError,KeyError,SyntaxError,RecursionError) as exc:
                    o["status"]="UNKNOWN_DECLINED_OR_INVALID_EDIT";o["failure_summary"]=str(exc)[:200];continue
                tree=tmp/("candidate-"+arm);shutil.copytree(base,tree)
                (tree/sp).write_text(candidate,encoding="utf-8")
                assert digest(tree/tp)==a["test_sha256"]
                t=time.monotonic()
                trial=native_test(tree,tp,sp)
                o["native_seconds"]=round(time.monotonic()-t,3)
                o["native"]=trial;o["candidate_sha256"]=digest(tree/sp);o["native_counts"]=dict(collections.Counter(trial["tests"].values()))
                o["qualified"]=repair_green(a["native"]["base"],trial)
                o["status"]="WARRANTED_BOUNDED_NATIVE_REPAIR" if o["qualified"] else ("REJECTED_NATIVE_REGRESSION" if trial["status"]=="EXECUTED" else "UNKNOWN_NATIVE")
                o["failure_summary"]="" if o["qualified"] else trial["diagnostic"][-1000:]
                shutil.rmtree(tree)
                print("NATIVE_SCORE",stage,c["id"],arm,o["status"],o["native_counts"],"AUTHOR_RANK",o["author_rank"],flush=True)
        history.append(rr)
    current={"stage":stage,"cases":history}
    prior["history"].append(current);prior["methods"]=methods
    prior["scope"]="Real selected original upstream author-test files; not full repo correctness or independent model-training nonexposure."
    prior["strict_G2_G3"]="UNKNOWN"
    totals={}
    for h in prior["history"]:
        stats={}
        for arm in ARMS[h["stage"]]:
            ar=[c["arms"][arm] for c in h["cases"]]
            stats[arm]={"repairs":sum(x["qualified"] for x in ar),"cases":len(ar),
                "top_two":sum(x.get("author_top_two",False) for x in ar),
                "calls":sum(x["call"].get("status") in ("RESPONSE","INVALID_RESPONSE","API_ERROR") for x in ar),
                "tokens":sum((x["call"].get("usage") or {}).get("total_tokens",0) for x in ar),
                "native_attempts":sum("native" in x for x in ar)}
        totals[str(h["stage"])]=stats
    prior["totals"]=totals
    if stage==3:
        prior["causal_heldout_candidates"]=[c["id"] for c in history if c["arms"]["O2"]["qualified"] and not c["arms"]["O2_without_O1"]["qualified"] and not c["arms"]["O1"]["qualified"] and not c["arms"]["fixed"]["qualified"]]
        prior["comparative_status"]="CANDIDATE_REQUIRES_CAUSAL_REVIEW" if prior["causal_heldout_candidates"] else "NO_OBSERVED_CAUSAL_REPAIR_ADVANTAGE"
    dump(ROOT/"receipt.json",prior)
    print("REAL_NATIVE_TOTALS",json.dumps(totals,sort_keys=True),"STRICT_G2_G3_UNKNOWN",flush=True)

def method_prompt(stage,prior):
    evidence=[]
    for h in prior["history"]:
        for c in h["cases"]:
            rows=c["features"]
            # Use the complete prior feature inventory, never future data.
            evidence.append({"id":c["id"],"author_location":c["author_location"],
                "feature_rows":rows,"arms":{k:{"selected":v.get("selected"),"qualified":v["qualified"],
                    "author_rank":v.get("author_rank"),"failure":v.get("failure_summary","")} for k,v in c["arms"].items()}})
    return "\n".join([
      "You are improving the investigation method itself from completed real upstream native defect repairs.",
      "Invent a reusable scalar scoring expression that ranks which two functions to inspect for future real defects. You have actual earlier author repair locations and native repair outcomes, not future source or tests.",
      "Return exactly {\"expression\":\"...\"} JSON. Use only s[\"feature\"] numeric fields, arithmetic +,-,*,%, comparisons, and/or/not, abs(), bounded numeric constants. Higher score is selected first. No imports, file access, hardcoded task ids, or arbitrary execution.",
      "Available features: "+json.dumps(FEATURES),
      "fail_hits/pass_hits count tests that execute a function; fail_rate/pass_rate normalize by number of each test outcome; ochiai is coverage suspiciousness; trace_match is traceback line within function; name_overlap,test_overlap,diag_overlap are lexical normalized overlaps; fail_lines/pass_lines are fractions of function lines covered; line_count,call_count,branch_count,return_count,raise_count are static AST metrics. oldscore is zero for O1; for O2 it is the learned O1 score, and may be composed with new features.",
      "Fixed conventional policy: 4*trace_match+3*ochiai+2*name_overlap+test_overlap+diag_overlap.",
      "Prior method expressions: "+json.dumps({k:v.get("expression") for k,v in prior["methods"].items()}),
      "Completed source-native evidence: "+json.dumps(evidence,separators=(",",":")),
      "Propose a new executable investigation rule which addresses a concrete prior miss or inefficiency. Do not fit task names or claim a guaranteed improvement."
    ])
def learn(stage):
    prior=load(ROOT/"prior"/"receipt.json")
    assert prior["source_sha"]==sha() and len(prior["history"])==stage
    if not any(h["cases"] for h in prior["history"]):
        call={"status":"UNKNOWN_NO_NATIVE_TRAINING"}
    else:
        call=call_model(method_prompt(stage,prior))
    dump(ROOT/"method_raw.json",{"source_sha":sha(),"after_stage":stage,"prior_digest":stable(prior),"call":call})
    print("LEARN_METHOD",stage,call["status"],flush=True)
def qualify_method(stage):
    prior=load(ROOT/"prior"/"receipt.json");p=load(ROOT/"method_raw.json")
    assert p["source_sha"]==sha() and p["after_stage"]==stage and p["prior_digest"]==stable(prior)
    call=p["call"];out={"source_sha":sha(),"after_stage":stage,"prior_digest":stable(prior),"call":call,"status":"UNKNOWN_METHOD"}
    if call["status"]=="RESPONSE" and call.get("model")==MODEL:
        assert call["prompt_sha256"]==hashlib.sha256(method_prompt(stage,prior).encode()).hexdigest()
        try:
            expr=call["response"]["expression"];safe_expr(expr)
            before=prior["methods"];training=[]
            for h in prior["history"]:
                for c in h["cases"]:
                    scores=[]
                    for row in c["features"]:
                        s=dict(row["features"])
                        if stage==2 and before.get("O1",{}).get("status")=="QUALIFIED_EXECUTABLE_CANDIDATE":
                            s["oldscore"]=eval_score(before["O1"]["expression"],s)
                        scores.append((eval_score(expr,s),row["id"]))
                    ids=[k for _,k in sorted(scores,key=lambda x:(-x[0],x[1]))]
                    training.append({"id":c["id"],"author_rank":ids.index(c["author_location"])+1})
            if not training:raise ValueError("no training")
            out.update({"expression":expr,"training":training,"status":"QUALIFIED_EXECUTABLE_CANDIDATE",
                        "uses_predecessor":stage==2 and any(isinstance(n,ast.Constant) and n.value=="oldscore" for n in ast.walk(safe_expr(expr)))})
        except (ValueError,TypeError,ArithmeticError,RecursionError,SyntaxError,KeyError) as exc:
            out["error_type"]=type(exc).__name__
    dump(ROOT/"method.json",out)
    print("METHOD_CANDIDATE",stage,json.dumps({k:v for k,v in out.items() if k!="call"},sort_keys=True),flush=True)
def preflight():
    for expr in ('s["ochiai"]*4+s["test_overlap"]','s["oldscore"]+2*s["trace_match"]'):
        assert isinstance(eval_score(expr,{k:1 for k in FEATURES}),float)
    for expr in ('__import__("os")','s["not_a_field"]','s.__class__','open("a")'):
        try:eval_score(expr,{k:1 for k in FEATURES})
        except (ValueError,TypeError,KeyError):continue
        raise AssertionError("bad expression accepted")
    print("METHOD_GRAMMAR_PREFLIGHT_OK")
if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("mode",choices=["preflight","propose","verify","learn","qualify_method"])
    ap.add_argument("stage",type=int,nargs="?",choices=[1,2,3]);a=ap.parse_args()
    if a.mode=="preflight":preflight()
    else:globals()[a.mode](a.stage)
