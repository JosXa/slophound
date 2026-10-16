import unittest,json,hashlib
from hound import hf_corpora as h
W='allenai/WildChat-4.8M';N='nebius/SWE-rebench-openhands-trajectories'
def row(text='An independent explanation of abstract concepts.',model='future-model-2099'):
 return {'model':model,'language':'English','toxic':False,'redacted':False,'conversation':[{'role':'user','content':'PRIVATE_INPUT','toxic':False,'redacted':False},{'role':'assistant','content':text,'language':'English','toxic':False,'redacted':False}]}
class Tests(unittest.TestCase):
 def test_assistant_model_hash_locator(self):
  r=h.parse_rows(W,[{'row_idx':12,'row':row()}],limit=3,max_rows=3)['records'][0]
  self.assertEqual(r['model'],'future-model-2099');self.assertEqual(r['row_index'],12);self.assertEqual(r['turn_index'],1)
  self.assertEqual(r['text_sha256'],hashlib.sha256(r['text'].encode()).hexdigest());self.assertNotIn('PRIVATE_INPUT',json.dumps(r));self.assertEqual(r['role_source'],'conversation[1].role')
 def test_filters(self):
  for text in ['Contact x@example.org','api_key=abcdefgh123456','```python\nprint(1)\n```','"borrowed quotation here"','Call +1 212 555 0199','My name is Alice Smith.']:
   self.assertEqual(h.parse_rows(W,[row(text)],3,3)['error']['code'],'zero_yield')
  r=row();r['redacted']=True;self.assertFalse(h.parse_rows(W,[r],3,3)['records'])
 def test_verbatim(self):
  r=row('These eight words are copied directly from another input.');r['conversation'][0]['content']=r['conversation'][1]['content'];self.assertFalse(h.parse_rows(W,[r],3,3)['records'])
 def test_bounds_dedup_language(self):
  self.assertEqual(len(h.parse_rows(W,[row(),row()],3,3)['records']),1)
  self.assertFalse(h.parse_rows(W,[row()],3,3,language='Japanese')['records'])
  with self.assertRaises(ValueError):h.parse_rows(W,[],0,3)
  with self.assertRaises(ValueError):h.parse_rows(W,[],3,100001)
 def test_nebius_role_card_model(self):
  r={'trajectory':[{'role':'system','content':'SYSTEM'},{'role':'tool','content':'TOOL'},{'role':'assistant','content':'I will inspect the failing behavior carefully.','tool_calls':None}]}
  out=h.parse_rows(N,[r],3,3)['records'][0];self.assertEqual(out['model'],'Qwen/Qwen3-Coder-480B-A35B-Instruct');self.assertEqual(out['model_source'],'dataset_card');self.assertEqual(out['source_kind'],'benchmark_run_agent');self.assertEqual(out['turn_index'],2)
 def test_truncated_missing_model_schema(self):
  wrapped={'row':row(),'truncated_cells':['conversation']};self.assertFalse(h.parse_rows(W,[wrapped],3,3)['records'])
  r=row();del r['model'];self.assertFalse(h.parse_rows(W,[r],3,3)['records'])
  self.assertEqual(h.parse_rows(N,[{'conversation':[]}],3,3)['error']['code'],'zero_yield')
 def test_fetch_hash_revision(self):
  payload=json.dumps({'rows':[{'row_idx':0,'row':row()}]}).encode();calls=[]
  def fetch(url,timeout,max_bytes):
   calls.append(url);return payload if '/rows?' in url else b'{"sha":"abc"}'
  out=h.sample_dataset(W,3,3,fetch=fetch);self.assertEqual(len(calls),3);self.assertEqual(out['source']['source_response_sha256'],hashlib.sha256(payload).hexdigest());self.assertFalse(out['source']['viewer_pinned_native_snapshot']);self.assertEqual(out['source']['observed_repo_revision_before'],'abc')
 def test_revision_change(self):
  count=[0]
  def fetch(url,timeout,max_bytes):
   count[0]+=1
   return json.dumps({'rows':[{'row':row()}]}).encode() if '/rows?' in url else json.dumps({'sha':str(count[0])}).encode()
  out=h.sample_dataset(W,3,3,fetch=fetch);self.assertFalse(out['records']);self.assertEqual(out['error']['code'],'revision_changed')
 def test_unavailable_and_byte_bound(self):
  self.assertEqual(h.sample_dataset('llm-jp/llm-jp-chatbot-arena-conversations',3,3)['error']['code'],'manual_unavailable')
  out=h.sample_dataset(W,3,3,fetch=lambda *a,**kw:b'x'*4000001);self.assertEqual(out['error']['code'],'byte_bound')
if __name__=='__main__':unittest.main()
