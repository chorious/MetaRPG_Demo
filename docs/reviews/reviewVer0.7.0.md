# reviewVer0.7.0 - Transaction-First 通过,但语义约束层仍需上移

日期: 2026-05-19

评审范围:

- `docs/reports/reportVer0.7.0.md`
- 20-turn live 验证结果
- `metarpg/agentic/*` v0.7.0 transaction-first 实现

---

## 0. 总体结论

v0.7.0 的 **transaction-first** 架构验证通过。

这次 20-turn 结果说明项目已经从 v0.6.x 的:

```text
Writer prose -> Translator/Scanner/Auditor 事后追杀 -> fallback
```

推进到:

```text
Feasibility
  -> NarrativeFrame
  -> Director(local vLLM)
  -> Validator
  -> Committer
  -> Renderer(DeepSeek Flash)
  -> Post-render Checker
```

这个方向是正确的。

但也要严厉指出:

```text
v0.7.0 管线足够稳定,但底层语义约束还不够抽象。
当前代码仍在若干关键路径上用关键词、substring、token overlap 做叙事语义判断。
这些低抽象实现解释了 hook/hint/motif 指标未达标。
```

核心评价:

> **v0.7.0 已经证明 "散文不改世界,transaction 才改世界" 是可行的。v0.7.1 的重点不是继续扩关键词表,而是把 intent、reference、hook、motif、hidden reveal 等语义判断上移到更高抽象层;如果 deterministic 规则不足,就调用 local LLM Semantic Judge。**

---

## 1. 20-turn 验证结果解读

用户提供的 20-turn summary:

| 指标 | 结果 | 目标 | 状态 |
|---|---:|---:|---|
| Turns 完成 | 20/20 | 20 | 通过 |
| 系统 fallback | 0 | 0 | 通过 |
| Director fallback | 2 | <5% | 未完全通过 |
| Hidden leaks | 0 | 0 | 通过但需谨慎解释 |
| Post-render pass | 20/20 | 20 | 通过但指标偏弱 |
| Hints surfaced | 4 | >=5 | 差 1 |
| Hooks engaged | 2 | >=3 | 差 1 |
| Motifs used | 1 | >=2 | 差 1 |
| Avg wall time | 19.3s | - | 通过 |

注意:

```text
Director fallback = 2/20 = 10%。
如果目标是 <5%,则 20 turn 内最多只能 0 或 1 次 fallback。
所以该项不能算完全通过。
```

积极结论:

1. 主链路已经打通。
2. Flash Render 质量达标。
3. local vLLM Director 能产出有效 transaction。
4. 系统级 fallback 清零。
5. 性能从 v0.6.x 的分钟级下降到 19.3s/turn,这是实质进步。

保留判断:

```text
Hidden leaks = 0 和 Post-render pass = 20/20 目前只能说明没有撞到 alias/debug/NPC-inner 关键词。
它不能充分证明 "语义上没有泄露 hidden truth" 或 "Renderer 没有偷加世界事实"。
```

---

## 2. 架构层面的成功

### 2.1 世界变更来源已经正确转移

v0.6.x 最大问题是让 prose 同时承担:

```text
玩家体验
世界变更声明
后续事实来源
审计对象
```

v0.7.0 把这些职责拆开:

```text
TurnTransaction -> 世界变更
Renderer prose   -> 玩家体验
Validator        -> transaction 约束
Post-checker     -> prose 轻量防线
```

这是正确的项目主线。

### 2.2 DeepSeek Flash 的位置正确

Flash 被限制为 Render 层,这很重要:

```text
它负责中文质感、节奏、感官、motif 变奏。
它不负责事实提交、hook 状态、hidden truth 边界。
```

这保留了 LLM 的文学优势,也避免把世界一致性托付给最终 prose。

### 2.3 DND 地城 seed 是合适验证场

Ashen Vault 的地城 seed 覆盖了足够多的机制:

```text
入口厅 / 下层门 / 黑灰 / 受伤 NPC / 潮湿阶梯
enigma / threshold / debt / lack / hidden truth / motif
```

它不是完整 DND 规则系统,但足以验证 transaction-first 的核心。

---

## 3. 当前低抽象问题清单

以下不是风格问题,而是会直接影响系统是否具备 "叙事理解感" 的底层问题。

### 3.1 Intent 识别仍靠动词表

位置:

```text
metarpg/agentic/runner.py::_feasibility_to_intent
```

当前实现用英文/中文动词 substring 映射:

```text
检查/查看/观察 -> inspect
问/询问/打听 -> ask
走/去/接近 -> move
```

这解释了 20-turn 中大量 `arrival` beat:

```text
Feasibility 输出稍微复杂一点,或中文表达不在表里,action_type 就退到 ambiguous。
ambiguous 再退到 arrival。
```

问题性质:

```text
这是 L1 reference/intent resolution,不是 L3 keyword hygiene。
不能靠继续扩动词表解决。
```

建议:

```text
新增 intent_resolver.py 或 reference_resolver.py。
用 local vLLM 输出 structured intent:
  action_type
  target_refs
  prop_refs
  confidence
  unresolved_mentions
```

### 3.2 Hook 匹配仍靠 subject/object 字符串重合

位置:

```text
metarpg/agentic/hook_manager.py::_match_hooks
metarpg/agentic/hook_manager.py::_fuzzy_match
```

当前逻辑:

```text
subject/object in search_terms
或 lower_door 与 lower_vault_door 共享 token 就算相关
```

问题:

```text
Hook 是叙事张力,不是字符串索引。
"门上的三道痕" 可能指向 threshold hook,但不一定命中 subject/object。
"艾伦回避下层" 也可能推动 debt/lack hook,不是只看 target 是否等于 alen。
```

建议:

```text
Hook relevance 应由 local vLLM judge 判断。
输入 active_hooks + player_intent + current beat + recent events。
输出:
  hook_id
  relevance: none | weak | strong
  proposed_status: dormant | surfaced | engaged | progressed | resolved
  reason
```

### 3.3 Motif 选择仍靠 label 命中

位置:

```text
metarpg/agentic/hook_manager.py::_select_motifs
```

当前逻辑:

```text
motif label 出现在 player_input 或 hook tension 中才选。
```

这解释了:

```text
Motifs used = 1,目标 >=2。
```

问题:

```text
Motif 的价值不是 "玩家提到了黑灰所以用黑灰"。
Motif 应该根据 beat、hook、最近使用历史、主题功能进行调度和变奏。
```

建议:

```text
新增 motif_scheduler.py。
维护 motif ledger:
  last_used_turn
  use_count
  last_variation
  associated_hooks
  pressure/lure

每 turn 至少选 1 个 motif,除非 beat 明确禁止。
选择依据: beat + active_hooks + recent usage + motif function。
```

### 3.4 Location ID 解析缺失导致 fallback

现象:

```text
Turn 3 lower_door
Turn 16 lower_level_door
seed 中 canonical ID 是 sealed_lower_door
```

Validator 拒绝 unknown_location 是正确的硬约束。
问题不在 Validator,而在 Validator 前缺少 Reference Resolver。

建议:

```text
seed 中为 location/entity/item/hook 增加 aliases。
story_packet 给 Director 注入 canonical ID 白名单。
reference_resolver 将自然语言 mention 映射到 canonical ID。
Validator 只接受 canonical ID,不做 fuzzy。
```

不要把 fuzzy matching 塞进 Validator。

### 3.5 Director 会发明 hook_id

现象:

```text
hook_mystery_ash
hook_entrance_mystery
hook_investigation_start
```

这些不在 seed。

问题:

```text
Director 还没有被结构化约束到 "只能引用 active_hooks ID"。
```

建议:

```text
Director prompt 注入:
  active_hook_ids
  allowed_hook_status_transitions

schema 层约束:
  mark_hook_status.hook_id 必须来自 active_hook_ids

Validator 硬拒或降级:
  unknown hook_id -> drop mark_hook_status,保留 event/texture
```

### 3.6 Hidden truth 检查仍是 alias substring

位置:

```text
transaction_validator.py::_reveals_hidden_truth
post_render_checker.py::_collect_hidden_aliases + alias scan
```

这只能作为廉价报警。

它抓得到:

```text
"bell sequence"
"stolen relic"
```

抓不到:

```text
"门像是在等待三次声音"
"某件被带到下层的东西留下了空位"
```

后者语义上可能已经接近 reveal。

建议:

```text
新增 semantic_judge.py:
  judge_hidden_truth_exposure(prose_or_commitment, hidden_truths, reveal_policy)

输出:
  none | weak_hint | strong_hint | direct_reveal
  evidence
  recommended_downgrade
```

### 3.7 NPC 内心独白检查仍靠短语

位置:

```text
post_render_checker.py::_NPC_INNER_INDICATORS
```

当前关键词:

```text
心想 / 内心 / 暗自 / 默念 / 心底 / 思索着 / 想着
```

问题:

```text
可见行为和内心判断的边界不是关键词能判的。
"她垂下眼,像是不愿回答" 是可见推断。
"她害怕你发现真相" 是 NPC 内心/hidden truth 泄露。
```

建议:

```text
交给 semantic_judge 判断:
  observable_reaction
  player_inference
  npc_private_mind
  hidden_truth_exposure
```

### 3.8 Post-render pass 指标偏弱

位置:

```text
post_render_checker.py::_find_uncommitted_facts
```

当前实现实际是占位,返回空。

因此:

```text
Post-render pass 20/20 只证明没撞到几个关键词。
它不能证明 Renderer 没有加入新的地点、物件、事实、关系承诺。
```

建议 v0.7.1:

```text
用 local vLLM 做 Render Entailment Judge:
  输入: rendered prose + validated transaction + visible world facts
  输出:
    supported_claims
    unsupported_claims
    harmless_texture
    canon_overclaim
```

---

## 4. 约束层应重新分层

v0.7.1 应明确四层约束:

### L0 Deterministic Hard Constraints

适合代码规则:

```text
ID 是否存在
物品归属
实体是否在场
地点是否可达
relation_delta / belief_delta 上限
hook_id 是否存在
hook status transition 是否允许
```

这些不需要 LLM。

### L1 Reference Resolution

适合 local vLLM + structured output:

```text
lower_door -> sealed_lower_door
old guard room -> old_guardroom
Alen / 艾伦 -> alen
ash / black residue / 黑灰 -> black_ash
```

这层输出 canonical refs。

### L2 Semantic Policy Judge

适合 local vLLM:

```text
hint vs reveal
canon vs utterance
texture vs fact
NPC private mind vs observable reaction
setting fit
motif usage quality
hook relevance
```

这是"有人感"判断所在层。

项目不应该假装这些能用正则解决。

### L3 Hygiene Scan

适合关键词/alias:

```text
debug terms
internal IDs
exact hidden aliases
schema/fallback/system terminology
```

这层只能做廉价报警,不能做主裁判。

---

## 5. v0.7.1 建议方向

### 5.1 新增 `reference_resolver.py`

职责:

```text
将玩家输入、Director 输出中的自然语言 mention 映射到 canonical world IDs。
```

输入:

```text
player_input
visible_entities
visible_items
reachable_locations
active_hooks
aliases
```

输出:

```json
{
  "action_type": "move",
  "targets": [
    {"mention": "lower door", "ref": "sealed_lower_door", "kind": "location", "confidence": 0.91}
  ],
  "unresolved_mentions": []
}
```

### 5.2 新增 `semantic_judge.py`

职责:

```text
所有无法可靠形式化的叙事判断交给 local vLLM。
```

建议函数:

```python
judge_hook_relevance(...)
judge_hidden_truth_exposure(...)
judge_commitment_level(...)
judge_render_claim_support(...)
judge_npc_private_mind(...)
judge_setting_fit(...)
```

输出必须结构化:

```python
SemanticJudgment:
    verdict: pass | downgrade | reject
    category: setting_violation | reveal_too_direct | canon_overclaim | npc_private_mind | motif_misuse
    evidence: str
    suggested_downgrade: str | None
    confidence: float
```

### 5.3 新增 `motif_scheduler.py`

职责:

```text
不再靠 label substring 选择 motif。
按 beat/hook/recent usage 调度 motif。
```

输出:

```text
motifs_to_use
required_variation
forbidden_repetition
```

示例:

```text
Turn 1: black_ash -> bitter smell
Turn 8: black_ash -> smear on stair water
Turn 17: bell -> three dull scratches, still no sound
```

### 5.4 扩展 seed aliases

seed 中应加入:

```yaml
locations:
  sealed_lower_door:
    aliases: [lower door, lower vault door, closed lower door, 下层门, 封闭的门]

items:
  black_ash:
    aliases: [ash, black residue, 灰, 黑灰, 灰烬]

entities:
  alen:
    aliases: [Alen, 艾伦, injured man, 受伤的人]
```

但注意:

```text
aliases 是 ReferenceResolver 的输入,不是到处 substring 判断的授权。
```

### 5.5 Director schema 增加强 ID 约束

Director prompt/schema 应明确:

```text
move_player.destination 必须来自 reachable_location_ids。
speak.entity 必须来自 visible_entity_ids。
mark_hook_status.hook_id 必须来自 active_hook_ids。
motif refs 必须来自 motifs_to_use。
```

这比事后 fuzzy 更稳。

---

## 6. 不建议继续做的事

不要继续:

```text
扩中文动词表
扩 hidden alias 表
扩 NPC 内心关键词
扩 hook fuzzy token overlap
扩 motif label 命中规则
```

这些会让系统重新滑回 v0.6 的问题:

```text
规则越来越多,抽象层级越来越低,误杀和漏杀越来越难解释。
```

如果某个判断需要"懂意思",就应该承认它是 semantic task,交给 local LLM judge。

---

## 7. 最终判断

v0.7.0 是一个有效 baseline。

它证明:

```text
transaction-first 能跑通。
DeepSeek Flash Render 能保留中文质量。
local vLLM Director 能生成可提交结构。
20-turn 稳定性已经超过 v0.6.x。
```

但它还没有完全实现项目想要的"强规则 + 有人感叙事理解"。

当前最需要上移抽象层级的路径:

```text
Intent
Reference resolution
Hook relevance
Motif scheduling
Hidden truth exposure
Commitment level classification
Render claim support
NPC private mind detection
```

这些路径如果继续用关键词匹配,系统会卡在"能跑但不懂"。

v0.7.1 的核心命题应是:

> **足够抽象的硬约束用代码做;需要语义理解的边界调用 local LLM judge;关键词只保留为 hygiene 兜底。**

---

## 8. 一句话总结

> **v0.7.0 成功把世界提交权从散文中拿了出来,这是正确的大架构。但底层约束还残留低抽象关键词路径。下一步不要继续补词表,而要建立 ReferenceResolver、SemanticJudge、MotifScheduler 三层,让需要"有人感"的判断由 local LLM 以结构化方式完成。**
