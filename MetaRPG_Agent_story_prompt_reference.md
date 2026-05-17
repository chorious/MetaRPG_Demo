# MetaRPG Agent v0.6 Story Prompt Reference

## Purpose

This file is a practical prompt reference for starting the v0.6 agentic story loop.

The goal is not to make the Writer LLM obey code-like behavior.
The goal is to give the Writer a strong local adventure frame so it can write vivid story segments while still producing auditable patch effects.

Core rule:

```text
Write boldly inside the local story packet.
Do not invent world-state consequences outside the candidate patch.
Do not expose hidden facts unless an admitted reveal is allowed.
```

---

## 1. Small Adventure Reference: The Lantern Under Greyfen

Use this as the default tiny adventure seed for early v0.6 evaluation.

### Premise

Greyfen is a wet roadside village built around an old iron mine.
Three nights ago, the miner Iven disappeared.
The mine was sealed by order of the guard post.
Mara, the tavern keeper, knows more than she wants to say.
Rusk, the guard captain, wants outsiders to stop asking questions.

The player begins in Mara's tavern during a slow rain.

### Player-Facing Opening

```text
雨水沿着酒馆的窗棂往下爬，炉火烧得很低。
玛拉站在吧台后，擦着一只已经很干净的木杯。
外面的路通向守卫站和旧矿口，但村里的人很少主动提起矿井。
```

### Hidden Truths

These are for audit and later reveal only.
Writer must not expose them directly.

```text
- There is an old maintenance passage near Mara's cellar.
- Mara once helped Iven use that passage.
- Rusk is pressuring Mara because he suspects she knows the route.
- Iven may still be alive beyond the sealed mine gate.
```

### Early Player-Visible Facts

```text
- The old mine is sealed.
- Iven is missing.
- Mara is cautious around mine-related questions.
- Rusk controls access at the guard post.
```

### Initial Local Cast

```text
Mara:
  location: tavern
  visible role: tavern keeper
  surface: reserved, tired, watchful
  knows: old_mine_is_sealed, iven_missing
  hidden knowledge: old_maintenance_passage, helped_iven_once

Rusk:
  location: guard_post
  visible role: guard captain
  surface: stern, procedural
  knows: old_mine_is_sealed, rusk_pressures_mara

Iven:
  location: unknown
  visible role: missing miner
```

---

## 2. Writer Agent System Prompt

Use this for DeepSeek Flash Writer.

```text
You are the Writer Agent for MetaRPG.

You write vivid, player-facing local adventure prose.
You are not the final authority on world state.
You propose candidate patch effects, assumptions, and segmented narrative.
The Committer decides what becomes canon after audit.

Your job:
1. Interpret the player's action in the given local story packet.
2. Write short, vivid narrative segments.
3. Propose candidate patch effects using only allowed effect kinds.
4. Declare assumptions explicitly.
5. Keep player-facing prose free of raw event ids, debug terms, belief percentages, and schema language.

Hard constraints:
- Do not let absent entities act, watch, speak, or react.
- Do not describe NPC inner thoughts as fact.
- Do not expose hidden facts unless allowed_reveals explicitly permits it.
- Do not invent new named NPCs, locations, objects, or hard facts unless candidate_patch includes an allowed effect for doing so.
- Do not make hard state changes only in prose.
- Every meaningful story segment must either reference candidate patch effects or be marked as pure sensory/transient.
- Keep the final narrative grounded in what the player can observe.

Style:
- Chinese prose.
- 1 to 4 short segments per turn.
- Concrete sensory detail is good.
- Do not over-explain trust, belief, probability, or system reasoning.
- Let mystery remain mystery.
```

---

## 3. Writer Agent User Prompt Template

```text
STORY PACKET
{story_packet_json}

PLAYER INPUT
{player_input}

TASK
Write a local turn draft.

Return strict JSON only.

Required output schema:
{
  "interpretation": "Plain-language interpretation of the player's action.",
  "segments": [
    {
      "id": "s1",
      "type": "player_action | sensory | npc_observable_reaction | npc_speech | journal | transition",
      "text": "Player-facing Chinese prose.",
      "patch_refs": ["effect_kind:target_or_id"],
      "declared_claims": ["claim-like plain strings"],
      "transient_only": false
    }
  ],
  "candidate_patch": [
    {
      "kind": "transient_event | journal_note | observe_reaction | knowledge_transfer | relation_delta | belief_delta | move | add_fact | remove_fact | create_hook | consume_item | acquire_item | risk_flag | reveal",
      "args": {}
    }
  ],
  "assumptions": [
    {
      "claim": "What assumption you used.",
      "basis": "Where in the story packet this came from."
    }
  ],
  "risk_notes": [
    "Any uncertainty or boundary you noticed."
  ]
}

Do not include markdown.
Do not include explanations outside JSON.
```

---

## 4. Example Story Packet: Tavern Start

```json
{
  "scene": {
    "location": "tavern",
    "visible_entities": ["player", "mara"],
    "visible_objects": ["bar_counter", "wooden_cup", "hearth"],
    "atmosphere": "rain outside, low fire, quiet tavern"
  },
  "player_context": {
    "known_facts": [],
    "recent_events": [],
    "inventory_or_handheld": []
  },
  "npc_surface": {
    "mara": {
      "role": "tavern keeper",
      "visible_mood": ["reserved", "tired", "watchful"],
      "can_speak": true
    }
  },
  "allowed_effect_kinds": [
    "transient_event",
    "journal_note",
    "observe_reaction",
    "knowledge_transfer",
    "relation_delta",
    "consume_item",
    "acquire_item",
    "reveal"
  ],
  "allowed_reveals": [
    "old_mine_is_sealed",
    "iven_missing"
  ],
  "forbidden": {
    "entities_not_present": ["rusk", "iven"],
    "hidden_fact_aliases": [
      "old_maintenance_passage",
      "secret_mine_entrance",
      "mara_helped_iven",
      "rusk_pressures_mara"
    ],
    "forbidden_narration": [
      "npc_inner_thought_hidden_fact",
      "remote_action",
      "raw_event_id",
      "belief_probability"
    ]
  }
}
```

---

## 5. Example Writer Output: Order Ale

Player input:

```text
要了一杯啤酒
```

Expected Writer JSON:

```json
{
  "interpretation": "玩家向在场的酒馆老板玛拉要一杯啤酒。",
  "segments": [
    {
      "id": "s1",
      "type": "player_action",
      "text": "你在吧台前停下，向玛拉要了一杯啤酒。",
      "patch_refs": ["transient_event:player_orders_ale"],
      "declared_claims": ["player and mara are in the tavern", "mara can provide tavern service"],
      "transient_only": false
    },
    {
      "id": "s2",
      "type": "npc_observable_reaction",
      "text": "玛拉没有多问，只从柜台后取出一只木杯，给你倒上颜色微浊的麦酒。",
      "patch_refs": ["acquire_item:ale", "observe_reaction:mara:routine_service"],
      "declared_claims": ["mara is physically present", "ale is plausible in tavern"],
      "transient_only": false
    }
  ],
  "candidate_patch": [
    {
      "kind": "acquire_item",
      "args": {"owner": "player", "item": "ale", "source": "mara"}
    },
    {
      "kind": "observe_reaction",
      "args": {"target": "mara", "reaction": "routine_service"}
    },
    {
      "kind": "relation_delta",
      "args": {"from": "mara", "to": "player", "dimension": "trust", "delta": 0.01}
    }
  ],
  "assumptions": [
    {
      "claim": "Mara can serve ale.",
      "basis": "Mara is the tavern keeper and the scene is a tavern."
    }
  ],
  "risk_notes": []
}
```

---

## 6. Example Writer Output: Compliment Ale

Player input:

```text
耸了耸肩 "这杯酒真不错"
```

Expected behavior:

```text
Do not order a second ale.
Treat this as a casual comment and mild social signal.
```

Expected Writer JSON:

```json
{
  "interpretation": "玩家用轻松的姿态称赞刚才拿到的酒，试图保持低压的社交气氛。",
  "segments": [
    {
      "id": "s1",
      "type": "player_action",
      "text": "你耸了耸肩，晃了晃手里的杯子，像是随口评价：这杯酒真不错。",
      "patch_refs": ["transient_event:player_compliments_ale"],
      "declared_claims": ["player recently acquired ale"],
      "transient_only": false
    },
    {
      "id": "s2",
      "type": "npc_observable_reaction",
      "text": "玛拉的目光在杯沿上停了一瞬，随后只是轻轻点头，继续擦她的杯子。",
      "patch_refs": ["observe_reaction:mara:brief_acknowledgement"],
      "declared_claims": ["mara is present", "mara can observe player"],
      "transient_only": false
    }
  ],
  "candidate_patch": [
    {
      "kind": "transient_event",
      "args": {"id": "player_compliments_ale"}
    },
    {
      "kind": "observe_reaction",
      "args": {"target": "mara", "reaction": "brief_acknowledgement"}
    },
    {
      "kind": "relation_delta",
      "args": {"from": "mara", "to": "player", "dimension": "trust", "delta": 0.01}
    }
  ],
  "assumptions": [
    {
      "claim": "Player still has the ale from the previous turn.",
      "basis": "recent_events or inventory_or_handheld includes ale"
    }
  ],
  "risk_notes": [
    "This is not a new drink order."
  ]
}
```

---

## 7. Example Writer Output: Drink Ale

Player input:

```text
一饮而尽
```

Expected behavior:

```text
Interpret as drinking the ale.
Do not turn it into speech to Mara.
Do not create hidden reveals.
```

Expected Writer JSON:

```json
{
  "interpretation": "玩家喝完了上一回合手中的麦酒。",
  "segments": [
    {
      "id": "s1",
      "type": "player_action",
      "text": "你仰头喝干杯中的麦酒，苦味和麦香顺着喉咙落下。",
      "patch_refs": ["consume_item:ale"],
      "declared_claims": ["player has or holds ale"],
      "transient_only": false
    },
    {
      "id": "s2",
      "type": "npc_observable_reaction",
      "text": "玛拉看了你一眼，没有评价，只把目光转回吧台。",
      "patch_refs": ["observe_reaction:mara:brief_notice"],
      "declared_claims": ["mara is present", "mara can observe player"],
      "transient_only": false
    }
  ],
  "candidate_patch": [
    {
      "kind": "consume_item",
      "args": {"owner": "player", "item": "ale"}
    },
    {
      "kind": "observe_reaction",
      "args": {"target": "mara", "reaction": "brief_notice"}
    }
  ],
  "assumptions": [
    {
      "claim": "Player has ale.",
      "basis": "recent event: player acquired ale from Mara"
    }
  ],
  "risk_notes": []
}
```

---

## 8. Example Writer Output: Ask Local News

Player input:

```text
"这附近发生了什么事情么？我是新来的，嘿嘿"
```

Expected behavior:

```text
Mara may reveal old_mine_is_sealed.
She must not reveal hidden maintenance passage.
She must not expose Rusk pressure unless allowed_reveals includes it.
```

Expected Writer JSON:

```json
{
  "interpretation": "玩家以新来者的口吻向玛拉打听附近发生的事情。",
  "segments": [
    {
      "id": "s1",
      "type": "player_speech",
      "text": "你用半开玩笑的语气问起附近最近是不是出了什么事。",
      "patch_refs": ["transient_event:player_asks_local_news"],
      "declared_claims": ["player speaks to present Mara"],
      "transient_only": false
    },
    {
      "id": "s2",
      "type": "npc_speech",
      "text": "玛拉停下擦杯子的动作，低声说：旧矿井封了，外乡人最好别往那边凑。",
      "patch_refs": ["reveal:old_mine_is_sealed", "knowledge_transfer:mara_to_player:old_mine_is_sealed"],
      "declared_claims": ["mara knows old_mine_is_sealed", "old_mine_is_sealed is allowed to reveal"],
      "transient_only": false
    },
    {
      "id": "s3",
      "type": "npc_observable_reaction",
      "text": "她说完便收住话头，像是不愿把这个话题再往深处推。",
      "patch_refs": ["observe_reaction:mara:cautious_about_mine"],
      "declared_claims": ["mara is present", "caution is observable"],
      "transient_only": false
    }
  ],
  "candidate_patch": [
    {
      "kind": "knowledge_transfer",
      "args": {"from": "mara", "to": "player", "fact": "old_mine_is_sealed"}
    },
    {
      "kind": "reveal",
      "args": {"fact": "old_mine_is_sealed", "mode": "npc_speech"}
    },
    {
      "kind": "observe_reaction",
      "args": {"target": "mara", "reaction": "cautious_about_mine"}
    },
    {
      "kind": "create_hook",
      "args": {"id": "hook_recent_mine_warning", "topic": "old_mine", "owner": "player"}
    }
  ],
  "assumptions": [
    {
      "claim": "Mara can speak about the mine being sealed.",
      "basis": "allowed_reveals includes old_mine_is_sealed"
    }
  ],
  "risk_notes": [
    "Do not mention secret passage or Rusk pressure."
  ]
}
```

---

## 9. Example Writer Output: Journal Note

Player input:

```text
静静地记下了这条信息
```

Expected behavior:

```text
This is an internal player memory/journal action.
No NPC speech required.
No relation delta required.
No ambiguous social act.
```

Expected Writer JSON:

```json
{
  "interpretation": "玩家把刚得知的矿井封闭信息记在心里。",
  "segments": [
    {
      "id": "s1",
      "type": "journal",
      "text": "你没有追问，只把“旧矿井已经封闭”这句话默默记下。",
      "patch_refs": ["journal_note:old_mine_is_sealed"],
      "declared_claims": ["player recently learned old_mine_is_sealed"],
      "transient_only": false
    },
    {
      "id": "s2",
      "type": "sensory",
      "text": "雨声仍在窗外细细敲着，吧台后的沉默没有被打破。",
      "patch_refs": [],
      "declared_claims": ["tavern atmosphere remains quiet"],
      "transient_only": true
    }
  ],
  "candidate_patch": [
    {
      "kind": "journal_note",
      "args": {"owner": "player", "fact": "old_mine_is_sealed", "note": "旧矿井已经封闭。"}
    },
    {
      "kind": "transient_event",
      "args": {"id": "player_silently_notes_information"}
    }
  ],
  "assumptions": [
    {
      "claim": "Player recently learned old_mine_is_sealed.",
      "basis": "recent event or player knowledge includes old_mine_is_sealed"
    }
  ],
  "risk_notes": [
    "No NPC reaction is required for this internal action."
  ]
}
```

---

## 10. Bad Output Examples

### Bad: Hidden Fact Leak

```text
玛拉想起地窖后的秘密矿道，手指轻轻一颤。
```

Why bad:

```text
NPC inner thought.
Hidden fact exposed.
No reveal patch.
```

Allowed repair:

```text
玛拉的手指在杯沿停了一瞬，但她没有解释原因。
```

### Bad: Absent Entity Action

```text
拉斯克在酒馆角落冷冷看着你。
```

Why bad:

```text
Rusk is at guard_post, not tavern.
Absent entity acts in player-visible scene.
```

Allowed repair:

```text
守卫站的方向仍在雨幕外沉默着。
```

### Bad: Raw Event Exposure

```text
player_asked_mara_about_something
```

Why bad:

```text
Internal event id exposed to player.
```

Allowed repair:

```text
你向玛拉打听附近的事。
```

### Bad: Patch/Text Mismatch

Narrative:

```text
你喝完了麦酒。
```

Patch:

```json
[]
```

Why bad:

```text
Story says an item was consumed, but patch did not record consume_item or transient_event.
```

---

## 11. Prompt Notes For Auditors

Auditors should not judge whether prose is pretty first.
They should first judge whether prose is grounded.

Important checks:

```text
- What does each segment literally claim?
- Which claim depends on which patch effect?
- Which claim depends on visible story packet facts?
- Does any sentence imply hidden knowledge?
- Does any absent entity act?
- Does any hard state change happen only in prose?
- Does any patch effect lack narrative support?
```

The Writer should be encouraged to be vivid.
The Auditor should be encouraged to be severe.
The Editor should be encouraged to be local.

---

## 12. Minimal Writer Prompt Smoke Test

Use this as a first manual smoke test.

Story packet:

```json
{
  "scene": {
    "location": "tavern",
    "visible_entities": ["player", "mara"],
    "visible_objects": ["ale", "bar_counter", "wooden_cup"],
    "atmosphere": "rain outside, quiet tavern"
  },
  "player_context": {
    "known_facts": ["old_mine_is_sealed"],
    "recent_events": ["player_acquired_ale_from_mara"],
    "inventory_or_handheld": ["ale"]
  },
  "allowed_effect_kinds": ["transient_event", "journal_note", "observe_reaction", "consume_item"],
  "allowed_reveals": [],
  "forbidden": {
    "entities_not_present": ["rusk", "iven"],
    "hidden_fact_aliases": ["secret_mine_entrance", "old_maintenance_passage"],
    "forbidden_narration": ["npc_inner_thought_hidden_fact", "remote_action", "raw_event_id", "belief_probability"]
  }
}
```

Player input:

```text
一饮而尽
```

Expected:

```text
- interpretation mentions drinking/finishing ale.
- candidate_patch includes consume_item:ale.
- no Rusk.
- no secret mine entrance.
- no raw event id in segment text.
- no "含糊的话".
```
