# MetaRPG v0.7.5 Simplified Mainline Plan

日期: 2026-05-20

来源:

- `docs/Opus/report_all_plan.md`
- `docs/Opus/report_rearch.md`
- `docs/reviews/reviewVer0.7.4.md`
- 真实体验 run: `runtime/agentic_runs/play_5d739e09/`

---

## 0. 版本定位

v0.7.5 不扩内容、不做代码大重构、不做新玩法。

这一版只解决一个问题:

> v0.7.4 的 smoke 指标已经能绿,但该跑的语义检查没有全部跑到,真实 play run 的 scorecard 也会掩盖 fallback、连续性、hidden truth 边界和 soft audit 未修复问题。

因此 v0.7.5 的目标不是宣传式的 "semantic closure",而是更具体的:

```text
Semantic Coverage Closure + Play Experience Gates
```

也就是:

```text
高风险 turn 必须被检查。
检查必须能产出稳定 diagnostic。
diagnostic 必须能进入 repair / fail-closed。
smoke 和 play 两条线都不能靠乐观分数过关。
```

---

## 1. 保留不变的主架构

v0.7.5 继续沿用 v0.7.0 以来的主线:

```text
Narrative Grammar
  -> NarrativeFrame
  -> Director 生成 TurnTransaction
  -> Validator 接受 / 降级 / 拒绝
  -> Committer 写 WorldGraph
  -> DeepSeek Flash Renderer 输出玩家文本
  -> Post-render Checker + SemanticJudge
  -> Repair / fail-closed
```

约束分层仍然是:

```text
L0 deterministic hard constraints
L1 reference resolution
L2 semantic policy judge
L3 hygiene scan
```

模型路由不变:

```text
DeepSeek Flash: Renderer / Render repair only
local vLLM: Director / Feasibility / ReferenceResolver fallback / SemanticJudge
配置来源: set.env
```

---

## 2. v0.7.5 必须修的核心问题

### H1 - L2 required coverage 不完整

v0.7.4 中 Turn 16 / 17 / 20 是高风险 turn,但 `l2_ran=false`。

要修:

```text
l2_required_turns
l2_ran_turns
l2_required_but_not_run_count
l2_required_but_not_run_turns
```

验收:

```text
l2_required_but_not_run_count = 0
```

### H2 - Unreachable response prose 自相矛盾

v0.7.4 中 `unreachable_location_response` 的 contract 明确:

```text
不要渲染玩家已成功到达该地点
```

但 prose 写成玩家已经回到门前、触摸/推动门。

要修:

```text
response_mode=unreachable 必须跑 intent_fulfillment
must_not_claim 必须被 SemanticJudge 执行
到达 / 触摸 / 推动 unreachable target => reject
```

验收:

```text
unreachable_response_contradiction_count = 0
```

### H3 - Absent NPC reaction 被 Validator 接受

v0.7.4 中 Turn 14 / 20 出现:

```text
visible_entity_ids = ["player"]
observe_reaction(entity="alen")
Validator accepted
```

要修:

```text
speak / observe_reaction 的 entity 必须在 visible_entity_ids
允许伪实体仅 player / environment
belief_evidence 若绑定 absent entity,必须 reject / downgrade / remove
```

验收:

```text
accepted_absent_entity_reaction_count = 0
accepted_absent_entity_speech_count = 0
```

### H4 - Entity / Object 类型边界混乱

v0.7.4 中 `black_ash` 进入 `visible_entities`,并被 Renderer 写成一个人。

要修:

```text
visible_entities: 只允许 NPC / actor
visible_objects: item / prop / inanimate object
at(item, location) 只能支持 object presence,不能支持 character agency
```

验收:

```text
object_as_visible_entity_count = 0
object_personification_claim_count = 0
```

### H5 - Play runner 真实体验门缺失

`play_5d739e09` 暴露:

```text
fallback turn 可以拿满分
第二人称突然切第一人称
喝过的麦酒被说成没碰
hidden truth 同时进入 public facts
soft audit 发现 too_mechanical 但 rewrite_history=0
```

要修:

```text
新增 analyze_play_run.py
play summary 不再只看 scorecard 自评
fallback / continuity / hidden truth / soft audit 必须进入验收
```

验收:

```text
fallback_full_score_count = 0
perspective_shift_count = 0
state_continuity_issue_count = 0
hidden_public_fact_overlap_count = 0
hidden_truth_semantic_reveal_count = 0
soft_audit_unrepaired_count = 0
play_scorecard_overoptimism_count = 0
```

---

## 3. Stable Diagnostics

v0.7.5 开始,新增问题不要只写自然语言 issue,而要有稳定 diagnostic code。

建议最小集合:

```text
METARPG_L2_REQUIRED_NOT_RUN
METARPG_UNREACHABLE_TARGET_CLAIMED_REACHED
METARPG_ABSENT_ENTITY_REACTION_ACCEPTED
METARPG_ABSENT_ENTITY_SPEECH_ACCEPTED
METARPG_OBJECT_AS_ENTITY
METARPG_OBJECT_PERSONIFIED
METARPG_HIDDEN_PUBLIC_FACT_OVERLAP
METARPG_HIDDEN_TRUTH_SEMANTIC_REVEAL
METARPG_FALLBACK_FULL_SCORE
METARPG_PERSPECTIVE_SHIFT
METARPG_STATE_CONTINUITY_BREAK
METARPG_SOFT_AUDIT_UNREPAIRED
```

每个 diagnostic 至少包含:

```text
code
severity
turn
evidence
source_artifact
repair_hint
```

这是后续向 "narrative compiler" 方向走的基础。

---

## 4. Phase 计划

### Phase 1 - Analyzer Contract

目标:

```text
先让问题可计算、可审计。
```

Deliverables:

- `scripts/analyze_agentic_run.py` 增加 L2 required / unreachable / absent entity / object type 指标。
- 新增 `scripts/analyze_play_run.py`,支持 `turn_001.json + scorecard_001.json` 格式。
- smoke summary / report 必须引用 analyzer JSON,不能手填。

验收:

```text
analyzer 能在 v0.7.4 artifact 上重算出已知问题:
  accepted_absent_entity_reaction_count >= 2
  object_as_visible_entity_count >= 1
  unreachable_response_contradiction_count >= 2

play analyzer 能在 play_5d739e09 上重算出:
  fallback_full_score_count >= 1
  perspective_shift_count >= 1
  state_continuity_issue_count >= 1
  hidden_public_fact_overlap_count >= 1
  soft_audit_unrepaired_count >= 1
```

### Phase 2 - L2 Required Matrix

目标:

```text
该跑 L2 的 turn 必须跑。
```

必跑条件:

```text
response_mode in {"unreachable", "absence", "fallback", "safe_fallback"}
must_not_claim 非空
tx.operations 包含 speak / observe_reaction
resolved target available=false
candidate_hints 命中 hidden_truth symbolic risk
post_render status = repaired
```

验收:

```text
l2_required_but_not_run_count = 0
```

### Phase 3 - Transaction Hardening

目标:

```text
错误事实不能进入 accepted transaction。
```

修复:

- `observe_reaction` / `speak` 使用 `visible_entity_ids` 作为真源。
- `player` / `environment` 是唯一默认伪实体。
- absent NPC 的 belief / relation / reaction 不得 accepted。
- `visible_entities` / `visible_objects` 强类型分离。

验收:

```text
accepted_absent_entity_reaction_count = 0
object_as_visible_entity_count = 0
```

### Phase 4 - Render / Intent Enforcement

目标:

```text
Renderer 不能违反 current-turn obligation。
```

修复:

- `judge_intent_fulfillment()` 读取 `must_not_claim`。
- unreachable 几类坏句必须 reject:
  - 已经到达 unreachable target
  - 触摸 unreachable target
  - 推动 unreachable target
- Renderer prompt 加 BAD / GOOD few-shot。
- object 不能人格化。

验收:

```text
unreachable_response_contradiction_count = 0
object_personification_claim_count = 0
```

### Phase 5 - Play Experience Gates

目标:

```text
真实 play run 不再被乐观 scorecard 掩盖。
```

修复:

- fallback 不能拿满分,必须跑 intent / perspective / continuity。
- 默认叙事视角为第二人称,第一人称切换必须报 issue。
- continuity judge 追踪最近状态:
  - drank / untouched
  - moved / still here
  - acquired / absent
- hidden truth 不得同时进入 public facts。
- soft audit failed 必须进入 editor rewrite 一轮,或明确 counted as unrepaired。

验收:

```text
fallback_full_score_count = 0
perspective_shift_count = 0
state_continuity_issue_count = 0
hidden_public_fact_overlap_count = 0
soft_audit_unrepaired_count = 0
```

### Phase 6 - Targeted Repair Proof

目标:

```text
不要只靠 live run 碰巧触发。
```

新增 fixtures:

```text
bad_prose_unreachable_arrival.json
bad_prose_absent_npc_present.json
bad_prose_object_personified.json
bad_play_fallback_inner_monologue.json
bad_play_hidden_public_fact_overlap.json
bad_play_state_continuity_break.json
```

验收:

```text
targeted repair_success >= 1
repair impossible 必须 fail-closed,不能算 pass
```

### Phase 7 - Revalidation

必须跑:

```text
20-turn Ashen Vault smoke
5-turn Greyfen play run
targeted repair suite
full relevant pytest subset
```

---

## 5. 验收表

| 指标 | v0.7.5 目标 |
|---|---:|
| errors | 0 |
| total_fallback_count | 0 |
| validator rejected_turns | 0 |
| move_player_missing_destination | 0 |
| invalid_active_hook_ids | [] |
| l2_required_but_not_run_count | 0 |
| accepted_absent_entity_reaction_count | 0 |
| accepted_absent_entity_speech_count | 0 |
| object_as_visible_entity_count | 0 |
| object_personification_claim_count | 0 |
| unreachable_response_contradiction_count | 0 |
| hidden_truth_nonpass_after_repair | 0 |
| unrepaired_l2_rejects | 0 |
| final_failed | 0 |
| fallback_full_score_count | 0 |
| perspective_shift_count | 0 |
| state_continuity_issue_count | 0 |
| hidden_public_fact_overlap_count | 0 |
| hidden_truth_semantic_reveal_count | 0 |
| soft_audit_unrepaired_count | 0 |
| play_scorecard_overoptimism_count | 0 |
| repair_attempts | >=1 live or targeted |
| avg smoke wall time | <=24s |

---

## 6. 明确不做

v0.7.5 不做:

- 不做代码结构大重构。
- 不物理拆包。
- 不做 NPC AI。
- 不做 move_entity / NPC follow。
- 不做多步 pathfinding。
- 不扩 hook / motif / seed 内容。
- 不用关键词替代语义判断。
- 不放松 Validator / SemanticJudge 换指标。
- 不把 repaired/light_repair 当原始 pass。

---

## 7. 完成后进入下一步

v0.7.5 完成并通过 smoke + play + targeted suite 后,再推进代码结构重构。

重构前提:

```text
当前行为已稳定
diagnostic 已可审计
play 与 smoke 入口事实已明确
```
