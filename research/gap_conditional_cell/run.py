#!/usr/bin/env python3
"""LLM-only-at-gaps pilot. No candidate expression is executed in the secret job.

For scientific comparison, ALWAYS is a separate counterfactual arm that spends
one model call on every case; GAP_ONLY calls the LLM only for proven finite
observation collisions with adequate available source features.
"""
import hashlib
import json
import os
import random
import time
from pathlib import Path
from openai import OpenAI
from structural import read_cases, assess, canonical, source_digest

HERE=Path(__file__).resolve().parent
OUT=HERE/"proposals.json"

INSTRUCTIONS = """You are a candidate observation constructor, NOT the verifier.
Given a declared source record s (a Python dictionary), propose an anonymous
pure expression that retains exactly the distinctions needed for the stated
protected outcome. You may not receive or execute its protected evaluation set.
There is no menu of predefined repair strategies.

Safe-expression language:
  s["name"] to read source fields, numeric / boolean / string literals,
  lists/tuples, +, -, *, %, comparisons, and/or/not, abs(expr), len(expr).
  NO methods, imports, loops, comprehension, attribute access, eval, exec,
  function definitions, file/network access or unsafe code. If you need a new
  primitive such as Unicode normalization, say NEED_NEW_PRIMITIVE.
  The output may distinguish states iff their protected outcomes differ
  on the authoritative declared domain. Do not over-split same-outcome states.

Return precisely one JSON object: {"action": "PROPOSE"|"NO_CHANGE"|
"NEED_AUTHORITY"|"NEED_NEW_SOURCE"|"NEED_NEW_PRIMITIVE",
"expression": "single expression or empty string",
"rationale": "short explanation"}.
Proposals are untrusted; an independent credential-free checker will decide.
"""

def prompt(case, arm, result):
    lines=[INSTRUCTIONS,
        "Protected requirement: " + case["contract"],
        "Source input fields: " + case["fields"],
        "Old observation: " + case["old_description"],
        "Source authority: " + ("DECLARED" if case["authority"]=="declared" else "NOT OWNER RATIFIED"),
        "Complete frozen source population: " + ("YES" if case["complete"] else "NO"),
        "You do not see any oracle labels or the protected evaluation dataset.",
    ]
    if arm=="GAP_ONLY":
        assert result["status"]=="ELIGIBLE_GAP"
        w=result["witness"]
        lines.extend([
          "A separate deterministic verifier established a consequential collision:",
          "Both of these two states have the SAME existing observation but DIFFERENT protected outcomes.",
          "Source A: "+canonical(w["left_input"]),
          "Source B: "+canonical(w["right_input"]),
          "Make a minimal source-grounded observation to restore the necessary distinction.",
          "Do not hardcode witness records; satisfy the full declared requirement.",
        ])
    else:
        lines.append("No structural diagnosis or witness is provided; decide from the stated requirement.")
    return "\n".join(lines)


def main():
    data=read_cases()
    cases=data["cases"]
    assessments={c["id"]:assess(c) for c in cases}
    assert sum(a["status"]=="ELIGIBLE_GAP" for a in assessments.values())==5
    jobs=[("ALWAYS",c) for c in cases]+[("GAP_ONLY",c) for c in cases if assessments[c["id"]]["status"]=="ELIGIBLE_GAP"]
    random.Random(data["seed"]).shuffle(jobs)
    out={
      "schema":"mathgraph/gap-conditional-api-proposals-v1",
      "source_sha":os.environ.get("GITHUB_SHA",""),
      "cases_sha256":source_digest(),
      "requested_model":data["baseline_model"],
      "reasoning_effort":data["reasoning_effort"],
      "frozen_population_size":len(cases),
      "expected_gated_calls":5,
      "expected_total_controlled_calls":14,
      "gate":{k:v["status"] for k,v in assessments.items()},
      "calls":[],
    }
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY_MISSING")
    client=OpenAI(api_key=os.environ["OPENAI_API_KEY"],timeout=85,max_retries=0)
    started=time.monotonic()
    for n,(arm,c) in enumerate(jobs,1):
        p=prompt(c,arm,assessments[c["id"]])
        r={"case_id":c["id"],"arm":arm,"prompt_sha256":hashlib.sha256(p.encode()).hexdigest(),"prompt_chars":len(p)}
        t=time.monotonic()
        try:
            response=client.responses.create(
                model=data["baseline_model"],
                reasoning={"effort":data["reasoning_effort"]},
                input=p,max_output_tokens=data["max_output_tokens"],
            )
            raw=(response.output_text or "").strip()
            try:
                parsed=json.loads(raw)
                if not isinstance(parsed,dict): raise ValueError("NON_OBJECT")
                action=parsed.get("action")
                if action not in ("PROPOSE","NO_CHANGE","NEED_AUTHORITY","NEED_NEW_SOURCE","NEED_NEW_PRIMITIVE"):
                    raise ValueError("INVALID_ACTION")
                expr=parsed.get("expression","")
                if not isinstance(expr,str):
                    raise ValueError("NON_STRING_EXPRESSION")
                r.update({"status":"RESPONSE","action":action,"expression":expr[:500],
                          "rationale":str(parsed.get("rationale",""))[:300]})
            except (ValueError,TypeError):
                r.update({"status":"INVALID_RESPONSE","action":None,"expression":"",
                          "raw_text":raw[:400]})
            r["returned_model"]=response.model
            r["usage"]=response.usage.model_dump() if response.usage else None
        except Exception as e:
            r.update({"status":"API_ERROR","action":None,"expression":"",
                      "error_type":type(e).__name__,
                      "http_status":getattr(e,"status_code",None)})
        r["elapsed_seconds"]=round(time.monotonic()-t,3)
        out["calls"].append(r)
        out["total_elapsed_seconds"]=round(time.monotonic()-started,3)
        OUT.write_text(json.dumps(out,sort_keys=True,indent=2,ensure_ascii=False)+"\n")
        print(f'{n}/{len(jobs)} {c["id"]} {arm} {r["status"]} {r.get("action","")}',flush=True)
        if r["status"]=="API_ERROR" and r.get("http_status") in (401,403,404):
            break
    if len(out["calls"])!=14 or any(r["status"]=="API_ERROR" for r in out["calls"]):
        raise SystemExit("INCOMPLETE_API_EXPERIMENT")
    print("COMPLETE_14_CALLS",flush=True)


if __name__=="__main__":
    main()
