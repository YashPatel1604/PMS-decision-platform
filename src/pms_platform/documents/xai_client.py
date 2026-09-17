"""Minimal xAI Grok chat client (OpenAI-compatible)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from pms_platform.config import settings


class XaiConfigError(RuntimeError):
    """Raised when XAI_API_KEY is missing."""


class XaiRequestError(RuntimeError):
    """Raised when the xAI API call fails."""


@dataclass(frozen=True)
class XaiChatResult:
    content: str
    model: str
    token_in: int | None
    token_out: int | None
    raw: dict[str, Any]


def xai_configured() -> bool:
    return bool(settings.xai_api_key and settings.xai_api_key.strip())


def chat_completion(
    messages: list[dict[str, str]],
    *,
    model: str | None = None,
    timeout_s: float = 60.0,
    client: httpx.Client | None = None,
) -> XaiChatResult:
    """Call xAI chat completions. Never send files — messages only."""
    if not xai_configured():
        raise XaiConfigError("XAI_API_KEY is not configured")

    model_name = model or settings.xai_model
    url = settings.xai_api_base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.xai_api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": model_name,
        "messages": messages,
        "temperature": 0.2,
    }

    owns_client = client is None
    http = client or httpx.Client(timeout=timeout_s)
    try:
        response = http.post(url, headers=headers, json=body)
        if response.status_code >= 400:
            raise XaiRequestError(f"xAI HTTP {response.status_code}: {response.text[:500]}")
        payload = response.json()
    except httpx.HTTPError as exc:
        raise XaiRequestError(str(exc)) from exc
    finally:
        if owns_client:
            http.close()

    choices = payload.get("choices") or []
    if not choices:
        raise XaiRequestError("xAI response missing choices")
    message = choices[0].get("message") or {}
    content = message.get("content") or ""
    usage = payload.get("usage") or {}
    return XaiChatResult(
        content=content,
        model=payload.get("model") or model_name,
        token_in=usage.get("prompt_tokens"),
        token_out=usage.get("completion_tokens"),
        raw=payload,
    )
