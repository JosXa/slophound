"""Layer 3: document-level statistics (category doc).

Each rule names a metric and a threshold. A metric receives the document and
returns a value plus the span the finding should point at. The rule fires when
`value >= threshold` (or `value <= threshold` for metrics registered as
"lower is worse"). Rules also carry minimum sentence or paragraph counts so a
three-line note is never judged on rhythm.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Callable

from .masking import Document
from .model import Finding, Rule
from .sentences import split_block, words

# metric name -> (function, fires_when_at_least)
MetricFn = Callable[[Document], tuple[float, tuple[int, int] | None, str]]
METRICS: dict[str, tuple[MetricFn, bool]] = {}


def metric(name: str, at_least: bool = True):
    def deco(fn: MetricFn):
        METRICS[name] = (fn, at_least)
        return fn

    return deco


_SENTENCE_END_RE = re.compile(r"""[.!?:;,]["')\]]*\s*$""")


def _paragraphs(doc: Document):
    """Paragraph blocks that are running prose.

    A single line without closing punctuation is a title, a caption, or a slide
    heading rather than a paragraph, so the rhythm metrics leave it out. The
    phrase layers still see it.
    """
    out = []
    for b in doc.blocks_of("paragraph"):
        text = doc.prose[b.start : b.end]
        if "\n" not in text and not _SENTENCE_END_RE.search(text):
            continue
        out.append(b)
    return out


def _sentences(doc: Document):
    spans = []
    for b in _paragraphs(doc) + doc.blocks_of("list"):
        spans.extend(split_block(doc.prose, b.start, b.end))
    return sorted(spans)


def _first_words(text: str, n: int) -> str:
    return " ".join(w.lower() for w in words(text)[:n])


@metric("sentence_length_cv", at_least=False)
def sentence_length_cv(doc: Document):
    """Coefficient of variation of sentence length in words. Low = monotone rhythm."""
    lengths = [len(words(doc.prose[s:e])) for s, e in _sentences(doc)]
    lengths = [n for n in lengths if n > 0]
    if len(lengths) < 2:
        return 1.0, None, ""
    mean = sum(lengths) / len(lengths)
    sd = math.sqrt(sum((n - mean) ** 2 for n in lengths) / len(lengths))
    cv = sd / mean if mean else 1.0
    return cv, None, f"sentence length varies {cv:.2f} (coefficient of variation) across {len(lengths)} sentences"


@metric("paragraph_opener_repeats")
def paragraph_opener_repeats(doc: Document):
    """Most frequent two-word paragraph opener. Counts repeats beyond the first."""
    openers = Counter()
    first_span: dict[str, tuple[int, int]] = {}
    for b in _paragraphs(doc):
        key = _first_words(doc.prose[b.start : b.end], 2)
        if not key:
            continue
        openers[key] += 1
        first_span.setdefault(key, (b.start, b.end))
    if not openers:
        return 0, None, ""
    key, n = openers.most_common(1)[0]
    span = first_span[key]
    return n - 1, (span[0], min(span[1], span[0] + 60)), f'{n} paragraphs open with "{key}"'


@metric("sentence_opener_run")
def sentence_opener_run(doc: Document):
    """Longest run of consecutive sentences within a paragraph sharing their first word."""
    best = 0
    best_span = None
    for b in _paragraphs(doc):
        spans = split_block(doc.prose, b.start, b.end)
        run = 0
        prev = None
        run_start = None
        for s, e in spans:
            first = _first_words(doc.prose[s:e], 1)
            if first and first == prev:
                run += 1
                if run > best:
                    best = run
                    best_span = (run_start, e)
            else:
                run = 1
                run_start = s
            prev = first
    return best, best_span, f"{best} consecutive sentences start with the same word"


_TRIAD_RE = re.compile(r"\b[\w'-]+, [\w'-]+,? and [\w'-]+\b", re.I)


@metric("triad_density")
def triad_density(doc: Document):
    """Lists of exactly three per 100 words."""
    n_words = doc.word_count()
    if n_words == 0:
        return 0.0, None, ""
    matches = list(_TRIAD_RE.finditer(doc.prose))
    density = len(matches) / n_words * 100
    span = (matches[0].start(), matches[0].end()) if matches else None
    return density, span, f"{len(matches)} groups of three in {n_words} words ({density:.1f} per 100)"


# "- **Label:** text" and "- **Label**: text" both count; the colon sits inside
# or outside the bold depending on the model.
_BOLD_COLON_RE = re.compile(r"^[ \t]*(?:[-*+]|\d+[.)])[ \t]+\*\*[^*:\n]{1,60}(?::\*\*|\*\*[ \t]*[:.])", re.M)


@metric("bold_label_bullets")
def bold_label_bullets(doc: Document):
    """Bullets that open with a bold label and a colon."""
    matches = list(_BOLD_COLON_RE.finditer(doc.masked))
    span = (matches[0].start(), matches[0].end()) if matches else None
    return len(matches), span, f"{len(matches)} bullets open with a bold label"


_CONNECTIVE_RE = re.compile(
    r"^(however|moreover|furthermore|additionally|in addition|overall|consequently|"
    r"nevertheless|ultimately|importantly|crucially|notably|that said|in short|in summary)\b",
    re.I,
)


@metric("connective_openers")
def connective_openers(doc: Document):
    """Paragraphs that open with a discourse connective."""
    hits = []
    for b in _paragraphs(doc):
        text = doc.prose[b.start : b.end].lstrip()
        offset = b.start + (b.end - b.start - len(text))
        m = _CONNECTIVE_RE.match(text)
        if m:
            hits.append((offset, offset + m.end()))
    return len(hits), hits[0] if hits else None, f"{len(hits)} paragraphs open with a connective"


# These phrases describe the document's route instead of advancing its subject.
# A single signpost can orient a long guide; the density metric below needs a
# repeated habit before it reports one.
_SIGNPOST_RE = re.compile(
    r"(?:\b(?:first|next),|\bhaving (?:covered|established)\b|\bin (?:this|the following|"
    r"the next) section\b|\bas (?:mentioned|noted) (?:above|earlier)\b|\blet(?: us|'s) turn to\b)",
    re.I,
)


@metric("signpost_density")
def signpost_density(doc: Document):
    """Structural signposts per 100 prose words; short documents are not scored."""
    n_words = doc.word_count()
    if n_words < 150:
        return 0.0, None, f"{n_words} words; fewer than 150 needed to score signposts"
    matches = list(_SIGNPOST_RE.finditer(doc.prose))
    density = len(matches) / n_words * 100
    span = (matches[0].start(), matches[0].end()) if matches else None
    return density, span, f"{len(matches)} structural signposts in {n_words} words ({density:.1f} per 100)"


# A closing paragraph beginning with one of these stock moral/recap phrases is
# a tell on its own. The lexical branch below catches a recap without requiring
# a grammar parser or a curated topic vocabulary.
_CODA_START_RE = re.compile(
    r"^(?:ultimately,|in the end,|in conclusion|as we've seen|only time will tell|"
    r"remember,|the future\b)",
    re.I,
)
# A conversational signoff can follow a real conclusion without becoming part
# of it. Treat that boilerplate as outside the prose ending when locating a coda.
_SIGNOFF_RE = re.compile(r"^(?:let me know if|i hope this helps|happy to|feel free to)\b", re.I)
_CONTENT_STOPWORDS = frozenset(
    "a an and are as at be been being but by can could did do does for from had has have "
    "he her here him his i if in into is it its may me might more most my no not of on or "
    "our out over should so that the their them then there these they this those to under us "
    "was we were what when where which who will with would you your".split()
)


def _content_words(text: str) -> set[str]:
    """Lowercase content words for a deliberately simple lexical-overlap check."""
    return {word.lower() for word in words(text) if len(word) > 3 and word.lower() not in _CONTENT_STOPWORDS}


@metric("conclusion_coda")
def conclusion_coda(doc: Document):
    """Stock final coda, or high content-word Jaccard overlap with the opening."""
    paras = _paragraphs(doc)
    if len(paras) < 2:
        return 0.0, None, ""
    first, last = paras[0], paras[-1]
    last_text = doc.prose[last.start : last.end].lstrip()
    if len(paras) >= 3 and _SIGNOFF_RE.match(last_text):
        last = paras[-2]
        last_text = doc.prose[last.start : last.end].lstrip()
    last_start = last.end - len(last_text)
    coda = _CODA_START_RE.match(last_text)
    if coda:
        return 1.0, (last_start, last_start + coda.end()), "final paragraph opens with a stock conclusion coda"
    opening = _content_words(doc.prose[first.start : first.end])
    closing = _content_words(last_text)
    union = opening | closing
    overlap = len(opening & closing) / len(union) if union else 0.0
    return overlap, (last.start, last.end) if overlap else None, (
        f"opening and final paragraphs share {len(opening & closing)} of {len(union)} content words "
        f"(Jaccard {overlap:.2f})"
    )


# This is intentionally paragraph-level: two normal sentences that start with
# "Every" are common, while repeated paragraph templates create a visible beat.
_EVERY_OPENER_RE = re.compile(
    r"^every\s+[a-z][\w'-]*\s+(?:is|are|was|were|be|been|being|has|have|had|"
    r"do|does|did|can|will|shall|must|should|would|may|might|[a-z]+(?:s|ed))\b",
    re.I,
)


@metric("every_template_openers")
def every_template_openers(doc: Document):
    """Paragraphs opening with the repeated 'Every noun verb' template."""
    hits = []
    for block in _paragraphs(doc):
        text = doc.prose[block.start : block.end].lstrip()
        start = block.end - len(text)
        match = _EVERY_OPENER_RE.match(text)
        if match:
            hits.append((start, start + match.end()))
    return len(hits), hits[0] if hits else None, f'{len(hits)} paragraphs open with "Every <noun> <verb>"'


_QUESTION_END_RE = re.compile(r"\?[\"')\]]*\s*$")


@metric("rhetorical_question_share")
def rhetorical_question_share(doc: Document):
    """Question sentences immediately followed by a declarative answer sentence."""
    spans = _sentences(doc)
    hits = []
    for current, following in zip(spans, spans[1:]):
        question = doc.prose[current[0] : current[1]]
        answer = doc.prose[following[0] : following[1]]
        if _QUESTION_END_RE.search(question) and not _QUESTION_END_RE.search(answer):
            hits.append((current[0], following[1]))
    if len(hits) < 3:
        return 0.0, None, f"{len(hits)} question-and-answer pairs; at least 3 are needed to score the share"
    share = len(hits) / len(spans) if spans else 0.0
    return share, hits[0], f"{len(hits)} of {len(spans)} prose sentences form question-and-answer pairs ({share:.0%})"


@metric("short_paragraph_share")
def short_paragraph_share(doc: Document):
    """Share of paragraphs that are a single sentence."""
    paras = _paragraphs(doc)
    if not paras:
        return 0.0, None, ""
    single = [b for b in paras if len(split_block(doc.prose, b.start, b.end)) <= 1]
    share = len(single) / len(paras)
    span = (single[0].start, single[0].end) if single else None
    return share, span, f"{len(single)} of {len(paras)} paragraphs are a single sentence"


_CLOSER_RE = re.compile(
    r",\s+(ensuring|highlighting|reflecting|allowing|enabling|underscoring|showcasing|"
    r"emphasizing|fostering|driving|paving|reinforcing|solidifying|demonstrating|"
    r"signaling|signalling|making it|contributing to)\b[^.!?]*$",
    re.I,
)


@metric("participial_closer_share")
def participial_closer_share(doc: Document):
    """Share of sentences ending in a trailing ', -ing ...' clause."""
    spans = _sentences(doc)
    if not spans:
        return 0.0, None, ""
    hits = []
    for s, e in spans:
        m = _CLOSER_RE.search(doc.prose[s:e].rstrip(".!?\"'"))
        if m:
            hits.append((s + m.start(), e))
    return len(hits) / len(spans), hits[0] if hits else None, f"{len(hits)} of {len(spans)} sentences trail off into a participial clause"


@metric("em_dash_density")
def em_dash_density(doc: Document):
    """Em dashes per 100 words. Kept for the density figure; punct.em-dash is the bite."""
    n_words = doc.word_count() or 1
    n = doc.masked.count("\u2014")
    return n / n_words * 100, None, f"{n} em dashes in {n_words} words"


def run(doc: Document, rules: list[Rule]) -> list[Finding]:
    findings: list[Finding] = []
    n_sentences = len(_sentences(doc))
    n_paragraphs = len(_paragraphs(doc))
    for rule in rules:
        if rule.metric not in METRICS:
            raise ValueError(f"{rule.id}: unknown metric {rule.metric!r}; known: {sorted(METRICS)}")
        if n_sentences < rule.min_sentences or n_paragraphs < rule.min_paragraphs:
            continue
        fn, at_least = METRICS[rule.metric]
        value, span, detail = fn(doc)
        fires = value >= rule.threshold if at_least else value <= rule.threshold
        if not fires:
            continue
        if span is None:
            first = doc.blocks[0] if doc.blocks else None
            span = (first.start, min(first.end, first.start + 60)) if first else (0, 0)
        findings.append(Finding(rule, span[0], span[1], detail=f"{rule.message} ({detail})"))
    return findings
