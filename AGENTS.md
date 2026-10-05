# slophound

A deterministic linter for prose written by language models. It reads a Markdown or plain-text file and reports the constructions that make generated text tiresome to read, in a form the agent that wrote the text can act on without further thinking.

Python scripts run through `uv`; rules in TOML.

## Working rules

- The pre-commit hook in `.githooks/` runs slophound on every staged Markdown file, this one included. Enable it once per clone with `git config core.hooksPath .githooks`.
- Any AI-ism you catch in your own writing here is a candidate rule. Check the catalog, and if it is missing, add it with the sentence you just wrote as the `example`.
- When adding, widening, or repairing a rule, first read [Adding rules](docs/adding-rules.md): what qualifies as a rule, how to pick tier and layer, how examples prove a rule, how to measure noise on human text, and the TOML escaping traps.

## Vision

### Why

Agents cannot see the slop they wrote. The same model that produced `this buys us a week of headroom` will, on review, read it as perfectly fine prose. Asking it to self-correct from a prose checklist spends reasoning budget on a task that is mostly pattern matching, and the result depends on how attentive the model happens to be that turn.

A deterministic linter removes the judgement call. It produces the same findings for the same text on every run. Red findings need a fix. A green report means the checks passed. The author agent runs slophound, gets a list of findings with locations and instructions, applies the fixes, reruns. We don't preclude eventually adding an LLM to the mix, but for now it remains a deterministic set of NLP tools that report typical AI-isms.

The goal is text that people do not mind reading. Whether a machine wrote it is nobody's business.

### Scope

Software and SaaS writing: ADRs, PRDs, plans, specs, README files, design documents, pull request descriptions, internal wiki pages. Generic AI-writing patterns apply everywhere, so most rules are register-agnostic, but the catalog leans toward the engineering vocabulary that current models overuse (`load-bearing`, `footgun`, `the shape of the problem`, `that holds`, `earns its keep`, `surgical change`).

Inputs are single documents of at most a few tens of thousands of tokens.

Out of scope: medical, legal, or journalistic register handling. Code slop. Rewriting, because slophound reports and the author rewrites.

### Detection

Deterministic only. Same input, same output, every run, on every machine.

Detection runs in three layers, ordered from cheapest to most expensive:

1. Regex for fixed phrases and sentence templates ("It's not X. It's Y.").
2. Part-of-speech and dependency parsing for constructions that regex cannot separate from legitimate use. "The worker holds a mutex" passes while "that holds even under load" fires. The difference is grammatical, so the rule is expressed grammatically.
3. Document-level statistics for rhythm and repetition: sentence-length uniformity, repeated paragraph openers, triad density, em-dash density.

Layer two uses established NLP libraries. They must load quickly on demand and release cleanly when the run ends, because an agent invokes the linter ad hoc and nothing stays resident between runs.

The core must produce deterministic, explainable findings. It excludes language-model scoring, perplexity detectors, and external services.

[Jev](https://typesafe.ai/blog/introducing-system-one-models-and-jev) is the sole exception and runs outside the core: it answers typed yes/no, choice, and score questions about a sentence and generates no text. Use it for checks that cannot be expressed deterministically (is this comparison a borrowed metaphor, is this coined label defined anywhere), or as the decider for edge cases that spaCy and the other NLP tools cannot settle (is "database connection pool" one established term or three stacked nouns). Everything that a regex, a parse, or a count can decide stays in the deterministic layers. Jev runs whenever a key is configured and is silent when none is. It never creates a finding. It decides whether a deterministic finding stands, at any severity. A rule declares the question it wants asked in its TOML. When the parse alone would only measure register, as with passive voice, the rule marks its question as required: it then reports only findings that Jev has answered, and stays silent without a key.

### Rules

Rules live in TOML, split across files by the detection layer that executes them. Each file contains enough comments at the top that an agent can add or repair a rule without reading any other documentation.

Every rule has:

- a severity: `bite` (exact match, must be fixed), `bark` (grammar-inferred), or `sniff` (document rhythm), in the Grammarly sense of error, warning, and suggestion. Em dashes are always a bite. The `--formal` flag prints the Grammarly words for CI systems and reporters. The rule files accept either vocabulary.
- a message that fully explains the problem and how to fix it. The report never requires a second lookup.
- at least one `example` sentence the rule must fire on and at least one `acceptable` sentence it must not fire on. `./slophound test` checks both. A rule without an `acceptable` case is rejected, because that is how word blacklists happen.
- source information such as which model families the pattern is most common in. This is informational. There are no per-model profiles or adapters.

### Output

Human-readable, modelled on eslint, rustc, and Bun: file, line, column, severity, rule id, the offending line with the match marked, the full rule message. Lines wider than the terminal (`COLUMNS` when set, 100 columns when no terminal is attached) are cut to a window around the match so the carets stay under the matched words. A summary line closes the report with counts per severity and a density figure (findings per hundred words). Density is informational.

Exit code 0 when there are no bites, 1 when there is at least one bite, 2 when the tool itself failed. Barks and sniffs never change the exit code.

### False positives

There is no ignore file and there is no inline suppression comment. Documents are one-off deliverables, and scattering linter directives through them is its own kind of slop.

A false positive is a bug in a rule. Preserve the legitimate wording and recommend a correction to the operator. Ask before preparing repository changes or submitting a contribution. Make approved corrections in a checkout, with regression examples and passing tests. Leave installed skills and package caches unchanged. Report unresolved findings honestly.

Temporary opt-outs are handled through command-line arguments for the current run only.

### Packaging

The standalone tool installs through `uvx` from Git or a local checkout. Package distributions include the rules and test corpus. The repository script retains its inline dependencies (PEP 723) for development through `uv`. Both entrypoints execute the same implementation.

slophound is greenfield. It takes ideas from earlier MIT-licensed projects in the space and vendors none of their code or catalogs.

### Relationship to the humanize skill

The skill in `skills/slophound/` builds on humanize. It invokes the standalone tool through `uvx` and requires the lint stage before loading the editorial reference. Deterministic checks belong in the linter, while the reference covers judgment about meaning, terminology, audience, and evidence. After editorial changes, the agent reruns the linter and reports resolved findings and remaining advisories. Agent delegation belongs to the harness.
