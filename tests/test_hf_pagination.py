import unittest,json,urllib.parse
from unittest.mock import patch
from hound import hf_corpora as h
from tests.test_hf_corpora import row

def fixture(total=250,duplicate=False):
 calls=[]
 def fetch(url,timeout,max_bytes):
  calls.append(url)
  if '/rows?' not in url:return b'{"sha":"stable"}'
  q=urllib.parse.parse_qs(urllib.parse.urlsplit(url).query);offset=int(q['offset'][0]);length=int(q['length'][0])
  rows=[{'row':row('Independent abstract explanation number '+str(i if not duplicate else i%3)+'.')} for i in range(offset,min(total,offset+length))]
  return json.dumps({'rows':rows,'num_rows_total':total}).encode()
 return fetch,calls

class Pagination(unittest.TestCase):
 def test_over_hundred_absolute_and_complete(self):
  fetch,calls=fixture();out=h.sample_dataset(h.WILDCHAT,125,200,fetch=fetch)
  self.assertEqual(len(out['records']),125);self.assertEqual(out['records'][-1]['row_index'],124)
  self.assertFalse(out['partial']);self.assertEqual(len(out['source']['pages']),2);self.assertEqual(len(calls),4)
 def test_dedup_exhaustion(self):
  fetch,_=fixture(105,True);out=h.sample_dataset(h.WILDCHAT,110,200,fetch=fetch)
  self.assertEqual(len(out['records']),3);self.assertTrue(out['partial']);self.assertEqual(out['partial_reason'],'exhausted')
 def test_page_request_bounds(self):
  for kwargs,reason in [({'max_pages':1},'page_bound'),({'max_requests':3},'request_bound')]:
   fetch,calls=fixture();out=h.sample_dataset(h.WILDCHAT,150,200,fetch=fetch,**kwargs)
   self.assertEqual(len(out['records']),100);self.assertEqual(out['partial_reason'],reason);self.assertEqual(len(calls),3)
 def test_aggregate_bytes(self):
  fetch,calls=fixture();out=h.sample_dataset(h.WILDCHAT,150,200,fetch=fetch,max_total_bytes=100)
  self.assertFalse(out['records']);self.assertEqual(out['error']['code'],'byte_bound')
 def test_time(self):
  fetch,calls=fixture()
  with patch.object(h.time,'monotonic',side_effect=[0,0,301,301,301,301,301,301]):
   out=h.sample_dataset(h.WILDCHAT,150,200,fetch=fetch)
  self.assertFalse(out['records']);self.assertEqual(out['error']['code'],'time_bound')
 def test_reasoning_rejected(self):
  for text in ['<think>Private reasoning</think>Final text.', 'analysis: Hidden reasoning\nfinal: Answer', '<analysis>hidden</analysis>', '[analysis] hidden']:
   self.assertFalse(h.parse_rows(h.WILDCHAT,[row(text)],3,3)['records'])
 def test_verbatim_unicode_whitespace(self):
  text='  Complete prose café.\n\nNo rewriting.  '
  fetch,_=fixture(2)
  def custom(url,timeout,max_bytes):
   if '/rows?' not in url:return b'{"sha":"stable"}'
   return json.dumps({'rows':[{'row':row(text)}]}).encode()
  out=h.sample_dataset(h.WILDCHAT,1,3,fetch=custom,start_offset=42)
  self.assertEqual(out['records'][0]['text'].encode(),text.encode());self.assertEqual(out['records'][0]['row_index'],42)
 def test_thousand_records(self):
  fetch,_=fixture(1500);out=h.sample_dataset(h.WILDCHAT,1000,1200,fetch=fetch)
  self.assertEqual(len(out['records']),1000);self.assertEqual(len(out['source']['pages']),10)
 def test_explicit_analysis_channel(self):
  r=row('Hidden reasoning without an inline marker.');r['conversation'][1]['channel']='analysis'
  self.assertFalse(h.parse_rows(h.WILDCHAT,[r],3,3)['records'])
 def test_large_valid_bounds(self):
  self.assertEqual(h.parse_rows(h.WILDCHAT,[],10000,100000)['error']['code'],'zero_yield')

if __name__=='__main__':unittest.main()
