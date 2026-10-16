"""Offline downloader contracts; fixture prose is never a shipped example."""
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import subprocess
import unittest
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import patch
from hound import cli, example_data


def digest(data):
    return hashlib.sha256(data).hexdigest()


def fixture_catalog():
    text = 'The worker checks the recorded result before continuing. ' * 4 + '\r\n'
    rows = [
        {'type': 'user', 'message': {'role': 'user', 'content': 'PRIVATE USER TEXT'}},
        {'type': 'assistant', 'message': {'role': 'assistant', 'id': 'm1', 'model': 'claude-test', 'content': [{'type': 'text', 'text': text}]}},
        {'type': 'assistant', 'message': {'role': 'assistant', 'id': 'm1', 'model': 'claude-test', 'content': [{'type': 'thinking', 'thinking': 'PRIVATE THINKING'}]}},
    ]
    raw = ('\n'.join(json.dumps(r) for r in rows)).encode()
    human = b'Human original\r\n\xc3\xa9\n'
    notice = b'License notice\r\n'
    source = 'sessions/claude_code/test.jsonl'
    sources = [{'source_path': source, 'source_url': 'https://example.test/ai', 'sha256': digest(raw), 'bytes': len(raw)}, {'source_path': 'pep.txt', 'source_url': 'https://example.test/human', 'sha256': digest(human), 'bytes': len(human)}]
    docs = [{'path': 'ai/test/message.md', 'source_path': source, 'sha256': digest(text.encode()), 'bytes': len(text.encode()), 'authorship': 'recorded-assistant-output', 'model': 'claude-test', 'text_line': 2, 'message_locator': {'jsonl_lines': [2, 3], 'message_id': 'm1', 'text_block_index': 0}}, {'path': 'human/pep.txt', 'source_path': 'pep.txt', 'sha256': digest(human), 'bytes': len(human), 'authorship': 'human-authored'}]
    catalog = {'schema_version': 1, 'sources': sources, 'documents': docs, 'notices': [{'path': 'notices/license.md', 'source_url': 'https://example.test/notice', 'sha256': digest(notice), 'bytes': len(notice)}]}
    return catalog, {sources[0]['source_url']: raw, sources[1]['source_url']: human, 'https://example.test/notice': notice}


class ExampleDataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.catalog, self.responses = fixture_catalog()

    def fetch(self, url, limit):
        return self.responses[url]

    def no_fetch(self, *args):
        self.fail('Unexpected network request')

    def test_cli_routes_before_lint_auth(self):
        previous = os.getcwd()
        out = io.StringIO()
        try:
            os.chdir(self.root)
            with patch.object(example_data, 'load_catalog', return_value=self.catalog), patch.object(example_data, 'fetch', side_effect=self.fetch), patch.object(cli, 'load_rules', side_effect=AssertionError('lint')), patch.object(cli, 'Engine', side_effect=AssertionError('NLP')), patch.object(cli, 'auth_main', side_effect=AssertionError('auth')), redirect_stdout(out):
                self.assertEqual(cli.main(['get-corpus']), 0)
        finally:
            os.chdir(previous)
        self.assertTrue((self.root / '.slophound/example-data/inventory.json').exists())
        self.assertIn('2 examples', out.getvalue())

    def test_packaged_catalog_counts(self):
        from importlib.resources import files
        self.assertLess(len(files('hound').joinpath('example_catalog.json').read_bytes()), 150_000)
        catalog = example_data.load_catalog()
        self.assertEqual(len(catalog['documents']), 168)
        self.assertEqual(sum(d['authorship'] == 'recorded-assistant-output' for d in catalog['documents']), 166)
        humans = [d for d in catalog['documents'] if d['authorship'] == 'human-authored']
        self.assertEqual({d['source_path'] for d in humans}, {'pep-0020.txt', 'pep-0257.txt'})
        self.assertTrue(all(d['revision'] == '475d6cdf8caf61cfe02ec527f84d9489566349e6' for d in humans))

    def test_bytes_privacy_offline_cache(self):
        self.assertEqual(example_data.download(self.root, self.catalog, self.fetch), 2)
        self.assertEqual((self.root / 'human/pep.txt').read_bytes(), self.responses['https://example.test/human'])
        self.assertTrue((self.root / 'ai/test/message.md').read_bytes().endswith(b'\r\n'))
        self.assertFalse(any(b'PRIVATE' in p.read_bytes() for p in self.root.rglob('*') if p.is_file()))
        self.assertEqual(example_data.download(self.root, self.catalog, self.no_fetch), 2)
        (self.root / 'human/pep.txt').write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError, 'hash|bytes'):
            example_data.download(self.root, self.catalog, self.no_fetch)
        self.assertEqual((self.root / 'human/pep.txt').read_bytes(), b'corrupt')

    def test_failure_never_reports_partial_success(self):
        for failure in ['network', 'source-hash', 'sample-hash', 'notice-hash', 'multiple-blocks']:
            with self.subTest(failure=failure):
                catalog, responses = fixture_catalog()
                if failure == 'source-hash': responses['https://example.test/ai'] += b' '
                if failure == 'sample-hash': catalog['documents'][0]['sha256'] = '0' * 64
                if failure == 'notice-hash': responses['https://example.test/notice'] += b'x'
                if failure == 'multiple-blocks':
                    rows = [json.loads(x) for x in responses['https://example.test/ai'].splitlines()]
                    rows[2]['message']['content'].append({'type': 'text', 'text': 'second block'})
                    raw = b'\n'.join(json.dumps(r).encode() for r in rows)
                    responses['https://example.test/ai'] = raw
                    catalog['sources'][0].update(sha256=digest(raw), bytes=len(raw))
                def fetch(url, limit):
                    if failure == 'network': raise OSError('network unavailable')
                    return responses[url]
                with self.assertRaises((ValueError, OSError)):
                    example_data.download(self.root, catalog, fetch)
                self.assertFalse(list(self.root.rglob('*')))

    def test_catalog_paths_rejected(self):
        for path in ['../escape', '/absolute', 'ai/../escape', 'ai\\escape', 'human//x']:
            with self.subTest(path=path):
                catalog = copy.deepcopy(self.catalog)
                catalog['documents'][0]['path'] = path
                with self.assertRaisesRegex(ValueError, 'path'):
                    example_data.download(self.root, catalog, self.no_fetch)

    def test_symlink_guard(self):
        outside = self.root / 'outside'; outside.mkdir()
        root = self.root / 'root'; root.mkdir()
        (root / 'ai').symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            example_data.download(root, self.catalog, self.no_fetch)
        self.assertFalse(list(outside.iterdir()))

    def test_default_output_is_ignored_from_subdirectories(self):
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        ignore = Path(__file__).resolve().parents[1] / ".gitignore"
        (self.root / ".gitignore").write_bytes(ignore.read_bytes())
        for name in [".slophound/example-data/inventory.json", "docs/.slophound/example-data/inventory.json"]:
            with self.subTest(name=name):
                result = subprocess.run(["git", "check-ignore", name], cwd=self.root, capture_output=True)
                self.assertEqual(result.returncode, 0)

    def test_fetch_bounded(self):
        test = self
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, limit):
                test.assertEqual(limit, 4)
                return b'1234'
        with patch('urllib.request.urlopen', return_value=Response()) as open_url:
            with self.assertRaisesRegex(ValueError, 'bound'):
                example_data.fetch('https://example.test/source', 3)
        self.assertGreater(open_url.call_args.kwargs['timeout'], 0)
        self.assertLessEqual(open_url.call_args.kwargs['timeout'], 30)

    def test_cli_failure_exit(self):
        err = io.StringIO()
        with patch.object(example_data, 'load_catalog', return_value=self.catalog), patch.object(example_data, 'fetch', side_effect=OSError('offline')), redirect_stderr(err):
            self.assertEqual(cli.main(['get-corpus', '--output-dir', str(self.root)]), 2)
        self.assertIn('offline', err.getvalue())
        self.assertFalse(list(self.root.iterdir()))
