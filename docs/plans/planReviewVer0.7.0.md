# planReviewVer0.7.0 - Narrative Transaction Architecture Review

日期: 2026-05-19

评审对象:

- `docs/plans/planVer0.7.0.md`
- `C:\Users\MUSHI\.claude\plans\jazzy-kindling-koala.md`

---

## 0. 总体结论

`planVer0.7.0.md` 的主方向通过。

v0.7.0 应该正式从 v0.6.x 的 Writer-first / Auditor-after-the-fact 架构,切换到 **Narrative Transaction Architecture**:

```text
Narrative Grammar
  -> NarrativeFrame
  -> Director 生成 TurnTransaction
  -> Validator 接受/降级/拒绝
  -> Committer 写 WorldGraph
  -> DeepSeek Flash Renderer 输出玩家文本
  -> Post-render Checker 做轻量防线
```

这个方向比单纯 "Function Calling 替代 JSON" 更接近项目愿景:

```text
内部叙事框架负责骨架和张力。
LLM 负责 motif 变奏和局部文学渲染。
WorldGraph 负责记录什么被承诺为真。
规则层负责决定什么能被提交。
```

严厉判断:

```text
能落地。
但落地版本会是有限场域内的结构化跑团引擎,不是任意开放世界的全自动 GM。
```

v0.7.0 的 scope 选择 DND-like 地城探索是正确的。它足够小,但能覆盖 hook、hint、threshold、enigma、debt、motif、hidden truth、render quality 等核心机制。

---

## 1. 与预期一致的部分

当前 `planVer0.7.0.md` 已经抓住了四个关键点。

### 1.1 散文不再承担世界提交职责

这是最大修正。

v0.6.x 的根本问题不是 Auditor 不够聪明,而是让散文同时承担:

```text
玩家体验
世界变更声明
后续事实来源
审计对象
```

这四个职责混在一起,必然导致误杀、漏杀、fallback 和事实污染。

v0.7.0 把 prose 降回 render 层,把世界变更提升为 TurnTransaction,这是正确的层级划分。

### 1.2 DeepSeek Flash 只做 Render

这个模型路由合理:

```text
DeepSeek Flash: 最终中文 prose / motif 变奏 / 感官节奏
local vLLM: intent、frame、director、validator 辅助、post-check
```

Flash 的优势是语言质量和场景质感,不应该让它承担世界提交、隐藏事实边界、hook 状态迁移这些机械约束。

### 1.3 Narrative Grammar 是必要层

Hook / Hint / Beat / Motif 不是剧情硬编码,而是叙事语法。

有限 hook 类型:

```text
lack
enigma
threshold
debt
contradiction
threat_timer
```

有限 hint 类型:

```text
gesture_hint
object_hint
speech_hint
absence_hint
spatial_hint
time_hint
```

这些结构能让 LLM 有骨架可依,但不替 LLM 写剧情。

### 1.4 DND Ashen Vault seed 合适

这个 seed 适合作为 v0.7.0 验收对象:

```text
入口厅
受伤 NPC Alen
黑灰 clue
封闭下层门
潮湿阶梯
隐藏的圣匣 / 铃声机制
```

它包含:

```text
社交张力
谜题张力
门槛张力
时间压力
隐藏真相
motif 复用
```

足够验证架构,又不会膨胀成完整 DND 战斗系统。

---

## 2. CC roadmap 的价值

Claude Code 输出的 `jazzy-kindling-koala.md` 大方向与 `planVer0.7.0.md` 一致,可以作为实施 checklist 使用。

它的主要价值是补了几条工程细节。

### 2.1 吸收: PyYAML 依赖

CC plan 指出 seed/grammar 使用 YAML,项目需要显式增加 PyYAML。

建议加入 Phase 1:

```text
requirements.txt / pyproject.toml 增加 PyYAML
tests/test_seed_loader.py 覆盖 YAML load
```

如果项目不想加依赖,也可以改用 JSON/TOML。但从可编辑性看,YAML 更适合 seed/grammar。

### 2.2 吸收: Director 先用 chat_json + Pydantic retry

CC plan 对 tool-calling 做了务实降级:

```text
先用 local vLLM chat_json + schema validation + retry。
不要第一步就依赖 vLLM native tool calling。
```

建议采纳。

v0.7.0 的关键是 transaction-first,不是必须第一天就完成 native function calling。

推荐路径:

```text
Phase 4:
  local vLLM -> JSON
  Pydantic/dataclass validation
  schema failure retry once
  still fail -> deterministic fallback transaction

Phase 4.5 / v0.7.1:
  评估 native tool calling 是否值得接入
```

### 2.3 吸收: legacy runner baseline

CC plan 建议保留 v0.6 legacy runner。

这很重要。

建议:

```python
run_agentic_turn_legacy(...)
run_agentic_turn_v070(...)
```

或者通过 config:

```text
agentic_pipeline = legacy | transaction
```

原因:

```text
1. 方便对照 Greyfen baseline。
2. 防止 v0.7.0 大改时破坏现有 smoke tests。
3. 可以用同一输入比较 writer-first vs transaction-first 的输出质量。
```

### 2.4 吸收: 现有模块复用表

CC plan 列出的 reuse 表有实际价值。

建议在实施任务中明确:

```text
feasibility.py      -> Intent/Feasibility
story_packet.py     -> 扩展 hooks/hints/motifs
model_client.py     -> flash/local router
committer.py        -> 新增 transaction commit path
scanner.py          -> post-render deterministic alias scan
time_flow.py        -> pre-turn primitive
entity_lifecycle.py -> pre-turn primitive
offscreen_tick.py   -> pre-turn primitive
```

这可以避免新架构变成完全重写。

---

## 3. 需要修正的风险点

### 3.1 Validator 不能写成纯 deterministic

CC plan 表格里把 Transaction Validator 写成 deterministic。

这不够。

建议拆成两层:

```text
Validator Core:
  deterministic, hard constraints only

Semantic Downgrader:
  local vLLM optional,用于 reveal->hint、canon->utterance、new_item->texture 等语义降级
```

原因:

```text
物品归属、实体在场、relation_delta 边界可以确定性判断。
但 "这句话是 reveal 还是 hint"、"这个细节是否构成新事实" 需要语义辅助。
```

最终接口建议:

```python
validate_transaction(tx, world, grammar) -> ValidationResult

ValidationResult:
    status: accepted | downgraded | rejected
    validated_transaction: TurnTransaction
    issues: list[ValidationIssue]
    downgrades: list[DowngradeRecord]
```

### 3.2 配置不能硬编码

CC plan 写了当前 local vLLM 地址:

```text
http://192.168.50.20:8101
qwen3.6-27b-nvfp4
```

文档里作为说明可以,实现中不能硬编码。

必须从:

```text
E:\GameDesign\MetaRPG_Dev\set.env
```

读取:

```text
base_url
flash_model
api_key
local_url
local_model
```

并保持:

```text
make_client("flash") -> Render
make_client("local") -> all non-render LLM calls
```

### 3.3 不要直接破坏 `commit_turn()` 旧接口

CC plan 建议把:

```python
commit_turn(world, candidate_patch, segments)
```

直接改成:

```python
commit_turn(world, validated_transaction)
```

风险偏高。

建议 v0.7.0 使用新增接口:

```python
commit_transaction(world, validated_transaction)
```

旧接口保留:

```python
commit_turn(world, admitted_patch, final_segments)
```

迁移顺序:

```text
Phase 5:
  新增 commit_transaction
  新 tests 覆盖 transaction path
  legacy tests 继续走 commit_turn

v0.7.1:
  视情况统一接口
```

### 3.4 Smoke test 不应只放 scripts

CC plan 建议:

```powershell
pytest scripts/agentic_dungeon_smoke_test.py -v
```

更好的结构:

```text
scripts/agentic_dungeon_smoke_test.py       # 手动/长跑
tests/test_agentic_dungeon_smoke.py         # pytest 回归入口
```

scripts 可以输出完整 run artifact。
tests 应该做可控、较短、可断言的 smoke。

### 3.5 `crystallize.py` 的职责必须明确降级

当前 plan 已写:

```text
crystallize 不再自动把散文写入 canon。
```

实施时要更硬:

```text
Renderer prose -> 不可直接 crystallize 到 WorldGraph。
crystallize 只能产出 PossibleCommitmentProposal。
Proposal 必须经过 transaction_validator 才能进入 world。
```

否则旧问题会从后门回来。

### 3.6 Post-render Checker 不要重新长成 Hard Auditor

Post-render Checker 的边界必须非常窄:

```text
检查 Renderer 是否偷加 transaction 外世界承诺。
检查 hidden_truth alias / NPC inner monologue / debug terms。
失败则 light repair。
```

它不应该重新判断:

```text
hook 是否合理
relation_delta 是否过大
NPC speech 是否有 patch support
物品是否存在
```

这些都应该在 Transaction Validator 里完成。

---

## 4. 建议的修订项

建议把以下内容补进 `planVer0.7.0.md` 或作为实施 issue。

### 4.1 Phase 1 增加依赖决策

```text
Add PyYAML or choose JSON/TOML.
Recommended: PyYAML, because seed/grammar is author-facing config.
```

### 4.2 Phase 2 明确 ValidationResult

补充:

```python
ValidationResult:
    status: Literal["accepted", "downgraded", "rejected"]
    transaction: TurnTransaction | None
    issues: list[ValidationIssue]
    downgrades: list[DowngradeRecord]
```

### 4.3 Phase 4 明确 schema validation 策略

补充:

```text
local vLLM Director first uses chat_json + Pydantic validation.
Retry once with validation errors.
If still invalid, deterministic fallback transaction.
Native tool calling is not a v0.7.0 blocker.
```

### 4.4 Phase 5 使用 adapter + 新 commit 接口

补充:

```text
WorldGraph adapter wraps existing WorldState.
Do not replace models.py in v0.7.0.
Add commit_transaction instead of breaking commit_turn.
```

### 4.5 Phase 8 拆分 script 和 pytest

补充:

```text
scripts/agentic_dungeon_smoke_test.py
tests/test_agentic_dungeon_smoke.py
```

### 4.6 保留 legacy runner

补充:

```text
run_agentic_turn_legacy remains callable.
run_agentic_turn defaults can switch by config after v0.7.0 smoke passes.
```

---

## 5. 实施优先级建议

不要先重写 `runner.py`。

正确顺序:

```text
1. Seed + Grammar loader
2. Transaction dataclasses
3. Validator core
4. commit_transaction
5. HookManager deterministic MVP
6. Director mock / local vLLM schema output
7. RenderBrief + Flash Renderer
8. Post-render checker
9. 最后切 runner
```

原因:

```text
runner 是集成层。
先改 runner 会让所有未完成模块一起失败,调试成本极高。
```

建议前 5 个 phase 都用 mock transaction / fixture 测,等模块闭合后再端到端。

---

## 6. 最小 MVP 切片

为了避免 v0.7.0 scope 过大,建议先做一个 3-turn MVP。

### Turn 1

玩家:

```text
我检查门槛上的黑灰。
```

期望:

```text
Intent: inspect black_ash
Frame: enigma / inspection / motif black_ash
Transaction: inspect_event + hint + affordance(compare_ash / ask_alen)
Commit: event + hook engaged
Render: DeepSeek Flash 写黑灰的气味/触感,不 reveal hidden truth
```

### Turn 2

玩家:

```text
我问艾伦这灰是怎么回事。
```

期望:

```text
Frame: social_pressure + enigma
Transaction: alen utterance + belief_evidence,不直接 canonize
Commit: utterance + belief delta
Render: Alen 回避/含糊,给 speech_hint
```

### Turn 3

玩家:

```text
我去看那扇封闭的下层门。
```

期望:

```text
Frame: threshold
Transaction: move/inspect lower_door + hint_door_three_marks
Commit: event + hook_lower_door_threshold surfaced
Render: 门、黑灰、无声铃 motif 变奏
```

这个 3-turn MVP 如果跑通,再扩到 20-turn smoke。

---

## 7. 最终判断

`planVer0.7.0.md` 是当前项目最合理的技术方向。

它正确放弃了:

```text
自动理解散文并直接固化世界
靠 Hard Auditor 关键词/claim 追杀维持一致性
让 Writer 同时负责创作和世界提交
```

它转向了:

```text
有限叙事语法
结构化 TurnTransaction
WorldGraph commit
DeepSeek Flash 专职 render
local vLLM 做规划和语义辅助
```

需要警惕的是:

```text
不要让 Validator 过度僵硬。
不要让 Post-render Checker 重新变成大 Auditor。
不要在 v0.7.0 一步重写所有旧接口。
不要把 DND seed 扩张成完整 DND 规则系统。
```

推荐状态:

```text
planVer0.7.0.md 作为架构真源。
CC roadmap 作为实施 checklist。
本 review 中的 PyYAML / Pydantic retry / legacy runner / commit_transaction 修正应吸收进具体开发任务。
```

---

## 8. 一句话总结

> **v0.7.0 的计划方向是对的:不是让 Auditor 更会读散文,而是让散文退出世界提交路径。下一步实施要保持 transaction-first 的架构纪律,同时务实吸收 CC roadmap 的 loader、schema retry、legacy baseline 等工程细节。**
