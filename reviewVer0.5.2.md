# MetaRPG Dev v0.5.2 Review

## Summary

v0.5.1 的方向是正确的：它已经把 MetaRPG 从纯 CLI/日志验证推进到了可被 UPF 调用的 playable bridge 原型。

但当前实现还不能算完成“UPF playable shell”。更准确的状态是：

```text
Python MetaRPG core: mostly working
Python bridge/session/snapshot: working prototype
Rust bridge client: implemented but not locally verified
UPF playable integration: partial
Save/load authority continuity: incomplete
```

核心差距不是 MetaRPG 理论层，而是 UPF 集成层。

当前最重要的问题是：

```text
MetaRPG 返回了权威世界状态，
但 UPF 没有真正把这个状态当作 UI/存档/面板的权威来源。
```

一句话：

```text
Bridge exists, but playable authority is not fully wired.
```

---

## Verification Snapshot

已验证：

```text
python -m pytest
=> 162 passed
```

备注：

```text
pytest 有 .pytest_cache 写入权限 warning，但不影响测试通过。
```

手动验证：

```text
python -m metarpg.bridge step
```

英文输入：

```text
go to guard post
```

返回结果正常：

```text
ok=true
snapshot.location=guard_post
snapshot.nearby_npcs=[rusk]
debug.budget=large
apply_report includes event + add_fact
```

未能验证：

```text
cargo test
```

原因：

```text
cargo is not recognized
```

所以 Rust/UPF 侧目前只做了静态审查，没有完成编译级确认。

---

## Overall Completion Estimate

以 `planVer0.5.1-playable-upf-bridge.md` 为目标线：

| Area | Status | Estimate |
|---|---:|---:|
| Python reasonability core | Good | 80-90% |
| Bridge protocol/CLI | Good prototype | 75-85% |
| Bridge session persistence | Medium-good | 65-75% |
| Snapshot export | Medium | 55-65% |
| Rust bridge subprocess client | Implemented, unverified | 45-60% |
| UPF engine routing | Partial | 40-50% |
| UPF panel/debug display | Weak | 25-40% |
| UPF save/load with MetaRPG state | Weak | 15-30% |
| Full playable Greyfen loop in UPF | Unconfirmed | 30-45% |

Practical read:

```text
As Python bridge prototype: ~75-85%
As v0.5.1 playable UPF integration: ~45-55%
```

---

## P0. UPF Does Not Apply MetaRPG Snapshot To Its UI State

### Symptom

The Python bridge returns a useful snapshot:

```json
{
  "location": "guard_post",
  "nearby_npcs": ["rusk"],
  "facts": [...],
  "relations": [...],
  "beliefs": [...]
}
```

But in UPF engine routing, after a successful bridge response, the emitted snapshot is still generated from UPF's internal game state:

```rust
let snapshot: GameStateSnapshot = (&self.game_state).into();
```

This means the player may see MetaRPG narration in chat while UPF panels still reflect the old UPF state.

### Why This Matters

v0.5.1's hard boundary is:

```text
MetaRPG decides world consequences.
UPF displays them.
```

Currently UPF displays messages from MetaRPG, but does not fully display MetaRPG's world state.

That leaves the playable shell in a half-integrated state:

```text
chat: MetaRPG-owned
panels: mostly UPF-owned
save: UPF-owned
```

This weakens the “single authoritative world logic source” goal.

### Required Fix

Add an explicit mapping layer:

```rust
fn apply_metarpg_snapshot_to_upf_state(
    game_state: &mut InternalGameState,
    snapshot: &MetaRpgBridgeSnapshot,
)
```

Minimum mapping:

```text
snapshot.location        -> player/world status section
snapshot.nearby_npcs     -> NPC panel proximity
snapshot.known_entities  -> known NPC/location panel data where possible
snapshot.relations       -> relationship/debug panel
snapshot.beliefs         -> MetaRPG debug or world-state panel
snapshot.active_hooks    -> debug/quest-like panel
snapshot.frontiers       -> debug panel
```

Do not force every MetaRPG concept into UPF's RPG stat model.
It is acceptable to add a separate MetaRPG snapshot/debug store to `InternalGameState`.

### Acceptance

After bridge response:

```text
MetaRPG snapshot.location=guard_post
UPF visible location/status shows guard_post
nearby NPC panel shows Rusk, not Mara
debug panel can show active_hooks/frontiers/beliefs
```

---

## P0. Bridge Failure Falls Back To UPF World Mutation

### Symptom

When MetaRPG mode is enabled and the bridge call fails, UPF currently adds an error message and then falls through to original UPF behavior:

```text
[MetaRPG Bridge Error] ... Falling back to original UPF behavior.
```

### Why This Matters

This violates the single-authority rule.

If a player input fails in MetaRPG mode, the safest result is:

```text
input accepted as user message
world mutation blocked
system error shown
player may retry
```

The unsafe result is:

```text
MetaRPG failed to judge the action
UPF independently interprets and mutates the same action
```

That reintroduces split-brain world logic.

### Required Fix

In MetaRPG mode:

```text
bridge success -> apply/display MetaRPG result
bridge error   -> show system error and stop
```

Do not fall through to original LLM/event path unless the user explicitly disables MetaRPG mode.

### Acceptance

With MetaRPG mode enabled and Python bridge unavailable:

```text
UPF displays bridge error
no original LLM call runs
no UPF events are applied
no inventory/location/quest mutation occurs
```

---

## P0. UPF Save Does Not Preserve MetaRPG Session Identity

### Symptom

`GameSave` currently stores:

```text
world
player
party
messages
internal_state
speaker_colors
character image
```

It does not store:

```text
metarpg_project_path
metarpg_session_id
metarpg_turn
last_bridge_response_hash
optional metarpg_state_json_blob
```

### Why This Matters

The Python bridge stores authoritative state in:

```text
runtime/bridge_sessions/{session_id}.json
```

If UPF save/load does not remember which MetaRPG session it belongs to, then loading a save can attach the UI to the wrong reasonability state.

This directly threatens:

```text
"刚才的情形" can still resolve if hook remains active
```

### Required Fix

Extend `GameSave` with:

```rust
#[serde(default)]
pub metarpg: Option<MetaRpgSaveLink>

pub struct MetaRpgSaveLink {
    pub enabled: bool,
    pub project_path: String,
    pub session_id: String,
    pub turn: Option<i32>,
    pub last_bridge_response_hash: Option<String>,
}
```

On save:

```text
include current MetaRPG bridge config
include last response turn/hash if available
```

On load:

```text
restore MetaRPG mode/config
reconnect to same session_id
warn if session file missing or turn/hash mismatches
```

### Acceptance

After save/load:

```text
MetaRPG mode remains enabled if it was enabled
same session_id is restored
recent hooks/frontiers are still available through bridge
UPF warns instead of silently continuing if session state is missing
```

---

## P1. MetaRPG Debug Toggle Is Not Actually Wired As A Separate Control

### Symptom

The UI has:

```text
Show MetaRPG Debug
```

But engine behavior appears tied to the general:

```text
debug_messages_enabled
```

The bridge request always uses default options from Rust, and the dedicated UI field is not clearly passed into the engine/bridge request path.

### Required Fix

Extend `EngineCommand::SetMetaRpgMode` or add a separate command:

```rust
SetMetaRpgConfig {
    enabled,
    project_path,
    session_id,
    show_debug,
}
```

Then set:

```json
"options": {
  "include_debug": show_debug
}
```

Rendering should follow:

```text
normal narration: always visible
MetaRPG debug summary: only visible when metarpg_show_debug=true
general UPF debug: controlled separately
```

### Acceptance

Toggling only `Show MetaRPG Debug` changes whether MetaRPG budget/frontier/affordance summaries appear, without changing unrelated UPF debug logs.

---

## P1. Rust Bridge Timeout Is Configured But Not Enforced

### Symptom

`MetaRpgBridgeConfig` includes:

```rust
timeout_seconds: u64
```

But `call_metarpg_bridge` uses:

```rust
child.wait_with_output()
```

This waits indefinitely.

### Risk

If Python hangs, UPF hangs during player input.

### Required Fix

Implement timeout handling.

Options:

```text
Use a worker thread + recv_timeout
Use wait-timeout crate
Use async process later if architecture changes
```

For v0.5.2, a simple blocking timeout is enough.

### Acceptance

If Python bridge sleeps longer than configured timeout:

```text
UPF receives bridge timeout error
Python subprocess is terminated
no world mutation occurs
UI remains responsive
```

---

## P1. Bridge Apply Report Is Too Thin

### Symptom

Bridge currently maps:

```text
canon_delta.events     -> event(kind="event")
canon_delta.facts_added -> event(kind="add_fact")
```

But it does not carry enough detail for:

```text
facts_removed
knowledge_added
relations changed
belief deltas
transient events
rejected/deferred events
risk flags
```

### Required Fix

Expand bridge apply report to include:

```text
applications
rejected
deferred
facts_added
facts_removed
knowledge_added
relation_deltas
belief_deltas
transient_events
risk_flags
```

This can remain JSON-first. It does not need full typed Rust mapping yet.

### Acceptance

For movement:

```text
facts_added includes at(player,guard_post)
facts_removed includes at(player,tavern)
```

For communication hook:

```text
knowledge_added shows Mara learned the reported event
hook consumption appears in debug or apply report
```

---

## P1. UPF Context Is Not Used Meaningfully

### Symptom

The bridge request type supports:

```json
"upf_context": {
  "player_name": "...",
  "world_title": "...",
  "inventory": [],
  "party": [],
  "npcs": [],
  "quests": []
}
```

Rust currently sends:

```rust
upf_context: None
```

Python bridge also mostly ignores `upf_context`.

### Required Fix

Pass minimal context from UPF:

```text
player_name
world_title
visible_location if available
inventory
party
known NPCs
active quests
```

Python should treat this as UI context, not authority over consequences.

### Acceptance

Bridge request generated from UPF includes player/world names and inventory/party context.
MetaRPG result remains authoritative for action consequences.

---

## P1. Chinese Bridge Testing Is Not Strong Enough

### Observation

Python unit tests include Chinese command behavior at engine level.

However, bridge CLI tests currently contain mojibake-looking strings in places, which weakens confidence in end-to-end Chinese bridge behavior.

Manual PowerShell pipe tests with Chinese input produced suspicious behavior, likely due to shell encoding path rather than core parser failure.

### Required Fix

Add bridge-level Chinese tests using Python subprocess with explicit UTF-8 input, avoiding shell pipe encoding ambiguity:

```python
subprocess.run(
    ["python", "-m", "metarpg.bridge", "step"],
    input=json.dumps(payload, ensure_ascii=False),
    encoding="utf-8",
)
```

Test actual readable Chinese strings:

```text
去守卫站
问玛拉关于矿场
将刚才的情形告诉玛拉
```

### Acceptance

Bridge-level tests verify:

```text
去守卫站 -> location=guard_post
问玛拉关于矿场 -> accepted local social action
将刚才的情形告诉玛拉 -> hook resolves after prior setup
```

---

## P2. README And Version Metadata Are Stale

### Symptom

README and package metadata still describe:

```text
MetaRPG Demo v0.1
```

But the implementation has v0.5/v0.5.1 concepts:

```text
claims
MetaAct
hooks
frontiers
affordance expansion
bridge protocol
UPF integration
```

### Required Fix

Update README to reflect current architecture:

```text
MetaRPG core
bridge CLI
UPF integration status
current acceptance tests
known limits
```

Update `pyproject.toml` description/version when the milestone stabilizes.

### Acceptance

A new reader can understand:

```text
how to run Python tests
how to call bridge manually
how to enable UPF MetaRPG mode
which parts are prototype vs complete
```

---

## v0.5.2 Recommended Implementation Order

1. Stop UPF fallback mutation on MetaRPG bridge failure.
2. Add MetaRPG snapshot storage/mapping inside UPF state.
3. Render MetaRPG location/NPC/hooks/frontiers/beliefs in UPF panels.
4. Persist MetaRPG session link in UPF save/load.
5. Wire `metarpg_show_debug` into engine config and bridge options.
6. Add Rust bridge timeout enforcement.
7. Expand bridge apply_report.
8. Add real Chinese bridge regression tests.
9. Install/enable Rust toolchain in the dev environment and run `cargo test`.
10. Run the Greyfen guard station -> tavern -> tell Mara loop through the UPF UI and record playtest notes.

---

## v0.5.2 Definition Of Done

v0.5.2 should be considered done when:

```text
- Python tests pass.
- Rust tests compile and pass.
- UPF MetaRPG mode success path displays MetaRPG narrative.
- UPF panels reflect MetaRPG snapshot location/NPC/debug state.
- Bridge failure does not trigger original UPF world mutation.
- UPF save/load restores MetaRPG project path + session id.
- MetaRPG debug toggle controls MetaRPG debug visibility.
- Bridge timeout prevents UI lockup.
- Chinese bridge tests use readable UTF-8 strings and pass.
- Greyfen/Mara playable loop works through UPF UI.
```

---

## Final Review Line

v0.5.1 built the bridge.

v0.5.2 should make the bridge authoritative.

The next milestone is not more imagination or more theory. It is ownership plumbing:

```text
MetaRPG owns consequences.
UPF owns presentation.
Save/load preserves the connection.
Debug proves the chain.
```
