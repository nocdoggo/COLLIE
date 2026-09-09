"""Module 04, Checkpoint 2 — the imputed FIFO ledger.

Every input here is one of the two aggregate scalars a controller already legitimately has: its
own dispatched order quantities, and observed aggregate receipts. See
``tests/test_ledger_not_evidence.py`` for the isolation half of this deliverable.
"""

from __future__ import annotations

from collie.contracts import ControlConfig, PeriodObservation
from collie.control.controller import OrCompilerController
from collie.control.grid import BASELINE_CONFIG
from collie.control.ledger import AgedUnits, FIFOLedger


def test_fifo_assignment_correctness() -> None:
    """Hand-worked sequence: order 10 at t1, order 5 at t2, receive 12 at t3 should consume all
    10 units of the t1 cohort (age 2) and 2 units of the t2 cohort (age 1), leaving 3 outstanding."""
    ledger = FIFOLedger()
    ledger.record_order(1, 10.0)
    ledger.record_order(2, 5.0)
    ledger.record_receipt(3, 12.0)

    aged = ledger.aged_mass()
    assert aged == (
        AgedUnits(age=2, quantity=10.0, imputed=True),
        AgedUnits(age=1, quantity=2.0, imputed=True),
    )
    assert ledger.outstanding_total == 3.0
    assert ledger.inconsistencies == ()


def test_fifo_assignment_across_multiple_receipts() -> None:
    ledger = FIFOLedger()
    ledger.record_order(1, 20.0)
    ledger.record_receipt(3, 8.0)
    ledger.record_receipt(5, 12.0)
    aged = ledger.aged_mass()
    assert aged == (
        AgedUnits(age=2, quantity=8.0, imputed=True),
        AgedUnits(age=4, quantity=12.0, imputed=True),
    )
    assert ledger.outstanding_total == 0.0


def test_zero_and_negative_orders_do_not_open_a_cohort() -> None:
    ledger = FIFOLedger()
    ledger.record_order(1, 0.0)
    ledger.record_order(2, -5.0)
    assert ledger.outstanding_total == 0.0
    ledger.record_receipt(3, 1.0)
    assert len(ledger.inconsistencies) == 1


def test_inconsistency_is_recorded_not_rebalanced() -> None:
    """A receipt bigger than every outstanding order is left unexplained, not smeared across
    existing cohorts or silently dropped. The books stay unbalanced; the event is logged."""
    ledger = FIFOLedger()
    ledger.record_order(1, 10.0)
    ledger.record_receipt(2, 15.0)

    assert ledger.outstanding_total == 0.0
    assert len(ledger.inconsistencies) == 1
    inconsistency = ledger.inconsistencies[0]
    assert inconsistency.period == 2
    assert inconsistency.unexplained_quantity == 5.0
    # The 10 units that *were* explained are still recorded as aged mass; nothing was discarded
    # or redistributed to make the 5-unit gap disappear.
    assert ledger.aged_mass() == (AgedUnits(age=1, quantity=10.0, imputed=True),)


def test_multiple_inconsistencies_accumulate() -> None:
    ledger = FIFOLedger()
    ledger.record_receipt(1, 5.0)
    ledger.record_receipt(2, 3.0)
    assert [i.unexplained_quantity for i in ledger.inconsistencies] == [5.0, 3.0]


def test_aged_mass_carries_imputation_marker() -> None:
    ledger = FIFOLedger()
    ledger.record_order(1, 4.0)
    ledger.record_receipt(2, 4.0)
    assert all(unit.imputed is True for unit in ledger.aged_mass())


def test_ledger_never_reads_forbidden_inputs() -> None:
    """The ledger's only two entry points take a period and a quantity. There is no import, no
    file access, and no reference to hidden state anywhere in the *code* of this module (the
    module docstring is prose explaining the boundary and legitimately names the forbidden
    inputs, so docstring nodes are excluded rather than grepping raw text)."""
    import ast
    import inspect

    from collie.control import ledger as ledger_module

    tree = ast.parse(inspect.getsource(ledger_module))
    forbidden_names = {"HiddenIncident", "HiddenAlertSpec", "SupplyRealization"}
    forbidden_literals = ("supply.csv", "incident.json")

    docstring_ids: set[int] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
            and node.body
        ):
            first = node.body[0]
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                docstring_ids.add(id(first.value))

    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            assert node.id not in forbidden_names, f"{node.id} referenced at line {node.lineno}"
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstring_ids
        ):
            for lit in forbidden_literals:
                assert lit not in node.value, (
                    f"{lit!r} in a non-docstring string at line {node.lineno}"
                )

    public_methods = {name for name in dir(FIFOLedger) if not name.startswith("_")}
    assert public_methods <= {
        "record_order",
        "record_receipt",
        "inconsistencies",
        "outstanding_total",
        "aged_mass",
    }


# ---------------------------------------------------------------------------
# the ablation flag
# ---------------------------------------------------------------------------


def _run_three_periods(controller: OrCompilerController) -> None:
    controller.reset()
    controller.order(
        PeriodObservation(
            period=1,
            date="t1",
            on_hand=0.0,
            in_transit_total=0.0,
            prev_order=0.0,
            prev_arrivals=0.0,
            profit_per_unit=4.0,
            holding_cost_per_unit=1.0,
            promised_lead_time=2,
            prev_demand=None,
        )
    )
    controller.order(
        PeriodObservation(
            period=2,
            date="t2",
            on_hand=0.0,
            in_transit_total=50.0,
            prev_order=50.0,
            prev_arrivals=0.0,
            profit_per_unit=4.0,
            holding_cost_per_unit=1.0,
            promised_lead_time=2,
            prev_demand=90.0,
        )
    )
    controller.order(
        PeriodObservation(
            period=3,
            date="t3",
            on_hand=0.0,
            in_transit_total=50.0,
            prev_order=0.0,
            prev_arrivals=50.0,
            profit_per_unit=4.0,
            holding_cost_per_unit=1.0,
            promised_lead_time=2,
            prev_demand=100.0,
        )
    )


def test_age_binned_telemetry_available_to_all_arms() -> None:
    """The ledger hook on ``OrCompilerController`` is a plain constructor argument, not a branch
    on ``arm_id``. Two controllers with different arm ids, each given its own ledger, record
    identically -- the flag is available to whichever arm asks for it, never to one arm alone."""
    config = ControlConfig(m=1.0, l_eff=2, gamma=1.0, predictive_model="probe")
    detector_ledger = FIFOLedger()
    shockspec_ledger = FIFOLedger()

    detector = OrCompilerController(
        order_cap=1000.0, config=config, arm_id="detector_control", ledger=detector_ledger
    )
    shockspec = OrCompilerController(
        order_cap=1000.0, config=config, arm_id="shockspec_arm", ledger=shockspec_ledger
    )

    _run_three_periods(detector)
    _run_three_periods(shockspec)

    assert detector_ledger.aged_mass() == shockspec_ledger.aged_mass()
    assert detector_ledger.inconsistencies == shockspec_ledger.inconsistencies


def test_age_binned_telemetry_is_off_by_default() -> None:
    ctrl = OrCompilerController(order_cap=1000.0, config=BASELINE_CONFIG)
    assert ctrl.ledger is None
