B. 项目代码整理计划（仅文档，不动代码）

  ▎ 目的：消除 v0.7.x 累积的"双轨并存 + 旁路 + 命名错位"问题，使新人 /
  ▎ 自己半年后还能理解。不做行为变更，只做归类、说明、命名、删除标记。 优先级 P0 > P1 > P2。

  ---
  B.1 当前结构问题（事实）

  1. metarpg/agentic/runner.py 1166 行，同时持有两条管线：
    - run_agentic_turn(...) — v0.6.6 Bold/Safe writer-first。
    - run_agentic_turn_v070(...) — v0.7.x transaction-first。
  两条共享同一文件、同一 import block，但调用栈完全不同。_feasibility_to_intent 这种 legacy helper 已经没人调用。
  2. metarpg/agentic/committer.py 同时持有：
    - apply_admitted_patch / commit_turn — legacy。
    - commit_transaction / _apply_operation / _apply_commitment — v0.7.x。
  写在一个文件里，没有命名前缀，读者无法 5 秒看出哪个是新路径。
  3. metarpg/agentic/schemas.py 末尾 re-export v0.7 transaction 类型，造成 Commitment / Operation 在 schemas 和
  transaction 两处都能 import；新人易写错。
  4. legacy-only 模块仍住在 agentic 包内：writer_agent / translator_agent / scanner / hard_auditor / soft_auditor_agent
  / editor_agent / repair_loop / refusal_fallback / parallel_dispatch / feasibility / crystallize / teacher_agent /
  scorecard / eval_runner / belief_tracker / entity_lifecycle / time_flow / offscreen_tick / lore_conflict。其中一部分是
   v0.6 Bold/Safe 专用，一部分是 v0.7 仍在用的 primitive。没有任何标记。
  5. metarpg/agentic/play_cli.py 仍走 legacy run_agentic_turn；scripts/play_agentic.py 走 play_cli。也就是说交互式 CLI
  玩的还是 v0.6.6，不是 v0.7.x。这与 README/PROJECT_STATUS 的描述存在显式矛盾。
  6. scripts/agentic_5turn_smoke_test.py 还在跑 legacy，scripts/agentic_dungeon_smoke_test.py 跑 v0.7.x。两个 smoke
  文件名不带版本标记。
  7. metarpg/ 根目录 仍住着 v0.1~v0.5 deterministic engine 的全部模块（engine.py / proposer.py / assembler.py /
  metaact.py / claims.py / dsl.py / parsing.py / world.py / cli.py / narrator.py / scenario_hooks.py / hookgen.py /
  hookmatch.py / hooks.py / affordance*.py / retrodict.py / plot_graph.py / plot_diagnose.py / scene_expand.py /
  frontier.py / expansion_budget.py / action_contract.py / apply_event.py / apply_report.py / events.py /
  export_snapshot.py / session_logger.py / rules.py / models.py / beliefs.py / bridge*.py）。ARCHITECTURE_REORG_PLAN.md
  (§3) 早就规定应该分 core/ / legacy/ / agentic/ / bridge/，但只在文档里。
  8. runtime/ 根目录 散落 25+ 个 session_*.md（旧 legacy CLI 输出）和 2 个 v065_*.log，混在 agentic_runs/ 与
  bridge_sessions/ 旁边。
  9. 根目录残留 smoke_test.log / smoke_test_v073.log / smoke_test_v073_clean.log 这些是临时 run 输出，不该 commit。
  10. docs/ 已经按 plan/review/report/architecture/prompts/archive/diary 分类（OK），但：
    - architecture/v0.6_interfaces.md 只覆盖 v0.6，v0.7.x 的 Transaction / NarrativeFrame / RenderBrief /
  SemanticJudgment 没有 interface doc。
    - prompts/ 只有一份 v0.6 reference，没有 v0.7 Director / Renderer / SemanticJudge 三个 prompt 的稳定参考。
    - archive/old_plans/ 内已经有 v0.5.x 与 v0.6.3 / v0.6.4 的 plan，但 v0.7.0 阶段的 planReviewVer0.7.0.md 仍住在
  docs/plans/ —— review 性质，应该归 docs/reviews/ 或 docs/archive/old_plans/。
  11. 测试命名分裂：test_v021_regression / test_v031_regression / ... / test_v064_regression
  是按版本归档；test_writer_modes / test_intent_fulfillment / ... 是按模块。没有约定也没有目录区分。

  ---
  B.2 整理动作清单（按优先级排序，全部仅文档/移动/重命名，不改行为）

  P0 — 立即必要，不做会持续误导读者

  编号: P0-1
  动作: 在 metarpg/agentic/runner.py 文件顶部加一段 === Pipeline boundary === 注释，明确指明 run_agentic_turn (legacy)
  与
    run_agentic_turn_v070 (current) 各自调用图、保留 / 弃用状态、是否仍接受新功能
  目标: 防止下一个开发者改错路径
  风险: 0
  ────────────────────────────────────────
  编号: P0-2
  动作: 在 committer.py 顶部加 docstring：明确 commit_turn 只供 legacy runner，commit_transaction 是 v0.7
    入口；在两个函数 docstring 内交叉指向
  目标: 同上
  风险: 0
  ────────────────────────────────────────
  编号: P0-3
  动作: 把 metarpg/agentic/schemas.py 末尾的 from metarpg.agentic.transaction import (...) re-export 改成 文档级标注
    "deprecated re-export, prefer metarpg.agentic.transaction directly"（先不删，避免破坏 import；只标
  deprecated）。落到
     docs/architecture/v0.7_interfaces.md 一并说明
  目标: 减少新代码沿用错路径
  风险: 0
  ────────────────────────────────────────
  编号: P0-4
  动作: 新建 docs/architecture/v0.7_interfaces.md，记录 WorldSeed / NarrativeGrammar / NarrativeFrame / TurnTransaction
  /
    RenderBrief / SemanticJudgment / ValidationResult / MotifSchedule / ResolvedIntent
    全部字段、生产者、消费者、约束。结构参考现有 v0.6_interfaces.md
  目标: 当前 v0.7 完全没有 interface doc
  风险: 0
  ────────────────────────────────────────
  编号: P0-5
  动作: 把 docs/plans/planReviewVer0.7.0.md 移到 docs/reviews/planReviewVer0.7.0.md（性质是 review 不是 plan）
  目标: 命名一致
  风险: 极低
  ────────────────────────────────────────
  编号: P0-6
  动作: 把根目录 smoke_test.log / smoke_test_v073.log / smoke_test_v073_clean.log 列入 .gitignore
    并从仓库移除（保留本地）。同时在 runtime/ 根目录的 session_*.md / v065_*.log 移到 runtime/legacy_sessions/
  目标: 阻止临时日志再被 commit
  风险: 低
  ────────────────────────────────────────
  编号: P0-7
  动作: 同步 README.md：交互式 CLI 当前仍是 legacy v0.6.6 (python -m metarpg.cli 与 play_agentic.py → play_cli)。README
    里说 "Current line (v0.6.6.1): agentic LLM pipeline — StoryPacket → Writer → ..." 与 PROJECT_STATUS 说的 v0.7.x
    已经发生分歧，需要明确写"交互式默认仍为 v0.6.6 legacy；v0.7.x transaction-first 只通过 agentic_dungeon_smoke_test.py

    入口"
  目标: 防止用户运行 README 命令以为是 v0.7
  风险: 0

  P1 — 半个版本内做，不影响代码行为，只整理可读性

  编号: P1-1
  动作: 在 metarpg/agentic/ 内引入两个虚拟分组目录的命名约定（先不真的移文件，只在 docs/architecture/v0.7_interfaces.md
    里登记归属）：v0.7 transaction-first 主链路：runner.py::run_agentic_turn_v070 / seed_loader.py /
  narrative_grammar.py
     / world_graph.py / reference_resolver.py / hook_manager.py / motif_scheduler.py / transaction.py /
    transaction_validator.py / director_agent.py / committer.py::commit_transaction / render_brief.py /
  renderer_agent.py
     / render_repair.py / post_render_checker.py / semantic_judge.py / model_client.py / run_logger.pyv0.6 legacy
    Bold/Safe：runner.py::run_agentic_turn / writer_agent.py / translator_agent.py / scanner.py / hard_auditor.py /
    soft_auditor_agent.py / editor_agent.py / repair_loop.py / refusal_fallback.py / feasibility.py /
    parallel_dispatch.py / crystallize.py / teacher_agent.py / scorecard.py / eval_runner.py / play_cli.py /
    committer.py::apply_admitted_patch + commit_turn / schemas.py两边共用  primitive：time_flow.py / entity_lifecycle.py

    / offscreen_tick.py / belief_tracker.py / lore_conflict.py / story_packet.py
  目标:
  ────────────────────────────────────────
  编号: P1-2
  动作: 每个 legacy-only 文件顶部 docstring 加 Status: legacy (v0.6.6, frozen)；每个 v0.7-only 文件加 Status: v0.7.x
    (active)；每个共用 primitive 加 Status: shared
  目标: 让 import 时就能看出归属
  ────────────────────────────────────────
  编号: P1-3
  动作: 重命名 smoke 脚本（仅文件名变化，import 全是绝对路径，影响极小，更新 README
    即可）：scripts/agentic_5turn_smoke_test.py →
  scripts/legacy_v066_5turn_smoke.pyscripts/agentic_dungeon_smoke_test.py
     → scripts/v070_dungeon_20turn_smoke.py
  目标: 名字立刻说出版本
  ────────────────────────────────────────
  编号: P1-4
  动作: 新建 docs/prompts/v0.7_director_prompt_reference.md + v0.7_renderer_prompt_reference.md +
    v0.7_semantic_judge_prompt_reference.md，把现在散在 director_agent.py / renderer_agent.py / semantic_judge.py 里的
    system prompt 抄出来 + 注明每条规则的引入版本（v0.7.0 / .1 / .2 / .3 / .4）
  目标: 让 prompt 改动可被 review
  ────────────────────────────────────────
  编号: P1-5
  动作: 在 tests/ 下加 README.md 说明命名约定：test_vXXX_regression.py = 按版本归档；按模块名命名的 =
    当前活跃。同时给当前活跃测试加目录前缀标签，不动文件
  目标: 让谁该跑、谁不该删一目了然
  ────────────────────────────────────────
  编号: P1-6
  动作: runtime/agentic_runs/ 增加 README.md 描述每个 run 目录内文件含义（events.jsonl / errors.jsonl /
    artifact_NNN_*.json / 未来的 manifest.json），并写明 analyze_agentic_run.py --json 是唯一指标真源
  目标: 与 ARCHITECTURE_REORG_PLAN §7 对齐
  ────────────────────────────────────────
  编号: P1-7
  动作: 在 docs/architecture/ 加 pipeline_v0.7_vs_v0.6.md 一张大对照表，把 P1-1 的分组、调用图、入口、为什么保留 legacy
    写清楚
  目标: 替代散落在 review 中的零散说明

  P2 — 等 v0.7.5 落地后再做，是物理移动而不是命名

  编号: P2-1
  动作: 按 ARCHITECTURE_REORG_PLAN §3 物理拆包：metarpg/legacy/ ← engine.py / proposer.py / assembler.py / metaact.py /
    claims.py / dsl.py / parsing.py / cli.py / narrator.py / session_logger.pymetarpg/core/ ← models.py / world.py /
    rules.py / hooks.py / hookmatch.py / hookgen.py / frontier.py / affordance*.py / retrodict.py / plot_graph.py /
    plot_diagnose.py / scene_expand.py / expansion_budget.py / action_contract.py / apply_event.py / apply_report.py /
    events.py / beliefs.py / scenario_hooks.pymetarpg/bridge/ ← bridge.py / bridge_protocol.py / bridge_session.py /
    export_snapshot.pymetarpg/agentic/ 保持但分子目录 agentic/legacy/ 与 agentic/v0_7/
  目标: 但只能在 v0.7.5 验收通过且 import 全部测过之后做；先用 compatibility re-export 兼容旧 import
  ────────────────────────────────────────
  编号: P2-2
  动作: agentic/legacy/ 内的 writer_agent / translator_agent / scanner / hard_auditor / soft_auditor_agent /
  editor_agent
    / repair_loop / refusal_fallback / parallel_dispatch / feasibility / crystallize / teacher_agent / scorecard /
    eval_runner / play_cli 全部物理迁移；committer.py 拆为 agentic/legacy/committer.py(apply_admitted_patch +
    commit_turn) 与 agentic/v0_7/committer.py(commit_transaction)；schemas.py 拆为 agentic/legacy/schemas.py 与
    agentic/v0_7/transaction.py（后者已存在）
  目标: 物理消除"同文件两路径"问题
  ────────────────────────────────────────
  编号: P2-3
  动作: 在 docs/archive/old_plans/ 内加入 planVer0.7.0.md / planVer0.7.2.1.md 的复本，仅当 v0.7.5 plan 写完时；当前 plan

    留在 docs/plans/ 即可
  目标: 历史可追溯
  ────────────────────────────────────────
  编号: P2-4
  动作: 评估是否合并 metarpg/data/seeds/dnd_ashen_vault_seed.yaml 旁边新增多 seed 支持；本期不做，仅在文档登记
  目标: 留作 v0.8 入口

  ---
  B.3 删除候选（先不删，只在文档登记 deprecated）

  这些已经被新路径完全替代、且没有 caller 在主链路上，但仍可能被某个 regression test 引用。请先在
  docs/architecture/v0.7_interfaces.md 写 "deprecated, planned removal in v0.8"，等 v0.7.5 落地后再用 grep 确认零 caller
   才删：

  - metarpg/agentic/runner.py::_feasibility_to_intent（v0.7.0 后没人调）
  - metarpg/agentic/repair_loop.py（被 v0.7.3 render_repair.py 替代；legacy runner 也没有真的接它）
  - metarpg/agentic/editor_agent.py（v0.6.6 Bold/Safe 已不走 editor）
  - metarpg/agentic/teacher_agent.py（PROJECT_STATUS freeze rule 明令"No Teacher code mutation"）
  - metarpg/agentic/eval_runner.py（被 scripts/analyze_agentic_run.py 替代）

  ---
  B.4 不要做（防止整理过头）

  - 不动 metarpg/agentic/runner.py 双路径并存；只加注释，不拆函数，直到 v0.7.5 验收通过。
  - 不删 legacy writer_agent / translator_agent / hard_auditor / soft_auditor_agent / scanner / refusal_fallback /
  parallel_dispatch / feasibility / crystallize：它们还服务 run_agentic_turn 与多个 test_vXXX_regression。
  - 不动 models.py：v0.7 world_graph.py 是 adapter，不替换 WorldState（来自 planReviewVer0.7.0 §3.3）。
  - 不动 bridge*.py：UPF bridge 仍在冻结期。
  - 不重命名 runtime/agentic_runs/ 内已有 run 目录。
  - 不引入新依赖（PyYAML 已存在；不要为整理加 pydantic / typer 等）。
  - 不在整理同一 commit 内修任何 bug（即使顺手发现）；按 ARCHITECTURE_REORG_PLAN §10 "No broad refactor mixed with
  behavior fixes"。

  ---
  B.5 整理 Done Definition

  - docs/architecture/v0.7_interfaces.md 存在并覆盖所有 v0.7 dataclass + producer/consumer。
  - runner.py / committer.py / schemas.py 头部注释明确说明 legacy vs v0.7 边界与 deprecated re-export。
  - README.md 与 PROJECT_STATUS.md 描述与运行入口一致（v0.6.6 交互 + v0.7.x smoke）。
  - metarpg/agentic/repair_loop.py（被 v0.7.3 render_repair.py 替代；legacy runner 也没有真的接它）
  - metarpg/agentic/editor_agent.py（v0.6.6 Bold/Safe 已不走 editor）
  - metarpg/agentic/teacher_agent.py（PROJECT_STATUS freeze rule 明令"No Teacher code mutation"）
  - metarpg/agentic/eval_runner.py（被 scripts/analyze_agentic_run.py 替代）

  ---
  B.4 不要做（防止整理过头）

  - 不动 metarpg/agentic/runner.py 双路径并存；只加注释，不拆函数，直到 v0.7.5 验收通过。
  - 不删 legacy writer_agent / translator_agent / hard_auditor / soft_auditor_agent / scanner / refusal_fallback / parallel_dispatch / feasibility / crystallize：它们还服务 run_agentic_turn 与多个
  test_vXXX_regression。
  - 不动 models.py：v0.7 world_graph.py 是 adapter，不替换 WorldState（来自 planReviewVer0.7.0 §3.3）。
  - 不动 bridge*.py：UPF bridge 仍在冻结期。
  - 不重命名 runtime/agentic_runs/ 内已有 run 目录。
  - 不引入新依赖（PyYAML 已存在；不要为整理加 pydantic / typer 等）。
  - 不在整理同一 commit 内修任何 bug（即使顺手发现）；按 ARCHITECTURE_REORG_PLAN §10 "No broad refactor mixed with behavior fixes"。

  ---
  B.5 整理 Done Definition

  - docs/architecture/v0.7_interfaces.md 存在并覆盖所有 v0.7 dataclass + producer/consumer。
  - runner.py / committer.py / schemas.py 头部注释明确说明 legacy vs v0.7 边界与 deprecated re-export。
  - README.md 与 PROJECT_STATUS.md 描述与运行入口一致（v0.6.6 交互 + v0.7.x smoke）。
  - runtime/ 根目录无散落 session_*.md / *.log，全部归到 runtime/legacy_sessions/。
  - .gitignore 阻止 smoke_test*.log 再进入仓库。
  - smoke 脚本名带版本号 (legacy_v066_5turn_smoke.py / v070_dungeon_20turn_smoke.py)。
    v0.7_semantic_judge_prompt_reference.md，把现在散在 director_agent.py / renderer_agent.py / semantic_judge.py 里的
    system prompt 抄出来 + 注明每条规则的引入版本（v0.7.0 / .1 / .2 / .3 / .4）
  目标: 让 prompt 改动可被 review
  ────────────────────────────────────────
  编号: P1-5
  动作: 在 tests/ 下加 README.md 说明命名约定：test_vXXX_regression.py = 按版本归档；按模块名命名的 =
    当前活跃。同时给当前活跃测试加目录前缀标签，不动文件
  目标: 让谁该跑、谁不该删一目了然
  ────────────────────────────────────────
  编号: P1-6
  动作: runtime/agentic_runs/ 增加 README.md 描述每个 run 目录内文件含义（events.jsonl / errors.jsonl /
    artifact_NNN_*.json / 未来的 manifest.json），并写明 analyze_agentic_run.py --json 是唯一指标真源
  目标: 与 ARCHITECTURE_REORG_PLAN §7 对齐
  ────────────────────────────────────────
  编号: P1-7
  动作: 在 docs/architecture/ 加 pipeline_v0.7_vs_v0.6.md 一张大对照表，把 P1-1 的分组、调用图、入口、为什么保留 legacy
    写清楚
  目标: 替代散落在 review 中的零散说明

  P2 — 等 v0.7.5 落地后再做，是物理移动而不是命名

  编号: P2-1
  动作: 按 ARCHITECTURE_REORG_PLAN §3 物理拆包：metarpg/legacy/ ← engine.py / proposer.py / assembler.py / metaact.py /
    claims.py / dsl.py / parsing.py / cli.py / narrator.py / session_logger.pymetarpg/core/ ← models.py / world.py /
    rules.py / hooks.py / hookmatch.py / hookgen.py / frontier.py / affordance*.py / retrodict.py / plot_graph.py /
    plot_diagnose.py / scene_expand.py / expansion_budget.py / action_contract.py / apply_event.py / apply_report.py /
    events.py / beliefs.py / scenario_hooks.pymetarpg/bridge/ ← bridge.py / bridge_protocol.py / bridge_session.py /
    export_snapshot.pymetarpg/agentic/ 保持但分子目录 agentic/legacy/ 与 agentic/v0_7/
  目标: 但只能在 v0.7.5 验收通过且 import 全部测过之后做；先用 compatibility re-export 兼容旧 import
  ────────────────────────────────────────
  编号: P2-2
  动作: agentic/legacy/ 内的 writer_agent / translator_agent / scanner / hard_auditor / soft_auditor_agent /
  editor_agent
    / repair_loop / refusal_fallback / parallel_dispatch / feasibility / crystallize / teacher_agent / scorecard /
    eval_runner / play_cli 全部物理迁移；committer.py 拆为 agentic/legacy/committer.py(apply_admitted_patch +
    commit_turn) 与 agentic/v0_7/committer.py(commit_transaction)；schemas.py 拆为 agentic/legacy/schemas.py 与
    agentic/v0_7/transaction.py（后者已存在）
  目标: 物理消除"同文件两路径"问题
  ────────────────────────────────────────
  编号: P2-3
  动作: 在 docs/archive/old_plans/ 内加入 planVer0.7.0.md / planVer0.7.2.1.md 的复本，仅当 v0.7.5 plan 写完时；当前 plan

    留在 docs/plans/ 即可
  目标: 历史可追溯
  ────────────────────────────────────────
  编号: P2-4
  动作: 评估是否合并 metarpg/data/seeds/dnd_ashen_vault_seed.yaml 旁边新增多 seed 支持；本期不做，仅在文档登记
  目标: 留作 v0.8 入口

  ---
  B.3 删除候选（先不删，只在文档登记 deprecated）

  这些已经被新路径完全替代、且没有 caller 在主链路上，但仍可能被某个 regression test 引用。请先在
  docs/architecture/v0.7_interfaces.md 写 "deprecated, planned removal in v0.8"，等 v0.7.5 落地后再用 grep 确认零 caller
   才删：

  - metarpg/agentic/runner.py::_feasibility_to_intent（v0.7.0 后没人调）
  - metarpg/agentic/repair_loop.py（被 v0.7.3 render_repair.py 替代；legacy runner 也没有真的接它）
  - metarpg/agentic/editor_agent.py（v0.6.6 Bold/Safe 已不走 editor）
  - metarpg/agentic/teacher_agent.py（PROJECT_STATUS freeze rule 明令"No Teacher code mutation"）
  - metarpg/agentic/eval_runner.py（被 scripts/analyze_agentic_run.py 替代）

  ---
  B.4 不要做（防止整理过头）

  - 不动 metarpg/agentic/runner.py 双路径并存；只加注释，不拆函数，直到 v0.7.5 验收通过。
  - 不删 legacy writer_agent / translator_agent / hard_auditor / soft_auditor_agent / scanner / refusal_fallback /
  parallel_dispatch / feasibility / crystallize：它们还服务 run_agentic_turn 与多个 test_vXXX_regression。
  - 不动 models.py：v0.7 world_graph.py 是 adapter，不替换 WorldState（来自 planReviewVer0.7.0 §3.3）。
  - 不动 bridge*.py：UPF bridge 仍在冻结期。
  - 不重命名 runtime/agentic_runs/ 内已有 run 目录。
  - 不引入新依赖（PyYAML 已存在；不要为整理加 pydantic / typer 等）。
  - 不在整理同一 commit 内修任何 bug（即使顺手发现）；按 ARCHITECTURE_REORG_PLAN §10 "No broad refactor mixed with
  behavior fixes"。

  ---
  B.5 整理 Done Definition

  - docs/architecture/v0.7_interfaces.md 存在并覆盖所有 v0.7 dataclass + producer/consumer。
  - runner.py / committer.py / schemas.py 头部注释明确说明 legacy vs v0.7 边界与 deprecated re-export。
  - README.md 与 PROJECT_STATUS.md 描述与运行入口一致（v0.6.6 交互 + v0.7.x smoke）。
  - runtime/ 根目录无散落 session_*.md / *.log，全部归到 runtime/legacy_sessions/。
  - .gitignore 阻止 smoke_test*.log 再进入仓库。
  - smoke 脚本名带版本号 (legacy_v066_5turn_smoke.py / v070_dungeon_20turn_smoke.py)。
  - 每个 agentic 模块头部 docstring 有 Status: legacy | v0.7.x | shared 标记。
  - 所有动作不引入任何运行时行为差异；pytest 通过数与整理前一致。

    / repair_loop / refusal_fallback / parallel_dispatch / feasibility / crystallize / teacher_agent / scorecard /
    eval_runner / play_cli 全部物理迁移；committer.py 拆为 agentic/legacy/committer.py(apply_admitted_patch +
    commit_turn) 与 agentic/v0_7/committer.py(commit_transaction)；schemas.py 拆为 agentic/legacy/schemas.py 与
    agentic/v0_7/transaction.py（后者已存在）
  目标: 物理消除"同文件两路径"问题
  ────────────────────────────────────────
  编号: P2-3
  动作: 在 docs/archive/old_plans/ 内加入 planVer0.7.0.md / planVer0.7.2.1.md 的复本，仅当 v0.7.5 plan 写完时；当前 plan

    留在 docs/plans/ 即可
  目标: 历史可追溯
  ────────────────────────────────────────
  编号: P2-4
  动作: 评估是否合并 metarpg/data/seeds/dnd_ashen_vault_seed.yaml 旁边新增多 seed 支持；本期不做，仅在文档登记
  目标: 留作 v0.8 入口

  ---
  B.3 删除候选（先不删，只在文档登记 deprecated）

  这些已经被新路径完全替代、且没有 caller 在主链路上，但仍可能被某个 regression test 引用。请先在
  docs/architecture/v0.7_interfaces.md 写 "deprecated, planned removal in v0.8"，等 v0.7.5 落地后再用 grep 确认零 caller
   才删：

  - metarpg/agentic/runner.py::_feasibility_to_intent（v0.7.0 后没人调）
  - metarpg/agentic/repair_loop.py（被 v0.7.3 render_repair.py 替代；legacy runner 也没有真的接它）
  - metarpg/agentic/editor_agent.py（v0.6.6 Bold/Safe 已不走 editor）
  - metarpg/agentic/teacher_agent.py（PROJECT_STATUS freeze rule 明令"No Teacher code mutation"）
  - metarpg/agentic/eval_runner.py（被 scripts/analyze_agentic_run.py 替代）

  ---
  B.4 不要做（防止整理过头）

  - 不动 metarpg/agentic/runner.py 双路径并存；只加注释，不拆函数，直到 v0.7.5 验收通过。
  - 不删 legacy writer_agent / translator_agent / hard_auditor / soft_auditor_agent / scanner / refusal_fallback /
  parallel_dispatch / feasibility / crystallize：它们还服务 run_agentic_turn 与多个 test_vXXX_regression。
  - 不动 models.py：v0.7 world_graph.py 是 adapter，不替换 WorldState（来自 planReviewVer0.7.0 §3.3）。
  - 不动 bridge*.py：UPF bridge 仍在冻结期。
  - 不重命名 runtime/agentic_runs/ 内已有 run 目录。
  - 不引入新依赖（PyYAML 已存在；不要为整理加 pydantic / typer 等）。
  - 不在整理同一 commit 内修任何 bug（即使顺手发现）；按 ARCHITECTURE_REORG_PLAN §10 "No broad refactor mixed with
  behavior fixes"。

  ---
  B.5 整理 Done Definition

  - docs/architecture/v0.7_interfaces.md 存在并覆盖所有 v0.7 dataclass + producer/consumer。
  - runner.py / committer.py / schemas.py 头部注释明确说明 legacy vs v0.7 边界与 deprecated re-export。
  - README.md 与 PROJECT_STATUS.md 描述与运行入口一致（v0.6.6 交互 + v0.7.x smoke）。
  - runtime/ 根目录无散落 session_*.md / *.log，全部归到 runtime/legacy_sessions/。
  - .gitignore 阻止 smoke_test*.log 再进入仓库。
  - smoke 脚本名带版本号 (legacy_v066_5turn_smoke.py / v070_dungeon_20turn_smoke.py)。
  - 每个 agentic 模块头部 docstring 有 Status: legacy | v0.7.x | shared 标记。
  - 所有动作不引入任何运行时行为差异；pytest 通过数与整理前一致。
  ---
  整合版 plan 与代码整理计划已落齐。两件事互相独立：

  - v0.7.5 plan (A) 决定下一版做什么（修 v0.7.4 review 列的 4 个真实漏洞、补 L2 必跑矩阵、补 manifest、跑 targeted
  目标: 历史可追溯
  ────────────────────────────────────────
  编号: P2-4
  动作: 评估是否合并 metarpg/data/seeds/dnd_ashen_vault_seed.yaml 旁边新增多 seed 支持；本期不做，仅在文档登记
  目标: 留作 v0.8 入口

  ---
  B.3 删除候选（先不删，只在文档登记 deprecated）

  这些已经被新路径完全替代、且没有 caller 在主链路上，但仍可能被某个 regression test 引用。请先在
  docs/architecture/v0.7_interfaces.md 写 "deprecated, planned removal in v0.8"，等 v0.7.5 落地后再用 grep 确认零 caller
   才删：

  - metarpg/agentic/runner.py::_feasibility_to_intent（v0.7.0 后没人调）
  - metarpg/agentic/repair_loop.py（被 v0.7.3 render_repair.py 替代；legacy runner 也没有真的接它）
  - metarpg/agentic/editor_agent.py（v0.6.6 Bold/Safe 已不走 editor）
  - metarpg/agentic/teacher_agent.py（PROJECT_STATUS freeze rule 明令"No Teacher code mutation"）
  - metarpg/agentic/eval_runner.py（被 scripts/analyze_agentic_run.py 替代）

  ---
  B.4 不要做（防止整理过头）

  - 不动 metarpg/agentic/runner.py 双路径并存；只加注释，不拆函数，直到 v0.7.5 验收通过。
  - 不删 legacy writer_agent / translator_agent / hard_auditor / soft_auditor_agent / scanner / refusal_fallback /
  parallel_dispatch / feasibility / crystallize：它们还服务 run_agentic_turn 与多个 test_vXXX_regression。
  - 不动 models.py：v0.7 world_graph.py 是 adapter，不替换 WorldState（来自 planReviewVer0.7.0 §3.3）。
  - 不动 bridge*.py：UPF bridge 仍在冻结期。
  - 不重命名 runtime/agentic_runs/ 内已有 run 目录。
  - 不引入新依赖（PyYAML 已存在；不要为整理加 pydantic / typer 等）。
  - 不在整理同一 commit 内修任何 bug（即使顺手发现）；按 ARCHITECTURE_REORG_PLAN §10 "No broad refactor mixed with
  behavior fixes"。

  ---
  B.5 整理 Done Definition

  - docs/architecture/v0.7_interfaces.md 存在并覆盖所有 v0.7 dataclass + producer/consumer。
  - runner.py / committer.py / schemas.py 头部注释明确说明 legacy vs v0.7 边界与 deprecated re-export。
  - README.md 与 PROJECT_STATUS.md 描述与运行入口一致（v0.6.6 交互 + v0.7.x smoke）。
  - runtime/ 根目录无散落 session_*.md / *.log，全部归到 runtime/legacy_sessions/。
  - .gitignore 阻止 smoke_test*.log 再进入仓库。
  - smoke 脚本名带版本号 (legacy_v066_5turn_smoke.py / v070_dungeon_20turn_smoke.py)。
  - 每个 agentic 模块头部 docstring 有 Status: legacy | v0.7.x | shared 标记。
  - 所有动作不引入任何运行时行为差异；pytest 通过数与整理前一致。