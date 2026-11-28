"""Credential-free fresh-extraction replay of final native decisions."""
import json
import os
from pathlib import Path
import sys
from core import HERE, ARMS, native, dump, load, digest, payload
import run


def main():
    if os.environ.get('OPENAI_API_KEY'):
        raise RuntimeError('cold replay must not receive the model credential')
    root = HERE.parent
    manifest_path = root / 'MANIFEST.json'
    if manifest_path.exists():
        manifest = load(manifest_path)
        for path, expected in manifest.items():
            if digest(root / path) != expected:
                raise ValueError('manifest mismatch: ' + path)
    native.build()
    checked, cache = [], {}
    for folder in sorted(run.WORK.glob('episode-*')):
        original = load(folder / 'episode.json')
        probes = load(folder / 'probe_proposals.json')
        first = load(folder / 'repair_proposals_1.json')
        second = load(folder / 'repair_proposals_2.json')
        for arm in ARMS:
            chosen = original['selected_round'][arm]
            call = (second if chosen == 2 else first).get(arm, {}).get('call', {})
            code = payload(probes[arm]['call']).get('probe_code')
            key = run.stable({'call': payload(call), 'probe': code})
            if key not in cache:
                cache[key] = run.verify_candidate(original['id'], call, code)
            fresh, prior = cache[key], original['final'][arm]
            for k in ('status', 'author_verified', 'probe_verified', 'candidate_sha256'):
                if fresh.get(k) != prior.get(k):
                    raise ValueError(f'replay decision mismatch: {original["id"]} {arm} {k}')
            for k in ('author_native', 'probe_native'):
                if fresh.get(k, {}).get('tests') != prior.get(k, {}).get('tests'):
                    raise ValueError('replay test roster/verdict mismatch')
            checked.append({'id': original['id'], 'arm': arm, 'author_verified': fresh.get('author_verified'),
                            'probe_verified': fresh.get('probe_verified')})
    result = {'status': 'PASS', 'final_decisions': len(checked), 'unique_replays': len(cache),
              'manifest_files': len(load(manifest_path)) if manifest_path.exists() else None,
              'checked': checked, 'scope': 'No new inference; final source, author tests and frozen-probe verdicts replayed.'}
    dump(root / 'cold_replay_receipt.json', result)
    print('P6_COLD_REPLAY', json.dumps(result, sort_keys=True), flush=True)


if __name__ == '__main__':
    main()
