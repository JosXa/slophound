"""Offset-preserving text evidence for the opt-in reference check only."""
import re
from .masking import _FENCE_RE, _INLINE_CODE_RE, _blank

_COMMENT = re.compile(r'<!--.*?(?:-->|\Z)', re.S)
_INDENTED_CODE = re.compile(r'^(?: {4}|\t)[^\n]*(?:\n(?:[ \t]*(?=\n)|(?: {4}|\t)[^\n]*))*', re.M)
_TAG = re.compile(r'''</?[A-Za-z][\w:.-]*(?=[\s/>])(?:[^>"']|"[^"]*(?:"|\Z)|'[^']*(?:'|\Z))*(?:>|\Z)''')
_TAG_NAME = re.compile(r'</?([A-Za-z][\w:.-]*)')
_FRONT = re.compile(r'^---[ \t]*\r?\n.*?(?:^(?:---|\.\.\.)[ \t]*(?:\r?\n|$)|\Z)', re.M | re.S)
_FIELD = re.compile(r'^(heading|title|lede|callout)[ \t]*:[ \t]*([^\n]*)', re.M | re.I)
_DEFINITION = re.compile(r'^ {0,3}\[(?:\\.|[^\]\\\n])+\]:[^\n]*(?:\n[ \t]+[^\n]*)*', re.M)
_LINK = re.compile(r'!?\[(?:\\.|[^\]\\\n])*\]\(')


def _value_end(value):
    """YAML comments start outside quoted scalars, after whitespace."""
    quote = None
    scalar_start = len(value) - len(value.lstrip())
    i = 0
    while i < len(value):
        char = value[i]
        if quote:
            if quote == '"' and char == '\\':
                i += 2
                continue
            if char == quote:
                if quote == "'" and value[i:i+2] == "''":
                    i += 2
                    continue
                quote = None
        elif i == scalar_start and char in {'"', "'"}:
            quote = char
        elif char == '#' and (i == 0 or value[i-1].isspace()):
            return i
        i += 1
    return len(value)


def _link_end(text, start):
    depth, quote, angle = 1, None, False
    i = start
    while i < len(text):
        char = text[i]
        if char == '\\':
            i += 2
            continue
        if quote:
            if char == quote:
                quote = None
        elif angle:
            if char == '>':
                angle = False
        elif char == '<':
            angle = True
        elif char in {'"', "'"}:
            quote = char
        elif char == '(':
            depth += 1
        elif char == ')':
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return len(text)


def reader_view(text, *, front=True):
    """Earliest construct wins; apparent code inside metadata is not code.

    Unsupported reader-facing YAML values are omitted and explicitly mark
    context incomplete. Unknown fields are never restored. Literal code remains
    evidence, even when it contains comment or tag syntax.
    """
    patterns = [('comment', _COMMENT), ('tag', _TAG), ('definition', _DEFINITION),
                ('link', _LINK), ('code', _FENCE_RE), ('code', _INDENTED_CODE), ('code', _INLINE_CODE_RE)]
    if front:
        patterns.insert(0, ('front', _FRONT))
    matches = [pattern.search(text) for _, pattern in patterns]
    visible, incomplete = text, False
    while any(match is not None for match in matches):
        _, slot, match = min((m.start(), slot, m) for slot, m in enumerate(matches) if m is not None)
        kind = patterns[slot][0]
        end = match.end()
        if kind == 'tag' and not match.group().startswith('</'):
            tag_name = _TAG_NAME.match(match.group())
            assert tag_name is not None  # Every _TAG match starts with a tag name.
            name = tag_name.group(1).lower()
            if name in {'script', 'style'}:
                closing = re.compile(r'</' + name + r'(?=[\s/>])', re.I)
                cursor, end = end, len(text)
                while candidate := closing.search(text, cursor):
                    closing_tag = _TAG.match(text, candidate.start())
                    if closing_tag:
                        end = closing_tag.end()
                        break
                    cursor = candidate.end()
        if kind == 'link':
            end = _link_end(text, end)
            # Labels are rendered; navigation and optional titles are not.
            label_start = match.start() + (2 if match.group().startswith('!') else 1)
            label_end = match.end() - 2
            label, missing = reader_view(text[label_start:label_end], front=False)
            visible = _blank(visible, match.start(), end)
            visible = visible[:label_start] + label + visible[label_end:]
            incomplete |= missing
        elif kind != 'code':
            visible = _blank(visible, match.start(), end)
            if kind == 'front':
                for field in _FIELD.finditer(text, match.start(), end):
                    value = field.group(2)
                    stop = _value_end(value)
                    scalar = value[:stop].strip()
                    if not scalar or scalar[0] in '|>!&*[{':
                        incomplete = True
                        continue
                    # A following indented continuation is unsupported, rather
                    # than falsely treated as absent reader-facing evidence.
                    following = text[field.end():end].splitlines()
                    for line in following[1:]:
                        if not line.strip() or line.lstrip().startswith('#'):
                            continue
                        if line.startswith((' ', '\t')):
                            incomplete = True
                        break
                    start = field.start(2)
                    safe, missing = reader_view(value[:stop], front=False)
                    visible = visible[:start] + safe + visible[start+stop:]
                    incomplete |= missing
        for index, old in enumerate(matches):
            if old is not None and old.start() < end:
                matches[index] = patterns[index][1].search(text, end)
    return visible, incomplete


def visible_heading(doc, visible, before):
    headings = []
    for block in doc.blocks_of('heading'):
        if block.end <= before:
            text = visible[block.start:block.end].strip()
            # Remove optional closing markers before consuming leading space.
            text = re.sub(r'[ \t]+#+[ \t]*$', '', text)
            text = re.sub(r'^#{1,6}(?:[ \t]+|$)', '', text).strip()
            if text:
                headings.append(text)
    return headings[-1] if headings else ''
