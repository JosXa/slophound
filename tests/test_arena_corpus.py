import hashlib
import json
import unittest
from unittest.mock import patch
from hound import arena_corpus as a


def row(text='自然について穏やかな説明です。', language='ja'):
    return dict(id='PRIVATE-ID', judge='PRIVATE-JUDGE', model_a='model-a', model_b='model-b', language=language,
                conversation_a=[dict(role='user', content='PRIVATE USER'), dict(role='assistant', content=text)],
                conversation_b=[dict(role='assistant', content='別の安全な回答です。')], openai_moderation={'flagged': False})


class ArenaTests(unittest.TestCase):
    def sample(self, rows, **kwargs):
        raw=('\n'.join(json.dumps(r, ensure_ascii=False) for r in rows)+'\n').encode()
        with patch.object(a, 'SOURCE_BYTES', len(raw)), patch.object(a, 'SOURCE_SHA256', hashlib.sha256(raw).hexdigest()):
            return a.sample_arena(kwargs.pop('limit', 100), fetch=lambda url, timeout: raw, **kwargs)

    def test_original_text_and_side_models(self):
        text='  日本語の回答。\n末尾も保存。  '
        result=self.sample([row(text)])
        self.assertIsNone(result['error'])
        self.assertEqual(result['records'][0]['text'].encode(), text.encode())
        self.assertEqual([(r['side'], r['model']) for r in result['records']], [('a','model-a'), ('b','model-b')])
        self.assertNotIn('PRIVATE', json.dumps(result))
        self.assertTrue(result['source']['pinned_native_snapshot'])

    def test_language_and_zero(self):
        self.assertEqual(len(self.sample([row(), row(language='en')], language='ja')['records']), 2)
        self.assertEqual(len(self.sample([row(), row(language='en')])['records']), 2)
        self.assertEqual(a.sample_arena(0, fetch=lambda *args: self.fail('fetched'))['records'], [])

    def test_hash_and_bounds(self):
        self.assertEqual(a.sample_arena(1, fetch=lambda *args, **kw: b'bad')['error']['code'], 'source_mismatch')
        for n in [-1, 10001, True, 1.2]:
            self.assertEqual(a.sample_arena(n)['error']['code'], 'invalid_limit')

    def test_flagged_and_sensitive(self):
        r=row(); r['openai_moderation']={'categories': {'violence': True}}
        self.assertEqual(self.sample([r])['records'], [])
        for text in ['mail x@example.org', '```python\nprint(1)\n```', '<think>secret</think>', '"quoted text"', 'api_key=abc123', '']:
            r=row(text); r['conversation_b']=[]
            self.assertEqual(self.sample([r])['records'], [], text)

    def test_tools_truncation_and_overlap(self):
        for extra in [{'tool_calls':[{}]}, {'truncated':True}, {'finish_reason':'length'}, {'thinking':'secret'}]:
            r=row(); r['conversation_b']=[]; r['conversation_a'][1].update(extra)
            self.assertEqual(self.sample([r])['records'], [])
        r=row('one two three four five six seven eight nine'); r['conversation_b']=[]
        r['conversation_a'][0]['content']='one two three four five six seven eight'
        self.assertEqual(self.sample([r])['records'], [])

    def test_screen_injection_and_dedup(self):
        calls=[]
        result=self.sample([row(),row()], screen=lambda text,others: calls.append((text,others)) or True)
        self.assertEqual(len(result['records']), 2)
        self.assertEqual(calls[0][1], ['PRIVATE USER'])
        self.assertEqual(self.sample([row()], screen=lambda t,o: False)['records'], [])
        r=row(); r['conversation_b']=r['conversation_a']; r['model_b']='other-model'
        self.assertEqual(len(self.sample([r])['records']), 2)

    def test_fetch_exception_redacted(self):
        result=a.sample_arena(1, fetch=lambda *args, **kw: (_ for _ in ()).throw(ValueError('PRIVATE')))
        self.assertEqual(result['error']['code'], 'fetch_failed')
        self.assertNotIn('PRIVATE', json.dumps(result))

if __name__ == '__main__': unittest.main()
