"""Surface constructions with arbitrary subjects, predicates, and complements.

Only grammatical markers drive these matches. The operator bans corrective
contrasts even when both alternatives are technically useful. No content-word
exceptions or statistical parser judgments decide whether a finding stands.
"""

import re

from .masking import Document
from .sentences import split_block


_TOKEN = re.compile(r"\w+(?:['-]\w+)*|[^\w\s]", re.UNICODE)
_BOUNDARIES = {",", ";", ":", "—", "–", "(", ")", "[", "]", '"'}
_BACKREF = {"it", "it's", "its", "this", "that's", "that", "these", "those", "they", "they're", "their"}


def _negative(word: str) -> bool:
    return word in {"not", "never", "neither", "nor", "cannot"} or word.endswith("n't")


def _has_words(tokens: list[str]) -> bool:
    return any(token[0].isalnum() for token in tokens)


def _contrast(tokens: list[str]) -> bool:
    for index, word in enumerate(tokens):
        if word not in {",", ";", "—", "–", "but"}:
            continue
        before, after = tokens[:index], tokens[index + 1:]
        if not _has_words(before) or not _has_words(after):
            continue
        # X, not Y also covers an inserted correction: X, not Y, does Z.
        if word in {",", ";", "—", "–"} and after[0] in {"not", "neither", "nor"}:
            return True
        if word == "but":
            # Either order is prohibited: X but not Y; not X but Y.
            # Stop at the next clause boundary, so an unrelated later negation
            # cannot supply the second half of the contrast.
            end = next((i for i, token in enumerate(after) if token in _BOUNDARIES), len(after))
            start = next((i + 1 for i in range(len(before) - 1, -1, -1)
                          if before[i] in _BOUNDARIES - {",", "—", "–"}), 0)
            if any(_negative(token) for token in before[start:] + after[:end]):
                return True
        if word == ";":
            end = next((i for i, token in enumerate(after) if token in _BOUNDARIES), len(after))
            if any(_negative(token) for token in after[:end]):
                return True
    return False


def contrastive_negation(doc: Document):
    """Yield sentence spans, or adjacent result/backreference sentence pairs.

    Existing segmentation owns sentence and Markdown boundaries. Plain negative
    reports remain valid; a second sentence must refer back to the preceding
    claim to constitute the paired construction.
    """
    for block in doc.blocks_of("paragraph", "list", "quote", "field"):
        previous = None
        for start, end in split_block(doc.prose, block.start, block.end):
            tokens = _TOKEN.findall(doc.prose[start:end].lower())
            if not _has_words(tokens):
                previous = None
                continue
            if _contrast(tokens):
                yield start, end
            elif previous and tokens[0] in _BACKREF:
                # Inspect only the opening clause of the backreference.
                stop = next((i for i, token in enumerate(tokens[1:], 1)
                             if token in _BOUNDARIES | {"that", "which", "who", "because", "if", "when", "where"}), len(tokens))
                negated = any(_negative(token) for token in tokens[:stop])
                prior_start, prior_negative = previous
                if negated and not prior_negative:
                    yield prior_start, end
            previous = (start, any(_negative(token) for token in tokens))
