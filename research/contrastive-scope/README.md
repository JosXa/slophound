# Contrastive results and verification caveats

History study, 2026-10-15.

## Corpus

[corpus.md](corpus.md) contains 93 additional assistant excerpts from 15 sessions.
[corpus.jsonl](corpus.jsonl) also retains 105 comparison controls. The five
user-provided examples live separately in [seeds.jsonl](seeds.jsonl) and do not
contribute to the additional-example count.

Recall exported 22 historical sessions as JSONL. Extraction accepted text parts
authored by the assistant and retained their session ID, message ID, text-part index, timestamp,
and original character offsets. Every saved excerpt was checked against that
source slice. Tool inputs, tool results, and user messages supplied no examples.
Full transcripts stay outside the committed corpus.

Deduplication collapses whitespace in each paragraph before comparison. It does
not merge paraphrases or repeated sentences within different paragraphs. Nearby
literal corrections, quoted examples, imperatives, and direct missing-evidence
reports were retained as controls after review. Paragraphs containing only the
alternative marker were also assigned to controls.

The exports contain no model attribution, so every record has `model: null`.
The sample concentrates on engineering investigations, especially video timing;
it cannot establish how often GPT uses these forms relative to other models.

## Recurring forms

The example labels overlap:

- 69 excerpts pair a positive claim with a rejected alternative.
- 14 use a negative evidence verb such as validate, prove, or establish.
- 17 close with an impersonal statement about incomplete verification.

Subject changes and contractions preserve the first form. The second often
repeats an evidence verb across two sentences, first affirming a result and then
denying a broader conclusion. The third appends a general verification status
after a measured result. Individual excerpts can combine these forms.

The factual limitation can matter. A useful rewrite states what was measured,
names the check the author did not perform, and explains any consequence for
the reader's decision. Removing the limitation would misrepresent the evidence.

## Rules

The existing `template.is-a-x-not-a-y` rule now covers plural subjects,
contractions, article-free complements, and wrapped text. Its technical type
exceptions also cover the distinction between concrete types and variables.

`template.evidence-scope-contrast` requires a sentence-opening evidence claim
followed by a rejected conclusion in the same paragraph. It distinguishes
inferential uses of support from ordinary feature support. Functional input
validation and connection establishment have regression controls.

`template.residual-verification` catches impersonal verdicts ending in untested,
unproved, unproven, unverified, unvalidated, or unconfirmed. A report that names
the check the author did not perform passes. Explained uncertainty about a
cause also passes.

All three rules report bites. Sentence templates match within one paragraph or
list item, including ordinary line wrapping.

## Measurement

[evaluation.json](evaluation.json) records the full findings, source revisions,
denominators, and comparison with the previous rule catalog. Each rule runs
alone so overlapping findings cannot hide a match.

| Sample | Documents | Prose words | Findings | Added findings |
| --- | ---: | ---: | ---: | ---: |
| Historical examples | 93 | 4,418 | 46 | 40 |
| Historical comparison controls | 105 | 4,959 | 2 | 0 |
| Rust RFCs | 512 | 741,422 | 14 | 11 |
| Ghostbuster human essays | 100 | 58,383 | 1 | 1 |
| Ghostbuster human Reuters | 100 | 46,945 | 1 | 1 |
| Ghostbuster human stories | 100 | 58,277 | 2 | 1 |

The targeted rules cover 46 of the 93 historical examples, compared with six
before this change. Other excerpts include noncopular contrasts, noun subjects,
and longer evidence qualifications outside the implemented templates. These
related constructions are retained for further evaluation.

The evidence and residual-status rules produced no findings in the external
human samples. The copular rule matches constructions in human writing too,
including technical explanations and quoted speech. These findings express a
style constraint and provide no evidence of machine authorship. The repository's
human regression corpus and existing documentation pass without edits.

## Reproduction

From the project root, run the collector on JSONL session exports:

```sh
python research/contrastive-scope/collect.py EXPORT_DIRECTORY research/contrastive-scope/corpus.jsonl
```

Run the evaluator with the project's dependencies available, passing local
checkouts of rust-lang/rfcs and vivek3141/ghostbuster-data. Both source revisions
are pinned in the script. The final argument pins the previous rule catalog.

```sh
python research/contrastive-scope/evaluate.py RUST_CHECKOUT GHOSTBUSTER_CHECKOUT 073e33d17068736ac8e4c2db02e8ced6a4f5f54d
./slophound test
```

The focused regression suite uses unittest discovery:

```sh
python -m unittest discover -s tests -p test_contrastive_scope.py -v
```
