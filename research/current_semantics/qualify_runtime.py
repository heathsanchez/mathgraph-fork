"""Post-run native qualification. No inference, candidate edits or rescoring."""
import collections
import json
from pathlib import Path
from base import HERE, DATA, WORK, dump, load, digest, build, native
from pipeline import guard, skill, rows_of, suite_for


def attest(result, freeze):
    files = result.get('output', {}).get('control_runtime_files', {})
    if not files: raise ValueError('missing native control import attestation')
    for path, sha in files.items():
        if path.startswith('/control/'):
            key, relative = 'control', path[len('/control/'):]
        elif path.startswith('/pointer/'):
            key, relative = 'pointer', path[len('/pointer/'):]
        else:
            raise ValueError('control/dependency imported outside pinned source')
        if freeze['pins'][key]['verified'][relative]['sha256'] != sha:
            raise ValueError('native imported source hash mismatch')
    return files


def main():
    freeze = guard(); out = HERE / 'runtime_qualification'; out.mkdir(exist_ok=True)
    environment = build()
    if 'rpds-py==0.25.0' not in environment['packages'] or 'simplejson==3.20.1' not in environment['packages']:
        raise ValueError('declared dependency correction absent')
    dump(out / 'environment.json', environment)
    corpus = load(DATA / 'corpus.json'); code = skill()['source']
    q = native(DATA / 'sources/patch', {'task': 'qualify', **corpus}, code)
    attest(q, freeze)
    qr = rows_of(q)
    assert len(qr) == len(corpus['pairs']) + len(corpus['external'])
    assert all(not r.get('learned_errors') and r['learned'] == r['expected'] == r['conventional'] for r in qr)
    dump(out / 'checker_qualification.json', q)
    results = {}
    for key in ('patch', 'fast'):
        a = native(DATA / 'sources' / key, {'task': key, 'pairs': corpus['pairs']}, code)
        attest(a, freeze)
        assert rows_of(a) == rows_of(load(WORK / f'{key}_audit.json'))
        s = native(DATA / 'sources' / key, {}, suite=suite_for(key))
        results[key] = {'audit': a, 'suite': s}
        dump(out / f'{key}.json', results[key])
        print('P7_POST_PROJECT', key, s['status'], s.get('returncode'), dict(collections.Counter(s.get('tests', {}).values())), flush=True)
    summary = {'status': 'POST_RUN_NATIVE_QUALIFICATION', 'original_run': 46110032011,
               'model_calls': 0, 'checker_cases': len(qr),
               'audit_rows_identical': True,
               'project_tests': {k: {'status': r['suite']['status'], 'returncode': r['suite'].get('returncode'),
                                     'counts': dict(collections.Counter(r['suite'].get('tests', {}).values()))} for k, r in results.items()},
               'scope': 'Same frozen sources, generated checker and corpus. Adds declared test dependency, satisfies control rpds minimum, raises memory limit, attests actual imports. Original failures retained.'}
    dump(out / 'summary.json', summary)
    print('P7_POST_SUMMARY', json.dumps(summary, sort_keys=True), flush=True)
    if any(r['suite']['status'] != 'EXECUTED' or r['suite'].get('returncode') != 0 for r in results.values()):
        raise RuntimeError('project-wide gate remains unqualified; audit evidence retained separately')


if __name__ == '__main__': main()
