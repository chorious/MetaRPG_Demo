# reviewVer0.7.2 - 可观测性进步,但不能验收为 Semantic Layer Completion

日期: 2026-05-19

评审范围:

- `docs/reports/reportVer0.7.2.md`
- `runtime/agentic_runs/v070_smoke_9d1b9af2/`
- v0.7.2 相关主链路:
  - `metarpg/agentic/runner.py`
  - `metarpg/agentic/reference_resolver.py`
  - `metarpg/agentic/hook_manager.py`
  - `metarpg/agentic/director_agent.py`
  - `metarpg/agentic/transaction_validator.py`
  - `metarpg/agentic/committer.py`
  - `metarpg/agentic/post_render_checker.py`

---

## 0. 总体结论

v0.7.2 **不能按 "Semantic Layer Completion" 验收**。

这次版本有一个真实进步:

```text
per-turn artifact 大量落盘,终于可以审计每个 turn 的 resolved_intent / frame / transaction / render_brief / post_render / semantic_judgments。
```

但正因为 artifact 足够多,它暴露出 report 结论与 runtime 事实不一致:

```text
report 的多项核心指标不是从 artifact/events 自动重算出来的。
实际 run 显示: move_player schema 有 no-op bug, absence_response 没触发, hook active list 被 semantic category 污染,
post-render L2 大量 reject, validator downgrade 仍很多。
```

所以本 review 的判断是:

```text
v0.7.2 可作为 observability + L2 detector integration 的中间版本。
v0.7.2 不可声明语义约束层闭环完成。
下一步应推进 v0.7.2.1 修复版,目标是修正结构性 bug 和指标口径,不是继续加新功能。
```

---

## 1. Artifact 重算结果

基于 `runtime/agentic_runs/v070_smoke_9d1b9af2/` 的 artifact/events 重算:

| 指标 | report 写法 | artifact/events 实际 | 评审 |
|---|---:|---:|---|
| errors | 0 | 0 | 通过 |
| post-render | 18 pass / 2 light_repair | 5 pass / 15 light_repair | report 错 |
| validator downgrade | 1 | 6 个 turn downgraded,9 条 downgrade record | report 错 |
| Director fallback | 2 | artifact 中 1 个 `source:fallback` | 口径不一致 |
| absence/input guard | 2 | 0 | report 错 |
| move_player missing destination | 未列 | 2 | 严重 bug |
| L2 checks | 3 | 19/20 有 semantic judgments | report 错 |
| hidden truth non-pass | 0 | 3 | report 错 |
| unsupported claim rejects | 未列 | 14 | 严重质量问题 |
| invalid active hook ids | 未列 | 5 类非法 hook id | 严重 bug |

非法 active hook id 包括:

```text
investigation
environmental_mystery
location_access
objective_barrier
environmental
```

这些不是 seed 中的 canonical hook id。它们不应出现在 `NarrativeFrame.active_hooks` 中,更不能被计入 "unique hooks engaged"。

---

## 2. 已经做对的部分

### 2.1 Artifact 可观测性明显改善

每 turn 现在基本都有:

- `artifact_XXX_resolved_intent.json`
- `artifact_XXX_narrative_frame.json`
- `artifact_XXX_transaction_raw.json`
- `artifact_XXX_transaction_validated.json`
- `artifact_XXX_render_brief.json`
- `artifact_XXX_semantic_judgments.json`
- `artifact_XXX_post_render.json`
- `artifact_XXX_motif_schedule.json`

这是 v0.7.2 最重要的正向成果。

以前 review 很多判断只能依赖 report 摘要。现在可以从 artifact 直接追踪:

```text
玩家输入 -> 解析结果 -> frame -> Director 输出 -> Validator 处理 -> Commit -> Render -> L2 checker
```

这个方向必须保留。

### 2.2 L2 SemanticJudge 确实开始进入 post-render

v0.7.1 的问题是 `semantic_judge.py` 存在,但主链路基本没用。

v0.7.2 中 `artifact_XXX_semantic_judgments.json` 显示 L2 已经真实运行,并且能抓到:

- unsupported entity/action
- spatial inconsistency
- location mismatch
- unsupported character state
- hidden-truth atmospheric allusion
- mechanic hint 过强

这说明 L2 方向正确。

但注意:

```text
L2 能抓到问题,不等于系统已经处理了问题。
当前大量 L2 reject 只是进入 light_repair 记录,并没有形成有效 repair/gating。
```

---

## 3. 阻断验收的问题

## 3.1 move_player schema no-op bug

artifact 显示至少两个 turn 的 `move_player` 使用了:

```json
{"target": "sealed_lower_door"}
{"target": "flooded_stair"}
```

而不是:

```json
{"destination": "sealed_lower_door"}
{"destination": "flooded_stair"}
```

当前代码路径:

- `committer.py` 只读 `params["destination"]`; 缺失则直接 return。
- `transaction_validator.py` 只在 `destination` 存在时检查 location; 缺失时不 hard_fail。
- `director_agent.py` 只 normalize `target_location -> destination`; 没有 normalize `target -> destination`。

结果:

```text
transaction 看起来发生了移动,
Validator 不报错,
Committer 实际不移动玩家,
后续 scene/visible_entities/reachable_locations 全部基于错误世界状态。
```

这直接 invalid 掉 v0.7.2 对 absence_response 的验证。

### v0.7.2.1 必须修复

1. `director_agent._parse_transaction()`:

```text
move_player.target_location -> destination
move_player.target -> destination
```

2. `transaction_validator._check_operation()`:

```text
move_player 缺 destination => hard_fail
move_player destination 不存在 => hard_fail
```

3. `committer._apply_operation()`:

```text
理论上不再收到缺 destination 的 move_player。
如果收到,记录 error 或 raise,不要静默 return。
```

4. 测试:

- `test_move_player_target_normalized_to_destination`
- `test_move_player_missing_destination_hard_fails`
- `test_move_player_commit_changes_player_location`

验收:

```text
20-turn artifact 中 move_player_missing_destination = 0
所有 move_player 要么产生 at(player,destination) delta,要么被 Validator rejected
```

---

## 3.2 Absence Response 没有被验证

report 写:

```text
Absence response = 2
```

artifact 实际:

```text
absence_response = 0
input_guard = 0
```

Turn 11 / Turn 19 中:

```text
resolved target: alen
available: true
visible_entity_ids: ["player", "alen"]
```

这说明 run 中系统认为 Alen 仍在场,所以 absence_response 根本没有被触发。

结合 3.1 的 move no-op bug,高概率是玩家移动状态没有正确提交,导致 scene 仍把 Alen 算作可见。

### v0.7.2.1 必须修复

不要只依赖 20-turn script 顺手覆盖。要增加一个定向测试:

```text
Given:
  player at flooded_stair
  alen at entrance_hall
When:
  player_input = "我问艾伦关于下层密室的事。"
Then:
  resolved_intent.targets[0].canonical_id == "alen"
  resolved_intent.targets[0].available == false
  runner emits source: absence_response transaction
  Director is not called
```

验收:

```text
targeted absence test 必须通过。
20-turn 中如果脚本确实制造了 absent target,则 artifact 必须出现 source:absence_response。
如果 20-turn 没制造 absent target,report 不得声称 Absence response = 2。
```

---

## 3.3 Semantic Hook Matching 污染 active_hooks

`hook_manager.py` 当前逻辑把 `SemanticJudgment.category` 当 hook id:

```python
semantic_judgments.append({
    "hook_id": j.category,
    ...
})
if j.verdict == "pass":
    matched.append(j.category)
```

这导致 active hooks 出现:

```text
investigation
environmental_mystery
location_access
objective_barrier
environmental
```

这些不是 `seed.active_hooks` 中的 id。

严重影响:

1. `Unique hooks engaged = 7` 是错算。
2. Director 看到非法 active hook,叙事 frame 被污染。
3. `dramatic_function` 被污染。
4. 后续 candidate hints / forbidden moves / hook status 判断都可能失真。

### v0.7.2.1 必须修复

正确做法:

```text
judge_hook_relevance 的每条 judgment 必须绑定真实 hook_id。
active_hooks 只能追加 seed.active_hooks 的 key。
semantic category 只能进入 evidence/category 字段,不能进入 active_hooks。
```

建议数据结构:

```python
HookRelevanceJudgment(
  hook_id: str,
  verdict: "pass" | "downgrade" | "reject",
  category: str,
  evidence: str,
  confidence: float,
)
```

如果暂时不改 dataclass,则 `hook_manager` 调用 judge 时必须保留输入 hook 顺序,并从 raw response 中读取 `hook_id`,不能用 `category` 代替。

验收:

```text
for every frame:
  set(frame.active_hooks) <= set(seed.active_hooks.keys())

20-turn invalid_active_hook_ids = 0
unique hooks engaged <= len(seed.active_hooks)
semantic_judgments 可以有 category,但 category 不得进入 active_hooks
```

---

## 3.4 L2 reject 没有形成真正闭环

artifact 显示:

```text
post_pass = 5
post_light_repair = 15
unsupported_claim_rejects = 14
hidden_truth_nonpass = 3
```

这说明 L2 Judge 不是没工作,而是工作后发现大量问题:

- Renderer 发明了门缝下有东西看着玩家。
- Renderer 发明了 Alen 持有短剑,但世界事实是 player 持有 short_sword。
- Renderer 发明了三道刻痕、铜铃震动、地下声响。
- Renderer 过强暗示 three-note bell sequence。
- Renderer 制造了 spatial/location mismatch。

这些不是小问题。它们正是我们想用 SemanticJudge 抓住的边界。

但当前系统只把它们标成 `light_repair`,report 还把整体 post-render 说成 18 pass / 2 repair。这在验收上是错误的。

### v0.7.2.1 必须修复

明确 post-render 状态语义:

```text
pass:
  L3 clean + L2 pass

light_repair:
  出现可修复问题,并且实际完成 repair 后再次检查通过

failed:
  L2 reject 或 hidden-truth non-pass 未被修复
```

最低限度:

```text
如果 L2 verdict == reject 且没有实际 repair pass,该 turn 不得计入 post-render pass。
```

v0.7.2.1 可以先不做复杂 rewrite,但必须改验收口径:

```text
unrepaired_l2_rejects = 0 才能 pass
```

更好的做法:

1. Renderer 输出后跑 checker。
2. 若 `render_claim_support: reject` 或 hidden exposure non-pass:
   - 生成 repair brief:
     - remove unsupported claims
     - preserve committed events only
     - forbid listed issue evidence
   - 调 Flash repair 一次。
3. 再跑 checker。
4. 仍 reject => turn failed,不能算 pass。

验收:

```text
unrepaired_l2_rejects = 0
hidden_truth_nonpass_after_repair = 0
post_render pass_after_repair >= 18/20
```

---

## 3.5 Validator downgrade 仍未达标

report 写:

```text
Downgrades = 1
```

artifact 实际:

```text
6 个 turn downgraded
9 条 downgrade record
```

其中一部分和 `move_player.target` no-op bug 相关。

例子:

```text
Turn 12:
move_player 使用 target=flooded_stair,没有 destination。
commitment 却写 canon: Player is now at flooded_stair。
Validator 因证据不足 downgrades。
```

这个不是 prompt 小问题,而是 schema/operation support 问题。

### v0.7.2.1 必须修复

在修复 move schema 后,再评估 canon prompt tuning 是否有效。

验收:

```text
downgraded_turns <= 2
downgrade_records <= 2
move/transfer/hook-status 对应的 canon commitment 能通过 operation-aware evidence check
```

---

## 3.6 Report 生成口径不可信

`reportVer0.7.2.md` 与 artifact 有多处硬矛盾:

- report: `Post-render: 18 pass, 2 light_repair`
- artifact/events: `5 pass, 15 light_repair`

- report: `Downgrades: 1`
- artifact: `6 downgraded turns, 9 records`

- report: `Absence response: 2`
- artifact: `0`

- report: `L2 semantic checks run: 3`
- artifact: `19/20 semantic_judgments non-empty`

这说明 report 不是由 runtime artifact 作为唯一真源自动生成的。

### v0.7.2.1 必须修复

增加或修改一个 run analyzer:

```text
scripts/analyze_agentic_run.py runtime/agentic_runs/<run_id>
```

它必须从 artifact/events 计算:

- turns
- errors
- fallback count
- absence_response count
- input_guard count
- move_player_missing_destination count
- validator accepted/downgraded/rejected
- downgrade record count
- post_render pass/light_repair/failed
- l2_judgment count
- l2 reject count
- hidden_truth non-pass count
- invalid_active_hook_ids
- unique canonical hooks engaged
- hook-bearing turns
- motifs used
- longest no-motif streak
- avg wall time from events

`docs/reports/reportVer0.7.2.1.md` 必须引用 analyzer output。手工 summary 可以写解释,但指标表不能手填。

验收:

```text
report metrics == analyze_agentic_run.py output
```

---

## 4. v0.7.2.1 推荐修复计划

v0.7.2.1 不应继续扩展叙事功能。它应该是一个 **correctness repair release**。

### Phase 0 - Artifact Analyzer

目标:

```text
建立 artifact 为唯一真源的指标计算。
```

交付:

- `scripts/analyze_agentic_run.py`
- 更新 smoke test 或 report 生成流程,自动打印 analyzer metrics

验收:

- report 数字与 artifact 重算一致
- analyzer 能检测 invalid hooks / move no-op / unrepaired L2 reject

### Phase 1 - Move Operation Schema Hardening

目标:

```text
消灭 move_player no-op。
```

交付:

- `target -> destination` normalization
- missing destination hard_fail
- committer 不静默吞掉 invalid move
- tests

验收:

- `move_player_missing_destination = 0`
- 移动 turn 改变 `at(player, location)`

### Phase 2 - Hook ID Integrity

目标:

```text
active_hooks 永远只含 canonical seed hook id。
```

交付:

- `judge_hook_relevance` 输出/消费真实 hook_id
- `NarrativeFrame.active_hooks` filter/guard
- tests

验收:

- `invalid_active_hook_ids = 0`
- `unique hooks engaged <= len(seed.active_hooks)`

### Phase 3 - Absence Response Targeted Test

目标:

```text
证明 known-but-unavailable target 能触发 absence_response。
```

交付:

- 构造 player/NPC 分离场景的单元/集成测试
- artifact 中记录 `source:absence_response`

验收:

- targeted absent NPC test pass
- Director 不被调用
- transaction source 是 `absence_response`

### Phase 4 - L2 Reject Gating / Repair

目标:

```text
L2 reject 不再被当成 pass。
```

交付:

- post-render status 区分 `pass / repaired / failed`
- repair once 或 fail closed
- report 统计 unrepaired rejects

验收:

- `unrepaired_l2_rejects = 0`
- `hidden_truth_nonpass_after_repair = 0`

### Phase 5 - Re-run 20-turn + reportVer0.7.2.1

目标:

```text
用 analyzer 生成可信报告。
```

验收表:

| 指标 | v0.7.2.1 目标 |
|---|---:|
| errors | 0 |
| report/analyzer mismatch | 0 |
| move_player_missing_destination | 0 |
| invalid_active_hook_ids | 0 |
| targeted absence_response test | pass |
| Director fallback | <=1/20 |
| validator downgraded turns | <=2 |
| downgrade records | <=2 |
| unrepaired_l2_rejects | 0 |
| hidden_truth_nonpass_after_repair | 0 |
| canonical unique hooks engaged | >=3 |
| longest no-motif streak | <=3 |
| avg wall time | <=22s |

---

## 5. 明确不建议做的事

v0.7.2.1 不建议:

- 继续增加更多 hook/hint/motif 规则。
- 用 NPC follow 掩盖 absence_response 问题。
- 把 `light_repair` 当 pass 统计。
- 把 SemanticJudge 的 category 当 hook id。
- 继续让 Validator 对缺字段 operation 宽容通过。
- 手工写 report 指标。
- 在 move no-op 未修前继续分析 Turn 11/19 的 absence 行为。

---

## 6. 最终评价

v0.7.2 的方向不是全错。它做成了两个重要基础:

1. artifact 可审计。
2. L2 SemanticJudge 开始真实暴露问题。

但这次 run 不能证明语义约束层完成。相反,它证明:

```text
结构化 transaction 层仍有 schema 漏洞。
语义 hook 层污染 canonical hook 集合。
absence_response 没有被真实验证。
post-render L2 已经抓到大量问题,但系统没有闭环处理。
report 指标没有以 artifact 为真源。
```

因此 v0.7.2.1 的核心命题应改为:

> **把 v0.7.2 暴露出来的结构正确性问题修掉,让 artifact、报告、世界状态和语义判断四者一致。**

只有 v0.7.2.1 达到上述验收后,才可以重新讨论:

```text
Semantic Constraint Layer 是否完成闭环。
```
