# MetaRPG planVer0.7.0 - Narrative Transaction Architecture

日期: 2026-05-19

目标: 将 MetaRPG 从 "Writer 散文 -> 事后 Auditor 追认" 改成 "Narrative Grammar -> TurnTransaction -> WorldGraph Commit -> DeepSeek Flash Render"。

---

## 0. 结论

v0.7.0 不再把核心问题定义为 "Hard Auditor 从字符串匹配升级到 Function Calling"。

Function Calling 仍然要做,但它只是 **TurnTransaction 的结构化输出手段**。真正的架构跃迁是:

```text
LLM 不再直接用散文改世界。

Director 生成可验证 TurnTransaction。
Validator 决定 transaction 能否进入 WorldGraph。
Renderer 只负责把已提交内容写成玩家可读叙事。
```

这条线更符合项目愿景:

```text
内部叙事框架提供骨架和张力。
LLM 负责 motif 变奏和局部文学渲染。
WorldGraph 记录什么被承诺为真。
规则层决定什么能被提交。
```

v0.7.0 的可落地目标不是任意开放世界,而是:

> 在一个 DND-like 地城探索场景中,玩家能连续玩 20-30 turn。系统能稳定生成 hook / hint / beat,提交世界交易,保留 LLM 的叙事质感,且不再靠关键词 Hard Auditor 维持世界一致性。

---

## 1. 为什么 v0.6.x 不够

v0.6.x 的核心形状是:

```text
Writer 写散文 + candidate_patch
  -> Translator 从散文抽 claim
  -> Scanner / Hard Auditor 事后判断
  -> Committer 写 world
```

这会产生结构性问题:

1. 散文是表达层,不是执行层。从散文反抽世界状态天然不稳定。
2. Auditor 越严,Writer 越容易被误杀;Auditor 越松,world 越容易被污染。
3. `crystallize` 从 prose 自动固化 fact,会把 texture / utterance / inference 错塞进 canon。
4. 寒暄、hint、reveal、affordance 的边界不是关键词能解决的。
5. 好的 Writer 输出常常被 contract / audit 问题埋掉,玩家看到 fallback。

因此 v0.7.0 必须倒置主流程:

```text
先决定本 turn 可提交的叙事交易。
再把交易渲染成散文。
```

---

## 2. 初始输入

v0.7.0 启动时有两类初始输入。

### 2.1 World Seed

World Seed 定义初始世界图景,包括地点、人物、物品、已知事实、隐藏事实、belief、hook、motif 和风格边界。

建议落地文件:

```text
metarpg/data/seeds/dnd_ashen_vault_seed.yaml
```

最小 seed 示例:

```yaml
world_id: dnd_ashen_vault
title: The Ashen Vault
genre: dnd_like_dungeon_crawl
tone:
  language: zh
  style: restrained, sensory, tense, low-fantasy
  forbidden_style:
    - modern technology
    - sci-fi weapons
    - comedy meta narration
    - explicit system/debug vocabulary

time:
  turn: 0
  dungeon_turn_minutes: 10
  torch_remaining_turns: 12

canon_facts:
  - id: f_player_at_entrance
    predicate: at
    args: [player, entrance_hall]
  - id: f_player_has_torch
    predicate: has
    args: [player, torch]
  - id: f_player_has_short_sword
    predicate: has
    args: [player, short_sword]
  - id: f_alen_at_entrance
    predicate: at
    args: [alen, entrance_hall]
  - id: f_lower_door_sealed
    predicate: sealed
    args: [lower_vault_door]
  - id: f_ash_on_threshold
    predicate: visible_object
    args: [black_ash, entrance_hall]

locations:
  entrance_hall:
    name: 地城入口厅
    tags: [threshold, cold_stone, torchlit]
    exits: [old_guardroom, flooded_stair, sealed_lower_door]
  old_guardroom:
    name: 旧卫兵室
    tags: [abandoned, searchable, rusted]
    exits: [entrance_hall]
  flooded_stair:
    name: 积水阶梯
    tags: [danger, water, echo]
    exits: [entrance_hall, lower_landing]
  sealed_lower_door:
    name: 封闭下层门
    tags: [threshold, locked, old_magic]
    exits: [entrance_hall]

entities:
  player:
    kind: player
    visible_name: 你
  alen:
    kind: npc
    visible_name: 艾伦
    surface:
      posture: 靠在入口厅的石柱旁,左臂用布条吊着
      mood: alert, ashamed
      voice: low, practical
    public_goal: 想活着离开,但又不愿承认自己需要帮助

items:
  torch:
    kind: tool
    owner: player
    tags: [light, consumable]
  short_sword:
    kind: weapon
    owner: player
    tags: [steel, close_range]
  black_ash:
    kind: clue
    location: entrance_hall
    tags: [residue, strange, inspectable]

beliefs:
  - id: b_alen_hides_key
    subject: alen
    proposition: alen has seen the lower door opened recently
    probability: 0.45
    visibility: director_only
  - id: b_flood_is_rising
    subject: dungeon
    proposition: water level below the stair is slowly rising
    probability: 0.55
    visibility: director_only
  - id: b_ash_marks_safe_path
    subject: black_ash
    proposition: the ash marks places where old warding failed
    probability: 0.35
    visibility: director_only

hidden_truths:
  - id: h_relic_moved_below
    statement: The stolen reliquary was carried through the lower vault door before dawn.
    aliases: [reliquary, stolen relic, before dawn, lower vault]
    reveal_policy: only via allowed_reveal after sufficient evidence
  - id: h_bell_sequence_opens_door
    statement: The lower vault door responds to a three-note bell sequence.
    aliases: [bell sequence, three-note chime, vault door song]
    reveal_policy: hint first, never direct exposition in opening turns

relations:
  - from: player
    to: alen
    dims:
      trust: 0.0
      fear: 0.1
      debt: 0.0

motifs:
  - id: m_black_ash
    label: 黑灰
    function: clue, contamination, failed protection
    allowed_variations: [fingerprint, smear, powder, line, bitter smell]
  - id: m_bell
    label: 无声的铃
    function: threshold, memory, mechanism
    allowed_variations: [dull metal, absent chime, three marks, vibration]
  - id: m_wet_stone
    label: 潮湿石阶
    function: time pressure, depth, danger
    allowed_variations: [echo, cold water, moss, rising line]

active_hooks:
  - id: hook_alen_debt
    hook_type: lack
    subject: alen
    object: safety
    tension: 艾伦需要帮助,但他不愿完全信任玩家。
    status: surfaced
    visible_hints: [hint_alen_arm, hint_alen_avoids_lower_door]
    affordances: [ask_alen, offer_help, leave_alen]
  - id: hook_black_ash_enigma
    hook_type: enigma
    subject: black_ash
    object: lower_vault
    tension: 黑灰出现在入口门槛,但来源不明。
    status: surfaced
    visible_hints: [hint_ash_smell, hint_ash_line]
    affordances: [inspect_ash, compare_ash, ask_alen_about_ash]
  - id: hook_lower_door_threshold
    hook_type: threshold
    subject: lower_vault_door
    object: lower_vault
    tension: 下层门封闭,但它明显不是普通锁。
    status: dormant
    visible_hints: [hint_door_three_marks]
    affordances: [inspect_door, force_door, search_guardroom]

starting_affordances:
  - ask_alen
  - inspect_ash
  - search_old_guardroom
  - move_to_flooded_stair
  - inspect_lower_door
```

### 2.2 Narrative Grammar

Narrative Grammar 定义 hook / hint / beat / motif 如何生成、升级、提交和解决。

建议落地文件:

```text
metarpg/data/narrative_grammar/dnd_dungeon_grammar.yaml
```

最小 grammar 示例:

```yaml
version: 0.7.0
name: dungeon_narrative_grammar

commitment_levels:
  texture:
    meaning: 氛围或表层描写,默认不进 canon,不能被后续逻辑强依赖。
  hint:
    meaning: 可感知信号,指向 hook,但不确认 hidden truth。
  affordance:
    meaning: 玩家可交互机会,进入 active affordances。
  event:
    meaning: 已发生事件,写入 event log。
  canon:
    meaning: 确定事实,写入 canon facts。
  utterance:
    meaning: 某角色说过的话,记录为来源化说法,不等于世界真相。
  belief_evidence:
    meaning: 改变 belief 概率的证据,不直接 reveal。

hook_types:
  lack:
    definition: 某人缺少安全、信息、物品、信任或出口。
    common_affordances: [ask, offer_help, trade, ignore]
    allowed_commitments: [hint, affordance, event, belief_evidence]
  enigma:
    definition: 有异常信号,原因未知。
    common_affordances: [inspect, compare, ask, follow]
    allowed_commitments: [texture, hint, affordance, belief_evidence]
  threshold:
    definition: 玩家面对进入新地点、新危险或新知识层的门槛。
    common_affordances: [enter, inspect, unlock, retreat]
    allowed_commitments: [hint, affordance, event, canon]
  debt:
    definition: 人情、帮助、承诺或交换造成的社会张力。
    common_affordances: [call_in_favor, repay, refuse, deepen_trust]
    allowed_commitments: [event, utterance, relation_delta, belief_evidence]
  contradiction:
    definition: 两个来源的说法或证据不一致。
    common_affordances: [confront, verify, compare_sources]
    allowed_commitments: [utterance, hint, affordance, belief_evidence]
  threat_timer:
    definition: 时间拖延会带来更坏状态。
    common_affordances: [hurry, wait, prepare, investigate]
    allowed_commitments: [hint, event, affordance, canon]

hint_types:
  gesture_hint:
    commitment_level: hint
    examples: [停顿, 避开目光, 指节收紧, 呼吸变慢]
  object_hint:
    commitment_level: hint
    examples: [划痕, 黑灰, 水线, 蜡封, 缺口]
  speech_hint:
    commitment_level: utterance
    examples: [改口, 含糊, 过快否认, 转移话题]
  absence_hint:
    commitment_level: hint
    examples: [本该在的东西不在, 常亮的灯熄灭]
  spatial_hint:
    commitment_level: hint
    examples: [冷风, 脚印, 门缝, 回声方向]
  time_hint:
    commitment_level: hint
    examples: [水位升高, 火把变短, 回声更近]

beat_types:
  arrival:
    function: 建立当前空间和可交互对象。
    default_hooks: [threshold, enigma]
  inspection:
    function: 将 hint 推向 affordance 或 belief_evidence。
    default_hooks: [enigma]
  social_pressure:
    function: 通过 NPC 反应制造信任、债务、隐瞒。
    default_hooks: [lack, debt, contradiction]
  threshold_crossing:
    function: 场景转移或进入新危险层。
    default_hooks: [threshold, threat_timer]
  aftermath:
    function: 处理行动余波,适合 inner_monologue 和 motif 变奏。
    default_hooks: [debt, enigma]
  complication:
    function: 已有目标变难,但不直接否定玩家行动。
    default_hooks: [threat_timer, contradiction]

motif_rules:
  max_motifs_per_turn: 2
  repeat_requires_variation: true
  motif_can_hint_hook: true
  motif_cannot_reveal_hidden_truth_directly: true
  renderer_should_use_motif_concretely: true

render_rules:
  prose_language: zh
  renderer_model: deepseek_flash
  max_segments: 3
  no_system_terms: true
  no_uncommitted_world_change: true
  player_inner_monologue_allowed: true
  npc_inner_monologue_forbidden: true
```

---

## 3. 目标项目框架

v0.7.0 结束时,项目主流程应收敛为:

```text
World Seed + Narrative Grammar
        ↓
WorldGraph 初始化
        ↓
PlayerInput
        ↓
Intent / Feasibility
        ↓
StoryPacket Builder
        ↓
Hook / Hint / Beat Manager
        ↓
Director / Transaction Planner
        ↓
Transaction Validator
        ↓
Committer
        ↓
Render Brief Builder
        ↓
Renderer (DeepSeek Flash)
        ↓
Post-render Checker
        ↓
Player Output + Updated WorldGraph
```

### 3.1 模型路由

配置来源:

```text
E:\GameDesign\MetaRPG_Dev\set.env
```

使用约定:

| 层 | 模型 | 配置键 |
|---|---|---|
| Renderer / 最终玩家文本 | DeepSeek Flash | `base_url`, `flash_model`, `api_key` |
| Intent / Feasibility | local vLLM | `local_url`, `local_model` |
| Hook / Beat Manager 的语义判断 | local vLLM | `local_url`, `local_model` |
| Director / Transaction Planner | local vLLM + structured schema/tool calling | `local_url`, `local_model` |
| Validator 的语义降级/NLI 辅助 | local vLLM | `local_url`, `local_model` |
| Post-render Checker | local vLLM + deterministic checks | `local_url`, `local_model` |

原则:

```text
DeepSeek Flash 只做 Render 层。
其他 LLM 调用默认走本地 vLLM。
Renderer 不允许直接提交世界变化。
```

---

## 4. 核心数据结构

### 4.1 WorldGraph

WorldGraph 取代 "facts + 一堆旁路字段" 的松散结构。它至少包含:

```python
WorldGraph:
    canon_facts: set[Fact]
    events: list[WorldEvent]
    utterances: list[Utterance]
    beliefs: dict[str, Belief]
    relations: dict[tuple[str, str], Relation]
    locations: dict[str, Location]
    entities: dict[str, Entity]
    items: dict[str, Item]
    hooks: dict[str, NarrativeHook]
    hints: dict[str, NarrativeHint]
    affordances: dict[str, Affordance]
    motifs: dict[str, Motif]
    hidden_truths: dict[str, HiddenTruth]
    time: WorldTime
```

兼容策略:

```text
v0.7.0 可以先在现有 WorldState 上增加 adapter,不要求一次性删除 metarpg.models.WorldState。
```

### 4.2 TurnTransaction

TurnTransaction 是 v0.7.0 的核心中间产物。

```python
TurnTransaction:
    id: str
    player_input: str
    player_intent: PlayerIntent
    narrative_frame: NarrativeFrame
    operations: list[Operation]
    commitments: list[Commitment]
    render_brief: RenderBrief
    forbidden_claims: list[ForbiddenClaim]
    assumptions: list[Assumption]
```

Operation 示例:

```text
move_player(destination)
transfer_item(item, from_entity, to_entity)
observe_reaction(entity, reaction)
speak(entity, speech_type, text, claim_refs)
create_affordance(kind, target, expires_turn)
update_relation(entity_a, entity_b, dim, delta)
update_belief(belief_id, evidence, delta)
mark_hook_status(hook_id, status)
add_event(event_type, participants, summary)
add_texture(text, points_to_hook)
inner_monologue(text)
```

Commitment 示例:

```text
canon_fact       真实世界事实
event            已发生事件
utterance        某角色说过的话,不等于真相
belief_evidence  影响概率但不 reveal
affordance       玩家可交互机会
texture          氛围/表层细节,默认不进 canon
inner_monologue  玩家主观意识,不进 canon
```

### 4.3 NarrativeFrame

NarrativeFrame 是结构主义叙事学进入工程的位置。

```python
NarrativeFrame:
    beat: str
    active_hooks: list[str]
    candidate_hints: list[str]
    motifs_to_use: list[str]
    dramatic_function: str
    allowed_commitment_levels: list[str]
    forbidden_moves: list[str]
```

例子:

```yaml
beat: aftermath_threshold
active_hooks: [hook_alen_debt, hook_lower_door_threshold]
candidate_hints: [hint_alen_avoids_lower_door, hint_door_three_marks]
motifs_to_use: [m_black_ash, m_wet_stone]
dramatic_function: 玩家离开入口厅前获得一层不完整但可行动的张力。
allowed_commitment_levels: [event, hint, affordance, belief_evidence]
forbidden_moves: [direct_hidden_truth_reveal, npc_inner_monologue]
```

---

## 5. Turn 流程

### Step 1 - Intent / Feasibility

输入:

```text
PlayerInput + 局部 WorldGraph
```

输出:

```python
PlayerIntent:
    action_type: ask | move | inspect | take | give | wait | attack | help | ambiguous
    targets: list[str]
    props: list[str]
    feasibility: possible | blocked | ambiguous
    world_response_kind: accept | friction | absence | reframing
```

LLM: local vLLM。

### Step 2 - StoryPacket Builder

输入:

```text
WorldGraph + PlayerIntent
```

输出:

```text
当前地点、可见实体、可见物品、玩家持有物、最近事件、active hooks、candidate hints、allowed reveals、forbidden hidden truths、motifs。
```

要求:

```text
StoryPacket 必须局部化,不能把所有 hidden_truths 暴露给 Render 层。
```

### Step 3 - Hook / Hint / Beat Manager

输入:

```text
StoryPacket + Narrative Grammar + PlayerIntent
```

输出:

```text
NarrativeFrame
```

规则:

1. Player action 可推进已有 hook,也可 surface dormant hook。
2. Hint 默认不 reveal hidden truth。
3. Motif 每 turn 最多 2 个,必须变奏。
4. Beat 选择服务于当前 action,不强推剧情。

LLM: deterministic first,必要时 local vLLM 辅助语义判断。

### Step 4 - Director / Transaction Planner

输入:

```text
PlayerIntent + StoryPacket + NarrativeFrame
```

输出:

```text
TurnTransaction
```

LLM: local vLLM。

输出方式:

```text
structured JSON schema 或 local tool calling。
```

Director 不写最终玩家 prose,只写 transaction 和 render_brief。

### Step 5 - Transaction Validator

输入:

```text
TurnTransaction + WorldGraph
```

输出:

```text
accepted / downgraded / rejected transaction
```

Hard checks:

```text
物品存在和归属
实体是否在场
地点是否可达或可新建
hidden_truth 是否被非法 reveal
relation_delta / belief_delta 是否越界
hook 状态迁移是否合法
commitment_level 是否允许
同 turn operations 是否互相矛盾
```

降级策略:

```text
canon_fact -> utterance
reveal -> hint
new_item -> texture / affordance
hard move -> attempted_move event
knowledge_transfer -> speech_hint
```

这层替代 v0.6 的大部分 Hard Auditor。

### Step 6 - Committer

输入:

```text
Validated TurnTransaction
```

输出:

```text
Updated WorldGraph + world_diff
```

只有 Committer 能写:

```text
canon_facts
events
utterances
beliefs
relations
inventory
locations
hooks
affordances
motifs
time
```

Renderer 不能写 world。

### Step 7 - Render Brief Builder

输入:

```text
Validated Transaction + world_diff + NarrativeFrame
```

输出:

```python
RenderBrief:
    committed_events: list[str]
    visible_reactions: list[str]
    allowed_hints: list[str]
    motifs_to_render: list[str]
    style_constraints: list[str]
    forbidden_claims: list[str]
```

RenderBrief 是 DeepSeek Flash 的唯一叙事依据。

### Step 8 - Renderer

输入:

```text
RenderBrief + local visible StoryPacket
```

输出:

```text
player-facing Chinese prose
```

LLM: DeepSeek Flash。

要求:

```text
DeepSeek Flash 可以大胆写 motif 变奏、节奏、感官和内心独白。
DeepSeek Flash 不允许新增未提交世界事实。
DeepSeek Flash 不允许写 NPC 内心。
DeepSeek Flash 不允许泄露 hidden_truth。
```

### Step 9 - Post-render Checker

输入:

```text
Rendered prose + Validated Transaction + forbidden_claims
```

输出:

```text
pass / light repair
```

检查目标只保留一个:

```text
Renderer 有没有偷偷增加 transaction 之外的世界承诺?
```

这不是新的主 Auditor,只是渲染防线。

---

## 6. 新文件和改造文件

### 6.1 新建

```text
metarpg/agentic/seed_loader.py
metarpg/agentic/world_graph.py
metarpg/agentic/narrative_grammar.py
metarpg/agentic/hook_manager.py
metarpg/agentic/transaction.py
metarpg/agentic/director_agent.py
metarpg/agentic/transaction_validator.py
metarpg/agentic/render_brief.py
metarpg/agentic/renderer_agent.py
metarpg/agentic/post_render_checker.py
metarpg/data/seeds/dnd_ashen_vault_seed.yaml
metarpg/data/narrative_grammar/dnd_dungeon_grammar.yaml
```

### 6.2 大改

```text
metarpg/agentic/runner.py
  从 writer-first 改为 transaction-first。

metarpg/agentic/model_client.py
  明确支持 flash/local 路由,支持 structured schema/tool calls。

metarpg/agentic/committer.py
  接收 ValidatedTransaction,不再直接相信 Writer patch。

metarpg/agentic/story_packet.py
  输出 hooks/hints/motifs/allowed_reveals/forbidden_claims。

metarpg/agentic/schemas.py
  增加 Transaction、Commitment、NarrativeFrame、RenderBrief。
```

### 6.3 降级/兼容

```text
metarpg/agentic/writer_agent.py
  v0.7.0 后不再是主入口。保留为兼容 wrapper 或拆分为 director_agent + renderer_agent。

metarpg/agentic/hard_auditor.py
  主职责迁移到 transaction_validator.py。旧 Hard Auditor 只保留兼容测试和 post-render 的轻量检查。

metarpg/agentic/crystallize.py
  不再自动把散文写入 canon。改为 commitment_extractor / proposal 工具,只提出候选,默认不 commit。

metarpg/agentic/refusal_fallback.py
  改成 fallback transaction: inner_monologue + texture,而不是系统模板 prose。
```

---

## 7. 实施 Phase

### Phase 1 - Seed + Grammar Loader (1-2 天)

交付:

```text
seed_loader.py
narrative_grammar.py
dnd_ashen_vault_seed.yaml
dnd_dungeon_grammar.yaml
```

验收:

```text
加载 seed 后 WorldGraph 有 player/alen/entrance_hall/black_ash/lower_door。
加载 grammar 后 hook_types 包含 lack/enigma/threshold/debt/contradiction/threat_timer。
```

### Phase 2 - Transaction Schema + Validator Skeleton (2 天)

交付:

```text
transaction.py
transaction_validator.py
tests/test_transaction_validator.py
```

验收:

```text
没有 torch 不能 extinguish torch。
不在场 entity 不能 speak。
hidden_truth 不能被 direct reveal。
reveal 可被降级为 hint。
```

### Phase 3 - Hook / Hint / Beat Manager (2-3 天)

交付:

```text
hook_manager.py
tests/test_hook_manager.py
```

验收:

```text
玩家 inspect black_ash -> hook_black_ash_enigma engaged。
玩家 help alen -> hook_alen_debt 增加 relation/belief affordance。
玩家 approach lower_door -> threshold beat surfaced。
```

### Phase 4 - Director Agent (3-4 天)

交付:

```text
director_agent.py
structured output schema
tests/test_director_agent.py
```

模型:

```text
local vLLM,使用 set.env 的 local_url/local_model。
```

验收:

```text
输入 "我检查门槛上的黑灰"。
Director 输出 inspection beat + inspect event + hint/affordance,不输出最终 prose。
```

### Phase 5 - Committer + WorldGraph Adapter (2-3 天)

交付:

```text
world_graph.py
committer.py 改造
tests/test_world_graph_commit.py
```

验收:

```text
ValidatedTransaction 能写 event/utterance/belief_delta/hook_status。
texture 不进入 canon_facts。
utterance 不等于 canon truth。
```

### Phase 6 - DeepSeek Flash Renderer (2 天)

交付:

```text
render_brief.py
renderer_agent.py
tests/test_renderer_agent.py
```

模型:

```text
DeepSeek Flash,使用 set.env 的 base_url/flash_model/api_key。
```

验收:

```text
给定同一个 ValidatedTransaction,Renderer 生成中文玩家文本。
文本使用指定 motifs,但不新增未提交事实。
```

### Phase 7 - Post-render Checker (2 天)

交付:

```text
post_render_checker.py
tests/test_post_render_checker.py
```

模型:

```text
local vLLM + deterministic forbidden claim check。
```

验收:

```text
Renderer 如果写出 hidden_truth 或 NPC 内心,checker 能要求 light repair。
Renderer 如果只做 motif 变奏,checker pass。
```

### Phase 8 - Runner 切换和 20-turn Playtest (3-5 天)

交付:

```text
runner.py transaction-first 主流程
scripts/agentic_dungeon_smoke_test.py
docs/reports/reportVer0.7.0.md
```

验收:

```text
DND 地城 seed 连续 20 turn 不 fallback。
至少 surface 5 个 hints。
至少 engage 3 个 hooks。
至少 resolve 或 expire 1 个 hook。
至少 2 个 motif 有跨 turn 变奏。
无 hidden_truth 非法直泄。
无 renderer 未提交事实进入 WorldGraph。
```

---

## 8. 数字目标

| 指标 | v0.6.6.x | v0.7.0 目标 |
|---|---:|---:|
| 主流程 | Writer-first | Transaction-first |
| Renderer 是否能改 world | 间接能 | 不能 |
| Hard Auditor 关键词依赖 | 高 | 低,仅 post-render 兜底 |
| fallback 触发率 | 高波动 | < 5% |
| 20-turn 可玩性 | 不稳定 | DND seed 可完成 |
| active hooks 增长/推进 | 偶发 | 每 3 turn 至少一次 |
| motif 复用 | prompt 期望 | ledger 追踪 |
| hidden truth 泄露 | 依赖扫描 | transaction 禁止 + post-check |
| prose 质量 | Writer 兼顾结构导致受损 | Render 层专职负责 |

---

## 9. 风险与边界

| 风险 | 处理 |
|---|---|
| 过度结构化导致文本僵硬 | Render 层只吃 render_brief,用 DeepSeek Flash 高质量渲染,保留 motif 变奏空间 |
| local vLLM 规划能力不足 | Director schema 缩小到 6 类动作和 8-10 个 operation,失败时 deterministic fallback transaction |
| Renderer 偷加新事实 | Post-render checker + light repair;不能通过 checker 的文本不输出 |
| WorldGraph 迁移太大 | v0.7.0 先做 adapter,不一次性删除旧 WorldState |
| DND 用户预期包含完整战斗 | v0.7.0 明确只做探索/社交/危险张力,完整战斗放 v0.8 |
| Hook grammar 变成硬编码剧情 | 只定义张力类型和状态迁移,不写固定剧情路径 |

---

## 10. 不在 v0.7.0 范围

```text
完整 DND 战斗系统
角色卡/法术/装备数值全规则
任意开放世界
长期主线自动规划
多人队伍管理
save/load 大改
```

v0.7.0 只验证:

```text
有限地城场域 + 结构化叙事语法 + TurnTransaction + DeepSeek Flash Render
```

---

## 11. Done Definition

v0.7.0 完成条件:

1. `dnd_ashen_vault_seed.yaml` 和 `dnd_dungeon_grammar.yaml` 可加载。
2. `runner.py` 默认走 transaction-first 流程。
3. Director 使用 local vLLM 输出 TurnTransaction。
4. Validator 能接受/降级/拒绝 transaction。
5. Committer 只提交 ValidatedTransaction。
6. Renderer 使用 DeepSeek Flash 生成最终中文玩家文本。
7. Post-render Checker 能阻止未提交事实和 hidden truth 泄露。
8. DND 地城 smoke test 连续 20 turn,无系统模板 fallback。
9. 报告记录 hook/hint/motif/world_diff 的真实数据。

---

## 12. 一句话总结

> **v0.7.0 的目标不是让 Auditor 更会读散文,而是让散文不再承担世界提交职责。项目进入 "Narrative Grammar 生成张力,TurnTransaction 提交世界,DeepSeek Flash 专职 Render" 的架构状态。这样 LLM 仍然能大胆创作 motif 和场景质感,但世界只接受经过结构化交易和规则校验的内容。**
