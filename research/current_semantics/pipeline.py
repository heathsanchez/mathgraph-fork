"""P7: current-source audit -> acquired checker -> reuse -> saved repair."""
import collections
import difflib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
import zipfile
from base import HERE, DATA, WORK, source, dump, load, digest, stable, build, native, skill_scope, apply_edits

MODELS = ('gpt-6.2-sol', 'gpt-6.1-sol', 'gpt-5.6-sol')
PATHS = {'patch': ('jsonpatch.py',), 'fast': ('fastjsonschema/draft04.py', 'fastjsonschema/draft06.py',
                                         'fastjsonschema/draft07.py', 'fastjsonschema/generator.py')}
CONTRACT = ('Use JSON equality from RFC 6902 section 4.6 and JSON Schema Draft 7 core section 4.2.3. '
            'Boolean and number are distinct JSON types. Numeric representations compare by numeric value '
            '(1 equals 1.0). Arrays compare elementwise in order. Objects compare keys and recursively '
            'corresponding values, independently of member order. Null only equals null; strings compare '
            'codepoints. Inputs are finite JSON-decoded Python values with string object keys. '
            'Do not introduce type coercion, serialization spelling comparison, or fixed-point assumptions.')


def guard():
    freeze = load(DATA / 'freeze.json')
    if digest(HERE / 'PROTOCOL.md') != freeze['protocol_sha256'] or digest(DATA / 'corpus.json') != freeze['corpus_sha256']:
        raise ValueError('frozen protocol/corpus drift')
    for path, identity in freeze['file_manifest'].items():
        p = DATA / 'sources' / path
        if 'symlink' in identity:
            if not p.is_symlink() or str(p.readlink()) != identity['symlink']: raise ValueError('source symlink drift')
        elif not p.is_file() or p.is_symlink() or digest(p) != identity['sha256']:
            raise ValueError('frozen source/test data drift')
    for key, pin in freeze['pins'].items():
        for name, identity in pin['verified'].items():
            p = DATA / 'sources' / key / name
            if digest(p) != identity['sha256'] or source.gitblob(p) != identity['git_blob']:
                raise ValueError('pinned source drift')
    return freeze


def call(prompt, limit=4000, model=None):
    from openai import OpenAI
    if model is None: model = load(WORK / 'model.json')['selected']
    started = time.monotonic()
    rec = {'model': model, 'reasoning_effort': 'low', 'max_output_tokens': limit, 'prompt': prompt,
           'prompt_sha256': stable(prompt)}
    try:
        response = OpenAI(api_key=os.environ['OPENAI_API_KEY'], timeout=150, max_retries=0).responses.create(
            model=model, input=prompt, reasoning={'effort': 'low'}, max_output_tokens=limit)
        rec.update(status='RETURNED', response=response.output_text, response_id=response.id,
                   actual_model=response.model, usage=response.usage.model_dump() if response.usage else None)
        try:
            text = response.output_text.strip()
            if text.startswith('```'): text = text[text.find('\n') + 1:text.rfind('```')]
            rec['parsed'] = json.loads(text)
        except ValueError: rec['parse_error'] = 'INVALID_JSON'
    except Exception as exc:
        rec.update(status='UNKNOWN_API_ERROR', error_type=type(exc).__name__, http_status=getattr(exc, 'status_code', None))
    rec['elapsed_seconds'] = time.monotonic() - started
    return rec


def model_selection():
    WORK.mkdir(exist_ok=True)
    attempts = []
    for model in MODELS:
        row = call('Return the text OK.', 32, model)
        attempts.append(row)
        dump(WORK / 'model.json', {'attempts': attempts, 'selected': model if row['status'] == 'RETURNED' else None})
        if row['status'] == 'RETURNED':
            print('P7_MODEL', model, flush=True)
            return
    raise RuntimeError('no transport-supported model')


def rows_of(result):
    return result.get('output', {}).get('rows', []) if result.get('status') == 'EXECUTED' and result.get('returncode') == 0 else []


def summarize(result):
    rows = rows_of(result)
    return {'status': result['status'], 'observations': len(rows),
            'mismatches': [r for r in rows if 'actual' in r and r['actual'] != r['expected']],
            'unknown': [r for r in rows if 'actual' not in r],
            'control_disagreements': [r for r in rows if 'conventional' in r and r['conventional'] != r['expected']]}


def suite_for(key):
    return ['.'] if key == 'patch' else ['-m', 'not benchmark', 'tests']


def initial():
    guard(); WORK.mkdir(exist_ok=True)
    dump(WORK / 'environment.json', build())
    corpus = load(DATA / 'corpus.json')
    result = native(DATA / 'sources/patch', {'task': 'patch', 'pairs': corpus['pairs']})
    dump(WORK / 'initial_patch_audit.json', result)
    summary = summarize(result)
    if summary['control_disagreements'] or not summary['observations']:
        raise RuntimeError('initial oracle did not qualify')
    for key in ('patch', 'fast'):
        suite = native(DATA / 'sources' / key, {}, suite=suite_for(key))
        dump(WORK / f'{key}_baseline_suite.json', suite)
        print('P7_PROJECT_BASELINE', key, suite['status'], dict(collections.Counter(suite.get('tests', {}).values())), flush=True)
    print('P7_INITIAL_DISCOVERY', json.dumps(summary), flush=True)


def learning(roundno):
    guard()
    corpus = load(DATA / 'corpus.json')
    first = summarize(load(WORK / 'initial_patch_audit.json'))
    context = {'contract': CONTRACT, 'exposed_pairs': corpus['pairs'][:4], 'observed_first_project_mismatches': first['mismatches'][:6]}
    if roundno == 2:
        qualification = load(WORK / 'qualification_1.json')
        if qualification['qualified']:
            dump(WORK / 'learning_2.json', {'status': 'SKIPPED_ALREADY_QUALIFIED'})
            return
        context['prior_program'] = load(WORK / 'learning_1.json').get('parsed')
        context['qualification_failure'] = qualification
    prompt = ('Construct a reusable executable checker from the supplied contract and first-project observations. '
              'Future source and expected answers are withheld. Return ONLY JSON {"source":"Python functions including equivalent(left, right)",'
              '"reason":"brief"}. Use only pure function definitions and builtins, no imports/decorators/default arguments, '
              'file/process/network operations or introspection. Return bool. Helper functions and recursion are allowed.\n' + json.dumps(context, sort_keys=True))
    dump(WORK / f'learning_{roundno}.json', call(prompt))


def qualify(roundno):
    guard()
    if roundno == 2 and (WORK / 'skill.json').exists(): return
    record = load(WORK / f'learning_{roundno}.json')
    parsed = record.get('parsed'); code = parsed.get('source') if isinstance(parsed, dict) else None
    try:
        skill_scope(code)
    except (ValueError, SyntaxError, TypeError) as exc:
        dump(WORK / f'qualification_{roundno}.json', {'qualified': False, 'status': 'REJECTED_SCOPE', 'error': str(exc)})
        return
    corpus = load(DATA / 'corpus.json')
    result = native(DATA / 'sources/patch', {'task': 'qualify', **corpus}, code)
    rows = rows_of(result)
    bad = [r for r in rows if r.get('learned_errors') or type(r.get('learned')) is not bool or r['learned'] != r['expected'] or r['conventional'] != r['expected']]
    qualified = len(rows) == len(corpus['pairs']) + len(corpus['external']) and not bad
    receipt = {'qualified': qualified, 'status': 'FINITE_QUALIFIED' if qualified else 'REJECTED_NATIVE',
               'source_sha256': stable(code), 'observations': len(rows), 'failures': bad, 'native': result}
    dump(WORK / f'qualification_{roundno}.json', receipt)
    if qualified:
        dump(WORK / 'skill.json', {'source': code, 'source_sha256': stable(code), 'qualification_sha256': stable(receipt),
                                  'qualification_round': roundno, 'corpus_sha256': digest(DATA / 'corpus.json'), 'contract': CONTRACT})
    print('P7_CHECKER_QUALIFICATION', roundno, qualified, len(rows), len(bad), flush=True)


def skill():
    row = load(WORK / 'skill.json')
    if stable(row['source']) != row['source_sha256'] or digest(DATA / 'corpus.json') != row['corpus_sha256']:
        raise ValueError('learned checker support drift')
    path = WORK / f'qualification_{row["qualification_round"]}.json'
    if not path.exists() or stable(load(path)) != row['qualification_sha256'] or not load(path)['qualified']:
        raise ValueError('learned checker qualification evidence withdrawn')
    skill_scope(row['source'])
    return row


def audits():
    guard()
    if not (WORK / 'skill.json').exists():
        dump(WORK / 'audit_status.json', {'status': 'UNKNOWN_UNQUALIFIED_CHECKER'})
        return
    code = skill()['source']; corpus = load(DATA / 'corpus.json')
    for key in ('patch', 'fast'):
        result = native(DATA / 'sources' / key, {'task': key, 'pairs': corpus['pairs']}, code)
        dump(WORK / f'{key}_audit.json', result)
        print('P7_CURRENT_AUDIT', key, json.dumps(summarize(result)), flush=True)
    # Actual execution with capability removed, then exact restoration. Removing
    # this engine's oracle yields UNKNOWN, not a proof of universal necessity.
    accepted = skill(); support_path = WORK / f'qualification_{accepted["qualification_round"]}.json'
    saved = support_path.read_bytes(); rejected = False
    try:
        support_path.unlink()
        try: skill()
        except ValueError: rejected = True
        if not rejected: raise AssertionError('withdrawn evidence still admitted')
        withdrawn = native(DATA / 'sources/fast', {'task': 'fast', 'pairs': corpus['pairs']})
    finally:
        support_path.write_bytes(saved)
    restored = native(DATA / 'sources/fast', {'task': 'fast', 'pairs': corpus['pairs']}, skill()['source'])
    original = rows_of(load(WORK / 'fast_audit.json'))
    assert all(r.get('learned') is None for r in rows_of(withdrawn))
    assert rows_of(restored) == original
    dump(WORK / 'withdraw_restore.json', {'withdrawn': withdrawn, 'restored': restored,
                                        'actual_missing_support_refused': rejected,
                                        'restored_rows_identical': True, 'withdrawn_claims': 'UNKNOWN'})


def originals(key):
    return {p: (DATA / 'sources' / key / p).read_text() for p in PATHS[key]}


def propose(roundno):
    guard(); out = {}
    if not (WORK / 'skill.json').exists():
        dump(WORK / f'proposals_{roundno}.json', out); return
    corpus = load(DATA / 'corpus.json'); pairmap = {r['id']: r for r in corpus['pairs']}
    previous = load(WORK / 'candidates_1.json') if roundno == 2 else {}
    for key in ('patch', 'fast'):
        summary = summarize(load(WORK / f'{key}_audit.json'))
        if not summary['mismatches'] or summary['control_disagreements'] or summary['unknown']: continue
        if roundno == 2 and previous.get(key, {}).get('qualified'): continue
        witnesses = [{**r, 'input_pair': pairmap[r['id']]} for r in summary['mismatches'][:8]]
        prompt = ('Repair the pinned current production implementation against its declared standard. '
                  'Return ONLY JSON {"decision":"PATCH"|"ABSTAIN","reason":"brief",'
                  '"edits":[{"path":"admitted file","replacements":[{"old":"unique ORIGINAL substring","new":"replacement"}]}]}. '
                  'At most 4 files, 6 nonoverlapping original-source replacements/file, 200 changed lines total. '
                  'No new imports, test introspection, process/network/file access. Original tests/expected answers cannot change. '
                  'Preserve positive numeric equivalence and all existing correct behavior. Second attempts edit ORIGINAL source afresh. '
                  'The acquired checker is finite-qualified advisory code; independent standard expectations remain authoritative.\n'
                  + json.dumps({'contract': CONTRACT, 'sources': originals(key), 'witnesses': witnesses,
                                'acquired_checker': skill()['source'],
                                'own_previous_attempt': previous.get(key) if roundno == 2 else None}, sort_keys=True))
        out[key] = call(prompt)
        dump(WORK / f'proposals_{roundno}.json', out)
    dump(WORK / f'proposals_{roundno}.json', out)


def verify_saved(key, record):
    parsed = record.get('parsed')
    if not isinstance(parsed, dict) or parsed.get('decision') != 'PATCH':
        return {'qualified': False, 'status': 'UNKNOWN_NO_PATCH'}
    original = originals(key)
    try: changed = apply_edits(original, parsed.get('edits'))
    except (ValueError, SyntaxError, TypeError) as exc:
        return {'qualified': False, 'status': 'REJECTED_SCOPE', 'error': str(exc)}
    with tempfile.TemporaryDirectory(prefix='p7-candidate-') as d:
        root = Path(d) / 'source'; shutil.copytree(DATA / 'sources' / key, root)
        diffs = {}
        for path, text in changed.items():
            (root / path).write_text(text)
            if text != original[path]: diffs[path] = ''.join(difflib.unified_diff(original[path].splitlines(True), text.splitlines(True), fromfile=path, tofile=path))
        corpus = load(DATA / 'corpus.json')
        audit = native(root, {'task': key, 'pairs': corpus['pairs']}, skill()['source'])
        suite = native(root, {}, suite=suite_for(key))
        baseline = load(WORK / f'{key}_baseline_suite.json')
        b, t = baseline.get('tests', {}), suite.get('tests', {})
        native_ok = (baseline['status'] == 'EXECUTED' and b and not any(v == 'error' for v in b.values())
                     and suite['status'] == 'EXECUTED' and suite.get('returncode') == 0 and set(b) == set(t)
                     and all(t[k] == ('skipped' if v == 'skipped' else 'pass') for k, v in b.items()))
        rows = rows_of(audit); original_rows = rows_of(load(WORK / f'{key}_audit.json'))
        audit_ok = len(rows) == len(original_rows) and bool(rows) and all('actual' in r and not r.get('learned_errors') and r['actual'] == r['expected'] == r['conventional'] == r['learned'] for r in rows)
        return {'qualified': bool(native_ok and audit_ok), 'status': 'WARRANTED_BOUNDED_REPAIR' if native_ok and audit_ok else 'REJECTED_OR_UNKNOWN',
                'sources': {p: s for p, s in changed.items() if s != original[p]}, 'source_sha256': {p: hashlib_text(s) for p, s in changed.items() if s != original[p]},
                'diffs': diffs, 'audit': audit, 'suite': suite, 'audit_ok': audit_ok, 'project_suite_ok': bool(native_ok)}


def hashlib_text(text):
    import hashlib
    return hashlib.sha256(text.encode()).hexdigest()


def verify(roundno):
    guard(); proposals = load(WORK / f'proposals_{roundno}.json'); out = {}
    for key, record in proposals.items():
        out[key] = verify_saved(key, record)
        dump(WORK / f'candidates_{roundno}.json', out)
        print('P7_CANDIDATE', key, roundno, out[key]['qualified'], out[key]['status'], flush=True)
    dump(WORK / f'candidates_{roundno}.json', out)


def final():
    guard(); selected = {}
    for roundno in (1, 2):
        for key, row in load(WORK / f'candidates_{roundno}.json').items():
            if key not in selected or row['qualified']:
                selected[key] = {'round': roundno, **row}
    dump(WORK / 'selected.json', selected)
    audits = {k: summarize(load(WORK / f'{k}_audit.json')) for k in ('patch', 'fast')} if (WORK / 'skill.json').exists() else {}
    calls = []
    model = load(WORK / 'model.json'); calls += model['attempts']
    for n in (1, 2):
        row = load(WORK / f'learning_{n}.json')
        if 'model' in row: calls.append(row)
        calls += list(load(WORK / f'proposals_{n}.json').values())
    summary = {'status': 'COMPLETED_BOUNDED', 'model': model['selected'], 'audits': audits,
               'qualified_repairs': {k: v['qualified'] for k, v in selected.items()},
               'model_calls': len(calls), 'input_tokens': sum((c.get('usage') or {}).get('input_tokens', 0) for c in calls),
               'output_tokens': sum((c.get('usage') or {}).get('output_tokens', 0) for c in calls),
               'boundary': 'Investigator-selected standards domain/current sources; finite checker and conventional parity, no general learning or economic superiority.'}
    dump(WORK / 'summary.json', summary)
    for key, row in selected.items():
        for path, diff in row.get('diffs', {}).items():
            dest = WORK / 'patches' / key / (path.replace('/', '_') + '.patch')
            dest.parent.mkdir(parents=True, exist_ok=True); dest.write_text(diff)
    print('P7_FINAL', json.dumps(summary), flush=True)


def replay():
    guard(); build(); corpus = load(DATA / 'corpus.json')
    qualifier = native(DATA / 'sources/patch', {'task': 'qualify', **corpus}, skill()['source'])
    assert len(rows_of(qualifier)) == len(corpus['pairs']) + len(corpus['external'])
    assert all(not r.get('learned_errors') and r['learned'] == r['expected'] == r['conventional'] for r in rows_of(qualifier))
    checked = []
    for key, old in load(WORK / 'selected.json').items():
        record = load(WORK / f'proposals_{old["round"]}.json')[key]
        new = verify_saved(key, record)
        assert new['qualified'] == old['qualified'] and new.get('source_sha256') == old.get('source_sha256')
        assert new.get('suite', {}).get('tests') == old.get('suite', {}).get('tests')
        assert rows_of(new.get('audit', {})) == rows_of(old.get('audit', {}))
        checked.append({'project': key, 'qualified': new['qualified']})
    dump(HERE / 'cold_replay.json', {'status': 'PASS', 'qualifier_rows': len(rows_of(qualifier)), 'candidates': checked,
                                     'scope': 'No new model calls; source/checker/audit/project-test outcomes replayed.'})


def bundle():
    files = {}
    for p in HERE.rglob('*'):
        if not p.is_file() or '__pycache__' in p.parts or p.name == 'evidence.zip': continue
        files['current_semantics/' + str(p.relative_to(HERE))] = p
    for p in (HERE.parent / 'applicability_transfer').glob('*.py'):
        files['applicability_transfer/' + p.name] = p
    manifest = {name: digest(p) for name, p in files.items()}
    with zipfile.ZipFile(HERE / 'evidence.zip', 'w', compression=zipfile.ZIP_DEFLATED) as z:
        for name, p in files.items(): z.write(p, name)
        z.writestr('MANIFEST.json', json.dumps(manifest, sort_keys=True, indent=2))
        z.writestr('README.md', 'Read current_semantics/PROTOCOL.md and work/summary.json. With Docker, run python3 current_semantics/pipeline.py replay. No key is needed for native replay.\n')
    print('P7_BUNDLE_SHA256', digest(HERE / 'evidence.zip'), flush=True)


if __name__ == '__main__':
    command = sys.argv[1]
    functions = {'initial': initial, 'model': model_selection, 'learn1': lambda: learning(1), 'learn2': lambda: learning(2),
                 'qualify1': lambda: qualify(1), 'qualify2': lambda: qualify(2), 'audits': audits,
                 'propose1': lambda: propose(1), 'propose2': lambda: propose(2), 'verify1': lambda: verify(1),
                 'verify2': lambda: verify(2), 'final': final, 'replay': replay, 'bundle': bundle}
    functions[command]()
