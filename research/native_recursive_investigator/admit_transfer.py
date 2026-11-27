"""Freeze real native-author regression cohorts; no calls to the model."""
import collections
import hashlib
import io
import json
import os
import pathlib
import re
import shutil
import tarfile
import tempfile
import time
import urllib.parse
import urllib.request
from native import HERE, build, digest, dump, exact_author_location, inventory, native_test, admit_red_green

POOL=json.loads((HERE/"transfer_pool.json").read_text())
SHARD=int(os.environ.get("TRANSFER_SHARD","0"))
assert 0<=SHARD<8 and len(POOL)==32 and len(set(POOL))==32
REPOS=tuple(POOL[SHARD*4:SHARD*4+4])
ROOT=HERE/"transfer-admission"
MAX_PER_REPO=8
def request(url,api=False):
    headers={"User-Agent":"mathgraph-native-research-20261127"}
    if api:
        headers["Accept"]="application/vnd.github+json"
        if os.environ.get("GITHUB_TOKEN"):
            headers["Authorization"]="Bearer "+os.environ["GITHUB_TOKEN"]
    with urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=75) as response:
        data=response.read(65*1024*1024+1)
        if len(data)>65*1024*1024:raise ValueError("archive size")
        return data
def api(repo,endpoint):
    return json.loads(request("https://api.github.com/repos/"+repo+"/"+endpoint,True))
def test_file(p):
    path=pathlib.PurePosixPath(p)
    return p.endswith(".py") and (
        any(x in ("tests","test","testing") for x in path.parts[:-1]) or
        path.name.startswith("test_") or path.name.endswith("_test.py"))
def doc(p):
    low=p.lower()
    return (low.startswith(("docs/","doc/","changelog/","changes/","news/")) or
        pathlib.PurePosixPath(low).name.startswith(("readme","changelog","changes","news","history")) or
        low.endswith((".md",".rst")))
def layout(files):
    src=[]; tests=[]
    for f in files:
        p=f["filename"]
        if test_file(p):tests.append(f)
        elif p.endswith(".py") and not pathlib.PurePosixPath(p).name in ("setup.py","conftest.py"):src.append(f)
        elif not doc(p):return None
    if len(src)!=1 or len(tests)!=1:return None
    s,t=src[0],tests[0]
    if s["status"]!="modified" or t["status"] not in ("modified","added"):return None
    if not 1<=s.get("changes",0)<=100:return None
    if t.get("changes",0)>500:return None
    return s,t
def safe_archive(repo,sha,to):
    data=request("https://codeload.github.com/"+repo+"/tar.gz/"+sha)
    with tarfile.open(fileobj=io.BytesIO(data),mode="r:gz") as tf:
        members=tf.getmembers()
        if sum(m.size for m in members)>240*1024*1024:raise ValueError("expanded archive size")
        tf.extractall(to,filter="data")
    dirs=list(to.iterdir())
    if len(dirs)!=1 or not dirs[0].is_dir():raise ValueError("unexpected archive layout")
    dirs[0].chmod(0o755)
    return dirs[0],hashlib.sha256(data).hexdigest()
def gitblob(path):
    b=path.read_bytes()
    return hashlib.sha1(("blob "+str(len(b))+"\0").encode()+b).hexdigest()
def eligible_title(s):
    return (bool(re.search(r"\b(fix(?:es|ed|ing)?|bug|regression|incorrect|wrong|error|fail(?:s|ure|ing)?)\b",s,re.I))
        and not re.search(r"\b(security|vulnerab\w*|cve|xss|csrf|injection|exploit|auth(?:entication|orization)?|credential|password|token)\b",s,re.I))
def sample_test_text(path,red):
    # Exact test definitions for failing node(s), plus import context, not the hidden fix.
    import ast
    text=path.read_text(encoding="utf-8")
    lines=text.splitlines(keepends=True)
    failures=[k.split("::")[-1].split("[")[0] for k,v in red["tests"].items() if v=="failure"]
    fragments=[]
    try:
        tree=ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and node.name in failures:
                start=min([node.lineno]+[d.lineno for d in node.decorator_list])
                fragments.append("".join(lines[start-1:node.end_lineno]))
    except SyntaxError:pass
    return ("\n".join(lines[:30])+"\n\n"+"\n\n".join(fragments))[:10000]
def exact_author_locations(old,new):
    # Compare same-name occurrences in order, then require byte-for-byte reconstruction.
    oldfs=inventory(old);newfs=inventory(new)
    a=collections.defaultdict(list);b=collections.defaultdict(list)
    for f in oldfs:a[f["name"]].append(f)
    for f in newfs:b[f["name"]].append(f)
    edits=[]
    for name,fs in a.items():
        gs=b.get(name,[])
        if len(fs)!=len(gs):continue
        for f,g in zip(fs,gs):
            if f["source"]!=g["source"]:
                edits.append((f,g))
    if not 1<=len(edits)<=2:return []
    lines=old.splitlines(keepends=True)
    for f,g in sorted(edits,key=lambda x:x[0]["start"],reverse=True):
        lines[f["start"]-1:f["end"]]=g["source"].splitlines(keepends=True)
    if "".join(lines)!=new:return []
    return [f["id"] for f,g in sorted(edits,key=lambda x:x[0]["start"])]

def prepare(repo,pr,merge,environment,number):
    sha=merge["sha"]
    parents=merge.get("parents",[])
    if not parents:return None,"UNKNOWN_NO_PARENT"
    parent=parents[0]["sha"]
    pair=layout(merge.get("files",[]))
    if pair is None:return None,"UNKNOWN_MERGE_LAYOUT"
    s,t=pair
    sp,tp=s["filename"],t["filename"]
    with tempfile.TemporaryDirectory(prefix="source-native-") as tmp:
        tmp=pathlib.Path(tmp)
        base,b_archive=safe_archive(repo,parent,tmp/"base")
        fixed,f_archive=safe_archive(repo,sha,tmp/"fixed")
        for p in (base/sp,fixed/sp,fixed/tp):
            if not p.is_file() or p.is_symlink():return None,"UNKNOWN_MISSING_EXACT_FILES"
        if gitblob(fixed/sp)!=s["sha"] or gitblob(fixed/tp)!=t["sha"]:
            return None,"UNKNOWN_HEAD_BLOB_IDENTITY"
        old_bytes=(base/sp).read_bytes()
        old=old_bytes.decode("utf-8")
        new=(fixed/sp).read_bytes().decode("utf-8")
        if "\r" in old or "\r" in new:return None,"UNKNOWN_NON_LF_SOURCE"
        loc=exact_author_locations(old,new)
        fs=[f for f in inventory(old) if len(f["source"])<=6500]
        if not loc or not set(loc)<={f["id"] for f in fs} or len(fs)<3:
            return None,"UNKNOWN_NOT_ONE_OR_TWO_BOUNDED_FUNCTIONS"
        if t["status"]=="modified" and (not (base/tp).is_file() or (base/tp).is_symlink()):return None,"UNKNOWN_BASE_TEST_IDENTITY"
        if t["status"]=="added" and (base/tp).exists():return None,"UNKNOWN_BASE_TEST_IDENTITY"
        original_test_sha=gitblob(base/tp) if (base/tp).exists() else None
        original_source_sha=gitblob(base/sp)
        (base/tp).parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(fixed/tp,base/tp)
        red=native_test(base,tp,sp)
        # Hold all other bytes constant; author source is the sole intervention.
        (base/sp).write_bytes((fixed/sp).read_bytes())
        green=native_test(base,tp,sp)
        (base/sp).write_bytes(old_bytes)
        proof={"base":red,"author":green}
        if not admit_red_green(red,green):
            return proof,"UNKNOWN_NATIVE_AUTHORITY"
        if any(not v["trace"] or not any(x.get("lines") for x in v["trace"].values()) for v in (red,green)):
            return proof,"UNKNOWN_NO_SOURCE_SPECTRUM"
        case_id=f"case-{100+SHARD*10+number:03d}"
        cohort="candidate"
        secret_dir=ROOT/f"private-{cohort}"/case_id
        secret_dir.mkdir(parents=True,exist_ok=True)
        # Retain only the original parent tree plus exact author test; never send fixed source to model.
        with tarfile.open(secret_dir/"base.tar.gz","w:gz") as tar:
            tar.add(base,arcname="base")
        authority={"id":case_id,"repo":repo,"pr":pr["number"],"parent":parent,"merge":sha,
                   "source_path":sp,"test_path":tp,"base_blob":original_source_sha,
                   "head_blob":s["sha"],"original_test_blob":original_test_sha,
                   "author_test_blob":t["sha"],"base_archive_sha256":b_archive,"head_archive_sha256":f_archive,
                   "overlay_archive_sha256":digest(secret_dir/"base.tar.gz"),
                   "source_sha256":digest(base/sp),"test_sha256":digest(base/tp),"location":loc[0],"locations":loc,
                   "environment":environment,"native":proof}
        dump(secret_dir/"authority.json",authority)
        raw={"id":case_id,"source_path":sp,"test_path":tp,
             "diagnostic":red["diagnostic"],"tests":red["tests"],"trace":red["trace"],
             "test_excerpt":sample_test_text(base/tp,red),"functions":fs,
             "module_header":"\n".join(old.splitlines()[:min(70,min(f["start"] for f in fs)-1)])[:5000],
             "source_sha256":authority["source_sha256"],"test_sha256":authority["test_sha256"]}
        dump(ROOT/f"public-{cohort}"/(case_id+".json"),raw)
        return {"case":case_id,"repo":repo,"pr":pr["number"],"parent":parent,"merge":sha,
                "source_path":sp,"test_path":tp,"passes":sum(v=="pass" for v in red["tests"].values()),
                "fails":sum(v=="failure" for v in red["tests"].values()),"skips":sum(v=="skipped" for v in red["tests"].values())},"ADMITTED"

def main():
    ROOT.mkdir(exist_ok=True)
    for c in ("candidate",):
        for kind in ("public","private"):
            d=ROOT/f"{kind}-{c}";d.mkdir(exist_ok=True);dump(d/"_cohort.json",{"cohort":c})
    env=build()
    attempts=[];selected=[]
    deadline=time.monotonic()+25*60
    def persist():dump(ROOT/"admission.json",{"source_sha":os.environ.get("GITHUB_SHA"),"shard":SHARD,"repository_order":REPOS,"environment":env,"attempts":attempts,"selected":selected})
    persist()
    for repo in REPOS:
        if len(selected)==2 or time.monotonic()>deadline-330:break
        try:
            prs=[]
            for page in (1,2):
                batch=api(repo,f"pulls?state=closed&sort=updated&direction=desc&per_page=100&page={page}")
                prs.extend(batch)
                if len(batch)<100:break
        except Exception as exc:
            attempts.append({"repo":repo,"status":"UNKNOWN_LIST","error":type(exc).__name__});persist();continue
        candidates=sorted({p["number"]:p for p in prs if p.get("merged_at") and p.get("merge_commit_sha") and eligible_title(p.get("title",""))}.values(),key=lambda p:-p["number"])[:25]
        checked=0
        for pr in candidates:
            if checked>=MAX_PER_REPO or time.monotonic()>deadline-330:break
            rec={"repo":repo,"pr":pr["number"],"merge":pr["merge_commit_sha"]}
            try:
                merge=api(repo,"commits/"+pr["merge_commit_sha"])
                if layout(merge.get("files",[])) is None:
                    rec["status"]="INELIGIBLE_METADATA";attempts.append(rec);persist();continue
                checked+=1
                result,status=prepare(repo,pr,merge,env,len(selected)+1)
                rec["status"]=status
                if status=="ADMITTED":
                    selected.append(result);rec.update(result)
                elif result is not None:
                    dump(ROOT/"rejected"/(repo.replace("/","_")+"_"+str(pr["number"])+".json"),result)
                    rec["native_summary"]={k:{"status":v["status"],"returncode":v.get("returncode"),"counts":dict(collections.Counter(v["tests"].values()))} for k,v in result.items()}
                attempts.append(rec);persist()
                print("ADMISSION",repo,pr["number"],status,flush=True)
                if status=="ADMITTED":break
            except Exception as exc:
                rec["status"]="UNKNOWN_ADMISSION_EXCEPTION";rec["error"]=type(exc).__name__
                # Error text can include upstream source paths; no credentials or auth headers.
                rec["detail"]=str(exc)[:350]
                attempts.append(rec);persist();print("ADMISSION",repo,pr["number"],rec["status"],rec["error"],flush=True)
        if not candidates:
            attempts.append({"repo":repo,"status":"NO_ELIGIBLE_MERGED_TITLE"});persist()
    print("ADMITTED_REAL_NATIVE_CASES",json.dumps(selected,sort_keys=True),flush=True)
    print("ADMISSION_COUNTS",SHARD,len(selected),dict(collections.Counter(a["status"] for a in attempts)),flush=True)
if __name__=="__main__":main()
