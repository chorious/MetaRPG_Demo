# reviewVer0.6.5 — v0.6.4 回顾 + v0.6.5 实施计划

日期: 2026-05-18
评审范围: v0.6.4 执行报告（`docs/reports/reportVer0.6.4.md`）+ smoke test 实测产物（`runtime/agentic_runs/smoke_90a0cc2a/`）

---

## 0. Review Target

本评审基于:

```text
docs/reports/reportVer0.6.4.md
runtime/agentic_runs/smoke_90a0cc2a/
  turn_001.json (winner=safe_loose, wall=49.01s)
  turn_002.json (winner=bold,       wall=97.69s)
  turn_003 (未生成 — 进程挂起)
  events.jsonl
set.env (flash_model=deepseek-v4-flash, local_model=qwen3.6-27b-nvfp4)
```

---

## 1. High-Level Judgment

**代码层面成功，运行层面失败**。计划的所有功能都已交付（双 Writer 并行、Feasibility Agent、决策树、可观察性），254 测试全过；但端到端 smoke test 在 Turn 3 挂起，无法证明这套架构在当前基础设施下可用。

报告 P0（延迟超标 7-14×）的诊断**部分错误**:

- 报告归因为"远端 LAN 网络往返"——实际基建是 Pro 5000-48G + 10G LAN + vLLM，昨天工作正常无闪退
- 真正原因是 **27B 模型在 4 路并发下的物理吞吐上限**: 总 throughput ~160 tps / 4 路 ≈ 每路 40 tps；Writer 输出 ~500 token ⇒ 单路 ~12.5s（与实测 10-15s 吻合）
- planVer0.6.4 的"1-2s/turn"假设隐含了"单路 200-400 tps"或"7B 级模型"，与现实不匹配

报告 Turn 3 挂起诊断**完全错误**:

- 报告说"服务器进入不可恢复状态"——实际 vLLM 端无任何 error log
- 必然是**客户端 bug**: parallel_dispatch 的 `fut.result()` 无超时 + 某路 future 没有正常返回

---

## 2. v0.6.4 代码事实速查（实施 v0.6.5 前必读）

| 文件:行 | 事实 | v0.6.5 含义 |
|---|---|---|
| `parallel_dispatch.py:42-44` | dict 迭代 + 无超时 `fut.result()` | 任一 future hang 就锁死主线程 |
| `model_client.py:36` | `httpx.Client(timeout=60.0)` 总超时 | 慢流响应可能不被正确切断 |
| `model_client.py:38-49` | DeepSeek 调用未设 `extra_body={"thinking":...}` | **V4-flash 默认 thinking-mode on，temperature 静默失效** |
| `model_client.py:45-46` | `enable_thinking=False` 只对 Qwen 设 | Qwen 侧 OK，DeepSeek 侧裸奔 |
| `runner.py:82-83` | `flash_client` + `local_client` 各一例 | httpx.Client 线程安全，共享 OK |
| `runner.py:125-148` | Safe Writers 走 `local_client`（Qwen） | v0.6.5 切到 `flash_client` |
| `runner.py:184-200` | audit batch 含 3 路 `_audit_candidate` + 1 路 soft | 每路串行 translator→scanner→hard，累积可达 180s+ |
| `set.env:2` | `flash_model = deepseek-v4-flash` | V4 thinking 默认 on，必须显式关 |

**DeepSeek V4 thinking-mode 陷阱**（来源 [DeepSeek API Docs](https://api-docs.deepseek.com/guides/thinking_mode)）:
> Thinking mode does not support the temperature, top_p, presence_penalty, or frequency_penalty parameters. Setting these parameters will not trigger an error but will also have no effect.

意味着 v0.6.4 给 Bold (temp 0.8) 和 Safe (temp 0.3) 设的差异化温度**从未生效**——Bold 和 Safe 的实际差异只剩 system prompt 一项，外加 reasoning_content 阶段产生的额外延迟。

---

## 3. v0.6.5 Context（变更动机）

用户决策（直接转述）:
- 不再追求 Safe 走 Qwen 的"双引擎冗余"——双 Writer 都切到 DeepSeek Flash
- 先搞清楚 Turn 3 挂起再优化，不要在不知 root cause 的情况下改架构

衍生约束:
- feasibility / translator / scanner / hard_audit / soft_auditor 这次**不动**，仍走 Qwen（用户原话"双 writer 都走 deepseek_flash"，scope 严格按这句话）
- Qwen 调用频次：每 turn 从 7 次降到 4 次（feasibility + 3 audit_candidate + 0 soft 改 1 soft），缓解远端服务器压力

---

## 4. 实施计划

### Phase 1 — 复现并定位 Turn 3 挂起（read-only 观测）

`parallel_dispatch.py` 加临时 trace（验证完即删）:
- submit 时 `print(f"[dispatch] submit {name} t={perf_counter():.1f}", flush=True)`
- `fut.result()` 前后各打一行带 elapsed
- 同步在 `runner.py::_audit_candidate` 内部 pre-translator / post-translator / post-scanner / post-hard 四步打边界

操作: `python scripts/agentic_5turn_smoke_test.py > runtime/v065_diag.log 2>&1`，复现挂起；日志告诉我们卡在哪个 future / 哪一步 LLM 调用。

**假设排序（按可能性）**:
1. **V4 thinking-mode 长响应让 httpx 60s 总超时失效** — Bold 走 Flash 且未关 thinking，reasoning_content 阶段慢但持续滴字节，httpx total timeout 被绕过
2. **audit 串行级联超时** — 单 worker 串 translator+scanner+hard 三次 LLM 调用，任一路慢则放大
3. **Qwen 远端排队** — 累计第三 turn 时队列堵
4. **（已排除）writer JSON 修复死循环** — `writer_agent.py:347-364` 最多一次重试

### Phase 2 — `parallel_dispatch.py` 加超时兜底（防御性，无副作用）

修改 `metarpg/agentic/parallel_dispatch.py::run_parallel`:
- 新增参数 `timeout_per_future: float | None = 120.0`
- 用 `concurrent.futures.as_completed(future_to_name, timeout=...)` 替换 dict 迭代——即使某 future 卡死，其他 future 结果照样能收
- 捕获 `concurrent.futures.TimeoutError`: 剩余未完成 future 调 `fut.cancel()`，结果写入 `TimeoutError(...)`
- ThreadPoolExecutor 改成手动管理（不用 `with`），最后调 `ex.shutdown(wait=False, cancel_futures=True)`，避免 `__exit__` 等卡死线程

`runner.py` 已经全程用 `isinstance(result, Exception)` 兜底（lines 116, 163, 207, 224），TimeoutError 是 Exception 子类——**runner.py 无需改动**。

### Phase 3 — `model_client.py` 加 thinking-mode 开关 + 结构化超时

修改 `metarpg/agentic/model_client.py`:
- 第 36 行 `httpx.Client(timeout=60.0)` → `httpx.Client(timeout=httpx.Timeout(connect=10.0, read=90.0, write=10.0, pool=10.0))`，结构化超时防"慢流"
- 第 38 行 `chat()` 签名加 `thinking: bool = False`
- 第 39-46 行 payload 构建后加:
  ```python
  if "deepseek" in self.model.lower() and not thinking:
      payload["extra_body"] = {"thinking": {"type": "disabled"}}
  ```
- 第 54 行 `chat_json()` 透传 `thinking` 参数

副作用与回滚策略: Bold 关 thinking 后 reasoning 质量略降，但 temperature 0.8 终于生效，整体散文风格反而更接近"任性大胆"的设计意图。若 Bold 散文质量明显倒退，在 `writer_agent.py::run_writer` 里 mode=="bold" 分支显式传 `thinking=True` 做 A/B（一行 hook，可保留）。

### Phase 4 — `runner.py` 把 Safe Writers 路由到 Flash

修改 `metarpg/agentic/runner.py` 第 125-148 行 `batch2_jobs`:
- `safe_loose`: `"client": local_client` → `"client": flash_client`，temperature 保持 0.3
- `safe_strict`: `"client": local_client` → `"client": flash_client`，**temperature 0.3 → 0.5**

理由: thinking 关掉后 temperature 终于生效，给 strict 一个略高于 loose 的随机性来产生 inter-Safe 差异——否则两路都用 0.3 会过于雷同，决策树第二/第三梯队失去意义。

并发评估:
- Flash: 每 turn 1→3 调用（1 bold + 2 safe），DeepSeek 单 key 并发额度完全够
- Qwen: 每 turn 7→4 调用（feasibility + 3 audit + 1 soft），远端服务器压力减半

### Phase 5 — 测试更新

- `tests/test_parallel_dispatch.py` 新增:
  - `test_per_future_timeout_returns_timeout_error`: 3 job、1 个 sleep(5s) 配 `timeout_per_future=0.3`，断言对应结果为 `TimeoutError`，其他正常返回
  - `test_timeout_does_not_block_other_results`: 断言总 wall time < 2 × timeout
- `tests/test_v064_regression.py` 新增:
  - `test_safe_writers_use_flash_client`: monkeypatch 截 `run_parallel` 的 jobs，断言 batch2 的 client 是 flash_client
- 新建 `tests/test_model_client_thinking.py`:
  - stub `httpx.Client.post` 捕获 payload；断言 `deepseek-v4-flash` 且 `thinking=False` 时 `payload["extra_body"]["thinking"]["type"] == "disabled"`
  - 断言 Qwen 模型不加 `extra_body`，仍正确加 `chat_template_kwargs={"enable_thinking": False}`
- `tests/test_writer_modes.py` 现有 `_CapturingClient` 已 client-agnostic，不需要改

### Phase 6 — Smoke Test 验证（4 步逐增量）

按顺序跑 4 次，每次写入 `runtime/v065_phase{N}.log`:

1. **Baseline**（带 Phase 1 trace，未改其他代码）: 复现 Turn 3 挂起，trace 指向具体 future
2. **+Phase 2**（超时兜底）: Turn 3 不再挂起，挂起的 future 转为 TimeoutError 并降级
3. **+Phase 3**（thinking off）: Bold 延迟从 10-30s 降到几秒
4. **+Phase 4**（Safe→Flash，完整 v0.6.5）: 跑全部 7 turn，对比 baseline:
   - 每 turn wall time（目标 8-15s）
   - Bold pass rate（关 thinking 后可能微降）
   - Safe pass rate（Flash 对 JSON-strict 更友好，应上升）
   - Qwen 调用次数（7→4）

完成后写 `docs/reports/reportVer0.6.5.md`，对比 v0.6.4 实测。

---

## 5. 关键修改文件清单

| 文件 | 改动类型 |
|---|---|
| `metarpg/agentic/parallel_dispatch.py` | 加 timeout + as_completed + 手动 shutdown |
| `metarpg/agentic/model_client.py` | 加 thinking 开关 + 结构化 httpx timeout |
| `metarpg/agentic/runner.py` lines 125-148 | Safe 路由切 Flash + strict temp 0.3→0.5 |
| `tests/test_parallel_dispatch.py` | +2 测试 |
| `tests/test_v064_regression.py` | +1 测试 |
| `tests/test_model_client_thinking.py` | 新建 |

`set.env` **不需要改**——`deepseek-v4-flash` 已是目标模型，只是要通过代码层关 thinking。

---

## 6. 验证清单

- [ ] Phase 1 trace 日志识别出 Turn 3 卡住的 future 名称和 elapsed
- [ ] Phase 2 后 `pytest tests/test_parallel_dispatch.py -v` 全通含新增 timeout 测试
- [ ] Phase 3 后 `pytest tests/test_model_client_thinking.py -v` 全通；手测一次 V4 请求确认 `extra_body` 真的进 payload
- [ ] Phase 4 后完整 254+新增测试全通
- [ ] Phase 6 step 4 的 smoke log 显示中位 wall time < 20s 且无挂起
- [ ] 报告内对比 v0.6.4 的 49-97s 与 v0.6.5 实测，明确"目标 ≤7s 是否仍不现实"的结论

---

## 7. 不在本次 scope（留给 v0.6.6+）

- Bold 通过后跳过 Safe Writers（报告中 B 方案）—— 仍可省 2 次调用，但需要决策树重排
- Safe Writers 不走 Translator，改 code-only 审计（报告 C 方案）—— 质感保护减弱，需另设回归
- 本地部署 Qwen 替代远端（报告 D 方案）—— 实际已是本地 LAN，不适用
- 决策树重排（Bold 失败时优先 Safe_strict 的 friction/reframing 分支）—— 需更多 turn 数据支撑
