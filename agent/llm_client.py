from __future__ import annotations

from typing import Any

import httpx

from config import llm_settings


class LLMRouterUnavailable(RuntimeError):
    pass


class LLMRouterClient:
    """Small OpenAI-compatible chat client for model routers."""

    def __init__(self) -> None:
        self.settings = llm_settings

    @property
    def enabled(self) -> bool:
        return self.settings.enabled

    async def chat_json(self, messages: list[dict[str, str]], temperature: float = 0.1) -> str:
        if not self.enabled:
            raise LLMRouterUnavailable("LLM router is not configured.")

        base_url = (self.settings.router_base_url or "").rstrip("/")
        url = f"{base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.settings.router_api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": self.settings.router_model,
            "messages": messages,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }
        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMRouterUnavailable("LLM router returned an unexpected response shape.") from exc
