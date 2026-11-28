"""Shared transport and source-pinned native execution, no model access."""
import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
DATA, WORK = HERE / 'data', HERE / 'work'
sys.path.insert(0, str(HERE.parent / 'applicability_transfer'))
import admit_legacy as source
from native import dump, load, digest, stable, repair_green
IMAGE = 'mathgraph-p7-current:20261128'


def build():
    if os.environ.get('OPENAI_API_KEY'):
        raise RuntimeError('native stage received model credential')
    p = subprocess.run(['docker', 'build', '-t', IMAGE, str(HERE)], text=True, capture_output=True, timeout=600)
    if p.returncode:
        raise RuntimeError('native image build failed: ' + p.stderr[-1200:])
    p = subprocess.run(['docker', 'run', '--rm', '--network', 'none', IMAGE, 'python', '-m', 'pip', 'freeze'],
                       text=True, capture_output=True, timeout=60)
    if p.returncode:
        raise RuntimeError('native environment census failed')
    info = subprocess.check_output(['docker', 'image', 'inspect', IMAGE, '--format', '{{.Id}}'], text=True).strip()
    return {'image': info, 'packages': p.stdout.splitlines()}


def native(root, payload, skill=None, *, suite=None):
    if os.environ.get('OPENAI_API_KEY'):
        raise RuntimeError('native stage received model credential')
    with tempfile.TemporaryDirectory(prefix='p7-native-') as d:
        temp = Path(d); temp.chmod(0o777)
        request = temp / 'request.json'; dump(request, payload)
        cmd = ['docker', 'run', '--rm', '--network', 'none', '--cap-drop', 'ALL',
               '--security-opt', 'no-new-privileges', '--pids-limit', '128', '--memory', '1800m',
               '--cpus', '2', '--read-only', '--user', '65534:65534',
               '--tmpfs', '/tmp:rw,nosuid,nodev,size=512m', '-v', str(Path(root).resolve()) + ':/work:ro',
               '-v', str((DATA / 'sources' / 'pointer').resolve()) + ':/pointer:ro',
               '-v', str((DATA / 'sources' / 'control').resolve()) + ':/control:ro',
               '-v', str(temp) + ':/out:rw', '-e', 'HOME=/tmp', '-e', 'PYTHONDONTWRITEBYTECODE=1',
               '-e', 'PYTHONPATH=/work/src:/work:/pointer:/control:/harness',
               '-e', 'PYTEST_DISABLE_PLUGIN_AUTOLOAD=1', '-w', '/work']
        if skill is not None:
            path = temp / 'learned.py'; path.write_text(skill)
            cmd += ['-v', str(path) + ':/skill/learned.py:ro']
        cmd += [IMAGE]
        if suite is not None:
            cmd += ['python', '-m', 'pytest', '-p', 'no:cacheprovider', '-q', '--tb=short',
                    '--junitxml=/out/junit.xml'] + suite
        else:
            cmd += ['python', '/harness/worker.py', '/out/request.json']
        started = time.monotonic()
        try:
            p = subprocess.run(cmd, text=True, capture_output=True, timeout=240)
        except subprocess.TimeoutExpired:
            return {'status': 'UNKNOWN_TIMEOUT', 'tests': {}, 'elapsed_seconds': time.monotonic() - started}
        result = {'status': 'EXECUTED', 'returncode': p.returncode,
                  'elapsed_seconds': time.monotonic() - started, 'diagnostic': (p.stdout + '\n' + p.stderr)[-16000:]}
        if suite is None:
            try:
                result['output'] = json.loads(p.stdout)
            except ValueError:
                result['status'] = 'UNKNOWN_NATIVE_OUTPUT'
            return result
        result['tests'] = {}
        path = temp / 'junit.xml'
        if not path.exists():
            result['status'] = 'UNKNOWN_NO_JUNIT'
            return result
        for c in ET.parse(path).getroot().iter('testcase'):
            key = c.attrib.get('classname', '') + '::' + c.attrib.get('name', '')
            if key in result['tests']:
                result['status'] = 'UNKNOWN_DUPLICATE_TEST'
                return result
            result['tests'][key] = next((t for t in ('failure', 'error', 'skipped') if c.find(t) is not None), 'pass')
        return result


def skill_scope(code):
    if not isinstance(code, str) or not 1 <= len(code) <= 14000:
        raise ValueError('checker size')
    tree = ast.parse(code)
    if not tree.body or any(not isinstance(n, ast.FunctionDef) for n in tree.body):
        raise ValueError('checker must contain only function definitions')
    if sum(n.name == 'equivalent' for n in tree.body) != 1:
        raise ValueError('equivalent function required')
    banned = {'open', 'exec', 'eval', 'compile', '__import__', 'globals', 'locals', 'getattr', 'setattr',
              'os', 'sys', 'subprocess', 'socket', 'requests', 'importlib', 'inspect', 'environ'}
    for n in ast.walk(tree):
        if isinstance(n, (ast.Import, ast.ImportFrom, ast.Global, ast.Nonlocal)):
            raise ValueError('checker effect')
        if isinstance(n, ast.Name) and (n.id in banned or n.id.startswith('__')):
            raise ValueError('checker privileged name')
        if isinstance(n, ast.Attribute) and (n.attr in banned or n.attr.startswith('__')):
            raise ValueError('checker privileged attribute')
        if isinstance(n, ast.FunctionDef) and (n.decorator_list or n.args.defaults or n.args.kw_defaults):
            raise ValueError('checker import-time expressions')
        if isinstance(n, ast.FunctionDef) and (n.returns is not None or any(a.annotation is not None for a in n.args.posonlyargs + n.args.args + n.args.kwonlyargs)):
            raise ValueError('checker annotation expressions')
    return code


def apply_edits(originals, edits):
    import difflib
    if not isinstance(edits, list) or not 1 <= len(edits) <= 4:
        raise ValueError('file edit count')
    result = dict(originals); seen = set(); changed = 0
    for row in edits:
        if not isinstance(row, dict) or set(row) != {'path', 'replacements'}:
            raise ValueError('edit fields')
        path = row['path']
        if path not in originals or path in seen:
            raise ValueError('unadmitted production file')
        seen.add(path)
        replacements = row['replacements']
        if not isinstance(replacements, list) or not 1 <= len(replacements) <= 6:
            raise ValueError('replacement count')
        source_text = originals[path]; spans = []
        for e in replacements:
            if not isinstance(e, dict) or set(e) != {'old', 'new'} or not all(isinstance(v, str) for v in e.values()):
                raise ValueError('replacement fields')
            old, new = e['old'], e['new']
            if not old or old == new or source_text.count(old) != 1:
                raise ValueError('unique original anchor required')
            a = source_text.index(old); b = a + len(old)
            if any(a < y and x < b for x, y, _ in spans):
                raise ValueError('overlapping replacements')
            spans.append((a, b, new))
        modified = source_text
        for a, b, text in sorted(spans, reverse=True):
            modified = modified[:a] + text + modified[b:]
        before, after = ast.parse(source_text), ast.parse(modified)
        import trial
        def names(t): return {n.id for n in ast.walk(t) if isinstance(n, ast.Name)} | {n.attr for n in ast.walk(t) if isinstance(n, ast.Attribute)}
        if (names(after) - names(before)) & trial.BANNED:
            raise ValueError('new privileged reference')
        if {ast.dump(n) for n in ast.walk(after) if isinstance(n, (ast.Import, ast.ImportFrom))} - {ast.dump(n) for n in ast.walk(before) if isinstance(n, (ast.Import, ast.ImportFrom))}:
            raise ValueError('new import')
        changed += sum(x[:1] in ('+', '-') for x in difflib.ndiff(source_text.splitlines(), modified.splitlines()))
        result[path] = modified
    if changed > 200:
        raise ValueError('changed-line budget')
    return result
