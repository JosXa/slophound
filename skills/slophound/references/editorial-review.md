# Editorial review

Review the document after the lint stage. This reference retains the judgment checks from humanize, with examples and acceptable uses. Fixed phrase inventories and mechanical patterns remain in the linter. A clean lint result does not establish that a claim is supported, a metaphor is useful, or a paragraph adds information.

Apply each check to the document. The examples illustrate possible revisions, with invented details where useful. Preserve established facts in the actual document, and use available evidence when adding specifics. Keep exact quotations and code intact. These examples do not override a linter finding. Handle false positives through the skill's approval flow.

## Audience

Identify who will read the text, what they already know, and what they need to decide or do. Infer this from the document and the assignment. Ask only when uncertainty would materially change the revision. Choose tone and detail for that audience.

## Concrete effects and significance

Replace praise, importance, and descriptions of how a feature feels with its behavior or a supported result. Remove an evaluative word and check whether any information is lost. If a benefit could describe almost any project, name the mechanism that produces it or remove the claim.

```text
Before: The database stays close at hand, with SQL you can read.
After: The .toSQL() method returns the exact SQL sent to the database.

Before: The new index makes the service more maintainable.
After: The new index removes the separate lookup table and its update job.
```

Keep an importance claim when the dependency or consequence is stated: an index may be essential because every query needs it. A trailing clause may explain a measured consequence, but it should not merely award praise to the preceding fact.

## Evidence, diagnosis, and completion

Check what supports each conclusion. A diagnosis needs a mechanism, observations, or a verification plan. Completion claims need the test scope and observed result. Check attributed claims against a named source. One source cannot establish a consensus.

```text
Before: This is probably a race condition.
After: The reader can observe the buffer after the length changes but before the payload is written. Trace those two writes to confirm the order.

Before: Implemented and verified.
After: All 42 unit tests passed. I did not exercise the migration path.

Before: Studies show that onboarding is faster.
After: In our April trial, the median setup time fell from 40 minutes to 25.
```

Keep a provisional diagnosis when it states the observations and how to test it. Keep a named source and its limitations. If evidence is unavailable, say what remains unknown. A retry mechanism alone does not establish that requests cannot fail.

## Uncertainty and consequential caveats

Match certainty to the evidence. Distinguish behavior not observed from behavior that is impossible. Keep conditions that could change the reader's decision, and move remote exceptions to a reference. A recommendation should explain the relevant tradeoff instead of avoiding a choice.

```text
Before: Both approaches have strengths and weaknesses, so the choice depends on many factors.
After: Use the queue when work can finish after the response. Keep processing synchronous when the caller needs the result.

Before: No action is needed.
After: Retries succeeded and the queue is empty, so no manual replay is needed.
```

Keep uncertainty the reader needs: if the failure cannot yet be reproduced, do not claim a confirmed cause. Reassurance needs the condition or evidence that justifies it.

## Repetition of meaning and structure

Check whether differently worded passages make the same point. Combine duplicates when neither adds evidence, a necessary distinction, or an action. Keep summaries that help readers navigate a long document or use a section independently.

```text
Before: Setup takes less time. New hires become productive sooner. The onboarding process is faster.
After: New hires can complete setup in 25 minutes.
```

Check the whole document for an introduction, sections, and conclusion that repeat one thesis with different words. Choose the structure based on the material. A conclusion can add a decision or synthesize evidence; a separately distributed summary may need to repeat facts.

Keep all factual items in a list, including a complete three-step procedure. Remove ornamental padding only when it adds no distinct information. A document statistic about repetition is a prompt to inspect the passage, not permission to discard useful content.

## Terminology

Use one term for each concept. Check whether changes between terms such as `workspace`, `project`, and `repository` reflect real distinctions. Define those distinctions where the reader needs them. Preserve exact product names, identifiers, and established technical terms.

```text
Before: The workspace stores the settings. Open the project to change them. The repository remembers your selection.
After: The workspace stores the settings. Open its Settings page to change them.
```

Keep different names for genuinely different objects. Introduce a new term only when a recurring concept needs a name, then define it. Unexplained labels make the reader guess whether a term is established or invented.

```text
Before: This creates the supervision paradox.
After: Reviewing each generated change takes longer than writing the change manually.
```

## Assumptions and explanation

Make each conclusion understandable from the information already provided. Introduce a concept before relying on it. Expand compressed explanations when the reader would otherwise have to reconstruct the missing steps.

```text
Before: The read-path ownership boundary prevents drift.
After: The cache module owns all reads. Other modules call its API, so they cannot bypass the expiration check.

Before: The API shape follows naturally from the data model.
After: Each account has several tokens, so the API lists tokens under an account ID.
```

Keep established compounds such as thread-local or copy-on-write when the audience knows them. Explain a derivation when it is needed to understand the decision. Acknowledging a problem is useful when the document assigns its resolution to a person, a decision, or another section.

## Actors, active voice, and figurative agency

Name the person or component that performs the action when responsibility matters. Components can perform literal operations such as rejecting input or logging a request. Revise language that assigns them intentions, judgment, or feelings. Prefer an active sentence when it identifies the actor more clearly.

```text
Before: Queries are validated before execution.
After: The compiler validates queries before execution.

Before: The free-text field explains why the reviewer chose this option.
After: The reviewer explains the choice in the text field.

Before: The 2025 result is where most advice comes from.
After: Most advice is based on the 2025 result.
```

Keep passive voice when the actor is unknown or irrelevant, as in a statement that a token was revoked at a recorded time. A copula followed by a where/what/how clause is a separate construction. Revise it when a direct statement is clearer. Neither construction proves that a model wrote the sentence.

## Analogies, metaphors, and ranges

Test whether an analogy explains an unfamiliar mechanism for this audience. Remove comparisons that merely borrow prestige from another company or require more explanation than the mechanism itself. State any limit that matters to the comparison.

```text
Before: The validator is a bouncer at the nightclub of your API.
After: The validator rejects requests with missing or incorrectly typed fields.

Before: From innovation to cultural transformation, the platform supports it all.
After: Teams use the platform to propose experiments and record changes to working practices.
```

Keep a comparison when it reduces the explanation needed, and keep a range when its endpoints share a meaningful scale, such as 0 to 100 ms. Do not replace an unwanted metaphor with another metaphor by default.

## Sentence flow and emphasis

Read connected sentences together. Join fragments when their relationship is the useful information. Split a sentence when its nested conditions require backtracking. Vary sentence length according to the explanation, because forced short sentences can be as distracting as dense ones.

```text
Before: The job fails. The worker retries. The lock remains. Nobody releases it.
After: When the job fails, the worker retries without releasing the lock.

Before: The function, when the input, which may be missing during startup, is absent, returns zero.
After: The function returns zero when the input is absent. This can happen during startup.
```

Replace an adverb with the relevant condition, comparison, or measured result when available. Keep literal manner and useful uncertainty. A short warning or command may be appropriate, but avoid forcing every paragraph into the same cadence.

## Formatting and report size

Use lists for distinct items and numbered steps when order matters. Use headings for sections with enough content to need navigation. Bold text should identify a useful distinction instead of repeating the first words of the sentence below it.

```text
Before: A report on a one-line fix has separate Summary, Changes, Tests, Notes, and Next Steps sections.
After: Fixed the loop bound in parser.py. The regression test passes.
```

Keep definition lists, changelogs, reference tables, and longer reports when their structure helps readers find information. Remove empty sections and repeated labels. Judge the structure by its use, not by a fixed paragraph or heading quota.

## Session residue and useful feedback

Read the artifact as someone who never saw the conversation. Replace references to drafting steps or rejected approaches with the enduring behavior or decision. Link to a named section when a reference would otherwise be ambiguous.

```text
Before: Now also handles empty arrays, as discussed in the review.
After: Empty arrays return zero.

Before: Great work, but the parser needs a bounds check.
After: The parser needs a bounds check before reading the next byte.
```

Keep release-note chronology, actual procedures, and confirmation of consequential actions. Keep positive feedback that identifies what should be preserved, such as a test that reproduces the failure. Remove statements about obeying style instructions from the delivered artifact.

## Final read

Read for coherence across sentences and sections. Check that revisions preserve facts, uncertainty, necessary distinctions, and the intended voice. Infer the tone from the audience and assignment. Add opinions, humor, or personal admissions only when appropriate to that assignment. Return to the skill's verification step after editing.
