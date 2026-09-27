#!/usr/bin/env -S uv run --script --quiet
# /// script
# requires-python = ">=3.11,<3.14"
# dependencies = [
#   "spacy==3.8.16",
#   "en-core-web-sm @ https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl",
# ]
# ///
"""Exploratory cadence counts, not production rules or authorship predictions."""

import argparse
from collections import Counter, defaultdict
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import tarfile

import spacy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hound.masking import build_document
from hound.sentences import sentence_spans, words

GHOST_REV = "86ebd72590556a81622986fab736ab9227a948af"
RUST_REV = "16f3bc024bdef9db7502ffbefeb602c37cee20bf"
WORD = re.compile(r"[A-Za-z]+(?:['’][A-Za-z]+)?")
IGNORE = set("the a an and or but of to in on for with by from that this these those its their our your his her my it they we you he she as at than which who what when where how not no more less same other only also very much most each all some any both such one two three".split())


def archive(repo, revision):
    data = subprocess.check_output(["git", "-C", str(repo), "archive", revision])
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        for item in tar:
            if item.isfile() and item.name.endswith((".md", ".txt")):
                yield item.name, tar.extractfile(item).read().decode("utf-8", errors="replace")


def sources(args):
    if args.ghostbuster:
        for name, text in archive(args.ghostbuster, GHOST_REV):
            parts = name.split("/")
            if len(parts) < 3 or parts[0] not in {"essay", "reuter", "wp"} or parts[1] not in {"human", "claude", "gpt"}:
                continue
            if len(parts) != (4 if parts[0] == "reuter" else 3):
                continue
            if args.domain and parts[0] not in args.domain:
                continue
            yield dict(id=name, group=f"ghostbuster/{parts[0]}/{parts[1]}", text=text,
                       source_url=f"https://github.com/vivek3141/ghostbuster-data/blob/{GHOST_REV}/{name}",
                       dataset_revision=GHOST_REV, model=parts[1])
    if args.rust:
        for name, text in archive(args.rust, RUST_REV):
            if name.startswith("text/") and name.endswith(".md"):
                yield dict(id=name, group="rust/historical", text=text,
                           source_url=f"https://github.com/rust-lang/rfcs/blob/{RUST_REV}/{name}",
                           dataset_revision=RUST_REV, model="historical-human-control")
    for path in args.extra:
        for line in path.read_text().splitlines():
            row = json.loads(line)
            row.setdefault("group", f"extra/{row['model']}/{row.get('genre', 'unknown')}")
            yield row


def surface(text):
    """High recall candidates; repeated nouns can match and require inspection."""
    pieces = re.split(r"[,;]", text)
    tokens = [list(WORD.finditer(p)) for p in pieces]
    lengths = [len(ts) for ts in tokens]
    echoes = []
    for i in range(len(pieces) - 1):
        a, b = tokens[i:i + 2]
        if not (3 <= len(a) <= 12 and 3 <= len(b) <= 12):
            continue
        for x in range(1, min(6, len(a) - 1)):
            for y in range(1, min(6, len(b) - 1)):
                word = a[x].group().lower()
                if word in IGNORE or word != b[y].group().lower() or abs(x - y) > 1:
                    continue
                prefix_a = " ".join(t.group().lower() for t in a[:x])
                prefix_b = " ".join(t.group().lower() for t in b[:y])
                if prefix_a == prefix_b:
                    continue
                echoes.append(dict(piece=i, word=word, positions=[x, y]))
    triple = len(pieces) == 3 and bool(re.match(r"\s*and\b", pieces[2], re.I)) and all(3 <= n <= 12 for n in lengths[:2]) and lengths[2] >= 4
    long_tail = triple and max(lengths[:2]) <= 8 and lengths[2] >= max(8, 1.5 * max(lengths[:2]))
    return pieces, lengths, echoes, triple, long_tail


def grammatical_predicates(parsed, starts):
    found = defaultdict(list)
    for t in parsed:
        if t.pos_ not in {"VERB", "AUX"}:
            continue
        subjects = [c for c in t.children if c.dep_ in {"nsubj", "nsubjpass", "csubj"}]
        for subject in subjects:
            piece = sum(t.idx >= x for x in starts) - 1
            if subject.idx < starts[piece]:
                continue
            found[piece].append(dict(word=t.lower_, lemma=t.lemma_, subject=subject.lower_, index=t.idx))
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ghostbuster", type=Path)
    parser.add_argument("--rust", type=Path)
    parser.add_argument("--domain", choices=("essay", "reuter", "wp"), action="append", default=[])
    parser.add_argument("--extra", type=Path, action="append", default=[])
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--min-words", type=int, default=200)
    parser.add_argument("--max-words", type=int, default=5000)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    groups = defaultdict(list)
    inventory = Counter()
    seen = set()
    for row in sources(args):
        inventory[row["group"]] += 1
        doc = build_document(row["id"], row["text"])
        spans = sentence_spans(doc, kinds=("paragraph", "list"))
        count = sum(len(words(doc.prose[s:e])) for s, e in spans)
        key = hashlib.sha256(re.sub(r"\s+", " ", row["text"]).encode()).hexdigest()
        # Duplicates are removed within a group; source groups remain separate.
        if not args.min_words <= count <= args.max_words or (row["group"], key) in seen:
            continue
        seen.add((row["group"], key))
        row.update(prose_words=count, sha256=key, sentences=len(spans))
        groups[row["group"]].append((row, doc, spans))
    nlp = spacy.load("en_core_web_sm", exclude=["ner"])
    result = {"parameters": vars(args) | {"spacy": spacy.__version__, "model_version": nlp.meta["version"]}, "groups": {}}
    matches, manifest = [], []
    for group, candidates in sorted(groups.items()):
        selected = sorted(candidates, key=lambda x: x[0]["sha256"])[:args.limit]
        stats = dict(available=inventory[group], eligible=len(candidates), documents=len(selected),
                     words=0, sentences=0, counts=Counter(), documents_with=Counter())
        jobs = []
        for row, doc, spans in selected:
            stats["words"] += row["prose_words"]
            stats["sentences"] += len(spans)
            manifest.append({k: v for k, v in row.items() if k != "text"})
            for start, end in spans:
                text = doc.prose[start:end]
                pieces, lengths, echoes, triple, long_tail = surface(text)
                if echoes or triple:
                    jobs.append((text, (row, doc, start, end, pieces, lengths, echoes, triple, long_tail)))
        seen_docs = defaultdict(set)
        for parsed, meta in nlp.pipe(jobs, as_tuples=True, batch_size=64):
            row, doc, start, end, pieces, lengths, echoes, triple, long_tail = meta
            starts = [0] + [m.end() for m in re.finditer(r"[,;]", parsed.text)]
            predicates = grammatical_predicates(parsed, starts)
            grammar_echo = [echo for echo in echoes if all(any(p["word"] == echo["word"] for p in predicates[i]) for i in (echo["piece"], echo["piece"] + 1))]
            labels = []
            if echoes:
                labels.append("surface_echo")
            if grammar_echo:
                labels.append("parsed_echo")
            if long_tail and any(e["piece"] == 0 for e in echoes):
                labels.append("surface_short_short_long")
            if long_tail and any(e["piece"] == 0 for e in grammar_echo):
                labels.append("parsed_short_short_long")
            if triple and all(predicates[i] for i in range(3)):
                labels.append("parsed_three_clauses")
            if not labels:
                continue
            stats["counts"].update(labels)
            for label in labels:
                seen_docs[label].add(row["id"])
            matches.append(dict(group=group, id=row["id"], source_url=row["source_url"],
                                line=doc.line_col(start)[0], start=start, end=end,
                                text=doc.text[start:end], masked_text=parsed.text,
                                labels=labels, lengths=lengths, echoes=echoes, predicates=predicates))
        stats["documents_with"].update({label: len(ids) for label, ids in seen_docs.items()})
        result["groups"][group] = stats
        print(group, stats, flush=True)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "summary.json").write_text(json.dumps(result, indent=2, default=str) + "\n")
    for name, rows in (("matches", matches), ("manifest", manifest)):
        (args.output / f"{name}.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))


if __name__ == "__main__":
    main()
