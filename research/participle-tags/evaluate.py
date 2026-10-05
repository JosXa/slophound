"""Evaluate detached outcome endings without enabling a production rule.

The comma candidate uses a closed list of outcome words. The grammar gate
parses the prefix, because parsing the suffix as VBN misses "answered".
"""

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from hound.layer_spacy import load_model
from hound.masking import build_document
from hound.sentences import sentence_spans, words
from probe import sources


CORE = (
    "answered", "verified", "simplified", "streamlined", "solved",
    "demystified", "reimagined", "elevated", "perfected",
)
EXTENDED = (
    "eliminated", "unified", "transformed", "decoded", "unlocked",
    "redefined", "reinvented", "tamed",
)
KINDS = ("paragraph", "list", "heading", "field")
TAIL = re.compile(
    r"(?P<separator>[,:])\s*(?P<outcome>" + "|".join(CORE + EXTENDED)
    + r")\b[.!?]*[\"')\]]*\s*$", re.I,
)
MAX_PREFIX_WORDS = 12
FINITE_TAGS = {"VBD", "VBP", "VBZ", "MD"}
NOMINAL_POS = {"NOUN", "PROPN", "PRON"}
LABEL_BOUNDARY = re.compile(r":\s+|\s+[—–]\s+")


def surface_candidates(doc):
    """Keep lexical candidates and reject only clearly incompatible shapes."""
    for start, end in sentence_spans(doc, KINDS):
        text = doc.prose[start:end]
        match = TAIL.search(text)
        if not match:
            continue
        whole_prefix = text[:match.start()].strip()
        labels = list(LABEL_BOUNDARY.finditer(whole_prefix))
        prefix = whole_prefix[labels[-1].end():].strip() if labels else whole_prefix
        shape_reason = None
        if not 1 <= len(words(prefix)) <= MAX_PREFIX_WORDS:
            shape_reason = "prefix-length"
        elif re.search(r"[,;:!?]", prefix):
            shape_reason = "earlier-separator"
        block = next(b for b in doc.blocks if b.start <= start < b.end)
        line, column = doc.line_col(start + match.start())
        yield {
            "sentence": doc.text[start:end], "prefix": prefix,
            "whole_prefix": whole_prefix, "label_boundary": bool(labels),
            "outcome": match["outcome"].lower(),
            "vocabulary": "core" if match["outcome"].lower() in CORE else "extended",
            "separator": "comma" if match["separator"] == "," else "colon",
            "line": line, "column": column, "block": block.kind,
            "start": start, "end": end, "context": doc.text[block.start:block.end],
            "shape_rejection": shape_reason,
        }


def grammar_rejection(parsed):
    """A prefix with a finite predicate cannot be the requested noun phrase."""
    if any(t.tag_ in FINITE_TAGS for t in parsed):
        return "finite-prefix"
    roots = [t for t in parsed if t.dep_ == "ROOT"]
    if not roots or roots[0].pos_ not in NOMINAL_POS:
        return "non-nominal-prefix"
    return None


def classify(candidates, nlp):
    for candidate, parsed in zip(candidates, nlp.pipe((c["prefix"] for c in candidates), batch_size=64)):
        rejection = candidate["shape_rejection"] or grammar_rejection(parsed)
        candidate["grammar_rejection"] = rejection
        candidate["prefix_parse"] = [
            {"text": t.text, "pos": t.pos_, "tag": t.tag_, "dep": t.dep_}
            for t in parsed
        ]
        candidate["proposal_finding"] = rejection is None and candidate["separator"] == "comma"
        candidate["colon_extension_finding"] = rejection is None and candidate["separator"] == "colon"
    return candidates


def controls(nlp):
    path = Path(__file__).with_name("controls.json")
    result = []
    for case in json.loads(path.read_text()):
        candidates = classify(list(surface_candidates(build_document(case["id"], case["text"]))), nlp)
        detected = any(c["proposal_finding"] for c in candidates)
        assert detected == case["expected_detection"], (case["id"], candidates)
        result.append(case | {"detected": detected, "candidates": candidates})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ghostbuster", type=Path)
    parser.add_argument("--rust", type=Path)
    parser.add_argument("--extra", type=Path, action="append", default=[])
    parser.add_argument("--reference-manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--controls-only", action="store_true")
    args = parser.parse_args()
    nlp = load_model("en")
    control_results = controls(nlp)
    wanted = None
    if args.reference_manifest:
        wanted = {
            (r["group"], r["id"])
            for line in args.reference_manifest.read_text().splitlines()
            for r in [json.loads(line)]
        }
    groups = defaultdict(Counter)
    candidates, manifest, seen = [], [], set()
    found_references = set()
    for row in (() if args.controls_only else sources(args)):
        if row["group"].startswith(("ghostbuster/", "rust/")) and wanted is not None:
            key = row["group"], row["id"]
            if key not in wanted:
                continue
            found_references.add(key)
        doc = build_document(row["id"], row["text"])
        spans = sentence_spans(doc, KINDS)
        prose = " ".join(doc.prose[s:e] for s, e in spans)
        digest = hashlib.sha256(re.sub(r"\s+", " ", prose).strip().encode()).hexdigest()
        key = row["group"], digest
        count = len(words(prose))
        if not count or key in seen:
            continue
        seen.add(key)
        metadata = {k: v for k, v in row.items() if k != "text"}
        manifest.append(metadata | {"sha256": digest, "words": count, "spans": len(spans)})
        stats = groups[row["group"]]
        stats.update(documents=1, words=count, spans=len(spans))
        for candidate in surface_candidates(doc):
            candidates.append(metadata | candidate)
    if wanted is not None:
        assert found_references == wanted, f"Missing {len(wanted - found_references)} reference documents"
    classify(candidates, nlp)
    for c in candidates:
        stats = groups[c["group"]]
        stats[f"lexical_{c['separator']}"] += 1
        if c["grammar_rejection"]:
            stats[f"rejected_{c['grammar_rejection']}"] += 1
        if c["proposal_finding"]:
            stats[f"proposal_{c['vocabulary']}"] += 1
        if c["colon_extension_finding"]:
            stats[f"colon_extension_{c['vocabulary']}"] += 1
    summary = {
        "proposal": {
            "core": CORE, "extended": EXTENDED, "separator": "comma",
            "max_prefix_words": MAX_PREFIX_WORDS, "blocks": KINDS,
            "grammar": "Nominal prefix after any colon/dash label, without VBD/VBP/VBZ/MD tokens",
            "severity": "bark", "enabled_in_production": False,
        },
        "spacy_model_version": nlp.meta["version"], "groups": groups,
        "controls": len(control_results), "control_failures": 0,
        "lexical_candidates": len(candidates),
        "proposal_findings": sum(c["proposal_finding"] for c in candidates),
        "colon_extension_findings": sum(c["colon_extension_finding"] for c in candidates),
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    (args.output / "controls.json").write_text(json.dumps(control_results, indent=2) + "\n")
    for name, rows in (("candidates", candidates), ("manifest", manifest)):
        (args.output / f"{name}.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
    print(json.dumps({k: v for k, v in summary.items() if k != "groups"}, indent=2))
    print("Documents:", sum(g["documents"] for g in groups.values()))


if __name__ == "__main__":
    main()
