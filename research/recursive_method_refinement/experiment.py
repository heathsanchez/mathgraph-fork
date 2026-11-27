#!/usr/bin/env python3
"""Small bounded constructor-acquisition pilot. Model output is inert AST data."""
import argparse
import ast
import copy
import hashlib
import itertools
import json
import math
import os
import random
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "gap_conditional_cell"))
from structural import _eval

MODEL = "gpt-5.6-sol"
MAX_CALLS_PER_STAGE = 2
DOMAIN = tuple(range(-2, 3))
CONTRACT = {
    1: "The output is the distance between two relevant integer measurements.",
    2: "The output is the total variation along three relevant integer measurements in order.",
    3: "The output is the distance between the total variation of the first three and the total variation of the last three of four ordered measurements.",
}

def canonical(x):
    return json.dumps(x, sort_keys=True, separators=(",", ":"), allow_nan=False)

def digest(x):
    return hashlib.sha256(canonical(x).encode()).hexdigest()

def sha():
    return os.environ.get("GITHUB_SHA", "LOCAL_PREFLIGHT")

def read(p):
    return json.loads(p.read_text())

def write(p, x):
    p.write_text(json.dumps(x, indent=2, sort_keys=True, allow_nan=False) + "\n")

def dist(a, b):
    return int(math.dist((a,), (b,)))

def oracle(stage, v):
    if stage == 1:
        return dist(*v)
    if stage == 2:
        return sum(dist(a,b) for a,b in zip(v,v[1:]))
    return dist(oracle(2,v[:3]), oracle(2,v[1:]))

def population(stage, transfer):
    n = stage + 2
    rng = random.Random(27112026 + stage * 137 + int(transfer) * 7919)
    fields = [("t" if transfer else "d") + str(i) for i in range(n)]
    roles = rng.sample(fields, stage+1)
    rows = []
    for values in itertools.product(DOMAIN, repeat=n):
        s = dict(zip(fields,values))
        rows.append((s,oracle(stage,[s[k] for k in roles])))
    ids = list(range(len(rows)))
    rng.shuffle(ids)
    train = [rows[i] for i in ids[:min(40,len(ids)//3)]]
    hold = [rows[i] for i in ids[min(40,len(ids)//3):]]
    return fields, train, hold

class Invalid(ValueError):
    pass

class Replace(ast.NodeTransformer):
    def __init__(self, mapping):
        self.mapping = mapping
    def visit_Name(self, node):
        return copy.deepcopy(self.mapping.get(node.id,node))

def parse_template(obj, macros):
    if not isinstance(obj,dict) or set(obj) != {"arity","expression"}:
        raise Invalid("schema")
    n, expr = obj["arity"], obj["expression"]
    if type(n) is not int or not 1 <= n <= 4 or not isinstance(expr,str) or len(expr)>300:
        raise Invalid("size_or_arity")
    tree = ast.parse(expr,mode="eval").body
    if sum(1 for _ in ast.walk(tree))>80:
        raise Invalid("raw_nodes")
    deps=set()
    def expand(node):
        if isinstance(node,ast.Name):
            if node.id not in [f"F{i}" for i in range(n)]:
                raise Invalid("unknown_parameter")
            return copy.deepcopy(node)
        if isinstance(node,ast.Constant):
            if type(node.value) is not int or abs(node.value)>32:
                raise Invalid("constant")
            return copy.deepcopy(node)
        if isinstance(node,ast.BinOp) and type(node.op) in (ast.Add,ast.Sub,ast.Mult,ast.Mod):
            return ast.BinOp(left=expand(node.left),op=node.op,right=expand(node.right))
        if isinstance(node,ast.UnaryOp) and type(node.op) in (ast.USub,ast.UAdd):
            return ast.UnaryOp(op=node.op,operand=expand(node.operand))
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and not node.keywords:
            name=node.func.id
            args=[expand(a) for a in node.args]
            if name=="abs" and len(args)==1:
                return ast.Call(func=ast.Name(id="abs",ctx=ast.Load()),args=args,keywords=[])
            if name in macros and len(args)==macros[name]["arity"]:
                deps.add(name)
                return Replace({f"F{i}":a for i,a in enumerate(args)}).visit(copy.deepcopy(macros[name]["tree"]))
        raise Invalid("unsupported_node")
    tree=ast.fix_missing_locations(expand(tree))
    if sum(1 for _ in ast.walk(tree))>200:
        raise Invalid("expanded_nodes")
    used={x.id for x in ast.walk(tree) if isinstance(x,ast.Name) and x.id!="abs"}
    if used!={f"F{i}" for i in range(n)}:
        raise Invalid("unused_role")
    mapping={f"F{i}":ast.Subscript(value=ast.Name(id="s",ctx=ast.Load()),slice=ast.Constant(value=f"F{i}"),ctx=ast.Load()) for i in range(n)}
    safe=ast.Expression(body=Replace(mapping).visit(copy.deepcopy(tree)))
    return {"arity":n,"tree":tree,"safe":safe,"expanded":ast.unparse(tree),"deps":sorted(deps)}

def value(template, binding, record):
    return _eval(template["safe"],{f"F{i}":record[key] for i,key in enumerate(binding)})

def match(template, fields, calibration, heldout=None):
    probes=checks=0
    for binding in itertools.permutations(fields,template["arity"]):
        probes+=1
        good=True
        for r,target in calibration:
            checks+=1
            try:
                good=type(value(template,binding,r)) is int and value(template,binding,r)==target
            except (ArithmeticError,ValueError,TypeError,KeyError):
                good=False
            if not good:
                break
        if good:
            if heldout is None:
                return {"fit":True,"binding":list(binding),"candidates":probes,"calibration_checks":checks}
            wrong=0
            first=None
            for r,target in heldout:
                try:
                    prediction=value(template,binding,r)
                    valid=type(prediction) is int and prediction==target
                except (ArithmeticError,ValueError,TypeError,KeyError):
                    valid=False
                if not valid:
                    wrong+=1
                    if first is None:
                        first={"input":r,"expected":target}
            return {"fit":True,"binding":list(binding),"candidates":probes,"calibration_checks":checks,
                    "heldout_rows":len(heldout),"wrong":wrong,"first_wrong":first}
    return {"fit":False,"candidates":probes,"calibration_checks":checks,
            "heldout_rows":0,"wrong":None}

def compiled(history):
    macros={}
    for rec in history:
        if rec["recursive"]["qualified"]:
            name="O"+str(rec["stage"])
            macros[name]=parse_template(rec["recursive"]["proposal"],macros)
    return macros

def load_history(stage):
    if stage==1:
        return []
    rec=read(HERE/"receipt.json")
    if rec["source_sha"]!=sha() or len(rec["history"])!=stage-1:
        raise RuntimeError("invalid_prior_stage_identity")
    return rec["history"]

def old_frontier(stage, macros):
    fields,train,_=population(stage,False)
    old={"projection":parse_template({"arity":1,"expression":"F0"},{})}
    old.update(macros)
    return {k:match(v,fields,train) for k,v in old.items()}

def prompt(stage, arm, macros, frontier):
    fields,train,_=population(stage,False)
    known={k:{"arity":v["arity"],"expanded_expression":v["expanded"]} for k,v in macros.items()}
    return "\n".join([
        "Invent a reusable pure observation-constructor template, not a row-specific answer.",
        "Output exactly one JSON object with keys arity (integer 1..4) and expression (string).",
        "Use generic parameters F0,F1,F2,F3. All declared parameters must occur. Field binding is automatically searched over injective assignments using calibration only.",
        "Allowed base grammar: integer constants -32..32, +,-,*,%, unary +/- and abs(x). No other syntax or function calls.",
        ("You may call previous qualified constructors by name O1/O2, with exactly their declared arity. You may invent any composition in the grammar." if arm=="recursive" else
         "Produce a standalone template using the base grammar only. You have the identical earlier constructor definitions and may inline or adapt them."),
        "The current source-independent requirement is: "+CONTRACT[stage],
        "Anonymous integer source fields, including one nuisance field: "+canonical(fields),
        "Prior qualified constructors (same information in both arms): "+canonical(known),
        "Existing constructor calibration search failed: "+canonical(frontier),
        "Calibration examples (input, exact required output): "+canonical(train),
        "Do not hardcode individual examples; the same template will be rebound to a new unseen population. The independent checker decides qualification. No explanation or code fence.",
    ])

def propose(stage):
    from openai import OpenAI
    history=load_history(stage)
    macros=compiled(history)
    frontier=old_frontier(stage,macros)
    out={"source_sha":sha(),"stage":stage,"prior_digest":digest(history),"frontier":frontier,"calls":[]}
    fields,train,_=population(stage,False)
    out["calibration_sha256"]=digest([fields,train])
    if any(x["fit"] for x in frontier.values()):
        out["status"]="STOP_OLD_METHOD_FITS_CALIBRATION"
        write(HERE/"proposals.json",out)
        return
    if not os.environ.get("OPENAI_API_KEY"):
        out["status"]="UNKNOWN_MISSING_CREDENTIAL"
        write(HERE/"proposals.json",out)
        return
    client=OpenAI(api_key=os.environ["OPENAI_API_KEY"],timeout=90,max_retries=0)
    # Alternate order to avoid always giving one arm the first call.
    arms=["recursive","standalone"] if stage%2 else ["standalone","recursive"]
    for arm in arms:
        p=prompt(stage,arm,macros,frontier)
        rec={"arm":arm,"prompt_sha256":hashlib.sha256(p.encode()).hexdigest(),"prompt_chars":len(p)}
        t=time.monotonic()
        try:
            rsp=client.responses.create(model=MODEL,reasoning={"effort":"low"},input=p,max_output_tokens=1600)
            rec["model"]=rsp.model
            rec["usage"]=rsp.usage.model_dump() if rsp.usage else None
            raw=(rsp.output_text or "").strip()
            rec["response_sha256"]=hashlib.sha256(raw.encode()).hexdigest()
            try:
                obj=json.loads(raw)
                if not isinstance(obj,dict) or set(obj)!={"arity","expression"}:
                    raise Invalid("response_schema")
                if type(obj["arity"]) is not int or not isinstance(obj["expression"],str) or len(obj["expression"])>300:
                    raise Invalid("response_size")
                rec["proposal"]=obj
                rec["status"]="RESPONSE"
            except (ValueError,TypeError):
                rec["status"]="INVALID_RESPONSE"
        except Exception as e:
            rec["status"]="API_ERROR"
            rec["error_type"]=type(e).__name__
            rec["http_status"]=getattr(e,"status_code",None)
        rec["seconds"]=round(time.monotonic()-t,3)
        out["calls"].append(rec)
        out["status"]="COMPLETE" if len(out["calls"])==2 else "PARTIAL"
        write(HERE/"proposals.json",out)
        print("PROPOSAL",stage,arm,rec["status"],flush=True)
        if rec["status"]=="API_ERROR" and rec.get("http_status") in (401,403,404):
            break

def qualification(stage, proposal, macros):
    try:
        template=parse_template(proposal,macros)
        scores=[]
        for transfer in (False,True):
            fields,train,hold=population(stage,transfer)
            scores.append(match(template,fields,train,hold))
        qualified=all(x["fit"] and x["wrong"]==0 and x["heldout_rows"]>0 for x in scores)
        # Same mathematical expression with dependencies inlined: distinguish
        # reference deletion from absence of the underlying semantic knowledge.
        inline={"arity":template["arity"],"expression":template["expanded"]}
        inline_scores=[]
        try:
            unrolled=parse_template(inline,{})
            for transfer in (False,True):
                fields,train,hold=population(stage,transfer)
                inline_scores.append(match(unrolled,fields,train,hold))
        except (Invalid,SyntaxError,ValueError,RecursionError):
            pass
        withdrawal={}
        for name in template["deps"]:
            try:
                parse_template(proposal,{k:v for k,v in macros.items() if k!=name})
                withdrawal[name]="STILL_EXPRESSIBLE"
            except (Invalid,ValueError):
                withdrawal[name]="REFERENCE_INVALIDATED"
        return {"qualified":qualified,"proposal":proposal,"expanded":template["expanded"],"dependencies":template["deps"],
                "development":scores[0],"transfer":scores[1],"withdrawal":withdrawal,
                "unrolled_semantic_control":inline_scores,
                "status":"WARRANTED_BOUNDED_FINITE_TEMPLATE" if qualified else "REJECTED_OR_UNRESOLVED"}
    except (Invalid,SyntaxError,ValueError,TypeError,RecursionError) as e:
        return {"qualified":False,"proposal":proposal,"status":"UNKNOWN_INVALID_TEMPLATE","error_type":type(e).__name__}

def verify(stage):
    history=load_history(stage)
    macros=compiled(history)
    p=read(HERE/"proposals.json")
    assert p["source_sha"]==sha() and p["stage"]==stage and p["prior_digest"]==digest(history)
    fields,train,_=population(stage,False)
    assert p["calibration_sha256"]==digest([fields,train])
    assert p["frontier"]==old_frontier(stage,macros)
    calls=p["calls"]
    assert len(calls)<=MAX_CALLS_PER_STAGE and len({r["arm"] for r in calls})==len(calls)
    assert all(r["arm"] in ("recursive","standalone") for r in calls)
    result={"stage":stage,"frontier":p["frontier"],"proposal_status":p["status"],"calls":calls}
    for arm in ("recursive","standalone"):
        r=next((x for x in calls if x["arm"]==arm),None)
        if r is not None:
            assert r["prompt_sha256"]==hashlib.sha256(prompt(stage,arm,macros,p["frontier"]).encode()).hexdigest()
        if r is None or r["status"]!="RESPONSE" or r["model"]!=MODEL:
            result[arm]={"qualified":False,"status":"UNKNOWN_NO_MATCHED_MODEL_RESPONSE"}
        else:
            result[arm]=qualification(stage,r["proposal"],macros if arm=="recursive" else {})
    history.append(result)
    chain=(len(history)==3 and all(r["recursive"]["qualified"] for r in history)
           and all("O"+str(i) in history[i]["recursive"].get("dependencies",[]) for i in (1,2)))
    out={"source_sha":sha(),"model":MODEL,"history":history,"qualified_named_three_stage_chain":chain,
         "strict_G2_G3":"UNKNOWN","scope":"constructed finite numeric native-oracle pilot; no autonomous external method invention or economic claim"}
    write(HERE/"receipt.json",out)
    print("SCORE",canonical(result),flush=True)
    print("CHAIN",chain,"STRICT_G2_G3_UNKNOWN",flush=True)

def preflight():
    examples=[{"arity":2,"expression":"abs(F0-F1)"},
              {"arity":3,"expression":"O1(F0,F1)+O1(F1,F2)"},
              {"arity":4,"expression":"O1(O2(F0,F1,F2),O2(F1,F2,F3))"}]
    macros={}
    for stage,p in enumerate(examples,1):
        assert not any(x["fit"] for x in old_frontier(stage,macros).values())
        q=qualification(stage,p,macros)
        assert q["qualified"],q
        if stage>1:
            assert q["withdrawal"]["O"+str(stage-1)]=="REFERENCE_INVALIDATED",q
            assert all(x["wrong"]==0 for x in q["unrolled_semantic_control"]),q
        macros["O"+str(stage)]=parse_template(p,macros)
    for expr in ("__import__('os')","F0.__class__","F0**99","F0+100000","F0+1","open(F0)"):
        try:
            parse_template({"arity":2,"expression":expr},macros)
        except (Invalid,SyntaxError,ValueError):
            continue
        raise AssertionError("unsafe or invalid template admitted")
    assert not qualification(1,{"arity":2,"expression":"F0+F1"},{})["qualified"]
    print("PREFLIGHT_OK_NATIVE_COMPLETE_DOMAINS_AND_UNROLL_CONTROLS")

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("mode",choices=["preflight","propose","verify"])
    parser.add_argument("stage",nargs="?",type=int,choices=[1,2,3])
    a=parser.parse_args()
    if a.mode=="preflight": preflight()
    elif a.stage is None: parser.error("stage required")
    elif a.mode=="propose": propose(a.stage)
    else: verify(a.stage)
