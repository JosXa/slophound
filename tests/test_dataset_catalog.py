"""Offline contracts: synthetic fixtures are not real-world availability counts."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch
from hound import cli, example_data
from tests.test_example_data import fixture_catalog, digest


class DatasetTests(unittest.TestCase):
    def test_catalogue_offline_route(self):
        with patch.object(example_data, 'fetch', side_effect=AssertionError('network')), patch.object(cli, 'Engine', side_effect=AssertionError('NLP')), patch.object(cli, 'auth_main', side_effect=AssertionError('keys')):
            for args in [['--list'], ['--info', 'trace-commons']]:
                out = io.StringIO()
                with redirect_stdout(out):
                    self.assertEqual(cli.main(['get-corpus', *args]), 0)
                self.assertIn('trace-commons', out.getvalue())
                self.assertIn('curated', out.getvalue())

    def test_bad_selection_and_limit(self):
        for args in [['--dataset', 'unknown'], ['--limit', '0'], ['--limit', '-1']]:
            with self.subTest(args=args), self.assertRaises(SystemExit):
                example_data.main(args)

    def test_frozen_metadata(self):
        from hound import datasets
        entries = datasets.load_datasets()
        self.assertEqual(entries['trace-commons-curated']['curated_count'], 166)
        self.assertEqual(entries['human-peps']['available_count'], 2)
        self.assertEqual(len(entries['pytest-docs']['documents']) + len(entries['click-docs']['documents']), 74)
        self.assertEqual(entries['pytest-docs']['authorship'], 'unknown-human-or-assisted')
        self.assertFalse(entries['sharechat']['downloadable'])
        self.assertFalse(entries['plain-writing-guidelines']['downloadable'])

    def test_scalable_whole_bytes_privacy_all_sources_and_cache_limits(self):
        from hound import datasets
        catalog, responses = fixture_catalog()
        source = catalog['sources'][0]
        rows = [json.loads(x) for x in responses[source['source_url']].splitlines()]
        text = rows[1]['message']['content'][0]['text']
        rows = [rows[0]] + [dict(type='assistant', message=dict(role='assistant', id=f'm{i}', model=f'original-model-{i}', content=[dict(type='text', text=text)])) for i in range(180)]
        rows += [dict(type='assistant', message=dict(role='assistant', id='unsafe', model='original', content=[dict(type='text', text=text+' secret=abc')]))]
        rows += [dict(type='assistant', message=dict(role='assistant', id='private-phone', model='original', content=[dict(type='text', text=text+' Call 212 555 0199.')]))]
        raw = b'\n'.join(json.dumps(r).encode() for r in rows)
        source.update(bytes=len(raw), sha256=digest(raw))
        responses[source['source_url']] = raw
        other = dict(source, source_path='sessions/claude_code/other.jsonl', source_url='https://example.test/other')
        catalog['sources'].append(other)
        responses[other['source_url']] = raw
        calls = []
        def fetch(url, limit):
            calls.append(url)
            return responses[url]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = datasets.download_dataset('trace-commons', root, 170, catalog=catalog, fetcher=fetch)
            self.assertEqual(result, 170)
            inv = json.loads((root/'trace-commons/limit-170/inventory.json').read_bytes())
            self.assertEqual(inv['available_count'], 360)
            self.assertIn(other['source_url'], calls)
            docs = inv['documents']
            self.assertEqual((root/'trace-commons/limit-170'/docs[0]['path']).read_bytes(), text.encode())
            self.assertTrue(all(d['model'].startswith('original-model-') for d in docs))
            self.assertFalse(any(b'PRIVATE' in p.read_bytes() or b'secret=abc' in p.read_bytes() for p in root.rglob('*') if p.is_file()))
            with patch.object(datasets, 'fetch', side_effect=AssertionError('offline')):
                self.assertEqual(datasets.download_dataset('trace-commons', root, 170, catalog=catalog), 170)
            self.assertEqual(datasets.download_dataset('trace-commons', root, 2, catalog=catalog, fetcher=fetch), 2)
            self.assertTrue((root/'trace-commons/limit-170/inventory.json').exists())
            p = root/'trace-commons/limit-170'/docs[0]['path']
            p.write_bytes(b'modified')
            with self.assertRaisesRegex(ValueError, 'hash|bytes'):
                datasets.download_dataset('trace-commons', root, 170, catalog=catalog, fetcher=fetch)
            self.assertEqual(p.read_bytes(), b'modified')

    def test_technical_docs_original_bytes_notice_and_cache(self):
        from hound import datasets
        data = b'Technical docs original\r\n'
        notice = b'License original\r\n'
        entries = datasets.load_datasets()
        entries['pytest-docs']['documents'] = [dict(path='ignored', source_path='doc.md', source_url='https://example.test/doc', bytes=len(data), sha256=digest(data), authorship='unknown-human-or-assisted', license_url='https://example.test/license', license_sha256=digest(notice))]
        responses = {'https://example.test/doc': data, 'https://example.test/license': notice}
        with tempfile.TemporaryDirectory() as tmp, patch.object(datasets, 'load_datasets', return_value=entries):
            self.assertEqual(datasets.download_dataset('pytest-docs', tmp, 1, fetcher=lambda u,n:responses[u]), 1)
            root = Path(tmp)/'pytest-docs/limit-1'
            self.assertEqual((root/'documents/0-doc.md').read_bytes(), data)
            self.assertEqual((root/'notices/license.txt').read_bytes(), notice)
            with patch.object(datasets, 'fetch', side_effect=AssertionError('network')):
                self.assertEqual(datasets.download_dataset('pytest-docs', tmp, 1), 1)

    def test_selection_coexists_curated_human_and_unavailable(self):
        from hound import datasets
        catalog, responses = fixture_catalog()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ['trace-commons-curated', 'human-peps']:
                self.assertEqual(datasets.download_dataset(name, root, 1000, catalog=catalog, fetcher=lambda u,n:responses[u]), 1)
                self.assertTrue((root/name/'limit-1000/inventory.json').exists())
            with self.assertRaisesRegex(ValueError, 'gated'):
                datasets.download_dataset('sharechat', root, 1000)
