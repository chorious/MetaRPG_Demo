# reviewVer0.7.3 - Artifact Invariant 全绿,但 Intent Fulfillment 仍未闭环

日期: 2026-05-19

评审范围:

- `docs/reports/reportVer0.7.3.md`
- `runtime/agentic_runs/v070_smoke_8dea5635/`
- `smoke_test_v073.log`
- `scripts/analyze_agentic_run.py`
- v0.7.3 主链路变更:
  - deterministic movement
  - RenderBrief grounding
  - absence_response
  - L2 hidden-truth symbolic policy
  - L2 repair loop wiring

---

## 0. 总体结论

v0.7.3 可以验收为 **single-seed artifact invariant baseline**。

它相对 v0.7.2.1 有实质进步:

```text
move_player no-op: 继续保持修复
active_hooks 非 canonical 污染: 继续保持修复
hidden_truth_nonpass: 从 1 降到 0
unrepaired_l2_rejects: 从 1 降到 0
deterministic_movement: 已真实触发 2 turn
absence_response: 已真实触发 2 turn
avg wall time: 21.64s -> 17.09s
```

但 v0.7.3 **不应被表述为完整 semantic quality closure**。

原因不是结构性失败,而是验收边界仍偏窄:

```text
1. 官方 20-turn 中仍有 validator rejected_turns = 1。
2. smoke log 最终摘要 Fallbacks = 2,但 analyzer source fallback = 1,口径未统一。
3. Turn 5 玩家说"搜索旧卫兵室",输出却继续写"密封下层门/推门",Post-render 仍 pass。
4. repair loop 已接线,但 20-turn 中 repair_attempts = 0,没有被 live run 证明。
5. Turn 16 "回到封闭下层门" 仍走 fallback,说明 unreachable/route navigation 还没有产品化路径。
```

因此本 review 的版本定性是:

```text
结构 invariant: 通过
artifact/analyzer 可审计性: 基本通过
hidden-truth symbolic policy: 通过单场景验证
spatial consistency regression: 当前 run 未复现
Intent Fulfillment: 未通过
repair loop: 已接线,未被真实验收
playable baseline: 可以继续内部试跑,不建议宣称语义闭环完成
```

v0.7.4 的核心应从 "L2 能抓泄露/空间错误" 推进到:

> **最终输出是否忠实响应本回合玩家意图,并且所有 fallback/rejected/unreachable 分支都有可审计、可验收的产品化路径。**

---

## 1. Analyzer 复核结果

对 `runtime/agentic_runs/v070_smoke_8dea5635` 运行:

```text
python scripts/analyze_agentic_run.py runtime/agentic_runs/v070_smoke_8dea5635
```

得到关键指标:

| 指标 | 结果 | 评审 |
|---|---:|---|
| turns | 20 | 通过 |
| errors | 0 | 通过 |
| source: director | 15 | 正常 |
| source: fallback | 1 | 达标,但与 smoke log 口径不一致 |
| source: absence_response | 2 | 通过 |
| source: deterministic_movement | 2 | 通过 |
| validator accepted_turns | 19 | 有 1 turn rejected |
| validator downgraded_turns | 1 | 通过 |
| validator rejected_turns | 1 | 不应从验收表中省略 |
| downgrade_records | 2 | 可接受 |
| post_render pass | 20 | 表面通过,但覆盖范围不足 |
| post_render repaired | 0 | repair loop 未被真实触发 |
| post_render failed | 0 | 通过 |
| repair_attempts | 0 | 未证明 repair loop |
| L2 judgments_run | 6 | 偏少,需要解释触发策略 |
| L2 hard_rejects | 0 | 通过 |
| hidden_truth_nonpass | 0 | 通过 |
| unique_canonical_engaged | 3 | 通过 |
| invalid_hook_ids | [] | 通过 |
| unique motifs used | 3 | 通过 |
| longest_no_motif_streak | 3 | 达标边界 |
| move_player_missing_destination | 0 | 通过 |
| unresolved_turns | 0 | 通过 |
| absent_target_turns | 7 | 需要继续区分 absent/unreachable/route |

Analyzer 输出:

```text
[OK] All invariants passed.
```

这个结论在 **当前 analyzer invariant 定义内** 是成立的。

但 review 必须补一句:

```text
All invariants passed != all semantic quality passed。
当前 invariant 没有覆盖 "prose 是否回应当前 player_input"。
```

---

## 2. 已经符合预期的部分

### 2.1 v0.7.2.1 的结构漏洞没有回归

v0.7.3 继续保持:

```text
move_player_missing_destination = 0
invalid_hook_ids = []
hidden_truth_nonpass = 0
unrepaired_l2_rejects = 0
errors = 0
```

这说明 v0.7.2.1 做的 correctness repair 没有被 v0.7.3 新功能破坏。

### 2.2 deterministic movement 方向正确

20-turn 中有 2 个 deterministic movement:

```text
Turn 6: 我回到入口厅。 -> entrance_hall
Turn 12: 我沿着积水阶梯往下走。 -> flooded_stair
```

这条路径正确:

```text
简单合法移动不需要 Director。
能用代码提交的状态变更,不应交给 LLM 输出 JSON。
```

它带来两个收益:

- 降低 fallback 面积。
- 降低平均延迟。

v0.7.4 应继续扩大 deterministic branch,但要避免把复杂路径规划硬塞进同一分支。

### 2.3 absence_response 已经产品化

Turn 11 / Turn 19 都触发:

```text
source: absence_response
reason: alen not in visible_entities
```

这比 v0.7.2 阶段只在 report 中声称触发要可靠得多。

这条路径是对的:

```text
不在场 NPC -> 不调用 Director 硬编对话 -> 返回可解释的缺席响应。
```

### 2.4 hidden-truth symbolic hint policy 有效

v0.7.2.1 的 Turn 4 问题是:

```text
三道划痕 + 门 + 等待回应
```

会和 hidden truth:

```text
three-note bell sequence opens lower vault door
```

形成过强 symbolic bridge。

v0.7.3 中:

```text
hidden_truth_nonpass = 0
```

说明 `symbolic_risk_patterns` 和 `safe_hint_boundary` 的方向是有效的。

这里特别重要的是:

```text
不是把 "三/three" 做成关键词禁用。
而是判断 "三 + 门/机制 + 回应/声音" 这个语义组合是否越界。
```

这符合项目从关键词约束转向语义约束的核心预期。

### 2.5 wall time 改善明显

v0.7.2.1:

```text
avg wall time = 21.64s
```

v0.7.3:

```text
avg wall time = 17.09s
```

这说明:

```text
能确定性处理的 turn 绕过 Director
不在场响应绕过 Director
repair loop 没被触发
```

三者共同降低了延迟。

但这也意味着:

```text
当前性能数字没有覆盖 repair loop 真正触发时的成本。
```

---

## 3. 不能放过的问题

## 3.1 Turn 5 是当前最大语义漏洞

玩家输入:

```text
我搜索旧卫兵室。
```

resolved intent:

```json
{
  "action_type": "ambiguous",
  "targets": [
    {
      "mention": "卫兵室",
      "canonical_id": "old_guardroom",
      "kind": "location",
      "confidence": 0.85,
      "available": false
    }
  ]
}
```

Director 原始意图其实合理:

```text
The area around the sealed lower door is bare stone; there is no guardroom here.
Player attempts to search a non-existent location.
```

但 validator 因为:

```text
observe_reaction for absent entity: environment
```

拒绝 transaction,随后 fallback。

最终玩家输出却是:

```text
你蹲在密封的下层门前...
发力...门纹丝不动...
这扇门不打算让路...
```

问题:

```text
这个输出没有回应 "搜索旧卫兵室"。
它像是复用了前一轮 "推门" 的叙事惯性。
Post-render checker 仍然判定 pass。
```

这说明当前 L2/Post-render 缺一个关键 judge:

```text
Intent Fulfillment Judge
```

它要判断:

```text
最终 prose 是否忠实表达了:
  player_input
  resolved_intent
  validated transaction
  当前 turn 的 source
```

如果没有这个 judge,系统会出现一种很危险的假绿:

```text
没有泄露 hidden truth
没有 NPC 内心独白
没有 unsupported canon
但它回答错了玩家这回合在做什么。
```

这对可玩性是致命的。

## 3.2 `rejected_turns = 1` 不应被验收表淡化

报告中 acceptance table 没有直接列:

```text
validator rejected_turns = 1
```

而 analyzer 明确显示:

```text
accepted_turns = 19
rejected_turns = 1
```

报告解释说:

```text
environment pseudo-entity 已 surgical fix,并跑了 5-turn retest。
```

这个解释可以接受为 root-cause note,但不能替代完整验收。

正式口径应是:

```text
v0.7.3 run v070_smoke_8dea5635 中仍有 1 个历史 rejected turn。
若代码已经修复,必须重新跑完整 20-turn,生成新的 run id 和 report。
```

否则 report 会形成一个坏习惯:

```text
20-turn 失败点用 5-turn retest 抵消。
```

这会削弱 artifact-as-truth 的纪律。

## 3.3 fallback 统计口径不统一

Analyzer:

```text
source: fallback = 1
```

Smoke log final summary:

```text
Fallbacks: 2
```

差异来自:

```text
Turn 5: Validation rejected original transaction -> fallback transaction
Turn 16: Director schema parse failed after retries -> fallback transaction
```

Analyzer source fallback 更像是在统计某类 source,而 smoke log 在统计实际 fallback 次数。

v0.7.4 必须拆开:

```text
director_schema_fallback_count
validation_rejection_fallback_count
system_safe_fallback_count
total_fallback_count
```

否则每次 report 都会在 "fallback 到底几个" 这个问题上产生歧义。

## 3.4 repair loop 没有被真实证明

v0.7.3 新增 repair loop,但当前 run:

```text
repair_attempts = 0
repaired = 0
failed = 0
```

这说明:

```text
这次 20-turn 没有失败需要 repair。
```

这不是坏事,但不能证明 repair loop 在真实坏输出下能工作。

v0.7.4 至少需要 targeted test:

```text
给 checker 一个包含 absent NPC / hidden truth symbolic bridge / unsupported spatial claim 的坏 prose。
确认 repair brief 生成。
确认 Flash repair 后 re-check pass。
确认无法修复时 fail closed。
```

## 3.5 Turn 16 暴露 route/unreachable handling 缺口

Turn 16:

```text
我回到封闭下层门。
```

resolved intent:

```json
{
  "action_type": "move",
  "targets": [
    {
      "canonical_id": "sealed_lower_door",
      "kind": "location",
      "available": false
    }
  ]
}
```

最终:

```text
source: fallback
reason: Director schema parse failed after retries
```

这在指标上可接受,但产品路径不理想。

如果目标地点在世界图中存在但当前不可达,系统不应走泛化 fallback。应有明确分支:

```text
unreachable_location_response
```

或:

```text
route_planner
```

区别:

```text
absent_entity: NPC/实体不在场
unreachable_location: 地点存在,但不在当前 reachable set
unknown_target: 无法解析
ambiguous_target: 多个候选冲突
```

这四类不应混在 fallback 里。

---

## 4. v0.7.4 核心命题

v0.7.4 的核心命题:

> **把 0.7.3 的 artifact invariant 全绿推进到 player-intent semantic correctness: 最终输出必须回应本回合玩家意图,所有无法执行的意图必须走明确、可审计、非 fallback 的拒绝/导航路径。**

换句话说:

```text
v0.7.3 证明了系统可以不泄露、不污染、不崩。
v0.7.4 要证明系统能正确回答玩家这回合到底做了什么。
```

---

## 5. v0.7.4 具体规划

## Phase 0 - Clean 0.7.3 Re-run Before New Features

目标:

```text
确认 environment pseudo-entity 修复已经进入完整 20-turn,而不是只通过 5-turn retest。
```

Deliverables:

- 重新运行完整:

```text
python scripts/agentic_dungeon_smoke_test.py --extended
```

- 生成新 run id。
- 用 analyzer 生成 report patch 或 `reportVer0.7.3.1.md`。

验收:

```text
errors = 0
validator rejected_turns = 0
move_player_missing_destination = 0
invalid_active_hook_ids = 0
hidden_truth_nonpass = 0
unrepaired_l2_rejects = 0
```

如果这一步不过,不要开始 v0.7.4 功能扩展。

## Phase 1 - Metrics Taxonomy / Analyzer Contract

目标:

```text
统一 report、analyzer、smoke log 对 fallback/reject/repair 的定义。
```

新增或拆分指标:

```text
director_schema_fallback_count
validation_rejection_fallback_count
system_safe_fallback_count
total_fallback_count

validator_rejected_turns
validator_rejected_then_safe_output_count

post_render_initial_pass
post_render_initial_failed
repair_attempts
repair_success
post_render_final_pass
post_render_final_failed

intent_fulfillment_pass
intent_fulfillment_downgrade
intent_fulfillment_reject
```

规则:

```text
source count 不能替代 total fallback count。
report 中所有指标必须来自 analyzer JSON。
smoke log final summary 必须复用 analyzer 计算,不能各算各的。
```

Deliverables:

- `scripts/analyze_agentic_run.py` 更新。
- `scripts/agentic_dungeon_smoke_test.py` final summary 改为引用 analyzer-style counters。
- tests:
  - `test_analyzer_counts_validation_rejection_fallback`
  - `test_analyzer_total_fallback_equals_component_sum`
  - `test_smoke_summary_matches_analyzer_json`

验收:

```text
report/analyzer/smoke summary mismatch = 0
total_fallback_count = director_schema + validation_rejection + system_safe
```

## Phase 2 - Intent Fulfillment Judge

目标:

```text
Post-render 不只检查 "有没有泄露/越界",还要检查 "有没有回答本回合玩家意图"。
```

新增函数:

```python
judge_intent_fulfillment(
    player_input: str,
    resolved_intent: ReferenceResolution,
    transaction: TurnTransaction,
    render_brief: RenderBrief,
    prose: str,
) -> SemanticJudgment
```

输出 schema:

```python
SemanticJudgment(
  verdict: Literal["pass", "downgrade", "reject"],
  category: Literal[
    "intent_fulfilled",
    "wrong_action",
    "wrong_target",
    "stale_context",
    "unsupported_continuation",
    "missing_refusal",
    "over_answered"
  ],
  evidence: str,
  suggested_downgrade: str | None,
  confidence: float
)
```

判定原则:

```text
pass:
  prose 明确回应本 turn 玩家动作,且不违背 transaction。

downgrade:
  prose 回应了大方向,但混入少量旧上下文或目标不够清晰。

reject:
  prose 主要描写了错误动作/错误对象/旧 turn 事件。
  prose 把无法执行的动作写成已经执行。
  prose 对 absent/unreachable target 没有给出缺席/不可达响应。
```

Turn 5 应成为回归用例:

```text
player_input: 我搜索旧卫兵室。
bad prose: 你蹲在密封的下层门前...发力...门纹丝不动...
expected: reject / wrong_target or stale_context
```

Deliverables:

- `semantic_judge.py`: 新增 `judge_intent_fulfillment()`。
- `post_render_checker.py`: 在 hidden truth / support / NPC mind 之后调用。
- `runner.py`: intent reject -> repair loop,repair 失败则 safe response。
- tests:
  - `test_intent_fulfillment_rejects_stale_door_prose_for_guardroom_search`
  - `test_intent_fulfillment_passes_absence_response`
  - `test_intent_fulfillment_passes_deterministic_movement`
  - `test_intent_fulfillment_rejects_wrong_target`

验收:

```text
intent_fulfillment_reject_after_repair = 0
Turn 5 类错误不能 pass
post_render pass 不再只代表 hygiene pass,而代表 semantic response pass
```

## Phase 3 - Current-Turn Render Contract

目标:

```text
让 Renderer 明确知道 "这一 turn 必须渲染什么",避免从历史 committed_events 中惯性续写。
```

RenderBrief 新增字段:

```python
current_turn_obligation: {
  "player_input": str,
  "action_type": str,
  "target_ids": list[str],
  "source": str,
  "must_address": list[str],
  "must_not_claim": list[str],
  "response_mode": Literal[
    "normal_resolution",
    "absence_response",
    "unreachable_response",
    "deterministic_movement",
    "safe_fallback"
  ]
}
```

构建规则:

```text
如果 target.available = false:
  must_address 包含 "目标不可用/不在当前可达范围"

如果 source = fallback:
  must_address 包含 "承认动作无法推进或只给 minimal texture"
  must_not_claim 包含 "不要渲染前一 turn 的动作成功"

如果 deterministic_movement:
  must_address 包含 "玩家移动到 destination"

如果 absence_response:
  must_address 包含 "目标 NPC 不在场"
```

Renderer prompt:

```text
The current turn obligation is higher priority than historical context.
Do not render a previous turn's action as if it is the current action.
If response_mode is absence/unreachable/safe_fallback, keep output short and grounded.
```

Deliverables:

- `transaction.py`: `RenderBrief.current_turn_obligation`。
- `render_brief.py`: obligation builder。
- `renderer_agent.py`: prompt 使用 obligation。
- tests:
  - `test_render_brief_current_turn_obligation_for_unavailable_location`
  - `test_renderer_prompt_prioritizes_current_turn`
  - `test_fallback_render_brief_does_not_replay_previous_turn`

验收:

```text
stale_context intent rejects = 0 after repair
fallback output 不再复用上一轮动作
```

## Phase 4 - Unreachable Location Response / Minimal Route Layer

目标:

```text
Turn 16 不再进入泛化 fallback。
```

先做轻量分支,不要上复杂 pathfinding:

```text
if resolved target is known location and available == false:
  if target exists in world graph but not reachable from current location:
      source = unreachable_location_response
  else:
      source = unknown_or_absent_location_response
```

输出 transaction:

```python
TurnTransaction(
  operations=[
    Operation("add_texture", {
      "text": "你辨认出方向,但从这里不能直接回到那扇门。"
    }),
    Operation("add_event", {
      "summary": "Player attempts to move toward an unreachable location."
    })
  ],
  commitments=[
    Commitment("utterance", "Target location is not directly reachable from current location.", 0)
  ],
  assumptions=[
    {"source": "unreachable_location_response", "target": target_id}
  ]
)
```

可选增强:

```text
如果 world graph 能找到 1-hop/2-hop route:
  给出方向 hint,但不自动移动多步。
```

不要在 v0.7.4 做:

```text
自动多步 path execution
复杂导航 AI
动态地图重写
```

Deliverables:

- `runner.py`: `unreachable_location_response` branch。
- `reference_resolver.py`: 区分 `available=false` 的原因。
- `scripts/analyze_agentic_run.py`: source 增加 `unreachable_location_response`。
- tests:
  - `test_known_unreachable_location_returns_unreachable_response`
  - `test_turn16_no_director_fallback_for_unreachable_door`
  - `test_unreachable_response_does_not_move_player`

验收:

```text
Turn 16 不再 source=fallback
director_schema_fallback_count = 0 或 <=1
total_fallback_count <=1
unreachable_location_response >=1 if script keeps Turn 16
```

## Phase 5 - Repair Loop Targeted Proof

目标:

```text
不要等 live 20-turn 碰巧产生坏输出,主动证明 repair loop 可用。
```

增加 targeted fixtures:

1. Stale context:

```text
input: 搜索旧卫兵室
bad prose: 推密封下层门
expected: intent reject -> repair -> prose mentions guardroom unavailable/current location
```

2. Hidden truth symbolic bridge:

```text
bad prose: 三道痕迹像在等待某个声音回应
expected: hidden truth downgrade/reject -> repair removes bridge
```

3. Absent NPC:

```text
bad prose: Alen 在你身后低声说...
world: Alen absent
expected: support reject -> repair removes Alen presence
```

4. Repair impossible:

```text
repair returns still-bad prose
expected: final failed or safe fallback,not pass
```

Deliverables:

- `tests/test_render_repair_targeted.py`
- `tests/fixtures/bad_prose_cases/*.json`
- analyzer fields:
  - `targeted_repair_cases`
  - `targeted_repair_pass`

验收:

```text
targeted repair tests pass
repair_success >= 1 in targeted suite
final failed never counted as pass
```

## Phase 6 - v0.7.4 Revalidation

20-turn 验收目标:

| 指标 | v0.7.3 | v0.7.4 目标 |
|---|---:|---:|
| errors | 0 | 0 |
| report/analyzer/smoke mismatch | 未完全统一 | 0 |
| validator rejected_turns | 1 | 0 |
| move_player_missing_destination | 0 | 0 |
| invalid_active_hook_ids | 0 | 0 |
| director_schema_fallback_count | 1 | 0 或 <=1 |
| validation_rejection_fallback_count | 1 | 0 |
| total_fallback_count | 2 in smoke log | <=1 |
| absence_response | 2 | >=1 |
| deterministic_movement | 2 | >=2 |
| unreachable_location_response | 0 | >=1 if Turn 16 retained |
| post_render final_failed | 0 | 0 |
| intent_fulfillment_reject_after_repair | 未统计 | 0 |
| hidden_truth_nonpass_after_repair | 0 | 0 |
| unrepaired_l2_rejects | 0 | 0 |
| repair_attempts | 0 | >=1 in targeted repair suite |
| canonical unique hooks engaged | 3 | >=3 |
| longest no-motif streak | 3 | <=3 |
| avg wall time | 17.09s | <=24s |

Deliverables:

- `docs/plans/planVer0.7.4.md`
- `docs/reports/reportVer0.7.4.md`
- updated analyzer JSON excerpt embedded in report
- targeted repair test report section

---

## 6. v0.7.4 明确不做的事

不建议在 v0.7.4 做:

- 不新增复杂 NPC AI。
- 不做自动多步 pathfinding 和地图导航系统。
- 不为了降低 rejected_turns 而放松 Validator。
- 不为了让 post-render pass 而降低 SemanticJudge 严格度。
- 不把 intent fulfillment 做成关键词匹配。
- 不继续扩大 hidden truth alias/keyword 表。
- 不把 5-turn retest 当成 20-turn 验收替代。

---

## 7. 最终评价

v0.7.3 是一个重要进展。

它把 v0.7.2.1 的:

```text
结构正确,但语义质量门仍失败
```

推进到:

```text
结构 invariant 全绿,hidden truth/spatial hard reject 当前清零
```

这说明 L1/L2/L3 的方向是可落地的。

但 v0.7.3 也暴露了下一层核心问题:

```text
一个输出可以不泄露、不越界、不崩溃,
但仍然没有回答玩家这回合的动作。
```

这正是 MetaRPG 要做成 playable narrative system 时必须补上的语义约束。

一句话结论:

```text
v0.7.3 可以归档为 artifact invariant baseline。
v0.7.4 必须补 Intent Fulfillment Judge、Current-Turn Render Contract、Unreachable Location Response 和 Repair Loop Targeted Proof。
否则项目会停留在"能避免明显违规",但还不能稳定做到"正确回应玩家行动"。
```
