# Contributing

Changes and ideas are welcome. Open an issue or submit a pull request. You propose the change, I review it, and I may decline it.

For rule changes, read [Adding rules](docs/adding-rules.md) and run `./slophound test`.

For changes to the report format or the packaging, also run `uv run python -m unittest discover tests`. The report tests in `tests/test_report.py` compare whole rendered findings, so a format change means updating the expected strings on purpose.
