"""Instance loading for the extended instance format.

An instance directory is the official InventoryBench layout plus two optional project-owned
files::

    <instance>/
      train.csv        official: historical demand samples
      test.csv         official: exact_dates_<id>, demand_<id>, [description_<id>,]
                                 lead_time_<id>, profit_<id>, holding_cost_<id>
      supply.csv       PROJECT-OWNED, optional: period, lead_time, pause_active
      incident.json    PROJECT-OWNED, optional: hidden truth

When the sidecar is absent the supply path is read from `test.csv`'s own `lead_time` column, so
official instances load unchanged. That is what makes the neutral-sidecar equivalence argument in
Task 4 possible.

Per `docs/env_contract.md` §7, only transit pause needs `supply.csv`; lead-time shifts and lost
shipments are natively expressible in `test.csv`.
"""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path

from collie.contracts import (
    EpisodeSpec,
    HiddenIncident,
    ObservationMode,
    ShockFamily,
    Split,
    SupplyEffect,
    SupplyEffectKind,
    SupplyRealization,
)

__all__ = ["LoadedInstance", "load_instance", "promised_lead_time_for"]

# Mirrors eval/run_baseline_policy.py::detect_promised_lead_time, audited in Task 2 and recorded
# in manifests/benchmark_v1.json. Kept here so the loader has no dependency on the submodule.
_PROMISED_BY_DIR = {"lead_time_0": 0, "lead_time_4": 4, "lead_time_stochastic": 2}


@dataclass(frozen=True, slots=True)
class LoadedInstance:
    """Everything an episode needs, with hidden truth kept in a separate attribute."""

    spec: EpisodeSpec
    demand: tuple[float, ...]
    supply: SupplyRealization
    profits: tuple[float, ...]
    holding_costs: tuple[float, ...]
    dates: tuple[str, ...]
    incident: HiddenIncident | None = None
    """Hidden. The runner passes this to the evaluator and to the oracle arm, never to a policy."""


def promised_lead_time_for(path: Path) -> int:
    """Derive the promised lead time from the instance path, as upstream does."""
    parts = {p for p in path.parts}
    for key, value in _PROMISED_BY_DIR.items():
        if key in parts:
            return value
    raise ValueError(
        f"cannot derive promised lead time from {path}; expected one of {sorted(_PROMISED_BY_DIR)} "
        "in the path, or pass promised_lead_time explicitly"
    )


def _read_rows(path: Path) -> tuple[list[str], list[list[str]]]:
    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    if not rows:
        raise ValueError(f"{path} is empty")
    return rows[0], rows[1:]


def _item_id(header: list[str]) -> str:
    for col in header:
        if col.startswith("demand_"):
            return col[len("demand_") :]
    raise ValueError(f"no demand_* column in {header}")


def _f(raw: str) -> float:
    """Parse a cell, treating the benchmark's `inf` spelling as a lost shipment."""
    token = raw.strip().strip('"')
    if token.lower() in {"inf", "+inf", "infinity"}:
        return math.inf
    return float(token)


def _load_supply_sidecar(path: Path, horizon: int) -> tuple[tuple[float, ...], tuple[bool, ...]]:
    header, rows = _read_rows(path)
    idx = {name.strip(): i for i, name in enumerate(header)}
    if "period" not in idx:
        raise ValueError(f"{path}: supply.csv requires a `period` column")
    lead: dict[int, float] = {}
    pause: dict[int, bool] = {}
    for row in rows:
        period = int(row[idx["period"]])
        if "lead_time" in idx:
            lead[period] = _f(row[idx["lead_time"]])
        if "pause_active" in idx:
            pause[period] = row[idx["pause_active"]].strip().lower() in {"1", "true", "yes"}
    if len(lead) not in (0, horizon) or len(pause) not in (0, horizon):
        raise ValueError(
            f"{path}: supply.csv must cover every period 1..{horizon} for any column it declares"
        )
    lead_times = tuple(lead[t] for t in range(1, horizon + 1)) if lead else ()
    pause_active = tuple(pause[t] for t in range(1, horizon + 1)) if pause else ()
    return lead_times, pause_active


def _load_incident(path: Path) -> HiddenIncident:
    raw = json.loads(path.read_text(encoding="utf-8"))
    effect = None
    if raw.get("supply_effect"):
        se = raw["supply_effect"]
        effect = SupplyEffect(
            kind=SupplyEffectKind(se["kind"]),
            start_period=int(se["start_period"]),
            length=int(se["length"]),
            disrupted_lead_time=se.get("disrupted_lead_time"),
        )
    return HiddenIncident(
        family=ShockFamily(raw["family"]),
        onset_period=int(raw["onset_period"]),
        magnitude=float(raw["magnitude"]),
        duration=int(raw["duration"]),
        conditional_independence=bool(raw["conditional_independence"]),
        supply_effect=effect,
        baseline_twin_id=raw.get("baseline_twin_id"),
        seed=raw.get("seed"),
        held_out_combo=bool(raw.get("held_out_combo", False)),
    )


def load_instance(
    instance_dir: Path | str,
    *,
    episode_id: str | None = None,
    promised_lead_time: int | None = None,
    order_cap: float = math.inf,
    observation_mode: ObservationMode = ObservationMode.UNCENSORED,
    split: Split | None = None,
) -> LoadedInstance:
    """Load one instance directory.

    ``order_cap`` defaults to ``inf`` because the benchmark imposes no cap
    (``docs/env_contract.md`` §2.3). An unbounded default is what lets the equivalence suite
    compare against the official pipeline; experiments pass the registered finite cap explicitly.

    ``episode_id`` should be the path relative to ``benchmark/``, which is the only identifier
    that is unique across the tree: every synthetic instance's own directory is named for its
    cost ratio, so 120 of them are called ``r1_med``. It falls back to the directory name for
    standalone use, where uniqueness is the caller's problem.
    """
    d = Path(instance_dir)
    test_header, test_rows = _read_rows(d / "test.csv")
    item_id = _item_id(test_header)
    idx = {name.strip().strip('"'): i for i, name in enumerate(test_header)}

    horizon = len(test_rows)
    demand = tuple(_f(r[idx[f"demand_{item_id}"]]) for r in test_rows)
    profits = tuple(_f(r[idx[f"profit_{item_id}"]]) for r in test_rows)
    holding = tuple(_f(r[idx[f"holding_cost_{item_id}"]]) for r in test_rows)
    dates = tuple(r[idx[f"exact_dates_{item_id}"]].strip().strip('"') for r in test_rows)
    csv_lead = tuple(_f(r[idx[f"lead_time_{item_id}"]]) for r in test_rows)

    desc_col = f"description_{item_id}"
    product_text = (
        test_rows[0][idx[desc_col]].strip().strip('"') if desc_col in idx and test_rows else None
    )

    train_demand: tuple[float, ...] = ()
    train_path = d / "train.csv"
    if train_path.is_file():
        train_header, train_rows = _read_rows(train_path)
        t_idx = {name.strip().strip('"'): i for i, name in enumerate(train_header)}
        col = t_idx.get(f"demand_{item_id}")
        if col is not None:
            train_demand = tuple(_f(r[col]) for r in train_rows)

    # Sidecar overrides only what it declares; anything else falls back to test.csv.
    lead_times, pause_active = csv_lead, ()
    supply_path = d / "supply.csv"
    if supply_path.is_file():
        side_lead, side_pause = _load_supply_sidecar(supply_path, horizon)
        if side_lead:
            lead_times = side_lead
        pause_active = side_pause

    incident_path = d / "incident.json"
    incident = _load_incident(incident_path) if incident_path.is_file() else None

    if promised_lead_time is None:
        promised_lead_time = promised_lead_time_for(d)

    spec = EpisodeSpec(
        episode_id=episode_id if episode_id is not None else d.name,
        item_id=item_id,
        horizon=horizon,
        promised_lead_time=promised_lead_time,
        profit_per_unit=profits[0],
        holding_cost_per_unit=holding[0],
        order_cap=order_cap,
        observation_mode=observation_mode,
        product_text=product_text,
        split=split,
        family=incident.family if incident else None,
        source="official" if incident is None else "collie-shockspec",
        train_demand=train_demand,
    )
    return LoadedInstance(
        spec=spec,
        demand=demand,
        supply=SupplyRealization(lead_times=lead_times, pause_active=pause_active),
        profits=profits,
        holding_costs=holding,
        dates=dates,
        incident=incident,
    )
