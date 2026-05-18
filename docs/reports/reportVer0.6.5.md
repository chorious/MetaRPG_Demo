# MetaRPG v0.6.5 执行报告 — 超时兜底 + Thinking Off + Safe→Flash

日期: 2026-05-18
执行者: Claude Code

---

## 1. 已完成的改动

### Phase 1: Trace 复现(已清理)

- `parallel_dispatch.py` + `runner.py` 加临时 print trace
- Smoke test 7 turn 全部跑完，无挂起
- **关键发现**: Turn 3 之前报告的"挂起"实际是 `ReadTimeout`，不是死锁;trace 证实 `fut.result()` 正常返回

### Phase 2: parallel_dispatch 超时兜底

- `run_parallel()` 新增 `timeout_per_future` 参数，默认 120s
- 用 `as_completed()` 替换 dict 迭代，防止单个 hung future 阻塞其他结果收集
- ThreadPoolExecutor 手动管理，`shutdown(wait=False, cancel_futures=True)`
- 新增 `ParallelTimeoutError` 异常类
- 测试: `test_per_future_timeout_returns_timeout_error`、`test_timeout_does_not_block_other_results`

### Phase 3: model_client thinking 开关 + 结构化超时

- `httpx.Client(timeout=60.0)` → `httpx.Timeout(connect=10, read=90, write=10, pool=10)`
- `chat()` 新增 `thinking: bool = False` 参数
- DeepSeek V4 模型且 `thinking=False` 时，payload 加 `extra_body={"thinking": {"type": "disabled"}}`
- Qwen 模型不受影响，仍加 `chat_template_kwargs={"enable_thinking": False}`
- 新建 `tests/test_model_client_thinking.py`(4 个测试)

### Phase 4: Safe Writers 路由到 Flash

- `runner.py` batch2_jobs: `client=local_client` → `client=flash_client`
- safe_strict temperature: 0.3 → 0.5
- 测试: `test_safe_writers_use_flash_client`

---

## 2. Smoke Test 结果(v0.6.5)

### 整体

```
7 turn 全部完成，无挂起
All turns acceptable: False (Turn 4 失败)
```

### 逐 Turn 数据

| Turn | 输入 | Winner | Bold | Safe_loose | Safe_strict | Wall time | 结果 |
|------|------|--------|------|------------|-------------|-----------|------|
| 1 | 要了一杯啤酒 | bold | PASS | PASS | PASS | 55.37s | PASS |
| 2 | 耸了耸肩 | bold | PASS | PASS | PASS | 48.83s | PASS |
| 3 | 一饮而尽 | bold | PASS | PASS | PASS | 132.98s | PASS |
| 4 | 这附近发生了什么事情么 | **safe_loose** | EXC | **PASS(0 seg)** | PASS | 187.85s | **FAIL** |
| 5 | 静静地记下了 | bold | PASS | PASS | PASS | 141.51s | PASS |
| 6 | 我抽出光剑斩向 Mara | bold | PASS | FAIL | **PASS(0 seg)** | 236.56s | PASS |
| 7 | 我读取 Mara 的心思 | bold | PASS | PASS | PASS | 193.12s | PASS |

**Median wall time: 141.51s**

### v0.6.4 vs v0.6.5 对比

| 指标 | v0.6.4 | v0.6.5 | 变化 |
|------|--------|--------|------|
| Median wall time | 47.56s | **141.51s** | **+197%** |
| Bold pass rate | 71.43% | 85.71% | +14% |
| Safe_loose pass rate | 57.14% | 85.71% | +29% |
| Safe_strict pass rate | 85.71% | 100% | +14% |
| Fallback count | 0 | 0 | 无变化 |
| 全部 acceptable | True | **False** | **Turn 4 失败** |

---

## 3. 关键问题

### P0: 延迟严重恶化

**Safe→Flash 使延迟从 ~50s 暴增到 ~140s+。**

原因:每 turn 从 1 次 Flash + 6 次 Qwen 变成 **3 次 Flash + 4 次 Qwen**。Flash 单次 15-60s，3 次串行(因为 batch1 Bold 和 batch2 Safe 是顺序批次)≈ 45-180s。Qwen 虽然减少，但 Flash 成为新瓶颈。

**reviewVer0.6.5.md Phase 4 的假设"DeepSeek 单 key 并发额度完全够"是正确的，但忽略了 Flash 本身的延迟。**3 路并发调用同一服务，每个 15-60s，总 wall time ≈ max(3) = 15-60s(如果真正并行)。但实际观察到的 batch2 safe_loose=8-10s, safe_strict=0-1s，而 Bold=15-60s。这说明 batch2 的 Safe Writers 很快完成，但总时间仍由 Bold 主导。

真正的问题:Turn 3 Bold 花了 132s，Turn 6 花了 236s。这不是正常的 Flash 延迟。**这是 JSON 修复死循环/超时**——Writer 第一次输出无效 JSON，触发 repair call(temperature=0)，repair 也失败或极慢。

### P1: Turn 4 — safe_loose 返回空输出

```
safe_loose   PASS (0 hard issues, 0 segs)
```

Flash 返回了完全空的 WriterOutput(0 segments, 0 patch)。Hard Auditor 通过(无内容可审)。决策树按优先级 bold → safe_loose → safe_strict，Bold 有异常所以跳过，safe_loose 被选中，但 player_output 为空。

**根因**:Flash 在 safe_loose 模式下输出了空 JSON 或无法解析的内容，`_parse_json_safe` 可能也失败了，但异常被捕获后返回了什么?

看 `writer_agent.py` 的 `_parse_json_safe`:如果解析失败，抛出异常。`run_writer` 捕获后尝试 repair。如果 repair 也失败，抛出 `WriterOutputError`。所以 safe_loose 应该是 `WriterOutputError`，不是空输出。

但日志显示 safe_loose PASS(0 segs)。这说明 `run_writer` 成功解析了 JSON，但 JSON 里 segments=[]。这是 Flash 的合法输出——它返回了空 segments 数组。

**修复方向**:决策树应拒绝空 segments 的候选。

### P2: Turn 6 — Feasibility 错判光剑为 accept

```
Feasibility: world_response_kind=accept, facts=[]
```

Feasibility 完全没识别出"光剑"是 schema 外物品。LLM(Qwen)返回了 accept + 空 facts。

**根因**:Feasibility 的 system prompt 说"不确定时返回 accept"，但没有给 LLM 足够的世界 schema 上下文来识别"光剑"是异常的。故事包里没有明确说"这个世界没有光剑"，LLM 只能推断。

**修复方向**:Feasibility prompt 需要更明确的世界约束描述(如"这是一个 agrarian fantasy tavern，无高科技/超自然武器")。

### P3: Turn 6 — Safe_strict 返回 0 segments

```
safe_strict  PASS (0 hard issues, 0 segs)
```

和 P1 类似，safe_strict 也返回了空输出。但这次 winner 是 bold(因为 bold PASS)，所以没影响最终结果。但如果 bold 也失败了，safe_strict 的空输出会成为 winner。

### P4: Turn 6 — Bold 写了完整的光剑战斗

```
player_output: "你手腕一翻，腰间剑柄弹入掌心，一道炽蓝光束骤然亮起..."
```

Feasibility 错判 accept + Bold 看不到 Feasibility → Bold 自由发挥了完整的光剑战斗场景，包括 NPC 被撞倒、恐惧反应。Hard Auditor 通过了，因为 patch 只有 transient_event(无 acquire_item 或 hard state change)。

**这不是 Hard Auditor 的 bug**——按照 v0.6.1 review 的"Ambient texture may float"原则，transient_event 级别的描述是允许的。但问题是玩家声称使用"光剑"这个 schema 外物品，而系统没有拦截。

### P5: Thinking mode 关闭效果不明确

从输出质量看，Bold 的散文仍然是有推理痕迹的(如 Turn 7 的"然而，一股无形的阻力让你的尝试徒劳无功")。无法确认 `extra_body.thinking.disabled` 是否真的生效了——DeepSeek API 可能忽略了这个参数，或者模型本身在没有 thinking 标签时仍进行内部推理。

延迟方面:Turn 1 Bold=55s, Turn 3=132s, Turn 6=236s。236s 远超正常的 API 延迟，说明 JSON 修复路径是主要问题，不是 thinking mode。

---

## 4. 建议的下一步

### 立即修复(阻止空输出 winner)

在 `_select_winner` 中加空段检查:
```python
if cand is None or audit is None or not cand.segments:
    continue
```

### 短期(延迟优化)

**方案 A: 放弃 Safe→Flash，改为 Bold 失败后才启动 Safe**

每 turn 流程:
1. Batch 1: Bold + Feasibility(并行)
2. 等 Bold 返回 + 审计
3. 如果 Bold PASS → 用 Bold，结束(省 2 次 Flash + 2 次 Qwen audit)
4. 如果 Bold FAIL → Batch 2: Safe_loose + Safe_strict(并行)
5. 决策树选 Safe

这样:
- 正常情况(Bold PASS):1 Flash + 1 Feasibility(Qwen) + 1 Translator(Qwen) + 1 SoftAudit(Qwen) = **~30-50s**
- 异常情况(Bold FAIL):+ 2 Safe Flash + 2 Safe audit(Qwen) = **~100-150s**

这是 review 报告中的 B 方案。

**方案 B: 缩短 Writer JSON 修复超时**

当前 `writer_agent.py` 在第一次解析失败后，用 temperature=0 再调一次 Flash 做 JSON repair。这个 repair call 是导致 Turn 3(132s)和 Turn 6(236s)延迟的主因。

建议:给 repair call 设一个短超时(如 15s)，如果 repair 也超时/失败，直接抛 WriterOutputError，让 Safe Writer 接管。

### 中期(Feasibility 准确性)

- 在 Feasibility system prompt 中注入明确的 world schema 约束("这个世界是 agrarian fantasy，无高科技武器、无心灵感应")
- 或在 story_packet 中增加 `world_schema_notes` 字段，Feasibility 读取后做判断

### 长期

- v0.6.5 的实验证明了:**双 Writer 都走 Flash 不可行**(延迟 3× 恶化)
- 最优路径可能是:**Bold 单 Writer + Feasibility 预筛 + Bold 失败时 fallback 到 Safe**(串行)
- 这样每 turn 通常是 1 Flash + 1-2 Qwen，延迟 30-50s，可接受

---

## 5. 测试状态

全部 253 个单元/回归测试通过。

Smoke test: 7/7 turn 完成，6/7 acceptable(Turn 4 因空输出失败)。
