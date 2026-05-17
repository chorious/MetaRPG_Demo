# MetaRPG Demo v0.2.1 Review

## Summary

v0.2 的方向是对的：从命令 parser 转向 MetaAct / Hypothesis / Claim Validation。但当前实现的核心问题是 **admission control 不够硬**。

现在的风险链条是：

```text
proposer 生成弱假说
-> assembler 允许 UNKNOWN/低置信内容进入 event
-> event 被 session/logger 当成正典变化
-> narrator 把弱假说渲染成现场事实
```

一句话：

```text
想象层泄漏成正典。
```

v0.2.1 不应该急着增加更多 act kind，而应该先把边界立住：

```text
Hypothesis != Patch
Patch != Canon
Mentioned entity != Physically present entity
Transient event != Canon event
Arrival event != Location state change
```

---

## P0. Movement Patch Does Not Move Player

### Symptom

日志里出现：

```text
你穿过狭窄的巷道，抵达了守卫站。
```

但下一回合状态仍然是：

```text
地点: 酒馆
附近的人: 玛拉
```

### Root Cause

`move_to_place` 当前只生成：

```text
event(player_arrived_at_X)
```

但没有生成真正的世界状态转移：

```text
remove_fact at(player, old_place)
add_fact at(player, new_place)
```

### Required Fix

移动类 act 必须产生 hard state delta：

```text
TRY move(player,destination)
REQUIRES destination_exists(destination)
REQUIRES accessible(destination)
REQUIRES connected_or_traversable(current_location,destination)
EFFECT remove_fact(at(player,current_location))
EFFECT add_fact(at(player,destination))
EFFECT canon_event(player_arrived_at_destination)
```

移动应该是 impact 3，不是 impact 0。

### Acceptance

```text
输入: 前往守卫站
期望:
- facts_added includes at(player,guard_post)
- facts_removed includes at(player,tavern)
- 下一状态地点 = 守卫站
- 附近的人 = 拉斯克
```

---

## P0. Sealed `old_mine` Must Not Be Directly Reachable

### Symptom

日志里出现：

```text
player_arrived_at_old_mine
```

但 `old_mine` 是 sealed hard canon。

### Required Fix

区分：

```text
old_mine_gate: 可以抵达的入口地点
old_mine: sealed 内部地点，不可直接 go
```

规则：

```text
go(old_mine) -> redirect/propose go(old_mine_gate)
enter(old_mine) -> requires opened(old_mine) or permission/key/found_passage
```

不能出现直接抵达：

```text
player_arrived_at_old_mine
```

除非已经 canonize 合法进入路径。

### Acceptance

```text
输入: 前往老矿
允许结果 A:
- redirect/propose old_mine_gate
- at(player,old_mine_gate)

允许结果 B:
- rejected: location_sealed(old_mine)

禁止:
- at(player,old_mine)
- player_arrived_at_old_mine as canon event
```

---

## P0. UNKNOWN Claims Cannot Support Canon Events

### Symptom

日志出现半解析事件进入正典变化：

```text
player_observed_了一眼角落
player_listened_to_mara
player_arrived_at_old_mine
```

这些不是稳定的 canon facts，只是 proposer 的弱解释或字符串残渣。

### Root Cause

`assembler.py` 当前对 impact 0 基本无条件放行：

```text
if impact == 0: allow
```

这让未知 claim 支撑的事件直接进入 `canon_delta.events`。

### Required Fix

事件必须分级：

```text
transient_event: 只进入 narration/archive，不进入 canon delta
canon_event: 可以进入 canon delta，但不改变硬状态
fact_event: 必须伴随 hard fact delta
```

建议 effect kind：

```text
transient_event(...)
canon_event(...)
add_fact(...)
remove_fact(...)
```

规则：

```text
UNKNOWN claim -> 只能支撑 transient_event
PROBABLE claim -> 可支撑低影响 narration/social texture，但不能支撑 hard canon
ACCEPTED/INFERRED core claims -> 可支撑 canon_event
ACCEPTED core claims -> 可支撑 hard fact delta
```

### Acceptance

```text
输入: 随便说一句无法归类的话
期望:
- 可以有 transient speak/gesture
- 不进入 hard canon facts
- 不出现奇怪 event 被列为正典变化
```

---

## P1. Renderer Confuses Mentioned Entities With Physically Present Entities

### Symptom

玩家在酒馆，状态显示附近只有玛拉，但 LLM 叙事写：

```text
角落里的鲁斯克则冷冷地注视着这一幕。
```

Rusk 不在酒馆。

### Root Cause

local slice 里有 `rusk_pressures_mara` 或 `debtor_creditor(mara,rusk)`，renderer 看到 Rusk，就把他当成现场实体。

### Required Fix

传给 renderer 的上下文必须分级：

```text
CURRENT_LOCATION: tavern
PHYSICALLY_PRESENT: player, mara
MENTIONED_ONLY: rusk
BELIEF_ONLY: rusk_pressures_mara
MOTIF_RELATED: debtor_creditor(mara,rusk)
```

Renderer 规则：

```text
PHYSICALLY_PRESENT 可以行动、说话、注视玩家。
MENTIONED_ONLY 只能被提及，不能被写成在现场。
BELIEF_ONLY 只能作为怀疑/推断，不可写成事实。
MOTIF_RELATED 只能作为关系背景，不可实体化。
```

### Acceptance

```text
输入: 看了一眼角落的鲁斯克，准备请他也喝一杯
当前地点: tavern
Rusk location: guard_post
期望:
- 不能写 Rusk 在角落
- 不能与 Rusk 现场互动
- 可生成: player thinks about/inquires about/invites absent Rusk
- 或 rejected/needs_target_present for direct interaction
```

---

## P1. Path A Old Parser Still Pollutes v0.2

### Symptom

自由中文被旧 parser 直接切成奇怪目标：

```text
player_observed_了一眼角落
```

### Required Fix

旧 parser 只能处理强格式命令：

```text
问玛拉关于矿场
去守卫站
观察玛拉
质问玛拉关于矿场
```

如果 target/topic/place 不在白名单里：

```text
canonical entities: player, mara, rusk, iven
canonical locations: tavern, guard_post, old_mine_gate, mara_cellar, old_mine
canonical topics: mine, old_mine, iven, local_news, service, ale
```

则 Path A 不应产出 patch，必须降级给 MetaAct proposer。

### Acceptance

```text
输入: 看了一眼角落的鲁斯克，准备请他也喝一杯
期望:
- 不产生 player_observed_了一眼角落
- 进入 MetaAct hypothesis
- claim validation 判断 Rusk 不在现场
```

---

## P1. Arrival Narration Must Be Driven By Hard State Delta

### Problem

Narrator 当前看到：

```text
event(player_arrived_at_guard_post)
```

就会写玩家抵达守卫站，即使没有 `at(player,guard_post)` 的 fact delta。

### Required Fix

Arrival narration requires hard delta：

```text
facts_added contains at(player,destination)
facts_removed contains at(player,old_location)
```

否则只能写：

```text
你准备前往守卫站。
你提到想去守卫站。
你看向守卫站的方向。
```

不能写“抵达”。

### Acceptance

```text
canon_delta.events contains player_arrived_at_guard_post
but no at(player,guard_post) added
=> narrator must not say arrived
```

---

## P2. Session Log Should Expose Hypothesis vs Canon

The session log currently collapses too much into “正典变化”。 For v0.2.1, logs should show at least:

```text
假说: order_drink / confidence=72%
声明验证:
- same_location(player,mara): accepted
- place_supports(tavern,drink_service): accepted
- item_plausible(ale,tavern): accepted/probable
采纳后果:
- canon_event(...)
- rel_delta(...)
未采纳后果:
- ...
正典变化:
- only accepted canon deltas
```

This matters because the whole architecture is about separating imagination from admission.

---

## Suggested v0.2.1 Implementation Order

1. Fix movement patch assembly.
2. Add claim validators for:
   ```text
   accessible(destination)
   destination_exists(destination)
   connected_or_traversable(current,destination)
   ```
3. Split event effects into transient/canon/hard fact consequences.
4. Gate UNKNOWN claims so they cannot enter hard canon.
5. Add renderer entity-presence sections.
6. Restrict Path A parser to canonical targets/topics/locations.
7. Add regression tests from the failing session.

---

## Regression Tests

### Movement Works

```text
input: 前往守卫站
assert facts_added includes at(player,guard_post)
assert facts_removed includes at(player,tavern)
assert current_location == guard_post
assert nearby_npcs == [rusk]
```

### Sealed Mine Is Not Directly Reachable

```text
input: 前往老矿
assert not Fact("at", ("player", "old_mine"))
assert no canon_event player_arrived_at_old_mine
```

### Mentioned Rusk Does Not Become Present

```text
setup: player at tavern, rusk at guard_post
input: 看了一眼角落的鲁斯克，准备请他也喝一杯
assert no narration says Rusk is in tavern/corner
assert no direct same_location interaction with rusk is accepted
```

### Unknown Target Does Not Become Canon Event

```text
input: 观察了一眼角落
assert no canon_event player_observed_了一眼角落
assert allowed transient_event or observe(scene)
```

### Arrival Requires Fact Delta

```text
if event player_arrived_at_X exists without at(player,X) delta
assert narrator does not say arrived
```

---

## Final Review Line

v0.2 的方向已经接近正确：玩家发出行为，系统生成假说，代码验证声明。但 v0.2.1 必须把门槛收紧。

The next milestone is not better imagination. It is stricter admission.

```text
Imagine wide.
Admit narrow.
Canonize only what survived validation.
```
