# Contributing a correction

Prerequisite: the operator approved preparing a contribution. Use a repository checkout for both rule and skill changes. The installed skill and the `uvx` cache are not development checkouts.

1. Clone `git@github.com:JosXa/slophound.git` into an agreed working directory, or use an existing clean checkout. Inspect its instructions, remotes, and working tree before changing files. Create a branch for the correction.
2. Read `CONTRIBUTING.md`. For a rule correction, also read `docs/adding-rules.md`. Locate the rule using the ID from the report, then add a minimal reproduction to its `acceptable` examples. Run `./slophound test` and confirm that the new example fails before changing the detector. Use a non-confidential equivalent if the original sentence cannot be shared.
3. Correct the detector, keeping its positive examples passing. Run `./slophound test` again, then lint the operator's document with `uvx --python 3.13 --from /absolute/path/to/checkout slophound draft.md`. For skill changes, edit `skills/slophound/` and test the affected workflow in a fresh agent session.
4. Show the patch and test results to the operator. Offer to submit a PR and follow their authorization. If they prefer an issue, include the sentence, rule ID, expected behavior, and reproduction command. The maintainer will review the contribution and may decline it.

Report whether verification used the released source or the corrected checkout. A local correction does not update other users' installations. Use the checkout for the rest of this review until the correction is available from the normal installation source.
