"""Layer 2: part-of-speech and dependency rules (categories verb, adj).

Each rule is a spaCy DependencyMatcher pattern written as TOML tables. The
model is loaded lazily, only when at least one rule from this layer is active,
and is dropped when the process exits. Nothing stays resident between runs.

Language models are picked by `--lang`. English ships with the entrypoint's
dependency block; other languages are downloaded into the same uv environment
on first use.
"""

from __future__ import annotations

import os
import subprocess
import sys
import warnings

from .masking import Document
from .model import Finding, Rule
from .sentences import containing_sentence, sentence_spans

_MODEL_BY_LANG = {
    "en": "en_core_web_sm",
}


class ModelError(Exception):
    pass


def model_name(lang: str) -> str:
    return _MODEL_BY_LANG.get(lang, f"{lang}_core_news_sm")


def load_model(lang: str):
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    warnings.filterwarnings("ignore", category=UserWarning)
    import spacy

    name = model_name(lang)
    try:
        return spacy.load(name, exclude=["ner"])
    except OSError:
        pass
    _download(name)
    try:
        return spacy.load(name, exclude=["ner"])
    except OSError as exc:
        raise ModelError(f"could not load spaCy model {name} after download: {exc}") from exc


def _download(name: str) -> None:
    """Install a spaCy model wheel into the running environment via uv."""
    from spacy.cli.download import get_compatibility, get_model_filename, get_version

    try:
        compat = get_compatibility()
        version = get_version(name, compat)
    except SystemExit as exc:  # spaCy exits on unknown models
        raise ModelError(f"no spaCy model named {name}; check the --lang code") from exc
    filename = get_model_filename(name, version)
    url = f"https://github.com/explosion/spacy-models/releases/download/{name}-{version}/{filename}"
    print(f"slophound: downloading spaCy model {name} {version}", file=sys.stderr)
    result = subprocess.run(
        ["uv", "pip", "install", "--quiet", "--python", sys.executable, url],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ModelError(f"model download failed: {result.stderr.strip()}")


def run(doc: Document, rules: list[Rule], nlp) -> list[Finding]:
    from spacy.matcher import DependencyMatcher

    matcher = DependencyMatcher(nlp.vocab)
    by_key: dict[int, Rule] = {}
    for rule in rules:
        matcher.add(rule.id, rule.dependency)
        by_key[nlp.vocab.strings[rule.id]] = rule

    findings: list[Finding] = []
    blocks = doc.blocks_of("paragraph", "list", "quote")
    texts = [doc.prose[b.start : b.end] for b in blocks]
    spans = sentence_spans(doc)
    import re

    for block, parsed in zip(blocks, nlp.pipe(texts, batch_size=32)):
        for key, token_ids in matcher(parsed):
            rule = by_key[key]
            tokens = [parsed[i] for i in token_ids]
            start = block.start + min(t.idx for t in tokens)
            end = block.start + max(t.idx + len(t.text) for t in tokens)
            if rule.unless:
                sent = containing_sentence(spans, start)
                context = doc.prose[sent[0] : sent[1]] if sent else doc.prose[start:end]
                if re.search(rule.unless, context, re.I):
                    continue
            findings.append(Finding(rule, start, end))
    return _merge_overlaps(findings)


def _merge_overlaps(findings: list[Finding]) -> list[Finding]:
    """Collapse overlapping matches of the same rule into one finding.

    A rule with several alternative patterns (or several token orders) can hit the
    same construction more than once; one sentence deserves one finding per rule.
    """
    merged: list[Finding] = []
    for f in sorted(findings, key=lambda f: (f.rule.id, f.start, f.end)):
        last = merged[-1] if merged else None
        if last and last.rule.id == f.rule.id and f.start <= last.end:
            merged[-1] = Finding(last.rule, last.start, max(last.end, f.end), last.detail)
        else:
            merged.append(f)
    return merged
