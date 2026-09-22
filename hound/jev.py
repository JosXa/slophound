"""Optional typed judgments through Jev, independent of deterministic findings.

Use JevClient as a context manager to reuse its connection across batches.
An unset key returns None without importing the SDK or opening a connection.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

from .config import read_jev_key

if TYPE_CHECKING:
    from typesafe_sdk import JSONContent, Question, SystemOneResponse, TypeSafeClient

DEFAULT_MODEL = "jev-1.13.0"


class JevError(Exception):
    """A request failure with no credentials, source text, or response body."""


class JevClient:
    def __init__(self, *, model: str = DEFAULT_MODEL) -> None:
        self.model = model
        self._key = read_jev_key()
        self._client: TypeSafeClient | None = None

    @property
    def enabled(self) -> bool:
        return self._key is not None

    def evaluate(self, *, state: JSONContent, questions: Mapping[str, Question]) -> SystemOneResponse | None:
        # Missing credentials contribute no results, messages, or failures.
        if not self.enabled or not questions:
            return None

        from typesafe_sdk import RetryPolicy, TypeSafeAPIError, TypeSafeClient, TypeSafeError

        try:
            if self._client is None:
                self._client = TypeSafeClient(
                    api_key=self._key,
                    model=self.model,
                    base_url="https://api.typesafe.ai",
                    timeout=5.0,
                    retry=RetryPolicy(max_retries=2, timeout=10.0),
                )
            return self._client.system_one(state=state, questions=questions)
        except TypeSafeAPIError as exc:
            raise JevError(f"Jev request failed (HTTP {exc.status}).") from None
        except TypeSafeError:
            raise JevError("Jev request failed or returned an invalid response.") from None
        except (ValueError, TypeError):
            raise JevError("Invalid Jev state, questions, or model.") from None

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> JevClient:
        return self

    def __exit__(self, *_exc) -> None:
        self.close()
