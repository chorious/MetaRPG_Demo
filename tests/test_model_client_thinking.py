"""Tests for model_client thinking-mode switch + structured timeout.

Uses monkey-patching on httpx.Client.post to capture payloads without
making real network requests.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from metarpg.agentic.model_client import LlmClient


def test_deepseek_thinking_disabled_adds_extra_body() -> None:
    """When model name contains 'deepseek' and thinking=False,
    payload must contain extra_body.thinking.type='disabled'."""
    client = LlmClient("https://api.deepseek.com", "fake-key", "deepseek-v4-flash")

    captured = {}
    original_post = client.client.post

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["payload"] = json
        resp = MagicMock()
        resp.raise_for_status = lambda: None
        resp.json = lambda: {
            "choices": [{"message": {"content": "ok"}}]
        }
        return resp

    with patch.object(client.client, "post", side_effect=fake_post):
        client.chat([{"role": "user", "content": "hi"}], temperature=0.7, thinking=False)

    payload = captured["payload"]
    assert "extra_body" in payload
    assert payload["extra_body"]["thinking"]["type"] == "disabled"
    assert payload["temperature"] == 0.7


def test_deepseek_thinking_true_does_not_add_extra_body() -> None:
    """When thinking=True, extra_body must NOT be injected."""
    client = LlmClient("https://api.deepseek.com", "fake-key", "deepseek-v4-flash")

    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["payload"] = json
        resp = MagicMock()
        resp.raise_for_status = lambda: None
        resp.json = lambda: {
            "choices": [{"message": {"content": "ok"}}]
        }
        return resp

    with patch.object(client.client, "post", side_effect=fake_post):
        client.chat([{"role": "user", "content": "hi"}], temperature=0.7, thinking=True)

    payload = captured["payload"]
    assert "extra_body" not in payload


def test_qwen_does_not_add_extra_body() -> None:
    """Qwen models must NOT get extra_body; they get chat_template_kwargs."""
    client = LlmClient("http://localhost:8101", "", "qwen3.6-27b-nvfp4")

    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["payload"] = json
        resp = MagicMock()
        resp.raise_for_status = lambda: None
        resp.json = lambda: {
            "choices": [{"message": {"content": "ok"}}]
        }
        return resp

    with patch.object(client.client, "post", side_effect=fake_post):
        client.chat([{"role": "user", "content": "hi"}], temperature=0.3, thinking=False)

    payload = captured["payload"]
    assert "extra_body" not in payload
    assert payload.get("chat_template_kwargs") == {"enable_thinking": False}


def test_chat_json_passes_thinking() -> None:
    """chat_json must forward the thinking kwarg to chat()."""
    client = LlmClient("https://api.deepseek.com", "fake-key", "deepseek-v4-flash")

    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["payload"] = json
        resp = MagicMock()
        resp.raise_for_status = lambda: None
        resp.json = lambda: {
            "choices": [{"message": {"content": '{"result": 42}'}}]
        }
        return resp

    with patch.object(client.client, "post", side_effect=fake_post):
        result = client.chat_json(
            [{"role": "user", "content": "test"}],
            temperature=0.5,
            thinking=False,
        )

    assert result == {"result": 42}
    assert captured["payload"]["extra_body"]["thinking"]["type"] == "disabled"


def test_request_timeout_overrides_read_timeout() -> None:
    """When request_timeout is passed, the POST call must use the custom timeout."""
    client = LlmClient("https://api.deepseek.com", "fake-key", "deepseek-v4-flash")

    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["timeout"] = timeout
        resp = MagicMock()
        resp.raise_for_status = lambda: None
        resp.json = lambda: {
            "choices": [{"message": {"content": "ok"}}]
        }
        return resp

    with patch.object(client.client, "post", side_effect=fake_post):
        client.chat(
            [{"role": "user", "content": "hi"}],
            temperature=0.7,
            request_timeout=5.0,
        )

    assert captured["timeout"] is not None
    assert captured["timeout"].read == 5.0
    assert captured["timeout"].connect == 10.0


def test_no_request_timeout_uses_default() -> None:
    """When request_timeout is omitted, the POST call uses the client default."""
    client = LlmClient("https://api.deepseek.com", "fake-key", "deepseek-v4-flash")

    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["timeout"] = timeout
        resp = MagicMock()
        resp.raise_for_status = lambda: None
        resp.json = lambda: {
            "choices": [{"message": {"content": "ok"}}]
        }
        return resp

    with patch.object(client.client, "post", side_effect=fake_post):
        client.chat([{"role": "user", "content": "hi"}], temperature=0.7)

    # Default timeout from __init__: connect=10, read=90, write=10, pool=10
    assert captured["timeout"].read == 90.0


if __name__ == "__main__":
    import pytest as _pt
    sys.exit(_pt.main([__file__, "-v"]))
