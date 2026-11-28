"""Post-outcome diagnostics only: no new inference and no primary rescoring."""
import collections
import json
from pathlib import Path
import tempfile
from core import HERE, native, load, dump, digest, stable
from run import unpack

OBSERVER_PROBE = '''from datetime import datetime, timedelta
from cachetools import TTLCache

class Timer:
    def __init__(self, value):
        self.value = value
    def __call__(self):
        return self.value

def fresh():
    tick = timedelta(microseconds=1)
    timer = Timer(datetime.max - tick)
    cache = TTLCache(maxsize=1, ttl=tick, timer=timer)
    cache["edge"] = 42
    assert cache["edge"] == 42
    timer.value = datetime.max
    assert cache.get("edge") is None
    return cache

def test_direct_expire_reports_entry():
    cache = fresh()
    assert cache.expire() == [("edge", 42)]

def test_list_then_expire_has_already_removed_entry():
    cache = fresh()
    assert list(cache) == []
    assert cache.expire() == []

def test_comprehension_then_expire_still_reports_entry():
    cache = fresh()
    assert [key for key in cache] == []
    assert cache.expire() == [("edge", 42)]
'''


def main():
    native.build()
    data, work = HERE / 'data', HERE / 'work'
    out = HERE / 'post_audit'
    out.mkdir(exist_ok=True)
    episode = load(work / 'episode-03' / 'episode.json')
    sources = {'base': None, 'author': (data / 'private/task-03/author_source.txt').read_text()}
    sources.update({arm: r.get('candidate_source') for arm, r in episode['final'].items()})
    results, cache = {}, {}
    for name, source in sources.items():
        with tempfile.TemporaryDirectory(prefix='p6-full-sql-') as d:
            root, authority = unpack('task-03', d)
            path = root / authority['source_path']
            if source is not None:
                path.write_text(source)
            h = digest(path)
            if h not in cache:
                cache[h] = native.native_test(root, 'tests', authority['source_path'], timeout=180)
            results[name] = {'source_sha256': h, 'native': cache[h]}
            dump(out / 'sql_full_suite.json', results)
            print('POST_SQL_FULL', name, cache[h]['status'], dict(collections.Counter(cache[h]['tests'].values())), flush=True)
    observers = {}
    for name in ('base', 'author'):
        with tempfile.TemporaryDirectory(prefix='p6-cache-observer-') as d:
            root, authority = unpack('task-02', d)
            if name == 'author':
                (root / authority['source_path']).write_bytes((data / 'private/task-02/author_source.txt').read_bytes())
            probe = root / 'test_mathgraph_observer_audit.py'
            probe.write_text(OBSERVER_PROBE)
            observers[name] = {'source_sha256': digest(root / authority['source_path']),
                               'native': native.native_test(root, probe.name, authority['source_path'], timeout=100)}
    dump(out / 'cache_observation.json', {'probe_code': OBSERVER_PROBE, 'results': observers})
    summary = {'status': 'POST_OUTCOME_DIAGNOSTIC', 'primary_run': 46106707860,
               'sql': {k: {'status': r['native']['status'], 'returncode': r['native'].get('returncode'),
                           'counts': dict(collections.Counter(r['native']['tests'].values())),
                           'nonpassing': {a: b for a, b in r['native']['tests'].items() if b != 'pass'}}
                       for k, r in results.items()},
               'cache': {k: {'status': r['native']['status'], 'returncode': r['native'].get('returncode'),
                             'tests': r['native']['tests']} for k, r in observers.items()},
               'scope': 'No model calls. Full source-author test-suite expansion and causal observer controls; frozen P6 scores unchanged.'}
    dump(out / 'summary.json', summary)
    print('P6_POST_AUDIT', json.dumps(summary, sort_keys=True), flush=True)


if __name__ == '__main__':
    main()
