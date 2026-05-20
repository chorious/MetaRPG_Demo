# MetaRPG Simplified Code Reorg Plan

日期: 2026-05-20

来源:

- `docs/Opus/report_rearch.md`
- `docs/Opus/report_all_plan.md`
- `docs/reviews/reviewVer0.7.4.md`

---

## 0. 执行时机

这份计划不在 v0.7.5 主线修复前执行。

顺序必须是:

```text
1. 完成 v0.7.5 主线 correctness patch
2. smoke + play + targeted suite 验收通过
3. 再做代码结构重构
```

原因:

```text
现在系统仍有真实行为漏洞。
如果边修行为边重构结构,很难判断 regression 是逻辑问题还是移动文件造成的。
```

---

## 1. 重构目标

这次代码结构重构只解决:

```text
双轨并存
入口误导
命名错位
legacy / v0.7 边界不清
临时日志和 artifact 组织混乱
```

不解决:

```text
叙事质量
semantic judge 规则
NPC AI
地图导航
新 seed
```

重构第一阶段以 "soft reorg" 为主:

```text
加边界注释
加 interface doc
修 README / PROJECT_STATUS
标记 legacy/shared/v0.7 active
整理脚本和 runtime 文档
```

物理移动文件放到第二阶段。

---

## 2. 当前事实

必须先承认当前项目是双轨:

```text
legacy v0.6.6 writer-first:
  run_agentic_turn(...)
  Writer -> Translator -> Scanner -> Hard/Soft Auditor -> Editor/Scorecard
  play_cli.py / scripts/play_agentic.py 目前仍主要走这条线

v0.7.x transaction-first:
  run_agentic_turn_v070(...)
  Feasibility -> ReferenceResolver -> Frame -> Director -> Validator -> Committer -> Renderer -> Checker
  agentic_dungeon_smoke_test.py 主要走这条线
```

这两条线都还不能直接删除:

```text
legacy 仍服务 play / regression
v0.7 是当前主线 smoke / semantic constraint path
```

所以第一轮重构原则是:

```text
先标清楚,不急着删。
```

---

## 3. Phase 1 - Boundary Docs and Entry Truth

目标:

```text
任何人打开 README / runner / committer,能立刻知道自己在看哪条管线。
```

动作:

1. 在 `metarpg/agentic/runner.py` 顶部加 Pipeline Boundary 注释:

```text
run_agentic_turn      = legacy v0.6.6 writer-first, frozen
run_agentic_turn_v070 = v0.7 transaction-first, active
```

2. 在 `metarpg/agentic/committer.py` 顶部加说明:

```text
commit_turn / apply_admitted_patch = legacy
commit_transaction = v0.7 active
```

3. 在 `metarpg/agentic/schemas.py` 标记:

```text
transaction 类型 re-export deprecated
new code should import from metarpg.agentic.transaction
```

4. 更新 `README.md` / `PROJECT_STATUS.md`:

```text
交互式 play 当前入口是否 legacy,必须如实写。
v0.7 transaction-first 的入口也必须明确写。
```

验收:

```text
README 不再让用户误以为 play_cli 已经是 v0.7 transaction-first。
runner / committer / schemas 的边界一眼可见。
```

---

## 4. Phase 2 - v0.7 Interface Documentation

目标:

```text
把 v0.7 当成一个可编译/可审计的 interface system 来写清楚。
```

新增:

```text
docs/architecture/v0.7_interfaces.md
```

至少覆盖:

```text
WorldSeed
NarrativeGrammar
ReferenceResolution / ResolvedRef
NarrativeFrame
TurnTransaction
Operation
Commitment
ValidationResult
RenderBrief
SemanticJudgment
MotifSchedule
PostRenderResult
```

每个类型写:

```text
字段
生产者
消费者
允许谁修改
关键 invariant
相关 diagnostic code
```

验收:

```text
新增 v0.7 功能前,开发者能从 interface doc 找到正确写入点。
```

---

## 5. Phase 3 - Module Status Tags

目标:

```text
不移动文件,先给每个模块贴状态。
```

状态:

```text
Status: legacy v0.6.6 writer-first, frozen
Status: v0.7.x transaction-first, active
Status: shared primitive
Status: deprecated, planned removal after v0.8
```

优先标记:

```text
runner.py
committer.py
schemas.py
writer_agent.py
translator_agent.py
scanner.py
hard_auditor.py
soft_auditor_agent.py
editor_agent.py
scorecard.py
play_cli.py
transaction.py
transaction_validator.py
director_agent.py
render_brief.py
renderer_agent.py
semantic_judge.py
post_render_checker.py
render_repair.py
reference_resolver.py
hook_manager.py
motif_scheduler.py
world_graph.py
model_client.py
run_logger.py
```

验收:

```text
每个关键 agentic 模块顶部都有 Status 注释或 docstring。
```

---

## 6. Phase 4 - Scripts and Runtime Organization

目标:

```text
run 结果和脚本命名不再误导。
```

动作:

1. 脚本命名加版本语义:

```text
scripts/agentic_5turn_smoke_test.py      -> legacy_v066_5turn_smoke.py
scripts/agentic_dungeon_smoke_test.py    -> v070_dungeon_20turn_smoke.py
```

如果暂时不改文件名,至少 README 中必须写明对应关系。

2. runtime 文档:

```text
runtime/agentic_runs/README.md
```

说明两类 run:

```text
smoke artifact run:
  artifact_NNN_*.json
  events.jsonl
  errors.jsonl
  manifest.json / run_manifest.json
  analyze_agentic_run.py

play run:
  turn_NNN.json
  scorecard_NNN.json
  summary.md
  run_manifest.json
  analyze_play_run.py
```

3. 临时日志整理:

```text
smoke_test*.log 加 .gitignore
runtime 根目录散落 session_*.md / v065_*.log 移入 runtime/legacy_sessions/
```

验收:

```text
脚本名或 README 能明确说明 legacy vs v0.7。
runtime 下每类 run 都有文档说明。
```

---

## 7. Phase 5 - Prompt and Test Documentation

目标:

```text
Prompt 改动和测试归属可 review。
```

新增 prompt reference:

```text
docs/prompts/v0.7_director_prompt_reference.md
docs/prompts/v0.7_renderer_prompt_reference.md
docs/prompts/v0.7_semantic_judge_prompt_reference.md
```

每条 prompt rule 标注:

```text
引入版本
对应 bug / review
对应 diagnostic code
```

新增:

```text
tests/README.md
```

说明:

```text
test_vXXX_regression.py = 历史回归
test_<module>.py = 当前活跃模块测试
play-run tests = 真实体验门
smoke analyzer tests = artifact 指标门
```

验收:

```text
以后改 prompt 或测试,能知道它属于哪条线。
```

---

## 8. Phase 6 - Physical Reorg, Deferred

这一步暂缓,等 soft reorg 完成、v0.7.5 稳定后再做。

目标结构可以是:

```text
metarpg/
  core/
  legacy/
  bridge/
  agentic/
    legacy/
    v0_7/
```

但第一轮不要马上移动:

```text
不拆 runner.py
不拆 committer.py
不移动大量 imports
不删除 legacy
```

物理移动必须满足:

```text
full pytest baseline known
compatibility re-export planned
import graph checked
one commit only does move, no behavior change
```

---

## 9. 明确不做

代码重构阶段不做:

- 不修叙事行为 bug。
- 不改 SemanticJudge 逻辑。
- 不改 Validator 规则。
- 不改 Renderer prompt。
- 不引入新依赖。
- 不删除 legacy runner。
- 不删除 bridge。
- 不替换 `WorldState`。
- 不做 broad refactor mixed with behavior fixes。

---

## 10. Done Definition

第一轮代码结构重构完成条件:

```text
README / PROJECT_STATUS 入口描述准确
docs/architecture/v0.7_interfaces.md 存在
runner.py / committer.py / schemas.py 边界清楚
关键 agentic 模块有 Status 标记
runtime/agentic_runs/README.md 存在
tests/README.md 存在
v0.7 prompt reference 存在
临时日志不再散落或进入仓库
不引入行为差异
pytest 结果与整理前一致
```

第二轮再评估是否物理拆包。
