"""Bounded assistant-only HF viewer adapters. Standard library; no disk writes.
Viewer rows are NOT a revision-pinned native snapshot. Regex screening is a
conservative heuristic, not proof of privacy, originality or license clearance.
fetch(url, timeout=seconds, max_bytes=n) -> bytes is injectable for offline tests.
"""
import hashlib
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

WILDCHAT='allenai/WildChat-4.8M'
NEBIUS='nebius/SWE-rebench-openhands-trajectories'
LLMJP='llm-jp/llm-jp-chatbot-arena-conversations'
MAX_BYTES=4_000_000
MAX_TEXT_BYTES=100_000
MAX_SECONDS=90
SUPPORTED=(WILDCHAT,NEBIUS)

# Reject whole assistant text, never redact/rewrite/truncate.
UNSAFE=re.compile(r'''(?ix)
 [\w.+-]+@[\w.-]+\.[a-z]{2,} | https?:// | www\. |
 \b(?:sk-|ghp_|github_pat_|AKIA)[a-z0-9_-]{8,} |
 \b(?:password|passwd|api[_ -]?key|access[_ -]?token|secret|authorization)\s*[:=] |
 -----BEGIN\s+.*PRIVATE\s+KEY | \b(?:\d{1,3}\.){3}\d{1,3}\b |
 (?:\+?\d[\d ()-]{8,}\d) | \b\d{3}-\d{2}-\d{4}\b |
 \b(?:my\s+name\s+is|my\s+address|date\s+of\s+birth|i\s+live\s+at)\b |
 \b\d+\s+\w+\s+(?:street|avenue|road|lane|drive)\b |
 \[\s*(?:redacted|removed|pii)\s*\] | <(?:redacted|pii)> |
 ``` | ^\s*> | [“”] | \"[^\"\n]{12,}\" |
 \b(?:copyright|all\s+rights\s+reserved|verbatim|lyrics|excerpt|quoted|quotation)\b |
 \b(?:fuck|shit|nigger|faggot)\w* |
 (?:^|\n)\s*(?:def\s+\w+|class\s+\w+|import\s+\w+|diff\s+--git|@@)
''',re.M)

REASONING=re.compile(r'(?im)</?(?:think|analysis|reasoning)\b|\[(?:analysis|reasoning)\]|^\s*(?:analysis|reasoning)\s*:|<\|(?:analysis|channel)\|>')

def _bounds(limit,max_rows):
    if type(limit) is not int or not 1<=limit<=10000: raise ValueError('limit must be 1..10000')
    if type(max_rows) is not int or not 1<=max_rows<=100000: raise ValueError('max_rows must be 1..100000')

def _error(code,message,source=None):
    return {'records':[],'source':source or {},'error':{'code':code,'message':message}}

def _flagged(value):
    if isinstance(value,dict):
        if any(value.get(k) is True for k in ('toxic','redacted','flagged')): return True
        if isinstance(value.get('categories'),dict) and any(x is True for x in value['categories'].values()): return True
        return any(_flagged(v) for v in value.values() if isinstance(v,(dict,list)))
    if isinstance(value,list):return any(_flagged(v) for v in value)
    return False

def _words(text):return re.findall(r'\w+',text.lower())

def _copied(text,others):
    words=_words(text)
    if len(words)<8:return False
    grams={tuple(words[i:i+8]) for i in range(len(words)-7)}
    for other in others:
        w=_words(other)
        if any(tuple(w[i:i+8]) in grams for i in range(len(w)-7)):return True
    return False

def _language_equal(actual,wanted):
    aliases={'en':'english','ja':'japanese'}
    norm=lambda x:aliases.get(str(x).lower(),str(x).lower())
    return norm(actual)==norm(wanted)

def parse_rows(dataset_id,rows,limit=3,max_rows=100,language=None):
    """Parse viewer envelopes or plain row dicts; fixtures must be synthetic.
    Preserves exact complete content. Unknown roles, tool args and row metadata
    never become text. Excludes assistant turns carrying tool calls (mixed action).
    """
    _bounds(limit,max_rows)
    if dataset_id not in SUPPORTED:return _error('manual_unavailable','No verified viewer adapter for this source.')
    records=[];seen=set();examined=0;rejected=0;start=time.monotonic();counts={}
    def reject(reason):counts[reason]=counts.get(reason,0)+1
    field='conversation' if dataset_id==WILDCHAT else 'trajectory'
    for position,wrapped in enumerate(rows):
        if examined>=max_rows or len(records)>=limit:break
        if time.monotonic()-start>MAX_SECONDS:break
        examined+=1
        if not isinstance(wrapped,dict):rejected+=1;continue
        if wrapped.get('truncated_cells'):rejected+=1;continue
        row=wrapped.get('row',wrapped)
        if not isinstance(row,dict) or _flagged(row):rejected+=1;continue
        turns=row.get(field)
        if not isinstance(turns,list) or len(turns)>1000:rejected+=1;continue
        model=row.get('model') if dataset_id==WILDCHAT else 'Qwen/Qwen3-Coder-480B-A35B-Instruct'
        if not isinstance(model,str) or not model.strip() or len(model)>200 or UNSAFE.search(model):rejected+=1;continue
        index=wrapped.get('row_idx',position)
        if type(index) is not int or index<0:rejected+=1;continue
        # Non-assistant text is used only transiently for overlap rejection.
        others=[t['content'] for t in turns if isinstance(t,dict) and t.get('role')!='assistant' and isinstance(t.get('content'),str)]
        if sum(len(t.encode()) for t in others)>MAX_BYTES:rejected+=1;continue
        for turn_index,turn in enumerate(turns):
            if len(records)>=limit:break
            if not isinstance(turn,dict) or turn.get('role')!='assistant':continue
            text=turn.get('content');lang=turn.get('language',row.get('language'))
            if language is not None and not _language_equal(lang,language):continue
            if not isinstance(text,str) or not text.strip() or len(text.encode())>MAX_TEXT_BYTES:rejected+=1;reject('empty_or_size_or_content_schema');continue
            if any(turn.get(k) for k in ('tool_calls','function_call','reasoning','reasoning_content','thinking','truncated','is_truncated')) or turn.get('finish_reason') in ('length','max_tokens','tool_calls','function_call'):rejected+=1;reject('incomplete_or_tool_or_reasoning');continue
            if _flagged(turn):rejected+=1;reject('privacy_flag');continue
            if REASONING.search(text) or turn.get('channel') in ('analysis','reasoning','commentary'):rejected+=1;reject('reasoning_marker');continue
            if UNSAFE.search(text):rejected+=1;reject('conservative_privacy_prose_screen');continue
            if _copied(text,others):rejected+=1;reject('nonassistant_overlap');continue
            digest=hashlib.sha256(text.encode('utf-8')).hexdigest()
            if digest in seen:continue
            seen.add(digest)
            records.append({'text':text,'text_sha256':digest,'dataset_id':dataset_id,'config':'default','split':'train','row_index':index,'turn_index':turn_index,'role':'assistant','role_source':f'{field}[{turn_index}].role','text_source':f'{field}[{turn_index}].content','model':model,'model_source':'row.model' if dataset_id==WILDCHAT else 'dataset_card','language':lang if isinstance(lang,str) and len(lang)<40 else None,'source_kind':'captured_conversation' if dataset_id==WILDCHAT else 'benchmark_run_agent'})
    out={'records':records,'source':{'dataset_id':dataset_id,'rows_examined':examined,'rejected_candidates_or_rows':rejected,'rejection_counts':dict(counts,other_row_schema_or_flags=rejected-sum(counts.values()))},'error':None}
    if not records:out['error']={'code':'zero_yield','message':'No complete assistant text passed role, schema, language and conservative screening within the row bound.'}
    return out

def _fetch(url,timeout=30,max_bytes=MAX_BYTES):
    # urllib makes no automatic retry; refuse redirects to keep request bounds.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs):return None
    request=urllib.request.Request(url,headers={'User-Agent':'slophound-local-assistant-sampler/1'})
    with urllib.request.build_opener(NoRedirect).open(request,timeout=timeout) as response:
        data=response.read(max_bytes+1)
    if len(data)>max_bytes:raise ValueError('response exceeds byte bound')
    return data

class _Budget(Exception):
    pass

def sample_dataset(dataset_id,limit,max_rows,language=None,*,fetch=None,
                   max_pages=50,max_requests=52,max_seconds=300,
                   max_total_bytes=64*1024*1024,page_size=None,start_offset=0):
    """Finite best-effort pagination, never a guaranteed limit or native pin.
    Budgets include both revision observations; no retries or response clipping.
    A partial nonempty result contains complete accepted texts only. Failures to
    observe matching revisions discard all records. Raw rows never reach disk.
    """
    _bounds(limit,max_rows)
    for key,value,ceiling in [('max_pages',max_pages,50),('max_requests',max_requests,52),('max_total_bytes',max_total_bytes,64*1024*1024)]:
        if type(value) is not int or not 1<=value<=ceiling:raise ValueError(key+' outside finite bound')
    if not isinstance(max_seconds,(int,float)) or isinstance(max_seconds,bool) or not 0<max_seconds<=300:raise ValueError('max_seconds must be >0 and <=300')
    if max_requests<3:raise ValueError('max_requests must allow before/page/after')
    if type(start_offset) is not int or start_offset<0:raise ValueError('invalid start_offset')
    cap=3 if dataset_id==NEBIUS else 100
    page_size=cap if page_size is None else page_size
    if type(page_size) is not int or not 1<=page_size<=cap:raise ValueError('page_size outside dataset bound')
    if dataset_id not in SUPPORTED:return _error('manual_unavailable','No verified viewer adapter for this source.',{'dataset_id':dataset_id})
    fetch=fetch or _fetch;start=time.monotonic()
    source={'dataset_id':dataset_id,'viewer_pinned_native_snapshot':False,'snapshot_caveat':'Before/after repo revisions are observations only; viewer is not a native revision-pinned snapshot.','config':'default','split':'train','pages':[],'requests':0,'response_bytes':0,'rows_examined':0,'rejected_candidates_or_rows':0,'rejection_counts':{},'bounds':{'limit':limit,'max_rows':max_rows,'max_pages':max_pages,'max_requests':max_requests,'max_seconds':max_seconds,'max_total_bytes':max_total_bytes,'page_size':page_size,'start_offset':start_offset}}
    api='https://huggingface.co/api/datasets/'+dataset_id
    def get(url):
        remaining=max_seconds-(time.monotonic()-start)
        if remaining<=0:raise _Budget('time_bound')
        if source['requests']>=max_requests:raise _Budget('request_bound')
        available=min(MAX_BYTES,max_total_bytes-source['response_bytes'])
        if available<=0:raise _Budget('byte_bound')
        source['requests']+=1
        raw=fetch(url,timeout=min(30,remaining),max_bytes=available)
        if not isinstance(raw,bytes):raise ValueError('not bytes')
        source['response_bytes']+=len(raw)
        if len(raw)>available:raise _Budget('byte_bound')
        if time.monotonic()-start>=max_seconds:raise _Budget('time_bound')
        return raw,json.loads(raw)
    records=[];seen=set();offset=start_offset;reason=None
    try:
        _,before=get(api);source['observed_repo_revision_before']=before.get('sha')
        if not before.get('sha'):return _error('revision_unavailable','Missing initial revision observation.',source)
        while len(records)<limit:
            if len(source['pages'])>=max_pages:reason='page_bound';break
            if source['requests']>=max_requests-1:reason='request_bound';break
            if source['rows_examined']>=max_rows:reason='row_bound';break
            length=min(page_size,max_rows-source['rows_examined'])
            url='https://datasets-server.huggingface.co/rows?'+urllib.parse.urlencode({'dataset':dataset_id,'config':'default','split':'train','offset':offset,'length':length})
            raw,page=get(url)
            digest=hashlib.sha256(raw).hexdigest()
            source['pages'].append({'url':url,'response_sha256':digest,'offset':offset,'requested_rows':length})
            source['source_response_sha256']=digest;source['viewer_url']=url
            rows=page.get('rows')
            if not isinstance(rows,list):return _error('schema_unavailable','Viewer has no row list.',source)
            if len(rows)>length:return _error('row_bound_exceeded','Viewer exceeded page bound.',source)
            normalized=[]
            for pos,wrapped in enumerate(rows):
                if not isinstance(wrapped,dict):normalized.append(wrapped);continue
                if 'row' in wrapped:
                    wrapped=dict(wrapped);wrapped.setdefault('row_idx',offset+pos)
                else:wrapped={'row':wrapped,'row_idx':offset+pos}
                if wrapped.get('row_idx')!=offset+pos:return _error('schema_unavailable','Unexpected absolute row locator.',source)
                normalized.append(wrapped)
            # Parse every candidate in the page so duplicates cannot hide later
            # unique texts behind a per-page quota.
            result=parse_rows(dataset_id,normalized,10000,length,language)
            if time.monotonic()-start>=max_seconds:raise _Budget('time_bound')
            if result['source']['rows_examined']<len(rows):raise _Budget('parser_bound')
            source['rows_examined']+=len(rows)
            source['rejected_candidates_or_rows']+=result['source']['rejected_candidates_or_rows']
            for key,count in result['source']['rejection_counts'].items():source['rejection_counts'][key]=source['rejection_counts'].get(key,0)+count
            for record in result['records']:
                if record['text_sha256'] in seen:continue
                seen.add(record['text_sha256'])
                record.update(source_response_sha256=digest,viewer_url=url,observed_repo_revision=before['sha'],viewer_pinned_native_snapshot=False)
                records.append(record)
                if len(records)>=limit:break
            offset+=len(rows)
            total=page.get('num_rows_total')
            if len(rows)<length or (type(total) is int and offset>=total):reason='exhausted';break
        _,after=get(api);source['observed_repo_revision_after']=after.get('sha')
        if not after.get('sha'):return _error('revision_unavailable','Missing final revision observation.',source)
        if before['sha']!=after['sha']:return _error('revision_changed','Repository revision changed across observations.',source)
        if not records:return _error('zero_yield','No complete eligible assistant prose within sampling bounds.',source)|{'partial':True,'partial_reason':reason or 'zero_yield'}
        return {'records':records,'source':source,'error':None,'partial':len(records)<limit,'partial_reason':reason if len(records)<limit else None}
    except _Budget as exc:
        return _error(str(exc),'Finite sampling budget reached; records discarded without completed revision observation.',source)
    except Exception as exc:
        return _error('fetch_failed','Bounded fetch/parsing failed: '+type(exc).__name__,source)
