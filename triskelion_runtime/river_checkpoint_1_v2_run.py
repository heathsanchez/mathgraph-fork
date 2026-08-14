from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.checkpoint_0.run import round_capability, safe_capability, tasks
from triskelion.artifacts import apply_artifact
from triskelion.providers import RiverProvider
from triskelion.runtime import Runtime
from triskelion.scope import matches_scope

PROTOCOL = "TRISKELION_RIVER_CHECKPOINT_1_V2"
MODEL = "Qwen/Qwen3.5-9B"
SEED = 20260816
MAX_TOKENS = 512
ARMS = ["cold", "raw_memory", "always_on", "verified"]


def visible_request(task):
    public = task.tests[:1]
    return (
        "Repair this Python function for its project's established contract. "
        "Preserve normal behavior. Return only one complete Python code block.\n\n"
        f"SOURCE:\n```python\n{task.source}```\n"
        f"PUBLIC EXAMPLE (protected edge cases are hidden): {json.dumps(public, sort_keys=True)}"
    )


def memory_view(runtime, task, arm):
    if arm == "cold":
        return [], ""
    if arm == "raw_memory":
        return ["PY.ZERO_DIVISION_DEFAULT.V1"], (
            "Prior lesson: division repairs should return 0.0 when the divisor is zero. "
            "Treat this as generally reusable."
        )
    ids = sorted(runtime.registry.capabilities) if arm == "always_on" else runtime.closure(task, scoped=True)
    descriptions = []
    for cid in ids:
        cap = runtime.registry.capabilities[cid]
        descriptions.append(json.dumps({
            "id": cid, "preconditions": cap.preconditions,
            "postconditions": cap.postconditions, "scope": cap.scope,
        }, sort_keys=True))
    return ids, "Installed capability manifests:\n" + "\n".join(descriptions)


def extract_source(text: str, function_name: str) -> str:
    blocks = re.findall(r"```(?:python)?\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    valid = []
    for index, block in enumerate(blocks):
        try:
            tree = ast.parse(block)
        except SyntaxError:
            continue
        defines_target = any(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name
            for node in tree.body
        )
        if defines_target:
            valid.append((index, block))
    if not valid:
        raise ValueError(f"no fenced Python block defines {function_name!r}")
    return valid[-1][1].strip() + "\n"


def self_test():
    assert extract_source("text```python\ndef f(x):\n return x\n```", "f").startswith("def f")
    assert "return 2" in extract_source(
        "```python\ndef f():\n return 1\n``` prose ```python\ndef f():\n return 2\n```", "f"
    )
    try:
        extract_source("```json\n{}\n```", "f")
    except ValueError:
        pass
    else:
        raise AssertionError("non-function block must fail")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test(); print("V2 extractor self-test: PASS"); return
    if args.out is None:
        raise SystemExit("--out is required")
    if args.out.exists():
        raise SystemExit("output exists; refusing to overwrite frozen evidence")
    args.out.mkdir(parents=True); (args.out / "RAW").mkdir()

    runtime = Runtime(args.out / "state")
    runtime.install(round_capability())
    safe = safe_capability(); safe.status = "verified"; runtime.install(safe)
    provider = RiverProvider(MODEL)
    corpus = tasks()
    raw_rows, results = [], {}

    for arm_i, arm in enumerate(ARMS):
        arm_rows = []
        for task_i, task in enumerate(corpus):
            selected, memory = memory_view(runtime, task, arm)
            prompt = visible_request(task) + ("\n\n" + memory if memory else "")
            call_seed = SEED + arm_i * 100 + task_i
            infrastructure_error = model_output_error = artifact_error = None
            response_row = None
            try:
                response = provider.sample(prompt, seed=call_seed, max_tokens=MAX_TOKENS)
                response_row = response.to_dict()
                response_row["text_sha256"] = hashlib.sha256(response.text.encode()).hexdigest()
            except Exception as exc:
                infrastructure_error = f"{exc.__class__.__name__}: {exc}"
            if infrastructure_error is None:
                try:
                    function_name = task.tests[0]["function"]
                    candidate = extract_source(response.text, function_name)
                except Exception as exc:
                    candidate = ""; model_output_error = f"{exc.__class__.__name__}: {exc}"
            else:
                candidate = ""
            if infrastructure_error is None and model_output_error is None:
                try:
                    for cid in sorted(selected, key=lambda x: (
                        runtime.registry.capabilities[x].artifact.get("execution_order", 100), x
                    )):
                        candidate = apply_artifact(runtime.registry.capabilities[cid].artifact["name"], candidate)
                except Exception as exc:
                    artifact_error = f"{exc.__class__.__name__}: {exc}"
            if infrastructure_error or model_output_error or artifact_error:
                verdict = {"passed": False, "infrastructure_error": infrastructure_error,
                           "model_output_error": model_output_error, "artifact_error": artifact_error,
                           "failures": []}
            else:
                verdict = runtime.verifier.verify(task, candidate).to_dict()
            row = {"arm": arm, "task_id": task.task_id, "selected": selected,
                   "prompt": prompt, "response": response_row, "candidate": candidate,
                   "infrastructure_error": infrastructure_error,
                   "model_output_error": model_output_error,
                   "artifact_error": artifact_error, "verdict": verdict}
            raw_rows.append(row); arm_rows.append(row)
        selected_pairs = sum(len(r["selected"]) for r in arm_rows)
        false_pairs = sum(
            not matches_scope(runtime.registry.capabilities[cid].scope, task)
            for task, row in zip(corpus, arm_rows) for cid in row["selected"]
        )
        responses = [r["response"] for r in arm_rows if r["response"]]
        results[arm] = {
            "passed": sum(r["verdict"]["passed"] for r in arm_rows), "total": len(arm_rows),
            "false_activation_rate": false_pairs / selected_pairs if selected_pairs else 0.0,
            "infrastructure_errors": sum(bool(r["verdict"].get("infrastructure_error")) for r in arm_rows),
            "output_format_errors": sum(bool(r["model_output_error"]) for r in arm_rows),
            "latency_ms_total": round(sum(r["latency_ms"] for r in responses), 3),
            "output_tokens_total": sum((r["output_tokens"] or 0) for r in responses),
        }

    evidence = {"protocol": PROTOCOL, "model": MODEL, "temperature": 0.0,
                "max_tokens": MAX_TOKENS, "seed": SEED, "results": results,
                "gates": {
                    "verified_gt_cold": results["verified"]["passed"] > results["cold"]["passed"],
                    "verified_gt_always_on": results["verified"]["passed"] > results["always_on"]["passed"],
                    "verified_lower_false_activation": results["verified"]["false_activation_rate"] < results["always_on"]["false_activation_rate"],
                    "zero_infrastructure_errors": sum(x["infrastructure_errors"] for x in results.values()) == 0,
                }}
    (args.out / "RAW" / "calls.json").write_text(json.dumps(raw_rows, indent=2, sort_keys=True) + "\n")
    (args.out / "RESULTS.json").write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps(evidence, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
