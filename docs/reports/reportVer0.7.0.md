# MetaRPG v0.7.0 执行报告 — Transaction-First Narrative Architecture

日期: 2026-05-19
执行者: Claude Code

---

## 1. 已完成的改动 (8 Phases)

### Phase 1 — Seed + Grammar Loader

- `metarpg/data/seeds/dnd_ashen_vault_seed.yaml` — Ashen Vault 地城种子
- `metarpg/data/narrative_grammar/dnd_dungeon_grammar.yaml` — 叙事语法定义
- `metarpg/agentic/seed_loader.py` — `load_seed() -> WorldSeed`
- `metarpg/agentic/narrative_grammar.py` — `load_grammar() -> NarrativeGrammar`
- `requirements.txt` — 添加 `pyyaml>=6.0`

### Phase 2 — Transaction Schema + Validator Skeleton

- `metarpg/agentic/transaction.py` — 核心数据类:
  `Operation`, `Commitment`, `NarrativeFrame`, `RenderBrief`,
  `TurnTransaction`, `ValidationIssue`, `DowngradeRecord`, `ValidationResult`
- `metarpg/agentic/transaction_validator.py` — 确定论验证核心
  - 硬约束检查: missing_item, absent_entity, unknown_location,
    relation/belief bounds, intra-turn contradiction, hidden_truth_direct_reveal
  - 降级路径: `canon -> utterance`, `reveal -> hint`, `new_item -> texture`
  - 语义降级器占位 (v0.7.1 接入 local vLLM)
- `tests/test_transaction_validator.py` — 13 tests

### Phase 3 — Hook / Hint / Beat Manager

- `metarpg/agentic/hook_manager.py` — `build_narrative_frame()`
  - 动作->节拍映射 (`inspect`->`inspection`, `ask`->`social_pressure`, ...)
  - Hook 匹配: subject/object 直接命中、模糊匹配、地点关联
  - Motif 选择: 玩家输入 + hook tension 文本匹配, 每回合最多 2 个
  - `_allowed_commitments_for_beat` 包含 universal `{"event", "utterance"}`
- `tests/test_hook_manager.py` — 7 tests

### Phase 4 — Director Agent

- `metarpg/agentic/director_agent.py` — `run_director()`
  - local vLLM 输出结构化 JSON (TurnTransaction)
  - `chat_json()` + Pydantic 重试一次
  - 失败时返回确定论 fallback transaction (`inner_monologue + texture`)
- `tests/test_director_agent.py` — 6 tests

### Phase 5 — Committer + WorldGraph Adapter

- `metarpg/agentic/world_graph.py` — `world_from_seed()`
  - 从 WorldSeed 初始化 WorldState
  - 确保 v0.7.0 扩展字段: `events`, `utterances`, `hints`, `affordances`, `_hook_status`
- `metarpg/agentic/committer.py` — 新增 `commit_transaction(world, tx)`
  - `_apply_operation`: `move_player`, `speak`, `transfer_item`, `update_relation`,
    `update_belief`, `mark_hook_status`, `add_event`
  - `_apply_commitment`: `event`, `utterance`, `affordance`
  - `texture`/`hint`/`belief_evidence` 为 no-op (纯叙事层, 不入 canon)
  - 不破坏 legacy `commit_turn()` 接口
- `tests/test_world_graph_commit.py` — 10 tests

### Phase 6 — DeepSeek Flash Renderer

- `metarpg/agentic/render_brief.py` — `build_render_brief()`
  - 从 transaction + frame + world 组装渲染简报
  - `committed_events` 取 `world.events[-3:]`
- `metarpg/agentic/renderer_agent.py` — `run_renderer()`
  - 唯一允许调用 DeepSeek Flash 的层
  - System prompt: 中文、不添加新事实、不泄露隐藏真相、不用 NPC 内心独白、使用 motif
- `tests/test_renderer_agent.py` — 4 tests

### Phase 7 — Post-render Checker

- `metarpg/agentic/post_render_checker.py` — `check_rendered_prose()`
  - 隐藏真相别名扫描 (case-insensitive)
  - NPC 内心独白检测 (中文指标: `心想`, `内心`, `暗自`, ...)
  - Debug / system 术语检测 (`DEBUG`, `SYSTEM`, `TRANSACTION`, ...)
  - 未提交事实占位 (v0.7.1 接入 NLI)
- `tests/test_post_render_checker.py` — 11 tests

### Phase 8 — Runner Switch + Playtest Harness

- `metarpg/agentic/runner.py` — 新增 `run_agentic_turn_v070()`
  - 完整管线: feasibility -> narrative_frame -> director -> validator ->
    committer -> render_brief -> renderer (Flash) -> post_render_checker
  - 验证拒绝时自动降级为 fallback transaction
  - 保留 legacy `run_agentic_turn()` 不变
- `scripts/agentic_dungeon_smoke_test.py` — CLI 脚本
  - 支持 `--turns N` (默认 3) 和 `--extended` (20-turn)
  - 逐 turn 输出 frame/transaction/validation/prose/post-render
- `tests/test_agentic_dungeon_smoke.py` — 3-turn MVP pytest 回归
  - Monkey-patch Director/Renderer/Feasibility, 无需 live LLM
  - 断言: inspection/social_pressure/threshold 节拍、utterance 不入 canon、
    move_player 改变世界状态、validation fallback 触发

---

## 2. 文件变更统计

### 新建 (14 个)

```
metarpg/agentic/seed_loader.py
metarpg/agentic/narrative_grammar.py
metarpg/agentic/hook_manager.py
metarpg/agentic/director_agent.py
metarpg/agentic/transaction.py
metarpg/agentic/transaction_validator.py
metarpg/agentic/world_graph.py
metarpg/agentic/render_brief.py
metarpg/agentic/renderer_agent.py
metarpg/agentic/post_render_checker.py
metarpg/data/seeds/dnd_ashen_vault_seed.yaml
metarpg/data/narrative_grammar/dnd_dungeon_grammar.yaml
scripts/agentic_dungeon_smoke_test.py
tests/test_*.py (8 个新测试文件)
```

### 修改 (1 个)

```
metarpg/agentic/runner.py          # 新增 run_agentic_turn_v070 +  imports
metarpg/agentic/committer.py       # 新增 commit_transaction
metarpg/agentic/schemas.py         # 追加 transaction 类型 re-export
requirements.txt                   # 添加 pyyaml>=6.0
```

---

## 3. 测试状态

**全部 362 个测试通过。**

| 测试文件 | 数量 | 说明 |
|---|---|---|
| `test_seed_loader.py` | 8 | 种子加载、字段完整性 |
| `test_transaction_validator.py` | 13 | 硬约束、降级路径 |
| `test_hook_manager.py` | 7 | 节拍选择、hook 匹配、motif 选择 |
| `test_director_agent.py` | 6 | schema 解析、重试、fallback |
| `test_world_graph_commit.py` | 10 | world_from_seed、commit_transaction |
| `test_renderer_agent.py` | 4 | render_brief、renderer 调用 |
| `test_post_render_checker.py` | 11 | 别名泄露、内心独白、debug 术语 |
| `test_agentic_dungeon_smoke.py` | 2 | 3-turn MVP、validation fallback |
| 原有回归测试 | 301 | v0.1 ~ v0.6.4 全部保持绿色 |

---

## 4. Smoke Test 结果 (v0.7.0)

### 3-turn MVP (mocked, 确定性)

```
tests/test_agentic_dungeon_smoke.py .. (2 passed)
```

- Turn 1 `inspect` -> `inspection` beat, event + hint + affordance committed
- Turn 2 `ask` -> `social_pressure` beat, utterance committed (不入 canon facts)
- Turn 3 `move` -> `threshold_crossing` beat, player location updated
- Validation fallback: 消费不存在的物品 -> rejected -> fallback committed

### Real LLM 脚本 (3 turns, 实际 endpoint)

```bash
python scripts/agentic_dungeon_smoke_test.py --turns 3
```

结果:
- 3/3 turns 完成, 0 errors
- 3/3 fallback (local vLLM 未运行, Director 降级为 fallback)
- DeepSeek Flash Renderer 正常工作, 输出中文叙事散文
- Post-render checker 3/3 pass
- 总耗时 ~48s (avg 16s/turn, 主要耗时在 Flash renderer)

---

## 5. 架构对比: v0.6.x vs v0.7.0

| 维度 | v0.6.x (Writer-First) | v0.7.0 (Transaction-First) |
|---|---|---|
| 核心中间件 | `WriterOutput` (散文+patch) | `TurnTransaction` (operations+commitments) |
| 世界变更来源 | Writer 散文 -> Translator -> patch | Director 结构化 JSON -> Validator -> Committer |
| 渲染层权限 | Writer 可隐式提交世界事实 | Renderer (Flash) **只渲染, 不提交** |
| 安全层位置 | 后置 (Hard Auditor 追散文) | 前置 (Validator 审 transaction) |
| LLM 路由 | Bold+Safe 都走 Flash/Qwen | **Flash 仅限 Renderer**, 其余默认 local vLLM |
| Fallback | refusal_fallback 模板 | Director fallback transaction + Validator fallback |
| NPC 内心独白 | Soft Auditor 后置检测 | 禁止出现在 frame + post-render checker 二次扫描 |

---

## 6. 已知限制与 v0.7.1 方向

### L1 — local vLLM 未接入时的全 fallback

当前 Director 依赖 local vLLM (`http://192.168.50.20:8101`) 输出结构化 JSON。
如果 local vLLM 不可达, 每 turn 都降级为 `inner_monologue + texture` fallback,
虽然安全但无叙事推进。

**v0.7.1**: 接入本地 Qwen3.6-27b-nvfp4 endpoint, 评估 Director schema 一次解析成功率。

### L2 — Feasibility -> Intent 映射过于简单

`_feasibility_to_intent()` 用硬编码动词表做归一化, 对复杂输入可能误判为 `ambiguous`。

**v0.7.1**: 用 local vLLM 做轻量级意图分类, 或扩展动词表。

### L3 — Post-render 未提交事实检测为占位

`_find_uncommitted_facts()` 返回空列表 (MVP 故意保守)。

**v0.7.1**: 接入 local vLLM NLI (Natural Language Inference) 判断 prose 中的实体
是否超出 transaction/world 范围。

### L4 — Director 未使用 native tool-calling

当前用 `chat_json()` + prompt 描述 schema, 靠重试保证解析。

**v0.7.1**: 若重试率 >10%, 评估 vLLM native tool-calling / structured generation
(OpenAI-compatible `response_format` 或 json_schema)。

### L5 — 20-turn 扩展未验证

3-turn MVP 通过, 但 20-turn 长程稳定性 (hook 推进、motif 变化、无泄漏)
需要 live LLM 才能验证。

**v0.7.1**: 运行 `python scripts/agentic_dungeon_smoke_test.py --extended`
并产出 report。

---

## 7. 建议的下一步

1. **启动 local vLLM** (`qwen3.6-27b-nvfp4` @ `192.168.50.20:8101`)
2. **运行 real LLM 3-turn MVP**: `python scripts/agentic_dungeon_smoke_test.py --turns 3`
3. **观察 Director 输出质量**: schema 一次解析成功率、fallback 率
4. **若 3-turn 通过, 扩展到 20-turn**: `--extended`
5. **根据 20-turn 结果决定**:
   - 是否给 Director 加 native tool-calling
   - 是否优化 Feasibility prompt 以提升 intent 准确率
   - 是否启用 post-render NLI 层
