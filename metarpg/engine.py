"""The 12-step turn loop (PLAN_SONNET §5) — v0.2 meta-act edition.

New flow:
  Raw text -> MetaAct -> Propose hypotheses -> Validate claims -> Select best
  -> Assemble patch -> Validate patch -> Apply -> Belief update -> Retrodiction
  -> Render

Boundary:
  LLM/compiler may propose.
  Canon engine decides.
  Renderer may dramatize, but may not create facts.

The old parse_input/compile_action path is preserved inside the proposer as
Path A (high-confidence command match).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import assembler, beliefs, dsl, metaact, proposer, retrodict, world as world_mod
from .affordance import AffordanceCandidate
from .affordance_expand import generate_candidates
from .affordance_score import rank_affordances, score_affordance
from .claims import validate_hypothesis_support_claims
from .expansion_budget import classify_budget
from .frontier import mark_expanded, mark_expanding, touch_frontier
from .hookgen import generate_hooks
from .hookmatch import build_hook_hypothesis, match_active_hooks
from .hooks import tick_hooks
from .models import (
    Action,
    ActHypothesis,
    Effect,
    Fact,
    Knowledge,
    Patch,
    ProposedEffect,
    ValidationResult,
    WorldState,
)
from .narrator import Narrator
from .parsing import compile_action, parse_input, _DEFAULT_COMPILERS
from .rules import validate_patch
from .scenario_hooks import ScenarioHooks
from .scene_expand import expand_scene


# ---------- v0.5 affordance -> hypothesis conversion ----------

_KIND_MAP: dict[str, str] = {
    "inspect": "observe_scene_or_entity",
    "move_through": "move_to_place",
    "talk_about": "ask_about_topic",
    "use_as_tool": "use_object_as_tool",
    "force_open": "physical_manipulation",
    "hide": "ambiguous_social_act",
    "listen": "listen_to_entities",
    "buy_or_trade": "order_drink",
    "ask_for_help": "help_entity",
    "threaten": "threat_or_pressure",
    "persuade": "communicative_act",
    "report_event": "ask_about_topic",
    "follow_up_hook": "ask_about_topic",
    "materialize_object": "object_materialization",
    "observe_reaction": "observe_scene_or_entity",
}


def _candidate_to_hypothesis(c: AffordanceCandidate) -> ActHypothesis:
    """Convert an affordance candidate into an ActHypothesis for the existing pipeline."""
    risks: list[ProposedEffect] = []
    if c.risk > 0:
        risks.append(ProposedEffect("risk_flag", (f"affordance_risk_{c.kind}",), 0))
    return ActHypothesis(
        act_kind=_KIND_MAP.get(c.kind, "ambiguous_social_act"),
        confidence=c.score,
        support_claims=list(c.support_claims),
        intended_effects=list(c.proposed_effects),
        risks=risks,
        raw_text=c.action_template,
        target=c.anchor,
        id=c.id,
    )


# ---------- the 12-step loop ----------

@dataclass
class TurnRecord:
    """Everything that happened in a single turn — for CLI rendering and tests."""

    turn: int
    action_text: str
    action: Action | None = None
    touched: set[str] = field(default_factory=set)
    slice_text: str = ""
    patch_text: str = ""
    validation: ValidationResult = field(default_factory=lambda: ValidationResult(ok=False))
    canon_delta: dict[str, Any] = field(default_factory=dict)
    belief_modulation: list[tuple[str, float, float, float]] = field(default_factory=list)
    retropath_text: str = ""
    retropath_status: str = ""
    canon_added_via_retro: list[str] = field(default_factory=list)
    narration: str = ""

    # v0.2 meta-act debug fields
    metaact_summary: str = ""
    hypothesis_kind: str = ""
    hypothesis_confidence: float = 0.0
    claim_summary: list[tuple[str, str, str]] = field(default_factory=list)
    rejected_effects: list[str] = field(default_factory=list)

    # v0.5 frontier/affordance debug fields
    touched_frontiers: list[str] = field(default_factory=list)
    budget_class: str = ""
    affordance_candidates: list[str] = field(default_factory=list)
    top_affordance: str = ""


class Engine:
    def __init__(
        self,
        state: WorldState,
        narrator: Narrator | None = None,
        hooks: ScenarioHooks | None = None,
    ) -> None:
        self.world = state
        self.narrator = narrator or Narrator(enabled=False)
        self.hooks = hooks
        self._compilers: dict[str, Any] = dict(_DEFAULT_COMPILERS)
        if hooks and hooks.action_compilers:
            self._compilers.update(hooks.action_compilers)

    def _compile_action(self, action: Action) -> Patch:
        compiler = self._compilers.get(action.verb)
        if compiler:
            return compiler(action, self.world, self.hooks)
        return Patch(
            intent=f"unknown({action.text})",
            requirements=["unrecognized_verb"],
            effects=[],
        )

    def step(self, text: str) -> TurnRecord:
        self.world.turn += 1
        rec = TurnRecord(turn=self.world.turn, action_text=text)

        # Dynamic frontier update
        if self.hooks and self.hooks.frontier_generator:
            self.world.frontier = self.hooks.frontier_generator(self.world)

        world_mod.archive_event(self.world, "player_input", text, None)

        # ===== v0.2 meta-act pipeline =====

        # Step 1: Build MetaAct
        meta = metaact.build_metaact(text, self.world)
        rec.metaact_summary = f"地点={meta.player_location} 附近={meta.local_entities} 线索={meta.surface_cues[:5]}"

        # === v0.5: frontier detection & affordance expansion ===
        touched_frontiers = touch_frontier(self.world, meta)
        rec.touched_frontiers = [f.id for f in touched_frontiers]
        for f in touched_frontiers:
            mark_expanding(self.world, f.id)

        budget = classify_budget(text, touched_frontiers)
        rec.budget_class = budget.class_.value

        aff_candidates: list[AffordanceCandidate] = []

        # Scene expansion for large-budget movements
        if budget.class_.value in ("large", "emergency"):
            aff_candidates.extend(expand_scene(self.world, meta.player_location, budget))

        # Frontier-based candidates
        if touched_frontiers:
            aff_candidates.extend(generate_candidates(self.world, touched_frontiers))

        # Score and deduplicate
        for c in aff_candidates:
            score_affordance(c, self.world, meta)
        seen: set[str] = set()
        unique_cands: list[AffordanceCandidate] = []
        for c in aff_candidates:
            key = f"{c.kind}:{c.anchor}"
            if key not in seen:
                seen.add(key)
                unique_cands.append(c)

        ranked = rank_affordances(unique_cands, budget.max_affordances)
        for c in ranked:
            if c.source_frontier and c.source_frontier.startswith("F_"):
                mark_expanded(self.world, c.source_frontier)

        rec.affordance_candidates = [f"{c.kind}:{c.anchor}(score={c.score:.2f})" for c in ranked]
        if ranked:
            rec.top_affordance = f"{ranked[0].kind}:{ranked[0].anchor}"

        # Convert top affordances to hypotheses and inject into pool
        affordance_hyps = [_candidate_to_hypothesis(c) for c in ranked[:budget.max_affordances]]

        # === v0.3.1: try hook match before generic proposer ===
        matched_hook, hook_score = match_active_hooks(meta, self.world)
        if matched_hook and hook_score >= 0.45:
            hook_hyp = build_hook_hypothesis(matched_hook, meta, self.world)
            hypotheses = [hook_hyp] + affordance_hyps
        else:
            # Step 2: Propose hypotheses
            hypotheses = proposer.propose(meta, self.world, self.hooks) + affordance_hyps

        # Step 3: Validate claims for each hypothesis (including subacts)
        for hyp in hypotheses:
            hyp.support_claims = validate_hypothesis_support_claims(self.world, hyp.support_claims)
            for subact in hyp.subacts:
                subact.claims = validate_hypothesis_support_claims(self.world, subact.claims)

        # Step 4: Select best hypothesis
        best = proposer.select_best(hypotheses)

        if best:
            rec.hypothesis_kind = best.act_kind
            rec.hypothesis_confidence = best.confidence
            all_claims = list(best.support_claims)
            for subact in best.subacts:
                all_claims.extend(subact.claims)
            rec.claim_summary = [
                (c.name, c.status.value, c.reason) for c in all_claims
            ]

            # Reject very low-confidence hypotheses (ambiguous fallbacks)
            if best.confidence < 0.5:
                rec.validation = ValidationResult(ok=False, reason="unparseable_input")
                rec.patch_text = "(no patch)"
                rec.narration = self.narrator.narrate(text, rec.validation, {}, "")
                world_mod.archive_event(self.world, "narration", rec.narration, None)
                return rec

            # Early rejection: if any core claim is REJECTED, reject the whole action.
            # v0.3 exception: open acts allow partial success via assembler filtering.
            _CORE_CLAIM_NAMES = {
                "same_location", "can_speak_to", "role_supports", "place_supports",
                "accessible", "destination_exists", "connected_or_traversable",
            }
            _V3_OPEN_ACT_KINDS = {
                "composite_physical_social_act", "composite_act",
                "physical_manipulation", "threat_or_pressure",
                "object_materialization", "communicative_act",
                "deception_or_probe", "use_object_as_tool",
            }
            skip_early_rejection = (
                best.act_kind in _V3_OPEN_ACT_KINDS
                or best.subacts  # composite acts handle rejection per-subact
            )
            if not skip_early_rejection:
                core_rejected = [
                    c for c in best.support_claims
                    if c.status.value == "rejected" and c.name in _CORE_CLAIM_NAMES
                ]
                if core_rejected:
                    c = core_rejected[0]
                    reason = f"not_same_location({','.join(c.args)})" if c.name == "same_location" else c.reason
                    rec.validation = ValidationResult(ok=False, reason=reason)
                    rec.patch_text = f"REJECT {best.act_kind}\nWHY {reason}"
                    rec.narration = self.narrator.narrate(text, rec.validation, {}, "")
                    world_mod.archive_event(self.world, "narration", rec.narration, None)
                    return rec

            # Set touched entities from hypothesis target
            rec.touched = {"player"}
            if best.target and best.target != "scene":
                for t in best.target.split(","):
                    if t.strip():
                        rec.touched.add(t.strip())
            if best.topic:
                rec.touched.add(best.topic)

            # Step 5: Assemble patch from validated hypothesis
            patch = assembler.assemble_patch(best, self.world)
        else:
            # Should not happen — fallback always produces something
            patch = Patch(intent=f"unknown({text})")

        # ===== fallback to v0.1 Path A if meta-act produced nothing useful =====
        if not patch.effects and not patch.requirements:
            action = parse_input(text)
            if action:
                patch = self._compile_action(action)
                rec.action = action
                touched = world_mod.touched_from_action(action, self.world)
                rec.touched = touched
            else:
                rec.validation = ValidationResult(ok=False, reason="unparseable_input")
                rec.patch_text = "(no patch)"
                rec.narration = self.narrator.narrate(text, rec.validation, {}, "")
                world_mod.archive_event(self.world, "narration", rec.narration, None)
                return rec

        rec.patch_text = dsl.render_patch(patch)

        # Step 6: Validate patch (existing rules)
        vr = validate_patch(self.world, patch)
        rec.validation = vr
        if not vr.ok:
            rec.patch_text = dsl.render_rejection(patch.intent, vr.reason)
            rec.narration = self.narrator.narrate(text, vr, {}, rec.slice_text)
            world_mod.archive_event(self.world, "narration", rec.narration, rec.touched)
            return rec

        # Build local slice for touched entities (for debug/narrator)
        if rec.touched:
            sl = world_mod.extract_local_slice(self.world, rec.touched)
            rec.slice_text = dsl.render_slice(sl)

        # Step 7+8: Apply patch (canon mutations + belief deltas)
        previous = beliefs.snapshot_probs(self.world)
        non_belief_effects: list[Effect] = []
        belief_effects: list[Effect] = []
        for eff in patch.effects:
            if eff.kind == "belief_delta":
                belief_effects.append(eff)
            else:
                non_belief_effects.append(eff)

        nb_patch = Patch(intent=patch.intent, effects=non_belief_effects)
        rec.canon_delta = world_mod.apply_patch(self.world, nb_patch)

        # v0.2.1: transient_events are for narration only, not hard canon
        transient_events = rec.canon_delta.pop("transient_events", [])
        rec.canon_delta.setdefault("transient_events", transient_events)

        for f in rec.canon_delta.get("facts_added", []):
            world_mod.record_canon(self.world, f"+ {f}")
        for f in rec.canon_delta.get("facts_removed", []):
            world_mod.record_canon(self.world, f"- {f}")

        rec.canon_delta.setdefault("belief_deltas", [])
        for eff in belief_effects:
            target, raw = eff.payload[0], float(eff.payload[1])
            result = beliefs.apply_delta(self.world, target, raw)
            if result is None:
                continue
            b, applied, factor = result
            rec.belief_modulation.append((b.description, raw, applied, b.prob))
            rec.canon_delta["belief_deltas"].append(
                (b.id, b.description, applied, b.prob)
            )

        # Step 9-11: retrodiction
        crossings = beliefs.threshold_crossings(self.world, previous)
        retro_templates = (
            self.hooks.retrodict_templates if self.hooks and self.hooks.retrodict_templates else None
        )
        for b in crossings:
            rp = retrodict.propose(self.world, b.description, templates=retro_templates)
            if rp is None:
                continue
            rec.retropath_text = dsl.render_retropath(rp)
            vrr = retrodict.validate(self.world, rp)
            if vrr.ok:
                added = retrodict.canonize(self.world, rp)
                rec.retropath_status = "canonized"
                rec.canon_added_via_retro = [str(f) for f in added]
                rec.canon_delta.setdefault("facts_added", []).extend(added)
            else:
                rec.retropath_status = "rejected"
                rec.canon_delta.setdefault("retrodiction_rejected", []).append(
                    (b.description, vrr.reason)
                )
            break

        # Step 12: narration
        rec.narration = self.narrator.narrate(text, vr, rec.canon_delta, rec.slice_text)
        world_mod.archive_event(self.world, "narration", rec.narration, rec.touched)

        # === v0.3.1: generate hooks from this turn, then tick ===
        generate_hooks(self.world, rec)
        tick_hooks(self.world)

        return rec
