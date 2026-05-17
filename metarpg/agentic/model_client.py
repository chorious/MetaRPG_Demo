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
        self.client = httpx.Client(timeout=60.0)

    def chat(self, messages: list[dict[str, str]], temperature: float = 0.7) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 2048,
        }
        if "qwen" in self.model.lower():
            payload["chat_template_kwargs"] = {"enable_thinking": False}

        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        resp = self.client.post(f"{self.base_url}/v1/chat/completions", json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    def chat_json(self, messages: list[dict[str, str]], temperature: float = 0.4) -> dict[str, Any]:
        text = self.chat(messages, temperature=temperature)
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
