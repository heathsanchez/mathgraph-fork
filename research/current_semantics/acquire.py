"""Acquire current sources and freeze authority before observation/inference."""
import hashlib
import json
import math
from pathlib import Path
import shutil
import tempfile
import time
from base import HERE, DATA, source, dump, digest, stable

REPOS = {'patch': ('stefankoegl/python-json-patch', 'master'),
         'fast': ('horejsek/python-fastjsonschema', 'master'),
         'control': ('python-jsonschema/jsonschema', 'main'),
         'pointer': ('stefankoegl/python-json-pointer', 'master'),
         'official': ('json-schema-org/JSON-Schema-Test-Suite', 'main')}


def compatible(expression, version=7):
    """The official current suite's documented ordered compatibility algorithm."""
    if expression is None: return True
    result = True
    for item in expression.split(','):
        item = item.strip()
        op = '<=' if item.startswith('<=') else '=' if item.startswith('=') else ''
        release = int(item[len(op):])
        result = version <= release if op == '<=' else version == release if op == '=' else version >= release
        if version <= release: break
    return result


def main():
    started = time.monotonic(); (DATA / 'sources').mkdir(parents=True, exist_ok=True)
    pins = {}
    for key, (repo, ref) in REPOS.items():
        commit = source.api(repo, 'commits/' + ref)
        tree = source.api(repo, 'git/trees/' + commit['commit']['tree']['sha'] + '?recursive=1')
        if tree.get('truncated'): raise ValueError('truncated source tree')
        with tempfile.TemporaryDirectory(prefix='p7-source-') as d:
            root, archive_sha = source.safe_archive(repo, commit['sha'], Path(d) / 'archive')
            dest = DATA / 'sources' / key
            if dest.exists(): raise ValueError('source destination already exists')
            shutil.copytree(root, dest)
        verified = {}
        for row in tree['tree']:
            path = dest / row['path']
            if row['type'] == 'blob' and (row['path'].endswith('.py') or row['path'] in ('README.md', 'README.rst', 'tox.ini', 'pytest.ini')):
                if not path.is_file() or path.is_symlink(): raise ValueError('missing source blob')
                if source.gitblob(path) != row['sha']: raise ValueError('source blob identity')
                verified[row['path']] = {'git_blob': row['sha'], 'sha256': digest(path)}
        pins[key] = {'repo': repo, 'ref': ref, 'sha': commit['sha'], 'tree': commit['commit']['tree']['sha'],
                     'archive_sha256': archive_sha, 'verified': verified}
        if key == 'fast':
            link = next(r for r in tree['tree'] if r['path'] == 'JSON-Schema-Test-Suite' and r['type'] == 'commit')
            sub = dest / link['path']
            if sub.exists(): sub.unlink() if sub.is_file() else shutil.rmtree(sub)
            with tempfile.TemporaryDirectory(prefix='p7-submodule-') as d:
                root, ash = source.safe_archive('json-schema-org/JSON-Schema-Test-Suite', link['sha'], Path(d) / 'archive')
                shutil.copytree(root, sub)
            pins[key]['submodule'] = {'sha': link['sha'], 'archive_sha256': ash}
        dump(DATA / 'acquisition_progress.json', {'pins': pins, 'completed_source': key,
                                                 'elapsed_seconds': time.monotonic() - started})
    # Independently specified literal expectations. Derived wrappers retain the
    # same equality under the declared recursive JSON rules; they are correlated.
    literals = [(True, 1, False), (False, 0, False), (1, 1.0, True), (0, -0.0, True),
                (True, True, True), (False, False, True), (None, None, True), (None, False, False),
                ('1', 1, False), ('true', True, False), ([], {}, False), ('é', 'e\u0301', False),
                ('é', '\u00e9', True), ([1, 2], [2, 1], False), ({'a': 1, 'b': 2}, {'b': 2.0, 'a': 1.0}, True),
                ({'a': True}, {'a': 1}, False), ([False], [0], False), ([1, {'x': True}], [1.0, {'x': True}], True),
                ({'x': [False, 2]}, {'x': [0, 2]}, False), ({'x': []}, {}, False)]
    pairs = []
    for i, (a, b, expected) in enumerate(literals):
        for reverse in (False, True):
            left, right = (b, a) if reverse else (a, b)
            for depth in range(4):
                for kind in ('array', 'object'):
                    x, y = left, right
                    for _ in range(depth): x, y = ([x], [y]) if kind == 'array' else ({'v': x}, {'v': y})
                    pairs.append({'id': f'literal-{i:02d}-{int(reverse)}-{depth}-{kind}', 'left': x, 'right': y, 'equal': expected})
    external, excluded = [], []
    for keyword in ('const', 'enum', 'uniqueItems'):
        suite_root = DATA / 'sources/official'
        alternatives = [suite_root / 'tests/draft7', suite_root / 'validation/tests/draft7', suite_root / 'validation/tests']
        matches = [p for p in alternatives if (p / (keyword + '.json')).is_file()]
        if len(matches) != 1: raise ValueError('missing or ambiguous official suite layout')
        path = matches[0] / (keyword + '.json')
        body = json.loads(path.read_text())
        groups = body if isinstance(body, list) else body['tests']
        for i, group in enumerate(groups):
            schema = group['schema']
            if not compatible(group.get('compatibility')):
                excluded.append({'file': str(path.relative_to(DATA)), 'group': i, 'reason': 'author dialect compatibility excludes draft7'})
                continue
            if not isinstance(schema, dict) or set(schema) - {keyword, '$schema'}:
                excluded.append({'file': str(path.relative_to(DATA)), 'group': i, 'reason': 'schema outside checker scope'})
                continue
            for j, t in enumerate(group['tests']):
                if not compatible(t.get('compatibility')):
                    excluded.append({'file': str(path.relative_to(DATA)), 'group': i, 'test': j, 'reason': 'author dialect compatibility excludes draft7'})
                    continue
                def finite(value):
                    if isinstance(value, float): return math.isfinite(value)
                    if isinstance(value, list): return all(finite(v) for v in value)
                    if isinstance(value, dict): return all(finite(v) for v in value.values())
                    return True
                if not finite(schema) or not finite(t['data']):
                    excluded.append({'file': str(path.relative_to(DATA)), 'group': i, 'test': j, 'reason': 'nonfinite value outside declared domain'})
                    continue
                external.append({'id': f'official-{keyword}-{i}-{j}', 'schema': schema, 'data': t['data'], 'valid': t['valid']})
    dump(DATA / 'corpus.json', {'pairs': pairs, 'external': external, 'excluded': excluded})
    file_manifest = {str(p.relative_to(DATA / 'sources')): ({'symlink': str(p.readlink())} if p.is_symlink() else {'sha256': digest(p)})
                     for p in sorted((DATA / 'sources').rglob('*')) if p.is_file() or p.is_symlink()}
    dump(DATA / 'freeze.json', {'pins': pins, 'corpus_sha256': digest(DATA / 'corpus.json'),
                               'file_manifest': file_manifest, 'protocol_sha256': digest(HERE / 'PROTOCOL.md'),
                               'acquisition_seconds': time.monotonic() - started})
    print('P7_FROZEN', json.dumps({'pins': {k: v['sha'] for k, v in pins.items()},
                                  'pairs': len(pairs), 'external': len(external), 'excluded': len(excluded)}), flush=True)


if __name__ == '__main__': main()
