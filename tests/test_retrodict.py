"""Retrodiction proposal, validation, and rejection tests."""
from __future__ import annotations

from metarpg import retrodict
from metarpg.models import Fact, WorldState
from metarpg.scenarios.greyfen import build


def test_propose_for_known_belief():
    w = build()
    rp = retrodict.propose(w, "rusk_pressures_mara")
    assert rp is not None
    assert rp.target == "rusk_pressures_mara"
    assert len(rp.causes) >= 1


def test_propose_for_unknown_belief_is_none():
    w = build()
    assert retrodict.propose(w, "no_such_belief") is None


def test_canonize_adds_facts():
    w = build()
    rp = retrodict.propose(w, "rusk_pressures_mara")
    assert rp is not None
    added = retrodict.canonize(w, rp)
    assert added
    for f in added:
        assert f in w.facts


def test_canonize_idempotent():
    w = build()
    rp = retrodict.propose(w, "rusk_pressures_mara")
    retrodict.canonize(w, rp)
    again = retrodict.canonize(w, rp)
    assert again == []


def test_retrodiction_rejected_when_violates_locked_facts():
    """Stretch acceptance §11: retrodiction is rejected when it contradicts canon."""
    w = build()
    # Force iven dead in hard canon to make the alive retropath illegal.
    w.facts.add(Fact("dead", ("iven",)))
    rp = retrodict.propose(w, "iven_alive_in_mine")
    assert rp is not None
    vr = retrodict.validate(w, rp)
    assert not vr.ok
    assert "alive_and_dead" in vr.reason


def test_mara_entered_includes_access_path():
    """Without a passage fact in canon, the retropath provides one (so check_forbidden passes)."""
    w = build()
    rp = retrodict.propose(w, "mara_entered_mine")
    assert rp is not None
    vr = retrodict.validate(w, rp)
    assert vr.ok, vr.reason
