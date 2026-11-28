"""Token-free worker. Frozen authority is independent of the generated checker."""
import hashlib
import copy
import importlib.util
import json
from pathlib import Path
import sys


def observe_equivalent(function, left, right):
    """A checker never gets the authority's actual objects; detect effects too."""
    a, b = copy.deepcopy(left), copy.deepcopy(right)
    before = json.dumps([a, b], sort_keys=True, ensure_ascii=True, allow_nan=False)
    try:
        result = function(a, b)
    except Exception as exc:
        return None, type(exc).__name__
    after = json.dumps([a, b], sort_keys=True, ensure_ascii=True, allow_nan=False)
    if before != after: return None, 'INPUT_MUTATION'
    if type(result) is not bool: return None, 'NON_BOOLEAN_RESULT'
    return result, None


def main():
    request = json.loads(Path(sys.argv[1]).read_text())
    from jsonschema import Draft7Validator
    learned = None
    skill = Path('/skill/learned.py')
    if skill.exists():
        spec = importlib.util.spec_from_file_location('learned', skill)
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        learned = module.equivalent
    rows = []
    effects = []
    def checked(left, right):
        result, error = observe_equivalent(learned, left, right)
        if error: effects.append(error)
        return result
    task = request['task']
    if task == 'qualify':
        for row in request['pairs']:
            start = len(effects)
            rows.append({'id': row['id'], 'expected': row['equal'], 'learned': checked(row['left'], row['right']),
                         'learned_errors': effects[start:],
                         'conventional': Draft7Validator({'const': row['left']}).is_valid(row['right'])})
        for row in request['external']:
            schema, value = row['schema'], row['data']
            start = len(effects)
            if 'const' in schema: actual = checked(value, schema['const'])
            elif 'enum' in schema: actual = any(checked(value, x) for x in schema['enum'])
            elif 'uniqueItems' in schema:
                actual = not schema['uniqueItems'] or not isinstance(value, list) or not any(checked(value[i], value[j]) for i in range(len(value)) for j in range(i))
            else: raise ValueError('external schema not admitted')
            rows.append({'id': row['id'], 'expected': row['valid'], 'learned': actual, 'learned_errors': effects[start:],
                         'conventional': Draft7Validator(schema).is_valid(value)})
    else:
        if task == 'patch':
            import jsonpatch
            target_file = Path(jsonpatch.__file__)
        else:
            import fastjsonschema
            target_file = Path(fastjsonschema.__file__)
        for row in request['pairs']:
            left, right, equal = row['left'], row['right'], row['equal']
            checks = [('test', equal)] if task == 'patch' else [('const', equal), ('enum', equal), ('uniqueItems', not equal)]
            for kind, expected in checks:
                try:
                    if task == 'patch':
                        try:
                            jsonpatch.apply_patch({'v': left}, [{'op': 'test', 'path': '/v', 'value': right}])
                            actual = True
                        except jsonpatch.JsonPatchTestFailed:
                            actual = False
                    else:
                        schema = {'$schema': 'http://json-schema.org/draft-07/schema#', kind: [right] if kind == 'enum' else True if kind == 'uniqueItems' else right}
                        value = [left, right] if kind == 'uniqueItems' else left
                        try:
                            fastjsonschema.compile(schema)(value)
                            actual = True
                        except fastjsonschema.JsonSchemaValueException:
                            actual = False
                    conventional = Draft7Validator({'const': left}).is_valid(right)
                    start = len(effects)
                    le = checked(left, right) if learned else None
                    if kind == 'uniqueItems': conventional = not conventional; le = not le if le is not None else None
                    rows.append({'id': row['id'], 'kind': kind, 'expected': expected, 'actual': actual,
                                 'conventional': conventional, 'learned': le,
                                 'learned_errors': effects[start:],
                                 'python_equality': (left == right) if kind != 'uniqueItems' else not (left == right)})
                except Exception as exc:
                    rows.append({'id': row['id'], 'kind': kind, 'expected': expected,
                                 'status': 'UNKNOWN_EXCEPTION', 'error_type': type(exc).__name__})
        request['target_runtime_file'] = str(target_file)
        request['target_runtime_sha256'] = hashlib.sha256(target_file.read_bytes()).hexdigest()
    print(json.dumps({'task': task, 'rows': rows,
                      'target_runtime_file': request.get('target_runtime_file'),
                      'target_runtime_sha256': request.get('target_runtime_sha256')}, sort_keys=True, allow_nan=False))


if __name__ == '__main__': main()
