"""Sentence and paragraph segmentation over the prose view of a document.

Regex-based on purpose: the document layer and the `unless` gates need a fast,
deterministic splitter that does not depend on the spaCy model being loaded.
Spans are offsets into the original text.
"""

from __future__ import annotations

import re

from .masking import Document

_ABBREV = re.compile(r"\b(?:e\.g|i\.e|vs|etc|Mr|Mrs|Dr|Ms|St|No|Fig|approx|cf)\.$", re.I)
_BOUNDARY = re.compile(r"[.!?]+[\"')\]]*(?=\s+[\"'(\[]?[A-Z0-9]|\s*$)")


def sentence_spans(doc: Document, kinds: tuple[str, ...] = ("paragraph", "list", "quote")) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for block in doc.blocks_of(*kinds):
        spans.extend(split_block(doc.prose, block.start, block.end))
    return spans


def split_block(text: str, start: int, end: int) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    segment = text[start:end]
    cursor = 0
    for m in _BOUNDARY.finditer(segment):
        candidate = segment[cursor : m.end()]
        if _ABBREV.search(candidate.rstrip()):
            continue
        s, e = _trim(segment, cursor, m.end())
        if e > s:
            spans.append((start + s, start + e))
        cursor = m.end()
    s, e = _trim(segment, cursor, len(segment))
    if e > s:
        spans.append((start + s, start + e))
    return spans


def _trim(segment: str, s: int, e: int) -> tuple[int, int]:
    while s < e and segment[s].isspace():
        s += 1
    while e > s and segment[e - 1].isspace():
        e -= 1
    return s, e


def containing_sentence(spans: list[tuple[int, int]], offset: int) -> tuple[int, int] | None:
    for s, e in spans:
        if s <= offset < e:
            return s, e
    return None


def words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9'\u00C0-\u024F]+", text)
