"""Extract candidates from JSONL transcripts exported by the recall agent.

Usage: uv run python research/contrastive-scope/collect.py EXPORT_DIRECTORY OUTPUT
Only assistant text parts qualify; tool results and quoted prompts never supply
authorship. Offsets refer to the original text part, before normalization.
"""

import hashlib
import json
from pathlib import Path
import re
import sys


FAMILIES = {
    "positive-negative": re.compile(r",\s+not\b|[—–]\s*not\b", re.I),
    "alternative": re.compile(r"\brather than\b", re.I),
    "evidence-limit": re.compile(
        r"\b(?:(?:does|do|did) not|doesn['’]t|don['’]t|didn['’]t) "
        r"(?:\w+ )?(?:validate|prove|establish)\b", re.I,
    ),
    "residual-status": re.compile(
        r"\bremains? (?:unclear|untested|unproved|unproven|unverified)\b", re.I,
    ),
}

# Reviewed nearby uses retained as controls: literal type/location corrections,
# imperatives, quotations, and direct reports of missing evidence. These are not
# included in the requested count of additional examples.
CONTROLS = set("""
b2f74bb97cbe deabb579cbea 2867b4ea192d ec08ff93e8f0 f084a3b856c0
39ef7d1a81fc ab4fd2c8ec99 605e27bbf38b 5ae99679aa37 6a5e382f79cd
e9d6aec53223 fd5e63185d0a 4f56468f5dd8 5d7fc64b2a1d aa7a21d264ee
a909f99fb2e4 d027ae6e63a4 2e20106ad35a 34afd4467be4 48ebbd94eab5
eb9a0bbdc14b 35a88ddb20e8 8c2917cd201d e6116ef04cb5 c058409d598e
5b3050702eb4 73b975ab1607 ed575d534068 159596ceb0b3 2051a75fd9e6
300c5c924baa d72a892a7861 05d549f05251
1e903685e4f2 f3906d3a6540 19064f64344c b9c601c0867f d2b6911cf648
8a4184345a10 2c28386f42a5 605403481700 1d3e444d25a2 0011db312f95
bcfc1a28f7ce c63dc255afa3 2a6ddaabbf9f
""".split())


def collect(directory):
    records = []
    seen = set()
    for path in sorted(directory.glob("ses_*.jsonl")):
        for line in path.read_text().splitlines():
            message = json.loads(line)
            if message["role"] != "assistant":
                continue
            for part_index, part in enumerate(message["parts"]):
                if part["type"] != "text":
                    continue
                text = part.get("text", "")
                for paragraph in re.finditer(r"\S[\s\S]*?(?=\n[ \t]*\n|\Z)", text):
                    excerpt = paragraph.group()
                    families = [name for name, pattern in FAMILIES.items() if pattern.search(excerpt)]
                    if not families or excerpt.startswith(("|", "```", ">")):
                        continue
                    key = re.sub(r"\s+", " ", excerpt).strip()
                    if key in seen:
                        continue
                    seen.add(key)
                    records.append({
                        "id": hashlib.sha256(key.encode()).hexdigest()[:12],
                        "session_id": path.stem,
                        "source_id": message["sourceId"],
                        "message_id": message["id"],
                        "timestamp_ms": message.get("timeCreated"),
                        "part_index": part_index,
                        "start": paragraph.start(),
                        "end": paragraph.end(),
                        "model": None,
                        "families": families,
                        "usage": "comparison-control" if (
                            families == ["alternative"]
                            or hashlib.sha256(key.encode()).hexdigest()[:12] in CONTROLS
                        ) else "example",
                        "text": excerpt,
                    })
    return records


def save(records, destination):
    destination.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
    )
    examples = [record for record in records if record["usage"] == "example"]
    report = [
        "# History excerpts\n",
        "The quotations preserve assistant text, with offsets and timestamps in the JSONL file.\n",
    ]
    for i, record in enumerate(examples, 1):
        report.extend([
            f"## {i}. {record['id']}\n",
            f"Session `{record['session_id']}`, message `{record['message_id']}`, "
            f"text part {record['part_index']}.\n",
            f"Families: {', '.join(record['families'])}.\n",
            "```text\n" + record["text"] + "\n```\n",
        ])
    destination.with_suffix(".md").write_text("\n".join(report))
    print(f"Saved {len(examples)} examples and {len(records) - len(examples)} controls.")


if __name__ == "__main__":
    save(collect(Path(sys.argv[1])), Path(sys.argv[2]))
