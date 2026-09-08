#!/usr/bin/env -S uv run --script --quiet
# /// script
# requires-python = ">=3.11,<3.14"
# dependencies = [
#   "spacy>=3.8,<3.9",
#   "en-core-web-sm @ https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl",
# ]
# ///
"""Print the spaCy parse of each sentence given on the command line.

Maintainer tool for writing verb/adj/noun rules: run it on the sentence you
want to catch and on the sentence you want to leave alone, then write the
DependencyMatcher pattern against the difference. Same model and version as
the linter itself, so what you see here is what the rule will see.

    tools/parse.py "That holds even under load." "The map holds three keys."
"""

import sys

import spacy


def main(sentences: list[str]) -> int:
    if not sentences:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    nlp = spacy.load("en_core_web_sm", exclude=["ner"])
    for sentence in sentences:
        print(f"## {sentence}")
        for token in nlp(sentence):
            print(
                f"  {token.i:2} {token.text:14} {token.lemma_:12} {token.pos_:6} "
                f"{token.tag_:5} {token.dep_:10} -> {token.head.text}"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
