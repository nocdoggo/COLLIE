"""Independent exhaustive oracle for short arrival histories."""

from __future__ import annotations

import inspect
import itertools

import pytest

from collie.verify.arrival import (
    ArrivalForwardFilter,
    ArrivalModel,
    RegisteredArrivalLaw,
    brute_force_sequence_probability,
)


def test_bruteforce_oracle_shares_no_production_transition_primitive() -> None:
    source = inspect.getsource(brute_force_sequence_probability)
    assert "transition_state(" not in source
    assert "advance_counter(" not in source


@pytest.mark.parametrize("dispatches", [(2.0, 3.0), (2.0, 3.0, 5.0)])
def test_brute_force_agrees_with_recursion(dispatches: tuple[float, ...]) -> None:
    law = RegisteredArrivalLaw(
        finite_delay_probabilities=(0.20, 0.45, 0.25),
        loss_probability=0.10,
        pause_probability=0.20,
        name="enumeration_oracle",
    )
    # Every aggregate receipt is a subset sum of dispatched cohorts.  The alphabet includes all of
    # them (plus impossible time orderings in the Cartesian product), so no multi-cohort emission is
    # silently omitted from the exhaustive comparison.
    receipt_alphabet = tuple(
        sorted(
            {
                sum(dispatches[index] for index in range(len(dispatches)) if mask & (1 << index))
                for mask in range(1 << len(dispatches))
            }
        )
    )
    for receipts in itertools.product(receipt_alphabet, repeat=len(dispatches)):
        forward = ArrivalForwardFilter(ArrivalModel(law))
        recursion_probability = 1.0
        try:
            for period, (dispatch, receipt) in enumerate(
                zip(dispatches, receipts, strict=True), start=1
            ):
                recursion_probability *= forward.step(
                    period=period, dispatch_quantity=dispatch, receipt=receipt
                )
        except ValueError as exc:
            assert "impossible" in str(exc)
            recursion_probability = 0.0
        exhaustive_probability = brute_force_sequence_probability(law, dispatches, receipts)
        assert recursion_probability == pytest.approx(exhaustive_probability, abs=1e-12)
