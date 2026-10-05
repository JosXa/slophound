# Structural Jev experiment

This experiment asks four semantic questions about a document. It does not estimate authorship. It is separate from default linting and does not change the exit codes from linting.

## Questions

- `redundant_conclusion`: Does the ending repeat earlier claims without adding useful synthesis, a decision, a qualification, or a next action?
- `empty_roadmap`: Does the opening announce the article's coverage without giving useful routing or sequencing information?
- `unsupported_stakes`: Does the document inflate consequences beyond the evidence or causal account it supplies?
- `formulaic_contrast`: Does it caricature an old/new or not-X-but-Y distinction instead of explaining a substantive difference?

The inspiration is SlopShape, https://arxiv.org/pdf/2609.15369v2, particularly its discussion of article structure and its stated limits. These are independently written editing rubrics, not a reproduction of the paper's feature instrument or classifier. The paper's performance figures do not apply to this experiment.

## Evaluation design

`cases.jsonl` contains 23 documents. Twenty are constructed by Walter for this experiment and carry rubric labels. Both the positive and negative examples are model-written. They cannot test AI-versus-human discrimination. The other three are existing repository corpus texts, included without structural gold labels and excluded from accuracy calculations. The repository source labels are retained. They have not been independently authenticated here.

The labelled set has eight development examples, eight holdout variants prepared before live evaluation, and four challenge examples. These holdout cases are same-author, same-template probes, not an independent external benchmark. Challenges include quoted bad writing, an instruction embedded in an HTML comment, a combined template, and a concrete rewrite.

All four questions are labelled on each constructed example. Cross-feature negatives intentionally test whether one conspicuous fault contaminates other judgments. Labels are human-readable hypotheses created by the same assistant that proposed the experiment, not independent expert annotations.

Frozen input SHA-256 before inference:

`84ae3797bbee95f857ce2f4a5049761105110d4b1aeb432a42fc3f674032b9d6`

The decision bands are exploratory: P(yes) >= 0.9 is flagged, <= 0.1 is clear, and the middle is review. Report abstentions, false positives, false negatives, missing answers and request failures separately. Do not interpret a criterion probability as P(AI authorship), or a high score as calibrated certainty.

## Data boundary

Only these synthetic and repository-corpus documents are authorised for the live run. No personal messages, source code, or secrets belong in the requests. The runner must not send labels, case names, split assignments, or source labels to the evaluator. Live calls require explicit opt-in and credentials supplied through the established configuration or environment. Dry runs must not read credentials.

Preserve raw provider output for audit. Record the returned model version, latency and usage. Do not silently drop unsuccessful cases or retune labels after seeing predictions. Any later revisions must be distinguished from this first run.
