import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout
from hound import datasets, hf_corpora, arena_corpus, example_data
from tests.test_hf_pagination import fixture

class DynamicTests(unittest.TestCase):
    def setUp(self):
        notice = patch.object(datasets, 'fetch', return_value=b'Original dataset attribution and terms\r\n')
        notice.start()
        self.addCleanup(notice.stop)
    def test_sample_cache_bytes_limits_and_partial(self):
        fetch, calls = fixture(2)
        with tempfile.TemporaryDirectory() as tmp, patch.object(hf_corpora, '_fetch', fetch):
            self.assertEqual(datasets.download_dataset('wildchat', tmp, 3), 2)
            root = Path(tmp)/'wildchat/limit-3'
            inv = json.loads((root/'inventory.json').read_bytes())
            self.assertTrue(inv['partial'])
            self.assertEqual(inv['partial_reason'], 'exhausted')
            self.assertFalse(inv['sources'][0]['viewer_pinned_native_snapshot'])
            self.assertTrue(inv['sources'][0]['pages'][0]['response_sha256'])
            for doc in inv['documents']:
                self.assertEqual((root/doc['path']).read_bytes(), ('Independent abstract explanation number '+str(doc['row_index'])+'.').encode())
            self.assertNotIn('PRIVATE', ''.join(p.read_text() for p in root.rglob('*') if p.is_file()))
            before = len(calls)
            self.assertEqual(datasets.download_dataset('wildchat', tmp, 3), 2)
            self.assertEqual(len(calls), before)
            self.assertEqual(datasets.download_dataset('wildchat', tmp, 1), 1)
            self.assertTrue((Path(tmp)/'wildchat/limit-1/inventory.json').exists())
            docpath = root/inv['documents'][0]['path']
            docpath.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'hash|bytes'):
                datasets.download_dataset('wildchat', tmp, 3)
    def test_zero_error_no_files(self):
        for result in [{'records':[], 'source':{}, 'error':{'code':'zero_yield'}}, {'records':[], 'source':{}, 'error':{'code':'fetch_failed'}}]:
            with tempfile.TemporaryDirectory() as tmp, patch.object(hf_corpora, 'sample_dataset', return_value=result):
                with self.assertRaisesRegex(ValueError, result['error']['code']):
                    datasets.download_dataset('wildchat', tmp, 2)
                self.assertEqual(list(Path(tmp).iterdir()), [])
    def test_static_parameters_and_selection_order(self):
        failure = {'records':[], 'source':{}, 'error':{'code':'zero_yield'}}
        with tempfile.TemporaryDirectory() as tmp, patch.object(hf_corpora, 'sample_dataset', return_value=failure) as sample:
            with self.assertRaises(ValueError):
                datasets.download_dataset('wildchat', tmp, 10000)
            self.assertEqual(sample.call_args.args, (hf_corpora.WILDCHAT, 10000, 100000))
            with self.assertRaises(ValueError):
                datasets.download_dataset('wildchat', tmp, 10001)
        fetch, _ = fixture(2)
        from tests.test_example_data import fixture_catalog
        catalog, responses = fixture_catalog()
        with tempfile.TemporaryDirectory() as tmp, patch.object(hf_corpora, '_fetch', fetch):
            for name in ('wildchat', 'human-peps', 'wildchat'):
                kwargs = {} if name=='wildchat' else {'catalog':catalog, 'fetcher':lambda u,n:responses[u]}
                self.assertGreater(datasets.download_dataset(name, tmp, 1, **kwargs), 0)
    def test_symlink_before_sampling(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root/'link').symlink_to(root, target_is_directory=True)
            with patch.object(hf_corpora, 'sample_dataset', side_effect=AssertionError('network')):
                with self.assertRaisesRegex(ValueError, 'symlink'):
                    datasets.download_dataset('wildchat', root/'link', 1)
    def test_arena_allowlist(self):
        text = '  自然について穏やかな説明です。\r\n  '
        result = {'records':[{'text':text, 'model':'model-a', 'row_index':0, 'role':'assistant', 'private':'PRIVATE USER', 'reasoning':'PRIVATE REASONING'}], 'source':{'native_url':arena_corpus.SOURCE_URL, 'revision':arena_corpus.REVISION, 'source_sha256':arena_corpus.SOURCE_SHA256}, 'error':None}
        with tempfile.TemporaryDirectory() as tmp, patch.object(arena_corpus, 'sample_arena', return_value=result):
            self.assertEqual(datasets.download_dataset('llm-jp-arena', tmp, 2), 1)
            root = Path(tmp)/'llm-jp-arena/limit-2'
            inv = json.loads((root/'inventory.json').read_bytes())
            self.assertEqual((root/inv['documents'][0]['path']).read_bytes(), text.encode())
            self.assertNotIn('PRIVATE', (root/'inventory.json').read_text())
    def test_cli_partial(self):
        fetch, _ = fixture(1)
        with tempfile.TemporaryDirectory() as tmp, patch.object(hf_corpora, '_fetch', fetch), redirect_stdout(io.StringIO()) as out:
            self.assertEqual(example_data.main(['--dataset','wildchat','--limit','3','--output-dir',tmp]), 0)
            self.assertIn('partial', out.getvalue())
            self.assertIn('exhausted', out.getvalue())
