"""Credential-free native probe and maintainer-test worker."""
import contextlib, io, json, os, sys, traceback
from pathlib import Path
assert not any(os.environ.get(k) for k in ('OPENAI_API_KEY','GITHUB_TOKEN'))
sys.path.insert(0, '/target')
req=json.loads(Path('/request.json').read_text())
class Limited(io.StringIO):
    def write(self,s):
        remaining=12000-self.tell()
        if remaining>0:super().write(s[:remaining])
        return len(s)
stream=Limited(); result={}
with contextlib.redirect_stdout(stream),contextlib.redirect_stderr(stream):
    if req['mode']=='probe':
        try:
            exec(compile(req['source'],'<investigator-probe>','exec'),{'__name__':'__main__'})
            result={'status':'EXECUTED','returncode':0}
        except BaseException as e:
            traceback.print_exc();result={'status':'EXECUTED','returncode':1,'exception':type(e).__name__}
    else:
        import pytest
        class Record:
            def __init__(self):self.rows={}
            def pytest_runtest_logreport(self,report):
                self.rows.setdefault(report.nodeid,{})[report.when]=report.outcome
        plugin=Record()
        result={'status':'EXECUTED','returncode':int(pytest.main(['-q','-W','error','-p','no:cacheprovider','tests'],plugins=[plugin]))}
        result['rows']=plugin.rows
result['diagnostic']=stream.getvalue()
Path('/out/result.json').write_text(json.dumps(result,sort_keys=True))
