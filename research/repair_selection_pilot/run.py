#!/usr/bin/env python3
"""Bounded paired LLM repair-choice pilot. No model output is executed."""
import hashlib
import json
import os
import random
import re
import sys
import time
from pathlib import Path

from openai import OpenAI

HERE = Path(__file__).resolve().parent
CASES_PATH = HERE / "cases.json"
OUT = HERE / "results.json"


def make_prompt(case, arm):
    lines = [
        "You are choosing a narrowly scoped software repair from five proposed actions.",
        "Protect valid existing behavior. Do not invent evidence or infer an absent requirement.",
        "If the provided evidence cannot establish which behavior is required, select E.",
        "Reply with exactly ONE uppercase letter A, B, C, D, or E. No explanation.",
        "",
        "Observed behavior:",
        case["observation"],
        "",
        "Candidate actions:",
    ]
    lines.extend(f'{k}: {case["choices"][k]}' for k in ("A", "B", "C", "D", "E"))
    if arm == "GENERAL":
        lines += ["", "Additional review guidance:",
                  "Consider boundary conditions, valid-case preservation, unintended regressions, "
                  "and whether evidence actually warrants the intended behavior. Be cautious."]
    elif arm == "DISTINCTION":
        lines += ["", "Independently grounded diagnostic (not a repair instruction):",
                  case["diagnosis"]]
    return "\n".join(lines)


def main():
    source_bytes = CASES_PATH.read_bytes()
    data = json.loads(source_bytes)
    expected = data["arms"]
    assert expected == ["RAW", "GENERAL", "DISTINCTION"]
    cases = data["cases"]
    assert len(cases) == 10 and len({x["id"] for x in cases}) == 10
    assert sum(x["category"] == "external_merged" for x in cases) == 8
    assert sum(x["category"] == "contract_unknown" for x in cases) == 2
    assert all(set(x["choices"]) == set("ABCDE") for x in cases)
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY_MISSING")
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"], timeout=90.0, max_retries=0)
    jobs = [(case, arm) for case in cases for arm in expected]
    random.Random(data["seed"]).shuffle(jobs)
    result = {
        "schema": data["schema"],
        "experiment_sha": os.environ.get("GITHUB_SHA", ""),
        "cases_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "model_requested": data["model"],
        "effort": data["reasoning_effort"],
        "max_output_tokens": data["max_output_tokens"],
        "expected_calls": len(jobs),
        "calls": [],
    }
    start = time.monotonic()
    for i, (case, arm) in enumerate(jobs, 1):
        prompt = make_prompt(case, arm)
        t = time.monotonic()
        outcome = {
            "case_id": case["id"], "arm": arm,
            "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
            "prompt_chars": len(prompt),
        }
        try:
            response = client.responses.create(
                model=data["model"],
                reasoning={"effort": data["reasoning_effort"]},
                input=prompt,
                max_output_tokens=data["max_output_tokens"],
            )
            response_text = (response.output_text or "").strip()
            m = re.fullmatch(r"[A-E]", response_text)
            outcome.update({
                "choice": m.group(0) if m else None,
                "output_text": response_text[:300],
                "model_returned": response.model,
                "usage": response.usage.model_dump() if response.usage is not None else None,
                "status": "RESPONSE" if m else "INVALID_RESPONSE",
            })
        except Exception as exc:
            status = getattr(exc, "status_code", None)
            outcome.update({"choice": None, "status": "API_ERROR", "http_status": status,
                            "error_type": type(exc).__name__})
            if status in (401, 403, 404):
                outcome["fatal"] = True
        outcome["elapsed_seconds"] = round(time.monotonic() - t, 3)
        result["calls"].append(outcome)
        result["total_elapsed_seconds"] = round(time.monotonic() - start, 3)
        OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        print(f'[{i:02d}/{len(jobs)}] {case["id"]} {arm}: {outcome["status"]}'
              f' choice={outcome["choice"]} elapsed={outcome["elapsed_seconds"]}s', flush=True)
        if outcome.get("fatal"):
            break
    if len(result["calls"]) != len(jobs):
        raise SystemExit("INCOMPLETE_AUTH_OR_MODEL_PREFLIGHT")
    if any(x["status"] == "API_ERROR" for x in result["calls"]):
        raise SystemExit("INCOMPLETE_API_ERRORS")
    print("ALL_CALLS_COMPLETED", len(result["calls"]), flush=True)


if __name__ == "__main__":
    main()
