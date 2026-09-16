---
name: slophound
description: Use when writing or editing prose for a human audience.
---

# Slophound

Run the linter before the editorial review. Keep the reference files closed until the relevant step below.

## 1. Lint and revise

Write the draft to a file, then run:

```sh
uvx --python 3.13 --from 'git+ssh://git@github.com/JosXa/slophound.git' slophound draft.md
```

This requires `uv` and Git access to the repository. The first run downloads dependencies. For a local checkout, replace the Git URL after `--from` with its absolute path. Reuse the same source throughout the review.

Fix every bite. Address barks and sniffs when they improve the text. Rerun after edits and retain the reports so you can count resolved findings. Exit code 0 means no bites, 1 means bites remain, and 2 means the tool failed. Resolve tool failures before continuing.

Treat accurate barks and sniffs as optional editorial advice. Keeping one needs only a reason in the final report and does not require a rule correction.

If a finding is a false positive, preserve the legitimate wording and show the operator the sentence, rule, and reason. Strongly recommend contributing a correction, and ask whether they want to prepare one. After approval, read [Contributing a correction](./references/contributing.md). Repository work and PR submission require the operator's authorization. Leave installed skills and the `uvx` cache unchanged.

The lint stage is complete when no bites remain, except false positives disclosed to the operator for which they declined or deferred a correction. Keep those findings visible in the final report. Do not disable rules or mask prose to obtain a clean result.

The linter masks tables, code, and other non-prose syntax. For reader-facing text inside a masked region, lint a plain-text extract as well and apply revisions to the original document. Preserve code and quotations that must remain exact.

## 2. Review the prose

Only after completing the lint stage, read [Editorial review](./references/editorial-review.md) in full. Apply its concrete tests, before/after examples, and acceptable cases to the document. Identify the intended audience and use your judgment about tone.

## 3. Verify and report

Rerun the linter after editorial changes, including any plain-text extracts. Resolve new bites using step 1. Check the final document for changes in meaning.

Report how many bites you resolved and how many barks or sniffs you addressed. Count resolved findings from the reports, including findings introduced and then fixed during editing. Avoid counting the same finding on repeated runs as a new fix.

Show the remaining findings using the final linter output in a fenced text block. Preserve the file, line, column, severity, rule ID, source text, caret span, and diagnostic message. Omit the contribution footer and repeated installation logs. Follow each retained finding with a short reason. List unresolved false positives separately with their original severity. A remaining bite must never be reported as zero bites.

For editorial concerns the linter did not report, quote the exact passage with its location and explain the concern separately. Never invent a rule ID or present an editorial observation as linter output.

For example:

```text
Done. Resolved 3 bites and addressed 1 bark.
Sniffs for your review:

draft.md:18:10  sniff  noun.cluster-three
  Read the deployment pipeline configuration first.
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  Three nouns stacked into one phrase ("database connection pool"). Readable, but one more and it tips over. Consider a preposition: "the connection pool of the database".

Kept: "deployment pipeline configuration" is the established term used by this team.
```
