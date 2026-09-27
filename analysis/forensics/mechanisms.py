"""Mechanism checks behind the per-family headroom verdicts. Exploratory.

Run: ``uv run python -m analysis.forensics.mechanisms``.

Each check turns one sentence of the report into a number read from the frozen code path:

* **demand_up double counting.** ``OrCompilerController`` builds its target from
  ``m * (1 + l_eff) * mean`` where ``mean`` is the *running* mean of train plus every observed
  demand. After a level shift the running mean itself climbs toward the new level, so a fixed
  compiled ``m`` multiplies a level that already contains part of the shift.
* **pulse reachability.** How many pulse periods an order placed at onset can still reach, read
  from the frozen supply physics (not from the lead-time parameter).
* **compound pause.** Which order periods can land during the pause or the demand window.
* **lead-time-shift under-correction.** The oracle's compiled lead-time offset against the true
  shift ``disrupted - baseline``.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np

from analysis.forensics.common import (
    FAMILY_KEY,
    ORACLE,
    load_raw,
    parse_episode_id,
    periods_by,
    write_json,
)
from analysis.forensics.harness import pilot_contexts
from analysis.forensics.q1_clairvoyant import arrival_map


def main() -> None:
    raw = load_raw()
    stored = periods_by(raw, [ORACLE])
    out: dict[str, list] = {key: [] for key in FAMILY_KEY.values()}
    with tempfile.TemporaryDirectory() as tmp:
        seen = set()
        for ctx in pilot_contexts(Path(tmp)):
            inc = ctx.instance.incident
            if inc is None:
                continue
            meta = parse_episode_id(ctx.episode_id)
            if meta["cluster"] in seen:
                continue
            seen.add(meta["cluster"])
            key = FAMILY_KEY[int(meta["fam"])]
            onset = inc.onset_period
            spec = ctx.instance.spec
            landing = arrival_map(ctx.instance)
            demand = list(ctx.instance.demand)
            train = list(spec.train_demand)
            oracle = stored[(ctx.episode_id, ORACLE)]
            cfg = next(r["control_config"] for r in oracle if r["active_spec_id"])
            row: dict[str, object] = {
                "cluster": meta["cluster"],
                "onset": onset,
                "promised_lead_time": spec.promised_lead_time,
                "compiled": cfg,
            }
            if key.startswith("demand_level"):
                # Implied belief about the current demand level, relative to the true level.
                true_level = 100.0 * inc.magnitude  # the registered stationary-IID mean is 100
                ratios = {}
                for offset in (0, 10, 20, spec.horizon - onset):
                    t = onset + offset
                    running = float(np.mean(train + demand[: t - 1]))
                    ratios[str(offset)] = cfg["m"] * running / true_level
                row["implied_over_true_level"] = ratios
            if key == "temporary_pulse":
                lands = landing[onset - 1]
                pulse = range(onset, onset + inc.duration)
                row["pulse_periods"] = [pulse.start, pulse.stop - 1]
                row["order_at_onset_lands"] = lands
                row["pulse_periods_reachable_from_onset"] = sum(
                    1 for t in pulse if lands is not None and t >= lands
                )
                row["pulse_periods_reachable_from_onset_minus_1"] = sum(
                    1 for t in pulse if landing[onset - 2] is not None and t >= landing[onset - 2]
                )
            if key == "compound":
                effect = inc.supply_effect
                pause = [effect.start_period, effect.start_period + effect.length - 1]
                row["pause_periods"] = pause
                row["demand_window"] = [onset, onset + inc.duration - 1]
                row["landing_of_order_placed_at"] = {
                    str(d): landing[onset - 1 + d] for d in (-3, -2, -1, 0, 1)
                }
                row["arm1_on_hand_at_onset"] = next(
                    r["on_hand_start"] for r in oracle if r["period"] == onset
                )
            if key == "lead_time_shift":
                effect = inc.supply_effect
                row["true_shift"] = effect.disrupted_lead_time - spec.promised_lead_time
                row["compiled_offset"] = cfg["l_eff"] - spec.promised_lead_time
            if key == "shipment_loss":
                effect = inc.supply_effect
                window = range(onset, onset + effect.length)
                row["loss_periods"] = [window.start, window.stop - 1]
                row["window_orders_that_land"] = sum(
                    1 for t in window if landing[t - 1] is not None
                )
                row["first_order_after_burst_lands"] = landing[window.stop - 1]
            out[key].append(row)
    path = write_json("mechanisms.json", {"per_family": out})
    print(json.dumps(out, indent=2, default=float))
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
