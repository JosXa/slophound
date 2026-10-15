"""Offline metadata and selective, hash-verified corpus downloads."""
from importlib.resources import files
import json
from pathlib import Path

from .example_data import (load_catalog, download, fetch, verify, safe_path,
                           MAX_TOTAL_BYTES, MAX_SOURCE_BYTES)
from .trace_commons import extract, sha
from . import hf_corpora, arena_corpus


RECORD_KEYS = {'dataset_id', 'config', 'split', 'row_index', 'turn_index', 'side',
               'role', 'role_source', 'text_source', 'model', 'model_source',
               'language', 'source_kind', 'source_response_sha256', 'viewer_url',
               'observed_repo_revision', 'viewer_pinned_native_snapshot'}

SOURCE_KEYS = {'dataset_id', 'native_url', 'revision', 'source_sha256', 'bytes',
               'pinned_native_snapshot', 'viewer_pinned_native_snapshot', 'snapshot_caveat',
               'config', 'split', 'requests', 'response_bytes', 'rows_examined',
               'rejected_candidates_or_rows', 'observed_repo_revision_before',
               'observed_repo_revision_after', 'source_response_sha256', 'viewer_url'}


def _source_metadata(source):
    clean = {k: v for k, v in source.items() if k in SOURCE_KEYS}
    if 'pages' in source:
        clean['pages'] = [{k: v for k, v in page.items() if k in
                           {'url', 'response_sha256', 'offset', 'requested_rows'}}
                          for page in source['pages']]
    return clean


def _sample(root, name, limit, entry, fetcher):
    if name == 'wildchat':
        adapted = None if fetcher is None else lambda url, timeout, max_bytes: fetcher(url, max_bytes)
        result = hf_corpora.sample_dataset(hf_corpora.WILDCHAT, limit, 100000, fetch=adapted)
    else:
        adapted = None if fetcher is None else lambda url, timeout: fetcher(url, arena_corpus.SOURCE_BYTES)
        result = arena_corpus.sample_arena(limit, fetch=adapted)
    if result.get('error') or not result['records']:
        error = result.get('error') or {'code': 'zero_yield'}
        raise ValueError(f"{name}: {error['code']}; no eligible complete assistant items written")
    pending = {}; documents = []
    for record in result['records'][:limit]:
        data = record['text'].encode('utf-8')
        digest = sha(data)
        path = f'ai/{len(documents)}-{digest}.md'
        doc = {k: v for k, v in record.items() if k in RECORD_KEYS}
        doc.update(path=path, bytes=len(data), sha256=digest,
                   authorship='recorded-assistant-output', manual_review=False)
        documents.append(doc); pending[path] = data
    notice = (f"Source: {entry['source_url']}\nDataset terms: {entry['licence']}\n"
              f"{entry['caveats']}\nAttribution and model information: inventory.json.\n"
              "No user prompts, tools or reasoning exported. Automated screening is not rights clearance.\n").encode()
    pending['notices/source-and-terms.txt'] = notice
    revision = result['source'].get('revision') or result['source'].get('observed_repo_revision_before')
    card_url = entry['source_url'] + f'/resolve/{revision}/README.md'
    card = (fetcher or fetch)(card_url, 1_000_000)
    if not isinstance(card, bytes) or not 0 < len(card) <= 1_000_000:
        raise ValueError('dataset notice byte bound exceeded')
    pending['notices/dataset-card.md'] = card
    selected = dict(schema_version=1, dataset=name, limit=limit,
                    selected_count=len(documents), available_count=None,
                    partial=len(documents)<limit,
                    partial_reason=result.get('partial_reason') or ('native_source_exhausted_after_screening' if len(documents)<limit else None),
                    scope=entry['scope'], sources=[_source_metadata(result['source'])], documents=documents,
                    notices=[dict(path='notices/source-and-terms.txt', bytes=len(notice), sha256=sha(notice)),
                             dict(path='notices/dataset-card.md', source_url=card_url, bytes=len(card), sha256=sha(card))])
    _write(root, selected, pending, fetcher)
    return len(documents)


def report_selection(name, output, limit):
    inventory = _cached(Path(output).absolute()/name/f'limit-{limit}')
    if inventory is None:
        raise ValueError('missing selection inventory')
    suffix = f"; partial: {inventory['partial_reason']}" if inventory.get('partial') else ''
    return f"{name}: {len(inventory['documents'])} complete items verified (requested at most {limit}){suffix}"


def load_datasets():
    return json.loads(files('hound').joinpath('dataset_catalog.json').read_bytes())


def _cached(root):
    path = safe_path(root, 'inventory.json')
    if not path.exists():
        return None
    catalog = json.loads(path.read_bytes())
    # Inventory digest prevents silently trusting accidental metadata edits.
    digest = safe_path(root, 'inventory.sha256')
    if digest.read_text().strip() != sha(path.read_bytes()):
        raise ValueError('inventory hash mismatch')
    for item in [*catalog['documents'], *catalog['notices']]:
        verify(safe_path(root, item['path']).read_bytes(), item)
    return catalog


def _write(root, catalog, pending, fetcher):
    for notice in catalog['notices']:
        data = pending.get(notice['path'])
        if data is None:
            data = fetcher(notice['source_url'], notice['bytes'])
        verify(data, notice)
        pending[notice['path']] = data
    inventory = json.dumps(catalog, ensure_ascii=False, sort_keys=True, indent=2).encode() + b'\n'
    pending['inventory.json'] = inventory
    pending['inventory.sha256'] = (sha(inventory)+'\n').encode()
    # Verify preexisting files before any write; exclusive creation never overwrites.
    for name, data in pending.items():
        p = safe_path(root, name)
        if p.exists() and p.read_bytes() != data:
            raise ValueError(f'bytes/hash mismatch: {name}')
    for name, data in pending.items():
        p = safe_path(root, name)
        if not p.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
            safe_path(root, name)
            with p.open('xb') as stream:
                stream.write(data)


def download_dataset(name, output, limit=1000, *, catalog=None, fetcher=None):
    if type(limit) is not int or not 1 <= limit <= 10000:
        raise ValueError('limit must be 1..10000')
    entries = load_datasets()
    if name not in entries:
        raise ValueError(f'unknown dataset: {name}')
    entry = entries[name]
    if not entry['downloadable']:
        raise ValueError(f"{name}: {entry['status']}; {entry['caveats']}")
    root = Path(output).absolute() / name / f'limit-{limit}'
    for managed in ('inventory.json', 'inventory.sha256', 'ai', 'documents', 'notices', 'human'):
        safe_path(root, managed)
    cached = _cached(root)
    if cached is not None:
        if cached.get('dataset') != name or cached.get('limit') != limit:
            raise ValueError('inventory selection mismatch')
        return len(cached['documents'])
    if name in ('wildchat', 'llm-jp-arena'):
        return _sample(root, name, limit, entry, fetcher)
    fetcher = fetch if fetcher is None else fetcher
    catalog = load_catalog() if catalog is None else catalog
    if name in ('human-peps', 'trace-commons-curated'):
        ai = name == 'trace-commons-curated'
        docs = [d for d in catalog['documents'] if (d['authorship'] == 'recorded-assistant-output') == ai]
        available = len(docs)
        docs = docs[:limit]
        selected = dict(catalog, documents=docs, dataset=name, limit=limit, available_count=available, selected_count=len(docs), partial=len(docs)<limit, partial_reason='frozen_selection_exhausted' if len(docs)<limit else None)
        selected['sources'] = [s for s in catalog['sources'] if any(d['source_path'] == s['source_path'] for d in docs)]
        if not ai:
            selected['notices'] = []  # PEP terms retained in original headers.
        count = download(root, selected, fetcher)
        inventory = safe_path(root, 'inventory.json').read_bytes()
        digest = safe_path(root, 'inventory.sha256')
        if not digest.exists():
            with digest.open('xb') as stream:
                stream.write((sha(inventory)+'\n').encode())
        return count
    pending = {}
    documents = []
    if name == 'trace-commons':
        sources = [s for s in catalog['sources'] if s['source_path'].startswith('sessions/claude_code/')]
        if sum(s['bytes'] for s in sources) > MAX_TOTAL_BYTES:
            raise ValueError('aggregate source byte bound exceeded')
        available = 0
        for source in sources:
            if not 0 < source['bytes'] <= MAX_SOURCE_BYTES:
                raise ValueError('source byte bound exceeded')
            raw = fetcher(source['source_url'], source['bytes'])
            verify(raw, source)
            records = extract([json.loads(line) for line in raw.splitlines() if line.strip()], source['source_path'])
            for record in records:
                if hf_corpora.UNSAFE.search(record['text']) or hf_corpora.REASONING.search(record['text']):
                    continue
                available += 1
                if len(documents) >= limit:
                    continue
                text = record.pop('text').encode('utf-8')
                locator_hash = sha((source['source_path']+'\0'+record['message_locator']['message_id']).encode())
                path = 'ai/'+locator_hash+'.md'
                metadata = dict(catalog.get('ai_metadata', {}))
                metadata.update(record, path=path, bytes=len(text), authorship='recorded-assistant-output', source_url=source['source_url'], source_sha256=source['sha256'], manual_review=False, rights_basis='donor certification; automated whole-record filter, no individual rights verification')
                documents.append(metadata)
                pending[path] = text
        notices = catalog['notices']
    else:
        available = len(entry['documents'])
        documents = [dict(d) for d in entry['documents'][:limit]]
        if any(type(d['bytes']) is not int or not 0 < d['bytes'] <= MAX_SOURCE_BYTES for d in documents):
            raise ValueError('document byte bound exceeded')
        if sum(d['bytes'] for d in documents) + MAX_SOURCE_BYTES > MAX_TOTAL_BYTES:
            raise ValueError('aggregate document byte bound exceeded')
        sources = []
        notices = []
        for index, doc in enumerate(documents):
            doc = dict(doc, path='documents/'+str(index)+'-'+Path(doc['source_path']).name)
            data = fetcher(doc['source_url'], doc['bytes'])
            verify(data, doc)
            pending[doc['path']] = data
            sources.append(dict(source_path=doc['source_path'], source_url=doc['source_url'], sha256=doc['sha256'], bytes=doc['bytes']))
            documents[index] = doc
            notice = dict(path='notices/license.txt', source_url=doc['license_url'], sha256=doc['license_sha256'])
            if not notices:
                notice_data = fetcher(notice['source_url'], MAX_SOURCE_BYTES)
                notice['bytes'] = len(notice_data)
                verify(notice_data, notice)
                pending[notice['path']] = notice_data
                notices.append(notice)
    selected = dict(schema_version=1, dataset=name, limit=limit, available_count=available, selected_count=len(documents), scope=entry['scope'], sources=sources, documents=documents, notices=notices)
    if not documents:
        raise ValueError(f'{name}: zero_yield; no eligible complete items written')
    selected.update(partial=len(documents)<limit, partial_reason='known_sources_exhausted_after_screening' if len(documents)<limit else None)
    _write(root, selected, pending, fetcher)
    return len(documents)
