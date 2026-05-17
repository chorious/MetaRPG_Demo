"""Compact debug DSL parser and renderer (PLAN_SONNET §4.3, §6).

Supported line forms:
  @FACT predicate(arg,arg,...)
  @KNOW agent knows predicate(arg,...)
  @REL from->to dim=value dim=value ...
  @MOTIF name(arg,...) param=value param=value ...
  @FRONTIER verb(args) | verb(args) | ...
  @BELIEF H1 description p=.45

Patch DSL (multi-line):
  TRY verb(args)
  REQUIRES requirement_predicate
  EFFECT event(name) | observe(name) | rel_delta(a,b,dim,delta)
       | belief_delta(name,delta) | add_fact(pred:arg:arg)
       | add_knowledge(agent:pred:arg:arg) | motif_delta(name:arg:arg,param,delta)

Retropath:
  RETROPATH target_description
  CAUSE predicate(arg,...)
  CAUSE predicate(arg,...)
  EXPLAINS observation_name

For round-trip simplicity, multi-arg structured payloads inside EFFECT use ':'
as an inner separator instead of nested parens (e.g. add_fact(at:player:tavern)).
"""
from __future__ import annotations

import re

from .models import (
    AvailableAction,
    Belief,
    Effect,
    Fact,
    Knowledge,
    LocalSlice,
    Motif,
    Patch,
    Relation,
    Retropath,
    ValidationResult,
)

_PRED_RE = re.compile(r"^([a-zA-Z_][a-zA-Z0-9_]*)\s*\(\s*([^)]*)\s*\)$")
_KV_RE = re.compile(r"([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*([+-]?\d*\.?\d+)")
_REL_HDR_RE = re.compile(r"^([a-zA-Z_][a-zA-Z0-9_]*)\s*->\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*(.*)$")
_BELIEF_RE = re.compile(
    r"^([A-Z]\d+)\s+([a-zA-Z_][a-zA-Z0-9_]*)\s+p\s*=\s*([+-]?\d*\.?\d+)$"
)


# ---------- low-level parse helpers ----------

def parse_predicate(text: str) -> tuple[str, tuple[str, ...]]:
    """Parse `name(arg,arg,...)` into (name, args).

    Args are stripped, may be identifiers, numbers, or empty (no nesting in v0.1).
    """
    m = _PRED_RE.match(text.strip())
    if not m:
        raise ValueError(f"bad predicate syntax: {text!r}")
    name = m.group(1)
    raw = m.group(2).strip()
    if not raw:
        return name, ()
    args = tuple(a.strip() for a in raw.split(","))
    return name, args


def parse_fact(text: str) -> Fact:
    name, args = parse_predicate(text)
    return Fact(predicate=name, args=args)


# ---------- @LINE parsers ----------

def parse_layer_line(line: str) -> object:
    """Dispatch on the @TAG prefix. Returns Fact/Knowledge/Relation/Motif/Frontier list/Belief."""
    s = line.strip()
    if not s or s.startswith("#"):
        return None
    if s.startswith("@FACT"):
        return parse_fact(s[len("@FACT"):].strip())
    if s.startswith("@KNOW"):
        return _parse_knowledge(s[len("@KNOW"):].strip())
    if s.startswith("@REL"):
        return _parse_relation(s[len("@REL"):].strip())
    if s.startswith("@MOTIF"):
        return _parse_motif(s[len("@MOTIF"):].strip())
    if s.startswith("@FRONTIER"):
        return _parse_frontier(s[len("@FRONTIER"):].strip())
    if s.startswith("@BELIEF"):
        return _parse_belief(s[len("@BELIEF"):].strip())
    raise ValueError(f"unknown layer prefix: {s!r}")


def _parse_knowledge(text: str) -> Knowledge:
    # "agent knows predicate(args)"
    parts = text.split(None, 2)
    if len(parts) != 3 or parts[1] != "knows":
        raise ValueError(f"bad @KNOW: {text!r}")
    agent = parts[0]
    fact = parse_fact(parts[2])
    return Knowledge(agent=agent, fact=fact)


def _parse_relation(text: str) -> Relation:
    m = _REL_HDR_RE.match(text)
    if not m:
        raise ValueError(f"bad @REL header: {text!r}")
    a, b, rest = m.group(1), m.group(2), m.group(3).strip()
    dims = {k: float(v) for k, v in _KV_RE.findall(rest)}
    return Relation(from_agent=a, to_agent=b, dimensions=dims)


def _parse_motif(text: str) -> Motif:
    # "name(args) param=value param=value"
    paren_end = text.find(")")
    if paren_end < 0:
        raise ValueError(f"bad @MOTIF: {text!r}")
    head = text[: paren_end + 1]
    tail = text[paren_end + 1:].strip()
    name, args = parse_predicate(head)
    params = {k: float(v) for k, v in _KV_RE.findall(tail)}
    return Motif(name=name, args=args, params=params)


def _parse_frontier(text: str) -> list[AvailableAction]:
    out: list[AvailableAction] = []
    for piece in text.split("|"):
        piece = piece.strip()
        if not piece:
            continue
        verb, args = parse_predicate(piece)
        out.append(AvailableAction(verb=verb, args=args))
    return out


def _parse_belief(text: str) -> Belief:
    m = _BELIEF_RE.match(text)
    if not m:
        raise ValueError(f"bad @BELIEF: {text!r}")
    return Belief(id=m.group(1), description=m.group(2), prob=float(m.group(3)))


# ---------- patch parse ----------

def parse_patch(text: str) -> Patch:
    """Parse the multi-line TRY/REQUIRES/EFFECT shape into a Patch."""
    intent = ""
    requirements: list[str] = []
    effects: list[Effect] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("TRY"):
            intent = line[len("TRY"):].strip()
        elif line.startswith("REQUIRES"):
            requirements.append(line[len("REQUIRES"):].strip())
        elif line.startswith("EFFECT"):
            effects.append(_parse_effect(line[len("EFFECT"):].strip()))
    if not intent:
        raise ValueError("patch missing TRY line")
    return Patch(intent=intent, requirements=requirements, effects=effects)


def _parse_effect(body: str) -> Effect:
    name, args = parse_predicate(body)
    if name == "event":
        return Effect("event", (args[0],))
    if name == "observe":
        return Effect("observe", (args[0],))
    if name == "rel_delta":
        return Effect("rel_delta", (args[0], args[1], args[2], float(args[3])))
    if name == "belief_delta":
        return Effect("belief_delta", (args[0], float(args[1])))
    if name == "add_fact":
        # add_fact(predicate:arg:arg)
        parts = args[0].split(":")
        f = Fact(predicate=parts[0], args=tuple(parts[1:]))
        return Effect("add_fact", (f,))
    if name == "remove_fact":
        parts = args[0].split(":")
        f = Fact(predicate=parts[0], args=tuple(parts[1:]))
        return Effect("remove_fact", (f,))
    if name == "add_knowledge":
        # add_knowledge(agent:pred:arg:arg)
        parts = args[0].split(":")
        agent = parts[0]
        f = Fact(predicate=parts[1], args=tuple(parts[2:]))
        return Effect("add_knowledge", (Knowledge(agent=agent, fact=f),))
    if name == "motif_delta":
        # motif_delta(name:arg:arg, param, delta)
        head = args[0].split(":")
        m_name = head[0]
        m_args = tuple(head[1:])
        return Effect("motif_delta", (m_name, m_args, args[1], float(args[2])))
    raise ValueError(f"unknown effect kind: {name!r}")


# ---------- renderers ----------

def render_fact(f: Fact) -> str:
    return f"@FACT {f}"


def render_knowledge(k: Knowledge) -> str:
    return f"@KNOW {k.agent} knows {k.fact}"


def render_relation(r: Relation) -> str:
    dims = " ".join(f"{k}={_fmt(v)}" for k, v in r.dimensions.items())
    return f"@REL {r.from_agent}->{r.to_agent} {dims}".rstrip()


def render_motif(m: Motif) -> str:
    head = f"{m.name}({','.join(m.args)})"
    params = " ".join(f"{k}={_fmt(v)}" for k, v in m.params.items())
    return f"@MOTIF {head} {params}".rstrip()


def render_frontier(fs: list[AvailableAction]) -> str:
    body = " | ".join(str(f) for f in fs)
    return f"@FRONTIER {body}"


def render_belief(b: Belief) -> str:
    return f"@BELIEF {b.id} {b.description} p={_fmt(b.prob)}"


def render_slice(sl: LocalSlice) -> str:
    lines: list[str] = []
    for f in sl.facts:
        lines.append(render_fact(f))
    for k in sl.knowledge:
        lines.append(render_knowledge(k))
    for r in sl.relations:
        lines.append(render_relation(r))
    for m in sl.motifs:
        lines.append(render_motif(m))
    if sl.beliefs:
        for b in sl.beliefs:
            lines.append(render_belief(b))
    if sl.frontier:
        lines.append(render_frontier(sl.frontier))
    return "\n".join(lines)


def render_patch(p: Patch) -> str:
    lines = [f"TRY {p.intent}"]
    for req in p.requirements:
        lines.append(f"REQUIRES {req}")
    for eff in p.effects:
        lines.append(f"EFFECT {_render_effect(eff)}")
    return "\n".join(lines)


def _render_effect(eff: Effect) -> str:
    k = eff.kind
    p = eff.payload
    if k == "event":
        return f"event({p[0]})"
    if k == "observe":
        return f"observe({p[0]})"
    if k == "rel_delta":
        return f"rel_delta({p[0]},{p[1]},{p[2]},{_signed(p[3])})"
    if k == "belief_delta":
        return f"belief_delta({p[0]},{_signed(p[1])})"
    if k == "add_fact":
        f: Fact = p[0]
        return f"add_fact({f.predicate}:{':'.join(f.args)})"
    if k == "remove_fact":
        f = p[0]
        return f"remove_fact({f.predicate}:{':'.join(f.args)})"
    if k == "add_knowledge":
        kn: Knowledge = p[0]
        return f"add_knowledge({kn.agent}:{kn.fact.predicate}:{':'.join(kn.fact.args)})"
    if k == "motif_delta":
        return f"motif_delta({p[0]}:{':'.join(p[1])},{p[2]},{_signed(p[3])})"
    return f"{k}({p})"


def render_rejection(action_form: str, reason: str) -> str:
    return f"REJECT {action_form}\nWHY {reason}"


def render_validation(action_form: str, vr: ValidationResult) -> str:
    if vr.ok:
        return f"VALIDATION accepted: {action_form}"
    why = vr.reason or (vr.failed_requirements[0] if vr.failed_requirements else "unknown")
    return render_rejection(action_form, why)


def render_retropath(rp: Retropath) -> str:
    lines = [f"RETROPATH {rp.target}"]
    for c in rp.causes:
        lines.append(f"CAUSE {c}")
    for e in rp.explains:
        lines.append(f"EXPLAINS {e}")
    return "\n".join(lines)


# ---------- formatting ----------

def _fmt(v: float) -> str:
    """Render an unsigned probability/score: 0.18 -> '.18', 1.00 -> '1.00'."""
    s = f"{v:.2f}"
    if s.startswith("0.") and len(s) > 2:
        return s[1:]
    if s.startswith("-0.") and len(s) > 3:
        return "-" + s[2:]
    return s


def _signed(v: float) -> str:
    """Render a signed delta: +0.04 -> '+.04', -0.30 -> '-.30'."""
    s = f"{v:+.2f}"
    if s.startswith("+0.") or s.startswith("-0."):
        return s[0] + s[2:]
    return s
