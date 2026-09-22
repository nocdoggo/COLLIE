"""tools/run_arms.py — the demo's argument guards, its module-02 wiring, and a small smoke."""

from __future__ import annotations

import pytest

from collie.arms.protocols import RepairingSpecPrompter, SpecParser, SpecPrompter
from collie.contracts import AlertMessage, PeriodObservation, Split
from collie.data.splits import FAMILIES, build_units
from collie.spec.adapters import ShockSpecParser, ShockSpecPrompter
from tools.run_arms import _SPEC_PROPOSAL_MARKER, dev_instances, main, spec_adapters


def _pool_size() -> int:
    units = build_units(Split.DEV)
    return min(len([u for u in units if u.family == f]) for f in FAMILIES) * len(FAMILIES)


def test_episodes_above_the_dev_pool_fails_loudly(tmp_path) -> None:
    """The CP2-audit finding: an unguarded IndexError above the pool, now a named bound."""
    pool = _pool_size()
    with pytest.raises(ValueError, match=f"exceeds the dev episode pool of {pool}"):
        dev_instances(tmp_path, pool + len(FAMILIES))


def test_episodes_must_be_a_multiple_of_six(tmp_path) -> None:
    with pytest.raises(ValueError, match="positive multiple of 6"):
        dev_instances(tmp_path, 7)


def test_demo_smoke_six_episodes(capsys) -> None:
    """One cycle of six: the ladder runs, the table prints, the ledger balances."""
    rc = main(["--split", "dev", "--episodes", "6", "--table"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "arm1_capped_base_stock" in out
    assert "oracle_shockspec_headroom" in out
    assert "conserved" in out
    assert "arms 8/9/10 proposals:" in out


def test_proposal_sharing_charges_every_decision_point_to_all_three_arms(tmp_path) -> None:
    """The books' invariant on the shared call set, measured rather than asserted by comment.

    Every proposal decision point is charged to arms 8, 9, and 10 — that is what makes the
    counterfactual accounting honest — and the physical count never exceeds the charged count.
    """
    from tools.run_arms import dev_instances, proposal_sharing, run_ladder

    _, ledger = run_ladder(dev_instances(tmp_path, 6), tmp_path)
    sharing = proposal_sharing(ledger)
    assert sharing.points > 0, "no proposals fired; the measurement would prove nothing"
    assert sharing.charged == 3 * sharing.points
    assert sharing.points <= sharing.physical <= sharing.charged


# ---------------------------------------------------------------------------
# the module-02 seam: real adapters, not a demo stand-in
# ---------------------------------------------------------------------------


def _obs(period: int, *, alert: AlertMessage | None = None) -> PeriodObservation:
    return PeriodObservation(
        period=period,
        date=f"2024-01-{period:02d}",
        on_hand=40.0,
        in_transit_total=15.0,
        prev_order=90.0,
        prev_arrivals=80.0,
        profit_per_unit=5.0,
        holding_cost_per_unit=1.0,
        promised_lead_time=2,
        prev_demand=100.0,
        alert=alert,
    )


def test_the_demo_injects_module_02s_real_adapters() -> None:
    """The runner's prompter/parser are module 02's, and satisfy the arm's declared seams."""
    prompter, parser = spec_adapters()
    assert isinstance(prompter, ShockSpecPrompter)
    assert isinstance(parser, ShockSpecParser)
    assert isinstance(prompter, SpecPrompter)
    assert isinstance(prompter, RepairingSpecPrompter)
    assert isinstance(parser, SpecParser)
    # Paired, not shared: the parser validates against its own prompter's evidence set.
    assert parser.prompter is prompter


def test_each_arm_gets_its_own_adapter_pair() -> None:
    """Sharing one pair across arms would cross-contaminate the permitted evidence set."""
    first_prompter, first_parser = spec_adapters()
    second_prompter, second_parser = spec_adapters()
    assert first_prompter is not second_prompter
    assert first_parser is not second_parser


def test_the_scripted_transport_marker_still_matches_module_02s_prompt() -> None:
    """The coupling the demo cannot fake: re-word module 02's prompt header and this fails.

    Without this, a header change would route the proposal prompt to the direct-action payload
    and every ShockSpec proposal would silently become a parse fallback.
    """
    prompter, _ = spec_adapters()
    text = prompter.prompt(_obs(3))
    assert _SPEC_PROPOSAL_MARKER in text
    # A repair prompt appends to the same text, so attempt 2 routes to the same payload.
    assert _SPEC_PROPOSAL_MARKER in prompter.repair_prompt()


def test_the_real_prompt_carries_its_own_evidence_identifiers() -> None:
    """Provenance invariant: evidence ids are the prompt's, and the hash is over its bytes."""
    prompter, _ = spec_adapters()
    alert = AlertMessage(alert_id="a2", period=2, text="supplier advisory")
    prompter.observe(_obs(1))
    text = prompter.prompt(_obs(2, alert=alert))
    bundle = prompter.bundle
    assert bundle.evidence_ids == ("obs_t1", "obs_t2", "alert_2")
    assert bundle.tau_j == 2
    assert all(identifier in text for identifier in bundle.evidence_ids)
    # The arm stamps prompt_hash from the same bytes the bundle hashed.
    import hashlib

    assert bundle.prompt_hash == hashlib.sha256(text.encode()).hexdigest()
    assert prompter.repair_prompt() != text
