"""Language-model client (Google Gemini API, free tier).

Get a free key at aistudio.google.com (Google account, no card) and store it
as the repository secret GEMINI_API_KEY; the workflow passes it in as
LLM_API_KEY. The request uses the OpenAI chat-completions format, so another
compatible provider only needs a different LLM_ENDPOINT and CEEMEA_MODEL.
"""
from __future__ import annotations

import os
import time

import requests

ENDPOINT = os.environ.get("LLM_ENDPOINT", "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions")
MODEL = os.environ.get("CEEMEA_MODEL", "gemini-3.8-flash")
PAUSE_SECONDS = float(os.environ.get("LLM_PAUSE", "7"))   # free tier allows about 10 requests a minute


def available() -> bool:
    return bool(os.environ.get("LLM_API_KEY"))


class ChatClient:
    def __init__(self, token: str | None = None, model: str = MODEL, endpoint: str = ENDPOINT):
        self.token = token or os.environ["LLM_API_KEY"]
        self.model, self.endpoint = model, endpoint
        self._last_call = 0.0

    def complete(self, system: str, user: str, *, max_tokens: int = 4000) -> str:
        wait = PAUSE_SECONDS - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        resp = requests.post(
            self.endpoint,
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
            json={"model": self.model, "max_tokens": max_tokens, "reasoning_effort": "low",
                  "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
            timeout=120,
        )
        self._last_call = time.monotonic()
        if resp.status_code == 429:
            raise RuntimeError("rate limit reached")
        if resp.status_code >= 400:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:150]}")
        try:
            data = resp.json()
        except ValueError:
            raise RuntimeError(f"non-JSON reply (HTTP {resp.status_code}): {resp.text[:150]!r}") from None
        text = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
        if not text.strip():
            raise ValueError("empty reply from model")
        return text

