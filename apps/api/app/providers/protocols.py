from __future__ import annotations

from typing import Any, Protocol, TypeVar

from pydantic import BaseModel

OutputT = TypeVar("OutputT", bound=BaseModel)


class ModelTransport(Protocol):
    """Provider-specific model invocation without teaching semantics."""

    name: str
    settings: Any

    def invoke_text(
        self,
        operation: str,
        prompt: str,
        *,
        hard_timeout_seconds: int | None = None,
        max_output_tokens: int | None = None,
        reasoning_effort: str | None = None,
        transport_timeout_seconds: int | None = None,
    ) -> str: ...

    def invoke_structured(
        self,
        schema: type[OutputT],
        prompt: str,
        *,
        hard_timeout_seconds: int | None = None,
        max_output_tokens: int | None = None,
        reasoning_effort: str | None = None,
        transport_timeout_seconds: int | None = None,
    ) -> OutputT: ...
