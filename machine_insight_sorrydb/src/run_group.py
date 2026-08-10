#!/usr/bin/env python3
import argparse, hashlib, json, os, random, re, time, traceback
from pathlib import Path
from openai import OpenAI
from sorrydb.database.sorry import Location
from sorrydb.utils.git_ops import prepare_repository
from sorrydb.database.process_sorries import build_lean_project
from sorrydb.utils.verify import verify_proof

MODEL="gpt-5.6-sol"; REASONING_EFFORT="medium"; MAX_OUTPUT_TOKENS=4096; MAX_ATTEMPTS=4
SOURCE_BEFORE_CHARS=6000; SOURCE_AFTER_CHARS=6000; DIAGNOSTIC_LIMIT=12000
CONDITIONS=["A_ONE_SHOT","B_RAW_RETRY","C_STRUCTURED_RESIDUAL","D_MACHINE_INSIGHT","SHUFFLED_RESIDUAL","RANDOM_REPAIR"]
REPAIR_FAMILIES=["LOCAL_EDIT","SIMPLIFICATION","REWRITE_DIRECTION_CHANGE","CONGRUENCE","TYPE_ALIGNMENT","INSTANCE_SYNTHESIS","PREMISE_RETRIEVAL","INDUCTION","CASE_SPLIT","EXTENSIONALITY","NORMALIZATION","ARITHMETIC_SOLVER","DECISION_PROCEDURE","CONTRADICTION","EXISTENTIAL_WITNESS","INTERMEDIATE_LEMMA","GENERALIZE","SPECIALIZE","CHANGE_GOAL_REPRESENTATION","CHANGE_TERM_REPRESENTATION","TACTIC_FAMILY_SWITCH"]
BASE_REPAIR={"TYPE_MISMATCH":"TYPE_ALIGNMENT","UNSOLVED_GOALS":"TACTIC_FAMILY_SWITCH","FAILED_SYNTHESIS":"INSTANCE_SYNTHESIS","MISSING_INSTANCE":"INSTANCE_SYNTHESIS","UNKNOWN_IDENTIFIER":"PREMISE_RETRIEVAL","TACTIC_NO_PROGRESS":"TACTIC_FAMILY_SWITCH","REWRITE_NO_MATCH":"REWRITE_DIRECTION_CHANGE","APPLICATION_MISMATCH":"TYPE_ALIGNMENT","UNIFICATION_FAILURE":"TYPE_ALIGNMENT","METAVARIABLE_REMAINS":"SPECIALIZE","COERCION_OR_CAST_MISMATCH":"TYPE_ALIGNMENT","MISSING_PREMISE_OR_LEMMA":"PREMISE_RETRIEVAL","TERMINATION_OR_RECURSION":"INDUCTION","GOAL_SHAPE_MISMATCH":"CHANGE_GOAL_REPRESENTATION","NAMESPACE_OR_IMPORT":"PREMISE_RETRIEVAL","OTHER":"INTERMEDIATE_LEMMA"}
ALTERNATES={"TYPE_ALIGNMENT":["CHANGE_TERM_REPRESENTATION","CHANGE_GOAL_REPRESENTATION"],"TACTIC_FAMILY_SWITCH":["INTERMEDIATE_LEMMA","CHANGE_GOAL_REPRESENTATION"],"INSTANCE_SYNTHESIS":["PREMISE_RETRIEVAL","TYPE_ALIGNMENT"],"PREMISE_RETRIEVAL":["INTERMEDIATE_LEMMA","SPECIALIZE"],"REWRITE_DIRECTION_CHANGE":["CHANGE_GOAL_REPRESENTATION","CONGRUENCE"],"SPECIALIZE":["GENERALIZE","INTERMEDIATE_LEMMA"],"INDUCTION":["CASE_SPLIT","GENERALIZE"],"CHANGE_GOAL_REPRESENTATION":["NORMALIZATION","INTERMEDIATE_LEMMA"],"INTERMEDIATE_LEMMA":["TACTIC_FAMILY_SWITCH","CHANGE_TERM_REPRESENTATION"]}
SYSTEM_PROMPT="""You are a Lean 4 theorem prover inside a controlled experiment. Produce ONLY the exact Lean code that should replace the target `sorry` token: no Markdown fences, no explanation, no label. You may use declarations already available in the supplied original project context. Never use `sorry`, `admit`, `axiom`, `unsafe`, or any mechanism that bypasses Lean's kernel. The candidate will be independently verified by the official SorryDB verifier. Keep the proof as short and robust as possible."""

def sha256_text(s): return hashlib.sha256(s.encode()).hexdigest()
def normalize_proof(text):
    text=(text or "").strip(); m=re.search(r"```(?:lean)?\s*(.*?)```",text,re.I|re.S)
    if m: text=m.group(1).strip()
    return re.sub(r"^(?:proof|answer|replacement)\s*:\s*","",text,flags=re.I).strip()
def forbidden(proof): return [tok for tok in ["sorry","admit","axiom","unsafe"] if re.search(rf"\b{tok}\b",proof)]
def source_context(repo_dir,task):
    p=repo_dir/task["location"]["path"]; txt=p.read_text(errors="replace"); line=task["location"]["start_line"]; lines=txt.splitlines(keepends=True); idx=sum(len(x) for x in lines[:max(0,line-1)]); return txt[max(0,idx-SOURCE_BEFORE_CHARS):min(len(txt),idx+SOURCE_AFTER_CHARS)]
def parse_residual(feedback,goal_before):
    f=feedback or ""; fl=f.lower(); family="OTHER"
    rules=[("UNKNOWN_IDENTIFIER",["unknown identifier","unknown constant","invalid field notation"]),("MISSING_INSTANCE",["failed to synthesize instance","type class instance problem is stuck"]),("TYPE_MISMATCH",["type mismatch","expected type"]),("APPLICATION_MISMATCH",["function expected at","application type mismatch","function application type mismatch"]),("UNIFICATION_FAILURE",["failed to unify","cannot unify"]),("REWRITE_NO_MATCH",["did not find instance of the pattern","rewrite tactic failed","no match found"]),("TACTIC_NO_PROGRESS",["tactic made no progress","no goals to be solved"]),("METAVARIABLE_REMAINS",["declaration has metavariables","contains metavariables","synthetic opaque"]),("COERCION_OR_CAST_MISMATCH",["failed to synthesize coe","coercion"]),("TERMINATION_OR_RECURSION",["fail to show termination","decreasing argument"]),("NAMESPACE_OR_IMPORT",["unknown namespace","invalid namespace","unknown module","unknown package"]),("UNSOLVED_GOALS",["unsolved goals","unsolved goal"])]
    for fam,pats in rules:
        if any(p in fl for p in pats): family=fam; break
    if family=="OTHER" and "failed to synthesize" in fl: family="FAILED_SYNTHESIS"
    expected=actual=None
    m=re.search(r"application type mismatch[\s\S]{0,1500}?argument\s+[^\n]*\s+has type\s*\n?\s*([^\n]+)[\s\S]{0,500}?but is expected to have type\s*\n?\s*([^\n]+)",f,re.I)
    if m: actual,expected=m.group(1).strip(),m.group(2).strip()
    else:
        m=re.search(r"has type\s*\n?\s*([^\n]+)[\s\S]{0,300}?expected(?: to have)? type\s*\n?\s*([^\n]+)",f,re.I)
        if m: actual,expected=m.group(1).strip(),m.group(2).strip()
    evidence=[]
    for chunk in re.split(r"\n(?=(?:error:|warning:|<error|unsolved goals))",f,flags=re.I):
        c=chunk.strip()
        if c and c not in evidence: evidence.append(c[:1200])
        if len(evidence)>=5: break
    unsolved=[]
    if "unsolved goals" in fl:
        tail=f[fl.find("unsolved goals"):]; unsolved=[tail[:4000]]
    ids=sorted(set(re.findall(r"(?:unknown identifier|unknown constant)\s+['`‘]?([^'`’\s<]+)",f,re.I)))[:12]
    distinctions={"TYPE_MISMATCH":["term type vs expected goal type"],"UNSOLVED_GOALS":["solved subgoals vs remaining subgoals"],"MISSING_INSTANCE":["mathematical premise vs typeclass instance"],"UNKNOWN_IDENTIFIER":["available declaration vs guessed identifier"],"REWRITE_NO_MATCH":["rewrite direction and syntactic goal shape"],"UNIFICATION_FAILURE":["implicit arguments and instantiated types"],"APPLICATION_MISMATCH":["function domain vs supplied argument"],"COERCION_OR_CAST_MISMATCH":["source type vs coerced target type"],"GOAL_SHAPE_MISMATCH":["current goal representation vs tactic precondition"]}.get(family,[])
    return {"family":family,"goal_before":goal_before,"goal_after":unsolved[0] if unsolved else None,"failed_mechanism":None,"expected_type":expected,"actual_type":actual,"unsolved_subgoals":unsolved,"relevant_identifiers":ids,"diagnostic_evidence":evidence,"confidence":"high" if family!="OTHER" else "low","suggested_distinctions_to_inspect":distinctions}
def select_repair(residual,attempt,previous):
    base=BASE_REPAIR.get(residual["family"],"INTERMEDIATE_LEMMA"); seq=[base]+ALTERNATES.get(base,["TACTIC_FAMILY_SWITCH","INTERMEDIATE_LEMMA"]); choice=seq[min(max(attempt-2,0),len(seq)-1)]
    if choice in previous:
        for x in seq+REPAIR_FAMILIES:
            if x not in previous: return x
    return choice
def random_repair(task_id,attempt): return REPAIR_FAMILIES[int.from_bytes(hashlib.sha256(f"{task_id}|{attempt}|random-repair-v1".encode()).digest()[:8],"big")%len(REPAIR_FAMILIES)]
def base_user(task,context): return f"""TARGET SORRYDB TASK ID: {task['id']}\nORIGINAL PROJECT: {task['repo']['remote']} @ {task['repo']['commit']}\nSOURCE FILE: {task['location']['path']}:{task['location']['start_line']}\n\nLEAN GOAL AT TARGET:\n{task['debug_info']['goal']}\n\nDETERMINISTIC ORIGINAL-SOURCE CONTEXT (same policy for all conditions):\n---BEGIN SOURCE CONTEXT---\n{context}\n---END SOURCE CONTEXT---\n\nReturn only the Lean code replacing the target sorry."""
def retry_user(task,context,condition,attempt,previous_proof,feedback,residual,repair=None,donor=None):
    b=base_user(task,context); prev=previous_proof[:10000]
    if condition=="B_RAW_RETRY": intervention=f"The previous candidate failed official Lean verification.\nPREVIOUS CANDIDATE:\n{prev}\n\nRAW LEAN VERIFIER FEEDBACK:\n{feedback[:DIAGNOSTIC_LIMIT]}\n\nRepair the proof using the raw verifier feedback."
    elif condition=="C_STRUCTURED_RESIDUAL": intervention=f"The previous candidate failed official Lean verification.\nPREVIOUS CANDIDATE:\n{prev}\n\nDETERMINISTIC STRUCTURED RESIDUAL (derived only from that Lean feedback; no proof hints):\n{json.dumps(residual,ensure_ascii=False,indent=2)}\n\nUse the residual evidence to choose your next proof strategy."
    elif condition=="D_MACHINE_INSIGHT": intervention=f"The previous candidate failed official Lean verification.\nPREVIOUS CANDIDATE:\n{prev}\n\nDETERMINISTIC STRUCTURED RESIDUAL:\n{json.dumps(residual,ensure_ascii=False,indent=2)}\n\nOBSTRUCTION-DRIVEN REPAIR FAMILY: {repair}\nYou must genuinely switch strategy toward this repair family rather than merely repeat the failed approach. The repair family is a control instruction, not a theorem-specific proof hint."
    elif condition=="SHUFFLED_RESIDUAL": intervention=f"The previous candidate failed official Lean verification.\nPREVIOUS CANDIDATE:\n{prev}\n\nCONTROL RESIDUAL (deterministically shuffled from another failed task; donor proof is never exposed):\n{json.dumps(donor,ensure_ascii=False,indent=2)}\n\nUse this residual evidence to choose your next proof strategy."
    elif condition=="RANDOM_REPAIR": intervention=f"The previous candidate failed official Lean verification.\nPREVIOUS CANDIDATE:\n{prev}\n\nDETERMINISTIC STRUCTURED RESIDUAL:\n{json.dumps(residual,ensure_ascii=False,indent=2)}\n\nRANDOM CONTROL REPAIR FAMILY: {repair}\nSwitch strategy toward this repair family."
    else: raise ValueError(condition)
    return b+f"\n\nRETRY ATTEMPT {attempt}/{MAX_ATTEMPTS}\n"+intervention+"\n\nReturn only the replacement Lean code."
def model_call(client,user_prompt):
    t0=time.time(); r=client.responses.create(model=MODEL,reasoning={"effort":REASONING_EFFORT},instructions=SYSTEM_PROMPT,input=user_prompt,max_output_tokens=MAX_OUTPUT_TOKENS); elapsed=time.time()-t0
    if getattr(r,"model",None)!=MODEL: raise RuntimeError(f"MODEL_DRIFT requested={MODEL} returned={getattr(r,'model',None)}")
    u=getattr(r,"usage",None); return normalize_proof(getattr(r,"output_text","")),getattr(r,"id",None),(u.model_dump() if u is not None and hasattr(u,"model_dump") else None),elapsed
def verify(repo_dir,task,proof):
    if not proof: return False,"EMPTY_CANDIDATE",0.0
    bad=forbidden(proof)
    if bad: return False,"FORBIDDEN_TOKEN:"+",".join(bad),0.0
    t0=time.time()
    try:
        ok,feedback=verify_proof(repo_dir,task["repo"]["lean_version"],Location(**task["location"]),proof,use_lean_interact=True); return bool(ok),str(feedback or ""),time.time()-t0
    except Exception as e: return False,f"VERIFY_EXCEPTION {type(e).__name__}: {e}\n{traceback.format_exc(limit=3)}",time.time()-t0
def choose_donor(first_failures,target_id,family):
    candidates=[x for x in first_failures if x["task_id"]!=target_id]; matched=[x for x in candidates if x["residual"]["family"]==family]; pool=matched or candidates
    if not pool: return None,False
    pool=sorted(pool,key=lambda x:sha256_text(target_id+"|"+x["task_id"])); return pool[0],bool(matched)
def rec(task,condition,attempt,proof,verified,feedback,residual,repair,prompt_hash,response_id,usage,em,ev,infra=False,extra=None):
    r={"task_id":task["id"],"project":task["repo"]["remote"],"project_commit":task["repo"]["commit"],"lean_version":task["repo"]["lean_version"],"condition":condition,"attempt":attempt,"model":MODEL,"reasoning_effort":REASONING_EFFORT,"prompt_hash":prompt_hash,"candidate_proof":proof,"lean_feedback":feedback,"residual":residual,"repair_family":repair,"input_tokens":(usage or {}).get("input_tokens"),"output_tokens":(usage or {}).get("output_tokens"),"total_tokens":(usage or {}).get("total_tokens"),"elapsed_model_seconds":em,"elapsed_verify_seconds":ev,"verified":bool(verified),"infra_error":bool(infra),"response_id":response_id}
    if extra:r.update(extra)
    return r
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--manifest",required=True); ap.add_argument("--group-index",type=int,required=True); ap.add_argument("--out-dir",required=True); a=ap.parse_args(); tasks=json.loads(Path(a.manifest).read_text()); groups=sorted({(t["repo"]["remote"],t["repo"]["commit"],t["repo"]["branch"],t["repo"]["lean_version"]) for t in tasks}); key=groups[a.group_index]; gtasks=sorted([t for t in tasks if (t["repo"]["remote"],t["repo"]["commit"],t["repo"]["branch"],t["repo"]["lean_version"])==key],key=lambda t:t["id"]); out=Path(a.out_dir); out.mkdir(parents=True,exist_ok=True); records=[]; client=OpenAI(api_key=os.environ["OPENAI_API_KEY"]); remote,commit,branch,lean_version=key; summary={"group_index":a.group_index,"group_key":key,"task_ids":[t["id"] for t in gtasks],"status":"RUNNING"}
    try:
        repo_dir=prepare_repository(remote,branch,commit,Path("/tmp/machine_insight_projects"),lean_version); actual=os.popen(f"git -C '{repo_dir}' rev-parse HEAD").read().strip()
        if actual!=commit: raise RuntimeError(f"COMMIT_DRIFT {actual} != {commit}")
        build_lean_project(repo_dir); contexts={t["id"]:source_context(repo_dir,t) for t in gtasks}; first={}; first_failures=[]
        for task in gtasks:
            user=base_user(task,contexts[task["id"]]); ph=sha256_text(SYSTEM_PROMPT+"\n"+user); proof,rid,usage,em=model_call(client,user); ok,feedback,ev=verify(repo_dir,task,proof); residual=None if ok else parse_residual(feedback,task["debug_info"]["goal"]); first[task["id"]]={"proof":proof,"response_id":rid,"usage":usage,"elapsed_model":em,"verified":ok,"feedback":feedback,"elapsed_verify":ev,"residual":residual,"prompt_hash":ph}
            if not ok:first_failures.append({"task_id":task["id"],"residual":residual})
            for cond in CONDITIONS: records.append(rec(task,cond,1,proof,ok,feedback,residual,None,ph,rid,usage,em,ev,extra={"physical_first_call_shared":True,"physical_call_charge_fraction":1.0/len(CONDITIONS)}))
        for task in gtasks:
            f=first[task["id"]]
            if f["verified"]:continue
            for cond in ["B_RAW_RETRY","C_STRUCTURED_RESIDUAL","D_MACHINE_INSIGHT","SHUFFLED_RESIDUAL","RANDOM_REPAIR"]:
                previous_proof=f["proof"]; feedback=f["feedback"]; previous_repairs=[]
                for attempt in range(2,MAX_ATTEMPTS+1):
                    residual=parse_residual(feedback,task["debug_info"]["goal"]); repair=None; donor_resid=None; donor_id=None; donor_matched=None
                    if cond=="D_MACHINE_INSIGHT": repair=select_repair(residual,attempt,previous_repairs); previous_repairs.append(repair)
                    elif cond=="RANDOM_REPAIR": repair=random_repair(task["id"],attempt)
                    elif cond=="SHUFFLED_RESIDUAL":
                        donor,donor_matched=choose_donor(first_failures,task["id"],residual["family"])
                        if donor is None: donor_resid={"family":"OTHER","goal_before":None,"goal_after":None,"failed_mechanism":None,"expected_type":None,"actual_type":None,"unsolved_subgoals":[],"relevant_identifiers":[],"diagnostic_evidence":["NO_ELIGIBLE_DONOR_IN_GROUP"],"confidence":"low","suggested_distinctions_to_inspect":[]}
                        else: donor_resid=donor["residual"]; donor_id=donor["task_id"]
                    user=retry_user(task,contexts[task["id"]],cond,attempt,previous_proof,feedback,residual,repair=repair,donor=donor_resid); ph=sha256_text(SYSTEM_PROMPT+"\n"+user); proof,rid,usage,em=model_call(client,user); ok,new_feedback,ev=verify(repo_dir,task,proof); extra={"physical_first_call_shared":False}
                    if cond=="SHUFFLED_RESIDUAL":extra.update({"donor_task_id":donor_id,"donor_family_matched":donor_matched})
                    if cond=="D_MACHINE_INSIGHT":extra["strategy_switch_due_to_verified_failure"]=True
                    records.append(rec(task,cond,attempt,proof,ok,new_feedback,residual,repair,ph,rid,usage,em,ev,extra=extra)); previous_proof,feedback=proof,new_feedback
                    if ok:break
        summary.update({"status":"COMPLETED","records":len(records),"tasks":len(gtasks),"first_verified":sum(1 for x in first.values() if x["verified"])})
    except Exception as e:
        summary.update({"status":"INFRA_ERROR","error":f"{type(e).__name__}: {e}","traceback":traceback.format_exc()})
        for task in gtasks:
            for cond in CONDITIONS: records.append(rec(task,cond,0,"",False,summary["error"],None,None,"",None,None,0,0,infra=True))
    with (out/f"group_{a.group_index:03d}.jsonl").open("w") as fh:
        for r in records:fh.write(json.dumps(r,ensure_ascii=False,sort_keys=True)+"\n")
    (out/f"group_{a.group_index:03d}_summary.json").write_text(json.dumps(summary,indent=2,ensure_ascii=False,sort_keys=True)); print(json.dumps(summary,sort_keys=True)); return 0
if __name__=="__main__": raise SystemExit(main())
