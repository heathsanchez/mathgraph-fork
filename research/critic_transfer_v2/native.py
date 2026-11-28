"""Native source and author-test authority. No model API access here."""
import ast
import collections
import hashlib
import json
import os
import pathlib
import subprocess
import tempfile
import xml.etree.ElementTree as ET

HERE=pathlib.Path(__file__).resolve().parent
IMAGE="mathgraph-critic-transfer-v2:20261128"
def dump(p,x):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,sort_keys=True,indent=2,ensure_ascii=False,allow_nan=False)+"\n")
def load(p):
    return json.loads(p.read_text())
def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()
def stable(x):
    return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
def run(cmd,**kw):
    return subprocess.run(cmd,check=False,text=True,capture_output=True,**kw)
def build():
    p=run(["docker","build","-t",IMAGE,str(HERE)],timeout=600)
    if p.returncode:
        print(p.stdout[-5000:],p.stderr[-5000:],flush=True)
        raise RuntimeError("DOCKER_BUILD_FAILED")
    p=run(["docker","run","--rm","--network","none",IMAGE,"python","-m","pip","freeze"],timeout=60)
    if p.returncode:
        raise RuntimeError("ENV_CENSUS_FAILED")
    ver=run(["docker","run","--rm","--network","none",IMAGE,"python","--version"],timeout=60)
    return {"python":ver.stdout.strip(),"packages":p.stdout.splitlines()}
def inventory(source):
    lines=source.splitlines(keepends=True)
    tree=ast.parse(source)
    out=[]
    def walk(nodes,prefix):
        for node in nodes:
            if isinstance(node,ast.ClassDef):
                walk(node.body,prefix+node.name+".")
            elif isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
                start=min([node.lineno]+[d.lineno for d in node.decorator_list])
                end=node.end_lineno
                body="".join(lines[start-1:end])
                if len(body)>12000:
                    continue
                out.append({"id":prefix+node.name+"@"+str(start),"name":prefix+node.name,
                            "start":start,"end":end,"source":body})
    walk(tree.body,"")
    return out
def exact_author_location(old,new):
    a=old.splitlines(keepends=True); b=new.splitlines(keepends=True)
    oldfs=inventory(old); newfs=inventory(new)
    matches=[]
    for f in oldfs:
        for g in newfs:
            if f["name"]==g["name"] and f["source"]!=g["source"]:
                merged="".join(a[:f["start"]-1])+g["source"]+"".join(a[f["end"]:])
                if merged==new:
                    matches.append(f["id"])
    return matches[0] if len(matches)==1 else None

def native_test(tree,test_path,source_path,*,timeout=150):
    """No credentials, no network, no host access except immutable source and output dir."""
    tree=tree.resolve()
    with tempfile.TemporaryDirectory(prefix="native-output-") as d:
        out=pathlib.Path(d).resolve(); out.chmod(0o777)
        cmd=["docker","run","--rm","--network","none","--cap-drop","ALL",
             "--security-opt","no-new-privileges","--pids-limit","128","--memory","1400m",
             "--cpus","2","--read-only","--user","65534:65534",
             "--tmpfs","/tmp:rw,nosuid,nodev,size=512m",
             "-v",str(tree)+":/work:ro","-v",str(out)+":/out:rw",
             "-e","HOME=/tmp","-e","PYTHONDONTWRITEBYTECODE=1",
             "-e","PYTHONPATH=/harness:/work/src:/work",
             "-e","PYTEST_DISABLE_PLUGIN_AUTOLOAD=1",
             "-e","NATIVE_SOURCE=/work/"+source_path,
             "-w","/work",IMAGE,"python","-m","pytest","-p","trace_plugin",
             "-p","no:cacheprovider","-q","--tb=short","--junitxml=/out/junit.xml",test_path]
        try:
            p=run(cmd,timeout=timeout)
        except subprocess.TimeoutExpired:
            return {"status":"UNKNOWN_TIMEOUT","tests":{},"trace":{},"diagnostic":""}
        info={"returncode":p.returncode,"status":"EXECUTED",
              "diagnostic":(p.stdout+"\n"+p.stderr)[-16000:],"tests":{},"trace":{}}
        xml=out/"junit.xml"
        if not xml.exists():
            info["status"]="UNKNOWN_NO_JUNIT"
            return info
        try:
            root=ET.parse(xml).getroot()
            for c in root.iter("testcase"):
                key=c.attrib.get("classname","")+"::"+c.attrib.get("name","")
                if key in info["tests"]:
                    info["status"]="UNKNOWN_DUPLICATE_CASE_ID"
                    return info
                result="pass"
                for typ in ("failure","error","skipped"):
                    if c.find(typ) is not None:
                        result=typ;break
                info["tests"][key]=result
            t=out/"trace.json"
            if t.exists():
                info["trace"]=load(t)
        except (ValueError,ET.ParseError,OSError):
            info["status"]="UNKNOWN_BAD_RECEIPT"
        return info
def admit_red_green(base,fixed):
    a,b=base["tests"],fixed["tests"]
    if base["status"]!="EXECUTED" or fixed["status"]!="EXECUTED":
        return False
    if base.get("returncode")!=1 or fixed.get("returncode")!=0 or not a or set(a)!=set(b):
        return False
    if any(v not in ("pass","failure","skipped") for v in a.values()):
        return False
    if sum(v=="pass" for v in a.values())<3 or not any(v=="failure" for v in a.values()):
        return False
    return all(b[k]==("skipped" if v=="skipped" else "pass") for k,v in a.items())
def repair_green(base,trial):
    a,b=base["tests"],trial["tests"]
    return (trial["status"]=="EXECUTED" and trial.get("returncode")==0
            and bool(a) and set(a)==set(b)
            and all(b[k]==("skipped" if v=="skipped" else "pass") for k,v in a.items()))

def patch_source(old,edits,allowed):
    functions={f["id"]:f for f in inventory(old)}
    if not isinstance(edits,list) or not 1<=len(edits)<=2:
        raise ValueError("bad edit count")
    seen=set(); changes=[]
    for e in edits:
        if not isinstance(e,dict) or set(e)!={"id","replacement"} or e["id"] not in allowed or e["id"] in seen:
            raise ValueError("out of scope edit")
        seen.add(e["id"]); f=functions[e["id"]]; replacement=e["replacement"]
        if not isinstance(replacement,str) or not replacement.strip() or len(replacement)>14000:
            raise ValueError("bad replacement")
        import textwrap
        # Whole function replacement; preserve existing indentation and name.
        rep=textwrap.dedent(replacement).rstrip()+"\n"
        oldrep=textwrap.dedent(f["source"])
        oldtree=ast.parse(oldrep); newtree=ast.parse(rep)
        if len(newtree.body)!=1 or not isinstance(newtree.body[0],(ast.FunctionDef,ast.AsyncFunctionDef)):
            raise ValueError("replacement must be one function")
        if newtree.body[0].name!=oldtree.body[0].name:
            raise ValueError("renamed function")
        # Refuse new test introspection, process/network/credential operations.
        def names(t):
            return {n.id for n in ast.walk(t) if isinstance(n,ast.Name)}|{n.attr for n in ast.walk(t) if isinstance(n,ast.Attribute)}
        banned={"pytest","unittest","sys","os","environ","subprocess","socket","requests","urllib","importlib",
                "inspect","builtins","__import__","exec","eval","compile","open","globals","locals","getattr",
                "setattr","__dict__","__class__","__subclasses__","__globals__","__builtins__","__code__"}
        if (names(newtree)-names(oldtree))&banned:
            raise ValueError("new privileged or introspective reference")
        oldimports={ast.dump(n) for n in ast.walk(oldtree) if isinstance(n,(ast.Import,ast.ImportFrom))}
        newimports={ast.dump(n) for n in ast.walk(newtree) if isinstance(n,(ast.Import,ast.ImportFrom))}
        if newimports-oldimports:
            raise ValueError("new imports disallowed in bounded pilot")
        indent=f["source"][:len(f["source"])-len(f["source"].lstrip(" \t"))]
        rep=textwrap.indent(rep,indent)
        if rep==f["source"]:
            raise ValueError("unchanged")
        changes.append((f["start"]-1,f["end"],rep))
    lines=old.splitlines(keepends=True)
    for start,end,rep in sorted(changes,reverse=True):
        lines[start:end]=[rep]
    result="".join(lines)
    ast.parse(result)
    return result

