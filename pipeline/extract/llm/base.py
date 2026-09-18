"""The interface every model backend answers, so swapping models is a config change."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class ModelError(RuntimeError):
    """The model answered, but not with usable text (blocked, empty, or cut short)."""


@dataclass(frozen=True)
class ModelAnswer:
    """One model reply: the raw text, plus token counts when the provider reports them."""

    text: str
    input_tokens: int | None = None
    output_tokens: int | None = None


class LlmBackend(Protocol):
    """Generates a JSON answer that follows `schema`."""

    @property
    def name(self) -> str:
        """Model identifier, stored with every extraction."""

    def generate(self, prompt: str, schema: dict[str, Any]) -> ModelAnswer: ...
