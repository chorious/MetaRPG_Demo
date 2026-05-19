# reviewVer0.7.1 - L1/Motif baseline 通过,但 Semantic Constraint Layer 未完成

日期: 2026-05-19

评审范围:

- `docs/reports/reportVer0.7.1.md`
- `runtime/agentic_runs/v070_smoke_5efb2704/events.jsonl`
- `runtime/agentic_runs/v070_smoke_5efb2704/errors.jsonl`
- v0.7.1 相关代码:
  - `metarpg/agentic/reference_resolver.py`
  - `metarpg/agentic/semantic_judge.py`
  - `metarpg/agentic/motif_scheduler.py`
  - `metarpg/agentic/runner.py`
  - `metarpg/agentic/hook_manager.py`
  - `metarpg/agentic/post_render_checker.py`
  - `metarpg/agentic/director_agent.py`
  - `metarpg/agentic/transaction_validator.py`

---

## 0. 总体结论

v0.7.1 **不能按 "Semantic Constraint Layer Upgrade 完成" 验收**。

更准确的验收口径应该是:

```text
v0.7.1 完成了 L1 ReferenceResolver 初版 + MotifScheduler 初版,
并证明它们能接入 v0.7.0 transaction-first pipeline。

但 L2 SemanticJudge 仍未成为主链路的一部分,
关键语义边界仍大量依赖 deterministic / substring / token overlap / keyword hygiene。
```

所以本次 review 的判断是:

```text
工程 baseline: 可接受
指标改善: 部分达标
语义约束愿景: 未达标
版本状态: 可作为 v0.7.1 baseline,不应宣布 semantic constraint layer 完成
```

这不是方向错误。方向仍然正确:

```text
玩家自然语言
  -> ReferenceResolver 归一化为 canonical refs
  -> NarrativeFrame / Director 生成 transaction
  -> Validator 只吃 canonical ID 和硬约束
  -> Committer 改世界
  -> Flash Renderer 只负责 render
  -> Post-render checker 做最后防线
```

问题在于: 当前落地只完成了这条路的一半。它解决了一些 v0.7.0 的具体失败点,但还没有解决我们最关心的"像人一样判断是否符合叙事设定"。

---

## 1. 指标验收

报告中的 v0.7.1 结果:

| 指标 | v0.7.0 baseline | v0.7.1 目标 | v0.7.1 实际 | 评审 |
|---|---:|---:|---:|---|
| Turns 完成 | 20 | 20 | 20 | 通过 |
| errors.jsonl | - | 0 | 0 | 通过 |
| Director fallback | 2/20 | <=1/20 | 2/20 | 未通过 |
| Hints surfaced | 4 | >=5 | 5 | 表面通过 |
| Hooks engaged | 2 | >=3 | 3 | 表面通过 |
| Motifs used | 1 | >=2 | 3 | 表面通过 |
| Motif variations | 1 | >=2 | 3 | 需谨慎解释 |
| Hidden leaks | 0 | 0 | 0 | 通过但证据偏弱 |
| Post-render pass | 20/20 | 20/20 | 20/20 | 通过但证据偏弱 |
| Avg wall time | 19.3s | <=25s | 16.0s | 通过 |

这里要严厉区分两种"通过":

1. **管线型通过**: 没 crash、能跑完、能输出、速度达标。
2. **语义型通过**: 系统真的理解了玩家意图、世界边界、hidden reveal、NPC 在场性、motif 叙事功能。

v0.7.1 主要通过的是第一类。第二类只部分成立。

---

## 2. 原始日志支持什么结论

`events.jsonl` 支持以下事实:

```text
20 turn_start_v070
20 story_packet_built
20 feasibility_complete
20 reference_resolver intent_resolved
20 frame_built
20 director transaction_produced
16 validator accepted
4  validator downgraded
20 commit_success
20 post_render pass
errors.jsonl length = 0
```

这说明 pipeline 稳定性是成立的。

但日志也暴露一个审计缺口:

```text
报告把 Turn 11 / Turn 19 标为 fallback。
events.jsonl 中这两个 turn 却记录为:
  director transaction_produced
  validator accepted
  commit_success
  post_render pass
```

可能原因是 fallback 只体现在 `TurnTransaction.assumptions` 里,而当前 run artifact 没有落盘完整 transaction。

这会造成一个严重问题:

```text
事后无法仅凭 runtime/agentic_runs/v070_smoke_5efb2704 完整复核报告结论。
```

v0.7.2 前必须补:

- 每 turn 保存 `resolved_intent.json`
- 每 turn 保存 `narrative_frame.json`
- 每 turn 保存 `transaction.raw.json`
- 每 turn 保存 `transaction.validated.json`
- 每 turn 保存 `render_brief.json`
- 每 turn 保存 `player_output.txt`
- 每 turn 保存 `post_render_check.json`
- 每 turn 保存 `semantic_judgments.jsonl`

否则 hooks/hints/motifs/leaks/fallback 的统计都只能部分相信。

---

## 3. 已经真正改善的部分

### 3.1 L1 ReferenceResolver 接入主链路

`runner.py` 已经在每 turn 调一次 `resolve_references()` 并把结果塞进 `NarrativeFrame`。

这符合我们在 v0.7.1 plan 中定下的调用纪律:

```text
Resolver 在 runner 做一次。
下游吃 ResolvedIntent,不要各层重复解析自然语言。
```

Turn 3 是正例:

```text
玩家输入: 我去看那扇封闭的下层门。
resolved target: sealed_lower_door
beat: threshold_crossing
validation: accepted
```

这说明 v0.7.0 的 location ID mismatch 问题确实被解决了一部分。

### 3.2 Director whitelist 方向正确

Director prompt 中加入:

- `reachable_location_ids`
- `visible_entity_ids`
- `active_hook_ids`
- `allowed_motif_ids`
- `resolved_intent`

并在 `_validate_structure()` 中检查:

- `mark_hook_status.hook_id`
- `move_player.destination`
- `speak.entity`

这是正确方向。Director 不应该自由发明 canonical ID。

### 3.3 Validator 回到硬约束职责

`transaction_validator.py` 中 `_location_exists()` 明确只接受 canonical ID,不做 alias resolution。

这是重要的架构纪律:

```text
ReferenceResolver 负责自然语言到 canonical ID。
Validator 负责 canonical ID 上的硬约束。
Validator 不应该再理解自然语言。
```

### 3.4 MotifScheduler 取代了旧的 motif label-substring 主路径

`motif_scheduler.py` 引入:

- hook/beat scoring
- cooldown
- variation rotation
- force-after-3-turns
- max motifs per turn

这比 v0.7.0 的 label matching 好很多。

---

## 4. 主要问题

## 4.1 Director fallback 目标未达成

v0.7.1 目标是:

```text
Director fallback <= 1/20
```

实际报告:

```text
Director fallback = 2/20 = 10%
```

这不能算通过。

报告解释为:

```text
Turn 11 / Turn 19 中玩家问艾伦,但艾伦不在当前地点。
这是 test-script / world-consistency edge case,不是 semantic-layer failure。
```

这个解释不够严格。

在 RPG 中,玩家问一个不在场 NPC 是非常正常的输入。系统应该做的是生成世界内响应:

```text
你回头望向入口厅的方向,才意识到艾伦没有跟下来。
这里只有水声和石阶回音回应你。
```

或者生成 affordance:

```text
你可以回入口厅找艾伦。
```

而不是让 Director 进入 fallback。

因此这不是"脚本问题"。这是 v0.7.1 缺少一类正式语义策略:

```text
absent_entity / unavailable_target / out_of_scene_interaction
```

它应该在 Director 之前由 intent/world-context 层处理。

建议 v0.7.2 增加:

```text
ResolvedIntent.target_state:
  present
  known_absent
  unknown
  unreachable

Frame policy:
  if target_state == known_absent:
    beat = absence_response
    allowed ops = add_texture, inner_monologue, add_event, offer_affordance
    forbidden ops = speak(entity), update_relation(entity), transfer_item(entity)
```

---

## 4.2 L2 SemanticJudge 基本没有进入主链路

这是本次最关键的问题。

`semantic_judge.py` 已经存在,包含:

- `judge_hook_relevance`
- `judge_hidden_truth_exposure`
- `judge_render_claim_support`

但实际主链路中:

```python
check_result = check_rendered_prose(prose, tx, world)
```

没有传入 `local_client`。

而 `post_render_checker.py` 的 L2 逻辑只有在:

```python
if _is_risk_turn(tx) and client is not None:
```

才会执行。

所以本次 20-turn 的 post-render pass 主要证明的是:

```text
L3 keyword hygiene 没扫出问题。
```

它没有证明:

```text
L2 semantic hidden-truth exposure 判断通过。
L2 semantic render-claim support 判断通过。
```

这与 v0.7.1 的核心命题不一致:

```text
需要语义理解的边界调用 local LLM judge。
关键词只保留为 hygiene 兜底。
```

当前事实更接近:

```text
关键词仍是 post-render 的实际主防线。
SemanticJudge 是可用模块,但没有成为主防线。
```

---

## 4.3 ReferenceResolver 仍有低层关键词残留

`reference_resolver.py` 中 `_infer_action_type()` 仍然是动词 substring 表:

```text
走/去/到/接近/靠近/进入 -> move
看/检查/观察/查看 -> inspect
问/说/告诉/聊 -> speak
拿/取/用/使用/给 -> interact
打/攻击/杀/推 -> attack
```

这比 v0.7.0 的 scattered verb table 集中了一点,但抽象层级没有根本变化。

更大的问题是 action type 与 reference resolution 混在同一个模块里:

```text
ReferenceResolver 应该解决 "玩家提到的对象是什么"。
IntentClassifier / FramePlanner 应该解决 "玩家想做什么"。
```

建议拆开:

```text
reference_resolver.py
  mention -> canonical refs

intent_classifier.py
  player_input + resolved_refs + scene -> structured intent

frame_builder.py
  structured intent + grammar + world -> NarrativeFrame
```

如果继续留在同一模块,至少要把 `_infer_action_type()` 标记为 L0.5 heuristic,不能把它描述成语义层完成。

---

## 4.4 Hook matching 仍有 token overlap fallback

`hook_manager.py` 已经从 fuzzy text matching 改到 canonical ID matching,这是好事。

但 `_match_hooks_v071()` 里仍有:

```text
canonical ID token overlap
```

这比自然语言 substring 好,但仍是低抽象规则。尤其是 `lower_vault`, `sealed_lower_door`, `lower_landing` 这类 ID 都会共享 `lower`,未来 seed 一复杂就容易误连 hook。

v0.7.1 MVP 可以暂时接受,但它不应该是长期方案。

建议:

```text
Hook matching 主路径:
  exact canonical subject/object match
  explicit hook affordance match
  grammar-defined hook transition

语义补全路径:
  judge_hook_relevance(player_intent, active_hooks, recent_events)

禁止:
  token overlap 自动推进 hook status
```

token overlap 最多只能作为 debug candidate,不能直接 engage hook。

---

## 4.5 Motif variation 没有真正传到 Renderer

`MotifSchedule` 有:

```text
required_variations
forbidden_repetition
```

但 `RenderBrief` 目前只有:

```text
motifs_to_render: list[str]
```

`renderer_agent.py` 的 prompt 也只看到 motif id,看不到:

- 本回合必须使用哪个 variation
- 最近禁止重复哪些 variation
- 这个 motif 在当前 beat 中承担什么功能

所以报告里的:

```text
Motif variations = 3
```

更像 scheduler 内部指标,不能证明玩家最终读到的 prose 真的完成了 variation。

建议把 `RenderBrief` 扩展为:

```python
motif_instructions: list[{
  "motif_id": str,
  "label": str,
  "function": str,
  "required_variation": str,
  "forbidden_repetition": list[str],
}]
```

Renderer prompt 不要只写:

```text
m_black_ash
```

而要写:

```text
Use motif m_black_ash as "bitter smell"; do not repeat "fingerprint".
```

---

## 4.6 Hidden leaks = 0 的证据偏弱

当前 `post_render_checker.py` 仍然保留:

- hidden truth alias substring scan
- NPC inner monologue phrase scan
- debug/system term scan
- `_find_uncommitted_facts()` placeholder

其中 `_find_uncommitted_facts()` 仍基本不工作,直接返回空 violations。

因此:

```text
Hidden leaks = 0
Post-render pass = 20/20
```

只能说明:

```text
没有命中已知 alias/关键词。
```

不能说明:

```text
语义上没有泄露 hidden truth。
语义上没有新增 uncommitted world fact。
语义上没有写 NPC private mind。
```

这正是我们不信关键词框架的原因。

---

## 5. 对当前报告的修正意见

`reportVer0.7.1.md` 的总体口径偏乐观。

建议把报告中的:

```text
v0.7.1 delivers the promised semantic constraint layer
```

改成:

```text
v0.7.1 delivers the first half of the semantic constraint layer:
L1 ReferenceResolver and MotifScheduler are operational.
L2 SemanticJudge exists but is not yet materially integrated into the live validation/checking path.
```

建议把:

```text
This is a test-script / world-consistency edge case rather than a ReferenceResolver or Validator failure.
```

改成:

```text
This exposes a missing absent-target policy.
The scripted input is reasonable for a live player; the system should produce an in-world absence response instead of allowing Director fallback.
```

建议把:

```text
Hidden leaks 0 = pass
```

改成:

```text
Hidden leaks 0 under current L3 scan.
No L2 semantic exposure proof was collected in this run.
```

---

## 6. v0.7.2 必须优先处理的事项

### P0 - 完整 run artifact

每 turn 落盘:

- `resolved_intent.json`
- `narrative_frame.json`
- `director_raw.json`
- `transaction_before_validation.json`
- `validation_result.json`
- `transaction_validated.json`
- `commit_delta.json`
- `render_brief.json`
- `player_output.txt`
- `post_render_check.json`
- `semantic_judgments.jsonl`

没有这些 artifact,后续 review 无法严肃复核。

### P0 - absent target policy

正式处理:

- 玩家问不在场 NPC
- 玩家对不在场对象行动
- 玩家说"那扇门"但当前场景有多个门/无门
- 玩家请求远程交互

这些都不应该触发 Director fallback。

### P0 - L2 SemanticJudge 真接入

最低要求:

```python
check_rendered_prose(prose, tx, world, client=local_client)
```

并在每次 L2 调用后落盘 judgment。

风险 turn 至少包括:

- transaction 有 hint/canon/belief_evidence
- transaction 有 mark_hook_status
- Renderer prose 中出现 hidden truth 相关对象
- Director 使用了 unresolved mention
- NPC speech / observe_reaction 涉及 hidden belief

### P1 - hook relevance judge 接入 unresolved / weak match

当 exact canonical subject/object match 不足时:

```text
不要 token overlap 自动 engage hook。
调用 judge_hook_relevance。
```

SemanticJudge 的 verdict 只能影响 frame candidate,不能直接改世界。

### P1 - action type 从 ReferenceResolver 中拆出

建立:

```text
intent_classifier.py
```

输出:

```python
StructuredIntent(
  action_type,
  target_refs,
  prop_refs,
  target_state,
  confidence,
  ambiguity,
  suggested_policy
)
```

### P1 - motif instruction 传到 Renderer

`required_variations` 必须进入 `RenderBrief` 和 prompt。

否则 motif variation 指标没有玩家侧证据。

---

## 7. 最终评价

v0.7.1 是一次有价值的工程推进,但不是语义层的完成版本。

它证明:

```text
canonical reference resolution 可以降低 ID mismatch。
transaction-first 架构可以继续承载更高抽象的叙事控制。
Motif 可以从 label matching 升级到 scheduler。
```

它没有证明:

```text
系统已经能用 human-feeling semantic judgment 约束剧情展开。
hidden truth / unsupported claim / NPC private mind 已经被语义判断覆盖。
absent target / coreference / ambiguous reference 已经被稳健处理。
```

因此建议版本状态写为:

```text
v0.7.1 accepted as L1+Motif baseline.
Semantic Constraint Layer remains incomplete.
v0.7.2 must integrate L2 judgments and absent-target policy before claiming semantic constraint success.
```

一句话:

> **v0.7.1 把"对象是谁"这件事做得更好了,但还没有把"这段展开在叙事上是否成立"这件事交给真正的语义层。**
