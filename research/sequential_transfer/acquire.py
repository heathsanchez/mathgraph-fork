"""Deterministic external task acquisition, before any P6 inference."""
import collections
import os
import time
from core import HERE, native, dump, load, digest, stable
import prepare as previous
import admit_legacy as upstream

DATA = HERE / 'data'
POOL = ('python-hyper/h11', 'python-hyper/hpack', 'python-hyper/hyperframe',
        'tkem/cachetools', 'andialbrecht/sqlparse', 'lepture/mistune',
        'jquast/wcwidth', 'Python-Markdown/markdown', 'uiri/toml',
        'agronholm/exceptiongroup', 'python-trio/outcome', 'pypa/pyproject-hooks')
TARGET = 4


def main():
    started = time.monotonic()
    DATA.mkdir(exist_ok=True)
    for p in ('public/future', 'private', 'rejected'):
        (DATA / p).mkdir(parents=True, exist_ok=True)
    previous.ROOT = DATA
    environment = native.build()
    attempts, selected = [], []

    def save():
        dump(DATA / 'admission.json', {
            'protocol_sha256': digest(HERE / 'PROTOCOL.md'), 'source_sha': os.environ.get('GITHUB_SHA'),
            'pool': POOL, 'selected': selected, 'attempts': attempts, 'environment': environment,
            'elapsed_seconds': time.monotonic() - started})
    save()
    for repo in POOL:
        if len(selected) >= TARGET or time.monotonic() - started > 1200:
            break
        try:
            prs = upstream.api(repo, 'pulls?state=closed&sort=updated&direction=desc&per_page=100')
            candidates = sorted([p for p in prs if p.get('merged_at') and p.get('merge_commit_sha')
                                 and upstream.eligible_title(p.get('title', ''))], key=lambda p: -p['number'])
        except Exception as exc:
            attempts.append({'repo': repo, 'status': 'UNKNOWN_LIST', 'error_type': type(exc).__name__})
            save()
            continue
        tested = 0
        for p in candidates:
            if tested >= 3 or time.monotonic() - started > 1200:
                break
            rec = {'repo': repo, 'pr': p['number']}
            try:
                merge = upstream.api(repo, 'commits/' + p['merge_commit_sha'])
                if upstream.layout(merge.get('files', [])) is None:
                    rec['status'] = 'INELIGIBLE_LAYOUT'
                    attempts.append(rec)
                    save()
                    continue
                tested += 1
                cid = f'task-{len(selected) + 1:02d}'
                result, status = previous.prepare(repo, p['number'], merge, environment, cid, 'future')
                rec['status'] = status
                if status == 'ADMITTED':
                    private = DATA / 'private' / cid
                    a = load(private / 'authority.json')
                    # Base identity is compared to independent GitHub object metadata too.
                    meta = upstream.api(repo, 'contents/' + a['source_path'] + '?ref=' + a['parent'])
                    if meta['sha'] != a['base_blob']:
                        raise ValueError('base Git object mismatch')
                    author = upstream.request('https://raw.githubusercontent.com/' + repo + '/' + a['head'] + '/' + a['source_path'])
                    (private / 'author_source.txt').write_bytes(author)
                    if upstream.gitblob(private / 'author_source.txt') != a['head_blob']:
                        raise ValueError('author Git object mismatch')
                    a['author_source_sha256'] = digest(private / 'author_source.txt')
                    dump(private / 'authority.json', a)
                    pub = DATA / 'public' / 'future' / (cid + '.json')
                    packet = load(pub)
                    packet.pop('test_excerpt', None)
                    packet['requirement'] = p['title']
                    packet['authority_boundary'] = 'Original source, independent PR title and baseline diagnostic; full author tests/fix withheld.'
                    dump(pub, packet)
                    result['public_sha256'] = digest(pub)
                    selected.append(result)
                elif result:
                    rec['native_summary'] = result
            except Exception as exc:
                rec.update(status='UNKNOWN_ACQUISITION', error_type=type(exc).__name__)
            attempts.append(rec)
            save()
            print('P6_ADMISSION', repo, p['number'], rec['status'], flush=True)
            if rec['status'] == 'ADMITTED':
                break
        if not candidates:
            attempts.append({'repo': repo, 'status': 'NO_ELIGIBLE_MERGED_TITLE'})
            save()
    save()
    print('P6_FROZEN', len(selected), dict(collections.Counter(x['status'] for x in attempts)), flush=True)
    if len(selected) < 3:
        print('UNKNOWN_INSUFFICIENT_COHORT_NO_API', flush=True)


if __name__ == '__main__':
    main()
