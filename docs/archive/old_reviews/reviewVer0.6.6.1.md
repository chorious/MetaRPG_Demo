# reviewVer0.6.6.1 — Hotfix: 自展开机制的五处工程断点 + inner_monologue 原语

日期: 2026-05-18
评审范围: `runtime/agentic_runs/play_6fde83d9/turn_003.json` 三路 Writer 全死,winner=fallback 事件

---

## 0. 问题定位(核对真相)

用户最初反馈:"Turn 3 准确但不够好——Mara 反馈太弱 + 需要自言自语"。

实测真相: **玩家看到的根本不是 LLM 的真实输出**,是 refusal_fallback 模板词拼接(`"你完成了感谢这个动作。\n周围如常..."`)。三路 Writer(Bold + Safe_loose + Safe_strict)都写得不错,但全部被 Hard Auditor 误判 hard_fail,被 fallback 取代。

Bold 实际输出的好东西(被埋没):
```
玛拉的目光在铜币上停留了片刻,嘴角微微一动——
那不像笑,更像某种谨慎的默许。
她迅速收起硬币,随即又拿起抹布擦拭吧台,没有再抬头。

你转身穿过几张散落的木桌,推开酒馆厚重的橡木门。
正午的阳光和街市的嘈杂声一同涌来...
```

这是好叙事。问题是引擎没把它送到玩家面前。

---

## 1. 五处工程断点(按阻塞性排序)

### 🔴 Bug 1: crystallize 与 hard_auditor 的 fact 参数顺序不一致

**症状**: `facts` 中明明有 `"has(coin,player)"`,但 Hard Auditor 报 "Player does not have 'coin' to consume"。Bold 死在这里。

**根因**:
- crystallize 提取 fact 时存为 `predicate="has", args=("coin", "player")` (item-first)
- `hard_auditor.py:271-274` 检查 `f.args == ("player", item)` (player-first)
- 参数顺序反了

**性质**: v0.6.6 重构引入的 regression。v0.6.5 之前 Hard Auditor 工作正常是因为 facts 由 committer 显式构造,与检查方向一致;v0.6.6 加 crystallize 后,LLM 自由产出的 fact 用了不同 convention。

**修复**: 二选一统一约定。建议改 crystallize 输出为 `("player", "coin")`(主语-宾语顺序更直觉,且 hard_auditor 已有的代码路径多)。

**文件**: `metarpg/agentic/crystallize.py`(查找 `predicate="has"` 的输出处) + 添加一个迁移 helper 处理已有 fact 库。

**测试**: 新增 `test_crystallize_has_args_order`,断言 `has(player, ale)` 格式;改 `test_inventory_events` 同步。

---

### 🔴 Bug 2: `move` 不在 allowed_effect_kinds,自展开多场景被堵死

**症状**: 玩家说"离开酒馆前往别处看看",Safe_loose / Safe_strict 都正确输出 `move:player` patch,被 `invalid_effect_kind` hard fail。

**根因**: story_packet `allowed_effect_kinds` 列表没有 `move`,committer 也没有 move 处理逻辑。

**性质**: v0.6.6 review 第 2.5 节说"原语 C 场景转移真正生效"(后改名为自展开版的"空间原语"),但实际重构没落地这一步。

**修复**:
1. `story_packet.py` 的 `allowed_effect_kinds` 加 `"move"`
2. `committer.py` 处理 `move` patch: 更新 `world.player_location`,新地点自动登记到 `world.locations`(LLM 描述被 crystallize 后,新 location 进 facts)
3. `schemas.py` 的 patch kind 白名单 加 `move`
4. `writer_agent.py` system prompt 加一行:"When player moves to a new location, emit a move patch with the destination name from your narrative."

**测试**: 新增 `test_move_patch_to_new_location`,验证 LLM 写 "你站在小镇主街" 后,`world.locations` 自动多一个 `town_main_street`。

---

### 🟡 Bug 3: 寒暄式 NPC speech 被 npc_speech_without_patch_support 误杀

**症状**: Safe_loose 让 Mara 说 "感谢你的慷慨" + "路上小心,外面的风有些大",两句都被判 `npc_speech_without_patch_support`。

**根因**: `hard_auditor.py` 对所有 npc_speech 都要求 `knowledge_transfer / reveal / create_hook` 支撑。但寒暄(greeting/farewell/thanks/pleasantry)是 social texture,**不创造可交互的 opportunity**,不应该被卡。

**修复**: hard_auditor 加 pleasantry 分类:
- 检查 npc_speech 的 evidence_span,匹配寒暄模式("感谢"、"路上小心"、"再会"、"欢迎"、"早安"等关键词或短句)
- 寒暄豁免 patch_support 检查
- 复杂判定可用一个轻量 Qwen 调用("这句话是寒暄还是传递新信息?")

**文件**: `metarpg/agentic/hard_auditor.py`(npc_speech 检查段附近)

**测试**: 新增 `test_pleasantry_speech_no_patch_required`。

---

### 🟡 Bug 4: lore_conflicts 误判嵌套关系和多次发言

**症状**: 当前 `lore_conflicts` 里两条都不是真冲突:
```
fact_a: at(ale,tavern)             ← 嵌套关系
fact_b: at(ale,rough_pottery_cup)

fact_a: said(mara,the_mine_is_sealed)             ← Mara 说过多句话
fact_b: said(mara,guards_patrol_more_frequently)
```

**根因**: 当前算法把"同一 subject 多个 predicate"一律判矛盾。但:
- `at(X, Y)` 是嵌套(X 在 Y 里),X 可以同时在多个嵌套层级 — `at(ale, tavern)` 和 `at(ale, rough_pottery_cup)` 不矛盾,只是详细程度不同
- `said(X, Y)` 是事件型 predicate,X 说过多句话本来就是正常的

**修复**: lore_conflict 检测重写:
- 只对"互斥型 predicate"做冲突检查
- 互斥定义: 同 predicate + 同 subject + value 在语义上不能共存(由 LLM 判定 + 缓存规则)
- `at(X, Y)` 走容器层级合并(陶杯属于酒馆,层级嵌套不算冲突)
- `said(X, *)` 不参与冲突检测(每次发言是独立 event)
- 真冲突示例: `dug_by(well, mara_grandfather)` vs `dug_by(well, community)` — 同 predicate 同 subject 不同 value 且互斥

**文件**: `metarpg/agentic/lore_conflict.py`

**测试**: 新增 `test_lore_conflict_at_predicate_nesting`、`test_lore_conflict_said_not_conflicting`、`test_lore_conflict_genuine_mutex`。

---

### 🟡 Bug 5: refusal_fallback 词拼接太机械 + 缺 inner_monologue 原语

**症状**: 即使 Writer 全死,玩家也应该看到有质感的叙事,而非 `"你完成了感谢这个动作。\n周围如常,没有什么需要立刻回应。"` 这种像系统报错的输出。

**根因**: `refusal_fallback.py` 用模板 + `preserve_player_voice` 词机械拼接,无 LLM 参与。v0.6.5/v0.6.6 review 多次说要重写但都推迟了。

**用户原话**: "这种场景需要插入某种**自言自语**"。

**修复方案 — 双轨**:

**A. refusal_fallback 改为单次 LLM 调用**(Flash,thinking off):
- Input: feasibility + preserve_player_voice + world_response_kind + 近 1 turn world state 摘要
- Output: 1-2 段以**玩家内心独白**为主的叙事,不创造新事实
- 模板四分支(absence/friction/reframing/accept)保留为 prompt 注入语气而非字面词拼接
- Fallback 输出标记 `segment.type="inner_monologue"`

**B. 新增 `inner_monologue` Segment type** 作为正式原语:

加入 Segment.type 枚举:
```
segment.type ∈ {
  "player_action",
  "npc_observable_reaction",
  "npc_speech",
  "sensory",
  "transition",
  "inner_monologue",  ← 新增
}
```

规则:
- 只能是 **player 自己的内心戏**,不能是 NPC(NPC 内心戏违反"不可见"约束)
- **不产生任何 patch**(declared_claims 强制为空,transient_only 强制 true)
- Hard Auditor 自动跳过 `patch_support_check` 和 `state_change` 检查
- Soft Auditor 仍检查"是否泄露 hidden_truth"(玩家内心可以怀疑,但不能突然就"知道")
- Writer system prompt 加指引: "在场景过渡、玩家明显沉思、或事件后情绪余波时,可插入 1 段 inner_monologue 增加质感"

**Refusal 路径下的玩家体验示例**(用 LLM 生成而非模板):
```
（你的手指还停在吧台边缘。
多付出去的那枚铜币现在归 Mara 了——
你说不清自己为什么要那么做。）
```

vs 当前模板:
```
你完成了感谢这个动作。
周围如常,没有什么需要立刻回应。
```

**文件**:
- `metarpg/agentic/refusal_fallback.py` 重写(模板 → LLM 调用)
- `metarpg/agentic/schemas.py` Segment.type 加 `inner_monologue`
- `metarpg/agentic/hard_auditor.py` inner_monologue 短路
- `metarpg/agentic/writer_agent.py` system prompt 加 inner_monologue 指引
- `metarpg/agentic/translator_agent.py` 处理 inner_monologue 的 claim 提取(只标记为主观,不进 facts)

**测试**:
- `test_inner_monologue_skips_patch_check`
- `test_refusal_fallback_uses_llm`
- `test_inner_monologue_no_patch_emitted`

---

## 2. 实施顺序

按"修一处验一处"的小步走:

| Step | Bug | 工作量 | 验证标准 |
|---|---|---|---|
| 1 | Bug 1(fact 参数顺序) | 0.5 天 | 重跑 play_6fde83d9 turn 3,Bold 应通过 audit,winner=bold |
| 2 | Bug 2(move 接通) | 1 天 | 同 turn,Safe_loose 的 move patch 也能通,玩家真到"street" |
| 3 | Bug 4(lore_conflicts 修正) | 0.5 天 | 重跑后 lore_conflicts 不应包含 at-nesting 或 said-multi |
| 4 | Bug 3(pleasantry 豁免) | 0.5 天 | "路上小心" 这类话不再 hard_fail |
| 5 | Bug 5(refusal LLM + inner_monologue) | 1.5 天 | 故意触发全死场景,fallback 输出像 "(你的手指还停在...)" 而非系统报错风 |

**总计**: ~4 天

**关键里程碑**: Step 1-2 完成后,turn 3 应该 winner=bold,玩家看到 Bold 的好叙事而非 fallback——这就直接回应了用户的"Mara 反馈太弱"反馈,因为反馈本来就在 Bold 里。

---

## 3. 关键修改文件清单

### 修改
- `metarpg/agentic/crystallize.py` — fact 参数顺序统一为 (subject, object)
- `metarpg/agentic/hard_auditor.py` — pleasantry 豁免 + inner_monologue 短路
- `metarpg/agentic/lore_conflict.py` — 重写互斥定义,排除 at-nesting / said-multi
- `metarpg/agentic/story_packet.py:allowed_effect_kinds` — 加 `move`
- `metarpg/agentic/committer.py` — 处理 move patch
- `metarpg/agentic/schemas.py` — patch kind 加 move; Segment.type 加 inner_monologue
- `metarpg/agentic/writer_agent.py` system prompt — move 指引 + inner_monologue 指引
- `metarpg/agentic/refusal_fallback.py` — 模板替换为 LLM 调用
- `metarpg/agentic/translator_agent.py` — inner_monologue 标记为主观 claim

### 新增测试
- `test_crystallize_has_args_order`
- `test_move_patch_to_new_location`
- `test_pleasantry_speech_no_patch_required`
- `test_lore_conflict_at_predicate_nesting`
- `test_lore_conflict_said_not_conflicting`
- `test_lore_conflict_genuine_mutex`
- `test_inner_monologue_skips_patch_check`
- `test_refusal_fallback_uses_llm`
- `test_inner_monologue_no_patch_emitted`

---

## 4. 数字目标(v0.6.6.1 vs v0.6.6)

| 指标 | v0.6.6 (play_6fde83d9) | v0.6.6.1 目标 |
|---|---|---|
| Turn 3 winner | fallback | **bold** |
| fallback 触发率(3 turn 内) | 33%(1/3) | **0%** |
| Bold pass rate(3 turn) | 67% | **100%** |
| 玩家可移动到新场景 | ❌(被 move audit 卡) | **✅** |
| lore_conflicts 假阳性 | 2/2 都是误判 | **0** |
| Refusal 出现时的输出质量 | 模板拼接 | **LLM 内心独白** |

---

## 5. 不在 v0.6.6.1 scope

| 不做 | 原因 |
|---|---|
| 加新 NPC / hardcode 内容 | v0.6.6 自展开方向不变,等 5 个 bug 修完后让 LLM 自展开继续 |
| 优化 wall time | 当前 ~60s/turn 够用,bug 优先 |
| Beliefs 坍缩调参 | beliefs 概率没变是因为 hook_tracker 应该跑但没接通?需先 grep 确认。如未接,放到 v0.6.6.2 |
| 主线弧 / quest | 同上 |
| save/load | v0.6.7 范畴 |

---

## 6. 一句话总结

> **v0.6.6 的自展开原语写完了,但有 5 个工程接缝没拧上,导致 Turn 3 这种简单场景三路 LLM 输出全被审计误杀,玩家看到的是 fallback 模板。v0.6.6.1 用 4 天修这 5 处接缝,并把 refusal_fallback 重写为 LLM 内心独白 + 引入 `inner_monologue` 作为正式 Segment 原语——这正好回应用户的"需要某种自言自语"反馈,同时不再加任何 hardcoded 内容。**
