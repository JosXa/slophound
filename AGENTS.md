# slophound

A deterministic linter for prose written by language models. It reads a Markdown or plain-text file and reports the constructions that make generated text tiresome to read, in a form the agent that wrote the text can act on without further thinking.

Python scripts run through `uv`; rules in TOML.

## Working rules

- The pre-commit hook in `.githooks/` runs slophound on every staged Markdown file, this one included. Enable it once per clone with `git config core.hooksPath .githooks`.
- Any AI-ism you catch in your own writing here is a candidate rule. Check the catalog; if it is missing, add it with the sentence you just wrote as the `example`.

## Vision

### Why

Agents cannot see the slop they wrote. The same model that produced `this buys us a week of headroom` will, on review, read it as perfectly fine prose. Asking it to self-correct from a prose checklist spends reasoning budget on a task that is mostly pattern matching, and the result depends on how attentive the model happens to be that turn.

A deterministic linter removes the judgement call. Red means fix it, green means done, and the same text produces the same findings on every run. The author agent runs slophound, gets a list of findings with locations and instructions, applies the fixes, reruns. We don't preclude eventually adding an LLM to the mix, but for now it remains a deterministic set of NLP tools that report typical AI-isms.

The goal is text that people do not mind reading. Whether a machine wrote it is nobody's business.

### Scope

Software and SaaS writing: ADRs, PRDs, plans, specs, README files, design documents, pull request descriptions, internal wiki pages. Generic AI-writing patterns apply everywhere, so most rules are register-agnostic, but the catalog leans toward the engineering vocabulary that current models overuse (`load-bearing`, `footgun`, `the shape of the problem`, `that holds`, `earns its keep`, `surgical change`).

Inputs are single documents of at most a few tens of thousands of tokens.

Out of scope: medical, legal, or journalistic register handling. Code slop. Rewriting; slophound reports, the author rewrites.

### Detection

Deterministic only. Same input, same output, every run, on every machine.

Detection runs in three layers, ordered from cheapest to most expensive:

1. Regex for fixed phrases and sentence templates ("It's not X. It's Y.").
2. Part-of-speech and dependency parsing for constructions that regex cannot separate from legitimate use. "The map holds three keys" passes while "that holds even under load" fires. The difference is grammatical, so the rule is expressed grammatically.
3. Document-level statistics for rhythm and repetition: sentence-length uniformity, repeated paragraph openers, triad density, em-dash density.

Established NLP libraries carry layer two. They must load quickly on demand and release cleanly when the run ends, because an agent invokes the linter ad hoc and nothing stays resident between runs.

No language-model scoring, perplexity detectors, or external services in the core. Those are neither deterministic nor explainable, and both properties are the point. If an LLM ever joins the mix, it runs as a separate layer and has no say in the exit code.

### Rules

Rules live in TOML, split across files by the detection layer that executes them. Each file carries enough comments at the top that an agent can add or repair a rule without reading any other documentation.

Every rule has:

- a severity: `bite` (exact match, must be fixed), `bark` (grammar-inferred), or `sniff` (document rhythm), in the Grammarly sense of error, warning, and suggestion. Em dashes are always a bite. The `--formal` flag prints the Grammarly words for CI systems and reporters; the rule files accept either vocabulary.
- a message that fully explains the problem and how to fix it. The report never requires a second lookup.
- at least one `example` sentence the rule must fire on and at least one `acceptable` sentence it must not fire on. `./slophound test` checks both. A rule without an `acceptable` case is rejected, because that is how word blacklists happen.
- provenance metadata such as which model families the pattern is most common in. This is informational. There are no per-model profiles or adapters.

### Output

Human-readable, modelled on eslint, rustc, and Bun: file, line, column, severity, rule id, the offending line with the match marked, the full rule message. A summary line closes the report with counts per severity and a density figure (findings per hundred words). Density is informational.

Exit code 0 when there are no bites, 1 when there is at least one bite, 2 when the tool itself failed. Barks and sniffs never change the exit code.

### False positives

There is no ignore file and there is no inline suppression comment. Documents are one-off deliverables; scattering linter directives through them is its own kind of slop.

A false positive is a bug in a rule. The report tells the agent so, points at the rule file, and asks it to tighten the pattern or add the sentence to `acceptable`, rerun the tests, and offer the fix upstream. Each false positive makes the tool better and leaves the document alone.

Temporary opt-outs are handled through command-line arguments for the current run only.

### Packaging

Python scripts with dependencies declared inline (PEP 723) and executed through `uv`. Nothing is required on the host beyond `uv` itself. First run downloads and caches; later runs start in under a second.

slophound is greenfield. It takes ideas from earlier MIT-licensed projects in the space and vendors none of their code or catalogs.

### Relationship to the humanize skill

slophound consolidates the pattern catalog that previously lived in prose form across a skill, a subagent, and a slash command. Whatever is deterministically checkable lives here as rules. The skill keeps only the guidance that needs a model: voice, structure, what to add rather than remove, plus the long-form catalog as a reference for its judgment pass. The skill invokes `slophound` (a symlink on `PATH` to `./slophound` in this repo); it does not duplicate it.
