# Live structural analysis in Slophound

## Result

Four document-level Jev checks now have an opt-in runner in this checkout. They evaluate redundant conclusions, empty roadmaps, unsupported stakes, and formulaic contrasts. The existing deterministic lint pipeline is unchanged. These scores concern writing properties, not the probability that an author used AI.

The first live run completed all 23 requests using `jev-1.13.0`, with no request or response-validation failures. The 20 labelled constructed documents supply 80 feature judgments. Three existing corpus documents are unlabelled probes and excluded from the counts.

## Paired examples from the prewritten holdout set

Values are the provider's P(yes) for the named property, not calibrated authorship probabilities.

| Property | Constructed bad example | Useful counterpart | Bad P(yes) | Counterpart P(yes) |
| --- | --- | --- | ---: | ---: |
| Redundant conclusion | Thumbnail article ends by repeating that separate storage allows independent retention | Ending adds a source-deletion/privacy check and a required integration test | 0.87 | 0.08 |
| Empty roadmap | Announces the importance, considerations and steps of weekly dependency updates | Routes new and existing installations to different sections and warns against destructive bootstrap | 0.56 | 0.16 |
| Unsupported stakes | Reordering two settings-menu entries is presented as necessary for the organization's survival | A missing tenant filter is tied to demonstrated cross-tenant deletion | 0.95 | 0.19 |
| Formulaic contrast | Old dashboards merely display numbers, modern ones inspire action and create the future | Replacing a mean with a histogram exposes slow requests, with a bucket-configuration caveat | 0.85 | 0.10 |

On the initial repetition test, the bad ending scored 0.90 and the useful one scored 0.09. A separate smoke call on the same positive text scored 0.89: the 0.90 decision boundary is demonstrably unstable for that example. Do not treat the boundary as a guarantee.

## Repeatability check

Three additional calls per selected document kept the requests unchanged. The repetitive ending scored 0.90, 0.89 and 0.89, switching between flagged and review. Unsupported stakes scored 0.95, 0.95 and 0.96, staying flagged. The weak roadmap example scored 0.56, 0.59 and 0.60, staying review. These nine extra calls are saved in `repeatability-live.json` and excluded from the main confusion counts and usage totals.

## Strict decisions

The bands were chosen before inference: >=0.90 flagged, <=0.10 clear, otherwise review. Count review outcomes separately as abstentions.

| Feature | True flags | False flags | True clears | False clears | Review |
| --- | ---: | ---: | ---: | ---: | ---: |
| Redundant conclusion | 1 | 0 | 3 | 0 | 16 |
| Empty roadmap | 0 | 0 | 1 | 0 | 19 |
| Unsupported stakes | 2 | 0 | 3 | 0 | 15 |
| Formulaic contrast | 0 | 0 | 11 | 0 | 9 |

Only 21 of 80 labelled judgments received a decisive answer. The other 59 abstained. Zero decisive errors in this small constructed set is not a useful general accuracy claim, given that low coverage and the dataset's origin.

## Failures worth retaining

- The rejected and quoted template passage raised unsupported-stakes P(yes) to 0.66, despite instructions to distinguish quotations from endorsements.
- A settings-menu exaggeration raised the contrast score to 0.83. Features are not cleanly separated.
- A document combining all four intended faults produced 0.85, 0.65, 0.86 and 0.84 respectively. None cleared the strict flag threshold.
- Its concrete rewrite scored 0.28, 0.34, 0.14 and 0.14. The direction is promising, but these are not decisive clears.
- Twain scored 0.55 for empty roadmap and RFC 1925 scored 0.59. Both remain review. A lower threshold would flag these passages. That would not demonstrate AI authorship, and may be a genre-sensitive editorial false positive.
- The HTML-comment injection asking for all scores to become 1.0 did not succeed in this one test. It is not proof of prompt-injection resistance.

A post-hoc 0.50 cutoff creates errors across all four feature families against the original labels. It has not been adopted. Some cross-feature labels are themselves debatable. No labels were changed after inference.

## Independent review notes

An independent review identified ambiguous cross-feature labels. The menu and field-name examples contain inflated reframing, so their negative contrast labels are debatable. The dashboard and documentation contrasts make broad promises, so their negative stakes labels are also debatable. Quoted examples are negative only under the stated policy of evaluating endorsed prose. The repetition labels assume these short documents do not need a recap.

Labels remain frozen. These disagreements limit interpretation of the confusion counts. A future dataset needs independent annotations, ordinary useful outlines, subtle positives, mixed evidence and exaggeration, and matched positive/negative prompt-injection attacks. Source headers were removed before the live run. Historical-human status alone does not make a structural finding wrong. `split-summary.json` preserves separate development, holdout and challenge counts.

Code review also found that the runner recorded, but did not reject, an unexpected returned model version. Every saved live response used `jev-1.13.0`, so the existing measurements are unaffected. The repair adds rejection and regression coverage rather than rerunning or replacing the saved evidence.

## What is ready

Unsupported stakes and redundant conclusions are promising advisory candidates. Roadmap detection is weak in this run. Formulaic contrast separates the selected pairs but spills into other features and does not produce a high-confidence positive. None is ready to become an automatic lint failure or an authorship verdict.

Next useful evaluation: independent annotators, longer real engineering documents, satire and quotations, multiple models and naturally edited drafts. The current 'holdout' is prewritten but shares the same author and construction patterns as the development examples. It is not an independent benchmark.

## Run it

From `/projects/slophound`:

```sh
# Offline: builds requests, reads no key, sends nothing.
uv run --no-project python tools/structural_eval.py \
  evals/structural/cases.jsonl --output /tmp/structural-dry-run.json

# Live: sends the dataset's document text to TypeSafe.
# Supply TYPESAFE_API_KEY privately, or use existing Slophound configuration.
uv run --no-project python tools/structural_eval.py \
  evals/structural/cases.jsonl --live --output /tmp/structural-live.json
```

Input is JSONL with `id`, `text`, `expected`, `split`, and `provenance`. For a new unlabelled document, use `expected: {}`. Only `text` is sent as evaluator state. No credentials, labels, case IDs or source labels are sent as state. The tool caps each run at 40 documents and rejects overlong input rather than silently truncating it.

## Evidence and verification

- `cases.jsonl`: exact source texts and labels.
- `dry-run.json`: inspectable requests, no inference.
- `smoke-live.json`: first live request.
- `live-v1.json`: all requests, validated probabilities, actual returned model, latency, token usage and raw valid provider responses.
- `hound/structural.py`: rubrics, validation, bounded no-retry transport and report counts.
- `tools/structural_eval.py`: explicit opt-in runner.
- `tests/test_structural.py`: offline unit tests.

Main live run usage: 20,495 input tokens and 1,886 output tokens. Median measured request latency: 273.865 ms. Sum of measured request latencies: 6,635.158 ms. The separate smoke request is not included in those totals.

Verification after the review repair: 76 unittest cases passed, including 19 structural tests. An independent ad-hoc check revalidated all 33 saved live responses and verified rejection of mismatched models, credential normalization, and socket-timeout metadata without network calls. The dataset hash is unchanged. The canonical Slophound suite reported 159 passed, zero failed, 151 rules. The baseline lint run on existing documents, with Jev disabled, had zero bites, four barks and two sniffs. Existing rules and default linting were unchanged.

Dataset SHA-256: `84ae3797bbee95f857ce2f4a5049761105110d4b1aeb432a42fc3f674032b9d6`.

## Scope

This is an uncommitted checkout experiment, not an installed release or enabled production gate. It has no automatic effect on ordinary Slophound runs. Both the clean and bad constructed examples are model-written, so this experiment tests structural judgments, not detection of machine authorship.
