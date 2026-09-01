"""Instance enumeration and stratification over the official benchmark tree.

Layout, as shipped (``docs/env_contract.md`` §1)::

    benchmark/real_trajectory/<lead_time>/<article_id>/
    benchmark/synthetic_trajectory/<lead_time>/<pattern>/<variant>/<r{1,2}_{low,med,high}>/

Two strata matter for the Task 4 equivalence argument, because they are the two axes the
accounting is sensitive to:

**Lead-time label** — ``lead_time_0``, ``lead_time_4``, ``lead_time_stochastic``. Only the
stochastic third contains ``lead_time = inf``, i.e. lost shipments, so it is the only label that
exercises the drop path at all. Equivalence tested on the deterministic labels alone would prove
nothing about the case most likely to diverge.

**Cost ratio** — holding cost is ``1.0`` in every one of the 1,320 instances and profit takes
exactly three values, so the ratio is a three-valued label with no binning required:

======  ===============  ==============
label   profit per unit  holding/profit
======  ===============  ==============
high    19.0             1/19
med     4.0              1/4
low     1.0              1
======  ===============  ==============

The label names refer to the **margin**, not to the holding burden: ``low`` is the punishing case
where every unit held costs a full unit of profit. Any table axis built from these labels has to
say so, or it reads backwards.

Sampling is by even stride over a sorted cell rather than by RNG. It is reproducible without
depending on the stability of any random implementation, and it spreads the selection across
demand patterns and articles instead of clustering on whichever ones sort first.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from collie.adapter.inventorybench import benchmark_root

__all__ = [
    "COST_RATIO_BY_PROFIT",
    "LEAD_TIME_LABELS",
    "TRAJECTORIES",
    "InstanceKey",
    "cost_ratio_label",
    "enumerate_instances",
    "stratified_sample",
    "stratify",
]

TRAJECTORIES = ("real_trajectory", "synthetic_trajectory")
LEAD_TIME_LABELS = ("lead_time_0", "lead_time_4", "lead_time_stochastic")

COST_RATIO_BY_PROFIT: dict[float, str] = {19.0: "high", 4.0: "med", 1.0: "low"}
"""Audited: holding cost is 1.0 everywhere and profit is one of these three values."""


@dataclass(frozen=True, slots=True, order=True)
class InstanceKey:
    """Identity and strata of one instance. ``relpath`` is the stable identifier we commit."""

    relpath: str
    trajectory: str
    lead_time_label: str
    cost_ratio_label: str
    profit_per_unit: float
    holding_cost_per_unit: float
    horizon: int
    item_id: str

    @property
    def cell(self) -> tuple[str, str, str]:
        return (self.trajectory, self.lead_time_label, self.cost_ratio_label)

    def path(self, root: Path | None = None) -> Path:
        return (root or benchmark_root()) / self.relpath


def cost_ratio_label(profit_per_unit: float) -> str:
    """Map profit to its stratum label, refusing to guess for an unaudited value."""
    try:
        return COST_RATIO_BY_PROFIT[float(profit_per_unit)]
    except KeyError:
        raise ValueError(
            f"profit_per_unit={profit_per_unit!r} is not one of the audited values "
            f"{sorted(COST_RATIO_BY_PROFIT)}. If the benchmark pin moved, re-run `make audit` "
            "and update COST_RATIO_BY_PROFIT deliberately rather than binning by distance."
        ) from None


def _lead_time_label(relpath: str) -> str:
    parts = relpath.split("/")
    for label in LEAD_TIME_LABELS:
        if label in parts:
            return label
    raise ValueError(f"no lead-time label in {relpath!r}; expected one of {LEAD_TIME_LABELS}")


def _read_header_economics(test_csv: Path) -> tuple[str, float, float, int]:
    """Return ``(item_id, profit, holding, horizon)`` from the first data row.

    Reads with :mod:`csv` rather than pandas: this runs over 1,320 files and only needs the
    first row plus a row count.
    """
    with test_csv.open(newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        header = next(reader)
        rows = list(reader)
    if not rows:
        raise ValueError(f"{test_csv} has a header but no data rows")
    idx = {name.strip().strip('"'): i for i, name in enumerate(header)}
    item_id = next(
        (col[len("demand_") :] for col in idx if col.startswith("demand_")),
        None,
    )
    if item_id is None:
        raise ValueError(f"no demand_* column in {test_csv}")
    profit = float(rows[0][idx[f"profit_{item_id}"]])
    holding = float(rows[0][idx[f"holding_cost_{item_id}"]])
    return item_id, profit, holding, len(rows)


def enumerate_instances(root: Path | None = None) -> tuple[InstanceKey, ...]:
    """Enumerate every instance under ``benchmark/``, sorted by ``relpath``.

    Sorted so that any downstream selection is reproducible without a second sort.
    """
    base = root or benchmark_root()
    keys: list[InstanceKey] = []
    for test_csv in sorted(base.rglob("test.csv")):
        instance_dir = test_csv.parent
        relpath = instance_dir.relative_to(base).as_posix()
        item_id, profit, holding, horizon = _read_header_economics(test_csv)
        keys.append(
            InstanceKey(
                relpath=relpath,
                trajectory=relpath.split("/")[0],
                lead_time_label=_lead_time_label(relpath),
                cost_ratio_label=cost_ratio_label(profit),
                profit_per_unit=profit,
                holding_cost_per_unit=holding,
                horizon=horizon,
                item_id=item_id,
            )
        )
    return tuple(sorted(keys))


def stratify(keys: tuple[InstanceKey, ...]) -> dict[tuple[str, str, str], tuple[InstanceKey, ...]]:
    """Group instances into ``(trajectory, lead_time_label, cost_ratio_label)`` cells."""
    cells: dict[tuple[str, str, str], list[InstanceKey]] = {}
    for key in keys:
        cells.setdefault(key.cell, []).append(key)
    return {cell: tuple(sorted(items)) for cell, items in sorted(cells.items())}


def _even_stride(items: tuple[InstanceKey, ...], count: int) -> tuple[InstanceKey, ...]:
    if count >= len(items):
        return items
    # Positions spread across the whole cell; ints are distinct because count <= len(items).
    return tuple(items[(i * len(items)) // count] for i in range(count))


def stratified_sample(
    keys: tuple[InstanceKey, ...],
    *,
    per_cell: int,
) -> tuple[InstanceKey, ...]:
    """Take ``per_cell`` instances from each of the 18 strata by even stride.

    A cell smaller than ``per_cell`` contributes all of its members rather than failing, so the
    caller decides whether the resulting total is large enough.
    """
    if per_cell < 1:
        raise ValueError(f"per_cell must be >= 1, got {per_cell}")
    selected: list[InstanceKey] = []
    for cell_keys in stratify(keys).values():
        selected.extend(_even_stride(cell_keys, per_cell))
    return tuple(sorted(selected))
