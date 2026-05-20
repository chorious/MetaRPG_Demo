  A. 整合版 plan（v0.7.5 — Semantic Quality Closure for Real）

  ▎ 起点：v0.7.4 (a1978aa) — fallback 清零、artifact 可信、intent obligation 接入、repair loop wiring 通过。
  ▎ 终点：在 Ashen Vault 单 seed 内，systemic invariant 与 player-intent semantic correctness 同时 hold；fallback /
  ▎ unrepaired / spatial / type / l2-coverage 五条线全部闭环。
  ▎ 冲突仲裁规则：v0.7.4 review > v0.7.3 review > v0.7.2.1 plan > v0.7.0 plan +
  ▎ planReview。下面所有条款都用最新版本覆盖旧版。

  ---
  A.0 方向真源（来自 planVer0.7.0，仍然有效，不变）

  Narrative Grammar
    -> NarrativeFrame
    -> Director 生成 TurnTransaction
    -> Validator 接受/降级/拒绝
    -> Committer 写 WorldGraph (adapter on WorldState)
    -> DeepSeek Flash Renderer 输出玩家文本
    -> Post-render Checker 做轻量防线

  约束分层（来自 review v0.7.0，仍然有效，不变）：
  - L0 deterministic hard constraint: ID 存在、归属、在场、可达、delta 边界、hook id 合法。
  - L1 reference resolution: 自然语言 mention → canonical ID。
  - L2 semantic policy judge: hint vs reveal、spatial、claim support、intent fulfillment、npc private mind。
  - L3 hygiene scan: alias / debug term 关键词。

  模型路由（来自 v0.7.0，仍然有效）：
  - flash → 仅 Renderer 与 Renderer-repair。
  - local → Director、Feasibility、ReferenceResolver LLM fallback、SemanticJudge、PostRenderChecker 的语义部分。
  - 配置永远从 set.env 读取，不允许硬编码。

  ---
  A.1 仍然成立、不要回退的设计纪律

  来自 v0.7.0~0.7.4 plan/review 的共识，已经写进现有代码、必须继续守住：

  1. 散文不改世界：只有 commit_transaction(world, validated_tx) 写世界；crystallize 在 v0.7.x 主链路里
  不再被调用（它仍在 run_agentic_turn legacy path 里）。
  2. Validator 不做 alias resolution：_location_exists 只接受 canonical id，所有 fuzzy 必须发生在 L1。
  3. active_hooks 白名单：所有写进 NarrativeFrame.active_hooks 的 id 必须 ∈ seed.active_hooks；SemanticJudge 的 category
   永远不允许进 active_hooks。
  4. move_player schema 硬约束：target / target_location 都被归一化为 destination，缺 destination = hard_fail；committer
   缺 destination 必须 raise，不再静默 return（v0.7.2.1 已修，不要回退）。
  5. artifact = single source of truth：所有指标必须由 scripts/analyze_agentic_run.py --json 计算，report 表格不再手写。
  6. fallback taxonomy 拆分：director_schema_fallback_count、validation_rejection_fallback_count、total_fallback_count
  分开。
  7. legacy runner 保留：run_agentic_turn (v0.6.6) 不被删除，但 不再投资新功能；smoke / play 的默认入口是
  run_agentic_turn_v070。
  8. 不要再扩关键词表：动词表、hidden alias 表、NPC 内心短语表、hook fuzzy token overlap 都已被多版 review 否决。
  9. 不要做以下事（来自最近三版 review 累积禁令）：
    - 不做完整 DND 战斗 / 数值规则。
    - 不做多步 pathfinding / 自动地图导航。
    - 不做隐式 NPC follow_player。
    - 不把 three / 三 做关键词封禁。
    - 不为降低指标而放松 Validator / SemanticJudge。
    - 不把 5-turn retest 当 20-turn 验收。
    - 不把 light_repair / repaired 当 pass 计数。

  ---
  A.2 v0.7.5 核心命题（按 v0.7.4 review 收口）

  ▎ 从 "fallback / metrics cleanup baseline" 推进到 "semantic coverage closure baseline"：让每个高风险 turn 都真的被 L2
  ▎ 检查，让 unreachable / absent / object-type 三类边界在 transaction 与 render 两侧同时硬掉，让 L2 repair 在 live run
  ▎ 中被规律化地证明有效。

  也就是把 v0.7.4 暴露的 4 个真实漏洞补掉（不要把它们留到 v0.8）：

  ┌─────┬────────────────────────────┬──────────────────────────────────────────────────┬──────────────────────────┐
  │ ID  │            漏洞            │                   当前代码位置                   │         修复方向         │
  ├─────┼────────────────────────────┼──────────────────────────────────────────────────┼──────────────────────────┤
  │     │ unreachable response prose │ render_brief.py::_build_current_turn_obligation  │ obligation contract + 把 │
  │ H1  │  自相矛盾                  │ + renderer_agent.py system rule 13 +             │  unreachable 强制纳入 L2 │
  │     │                            │ post_render_checker.py::_is_risk_turn            │  必跑                    │
  ├─────┼────────────────────────────┼──────────────────────────────────────────────────┼──────────────────────────┤
  │     │ absent NPC 的              │ transaction_validator.py::_check_operation       │ observe_reaction 用      │
  │ H2  │ observe_reaction 仍被      │ (observe_reaction 已做 absent 判定，但           │ visible_entity_ids       │
  │     │ Validator accept           │ _entity_present 只看 at fact，不看               │ 当真源                   │
  │     │                            │ visible_entity_ids)                              │                          │
  ├─────┼────────────────────────────┼──────────────────────────────────────────────────┼──────────────────────────┤
  │     │ item/object 被塞进         │ render_brief.py::_get_visible_entities 只从 at   │ RenderBrief 强类型 +     │
  │ H3  │ visible_entities，Renderer │ 推 entities，没有 entity vs item 类型纪律        │ Renderer prompt 禁止     │
  │     │  把 black_ash 写成人       │                                                  │ personify                │
  ├─────┼────────────────────────────┼──────────────────────────────────────────────────┼──────────────────────────┤
  │     │                            │                                                  │ 把 unreachable / absence │
  │ H4  │ L2 risk-turn 触发不准      │ post_render_checker.py::_is_risk_turn 只看       │  / fallback /            │
  │     │                            │ mark_hook_status 终态和 canon commit             │ observe_reaction(absent) │
  │     │                            │                                                  │  等加入必跑条件          │
  └─────┴────────────────────────────┴──────────────────────────────────────────────────┴──────────────────────────┘

  ---
  A.3 Phase 计划（v0.7.5）

  ▎ 严格沿用最近三版的纪律：每个 phase 必须有 targeted test，禁止把"smoke 没复现"当通过。

  Phase 0 — Clean Re-run + 指标基线封存

  - 跑一次完整 20-turn，把 v0.7.4 的指标用 analyze_agentic_run.py --fail-on-invariant 重新冷固化，落
  docs/reports/reportVer0.7.4.1.md（只是基线快照，不引入新功能）。
  - 如果某项 invariant 在第二次 run 上 regression，先修，再进入 Phase 1。

  Phase 1 — L2 Required Matrix（接收 v0.7.4 review §4.1）

  - 在 analyze_agentic_run.py 加：
    - l2_required_turns / l2_ran_turns / l2_required_but_not_run_count / l2_required_but_not_run_turns。
  - 在 post_render_checker.py::_is_risk_turn 增加触发条件：
    - obligation.response_mode in {"unreachable","absence","fallback"}
    - obligation.must_not_claim 非空
    - tx.operations 包含 speak 或 observe_reaction
    - tx.player_intent 含 available=false 的 target
    - candidate_hints 涉及 hidden_truth symbolic_risk_patterns
    - 上一轮 post_render status == repaired（重检质量）
  - 验收：l2_required_but_not_run_count = 0，Turn 16/17/20 类必须真的跑 L2。

  Phase 2 — Unreachable Intent Enforcement

  - 修复 prose 与 transaction 自相矛盾：
    - judge_intent_fulfillment 读 current_turn_obligation.must_not_claim，将"到达 / 触摸 / 推动 unreachable target"标
  wrong_target reject。
    - Renderer system prompt 对 response_mode == "unreachable" 注入两条 few-shot（BAD/GOOD）。
  - analyzer 加 unreachable_response_contradiction_count。
  - 验收：unreachable_response_contradiction_count = 0。

  Phase 3 — Validator Spatial Guard 真闭合

  - _check_operation 中 speak 和 observe_reaction 不再用 _entity_present（只看 at 事实），改用
  tx.narrative_frame.canonical_id_whitelist["visible_entity_ids"]，伪实体仅保留 player / environment。
  - update_belief / update_relation 若对应 entity 不在 visible 集合，downgrade 为 belief_evidence 或剔除。
  - analyzer 加 accepted_absent_entity_reaction_count / accepted_absent_entity_speech_count。
  - 验收：上述两项 = 0；Turn 14 / Turn 20 类不再 accepted。

  Phase 4 — Entity / Object Type Discipline

  - RenderBrief.visible_entities 只能包含 NPC（world.npcs）。
  - RenderBrief.visible_objects 在 _build_render_brief 中真正从 seed.items + at(item, loc) 推导（当前是 [] TODO）。
  - renderer_agent.py system prompt：visible_objects 默认无生命，禁止人格化。
  - judge_render_claim_support prompt 注入：at(item, location) 是 object presence，不是 character agency。
  - analyzer 加 object_as_visible_entity_count / object_personification_claim_count。
  - 验收：object_as_visible_entity_count = 0，black_ash 不再被写成人。

  Phase 5 — L2 Repair Loop Targeted Proof（接收 v0.7.3 Phase 5 未尽事项 + v0.7.4 §3.4）

  - 加 tests/fixtures/bad_prose_cases/*.json：
    a. stale-context（搜索 → 推门）
    b. hidden-truth symbolic bridge
    c. absent NPC 在场叙述
    d. repair impossible（验 fail-closed）
  - 在 analyzer 加 targeted_repair_cases / targeted_repair_pass。
  - 验收：targeted suite 内 repair_success >= 1，fail-closed 路径不被算入 pass。

  Phase 6 — Report Contract Tightening（接收 v0.7.4 §4.5）

  - 区分 semantic_judgment_count vs l2_ran_turn_count vs l2_required_turn_count。
  - 恢复 runtime/agentic_runs/<run_id>/manifest.json（来自 ARCHITECTURE_REORG_PLAN §7.1，目前缺失），同时保留
  events.jsonl / errors.jsonl / artifact_NNN_*.json。
  - 验收：report / analyzer / smoke summary 三者数字一致；manifest.json 存在。

  Phase 7 — v0.7.5 20-turn Revalidation

  ┌──────────────────────────────────────────┬────────┬───────────────────────┐
  │                   指标                   │ v0.7.4 │      v0.7.5 目标      │
  ├──────────────────────────────────────────┼────────┼───────────────────────┤
  │ errors                                   │      0 │                     0 │
  ├──────────────────────────────────────────┼────────┼───────────────────────┤
  │ total_fallback_count                     │      0 │                     0 │
  ├──────────────────────────────────────────┼────────┼───────────────────────┤
  │ validator rejected_turns                 │      0 │                     0 │
  ├──────────────────────────────────────────┼────────┼───────────────────────┤
  │ move_player_missing_destination          │      0 │                     0 │
  ├──────────────────────────────────────────┼────────┼───────────────────────┤
  │ invalid_active_hook_ids                  │     [] │                    [] │
  ├──────────────────────────────────────────┼────────┼───────────────────────┤
  │ l2_required_but_not_run_count            │ 未统计 │                     0 │
  ├──────────────────────────────────────────┼────────┼───────────────────────┤
  │ accepted_absent_entity_reaction_count    │     ≥2 │                     0 │
  ├──────────────────────────────────────────┼────────┼───────────────────────┤
  │ object_as_visible_entity_count           │     ≥1 │                     0 │
  ├──────────────────────────────────────────┼────────┼───────────────────────┤
  │ unreachable_response_contradiction_count │     ≥2 │                     0 │
  ├──────────────────────────────────────────┼────────┼───────────────────────┤
  │ hidden_truth_nonpass_after_repair        │      0 │                     0 │
  ├──────────────────────────────────────────┼────────┼───────────────────────┤
  │ unrepaired_l2_rejects                    │      0 │                     0 │
  ├──────────────────────────────────────────┼────────┼───────────────────────┤
  │ final_failed                             │      0 │                     0 │
  ├──────────────────────────────────────────┼────────┼───────────────────────┤
  │ repair_attempts (live + targeted)        │      1 │ ≥1 live + ≥1 targeted │
  ├──────────────────────────────────────────┼────────┼───────────────────────┤
  │ canonical unique hooks engaged           │      3 │                    ≥3 │
  ├──────────────────────────────────────────┼────────┼───────────────────────┤
  │ longest no-motif streak                  │      3 │                    ≤3 │
  ├──────────────────────────────────────────┼────────┼───────────────────────┤
  │ avg wall time                            │ 14.34s │                  ≤24s │
  └──────────────────────────────────────────┴────────┴───────────────────────┘

  ---
  A.4 v0.7.5 明确不做

  - 不做 move_entity / NPC 跟随系统（继续按 v0.7.3 review §Phase 2 方案 A：严格禁止隐式跟随，把 move_entity 放
  v0.7.6+）。
  - 不引入 NPC AI / belief autonomous update。
  - 不扩 hook / motif / hint 数量。
  - 不把语义检查替换成关键词。
  - 不动 legacy 路径任何行为。
  - 不接 UPF bridge。
  - 不引入 native function-calling（仍走 chat_json + retry + deterministic fallback）。

  ---
  A.5 v0.8 之后的 backlog（仅记录方向，本期不动）

  - move_entity + 显式 NPC follow（v0.7.3 review 方案 B）
  - 多 seed / 多场景与场景间地图
  - 复杂战斗与角色卡数值
  - 长期主线规划（plot graph 与 agentic 结合）
  - UPF bridge 复活（仅当上面 Ashen Vault 通过 50-turn 稳定后）