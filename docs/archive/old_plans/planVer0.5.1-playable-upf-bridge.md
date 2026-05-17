# MetaRPG Dev v0.5.1 Plan - UPF Playable Bridge

## 0. Correction

Earlier plans treated UPF mostly as a reference architecture.
That is not enough.

UPF should be treated as the fastest playable shell for MetaRPG.

Correct division:

```text
MetaRPG = reasonability core / local world expansion engine
UPF     = playable runtime / UI / character sheet / save-load / event display
```

The goal of v0.5.1 is not to port MetaRPG into Rust.
The goal is to let UPF run as a game while delegating player-action consequences to the MetaRPG Python core.

---

## 1. Core Thesis

MetaRPG needs a playable surface to test whether these abstractions feel real:

```text
claims
admitted events
hooks
frontiers
affordance expansion
plot diagnostics
retrodictive reasonability
```

CLI logs are useful for debugging, but they do not reveal whether the system feels like a playable RPG.

UPF already has:

```text
Rust/egui desktop shell
chat-style player input
message history
character/world panels
NPC/party/quest/inventory/state panels
structured NarrativeEvent and NarrativeApplyReport
save/load flow
LLM configuration UI
```

So UPF should become:

```text
MetaRPG playable client
```

---

## 2. Hard Boundary

There must be only one authoritative world logic source.

Rule:

```text
MetaRPG decides world consequences.
UPF displays them.
```

UPF may keep UI state, character panels, settings, and save wrappers.
But player actions should not be independently interpreted by both UPF and MetaRPG.

Avoid this:

```text
UPF LLM/apply_event mutates state
MetaRPG engine also mutates state
=> split-brain world
```

Target this:

```text
UPF receives player input
UPF calls MetaRPG bridge
MetaRPG returns narrative + apply_report + snapshot + debug surfaces
UPF renders the result
```

---

## 3. Runtime Architecture

### 3.1 Recommended v0.5.1 Bridge

Use subprocess JSON first.

```text
UPF Rust process
  -> spawn python -m metarpg.bridge step
  -> send request JSON via stdin
  -> read response JSON via stdout
  -> update UI/message panels
```

Why subprocess first:

```text
lowest integration complexity
no PyO3 build complexity
no HTTP service lifecycle yet
works with current Python prototype
safe enough for local desktop playtest
```

Later options:

```text
v0.5.2: long-running Python sidecar service over localhost HTTP
v0.6+: Rust shell + Python core service with session cache
v1.x: selective Rust port or PyO3 only if performance demands it
```

### 3.2 Bridge Flow

```text
1. Player types in UPF UI.
2. UPF EngineCommand::SubmitPlayerInput receives text.
3. UPF builds MetaRPGBridgeRequest.
4. Rust calls Python bridge.
5. Python loads/creates MetaRPG session.
6. MetaRPG runs one engine step.
7. Python returns MetaRPGBridgeResponse.
8. UPF appends player/narrator/system messages.
9. UPF displays snapshot/debug surfaces.
10. UPF save embeds MetaRPG session blob/path.
```

---

## 4. Bridge Protocol

### 4.1 Request Shape

File target:

```text
metarpg/bridge_protocol.py
```

Request JSON:

```json
{
  "protocol_version": 1,
  "command": "step",
  "session_id": "default",
  "player_text": "推门进入酒馆",
  "language": "zh-CN",
  "upf_context": {
    "player_name": "Unnamed Hero",
    "world_title": "Greyfen",
    "visible_location": "street",
    "inventory": [],
    "party": [],
    "npcs": [],
    "quests": []
  },
  "options": {
    "include_debug": true,
    "max_affordance_candidates": 8,
    "force_no_llm": false
  }
}
```

### 4.2 Response Shape

```json
{
  "protocol_version": 1,
  "ok": true,
  "session_id": "default",
  "turn": 12,
  "messages": [
    {
      "speaker": "narrator",
      "text": "你推开酒馆的门，潮湿的木香和低声交谈涌出来。"
    }
  ],
  "apply_report": {
    "applications": [
      {
        "event": {
          "kind": "travel",
          "args": ["player", "street", "tavern"]
        },
        "outcome": "applied"
      }
    ]
  },
  "snapshot": {
    "location": "tavern",
    "facts": [],
    "known_entities": [],
    "active_hooks": [],
    "frontiers": []
  },
  "debug": {
    "budget": "large",
    "touched_frontiers": ["scene_boundary:tavern"],
    "top_affordances": ["talk_to_bartender", "listen_to_room"],
    "plot_issues": []
  }
}
```

Error response:

```json
{
  "protocol_version": 1,
  "ok": false,
  "session_id": "default",
  "error": {
    "code": "bridge_failed",
    "message": "Python MetaRPG bridge crashed or returned invalid JSON"
  }
}
```

---

## 5. Python Side Work

### 5.1 `metarpg/bridge.py`

Add command-line bridge:

```text
python -m metarpg.bridge step
```

Responsibilities:

```text
read JSON from stdin
validate protocol_version
load or create session
call existing MetaRPG engine step
serialize narrative/messages
serialize ApplyReport
serialize world snapshot
serialize hooks/frontiers/affordances/plot diagnostics
write JSON to stdout
write internal errors to stderr
```

### 5.2 Session Storage

Suggested path:

```text
runtime/bridge_sessions/{session_id}.json
```

Session must include:

```text
WorldState
turn index
active hooks
frontier registry
plot graph summary
recent messages or cold archive pointer
```

### 5.3 Snapshot Export

Add or extend:

```text
metarpg/export_snapshot.py
```

Snapshot tiers:

```text
player-visible state
UPF panel state
MetaRPG debug state
save blob
```

Do not expose every internal belief/frontier in normal UI unless debug is enabled.

---

## 6. Rust / UPF Side Work

### 6.1 New Rust Module

File target:

```text
vendor/Unlimited_possibilies_framework/src/engine/metarpg_bridge.rs
```

Responsibilities:

```text
define MetaRpgBridgeRequest
define MetaRpgBridgeResponse
call python subprocess
handle timeout
parse JSON
return typed result to Engine
```

Suggested command:

```text
python -m metarpg.bridge step
```

Working directory should be:

```text
E:\GameDesign\MetaRPG_Dev
```

But make this configurable later.

### 6.2 Engine Routing

Modify:

```text
vendor/Unlimited_possibilies_framework/src/engine/engine.rs
```

Add a mode flag:

```text
use_metarpg_core: bool
```

When enabled:

```text
EngineCommand::SubmitPlayerInput
  -> call_metarpg_bridge
  -> append returned messages
  -> update snapshot panels
  -> display debug reports
```

When disabled:

```text
use original UPF behavior
```

This fallback matters because UPF should remain runnable while integration is unstable.

### 6.3 UI Toggle

Modify UI settings:

```text
Use MetaRPG Core
MetaRPG Project Path
MetaRPG Session Id
Show MetaRPG Debug
```

Default for this project can be enabled, but upstream UPF behavior should stay available.

### 6.4 Response Rendering

Map MetaRPG messages into UPF messages:

```text
speaker=narrator -> Message::Roleplay(Narrator)
speaker=npc      -> Message::Roleplay(Npc)
speaker=system   -> Message::System
speaker=debug    -> Message::System if debug enabled
```

Map apply_report into existing UPF `NarrativeApplied` response if possible.
If schemas differ, add a lightweight MetaRPG debug message first, then improve typed mapping later.

---

## 7. State Mapping

### 7.1 MetaRPG To UPF

Minimum mapping:

```text
MetaRPG player location -> UPF world/status section
MetaRPG known NPCs      -> UPF NPC panel
MetaRPG objects/items   -> UPF inventory/loot if admitted as owned/nearby
MetaRPG relations       -> UPF relationships
MetaRPG hooks           -> debug or quest-like panel
MetaRPG frontiers       -> debug panel
MetaRPG plot issues     -> debug/system messages
```

Do not force all MetaRPG facts into UPF's RPG stats.
Some facts should remain in MetaRPG-specific debug/snapshot data.

### 7.2 UPF To MetaRPG

UPF may pass visible UI context:

```text
player name
character class/background
inventory
party members
current world definition
selected tone/rules
```

But MetaRPG should treat this as input context, not authority over consequences.

---

## 8. Save / Load Strategy

UPF save should include a pointer or blob for MetaRPG state.

Recommended first version:

```text
UPF save stores:
  metarpg_session_id
  metarpg_project_path
  metarpg_state_json_blob optional
```

Python bridge also stores:

```text
runtime/bridge_sessions/{session_id}.json
```

On load:

```text
UPF restores UI state
UPF tells bridge to load session_id
MetaRPG restores authoritative reasonability state
```

Avoid save mismatch by recording:

```text
metarpg_turn
upf_message_count
last_bridge_response_hash
```

---

## 9. Debug Surfaces

UPF should expose MetaRPG internals enough to playtest the theory.

Debug panel should show:

```text
last expansion budget
touched frontiers
top affordance candidates
admitted events
rejected/deferred events
active hooks
plot diagnostics
unknown-fact warnings
teleport warnings
knowledge leak warnings
```

This is not just developer vanity.
It is how we judge whether the player experience matches the theory.

---

## 10. Minimal Playable Demo

### 10.1 Demo Scenario

Use Greyfen / guard station / tavern / Mara loop.

Required sequence:

```text
1. Player starts near guard station or street.
2. Player tries to enter/inspect guard station.
3. Guard/Rusk cold response creates communicable hook.
4. Player enters tavern.
5. Tavern entry triggers large scene-boundary expansion.
6. Player tells Mara about the earlier guard station situation.
7. System resolves "刚才的情形" through hook payload.
8. Mara learns the event only after communication.
9. No unrelated NPC or object appears from nowhere.
10. Debug panel shows hook/frontier/apply_report causality.
```

### 10.2 Experience Target

Player should feel:

```text
The world opens when I cross a meaningful boundary.
Specific people remember and react only to what they can know.
My vague references can work when there is a real recent hook.
The game allows open actions, but does not accept arbitrary hallucinated outcomes.
```

---

## 11. Implementation Phases

### Phase A - Python Bridge Skeleton

Files:

```text
metarpg/bridge_protocol.py
metarpg/bridge.py
tests/test_bridge_protocol.py
```

Tasks:

```text
- Define request/response dataclasses.
- Implement stdin/stdout JSON command.
- Return deterministic demo response from current engine/scenario.
- Add tests for valid request, invalid JSON, bridge error response.
```

### Phase B - MetaRPG Session Adapter

Files:

```text
metarpg/bridge_session.py
metarpg/export_snapshot.py
tests/test_bridge_session.py
```

Tasks:

```text
- Load/create bridge session by id.
- Persist WorldState plus hooks/frontiers/plot graph summary.
- Export player-visible and debug snapshots.
```

### Phase C - Rust Bridge Client

Files:

```text
vendor/Unlimited_possibilies_framework/src/engine/metarpg_bridge.rs
vendor/Unlimited_possibilies_framework/src/engine/mod.rs
```

Tasks:

```text
- Add typed request/response structs.
- Spawn Python bridge subprocess.
- Send JSON stdin and read stdout.
- Handle timeout and invalid response.
```

### Phase D - UPF Engine Routing

Files:

```text
vendor/Unlimited_possibilies_framework/src/engine/engine.rs
vendor/Unlimited_possibilies_framework/src/engine/protocol.rs
```

Tasks:

```text
- Add config/mode for MetaRPG core.
- Route SubmitPlayerInput through bridge when enabled.
- Convert bridge messages to UPF Message values.
- Convert bridge apply_report/snapshot to UI responses as far as possible.
```

### Phase E - UI Controls And Debug Panel

Files:

```text
vendor/Unlimited_possibilies_framework/src/ui/app.rs
vendor/Unlimited_possibilies_framework/src/ui/right_panel.rs
```

Tasks:

```text
- Add Use MetaRPG Core toggle.
- Add project path/session id fields.
- Add MetaRPG debug display.
- Keep original UPF path available.
```

### Phase F - Playtest Script

Files:

```text
scripts/run_upf_metarpg_demo.ps1
runtime/playtest_notes_v051.md
```

Tasks:

```text
- Start UPF with MetaRPG path configured.
- Run Greyfen/Mara test loop.
- Record whether hooks/frontiers/diagnostics match expectation.
```

---

## 12. Acceptance Tests

### 12.1 Bridge CLI Works

Command:

```text
python -m metarpg.bridge step
```

Given valid JSON stdin, it returns valid JSON stdout with:

```text
ok=true
messages
apply_report
snapshot
```

### 12.2 Invalid JSON Does Not Crash

Given invalid stdin:

```text
ok=false
error.code=invalid_json
```

### 12.3 UPF Can Call Bridge

From Rust test or manual run:

```text
call_metarpg_bridge(request)
```

Expected:

```text
response parsed successfully
narrator message appended
no original UPF LLM call required
```

### 12.4 Single Authority

When MetaRPG mode is enabled:

```text
UPF does not independently apply LLM-generated world events for the same player input.
```

### 12.5 Save/Load Keeps MetaRPG Session

After save/load:

```text
session_id restored
recent hook still available
"刚才的情形" can still resolve if hook remains active
```

---

## 13. Risks

### Risk: Subprocess Is Slow

Acceptable for v0.5.1.
If latency is bad, move to long-running localhost service.

### Risk: Schema Mismatch

Keep first schema deliberately small.
Do not map every MetaRPG concept to existing UPF fields immediately.
Use debug JSON for unmapped data.

### Risk: Two Engines Fight

Solve with mode routing:

```text
MetaRPG mode enabled -> MetaRPG owns player consequences
MetaRPG mode disabled -> original UPF owns consequences
```

### Risk: UI Becomes Debug-Heavy

Keep normal display narrative-first.
Put hooks/frontiers/diagnostics behind debug toggle.

---

## 14. Definition Of Done

v0.5.1 is done when:

```text
- Python bridge can run one MetaRPG step from JSON stdin/stdout.
- UPF can call the Python bridge from Rust.
- UPF can display MetaRPG narrative messages.
- UPF can show at least minimal MetaRPG snapshot/debug info.
- MetaRPG mode avoids duplicate UPF world mutation for the same input.
- Save/load preserves or restores MetaRPG session identity.
- Greyfen guard-station -> tavern -> tell Mara playtest works in UPF UI.
```

---

## 15. Conceptual Result

v0.4 gives MetaRPG legal world mutation.
v0.5 gives MetaRPG controlled affordance expansion.
v0.5.1 gives MetaRPG a playable shell.

The combined stack becomes:

```text
UPF UI
  -> player input / panels / save-load
MetaRPG bridge
  -> JSON protocol boundary
MetaRPG core
  -> claims / events / hooks / frontiers / graph diagnostics
UPF UI
  -> rendered playable experience
```

This is the first version where the theory can be judged by feel rather than only by logs.
