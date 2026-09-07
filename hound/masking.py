"""Turn Markdown into views the detection layers can search without tripping over
markup, while keeping every character offset identical to the original text.

Three views, all exactly as long as the source text:

- `masked`: code fences, inline code, URLs, link targets, front matter (except
  values the reader sees, such as a slide `heading:`), HTML comments, HTML tags
  and tables are replaced by spaces. Everything else,
  including emphasis markers and quote characters, is untouched. Punctuation
  rules run here because they care about the raw characters.
- `prose`: `masked` with typographic quotes normalised to ASCII and Markdown
  markup (heading hashes, list bullets, blockquote markers, emphasis) blanked.
  Phrase, template and grammar rules run here.

Blocks describe the structure: each heading, list item, paragraph, blockquote
paragraph or rendered front-matter value (`field`) becomes one block with its
kind and span, so layers can skip headings or quotes and the document layer can
reason about paragraphs.

Maintenance rules for this file:

- Every regex carries a comment saying what it matches and why it exists or was
  changed. Most of them were tightened after a false positive on a real
  document, and the next reader needs that story to avoid undoing the fix.
- When a document from the wild exposes a gap, add a reduced copy of the
  offending construct to `check_masking` in `selftest.py` before changing the
  regex, so the case stays covered.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Characters normalised in the prose view. Same length, so offsets survive.
_QUOTE_MAP = str.maketrans({"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"'})

# Fenced code, ``` or ~~~, closed by the same fence. Code is never prose.
_FENCE_RE = re.compile(r"^(```|~~~)[^\n]*\n.*?^\1[^\n]*$", re.M | re.S)
# Inline code. Documentation quotes phrases in backticks to talk about them, and
# those must not count as the author using them.
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
# Front matter at the top of the file, plus the per-slide `---` blocks Slidev
# and Marp put between slides. The YAML structure is never prose, but the values
# often are: a slide's `heading:`, `lede:` or `callout:` is rendered text the
# reader sees, so `_expose_front_matter_values` puts multi-word values back as
# `field` blocks. The body lines must look like YAML (key at column 0 or an
# indented continuation) so a `---` thematic break followed by prose is not
# swallowed. Added after slide decks reported `layout: default` as a repeated
# paragraph opener.
_FRONT_MATTER_RE = re.compile(r"(?:\A|(?<=\n\n))---[ \t]*\n(?:[A-Za-z_][^\n]*\n|[ \t]+[^\n]*\n)*?---[ \t]*\n")
# One YAML line: optional indent and list dash, optional `key:`, then the value.
_YAML_LINE_RE = re.compile(r"^([ \t]*(?:-[ \t]+)?)(?:([A-Za-z_][\w-]*):[ \t]+)?(.*?)[ \t]*$")
# Keys whose values are machine input even when they contain spaces (`class:
# text-center mt-4`). Everything else with two or more words is treated as text
# the reader will see.
_MACHINE_KEYS = frozenset(
    "class style src href url link image background backgroundimage icon color colour "
    "accent layout theme transition font fonts id key glob path file files tags".split()
)
# Link label of an inline link. Only Title Case labels get blanked (see
# `_blank_title_labels`): they are names of pages, not the author's words. Added
# after a link to a Confluence page called "Artifact-Centric Approach" fired
# `template.compressed-compound`.
_LINK_LABEL_RE = re.compile(r"\[([^\]\n]+)\]\(")
# HTML comments hold speaker notes and reviewer remarks, not delivered prose.
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
# Inline HTML and Vue/MDX components. Attributes may wrap onto following lines
# (CommonMark HTML blocks allow it and component-heavy Markdown does it a lot), so
# a tag may span lines as long as everything up to `>` is an attribute list, and
# quoted attribute values may themselves span lines (`:items="[\n ... \n]"`).
# A lone `<` in prose has no such continuation and stays visible. Each token is
# delimited unambiguously (one `\s*`, then a name or quoted string) so a
# non-matching `<` fails fast instead of backtracking across the document.
_HTML_TAG_RE = re.compile(
    r"</?[A-Za-z][A-Za-z0-9.:-]*"  # tag or component name
    r"(?:\s+[A-Za-z_:@#][\w.:@#-]*(?:=(?:\"[^\"]*\"|'[^']*'|[^\s\"'<>`]+))?)*"
    r"\s*/?>"
)
# Fenced containers (`::: tip` ... `:::`) from markdown-it and its derivatives
# (VitePress, Docusaurus, Obsidian). Only the marker lines go; the content between
# them is normal prose and stays linted.
_CONTAINER_MARK_RE = re.compile(r"^[ \t]*:{3,}[^\n]*$", re.M)
# Bare URLs. Their path segments look like slug-compounds and hyphenated words.
_URL_RE = re.compile(r"(?:https?|ftp)://[^\s)>\]]+|www\.[^\s)>\]]+")
# The `](target)` part of a link, including titles. Runs after the label pass.
_LINK_TARGET_RE = re.compile(r"\]\([^)\n]*\)")
# Pipe tables. Cells are fragments and would skew every sentence metric.
_TABLE_LINE_RE = re.compile(r"^[ \t]*\|.*$", re.M)
# The markers below are blanked in the prose view so a rule anchored at `^` sees
# the first word of the heading, item or quote rather than the markup.
_HEADING_RE = re.compile(r"^(#{1,6})[ \t]+")
_BULLET_RE = re.compile(r"^([ \t]*)([-*+]|\d+[.)])[ \t]+")
_QUOTE_MARK_RE = re.compile(r"^([ \t]*>)+[ \t]?")
# Emphasis delimiters attached to a word on the inner side. A lone `*` or `_`
# with spaces on both sides is left alone (it might be arithmetic or a name).
_EMPHASIS_RE = re.compile(r"(\*\*|__|\*|_)(?=\S)|(?<=\S)(\*\*|__|\*|_)")
# Closing hashes of an ATX heading (`## Title ##`).
_ATX_TRAILING_RE = re.compile(r"[ \t]+#+[ \t]*$")


@dataclass
class Block:
    kind: str  # heading | list | paragraph | quote | field
    start: int
    end: int  # exclusive


@dataclass
class Document:
    path: str
    text: str
    masked: str
    prose: str
    blocks: list[Block]
    line_starts: list[int]

    def line_col(self, offset: int) -> tuple[int, int]:
        """1-based line and column for an offset."""
        import bisect

        line = bisect.bisect_right(self.line_starts, offset) - 1
        return line + 1, offset - self.line_starts[line] + 1

    def line_span(self, offset: int) -> tuple[int, int]:
        """Start and end offsets of the line containing `offset`."""
        line, _ = self.line_col(offset)
        start = self.line_starts[line - 1]
        end = self.line_starts[line] - 1 if line < len(self.line_starts) else len(self.text)
        return start, end

    def blocks_of(self, *kinds: str) -> list[Block]:
        return [b for b in self.blocks if b.kind in kinds]

    def word_count(self) -> int:
        return len(re.findall(r"[A-Za-z0-9'\u00C0-\u024F]+", self.prose))


def _blank(text: str, start: int, end: int) -> str:
    """Replace text[start:end] with spaces, keeping newlines."""
    segment = "".join("\n" if ch == "\n" else " " for ch in text[start:end])
    return text[:start] + segment + text[end:]


def _blank_matches(text: str, regex: re.Pattern) -> str:
    out = text
    for m in regex.finditer(text):
        out = _blank(out, m.start(), m.end())
    return out


def _expose_front_matter_values(text: str, masked: str) -> tuple[str, set[int]]:
    """Restore rendered text inside front matter blocks and report where it sits.

    Slide decks and static-site pages keep visible copy in YAML: `heading:`,
    `lede:`, `callout:`, `title:`, `description:`, list items with `title:` and
    `detail:`. A value with two or more words, under a key that is not a machine
    setting, is text the reader sees and is linted like a paragraph. Keys,
    indentation and one-word or quoted-machine values stay blank. Returns the
    updated masked view and the start offsets of the exposed lines.
    """
    field_lines: set[int] = set()
    for fm in _FRONT_MATTER_RE.finditer(text):
        pos = fm.start()
        for raw_line in text[fm.start() : fm.end()].split("\n"):
            line_start = pos
            pos += len(raw_line) + 1
            if raw_line.strip() == "---":
                continue
            m = _YAML_LINE_RE.match(raw_line)
            if not m:
                continue
            key, value = m.group(2), m.group(3)
            if key is not None and key.lower() in _MACHINE_KEYS:
                continue
            vstart = m.start(3)
            vend = m.end(3)
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                vstart += 1
                vend -= 1
            if len(re.findall(r"[A-Za-z\u00C0-\u024F]{2,}", raw_line[vstart:vend])) < 2:
                continue
            s, e = line_start + vstart, line_start + vend
            masked = masked[:s] + text[s:e] + masked[e:]
            field_lines.add(line_start)
    return masked, field_lines


def build_document(path: str, text: str, skip_quotes: bool = False) -> Document:
    masked = text
    masked = _blank_matches(masked, _FRONT_MATTER_RE)
    masked, field_lines = _expose_front_matter_values(text, masked)
    masked = _blank_matches(masked, _FENCE_RE)
    masked = _blank_matches(masked, _INLINE_CODE_RE)
    masked = _blank_matches(masked, _HTML_COMMENT_RE)
    masked = _blank_matches(masked, _HTML_TAG_RE)
    masked = _blank_matches(masked, _CONTAINER_MARK_RE)
    masked = _blank_title_labels(masked)  # before targets: it keys off `](`
    masked = _blank_matches(masked, _LINK_TARGET_RE)
    masked = _blank_matches(masked, _URL_RE)
    masked = _blank_matches(masked, _TABLE_LINE_RE)

    line_starts = [0] + [m.end() for m in re.finditer(r"\n", text)]
    blocks: list[Block] = []
    prose_lines: list[str] = []
    masked_lines: list[str] = []

    pos = 0
    current: Block | None = None
    for raw_line in masked.split("\n"):
        line = raw_line
        line_start = pos
        pos += len(raw_line) + 1
        stripped = line.strip()

        kind: str | None
        if not stripped:
            kind = None
        elif line_start in field_lines:
            # A front-matter value the reader sees (`lede: Both sit at the top.`).
            # One block per line, like a heading; the rhythm metrics skip it.
            kind = "field"
        elif _QUOTE_MARK_RE.match(line):
            kind = "quote"
            if skip_quotes:
                # --skip-quotes hides quoted text from every layer, punctuation included.
                line = " " * len(raw_line)
        elif _HEADING_RE.match(line):
            kind = "heading"
        elif _BULLET_RE.match(line):
            kind = "list"
        else:
            kind = "paragraph"

        prose_line = line.translate(_QUOTE_MAP)
        if kind == "quote":
            if skip_quotes:
                prose_line = " " * len(line)
            else:
                prose_line = _blank_prefix(prose_line, _QUOTE_MARK_RE)
                # A quoted list item or heading still has its own marker.
                prose_line = _blank_prefix(prose_line, _BULLET_RE)
                prose_line = _blank_prefix(prose_line, _HEADING_RE)
        elif kind == "heading":
            prose_line = _blank_prefix(prose_line, _HEADING_RE)
            prose_line = _blank_matches(prose_line, _ATX_TRAILING_RE)
        elif kind == "list":
            prose_line = _blank_prefix(prose_line, _BULLET_RE)
        prose_line = _blank_matches(prose_line, _EMPHASIS_RE)
        prose_lines.append(prose_line)
        masked_lines.append(line)

        line_end = line_start + len(raw_line)
        if kind is None:
            current = None
            continue
        # Headings and list items are one block per line. Paragraph and quote
        # lines continue the previous block of the same kind.
        if current is not None and current.kind == kind and kind in ("paragraph", "quote"):
            current.end = line_end
        else:
            current = Block(kind, line_start, line_end)
            blocks.append(current)

    prose = "\n".join(prose_lines)
    masked = "\n".join(masked_lines)
    assert len(prose) == len(text) == len(masked), "views must keep offsets"
    return Document(path, text, masked, prose, blocks, line_starts)


def _blank_title_labels(text: str) -> str:
    """Hide link labels that are names of things, such as page titles in Title Case.

    A lowercase label like [the migration guide](...) is prose and stays visible.
    """
    out = text
    for m in _LINK_LABEL_RE.finditer(text):
        label = m.group(1)
        tokens = [t for t in re.split(r"[\s-]+", label) if t]
        if len(tokens) >= 2 and all(t[0].isupper() or t[0].isdigit() for t in tokens):
            out = _blank(out, m.start(1), m.end(1))
    return out


def _blank_prefix(line: str, regex: re.Pattern) -> str:
    m = regex.match(line)
    if not m:
        return line
    return " " * m.end() + line[m.end() :]
