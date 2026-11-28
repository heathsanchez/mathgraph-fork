"""Credential-free native interpreter. Expected values never enter this process."""
import hashlib
import importlib
import json
from pathlib import Path
import sys
import time


def execute(source, operation, inputs):
    namespace = {}
    if source is not None:
        exec(compile(source, '<constructed-method>', 'exec'), namespace)
        method = namespace['investigate']
    rows = []
    for value in inputs:
        calls = []
        started = time.monotonic()
        def observe(text):
            if not isinstance(text, str) or len(text) > 16000 or len(calls) >= 64:
                raise ValueError('native observation budget/domain')
            output = operation(text)
            calls.append({'input': text, 'output': output})
            return output
        try:
            if source is None:
                answer = observe(value)
            else:
                answer = method(value, observe)
            if answer is not None and not isinstance(answer, str):
                raise TypeError('constructed result must be string or None')
            row = {'input': value, 'output': answer, 'status': 'RETURNED'}
        except Exception as exc:
            row = {'input': value, 'status': 'UNKNOWN_NATIVE_EXCEPTION',
                   'error_type': type(exc).__name__, 'error': str(exc)[:240]}
        row.update(observations=calls, elapsed_seconds=time.monotonic()-started)
        rows.append(row)
    return rows


def main():
    request = json.loads(Path('/work/request.json').read_text())
    assert set(request) <= {'inputs', 'source', 'options'}
    assert all(isinstance(s, str) for s in request['inputs'])
    sys.path.insert(0, '/target')
    ftfy = importlib.import_module('ftfy')
    operation = lambda s: ftfy.fix_text(s, **request.get('options', {}))
    result = {'rows': execute(request.get('source'), operation, request['inputs']),
              'target_import': str(Path(ftfy.__file__).resolve()),
              'target_import_sha256': hashlib.sha256(Path(ftfy.__file__).read_bytes()).hexdigest(),
              'request_keys': sorted(request), 'expected_available_to_program': False}
    Path('/out/result.json').write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2)+'\n')


if __name__ == '__main__':
    main()
