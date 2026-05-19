from pathlib import Path

from metarpg.agentic.render_brief import build_render_brief
from metarpg.agentic.renderer_agent import run_renderer
from metarpg.agentic.seed_loader import load_seed
from metarpg.agentic.transaction import NarrativeFrame, RenderBrief, TurnTransaction
from metarpg.agentic.world_graph import world_from_seed

SEED_PATH = Path("metarpg/data/seeds/dnd_ashen_vault_seed.yaml")


class _MockFlashClient:
    def __init__(self, response: str) -> None:
        self.response = response

    def chat(self, messages: list[dict], temperature: float = 0.8) -> str:
        return self.response


def test_render_brief_from_world():
    seed = load_seed(SEED_PATH)
    world = world_from_seed(seed)
    frame = NarrativeFrame(
        beat="inspection",
        candidate_hints=["hint_ash_smell"],
        motifs_to_use=["m_black_ash"],
    )
    tx = TurnTransaction(
        operations=[],
        commitments=[],
    )
    brief = build_render_brief(tx, frame, world)
    assert "m_black_ash" in brief.motifs_to_render
    assert "hint_ash_smell" in brief.allowed_hints


def test_renderer_returns_text():
    brief = RenderBrief(
        committed_events=["Player inspects black ash"],
        allowed_hints=["hint_ash_smell"],
        motifs_to_render=["m_black_ash"],
    )
    client = _MockFlashClient("门槛上的黑灰在火光下泛着细密的颗粒感。")
    text = run_renderer(brief, {"scene": {"location": "entrance_hall"}}, client)
    assert isinstance(text, str)
    assert len(text) > 0


def test_renderer_uses_motifs():
    brief = RenderBrief(
        committed_events=["Player approaches lower door"],
        motifs_to_render=["m_wet_stone"],
    )
    client = _MockFlashClient("潮湿的石阶在脚下发出轻微的回响。")
    text = run_renderer(brief, {"scene": {}}, client)
    assert "潮湿" in text or "石阶" in text


def test_render_brief_includes_recent_events():
    seed = load_seed(SEED_PATH)
    world = world_from_seed(seed)
    world.events = [
        {"summary": "Event A"},
        {"summary": "Event B"},
        {"summary": "Event C"},
        {"summary": "Event D"},
    ]
    frame = NarrativeFrame(beat="aftermath")
    tx = TurnTransaction()
    brief = build_render_brief(tx, frame, world)
    # events[-3:] on 4 items returns B, C, D
    assert "Event A" not in brief.committed_events
    assert "Event B" in brief.committed_events
    assert "Event C" in brief.committed_events
    assert "Event D" in brief.committed_events
