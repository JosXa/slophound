"""Measure the changed rules on the history corpus and pinned human controls.

Run through uv with the project's dependencies; pass the two local repository
paths in the order rust-lang/rfcs, vivek3141/ghostbuster-data.
"""

from collections import Counter
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tomllib

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hound.engine import Engine
from hound.loader import load_rules, _build_rule
from hound.masking import build_document

HERE = Path(__file__).resolve().parent
RULE_IDS = {
    "template.contrastive-negation",
    "template.residual-verification",
}
PREVIOUS_RULE_IDS = {
    "template.is-a-x-not-a-y", "template.evidence-scope-contrast",
    "template.residual-verification", "template.abstract-benefit-contrast",
}
RUST_REV = "16f3bc024bdef9db7502ffbefeb602c37cee20bf"
GHOST_REV = "86ebd72590556a81622986fab736ab9227a948af"


def archive(repo, revision):
    data = subprocess.check_output(["git", "-C", str(repo), "archive", revision])
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        for item in sorted(tar, key=lambda item: item.name):
            if item.isfile() and item.name.endswith((".md", ".txt")):
                yield item.name, tar.extractfile(item).read().decode("utf-8", errors="replace")


def evaluate(rust, ghost, baseline):
    root = HERE.parents[1]
    revision = subprocess.check_output(["git", "-C", str(root), "rev-parse", baseline], text=True).strip()
    before = tomllib.loads(subprocess.check_output(
        ["git", "-C", str(root), "show", f"{revision}:rules/template.toml"], text=True,
    ))
    rules = [rule for rule in load_rules() if rule.id in RULE_IDS]
    engines = {rule.id: Engine([rule]) for rule in rules}
    baseline_engine = Engine([
        _build_rule(raw, "template", Path("baseline/template.toml"))
        for raw in before["rule"] if raw["id"] in PREVIOUS_RULE_IDS | RULE_IDS
    ])
    groups = {}

    def add(group, name, text, metadata=None):
        result = groups.setdefault(group, {"documents": 0, "prose_words": 0, "findings": []})
        doc = build_document(name, text)
        result["documents"] += 1
        result["prose_words"] += len(re.findall(r"\b[A-Za-z]+\b", doc.prose))
        previous = baseline_engine.lint_deterministic(doc)
        for rule_id, engine in engines.items():
            for finding in engine.lint_deterministic(doc):
                result["findings"].append({
                    "document": name,
                    "rule": rule_id,
                    "start": finding.start,
                    "end": finding.end,
                    "already_matched": any(hit.start < finding.end and finding.start < hit.end for hit in previous),
                    "context": text[max(0, finding.start - 90):min(len(text), finding.end + 160)],
                    **(metadata or {}),
                })

    records = [json.loads(line) for line in (HERE / "corpus.jsonl").read_text().splitlines()]
    for record in records:
        add("history/" + record["usage"], record["id"], record["text"])
    for name, text in archive(rust, RUST_REV):
        if name.startswith("text/") and name.endswith(".md"):
            add("rust/historical-human", name, text)
    selected = Counter()
    for name, text in archive(ghost, GHOST_REV):
        parts = name.split("/")
        if len(parts) < 3 or parts[0] not in {"essay", "reuter", "wp"} or parts[1] != "human":
            continue
        if len(parts) != (4 if parts[0] == "reuter" else 3) or selected[parts[0]] >= 100:
            continue
        selected[parts[0]] += 1
        add("ghostbuster/" + parts[0] + "/human", name, text)
    for result in groups.values():
        result["findings_by_rule"] = dict(Counter(hit["rule"] for hit in result["findings"]))
        result["matched_documents"] = len({hit["document"] for hit in result["findings"]})
        result["new_findings"] = sum(not hit["already_matched"] for hit in result["findings"])
    return {"baseline_revision": revision, "revisions": {"rust-lang/rfcs": RUST_REV, "vivek3141/ghostbuster-data": GHOST_REV}, "groups": groups}


if __name__ == "__main__":
    result = evaluate(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3] if len(sys.argv) > 3 else "HEAD")
    (HERE / "evaluation.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({key: {k: v for k, v in value.items() if k != "findings"} for key, value in result["groups"].items()}, indent=2))
