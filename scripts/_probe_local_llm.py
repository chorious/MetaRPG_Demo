"""One-shot probe of the local Qwen narrator path. Not part of the package — delete after use."""
from __future__ import annotations
import time

import httpx

URL = "http://192.168.50.20:8101/v1/chat/completions"
MODEL = "qwen3.6-27b-nvfp4"

SYSTEM = (
    "You are the renderer for a retrodictive reasonability engine. "
    "You may dramatize but you MUST NOT invent facts. "
    "Use only entities and events that appear in the supplied CANON DELTA, "
    "VALIDATION, and LOCAL SLICE. "
    "Output one short paragraph, 1 to 3 sentences. "
    "If validation rejected the action, narrate the failure in-world."
)

USER = """PLAYER ACTION: ask Mara about the mine
VALIDATION: accepted
CANON DELTA:
events: ["player_asked_mara_about_mine"]
observations: ["mara_evasive_about_mine"]
rel_deltas: [("mara, player, trust, 0.04")]
belief_deltas: [("H1, mara_knows_recent_entry, 0.131, 0.58")]
LOCAL SLICE:
@FACT at(player,tavern)
@FACT at(mara,tavern)
@FACT said(mara,the_mine_is_sealed)
@REL mara->player trust=.18 fear=.10 curiosity=.35"""

body = {
    "model": MODEL,
    "messages": [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": USER},
    ],
    "max_tokens": 200,
    "temperature": 0.7,
    "chat_template_kwargs": {"enable_thinking": False},
}

t0 = time.time()
r = httpx.post(URL, json=body, timeout=30.0)
dt = time.time() - t0
print(f"STATUS {r.status_code}  elapsed={dt:.2f}s")
print("---")
print(r.json()["choices"][0]["message"]["content"])
