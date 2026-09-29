"""Smoke-test the wheel through the same isolated command path users run.

The project must remain untouched: the build runs from a temporary source copy,
and uvx executes from a different temporary directory. uvx environments are
cached by uv but are never installed as a global tool.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[1]


def _ignore_build_artifacts(_directory: str, names: list[str]) -> set[str]:
    return {
        name
        for name in names
        if name in {".git", ".tmp", ".venv", "mise", "uv.lock", "build", "dist", "__pycache__"}
        or name.startswith(".env")
        or name.endswith((".egg-info", ".pyc"))
    }


class DistributionSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary_directory = tempfile.TemporaryDirectory(prefix="slophound-distribution-")
        cls.addClassCleanup(cls.temporary_directory.cleanup)
        cls.temporary_root = Path(cls.temporary_directory.name)
        cls.source = cls.temporary_root / "source"
        cls.outside_repository = cls.temporary_root / "outside"
        cls.wheel_directory = cls.temporary_root / "wheel"
        cls.config_directory = cls.temporary_root / "config"
        shutil.copytree(REPOSITORY, cls.source, ignore=_ignore_build_artifacts)
        cls.outside_repository.mkdir()

        cls._run_command(
            ["uv", "build", "--sdist", "--out-dir", str(cls.wheel_directory)],
            cwd=cls.source,
            expected_returncode=0,
        )
        archives = list(cls.wheel_directory.glob("slophound-*.tar.gz"))
        if len(archives) != 1:
            raise AssertionError(f"expected one source archive, found {archives}")
        extracted = cls.temporary_root / "extracted"
        with tarfile.open(archives[0]) as archive:
            archive.extractall(extracted, filter="data")
        source_root = next(extracted.iterdir())
        for relative in ("CONTRIBUTING.md", "skills/slophound/SKILL.md", "skills/slophound/references/editorial-review.md"):
            if not (source_root / relative).is_file():
                raise AssertionError(f"source distribution missing {relative}")
        cls._run_command(
            ["uv", "build", "--wheel", "--out-dir", str(cls.wheel_directory)],
            cwd=source_root,
            expected_returncode=0,
        )
        wheels = list(cls.wheel_directory.glob("slophound-*.whl"))
        if len(wheels) != 1:
            raise AssertionError(f"expected one wheel, found {wheels}")
        cls.wheel = wheels[0]

    @classmethod
    def _run_command(
        cls,
        arguments: list[str],
        *,
        cwd: Path,
        expected_returncode: int,
        input_text: str | None = None,
    ) -> str:
        completed = subprocess.run(
            arguments,
            cwd=cwd,
            input=input_text,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env={**os.environ, "TYPESAFE_API_KEY": "", "XDG_CONFIG_HOME": str(cls.config_directory),
                 "APPDATA": str(cls.config_directory)},
            timeout=180,
        )
        output = completed.stdout
        if completed.returncode != expected_returncode:
            raise AssertionError(
                f"command failed: {arguments!r}\n"
                f"expected exit {expected_returncode}, got {completed.returncode}\n{output}"
            )
        return output

    @classmethod
    def _uvx(cls, *arguments: str, expected_returncode: int, input_text: str | None = None) -> str:
        return cls._run_command(
            ["uvx", "--python", "3.13", "--from", str(cls.wheel), "slophound", *arguments],
            cwd=cls.outside_repository,
            expected_returncode=expected_returncode,
            input_text=input_text,
        )

    def test_wheel_command_behaviour_and_resources(self) -> None:
        help_output = self._uvx("--help", expected_returncode=0)
        self.assertIn("usage: slophound", help_output)

        regex_output = self._uvx(
            "--only",
            "phrase.load-bearing",
            "-",
            expected_returncode=1,
            input_text="The retry logic is load-bearing.\n",
        )
        self.assertIn("bite", regex_output)
        self.assertIn("phrase.load-bearing", regex_output)
        rule_locations = [
            Path(line.strip()) for line in regex_output.splitlines()
            if line.strip().replace("\\", "/").endswith("hound/rules/phrase.toml")
        ]
        self.assertEqual(1, len(rule_locations), regex_output)
        self.assertTrue(rule_locations[0].is_file())
        self.assertEqual("rules", rule_locations[0].parent.name)
        self.assertEqual("hound", rule_locations[0].parent.parent.name)
        self.assertFalse(rule_locations[0].resolve().is_relative_to(REPOSITORY.resolve()))

        bark_output = self._uvx(
            "--only",
            "verb.holds",
            "-",
            expected_returncode=0,
            input_text="That holds even under load.\n",
        )
        self.assertIn("bark", bark_output)
        self.assertIn("verb.holds", bark_output)
        self._uvx(
            "--strict",
            "--only",
            "verb.holds",
            "-",
            expected_returncode=1,
            input_text="That holds even under load.\n",
        )

        clean_output = self._uvx(
            "-",
            expected_returncode=0,
            input_text="The team changed the configuration after reviewing the logs.\n",
        )
        self.assertIn("0 bites, 0 barks, 0 sniffs", clean_output)

        unknown_rule_output = self._uvx(
            "--only", "missing.rule", "-", expected_returncode=2, input_text="text\n"
        )
        self.assertIn("unknown rule id", unknown_rule_output)
        missing_input_output = self._uvx(expected_returncode=2)
        self.assertIn("give at least one file", missing_input_output)

        selftest_output = self._uvx("test", expected_returncode=0)
        self.assertRegex(selftest_output, r"\d+ passed, 0 failed")

        # Exercise the installed Python wrapper outside the checkout. An unset
        # key returns no result and does not even import the network SDK.
        module_output = self._run_command(
            ["uv", "run", "--no-project", "--python", "3.13", "--with", str(self.wheel), "python", "-c",
             "import sys; from hound.jev import JevClient; "
             "client = JevClient(); assert not client.enabled; "
             "assert client.evaluate(state='text', questions={'check': {'type': 'noul', 'instructions': 'One phrase?'}}) is None; "
             "assert 'typesafe_sdk' not in sys.modules; client.close(); print('Optional wrapper passed')"],
            cwd=self.outside_repository, expected_returncode=0,
        )
        self.assertIn("Optional wrapper passed", module_output)

        # Auth must store the key outside the project, without echoing it.
        auth_output = self._uvx("auth", "set-key", expected_returncode=0, input_text="distribution-test-key\n")
        self.assertNotIn("distribution-test-key", auth_output)
        config = self.config_directory / "slophound" / "config.toml"
        self.assertIn("distribution-test-key", config.read_text(encoding="utf-8"))

        # Verify the wheel includes the veto layer and TOML criteria, and uses
        # the stored credential during normal linting. Never contact the API.
        probe = self.outside_repository / "jev_probe.py"
        probe.write_text(
            "import json\n"
            "from unittest.mock import patch\n"
            "import httpx2\n"
            "from typesafe_sdk import TypeSafeClient\n"
            "from hound.engine import Engine\n"
            "from hound.loader import load_rules\n"
            "from hound.masking import build_document\n"
            "calls = []\n"
            "def handle(request):\n"
            "    payload = json.loads(request.content)\n"
            "    calls.append(payload)\n"
            "    return httpx2.Response(200, json={\n"
            "        'model': 'jev-1.13.0', 'usage': {'input_tokens': 1, 'output_tokens': 0},\n"
            "        'answers': {key: {'type': 'noul', 'noul': 0.99} for key in payload['questions']}})\n"
            "with patch('typesafe_sdk.TypeSafeClient', side_effect=lambda **kw:\n"
            "        TypeSafeClient(transport=httpx2.MockTransport(handle), **kw)):\n"
            "    engine = Engine(load_rules())\n"
            "    doc = build_document('draft.md', 'Check the database connection pool.')\n"
            "    ids = sorted(f.rule.id for f in engine.lint_deterministic(doc))\n"
            "    assert ids == ['noun.cluster-three', 'template.figure-of-speech'], ids\n"
            "    assert engine.lint(doc) == []\n"
            "assert len(calls) == 1 and len(calls[0]['questions']) == 2, calls\n"
            "print('Jev term review passed')\n",
            encoding="utf-8",
        )
        output = self._run_command(
            ["uv", "run", "--no-project", "--python", "3.13", "--with", str(self.wheel), "python", str(probe)],
            cwd=self.outside_repository, expected_returncode=0,
        )
        self.assertIn("Jev term review passed", output)

    def test_local_rule_edits_invalidate_uvx_cache(self) -> None:
        command = ["uvx", "--python", "3.13", "--from", str(self.source),
                   "slophound", "--only", "phrase.load-bearing", "-"]
        self._run_command(command, cwd=self.outside_repository, expected_returncode=1,
                          input_text="The retry logic is load-bearing.\n")
        rule_file = self.source / "rules" / "phrase.toml"
        original = rule_file.read_text(encoding="utf-8")
        pattern = r"pattern = '\bload[- ]bearing\b'"
        self.assertEqual(1, original.count(pattern))
        rule_file.write_text(original.replace(pattern, r"pattern = '\bdistribution-cache-probe\b'"),
                             encoding="utf-8")
        self._run_command(command, cwd=self.outside_repository, expected_returncode=0,
                          input_text="The retry logic is load-bearing.\n")


if __name__ == "__main__":
    unittest.main()
