"""Alternating credentialed inference and token-free native execution steps."""
import collections
import concurrent.futures
import copy
import json
import os
from pathlib import Path
import shutil
import sys
import tarfile
import tempfile
import time
import zipfile
from core import (HERE, ARMS, MODEL, native, legacy, dump, load, stable, digest,
                  check_probe, qualify_method, selected_methods, context,
                  compact, public_packet, payload, choose_candidate, probe_prompt, repair_prompt, learn_prompt)

DATA = HERE / 'data'
WORK = HERE / 'work'


def state():
    path = WORK / 'state.json'
    return load(path) if path.exists() else {'history': [], 'registry': [], 'evidence': {}}


def tasks():
    return load(DATA / 'admission.json')['selected']


def packet(index):
    if len(tasks()) < 3 or index >= len(tasks()):
        return None
    row = tasks()[index]
    path = DATA / 'public' / 'future' / (row['id'] + '.json')
    if digest(path) != row['public_sha256']:
        raise ValueError('public task integrity')
    return load(path)


def batch_calls(prompts, limit):
    """Identical input shares a draw; distinct arms execute independently."""
    unique = {}
    for arm, prompt in prompts.items():
        unique.setdefault(stable(prompt), {'prompt': prompt, 'arms': []})['arms'].append(arm)
    def invoke(item):
        key, row = item
        result = legacy.call(row['prompt'], limit)
        return key, {'call': result, 'shared_arms': row['arms'], 'shared_draw': len(row['arms']) > 1}
    records = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        for key, row in executor.map(invoke, unique.items()):
            for arm in row['shared_arms']:
                records[arm] = {**row, 'draw_id': key}
    return records


def episode_dir(index):
    path = WORK / f'episode-{index + 1:02d}'
    path.mkdir(parents=True, exist_ok=True)
    return path


def contexts(index, p):
    s = state()
    return {arm: context(arm, public_packet(p), s['registry'], s['evidence'], s['history']) for arm in ARMS}


def propose_probes(index):
    p = packet(index)
    if p is None:
        return
    ctxs = contexts(index, p)
    order = ARMS[index % 4:] + ARMS[:index % 4]
    prompts = {arm: probe_prompt(ctxs[arm]) for arm in order}
    records = batch_calls(prompts, 2400)
    dump(episode_dir(index) / 'probe_proposals.json', records)
    dump(episode_dir(index) / 'method_selection.json', {
        arm: [m['id'] for m in selected_methods(arm, p, state()['registry'], state()['evidence'])]
        for arm in ARMS})
    print('P6_PROBES_FROZEN', index + 1, len({x['draw_id'] for x in records.values()}), flush=True)


def unpack(cid, directory):
    private = DATA / 'private' / cid
    a = load(private / 'authority.json')
    if digest(private / 'base.tar.gz') != a['overlay_archive_sha256']:
        raise ValueError('source archive integrity')
    with tarfile.open(private / 'base.tar.gz', 'r:gz') as tf:
        tf.extractall(directory, filter='data')
    root = Path(directory) / 'base'
    if digest(root / a['source_path']) != a['source_sha256'] or digest(root / a['test_path']) != a['test_sha256']:
        raise ValueError('source or authority mismatch')
    return root, a


def native_probe(root, a, code):
    try:
        check_probe(code)
    except (ValueError, SyntaxError, TypeError) as exc:
        return {'status': 'REJECTED_PROBE_SCOPE', 'error': str(exc), 'tests': {}}
    path = root / 'test_mathgraph_semantic_probe.py'
    if path.exists():
        raise ValueError('probe file collision')
    path.write_text(code)
    try:
        result = native.native_test(root, path.name, a['source_path'], timeout=100)
        if result['status'] == 'EXECUTED' and not any(t.get('lines') for t in result.get('trace', {}).values()):
            result['status'] = 'UNKNOWN_PROBE_DID_NOT_EXECUTE_TARGET'
        return result
    finally:
        path.unlink()


def probes_baseline(index):
    p = packet(index)
    if p is None:
        return
    native.build()
    rows = load(episode_dir(index) / 'probe_proposals.json')
    out, cache = {}, {}
    for arm, row in rows.items():
        code = payload(row['call']).get('probe_code')
        key = stable(code)
        if key not in cache:
            with tempfile.TemporaryDirectory(prefix='p6-probe-base-') as d:
                root, a = unpack(p['id'], d)
                cache[key] = native_probe(root, a, code)
        out[arm] = cache[key]
    dump(episode_dir(index) / 'probe_baseline.json', out)
    print('P6_PROBES_BASELINE', index + 1, {a: r['status'] for a, r in out.items()}, flush=True)


def propose_repairs(index, roundno):
    p = packet(index)
    if p is None:
        return
    folder = episode_dir(index)
    probes, baselines = load(folder / 'probe_proposals.json'), load(folder / 'probe_baseline.json')
    previous = load(folder / 'native_1.json') if roundno == 2 else {}
    ctxs = contexts(index, p)
    order = ARMS[index % 4:] + ARMS[:index % 4]
    prompts = {}
    for arm in order:
        prior = previous.get(arm)
        if prior and prior['author_verified'] and prior['probe_verified']:
            continue
        # API records have no author correction or complete test file.
        prompts[arm] = repair_prompt(ctxs[arm], probes[arm]['call'].get('parsed'), baselines[arm], prior)
    rows = batch_calls(prompts, 2400)
    dump(folder / f'repair_proposals_{roundno}.json', rows)
    print('P6_REPAIR_PROPOSALS', index + 1, roundno, len({x['draw_id'] for x in rows.values()}), flush=True)


def verify_candidate(cid, call, probe_code):
    parsed = call.get('parsed')
    result = {'author_verified': False, 'probe_verified': False}
    if not isinstance(parsed, dict) or parsed.get('decision') != 'PATCH':
        return {**result, 'status': 'ABSTAIN' if isinstance(parsed, dict) and parsed.get('decision') == 'ABSTAIN' else 'UNKNOWN_NO_VALID_PATCH'}
    with tempfile.TemporaryDirectory(prefix='p6-native-') as d:
        root, a = unpack(cid, d)
        source = root / a['source_path']
        try:
            candidate = legacy.patch(source.read_text(), parsed.get('edits'))
        except (ValueError, SyntaxError, TypeError) as exc:
            return {**result, 'status': 'REJECTED_PATCH_SCOPE', 'error': str(exc)}
        source.write_text(candidate)
        started = time.monotonic()
        author = native.native_test(root, a['test_path'], a['source_path'], timeout=100)
        probe = native_probe(root, a, probe_code)
        if digest(root / a['test_path']) != a['test_sha256']:
            raise ValueError('author tests changed')
        av = native.repair_green(a['native']['base'], author)
        pv = probe.get('status') == 'EXECUTED' and probe.get('returncode') == 0 and bool(probe.get('tests'))
        return {**result, 'status': 'WARRANTED_AUTHOR_TEST_SCOPE' if av else 'REJECTED_OR_UNKNOWN',
                'author_verified': av, 'probe_verified': pv, 'candidate_sha256': digest(source),
                'candidate_source': candidate, 'author_native': author, 'probe_native': probe,
                'native_elapsed_seconds': time.monotonic() - started}


def verify_repairs(index, roundno):
    p = packet(index)
    if p is None:
        return
    folder = episode_dir(index)
    proposals = load(folder / f'repair_proposals_{roundno}.json')
    probes = load(folder / 'probe_proposals.json')
    out, cache = {}, {}
    for arm, row in proposals.items():
        code = payload(probes[arm]['call']).get('probe_code')
        key = stable({'proposal': row['call'].get('parsed'), 'probe': code})
        if key not in cache:
            cache[key] = verify_candidate(p['id'], row['call'], code)
        out[arm] = cache[key]
        print('P6_NATIVE', index + 1, roundno, arm, out[arm]['author_verified'], out[arm]['probe_verified'], flush=True)
    dump(folder / f'native_{roundno}.json', out)


def close_episode(index):
    p = packet(index)
    if p is None:
        return
    folder = episode_dir(index)
    first, second = load(folder / 'native_1.json'), load(folder / 'native_2.json')
    choices = {arm: choose_candidate(first.get(arm), second.get(arm)) for arm in ARMS}
    final = {arm: choices[arm][1] for arm in ARMS}
    probes = load(folder / 'probe_proposals.json')
    # This specificity test happens only AFTER every proposal is frozen.
    specificity, cache = {}, {}
    for arm in ARMS:
        code = payload(probes[arm]['call']).get('probe_code')
        key = stable(code)
        if key not in cache:
            with tempfile.TemporaryDirectory(prefix='p6-author-probe-') as d:
                root, a = unpack(p['id'], d)
                src = DATA / 'private' / p['id'] / 'author_source.txt'
                if digest(src) != a['author_source_sha256']:
                    raise ValueError('author source changed')
                (root / a['source_path']).write_bytes(src.read_bytes())
                cache[key] = native_probe(root, a, code)
        specificity[arm] = cache[key]
    dump(folder / 'author_probe_specificity.json', specificity)
    crosschecks = []
    for candidate_arm in ARMS:
        candidate = final[candidate_arm].get('candidate_source')
        if not candidate:
            continue
        for probe_arm in ARMS:
            code = payload(probes[probe_arm]['call']).get('probe_code')
            key = stable({'candidate': candidate, 'probe': code})
            if key not in cache:
                with tempfile.TemporaryDirectory(prefix='p6-crosscheck-') as d:
                    root, a = unpack(p['id'], d)
                    (root / a['source_path']).write_text(candidate)
                    cache[key] = native_probe(root, a, code)
            crosschecks.append({'candidate_arm': candidate_arm, 'probe_arm': probe_arm,
                                'author_verified': final[candidate_arm].get('author_verified'),
                                'native': cache[key]})
    dump(folder / 'candidate_probe_crosschecks.json', crosschecks)
    summary = {'id': p['id'], 'requirement': p['requirement'], 'source_sha256': p['source_sha256'],
               'selected_round': {arm: choices[arm][0] for arm in ARMS},
               'attempts': {'1': first, '2': second},
               'final': final, 'probe_specificity': specificity,
               'probe_baseline': load(folder / 'probe_baseline.json'),
               'frozen_probes': {a: probes[a]['call'].get('parsed') for a in ARMS}}
    dump(folder / 'episode.json', summary)
    s = state()
    # Candidate source is not needed in later contexts; source-bound hashes retain it.
    history = compact(summary)
    def hide_candidate_sources(v):
        if isinstance(v, list):
            for x in v: hide_candidate_sources(x)
        elif isinstance(v, dict):
            if 'candidate_source' in v:
                v['candidate_source_sha256'] = stable(v.pop('candidate_source'))
            for x in v.values(): hide_candidate_sources(x)
    hide_candidate_sources(history)
    s['history'].append(history)
    s['evidence'][p['id']] = stable(summary)
    dump(WORK / 'state.json', s)
    print('P6_EPISODE_CLOSED', index + 1, {a: final[a].get('author_verified', False) for a in ARMS}, flush=True)


def learn(index):
    p = packet(index)
    if p is None or index >= len(tasks()) - 1:
        return
    s = state()
    record = legacy.call(learn_prompt(s['history'], p), 1800)
    dump(episode_dir(index) / 'learning.json', record)
    # Qualification itself has no API execution and does not see future source.
    method = qualify_method(record.get('parsed'), p, dict(s['evidence']))
    s['registry'].append(method)
    dump(WORK / 'state.json', s)
    print('P6_METHOD', index + 1, method['status'], flush=True)


def final():
    WORK.mkdir(exist_ok=True)
    s = state()
    rows = [load(p) for p in sorted(WORK.glob('episode-*/episode.json'))]
    scores = {arm: {'author_test_successes': 0, 'author_and_probe_successes': 0,
                    'probe_rejects_author': 0, 'probe_specificity_unknown': 0} for arm in ARMS}
    for row in rows:
        for arm in ARMS:
            f = row['final'][arm]
            scores[arm]['author_test_successes'] += bool(f.get('author_verified'))
            scores[arm]['author_and_probe_successes'] += bool(f.get('author_verified') and f.get('probe_verified'))
            sp = row['probe_specificity'][arm]
            scores[arm]['probe_rejects_author'] += sp.get('status') == 'EXECUTED' and sp.get('returncode') == 1 and any(v == 'failure' for v in sp.get('tests', {}).values())
            scores[arm]['probe_specificity_unknown'] += sp.get('status') != 'EXECUTED' or sp.get('returncode') not in (0, 1) or not bool(sp.get('tests')) or any(v == 'error' for v in sp.get('tests', {}).values())
    draws = {}
    perarm = {a: {'nominal_calls': 0, 'allocated_calls': 0.0, 'allocated_input_tokens': 0.0,
                   'allocated_output_tokens': 0.0} for a in ARMS}
    for path in WORK.glob('episode-*/*proposals*.json'):
        for arm, row in load(path).items():
            draws.setdefault(row['draw_id'], row['call'])
            share = len(row['shared_arms'])
            perarm[arm]['nominal_calls'] += 1
            perarm[arm]['allocated_calls'] += 1 / share
            for k in ('input_tokens', 'output_tokens'):
                perarm[arm]['allocated_' + k] += (row['call'].get('usage') or {}).get(k, 0) / share
    learning = [load(p) for p in WORK.glob('episode-*/learning.json')]
    allcalls = list(draws.values()) + learning
    events = {}
    def collect(value):
        if isinstance(value, list):
            for v in value: collect(v)
        elif isinstance(value, dict):
            if 'native_event_id' in value: events[value['native_event_id']] = value['elapsed_seconds']
            for v in value.values(): collect(v)
    for root in (DATA, WORK):
        for path in root.rglob('*.json'): collect(load(path))
    cost = {'distinct_task_calls': len(draws), 'common_learning_calls': len(learning), 'per_arm_allocated': perarm,
            'physical_native_executions': len(events), 'physical_native_seconds': sum(events.values()),
            'actual_input_tokens': sum((c.get('usage') or {}).get('input_tokens', 0) for c in allcalls),
            'actual_output_tokens': sum((c.get('usage') or {}).get('output_tokens', 0) for c in allcalls),
            'sum_model_latency_seconds': sum(c.get('elapsed_seconds', 0) for c in allcalls),
            'acquisition_seconds': load(DATA / 'admission.json')['elapsed_seconds']}
    engine, memory = (scores[a]['author_test_successes'] for a in ('engine', 'memory'))
    result = {'status': 'COMPLETE_BOUNDED' if len(rows) == len(tasks()) and len(rows) >= 3 else 'UNKNOWN_INCOMPLETE',
              'model': MODEL, 'episodes': len(rows), 'scores': scores, 'cost': cost,
              'comparison': 'TIE' if engine == memory else 'CANDIDATE_ENGINE_GAIN' if engine > memory else 'ENGINE_LOWER',
              'qualified_methods': sum(m['status'] == 'FINITE_QUALIFIED' for m in s['registry']),
              'boundaries': ['Published tasks; pretraining exposure unknown', 'One stochastic trial; shared identical prompts are one draw',
                             'Native authority is the fixed author-test module', 'No general self-improvement or economic superiority established']}
    dump(WORK / 'summary.json', result)
    evidence = HERE / 'evidence'
    evidence.mkdir(exist_ok=True)
    package = evidence / 'sequential_transfer'
    package.mkdir(exist_ok=True)
    # Full data retained in the data artifact. Portable evidence keeps exact source,
    # proposals and verdicts; large traces are replaced by hashes.
    for root in (DATA, WORK):
        for path in root.rglob('*.json'):
            x = load(path)
            def trim(v):
                if isinstance(v, list): return [trim(a) for a in v]
                if not isinstance(v, dict): return v
                return {k: trim(a) for k, a in v.items() if k != 'trace'} | ({'trace_sha256': stable(v['trace'])} if 'trace' in v else {})
            dump(package / root.name / path.relative_to(root), trim(x))
    for path in (DATA / 'private').rglob('*'):
        if path.is_file() and path.suffix != '.json':
            dest = package / 'data' / 'private' / path.relative_to(DATA / 'private')
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)
    for path in HERE.glob('*.py'):
        shutil.copy2(path, package / path.name)
    for name in ('PROTOCOL.md', 'Dockerfile', 'trace_plugin.py'):
        shutil.copy2(HERE / name, package / name)
    prior = evidence / 'applicability_transfer'
    prior.mkdir(exist_ok=True)
    for path in (HERE.parent / 'applicability_transfer').glob('*.py'):
        shutil.copy2(path, prior / path.name)
    (evidence / 'README.md').write_text('# P6 native research trial\n\nRead sequential_transfer/PROTOCOL.md and sequential_transfer/work/summary.json.\n'
        'With Docker installed, run `python3 sequential_transfer/replay.py` for credential-free native replay.\n'
        'Recorded inference, negative outcomes and sources are included. No API key is needed for replay.\n')
    dump(evidence / 'MANIFEST.json', {str(p.relative_to(evidence)): digest(p) for p in sorted(evidence.rglob('*')) if p.is_file()})
    with zipfile.ZipFile(HERE / 'evidence.zip', 'w', compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(evidence.rglob('*')):
            if p.is_file(): z.write(p, p.relative_to(evidence))
    print('P6_SUMMARY', json.dumps(result, sort_keys=True), flush=True)
    print('P6_EVIDENCE_SHA256', digest(HERE / 'evidence.zip'), flush=True)


if __name__ == '__main__':
    command = sys.argv[1]
    index = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    if command == 'probes': propose_probes(index)
    elif command == 'probe_native': probes_baseline(index)
    elif command == 'repair1': propose_repairs(index, 1)
    elif command == 'repair2': propose_repairs(index, 2)
    elif command == 'native1': verify_repairs(index, 1)
    elif command == 'native2': verify_repairs(index, 2)
    elif command == 'close': close_episode(index)
    elif command == 'learn': learn(index)
    elif command == 'final': final()
    else: raise ValueError('unknown stage')
