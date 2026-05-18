"""Lightweight LLM client wrapper for agentic agents.

Reads from existing set.env (local_url, base_url, api_key).
"""
from __future__ import annotations

import json
import os
from typing import Any

import httpx


_ENV_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "set.env")


def _load_env() -> dict[str, str]:
    cfg: dict[str, str] = {}
    if not os.path.exists(_ENV_PATH):
        return cfg
    with open(_ENV_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            cfg[k.strip()] = v.strip()
    return cfg


class LlmClient:
    def __init__(self, base_url: str, api_key: str, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        # Structured timeout: slow streams from thinking-mode models can
        # keep a connection alive for minutes.  Read=90s catches that.
        self.client = httpx.Client(
            timeout=httpx.Timeout(connect=10.0, read=90.0, write=10.0, pool=10.0)
        )

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        thinking: bool = False,
        request_timeout: float | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 4096,
        }
        if "qwen" in self.model.lower():
            payload["chat_template_kwargs"] = {"enable_thinking": False}
        # DeepSeek V4: thinking-mode defaults to on and silently ignores
        # temperature/top_p.  Explicitly disable it when caller wants
        # temperature to take effect.
        if "deepseek" in self.model.lower() and not thinking:
            payload["extra_body"] = {"thinking": {"type": "disabled"}}

        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        timeout = (
            httpx.Timeout(connect=10.0, read=request_timeout, write=10.0, pool=10.0)
            if request_timeout is not None
            else self.client.timeout
        )
        resp = self.client.post(
            f"{self.base_url}/v1/chat/completions",
            json=payload,
            headers=headers,
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    def chat_json(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.4,
        thinking: bool = False,
    ) -> dict[str, Any]:
        text = self.chat(messages, temperature=temperature, thinking=thinking)
        # Strip markdown code fences if present
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        return json.loads(text.strip())


def make_client(kind: str = "flash") -> LlmClient | None:
    """kind: 'flash' (DeepSeek Flash), 'local' (Qwen3.6), 'pro' (DeepSeek Pro)."""
    cfg = _load_env()
    if kind == "flash":
        url = cfg.get("base_url", "https://api.deepseek.com")
        key = cfg.get("api_key", "")
        model = cfg.get("flash_model", "deepseek-chat")
    elif kind == "local":
        url = cfg.get("local_url", "http://localhost:8101")
        key = cfg.get("api_key", "")
        model = cfg.get("local_model", "qwen3.6-27b-nvfp4")
    elif kind == "pro":
        url = cfg.get("base_url", "https://api.deepseek.com")
        key = cfg.get("api_key", "")
        model = cfg.get("pro_model", "deepseek-chat")
    else:
        return None

    if not key:
        return None
    return LlmClient(base_url=url, api_key=key, model=model)
