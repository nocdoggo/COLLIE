"""Invented, in-memory tests for the non-network OSS safety prototype."""

from __future__ import annotations

import builtins
import hashlib
import socket
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError, replace

import pytest

from analysis.coling.followup import oss_safeguards as ss


def original() -> ss.SyntheticDecoding:
    return ss.SyntheticDecoding(ss.DecodingKind.ORIGINAL_DEFAULT)


def spec(decoding: ss.SyntheticDecoding | None = None) -> ss.SyntheticSpec:
    decoding = decoding or original()
    # An invented lower observation, not an asserted maximum, for the follow-up.
    observed_overrun = 2 if decoding.kind is ss.DecodingKind.CAPPED_FOLLOWUP else 0
    max_output = (decoding.max_output_tokens or 1) + observed_overrun
    charge_ceiling = 3 + max_output * 5 + 2
    bound = ss.SyntheticPhysicalBound(
        1, max_output, 3, 5, 2, charge_ceiling, "SYNTH-BOUND-A"
    )
    return ss.SyntheticSpec(decoding, bound, known_min_overrun_tokens=observed_overrun)


def assurances(value: ss.SyntheticSpec, **changes) -> ss.SyntheticAssurances:
    approved = ss.SyntheticAssurances(
        quiescent=True,
        billing_reconciled=True,
        pricing_verified=True,
        provider_verified=True,
        token_enforcement_verified=True,
        reasoning_in_bound=True,
        failure_charges_in_bound=True,
        overruns_in_bound=True,
        physical_bound_verified=True,
        independent_bound_verified=True,
        registered_spec_hash=value.fingerprint,
        independent_review_hash=value.fingerprint,
    )
    return replace(approved, **changes)


def run(
    suffix: str = "A",
    *,
    model: ss.SyntheticModel = ss.SyntheticModel.OSS,
    spent: int = 0,
    cap: int | None = ss.nanos("1"),
    completed_cap: int | None = None,
) -> ss.SyntheticRun:
    return ss.SyntheticRun(
        f"SYNTH-RUN-{suffix}",
        model,
        spent,
        cap,
        complete=cap is None,
        completed_cap_nanos=completed_cap,
    )


def simulation(
    *,
    runs: tuple[ss.SyntheticRun, ...] | None = None,
    liabilities: tuple[ss.SyntheticLiability, ...] = (),
    value: ss.SyntheticSpec | None = None,
    evidence: ss.SyntheticAssurances | None = None,
) -> ss.SyntheticSimulation:
    value = value or spec()
    return ss.SyntheticSimulation(
        spec=value,
        assurances=evidence or assurances(value),
        runs=runs if runs is not None else (run(),),
        liabilities=liabilities,
    )


def receipt(
    subject: str,
    suffix: str,
    charge: int,
    final: bool = True,
    *,
    input_tokens: int | None = None,
    completion_tokens: int | None = None,
) -> ss.SyntheticReceipt:
    return ss.SyntheticReceipt(
        subject,
        f"SYNTH-RECEIPT-{suffix}",
        charge,
        final,
        reported_input_tokens=input_tokens,
        reported_completion_tokens=completion_tokens,
    )


def cap_resolution(
    suffix: str = "A",
    *,
    evidence: str = "A",
    spent: int = 20,
    previous_cap: int = 10,
    replacement_cap: int = 30,
    final: bool = True,
    reductions: tuple[tuple[str, int], ...] = (),
) -> ss.SyntheticRunCapResolution:
    return ss.SyntheticRunCapResolution(
        run_id=f"SYNTH-RUN-{suffix}",
        evidence_id=f"SYNTH-RESOLUTION-{evidence}",
        confirmed_spent_nanos=spent,
        confirmed_original_cap_nanos=previous_cap,
        replacement_cap_nanos=replacement_cap,
        final=final,
        cap_reductions=reductions,
    )


def reserve(sim: ss.SyntheticSimulation, run_id: str = "SYNTH-RUN-A") -> ss.SyntheticTicket:
    operation = sim.begin(run_id)
    return sim.reserve_next(operation.operation_id)


def output(
    suffix: str,
    *,
    decoding: ss.SyntheticDecoding | None = None,
    source: str = "A",
    reading: ss.SyntheticReading = ss.SyntheticReading.ALPHA,
) -> ss.SyntheticOutput:
    return ss.SyntheticOutput(
        f"SYNTH-ITEM-{suffix}", decoding or original(), f"SYNTH-SOURCE-{source}", reading
    )


@pytest.mark.parametrize(
    ("text", "expected"),
    [("0", 0), ("6", 6_000_000_000), ("0.000000001", 1), ("4.135791", 4_135_791_000)],
)
def test_amounts_and_caps_are_exact_integer_nanodollars(text: str, expected: int) -> None:
    assert ss.nanos(text) == expected
    assert ss.MODEL_CAP_NANOS == ss.nanos("6")
    assert ss.STUDY_CAP_NANOS == ss.nanos("200")


@pytest.mark.parametrize("value", [0.1, True, "-1", "1e-9", "0.0000000001", "NaN", ".5", "01"])
def test_amounts_never_round_or_accept_float_or_noncanonical_input(value) -> None:
    with pytest.raises(ValueError):
        ss.nanos(value)


def test_physical_bound_includes_input_output_and_extra() -> None:
    bound = ss.SyntheticPhysicalBound(3, 5, 2, 7, 11, 60, "SYNTH-BOUND-A")
    assert bound.token_price_crosscheck_nanos == 3 * 2 + 5 * 7 + 11
    assert bound.worst_case_nanos == 60  # the separate ceiling, not the smaller cross-check
    with pytest.raises(ValueError, match="separately supplied"):
        ss.SyntheticPhysicalBound(1, 1, 1, 1)
    with pytest.raises(ValueError, match="must be positive"):
        ss.SyntheticPhysicalBound(0, 0, 0, 0, 0, 0, "SYNTH-BOUND-A")
    with pytest.raises(ValueError):
        ss.SyntheticPhysicalBound(1, True, 2, 3)


@pytest.mark.parametrize(
    "missing",
    [
        "quiescent",
        "billing_reconciled",
        "pricing_verified",
        "provider_verified",
        "token_enforcement_verified",
        "reasoning_in_bound",
        "failure_charges_in_bound",
        "overruns_in_bound",
        "physical_bound_verified",
        "independent_bound_verified",
    ],
)
def test_each_missing_assurance_blocks_before_any_reservation(missing: str) -> None:
    value = spec()
    sim = simulation(value=value, evidence=assurances(value, **{missing: False}))
    before = sim.snapshot()
    with pytest.raises(ss.SafetyRefusal, match=missing):
        sim.begin("SYNTH-RUN-A")
    assert sim.snapshot() == before
    assert sim.snapshot().physical_attempts == 0


@pytest.mark.parametrize("missing", ["registered_spec_hash", "independent_review_hash"])
def test_registration_and_independent_review_must_match_the_exact_synthetic_spec(
    missing: str,
) -> None:
    value = spec()
    sim = simulation(value=value, evidence=assurances(value, **{missing: "0" * 64}))
    with pytest.raises(ss.SafetyRefusal, match="hash|review"):
        sim.begin("SYNTH-RUN-A")
    assert sim.snapshot().physical_attempts == 0


def test_changing_the_bound_or_decoding_invalidates_the_synthetic_registration() -> None:
    first = spec()
    changed_bound = replace(
        first,
        physical_bound=replace(
            first.physical_bound, extra_nanos=3, independent_charge_ceiling_nanos=11
        ),
    )
    capped = spec(ss.SyntheticDecoding(ss.DecodingKind.CAPPED_FOLLOWUP, 256))
    assert len({first.fingerprint, changed_bound.fingerprint, capped.fingerprint}) == 3
    for value in (changed_bound, capped):
        sim = simulation(value=value, evidence=assurances(first))
        with pytest.raises(ss.SafetyRefusal, match="registration"):
            sim.begin("SYNTH-RUN-A")


def test_assurance_drift_after_reservation_blocks_even_the_mock_transport() -> None:
    value = spec()
    sim = simulation(value=value)
    ticket = reserve(sim)
    transport = ss.SyntheticTransport((ss.SyntheticReply(ss.ReplyKind.ANSWER, 1),))
    sim.set_assurances(assurances(value, provider_verified=False))
    with pytest.raises(ss.SafetyRefusal, match="provider_verified"):
        sim.dispatch(ticket.ticket_id, transport)
    assert transport.consumed == 0
    assert sim.snapshot().attempt_reservations_nanos == ticket.bound_nanos
    sim.set_assurances(assurances(value))
    assert sim.dispatch(ticket.ticket_id, transport).state is ss.OperationState.COMPLETE


def test_open_and_closed_holds_include_spend_without_double_counting() -> None:
    sim = simulation(
        runs=(
            run("A", spent=ss.nanos("1"), cap=ss.nanos("4")),
            run("B", spent=ss.nanos("0.5"), cap=None),
            run("C", model=ss.SyntheticModel.OTHER, spent=ss.nanos("2"), cap=ss.nanos("10")),
        )
    )
    before = sim.snapshot()
    assert before.model_spent_nanos == ss.nanos("1.5")
    assert before.model_held_nanos == ss.nanos("4.5")
    assert before.study_spent_nanos == ss.nanos("3.5")
    assert before.study_held_nanos == ss.nanos("14.5")
    ticket = reserve(sim)
    after = sim.snapshot()
    assert after.model_held_nanos == before.model_held_nanos
    assert after.study_held_nanos == before.study_held_nanos
    assert after.attempt_reservations_nanos == ticket.bound_nanos


def test_exact_model_cap_is_allowed_but_one_nano_over_is_refused() -> None:
    exact = simulation(runs=(run(cap=ss.MODEL_CAP_NANOS),))
    assert exact.snapshot().model_held_nanos == ss.MODEL_CAP_NANOS
    assert reserve(exact).bound_nanos == 10
    over = simulation(runs=(run(cap=ss.MODEL_CAP_NANOS + 1),))
    with pytest.raises(ss.SafetyRefusal, match="model cap"):
        over.begin("SYNTH-RUN-A")
    assert over.snapshot().physical_attempts == 0


def test_exact_study_cap_is_allowed_but_one_nano_over_is_refused() -> None:
    other = run("B", model=ss.SyntheticModel.OTHER, cap=ss.nanos("199.9"))
    exact = simulation(runs=(run(cap=ss.nanos("0.1")), other))
    assert exact.snapshot().study_held_nanos == ss.STUDY_CAP_NANOS
    assert reserve(exact).bound_nanos == 10
    over = simulation(runs=(run(cap=ss.nanos("0.1") + 1), other))
    with pytest.raises(ss.SafetyRefusal, match="study cap"):
        over.begin("SYNTH-RUN-A")


def test_attempt_can_consume_exactly_the_run_cap_but_not_one_nano_more() -> None:
    sim = simulation(runs=(run(spent=ss.MODEL_CAP_NANOS - 10, cap=ss.MODEL_CAP_NANOS),))
    ticket = reserve(sim)
    assert sim.dispatch(
        ticket.ticket_id, ss.SyntheticTransport((ss.SyntheticReply(ss.ReplyKind.ANSWER, 10),))
    ).state is ss.OperationState.COMPLETE
    assert sim.snapshot().model_spent_nanos == ss.MODEL_CAP_NANOS
    operation = sim.begin("SYNTH-RUN-A")
    before = sim.snapshot()
    with pytest.raises(ss.SafetyRefusal, match="reserve"):
        sim.reserve_next(operation.operation_id)
    assert sim.snapshot() == before


def test_preexisting_run_overspend_is_counted_and_refused() -> None:
    sim = simulation(runs=(run(spent=20, cap=10),))
    before = sim.snapshot()
    assert before.model_held_nanos == 20
    assert before.prior_run_cap_breaches == (
        ss.SyntheticRunCapBreach("SYNTH-RUN-A", ss.SyntheticModel.OSS, 20, 10),
    )
    with pytest.raises(FrozenInstanceError):
        before.prior_run_cap_breaches[0].spent_nanos = 10
    with pytest.raises(ss.SafetyRefusal, match="breach.*separate resolution"):
        sim.begin("SYNTH-RUN-A")
    with pytest.raises(ss.SafetyRefusal, match="breach.*separate resolution"):
        sim.reallocate_caps((("SYNTH-RUN-A", 20),))
    assert sim.snapshot() == before
    assert sim.run("SYNTH-RUN-A").cap_nanos == 10


def test_prior_cap_breach_needs_separate_final_matching_evidence() -> None:
    sim = simulation(runs=(run(spent=20, cap=10),))
    before = sim.snapshot()
    for bad in (
        cap_resolution(final=False),
        cap_resolution(spent=19),
        cap_resolution(previous_cap=9),
        cap_resolution(replacement_cap=19),
        cap_resolution("B"),
    ):
        with pytest.raises(ss.SafetyRefusal):
            sim.resolve_prior_run_cap_breach(bad)
        assert sim.snapshot() == before
    resolution = cap_resolution()
    sim.resolve_prior_run_cap_breach(resolution)
    after = sim.snapshot()
    assert after.prior_run_cap_breaches == before.prior_run_cap_breaches
    assert after.run_cap_resolutions == (resolution,)
    assert sim.run("SYNTH-RUN-A").spent_nanos == 20
    assert sim.run("SYNTH-RUN-A").cap_nanos == 30
    with pytest.raises(ss.SafetyRefusal, match="no unresolved"):
        sim.resolve_prior_run_cap_breach(cap_resolution(evidence="B"))
    assert sim.snapshot() == after
    assert reserve(sim).bound_nanos == 10
    with pytest.raises(FrozenInstanceError):
        after.run_cap_resolutions[0].replacement_cap_nanos = 10


def test_resolving_one_prior_breach_does_not_hide_another_or_reuse_evidence() -> None:
    sim = simulation(runs=(run("A", spent=20, cap=10), run("B", spent=20, cap=10)))
    prior = sim.snapshot().prior_run_cap_breaches
    sim.resolve_prior_run_cap_breach(cap_resolution("A", evidence="A"))
    with pytest.raises(ss.SafetyRefusal, match="breach.*separate resolution"):
        sim.begin("SYNTH-RUN-A")
    with pytest.raises(ss.SafetyRefusal, match="already used"):
        sim.resolve_prior_run_cap_breach(cap_resolution("B", evidence="A"))
    sim.resolve_prior_run_cap_breach(cap_resolution("B", evidence="B"))
    assert sim.snapshot().prior_run_cap_breaches == prior
    assert len(sim.snapshot().run_cap_resolutions) == 2
    assert sim.begin("SYNTH-RUN-A").state is ss.OperationState.READY


def test_later_reallocation_does_not_erase_a_resolved_historical_breach() -> None:
    sim = simulation(runs=(run(spent=20, cap=10),))
    before = sim.snapshot().prior_run_cap_breaches
    resolution = cap_resolution()
    sim.resolve_prior_run_cap_breach(resolution)
    sim.reallocate_caps((("SYNTH-RUN-A", 20),))
    assert sim.run("SYNTH-RUN-A").cap_nanos == 20
    assert sim.snapshot().prior_run_cap_breaches == before
    assert sim.snapshot().run_cap_resolutions == (resolution,)


def test_prior_breach_and_idle_model_cap_reduction_commit_atomically() -> None:
    sim = simulation(
        runs=(
            run("A", spent=ss.nanos("3"), cap=ss.nanos("2")),
            run("B", cap=ss.nanos("4")),
        )
    )
    before = sim.snapshot()
    assert before.model_spent_nanos == ss.nanos("3")
    assert before.model_held_nanos == ss.nanos("7")
    with pytest.raises(ss.SafetyRefusal, match="shared cap"):
        sim.resolve_prior_run_cap_breach(
            cap_resolution(
                spent=ss.nanos("3"),
                previous_cap=ss.nanos("2"),
                replacement_cap=ss.nanos("3"),
            )
        )
    assert sim.snapshot() == before
    resolution = cap_resolution(
        spent=ss.nanos("3"),
        previous_cap=ss.nanos("2"),
        replacement_cap=ss.nanos("3"),
        reductions=(("SYNTH-RUN-B", ss.nanos("3")),),
    )
    sim.resolve_prior_run_cap_breach(resolution)
    after = sim.snapshot()
    assert after.model_held_nanos == ss.MODEL_CAP_NANOS
    assert after.prior_run_cap_breaches == before.prior_run_cap_breaches
    assert after.budget_breaches == before.budget_breaches
    assert any(
        breach.scope is ss.BudgetScope.MODEL and breach.kind is ss.BudgetBreachKind.FINITE_HELD
        for breach in after.budget_breaches
    )
    assert after.run_cap_resolutions == (resolution,)
    assert after.run_cap_resolution_transactions == (
        ss.SyntheticResolutionTransaction(
            resolution.evidence_id,
            (
                ss.SyntheticCapChange("SYNTH-RUN-A", ss.nanos("2"), ss.nanos("3")),
                ss.SyntheticCapChange("SYNTH-RUN-B", ss.nanos("4"), ss.nanos("3")),
            ),
        ),
    )
    assert sim.run("SYNTH-RUN-A").cap_nanos == ss.nanos("3")
    assert sim.run("SYNTH-RUN-B").cap_nanos == ss.nanos("3")


def test_prior_breach_can_atomically_reduce_an_idle_other_model_cap_for_the_study() -> None:
    sim = simulation(
        runs=(
            run("A", spent=ss.nanos("2"), cap=ss.nanos("1")),
            run("B", model=ss.SyntheticModel.OTHER, cap=ss.nanos("199")),
        )
    )
    assert sim.snapshot().study_held_nanos == ss.nanos("201")
    resolution = cap_resolution(
        spent=ss.nanos("2"),
        previous_cap=ss.nanos("1"),
        replacement_cap=ss.nanos("2"),
        reductions=(("SYNTH-RUN-B", ss.nanos("198")),),
    )
    sim.resolve_prior_run_cap_breach(resolution)
    assert sim.snapshot().study_held_nanos == ss.STUDY_CAP_NANOS
    assert sim.snapshot().model_held_nanos == ss.nanos("2")
    assert sim.run("SYNTH-RUN-B").cap_nanos == ss.nanos("198")
    assert sim.snapshot().prior_run_cap_breaches[0].original_cap_nanos == ss.nanos("1")


def test_atomic_cap_resolution_recovers_finite_held_fault_after_liability_reconciliation() -> None:
    liability = ss.SyntheticLiability("SYNTH-LIABILITY-A", ss.SyntheticModel.OSS, None)
    sim = simulation(
        runs=(
            run("A", spent=ss.nanos("3"), cap=ss.nanos("2")),
            run("B", cap=ss.nanos("4")),
        ),
        liabilities=(liability,),
    )
    assert sim.snapshot().model_held_nanos is None
    sim.reconcile_liability(receipt(liability.liability_id, "A", 0))
    overheld = sim.snapshot()
    assert overheld.model_held_nanos == ss.nanos("7")
    assert any("model finite_held" in fault for fault in overheld.faults)
    resolution = cap_resolution(
        spent=ss.nanos("3"),
        previous_cap=ss.nanos("2"),
        replacement_cap=ss.nanos("3"),
        reductions=(("SYNTH-RUN-B", ss.nanos("3")),),
    )
    sim.resolve_prior_run_cap_breach(resolution)
    after = sim.snapshot()
    assert after.model_held_nanos == ss.MODEL_CAP_NANOS
    assert after.faults == ()
    assert after.budget_breaches == overheld.budget_breaches
    assert after.prior_run_cap_breaches == overheld.prior_run_cap_breaches
    assert after.run_cap_resolutions == (resolution,)
    assert sim.begin("SYNTH-RUN-A").state is ss.OperationState.READY


def test_cap_reallocation_can_clear_only_a_reconciled_finite_held_fault() -> None:
    liability = ss.SyntheticLiability("SYNTH-LIABILITY-A", ss.SyntheticModel.OSS, None)
    sim = simulation(runs=(run(cap=ss.MODEL_CAP_NANOS),), liabilities=(liability,))
    sim.reconcile_liability(receipt(liability.liability_id, "A", 1))
    overheld = sim.snapshot()
    assert any("finite_held" in fault for fault in overheld.faults)
    sim.reallocate_caps((("SYNTH-RUN-A", ss.MODEL_CAP_NANOS - 1),))
    after = sim.snapshot()
    assert after.model_held_nanos == ss.MODEL_CAP_NANOS
    assert after.faults == ()
    assert after.budget_breaches == overheld.budget_breaches


def test_confirmed_spend_breach_cannot_be_fixed_by_cap_redistribution() -> None:
    sim = simulation(
        runs=(
            run("A", spent=ss.MODEL_CAP_NANOS + 1, cap=ss.nanos("2")),
            run("B", cap=ss.nanos("1")),
        )
    )
    before = sim.snapshot()
    resolution = cap_resolution(
        spent=ss.MODEL_CAP_NANOS + 1,
        previous_cap=ss.nanos("2"),
        replacement_cap=ss.MODEL_CAP_NANOS + 1,
        reductions=(("SYNTH-RUN-B", 1),),
    )
    with pytest.raises(ss.SafetyRefusal, match="fault"):
        sim.resolve_prior_run_cap_breach(resolution)
    assert sim.snapshot() == before
    assert any(
        breach.kind is ss.BudgetBreachKind.CONFIRMED_SPEND
        and breach.scope is ss.BudgetScope.MODEL
        for breach in before.budget_breaches
    )


@pytest.mark.parametrize(
    "reductions",
    [
        (("SYNTH-RUN-A", 20),),
        (("SYNTH-RUN-Z", 1),),
        (("SYNTH-RUN-C", 1),),
        (("SYNTH-RUN-B", 51),),
        (("SYNTH-RUN-B", 4),),
        (("SYNTH-RUN-B", 10), ("SYNTH-RUN-B", 9)),
    ],
)
def test_invalid_atomic_cap_reductions_leave_everything_unchanged(
    reductions: tuple[tuple[str, int], ...],
) -> None:
    sim = simulation(
        runs=(run("A", spent=20, cap=10), run("B", spent=5, cap=50), run("C", cap=None))
    )
    before = sim.snapshot()
    before_runs = tuple(sim.run(f"SYNTH-RUN-{name}") for name in ("A", "B", "C"))
    with pytest.raises(ss.SafetyRefusal):
        sim.resolve_prior_run_cap_breach(cap_resolution(reductions=reductions))
    assert sim.snapshot() == before
    assert tuple(sim.run(f"SYNTH-RUN-{name}") for name in ("A", "B", "C")) == before_runs


def test_concurrent_prior_breach_resolutions_commit_at_most_one_transaction() -> None:
    sim = simulation(runs=(run("A", spent=20, cap=10), run("B", cap=50)))
    barrier = threading.Barrier(2)

    def resolve(evidence: str) -> bool:
        barrier.wait()
        try:
            sim.resolve_prior_run_cap_breach(
                cap_resolution(evidence=evidence, reductions=(("SYNTH-RUN-B", 40),))
            )
            return True
        except ss.SafetyRefusal:
            return False

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sum(executor.map(resolve, ("A", "B"))) == 1
    state = sim.snapshot()
    assert len(state.run_cap_resolutions) == 1
    assert len(state.run_cap_resolution_transactions) == 1
    assert len(state.prior_run_cap_breaches) == 1
    assert state.model_held_nanos == 70


@pytest.mark.parametrize("limit", ["model", "study"])
def test_prior_cap_resolution_still_respects_shared_caps(limit: str) -> None:
    other = ()
    replacement = ss.MODEL_CAP_NANOS + 1
    if limit == "study":
        other = (run("B", model=ss.SyntheticModel.OTHER, cap=ss.STUDY_CAP_NANOS - 20),)
        replacement = 21
    sim = simulation(runs=(run(spent=20, cap=10), *other))
    before = sim.snapshot()
    with pytest.raises(ss.SafetyRefusal, match="shared cap"):
        sim.resolve_prior_run_cap_breach(cap_resolution(replacement_cap=replacement))
    assert sim.snapshot() == before


def test_prior_cap_resolution_waits_for_unknown_liabilities() -> None:
    liability = ss.SyntheticLiability(
        "SYNTH-LIABILITY-A", ss.SyntheticModel.OSS, 5,
        independent_max_evidence_id="SYNTH-INDEPENDENT-A",
    )
    sim = simulation(runs=(run(spent=20, cap=10),), liabilities=(liability,))
    with pytest.raises(ss.SafetyRefusal, match="liabilities or attempts"):
        sim.resolve_prior_run_cap_breach(cap_resolution())
    sim.reconcile_liability(receipt(liability.liability_id, "A", 0))
    sim.resolve_prior_run_cap_breach(cap_resolution())
    assert len(sim.snapshot().prior_run_cap_breaches) == 1
    assert len(sim.snapshot().run_cap_resolutions) == 1


def test_prior_cap_resolution_cannot_bypass_missing_billing_or_review_assurance() -> None:
    value = spec()
    sim = simulation(value=value, runs=(run(spent=20, cap=10),))
    before = sim.snapshot()
    for changed in (
        assurances(value, billing_reconciled=False),
        assurances(value, independent_review_hash=None),
    ):
        sim.set_assurances(changed)
        with pytest.raises(ss.SafetyRefusal):
            sim.resolve_prior_run_cap_breach(cap_resolution())
        assert sim.snapshot() == before
    sim.set_assurances(assurances(value))
    with pytest.raises(ss.SafetyRefusal, match="breach.*separate resolution"):
        sim.begin("SYNTH-RUN-A")
    assert sim.snapshot().prior_run_cap_breaches == before.prior_run_cap_breaches


def test_other_model_cap_breach_stays_blocked_in_this_narrow_mock() -> None:
    sim = simulation(
        runs=(run("A"), run("B", model=ss.SyntheticModel.OTHER, spent=20, cap=10))
    )
    with pytest.raises(ss.SafetyRefusal, match="only open synthetic OSS"):
        sim.resolve_prior_run_cap_breach(cap_resolution("B"))
    with pytest.raises(ss.SafetyRefusal, match="breach.*separate resolution"):
        sim.begin("SYNTH-RUN-A")


def test_reallocation_is_atomic_and_never_changes_the_model_cap() -> None:
    sim = simulation(
        runs=(
            run("A", spent=ss.nanos("1"), cap=ss.nanos("4")),
            run("B", spent=ss.nanos("1"), cap=ss.nanos("2")),
        )
    )
    before = sim.snapshot()
    with pytest.raises(ss.SafetyRefusal, match="shared cap"):
        sim.reallocate_caps((("SYNTH-RUN-A", ss.nanos("1")), ("SYNTH-RUN-B", ss.nanos("5") + 1)))
    assert sim.snapshot() == before
    assert sim.run("SYNTH-RUN-A").cap_nanos == ss.nanos("4")
    sim.reallocate_caps((("SYNTH-RUN-A", ss.nanos("1")), ("SYNTH-RUN-B", ss.nanos("5"))))
    assert sim.run("SYNTH-RUN-A").cap_nanos == ss.nanos("1")
    assert sim.run("SYNTH-RUN-B").cap_nanos == ss.nanos("5")
    assert sim.snapshot().model_held_nanos == ss.MODEL_CAP_NANOS


def test_reallocation_refuses_below_spend_closed_runs_other_models_and_duplicates() -> None:
    sim = simulation(
        runs=(
            run("A", spent=5, cap=20),
            run("B", cap=None),
            run("C", model=ss.SyntheticModel.OTHER, cap=20),
        )
    )
    before = sim.snapshot()
    for changes in (
        (("SYNTH-RUN-A", 4),),
        (("SYNTH-RUN-A", 0),),
        (("SYNTH-RUN-B", 10),),
        (("SYNTH-RUN-C", 10),),
    ):
        with pytest.raises(ss.SafetyRefusal):
            sim.reallocate_caps(changes)
    with pytest.raises(ValueError, match="duplicate"):
        sim.reallocate_caps((("SYNTH-RUN-A", 10), ("SYNTH-RUN-A", 11)))
    assert sim.snapshot() == before


def test_a_synthetic_run_cannot_be_closed_without_explicit_completeness() -> None:
    with pytest.raises(ValueError, match="only when explicitly complete"):
        ss.SyntheticRun("SYNTH-RUN-A", ss.SyntheticModel.OSS, 5, None)
    with pytest.raises(ValueError, match="only when explicitly complete"):
        ss.SyntheticRun("SYNTH-RUN-A", ss.SyntheticModel.OSS, 5, 10, complete=True)
    closed = ss.SyntheticRun("SYNTH-RUN-A", ss.SyntheticModel.OSS, 5, None, complete=True)
    assert closed.held_nanos == 5


def test_completed_run_cap_history_is_recorded_or_explicitly_unknown() -> None:
    unknown = run("A", spent=4, cap=None)
    known = run("B", model=ss.SyntheticModel.OTHER, spent=5, cap=None, completed_cap=8)
    sim = simulation(runs=(unknown, known))
    assert sim.snapshot().completed_run_cap_history == (
        ss.SyntheticCompletedRunCapHistory("SYNTH-RUN-A", ss.SyntheticModel.OSS, 4, None),
        ss.SyntheticCompletedRunCapHistory("SYNTH-RUN-B", ss.SyntheticModel.OTHER, 5, 8),
    )
    assert sim.snapshot().prior_run_cap_breaches == ()
    with pytest.raises(ValueError, match="only a completed"):
        run("C", cap=10, completed_cap=10)
    with pytest.raises(ValueError, match="positive historical cap"):
        run("D", cap=None, completed_cap=0)


def test_known_breach_in_completed_run_is_visible_and_cannot_be_reopened() -> None:
    sim = simulation(runs=(run("A"), run("B", spent=20, cap=None, completed_cap=10)))
    state = sim.snapshot()
    assert state.completed_run_cap_history == (
        ss.SyntheticCompletedRunCapHistory("SYNTH-RUN-B", ss.SyntheticModel.OSS, 20, 10),
    )
    assert state.prior_run_cap_breaches == (
        ss.SyntheticRunCapBreach("SYNTH-RUN-B", ss.SyntheticModel.OSS, 20, 10),
    )
    with pytest.raises(ss.SafetyRefusal, match="breach.*separate resolution"):
        sim.begin("SYNTH-RUN-A")
    with pytest.raises(ss.SafetyRefusal, match="only open synthetic OSS"):
        sim.resolve_prior_run_cap_breach(cap_resolution("B"))
    assert sim.snapshot() == state


def test_reallocation_is_blocked_while_a_physical_attempt_is_reserved() -> None:
    sim = simulation()
    ticket = reserve(sim)
    with pytest.raises(ss.SafetyRefusal, match="reserved"):
        sim.reallocate_caps((("SYNTH-RUN-A", 20),))
    assert sim.snapshot().attempt_reservations_nanos == ticket.bound_nanos


def test_known_external_unknown_is_held_and_requires_a_final_matching_receipt() -> None:
    liability = ss.SyntheticLiability(
        "SYNTH-LIABILITY-A", ss.SyntheticModel.OSS, ss.nanos("0.5"),
        independent_max_evidence_id="SYNTH-INDEPENDENT-A",
    )
    sim = simulation(runs=(run(spent=ss.nanos("1"), cap=ss.nanos("5")),), liabilities=(liability,))
    before = sim.snapshot()
    assert before.model_held_nanos == ss.nanos("5.5")
    with pytest.raises(ss.SafetyRefusal, match="unknown"):
        sim.begin("SYNTH-RUN-A")
    with pytest.raises(ss.SafetyRefusal, match="non-final"):
        sim.reconcile_liability(receipt(liability.liability_id, "A", 0, final=False))
    assert sim.snapshot() == before
    sim.reconcile_liability(receipt(liability.liability_id, "B", ss.nanos("0.2")))
    after = sim.snapshot()
    assert after.unknown_count == 0
    assert after.model_spent_nanos == ss.nanos("1.2")
    assert after.model_held_nanos == ss.nanos("5.2")
    assert sim.begin("SYNTH-RUN-A").state is ss.OperationState.READY


@pytest.mark.parametrize("model", [ss.SyntheticModel.OSS, ss.SyntheticModel.OTHER])
def test_unbounded_prior_liability_blocks_until_a_final_receipt(model: ss.SyntheticModel) -> None:
    liability = ss.SyntheticLiability("SYNTH-LIABILITY-A", model, None)
    sim = simulation(liabilities=(liability,))
    before = sim.snapshot()
    assert before.study_held_nanos is None
    assert (before.model_held_nanos is None) == (model is ss.SyntheticModel.OSS)
    with pytest.raises(ss.SafetyRefusal, match="unknown"):
        reserve(sim)
    sim.reconcile_liability(receipt(liability.liability_id, "A", 0))
    assert sim.snapshot().unknown_count == 0
    assert reserve(sim).bound_nanos == 10


def test_receipt_cannot_be_reused_for_another_liability() -> None:
    liabilities = (
        ss.SyntheticLiability(
            "SYNTH-LIABILITY-A", ss.SyntheticModel.OSS, 10,
            independent_max_evidence_id="SYNTH-INDEPENDENT-A",
        ),
        ss.SyntheticLiability(
            "SYNTH-LIABILITY-B", ss.SyntheticModel.OSS, 10,
            independent_max_evidence_id="SYNTH-INDEPENDENT-B",
        ),
    )
    sim = simulation(liabilities=liabilities)
    sim.reconcile_liability(receipt("SYNTH-LIABILITY-A", "A", 5))
    before = sim.snapshot()
    with pytest.raises(ss.SafetyRefusal, match="already used"):
        sim.reconcile_liability(receipt("SYNTH-LIABILITY-B", "A", 5))
    assert sim.snapshot() == before
    with pytest.raises(ss.SafetyRefusal, match="unknown"):
        sim.begin("SYNTH-RUN-A")
    sim.reconcile_liability(receipt("SYNTH-LIABILITY-B", "B", 5))
    assert sim.snapshot().unknown_count == 0


def test_each_unknown_attempt_must_be_reconciled_before_new_dispatch() -> None:
    sim = simulation(runs=(run(cap=100),))
    first, second = reserve(sim), reserve(sim)
    sim.interrupt(first.ticket_id)
    sim.interrupt(second.ticket_id)
    assert sim.snapshot().unknown_count == 2
    sim.reconcile_attempt(receipt(first.ticket_id, "A", 1))
    assert sim.snapshot().unknown_count == 1
    with pytest.raises(ss.SafetyRefusal, match="unknown"):
        sim.begin("SYNTH-RUN-A")
    sim.reconcile_attempt(receipt(second.ticket_id, "B", 2))
    assert sim.snapshot().unknown_count == 0
    assert sim.snapshot().model_spent_nanos == 3
    assert sim.operation(first.operation_id).state is ss.OperationState.FAILED
    assert sim.operation(second.operation_id).state is ss.OperationState.FAILED


def test_discovered_charge_above_prior_liability_bound_is_recorded_and_faults() -> None:
    liability = ss.SyntheticLiability(
        "SYNTH-LIABILITY-A", ss.SyntheticModel.OSS, 10,
        independent_max_evidence_id="SYNTH-INDEPENDENT-A",
    )
    sim = simulation(liabilities=(liability,))
    sim.reconcile_liability(receipt(liability.liability_id, "A", 11))
    state = sim.snapshot()
    assert state.model_spent_nanos == 11
    assert state.unknown_count == 0
    assert state.faults
    with pytest.raises(ss.SafetyRefusal, match="faulted"):
        sim.begin("SYNTH-RUN-A")


def test_prior_liability_revealed_over_model_cap_is_recorded_not_discarded() -> None:
    liability = ss.SyntheticLiability("SYNTH-LIABILITY-A", ss.SyntheticModel.OSS, None)
    sim = simulation(runs=(run(cap=ss.MODEL_CAP_NANOS),), liabilities=(liability,))
    sim.reconcile_liability(receipt(liability.liability_id, "A", 1))
    assert sim.snapshot().model_spent_nanos == 1
    assert sim.snapshot().model_held_nanos == ss.MODEL_CAP_NANOS + 1
    assert sim.snapshot().faults
    with pytest.raises(ss.SafetyRefusal, match="faulted"):
        sim.begin("SYNTH-RUN-A")


def test_initial_confirmed_model_spend_breach_is_recorded_with_indeterminate_hold() -> None:
    liability = ss.SyntheticLiability("SYNTH-LIABILITY-A", ss.SyntheticModel.OSS, None)
    sim = simulation(
        runs=(run(spent=ss.MODEL_CAP_NANOS + 1, cap=ss.MODEL_CAP_NANOS + 1),),
        liabilities=(liability,),
    )
    state = sim.snapshot()
    assert state.model_spent_nanos == ss.MODEL_CAP_NANOS + 1
    assert state.model_held_nanos is None and state.study_held_nanos is None
    assert ss.SyntheticBudgetBreach(
        ss.BudgetScope.MODEL,
        ss.BudgetBreachKind.CONFIRMED_SPEND,
        ss.MODEL_CAP_NANOS + 1,
        ss.MODEL_CAP_NANOS,
        "SYNTH-INITIAL",
    ) in state.budget_breaches
    assert not any(
        breach.scope is ss.BudgetScope.MODEL and breach.kind is ss.BudgetBreachKind.FINITE_HELD
        for breach in state.budget_breaches
    )
    with pytest.raises(ss.SafetyRefusal, match="faulted"):
        sim.begin("SYNTH-RUN-A")


def test_initial_confirmed_study_spend_breach_is_recorded_with_indeterminate_hold() -> None:
    liability = ss.SyntheticLiability("SYNTH-LIABILITY-A", ss.SyntheticModel.OTHER, None)
    sim = simulation(
        runs=(
            run("A"),
            run("B", model=ss.SyntheticModel.OTHER, spent=ss.STUDY_CAP_NANOS + 1, cap=None),
        ),
        liabilities=(liability,),
    )
    state = sim.snapshot()
    assert state.study_spent_nanos == ss.STUDY_CAP_NANOS + 1
    assert state.study_held_nanos is None
    assert ss.SyntheticBudgetBreach(
        ss.BudgetScope.STUDY,
        ss.BudgetBreachKind.CONFIRMED_SPEND,
        ss.STUDY_CAP_NANOS + 1,
        ss.STUDY_CAP_NANOS,
        "SYNTH-INITIAL",
    ) in state.budget_breaches
    with pytest.raises(ss.SafetyRefusal, match="faulted"):
        sim.begin("SYNTH-RUN-A")


@pytest.mark.parametrize("scope", [ss.BudgetScope.MODEL, ss.BudgetScope.STUDY])
def test_confirmed_spend_breach_is_recorded_while_another_liability_is_unbounded(
    scope: ss.BudgetScope,
) -> None:
    model = ss.SyntheticModel.OSS if scope is ss.BudgetScope.MODEL else ss.SyntheticModel.OTHER
    liabilities = (
        ss.SyntheticLiability("SYNTH-LIABILITY-A", model, None),
        ss.SyntheticLiability("SYNTH-LIABILITY-B", model, None),
    )
    runs = (run(cap=10),)
    charge = ss.MODEL_CAP_NANOS + 1
    if scope is ss.BudgetScope.STUDY:
        runs = (*runs, run("B", model=model, spent=ss.STUDY_CAP_NANOS, cap=None))
        charge = 1
    sim = simulation(runs=runs, liabilities=liabilities)
    sim.reconcile_liability(receipt("SYNTH-LIABILITY-A", "A", charge))
    state = sim.snapshot()
    cap = ss.MODEL_CAP_NANOS if scope is ss.BudgetScope.MODEL else ss.STUDY_CAP_NANOS
    assert state.study_held_nanos is None
    if scope is ss.BudgetScope.MODEL:
        assert state.model_held_nanos is None
    assert ss.SyntheticBudgetBreach(
        scope, ss.BudgetBreachKind.CONFIRMED_SPEND, cap + 1, cap, "SYNTH-RECEIPT-A"
    ) in state.budget_breaches
    assert not any(
        breach.scope is scope and breach.kind is ss.BudgetBreachKind.FINITE_HELD
        for breach in state.budget_breaches
    )
    assert any(f"{scope.value} confirmed_spend" in fault for fault in state.faults)
    sim.reconcile_liability(receipt("SYNTH-LIABILITY-B", "B", 0))
    after = sim.snapshot()
    assert any(
        breach.scope is scope and breach.kind is ss.BudgetBreachKind.CONFIRMED_SPEND
        for breach in after.budget_breaches
    )
    assert any(
        breach.scope is scope and breach.kind is ss.BudgetBreachKind.FINITE_HELD
        for breach in after.budget_breaches
    )


def test_finite_held_breach_is_not_misreported_as_confirmed_spend() -> None:
    held_only = simulation(runs=(run(cap=ss.MODEL_CAP_NANOS + 1),)).snapshot()
    model_kinds = {
        breach.kind for breach in held_only.budget_breaches if breach.scope is ss.BudgetScope.MODEL
    }
    assert model_kinds == {ss.BudgetBreachKind.FINITE_HELD}
    spent_and_held = simulation(
        runs=(run(spent=ss.MODEL_CAP_NANOS + 1, cap=ss.MODEL_CAP_NANOS + 1),)
    ).snapshot()
    model_kinds = {
        breach.kind
        for breach in spent_and_held.budget_breaches
        if breach.scope is ss.BudgetScope.MODEL
    }
    assert model_kinds == {
        ss.BudgetBreachKind.CONFIRMED_SPEND,
        ss.BudgetBreachKind.FINITE_HELD,
    }


def test_unknown_attempt_blocks_other_reserved_dispatch_until_reconciled() -> None:
    sim = simulation(runs=(run(cap=100),))
    first = reserve(sim)
    second = reserve(sim)
    timed_out = ss.SyntheticTransport((ss.SyntheticReply(ss.ReplyKind.TRANSIENT, None),))
    answer = ss.SyntheticTransport((ss.SyntheticReply(ss.ReplyKind.ANSWER, 1),))
    assert sim.dispatch(first.ticket_id, timed_out).state is ss.OperationState.WAITING_FOR_BILL
    assert sim.snapshot().unknown_count == 1
    with pytest.raises(ss.SafetyRefusal, match="unknown"):
        sim.dispatch(second.ticket_id, answer)
    assert answer.consumed == 0
    with pytest.raises(ss.SafetyRefusal, match="unknown"):
        sim.reallocate_caps((("SYNTH-RUN-A", 100),))
    sim.reconcile_attempt(receipt(first.ticket_id, "A", 4))
    assert sim.operation(first.operation_id).state is ss.OperationState.READY
    assert sim.operation(first.operation_id).outer_attempt == 2
    assert sim.dispatch(second.ticket_id, answer).state is ss.OperationState.COMPLETE
    assert sim.snapshot().model_spent_nanos == 5


def test_unknown_attempt_needs_matching_final_evidence_and_cannot_be_reconciled_twice() -> None:
    sim = simulation()
    ticket = reserve(sim)
    sim.dispatch(
        ticket.ticket_id, ss.SyntheticTransport((ss.SyntheticReply(ss.ReplyKind.ANSWER, None),))
    )
    before = sim.snapshot()
    with pytest.raises(ss.SafetyRefusal, match="non-final"):
        sim.reconcile_attempt(receipt(ticket.ticket_id, "A", 1, final=False))
    with pytest.raises(ss.SafetyRefusal, match="unknown synthetic ticket"):
        sim.reconcile_attempt(receipt("SYNTH-TICKET-999", "B", 1))
    assert sim.snapshot() == before
    sim.reconcile_attempt(receipt(ticket.ticket_id, "C", 1))
    assert sim.operation(ticket.operation_id).state is ss.OperationState.COMPLETE
    with pytest.raises(ss.SafetyRefusal, match="unknown charge"):
        sim.reconcile_attempt(receipt(ticket.ticket_id, "D", 1))


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        (ss.ReplyKind.ANSWER, ss.OperationState.COMPLETE),
        (ss.ReplyKind.EMPTY_ECHO, ss.OperationState.READY),
        (ss.ReplyKind.TRANSIENT, ss.OperationState.READY),
        (ss.ReplyKind.REFUSAL, ss.OperationState.FAILED),
        (ss.ReplyKind.FATAL, ss.OperationState.FAILED),
        (ss.ReplyKind.INTERRUPTED, ss.OperationState.FAILED),
    ],
)
def test_each_ambiguous_reply_waits_for_final_billing(
    kind: ss.ReplyKind, expected: ss.OperationState
) -> None:
    sim = simulation()
    ticket = reserve(sim)
    result = sim.dispatch(ticket.ticket_id, ss.SyntheticTransport((ss.SyntheticReply(kind, None),)))
    assert result.state is ss.OperationState.WAITING_FOR_BILL
    assert sim.snapshot().attempt_reservations_nanos == 10
    sim.reconcile_attempt(receipt(ticket.ticket_id, "A", 3))
    assert sim.operation(ticket.operation_id).state is expected
    assert sim.snapshot().model_spent_nanos == 3


def test_interruption_keeps_the_bound_and_never_silently_retries() -> None:
    sim = simulation()
    ticket = reserve(sim)
    sim.interrupt(ticket.ticket_id)
    assert sim.snapshot().attempt_reservations_nanos == 10
    assert sim.snapshot().unknown_count == 1
    with pytest.raises(ss.SafetyRefusal, match="unknown"):
        sim.reserve_next(ticket.operation_id)
    sim.reconcile_attempt(receipt(ticket.ticket_id, "A", 0))
    assert sim.snapshot().attempt_reservations_nanos == 0
    assert sim.operation(ticket.operation_id).state is ss.OperationState.FAILED
    with pytest.raises(ss.SafetyRefusal, match="not ready"):
        sim.reserve_next(ticket.operation_id)


def test_exhausted_mock_script_conservatively_creates_an_unknown_charge() -> None:
    sim = simulation()
    ticket = reserve(sim)
    with pytest.raises(ss.SafetyRefusal, match="charge is unknown"):
        sim.dispatch(ticket.ticket_id, ss.SyntheticTransport(()))
    assert sim.snapshot().unknown_count == 1
    sim.reconcile_attempt(receipt(ticket.ticket_id, "A", 0))
    assert sim.operation(ticket.operation_id).state is ss.OperationState.FAILED


@pytest.mark.parametrize("kind", [ss.ReplyKind.REFUSAL, ss.ReplyKind.FATAL])
def test_known_terminal_failure_is_counted_and_not_retried(kind: ss.ReplyKind) -> None:
    sim = simulation()
    ticket = reserve(sim)
    result = sim.dispatch(ticket.ticket_id, ss.SyntheticTransport((ss.SyntheticReply(kind, 2),)))
    assert result.state is ss.OperationState.FAILED
    assert sim.snapshot().physical_attempts == 1
    assert sim.snapshot().model_spent_nanos == 2
    with pytest.raises(ss.SafetyRefusal, match="not ready"):
        sim.reserve_next(result.operation_id)


def test_four_empty_echoes_end_the_operation_without_an_outer_retry() -> None:
    sim = simulation()
    operation = sim.begin("SYNTH-RUN-A")
    transport = ss.SyntheticTransport((ss.SyntheticReply(ss.ReplyKind.EMPTY_ECHO, 1),) * 4)
    for echo in range(1, 5):
        ticket = sim.reserve_next(operation.operation_id)
        assert (ticket.outer_attempt, ticket.echo_attempt) == (1, echo)
        operation = sim.dispatch(ticket.ticket_id, transport)
    assert operation.state is ss.OperationState.FAILED
    assert operation.physical_attempts == 4
    assert sim.snapshot().model_spent_nanos == 4


def test_eight_transients_end_the_operation_without_a_ninth_attempt() -> None:
    sim = simulation()
    operation = sim.begin("SYNTH-RUN-A")
    transport = ss.SyntheticTransport((ss.SyntheticReply(ss.ReplyKind.TRANSIENT, 1),) * 8)
    for outer in range(1, 9):
        ticket = sim.reserve_next(operation.operation_id)
        assert (ticket.outer_attempt, ticket.echo_attempt) == (outer, 1)
        operation = sim.dispatch(ticket.ticket_id, transport)
    assert operation.state is ss.OperationState.FAILED
    assert operation.physical_attempts == 8
    with pytest.raises(ss.SafetyRefusal):
        sim.reserve_next(operation.operation_id)


def test_each_retry_must_fit_the_remaining_run_budget() -> None:
    sim = simulation(runs=(run(cap=11),))
    operation = sim.begin("SYNTH-RUN-A")
    transport = ss.SyntheticTransport((ss.SyntheticReply(ss.ReplyKind.TRANSIENT, 1),) * 3)
    for _ in range(2):
        ticket = sim.reserve_next(operation.operation_id)
        operation = sim.dispatch(ticket.ticket_id, transport)
    before = sim.snapshot()
    with pytest.raises(ss.SafetyRefusal, match="reserve"):
        sim.reserve_next(operation.operation_id)
    assert sim.snapshot() == before
    assert before.model_spent_nanos == 2
    assert before.physical_attempts == 2
    assert transport.consumed == 2


def test_all_32_nested_attempts_are_individually_reserved_counted_and_charged() -> None:
    sim = simulation(runs=(run(cap=320),))
    operation = sim.begin("SYNTH-RUN-A")
    empty = ss.SyntheticReply(ss.ReplyKind.EMPTY_ECHO, 1)
    transient = ss.SyntheticReply(ss.ReplyKind.TRANSIENT, 1)
    answer = ss.SyntheticReply(ss.ReplyKind.ANSWER, 1)
    transport = ss.SyntheticTransport(
        (empty, empty, empty, transient) * 7 + (empty, empty, empty, answer)
    )
    for index in range(ss.MAX_PHYSICAL_ATTEMPTS):
        ticket = sim.reserve_next(operation.operation_id)
        assert (ticket.outer_attempt, ticket.echo_attempt) == (index // 4 + 1, index % 4 + 1)
        assert ticket.bound_nanos == 10
        assert sim.snapshot().attempt_reservations_nanos == 10
        operation = sim.dispatch(ticket.ticket_id, transport)
        assert sim.snapshot().physical_attempts == index + 1
    assert transport.consumed == 32
    assert operation.state is ss.OperationState.COMPLETE
    assert operation.physical_attempts == 32
    assert sim.snapshot().model_spent_nanos == 32
    assert sim.snapshot().attempt_reservations_nanos == 0
    with pytest.raises(ss.SafetyRefusal):
        sim.reserve_next(operation.operation_id)


def test_charge_above_the_verified_bound_is_recorded_and_faults_closed() -> None:
    sim = simulation(runs=(run(cap=10),))
    ticket = reserve(sim)
    operation = sim.dispatch(
        ticket.ticket_id, ss.SyntheticTransport((ss.SyntheticReply(ss.ReplyKind.ANSWER, 11),))
    )
    state = sim.snapshot()
    assert operation.state is ss.OperationState.FAILED
    assert state.model_spent_nanos == 11
    assert state.model_held_nanos == 11
    assert state.faults
    with pytest.raises(ss.SafetyRefusal, match="faulted"):
        sim.begin("SYNTH-RUN-A")


def test_later_run_cap_breach_retains_its_ticket_and_original_cap() -> None:
    sim = simulation(runs=(run(cap=10),))
    ticket = reserve(sim)
    sim.dispatch(
        ticket.ticket_id, ss.SyntheticTransport((ss.SyntheticReply(ss.ReplyKind.ANSWER, 11),))
    )
    state = sim.snapshot()
    assert state.prior_run_cap_breaches == ()
    assert state.later_run_cap_breaches == (
        ss.SyntheticRunCapBreach("SYNTH-RUN-A", ss.SyntheticModel.OSS, 11, 10, ticket.ticket_id),
    )
    with pytest.raises(FrozenInstanceError):
        state.later_run_cap_breaches[0].original_cap_nanos = 11
    with pytest.raises(ss.SafetyRefusal, match="faults"):
        sim.reallocate_caps((("SYNTH-RUN-A", 11),))
    assert sim.snapshot().later_run_cap_breaches == state.later_run_cap_breaches


def test_later_run_cap_breach_discovered_by_final_receipt_remains_auditable() -> None:
    sim = simulation(runs=(run(cap=20),))
    first, second = reserve(sim), reserve(sim)
    sim.interrupt(first.ticket_id)
    sim.interrupt(second.ticket_id)
    sim.reconcile_attempt(receipt(first.ticket_id, "A", 21))
    state = sim.snapshot()
    assert state.model_held_nanos is None
    assert state.later_run_cap_breaches == (
        ss.SyntheticRunCapBreach("SYNTH-RUN-A", ss.SyntheticModel.OSS, 21, 20, first.ticket_id),
    )
    sim.reconcile_attempt(receipt(second.ticket_id, "B", 0))
    assert sim.snapshot().later_run_cap_breaches == state.later_run_cap_breaches
    assert sim.snapshot().reconciliation_receipts[0].receipt_id == "SYNTH-RECEIPT-A"
    assert sim.snapshot().faults


def test_two_three_dollar_tickets_breach_and_interruption_make_exposure_indeterminate() -> None:
    bound = ss.SyntheticPhysicalBound(
        0, 0, 0, 0, ss.nanos("3"), ss.nanos("3"), "SYNTH-BOUND-A"
    )
    value = ss.SyntheticSpec(original(), bound)
    sim = simulation(value=value, runs=(run(cap=ss.MODEL_CAP_NANOS),))
    first = reserve(sim)
    second = reserve(sim)
    sim.dispatch(
        first.ticket_id,
        ss.SyntheticTransport((ss.SyntheticReply(ss.ReplyKind.ANSWER, ss.nanos("3") + 1),)),
    )
    state = sim.snapshot()
    assert state.model_spent_nanos == ss.nanos("3") + 1
    assert state.attempt_reservations_nanos is None
    assert state.model_held_nanos is None
    assert state.study_held_nanos is None
    assert state.indeterminate_ticket_ids == (second.ticket_id,)
    assert state.physical_bound_breaches == (
        ss.SyntheticPhysicalBoundBreach(
            first.ticket_id,
            first.run_id,
            ss.BoundDimension.CHARGE,
            ss.nanos("3") + 1,
            ss.nanos("3"),
        ),
    )
    assert state.faults
    with pytest.raises(ss.SafetyRefusal, match="faulted"):
        sim.dispatch(
            second.ticket_id, ss.SyntheticTransport((ss.SyntheticReply(ss.ReplyKind.ANSWER, 0),))
        )
    sim.interrupt(second.ticket_id)
    interrupted = sim.snapshot()
    assert interrupted.unknown_count == 1
    assert interrupted.model_held_nanos is None and interrupted.study_held_nanos is None
    with pytest.raises(ss.SafetyRefusal, match="non-final"):
        sim.reconcile_attempt(receipt(second.ticket_id, "A", ss.nanos("2"), final=False))
    assert sim.snapshot() == interrupted
    sim.reconcile_attempt(receipt(second.ticket_id, "A", ss.nanos("2")))
    reconciled = sim.snapshot()
    assert reconciled.indeterminate_ticket_ids == ()
    assert reconciled.attempt_reservations_nanos == 0
    assert reconciled.model_spent_nanos == ss.nanos("5") + 1
    assert reconciled.model_held_nanos == ss.MODEL_CAP_NANOS
    assert reconciled.study_held_nanos == ss.MODEL_CAP_NANOS
    assert reconciled.faults  # settling the other attempt does not validate the broken bound
    assert reconciled.physical_bound_breaches == state.physical_bound_breaches
    with pytest.raises(ss.SafetyRefusal, match="faulted"):
        sim.begin("SYNTH-RUN-A")


def test_ticket_charge_records_both_confirmed_spend_breaches_when_holds_are_indeterminate() -> None:
    bound = ss.SyntheticPhysicalBound(
        0, 0, 0, 0, ss.nanos("3"), ss.nanos("3"), "SYNTH-BOUND-A"
    )
    value = ss.SyntheticSpec(original(), bound)
    sim = simulation(
        value=value,
        runs=(
            run("A", cap=ss.MODEL_CAP_NANOS),
            run("B", model=ss.SyntheticModel.OTHER, spent=ss.nanos("194"), cap=None),
        ),
    )
    first, second = reserve(sim), reserve(sim)
    charge = ss.MODEL_CAP_NANOS + 1
    sim.dispatch(
        first.ticket_id, ss.SyntheticTransport((ss.SyntheticReply(ss.ReplyKind.ANSWER, charge),))
    )
    state = sim.snapshot()
    assert state.model_held_nanos is None and state.study_held_nanos is None
    assert state.model_spent_nanos == ss.MODEL_CAP_NANOS + 1
    assert state.study_spent_nanos == ss.STUDY_CAP_NANOS + 1
    for scope, cap in (
        (ss.BudgetScope.MODEL, ss.MODEL_CAP_NANOS),
        (ss.BudgetScope.STUDY, ss.STUDY_CAP_NANOS),
    ):
        assert ss.SyntheticBudgetBreach(
            scope, ss.BudgetBreachKind.CONFIRMED_SPEND, cap + 1, cap, first.ticket_id
        ) in state.budget_breaches
        assert not any(
            breach.scope is scope and breach.kind is ss.BudgetBreachKind.FINITE_HELD
            for breach in state.budget_breaches
        )
    assert state.later_run_cap_breaches == (
        ss.SyntheticRunCapBreach(
            "SYNTH-RUN-A", ss.SyntheticModel.OSS, charge, ss.MODEL_CAP_NANOS, first.ticket_id
        ),
    )
    sim.interrupt(second.ticket_id)
    sim.reconcile_attempt(receipt(second.ticket_id, "A", 0))
    assert sim.snapshot().model_held_nanos == ss.MODEL_CAP_NANOS + 1
    assert sim.snapshot().study_held_nanos == ss.STUDY_CAP_NANOS + 1
    assert sim.snapshot().later_run_cap_breaches == state.later_run_cap_breaches


def test_bound_breach_invalidates_outstanding_tickets_across_synthetic_runs() -> None:
    bound = ss.SyntheticPhysicalBound(
        0, 0, 0, 0, ss.nanos("3"), ss.nanos("3"), "SYNTH-BOUND-A"
    )
    value = ss.SyntheticSpec(original(), bound)
    sim = simulation(value=value, runs=(run("A", cap=ss.nanos("3")), run("B", cap=ss.nanos("3"))))
    first = reserve(sim, "SYNTH-RUN-A")
    second = reserve(sim, "SYNTH-RUN-B")
    reply = ss.SyntheticReply(ss.ReplyKind.ANSWER, ss.nanos("3") + 1)
    sim.dispatch(first.ticket_id, ss.SyntheticTransport((reply,)))
    assert sim.snapshot().indeterminate_ticket_ids == (second.ticket_id,)
    assert sim.snapshot().model_held_nanos is None
    assert sim.snapshot().study_held_nanos is None
    sim.interrupt(second.ticket_id)
    sim.reconcile_attempt(receipt(second.ticket_id, "A", 0))
    assert sim.snapshot().model_held_nanos == ss.MODEL_CAP_NANOS + 1
    assert sim.snapshot().study_held_nanos == ss.MODEL_CAP_NANOS + 1
    assert sim.snapshot().faults


def test_indeterminate_exposure_persists_until_every_affected_ticket_is_reconciled() -> None:
    sim = simulation(runs=(run(cap=100),))
    first, second, third = reserve(sim), reserve(sim), reserve(sim)
    bad = ss.SyntheticReply(ss.ReplyKind.ANSWER, 1, reported_input_tokens=2)
    sim.dispatch(first.ticket_id, ss.SyntheticTransport((bad,)))
    state = sim.snapshot()
    assert state.indeterminate_ticket_ids == (second.ticket_id, third.ticket_id)
    assert state.model_held_nanos is None and state.study_held_nanos is None
    sim.interrupt(second.ticket_id)
    sim.interrupt(third.ticket_id)
    sim.reconcile_attempt(receipt(second.ticket_id, "A", 1))
    state = sim.snapshot()
    assert state.indeterminate_ticket_ids == (third.ticket_id,)
    assert state.attempt_reservations_nanos is None
    assert state.model_held_nanos is None and state.study_held_nanos is None
    sim.reconcile_attempt(receipt(third.ticket_id, "B", 1))
    state = sim.snapshot()
    assert state.indeterminate_ticket_ids == ()
    assert state.model_held_nanos == 100 and state.study_held_nanos == 100
    assert state.model_spent_nanos == 3
    assert state.faults


def test_breach_discovered_during_reconciliation_invalidates_other_unknown_tickets() -> None:
    sim = simulation(runs=(run(cap=100),))
    first, second = reserve(sim), reserve(sim)
    sim.interrupt(first.ticket_id)
    sim.interrupt(second.ticket_id)
    assert sim.snapshot().attempt_reservations_nanos == 20
    sim.reconcile_attempt(receipt(first.ticket_id, "A", 11))
    state = sim.snapshot()
    assert state.model_spent_nanos == 11
    assert state.indeterminate_ticket_ids == (second.ticket_id,)
    assert state.model_held_nanos is None and state.study_held_nanos is None
    sim.reconcile_attempt(receipt(second.ticket_id, "B", 2))
    state = sim.snapshot()
    assert state.model_spent_nanos == 13
    assert state.model_held_nanos == 100 and state.study_held_nanos == 100
    assert state.faults


def test_concurrent_reservations_cannot_take_the_same_run_funds() -> None:
    sim = simulation(runs=(run(cap=50),))
    operations = [sim.begin("SYNTH-RUN-A") for _ in range(20)]
    barrier = threading.Barrier(len(operations))

    def attempt(operation: ss.SyntheticOperation) -> bool:
        barrier.wait()
        try:
            sim.reserve_next(operation.operation_id)
            return True
        except ss.SafetyRefusal:
            return False

    with ThreadPoolExecutor(max_workers=len(operations)) as executor:
        accepted = list(executor.map(attempt, operations))
    assert sum(accepted) == 5
    state = sim.snapshot()
    assert state.physical_attempts == 5
    assert state.attempt_reservations_nanos == 50
    assert state.model_held_nanos == 50


def test_concurrent_mock_settlements_charge_every_reserved_attempt_once() -> None:
    sim = simulation(runs=(run(cap=100),))
    tickets = [reserve(sim) for _ in range(10)]
    transport = ss.SyntheticTransport((ss.SyntheticReply(ss.ReplyKind.ANSWER, 3),) * 10)
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(
            executor.map(lambda ticket: sim.dispatch(ticket.ticket_id, transport), tickets)
        )
    assert all(result.state is ss.OperationState.COMPLETE for result in results)
    assert transport.consumed == 10
    assert sim.snapshot().model_spent_nanos == 30
    assert sim.snapshot().attempt_reservations_nanos == 0
    with pytest.raises(ss.SafetyRefusal, match="not reserved"):
        sim.dispatch(tickets[0].ticket_id, transport)


def test_concurrent_reallocation_cannot_race_a_reservation() -> None:
    sim = simulation(runs=(run("A", cap=10), run("B", cap=10)))
    operation = sim.begin("SYNTH-RUN-A")
    barrier = threading.Barrier(2)

    def take() -> bool:
        barrier.wait()
        try:
            sim.reserve_next(operation.operation_id)
            return True
        except ss.SafetyRefusal:
            return False

    def move() -> bool:
        barrier.wait()
        try:
            sim.reallocate_caps((("SYNTH-RUN-A", 1), ("SYNTH-RUN-B", 19)))
            return True
        except ss.SafetyRefusal:
            return False

    with ThreadPoolExecutor(max_workers=2) as executor:
        taken = executor.submit(take)
        moved = executor.submit(move)
        assert int(taken.result()) + int(moved.result()) == 1
    state = sim.snapshot()
    assert state.model_held_nanos == 20
    assert state.attempt_reservations_nanos in (0, 10)


def test_only_the_closed_synthetic_transport_is_accepted() -> None:
    sim = simulation()
    ticket = reserve(sim)

    class NotSynthetic:
        def __getattr__(self, name):
            raise AssertionError("an arbitrary adapter must never be invoked")

    with pytest.raises(ss.SafetyRefusal, match="synthetic transport"):
        sim.dispatch(ticket.ticket_id, NotSynthetic())
    assert sim.snapshot().attempt_reservations_nanos == 10


@pytest.mark.parametrize("substitution", ["store", "tuple_element", "tuple_subclass"])
def test_private_transport_store_substitution_never_executes_a_callback(substitution: str) -> None:
    invoked: list[str] = []

    class InertCallback:
        def __len__(self):
            invoked.append("len")
            return 1

        def __iter__(self):
            invoked.append("iter")
            return iter(())

        def __getitem__(self, index):
            invoked.append("getitem")
            return None

        def __call__(self):
            invoked.append("call")

    class InertTuple(tuple):
        def __len__(self):
            invoked.append("tuple-len")
            return 0

        def __iter__(self):
            invoked.append("tuple-iter")
            return iter(())

    sim = simulation()
    ticket = reserve(sim)
    transport = ss.SyntheticTransport((ss.SyntheticReply(ss.ReplyKind.ANSWER, 1),))
    trap = InertCallback()
    if substitution == "store":
        transport._replies = trap
    elif substitution == "tuple_element":
        transport._replies = (trap,)
    else:
        transport._replies = InertTuple()
    with pytest.raises(ss.SafetyRefusal, match="reply store"):
        sim.dispatch(ticket.ticket_id, transport)
    assert invoked == []
    assert transport.consumed == 0
    assert sim.snapshot().unknown_count == 1
    with pytest.raises(ss.SafetyRefusal, match="unknown"):
        sim.begin("SYNTH-RUN-A")
    sim.reconcile_attempt(receipt(ticket.ticket_id, "A", 0))
    assert sim.operation(ticket.operation_id).state is ss.OperationState.FAILED


def test_private_transport_index_substitution_is_refused_without_comparison_callback() -> None:
    invoked: list[str] = []

    class InertIndex:
        def __eq__(self, other):
            invoked.append("eq")
            return False

        def __ge__(self, other):
            invoked.append("ge")
            return False

    sim = simulation()
    ticket = reserve(sim)
    transport = ss.SyntheticTransport((ss.SyntheticReply(ss.ReplyKind.ANSWER, 1),))
    transport._next_index = InertIndex()
    with pytest.raises(ss.SafetyRefusal, match="position"):
        sim.dispatch(ticket.ticket_id, transport)
    assert invoked == []
    assert sim.snapshot().unknown_count == 1


def test_private_transport_lock_substitution_never_enters_callback() -> None:
    invoked: list[str] = []

    class InertContext:
        def __enter__(self):
            invoked.append("enter")
            return self

        def __exit__(self, *args):
            invoked.append("exit")

    sim = simulation()
    ticket = reserve(sim)
    transport = ss.SyntheticTransport((ss.SyntheticReply(ss.ReplyKind.ANSWER, 1),))
    transport._lock = InertContext()
    with pytest.raises(ss.SafetyRefusal, match="transport lock"):
        sim.dispatch(ticket.ticket_id, transport)
    assert invoked == []
    with pytest.raises(ss.SafetyRefusal, match="transport lock"):
        _ = transport.consumed
    assert invoked == []
    assert sim.snapshot().unknown_count == 1
    sim.reconcile_attempt(receipt(ticket.ticket_id, "A", 0))
    assert sim.operation(ticket.operation_id).state is ss.OperationState.FAILED


def test_mock_flow_uses_no_file_or_network_entry_point(monkeypatch) -> None:
    def forbidden(*args, **kwargs):
        raise AssertionError("the synthetic prototype tried to access a file or network")

    with monkeypatch.context() as patch:
        patch.setattr(builtins, "open", forbidden)
        patch.setattr(socket.socket, "connect", forbidden)
        patch.setattr(socket.socket, "connect_ex", forbidden)
        patch.setattr(socket, "create_connection", forbidden)
        sim = simulation()
        ticket = reserve(sim)
        result = sim.dispatch(
            ticket.ticket_id, ss.SyntheticTransport((ss.SyntheticReply(ss.ReplyKind.ANSWER, 1),))
        )
        decision = ss.append_synthetic(ss.SyntheticHistory.empty(original()), (output("A"),))
        assert result.state is ss.OperationState.COMPLETE
        assert decision.added_items == ("SYNTH-ITEM-A",)


def test_original_default_and_capped_followup_are_distinct_conditions() -> None:
    default = original()
    bounded = ss.SyntheticDecoding(ss.DecodingKind.CAPPED_FOLLOWUP, 256)
    differently_bounded = ss.SyntheticDecoding(ss.DecodingKind.CAPPED_FOLLOWUP, 128)
    assert default.max_output_tokens is None
    assert default.request_features == ("temperature=0", "reasoning=provider-default")
    assert bounded.request_features == (*default.request_features, "max_tokens=256")
    identities = {
        default.cache_identity,
        bounded.cache_identity,
        differently_bounded.cache_identity,
    }
    assert len(identities) == 3
    with pytest.raises(ValueError, match="no explicit output limit"):
        ss.SyntheticDecoding(ss.DecodingKind.ORIGINAL_DEFAULT, 256)
    with pytest.raises(ValueError, match="positive"):
        ss.SyntheticDecoding(ss.DecodingKind.CAPPED_FOLLOWUP, None)


def test_requested_limit_alone_is_not_a_verified_physical_charge_bound() -> None:
    capped = ss.SyntheticDecoding(ss.DecodingKind.CAPPED_FOLLOWUP, 300)
    with pytest.raises(ValueError, match="separately supplied"):
        ss.SyntheticPhysicalBound(0, 300, 0, 1)
    with pytest.raises(ValueError, match="synthetic bound identifier"):
        ss.SyntheticPhysicalBound(0, 302, 0, 1, 0, 310)

    # The observed overrun is a lower bound only. This mock separately assumes,
    # rather than infers, that 302 is a verified synthetic billable maximum.
    capped_only = ss.SyntheticPhysicalBound(0, 300, 0, 1, 0, 300, "SYNTH-BOUND-A")
    with pytest.raises(ValueError, match="explicit synthetic overrun"):
        ss.SyntheticSpec(capped, capped_only)
    with pytest.raises(ValueError, match="excludes known overrun"):
        ss.SyntheticSpec(capped, capped_only, known_min_overrun_tokens=2)
    too_small = ss.SyntheticPhysicalBound(0, 301, 0, 1, 0, 310, "SYNTH-BOUND-A")
    with pytest.raises(ValueError, match="excludes known overrun"):
        ss.SyntheticSpec(capped, too_small, known_min_overrun_tokens=2)
    with pytest.raises(ValueError, match="300-token request.*302 example"):
        ss.SyntheticSpec(capped, too_small, known_min_overrun_tokens=1)
    with pytest.raises(ValueError, match="does not cover"):
        ss.SyntheticPhysicalBound(0, 302, 0, 1, 0, 300, "SYNTH-BOUND-A")

    independent = ss.SyntheticPhysicalBound(0, 302, 0, 1, 0, 310, "SYNTH-BOUND-A")
    value = ss.SyntheticSpec(capped, independent, known_min_overrun_tokens=2)
    for missing in ("overruns_in_bound", "independent_bound_verified"):
        sim = simulation(value=value, evidence=assurances(value, **{missing: False}))
        with pytest.raises(ss.SafetyRefusal, match=missing):
            sim.begin("SYNTH-RUN-A")

    sim = simulation(value=value, runs=(run(cap=310),))
    ticket = reserve(sim)
    assert ticket.bound_nanos == 310  # not the requested 300, nor the 302 cross-check
    reply = ss.SyntheticReply(ss.ReplyKind.ANSWER, 302, reported_completion_tokens=302)
    result = sim.dispatch(ticket.ticket_id, ss.SyntheticTransport((reply,)))
    assert result.state is ss.OperationState.COMPLETE
    assert sim.snapshot().model_spent_nanos == 302
    assert sim.snapshot().faults == ()


def test_known_overrun_example_is_not_treated_as_a_general_maximum() -> None:
    capped = ss.SyntheticDecoding(ss.DecodingKind.CAPPED_FOLLOWUP, 300)
    bound = ss.SyntheticPhysicalBound(0, 1000, 0, 1, 0, 1000, "SYNTH-BOUND-A")
    value = ss.SyntheticSpec(capped, bound, known_min_overrun_tokens=2)
    sim = simulation(value=value, runs=(run(cap=1000),))
    ticket = reserve(sim)
    reply = ss.SyntheticReply(ss.ReplyKind.ANSWER, 999, reported_completion_tokens=999)
    assert sim.dispatch(ticket.ticket_id, ss.SyntheticTransport((reply,))).state is (
        ss.OperationState.COMPLETE
    )
    assert ticket.bound_nanos == 1000
    assert sim.snapshot().model_spent_nanos == 999
    assert sim.snapshot().faults == ()


def test_reported_output_above_independent_token_bound_faults_even_below_charge_ceiling() -> None:
    capped = ss.SyntheticDecoding(ss.DecodingKind.CAPPED_FOLLOWUP, 300)
    bound = ss.SyntheticPhysicalBound(0, 302, 0, 1, 0, 1000, "SYNTH-BOUND-A")
    value = ss.SyntheticSpec(capped, bound, known_min_overrun_tokens=2)
    sim = simulation(value=value, runs=(run(cap=1000),))
    ticket = reserve(sim)
    reply = ss.SyntheticReply(ss.ReplyKind.ANSWER, 303, reported_completion_tokens=303)
    operation = sim.dispatch(ticket.ticket_id, ss.SyntheticTransport((reply,)))
    assert operation.state is ss.OperationState.FAILED
    assert sim.snapshot().model_spent_nanos == 303
    assert "token bound" in sim.snapshot().faults[0]
    with pytest.raises(ss.SafetyRefusal, match="faulted"):
        sim.begin("SYNTH-RUN-A")


def test_ambiguous_output_overrun_faults_before_billing_reconciliation() -> None:
    capped = ss.SyntheticDecoding(ss.DecodingKind.CAPPED_FOLLOWUP, 300)
    bound = ss.SyntheticPhysicalBound(0, 302, 0, 1, 0, 1000, "SYNTH-BOUND-A")
    value = ss.SyntheticSpec(capped, bound, known_min_overrun_tokens=2)
    sim = simulation(value=value, runs=(run(cap=1000),))
    ticket = reserve(sim)
    reply = ss.SyntheticReply(ss.ReplyKind.TRANSIENT, None, reported_completion_tokens=303)
    assert sim.dispatch(ticket.ticket_id, ss.SyntheticTransport((reply,))).state is (
        ss.OperationState.WAITING_FOR_BILL
    )
    pending = sim.snapshot()
    assert "token bound" in pending.faults[0]
    assert pending.indeterminate_ticket_ids == (ticket.ticket_id,)
    assert pending.model_held_nanos is None and pending.study_held_nanos is None
    with pytest.raises(ss.SafetyRefusal, match="faulted"):
        sim.begin("SYNTH-RUN-A")
    sim.reconcile_attempt(receipt(ticket.ticket_id, "A", 303))
    assert sim.snapshot().model_spent_nanos == 303
    assert "token bound" in sim.snapshot().faults[0]
    assert sim.operation(ticket.operation_id).state is ss.OperationState.FAILED


@pytest.mark.parametrize(
    ("field", "reason"),
    [("reported_input_tokens", "input"), ("reported_completion_tokens", "output")],
)
def test_reported_token_breach_faults_immediately_while_charge_is_unknown(
    field: str, reason: str
) -> None:
    sim = simulation()
    ticket = reserve(sim)
    reply = ss.SyntheticReply(ss.ReplyKind.TRANSIENT, None, **{field: 2})
    result = sim.dispatch(ticket.ticket_id, ss.SyntheticTransport((reply,)))
    assert result.state is ss.OperationState.WAITING_FOR_BILL
    pending = sim.snapshot()
    assert reason in pending.faults[0]
    assert getattr(sim.ticket(ticket.ticket_id), field) == 2
    dimension = (
        ss.BoundDimension.INPUT_TOKENS
        if field == "reported_input_tokens"
        else ss.BoundDimension.COMPLETION_TOKENS
    )
    assert pending.physical_bound_breaches == (
        ss.SyntheticPhysicalBoundBreach(ticket.ticket_id, ticket.run_id, dimension, 2, 1),
    )
    with pytest.raises(FrozenInstanceError):
        pending.physical_bound_breaches[0].observed = 1
    assert pending.unknown_count == 1
    assert pending.indeterminate_ticket_ids == (ticket.ticket_id,)
    assert pending.attempt_reservations_nanos is None
    assert pending.model_held_nanos is None and pending.study_held_nanos is None
    with pytest.raises(ss.SafetyRefusal, match="faulted"):
        sim.begin("SYNTH-RUN-A")
    sim.reconcile_attempt(receipt(ticket.ticket_id, "A", 0))
    after = sim.snapshot()
    assert after.indeterminate_ticket_ids == ()
    assert after.model_held_nanos == ss.nanos("1")
    assert after.study_held_nanos == ss.nanos("1")
    assert after.faults
    assert after.physical_bound_breaches == pending.physical_bound_breaches


def test_both_reported_token_breaches_are_recorded_before_unknown_charge_settles() -> None:
    sim = simulation()
    ticket = reserve(sim)
    reply = ss.SyntheticReply(
        ss.ReplyKind.TRANSIENT, None, reported_completion_tokens=2, reported_input_tokens=2
    )
    sim.dispatch(ticket.ticket_id, ss.SyntheticTransport((reply,)))
    assert len(sim.snapshot().faults) == 2
    assert sim.ticket(ticket.ticket_id).reported_input_tokens == 2
    assert sim.ticket(ticket.ticket_id).reported_completion_tokens == 2
    assert "input" in sim.snapshot().faults[0]
    assert "output" in sim.snapshot().faults[1]
    assert [breach.dimension for breach in sim.snapshot().physical_bound_breaches] == [
        ss.BoundDimension.INPUT_TOKENS,
        ss.BoundDimension.COMPLETION_TOKENS,
    ]
    sim.reconcile_attempt(receipt(ticket.ticket_id, "A", 1))
    assert len(sim.snapshot().faults) == 2
    assert sim.operation(ticket.operation_id).state is ss.OperationState.FAILED


def test_reported_input_and_completion_at_independent_bounds_are_allowed() -> None:
    sim = simulation()
    ticket = reserve(sim)
    reply = ss.SyntheticReply(
        ss.ReplyKind.ANSWER, 5, reported_completion_tokens=1, reported_input_tokens=1
    )
    operation = sim.dispatch(ticket.ticket_id, ss.SyntheticTransport((reply,)))
    assert operation.state is ss.OperationState.COMPLETE
    assert sim.snapshot().faults == ()
    assert sim.snapshot().model_spent_nanos == 5


@pytest.mark.parametrize(
    ("field", "dimension"),
    [("input_tokens", ss.BoundDimension.INPUT_TOKENS),
     ("completion_tokens", ss.BoundDimension.COMPLETION_TOKENS)],
)
def test_final_receipt_new_usage_faults_and_invalidates_other_pending_attempts(
    field: str, dimension: ss.BoundDimension
) -> None:
    sim = simulation(runs=(run(cap=100),))
    first, second = reserve(sim), reserve(sim)
    sim.dispatch(
        first.ticket_id, ss.SyntheticTransport((ss.SyntheticReply(ss.ReplyKind.TRANSIENT, None),))
    )
    final = receipt(first.ticket_id, "A", 1, **{field: 2})
    sim.reconcile_attempt(final)
    state = sim.snapshot()
    assert state.model_spent_nanos == 1
    assert state.model_held_nanos is None and state.study_held_nanos is None
    assert state.indeterminate_ticket_ids == (second.ticket_id,)
    assert state.physical_bound_breaches == (
        ss.SyntheticPhysicalBoundBreach(first.ticket_id, first.run_id, dimension, 2, 1),
    )
    assert state.reconciliation_receipts == (final,)
    settled = sim.ticket(first.ticket_id)
    assert settled.reported_input_tokens is None and settled.reported_completion_tokens is None
    actual = (
        settled.receipt_reported_input_tokens
        if field == "input_tokens"
        else settled.receipt_reported_completion_tokens
    )
    assert actual == 2
    sim.interrupt(second.ticket_id)
    sim.reconcile_attempt(receipt(second.ticket_id, "B", 0))
    assert sim.snapshot().model_held_nanos == 100
    assert sim.snapshot().faults


def test_absent_receipt_usage_remains_none_and_is_not_synthetic_zero() -> None:
    sim = simulation()
    ticket = reserve(sim)
    reply = ss.SyntheticReply(ss.ReplyKind.TRANSIENT, None, reported_input_tokens=0)
    sim.dispatch(ticket.ticket_id, ss.SyntheticTransport((reply,)))
    final = receipt(ticket.ticket_id, "A", 0)
    sim.reconcile_attempt(final)
    settled = sim.ticket(ticket.ticket_id)
    assert settled.reported_input_tokens == 0
    assert settled.reported_completion_tokens is None
    assert settled.receipt_reported_input_tokens is None
    assert settled.receipt_reported_completion_tokens is None
    assert sim.snapshot().reconciliation_receipts == (final,)
    assert final.reported_input_tokens is None and final.reported_completion_tokens is None
    assert sim.snapshot().usage_conflicts == ()
    assert sim.snapshot().physical_bound_breaches == ()


def test_final_receipt_records_both_token_breaches_and_a_charge_breach() -> None:
    sim = simulation(runs=(run(cap=100),))
    first, second = reserve(sim), reserve(sim)
    sim.dispatch(
        first.ticket_id, ss.SyntheticTransport((ss.SyntheticReply(ss.ReplyKind.TRANSIENT, None),))
    )
    final = receipt(first.ticket_id, "A", 11, input_tokens=2, completion_tokens=2)
    sim.reconcile_attempt(final)
    state = sim.snapshot()
    assert state.model_spent_nanos == 11
    assert state.indeterminate_ticket_ids == (second.ticket_id,)
    assert state.model_held_nanos is None and state.study_held_nanos is None
    assert [breach.dimension for breach in state.physical_bound_breaches] == [
        ss.BoundDimension.INPUT_TOKENS,
        ss.BoundDimension.COMPLETION_TOKENS,
        ss.BoundDimension.CHARGE,
    ]
    assert state.reconciliation_receipts == (final,)
    with pytest.raises(ss.SafetyRefusal, match="faulted"):
        sim.begin("SYNTH-RUN-A")


def test_receipt_usage_conflict_is_recorded_and_does_not_discard_confirmed_charge() -> None:
    sim = simulation(runs=(run(cap=100),))
    first, second = reserve(sim), reserve(sim)
    reply = ss.SyntheticReply(ss.ReplyKind.TRANSIENT, None, reported_input_tokens=0)
    sim.dispatch(first.ticket_id, ss.SyntheticTransport((reply,)))
    final = receipt(first.ticket_id, "A", 2, input_tokens=1)
    sim.reconcile_attempt(final)
    state = sim.snapshot()
    assert state.model_spent_nanos == 2
    assert state.model_held_nanos is None and state.study_held_nanos is None
    assert state.indeterminate_ticket_ids == (second.ticket_id,)
    assert state.usage_conflicts == (
        ss.SyntheticUsageConflict(
            first.ticket_id, final.receipt_id, ss.BoundDimension.INPUT_TOKENS, 0, 1
        ),
    )
    assert state.physical_bound_breaches == ()  # both counts are within the synthetic bound
    assert state.reconciliation_receipts == (final,)
    assert sim.ticket(first.ticket_id).reported_input_tokens == 0
    assert sim.ticket(first.ticket_id).receipt_reported_input_tokens == 1
    sim.interrupt(second.ticket_id)
    sim.reconcile_attempt(receipt(second.ticket_id, "B", 0))
    assert sim.snapshot().model_held_nanos == 100
    assert sim.snapshot().usage_conflicts == state.usage_conflicts
    assert sim.snapshot().faults


def test_receipt_repeating_an_already_observed_breach_does_not_erase_or_duplicate_it() -> None:
    sim = simulation()
    ticket = reserve(sim)
    reply = ss.SyntheticReply(ss.ReplyKind.TRANSIENT, None, reported_input_tokens=2)
    sim.dispatch(ticket.ticket_id, ss.SyntheticTransport((reply,)))
    prior = sim.snapshot().physical_bound_breaches
    final = receipt(ticket.ticket_id, "A", 1, input_tokens=2)
    sim.reconcile_attempt(final)
    assert sim.snapshot().physical_bound_breaches == prior
    assert sim.snapshot().usage_conflicts == ()
    assert sim.snapshot().reconciliation_receipts == (final,)
    assert sim.snapshot().faults


def test_linked_prior_liability_receipt_checks_usage_and_charge_against_its_bound() -> None:
    value = spec()
    liability = ss.SyntheticLiability(
        "SYNTH-LIABILITY-A", ss.SyntheticModel.OSS, None, physical_spec_hash=value.fingerprint
    )
    sim = simulation(value=value, liabilities=(liability,))
    final = receipt(liability.liability_id, "A", 11, input_tokens=2, completion_tokens=2)
    sim.reconcile_liability(final)
    state = sim.snapshot()
    assert state.model_spent_nanos == 11
    assert state.reconciliation_receipts == (final,)
    assert state.liability_reconciliations == (
        ss.SyntheticLiabilityReconciliation(liability, final),
    )
    assert state.liability_bound_breaches == (
        ss.SyntheticLiabilityBoundBreach(
            liability.liability_id, ss.BoundDimension.INPUT_TOKENS, 2, 1
        ),
        ss.SyntheticLiabilityBoundBreach(
            liability.liability_id, ss.BoundDimension.COMPLETION_TOKENS, 2, 1
        ),
        ss.SyntheticLiabilityBoundBreach(liability.liability_id, ss.BoundDimension.CHARGE, 11, 10),
    )
    assert len(state.faults) == 3


def test_linked_liability_missing_usage_is_unknown_not_zero() -> None:
    value = spec()
    liability = ss.SyntheticLiability(
        "SYNTH-LIABILITY-A", ss.SyntheticModel.OSS, None, physical_spec_hash=value.fingerprint
    )
    sim = simulation(value=value, liabilities=(liability,))
    final = receipt(liability.liability_id, "A", 11)
    sim.reconcile_liability(final)
    state = sim.snapshot()
    assert final.reported_input_tokens is None and final.reported_completion_tokens is None
    assert state.reconciliation_receipts == (final,)
    assert state.liability_bound_breaches == (
        ss.SyntheticLiabilityBoundBreach(liability.liability_id, ss.BoundDimension.CHARGE, 11, 10),
    )


def test_linked_liability_usage_breach_is_recorded_while_another_liability_is_unbounded() -> None:
    value = spec()
    first = ss.SyntheticLiability(
        "SYNTH-LIABILITY-A", ss.SyntheticModel.OSS, None, physical_spec_hash=value.fingerprint
    )
    second = ss.SyntheticLiability("SYNTH-LIABILITY-B", ss.SyntheticModel.OSS, None)
    sim = simulation(value=value, liabilities=(first, second))
    final = receipt(first.liability_id, "A", 1, input_tokens=2)
    sim.reconcile_liability(final)
    state = sim.snapshot()
    assert state.model_held_nanos is None and state.study_held_nanos is None
    assert state.liability_bound_breaches == (
        ss.SyntheticLiabilityBoundBreach(first.liability_id, ss.BoundDimension.INPUT_TOKENS, 2, 1),
    )
    assert state.reconciliation_receipts == (final,)
    assert "input" in state.faults[0]
    sim.reconcile_liability(receipt(second.liability_id, "B", 0))
    assert sim.snapshot().liability_bound_breaches == state.liability_bound_breaches
    assert sim.snapshot().faults


def test_unlinked_liability_receipt_usage_is_preserved_but_fails_closed() -> None:
    liability = ss.SyntheticLiability(
        "SYNTH-LIABILITY-A", ss.SyntheticModel.OSS, 10,
        independent_max_evidence_id="SYNTH-INDEPENDENT-A",
    )
    sim = simulation(liabilities=(liability,))
    final = receipt(liability.liability_id, "A", 0, input_tokens=0)
    sim.reconcile_liability(final)
    state = sim.snapshot()
    assert state.reconciliation_receipts == (final,)
    assert state.liability_reconciliations == (
        ss.SyntheticLiabilityReconciliation(liability, final),
    )
    assert final.reported_input_tokens == 0 and final.reported_completion_tokens is None
    assert state.liability_bound_breaches == ()
    assert "no matched physical bound" in state.faults[0]
    with pytest.raises(ss.SafetyRefusal, match="faulted"):
        sim.begin("SYNTH-RUN-A")


def test_unlinked_usage_fault_does_not_hide_confirmed_spend_while_another_charge_is_unknown(
) -> None:
    liabilities = (
        ss.SyntheticLiability("SYNTH-LIABILITY-A", ss.SyntheticModel.OSS, None),
        ss.SyntheticLiability("SYNTH-LIABILITY-B", ss.SyntheticModel.OSS, None),
    )
    sim = simulation(liabilities=liabilities)
    final = receipt("SYNTH-LIABILITY-A", "A", ss.MODEL_CAP_NANOS + 1, input_tokens=2)
    sim.reconcile_liability(final)
    state = sim.snapshot()
    assert state.model_held_nanos is None and state.study_held_nanos is None
    assert state.reconciliation_receipts == (final,)
    assert any("no matched physical bound" in fault for fault in state.faults)
    assert ss.SyntheticBudgetBreach(
        ss.BudgetScope.MODEL,
        ss.BudgetBreachKind.CONFIRMED_SPEND,
        ss.MODEL_CAP_NANOS + 1,
        ss.MODEL_CAP_NANOS,
        final.receipt_id,
    ) in state.budget_breaches


def test_liability_link_requires_the_matching_synthetic_oss_specification() -> None:
    value = spec()
    with pytest.raises(ValueError, match="OSS spec"):
        ss.SyntheticLiability(
            "SYNTH-LIABILITY-A", ss.SyntheticModel.OTHER, None, physical_spec_hash=value.fingerprint
        )
    wrong = ss.SyntheticLiability(
        "SYNTH-LIABILITY-A", ss.SyntheticModel.OSS, None, physical_spec_hash="0" * 64
    )
    with pytest.raises(ValueError, match="different physical specification"):
        simulation(value=value, liabilities=(wrong,))


@pytest.mark.parametrize("field", ["input_tokens", "completion_tokens"])
@pytest.mark.parametrize("bad", [-1, True, 1.0])
def test_receipt_usage_requires_nonnegative_exact_integers(field: str, bad) -> None:
    with pytest.raises(ValueError, match="reported_"):
        receipt("SYNTH-TICKET-1", "A", 0, **{field: bad})


@pytest.mark.parametrize("field", ["reported_input_tokens", "reported_completion_tokens"])
@pytest.mark.parametrize("bad", [-1, True, 1.0])
def test_reported_usage_requires_nonnegative_exact_integers(field: str, bad) -> None:
    with pytest.raises(ValueError, match=field):
        ss.SyntheticReply(ss.ReplyKind.ANSWER, 0, **{field: bad})


def test_reservation_uses_the_independent_charge_ceiling_not_a_token_price_estimate() -> None:
    bound = ss.SyntheticPhysicalBound(1, 1, 1, 1, 0, 100, "SYNTH-BOUND-A")
    assert bound.token_price_crosscheck_nanos == 2
    value = ss.SyntheticSpec(original(), bound)
    too_small = simulation(value=value, runs=(run(cap=99),))
    operation = too_small.begin("SYNTH-RUN-A")
    with pytest.raises(ss.SafetyRefusal, match="reserve"):
        too_small.reserve_next(operation.operation_id)
    assert too_small.snapshot().physical_attempts == 0
    enough = simulation(value=value, runs=(run(cap=100),))
    assert reserve(enough).bound_nanos == 100


def test_output_append_preserves_exact_historical_bytes_and_provenance() -> None:
    initial = ss.SyntheticHistory.empty(original())
    first = output("A", source="A")
    second = output("B", source="B", reading=ss.SyntheticReading.BETA)
    first_decision = ss.append_synthetic(initial, (first,))
    history = ss.SyntheticHistory(first_decision.combined_bytes, original())
    supplied = history.historical_bytes
    result = ss.append_synthetic(history, (second,))
    assert history.historical_bytes == supplied
    assert result.historical_bytes == supplied
    assert result.combined_bytes == supplied + result.appended_bytes
    assert result.historical_sha256 == hashlib.sha256(supplied).hexdigest()
    assert result.combined_sha256 == hashlib.sha256(result.combined_bytes).hexdigest()
    assert result.added_items == ("SYNTH-ITEM-B",)
    assert ss.SyntheticHistory(result.combined_bytes, original()).records == (first, second)


def test_identical_output_duplicates_are_explicit_idempotent_noops() -> None:
    first = output("A")
    decision = ss.append_synthetic(ss.SyntheticHistory.empty(original()), (first,))
    history = ss.SyntheticHistory(decision.combined_bytes, original())
    result = ss.append_synthetic(history, (first, first))
    assert result.appended_bytes == b""
    assert result.combined_bytes == history.historical_bytes
    assert result.duplicate_items == ("SYNTH-ITEM-A", "SYNTH-ITEM-A")


@pytest.mark.parametrize("difference", ["reading", "provenance"])
def test_output_conflicts_are_all_or_nothing_and_leave_history_unchanged(difference: str) -> None:
    first = output("A")
    decision = ss.append_synthetic(ss.SyntheticHistory.empty(original()), (first,))
    history = ss.SyntheticHistory(decision.combined_bytes, original())
    before = history.historical_bytes
    conflict = (
        output("A", reading=ss.SyntheticReading.BETA)
        if difference == "reading"
        else output("A", source="B")
    )
    with pytest.raises(ss.OutputConflict, match="conflicting"):
        ss.append_synthetic(history, (output("B"), conflict))
    assert history.historical_bytes == before
    assert history.records == (first,)


def test_conflicting_additions_and_historical_duplicates_are_detected() -> None:
    history = ss.SyntheticHistory.empty(original())
    with pytest.raises(ss.OutputConflict, match="conflicting"):
        ss.append_synthetic(history, (output("A"), output("A", reading=ss.SyntheticReading.BETA)))
    one = ss.append_synthetic(history, (output("A"),))
    with pytest.raises(ss.OutputConflict, match="duplicate"):
        ss.SyntheticHistory(one.combined_bytes + one.appended_bytes, original())


def test_capped_followup_cannot_fill_original_history() -> None:
    default = original()
    capped = ss.SyntheticDecoding(ss.DecodingKind.CAPPED_FOLLOWUP, 256)
    original_history = ss.SyntheticHistory.empty(default)
    bounded_output = output("A", decoding=capped)
    with pytest.raises(ss.OutputConflict, match="distinct decoding"):
        ss.append_synthetic(original_history, (bounded_output,))
    bounded_history = ss.SyntheticHistory.empty(capped)
    result = ss.append_synthetic(bounded_history, (bounded_output,))
    assert result.added_items == ("SYNTH-ITEM-A",)
    assert original_history.records == ()
    with pytest.raises(ss.OutputConflict, match="decoding"):
        ss.SyntheticHistory(result.combined_bytes, default)


def test_history_accepts_only_tagged_canonical_bounded_synthetic_bytes() -> None:
    default = original()
    with pytest.raises(ss.OutputConflict, match="tagged"):
        ss.SyntheticHistory(b"not-synthetic", default)
    history = ss.SyntheticHistory.empty(default)
    with pytest.raises(ss.OutputConflict, match="incomplete"):
        ss.SyntheticHistory(history.historical_bytes + b"SYNTH-ITEM-A", default)
    with pytest.raises(ss.OutputConflict, match="tagged"):
        ss.SyntheticHistory(
            history.historical_bytes + b"X" * ss.MAX_SYNTHETIC_HISTORY_BYTES, default
        )
    with pytest.raises(ValueError, match="synthetic item"):
        ss.SyntheticOutput("ITEM-A", default, "SYNTH-SOURCE-A", ss.SyntheticReading.ALPHA)


def test_returned_state_and_history_are_immutable_values() -> None:
    sim = simulation()
    state = sim.snapshot()
    history = ss.SyntheticHistory.empty(original())
    with pytest.raises(FrozenInstanceError):
        state.model_spent_nanos = 9
    with pytest.raises(FrozenInstanceError):
        history.historical_bytes = b"changed"
    assert sim.snapshot().model_spent_nanos == 0


@pytest.mark.parametrize(
    ("field", "dimension"),
    [
        ("input_tokens", ss.BoundDimension.INPUT_TOKENS),
        ("completion_tokens", ss.BoundDimension.COMPLETION_TOKENS),
    ],
)
def test_late_final_usage_faults_before_retry_without_charging_twice(
    field: str, dimension: ss.BoundDimension
) -> None:
    sim = simulation(runs=(run(cap=100),))
    operation = sim.begin("SYNTH-RUN-A")
    first = sim.reserve_next(operation.operation_id)
    transport = ss.SyntheticTransport((ss.SyntheticReply(ss.ReplyKind.TRANSIENT, 3),))
    assert sim.dispatch(first.ticket_id, transport).state is ss.OperationState.READY
    assert sim.snapshot().model_spent_nanos == 3
    late = receipt(first.ticket_id, "A", 3, **{field: 2})
    sim.reconcile_attempt(late)
    state = sim.snapshot()
    assert state.model_spent_nanos == 3 and state.study_spent_nanos == 3
    assert state.physical_attempts == 1 and transport.consumed == 1
    assert state.physical_bound_breaches == (
        ss.SyntheticPhysicalBoundBreach(first.ticket_id, first.run_id, dimension, 2, 1),
    )
    assert state.reconciliation_receipts == (late,)
    assert state.shared_physical_bound_disproved
    with pytest.raises(ss.SafetyRefusal, match="faulted"):
        sim.reserve_next(operation.operation_id)


def test_late_usage_breach_invalidates_an_already_reserved_retry() -> None:
    sim = simulation(runs=(run(cap=100),))
    operation = sim.begin("SYNTH-RUN-A")
    first = sim.reserve_next(operation.operation_id)
    sim.dispatch(
        first.ticket_id, ss.SyntheticTransport((ss.SyntheticReply(ss.ReplyKind.TRANSIENT, 2),))
    )
    second = sim.reserve_next(operation.operation_id)
    sim.reconcile_attempt(receipt(first.ticket_id, "A", 2, input_tokens=2))
    state = sim.snapshot()
    assert state.model_spent_nanos == 2
    assert state.indeterminate_ticket_ids == (second.ticket_id,)
    assert state.model_held_nanos is None and state.study_held_nanos is None
    transport = ss.SyntheticTransport((ss.SyntheticReply(ss.ReplyKind.ANSWER, 1),))
    with pytest.raises(ss.SafetyRefusal, match="faulted"):
        sim.dispatch(second.ticket_id, transport)
    assert transport.consumed == 0
    sim.interrupt(second.ticket_id)
    sim.reconcile_attempt(receipt(second.ticket_id, "B", 0))
    assert sim.snapshot().model_spent_nanos == 2
    assert sim.snapshot().model_held_nanos == 100
    assert sim.snapshot().faults


def test_late_final_receipt_records_both_usage_breaches_for_one_booked_charge() -> None:
    sim = simulation()
    operation = sim.begin("SYNTH-RUN-A")
    ticket = sim.reserve_next(operation.operation_id)
    sim.dispatch(
        ticket.ticket_id, ss.SyntheticTransport((ss.SyntheticReply(ss.ReplyKind.TRANSIENT, 3),))
    )
    late = receipt(ticket.ticket_id, "A", 3, input_tokens=2, completion_tokens=2)
    sim.reconcile_attempt(late)
    state = sim.snapshot()
    assert state.model_spent_nanos == 3
    assert [breach.dimension for breach in state.physical_bound_breaches] == [
        ss.BoundDimension.INPUT_TOKENS,
        ss.BoundDimension.COMPLETION_TOKENS,
    ]
    assert state.reconciliation_receipts == (late,)
    with pytest.raises(ss.SafetyRefusal, match="faulted"):
        sim.reserve_next(operation.operation_id)


def test_late_usage_can_enrich_a_prior_final_receipt_with_the_same_id() -> None:
    sim = simulation()
    operation = sim.begin("SYNTH-RUN-A")
    ticket = sim.reserve_next(operation.operation_id)
    sim.dispatch(
        ticket.ticket_id, ss.SyntheticTransport((ss.SyntheticReply(ss.ReplyKind.TRANSIENT, None),))
    )
    first = receipt(ticket.ticket_id, "A", 2)
    sim.reconcile_attempt(first)
    late = receipt(ticket.ticket_id, "A", 2, input_tokens=1)
    sim.reconcile_attempt(late)
    assert sim.snapshot().model_spent_nanos == 2
    assert sim.snapshot().reconciliation_receipts == (first, late)
    assert sim.ticket(ticket.ticket_id).receipt_reported_input_tokens == 1
    assert sim.ticket(ticket.ticket_id).receipt_reported_completion_tokens is None
    assert sim.snapshot().faults == ()
    with pytest.raises(ss.SafetyRefusal, match="already used"):
        sim.reconcile_attempt(late)
    assert sim.snapshot().model_spent_nanos == 2
    assert sim.reserve_next(operation.operation_id).bound_nanos == 10


def test_late_usage_conflicts_with_an_earlier_receipt_without_overwriting_it() -> None:
    sim = simulation()
    ticket = reserve(sim)
    sim.dispatch(
        ticket.ticket_id, ss.SyntheticTransport((ss.SyntheticReply(ss.ReplyKind.ANSWER, None),))
    )
    first = receipt(ticket.ticket_id, "A", 2, input_tokens=0)
    sim.reconcile_attempt(first)
    late = receipt(ticket.ticket_id, "B", 2, input_tokens=1)
    sim.reconcile_attempt(late)
    state = sim.snapshot()
    assert state.model_spent_nanos == 2
    assert state.usage_conflicts == (
        ss.SyntheticUsageConflict(
            ticket.ticket_id, late.receipt_id, ss.BoundDimension.INPUT_TOKENS, 0, 1
        ),
    )
    assert state.reconciliation_receipts == (first, late)
    assert sim.ticket(ticket.ticket_id).receipt_reported_input_tokens == 0
    assert state.shared_physical_bound_untrusted and not state.shared_physical_bound_disproved
    assert state.faults


@pytest.mark.parametrize("claimed", [2, 4, 11])
def test_late_contradictory_charge_is_audited_indeterminate_and_never_double_counted(
    claimed: int,
) -> None:
    sim = simulation(runs=(run(cap=100),))
    operation = sim.begin("SYNTH-RUN-A")
    ticket = sim.reserve_next(operation.operation_id)
    sim.dispatch(
        ticket.ticket_id, ss.SyntheticTransport((ss.SyntheticReply(ss.ReplyKind.TRANSIENT, 3),))
    )
    disputed = receipt(ticket.ticket_id, "A", claimed)
    with pytest.raises(ss.SafetyRefusal, match="contradictory"):
        sim.reconcile_attempt(disputed)
    state = sim.snapshot()
    assert state.model_spent_nanos == 3 and state.study_spent_nanos == 3
    assert state.model_held_nanos is None and state.study_held_nanos is None
    assert state.attempt_reservations_nanos is None
    assert state.indeterminate_charge_ticket_ids == (ticket.ticket_id,)
    assert state.charge_conflicts == (
        ss.SyntheticChargeConflict(ticket.ticket_id, disputed.receipt_id, 3, claimed),
    )
    assert state.reconciliation_receipts == (disputed,)
    assert state.shared_physical_bound_untrusted
    assert not state.shared_physical_bound_disproved
    with pytest.raises(ss.SafetyRefusal, match="faulted"):
        sim.reserve_next(operation.operation_id)
    sim.reconcile_attempt(receipt(ticket.ticket_id, "B", 3, input_tokens=0))
    assert sim.snapshot().model_spent_nanos == 3
    assert sim.snapshot().model_held_nanos is None
    assert sim.snapshot().indeterminate_charge_ticket_ids == (ticket.ticket_id,)
    assert sim.snapshot().charge_conflicts == state.charge_conflicts


def test_duplicate_receipt_id_with_contradictory_charge_still_fails_closed() -> None:
    sim = simulation()
    ticket = reserve(sim)
    sim.dispatch(
        ticket.ticket_id, ss.SyntheticTransport((ss.SyntheticReply(ss.ReplyKind.ANSWER, None),))
    )
    first = receipt(ticket.ticket_id, "A", 3)
    sim.reconcile_attempt(first)
    disputed = receipt(ticket.ticket_id, "A", 4)
    with pytest.raises(ss.SafetyRefusal, match="contradictory"):
        sim.reconcile_attempt(disputed)
    state = sim.snapshot()
    assert state.model_spent_nanos == 3
    assert state.model_held_nanos is None
    assert state.reconciliation_receipts == (first, disputed)
    assert state.charge_conflicts[0].receipt_id == first.receipt_id


def test_late_charge_conflict_also_records_new_usage_breach_without_double_charge() -> None:
    sim = simulation()
    ticket = reserve(sim)
    sim.dispatch(
        ticket.ticket_id, ss.SyntheticTransport((ss.SyntheticReply(ss.ReplyKind.ANSWER, 3),))
    )
    disputed = receipt(ticket.ticket_id, "A", 4, input_tokens=2)
    with pytest.raises(ss.SafetyRefusal, match="contradictory"):
        sim.reconcile_attempt(disputed)
    state = sim.snapshot()
    assert state.model_spent_nanos == 3
    assert state.model_held_nanos is None and state.study_held_nanos is None
    assert state.shared_physical_bound_disproved
    assert state.physical_bound_breaches == (
        ss.SyntheticPhysicalBoundBreach(
            ticket.ticket_id, ticket.run_id, ss.BoundDimension.INPUT_TOKENS, 2, 1
        ),
    )
    assert state.charge_conflicts == (
        ss.SyntheticChargeConflict(ticket.ticket_id, disputed.receipt_id, 3, 4),
    )


def test_finite_independent_liability_maximum_requires_separate_synthetic_evidence() -> None:
    with pytest.raises(ValueError, match="separate synthetic evidence"):
        ss.SyntheticLiability("SYNTH-LIABILITY-A", ss.SyntheticModel.OSS, 10)
    with pytest.raises(ValueError, match="synthetic independent identifier"):
        ss.SyntheticLiability(
            "SYNTH-LIABILITY-A", ss.SyntheticModel.OSS, 10,
            independent_max_evidence_id="NOT-SYNTHETIC",
        )
    with pytest.raises(ValueError, match="finite maximum"):
        ss.SyntheticLiability(
            "SYNTH-LIABILITY-A", ss.SyntheticModel.OSS, None,
            independent_max_evidence_id="SYNTH-INDEPENDENT-A",
        )


def test_shared_liability_maximum_must_cover_the_registered_synthetic_physical_bound() -> None:
    value = spec()
    liability = ss.SyntheticLiability(
        "SYNTH-LIABILITY-A", ss.SyntheticModel.OSS, 9, physical_spec_hash=value.fingerprint
    )
    assert liability.maximum_kind is ss.LiabilityMaximumKind.SHARED_PHYSICAL
    with pytest.raises(ValueError, match="cover the physical bound"):
        simulation(value=value, liabilities=(liability,))


def test_disproved_shared_maximum_is_indeterminate_but_independent_maximum_survives() -> None:
    value = spec()
    trigger = ss.SyntheticLiability(
        "SYNTH-LIABILITY-A", ss.SyntheticModel.OSS, 10, physical_spec_hash=value.fingerprint
    )
    shared = ss.SyntheticLiability(
        "SYNTH-LIABILITY-B", ss.SyntheticModel.OSS, 10, physical_spec_hash=value.fingerprint
    )
    independent = ss.SyntheticLiability(
        "SYNTH-LIABILITY-C", ss.SyntheticModel.OSS, 9,
        physical_spec_hash=value.fingerprint, independent_max_evidence_id="SYNTH-INDEPENDENT-C",
    )
    assert trigger.maximum_kind is ss.LiabilityMaximumKind.SHARED_PHYSICAL
    assert independent.maximum_kind is ss.LiabilityMaximumKind.INDEPENDENT
    sim = simulation(value=value, runs=(run(cap=100),), liabilities=(trigger, shared, independent))
    assert sim.snapshot().model_held_nanos == 129
    sim.reconcile_liability(receipt(trigger.liability_id, "A", 1, input_tokens=2))
    state = sim.snapshot()
    assert state.shared_physical_bound_disproved
    assert state.indeterminate_liability_ids == (shared.liability_id,)
    assert state.model_held_nanos is None and state.study_held_nanos is None
    sim.reconcile_liability(receipt(shared.liability_id, "B", 0))
    after_shared = sim.snapshot()
    assert after_shared.indeterminate_liability_ids == ()
    assert after_shared.model_held_nanos == 110  # run hold + booked charge + independent max
    assert after_shared.study_held_nanos == 110
    assert after_shared.faults
    sim.reconcile_liability(receipt(independent.liability_id, "C", 2))
    assert sim.snapshot().model_spent_nanos == 3
    assert sim.snapshot().faults


def test_disproved_independent_evidence_invalidates_only_maxima_using_that_evidence() -> None:
    first = ss.SyntheticLiability(
        "SYNTH-LIABILITY-A", ss.SyntheticModel.OSS, 10,
        independent_max_evidence_id="SYNTH-INDEPENDENT-X",
    )
    same = ss.SyntheticLiability(
        "SYNTH-LIABILITY-B", ss.SyntheticModel.OSS, 10,
        independent_max_evidence_id="SYNTH-INDEPENDENT-X",
    )
    separate = ss.SyntheticLiability(
        "SYNTH-LIABILITY-C", ss.SyntheticModel.OSS, 10,
        independent_max_evidence_id="SYNTH-INDEPENDENT-Y",
    )
    sim = simulation(runs=(run(cap=100),), liabilities=(first, same, separate))
    sim.reconcile_liability(receipt(first.liability_id, "A", 11))
    state = sim.snapshot()
    assert state.disproved_independent_max_evidence_ids == ("SYNTH-INDEPENDENT-X",)
    assert state.indeterminate_liability_ids == (same.liability_id,)
    assert state.model_held_nanos is None
    sim.reconcile_liability(receipt(same.liability_id, "B", 0))
    assert sim.snapshot().indeterminate_liability_ids == ()
    assert sim.snapshot().model_held_nanos == 121
    assert sim.snapshot().faults


@pytest.mark.parametrize("scope", [ss.BudgetScope.MODEL, ss.BudgetScope.STUDY])
def test_held_only_fault_clears_after_reconciliation_with_immutable_audit(
    scope: ss.BudgetScope,
) -> None:
    model = ss.SyntheticModel.OSS if scope is ss.BudgetScope.MODEL else ss.SyntheticModel.OTHER
    maximum = ss.nanos("4") if scope is ss.BudgetScope.MODEL else ss.nanos("110")
    charge = ss.nanos("3") if scope is ss.BudgetScope.MODEL else ss.nanos("100")
    cap = ss.MODEL_CAP_NANOS if scope is ss.BudgetScope.MODEL else ss.STUDY_CAP_NANOS
    first = ss.SyntheticLiability(
        "SYNTH-LIABILITY-A", model, maximum, independent_max_evidence_id="SYNTH-INDEPENDENT-A"
    )
    second = ss.SyntheticLiability(
        "SYNTH-LIABILITY-B", model, maximum, independent_max_evidence_id="SYNTH-INDEPENDENT-B"
    )
    sim = simulation(runs=(run(cap=ss.nanos("1")),), liabilities=(first, second))
    assert scope in sim.snapshot().active_held_breaches
    sim.reconcile_liability(receipt(first.liability_id, "A", charge))
    overheld = sim.snapshot()
    assert any(f"{scope.value} finite_held" in fault for fault in overheld.faults)
    assert overheld.held_exposure_resolutions == ()
    sim.reconcile_liability(receipt(second.liability_id, "B", 0))
    after = sim.snapshot()
    held = ss.nanos("1") + charge
    assert after.faults == ()
    assert scope not in after.active_held_breaches
    assert after.budget_breaches == overheld.budget_breaches
    assert after.held_exposure_resolutions == (
        ss.SyntheticHeldExposureResolution(scope, "SYNTH-RECEIPT-B", held, cap, 1),
    )
    with pytest.raises(FrozenInstanceError):
        after.held_exposure_resolutions[0].held_nanos = 0
    assert sim.begin("SYNTH-RUN-A").state is ss.OperationState.READY


def test_held_breach_waits_for_all_relevant_liabilities_even_when_current_hold_fits() -> None:
    first = ss.SyntheticLiability(
        "SYNTH-LIABILITY-A", ss.SyntheticModel.OSS, ss.nanos("3"),
        independent_max_evidence_id="SYNTH-INDEPENDENT-A",
    )
    second = ss.SyntheticLiability(
        "SYNTH-LIABILITY-B", ss.SyntheticModel.OSS, ss.nanos("3"),
        independent_max_evidence_id="SYNTH-INDEPENDENT-B",
    )
    sim = simulation(runs=(run(cap=ss.nanos("1")),), liabilities=(first, second))
    prior = sim.snapshot().budget_breaches
    assert sim.snapshot().model_held_nanos == ss.nanos("7")
    before = sim.snapshot()
    with pytest.raises(ss.SafetyRefusal, match="non-final"):
        sim.reconcile_liability(receipt(first.liability_id, "A", 0, final=False))
    assert sim.snapshot() == before
    sim.reconcile_liability(receipt(first.liability_id, "A", 0))
    pending = sim.snapshot()
    assert pending.model_held_nanos == ss.nanos("4")
    assert pending.active_held_breaches == (ss.BudgetScope.MODEL,)
    assert pending.held_exposure_resolutions == ()
    with pytest.raises(ss.SafetyRefusal, match="unknown"):
        sim.begin("SYNTH-RUN-A")
    sim.reconcile_liability(receipt(second.liability_id, "B", 0))
    after = sim.snapshot()
    assert after.active_held_breaches == ()
    assert after.budget_breaches == prior
    assert after.held_exposure_resolutions == (
        ss.SyntheticHeldExposureResolution(
            ss.BudgetScope.MODEL, "SYNTH-RECEIPT-B", ss.nanos("1"), ss.MODEL_CAP_NANOS, 0
        ),
    )


def test_model_held_resolution_can_be_audited_while_other_model_liability_remains() -> None:
    first = ss.SyntheticLiability(
        "SYNTH-LIABILITY-A", ss.SyntheticModel.OSS, ss.nanos("6"),
        independent_max_evidence_id="SYNTH-INDEPENDENT-A",
    )
    second = ss.SyntheticLiability("SYNTH-LIABILITY-B", ss.SyntheticModel.OTHER, None)
    sim = simulation(runs=(run(cap=ss.nanos("1")),), liabilities=(first, second))
    assert sim.snapshot().model_held_nanos == ss.nanos("7")
    assert sim.snapshot().study_held_nanos is None
    sim.reconcile_liability(receipt(first.liability_id, "A", 0))
    state = sim.snapshot()
    assert state.model_held_nanos == ss.nanos("1") and state.study_held_nanos is None
    assert state.held_exposure_resolutions == (
        ss.SyntheticHeldExposureResolution(
            ss.BudgetScope.MODEL, "SYNTH-RECEIPT-A", ss.nanos("1"), ss.MODEL_CAP_NANOS, 0
        ),
    )
    with pytest.raises(ss.SafetyRefusal, match="unknown"):
        sim.begin("SYNTH-RUN-A")


def test_nonrecoverable_bound_fault_conservatively_retains_held_only_block() -> None:
    value = spec()
    shared = ss.SyntheticLiability(
        "SYNTH-LIABILITY-A", ss.SyntheticModel.OSS, 10, physical_spec_hash=value.fingerprint
    )
    independent = ss.SyntheticLiability(
        "SYNTH-LIABILITY-B", ss.SyntheticModel.OSS, 10,
        independent_max_evidence_id="SYNTH-INDEPENDENT-B",
    )
    sim = simulation(
        value=value, runs=(run(cap=ss.MODEL_CAP_NANOS),), liabilities=(shared, independent)
    )
    sim.reconcile_liability(receipt(shared.liability_id, "A", 0, input_tokens=2))
    sim.reconcile_liability(receipt(independent.liability_id, "B", 0))
    state = sim.snapshot()
    assert state.model_held_nanos == ss.MODEL_CAP_NANOS
    assert state.shared_physical_bound_disproved
    assert ss.BudgetScope.MODEL in state.active_held_breaches
    assert state.held_exposure_resolutions == ()
    assert state.faults
    with pytest.raises(ss.SafetyRefusal, match="faulted"):
        sim.begin("SYNTH-RUN-A")


def test_disputed_three_dollar_booking_does_not_create_confirmed_overspend() -> None:
    bound = ss.SyntheticPhysicalBound(
        0, 0, 0, 0, ss.nanos("3"), ss.nanos("3"), "SYNTH-BOUND-A"
    )
    value = ss.SyntheticSpec(original(), bound)
    sim = simulation(value=value, runs=(run(cap=ss.MODEL_CAP_NANOS),))
    first, second = reserve(sim), reserve(sim)
    sim.dispatch(
        first.ticket_id,
        ss.SyntheticTransport((ss.SyntheticReply(ss.ReplyKind.ANSWER, ss.nanos("3")),)),
    )
    with pytest.raises(ss.SafetyRefusal, match="contradictory"):
        sim.reconcile_attempt(receipt(first.ticket_id, "A", 0))
    sim.interrupt(second.ticket_id)
    pending = sim.snapshot()
    assert pending.model_spent_nanos == ss.nanos("3")
    assert pending.model_disputed_booked_nanos == ss.nanos("3")
    assert pending.model_confirmed_spent_nanos == 0
    assert pending.unknown_count == 2
    sim.reconcile_attempt(receipt(second.ticket_id, "B", ss.nanos("3") + 1))
    state = sim.snapshot()
    assert state.model_spent_nanos == ss.nanos("6") + 1
    assert state.study_spent_nanos == ss.nanos("6") + 1
    assert state.model_disputed_booked_nanos == ss.nanos("3")
    assert state.study_disputed_booked_nanos == ss.nanos("3")
    assert state.model_confirmed_spent_nanos == ss.nanos("3") + 1
    assert state.study_confirmed_spent_nanos == ss.nanos("3") + 1
    assert not state.model_confirmed_spend_breach and not state.study_confirmed_spend_breach
    assert state.model_held_nanos is None and state.study_held_nanos is None
    assert state.indeterminate_charge_ticket_ids == (first.ticket_id,)
    assert state.later_run_cap_breaches == ()
    assert not any(
        breach.kind is ss.BudgetBreachKind.CONFIRMED_SPEND for breach in state.budget_breaches
    )
    assert sim.ticket(first.ticket_id).charge_nanos == ss.nanos("3")
    assert sim.ticket(second.ticket_id).charge_nanos == ss.nanos("3") + 1
    assert state.faults
    with pytest.raises(ss.SafetyRefusal, match="faulted"):
        sim.begin("SYNTH-RUN-A")


def test_confirmed_overspend_is_still_recorded_without_the_disputed_booking() -> None:
    bound = ss.SyntheticPhysicalBound(
        0, 0, 0, 0, ss.nanos("3"), ss.nanos("3"), "SYNTH-BOUND-A"
    )
    value = ss.SyntheticSpec(original(), bound)
    sim = simulation(value=value, runs=(run(cap=ss.MODEL_CAP_NANOS),))
    first, second = reserve(sim), reserve(sim)
    sim.dispatch(
        first.ticket_id,
        ss.SyntheticTransport((ss.SyntheticReply(ss.ReplyKind.ANSWER, ss.nanos("3")),)),
    )
    with pytest.raises(ss.SafetyRefusal, match="contradictory"):
        sim.reconcile_attempt(receipt(first.ticket_id, "A", 0))
    sim.interrupt(second.ticket_id)
    sim.reconcile_attempt(receipt(second.ticket_id, "B", ss.nanos("7")))
    state = sim.snapshot()
    assert state.model_spent_nanos == ss.nanos("10")
    assert state.model_disputed_booked_nanos == ss.nanos("3")
    assert state.model_confirmed_spent_nanos == ss.nanos("7")
    assert state.model_confirmed_spend_breach
    assert ss.SyntheticBudgetBreach(
        ss.BudgetScope.MODEL,
        ss.BudgetBreachKind.CONFIRMED_SPEND,
        ss.nanos("7"),
        ss.MODEL_CAP_NANOS,
        "SYNTH-RECEIPT-B",
    ) in state.budget_breaches
    assert state.later_run_cap_breaches == (
        ss.SyntheticRunCapBreach(
            "SYNTH-RUN-A", ss.SyntheticModel.OSS, ss.nanos("7"), ss.MODEL_CAP_NANOS,
            second.ticket_id,
        ),
    )
    assert state.contested_budget_breaches == ()
    assert state.contested_later_run_cap_breaches == ()
    assert state.model_held_nanos is None and state.faults


def test_later_dispute_qualifies_but_does_not_erase_historical_breach_observations() -> None:
    bound = ss.SyntheticPhysicalBound(
        0, 0, 0, 0, ss.nanos("3"), ss.nanos("3"), "SYNTH-BOUND-A"
    )
    value = ss.SyntheticSpec(original(), bound)
    sim = simulation(value=value, runs=(run(cap=ss.MODEL_CAP_NANOS),))
    first, second = reserve(sim), reserve(sim)
    sim.dispatch(
        first.ticket_id,
        ss.SyntheticTransport((ss.SyntheticReply(ss.ReplyKind.ANSWER, ss.nanos("3")),)),
    )
    sim.dispatch(
        second.ticket_id,
        ss.SyntheticTransport((ss.SyntheticReply(ss.ReplyKind.ANSWER, ss.nanos("3") + 1),)),
    )
    before = sim.snapshot()
    assert before.model_confirmed_spend_breach
    confirmed = next(
        breach for breach in before.budget_breaches
        if breach.scope is ss.BudgetScope.MODEL
        and breach.kind is ss.BudgetBreachKind.CONFIRMED_SPEND
    )
    run_breach = before.later_run_cap_breaches[0]
    with pytest.raises(ss.SafetyRefusal, match="contradictory"):
        sim.reconcile_attempt(receipt(first.ticket_id, "A", 0))
    after = sim.snapshot()
    assert after.model_spent_nanos == ss.nanos("6") + 1
    assert after.model_confirmed_spent_nanos == ss.nanos("3") + 1
    assert not after.model_confirmed_spend_breach
    assert confirmed in after.budget_breaches
    assert after.contested_budget_breaches == (
        ss.SyntheticContestedBudgetBreach(confirmed, (first.ticket_id,)),
    )
    assert run_breach in after.later_run_cap_breaches
    assert after.contested_later_run_cap_breaches == (
        ss.SyntheticContestedRunCapBreach(run_breach, (first.ticket_id,)),
    )
    assert after.model_held_nanos is None and after.faults
    with pytest.raises(ss.SafetyRefusal, match="faulted"):
        sim.begin("SYNTH-RUN-A")


def test_multiple_conflicts_exclude_one_booked_charge_only_once() -> None:
    bound = ss.SyntheticPhysicalBound(
        0, 0, 0, 0, ss.nanos("3"), ss.nanos("3"), "SYNTH-BOUND-A"
    )
    value = ss.SyntheticSpec(original(), bound)
    sim = simulation(value=value, runs=(run(cap=ss.MODEL_CAP_NANOS),))
    first = reserve(sim)
    sim.dispatch(
        first.ticket_id,
        ss.SyntheticTransport((ss.SyntheticReply(ss.ReplyKind.ANSWER, ss.nanos("3")),)),
    )
    for suffix, claimed in (("A", 0), ("B", ss.nanos("1"))):
        with pytest.raises(ss.SafetyRefusal, match="contradictory"):
            sim.reconcile_attempt(receipt(first.ticket_id, suffix, claimed))
    state = sim.snapshot()
    assert state.model_spent_nanos == ss.nanos("3")
    assert state.model_disputed_booked_nanos == ss.nanos("3")
    assert state.model_confirmed_spent_nanos == 0
    assert len(state.charge_conflicts) == 2
    assert state.unknown_count == 1
    assert state.model_held_nanos is None and state.faults


def test_study_confirmed_spend_also_excludes_the_disputed_booking() -> None:
    bound = ss.SyntheticPhysicalBound(
        0, 0, 0, 0, ss.nanos("3"), ss.nanos("3"), "SYNTH-BOUND-A"
    )
    value = ss.SyntheticSpec(original(), bound)
    sim = simulation(
        value=value,
        runs=(
            run("A", cap=ss.MODEL_CAP_NANOS),
            run("B", model=ss.SyntheticModel.OTHER, spent=ss.nanos("194"), cap=None),
        ),
    )
    first, second = reserve(sim), reserve(sim)
    sim.dispatch(
        first.ticket_id,
        ss.SyntheticTransport((ss.SyntheticReply(ss.ReplyKind.ANSWER, ss.nanos("3")),)),
    )
    with pytest.raises(ss.SafetyRefusal, match="contradictory"):
        sim.reconcile_attempt(receipt(first.ticket_id, "A", 0))
    sim.interrupt(second.ticket_id)
    sim.reconcile_attempt(receipt(second.ticket_id, "B", ss.nanos("3") + 1))
    state = sim.snapshot()
    assert state.study_spent_nanos == ss.nanos("200") + 1
    assert state.study_disputed_booked_nanos == ss.nanos("3")
    assert state.study_confirmed_spent_nanos == ss.nanos("197") + 1
    assert not state.study_confirmed_spend_breach
    assert not any(
        breach.scope is ss.BudgetScope.STUDY
        and breach.kind is ss.BudgetBreachKind.CONFIRMED_SPEND
        for breach in state.budget_breaches
    )
    assert state.study_held_nanos is None and state.faults
