"""Conservative context eligibility for advisory reference candidates.

Any preceding rendered content can supply a referent, including synonyms and
bridging references. Silence does not establish that a reference is clear.
"""
import re

from .masking import (
    Document, _FENCE_RE, _INLINE_CODE_RE, _TABLE_LINE_RE, _LINK_LABEL_RE,
    _URL_RE, _HTML_COMMENT_RE, _FRONT_MATTER_RE,
)

# Non-whitespace in the offset-preserving prose view establishes possible context.
_VISIBLE = re.compile(r'\S')
_RENDERED_CONTEXT = (_FENCE_RE, _INLINE_CODE_RE, _TABLE_LINE_RE, _LINK_LABEL_RE, _URL_RE)


def opening_reference_candidate(doc: Document, start: int) -> bool:
    """Accept only a body assertion without preceding reader-visible context.

    Detection masking excludes code, tables and some link labels as lint targets;
    it does not make them invisible to the reader. Hidden comments and machine
    metadata cannot establish a referent. Rendered metadata is already in prose.
    """
    if _VISIBLE.search(doc.prose, 0, start):
        return False
    # Quote blocks survive --skip-quotes; that detection opt-out does not
    # erase reader context. Hidden comments and metadata create no quote blocks.
    if any(b.kind == 'quote' and b.end <= start for b in doc.blocks):
        return False
    block = next((b for b in doc.blocks if b.start <= start < b.end), None)
    if block is None or block.kind != 'paragraph':
        return False
    invisible = [(m.start(), m.end())
                 for pattern in (_HTML_COMMENT_RE, _FRONT_MATTER_RE)
                 for m in pattern.finditer(doc.text, 0, start)]
    for pattern in _RENDERED_CONTEXT:
        for match in pattern.finditer(doc.text, 0, start):
            # A hidden range must contain the whole construct to hide its
            # context. Comment syntax inside rendered code is literal text.
            if not any(left <= match.start() and match.end() <= right
                       for left, right in invisible):
                return False
    return True
