# reviewVer0.7.4 - 指标闭环通过,但 Semantic Closure 结论过早

日期: 2026-05-20

评审范围:

- `docs/reports/reportVer0.7.4.md`
- `runtime/agentic_runs/v070_smoke_3abf4c15/`
- `runtime/agentic_runs/play_5d739e09/`
- smoke test 终端输出:
  - `C:\Users\MUSHI\.claude\projects\D--guKimi\66bbc627-a8b6-43b2-b431-59d9a04d0d1f\tool-results\br2pdz47f.txt`
- v0.7.4 新增测试子集:
  - `tests/test_analyzer_taxonomy.py`
  - `tests/test_intent_fulfillment.py`
  - `tests/test_render_brief_obligation.py`
  - `tests/test_unreachable_location.py`
  - `tests/test_render_repair_targeted.py`

---

## 0. 总体结论

v0.7.4 相比 v0.7.3 是明显进步,但不能按报告结论验收为 **semantic quality closure**。

它可以验收为:

```text
analyzer taxonomy cleanup
fallback elimination baseline
intent contract initial implementation
repair loop wiring proof
```

但不能验收为:

```text
semantic quality closure
player-intent correctness closure
spatial consistency closure
```

核心原因:

```text
Analyzer / smoke summary 已经全绿,但 artifact 中仍存在语义矛盾:

1. unreachable_location_response 的 prose 写成了玩家已经到达目标门并触碰/推动门。
2. absent NPC 的 observe_reaction 仍被 Validator 接受。
3. black_ash 这类 item 被塞进 visible_entities,并被 Renderer 写成人。
4. L2 并没有在这些高风险 turn 上运行,所以 final_pass 是漏判后的绿。
```

因此本 review 的版本定性是:

```text
结构指标: 通过
fallback taxonomy: 通过
report/analyzer/smoke 数字一致性: 通过
Turn 5 stale-context regression: 已改善
semantic coverage: 未通过
transaction spatial consistency: 未通过
entity/object type discipline: 未通过
是否可进入 v0.8.0: 不建议
```

补充检查 `play_5d739e09` 后,这个结论需要进一步加强:

```text
真实 play run 能形成基本可读的酒馆 -> 问线索 -> 去哨站 -> 遇到 Rusk 流程。
但 play runner 的 scorecard 明显过度乐观:
  fallback turn 可以拿 experience=1.0 / grounding=1.0
  hidden truth 可以通过 public facts 泄露
  叙述视角和连续性错误没有被抓
  soft audit 只记录,不触发 rewrite
```

v0.7.4 下一步不应直接扩展 entity AI 或多场景。应先做 v0.7.4.1 correctness patch,把 "该跑 L2 的地方没跑" 和 "transaction 层允许错误事实" 这两个问题修掉。

---

## 1. 复核结果

对 `runtime/agentic_runs/v070_smoke_3abf4c15` 运行:

```text
python scripts/analyze_agentic_run.py runtime/agentic_runs/v070_smoke_3abf4c15
python scripts/analyze_agentic_run.py --fail-on-invariant runtime/agentic_runs/v070_smoke_3abf4c15
```

Analyzer 输出:

| 指标 | 结果 | 评审 |
|---|---:|---|
| turns | 20 | 通过 |
| errors | 0 | 通过 |
| fallback | 0 | 通过 |
| director_schema_fallback_count | 0 | 通过 |
| validation_rejection_fallback_count | 0 | 通过 |
| total_fallback_count | 0 | 通过 |
| deterministic_movement | 2 | 通过 |
| absence_response | 2 | 通过 |
| unreachable_location_response | 2 | 结构通过,语义未过 |
| validator accepted_turns | 20 | 表面通过 |
| validator rejected_turns | 0 | 表面通过 |
| downgraded_turns | 1 | 可接受 |
| post_render initial_pass | 19 | 通过 |
| post_render repaired | 1 | 触发一次 |
| post_render final_pass | 20 | 表面通过 |
| final_failed | 0 | 表面通过 |
| repair_attempts | 1 | 通过,但修复质量仍有漏判 |
| L2 judgments_run | 9 | 数字需重定义 |
| hard_rejects | 0 | 表面通过 |
| hidden_truth_nonpass | 0 | 表面通过 |
| invalid_hook_ids | [] | 通过 |
| move_player_missing_destination | 0 | 通过 |
| unresolved_turns | 0 | 通过 |
| absent_target_turns | 7 | 正常但需细分 |

Analyzer 与 smoke final summary 这次一致。v0.7.3 的 fallback 统计口径问题已经修掉。

新增测试子集复跑结果:

```text
26 passed
```

说明 v0.7.4 的新增单元测试本身可以通过。

注意: 第一次在普通 sandbox 下运行 pytest 失败,原因是 `C:\Users\MUSHI\AppData\Local\Temp\pytest-of-MUSHI` 和 `.pytest_cache` 权限,不是测试断言失败。使用正常权限后测试通过。

---

## 2. 已经符合预期的部分

### 2.1 Fallback taxonomy 修复有效

v0.7.3 的问题是:

```text
analyzer source fallback = 1
smoke summary fallback = 2
```

v0.7.4 中:

```text
director_schema_fallback_count = 0
validation_rejection_fallback_count = 0
total_fallback_count = 0
```

这项通过。

后续 report 应继续保持:

```text
source distribution 不替代 fallback taxonomy
fallback taxonomy 必须拆分原因
```

### 2.2 Turn 5 stale-context 问题明显改善

v0.7.3 的 Turn 5:

```text
玩家输入: 我搜索旧卫兵室。
输出: 继续写推密封下层门。
```

v0.7.4 的 Turn 5:

```text
你踱步到通道尽头。这里没有旧卫兵室——只有那扇沉重的铁门...
```

虽然仍然比较简短,但它至少回应了:

```text
玩家搜索旧卫兵室
当前地点找不到旧卫兵室
```

这说明 `Current-Turn Render Contract` 和 `Intent Fulfillment` 的方向是对的。

### 2.3 Unreachable branch 进入 pipeline

Turn 16 / Turn 17 不再 fallback,而是:

```text
source: unreachable_location_response
```

这说明 v0.7.4 已经把:

```text
known location but not directly reachable
```

从 generic fallback 中剥离出来。

这项结构上通过。

### 2.4 Repair loop 至少被 live run 触发

Turn 6:

```text
post_render status = repaired
repair_attempted = true
repair_success = true
```

这比 v0.7.3 的 `repair_attempts = 0` 前进了一步。

但见下文: 当前 repair 后仍存在 entity/object 类型漏判,所以只能说 repair loop 被触发,不能说 repair quality 已经充分验证。

---

## 3. 不能放过的问题

## 3.1 P0: unreachable response 的 prose 与 transaction 自相矛盾

Turn 16 的 RenderBrief:

```json
{
  "player_location": "flooded_stair",
  "current_turn_obligation": {
    "player_input": "我回到封闭下层门。",
    "action_type": "move",
    "target_ids": ["sealed_lower_door"],
    "source": "unreachable_location_response",
    "response_mode": "unreachable",
    "must_address": ["目标地点存在但当前无法直接到达"],
    "must_not_claim": ["不要渲染玩家已成功到达该地点"]
  }
}
```

这是正确的 contract。

但最终 prose:

```text
你握着短剑与火炬，转身回到那道封闭的下层门——它依然沉默地立在浑浊的水面之下。
...
你试着推动铁门，它纹丝不动。
```

这直接违反了:

```text
不要渲染玩家已成功到达该地点
```

Turn 17 同类:

```text
你试着摸索门边...
```

而 transaction 仍然是:

```text
The sealed lower door is not directly reachable from here.
```

更严重的是:

```json
artifact_016_semantic_judgments.json:
{
  "judgments": [],
  "l2_ran": false
}

artifact_017_semantic_judgments.json:
{
  "judgments": [],
  "l2_ran": false
}
```

也就是说 v0.7.4 把 current-turn contract 写进了 RenderBrief,但 checker 没有在最需要检查的 unreachable turn 上运行。

这直接推翻报告中的强结论:

```text
the system now checks that rendered prose actually responds to the current turn's player intent
```

更准确说法应是:

```text
系统在部分 risk turns 上检查了 intent fulfillment。
但 unreachable response 这种最高风险 response mode 没有被检查。
```

## 3.2 P0: absent NPC 的 observe_reaction 仍被 Validator 接受

Turn 20 的 transaction:

```json
{
  "kind": "observe_reaction",
  "params": {
    "entity": "alen",
    "description": "Alen watches you from the shadows..."
  }
}
```

同一 turn 的 whitelist:

```json
"visible_entity_ids": ["player"]
```

同一 turn 的 RenderBrief:

```json
"visible_entities": [],
"absent_entities": ["alen"]
```

Validator 结果:

```text
accepted
issues: []
```

这说明:

```text
absent NPC reaction guard 没有在 transaction validator 层真正生效。
```

Turn 14 也有同类问题:

```text
observe_reaction entity=alen
visible_entity_ids=["player"]
Validator accepted
```

Renderer 最后没有写出 Alen,所以玩家输出看起来没炸。但这是运气,不是约束。

正确原则应是:

```text
transaction 层不能包含 absent NPC 的 speak / observe_reaction / belief_evidence。
如果 Director 生成了,Validator 必须 hard_fail 或删除/降级。
```

不能把这个问题留给 Renderer:

```text
Renderer 不渲染错误 reaction != transaction 没有错误事实。
```

## 3.3 P1: item/entity 类型边界穿透

Turn 6 的 RenderBrief:

```json
"visible_entities": ["black_ash", "alen"],
"visible_objects": []
```

`black_ash` 是 item / prop,不是 entity。

最终 prose:

```text
黑灰——那个总像融在阴影里的人——站在柱旁...
```

L2 `render_claim_support` 还判定:

```text
pass
evidence: mentions Black Ash and Alen being present in the hall, which aligns with at(black_ash,entrance_hall)
```

这暴露了两个问题:

```text
1. RenderBrief 把 object/item 塞进 visible_entities。
2. L2 把 at(item, location) 误解成人物在场支持。
```

这是类型系统问题,不是文案问题。

如果不修,后续会继续出现:

```text
black_ash 被写成人
door 被写成 NPC
torch 被写成行动者
```

## 3.4 P1: L2 coverage 指标误导

Report 写:

```text
Intent fulfillment judge ran on all 9 risk turns.
```

但 artifact 显示:

```text
Turn 6: l2_ran = true, 3 judgments
Turn 9: l2_ran = true, 3 judgments
Turn 12: l2_ran = true, 3 judgments
其他 turns: l2_ran = false
```

所以 `judgments_run = 9` 更像是:

```text
3 turns * 3 judgments
```

而不是:

```text
9 risk turns
```

这种口径会掩盖真正问题:

```text
Turn 16 / 17 / 20 明显高风险,但 L2 没跑。
```

v0.7.4.1 必须增加:

```text
l2_required_turns
l2_ran_turns
l2_required_but_not_run_count
```

而不是只统计 judgment 条数。

## 3.5 P1: Turn 20 hidden-truth / spatial risk 没进入 L2

Turn 20 transaction 中有:

```text
三处 angular marks
faintly glowing
residual heat
low resonant hum
synchronized with the faint pulse of the ash marks
```

这些并不必然违规,但它们靠近 hidden truth symbolic bridge:

```text
door + marks + resonance/hum + mechanism-like response
```

同时该 turn 还包含 absent Alen reaction。

按 v0.7.4 自己的目标,这是典型 risk turn,但:

```json
artifact_020_semantic_judgments.json:
{
  "judgments": [],
  "l2_ran": false
}
```

这说明 risk trigger 规则不可靠。

## 3.6 P2: artifact 包装说明不完全一致

用户给出的目录说明里包括:

```text
run.log
manifest.json
```

但实际 `runtime/agentic_runs/v070_smoke_3abf4c15/` 中检查到的是:

```text
events.jsonl
errors.jsonl
artifact_001_*.json ... artifact_020_*.json
```

未看到 `run.log` 和 `manifest.json`。

这不影响主结论,但说明 artifact packaging / report 描述仍需一致。后续如果要长期审计,`manifest.json` 很有必要,应该恢复。

---

## 4. 真实体验 Run `play_5d739e09` 补充复核

`play_5d739e09` 是更接近真实使用的 5-turn live run,不是 v0.7.4 smoke artifact 格式。

目录结构:

```text
turn_001.json ... turn_005.json
scorecard_001.json ... scorecard_005.json
run_manifest.json
events.jsonl
errors.jsonl
summary.md
```

`scripts/analyze_agentic_run.py` 不能直接分析这类 run:

```text
Error: no artifacts found in runtime\agentic_runs\play_5d739e09
```

因此它需要单独的 play-run analyzer,不能用 smoke analyzer 的绿灯替代真实体验验收。

### 4.1 表面流程是可读的

5 回合玩家动线:

```text
1. 和 Mara 寒暄,问近况,要酒
2. 品尝麦酒,追问矿井和 Iven,提出帮忙
3. 询问附近可去地点
4. 给小费,离开酒馆前往哨站
5. 与 Rusk 友好打招呼
```

这条线在输出层面能形成:

```text
tavern -> Mara clue -> guard post -> Rusk
```

作为最低限度 playable flow 是成立的。

但这并不代表体验验收通过。

### 4.2 P0: Turn 2 fallback 破坏核心交互

Turn 2 玩家输入:

```text
点了点头，品尝了一番麦酒 "本地的？味道不错。看起来矿井是挺危险的。伊文不见了？需要我帮忙找找么？"
```

预期响应:

```text
Mara 至少应回应玩家关于 Iven / 是否需要帮忙的提议。
```

实际 winner:

```text
winner=fallback
```

最终输出:

```text
麦酒顺着喉咙滑下去...
我盯着那圈白沫...
帮忙找找……这话出口时自己都觉得轻飘飘的...
```

问题:

```text
1. 没有让 Mara 回应玩家提议。
2. 从默认第二人称突然切到第一人称。
3. 变成玩家内心独白,而不是酒馆社交回合。
4. candidate_patch 只是 refusal_fallback transient_event,没有承载真实交互。
```

更严重的是 scorecard:

```text
experience = 1.0
grounding = 1.0
action_understanding = 1.0
notes = winner=fallback
```

这说明:

```text
synthetic fallback 当前可以绕过真实体验评估。
```

v0.7.4.1 必须规定:

```text
fallback turn 不能默认满分。
fallback 必须进入 intent fulfillment / perspective / continuity judge。
```

### 4.3 P0: Hidden truth 与 public facts 混线

play run 的 story packet 中:

```text
allowed_reveals = []
auditor_only.hidden_truths = at(rusk,guard_post), alias=rusk_at_guard_post
```

但同一个 packet 的公开 facts 同时包含:

```text
at(rusk,guard_post)
```

Turn 3 Mara 直接说:

```text
北边哨站有个叫Rusk的卫兵
```

Hard audit 仍然 passed。

这说明:

```text
hidden truth 没有被 packet 边界隔离。
只扫 alias=rusk_at_guard_post 不够,自然语言 "北边哨站有个 Rusk" 同样是 reveal。
```

这和 v0.7.4 smoke 中的 hidden-truth symbolic policy 是同一个大问题:

```text
不是关键词表不够,而是 public facts / auditor facts 的分层不可靠。
```

v0.7.4.1 需要新增:

```text
hidden_public_fact_overlap_count
hidden_truth_semantic_reveal_count
```

验收必须是:

```text
auditor_only.hidden_truths 不得同时出现在 story_packet.facts。
未在 allowed_reveals 中的 hidden truth,不得被 NPC 自然语言透露。
```

### 4.4 P1: Turn 3 state continuity miss

Turn 2 已经:

```text
品尝了一番麦酒
```

Turn 3 输出:

```text
你点点头，把没碰的麦酒往吧台推了推...
```

这违反连续性。

scorecard 仍给:

```text
experience = 1.0
grounding = 1.0
state_continuity_score = 0.0
packet_support_score = 0.0
```

这里有两个问题:

```text
1. continuity judge 没有实际参与总分。
2. state_continuity_score = 0.0 没有触发 issue 或降分。
```

v0.7.4.1 必须让 continuity 成为硬门之一:

```text
喝过/拿过/交出/移动过 的对象状态不能在后续 turn 被反向描述。
```

### 4.5 P1: Soft audit 发现问题但不闭环

Turn 5 soft audit 标出:

```text
too_mechanical:
  "你决定友好地打个招呼，试图打破这层冰霜。"
  "似乎在评估你的威胁程度。"
```

判断是对的。

但:

```text
rewrite_history = 0
editor_tasks = null
```

最终输出仍保留这些问题。

这说明:

```text
soft audit 只是记录,没有触发 editor rewrite。
```

如果 soft audit 不影响输出,就不能把它写进可用质量保障里。

v0.7.4.1 需要:

```text
soft_audit_failed -> editor_task -> rewrite once -> re-score
```

至少对:

```text
too_mechanical
perspective_shift
clinical_npc_analysis
```

执行一轮轻量 rewrite。

### 4.6 P1: Scorecard 过度乐观

`summary.md`:

```text
turn_001: experience 1.00 / grounding 1.00
turn_002: experience 1.00 / grounding 1.00
turn_003: experience 1.00 / grounding 1.00
turn_004: experience 1.00 / grounding 1.00
turn_005: experience 0.85 / grounding 1.00
```

但人工复核:

```text
Turn 2 fallback 没回应核心社交动作
Turn 2 视角切到第一人称
Turn 3 麦酒状态连续性错误
Turn 3 hidden truth 通过 Mara 透露 Rusk at guard_post
Turn 5 soft audit 不修复
```

因此 scorecard 总分不能作为真实体验验收。

Play runner 需要新指标:

```text
fallback_full_score_count
perspective_shift_count
state_continuity_issue_count
hidden_public_fact_overlap_count
soft_audit_unrepaired_count
play_scorecard_overoptimism_count
```

---

## 5. v0.7.4.1 修复方向

v0.7.4.1 不应扩叙事功能,只做 correctness patch。

核心命题:

> **所有 current-turn obligation、spatial visibility、entity/object type 的约束必须在 Validator / L2 checker / Analyzer 三处形成闭环。**

补充 `play_5d739e09` 后,核心命题需要扩展为:

> **Smoke run 与 live play run 都必须可审计。play runner 的 fallback、hidden truth、连续性、soft audit 不得被 summary 分数掩盖。**

---

## Phase 1 - L2 Required Matrix

目标:

```text
明确哪些 turn 必须跑 L2,并让 analyzer 能发现该跑没跑。
```

必须跑 L2 的条件:

```text
current_turn_obligation.response_mode in ["unreachable", "absence", "safe_fallback"]
current_turn_obligation.must_not_claim 非空
transaction 中存在 speak / observe_reaction
transaction 中存在 absent target 或 available=false target
candidate_hints 涉及 hidden_truth symbolic_risk_patterns
Director 生成了 hint_door_three_marks / m_bell / resonance / hum 一类高风险组合
post-render status 是 repaired
```

新增 analyzer 指标:

```text
l2_required_turns
l2_ran_turns
l2_required_but_not_run_count
l2_required_but_not_run_turns
```

验收:

```text
l2_required_but_not_run_count = 0
Turn 16 / 17 / 20 必须进入 L2 或被明确解释为不需要
```

---

## Phase 2 - Unreachable Intent Enforcement

目标:

```text
unreachable_location_response 的 prose 不得描写玩家已到达目标地点。
```

规则:

```text
如果 response_mode == "unreachable":
  prose 必须表达 "当前无法直接到达/无法从这里过去"
  prose 不得表达 "已经回到/站在/触摸/推动目标门"
  prose 可以描写远处、记忆、方向判断,但不能发生目标地点互动
```

实现建议:

- `judge_intent_fulfillment()` 必须读取 `current_turn_obligation.must_not_claim`。
- 对 `response_mode=unreachable` 增加 few-shot:

```text
BAD: "你回到那扇门前,试着推动它。"
GOOD: "你辨认出那扇门的方向,但积水和断裂的阶梯让你无法从这里直接回去。"
```

Analyzer 新增:

```text
unreachable_response_contradiction_count
```

验收:

```text
Turn 16 / 17 不再出现到达、触摸、推动 sealed_lower_door 的 prose。
unreachable_response_contradiction_count = 0
```

---

## Phase 3 - Validator Spatial Guard Repair

目标:

```text
absent NPC reaction 不得进入 accepted transaction。
```

Validator 规则:

```text
For speak(entity):
  entity must be in visible_entity_ids

For observe_reaction(entity):
  entity must be in visible_entity_ids
  except explicit pseudo_entities: ["player", "environment"]

For belief_evidence commitment linked to an absent entity:
  reject or downgrade/remove
```

注意:

```text
"Alen watches from shadows" 不是合法绕过。
如果 Alen 不在 visible_entity_ids,就不能观察他的反应。
```

新增 analyzer 指标:

```text
accepted_absent_entity_reaction_count
accepted_absent_entity_speech_count
accepted_absent_entity_commitment_count
```

验收:

```text
accepted_absent_entity_reaction_count = 0
Turn 14 / Turn 20 不再 accepted absent Alen observe_reaction
```

---

## Phase 4 - Entity / Object Type Discipline

目标:

```text
item / object / location 不得进入 visible_entities。
```

RenderBrief 类型规则:

```text
visible_entities: NPC / actor only
visible_objects: item / prop only
visible_locations: optional, location affordances only
```

`black_ash` 应进入:

```text
visible_objects
```

不能进入:

```text
visible_entities
```

Renderer prompt:

```text
Items in visible_objects are inanimate unless explicitly marked as actor.
Never personify visible_objects as people or NPCs.
```

L2 `render_claim_support()`:

```text
at(item, location) supports object presence, not character agency.
```

新增 analyzer 指标:

```text
object_as_visible_entity_count
object_personification_claim_count
```

验收:

```text
black_ash 不再进入 visible_entities
Turn 6 不再出现 "黑灰...的人"
object_as_visible_entity_count = 0
```

---

## Phase 5 - Report Contract Tightening

目标:

```text
报告不再把 judgment count 误写成 risk turn count。
```

Report 必须区分:

```text
semantic_judgment_count
l2_ran_turn_count
l2_required_turn_count
intent_fulfillment_judgment_count
intent_fulfillment_turn_count
```

Artifact packaging:

```text
恢复或补齐 manifest.json
明确 run.log 与 events.jsonl 的关系
```

验收:

```text
report/analyzer/smoke mismatch = 0
report 中 "risk turns" 与 artifact 中 l2_ran_turns 一致
manifest.json 存在
```

---

## Phase 6 - Play Runner Experience Gates

目标:

```text
让真实 play run 的 summary 不再过度乐观。
```

新增 play analyzer:

```text
scripts/analyze_play_run.py runtime/agentic_runs/play_*
```

需要统计:

```text
turns
winner distribution
fallback_turns
fallback_full_score_count
perspective_shift_count
state_continuity_issue_count
hidden_public_fact_overlap_count
hidden_truth_semantic_reveal_count
soft_audit_failed_count
soft_audit_unrepaired_count
scorecard_overoptimism_count
avg_wall_time
```

必须新增 targeted tests:

```text
Turn 2 style:
  player asks NPC for help finding Iven
  fallback output only inner monologue
  expected: intent fulfillment downgrade/reject, experience < 1.0

Turn 2 perspective:
  output switches from "你" to "我"
  expected: perspective_shift issue

Turn 3 continuity:
  previous turn tasted ale
  current turn says "untouched ale"
  expected: state_continuity issue

Hidden truth:
  hidden_truth at(rusk,guard_post)
  public facts also contain at(rusk,guard_post)
  expected: hidden_public_fact_overlap hard issue

Soft audit:
  too_mechanical issue exists
  rewrite_history empty
  expected: soft_audit_unrepaired_count > 0 and summary not acceptable
```

验收:

```text
fallback_full_score_count = 0
perspective_shift_count = 0
state_continuity_issue_count = 0
hidden_public_fact_overlap_count = 0
soft_audit_unrepaired_count = 0
play_scorecard_overoptimism_count = 0
```

---

## 6. v0.7.4.1 重新验收标准

| 指标 | v0.7.4 | v0.7.4.1 目标 |
|---|---:|---:|
| errors | 0 | 0 |
| total_fallback_count | 0 | 0 |
| validator rejected_turns | 0 | 0 或有明确 fail-closed |
| move_player_missing_destination | 0 | 0 |
| invalid_active_hook_ids | [] | [] |
| l2_required_but_not_run_count | 未统计 | 0 |
| accepted_absent_entity_reaction_count | 至少 2 | 0 |
| object_as_visible_entity_count | 至少 1 | 0 |
| unreachable_response_contradiction_count | 至少 2 | 0 |
| hidden_truth_nonpass_after_repair | 0 | 0 |
| unrepaired_l2_rejects | 0 | 0 |
| final_failed | 0 | 0 |
| repair_attempts | 1 | >=1 targeted 或 live |
| avg wall time | 14.34s | <=24s |
| play fallback_full_score_count | 未统计 | 0 |
| play perspective_shift_count | 未统计 | 0 |
| play state_continuity_issue_count | 未统计 | 0 |
| play hidden_public_fact_overlap_count | 未统计 | 0 |
| play soft_audit_unrepaired_count | 至少 1 | 0 |
| play scorecard_overoptimism_count | 未统计 | 0 |

必须保留的 targeted tests:

```text
Turn 16 style:
  source=unreachable_location_response
  bad prose says "arrived at / touched / pushed target door"
  expected: intent_fulfillment reject

Turn 20 style:
  visible_entity_ids=["player"]
  operation observe_reaction(entity="alen")
  expected: validator hard_fail or operation removed before accepted transaction

Turn 6 style:
  visible_objects=["black_ash"]
  visible_entities must not include black_ash
  bad prose personifies black_ash as a person
  expected: render_claim_support reject

Play Turn 2 style:
  winner=fallback
  output does not answer Mara/help offer and switches to first person
  expected: fallback not full score, perspective issue, intent issue

Play Turn 3 style:
  previous turn tasted ale
  output says untouched ale
  expected: continuity issue

Play hidden truth style:
  at(rusk,guard_post) exists in auditor_only.hidden_truths and public facts
  expected: packet construction hard issue
```

---

## 7. 最终评价

v0.7.4 不是失败版本。

它修掉了 v0.7.3 中非常重要的工程问题:

```text
fallback 口径统一
validation rejection fallback 消失
Turn 5 stale context 改善
unreachable branch 接入
repair loop live 触发
新增测试通过
```

但它现在的问题更接近项目核心:

```text
系统已经学会把数字做绿。
但有些关键语义约束没有进入必须检查的路径。
真实 play run 进一步说明,summary 分数也会把 fallback、连续性和 hidden truth 边界问题压过去。
```

这正是当前 MetaRPG 最危险的阶段。因为 report 看起来全绿,但 artifact 仍然显示:

```text
不可达目标被写成已经到达
缺席 NPC 仍在 transaction 中观察玩家
物件被当成人
高风险 turn 没有跑 L2
```

一句话结论:

```text
v0.7.4 可归档为 fallback/metrics cleanup baseline。
不要标记为 semantic quality closure。
下一步应做 v0.7.4.1,专门修 L2 required coverage、unreachable prose enforcement、absent NPC validator guard、entity/object type discipline,并为 play runner 增加 fallback/continuity/hidden-truth/soft-audit 体验门。
```
