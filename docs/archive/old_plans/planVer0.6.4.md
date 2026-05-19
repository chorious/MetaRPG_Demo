# MetaRPG planVer0.6.4 — 双 Writer 并行流水线

## Context

### 问题背景

v0.6 流水线在玩家任性输入（"抽光剑斩 Mara"、"读 Mara 心思"、"找不在场的 Rusk 谈话"）下会死机：Writer 没有"世界化拒绝"的工具，三个坏选项之间撞墙——

- 接梗写光剑 → Hard Auditor 抓 `acquire_item:lightsaber` 不合法 → hard_fail
- 写"你没有光剑" → 元叙述破第四面墙
- 偷换意图写"伸手摸腰间" → 玩家觉得"游戏没听我的话"

Hard Auditor 是事后追责，不是事前裁决；当 Writer 被任性带进沟里，没人负责把"不可能"翻译回世界语言。

### 产品定位（已确认）

- "近乎酒馆的体验，又存在真实约束"——必须承担玩家任性
- 任性回应**用世界的语言**说出，绝不出现 `hard_fail` / `absent_object_action` 这类系统词
- 风格倾向**拒绝+解释**："你的手抓向腰间——什么都没有"
- 延迟上限 10-15s，当前 8-12s，不能堆 agent，必须靠并行

### 模型资源（关键校准）

- DeepSeek **Flash**（远程，~2-5s/call）— Writer 专属
- 本地 **Qwen3.6-27B**（localhost:8101，每路 ~1-2s，**4 路真并发，每路独立 64K 上下文**）— 这是性能预算的真正杠杆
- DeepSeek **Pro** — Teacher 离线用，热路径不碰

64K × 4 并发意味着：本地 Qwen 是一个**没被用满的、和 Flash 同档创作能力的免费资源**。当前流水线只把它当审查/分类器用——这是核心浪费。

---

## 核心设计：双 Writer 三候选 + 第二批并行审查

### 思路一句话

**让本地 Qwen 同时写一份"保守版本"作为兜底**，Flash 写"激进版本"作为首选。审计选哪个，不靠规则压 Writer，靠**事后从多份候选里挑**。

这把"规则 vs 风味"的矛盾**从串行的取舍变成并行的备选**——Bold Writer 永远不被规则压制（它失败就被丢弃），Safe Writer 永远保底（它从一开始就在规则内创作）。

### 流水线时序

```
T=0.0  StoryPacket build                                       0.3s
        ↓
T=0.3  第一批 fan-out（Flash 1 路 + Qwen 1 路）
         Flash slot:  Writer_Bold (temp=0.8, 无 feasibility)   3.0s
         Qwen slot 1: Feasibility (轻量裁决)                   1.0s
        
T=1.3  Feasibility 返回 → 启动 Safe Writers（Qwen 2 路）
         Qwen slot 1: Writer_Safe_loose (temp=0.3, 看 facts)   1.8s
         Qwen slot 2: Writer_Safe_strict (conservative prompt) 1.8s
        
T=3.3  Bold + Safe_loose + Safe_strict 全部就绪
        
T=3.3  第二批 fan-out（Qwen 4 路吃满 + code 并行）
         Qwen slot 1: Translator on Bold                       1.5s
         Qwen slot 2: Translator on Safe_loose                 1.5s
         Qwen slot 3: Translator on Safe_strict                1.5s
         Qwen slot 4: SoftAuditor on Bold (Safe 不审 soft)     2.0s
         [code]:      Scanner on 三份 (并行 0.2s)
        
T=5.3  Translator/SoftAuditor 全部完成
        
T=5.3  HardAuditor (code) on 三份                              0.5s
        ↓
T=5.8  决策树（按优先级选）:
         Bold.hard_pass?       → use Bold
         Safe_loose.hard_pass? → use Safe_loose
         Safe_strict.hard_pass? → use Safe_strict  
         all failed?          → refusal_fallback 模板
        ↓
T=5.8  Committer + Scorecard                                   0.3s

总延迟 ~6.1s（远低于 10s 上限）
```

### Feasibility 的输出形态（关键设计）

不输出"写作指令"，**只输出事实和锚点**。Safe Writer 拿到事实自己决定怎么写：

```json
{
  "stated_action": "draw_weapon_and_attack",
  "stated_props": ["lightsaber"],
  "stated_targets": ["mara"],
  "feasibility_facts": [
    "玩家声称使用'光剑'，但此世界 schema 无此物（agrarian fantasy tavern）",
    "玩家声称攻击 Mara，但场景无 combat affordance"
  ],
  "preserve_player_voice": ["斩"],
  "world_response_kind": "absence | friction | reframing | accept"
}
```

**三个字段的职责分离**：

- `feasibility_facts`：**陈述事实，不写指令**。Qwen 看到事实会自己融入散文。规则的"硬"部分进这里。
- `preserve_player_voice`：**最低承诺**。玩家用了"斩"，散文必须以某种方式承认这个动作（哪怕扑空）。避免偷换玩家意图。
- `world_response_kind`：**只在 prompt 路由用**——Safe Writer 根据 kind 挂不同的 system prompt（absence / friction / reframing / accept 四套）。规则做在路由层，不污染散文层。

**关键设计**：world_response_kind 不直接出现在 Writer 看到的 prompt 内容里，只是决定挂哪套 system prompt。这避免了 Writer "按规则写"——它只看到一份合适的 prompt 引导和事实陈述。

### Bold Writer 的特殊性

Bold Writer **拿不到 Feasibility 输出**——它和 Feasibility 并发跑。这是有意为之：

- 让 Bold 完全自由发挥（这是风味的源头）
- 如果输入合法，Bold 大概率通过审计，被采用——风味无损
- 如果输入任性，Bold 大概率失败被丢弃——Safe 接管，靠 Feasibility facts 写出有质感的拒绝

**Bold Writer 永远不被规则压制。它的失败是预期的，不是故障。**

### 四套 Safe Writer system prompt

`absence_prompt` 示例（不是任务指令，是风味引导）：
```
玩家的某个声称落空了。让这种落空在身体感官中发生——
一个手势够不到的距离、一个本应有重量却轻飘的瞬间、
一阵不该这么静的静。
不要解释，让玩家自己读出。
NPC 可以看到这个错位，但她也不完全理解。
preserve_player_voice 列出的词必须以某种方式出现在散文里。
```

`friction_prompt`、`reframing_prompt`、`accept_prompt` 类似，每套都是风味化的引导，不是任务清单。

### 决策树细节

```python
def select_winner(bold, safe_loose, safe_strict, audits):
    candidates = [
        ("bold", bold, audits["bold"]),
        ("safe_loose", safe_loose, audits["safe_loose"]),
        ("safe_strict", safe_strict, audits["safe_strict"]),
    ]
    for name, writer_output, audit in candidates:
        if audit["passed"]:
            return name, writer_output, audit
    return "fallback", refusal_fallback(feasibility), {"passed": True, "synthetic": True}
```

**决策顺序固定**：Bold > Safe_loose > Safe_strict > template fallback。
Bold 通过就用 Bold（哪怕平庸）——保 Flash 的语感优势。

---

## 文件改动清单

### 新增文件

- **`metarpg/agentic/feasibility.py`**
  - 函数：`run_feasibility(story_packet, player_input) -> FeasibilityReport`
  - 模型：本地 Qwen（`make_client("local")`）
  - 含 deterministic 预筛：先查 story_packet 的 visible_entities / visible_objects / inventory / allowed_effect_kinds——若玩家声称的物件/实体明显不在 schema 内，直接给 `world_response_kind=absence` + 对应 facts，不必走 LLM。其他情况交给 LLM。
  
- **`metarpg/agentic/refusal_fallback.py`**
  - 函数：`generate(feasibility: FeasibilityReport) -> list[Segment]`
  - 无 LLM 模板兜底（三套 world_response_kind 各一组中文模板）
  - 仅在三份 Writer 候选全部失败时启用——预期触发率 <5%
  
- **`metarpg/agentic/parallel_dispatch.py`**
  - 函数：`run_writers_parallel(story_packet, player_input) -> dict[name, WriterOutput]`
  - 函数：`run_audits_parallel(candidates: dict, story_packet, world) -> dict[name, audit_result]`
  - 用 `concurrent.futures.ThreadPoolExecutor(max_workers=4)`（Qwen 后端是真并发，httpx.Client 是线程安全的）
  - 注意：Flash 和 Qwen 用不同的 client 实例，避免 client 内部状态冲突
  
- **`evals/cases/lightsaber_absence.json`**（任性回归）
- **`evals/cases/absent_npc_talk.json`**（任性回归）
- **`evals/cases/ambient_guests_pass.json`**（v0.6.1 review §11 要的）
- **`evals/cases/notebook_medium_issue.json`**（v0.6.1 review §11 要的）
- **`evals/cases/npc_offer_needs_patch.json`**（v0.6.1 review §11 要的）

### 修改文件

- **`metarpg/agentic/schemas.py`**：
  - 新增 `FeasibilityReport` dataclass，字段：`stated_action / stated_props / stated_targets / feasibility_facts / preserve_player_voice / world_response_kind`
  - `TurnDraft` 增加 `feasibility: FeasibilityReport | None`、`writer_candidates: dict[str, WriterOutput]`、`winner_name: str` 字段
  - `world_response_kind` 字面量类型: `"absence" | "friction" | "reframing" | "accept"`

- **`metarpg/agentic/writer_agent.py`**：
  - `run_writer()` 签名扩展：`temperature: float = 0.7`、`feasibility: FeasibilityReport | None = None`、`mode: str = "bold"`
  - 内部按 mode 切 system prompt：
    - `bold` → 现有 prompt（保持不变）
    - `safe_loose` → 现有 prompt + 注入 feasibility_facts 段 + temp=0.3
    - `safe_strict_<kind>` → 四套新 prompt（按 world_response_kind 选）+ 注入 feasibility_facts
  - 新增 `_SAFE_PROMPT_ABSENCE` / `_SAFE_PROMPT_FRICTION` / `_SAFE_PROMPT_REFRAMING` / `_SAFE_PROMPT_ACCEPT` 常量

- **`metarpg/agentic/model_client.py`**：
  - `LlmClient` 加文档：确认 httpx.Client 线程安全
  - 增加可选的 `make_client_pool(kind, size=4)` 返回多个独立实例——避免多个并发请求争用一个 client 的内部状态（实际可能不需要，但留接口）

- **`scripts/agentic_5turn_smoke_test.py`** 全面重写流水线：
  - 删除当前的串行 Translator → Scanner → HardAudit → SoftAudit 流程
  - 用 `parallel_dispatch.py` 跑两批 fan-out
  - 决策树选 winner
  - 评分块**调用 `TurnScorecard.compute_player_experience()`**（修 v0.6.1 review §3）
  - 把 `winner.soft_audit["issues"]` 读进 `sc.soft_issues`（修 v0.6.1 review §3）
  - 加 turn 6：`"我抽出光剑斩向 Mara"`（验证 absence 路径）
  - 加 turn 7：`"我读取 Mara 的心思"`（验证 reframing 路径）

- **`metarpg/agentic/repair_loop.py`**：
  - **删除二次 Writer 调用**——v0.6.4 永远只调一次 Bold，并行 Safe 兜底
  - 文件保留但函数体改为：若 winner 是 fallback，记录失败原因到 `rewrite_history`；否则什么都不做
  - 或更激进：删掉整个文件，逻辑挪进 parallel_dispatch.py 的决策树

- **`metarpg/agentic/hard_auditor.py`**（小修两处 bug，v0.6.1 review §4）：
  - `_check_patch_validity` 中 consume_item 的 hard/medium severity 倒置（line 272-296）：item 在 inventory/visible_objs 但 facts 没有 → medium（数据不一致）；都没有 → hard_fail（凭空消费）
  - `_check_alignment` 中 `npc_offer` 被双重检查（line 328-368）：合并 speech_claims 和 offer_claims 逻辑

- **`metarpg/agentic/story_packet.py`** + **`metarpg/agentic/committer.py`**（修 v0.6.1 review §6.1）：
  - WorldState 增加 `event_log: list[dict]` 字段（在 `metarpg/models.py`，或用现有结构）
  - committer 把 `transient_event` / `observe_reaction` / `journal_note` 的 args 推入 event_log
  - `_recent_events()` 读 event_log 而非只读 facts
  - **这是双 Writer 方案能 work 的前提**——否则 turn N+1 的 story_packet 不知道 turn N 玩家做了什么

### 不动

- `committer.py` 的核心 apply 逻辑（只加 event_log push）
- `teacher_agent.py`
- `translator_agent.py`、`scanner.py`、`soft_auditor_agent.py`
- `editor_agent.py`（v0.6.4 不走 repair-rewrite 路径，但保留供未来用）

---

## 关键风险与缓解

### 风险 1：Qwen 在 conservative+facts 约束下能否保留质感

**这是整个方案的成败点**，用户已表态可接受不行就换模型。  
缓解：
- 四套 Safe prompt 是**风味化引导**而非任务清单，最大化保留 Qwen 的创作空间
- Bold > Safe_loose > Safe_strict 决策顺序，先尝试质感更强的选项
- 兜底模板只在 <5% 的全失败场景启用，不污染主流体验
- **实施期建议**：先单独跑 5-10 个任性输入手工读 Safe Writer 输出，看质感是否可接受，再决定是否升级 Safe Writer 模型

### 风险 2：Qwen 4 路并发是否真的并发

用户已确认支持 4 路且每路 64K。但 vLLM/llama.cpp 后端的实际吞吐需要压测。  
缓解：
- `tests/test_parallel_dispatch.py` 第一项测试就是真实并发压测——3 个 1s 调用同时发，验证 wall time < 1.5s
- 若并发不达预期，回退方案：Translator on Safe_loose 和 Safe_strict 合并（一个 Qwen 调用同时审两份），仍能省 1+s

### 风险 3：Bold Writer 看不到 Feasibility 会不会经常失败浪费 Flash 钱

**这是设计目标**，不是 bug——Bold 失败时 Safe 接管。但若 Bold 在**合法**输入下也常失败，那 Flash token 被白烧。  
缓解：
- v0.5 已经证明 Flash 在 story_packet 约束下能写得合法。只有真任性输入才会让 Bold 失败
- 监控 Bold 失败率：若 >30%（含合法输入），重新审视 Bold prompt
- Bold 的 system prompt 保持现有内容（已被验证），不动

### 风险 4：决策树永远选 Bold 会不会埋没 Safe 的工作

**这是有意的**——永远优先 Bold 的语感。Safe 的工作只在 Bold 失败时被用。  
副作用：Safe Writer 的 token 在 Bold 通过时被丢弃——可接受，因为 Qwen 是免费的。

### 风险 5：feasibility 误判合法输入为任性

例：玩家说"我看看墙上的画"，packet 里没列画。  
缓解：
- Feasibility 的 deterministic 预筛只对**明显 schema 外**的物件标记 absence（光剑、手机、激光武器这类）
- 普通"未列出但合理"的物件由 LLM 判断，**默认倾向 accept**——Qwen prompt 明确："不确定时返回 accept"
- 即使误判为 friction/reframing，Bold 那份不受影响——Bold 是平行跑的，看不到 Feasibility——所以 Bold 仍然会自由写"看看墙上的画"，HardAuditor 不会因为 packet 没列就否决（只要不引入 add_fact），Bold 通过被采用，Safe 的误判被丢弃

**这是双 Writer 架构最优雅的地方**：Feasibility 误判不致命，因为 Bold 是个独立轨道。

---

## 验证流程

### 单元测试（新增）

- **`tests/test_feasibility.py`**：
  - 光剑输入 → `world_response_kind == "absence"`，`feasibility_facts` 含"光剑"和"无此物"
  - 读心术输入 → `world_response_kind == "reframing"`
  - "看看墙上的画"（packet 无画）→ `world_response_kind == "accept"`（默认倾向）
  - "找 Rusk 说话"（Rusk 不在场）→ `world_response_kind == "absence"`
  - 无 LLM 时（mock client 不可用）→ deterministic 预筛对光剑仍能给 absence

- **`tests/test_parallel_dispatch.py`**：
  - 真实并发压测：3 个 mock 1s 调用同时发，wall time < 1.5s
  - 一路异常其他继续：mock 一个 future 抛错，其他正常返回
  - Flash + Qwen 同时跑：用真实 client（如果 set.env 有 key），验证 Bold 和 Safe 同时返回

- **`tests/test_writer_modes.py`**：
  - `mode="bold"` → 不含 feasibility 内容在 prompt 里
  - `mode="safe_loose"` → prompt 含 feasibility_facts 段
  - `mode="safe_strict_absence"` → 挂 absence system prompt

### 端到端测试

跑改造后的 `agentic_5turn_smoke_test.py`，包含 7 turn：

```
turn 1: 要了一杯啤酒              (accept)
turn 2: 耸了耸肩 "这杯酒真不错"    (accept)
turn 3: 一饮而尽                   (accept)
turn 4: "这附近发生了什么事情么？" (accept)
turn 5: 静静地记下了这条信息       (accept)
turn 6: 我抽出光剑斩向 Mara        (absence ← 新增)
turn 7: 我读取 Mara 的心思          (reframing ← 新增)
```

每 turn 检查：

1. `turn_NNN.json` 含 `feasibility` 字段、`writer_candidates` 三份、`winner_name`
2. turn 1-5 应当 `winner_name == "bold"`
3. turn 6-7 大概率 `winner_name == "safe_loose"` 或 `"safe_strict"`
4. 任性 turn 的 `player_output` 不含"光剑"、"读心"、"hard_fail"、"absent" 等系统/原文词
5. 任性 turn 的 `player_output` 含某种身体感知（"腰间"、"空手"、"凝视"、"目光"任一）
6. `admitted_patch` 在任性 turn 不含 `acquire_item:lightsaber` 或类似不合法 effect
7. 总延迟（每 turn wall time）< 8s

### 性能基线

- 跑 7-turn 测试 3 次取中位数
- 当前基线：~8-12s/turn
- 目标：≤7s/turn 中位数

若达不到，先检查 Qwen 并发真实性（用 test_parallel_dispatch.py 压测）。

### 人工读

最终验收：3 个人盲读 turn 6-7 的 player_output（不告诉他们是哪个 Writer 写的），判断"这段散文是不是有质感的拒绝"。若 2/3 通过则验收。

---

## 实施顺序建议（给执行者）

按风险递增、依赖正确的顺序：

1. **修 v0.6.1 review 列出的工程 bug**（独立、低风险）
   - hard_auditor.py 两处 bug
   - story_packet recent_events / committer event_log
   - 跑现有 smoke test 不退步
2. **新增 schemas**（FeasibilityReport，TurnDraft 字段）
3. **写 parallel_dispatch.py** + 单元测试（先用 mock 验证并发）
4. **写 feasibility.py** + 单元测试（先 deterministic 路径，再 LLM 路径）
5. **改 writer_agent.py 支持 mode**（先只加 safe_loose，验证 prompt 切换工作）
6. **加四套 safe_strict prompt**（按 world_response_kind）
7. **写 refusal_fallback.py 模板**
8. **重写 smoke test 流水线**（用双 Writer 三候选 + 决策树）
9. **新增 5 个 eval case**
10. **跑 7-turn 端到端 + 人工读 turn 6-7**

每一步独立可验证。任何一步失败可回到上一步状态。

---

## 不在本次范围

- Director / Reader / Highlight Memory 等"进攻位" agent——用户已明确不加角色
- Editor 真正的 narrative rewrite（v0.6.4 用 Safe Writer 兜底替代 repair）
- Teacher 自动促升规则——保留 manual gate
- UPF bridge / Rust 集成
- 修改 LLM 模型选择——若 Safe Writer 质感不行再升级

---

## 总结

v0.6.4 的核心改动是**结构性的**，不是参数调优：

1. **Writer 不再是单点**——三份候选并发跑，事后选
2. **本地 Qwen 从"审查者"变"创作者"**——吃满 4 路并发，写 Safe 兜底
3. **规则做在 prompt 路由层**——四套 Safe system prompt 按 world_response_kind 切换，不直接污染散文层
4. **Feasibility 不写指令**——只陈述事实和锚点（preserve_player_voice）
5. **Bold Writer 完全自由**——它看不到 Feasibility，失败是预期的不是故障
6. **顺带修掉 v0.6.1 review 列出的所有工程问题**——scorecard 失真、recent_events 断层、3 个新 eval case、hard_auditor 两处 bug

预期成果：
- 任性输入不再死机，回应**用世界的语言**说出
- 风味在合法输入下完全保留（Bold 通过率应 >90%）
- 延迟 ~6s，留出余量
- Flash 调用仍是 1 次/turn，成本不变

执行者：Sonnet（按上方"实施顺序建议"分 10 步推进）
