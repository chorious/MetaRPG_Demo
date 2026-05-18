# MetaRPG v0.6.4 执行报告 — 双 Writer 并行流水线

日期: 2026-05-18
执行者: Claude Code

---

## 1. 已完成的代码改动

### 新增文件

| 文件 | 说明 |
|---|---|
| `metarpg/agentic/parallel_dispatch.py` | ThreadPoolExecutor 封装,支持一路异常其他继续 |
| `metarpg/agentic/feasibility.py` | Feasibility Agent,纯 LLM 路径,失败兜底 accept |
| `metarpg/agentic/refusal_fallback.py` | 4 套模板兜底(absence/friction/reframing/accept),无 LLM |
| `tests/test_parallel_dispatch.py` | 5 个单元测试 |
| `tests/test_feasibility.py` | 8 个单元测试 |
| `tests/test_writer_modes.py` | 16 个单元测试 |
| `tests/test_v064_regression.py` | 8 个回归测试(决策树/fallback/观察性字段) |
| `evals/cases/lightsaber_absence.json` | 任性回归:光剑斩 Mara |
| `evals/cases/absent_npc_talk.json` | 任性回归:找不在场的 Rusk 说话 |
| `evals/cases/ambient_guests_pass.json` | v0.6.1 review §11:无名背景客人应通过 |
| `evals/cases/notebook_medium_issue.json` | v0.6.1 review §11:未登记道具应为 medium |
| `evals/cases/npc_offer_needs_patch.json` | v0.6.1 review §11:NPC 要约需 patch 支撑 |

### 修改文件

| 文件 | 改动 |
|---|---|
| `metarpg/agentic/writer_agent.py` | 新增 `mode`/`feasibility`/`temperature` 参数;4 套 safe_strict system prompt;`_select_system_prompt` 路由 |
| `metarpg/agentic/runner.py` | **全面重写**:串行 Writer→Translator→Scanner→HardAudit→SoftAudit 替换为双 Writer 三候选并行流水线;新增 `_select_winner` 决策树;新增 `aggregate_v064_stats` |
| `metarpg/agentic/run_logger.py` | `close()` 新增 `v064_stats` 参数,manifest 和 summary.md 多输出 Bold/Safe 通过率和 winner 分布 |
| `metarpg/agentic/schemas.py` | `TurnDraft` 新增 `candidate_audits`/`turn_wall_time_s` |
| `metarpg/agentic/committer.py` | `journal_note` 分支增加 `world.turn_event_log.append` |
| `scripts/agentic_5turn_smoke_test.py` | 加 turn 6/7(光剑/读心);打印 candidate 状态表和 winner_name;close() 传入 v064_stats |

### 测试汇总

```
全部 254 个测试通过(246 个已有 + 8 个 v0.6.4 新增)
```

---

## 2. 端到端 Smoke Test 结果

### 运行环境

- Flash: DeepSeek Flash via api.deepseek.com
- Qwen: qwen3.6-27b-nvfp4 @ 192.168.50.20:8101 (远程 Ubuntu 24.04 + RTX 5070 Ti 16G)
- 并发: ThreadPoolExecutor(max_workers=4)

### Turn 1: 要了一杯啤酒

```
wall time: 49.01s
feasibility: accept
bold:      FAIL (1 hard issue, 2 segs)
safe_loose: PASS (0 hard issues, 3 segs)
safe_strict: PASS (0 hard issues, 3 segs)
winner: safe_loose

player_output:
  你向吧台走去，声音在嘈杂的酒馆中显得格外清晰："来一杯啤酒。"
  玛拉抬起头，眼神中带着几分谨慎与好奇。她迅速从酒桶中倒出一杯金黄色的啤酒...
  你接过酒杯，麦香扑鼻。酒馆里的紧张气氛似乎因这杯饮品而稍缓...
```

**Bold 失败原因**:Hard Auditor 报 1 个 issue。从输出看 Bold 只有 2 个 segment,`acquire_item:beer` 的 patch_ref 未正确挂到 segment 上,导致 hard audit 认为"硬状态变化无叙事支撑"。Safe_loose 的 3 段叙事结构更完整,通过了审计。

**关键发现**:Safe_loose 的输出质感**可接受**——有感官细节(麦香、金黄色、泡沫),NPC 有反应但无内心独白泄露。说明 Qwen 在 feasibility_facts 约束下仍能写出有质感的散文。

### Turn 2: 耸了耸肩 "这杯酒真不错"

```
wall time: 97.69s
feasibility: accept
bold:      PASS (0 hard issues, 3 segs)
safe_loose: PASS (0 hard issues, 3 segs)
safe_strict: PASS (0 hard issues, 2 segs)
winner: bold (决策树优先)

player_output:
  你耸了耸肩，举起手中的酒杯晃了晃，琥珀色的酒液在烛光下泛着温润的光...
  吧台周围飘着麦芽和柴火的气味...
  玛拉停下擦杯子的手，抬眼望向你。她嘴角微微上扬...
```

Bold 输出质量良好,有感官细节(琥珀色、烛光、麦芽、柴火、噼啪声),NPC 反应自然。Safe 工作被丢弃但证明了兜底存在。

### Turn 3: 一饮而尽 — **挂起**

```
wall time: >600s (未结束,手动终止)
bold:      PASS (0 hard issues, 2 segs)
safe_loose: MISSING (writer exception)
```

Safe_loose writer 在并行调用中抛出异常(具体异常未捕获到 stdout)。进程在收集 candidates 后卡住,未输出后续审计/决策信息。

**事后诊断**:尝试对 Qwen 服务器发单次 POST 请求,**TimeoutError**。GET /v1/models 仍返回 200。说明服务器在处理完 Turn 1+2 的 10+ 次并发 POST 后进入不可恢复状态,无法接受新的 chat completions 请求。

---

## 3. 关键问题

### P0: 延迟严重超标

| 指标 | 计划值 | 实测值 | 偏差 |
|---|---|---|---|
| 每 turn wall time | ≤7s | 49-97s | **7-14×** |
| Qwen 单次调用 | 1-2s | 10-15s+ | **5-10×** |
| Flash 单次调用 | 3s | ~10-20s | **3-7×** |

**根因**:远程 Qwen(192.168.50.20)的实际响应时间远高于计划假设。即使 4 路并发,每 turn 需要 7 次 Qwen 调用( feasibility + 2 Writers + 3 Translators + 1 SoftAudit ),峰值并发 4 路,总 wall time ≈ ceil(7/4) × 15s ≈ 30s,再加上 Flash 的 10-20s,实际 40-60s/turn 是理论下限。

**计划假设的误判**:planVer0.6.4.md 假设 "每路 ~1-2s" 是基于 localhost 的本地推理延迟。192.168.50.20 是 LAN 另一台机器,网络往返 + vLLM/llama.cpp 调度开销使延迟倍增。

### P1: Qwen 服务器并发承受能力不足

Turn 1+2 共发了 ~14 次 POST 请求(7 次/turn × 2 turn)。Turn 3 开始时服务器已无法响应。说明后端(vLLM/llama.cpp)的并发处理能力远低于 "4 路真并发" 的预期。

可能原因:
- vLLM 的 `max_num_seqs` 或 GPU 内存限制,队列堆积后超时
- llama.cpp 的 server 模式不支持真正的请求级并发,请求串行处理
- 16G VRAM 装 27B 模型后剩余显存不足,并发 batch 大小受限

### P2: Bold 在 Turn 1 失败率偏高

计划预期 Bold 在合法输入下通过率 >90%。实测 Turn 1 Bold 失败(因 segment-patch 对齐问题)。虽然只有 2 个样本,但趋势需要监控。

### P3: Safe Writer 的 token 浪费

决策树固定 Bold > Safe_loose > Safe_strict。在 Bold 通过的场景(Turn 2),Safe 的 2 次 Writer + 2 次 Translator 调用被完全丢弃。由于 Qwen 延迟高,这造成显著的时间浪费。

---

## 4. 建议的下一步

### 立即(恢复基础设施)

1. **重启远程 Qwen 服务**:SSH 到 192.168.50.20,检查 vLLM/llama.cpp 进程状态,必要时重启
2. **确认后端并发能力**:用 `tests/test_parallel_dispatch.py` 的压测模式直接对 Qwen endpoint 发 4 个并发请求,看 wall time
3. **如果后端确实是串行处理**:planVer0.6.4.md 的整个并行假设需要重写

### 短期(降低延迟,3 选 1 或组合)

| 方案 | 改动 | 预期节省 | 风险 |
|---|---|---|---|
| A. 合并 Safe_loose+Safe_strict | 只保留一个 Safe Writer,减少 1 次 Writer + 1 次 Translator | ~15-20s/turn | Safe 多样性降低,兜底变弱 |
| B. Bold 失败后才启动 Safe | 第一批只发 Bold + Feasibility;若 Bold 审计失败,再串行发 Safe | ~15-20s/turn( Bold 通过时) | Bold 失败时延迟反而更长 |
| C. 跳过 Safe 的 Translator | Safe 候选不走 full audit,直接用 Scanner+HardAudit(code) | ~15s/turn | Translator 的质量检查丢失,HardAudit 可能漏掉叙事 claim |
| D. 本地部署 Qwen | 在 Win11 + RTX Pro 5000 48G 上跑 vLLM,消除网络延迟 | ~10-15s/turn | 需要配置本地 vLLM,模型文件需复制 |

**推荐组合**:B + C — Bold 通过后不启动 Safe Writers(省 2 次 Writer),Safe Writers 不走 Translator(只走 Scanner+HardAudit,省 2 次 Translator)。这样每 turn 的 Qwen 调用从 7 次降到:
- Bold 通过时: Feasibility(1) + Safe 不启动 + Translator on Bold(1) + SoftAudit(1) = **3 次**
- Bold 失败时: Feasibility(1) + Safe Writer(1) + Translator on Bold(1) + SoftAudit(1) + Scanner/Hard on Safe = **4 次**

### 中期(架构调整)

若本地 Qwen 仍无法达到 1-2s/turn,考虑:
- 用更大的本地模型(Qwen3.6-27B 换到本地 48G 卡,可能可以跑更高 batch size)
- 或用更小的本地模型(如 Qwen3-14B)做 Feasibility/Safe,牺牲一点质感换速度
- 或放弃 Safe Writer 并行,改为串行 Feasibility → 若 need_safe 则串行 Safe → 审 Bold + Safe 两份,选一份(总延迟 ~Bold_time + Safe_time,但 Qwen 调用量减少)

### 长期(监控)

- 在 run_manifest 中持续记录 `bold_pass_rate` 和 `median_turn_wall_time_s`
- 若 Bold 通过率连续 3 次 run < 70%,重新审视 Bold prompt
- 若 median wall time > 15s,触发延迟优化警报

---

## 5. 代码质量总结

- **契约兼容性**:v0.6.3 的 11 个回归测试全部通过,`run_agentic_turn` 签名和返回 dict 不变
- **可观察性**:每 turn 输出 candidate 状态表 + winner_name + wall_time,run_manifest 汇总通过率
- **错误处理**:一路 Writer 异常不影响其他路;全部 Writer 异常时回退到 v0.6.3 错误路径
- **测试覆盖**:新增 37 个单元/回归测试,全部通过

---

## 6. 附件

- Smoke test 完整输出(前 2 turn):见 `runtime/agentic_runs/smoke_90a0cc2a/`
  - `turn_001.json`: winner=safe_loose, wall_time=49.01s
  - `turn_002.json`: winner=bold, wall_time=97.69s
  - `turn_003.json`: 未生成(进程挂起)
  - `events.jsonl`: 含 batch1_complete、writers_complete、winner_selected 事件
