# MetaRPG v0.6.6.1

A retrodictive reasonability engine. The player drives a small village mystery;
hidden truths are tracked as probabilistic beliefs; high-confidence hypotheses
get canonized only after passing a forbidden-pattern check.

Current line (v0.6.6.1): agentic LLM pipeline — StoryPacket → Writer →
Translator → Scanner → Hard Auditor → Soft Auditor → Editor → Committer.
See [CHANGELOG.md](CHANGELOG.md) and `PROJECT_STATUS.md`.

Baseline v0.5.2 makes the bridge authoritative: MetaRPG owns consequences,
UPF owns presentation, save/load preserves the connection.

## Quickstart

```powershell
# from project root
pip install -r requirements.txt

# Run all Python tests
python -m pytest

# Interactive REPL (uses LLM if set.env reachable)
python -m metarpg.cli
python -m metarpg.cli --no-llm

# Scripted demo
python -m metarpg.cli --script scripts/milestone.txt --no-llm
python -m metarpg.cli --script scripts/milestone_zh.txt --no-llm

# Call bridge manually (JSON via stdin/stdout)
$json = '{"protocol_version":1,"command":"step","session_id":"manual","player_text":"环顾四周","options":{"force_no_llm":true}}'
$json | python -m metarpg.bridge step
```

If you see a `UnicodeEncodeError` on the legacy Windows console, set the env
var first: `$env:PYTHONIOENCODING='utf-8'`. The CLI also calls
`sys.stdout.reconfigure('utf-8')` defensively.

## Layout

```
metarpg/
  __init__.py       version
  models.py         dataclasses: Fact, Knowledge, Relation, Motif, Frontier,
                    Belief, Patch, Effect, Action, WorldState, LocalSlice, Retropath
  dsl.py            parse/render the compact @LAYER lines + TRY/REQUIRES/EFFECT patches
  world.py          WorldState, local-slice extraction, patch application, JSONL archive
  rules.py          validate_patch + check_forbidden (alive ∧ dead, two locations,
                    entry without access)
  beliefs.py        apply_delta with motif modulation, threshold crossings
  retrodict.py      explanation path proposal + validation + canonization
  proposer.py       hypothesis generation: affordance expansion + select_best
  scenario_hooks.py ScenarioHooks registration system (topic impacts, compilers,
                    retropath templates, dynamic frontier)
  narrator.py       optional LLM narration (Qwen local first, DeepSeek-Flash fallback)
  engine.py         the 12-step turn loop + pluggable verb compilers
  bridge.py         CLI entry point for UPF subprocess bridge (JSON stdin/stdout)
  bridge_protocol.py BridgeRequest / BridgeResponse / BridgeSnapshot types
  bridge_session.py session save/load for bridge mode (JSON per session)
  export_snapshot.py convert WorldState to player-visible + debug snapshot
  cli.py            REPL + --script mode + /matrix /canon /beliefs /archive debug cmds
  session_logger.py per-session Markdown interaction log
  scenarios/
    greyfen.py      PLAN §3 initial state + all scenario-specific hooks
    __init__.py
  tests/            pytest suite
scripts/
  milestone.txt     English 8-turn walkthrough
  milestone_zh.txt  Chinese 8-turn walkthrough
runtime/            per-session cold archive + canon log + session log (gitignored)
  bridge_sessions/  bridge mode session persistence (gitignored)
```

## Architecture: Engine is scenario-agnostic

The engine knows **verbs** and **rules**, not **content**. All scenario-specific
logic lives in `ScenarioHooks`, registered by the scenario module:

| What | Where (before) | Where (now) |
|------|---------------|-------------|
| Topic → belief impacts | Hard-coded in `engine.py` | Registered via `hooks.topic_impacts` |
| Action compilers (verbs) | Hard-coded 7-branch `compile_action` | Default compilers in engine; scenario overrides via `hooks.action_compilers` |
| Listen combos (Rusk+Mara) | Hard-coded in `engine.py` | Greyfen-specific compiler in `scenarios/greyfen.py` |
| Retropath templates | Global `retrodict._TEMPLATES` | Isolated per-engine via `hooks.retrodict_templates` |
| Frontier | Static list in `WorldState` | Dynamic generator via `hooks.frontier_generator` |

A new scenario only needs to implement `build()` (initial world) and `build_hooks()`
(registrations). The engine code never changes.

### Adding a new scenario (no engine changes)

```python
# scenarios/my_village.py
from metarpg.scenario_hooks import ScenarioHooks
from metarpg.models import ...

def build_hooks() -> ScenarioHooks:
    return ScenarioHooks(
        topic_impacts={
            ("ask", "treasure"): [("villager_knows_location", 0.12)],
        },
        action_compilers={
            "bribe": _compile_bribe,  # custom verb
        },
        retrodict_templates={
            "villager_knows_location": Retropath(...),
        },
        frontier_generator=_generate_frontier,
    )

def build() -> WorldState:
    ...
```

## Bridge protocol (UPF integration)

MetaRPG exposes a subprocess bridge consumed by the UPF engine:

```
UPF (Rust) --JSON stdin/stdout--> python -m metarpg.bridge step
```

### Request

```json
{
  "protocol_version": 1,
  "command": "step",
  "session_id": "my_save",
  "player_text": "去守卫站",
  "language": "zh-CN",
  "options": {
    "force_no_llm": true,
    "include_debug": true
  }
}
```

### Response

```json
{
  "protocol_version": 1,
  "ok": true,
  "session_id": "my_save",
  "turn": 3,
  "messages": [{"speaker": "narrator", "text": "..."}],
  "apply_report": {
    "applications": [{"event": {"kind": "add_fact", "args": [...]}, "outcome": "applied"}]
  },
  "snapshot": {
    "location": "guard_post",
    "nearby_npcs": ["rusk"],
    "facts": [...],
    "relations": [...],
    "beliefs": [...]
  },
  "debug": {
    "budget": "large",
    "touched_frontiers": [...],
    "top_affordances": [...]
  }
}
```

### Enabling UPF MetaRPG mode

In UPF, open **Settings** and enable **MetaRPG Core**. Set:
- Project path: `E:\GameDesign\MetaRPG_Dev`
- Session ID: any string (persisted in UPF saves)
- Show MetaRPG Debug: toggle for budget/affordance/frontier panels

When enabled, player input is routed through the MetaRPG bridge. MetaRPG owns
all world consequences; UPF displays the resulting snapshot.

### Save/load with MetaRPG

UPF `GameSave` stores a `MetaRpgSaveLink` containing:
- `enabled` — whether MetaRPG mode was on
- `project_path` — path to MetaRPG installation
- `session_id` — bridge session identity
- `turn` — last known turn from bridge response

Loading a save restores the MetaRPG config and reconnects to the same session,
so hooks and frontiers remain available.

## Turn output

Each turn prints, in order:

```
TOUCHED          which entities the slice was built around
LOCAL SLICE      the compressed view passed to the compiler/narrator
PATCH            TRY / REQUIRES / EFFECT lines proposed for this turn
VALIDATION       accepted or rejected with a WHY message
BELIEF DELTAS    raw, modulated, and resulting probability per belief
CANON DELTA      facts added/removed this turn
RETROPATH        (if any) proposed/canonized/rejected explanation chain
NARRATION        renderer output (LLM or template)
```

In compact mode (default), only the status panel + narration + key changes are shown.
Use `/debug` to toggle full technical output.

## DSL cheat sheet

```
@FACT predicate(arg,arg,...)
@KNOW agent knows predicate(arg,...)
@REL from->to dim=value dim=value ...
@MOTIF name(arg,...) param=value param=value ...
@FRONTIER verb(args) | verb(args) | ...
@BELIEF H1 description p=.45

TRY verb(args)
REQUIRES same_location(a,b) | at(a,p) | accessible(p) | knows(a,p,arg,arg)
EFFECT event(name) | observe(name)
       | rel_delta(a,b,dim,+.04) | belief_delta(name,+.10)
       | add_fact(pred:arg:arg) | remove_fact(pred:arg:arg)
       | add_knowledge(agent:pred:arg:arg) | motif_delta(name:arg:arg,param,+.05)

REJECT verb(args)
WHY missing_required_location(...) | not_same_location(...) | location_inaccessible(...)

RETROPATH belief_description
CAUSE predicate(arg,...)
EXPLAINS observation_name
```

## Verbs supported in v0.5.2

`ask`, `go`, `observe`, `confront`, `help`, `listen`, `sneak`, `tell`. Aliases: talk →
ask, walk → go, look → observe, accuse → confront, offer → help.

**中文输入也支持**, `engine.py` 会先做中文词转英文再进解析器:
- 动词: 问, 去/走, 看/观察, 质问, 帮/帮助, 听, 潜入, 告诉/说
- 实体: 玛拉(Mara), 拉斯克(Rusk), 艾文(Iven)
- 地点: 酒馆(tavern), 守卫站(guard_post), 老矿/矿场(old_mine), 矿口(old_mine_gate), 地窖(mara_cellar)

示例:
```
> 问玛拉关于矿场
> 去守卫站
> 质问玛拉关于老矿
> 听拉斯克和玛拉
> 将刚才的情形告诉玛拉
```

已有脚本:
- `scripts/milestone.txt` — 英文 8 回合演练
- `scripts/milestone_zh.txt` — 中文 8 回合演练

## LLM narrator

`narrator.py` reads `set.env`:

```
local_url = http://192.168.50.20:8101
local_model = qwen3.6-27b-nvfp4
base_url = https://api.deepseek.com
flash_model = deepseek-v4-flash
api_key = sk-...
```

It tries local Qwen first (OpenAI-compatible at
`<local_url>/v1/chat/completions`), then DeepSeek's flash model at
`<base_url>/v1/chat/completions`. If both fail it falls back to a deterministic
template so the engine keeps running.

**Qwen3.6 thinking mode:** 本地模型是 Qwen3.x 系列(思考模型),服务端没开 reasoning
parser。narrator 发送请求时通过 `chat_template_kwargs: {"enable_thinking":
False}` 关闭 thinking,确保答案直接出现在 `content` 字段,不会截断。

The renderer is constrained: it may dramatize the canon delta but cannot
invent new entities or events (system prompt enforces this).

`set.env` is in `.gitignore`. Do not commit it.

## §11 / v0.5.2 acceptance status

Minimum (all pass):

- ✓ CLI runs from project root
- ✓ Scenario inits with 3 NPCs + 5 locations
- ✓ Every turn prints slice / patch / validation / beliefs / canon / narration
- ✓ 7+ verbs supported (ask / go / observe / confront / help / listen / sneak / tell)
- ✓ Actions rejected by validation (e.g. asking Rusk when not at guard post)
- ✓ Belief probabilities updated by future events
- ✓ Retrodictive explanations canonize when a hypothesis crosses p=0.80
- ✓ Cold archive stores raw text, never reread in normal turn loop
- ✓ Tests cover validator, belief update, retrodiction safety
- ✓ Bridge protocol serializes/deserializes correctly
- ✓ Bridge CLI returns valid JSON for valid input; error JSON for invalid input
- ✓ Session save/load preserves world state across bridge calls
- ✓ Chinese bridge tests pass with explicit UTF-8 encoding
- ✓ Bridge failure does not fall back to UPF world mutation
- ✓ MetaRPG snapshot is mapped into UPF UI state
- ✓ UPF save/load preserves MetaRPG session identity
- ✓ Bridge timeout prevents UI lockup

Stretch (all pass):

- ✓ Local slice proves touched-entity locality
- ✓ `/matrix` `/canon` `/beliefs` debug commands
- ✓ Retrodiction is rejected when it contradicts hard canon
  (see `tests/test_retrodict.py::test_retrodiction_rejected_when_violates_locked_facts`)
- ✓ Engine is scenario-agnostic; all scenario logic lives in `ScenarioHooks`
- ✓ Frontier is dynamically generated from world state
- ✓ New scenarios can add verbs / topics / retropaths without touching engine code
- ✓ Frontier deduplication prevents infinite inflation
- ✓ Bridge apply report includes facts_removed, knowledge_added, rel_deltas,
  belief_deltas, transient_events, risk_flags

## Known limits

- Action parser is keyword-based, not NLU. Inputs like "could you possibly
  ask Mara if maybe the mine ..." won't parse. Stick to the simple verb
  forms above.
- Belief modulation is a single bounded factor `[0.5, 1.5]`. Not true Bayes.
- Retropath templates are scenario-local but hardcoded in `retrodict.py`.
  Scenarios can register more via `retrodict.register_template`.
- One retropath canonization per turn (avoids cascading).
- UPF save stores the MetaRPG session link, not the full world state. If the
  `runtime/bridge_sessions/` files are lost, loaded saves will warn and start
  fresh sessions.
