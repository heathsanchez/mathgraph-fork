#!/usr/bin/env python3
"""Credential-free independent assessment of structurally gated LLM proposals."""
import hashlib
import json
import os
from collections import Counter
from pathlib import Path
from structural import read_cases, assess, verify_expression, source_digest, canonical

HERE=Path(__file__).resolve().parent


def main():
    data=read_cases()
    cases=data["cases"]
    by_id={c["id"]:c for c in cases}
    raw=json.loads((HERE/"proposals.json").read_text())
    assert raw["schema"]=="mathgraph/gap-conditional-api-proposals-v1"
    assert raw["cases_sha256"]==source_digest(),"SOURCE_DATA_CHANGED_AFTER_MODEL_CALL"
    if os.environ.get("GITHUB_SHA") and raw["source_sha"] != os.environ["GITHUB_SHA"]:
        assert os.environ.get("GAP_RESCORE_ORIGINAL_SOURCE_SHA") == raw["source_sha"], "UNAUTHORIZED_REQUALIFICATION"
        assert raw["source_sha"] == "7c66e67ee3ba0e2c6ef9da8cac5041cf489b6a63", "UNEXPECTED_ORIGINAL_SOURCE"
    pairs=[(r["arm"],r["case_id"]) for r in raw["calls"]]
    assert len(pairs)==len(set(pairs))==14,"DUPLICATE_OR_MISSING_CALL"
    assert all(a in ("ALWAYS","GAP_ONLY") and k in by_id for a,k in pairs),"FOREIGN_CASE"
    expect=set([("ALWAYS",c["id"]) for c in cases]+[
        ("GAP_ONLY",c["id"]) for c in cases if assess(c)["status"]=="ELIGIBLE_GAP"])
    assert set(pairs)==expect,"GAP_ONLY_SPENT_ON_NON_GAP"
    assert all(r["status"]=="RESPONSE" for r in raw["calls"]),"INVALID_MODEL_RESPONSE"
    assert all(r.get("returned_model")==data["baseline_model"] for r in raw["calls"]),"MODEL_DRIFT"
    rows=[]
    for case in cases:
        gate=assess(case)
        for arm in ("ALWAYS","GAP_ONLY"):
            model=next((r for r in raw["calls"] if r["case_id"]==case["id"] and r["arm"]==arm),None)
            if model is None:
                result={"status":"STRUCTURAL_STOP","reason":gate["status"]}
            elif model["action"]=="PROPOSE":
                result=verify_expression(case,model["expression"])
            else:
                result={"status":"MODEL_DECLINED","reason":model["action"]}
            rows.append({
                "case":case["id"],"source":case["source_ref"],"arm":arm,
                "structural_gate":gate["status"],
                "called_model":model is not None,
                "model_action":model.get("action") if model else None,
                "proposed_expression":model.get("expression") if model else None,
                "verifier":result,
                "valid_lawful_completion":(
                    gate["status"]=="ELIGIBLE_GAP" and
                    result["status"]=="WARRANTED_FROZEN_FINITE_KERNEL"
                ),
                "source_sha256":raw["cases_sha256"],
            })
    by_arm={}
    for arm in ("ALWAYS","GAP_ONLY"):
        sub=[x for x in rows if x["arm"]==arm]
        verified=[x for x in sub if x["structural_gate"]=="ELIGIBLE_GAP"]
        by_arm[arm]={
            "calls":sum(x["called_model"] for x in sub),
            "eligible_gap_cases":len(verified),
            "lawfully_closed_gaps":sum(x["valid_lawful_completion"] for x in verified),
            "unresolved_gaps":sum(not x["valid_lawful_completion"] for x in verified),
            "unnecessary_calls":sum(
                x["called_model"] and x["structural_gate"]!="ELIGIBLE_GAP"
                for x in sub
            ),
            "false_finite_warrant":sum(
                x["verifier"]["status"]=="WARRANTED_FROZEN_FINITE_KERNEL"
                and x["structural_gate"]!="ELIGIBLE_GAP"
                for x in sub
            ),
            "sample_only_agreements":sum(
                x["verifier"]["status"]=="CONSISTENT_SAMPLES_ONLY" for x in sub
            ),
            "unsupported_code_executed":0,
        }
    total_usage={"input_tokens":0,"output_tokens":0,"total_tokens":0}
    usage_per_arm={a:dict(total_usage) for a in ("ALWAYS","GAP_ONLY")}
    for r in raw["calls"]:
        u=r.get("usage") or {}
        for k in total_usage:
            v=int(u.get(k) or 0)
            total_usage[k]+=v
            usage_per_arm[r["arm"]][k]+=v
    out={
        "schema":"mathgraph/gap-conditional-scored-v1",
        "status":"WARRANTED_LOCAL_FINITE_PILOT",
        "source_sha":raw["source_sha"],
        "verifier_commit":os.environ.get("GITHUB_SHA",""),
        "requalification_of_original":(
            os.environ.get("GITHUB_SHA","")!=raw["source_sha"]
        ),
        "cases_sha256":raw["cases_sha256"],
        "model":data["baseline_model"],
        "structure":{c["id"]:assess(c)["status"] for c in cases},
        "arms":by_arm,
        "usage":total_usage,
        "usage_per_arm":usage_per_arm,
        "rows":rows,
        "limits":[
          "Finite reduced examples, not fresh source-native upstream execution, whole-repo assurance or owner endorsement.",
          "Source authority and target labels are author-declared fixtures; gate cannot independently establish their truth.",
          "This asks the LLM to propose source expressions; it does not synthesize arbitrary executable programs or new instrument types.",
          "The safe interpreter is a deliberately supplied finite expression language; a required unknown primitive remains UNKNOWN.",
          "A finite target-kernel match does not prove correctness outside the declared fixture domain or future actions.",
          "An earlier scorer labeled a sample-only match as a finite warrant: corrected to CONSISTENT_SAMPLES_ONLY without rerunning any model.",
          "A model proposal is not a signed/authenticated Unit or a deployed MathGraph Cell.",
          "Historical source examples and requirement descriptions may be present in training data.",
          "A single response per case is not evidence of general-model performance or superior economic impact.",
        ]
    }
    (HERE/"summary.json").write_text(json.dumps(out,indent=2,sort_keys=True,ensure_ascii=False)+"\n")
    print("STRUCTURE",json.dumps(out["structure"],sort_keys=True))
    print("COMPARATIVE_RESULT",json.dumps(by_arm,sort_keys=True))
    print("USAGE_BY_ARM",json.dumps(usage_per_arm,sort_keys=True))
    for x in rows:
        print("CASE",x["case"],x["arm"],x["structural_gate"],x["model_action"],x["verifier"])
    # The source-gate must always be respected. No claim about LLM success.
    assert by_arm["GAP_ONLY"]["unnecessary_calls"]==0
    assert by_arm["ALWAYS"]["calls"]==len(cases)
    assert by_arm["GAP_ONLY"]["calls"]==5
    print("QUALIFIED_FINITE_SCORING_COMPLETE")


if __name__=="__main__":
    main()
