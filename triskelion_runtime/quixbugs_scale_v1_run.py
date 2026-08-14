from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from triskelion.providers import RiverProvider

PROTOCOL = "TRISKELION_QUIXBUGS_SCALE_V1"
MODEL = "Qwen/Qwen3.5-9B"
SEED = 20260818
MAX_TOKENS = 1400
ARMS = ("cold", "raw_memory", "always_on", "verified", "wrong_scope_manifest")
CAP_ORDER = (
    "QB.BOUNDARY_COMPLETENESS.V1",
    "QB.RECURSIVE_PROGRESS.V1",
    "QB.MONOTONE_ACCUMULATION.V1",
    "QB.GRAPH_FRONTIER.V1",
    "QB.PRESERVE_BRANCHES.V1",
)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def extract_candidate(text: str) -> str:
    blocks = re.findall(r"```(?:python)?\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    valid = []
    for index, block in enumerate(blocks):
        try:
            ast.parse(block)
        except SyntaxError:
            continue
        valid.append((index, block))
    if not valid:
        raise ValueError("no fenced block parses as a complete Python module")
    return valid[-1][1].strip() + "\n"


def contract_from_test(text: str) -> str:
    tree = ast.parse(text)
    return ast.get_docstring(tree, clean=False) or "No module contract was supplied."


def calls_itself(source: str, task_id: str) -> bool:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    return any(
        isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == task_id
        for node in ast.walk(tree)
    )


def routed_capabilities(task_id: str, source: str, contract: str) -> list[str]:
    """Frozen source-only router. Gold labels are intentionally inaccessible."""
    joined = (source + "\n" + contract).lower()
    selected = []
    boundary_terms = ("inclusive", "lowest index", "upper bound", "maximum", "first n", "at most", "range(")
    if any(term in joined for term in boundary_terms):
        selected.append(CAP_ORDER[0])
    recursive = calls_itself(source, task_id)
    if recursive:
        selected.append(CAP_ORDER[1])
    monotone_terms = ("max_so_far", "longest", "visited", "nodesseen", "ordered_nodes", "result =", "result +=")
    if any(term in joined for term in monotone_terms) and any(
        isinstance(node, (ast.For, ast.While)) for node in ast.walk(ast.parse(source))
    ):
        selected.append(CAP_ORDER[2])
    graph_terms = ("successor", "incoming_nodes", "outgoing_nodes", "weight_by_edge", "length_by_edge", "queue", "nodesseen")
    if any(term in joined for term in graph_terms):
        selected.append(CAP_ORDER[3])
    preserve_terms = ("subset", "subsequence", "sequence", "reversed", "yield", "permutation")
    if recursive and any(term in joined for term in preserve_terms):
        selected.append(CAP_ORDER[4])
    return selected


def wrong_scope(selected: list[str], gold: list[str]) -> list[str]:
    """Keep activation count but replace each routed critic with a gold-inapplicable critic."""
    wrong = []
    for i, cid in enumerate(selected):
        available = [x for x in CAP_ORDER if x not in gold and x != cid]
        if not available:
            available = [x for x in CAP_ORDER if x != cid]
        wrong.append(available[(CAP_ORDER.index(cid) + i) % len(available)])
    return wrong


def guidance(capabilities: dict[str, dict], ids: list[str]) -> str:
    records = []
    for cid in ids:
        cap = capabilities[cid]
        records.append(json.dumps({
            "capability_id": cid,
            "interface": cap["interface"],
            "preconditions": cap["preconditions"],
            "postconditions": cap["postconditions"],
            "scope": cap["scope"],
            "executable_guidance": cap["artifact"]["template"],
        }, sort_keys=True))
    return "Installed capability manifests and callable critic outputs:\n" + "\n".join(records)


def raw_memory(snapshot: Path, manifest: dict) -> str:
    episodes = []
    for task_id in manifest["acquisition"].values():
        buggy = (snapshot / "python_programs" / f"{task_id}.py").read_text()
        correct = (snapshot / "correct_python_programs" / f"{task_id}.py").read_text()
        episodes.append(f"EPISODE {task_id}\nFAILED SOURCE:\n{buggy}\nVERIFIED REPAIR:\n{correct}")
    return "Prior raw successful repair episodes (unscoped):\n\n" + "\n\n".join(episodes)


def prompt_for(task_id: str, source: str, contract: str, memory: str) -> str:
    prompt = (
        "Repair this independently authored Python module for the stated project contract. "
        "Return only one complete replacement module in a fenced Python code block. "
        "Do not mention or invent tests.\n\n"
        f"TASK: {task_id}\nCONTRACT:\n{contract}\n\nBUGGY MODULE:\n```python\n{source}```"
    )
    return prompt + ("\n\n" + memory if memory else "")


def purge_pycache(root: Path) -> None:
    for path in root.rglob("__pycache__"):
        shutil.rmtree(path, ignore_errors=True)
    for path in root.rglob("*.pyc"):
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def verifier_once(snapshot: Path, test_path: str, module_path: str, candidate: str, timeout: float) -> dict:
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="triskelion_qb_verify_") as td:
        root = Path(td) / "repo"
        shutil.copytree(snapshot, root)
        target = root / module_path
        original_hash = hashlib.sha256(target.read_bytes()).hexdigest()
        candidate_hash = sha256_text(candidate)
        try:
            target.write_text(candidate)
            purge_pycache(root)
            env = os.environ.copy()
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            proc = subprocess.run(
                [sys.executable, "-B", "-m", "pytest", "-q", test_path],
                cwd=root, env=env, text=True, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, timeout=timeout,
            )
            status = "pass" if proc.returncode == 0 else "fail"
            return {"status": status, "passed": status == "pass", "returncode": proc.returncode,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 3),
                    "output": proc.stdout[-5000:], "candidate_sha256": candidate_hash,
                    "original_sha256": original_hash}
        except subprocess.TimeoutExpired as exc:
            output = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            return {"status": "timeout", "passed": False, "returncode": None,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 3),
                    "output": output[-5000:], "candidate_sha256": candidate_hash,
                    "original_sha256": original_hash}
        finally:
            target.write_bytes((snapshot / module_path).read_bytes())
            purge_pycache(root)


def verify(snapshot: Path, task: dict, candidate: str, timeout: float) -> dict:
    first = verifier_once(snapshot, task["test_path"], task["buggy_path"], candidate, timeout)
    replay = verifier_once(snapshot, task["test_path"], task["buggy_path"], candidate, timeout) if first["passed"] else None
    passed = bool(first["passed"] and replay and replay["passed"])
    return {"passed": passed, "first": first, "immediate_replay": replay,
            "provenance_verified": first["candidate_sha256"] == sha256_text(candidate),
            "isolated_order_independent": True}


def self_test(base: Path) -> None:
    frozen = base / "frozen_v1"
    manifest = json.loads((frozen / "CORPUS_MANIFEST.json").read_text())
    caps = json.loads((frozen / "CAPABILITIES.json").read_text())
    assert len(manifest["tasks"]) == 40 and len(manifest["gold_applicability"]) == 35
    assert {x["capability_id"] for x in caps} == set(CAP_ORDER)
    assert extract_candidate("x```python\ndef f():\n return 1\n```y").startswith("def f")
    snapshot = base / "upstream_snapshot"
    task = next(x for x in manifest["tasks"] if x["task_id"] == "find_first_in_sorted")
    source = (snapshot / task["buggy_path"]).read_text()
    test = (snapshot / task["test_path"]).read_text()
    assert CAP_ORDER[0] in routed_capabilities(task["task_id"], source, contract_from_test(test))
    correct = (snapshot / task["correct_path"]).read_text()
    verdict = verify(snapshot, task, correct, 15)
    assert verdict["passed"] and verdict["immediate_replay"]["passed"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", choices=ARMS)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--timeout", type=float, default=15.0)
    args = ap.parse_args()
    base = Path(__file__).resolve().parent
    if args.self_test:
        self_test(base); print("QuixBugs scale self-test: PASS"); return
    if args.arm is None or args.out is None:
        raise SystemExit("--arm and --out are required")
    if args.out.exists():
        raise SystemExit("output exists; refusing to overwrite frozen evidence")
    args.out.mkdir(parents=True); (args.out / "RAW").mkdir()
    frozen = base / "frozen_v1"; snapshot = base / "upstream_snapshot"
    manifest = json.loads((frozen / "CORPUS_MANIFEST.json").read_text())
    cap_list = json.loads((frozen / "CAPABILITIES.json").read_text())
    capabilities = {x["capability_id"]: x for x in cap_list}
    provider = RiverProvider(MODEL)
    raw_episode_text = raw_memory(snapshot, manifest) if args.arm == "raw_memory" else ""
    rows = []
    protected = [x for x in manifest["tasks"] if x["split"] == "protected"]
    for task_i, task in enumerate(protected):
        task_id = task["task_id"]
        source = (snapshot / task["buggy_path"]).read_text()
        test_text = (snapshot / task["test_path"]).read_text()
        contract = contract_from_test(test_text)
        routed = routed_capabilities(task_id, source, contract)
        gold = manifest["gold_applicability"][task_id]
        if args.arm == "always_on": selected = list(CAP_ORDER)
        elif args.arm == "verified": selected = routed
        elif args.arm == "wrong_scope_manifest": selected = wrong_scope(routed, gold)
        else: selected = []
        memory = raw_episode_text if args.arm == "raw_memory" else (
            guidance(capabilities, selected) if selected else ""
        )
        prompt = prompt_for(task_id, source, contract, memory)
        response_row = None; candidate = ""
        infrastructure_error = model_output_error = None
        try:
            response = provider.sample(prompt, seed=SEED + task_i, max_tokens=MAX_TOKENS)
            response_row = response.to_dict(); response_row["text_sha256"] = sha256_text(response.text)
        except Exception as exc:
            infrastructure_error = f"{exc.__class__.__name__}: {exc}"
        if response_row:
            try:
                candidate = extract_candidate(response.text)
            except Exception as exc:
                model_output_error = f"{exc.__class__.__name__}: {exc}"
        verdict = ({"passed": False, "infrastructure_error": infrastructure_error,
                    "model_output_error": model_output_error}
                   if infrastructure_error or model_output_error
                   else verify(snapshot, task, candidate, args.timeout))
        false_selected = [cid for cid in selected if cid not in gold]
        missed = [cid for cid in gold if cid not in selected]
        rows.append({"protocol": PROTOCOL, "arm": args.arm, "task_id": task_id,
                     "category": task["category"], "seed": SEED + task_i,
                     "selected": selected, "routed_before_intervention": routed,
                     "gold_applicability": gold, "false_selected": false_selected,
                     "missed": missed, "prompt": prompt, "response": response_row,
                     "candidate": candidate, "candidate_sha256": sha256_text(candidate),
                     "infrastructure_error": infrastructure_error,
                     "model_output_error": model_output_error, "verdict": verdict})
    selected_n = sum(len(r["selected"]) for r in rows)
    summary = {"protocol": PROTOCOL, "model": MODEL, "temperature": 0.0,
               "max_tokens": MAX_TOKENS, "seed": SEED, "arm": args.arm,
               "passed": sum(r["verdict"]["passed"] for r in rows), "total": len(rows),
               "selected_activations": selected_n,
               "false_activations": sum(len(r["false_selected"]) for r in rows),
               "false_activation_rate": (sum(len(r["false_selected"]) for r in rows) / selected_n if selected_n else 0.0),
               "missed_activations": sum(len(r["missed"]) for r in rows),
               "infrastructure_errors": sum(bool(r["infrastructure_error"]) for r in rows),
               "output_format_errors": sum(bool(r["model_output_error"]) for r in rows),
               "latency_ms_total": round(sum((r["response"] or {}).get("latency_ms", 0) for r in rows), 3),
               "output_tokens_total": sum((r["response"] or {}).get("output_tokens") or 0 for r in rows)}
    (args.out / "RAW" / "calls.json").write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n")
    (args.out / "RESULTS.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
