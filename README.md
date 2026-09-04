# slophound

A linter for prose written by language models. Point it at a Markdown file, get back the sentences that make it read like a machine wrote it, with line numbers and instructions. Make it red, make it green.

Agents cannot see the slop they wrote. slophound can.

```
docs/adr-014.md:12:1  warning     verb.buys-us
  That buys us a week of headroom before the migration.
  ^^^^^^^^^^^^
  "buys (us) X" is a Claude reflex for trading one thing for another. Name the trade: what was spent, what was gained, and for how long.

docs/adr-014.md:31:1  error       template.not-x-but-y
  This isn't a cache problem. It's a consistency problem.
  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  Negation-then-reveal ("It's not X, it's Y"). Delete the negated half and state the positive claim.

1 error, 1 warning, 0 suggestions · 1.4 findings per 100 words
```

Deterministic. Same input, same output, no model in the loop. Rules are plain TOML that any agent can read, test, and repair when a finding is wrong.

## Usage

Requires only [`uv`](https://docs.astral.sh/uv/). The first run downloads spaCy and its English model (about 15 seconds); later runs start in under a second.

```sh
./slophound README.md docs/*.md     # lint files
cat draft.txt | ./slophound -       # lint stdin
./slophound test                    # run the rule and corpus tests
```

Exit code 0 when there are no errors, 1 when at least one error was found, 2 when the tool itself failed. Warnings and suggestions never change the exit code unless `--strict` is set.

| Flag | Effect |
|---|---|
| `--strict` | Warnings count as errors for the exit code. |
| `--disable ID[,ID]` | Skip specific rules for this run. |
| `--disable-category CAT[,CAT]` | Skip a whole rule file (`phrase`, `template`, `punct`, `verb`, `adj`, `doc`). |
| `--only ID[,ID]` | Run just these rules. |
| `--lang XX` | spaCy language code for the grammar layer. Non-English models download on demand. |
| `--skip-quotes` | Leave blockquotes unlinted. |
| `--no-footer` | Omit the false-positive instructions. |

Code blocks, inline code, URLs, link targets, tables, front matter, and HTML comments are never linted.

## How it works

Three detection layers, cheapest first:

1. **Regex** for fixed phrases, sentence templates, and punctuation (`rules/phrase.toml`, `rules/template.toml`, `rules/punct.toml`). These produce errors.
2. **Dependency parsing** with spaCy for constructions that regex cannot tell apart from legitimate use: "the map holds three keys" passes, "that holds even under load" fires (`rules/verb.toml`, `rules/adj.toml`). These produce warnings.
3. **Document statistics** for rhythm and repetition: uniform sentence length, repeated paragraph openers, triad density, bold-label bullet lists (`rules/doc.toml`). These produce suggestions.

Every rule carries its own message, at least one `example` sentence it must fire on, and at least one `acceptable` sentence it must leave alone. `./slophound test` checks all of them, plus a small corpus of human and generated text under `tests/corpus/`, plus this repository's own Markdown.

## False positives

There is no ignore file and no inline suppression comment. When a finding is wrong, the rule is wrong: open the rule file the report points at, tighten the pattern or add the sentence to `acceptable`, run `./slophound test`, and send the change upstream. The footer of every report spells this out for the agent reading it.

## Contributing

Enable the pre-commit hook once per clone so your own Markdown gets linted:

```sh
git config core.hooksPath .githooks
```

See the Vision section in [AGENTS.md](./AGENTS.md) for what this project is and is not.

## License

MIT
