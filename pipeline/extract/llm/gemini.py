"""Gemma and Gemini models through the Gemini API.

    POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent

Gemma 4 ignores `systemInstruction` and plain "reply in JSON" requests, but does follow
`responseJsonSchema` (verified 2026-09-17), so the schema is what makes output parseable.
The key travels in a header, never in the URL.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from pipeline.extract.llm.base import ModelAnswer, ModelError
from pipeline.http import RETRYABLE_STATUSES, TOO_MANY_REQUESTS, post_json

BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

RETRY_STATUSES = RETRYABLE_STATUSES - {TOO_MANY_REQUESTS}
"""A rate limit is not retried here. Retrying inside one request would bypass the pacer,
and with several workers doing it at once the retries themselves caused the next refusal.
The caller slows the whole run down instead (see `quota.Pacer.pause`)."""


@dataclass(frozen=True)
class GeminiBackend:
    """Calls one Gemini-API model. Stateless apart from the shared HTTP client."""

    api_key: str
    model: str
    client: httpx.Client
    max_output_tokens: int = 2048
    temperature: float = 0.0

    @property
    def name(self) -> str:
        return self.model

    def generate(self, prompt: str, schema: dict[str, Any]) -> ModelAnswer:
        body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseJsonSchema": schema,
                "maxOutputTokens": self.max_output_tokens,
                "temperature": self.temperature,
            },
        }
        data = post_json(
            self.client,
            f"{BASE_URL}/{self.model}:generateContent",
            label=f"Gemini {self.model}",
            json_body=body,
            headers={"x-goog-api-key": self.api_key},
            retry_statuses=RETRY_STATUSES,
        )
        return _read_answer(data, self.model)


def _read_answer(data: dict[str, Any], model: str) -> ModelAnswer:
    candidates = data.get("candidates") or []
    if not candidates:
        raise ModelError(f"{model}: no candidates ({data.get('promptFeedback', {})})")
    candidate = candidates[0]
    parts = (candidate.get("content") or {}).get("parts") or []
    text = "".join(part.get("text", "") for part in parts)
    reason = candidate.get("finishReason")
    if not text:
        raise ModelError(f"{model}: empty answer (finishReason={reason})")
    if reason == "MAX_TOKENS":
        raise ModelError(f"{model}: answer cut off at the token limit")
    usage = data.get("usageMetadata") or {}
    return ModelAnswer(
        text=text,
        input_tokens=usage.get("promptTokenCount"),
        output_tokens=usage.get("candidatesTokenCount"),
    )
