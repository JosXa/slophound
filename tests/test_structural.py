"""Offline contracts for the opt-in experimental evaluator."""
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

FEATURES = ("redundant_conclusion", "empty_roadmap", "unsupported_stakes", "formulaic_contrast")


def row(**changes):
    return {"id": "synthetic-1", "text": "A synthetic paragraph.", "expected": {FEATURES[0]: True},
            "split": "test", "provenance": "synthetic", **changes}


def response():
    return {"model": "jev-1.13.0", "answers": {f: {"type": "noul", "noul": p}
            for f, p in zip(FEATURES, [0.9, 0.1, 0.5, 0.99])},
            "usage": {"input_tokens": 10, "output_tokens": 4}}


class StructuralTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec("hound.structural"), "experimental module missing")
        from hound import structural
        self.s = structural

    def test_request_is_pinned_native_noul_with_only_text_state(self):
        request = self.s.build_request(row()["text"])
        self.assertEqual(request["model"], "jev-1.13.0")
        self.assertEqual(request["state"], {"text": row()["text"]})
        self.assertEqual(set(request["questions"]), set(FEATURES))
        for q in request["questions"].values():
            self.assertEqual(q["type"], "noul")
            self.assertIn("text", q["instructions"])
            self.assertEqual(set(q["criteria"]), {"true", "false"})

    def test_response_bands_and_metadata(self):
        parsed = self.s.validate_response(response())
        self.assertEqual([parsed[f]["status"] for f in FEATURES], ["flagged", "clear", "review", "flagged"])
        self.assertEqual(parsed[FEATURES[0]]["p_yes"], 0.9)

    def test_returned_model_mismatch_is_error_with_no_accepted_probabilities(self):
        labelled = row(expected=dict(zip(FEATURES, [True, False, True, False])))
        for model in ["jev-other", "jev-1.13.0 "]:
            with self.subTest(model=model):
                raw = response()
                raw["model"] = model
                with patch.dict("os.environ", {"TYPESAFE_API_KEY": "test-only"}), \
                     patch.object(self.s, "send_request", return_value=raw):
                    report = self.s.evaluate_dataset([labelled], live=True)
                item = report["rows"][0]
                self.assertEqual(item["status"], "error")
                self.assertEqual(item["errors"], ["invalid_response"])
                for feature in FEATURES:
                    self.assertEqual(item["features"][feature], {"p_yes": None, "status": "error"})
                    counts = report["summary"][feature]
                    self.assertEqual(counts["errors"], 1)
                    for bucket in ("tp", "tn", "fp", "fn", "abstentions"):
                        self.assertEqual(counts[bucket], 0)
                with self.assertRaises(ValueError):
                    self.s.validate_response(raw)

    def test_environment_credential_whitespace_is_normalized(self):
        with patch.dict("os.environ", {"TYPESAFE_API_KEY": " \ttest-only\n"}), \
             patch("hound.config._read_config", side_effect=AssertionError("config read")), \
             patch.object(self.s, "send_request", return_value=response()) as send:
            report = self.s.evaluate_dataset([row()], live=True)
        self.assertEqual(report["rows"][0]["status"], "ok")
        self.assertEqual(send.call_args.args[1], "test-only")

    def test_report_timeout_scope_preserves_timeout_seconds(self):
        limits = self.s.evaluate_dataset([row()], timeout=7)["limits"]
        self.assertEqual(limits["timeout_seconds"], 7)
        self.assertEqual(limits.get("timeout_scope"), "socket_operation")

    def test_cli_help_describes_socket_operation_timeout(self):
        script = Path(__file__).resolve().parents[1] / "tools/structural_eval.py"
        result = subprocess.run([sys.executable, str(script), "--help"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        help_text = " ".join(result.stdout.split())
        self.assertIn("socket-operation timeout", help_text)
        self.assertIn("not an overall deadline", help_text)

    def test_invalid_probabilities_never_become_clear(self):
        for value in [True, False, None, "0.9", float("nan"), float("inf"), -0.01, 1.01]:
            with self.subTest(value=value):
                raw = response()
                raw["answers"][FEATURES[0]]["noul"] = value
                with self.assertRaises(ValueError):
                    self.s.validate_response(raw)

    def test_invalid_response_shape(self):
        raws = [None, [], {}, response(), response(), response(), response(), response()]
        del raws[3]["answers"][FEATURES[0]]
        raws[4]["answers"][FEATURES[0]]["type"] = "score"
        raws[5]["model"] = ""
        raws[6]["usage"]["input_tokens"] = True
        del raws[7]["usage"]
        for raw in raws:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                self.s.validate_response(raw)

    def test_dataset_validation_rejects_not_truncates(self):
        valid = self.s.load_dataset(io.StringIO(json.dumps(row()) + "\n"))
        self.assertEqual(valid, [row()])
        invalid = [row(text="x" * (self.s.MAX_TEXT_CHARS + 1)), row(text=""), row(expected={"unknown": True}),
                   row(expected={FEATURES[0]: 1}), row(id=""), row(split=""), {"id": "x"}]
        for item in invalid:
            with self.subTest(item=str(item)[:80]), self.assertRaises(ValueError):
                self.s.load_dataset(io.StringIO(json.dumps(item)))
        for data in ["", "not json", "\n".join(json.dumps(row(id=str(i))) for i in range(41)),
                     json.dumps(row()) + "\n" + json.dumps(row())]:
            with self.assertRaises(ValueError):
                self.s.load_dataset(io.StringIO(data))

    def test_dry_run_never_loads_key_or_calls_transport(self):
        with patch.object(self.s, "read_jev_key", side_effect=AssertionError("key read")), \
             patch.object(self.s, "send_request", side_effect=AssertionError("network")):
            report = self.s.evaluate_dataset([row()])
        self.assertEqual(report["mode"], "dry_run")
        self.assertEqual(report["rows"][0]["status"], "not_run")
        self.assertIsNone(report["rows"][0]["features"][FEATURES[0]]["p_yes"])
        self.assertIn("request", report["rows"][0])
        self.assertEqual(report["summary"][FEATURES[0]]["not_run"], 1)

    def test_missing_credentials_is_error_not_clean(self):
        with patch.dict("os.environ", {}, clear=True), patch.object(self.s, "read_jev_key", return_value=None), \
             patch.object(self.s, "send_request", side_effect=AssertionError("network")):
            report = self.s.evaluate_dataset([row()], live=True)
        self.assertEqual(report["rows"][0]["status"], "error")
        self.assertEqual(report["summary"][FEATURES[0]]["errors"], 1)
        self.assertTrue(report["rows"][0]["errors"])

    def test_live_mock_retains_raw_metadata_and_label_only_confusion(self):
        labelled = row(expected=dict(zip(FEATURES, [True, False, True, False])))
        with patch.dict("os.environ", {"TYPESAFE_API_KEY": "test-only"}), \
             patch.object(self.s, "send_request", return_value=response()) as send:
            report = self.s.evaluate_dataset([labelled], live=True)
        send.assert_called_once()
        item = report["rows"][0]
        self.assertEqual(item["raw_response"], response())
        self.assertEqual(item["model"], response()["model"])
        self.assertEqual(item["usage"], response()["usage"])
        self.assertGreaterEqual(item["latency_ms"], 0)
        for f, count in zip(FEATURES, ["tp", "tn", "abstentions", "fp"]):
            self.assertEqual(report["summary"][f][count], 1)
        with patch.dict("os.environ", {"TYPESAFE_API_KEY": "test-only"}), \
             patch.object(self.s, "send_request", return_value=response()):
            report = self.s.evaluate_dataset([row(expected={FEATURES[1]: True})], live=True)
        self.assertEqual(report["summary"][FEATURES[1]]["fn"], 1)
        self.assertEqual(report["summary"][FEATURES[0]]["labelled"], 0)

    def test_request_error_is_sanitized_and_not_retried(self):
        with patch.dict("os.environ", {"TYPESAFE_API_KEY": "test-only"}), \
             patch.object(self.s, "send_request", side_effect=TimeoutError("secret text")) as send:
            report = self.s.evaluate_dataset([row()], live=True)
        send.assert_called_once()
        self.assertNotIn("secret text", json.dumps(report))
        self.assertEqual(report["rows"][0]["status"], "error")

    def test_malformed_response_is_error_with_no_probabilities(self):
        raw = response()
        raw["answers"][FEATURES[0]]["noul"] = float("nan")
        with patch.dict("os.environ", {"TYPESAFE_API_KEY": "test-only"}), \
             patch.object(self.s, "send_request", return_value=raw):
            report = self.s.evaluate_dataset([row()], live=True)
        self.assertEqual(report["rows"][0]["status"], "error")
        self.assertIsNone(report["rows"][0]["raw_response"])
        json.dumps(report, allow_nan=False)

    def test_timeout_and_case_limits_apply_before_network(self):
        for timeout in [0, -1, True, float("nan"), 61]:
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                self.s.evaluate_dataset([row()], timeout=timeout)
        with self.assertRaises(ValueError):
            self.s.evaluate_dataset([row(id=str(i)) for i in range(41)])

    def test_huge_integer_probability_is_rejected_as_validation_error(self):
        raw = response()
        raw["answers"][FEATURES[0]]["noul"] = 10 ** 400
        with self.assertRaises(ValueError):
            self.s.validate_response(raw)

    def test_transport_uses_fixed_endpoint_timeout_and_blocks_redirects(self):
        from unittest.mock import MagicMock
        transport = MagicMock()
        transport.open.return_value.__enter__.return_value.read.return_value = json.dumps(response()).encode()
        with patch.object(self.s, "build_opener", return_value=transport) as build:
            self.assertEqual(self.s.send_request(self.s.build_request("test"), "test-only", 7), response())
        req = transport.open.call_args.args[0]
        self.assertEqual(req.full_url, "https://api.typesafe.ai/v1/systemone")
        self.assertEqual(req.get_method(), "POST")
        self.assertEqual(transport.open.call_args.kwargs["timeout"], 7)
        self.assertEqual(json.loads(req.data)["model"], "jev-1.13.0")
        self.assertIsNone(build.call_args.args[0].redirect_request(req, None, 302, "redirect", {}, "https://other.invalid"))
        transport.open.assert_called_once()

    def test_transport_rejects_oversize_response(self):
        from unittest.mock import MagicMock
        transport = MagicMock()
        transport.open.return_value.__enter__.return_value.read.return_value = b" " * (self.s.MAX_RESPONSE_BYTES + 1)
        with patch.object(self.s, "build_opener", return_value=transport), self.assertRaises(ValueError):
            self.s.send_request(self.s.build_request("test"), "test-only", 7)

    def test_cli_dry_run_and_rejected_input(self):
        script = Path(__file__).resolve().parents[1] / "tools/structural_eval.py"
        with tempfile.TemporaryDirectory() as tmp:
            dataset = Path(tmp) / "cases.jsonl"
            output = Path(tmp) / "report.json"
            dataset.write_text(json.dumps(row()) + "\n")
            result = subprocess.run([sys.executable, str(script), str(dataset), "--output", str(output)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(output.read_text())["mode"], "dry_run")
            dataset.write_text("invalid\n")
            result = subprocess.run([sys.executable, str(script), str(dataset)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(json.loads(result.stdout)["status"], "error")


if __name__ == "__main__":
    unittest.main()
