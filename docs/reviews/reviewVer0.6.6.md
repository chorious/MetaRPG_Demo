# reviewVer0.6.6 — 自展开世界:本体论原语而非内容硬编码

日期: 2026-05-18
评审范围: 全部 v0.6.x 累积 + 与用户对齐的根本目标

---

## 0. 立场再次校准(诚实记录,这是第三次)

本文件之前的版本都偏了:
- **v1**: 砍引擎复杂度 → 错,引擎不是迭代慢的根因
- **v2**: 激进精简引擎 → 错,同样
- **v3**: 硬编码 3 NPC + 5 hook + 主线弧 → **更错**,把项目变成了"AI 当渲染器,我们当编剧"

用户原始目标(原话):
> 我想要的是你结构化抽象到一个点上,依靠LLM的灵感写作,就能自动张开一个世界。比如一个人存在周期节律这么一个基础规则,就会出现时间感觉,然后LLM创造一种可能世界,被接受后就固化到世界知识当成一种已知。

这是一个**生成式约束**而非**否定式约束**的系统:
- 否定式("不能出现光剑")已经在做,这是 v0.6.5 之前所有约束的本质
- 生成式("时间在流,所以 Mara 必须有疲倦")是 v0.6.6 才开始做的事

**v0.6.6 的核心命题: 给 LLM 一组本体论原语,LLM 在原语下创作,被接受的虚构固化为新知识,新知识约束未来虚构。世界自己长大,我们不写内容。**

---

## 1. 三条用户对齐(2026-05-18)

| # | 问题 | 决策 | 含义 |
|---|---|---|---|
| 1 | 固化门槛 | 物理事实(地点/物品/外表/动作) Audit 过即固化;NPC 内心/秘密/动机是**概率矩阵**,随交互坍缩 | 双层世界知识:确定层(facts) + 概率层(beliefs) |
| 2 | LLM 写出与已固化事实冲突时 | 记为"传说冲突",可共存 | 不强制 LLM 重写,世界容纳矛盾。"Mara 说井是爷爷挖的" 与 "Olen 说井是社区共挖的" 可同时是 facts |
| 3 | 节律原语起点 | **时间流动**(日夜/turn=时间流逝) | NPC 状态(疲劳/饱/情绪)随 world.time tick 自动推进 |

---

## 2. v0.6.6 = 三大原语 + 一个固化机制 + 一个传说冲突机制

### 2.1 原语 A — 时间流动 (`time_flow.py` 新建)

**核心**: world.time 不再只是 `world.turn` 计数,而是有结构的时间(`hour_of_day`、`day_count`、`season`)。

实现要点:
- `world.time = {turn: int, hour: int, day: int}`
- 每个 player 行动消耗时间(由 LLM 估算,默认 5-30 分钟,固化到 commit)
- `hour` 推进会 wrap 到下一天,触发 `day_count++`
- story_packet 把 time 暴露给 Writer:`"current_time": "黄昏 17:40, 第 3 天"`
- Writer prompt 加: 看到时间时,所有 NPC 的状态必须反映时间(早起的人在傍晚显得疲倦,清晨的人显得清醒)

测试: 同一个 Mara,turn 1(早晨)是 "袖子卷起,刚打完水",turn 10(深夜)是 "用手背擦了擦眼角,你看出她已经撑了一天"。

### 2.2 原语 B — 实体生命周期 (`entity_lifecycle.py` 新建)

**核心**: 每个被 LLM 命名的实体(人/动物/具名物)自动获得生命周期字段。

实现要点:
- 字段: `{energy, mood, last_seen_turn, last_seen_location, life_state}`
  - energy: 0.0-1.0,随 turn 衰减,睡眠/吃饭恢复
  - mood: 一个向量,LLM 可读可推,基于近期事件衰减
  - life_state: alive/asleep/injured/dead — 影响 LLM 描述
- LLM 首次命名实体时,Writer 输出 `acquire_entity` patch(类比 acquire_item),自动初始化字段
- 实体不在场时仍在 tick(后台状态推进,见 2.5 离场推演)
- story_packet 暴露**当前在场实体**的状态给 Writer

测试: 玩家在 tavern 见过 Mara(turn 1),turn 10 再去 tavern,Mara 的 energy 应该已经从 0.9 衰到 0.3,Writer 描述她"靠在椅背上,杯子在指间转得很慢"。

### 2.3 原语 C — 双层世界知识(facts + beliefs)

**核心**: 把 v0.6.x 现有的 `world.facts` 和 `auditor_only.all_beliefs` 整合成对偶系统。

| 层 | 性质 | 固化条件 | LLM 可见性 |
|---|---|---|---|
| **facts** | 确定的、不可推翻的物理世界 | Hard Audit 通过即固化 | Writer 完全可见,叙事必须遵守 |
| **beliefs** | NPC 内心/秘密/动机 | 概率矩阵,初始化时由 LLM 估给定先验 | Writer 看到的是"可能性分布",不是确定值 |

实现要点:
- `world.facts: list[Fact]` — 既有,扩充类型(LocationFact、EntityAppearanceFact、EventFact、PropFact)
- `world.beliefs: dict[BeliefID, BeliefState]` — 既有 H1-H6 改为通用
- belief 坍缩规则:玩家行动 + LLM 判断 → 增加证据 → 概率更新
- story_packet 给 Writer 的格式:
  ```
  facts (must respect):
    - The well in village square has clear water
    - Mara has tied-back red hair
  beliefs (probabilistic, narrate consistently with one but don't reveal):
    - Mara knows about the mine (p=0.45)
    - Rusk is hiding something about the night patrol (p=0.30)
  ```
- Writer 在叙事中 implicit 选一个 belief 投影,被玩家行动**确认**或**反证**后,概率向 1 或 0 坍缩
- 坍缩到 > 0.85 或 < 0.15 时,转入 facts(或被删除)

测试: 玩家连续 3 turn 问 Mara 关于矿坑,每次 Mara 含糊回答 → `mara_knows_recent_entry` 概率从 0.45 升到 0.78 → turn 8 Mara 主动透露 → 概率 1.0,转入 facts: "Mara 知道矿坑的事"。

### 2.4 原语 D — 固化机制 (`crystallize.py` 新建,~80 行)

**核心**: 把 Writer 写出的散文中的"新世界事实"提取并写入 world.facts。

实现要点:
- 在 `committer.py` 的 commit 阶段之后加 crystallize step
- 输入: `final_segments` + 已通过的 `hard_audit`
- LLM(Qwen) 调用: "以下叙事中,有哪些是**新的物理世界事实**(地点/物品/实体外貌/具体动作)? 输出 JSON list"
- 每条新 fact 进 `world.facts`,带 source(`turn_id`)和 confidence
- 不固化的: NPC 内心独白(已被 Hard Auditor 拦)、推测、玩家的主观感受

测试: turn 1 Writer 写 "Mara 从架上取下陶杯" → crystallize 提取 `prop_exists(clay_cup, in tavern)`、`appearance(mara, has_pottery_shelf_behind_her)`。下次 LLM 看到 facts 时,陶杯和木桶是已知的,不能突然变成"金属杯"。

### 2.5 原语 E — 传说冲突 (`lore_conflict.py` 新建,~40 行)

**核心**: 当 crystallize 提取的新 fact 与已有 fact 矛盾时,不报错、不重写,而是**记录两者并存**。

实现要点:
- 每个 fact 带 source attribution: "Mara 在 turn 5 声称:井是爷爷挖的"
- 矛盾检测:同一 predicate 不同 args(`well_dug_by(mara_grandfather)` vs `well_dug_by(community)`)
- 不删除任何一方,在 `world.lore_conflicts` 里记录这一对
- story_packet 把存在冲突的 fact 标记给 Writer:"⚠️ Mara 和 Olen 对井的来源说法不一致"
- Writer 可以在叙事中**主动利用矛盾**(让 NPC 互相质疑、让玩家发现某方在撒谎)

测试: Mara 在 turn 5 说"井是爷爷挖的",Olen 在 turn 8 说"井是社区共挖的"。两条都进 facts,但 lore_conflicts 标记。turn 12 玩家追问 Mara,Writer 看到冲突,让 Mara 沉默或改口。

### 2.6 原语 F — 离场推演 (`offscreen_tick.py` 新建,~60 行)

**核心**: 玩家不看着 NPC 时,NPC 也在 tick。

实现要点:
- 每 turn 开始前,对所有 `last_seen_turn < current_turn - 1` 的实体跑一次 tick
- LLM(Qwen) 调用:"Mara 在过去 X 小时(玩家不在场期间),做了什么?"
- 输出限制:一句话,不创造新事实,只更新 energy/mood/life_state
- 玩家下次见到该 NPC 时,Writer 看到的是 tick 后的状态
- 这条让 NPC 真的"有自己的生活",而不是只在被玩家看到时才存在

测试: 玩家 turn 5 离开 tavern,turn 10 回来。期间 Mara 在 offscreen tick 中可能"招待了 3 个旅人,补了一次水桶,小睡了一会儿"。turn 10 玩家见她时,Writer 看到这些,叙事会织进去。

---

## 3. v0.6.6 引擎修复(顺手做,1 行 + 30 行)

只修阻塞 Turn 2 的两个 bug,**其他引擎一律不动**:

| # | 改动 | 文件 | 行数 |
|---|---|---|---|
| 1 | `max_tokens` 2048 → 4096 | `model_client.py:43` | 1 |
| 2 | Hard Auditor `consume_item` 读 recent_events | `hard_auditor.py:266-299` | ~30 |

---

## 4. v0.6.6 显式不做的事

| 不做 | 理由 |
|---|---|
| ❌ 硬编码 3 个 location | 玩家移动到新地点时,LLM 自由创作,crystallize 后地点固化 |
| ❌ 硬编码 3 个 NPC + schedule | 任何被命名的实体自动获得生命周期,schedule 由 offscreen_tick 涌现 |
| ❌ 硬编码 5 个 hook | beliefs 概率坍缩自然产生"揭示时刻",不需要预定义 hook |
| ❌ 主线弧 | 没有"主线",只有玩家在原语世界中行动产生的事件序列 |
| ❌ 砍 Safe Writers / refusal_fallback | 这些是质量保险,与自展开正交 |
| ❌ 简化 Feasibility 4 分支 | absence/friction/reframing 是"世界拒绝"的语气库,有用 |
| ❌ 优化 wall time | 6 个原语会增加 LLM 调用,延迟会涨。先证明涌现可行,再优化 |

---

## 5. 实施顺序(每步都有可验证里程碑)

### Phase 1 — 时间流动 + 引擎修复(2-3 天)

- max_tokens 修
- hard_auditor 读 recent_events 修
- `world.time` 数据结构 + tick 推进
- story_packet 暴露 time
- Writer prompt 改

**验收**: 玩同一场景 5 turn,Mara 在 turn 1 早晨 vs turn 5 黄昏的描述明显不同(精力、光线、活动)。

### Phase 2 — 实体生命周期(3-4 天)

- `acquire_entity` patch
- entity 状态字段
- 衰减规则
- story_packet 暴露在场实体状态

**验收**: 玩家与 Mara 连续互动 10 turn,Mara 的 energy 衰减肉眼可见(从精力充沛 → 疲倦)。

### Phase 3 — 固化机制 (crystallize) + 双层知识(3-4 天)

- world.facts 扩充类型
- world.beliefs 通用化
- crystallize step in committer
- story_packet 区分 facts vs beliefs

**验收**: turn 1 LLM 创作的物品(陶杯、木桶)在 turn 5 LLM 必须遵守,不能突然变成金属。一个 belief 在玩家追问后从 0.45 升到 0.85,变成 fact。

### Phase 4 — 传说冲突(2 天)

- lore_conflicts 数据结构
- 冲突检测
- story_packet 标记冲突
- Writer prompt 加冲突利用指引

**验收**: 构造一个 case,让两个 NPC 在不同 turn 给同一物品的不同来源。Writer 在 turn 12 让玩家发现矛盾。

### Phase 5 — 离场推演 (offscreen_tick)(2 天)

- offscreen_tick LLM 调用
- 状态更新规则
- story_packet 注入

**验收**: 玩家离开 tavern 5 turn,回来时 Mara 的状态(包括叙事中的小行为)反映了离场期间的变化。

### Phase 6 — 端到端 playtest(2-3 天)

- 真人玩 20+ turn,记录每次 turn 的固化、冲突、坍缩、tick
- 发现的 prompt 问题反复迭代

**总工作量**: ~2 周

---

## 6. 关键修改文件清单(v0.6.6)

### 新建文件
- `metarpg/agentic/time_flow.py` — time tick + hour wrap
- `metarpg/agentic/entity_lifecycle.py` — 实体生命周期字段 + 衰减
- `metarpg/agentic/crystallize.py` — 散文 → fact 提取
- `metarpg/agentic/lore_conflict.py` — 矛盾检测
- `metarpg/agentic/offscreen_tick.py` — 离场实体 tick

### 改动文件
- `metarpg/agentic/model_client.py:43` — max_tokens
- `metarpg/agentic/hard_auditor.py:266-299` — consume_item 读 recent_events
- `metarpg/agentic/story_packet.py` — 暴露 time / facts / beliefs / conflicts / entity states
- `metarpg/agentic/writer_agent.py` — system prompt 加原语指引
- `metarpg/agentic/committer.py` — 接入 crystallize step
- `metarpg/agentic/runner.py` — 接入 offscreen_tick (turn 开始) + crystallize (commit 后)
- `metarpg/agentic/schemas.py` — 新 patch kind: `acquire_entity`、`time_advance`、`belief_update`
- `metarpg/world/state.py` (或对应) — world.time / world.beliefs / world.lore_conflicts 字段

### 测试
- `tests/test_time_flow.py`
- `tests/test_entity_lifecycle.py`
- `tests/test_crystallize.py`
- `tests/test_lore_conflict.py`
- `tests/test_offscreen_tick.py`
- `tests/test_belief_collapse.py`

---

## 7. 数字目标(v0.6.6 vs v0.6.5)

| 指标 | v0.6.5 | v0.6.6 目标 |
|---|---|---|
| 可玩 turn 数(不重复) | ~3 | **20+** |
| 自展开 location 数(玩家走到的) | 0 | **>= 5** |
| 自展开 entity 数(LLM 命名的) | ~3 (预设) | **>= 10** |
| world.facts 增长(20 turn 后) | n/a | **>= 50 条** |
| beliefs 坍缩事件 | 0 | **>= 3** |
| lore_conflict 事件 | n/a | **>= 1** |
| Bold 输出质量 | 已 OK | 保持 |
| 中位 wall time | 141s | **接受涨到 ~200s** (6 原语都开) |

---

## 8. 风险与缓解

| 风险 | 缓解 |
|---|---|
| 6 个原语 LLM 调用累积,wall time 大涨 | 优先 Phase 1(time)单独验证涌现效果是否值得;不值得就停 |
| crystallize 提取错误的 fact(把推测当事实固化) | crystallize prompt 严格限定"必须是被 Hard Auditor 通过的物理描述";低置信度的不进 facts |
| beliefs 坍缩规则调不准,要么从不揭示要么一直揭示 | Phase 3 用固定阈值 0.85/0.15,playtest 调参 |
| LLM 命名混乱(turn 1 叫 "Mara",turn 5 改叫 "玛拉小姐") | entity_lifecycle 用 canonical_name + aliases;crystallize 时归一化 |
| 离场 tick 创造矛盾事实 | offscreen_tick 输出限制为"状态更新",不允许创造新 entity/location/event |
| 自展开方向太抽象,2 周做不完 | 每个 Phase 独立可验,做不完就停在能 ship 的 Phase。Phase 1 + 引擎修复就已经比 v0.6.5 好 |

---

## 9. v0.6.7 蓝图(纯 UX,假设 v0.6.6 涌现已工作)

- Save / Load(JSON 序列化 world)
- Beliefs 概率可视化(玩家可选打开"导演视角"看坍缩进度)
- 时间流可视化(进度条/日历)
- 玩家可命名实体/地点(主动固化)
- ambient 事件触发系统(基于 time + belief 状态)

---

## 10. 一句话总结

> **v0.6.6 不写内容,写原语。给 LLM 时间流 + 实体生命周期 + 双层知识 + 固化机制 + 传说冲突 + 离场推演这六件事,让世界自己长出 NPC、地点、矛盾和叙事弧。引擎只修两行真 bug,其他不动。这是"受强约束的 LLM 跑团"原始目标的第一次真正实现——之前的版本一直在做"防止 AI 说错",从这版开始做"让 AI 创造一个会自己长大的世界"。**
