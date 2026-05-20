# reviewVer0.7.2.1 - Correctness Repair 基线通过,语义质量闭环仍未完成

日期: 2026-05-19

评审范围:

- `docs/reports/reportVer0.7.2.1.md`
- `docs/plans/planVer0.7.2.1.md`
- `runtime/agentic_runs/v070_smoke_29c558fb/`
- `scripts/analyze_agentic_run.py`
- v0.7.2.1 主链路修复:
  - `metarpg/agentic/director_agent.py`
  - `metarpg/agentic/transaction_validator.py`
  - `metarpg/agentic/committer.py`
  - `metarpg/agentic/semantic_judge.py`
  - `metarpg/agentic/hook_manager.py`
  - `metarpg/agentic/post_render_checker.py`
  - `metarpg/agentic/runner.py`

---

## 0. 总体结论

v0.7.2.1 可以验收为 **correctness repair baseline**。

它修掉了 v0.7.2 review 中最关键的结构性问题:

```text
move_player no-op: 已修
active_hooks 非 canonical 污染: 已修
absence_response 不可验证: 已修到可验证
report 指标非 artifact 真源: 已修
L2 reject 被混成 pass/light_repair: 已修成 pass/repaired/failed 三态
```

但 v0.7.2.1 **不能验收为 semantic quality 完成**,也不能说 Semantic Layer 已经闭环。

原因:

```text
analyzer --fail-on-invariant 仍失败:
  unrepaired_l2_rejects = 1
  hidden_truth_nonpass = 1

这两个不是报告 bug,而是真实语义质量门没有过。
```

因此本 review 的版本定性是:

```text
结构正确性: 通过
指标可信度: 通过
运行可审计性: 通过
语义质量闭环: 未通过
玩家可用 baseline: 谨慎可试,不建议宣称稳定 playable
```

v0.7.3 的重点不应继续补 artifact/schema,而应转向:

```text
movement deterministic
NPC spatial consistency
Renderer grounding
L2 repair loop
hidden-truth symbolic hint policy
```

---

## 1. Analyzer 复核结果

对 `runtime/agentic_runs/v070_smoke_29c558fb` 运行:

```text
python scripts/analyze_agentic_run.py runtime/agentic_runs/v070_smoke_29c558fb
```

得到的关键指标:

| 指标 | 结果 | 评审 |
|---|---:|---|
| turns | 20 | 通过 |
| errors | 0 | 通过 |
| source: director | 18 | 正常 |
| source: fallback | 1 | 达标,但仍需 v0.7.3 消除 |
| source: absence_response | 1 | 通过 |
| validator accepted_turns | 20 | 通过 |
| validator downgraded_turns | 1 | 通过 |
| downgrade_records | 1 | 通过 |
| post_render pass | 18 | 可接受 |
| post_render repaired | 0 | 说明还没有真实 repair loop |
| post_render failed | 2 | 可接受为 fail-closed,但不是质量通过 |
| L2 judgments_run | 10 | 通过 |
| L2 hard_rejects | 1 | 未闭环 |
| hidden_truth_nonpass | 1 | 未闭环 |
| unique_canonical_engaged | 3 | 通过 |
| invalid_hook_ids | [] | 通过 |
| unique motifs used | 3 | 通过 |
| longest_no_motif_streak | 3 | 通过 |
| move_player_missing_destination | 0 | 通过 |
| unresolved_turns | 0 | 通过 |
| absent_target_turns | 5 | 需要解释,但不阻断 |

对同一 run 运行:

```text
python scripts/analyze_agentic_run.py --fail-on-invariant runtime/agentic_runs/v070_smoke_29c558fb
```

仍会返回非零退出码,因为:

```text
!!! INVARIANT VIOLATIONS !!!
  - unrepaired_l2_rejects=1
  - hidden_truth_nonpass=1
```

这点必须写进 report/review 口径:

```text
不是 all invariants pass。
是 structural invariants pass, semantic quality gates still fail on 2 turns。
```

---

## 2. 已经符合预期的部分

### 2.1 Artifact / Report 一致性恢复

v0.7.2 的最大问题之一是 report 和 artifact 事实不一致。

v0.7.2.1 中:

- `reportVer0.7.2.1.md` 的主数字与 `analyze_agentic_run.py` 输出一致。
- analyzer 支持 `--json`。
- analyzer 支持 `--fail-on-invariant`。
- per-turn artifact 完整存在。

这是重要进展。

后续所有 report 都应遵守:

```text
report metric table = analyzer output
手工文字只能解释,不能改数字
```

### 2.2 move_player no-op 修复有效

v0.7.2 中 `move_player` 可以携带:

```json
{"target": "flooded_stair"}
```

但 committer 只读 `destination`,导致移动 no-op。

v0.7.2.1 中:

- `target -> destination` normalize 已加。
- `target_location -> destination` 保留。
- `_validate_structure()` 会检查 `move_player.destination`。
- Validator 缺 `destination` hard_fail。
- Committer 对缺 `destination` fail loudly。
- analyzer 显示 `move_player_missing_destination = 0`。

这项通过。

### 2.3 hook_id 污染修复有效

v0.7.2 中 SemanticJudge 的 `category` 被写进 `active_hooks`,造成:

```text
investigation
environmental_mystery
location_access
objective_barrier
environmental
```

这类非 seed hook 污染。

v0.7.2.1 中:

- `SemanticJudgment.hook_id` 成为独立字段。
- `category` 只作为语义分类。
- HookManager 用 `hook_id`,不用 `category`。
- HookManager 加 seed whitelist。
- analyzer 显示 `invalid_hook_ids = []`。

这项通过。

### 2.4 absence_response 已真实触发

Turn 19:

```text
player_input: 我问艾伦是否愿意一起下去。
resolved target: alen
available: false
source: absence_response
visible_entity_ids: ["player"]
```

这说明 v0.7.2.1 已经证明:

```text
known-but-unavailable target -> absence_response
```

不是像 v0.7.2 那样只在 report 中声称触发。

这项通过。

### 2.5 L2 三态 gating 开始工作

v0.7.2 把大量 L2 reject 写成 `light_repair`,但没有实际闭环。

v0.7.2.1 改成:

```text
pass
repaired
failed
```

当前 run:

```text
pass = 18
repaired = 0
failed = 2
```

这说明 fail-closed 口径已经生效。失败 turn 没有再被混成 pass。

这项结构上通过。

---

## 3. 仍未通过的部分

## 3.1 Turn 4 hidden-truth symbolic hint

Turn 4 玩家输入:

```text
我试着推开那扇门。
```

L2 判定:

```text
hidden_truth_exposure: downgrade
category: symbolic_hint
```

触发点:

```text
三道平行划痕 / three parallel scratches
waiting for some response
```

它与 hidden truth:

```text
lower vault door responds to a three-note bell sequence
```

形成强关联。

这不是结构 bug。L2 正确抓到了一个过强的 symbolic hint。

但这说明:

```text
Renderer/Director 对 hidden-truth 附近的 symbolic motif 控制仍不够。
```

注意: 不建议简单把 `"three"` 加进关键词表一刀切。那会误杀大量正常文本。

更合理的 v0.7.3 方向:

```text
hidden truth risk pattern:
  number three + door/mechanism + response/sound/bell/waiting

而不是:
  any "three" => block
```

## 3.2 Turn 12 spatial inconsistency 根因不只是 Renderer

Turn 12 玩家输入:

```text
我沿着积水阶梯往下走。
```

L2 判定:

```text
render_claim_support: reject
category: spatial_inconsistency
```

表面看是 Renderer 把玩家和 Alen 写在同一空间,但 artifact 说明根因更深。

Turn 12 transaction 里已经有:

```json
{
  "kind": "observe_reaction",
  "params": {
    "entity": "alen",
    "description": "Alen follows closely behind..."
  }
}
```

以及:

```json
{
  "kind": "add_event",
  "params": {
    "summary": "Player and Alen descend into the flooded stairwell."
  }
}
```

但 world facts 里:

```text
at(player,flooded_stair)
at(alen,entrance_hall)
```

这说明问题不只是 Renderer 发明 prose,而是 Director/transaction 已经表达了:

```text
Alen follows / Player and Alen descend
```

但当前 operation set 没有真正提交:

```text
move_entity(alen, flooded_stair)
party_follow
```

因此 v0.7.3 必须处理 NPC 空间一致性,不能只把锅丢给 Renderer。

正确约束应是:

```text
如果 transaction 声称 NPC 跟随玩家移动:
  必须有明确 move_entity / move_npc / party_follow operation
否则:
  observe_reaction/speech/render 不得把该 NPC 写成当前可见
```

## 3.3 Turn 16 fallback 仍存在

Turn 16:

```text
我回到封闭下层门。
source: fallback
reason: Director schema parse failed after retries
```

这已经达成 `<=1/20`,但不是理想状态。

更重要的是,这是一个普通 movement action。让 local vLLM Director 处理这种确定性移动,没有必要。

v0.7.3 应把 movement 从 Director 不稳定区剥离出去:

```text
if action_type == "move" and target location is valid/reachable:
  deterministic move transaction
else:
  Director
```

这样既降低 fallback,也降低 wall time。

## 3.4 `repaired = 0` 说明还没有 repair loop

v0.7.2.1 的三态 gating 是对的,但只是 fail-closed。

当前:

```text
failed = 2
repaired = 0
```

这说明:

```text
系统已经能判断输出坏了,但还不能自动修好。
```

v0.7.3 不应继续只记录 failed,而应进入 repair loop:

```text
Render -> L2 failed -> build repair brief -> Flash repair once -> re-check -> pass/repaired/failed
```

---

## 4. v0.7.3 具体规划

v0.7.3 的核心命题:

> 在 v0.7.2.1 的结构正确性基线上,补上 movement deterministic、NPC 空间一致性、Renderer grounding 和 L2 repair loop,让语义质量门从"能抓到问题"推进到"能闭环修复问题"。

---

## Phase 1 - Deterministic Movement Path

目标:

```text
普通合法移动不再调用 Director。
消除 movement turn 的 JSON schema fallback。
降低平均延迟。
```

触发条件:

```text
resolved_intent.action_type == "move"
exactly one target ref
target.kind == "location"
target.available == true
target.canonical_id in reachable_location_ids
```

输出:

```python
TurnTransaction(
  operations=[
    Operation("move_player", {"destination": target_id}),
    Operation("add_event", {"summary": "Player moves to <target_id>."}),
    Operation("add_texture", {"text": "...minimal sensory transition..."})
  ],
  commitments=[
    Commitment("canon", "Player moves to <target_id>.", operation_index=0),
    Commitment("event", "Player moves to <target_id>.", operation_index=1),
    Commitment("texture", "...", operation_index=2)
  ],
  assumptions=[{"source": "deterministic_movement"}]
)
```

注意:

```text
deterministic movement 只负责状态移动和极小 texture。
不要生成复杂剧情、hook reveal、NPC reaction。
```

Deliverables:

- `runner.py`: 在 Director 前增加 deterministic movement branch。
- `transaction.py`: 可选记录 source。
- `scripts/analyze_agentic_run.py`: source 增加 `deterministic_movement`。
- tests:
  - `test_deterministic_move_bypasses_director`
  - `test_deterministic_move_commits_player_location`
  - `test_unreachable_move_does_not_bypass_director_or_returns_absence_response`

验收:

```text
movement fallback = 0
total fallback = 0 或 <=1/20
move_player_missing_destination = 0
deterministic_movement turns >= 2 in 20-turn
avg wall time <= 20s
```

---

## Phase 2 - NPC Spatial Consistency

目标:

```text
NPC 不得在 transaction/render 中出现在错误地点。
如果 NPC 跟随,必须被显式提交。
```

需要先决定 v0.7.3 是否支持 NPC 跟随。

### 方案 A: 不支持跟随,严格限制

规则:

```text
如果 player moves away and NPC not moved:
  subsequent visible_entities excludes NPC
  Director forbidden to speak/observe_reaction for absent NPC
  Renderer forbidden to describe absent NPC as present
```

优点:

- 简单。
- 与当前 absence_response 方向一致。
- 不引入 NPC AI。

缺点:

- 玩家邀请/带走 NPC 的体验较弱。

### 方案 B: 支持显式 move_entity

新增 operation:

```python
Operation("move_entity", {"entity": "alen", "destination": "flooded_stair"})
```

规则:

```text
如果 Director 声称 Alen follows / accompanies / descends with player:
  必须有 move_entity(alen, player_destination)
否则 Validator hard_fail 或 downgrade claim
```

优点:

- 可以表达 NPC 跟随。
- 对跑团体验更自然。

缺点:

- 引入新的状态变更类型。
- 需要 Validator/Committer/RenderBrief 同步支持。

v0.7.3 推荐:

```text
先做方案 A,不支持隐式跟随。
把 move_entity 留到 v0.7.4。
```

Deliverables:

- Validator:
  - `speak.entity` / `observe_reaction.entity` 必须在 current visible_entities。
  - `add_event` summary 若包含 absent NPC + follow/accompany/move 语义,调用 L2 或 deterministic guard。
- Director prompt:
  - "Do not describe absent NPCs as following unless an explicit move_entity operation exists. move_entity is not available in this version."
- RenderBrief:
  - 加入 `visible_entities`。
  - 加入 `absent_entities`。
  - 加入 `player_location`。
- tests:
  - `test_director_cannot_observe_absent_npc`
  - `test_render_brief_contains_visible_and_absent_entities`
  - `test_turn12_no_alen_in_flooded_stair_without_move_entity`

验收:

```text
spatial_inconsistency L2 hard rejects = 0
absent NPC rendered as present = 0
Turn 12 不再把 Alen 写到 flooded_stair
```

---

## Phase 3 - RenderBrief Grounding Upgrade

目标:

```text
Renderer 只根据当前可见事实 render,不靠旧 story_packet 或泛化想象补空间关系。
```

RenderBrief 增加:

```python
player_location: str
visible_entities: list[str]
visible_objects: list[str]
absent_entities: list[str]
committed_operations: list[dict]
committed_facts_delta: list[str]
forbidden_entity_claims: list[str]
forbidden_spatial_claims: list[str]
```

Renderer prompt 明确:

```text
Only describe entities in visible_entities as physically present.
Never place absent_entities in the scene.
If an absent entity is mentioned by player, describe absence, not reaction.
Do not introduce new marks/sounds/mechanisms unless they appear in committed_operations or allowed_hints.
```

Deliverables:

- `render_brief.py` 扩展字段。
- `renderer_agent.py` prompt 更新。
- runner 构建 RenderBrief 时传当前 post-commit world scene。
- tests:
  - `test_render_brief_filters_absent_entities`
  - `test_renderer_prompt_contains_absent_entity_guard`
  - `test_render_brief_contains_player_location`

验收:

```text
render_claim_support hard_rejects = 0
spatial_inconsistency = 0
unsupported_character_state 显著下降
```

---

## Phase 4 - L2 Repair Loop

目标:

```text
L2 failed 不只记录,而是尝试修复一次。
```

流程:

```text
1. Renderer 生成 prose
2. Post-render checker
3. if status == failed:
     build RepairBrief
     call Flash repair once
     run checker again
4. if second check pass:
     status = repaired
     player_output = repaired_prose
   else:
     status = failed
     player_output = safe fallback / minimal grounded prose
```

RepairBrief 内容:

```python
original_prose
issues
semantic_judgments
committed_events
visible_entities
absent_entities
player_location
allowed_hints
forbidden_claims
```

Repair prompt 原则:

```text
Preserve only committed events.
Remove unsupported entity/action/location claims.
Remove symbolic hidden-truth hints named in issues.
Keep 1-2 short Chinese paragraphs.
Do not add new facts.
```

Deliverables:

- `renderer_agent.py`: `repair_renderer_output(...)` 或单独 `render_repair.py`。
- `runner.py`: failed -> repair once -> re-check。
- `post_render_checker.py`: 支持 `repair_round` metadata。
- analyzer:
  - `failed_initial`
  - `repaired`
  - `failed_final`
  - `repair_attempts`
- tests:
  - `test_l2_failed_triggers_repair`
  - `test_repair_removes_absent_npc_claim`
  - `test_repair_failure_counts_failed`

验收:

```text
initial_failed 可以 >0
final_failed <=1/20
repaired >=1 if initial_failed >0
unrepaired_l2_rejects = 0
hidden_truth_nonpass_after_repair = 0
avg wall time <=28s
```

---

## Phase 5 - Hidden Truth Symbolic Hint Policy

目标:

```text
避免 "三道痕迹 + 门 + 等待回应" 这种强 symbolic bridge。
```

不建议:

```text
把 "three/三" 加为全局 forbidden keyword。
```

建议建立 hidden-truth risk patterns:

```yaml
hidden_truths:
  h_bell_sequence_opens_door:
    symbolic_risk_patterns:
      - concepts: [three, door, response]
      - concepts: [three, bell, mechanism]
      - concepts: [three marks, waiting, sound]
    safe_hint_boundary:
      allowed:
        - old scratches
        - uneven wear
        - cold metal vibration
      disallowed:
        - exact count of three linked to mechanism
        - bell/chime imagery near door before evidence
        - "waiting for a response" near three marks
```

SemanticJudge 使用这些 pattern 作为 context,而不是靠 substring。

Deliverables:

- seed hidden_truth 增加 `symbolic_risk_patterns`。
- `semantic_judge.judge_hidden_truth_exposure()` prompt 注入 patterns。
- Renderer prompt 注入 per-hidden-truth `safe_hint_boundary`。
- tests:
  - `test_three_alone_not_blocked`
  - `test_three_door_response_blocked`
  - `test_safe_wear_hint_allowed`

验收:

```text
hidden_truth_nonpass_after_repair = 0
symbolic_hint false positives 可控
Turn 4 不再 failed
```

---

## Phase 6 - v0.7.3 20-turn Revalidation

目标:

```text
证明 v0.7.3 从 correctness baseline 推进到 semantic quality closure baseline。
```

验收表:

| 指标 | v0.7.2.1 | v0.7.3 目标 |
|---|---:|---:|
| errors | 0 | 0 |
| report/analyzer mismatch | 0 | 0 |
| move_player_missing_destination | 0 | 0 |
| invalid_active_hook_ids | 0 | 0 |
| Director fallback | 1/20 | 0 或 <=1/20 |
| deterministic_movement turns | 0 | >=2 |
| absence_response | 1 | >=1,如脚本仍制造 absent target |
| validator downgraded turns | 1 | <=1 |
| post_render final_failed | 2 | <=1 |
| repaired turns | 0 | >=1 if initial_failed >0 |
| unrepaired_l2_rejects | 1 | 0 |
| hidden_truth_nonpass_after_repair | 1 | 0 |
| spatial_inconsistency hard rejects | 1 | 0 |
| canonical unique hooks engaged | 3 | >=3 |
| longest no-motif streak | 3 | <=3 |
| avg wall time | 21.64s | <=28s with repair |

Deliverables:

- `docs/plans/planVer0.7.3.md`
- `docs/reports/reportVer0.7.3.md`
- updated analyzer output attached or embedded

---

## 5. v0.7.3 明确不做的事

v0.7.3 不建议做:

- 不新增复杂 NPC AI。
- 不用 `follow_player: true` 掩盖空间一致性问题。
- 不把 "三/three" 做全局关键词封禁。
- 不降低 L2 judge 严格度来让指标好看。
- 不把 failed 计入 pass。
- 不继续扩 hook/motif 数量来提高指标。
- 不在没有 repair loop 的情况下宣称 semantic closure。

---

## 6. 最终评价

v0.7.2.1 是一次有效修复。

它把 v0.7.2 的混乱状态推进到:

```text
结构正确
指标可信
artifact 可审计
失败可定位
```

这已经达到 correctness repair 的目标。

但它也清楚显示:

```text
L2 现在能抓问题,但系统还不能稳定修问题。
Director 仍会在简单 movement 上 fallback。
NPC 空间关系仍会穿透 transaction/render 边界。
hidden-truth symbolic hints 仍需更细的策略。
```

因此 v0.7.3 的核心目标应该是:

> **从 "semantic detector" 推进到 "semantic repair and grounding loop"。**

一句话结论:

```text
v0.7.2.1 可作为结构正确性基线归档。
v0.7.3 必须解决 movement deterministic、NPC 空间一致性、Renderer grounding 和 L2 repair,否则项目仍只是会发现叙事错误,还不能可靠地产出合格叙事。
```
