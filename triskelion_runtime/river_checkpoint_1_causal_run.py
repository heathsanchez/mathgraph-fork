from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.checkpoint_0.run import safe_capability, tasks
from experiments.river_checkpoint_1_v2.run import extract_source, visible_request
from triskelion.artifacts import apply_artifact
from triskelion.providers import RiverProvider
from triskelion.runtime import Runtime

PROTOCOL = "TRISKELION_RIVER_CHECKPOINT_1_CAUSAL_V1"
MODEL = "Qwen/Qwen3.5-9B"
SEED = 20260817
MAX_TOKENS = 512
INTERVENTIONS = {
    "none": (False, False),
    "manifest_only": (True, False),
    "artifact_only": (False, True),
    "full": (True, True),
}


def manifest_text(cap):
    return "Installed scoped capability manifest:\n" + json.dumps({
        "id": cap.capability_id,
        "preconditions": cap.preconditions,
        "postconditions": cap.postconditions,
        "scope": cap.scope,
    }, sort_keys=True)


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists(): raise SystemExit("output exists; refusing to overwrite frozen evidence")
    args.out.mkdir(parents=True); (args.out / "RAW").mkdir()
    runtime = Runtime(args.out / "state")
    cap = safe_capability(); cap.status = "verified"; runtime.install(cap)
    provider = RiverProvider(MODEL)
    corpus = tasks()[:2]
    rows = []

    for task_i, task in enumerate(corpus):
        seed = SEED + task_i
        for name, (show_manifest, apply_executable) in INTERVENTIONS.items():
            prompt = visible_request(task)
            if show_manifest: prompt += "\n\n" + manifest_text(cap)
            infrastructure_error = model_output_error = artifact_error = None
            response_row = None; candidate = ""
            try:
                response = provider.sample(prompt, seed=seed, max_tokens=MAX_TOKENS)
                response_row = response.to_dict()
                response_row["text_sha256"] = hashlib.sha256(response.text.encode()).hexdigest()
            except Exception as exc:
                infrastructure_error = f"{exc.__class__.__name__}: {exc}"
            if not infrastructure_error:
                try: candidate = extract_source(response.text, task.tests[0]["function"])
                except Exception as exc: model_output_error = f"{exc.__class__.__name__}: {exc}"
            if apply_executable and candidate and not model_output_error:
                try: candidate = apply_artifact(cap.artifact["name"], candidate)
                except Exception as exc: artifact_error = f"{exc.__class__.__name__}: {exc}"
            if infrastructure_error or model_output_error or artifact_error:
                verdict = {"passed": False, "infrastructure_error": infrastructure_error,
                           "model_output_error": model_output_error, "artifact_error": artifact_error,
                           "failures": []}
            else: verdict = runtime.verifier.verify(task, candidate).to_dict()
            rows.append({"task_id": task.task_id, "intervention": name,
                         "show_manifest": show_manifest, "apply_executable": apply_executable,
                         "prompt": prompt, "response": response_row, "candidate": candidate,
                         "infrastructure_error": infrastructure_error,
                         "model_output_error": model_output_error,
                         "artifact_error": artifact_error, "verdict": verdict})

    by = {(r["task_id"], r["intervention"]): r for r in rows}
    pair_equal = {}
    for task in corpus:
        tid = task.task_id
        def response_hash(intervention):
            response = by[(tid, intervention)]["response"]
            return response["text_sha256"] if response else None
        pair_equal[tid] = {
            "none_equals_artifact_only": response_hash("none") is not None and response_hash("none") == response_hash("artifact_only"),
            "manifest_only_equals_full": response_hash("manifest_only") is not None and response_hash("manifest_only") == response_hash("full"),
        }
    passed = {name: sum(by[(t.task_id,name)]["verdict"]["passed"] for t in corpus) for name in INTERVENTIONS}
    artifact_closures = sum(
        not by[(t.task_id,"none")]["verdict"]["passed"] and by[(t.task_id,"artifact_only")]["verdict"]["passed"]
        for t in corpus
    )
    incremental_closures = sum(
        not by[(t.task_id,"manifest_only")]["verdict"]["passed"] and by[(t.task_id,"full")]["verdict"]["passed"]
        for t in corpus
    )
    infrastructure_errors = sum(bool(r["infrastructure_error"]) for r in rows)
    result = {"protocol": PROTOCOL, "model": MODEL, "temperature": 0.0,
              "max_tokens": MAX_TOKENS, "seed": SEED, "tasks": [t.task_id for t in corpus],
              "passed": passed, "paired_response_hashes": pair_equal,
              "artifact_causal_closures": artifact_closures,
              "incremental_artifact_closures_beyond_manifest": incremental_closures,
              "infrastructure_errors": infrastructure_errors,
              "gates": {
                  "paired_outputs_identical": all(all(v.values()) for v in pair_equal.values()),
                  "zero_infrastructure_errors": infrastructure_errors == 0,
                  "artifact_only_passes_both": passed["artifact_only"] == len(corpus),
                  "full_passes_both": passed["full"] == len(corpus),
                  "artifact_causal_closure": artifact_closures >= 1,
                  "incremental_artifact_value_beyond_manifest": incremental_closures >= 1,
              }}
    (args.out / "RAW" / "calls.json").write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n")
    (args.out / "RESULTS.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__": main()
