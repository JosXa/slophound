# slophound

A linter for prose written by language models. Point it at a Markdown file, get back the sentences that make it read like a machine wrote it, with line numbers and instructions. Make it red, make it green.

Agents cannot see the slop they wrote. slophound can.

```
docs/adr-014.md:12:8  error    verb.buys-us
  That buys us a week of headroom before the migration.
       ^^^^^^^
  "X buys us Y" dresses up "X gives us Y". Name what you get.

docs/adr-014.md:31:1  warning  template.not-x-but-y
  This isn't a cache problem. It's a consistency problem.
  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  Negation-then-reveal. State the second half directly.

1 error, 1 warning, 0 suggestions · 1.4 findings per 100 words
```

Deterministic. Same input, same output, no model in the loop. Rules are plain TOML that any agent can read, test, and repair when a finding is wrong.

Requires only [`uv`](https://docs.astral.sh/uv/). Dependencies resolve on first run and are cached after.

See [VISION.md](./VISION.md) for what this project is and is not.

## Status

Pre-alpha. Nothing to run yet.

## License

MIT
