"""Download only frozen examples; upstream sessions are never written to disk."""
import argparse
from importlib.resources import files
import json
import os
from pathlib import Path
import re
import sys
import urllib.request

from .trace_commons import extract, sha

MAX_SOURCE_BYTES = 20_000_000
MAX_TOTAL_BYTES = 100_000_000
TIMEOUT = 30
DEFAULT_OUTPUT = Path('.slophound/example-data')


def load_catalog():
    catalog = json.loads(files('hound').joinpath('example_catalog.json').read_bytes())
    sources = {source['source_path']: source for source in catalog['sources']}
    for index, doc in enumerate(catalog['documents']):
        if doc['authorship'] == 'recorded-assistant-output':
            source = sources[doc['source_path']]
            catalog['documents'][index] = dict(catalog['ai_metadata'], **doc,
                                               source_url=source['source_url'], source_sha256=source['sha256'])
    return catalog


def fetch(url, limit):
    with urllib.request.urlopen(url, timeout=TIMEOUT) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f'download byte bound exceeded: {url}')
    return data


def safe_path(root, name):
    if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*', name) or any(p in ('.', '..') for p in name.split('/')):
        raise ValueError(f'unsafe catalog path: {name!r}')
    path = root / name
    for part in (path, *path.parents):
        if part.is_symlink():
            raise ValueError(f'symlink output path: {part}')
    return path


def verify(data, item):
    if len(data) != item['bytes'] or sha(data) != item['sha256']:
        raise ValueError(f"bytes/hash mismatch: {item.get('path', item.get('source_path', item.get('source_url')))}")


def download(output, catalog=None, fetcher=None):
    catalog = load_catalog() if catalog is None else catalog
    fetcher = fetch if fetcher is None else fetcher
    root = Path(os.path.abspath(output))
    documents = catalog['documents']
    sources = {s['source_path']: s for s in catalog['sources']}
    if len(sources) != len(catalog['sources']):
        raise ValueError('duplicate catalog source path')
    if catalog['schema_version'] != 1 or not documents:
        raise ValueError('invalid example catalog')
    for item in [*sources.values(), *catalog['notices'], *documents]:
        if not isinstance(item['bytes'], int) or not 0 < item['bytes'] <= MAX_SOURCE_BYTES or not re.fullmatch('[0-9a-f]{64}', item['sha256']):
            raise ValueError('catalog hash/byte bounds invalid')
        if 'source_url' in item and not item['source_url'].startswith('https://'):
            raise ValueError('catalog source must use HTTPS')
    if sum(s['bytes'] for s in sources.values()) + sum(n['bytes'] for n in catalog['notices']) > MAX_TOTAL_BYTES:
        raise ValueError('aggregate source byte bound exceeded')
    for doc in documents:
        if doc['source_path'] not in sources:
            raise ValueError('missing catalog source')
        group = 'ai/' if doc['authorship'] == 'recorded-assistant-output' else 'human/'
        if doc['authorship'] not in ('recorded-assistant-output', 'human-authored') or not doc['path'].startswith(group):
            raise ValueError('invalid authorship output path')
    managed = [*documents, *catalog['notices']]
    paths = {item['path']: safe_path(root, item['path']) for item in managed}
    if len(paths) != len(managed) or any(not n['path'].startswith('notices/') for n in catalog['notices']):
        raise ValueError('duplicate or invalid managed output path')
    inventory = json.dumps(catalog, ensure_ascii=False, sort_keys=True, indent=2).encode('utf-8') + b'\n'
    inventory_item = {'path': 'inventory.json', 'sha256': sha(inventory), 'bytes': len(inventory)}
    paths['inventory.json'] = safe_path(root, 'inventory.json')
    missing = []
    for item in [*managed, inventory_item]:
        path = paths[item['path']]
        if path.exists():
            verify(path.read_bytes(), item)
        else:
            missing.append(item)
    if not missing:
        return len(documents)
    # Prepare and validate everything before any directory or file is created.
    pending = {}
    wanted = {item['path'] for item in missing}
    total = 0
    for source_path, source in sources.items():
        docs = [d for d in documents if d['source_path'] == source_path and d['path'] in wanted]
        if not docs:
            continue
        raw = fetcher(source['source_url'], source['bytes'])
        total += len(raw)
        if total > MAX_TOTAL_BYTES:
            raise ValueError('aggregate download byte bound exceeded')
        verify(raw, source)
        ai_docs = [d for d in docs if d['authorship'] == 'recorded-assistant-output']
        records = {}
        if ai_docs:
            rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
            records = {r['message_locator']['message_id']: r for r in extract(rows, source_path)}
        for doc in docs:
            data = raw
            if doc in ai_docs:
                record = records.get(doc['message_locator']['message_id'])
                if record is None or any(record[key] != doc[key] for key in ('message_locator', 'text_line', 'model', 'sha256')):
                    raise ValueError(f"frozen complete message mismatch: {doc['path']}")
                data = record['text'].encode('utf-8')
            verify(data, doc)
            pending[doc['path']] = data
        # raw and parsed user/tool/thinking data have no persistent cache.
    for notice in catalog['notices']:
        if notice['path'] in wanted:
            data = fetcher(notice['source_url'], notice['bytes'])
            verify(data, notice)
            pending[notice['path']] = data
    if 'inventory.json' in wanted:
        pending['inventory.json'] = inventory
    # Exclusive creation never replaces existing outputs, even on a competing run.
    # Disk failures may leave verified files; no success is reported and reruns resume.
    for name, data in pending.items():
        path = safe_path(root, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        safe_path(root, name)
        with path.open('xb') as stream:
            stream.write(data)
    return len(documents)


def main(argv=None):
    from .datasets import load_datasets, download_dataset, report_selection
    entries = load_datasets()
    parser = argparse.ArgumentParser(prog='slophound get-corpus', description='Inspect and select corpora without NLP or keys. Default: frozen 166 curated AI messages plus two human PEPs, not whole Trace Commons.')
    parser.add_argument('--output-dir', type=Path, default=DEFAULT_OUTPUT, help='output directory (default: .slophound/example-data relative to cwd)')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--list', action='store_true', help='offline dataset catalogue; not a golden-quality ranking')
    mode.add_argument('--info', choices=entries, metavar='DATASET', help='offline metadata and limitations')
    parser.add_argument('--dataset', action='append', choices=entries, help='repeat to select datasets; unavailable entries fail explicitly')
    parser.add_argument('--purpose', choices=sorted({p for e in entries.values() for p in e['purposes']}), help='select downloadable datasets matching this purpose')
    parser.add_argument('--limit', type=int, default=None, help='maximum complete items per dataset, 1..10000 (selective default 1000); never truncates text; eligible yield may be lower')
    args = parser.parse_args(argv)
    if args.limit is not None and not 1 <= args.limit <= 10000:
        parser.error('--limit must be 1..10000')
    if args.list:
        for name, entry in entries.items():
            available = entry['available_count'] if entry['available_count'] is not None else 'unknown until inspected'
            print(f"{name}: {entry['status']}; known eligible={available}; curated={entry['curated_count']}; scope={entry['scope']}; purposes={','.join(entry['purposes'])}; {entry['cache']}")
        return 0
    if args.info:
        print(json.dumps(entries[args.info], ensure_ascii=False, indent=2))
        return 0
    selected = args.dataset or []
    if args.purpose:
        selected = [name for name in (selected or entries) if args.purpose in entries[name]['purposes'] and entries[name]['downloadable']]
        if not selected:
            parser.error('no downloadable datasets match purpose')
    if args.limit is not None and not selected:
        selected = ['trace-commons-curated', 'human-peps']
    try:
        if selected:
            for name in dict.fromkeys(selected):
                if not entries[name]['downloadable']:
                    raise ValueError(f"{name}: {entries[name]['status']}; {entries[name]['caveats']}")
            count = 0
            for name in dict.fromkeys(selected):
                count += download_dataset(name, args.output_dir, args.limit or 1000)
                print(report_selection(name, args.output_dir, args.limit or 1000))
        else:
            count = download(args.output_dir)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f'slophound get-corpus: {exc}', file=sys.stderr)
        return 2
    provenance = '<dataset>/limit-<N>/inventory.json and notices/' if selected else 'inventory.json and notices/'
    print(f'{count} examples verified in {args.output_dir}; provenance: {provenance}')
    return 0
