"""Surface constructions with arbitrary subjects, predicates, and complements.

The operator bans corrective contrasts even when both alternatives are useful.
Grammatical markers and dictionary inflections distinguish those alternatives
from introductory adverbs, descriptive supplements, and continued actions.
"""

from functools import lru_cache
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


@lru_cache(maxsize=4096)
def _lemmas(word: str):
    # Dictionary lookup only: no OOV prediction or statistical tagging.
    from lemminflect import getAllLemmas
    return getAllLemmas(word)


@lru_cache(maxsize=4096)
def _verb_tags(word: str) -> frozenset[str]:
    from lemminflect import getAllInflections
    return frozenset(
        tag for lemma in _lemmas(word).get("VERB", ())
        for tag, forms in getAllInflections(lemma, upos="VERB").items()
        if word in forms
    )


def _adverb(word: str) -> bool:
    # Ambiguous nouns such as "today" can supply real alternatives.
    return set(_lemmas(word)) == {"ADV"}


def _finite(word: str) -> bool:
    return bool(_verb_tags(word) & {"VBD", "VBP", "VBZ"}) or word in {
        "can", "could", "may", "might", "must", "shall", "should", "will", "would",
    }


def _introductory(before: list[str], after: list[str]) -> bool:
    # An adverb introduces one assertion: "Therefore, not every request arrives."
    # Adverb alternatives such as "Quickly, not slowly" still match.
    clause_end = next((i for i, token in enumerate(after) if token in _BOUNDARIES), len(after))
    return (all(_adverb(token) for token in before)
            and any(_finite(token) for token in after[1:clause_end]))


def _supplement(before: list[str], after: list[str]) -> bool:
    # Subject, not <participle ...>, <finite predicate>.
    # A preceding gerund/progressive can instead be the accepted alternative.
    if len(after) < 3 or after[0] != "not" or "VBG" not in _verb_tags(after[1]):
        return False
    if any(token in _BOUNDARIES or "VBG" in _verb_tags(token)
           or (_finite(token) and not set(_lemmas(token)) & {"NOUN", "ADJ"})
           for token in before):
        return False
    close = next((i for i, token in enumerate(after) if token in _BOUNDARIES), len(after))
    if close == len(after) or after[close] != ",":
        return False
    predicate = next((token for token in after[close + 1:] if not _adverb(token)), "")
    return bool(predicate) and _finite(predicate)


def _continued_action(tokens: list[str], index: int) -> bool:
    # Negated aspectual cessation asserts continuation. A noun object in
    # "never stopped the worker" still expresses an ordinary negative claim.
    rest = tokens[index + 1:]
    while rest and not _negative(rest[0]) and (
        _adverb(rest[0]) or rest[0] in {"have", "has", "had", "been", "be"}
    ):
        rest = rest[1:]
    if len(rest) < 2:
        return False
    lemmas = set(_lemmas(rest[0]).get("VERB", ()))
    if not lemmas & {"stop", "cease"}:
        return False
    return "VBG" in _verb_tags(rest[1]) or (
        "cease" in lemmas and len(rest) > 2 and rest[1] == "to" and "VB" in _verb_tags(rest[2])
    )


def _has_negation(tokens: list[str]) -> bool:
    return any(_negative(token) and not _continued_action(tokens, i)
               and not (i and tokens[i - 1] == "," and _supplement(tokens[:i - 1], tokens[i:]))
               for i, token in enumerate(tokens))


def _contrast(tokens: list[str]) -> bool:
    for index, word in enumerate(tokens):
        if word not in {",", ";", "—", "–", "but"}:
            continue
        before, after = tokens[:index], tokens[index + 1:]
        if not _has_words(before) or not _has_words(after):
            continue
        # X, not Y also covers an inserted correction: X, not Y, does Z.
        if word in {",", ";", "—", "–"} and after[0] in {"not", "neither", "nor"}:
            if not (word == "," and (_introductory(before, after) or _supplement(before, after))):
                return True
        if word == "but":
            # Either order is prohibited: X but not Y; not X but Y.
            # Stop at the next clause boundary, so an unrelated later negation
            # cannot supply the second half of the contrast.
            end = next((i for i, token in enumerate(after) if token in _BOUNDARIES), len(after))
            start = next((i + 1 for i in range(len(before) - 1, -1, -1)
                          if before[i] in _BOUNDARIES - {",", "—", "–"}), 0)
            if _has_negation(before[start:]) or _has_negation(after[:end]):
                return True
        if word == ";":
            end = next((i for i, token in enumerate(after) if token in _BOUNDARIES), len(after))
            if _has_negation(after[:end]):
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
                negated = _has_negation(tokens[:stop])
                prior_start, prior_negative = previous
                if negated and not prior_negative:
                    yield prior_start, end
            previous = (start, _has_negation(tokens))
