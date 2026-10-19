"""A stand-in for llm.GitHubModels that replies from the fixture file."""
from __future__ import annotations

import json

import make_fixtures as fx_data


class FakeClient:
    model = "fake/scripted-replies"

    def __init__(self):
        self.prompts: list[str] = []

    def complete(self, system: str, user: str, **kw) -> str:
        self.prompts.append(user)
        iso = next(k for k in fx_data.LLM_REPLY if f"[{k}-" in user or (k == "STH" and "Southmark" in user))
        reply = fx_data.LLM_REPLY[iso]
        return reply if isinstance(reply, str) else "```json\n" + json.dumps(reply) + "\n```"
