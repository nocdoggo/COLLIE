"""Instance directory writer (Task 6.3): official InventoryBench format plus sidecars.

Writes the exact layout the frozen loader parses (``collie/sim/loader.py``)::

    <relpath>/        train.csv, test.csv, [supply.csv], incident.json   (shocked)
    <relpath>__twin/  train.csv, test.csv                                 (unshocked twin)

Three disciplines are enforced here rather than by convention:

- **Integer cells.** Every demand / profit / holding / finite lead-time cell is written as an
  integer (env contract §8.1). A non-integer finite value raises rather than being formatted,
  because a fractional cell would break the exact-accounting argument downstream.
- **No hidden truth in observable files.** ``test.csv`` carries only the five official columns.
  The incident lives in ``incident.json`` alone; ``baseline_twin_id`` is stamped onto the
  incident here, at write time, because the generator cannot know where the twin will live.
- **Byte stability.** Fixed column order, LF endings, ``json.dumps(..., sort_keys=True)`` with a
  trailing newline — the same recipe as ``tools/audit_benchmark.py``.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from collie.data.families.base import GeneratedEpisode

__all__ = ["DEFAULT_ITEM_ID", "write_pair"]

DEFAULT_ITEM_ID = "chips(Regular)"
"""The official synthetic item id. Carrying it keeps generated instances format-identical to the
official tree; it names nothing about the family, the onset, or the seed."""

TWIN_SUFFIX = "__twin"


def _fmt_cell(value: float) -> str:
    """Format one cell. ``inf`` is the benchmark's own spelling of a lost shipment."""
    if math.isinf(value):
        return "inf"
    if value != int(value):
        raise ValueError(
            f"refusing to write non-integer cell {value}: the integer-cell invariant "
            "(env contract §8.1) is what keeps the accounting exact"
        )
    return str(int(value))


def _write_csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    lines = [",".join(header)]
    lines.extend(",".join(row) for row in rows)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_test_csv(
    path: Path,
    *,
    item_id: str,
    demand: tuple[float, ...],
    lead_times: tuple[float, ...],
    profit: float,
    holding: float,
) -> None:
    horizon = len(demand)
    if len(lead_times) != horizon:
        raise ValueError(f"lead_times has {len(lead_times)} entries but demand has {horizon}")
    header = [
        f"exact_dates_{item_id}",
        f"demand_{item_id}",
        f"lead_time_{item_id}",
        f"profit_{item_id}",
        f"holding_cost_{item_id}",
    ]
    rows = [
        [
            f"Period_{t}",
            _fmt_cell(demand[t - 1]),
            _fmt_cell(lead_times[t - 1]),
            _fmt_cell(profit),
            _fmt_cell(holding),
        ]
        for t in range(1, horizon + 1)
    ]
    _write_csv(path, header, rows)


def _write_train_csv(path: Path, *, item_id: str, train: tuple[float, ...]) -> None:
    header = [f"exact_dates_{item_id}", f"demand_{item_id}"]
    rows = [[f"Period_{t}", _fmt_cell(v)] for t, v in enumerate(train, start=1)]
    _write_csv(path, header, rows)


def _write_supply_csv(path: Path, *, pause_active: tuple[bool, ...]) -> None:
    """The pause is the one thing ``test.csv`` cannot express (env contract §7). Lead times are
    deliberately *not* restated: they come from ``test.csv`` and restating them would only add a
    second source to keep neutral."""
    rows = [[str(t), "true" if p else "false"] for t, p in enumerate(pause_active, start=1)]
    _write_csv(path, ["period", "pause_active"], rows)


def _incident_payload(ep: GeneratedEpisode, twin_relpath: str, held_out_combo: bool) -> dict:
    incident = ep.incident
    effect = incident.supply_effect
    return {
        "family": str(incident.family),
        "onset_period": incident.onset_period,
        "magnitude": incident.magnitude,
        "duration": incident.duration,
        "conditional_independence": incident.conditional_independence,
        "supply_effect": (
            {
                "kind": str(effect.kind),
                "start_period": effect.start_period,
                "length": effect.length,
                "disrupted_lead_time": effect.disrupted_lead_time,
            }
            if effect is not None
            else None
        ),
        "baseline_twin_id": twin_relpath,
        "seed": incident.seed,
        "held_out_combo": held_out_combo,
    }


def write_pair(
    root: Path,
    ep: GeneratedEpisode,
    *,
    relpath: str,
    profit: float = 4.0,
    holding: float = 1.0,
    item_id: str = DEFAULT_ITEM_ID,
    held_out_combo: bool = False,
) -> Path:
    """Write the shocked instance and its unshocked twin under ``root``.

    Returns the shocked instance's directory. The twin shares the train file and every pre-onset
    draw; it carries no ``incident.json``, so it loads as an ordinary unshocked instance.
    """
    horizon = len(ep.demand)
    if len(ep.twin_demand) != horizon or len(ep.twin_lead_times) != horizon:
        raise ValueError("the twin must cover the same horizon as the episode")
    if ep.pause_active and len(ep.pause_active) != horizon:
        raise ValueError("pause_active must align with the horizon")

    twin_relpath = relpath + TWIN_SUFFIX
    twin_dir = root / twin_relpath
    twin_dir.mkdir(parents=True, exist_ok=True)
    _write_train_csv(twin_dir / "train.csv", item_id=item_id, train=ep.train_demand)
    _write_test_csv(
        twin_dir / "test.csv",
        item_id=item_id,
        demand=ep.twin_demand,
        lead_times=ep.twin_lead_times,
        profit=profit,
        holding=holding,
    )

    instance_dir = root / relpath
    instance_dir.mkdir(parents=True, exist_ok=True)
    _write_train_csv(instance_dir / "train.csv", item_id=item_id, train=ep.train_demand)
    _write_test_csv(
        instance_dir / "test.csv",
        item_id=item_id,
        demand=ep.demand,
        lead_times=ep.lead_times,
        profit=profit,
        holding=holding,
    )
    if ep.pause_active:
        _write_supply_csv(instance_dir / "supply.csv", pause_active=ep.pause_active)

    payload = _incident_payload(ep, twin_relpath, held_out_combo or ep.incident.held_out_combo)
    (instance_dir / "incident.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return instance_dir
