#!/usr/bin/env python3
"""Finite, source-scoped structural gap gate and safe expression interpreter.

No labels naming repair families. Never execute model-generated Python.
This module does not authenticate normativity, completeness, or real source states;
those are independent fixture admission boundaries.
"""
import ast
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
CASES = HERE / "cases.json"


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def source_digest():
    return hashlib.sha256(CASES.read_bytes()).hexdigest()


def read_cases():
    obj = json.loads(CASES.read_text())
    assert obj["schema"] == "mathgraph/gap-conditional-v1"
    assert len(obj["cases"]) == 9
    assert len({c["id"] for c in obj["cases"]}) == 9
    return obj


def assess(case):
    """A source- and oracle-relative finite obstruction, or a protected STOP."""
    if case["authority"] != "declared":
        return {"status": "UNKNOWN_AUTHORITY", "witness": None}
    rows = case["rows"]
    if not rows or any("target" not in x for x in rows):
        return {"status": "UNKNOWN_TARGET", "witness": None}
    seen_source = {}
    for r in rows:
        key = canonical(r["input"])
        if key in seen_source and canonical(seen_source[key]["target"]) != canonical(r["target"]):
            return {"status": "UNOBSERVABLE_FROM_SOURCE", "witness": {
                "left_input": seen_source[key]["input"],
                "right_input": r["input"],
                "same_source": True,
                "different_required_outcomes": True}}
        seen_source.setdefault(key, r)
    seen = {}
    for r in rows:
        key = canonical(r["old_image"])
        if key in seen and canonical(seen[key]["target"]) != canonical(r["target"]):
            return {"status": "ELIGIBLE_GAP", "witness": {
                "left_input": seen[key]["input"],
                "right_input": r["input"],
                "same_old_observation": True,
                "different_required_outcomes": True}}
        seen.setdefault(key, r)
    if case["complete"]:
        return {"status": "SUFFICIENT_FROZEN_FINITE", "witness": None}
    return {"status": "UNKNOWN_INCOMPLETE", "witness": None}


class UnsafeExpression(ValueError):
    pass


ALLOWED_BINS = {
    ast.Add: lambda a,b:a+b,
    ast.Sub: lambda a,b:a-b,
    ast.Mult: lambda a,b:a*b,
    ast.Mod: lambda a,b:a%b,
}
ALLOWED_CMP = {
    ast.Eq: lambda a,b:a==b,
    ast.NotEq: lambda a,b:a!=b,
    ast.Gt: lambda a,b:a>b,
    ast.GtE: lambda a,b:a>=b,
    ast.Lt: lambda a,b:a<b,
    ast.LtE: lambda a,b:a<=b,
}
ALLOWED_UNARY = {
    ast.Not: lambda x:not x,
    ast.USub: lambda x:-x,
    ast.UAdd: lambda x:+x,
}
ALLOWED_CALLS = {"abs": abs, "len": len}


def _eval(node, source):
    if isinstance(node, ast.Expression):
        return _eval(node.body, source)
    if isinstance(node, ast.Constant):
        if type(node.value) not in (str, int, float, bool, type(None)):
            raise UnsafeExpression("UNSUPPORTED_CONSTANT")
        return node.value
    if isinstance(node, ast.Name):
        if node.id != "s":
            raise UnsafeExpression("NAME_NOT_ALLOWED")
        return source
    if isinstance(node, ast.Subscript):
        if not (isinstance(node.value, ast.Name) and node.value.id == "s"
                and isinstance(node.slice, ast.Constant) and type(node.slice.value) is str):
            raise UnsafeExpression("ONLY_SOURCE_FIELD_SUBSCRIPT")
        if node.slice.value not in source:
            raise UnsafeExpression("UNKNOWN_SOURCE_FIELD")
        return source[node.slice.value]
    if isinstance(node, (ast.Tuple, ast.List)):
        return [_eval(n, source) for n in node.elts]
    if isinstance(node, ast.BinOp) and type(node.op) in ALLOWED_BINS:
        return ALLOWED_BINS[type(node.op)](_eval(node.left,source),_eval(node.right,source))
    if isinstance(node, ast.UnaryOp) and type(node.op) in ALLOWED_UNARY:
        return ALLOWED_UNARY[type(node.op)](_eval(node.operand,source))
    if isinstance(node, ast.BoolOp) and type(node.op) in (ast.And,ast.Or):
        vs = [_eval(n,source) for n in node.values]
        return all(bool(v) for v in vs) if isinstance(node.op,ast.And) else any(bool(v) for v in vs)
    if isinstance(node, ast.Compare) and all(type(op) in ALLOWED_CMP for op in node.ops):
        prev = _eval(node.left,source)
        for op,nxt in zip(node.ops,node.comparators):
            v=_eval(nxt,source)
            if not ALLOWED_CMP[type(op)](prev,v):
                return False
            prev=v
        return True
    if (isinstance(node, ast.Call) and isinstance(node.func,ast.Name)
            and node.func.id in ALLOWED_CALLS and len(node.args)==1 and not node.keywords):
        return ALLOWED_CALLS[node.func.id](_eval(node.args[0],source))
    raise UnsafeExpression("UNSUPPORTED_SYNTAX:" + type(node).__name__)


def compile_expression(expr):
    if not isinstance(expr,str) or not expr.strip() or len(expr)>300:
        raise UnsafeExpression("INVALID_EXPRESSION_SIZE")
    try:
        tree=ast.parse(expr,mode="eval")
    except (SyntaxError,ValueError) as e:
        raise UnsafeExpression("INVALID_EXPRESSION_SYNTAX") from e
    if sum(1 for _ in ast.walk(tree))>80:
        raise UnsafeExpression("EXPRESSION_TOO_COMPLEX")
    # Structural syntax preflight, not a safety claim for arbitrary Python:
    # AST evaluator below is the only execution mechanism.
    return tree


def verify_expression(case,expr):
    """Exact target-kernel preservation on every *frozen finite* row."""
    try:
        tree=compile_expression(expr)
        values=[]
        for r in case["rows"]:
            value=_eval(tree,r["input"])
            values.append(canonical(value))
        targets=[canonical(r["target"]) for r in case["rows"]]
        for i in range(len(values)):
            for j in range(i+1,len(values)):
                if (values[i]==values[j]) != (targets[i]==targets[j]):
                    return {"status":"REJECTED_KERNEL_MISMATCH",
                            "first_pair":[i,j],
                            "error":"OVER_SPLIT" if targets[i]==targets[j] else "UNDER_SPLIT",
                            "checked_rows":len(values)}
        return {"status":"WARRANTED_FROZEN_FINITE_KERNEL",
                "checked_rows":len(values),
                "distinct_target_classes":len(set(targets)),
                "distinct_output_classes":len(set(values))}
    except (UnsafeExpression, TypeError, ValueError, KeyError, ZeroDivisionError, OverflowError, RecursionError) as e:
        return {"status":"UNKNOWN_UNSUPPORTED_OR_FAILED_CONSTRUCTION",
                "reason": type(e).__name__,
                "detail":str(e)[:180]}
    except Exception as e:
        return {"status":"UNKNOWN_EXECUTION", "reason":type(e).__name__}


def self_test():
    obj=read_cases()
    count={}
    for case in obj["cases"]:
        r=assess(case)
        count[r["status"]]=count.get(r["status"],0)+1
        print(case["id"],r["status"])
    assert count == {
        "ELIGIBLE_GAP":5,
        "SUFFICIENT_FROZEN_FINITE":1,
        "UNKNOWN_INCOMPLETE":1,
        "UNKNOWN_AUTHORITY":1,
        "UNOBSERVABLE_FROM_SOURCE":1,
    }, count
    assert verify_expression(obj["cases"][0],'s["key"]')["status"]=="WARRANTED_FROZEN_FINITE_KERNEL"
    assert verify_expression(obj["cases"][1],'(s["frame"], s["coords"])')["status"]=="WARRANTED_FROZEN_FINITE_KERNEL"
    assert verify_expression(obj["cases"][2],'abs(s["current"] - s["previous_same_cell"]) > 5')["status"]=="WARRANTED_FROZEN_FINITE_KERNEL"
    assert verify_expression(obj["cases"][3],'s["temperature"] < 120 or s["temperature"] > 180')["status"]=="WARRANTED_FROZEN_FINITE_KERNEL"
    assert verify_expression(obj["cases"][4],'s["word"]')["status"]=="REJECTED_KERNEL_MISMATCH"
    assert verify_expression(obj["cases"][0],'__import__("os").system("true")')["status"]=="UNKNOWN_UNSUPPORTED_OR_FAILED_CONSTRUCTION"
    print("STRUCTURAL_GATE_AND_SAFE_DSL_SELF_TEST_OK",count,source_digest())


if __name__=="__main__":
    self_test()
