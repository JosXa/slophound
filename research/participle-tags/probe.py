"""Search pinned reference corpora for a comma and one final participle.

This collects candidates for review, without treating the construction as a
writing defect. Run `uv run research/participle-tags/probe.py --help`.
"""

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hound.masking import build_document
from hound.sentences import sentence_spans, words
from tools.cadence_probe import GHOST_REV, RUST_REV, archive
from lemminflect import getAllLemmas, getInflection


TAIL = re.compile(r",\s*(?P<tag>[A-Za-z]+)[.!?]*\s*$")


def is_participle(word):
    return any(
        word.lower() in {form.lower() for form in getInflection(lemma, tag="VBN")}
        for lemma in getAllLemmas(word.lower()).get("VERB", ())
    )


def sources(args):
    if args.ghostbuster:
        for name, text in archive(args.ghostbuster, GHOST_REV):
            parts = name.split("/")
            if len(parts) != (4 if parts[0] == "reuter" else 3):
                continue
            if parts[0] not in {"essay", "reuter", "wp"} or parts[1] not in {"human", "claude", "gpt"}:
                continue
            yield {
                "id": name, "group": f"ghostbuster/{parts[0]}/{parts[1]}",
                "text": text, "dataset_revision": GHOST_REV,
                "source_url": f"https://github.com/vivek3141/ghostbuster-data/blob/{GHOST_REV}/{name}",
            }
    if args.rust:
        for name, text in archive(args.rust, RUST_REV):
            if name.startswith("text/") and name.endswith(".md"):
                yield {
                    "id": name, "group": "rust/historical", "text": text,
                    "dataset_revision": RUST_REV,
                    "source_url": f"https://github.com/rust-lang/rfcs/blob/{RUST_REV}/{name}",
                }
    for path in args.extra:
        for line in path.read_text().splitlines():
            yield json.loads(line)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ghostbuster", type=Path)
    parser.add_argument("--rust", type=Path)
    parser.add_argument("--extra", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--min-words", type=int, default=200)
    parser.add_argument("--max-words", type=int, default=5000)
    parser.add_argument("--headings", action="store_true")
    args = parser.parse_args()
    groups = defaultdict(list)
    seen = set()
    for row in sources(args):
        doc = build_document(row["id"], row["text"])
        kinds = ("paragraph", "list", "heading") if args.headings else ("paragraph", "list")
        spans = sentence_spans(doc, kinds)
        count = sum(len(words(doc.prose[s:e])) for s, e in spans)
        sha = hashlib.sha256(re.sub(r"\s+", " ", row["text"]).encode()).hexdigest()
        key = row["group"], sha
        if not args.min_words <= count <= args.max_words or key in seen:
            continue
        seen.add(key)
        row.update(sha256=sha, prose_words=count)
        groups[row["group"]].append((row, doc, spans))
    result = {"parameters": {k: str(v) for k, v in vars(args).items()}, "groups": {}}
    matches, manifest = [], []
    for group, candidates in sorted(groups.items()):
        selected = sorted(candidates, key=lambda x: x[0]["sha256"])[:args.limit]
        stats = {"eligible": len(candidates), "texts": len(selected), "words": 0, "sentences": 0, "tags": Counter()}
        for row, doc, spans in selected:
            manifest.append({k: v for k, v in row.items() if k != "text"})
            stats["words"] += row["prose_words"]
            stats["sentences"] += len(spans)
            for start, end in spans:
                sentence = doc.prose[start:end]
                match = TAIL.search(sentence)
                if not match or not is_participle(match["tag"]):
                    continue
                stats["tags"][match["tag"].lower()] += 1
                matches.append({
                    "id": row["id"], "group": group, "source_url": row["source_url"],
                    "line": doc.line_col(start)[0], "text": doc.text[start:end],
                    "masked_text": sentence, "tag": match["tag"].lower(),
                    "comma_count": sentence.count(","), "words_before": len(words(sentence[:match.start()])),
                })
        result["groups"][group] = stats
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    for name, rows in (("matches", matches), ("manifest", manifest)):
        (args.output / f"{name}.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
    print(json.dumps(result, indent=2))
    print(f"Candidates: {len(matches)}")


if __name__ == "__main__":
    main()
