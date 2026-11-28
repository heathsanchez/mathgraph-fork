"""Trusted pytest spectrum collection; source is mounted read-only."""
import json
import os
import sys
from pathlib import Path
import pytest

TARGET=os.environ.get("NATIVE_SOURCE","")
ROWS={}
CURRENT={}
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    hits=set()
    old=sys.gettrace()
    def tracer(frame,event,arg):
        if frame.f_code.co_filename!=TARGET:
            return None
        if event=="line":
            hits.add(frame.f_lineno)
        return tracer
    try:
        sys.settrace(tracer)
        yield
    finally:
        sys.settrace(old)
        CURRENT[item.nodeid]=sorted(hits)
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item,call):
    result=yield
    report=result.get_result()
    if report.when=="call":
        ROWS[item.nodeid]={"outcome":report.outcome,"lines":CURRENT.get(item.nodeid,[])}
def pytest_sessionfinish(session,exitstatus):
    Path("/out/trace.json").write_text(json.dumps(ROWS,sort_keys=True))

