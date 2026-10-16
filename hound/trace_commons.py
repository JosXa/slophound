"""Pinned Trace Commons privacy filter and complete native-message extraction."""
from collections import defaultdict
import hashlib
from pathlib import Path
import re


def sha(data):
    return hashlib.sha256(data).hexdigest()


def safe_text(text):
    """Conservative whole-message rejection, never masking or redaction."""
    if not isinstance(text, str) or not 160 <= len(text) <= 12000:
        return False
    prose = re.sub(r'`[^`\n]*`', '', text)
    patterns = [r'```|~~~', r'(?m:^\s*>)', r'["“”]', r'https?://|www\.',
                r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}',
                r'/(?:home|Users|tmp|workspace|projects|root|mnt|var|private|opt)/',
                r'[A-Za-z]:[\\/]', r'\[(?:REDACTED|ANON|EMAIL|SECRET|USER|NAME)', r'~[/\\\\]',
                r'\b(?:sk-|gh[pousr]_|github_pat_|glpat-|AKIA|ASIA|xox[baprs]-|AIza|Bearer\s)',
                r'\b(?:password|secret|token|api[_ -]?key)\s*[:=]',
                r'BEGIN [A-Z ]*PRIVATE KEY', r'\beyJ[A-Za-z0-9_-]+\.',
                r'<(?:user|system|assistant|tool|script|style|blockquote)\b',
                r'(?m:^\s*(?:def |class |import |from \w+ import |function |const |let |diff --git|@@ ))']
    return not any(re.search(p, text if p != r'["“”]' else prose, re.I) for p in patterns)


def extract(rows, source_path):
    """Exactly one complete visible text block grouped by native message ID."""
    if not source_path.startswith('sessions/claude_code/'):
        return []
    groups = defaultdict(list)
    for line, row in enumerate(rows, 1):
        message = row.get('message', {})
        if row.get('type') == 'assistant' and message.get('role') == 'assistant' and message.get('id'):
            groups[message['id']].append((line, message))
    records = []
    for message_id, messages in groups.items():
        texts = [(line, i, block.get('text'), message.get('model', 'unknown'))
                 for line, message in messages
                 for i, block in enumerate(message.get('content', []))
                 if isinstance(block, dict) and block.get('type') == 'text']
        if len(texts) != 1:
            continue
        line, block_index, text, model = texts[0]
        if not isinstance(model, str) or model == '<synthetic>' or not safe_text(text):
            continue
        records.append({'source_path': source_path,
                        'session_id': Path(source_path).stem,
                        'message_locator': {'jsonl_lines': [n for n, _ in messages],
                                            'message_id': message_id, 'text_block_index': block_index},
                        'text_line': line, 'model': model, 'text': text,
                        'sha256': sha(text.encode('utf-8'))})
    return records
