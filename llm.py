"""Language-model client: GitHub Models (free for personal accounts).

Inside GitHub Actions the built-in GITHUB_TOKEN is used, so no API key or
payment is needed; the workflow just declares `permissions: models: read`.
To run locally, set GITHUB_TOKEN to a personal access token with the
'models: read' permission.

The endpoint follows the OpenAI chat-completions format, so switching to
another OpenAI-compatible provider only means changing ENDPOINT and MODEL.
"""
from __future__ import annotations

import os
import time

import requests

ENDPOINT = os.environ.get("LLM_ENDPOINT", "https://models.github.ai/inference/chat/completions")
MODEL = os.environ.get("CEEMEA_MODEL", "openai/gpt-4.1-mini")
PAUSE_SECONDS = float(os.environ.get("LLM_PAUSE", "5"))   # stay well inside free-tier per-minute limits


def available() -> bool:
    return bool(os.environ.get("GITHUB_TOKEN"))


class GitHubModels:
    def __init__(self, token: str | None = None, model: str = MODEL, endpoint: str = ENDPOINT):
        self.token = token or os.environ["GITHUB_TOKEN"]
        self.model, self.endpoint = model, endpoint
        self._last_call = 0.0

    def complete(self, system: str, user: str, *, max_tokens: int = 900) -> str:
        wait = PAUSE_SECONDS - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        resp = requests.post(
            self.endpoint,
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
            json={"model": self.model, "temperature": 0, "max_tokens": max_tokens,
                  "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
            timeout=90,
        )
        self._last_call = time.monotonic()
        if resp.status_code == 429:
            raise RuntimeError("GitHub Models rate limit reached")
        resp.raise_for_status()
        text = (resp.json().get("choices") or [{}])[0].get("message", {}).get("content") or ""
        if not text.strip():
            raise ValueError("empty reply from model")
        return text
