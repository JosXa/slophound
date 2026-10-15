# Contrastive results and verification caveats

History study, 2026-10-15, with the broader construction policy applied on 2026-10-16.

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

Deduplication collapses whitespace in each paragraph before comparison and
retains paraphrases and repeated sentences within different paragraphs. Nearby
literal corrections, quoted examples, imperatives, and direct missing-evidence
reports were retained as controls after review. Paragraphs containing only the
alternative marker were also assigned to controls.

The exports contain no model attribution, so every record has `model: null`.
The sample concentrates on engineering investigations, especially video timing.
Comparing GPT's frequency with other models requires attributed samples.

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

`template.contrastive-negation` replaces the separate rules for copular contrasts,
evidence-scope denials, and abstract benefits. A deterministic token scanner
recognizes these constructions with arbitrary subjects, predicates, and complements:

- A claim followed by a punctuation-separated negative alternative, such as
  `X, not Y`, including inserted corrections.
- Clauses joined by `but`, with negation on either side.
- A positive clause followed by a semicolon and a negative clause.
- Adjacent sentences where the second refers back with a pronoun or
  demonstrative and negates its opening claim.

Matching depends on grammatical markers such as `not`, `but`, contractions,
and punctuation. Technical nouns, evidence verbs, and abstract-noun suffixes
have no special treatment. Statistical parsing and model calls are unnecessary.
The scanner retains sentence offsets, respects Markdown block boundaries and
masked code, and handles line wrapping. Ordinary independent negative reports
still pass.

`template.residual-verification` catches impersonal verdicts ending in untested,
unproved, unproven, unverified, unvalidated, or unconfirmed. A report that names
the check the author did not perform passes. Explained uncertainty about a
cause also passes.

Both rules report bites. A factual correction requires a rewrite that preserves
its consequential distinction, including units, mutation behavior, permissions,
prices, and missing checks. The abstract-benefit example now receives a bite.

## Measurement

[evaluation.json](evaluation.json) records the full findings, source revisions,
denominators, and comparison with the previous rule catalog. Each rule runs
alone so overlapping findings cannot hide a match.

| Sample | Documents | Prose words | Findings | Added findings |
| --- | ---: | ---: | ---: | ---: |
| Historical examples | 93 | 4,418 | 111 | 60 |
| Historical comparison controls | 105 | 4,959 | 41 | 39 |
| Rust RFCs | 512 | 741,422 | 1,588 | 1,574 |
| Ghostbuster human essays | 100 | 58,383 | 59 | 58 |
| Ghostbuster human Reuters | 100 | 46,945 | 76 | 75 |
| Ghostbuster human stories | 100 | 58,277 | 144 | 142 |

The targeted rules cover 91 of the 93 historical examples, compared with 51 in
the preceding implementation. Multiple findings can occur in one excerpt.
The two remaining paragraphs use longer causal qualifications with `so` and
embedded negative clauses outside the scanner's constructions.

The broader policy produces 1,867 findings across 550 of 812 external human
documents. These are raw match counts, with sampled contexts inspected for
accidental grammatical matches. Human and model-authored writing follow the same
policy. Evaluating authorship or precision requires separate labeled assessments.
The control labels preserve the initial narrow
review, so matches in that group are expected after the policy change.

The repository's original human fixtures retain their text. Six exact positive
spans are recorded in [human-findings.json](../../tests/corpus/human-findings.json).
Selftests reject both additional findings and missing expected findings. This
fixture manifest has no effect on lint output. Repository documentation was
rewritten to comply with the same rule while retaining its factual limits.

## Operator review

[operator-review.jsonl](operator-review.jsonl) preserves the initial judgments
on ten previously missed excerpts. The operator subsequently accepted banning
all ten, including those first described as acceptable or borderline.

Eight proposed factual counterexamples were also explicitly accepted as true
positives. They cover timeout units, local versus remote branches, copies versus
references, permission inheritance, pricing, diagnosis, token tests, and backup
restoration. All eighteen examples now have blocking regression cases in
[test_contrastive_scope.py](../../tests/test_contrastive_scope.py).

## Reproduction

From the project root, run the collector on JSONL session exports:

```sh
python research/contrastive-scope/collect.py EXPORT_DIRECTORY research/contrastive-scope/corpus.jsonl
```

Run the evaluator with the project's dependencies available, passing local
checkouts of rust-lang/rfcs and vivek3141/ghostbuster-data. Both source revisions
are pinned in the script. The final argument pins the previous rule catalog.

```sh
python research/contrastive-scope/evaluate.py RUST_CHECKOUT GHOSTBUSTER_CHECKOUT b6e2551
./slophound test
```

The focused regression suite uses unittest discovery:

```sh
python -m unittest discover -s tests -p test_contrastive_scope.py -v
```
