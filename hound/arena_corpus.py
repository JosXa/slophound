"""Pinned native Arena assistant-only sampler; raw source lives only in memory.

fetch injection contract: fetch(url, timeout=30) -> bytes. screen(text, user_texts)
returns True to retain. Outputs remain subject to respective model licences;
user prompts (CC BY 4.0) are never exported. No automatic retries or disk cache.
"""
import hashlib
import json
import re
import time
import urllib.request
from .hf_corpora import UNSAFE, REASONING, MAX_TEXT_BYTES

DATASET_ID = 'llm-jp/llm-jp-chatbot-arena-conversations'
REVISION = '41d630bccb230db0c4b0492fe8e1a49a483a0e1b'
SOURCE_URL = f'https://huggingface.co/datasets/{DATASET_ID}/resolve/{REVISION}/conversations.jsonl'
SOURCE_BYTES = 5896520
SOURCE_SHA256 = 'f3e70f73f189a93a36ed1d4596f4faa3aeb7053ff750c571f24d08e437d1b69a'
MAX_LIMIT = 10000
# Intentionally conservative: this is a screening heuristic, not a PII guarantee.
_UNSAFE = re.compile(r'[@]|https?://|\b(?:api[_ -]?key|password|secret|token|bearer|ssh-rsa|AKIA[A-Z0-9]+)\b|\b(?:\d[ -]?){7,}\b|```|`|<\/?(?:think|thinking|analysis)>|\b(?:def |import |function |console\.|SELECT .+ FROM|chain.of.thought|let.s think|step.by.step)\b|["“”「」『』]|^\s*>', re.I | re.M)


def conservative_screen(text, others):
    if len(text.encode('utf-8')) > MAX_TEXT_BYTES or _UNSAFE.search(text) or UNSAFE.search(text) or REASONING.search(text):
        return False
    words = re.findall(r'\w+', text.casefold())
    grams = {tuple(words[i:i+8]) for i in range(max(0, len(words)-7))}
    for other in others:
        w = re.findall(r'\w+', other.casefold())
        if any(tuple(w[i:i+8]) in grams for i in range(max(0, len(w)-7))):
            return False
    return True


def _fetch(url, timeout=30):
    deadline = time.monotonic() + timeout
    with urllib.request.urlopen(url, timeout=timeout) as response:
        chunks = []
        size = 0
        while True:
            if time.monotonic() >= deadline:
                raise TimeoutError()
            chunk = response.read(65536)
            if not chunk:
                return b''.join(chunks)
            chunks.append(chunk)
            size += len(chunk)
            if size > SOURCE_BYTES:
                raise ValueError('oversized source')


def _flagged(value):
    if isinstance(value, dict):
        return any(_flagged(v) for k, v in value.items() if k not in ('category_scores', 'scores'))
    if isinstance(value, list):
        return any(_flagged(v) for v in value)
    return value is True


def _incomplete(item):
    return (any(item.get(k) for k in ('truncated', 'is_truncated', 'tool_calls', 'function_call', 'thinking', 'reasoning', 'reasoning_content'))
            or item.get('finish_reason') in ('length', 'max_tokens', 'tool_calls', 'function_call'))


def sample_arena(limit, language=None, *, screen=None, fetch=None):
    source = {'native_url': SOURCE_URL, 'revision': REVISION, 'source_sha256': SOURCE_SHA256,
              'bytes': SOURCE_BYTES, 'pinned_native_snapshot': True}
    result = {'records': [], 'source': source, 'error': None}
    def fail(code):
        result['records'] = []
        result['error'] = {'code': code}
        return result
    if type(limit) is not int or not 0 <= limit <= MAX_LIMIT:
        return fail('invalid_limit')
    if language is not None and not isinstance(language, str):
        return fail('invalid_language')
    if not limit:
        return result
    try:
        raw = (fetch or _fetch)(SOURCE_URL, timeout=30)
    except Exception:
        return fail('fetch_failed')
    if not isinstance(raw, bytes) or len(raw) != SOURCE_BYTES or hashlib.sha256(raw).hexdigest() != SOURCE_SHA256:
        return fail('source_mismatch')
    try:
        rows = [json.loads(line) for line in raw.decode('utf-8').splitlines() if line.strip()]
    except (ValueError, UnicodeError):
        return fail('invalid_source')
    del raw
    screening = screen or conservative_screen
    seen = set()
    for row_index, row in enumerate(rows):
        if not isinstance(row, dict):
            return fail('invalid_source')
        if _flagged(row.get('openai_moderation')) or _incomplete(row):
            continue
        lang = row.get('language')
        if language is not None and (not isinstance(lang, str) or lang.casefold() != language.casefold()):
            continue
        conversations = [row.get('conversation_a', []), row.get('conversation_b', [])]
        others = [m['content'] for c in conversations if isinstance(c, list) for m in c
                  if isinstance(m, dict) and m.get('role') == 'user' and isinstance(m.get('content'), str)]
        for side, conversation in zip(('a', 'b'), conversations):
            model = row.get('model_' + side)
            if not isinstance(model, str) or not model or len(model)>200 or UNSAFE.search(model) or not isinstance(conversation, list):
                continue
            for turn_index, message in enumerate(conversation):
                if not isinstance(message, dict) or message.get('role') != 'assistant' or _incomplete(message):
                    continue
                text = message.get('content')
                if not isinstance(text, str) or not text.strip():
                    continue
                try:
                    encoded = text.encode('utf-8')
                    if not screening(text, others):
                        continue
                except Exception:
                    return fail('screen_failed')
                digest = hashlib.sha256(encoded).hexdigest()
                if (model, digest) in seen:
                    continue
                seen.add((model, digest))
                result['records'].append({'text': text, 'text_sha256': digest, 'dataset_id': DATASET_ID,
                    'row_index': row_index, 'side': side, 'turn_index': turn_index, 'model': model,
                    'model_source': 'model_' + side, 'language': lang, 'role': 'assistant',
                    'source_kind': 'native_jsonl', 'provenance': {'revision': REVISION, 'source_sha256': SOURCE_SHA256}})
                if len(result['records']) >= limit:
                    return result
    return result
