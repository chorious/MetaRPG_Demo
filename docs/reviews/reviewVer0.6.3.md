# reviewVer0.6.3 - Flash Writer, JSON Contract, and v0.6.3 Refactor Review

## 0. Review Target

This review is based mainly on:

```text
runtime/agentic_runs/play_5600cb55
```

Observed artifacts:

```text
turn_001.json
turn_002.json
turn_003_error.json
scorecard_001.json
scorecard_002.json
events.jsonl
errors.jsonl
```

Missing artifacts:

```text
run_manifest.json
summary.md
```

The run is valuable because it shows the v0.6.3 direction is beginning to work: the system now keeps enough evidence to diagnose the failure, but it also proves the current Writer contract is still too fragile.

---

## 1. High-Level Judgment

The biggest change in this run is that Flash is no longer merely producing useless raw text.

It is doing something close to the intended Writer role:

```text
understand local player intent
write a vivid local scene
extend small social texture
propose implied local details
connect the turn with recent history
```

That is good.

The problem is not that Flash invented details.
The problem is that Flash invented details while also failing the machine contract.

The v0.6 architecture should not suppress invention entirely. It should force invention into an auditable shape.

The correct rule is:

```text
Writer may invent local plausible details.
Writer must declare them in candidate_patch / assumptions.
Writer must return complete valid JSON.
Auditors decide what can become canon.
```

---

## 2. What Happened In play_5600cb55

### 2.1 Turn 1

Player input:

```text
琢磨了一下，要了杯酒喝 "最近有啥消息啊这附近？"
```

Writer output was coherent:

```text
你走到吧台前，对玛拉说：“来一杯酒，最近有啥消息啊这附近？”
玛拉抬眼看了看你，沉默片刻。她从身后取出一只陶杯，缓缓倒满麦酒，推到你面前。
她压低声音说：“嗯……听说北边矿道那边最近不太平，夜里总有人听见奇怪的动静。镇长那边似乎在加派人手，但也没多说什么。你一个人在外头，小心点。”
```

Hard Auditor passed.
Soft Auditor found:

```text
too_mechanical
underspecified_feedback
```

This is a fair soft critique, not a hard failure.

The response is playable, but Mara still sounds like a quest giver. That is exactly the kind of issue Soft Auditor should catch.

### 2.2 Turn 2

Player input:

```text
"好的，我明白" 将酒一饮而尽。 "本地的么？味道真好。"
```

Writer output was also coherent:

```text
你端起那杯麦酒，一仰头，温热的液体顺着喉咙滑下，麦芽的醇厚与微苦在舌尖散开。你放下杯子，杯底在木桌上发出一声轻响。
玛拉看着你将酒喝完，原本谨慎的眼神里闪过一丝柔和。她轻轻点了点头，嘴角微微上扬，似乎对你的直爽举动感到些许意外。
“本地的东西，从不掺假。”玛拉的回答简短，声音不大，却带着一丝自矜。她随手抹了抹吧台，目光在你脸上停留了一瞬，似乎等你回应。
```

Hard Auditor passed.
Soft Auditor found:

```text
underspecified_feedback
too_mechanical
```

But one of these soft critiques is questionable.

Soft Auditor claimed Mara failed to answer the previous "最近有啥消息" question. That is not right for this turn. The current player input asked whether the drink was local and praised its taste. Mara's answer directly addressed that.

This means Soft Auditor is over-weighting `recent_history` and under-weighting `current_player_input`.

That is not a Writer failure.
It is a Soft Auditor prompt and context-priority failure.

### 2.3 Turn 3

Player input:

```text
"我也不喜欢掺假 —— 直白一点，多好，哈哈" 检查了一下自己的背包，准备取出一点食物来吃
```

Writer failed with invalid JSON:

```text
WriterOutputError: Expecting ',' delimiter: line 27 column 6
```

The captured raw prefix shows useful content before the syntax failure:

```text
玩家笑着回应玛拉关于酒不掺假的直白，然后检查自己的背包，从中取出一些食物来吃。
```

Then Flash invented:

```text
一块干面包
半条肉干
几枚铜币
```

And later started inventing Mara offering:

```text
腌酸黄瓜
```

This is not automatically bad.

In a tavern scene, dry bread, jerky, coins, and pickles are locally plausible. But the current story packet had:

```text
inventory_or_handheld: []
```

So these details cannot be treated as already true.

They must be either:

```text
candidate_patch: acquire_item / reveal_inventory / transient_prop
```

or downgraded to:

```text
the player searches but finds nothing definite
```

The JSON failure prevented the system from reaching Hard Auditor, so this turn became a Writer contract failure before it became a grounding judgment.

---

## 3. Why Flash Returned Invalid JSON

The most likely cause is not one single bug.

It is a pressure stack:

```text
1. Writer is asked to be vivid.
2. Writer is asked to maintain strict JSON.
3. Writer is asked to output many fields.
4. Chinese prose contains quotes, punctuation, em dashes, and nested dialogue.
5. The turn invited inventory invention.
6. Temperature is high enough for creative expansion.
7. The output schema is long enough that one missing comma ruins the whole turn.
```

The visible failure happened around:

```text
"decla...
```

That suggests the model was still inside a segment object and failed to complete a field. This is a format-completion problem, not a story-comprehension problem.

The prompt should explicitly remind Writer that output completeness matters more than adding another detail.

---

## 4. Prompt-Level Fixes

The user suggestion is correct:

```text
在 prompt 里面提醒它输出要满足格式完整，输出字数要达到说清楚
```

This should improve stability.

But it must be worded carefully. If we only say "write valid JSON", the model may still prioritize prose. The instruction should make JSON completeness a first-class success condition.

Recommended Writer prompt additions:

```text
FORMAT PRIORITY
- Your response must be one complete valid JSON object.
- The JSON must be parseable by Python json.loads without repair.
- Every object and array must be closed.
- Every property name must use double quotes.
- Every string must be closed before the next field begins.
- Do not stop in the middle of a field.
- If you are running out of space, shorten prose and close the JSON correctly.
- Prefer fewer complete segments over many incomplete segments.
- Do not include markdown fences.
- Do not include comments.
```

Recommended length instruction:

```text
LENGTH CONTROL
- Write enough prose to make the player's action clear and playable.
- Prefer 2-3 complete segments.
- Each segment should be 1-3 sentences.
- Avoid adding extra objects, extra NPC actions, or extra assumptions just to be vivid.
- Completeness and parseability are more important than flourish.
```

Recommended invention instruction:

```text
LOCAL INVENTION RULE
- You may introduce small plausible local details only if they do not become hard facts.
- If you invent a concrete object in the player's possession, declare it in candidate_patch or mark it as an assumption requiring audit.
- If inventory_or_handheld is empty, do not state that the player already owns specific items unless candidate_patch proposes reveal_inventory or acquire_item.
- Tavern ambience may include generic smell, noise, warmth, cups, benches, and unnamed patrons.
- Named items, money, weapons, notes, keys, food in the player's pack, or NPC gifts must be represented in candidate_patch.
```

Recommended output-size safety:

```text
STOP CONDITION
Before finishing, mentally verify:
1. JSON starts with { and ends with }.
2. All arrays are closed.
3. All segment objects are closed.
4. candidate_patch is an array even if empty.
5. assumptions is an array even if empty.
6. risk_notes is an array even if empty.
```

This is not magic, but it reduces the obvious class of failures.

---

## 5. Prompt Alone Is Not Enough

A prompt fix is necessary but insufficient.

The system should assume a live LLM will eventually return bad JSON again.

Therefore v0.6.3 should add a syntax-repair pass:

```text
Writer call
-> json.loads
-> if fail: JSON syntax repair call at temperature=0
-> json.loads again
-> if still fail: write turn_NNN_error.json
```

Important:

```text
The repair pass must fix JSON syntax only.
It must not rewrite story content.
It must not add new facts.
It must not improve prose.
```

Suggested repair prompt:

```text
Your previous output is invalid JSON.
Fix JSON syntax only.
Do not change story content.
Do not add or remove story facts.
Do not improve prose.
Return one valid JSON object only.
It must parse with Python json.loads.

JSON error:
<error>

Invalid output:
<raw_output>
```

This lets Flash remain creative while preventing one comma from killing the whole turn.

---

## 6. Raw Output Logging Still Needs Fixing

`turn_003_error.json` exists and is valid JSON.

That is progress.

But the field:

```text
raw_writer_output
```

is empty.

Only `error_message.raw_prefix` contains part of the failed Writer output.

This is not enough.

Root cause:

```text
runner.py initializes raw_writer_output = ""
runner.py only fills raw_writer_output after run_writer succeeds
when run_writer raises WriterOutputError, raw_text exists on the exception but runner does not read it
```

Required fix:

```python
raw_writer_output = getattr(exc, "raw_text", "")
```

Then pass that to:

```python
run_logger.write_error_turn(..., raw_output=raw_writer_output)
```

This is a P0 fix because without full raw output, JSON failure diagnosis becomes guesswork again.

---

## 7. Run Closing Still Needs Fixing

The run directory has:

```text
events.jsonl
errors.jsonl
turn_001.json
turn_002.json
turn_003_error.json
scorecard_001.json
scorecard_002.json
```

But lacks:

```text
run_manifest.json
summary.md
```

Likely cause:

```text
play_cli.py only calls logger.close() on /quit
```

If the user stops after an error or the process exits unexpectedly, the run never writes final manifest/summary.

Required fix:

```text
wrap main loop in try/finally
always call logger.close()
include attempted turns, completed turns, failed turns
record hard failure for turn_003 writer_failure
```

Without this, runtime evidence remains fragmented.

---

## 8. Soft Auditor Context Priority Problem

Turn 2 shows that Soft Auditor can critique the wrong thing.

It looked at previous history:

```text
最近有啥消息啊这附近？
```

and blamed the current turn for not answering it, even though the current player asked:

```text
本地的么？味道真好。
```

Soft Auditor needs an explicit hierarchy:

```text
1. Current player input is primary.
2. Immediate previous output is continuity context.
3. Earlier history is background only.
4. Do not require the current NPC response to answer an older question if the current input changed topic.
```

Recommended Soft Auditor prompt addition:

```text
When judging responsiveness, prioritize the current_player_input.
Use recent_history only for continuity contradictions or unresolved promises.
Do not mark a response as underspecified just because it does not continue an older topic after the player has asked a new question.
```

This matters because wrong soft critiques will send Editor repairs in the wrong direction.

---

## 9. Hard Auditor Implication From Turn 3

Turn 3 never reached Hard Auditor, but it reveals a needed rule category.

Current packet:

```text
inventory_or_handheld: []
```

Writer attempted:

```text
背包里有干面包、肉干、铜币
```

This should not necessarily be a hard failure. It depends on how the system wants to treat player inventory.

Recommended classification:

```text
Case A: Player says "I take food from my pack" and inventory is unspecified.
-> Medium issue: unverified inventory reveal.
-> Require candidate_patch kind reveal_inventory or transient_inventory_assumption.

Case B: Writer invents important item such as key, note, weapon, potion, named relic.
-> Hard or medium depending on impact.

Case C: Writer invents tiny tavern ambience not owned by player.
-> Usually allowed as ambient.

Case D: NPC gives player a concrete object.
-> Must have acquire_item or transient_event / offer effect.
```

This preserves Flash's useful imagination without letting it silently rewrite world state.

---

## 10. Recommended v0.6.3 Patch List

### P0 - Forensic Correctness

```text
1. Capture WriterOutputError.raw_text into turn_NNN_error.json.
2. Always write run_manifest.json and summary.md through try/finally.
3. Add tests proving failed Writer output preserves raw text.
4. Add tests proving failed runs still write summary and manifest.
```

### P1 - Writer JSON Stability

```text
1. Add FORMAT PRIORITY section to Writer system/user prompt.
2. Add LENGTH CONTROL section.
3. Add LOCAL INVENTION RULE section.
4. Lower repair temperature to 0 if adding repair pass.
5. Add one JSON syntax repair retry before hard failure.
```

### P2 - Auditor Alignment

```text
1. Teach Soft Auditor to prioritize current input over older history.
2. Add inventory-invention medium rule to Hard Auditor.
3. Make Editor consume soft issues and produce local rewrite tasks.
```

### P3 - Scorecard Truthfulness

```text
1. Make writer_failure produce an explicit scorecard_003.json or embedded scorecard.
2. Make failed turn reduce run acceptable=false.
3. Make state_continuity_score and packet_support_score meaningful or hide them until implemented.
```

---

## 11. Suggested Writer Prompt Patch

A compact patch can be added near the end of the Writer prompt:

```text
FORMAT PRIORITY
Return one complete valid JSON object only. It must parse with Python json.loads without repair.
Use double quotes for every property name and string. Close every string, object, and array.
If you are running out of room, shorten the prose and close the JSON correctly.
Prefer 2-3 complete segments over 4 incomplete segments.
Never stop in the middle of a property such as declared_claims, candidate_patch, assumptions, or risk_notes.

LENGTH CONTROL
Write enough to make the action clear and playable, but do not over-expand.
Each segment should be 1-3 sentences.
Do not add extra objects or NPC actions just to be vivid.
Completeness and parseability are more important than flourish.

LOCAL INVENTION RULE
Small ambient details are allowed. Concrete inventory, money, named props, gifts, notes, weapons, food in the player's pack, and new useful objects must be represented in candidate_patch or assumptions.
If inventory_or_handheld is empty, do not state that the player already owns specific items unless you explicitly mark it as a proposed inventory reveal.
```

This directly addresses the current failure without making the Writer timid.

---

## 12. Final Judgment

Flash's invention is not the enemy.

In this run, the invention is actually one of the first signs that the Writer role is becoming alive:

```text
dry bread
jerky
coins
pickles
Mara's tavern pride
small social warmth
```

These are the kinds of details a story engine needs.

But v0.6.3 must force them through a stronger contract:

```text
complete JSON
explicit candidate patch
full raw failure logging
auditor classification
local repair
truthful scorecard
```

The next milestone should not be "make Flash less imaginative".

It should be:

```text
make Flash imaginative inside a format that never disappears, never silently commits, and can always be audited.
```
