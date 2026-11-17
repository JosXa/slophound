from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Mapping
from types import SimpleNamespace

from .config import DecisionsConfig, read_decisions_config
from .jev import JevClient, JevError

_RETRIED_STATUSES = frozenset({408, 409, 429, 500, 502, 503, 504})


def open_decider(*, max_retries: int = 2) -> JevClient | DecisionsClient:
    config = read_decisions_config()
    if config is None:
        return JevClient(max_retries=max_retries)
    return DecisionsClient(config, max_retries=max_retries)


class DecisionsClient:
    def __init__(self, config: DecisionsConfig, *, max_retries: int = 2) -> None:
        self.config = config
        self.model = config.model
        self.max_retries = max_retries

    enabled = True

    def evaluate(self, *, state, questions: Mapping[str, Mapping]) -> SimpleNamespace | None:
        if not questions:
            return None
        body = {
            "model": self.model,
            "input": json.dumps(state, ensure_ascii=False),
            "questions": [_question(name, question) for name, question in questions.items()],
        }
        return _response(self._post(body))

    def _post(self, body: dict) -> dict | None:
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        request = urllib.request.Request(
            self.config.base_url.rstrip("/") + "/decisions",
            data=json.dumps(body).encode("utf-8"), headers=headers, method="POST",
        )
        for attempt in range(self.max_retries + 1):
            try:
                with urllib.request.urlopen(request, timeout=self.config.timeout) as response:
                    return json.load(response)
            except urllib.error.HTTPError as exc:
                if exc.code not in _RETRIED_STATUSES or attempt == self.max_retries:
                    raise JevError(f"Decisions request failed (HTTP {exc.code}).") from None
            except (urllib.error.URLError, TimeoutError, OSError):
                if attempt == self.max_retries:
                    raise JevError("Decisions request failed.") from None
            except ValueError:
                raise JevError("Decisions endpoint returned invalid JSON.") from None
            time.sleep(0.5 * 2 ** attempt)

    def close(self) -> None:
        pass

    def __enter__(self) -> DecisionsClient:
        return self

    def __exit__(self, *_exc) -> None:
        self.close()


def _question(name: str, question: Mapping) -> dict:
    criteria = question.get("criteria") or {}
    instructions = question.get("instructions", "")
    match question.get("type"):
        case "noul":
            rubric = " ".join(f"Answer {answer} when: {text}" for answer, text in criteria.items())
            return {"type": "predicate", "name": name, "instructions": f"{instructions} {rubric}".strip()}
        case "choice":
            return {
                "type": "choice", "name": name, "instructions": instructions,
                "choices": [{"value": value, "description": text} for value, text in criteria.items()],
            }
    raise JevError(f"The decisions client cannot ask a {question.get('type')!r} question.")


def _response(payload: dict) -> SimpleNamespace:
    if not isinstance(payload, dict) or not isinstance(payload.get("answers"), list):
        raise JevError("Decisions endpoint returned an invalid response.")
    nouls, choices = {}, {}
    for answer in payload["answers"]:
        if not isinstance(answer, dict):
            continue
        if answer.get("type") == "predicate":
            nouls[answer.get("name")] = SimpleNamespace(type="noul", noul=answer.get("probability"))
        elif answer.get("type") == "choice":
            probabilities = {str(p.get("value")): p.get("probability")
                             for p in answer.get("probabilities") or [] if isinstance(p, dict)}
            choices[answer.get("name")] = SimpleNamespace(
                type="choice", choice=answer.get("choice"),
                confidence=answer.get("confidence"), probabilities=probabilities,
            )
    return SimpleNamespace(model=payload.get("model"), nouls=nouls, choices=choices)
