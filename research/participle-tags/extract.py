"""Extract prose from saved assistant messages and authored file payloads.

HTML contributes visible text and comments, Python contributes comments and
docstrings, and C-family files contribute comments with quoted strings skipped.
This does not infer whether a Write copied an existing repository's wording.
"""

import argparse
import ast
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import re
import tokenize


PROSE_SUFFIXES = {".md", ".mdx", ".txt", ".rst"}
C_SUFFIXES = {
    ".c", ".h", ".cpp", ".hpp", ".js", ".mjs", ".jsx", ".ts", ".tsx",
    ".java", ".kt", ".kts", ".swift", ".cs", ".css", ".scss",
}
COMMENT_OR_STRING = re.compile(
    r'(?P<string>"(?:\\.|[^"\\])*"|\x27(?:\\.|[^\x27\\])*\x27|`(?:\\.|[^`\\])*`)'
    r'|(?P<line>//[^\n]*)|(?P<block>/\*[\s\S]*?\*/)',
)


class VisibleHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.comments = [], []
        self.ignored = None

    def handle_starttag(self, tag, attrs):
        if self.ignored:
            return
        if tag in {"script", "style", "pre", "code", "template", "svg"}:
            self.ignored = tag
        elif tag in {"p", "div", "section", "article", "li", "h1", "h2", "h3", "h4", "h5", "h6", "br"}:
            self.parts.append("\n\n")

    def handle_endtag(self, tag):
        if self.ignored:
            if tag == self.ignored:
                self.ignored = None
        elif tag in {"p", "div", "section", "article", "li", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self.parts.append("\n\n")

    def handle_data(self, data):
        if not self.ignored:
            self.parts.append(data)

    def handle_comment(self, data):
        if not self.ignored:
            self.comments.append((self.getpos()[0], data.strip()))


def artifact_parts(text, filename):
    suffix = Path(filename).suffix.lower()
    if suffix in PROSE_SUFFIXES:
        yield "file-prose", None, text
    elif suffix in {".html", ".htm", ".svelte"}:
        parser = VisibleHTML()
        parser.feed(text)
        yield "html-visible", None, "".join(parser.parts)
        for line, comment in parser.comments:
            yield "html-comment", line, comment
    elif suffix == ".py":
        try:
            tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
        except (tokenize.TokenError, IndentationError):
            tokens = []
        for token in tokens:
            if token.type == tokenize.COMMENT:
                yield "python-comment", token.start[0], token.string[1:].strip()
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                docstring = ast.get_docstring(node, clean=False)
                if docstring is not None:
                    yield "python-docstring", node.body[0].lineno, docstring
    elif suffix in C_SUFFIXES:
        for match in COMMENT_OR_STRING.finditer(text):
            if match.lastgroup == "string":
                continue
            comment = match.group()[2:] if match.lastgroup == "line" else match.group()[2:-2]
            comment = re.sub(r"^\s*\* ?", "", comment, flags=re.M)
            yield "c-family-comment", text.count("\n", 0, match.start()) + 1, comment.strip()


def cc_records(paths):
    for path in paths:
        response = json.loads(path.read_text())
        assert not response["partial"]
        for wrapped in response["rows"]:
            assert not wrapped["truncated_cells"]
            row = wrapped["row"]
            for index, entry in enumerate(json.loads(row["trajectory"])):
                message = entry.get("message", {})
                if message.get("role") != "assistant":
                    continue
                metadata = {
                    "dataset": "cc-bench", "dataset_row": wrapped["row_idx"],
                    "model": row["model_name"], "task_id": row["task_id"],
                    "date": entry.get("timestamp"),
                    "source_url": "https://huggingface.co/datasets/zai-org/CC-Bench-trajectories/tree/792c6d3221db4d9ed475702ed61a176dd8948152",
                    "dataset_revision": "792c6d3221db4d9ed475702ed61a176dd8948152",
                }
                for block_index, block in enumerate(message.get("content", [])):
                    locator = f"train/{wrapped['row_idx']}/message/{index}/block/{block_index}"
                    if block.get("type") == "text" and block.get("text") != "(no content)":
                        yield metadata | {"id": locator, "genre": "assistant_message", "text": block.get("text", "")}
                    elif block.get("type") == "tool_use" and block.get("name") in {"Write", "Edit", "MultiEdit"}:
                        values = block["input"]
                        filename = values.get("file_path", "")
                        edits = values.get("edits", [values])
                        for edit_index, edit in enumerate(edits):
                            text = edit.get("content", edit.get("new_string", ""))
                            yield metadata | {
                                "id": f"{locator}/edit/{edit_index}", "genre": "write_payload",
                                "file_path": filename, "text": text, "tool": block["name"],
                            }


def reader_records(rows):
    for row in rows:
        metadata = {k: v for k, v in row.items() if k != "text"}
        dataset = metadata.setdefault("dataset", "trace-commons")
        model = row.get("model") or "unattributed"
        if row["genre"] in {"assistant_message", "assistant_trace_text"}:
            yield metadata | {"group": f"{dataset}/{model}/assistant", "text": row["text"]}
            continue
        filename = row.get("file_path", "")
        for index, (genre, line, text) in enumerate(artifact_parts(row["text"], filename)):
            if text.strip():
                yield metadata | {
                    "id": f"{row['id']}/extract/{index}",
                    "group": f"{dataset}/{model}/{genre}", "genre": genre,
                    "artifact_line": line, "text": text,
                }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jsonl", type=Path, action="append", default=[])
    parser.add_argument("--cc-response", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = list(cc_records(args.cc_response))
    for path in args.jsonl:
        rows.extend(json.loads(line) for line in path.read_text().splitlines())
    records = list(reader_records(rows))
    args.output.write_text("".join(json.dumps(row) + "\n" for row in records))
    print(f"Extracted {len(records)} reader-text records from {len(rows)} assistant records/payloads.")


if __name__ == "__main__":
    main()
