"""Credential storage, optional Jev calls, and command output contracts."""

from __future__ import annotations

import getpass
import io
import json
import os
import stat
import tempfile
import tomllib
import unittest
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import httpx2
from typesafe_sdk import Choice, Noul, Score, TypeSafeClient

from hound.cli import main
from hound.config import ConfigError, config_path, read_jev_key, save_jev_key
from hound.engine import Engine
from hound.jev import JevClient, JevError
from hound.loader import RuleError, _build_rule, load_rules
from hound.masking import build_document


KEY = "test-only-key"
QUESTIONS = {"cluster": Noul(instructions="Do these words form one noun phrase?")}
RESPONSE = {
    "model": "jev-1.13.0",
    "usage": {"input_tokens": 24, "output_tokens": 0},
    "answers": {"cluster": {"type": "noul", "noul": 0.93}},
}


class IsolatedConfig(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="slophound-jev-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.enterContext(patch.dict(os.environ, {
            "TYPESAFE_API_KEY": "", "XDG_CONFIG_HOME": str(self.root),
            "APPDATA": str(self.root), "TYPESAFE_LOG_LEVEL": "",
        }))
        self.path = self.root / "slophound" / "config.toml"

    def write_config(self, text: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(text, encoding="utf-8")

    def cli(self, *argv: str, stdin: str = "") -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with patch("sys.stdin", io.StringIO(stdin)), redirect_stdout(out), redirect_stderr(err):
            code = main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def transport(self, handler):
        transport = httpx2.MockTransport(handler)
        return self.enterContext(patch("typesafe_sdk.TypeSafeClient", side_effect=lambda **kw: TypeSafeClient(transport=transport, **kw)))


class KeyStorage(IsolatedConfig):
    def test_platform_paths_and_relative_xdg_fallback(self) -> None:
        for platform in ("linux", "darwin", "win32"):
            with self.subTest(platform=platform), patch("hound.config.sys.platform", platform):
                self.assertEqual(self.path, config_path())
        with patch("hound.config.sys.platform", "darwin"), patch.dict(os.environ, {"XDG_CONFIG_HOME": "relative"}):
            with patch("hound.config.Path.home", return_value=self.root):
                self.assertEqual(self.root / ".config/slophound/config.toml", config_path())
        with patch("hound.config.sys.platform", "win32"), patch.dict(os.environ, {"APPDATA": ""}):
            with patch("hound.config.Path.home", return_value=self.root):
                self.assertEqual(self.root / "AppData/Roaming/slophound/config.toml", config_path())

    def test_unset_key_does_not_create_config(self) -> None:
        self.assertIsNone(read_jev_key())
        self.assertFalse(self.path.exists())
        for text in ("", "[jev]\n", '[jev]\napi_key = "  "\n', "[other]\nvalue = 1\n"):
            with self.subTest(text=text):
                self.write_config(text)
                self.assertIsNone(read_jev_key())

    def test_environment_wins_without_reading_config(self) -> None:
        self.write_config("not valid TOML")
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": "  " + KEY + "\n"}):
            self.assertEqual(KEY, read_jev_key())

    def test_save_round_trip_preserves_other_settings_and_comments(self) -> None:
        self.write_config('# Keep this.\n[other]\nvalue = 3\n[jev]\nmodel = "custom"\napi_key = "old"\n')
        self.assertEqual(self.path, save_jev_key(' test-"quoted"-\\key \n'))
        self.assertEqual('test-"quoted"-\\key', read_jev_key())
        text = self.path.read_text()
        self.assertIn("# Keep this.", text)
        parsed = tomllib.loads(text)
        self.assertEqual(3, parsed["other"]["value"])
        self.assertEqual("custom", parsed["jev"]["model"])
        if os.name != "nt":
            self.assertEqual(0o600, stat.S_IMODE(self.path.stat().st_mode))

    def test_new_directory_is_private(self) -> None:
        save_jev_key(KEY)
        if os.name != "nt":
            self.assertEqual(0o700, stat.S_IMODE(self.path.parent.stat().st_mode))

    def test_bad_keys_and_configs_do_not_leak_or_overwrite(self) -> None:
        for value in ("", "two keys", "line\nbreak", "nonascii-é", "control\x00"):
            with self.subTest(value=value), self.assertRaises(ConfigError):
                save_jev_key(value)
        for text in ('[jev]\napi_key = "secret', "jev = 4", "[jev]\napi_key = 42"):
            self.write_config(text)
            with self.subTest(text=text):
                with self.assertRaises(ConfigError) as error:
                    read_jev_key()
                self.assertNotIn("secret", str(error.exception))
        original = '[jev]\napi_key = "secret'
        self.write_config(original)
        with self.assertRaises(ConfigError):
            save_jev_key(KEY)
        self.assertEqual(original, self.path.read_text())

    def test_failed_replace_keeps_old_key_and_removes_temp_file(self) -> None:
        save_jev_key("old-key")
        with patch("hound.config.os.replace", side_effect=OSError("secret error")):
            with self.assertRaises(ConfigError) as error:
                save_jev_key(KEY)
        self.assertNotIn("secret", str(error.exception))
        self.assertEqual("old-key", read_jev_key())
        self.assertEqual([self.path], list(self.path.parent.iterdir()))


class JevCalls(IsolatedConfig):
    def test_unset_client_is_silent_and_never_opens_transport(self) -> None:
        out, err = io.StringIO(), io.StringIO()
        with patch("typesafe_sdk.TypeSafeClient") as factory, redirect_stdout(out), redirect_stderr(err):
            with JevClient() as client:
                self.assertFalse(client.enabled)
                self.assertIsNone(client.evaluate(state="database connection pool", questions=QUESTIONS))
            factory.assert_not_called()
        self.assertEqual("", out.getvalue() + err.getvalue())

    def test_request_response_and_connection_lifecycle(self) -> None:
        save_jev_key(KEY)
        requests = []

        def handle(request):
            requests.append(request)
            return httpx2.Response(200, json=RESPONSE)

        factory = self.transport(handle)
        # An unrelated SDK endpoint override must not receive the stored key.
        with patch.dict(os.environ, {"TYPESAFE_BASE_URL": "http://untrusted.invalid", "TYPESAFE_DEFAULT_MODEL": "other"}):
            with JevClient() as client:
                self.assertTrue(client.enabled)
                for _ in range(2):
                    result = client.evaluate(state="database\nconnection pool", questions=QUESTIONS)
                    self.assertEqual(0.93, result.nouls["cluster"].noul)
                self.assertIsNone(client.evaluate(state="unused", questions={}))
        self.assertEqual(1, factory.call_count)
        self.assertEqual(2, len(requests))
        request = requests[0]
        self.assertEqual("https://api.typesafe.ai/v1/systemone", str(request.url))
        self.assertEqual("Bearer " + KEY, request.headers["Authorization"])
        payload = json.loads(request.content)
        self.assertEqual("database\nconnection pool", payload["state"])
        self.assertEqual("jev-1.13.0", payload["model"])
        self.assertEqual("noul", payload["questions"]["cluster"]["type"])
        self.assertNotIn(KEY, repr(client))

    def test_api_errors_are_sanitized_and_transient_failures_retried(self) -> None:
        save_jev_key(KEY)
        calls = []

        def handle(request):
            calls.append(request)
            return httpx2.Response(529 if len(calls) == 1 else 401, json={"error": KEY})

        self.transport(handle)
        with JevClient() as client, self.assertRaises(JevError) as error:
            client.evaluate(state="private prose", questions=QUESTIONS)
        self.assertEqual(2, len(calls))
        self.assertIn("401", str(error.exception))
        self.assertNotIn(KEY, str(error.exception))
        self.assertIsNone(error.exception.__cause__)

    def test_choice_and_score_batch_returns_typed_answers(self) -> None:
        save_jev_key(KEY)
        requests = []
        response = {
            **RESPONSE,
            "answers": {
                "kind": {"type": "choice", "choice": "technical", "confidence": 0.9,
                         "probabilities": {"technical": 0.9, "general": 0.1}},
                "clarity": {"type": "score", "score": 0.8, "confidence": 0.8,
                            "legend": {"0": "Unclear", "1": "Clear"},
                            "probabilities": {"0": 0.2, "1": 0.8}},
            },
        }

        def handle(request):
            requests.append(json.loads(request.content))
            return httpx2.Response(200, json=response)

        self.transport(handle)
        with JevClient(model="jev-preview") as client:
            result = client.evaluate(
                state={"sentence": "Check the database connection pool."},
                questions={
                    "kind": Choice(instructions="Classify the vocabulary.", criteria={"technical": None, "general": None}),
                    "clarity": Score(instructions="Assess clarity.", criteria=["Unclear", "Clear"]),
                },
            )
        self.assertEqual("technical", result.choices["kind"].choice)
        self.assertEqual(0.8, result.scores["clarity"].score)
        self.assertEqual(1, len(requests))
        self.assertEqual("jev-preview", requests[0]["model"])
        self.assertEqual({"kind", "clarity"}, set(requests[0]["questions"]))

    def test_empty_score_criteria_fail_before_network_without_exposing_input(self) -> None:
        save_jev_key(KEY)
        requests = []

        def handle(request):
            requests.append(request)
            return httpx2.Response(200, json=RESPONSE)

        self.transport(handle)
        with JevClient() as client, self.assertRaises(JevError) as error:
            client.evaluate(state="private prose", questions={"bad": {"type": "score", "instructions": KEY, "criteria": []}})
        self.assertEqual([], requests)
        self.assertNotIn(KEY, str(error.exception))
        self.assertNotIn("private prose", str(error.exception))

    def test_invalid_response_is_a_sanitized_error(self) -> None:
        save_jev_key(KEY)
        self.transport(lambda _: httpx2.Response(200, json={"private": KEY}))
        with JevClient() as client, self.assertRaises(JevError) as error:
            client.evaluate(state="text", questions=QUESTIONS)
        self.assertNotIn(KEY, str(error.exception))


class AutomaticTermChecks(IsolatedConfig):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = Engine(load_rules())

    def responses(self, probability=0.99):
        requests = []

        def handle(request):
            payload = json.loads(request.content)
            requests.append(payload)
            answers = {
                key: {"type": "noul", "noul": probability(key) if callable(probability) else probability}
                for key in payload["questions"]
            }
            return httpx2.Response(200, json={**RESPONSE, "answers": answers})

        self.transport(handle)
        return requests

    def test_configured_key_automatically_vetoes_an_established_term(self) -> None:
        doc = build_document("draft.md", "Check the database connection pool.\n")
        baseline = self.engine.lint(doc)
        self.assertEqual(["noun.cluster-three"], [f.rule.id for f in baseline])
        save_jev_key(KEY)
        requests = self.responses()
        self.assertEqual([], self.engine.lint(doc))
        self.assertEqual(1, len(requests))
        self.assertEqual([{
            "sentence": "Check the database connection pool.",
            "matched_text": "database connection pool",
            "tokens": ["database", "connection", "pool"],
        }], requests[0]["state"]["items"])

    def test_unset_key_keeps_cluster_report_without_opening_transport(self) -> None:
        with patch("typesafe_sdk.TypeSafeClient") as factory:
            code, out, err = self.cli("--only", "noun.cluster-three", "--no-footer", "-",
                                      stdin="Check the database\nconnection pool.\n")
        factory.assert_not_called()
        self.assertEqual((0, ""), (code, err))
        self.assertIn("sniff  noun.cluster-three", out)
        self.assertIn("  connection pool.\n  ^^^^^^^^^^ ^^^^", out)
        self.assertNotIn("Jev", out)

    def test_uncertain_answer_keeps_original_finding_and_marks(self) -> None:
        doc = build_document("draft.md", "Check the database\nconnection pool.\n")
        baseline = self.engine.lint(doc)
        save_jev_key(KEY)
        requests = self.responses(0.5)
        self.assertEqual(baseline, self.engine.lint(doc))
        self.assertEqual(1, len(requests))
        self.assertEqual("database\nconnection pool", requests[0]["state"]["items"][0]["matched_text"])

    def test_api_failure_preserves_cli_output_and_exit_code(self) -> None:
        args = ("--strict", "--no-footer", "-")
        text = "Check the database connection pool. That holds even under load.\n"
        baseline = self.cli(*args, stdin=text)
        self.assertEqual(1, baseline[0])
        save_jev_key(KEY)
        factory = self.transport(lambda _: httpx2.Response(401, json={"error": KEY}))
        self.assertEqual(baseline, self.cli(*args, stdin=text))
        factory.assert_called_once()

    def test_veto_only_removes_findings_whose_rule_asks_for_it(self) -> None:
        text = "Check the database connection pool. That holds even under load.\n"
        save_jev_key(KEY)
        requests = self.responses()
        for strict, expected in ((False, 0), (True, 1)):
            args = ("--strict", "--no-footer", "-") if strict else ("--no-footer", "-")
            code, out, err = self.cli(*args, stdin=text)
            self.assertEqual((expected, ""), (code, err))
            self.assertIn("verb.holds", out)
            self.assertNotIn("noun.cluster-three", out)
        code, out, err = self.cli("--no-footer", "-", stdin=text + "The build cache eviction policy changed.\n")
        self.assertEqual((1, ""), (code, err))
        self.assertIn("noun.cluster-four", out)
        self.assertEqual([1, 1, 1], [len(r["questions"]) for r in requests])

    def test_semicolon_bark_is_kept_without_key_and_cleared_by_jev_under_strict(self) -> None:
        # The semicolon rule is a bark, so Jev's verdict decides the --strict
        # exit code. That is the point: the regex only sees the shape.
        args = ("--strict", "--only", "punct.semicolon-splice", "--no-footer", "-")
        text = "We ship on Monday; the retrospective is on Tuesday.\n"
        with patch("typesafe_sdk.TypeSafeClient") as factory:
            code, out, err = self.cli(*args, stdin=text)
        factory.assert_not_called()
        self.assertEqual((1, ""), (code, err))
        self.assertIn("bark   punct.semicolon-splice", out)
        self.assertIn("wearing a hat", out)
        save_jev_key(KEY)
        requests = self.responses(lambda key: 0.95)
        code, out, err = self.cli(*args, stdin=text)
        self.assertEqual((0, ""), (code, err))
        self.assertNotIn("punct.semicolon-splice", out)
        self.assertEqual(1, len(requests))
        item = requests[0]["state"]["items"][0]
        self.assertEqual(text.strip(), item["sentence"])
        self.assertEqual("Monday; ", item["matched_text"])
        self.responses(0.3)
        code, out, _ = self.cli(*args, stdin=text)
        self.assertEqual(1, code)
        self.assertIn("punct.semicolon-splice", out)

    def test_threshold_is_inclusive_and_each_answer_applies_only_to_its_finding(self) -> None:
        text = "Check the database connection pool. Read the ceremony momentum compass."
        doc = build_document("draft.md", text)
        baseline = self.engine.lint(doc)
        self.assertEqual(2, len(baseline))
        threshold = baseline[0].rule.jev_veto.threshold
        save_jev_key(KEY)
        requests = self.responses(lambda key: threshold if key == "finding_0" else threshold - 0.001)
        self.assertEqual([baseline[1]], self.engine.lint(doc))
        self.assertEqual(1, len(requests))
        self.assertIn("`items[0]`", requests[0]["questions"]["finding_0"]["instructions"])
        self.assertIn("`items[1]`", requests[0]["questions"]["finding_1"]["instructions"])

    def test_batches_are_small_and_do_not_cross_paragraphs(self) -> None:
        text = "Check the database connection pool. " * 8 + "\n\nRead the ceremony momentum compass."
        doc = build_document("draft.md", text)
        baseline = self.engine.lint(doc)
        save_jev_key(KEY)
        requests = self.responses()
        self.assertEqual([f for f in baseline if f.rule.id != "noun.cluster-three"], self.engine.lint(doc))
        self.assertEqual([6, 2, 1], [len(r["state"]["items"]) for r in requests])
        ids = [f"finding_{i}" for i, f in enumerate(baseline) if f.rule.id == "noun.cluster-three"]
        self.assertEqual(ids, [key for r in requests for key in r["questions"]])
        self.assertIn("`items[0]`", requests[1]["questions"][ids[6]]["instructions"])

    def test_only_sentence_context_and_unmasked_prose_are_sent(self) -> None:
        text = "Previous sentence. Check the **database**\nconnection pool with `secret-code`. Next sentence.\n"
        save_jev_key(KEY)
        requests = self.responses()
        self.assertEqual([], self.engine.lint(build_document("private-path.md", text)))
        payload = json.dumps(requests)
        for excluded in ("Previous sentence", "Next sentence", "secret-code", "private-path.md"):
            self.assertNotIn(excluded, payload)
        self.assertEqual(["database", "connection", "pool"], requests[0]["state"]["items"][0]["tokens"])

    def test_discontinuous_match_keeps_intervening_words_in_context(self) -> None:
        text = "Give every client platform its own AGENTS.md\nA root file with purpose and rules."
        doc = build_document("draft.md", text)
        baseline = self.engine.lint(doc)
        save_jev_key(KEY)
        requests = self.responses(0.1)
        self.assertEqual(baseline, self.engine.lint(doc))
        item = requests[0]["state"]["items"][0]
        self.assertEqual(["AGENTS.md", "root", "file"], item["tokens"])
        self.assertEqual("AGENTS.md\nA root file", item["matched_text"])
        self.assertEqual(text, item["sentence"])

    def test_long_sentence_is_retained_without_truncation_or_request(self) -> None:
        text = "Check the database connection pool " + "before release " * 200 + "."
        doc = build_document("draft.md", text)
        baseline = self.engine.lint(doc)
        self.assertTrue(baseline)
        save_jev_key(KEY)
        requests = self.responses()
        self.assertEqual(baseline, self.engine.lint(doc))
        self.assertEqual([], requests)

    def test_missing_wrong_type_and_out_of_range_answers_keep_findings(self) -> None:
        doc = build_document("draft.md", "Check the database connection pool.")
        baseline = self.engine.lint(doc)
        save_jev_key(KEY)
        for answers in (
            {}, {"other": {"type": "noul", "noul": 1}},
            {"finding_0": {"type": "noul", "noul": 1.1}},
            {"finding_0": {"type": "choice", "choice": "yes", "confidence": 1, "probabilities": {"yes": 1}}},
        ):
            with self.subTest(answers=answers):
                self.transport(lambda _: httpx2.Response(200, json={**RESPONSE, "answers": answers}))
                self.assertEqual(baseline, self.engine.lint(doc))

    def test_second_batch_failure_restores_the_whole_deterministic_report(self) -> None:
        text = "Check the database connection pool. " * 7
        doc = build_document("draft.md", text)
        baseline = self.engine.lint(doc)
        save_jev_key(KEY)
        requests = []

        def handle(request):
            payload = json.loads(request.content)
            requests.append(payload)
            if len(requests) == 2:
                return httpx2.Response(401, json={"error": KEY})
            return httpx2.Response(200, json={**RESPONSE, "answers": {
                key: {"type": "noul", "noul": 1} for key in payload["questions"]
            }})

        self.transport(handle)
        self.assertEqual(baseline, self.engine.lint(doc))
        self.assertEqual(2, len(requests))

    def test_timeout_and_bad_config_do_not_fail_lint_or_print_errors(self) -> None:
        text = "Check the database connection pool."
        args = ("--only", "noun.cluster-three", "--no-footer", "-")
        baseline = self.cli(*args, stdin=text)
        self.write_config("invalid TOML")
        self.assertEqual(baseline, self.cli(*args, stdin=text))
        self.path.unlink()
        save_jev_key(KEY)
        with patch.object(JevClient, "evaluate", side_effect=JevError("Request timed out")):
            self.assertEqual(baseline, self.cli(*args, stdin=text))

    def test_disabled_rules_masked_text_and_stronger_findings_make_no_requests(self) -> None:
        save_jev_key(KEY)
        with patch("typesafe_sdk.TypeSafeClient") as factory:
            self.cli("--disable", "noun.cluster-three", "-", stdin="Check the database connection pool.")
            self.engine.lint(build_document("draft.md", "Check `database connection pool`."))
            self.engine.lint(build_document("draft.md", "The build cache eviction policy changed."))
            factory.assert_not_called()

    def test_selftest_uses_deterministic_detection_even_with_a_key(self) -> None:
        from hound.selftest import check_rule, _check_grammar_findings_carry_token_marks

        save_jev_key(KEY)
        rule = next(r for r in self.engine.rules if r.id == "noun.cluster-three")
        with patch("typesafe_sdk.TypeSafeClient") as factory:
            self.assertEqual([], check_rule(self.engine, rule))
            self.assertEqual([], _check_grammar_findings_carry_token_marks(self.engine))
            factory.assert_not_called()


class VetoRuleValidation(unittest.TestCase):
    def test_invalid_veto_specs_fail_at_load_time(self) -> None:
        raw = {
            "id": "phrase.test", "severity": "sniff", "pattern": "test", "message": "Test.",
            "example": ["test"], "acceptable": ["other"],
            "jev_veto": {"instructions": "Is it a term?", "criteria": {"true": "Yes.", "false": "No."}, "threshold": 0.9},
        }
        self.assertEqual(0.9, _build_rule(raw, "phrase", Path("<test>")).jev_veto.threshold)
        for value in (True, "0.9", 0.5, 1.01, float("nan"), float("inf")):
            bad = deepcopy(raw)
            bad["jev_veto"]["threshold"] = value
            with self.subTest(threshold=value), self.assertRaises(RuleError):
                _build_rule(bad, "phrase", Path("<test>"))
        for value in ({}, [], {"instructions": ""}, {**raw["jev_veto"], "criteria": {"true": "yes"}},
                      {**raw["jev_veto"], "instructions": " "}, {**raw["jev_veto"], "typo": True}):
            with self.subTest(veto=value), self.assertRaises(RuleError):
                _build_rule({**raw, "jev_veto": value}, "phrase", Path("<test>"))
        for severity in ("bite", "bark", "error", "warning"):
            with self.subTest(severity=severity):
                self.assertIsNotNone(_build_rule({**raw, "severity": severity}, "phrase", Path("<test>")).jev_veto)


class CredentialCommands(IsolatedConfig):
    def test_set_key_from_stdin_without_echo(self) -> None:
        code, out, err = self.cli("auth", "set-key", stdin=KEY + "\n")
        self.assertEqual((0, ""), (code, err))
        self.assertIn(str(self.path), out)
        self.assertNotIn(KEY, out)
        self.assertEqual(KEY, read_jev_key())

    def test_set_key_uses_hidden_prompt_at_terminal(self) -> None:
        with patch("sys.stdin.isatty", return_value=True), patch("getpass.getpass", return_value=KEY) as prompt:
            with redirect_stdout(io.StringIO()):
                self.assertEqual(0, main(["auth", "set-key"]))
        prompt.assert_called_once()
        self.assertEqual(KEY, read_jev_key())

    def test_prompt_refuses_echo_fallback(self) -> None:
        with patch("sys.stdin.isatty", return_value=True), patch("getpass.getpass", side_effect=getpass.GetPassWarning):
            with redirect_stderr(io.StringIO()):
                self.assertEqual(2, main(["auth", "set-key"]))
        self.assertFalse(self.path.exists())

    def test_empty_stdin_is_rejected_without_writing(self) -> None:
        code, out, err = self.cli("auth", "set-key")
        self.assertEqual(2, code)
        self.assertEqual("", out)
        self.assertIn("key", err)
        self.assertFalse(self.path.exists())

    def test_lint_output_and_strict_exit_do_not_depend_on_key(self) -> None:
        args = ("--strict", "--only", "verb.holds", "--no-footer", "-")
        text = "That holds even under load.\n"
        baseline = self.cli(*args, stdin=text)
        self.assertEqual(1, baseline[0])
        with patch("typesafe_sdk.TypeSafeClient") as factory:
            save_jev_key(KEY)
            self.assertEqual(baseline, self.cli(*args, stdin=text))
            self.write_config("invalid config")
            self.assertEqual(baseline, self.cli(*args, stdin=text))
            factory.assert_not_called()


if __name__ == "__main__":
    unittest.main()
