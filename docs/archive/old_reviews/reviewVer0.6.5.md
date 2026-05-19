# reviewVer0.6.5 — Safe→Flash 实验回顾与 v0.6.6 方向

日期: 2026-05-18
评审范围: v0.6.5 执行报告（`docs/reports/reportVer0.6.5.md`）+ smoke test 7 turn 完整产物

---

## 0. Review Target

本评审基于:

```text
docs/reports/reportVer0.6.5.md
runtime/agentic_runs/smoke_*/ (7 turn)
```

已观察到的实现改动:

```text
metarpg/agentic/parallel_dispatch.py  (+timeout, +as_completed, +ParallelTimeoutError)
metarpg/agentic/model_client.py       (+thinking 开关, +结构化 httpx timeout)
metarpg/agentic/runner.py             (Safe→Flash, safe_strict temp 0.3→0.5)
tests/test_parallel_dispatch.py       (+2 测试)
tests/test_v064_regression.py         (+1 测试)
tests/test_model_client_thinking.py   (+4 测试)
```

253 单元测试通过。

---

## 1. High-Level Judgment

**计划全部落地，但实验结果证伪了核心假设——Safe→Flash 让延迟从 47.56s 中位升到 141.51s（+197%），需要回退到串行 fallback 架构。** 报告本身写得诚实且证据充分。

v0.6.5 的真正价值不在于"加速"——它在三件事上是值得的:

1. **Turn 3 不是死锁** — trace 证实 `fut.result()` 正常返回，所谓挂起其实是 ReadTimeout。v0.6.4 报告里"服务器进入不可恢复状态"的诊断被推翻
2. **超时兜底必要且无副作用** — Phase 2 的 `ParallelTimeoutError` + `as_completed` 是未来任何并行架构都受益的防御性基建
3. **双 Flash 路线被实验排除** — 这是 v0.6.5 实验设计的本意，结果决断地告诉我们"不要这么做"，比继续争论便宜得多

---

## 2. 报告诊断逐条复核

### ✅ 正确诊断

**P0 延迟主因是 JSON repair call，不是 thinking-mode**

- Turn 3 Bold=132s、Turn 6=236s 远超正常 API 延迟
- `writer_agent.py:347-364` 的 repair 路径（首次解析失败 → temperature=0 重调 Flash）才是新瓶颈
- Phase 3 disable thinking-mode 的延迟收益被 repair 路径吃掉了

**P1 空 segments winner**

- Turn 4 `safe_loose PASS (0 segs)` 是真 bug
- `_select_winner` 决策树没有空候选拒绝，导致 `player_output` 空白
- 5 行代码可修，但属于阻塞性问题

**架构方向收敛回 v0.6.4 B 方案**

- 报告"立即修复"和"短期方案 A"加起来就是 v0.6.4 报告里的 B 方案
- 闭环说明:之前 v0.6.4 报告的推荐方向是对的，只是 v0.6.5 不应该走"双 Flash"分支

### ⚠️ 需要再验证

**P5 thinking-mode 是否真生效 — 当前证据不足**

- Phase 3 的 `tests/test_model_client_thinking.py` 是 stub-level 测试，只断言 payload 里有 `extra_body.thinking.disabled`
- **未验证 DeepSeek 服务端是否真的执行了 disable**
- 验证方法: 用同一 prompt 跑两次（thinking=True / thinking=False），对比响应里 `reasoning_content` 字段存在性、completion_tokens 数量差异、wall time 差异。该实验单次完成只需 10 分钟，应在 v0.6.6 前补做

### 🔴 报告轻描淡写但实际严重的一项

**Turn 6 光剑事件不是"按 ambient texture 原则允许"——这是语义安全漏洞**

报告 P4 说"按 v0.6.1 review 的 'Ambient texture may float' 原则，transient_event 级别的描述是允许的"。这条解释**不成立**:

- v0.6.1 ambient texture 指的是**背景客人、环境氛围**这类无名实体
- 光剑是**玩家主动持有并使用**的具名物品，且导致 NPC 反应（Mara 被撞倒、恐惧）
- 这条 patch 即使全是 transient_event，也已经污染了**叙事真值**——下一 turn world.transcript 里就有"玩家持光剑"，但 world.inventory/schema 里没有

证据链:
1. Feasibility（Qwen）错判 `accept`，facts 为空 → Bold 看不到任何约束
2. Hard Auditor 不检查"叙事提到的具名物品是否在 world.schema 内"
3. Soft Auditor 只看叙事一致性，不看世界设定

**这意味着任何"任性"输入只要 Feasibility 没拦住就会一路绿灯。** 比延迟问题更应优先修。

---

## 3. 数据层面对比

| 维度 | v0.6.4 | v0.6.5 | 解读 |
|---|---|---|---|
| Median wall time | 47.56s | 141.51s | **延迟代价巨大，必须回滚 Safe→Flash** |
| Bold pass rate | 71.43% | 85.71% | Flash 关 thinking 后 JSON 解析更稳定 |
| Safe_loose pass rate | 57.14% | 85.71% | Flash 在 JSON-strict 上显著优于 Qwen |
| Safe_strict pass rate | 85.71% | 100% | 同上 |
| Fallback count | 0 | 0 | Phase 2 超时兜底未被触发，机制存在但未验证有效性 |
| 全部 acceptable | True | **False (Turn 4)** | 阻塞性 bug |

**值得保留的收益**: Flash 在 JSON-strict prompt 上的稳定性优势。这条信号要保留——但要通过"Bold 失败时 fallback 一个 Flash Safe"而不是"恒定双 Flash 并行"的方式。

**值得放弃的代价**: 双 Flash 并行的延迟。Bold/Safe 两路对同一 Flash endpoint 串行排队、单次 repair call 可达 60s+，让 wall time 不可控。

---

## 4. v0.6.6 实施优先级（按血压排序）

### P0 — 必须立即修复（不修没法 ship）

**1. 决策树拒绝空 segments 候选**

`metarpg/agentic/runner.py::_select_winner`:
```python
for name in priority_order:
    cand = candidates.get(name)
    audit = candidate_audits.get(name, {})
    if cand is None or not cand.segments:
        continue
    if audit.get("passed") and ...:
        return name, cand, audit
```

测试: 加一个 case，构造 3 个候选其中两个 segments=[]，断言 winner 是第三个。

### P1 — 高优先级（解决延迟）

**2. Writer JSON repair 路径加超时熔断**

`metarpg/agentic/writer_agent.py::run_writer` 第二次（repair）调用时，传 client 一个**显式短超时**（建议 20s）。超时就直接抛 `WriterOutputError`，不再等。

实施: `LlmClient.chat()` 加 `request_timeout: float | None = None` 参数，传入时覆盖 client 默认超时（用 `httpx.Timeout(read=request_timeout)`）。

**3. 架构回滚: Safe 切回 Qwen + 串行 fallback**

修改 `runner.py`:
- 阶段 1（并行）: Bold(Flash) + Feasibility(Qwen)
- 阶段 2: 审计 Bold（translator + scanner + hard + soft，串行/并行均可）
- **如果 Bold 审计 PASS**: 直接 commit，整个 turn 结束（**省 2 路 Safe Writer + 2 路 audit_candidate**）
- **如果 Bold 审计 FAIL**: 阶段 3（并行）: Safe_loose(Qwen) + Safe_strict(Qwen)，然后审计

预期 wall time:
- Bold PASS 路径（占多数 turn）: ~30-50s
- Bold FAIL 路径（少数）: ~80-120s

Safe 切回 Qwen 是因为:
- Bold 已经吃了 Flash 配额；Safe 走 Qwen 让两端负载平衡
- Qwen 在 v0.6.4 实测里 Safe pass rate 是 85.71%，本身够用
- Bold FAIL 时玩家已经在等，多花 10s 让 Safe 走 Qwen 比抢 Flash 排队更可控

### P2 — 中优先级（解决语义安全）

**4. Feasibility 注入 world_schema 约束**

修改 `metarpg/agentic/feasibility.py` 的 system prompt，明确给出世界设定边界:

```
This world is an agrarian fantasy tavern setting.
The following are OUTSIDE this world:
- High-tech weapons (lightsabers, guns, etc.)
- Telepathy/mind-reading abilities
- Modern items (phones, electricity, vehicles)

When player input references such things, return:
- world_response_kind: "absence" (the thing doesn't exist)
- preserve_player_voice: <neutralized version>
- facts: ["<thing> does not exist in this world"]
```

或者更工程化的做法: 在 `story_packet` 中增加 `world_schema_notes` 字段，Feasibility 显式读取。

**5. Hard Auditor 增加 schema 检查**

`metarpg/agentic/hard_auditor.py`（或对应文件）扫描 segments 里出现的具名物品/能力，若不在 `world.schema.items` / `world.schema.abilities` 内，标 medium issue 或 hard issue。

这条比改 Feasibility 更彻底——即使 Feasibility 漏掉，Hard Auditor 兜底拦截。

### P3 — 验证（不修但要确认）

**6. Thinking-mode 真生效验证**

新建 `scripts/verify_thinking_off.py`:
- 用同一 prompt 调 Flash 两次（thinking=True / thinking=False）
- 对比响应的 `usage.completion_tokens`、wall time、是否含 `reasoning_content` 字段
- 期望: thinking=False 时 completion_tokens 显著减少（无 reasoning 阶段），wall time 显著降

如果 thinking-mode 实际未生效:
- 检查 DeepSeek API 当前文档（可能参数名变了，比如 `reasoning_effort=none` 替代 `extra_body.thinking.type=disabled`）
- 重新设计 disable 方式

---

## 5. v0.6.5 留下的可保留资产

| 资产 | 是否保留 | 理由 |
|---|---|---|
| `ParallelTimeoutError` + `as_completed` 兜底 | **保留** | 防御性基建，未来任何并行架构受益 |
| `httpx.Timeout(connect/read/write/pool)` 结构化 | **保留** | 比 60s 总超时更鲁棒 |
| `thinking: bool` 参数 + V4 extra_body | **保留但需验证** | API 路径正确，需 P3 实验确认服务端真生效 |
| safe_strict temp 0.3→0.5 | **回滚** | Safe 切回 Qwen 后 temperature 路径会变（Qwen 也支持 temperature） |
| Safe→Flash 路由 | **回滚** | 实验证伪 |
| `tests/test_parallel_dispatch.py` 超时测试 | **保留** | 即使不再用双 Flash，timeout 兜底测试仍有效 |
| `tests/test_model_client_thinking.py` | **保留** | DeepSeek 调用 contract 测试 |
| `tests/test_v064_regression.py::test_safe_writers_use_flash_client` | **回滚或改写** | 路由变了，断言对象变 |

---

## 6. 关键修改文件清单（v0.6.6）

| 文件 | 改动 |
|---|---|
| `metarpg/agentic/runner.py::_select_winner` | 加空 segments 拒绝 |
| `metarpg/agentic/runner.py` 主流程 | 改成 Bold-first + audit-then-branch 串行 fallback |
| `metarpg/agentic/writer_agent.py::run_writer` | repair 路径加 20s 短超时 |
| `metarpg/agentic/model_client.py::chat` | 加 `request_timeout` 参数 |
| `metarpg/agentic/feasibility.py` | system prompt 注入 world schema 边界 |
| `metarpg/agentic/hard_auditor.py` | schema-check segments 出现的具名实体 |
| `scripts/verify_thinking_off.py` | 新建,P3 验证脚本 |
| `tests/test_v064_regression.py` | 调整路由相关断言 |
| `tests/test_select_winner.py`（可能新建） | 空 segments 拒绝测试 |

---

## 7. 不在 v0.6.6 scope（留待 v0.6.7+）

- 本地部署 Qwen 替代远端 — 报告 D 方案，已确认基建本身没问题，不是瓶颈
- 决策树重排（Bold 失败时优先 safe_strict 的特定分支） — 需要更多 turn 数据
- Translator/Scanner 走 code-only 不走 LLM — 报告 C 方案，质感保护减弱，需另设回归
- "约定式 ambient" vs "禁止 ambient" 的策略再调 — 需先把 schema 检查铺上再讨论

---

## 8. 结论

v0.6.5 是一次**结论为负但价值为正的实验**:

- 证伪了"双 Flash 并行加速"假设
- 证伪了"Turn 3 是服务端死锁"的旧诊断
- 暴露了 JSON repair 路径是新瓶颈
- 暴露了 Feasibility + Hard Auditor 对世界 schema 边界的双重盲区
- 留下了可保留的超时兜底/thinking 开关/httpx 结构化超时三项基建

v0.6.6 方向: **回到串行 fallback（v0.6.4 报告 B 方案）+ 修空候选 bug + 补 world schema 边界**。
