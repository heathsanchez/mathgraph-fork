"""P6's small evidence-bound method selector and pre-repair probe verifier."""
import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import uuid

HERE = Path(__file__).resolve().parent
LEGACY = HERE.parent / 'applicability_transfer'
sys.path.insert(0, str(LEGACY))
import native
import trial as legacy
native.HERE = HERE
native.IMAGE = 'mathgraph-p6-native:20261128'
_native_test = native.native_test


def timed_native(*args, **kwargs):
    if os.environ.get('OPENAI_API_KEY'):
        raise RuntimeError('native host must not have the model credential')
    started = time.monotonic()
    result = _native_test(*args, **kwargs)
    return {**result, 'native_event_id': uuid.uuid4().hex,
            'elapsed_seconds': time.monotonic() - started}


native.native_test = timed_native

ARMS = ('engine', 'memory', 'removal', 'cold')
MODEL = legacy.MODEL
dump, load, stable, digest = native.dump, native.load, native.stable, native.digest


def check_probe(code):
    if not isinstance(code, str) or not 1 <= len(code) <= 12000 or len(code.splitlines()) > 200:
        raise ValueError('probe size')
    tree = ast.parse(code)
    banned = legacy.BANNED - {'pytest', 'unittest'}
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    names |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    if names & banned or any(n.startswith('__') for n in names):
        raise ValueError('probe privileged reference')
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            modules = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or '']
            if getattr(node, 'level', 0) or any(m.split('.')[0] in banned for m in modules):
                raise ValueError('probe privileged import')
    if not any(isinstance(n, ast.FunctionDef) and n.name.startswith('test_') for n in tree.body):
        raise ValueError('probe needs pytest tests')
    if not any(isinstance(n, ast.Assert) for n in ast.walk(tree)):
        raise ValueError('probe needs an explicit assertion')
    return code


def qualify_method(parsed, packet, support):
    try:
        if not isinstance(parsed, dict) or set(parsed) != {'guidance', 'probe_recipe', 'guard'}:
            raise ValueError('method fields')
        for key in ('guidance', 'probe_recipe'):
            if not isinstance(parsed[key], str) or not 1 <= len(parsed[key]) <= 1800:
                raise ValueError('method text size')
        g = legacy.validate_guard(parsed['guard'])
        fs = legacy.features(packet)
        if not any(legacy.holds(g, f) for f in fs):
            raise ValueError('method no evidence match')
        if any(legacy.holds(g, {**f, 'failed_hits': 0}) for f in fs):
            raise ValueError('method withdrawal')
    except (ValueError, TypeError, KeyError) as exc:
        return {'status': 'REJECTED_METHOD', 'error': str(exc)}
    return {'status': 'FINITE_QUALIFIED', 'method': parsed, 'support': support,
            'id': stable({'method': parsed, 'support': support}),
            'boundary': 'Finite structural applicability; semantic generalization UNKNOWN.'}


def available(registry, evidence):
    return [m for m in registry if m.get('status') == 'FINITE_QUALIFIED'
            and all(evidence.get(k) == v for k, v in m['support'].items())]


def selected_methods(arm, packet, registry, evidence):
    methods = available(registry, evidence)
    if arm == 'cold':
        return []
    if arm == 'memory':
        return methods
    fs = legacy.features(packet)
    selected = [m for m in methods if any(legacy.holds(m['method']['guard'], f) for f in fs)]
    if arm == 'removal' and selected:
        selected = selected[:-1]
    return selected


def context(arm, packet, registry, evidence, history):
    result = {'task': packet}
    if arm != 'cold' and history:
        result['completed_history'] = history
    methods = selected_methods(arm, packet, registry, evidence)
    if methods:
        result['available_methods'] = methods
    # No arm label or absent/inactive guidance text. Identical inputs share a draw.
    return result


def compact(value):
    if isinstance(value, list):
        return [compact(v) for v in value]
    if not isinstance(value, dict):
        return value
    out = {}
    for k, v in value.items():
        if k in ('prompt', 'trace', 'source', 'probe_code'):
            out[k + '_sha256'] = stable(v)
        elif k == 'tests':
            from collections import Counter
            out['test_counts'] = dict(Counter(v.values()))
            out['nonpassing_tests'] = {a: b for a, b in v.items() if b != 'pass'}
            out['test_roster_sha256'] = stable(v)
        elif k == 'diagnostic':
            out[k] = v[-5000:]
        else:
            out[k] = compact(v)
    return out


def public_packet(packet):
    return {k: v for k, v in packet.items() if k not in ('tests', 'test_excerpt')}


def payload(call):
    x = call.get('parsed')
    return x if isinstance(x, dict) else {}


def choose_candidate(first, second):
    """Keep previously earned author-test evidence when a later attempt regresses."""
    rows = [(roundno, row) for roundno, row in ((1, first), (2, second)) if row]
    if not rows:
        return 0, {'status': 'UNKNOWN_NO_CANDIDATE', 'author_verified': False, 'probe_verified': False}
    return max(rows, key=lambda pair: (bool(pair[1].get('author_verified')),
                                      bool(pair[1].get('probe_verified')), pair[0]))


def probe_prompt(ctx):
    return (
        'Investigate a real Python regression. Before proposing any repair, design independent semantic '
        'boundary checks from the requirement, original source and observed baseline failure. '
        'Do not simply duplicate the visible assertion. Exercise nearby valid inputs and plausible incomplete '
        'repairs. Available methods are advisory; freely choose, adapt, reconstruct or ignore them. '
        'Return ONLY JSON {"reason":"brief rationale","probe_code":"complete pytest module"}. '
        'Use ordinary imports of the target package and pytest, <=200 lines, <=12000 characters. '
        'Include test_ functions and explicit assert statements. No file reads, process/network access, '
        'introspection, hidden author tests or package source inspection. No mocks of the implementation. '
        'Some checks may fail on the original buggy source. The probe is frozen before repair.\n'
        + json.dumps(ctx, sort_keys=True)
    )


def repair_prompt(ctx, probe, probe_baseline, previous):
    return (legacy.contract() + '\nUse the task requirement, source and execution evidence. '
            'Available methods are advisory; freely choose, adapt, reconstruct or ignore them. '
            'Preserve semantic boundaries as well as original passing cases. The semantic probe is frozen; '
            'if a probe appears wrong, explain rather than changing tests. No author correction is supplied.\n'
            + json.dumps({'context': ctx, 'frozen_probe': probe, 'probe_baseline': compact(probe_baseline),
                          'own_previous_attempt': compact(previous)}, sort_keys=True))


def learn_prompt(history, packet):
    return (
        'From completed real investigations and verification, construct ONE reusable investigation method. '
        'Future tasks are withheld. Return ONLY JSON {"guidance":"<=1800 characters",'
        '"probe_recipe":"<=1800 characters describing how to generate semantic checks before a repair",'
        '"guard":{"all":[{"feature":"failed_hits","op":"gt","value":0}]}}. '
        'The guard has 1-4 unique feature atoms; features ' + str(legacy.FEATURES) +
        '; operators ' + str(legacy.OPS) + '; integer values 0..10000. Include failed_hits>0 or >=1. '
        'It must match at least one preceding failure-covered function and become inactive at zero failing coverage. '
        'Learn from failures and incorrect probes. Do not include repository names, paths, identifiers, '
        'test names, literal source or case-specific constants. This is an advisory method, not a proof.\n'
        + json.dumps({'completed_history': history, 'preceding_function_features': legacy.features(packet)}, sort_keys=True)
    )
