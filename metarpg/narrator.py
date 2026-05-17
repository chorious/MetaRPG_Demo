"""External-LLM narration with deterministic fallback.

The renderer never invents facts — its job is to dramatize the canon delta and
validation result. Reads `set.env` from the project root (see PLAN_SONNET §0
context): local Qwen at `local_url` is tried first, DeepSeek `flash_model` is
the fallback, and a stitched-template string is used if both fail.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

try:
    import httpx
except ImportError:  # narrator is optional; engine still works in template mode
    httpx = None  # type: ignore[assignment]

from .models import Fact, ValidationResult


SYSTEM_PROMPT = (
    "你是一个复古型合理性引擎的叙事渲染器。"
    "你可以对事件进行戏剧化描写，但绝对不可以编造新的事实。"
    "只能使用来自提供的 CANON DELTA、VALIDATION 和 LOCAL SLICE 中的实体与事件。"
    "输出一段简短的中文叙述，1 到 3 句话。"
    "如果动作被规则拒绝，请用剧情中的方式描写失败。"
)


@dataclass
class NarratorConfig:
    local_url: str = ""
    local_model: str = ""
    base_url: str = ""
    api_key: str = ""
    flash_model: str = ""
    pro_model: str = ""
    timeout: float = 6.0


def load_config(env_path: str) -> NarratorConfig:
    """Parse the project `set.env` file (key = value lines)."""
    cfg = NarratorConfig()
    if not os.path.exists(env_path):
        return cfg
    raw: dict[str, str] = {}
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            raw[k.strip()] = v.strip()
    cfg.local_url = raw.get("local_url", "")
    cfg.local_model = raw.get("local_model", "")
    cfg.base_url = raw.get("base_url", "")
    cfg.api_key = raw.get("api_key", "")
    cfg.flash_model = raw.get("flash_model", "")
    cfg.pro_model = raw.get("pro_model", "")
    return cfg


class Narrator:
    def __init__(self, env_path: str | None = None, enabled: bool = True) -> None:
        self.enabled = enabled and httpx is not None
        self.cfg = load_config(env_path) if env_path else NarratorConfig()

    # ---------- public ----------

    def narrate(
        self,
        action_text: str,
        validation: ValidationResult,
        canon_delta: dict[str, Any],
        slice_text: str,
    ) -> str:
        prompt = self._build_user_prompt(action_text, validation, canon_delta, slice_text)
        if not self.enabled:
            return self._fallback(action_text, validation, canon_delta)
        for caller in (self._call_local, self._call_remote):
            try:
                out = caller(prompt)
                if out:
                    return out.strip()
            except Exception:
                continue
        return self._fallback(action_text, validation, canon_delta)

    # ---------- prompt assembly ----------

    def _build_user_prompt(
        self,
        action_text: str,
        validation: ValidationResult,
        canon_delta: dict[str, Any],
        slice_text: str,
    ) -> str:
        parts: list[str] = []
        parts.append(f"PLAYER ACTION: {action_text}")
        if validation.ok:
            parts.append("VALIDATION: accepted")
        else:
            parts.append(f"VALIDATION: rejected — {validation.reason}")
        parts.append("CANON DELTA:")
        parts.append(_format_delta(canon_delta))
        parts.append("LOCAL SLICE:")
        parts.append(slice_text or "(empty)")
        return "\n".join(parts)

    # ---------- HTTP callers ----------

    def _call_local(self, user_prompt: str) -> str:
        if not self.cfg.local_url or not self.cfg.local_model or httpx is None:
            return ""
        url = self.cfg.local_url.rstrip("/") + "/v1/chat/completions"
        # Local model is Qwen3.x — a thinking model. Disable thinking via the
        # chat-template kwarg so the answer arrives directly in `content`.
        return self._post_chat(
            url,
            self.cfg.local_model,
            user_prompt,
            api_key=None,
            extra={"chat_template_kwargs": {"enable_thinking": False}},
        )

    def _call_remote(self, user_prompt: str) -> str:
        if not self.cfg.base_url or not self.cfg.flash_model or httpx is None:
            return ""
        url = self.cfg.base_url.rstrip("/") + "/v1/chat/completions"
        return self._post_chat(
            url,
            self.cfg.flash_model,
            user_prompt,
            api_key=self.cfg.api_key or None,
        )

    def _post_chat(
        self,
        url: str,
        model: str,
        user_prompt: str,
        api_key: str | None,
        extra: dict[str, Any] | None = None,
    ) -> str:
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        body: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.7,
            "max_tokens": 200,
        }
        if extra:
            body.update(extra)
        with httpx.Client(timeout=self.cfg.timeout) as client:
            r = client.post(url, headers=headers, json=body)
            r.raise_for_status()
            data = r.json()
        return data["choices"][0]["message"]["content"]

    # ---------- fallback (no LLM) ----------

    def _fallback(
        self,
        action_text: str,
        validation: ValidationResult,
        canon_delta: dict[str, Any],
    ) -> str:
        if not validation.ok:
            return f"你试图{action_text.strip()}，但失败了——{validation.reason.replace('_', ' ')}。"
        bits: list[str] = []
        # Transient events first (narration only, not canon)
        for ev in canon_delta.get("transient_events", []):
            bits.append(_event_to_prose_cn(ev))
        # Canon events (admitted to canon delta)
        for ev in canon_delta.get("events", []):
            bits.append(_event_to_prose_cn(ev))
        for ob in canon_delta.get("observations", []):
            bits.append(_event_to_prose_cn(ob))
        # v0.3: risk flags narrated as ambient tension
        for rf in canon_delta.get("risk_flags", []):
            bits.append(_event_to_prose_cn(rf))
        if not bits:
            facts_added = canon_delta.get("facts_added", [])
            if facts_added:
                bits.append(_fact_to_prose_cn(facts_added[0]))
            objects_added = canon_delta.get("objects_added", [])
            if objects_added and not facts_added:
                bits.append(f"你获得了 {objects_added[0][0]}。")
        if not bits:
            return "时间安静地流逝。"
        return " ".join(bits)


# ---------- formatting helpers ----------

def _format_delta(delta: dict[str, Any]) -> str:
    lines: list[str] = []
    for key in (
        "events",
        "observations",
        "rel_deltas",
        "belief_deltas",
        "facts_added",
        "facts_removed",
        "knowledge_added",
        "motif_deltas",
    ):
        items = delta.get(key) or []
        if not items:
            continue
        lines.append(f"{key}: {json.dumps([_stringify(x) for x in items], ensure_ascii=False)}")
    return "\n".join(lines) if lines else "(no change)"


def _stringify(x: object) -> str:
    if isinstance(x, Fact):
        return str(x)
    if isinstance(x, tuple):
        return "(" + ", ".join(_stringify(v) for v in x) + ")"
    return str(x)


def _event_to_prose(ev: str) -> str:
    words = ev.replace("_", " ").strip()
    return words[:1].upper() + words[1:] + "." if words else ""


def _event_to_prose_cn(ev: str) -> str:
    """中文 fallback 叙事——尽量从 snake_case 事件名拼出通顺句子。"""
    if not ev:
        return ""
    known: dict[str, str] = {
        "player asked mara about mine": "你向玛拉问起矿场的事。",
        "player asked rusk about mine": "你向拉斯克问起矿场的事。",
        "player asked mara about iven": "你向玛拉问起艾文的事。",
        "player asked mara about local news": "你向玛拉打听附近有什么大事。",
        "player asked someone about something": "你向某人问起某事。",
        "player confronted mara about mine": "你质问玛拉关于矿场的事。",
        "player confronted someone about something": "你质问某人。",
        "player observed mara": "你观察了玛拉。",
        "player observed scene": "你环顾四周。",
        "player helped mara": "你帮助了玛拉。",
        "player listened to rusk and mara": "你偷听到拉斯克与玛拉的对话。",
        "player listened to silence": "你侧耳倾听，只听到寂静。",
        "player arrived at guard post": "你抵达了守卫站。",
        "player arrived at tavern": "你回到了酒馆。",
        "player asked rusk about iven": "你向拉斯克问起艾文的事。",
        "mara evasive about mine": "玛拉对此闪烁其词。",
        "mara evasive about local news": "玛拉对附近的消息避而不谈。",
        "mara evasive about iven": "玛拉对此避而不答。",
        "mara defensive about mine": "玛拉显得防御性十足。",
        "rusk evasive about mine": "拉斯克对此避而不谈。",
        "rusk warning mara about outsiders": "拉斯克警告玛拉不要对局外人透露矿场的事。",
        "player sneaked into old mine": "你潜入了老矿。",
        "player ordered ale from mara": "你向玛拉要了一杯麦芽啤酒。",
        "social signal player mara ordinary customer request": "玛拉把你当作普通顾客，随口应了一声。",
        "player complained to mara about no service": "你向玛拉抱怨酒馆连酒都没有。",
        "social signal player mara irritated customer": "玛拉察觉到你的不满，神色略显紧张。",
        "player spoke unclearly to mara": "你对玛拉说了些含糊的话。",
        "mara acknowledged or ignored player": "玛拉看了你一眼，没有多说什么。",
        "player made unclear gesture": "你做了个不明所以的动作。",
        "mara responded to mine": "玛拉对矿场的话题有所回应。",
        "mara responded to local news": "玛拉随口说了些附近的消息。",
        "mara responded to topic": "玛拉回应了你的话题。",
        "mara responded to something": "玛拉有所回应。",
    }
    key = ev.strip().lower().replace("_", " ")
    if key in known:
        return known[key]
    # generic: try to make it readable in Chinese context
    words = ev.replace("_", " ").strip()
    return words + "。" if words else ""


def _fact_to_prose(f: Fact) -> str:
    return f"It becomes clear: {f}."


def _fact_to_prose_cn(f: Fact) -> str:
    return f"你意识到：{f}。"
