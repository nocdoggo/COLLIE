"""Task 6.3 / Task 8 — build COLLIE-ShockSpec instance directories and the manifest.

``--split dev --limit N`` writes instance pairs (shocked + twin) seed-index-major so every
family is covered before any family repeats: a limit cuts seeds, never families. Seeds come from
the frozen registry (``collie/data/splits.py``); the wave-3 provisional scheme is exactly the
registry's, so early outputs regenerate unchanged.

``--all --out manifests/shockspec_v1.json`` emits the manifest, byte-stable on regeneration
(``--check`` proves staleness without writing). Episode parameters in the manifest come from the
generator itself, so the manifest cannot drift from the data it names.

Promised lead time: generated paths carry no ``lead_time_*`` component, so the frozen loader
cannot derive one from the path. The manifest records ``promised_lead_time`` per rollout (the
twin's constant baseline lead time; research notes §6) and consumers pass it explicitly.

Usage::

    uv run python -m tools.build_shockspec --split dev --limit 18 --out /tmp/shockspec_dev
    uv run python -m tools.build_shockspec --all --out manifests/shockspec_v1.json
    uv run python -m tools.build_shockspec --all --check --out manifests/shockspec_v1.json
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterator
from pathlib import Path

from collie import BENCHMARK_COMMIT
from collie.contracts import Split, SupplyRealization
from collie.data.families import generate_episode
from collie.data.families.base import BaselineSpec, FamilyParams, GeneratedEpisode
from collie.data.nullbank import BANK_SIZE, FRAGILITY_SIZE, build_nullbank
from collie.data.splits import (
    FAMILIES,
    FAMILY_SHOCK,
    N_FALSE_ALERT_NULL,
    N_SILENT_NULL,
    SEEDS_PER_FAMILY,
    RolloutSlice,
    build_rollouts,
    build_units,
    combo_of_params,
    generate_ood_episode,
    seed_for,
)
from collie.data.writer import TWIN_SUFFIX, write_pair
from collie.sim.supply import LeadTimeSupply

REPO_ROOT = Path(__file__).resolve().parents[1]
HORIZON = 50  # official synthetic horizon (docs/env_contract.md §1)


def dev_episodes(limit: int) -> Iterator[tuple[int, int, int]]:
    """Yield ``(family, seed_index, seed)`` from the frozen dev pool."""
    emitted = 0
    for index in range(SEEDS_PER_FAMILY[Split.DEV]):
        for family in FAMILIES:
            if emitted >= limit:
                return
            yield family, index, seed_for(family, Split.DEV, index)
            emitted += 1


def render_comparison(ep: GeneratedEpisode) -> str:
    """Side-by-side of the shocked series against its twin with the onset marked, so the auditor
    can see the pre-onset paths coincide."""
    onset = ep.incident.onset_period
    lines = [
        f"family={ep.incident.family} onset={onset} magnitude={ep.incident.magnitude} "
        f"duration={ep.incident.duration} seed={ep.incident.seed}",
        f"{'period':>6} {'twin':>8} {'shocked':>8}  note",
    ]
    for t in range(1, len(ep.demand) + 1):
        twin, shocked = ep.twin_demand[t - 1], ep.demand[t - 1]
        note = ""
        if t == onset:
            note = "<- onset"
        elif t > onset and twin != shocked:
            note = "*"
        lines.append(f"{t:>6} {twin:>8.0f} {shocked:>8.0f}  {note}")
    return "\n".join(lines)


def render_arrival_comparison(seed: int = 1050000, horizon: int = 30) -> str:
    """Arrival timelines for shift vs loss vs pause on one order schedule (Checkpoint 2 demo):
    three visibly different supply behaviours driven from one seed."""
    orders = [float(10 + (t * 37) % 14) for t in range(1, horizon + 1)]
    panels: dict[str, tuple[GeneratedEpisode, list[float]]] = {}
    for name, family, kw in (
        ("shift 2->4", 4, {"baseline_lead_time": 2, "disrupted_lead_time": 4}),
        ("loss x3", 5, {"loss_length": 3}),
        ("pause x4", 6, {"pause_length": 4}),
    ):
        ep = generate_episode(
            seed=seed, horizon=horizon, params=FamilyParams(family, baseline=BaselineSpec(), **kw)
        )
        proc = LeadTimeSupply(
            SupplyRealization(lead_times=ep.lead_times, pause_active=ep.pause_active)
        )
        got: list[float] = []
        for t, q in enumerate(orders, start=1):
            proc.dispatch(t, q)
            got.append(proc.receive(t))
        panels[name] = (ep, got)

    names = list(panels)
    onset = panels[names[0]][0].incident.onset_period
    lines = [
        f"seed={seed}, one order schedule, all three supply shocks at onset={onset}",
        f"{'period':>6} {'order':>6}" + "".join(f" {n:>10}" for n in names),
    ]
    for t in range(1, horizon + 1):
        row = f"{t:>6} {orders[t - 1]:>6.0f}"
        row += "".join(f" {panels[n][1][t - 1]:>10.0f}" for n in names)
        if t == onset:
            row += "  <- onset"
        lines.append(row)
    return "\n".join(lines)


def _incident_fields(ep: GeneratedEpisode) -> dict[str, object]:
    effect = ep.incident.supply_effect
    return {
        "onset": ep.incident.onset_period,
        "magnitude": ep.incident.magnitude,
        "duration": ep.incident.duration,
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
    }


def render_manifest() -> str:
    """Render the shockspec manifest. Byte-stable by construction: fixed iteration order,
    ``sort_keys=True``, LF endings, trailing newline — the ``tools/audit_benchmark.py`` recipe.
    """
    units = [u for split in (Split.TEST, Split.DEV, Split.CAL) for u in build_units(split)]
    episodes: dict[str, dict[str, object]] = {}
    for unit in units:
        if unit.slice is RolloutSlice.OOD:
            ep = generate_ood_episode(seed=unit.seed, horizon=HORIZON)
        else:
            assert unit.params is not None
            ep = generate_episode(seed=unit.seed, horizon=HORIZON, params=unit.params)
        episodes[unit.independent_unit_id] = _incident_fields(ep)

    rollouts: list[dict[str, object]] = []
    for split in (Split.TEST, Split.DEV, Split.CAL):
        for r in build_rollouts(split):
            label = f"f{r.family}" if r.family is not None else str(r.slice)
            instance = f"{split.value}/{label}/s{r.seed}"
            row: dict[str, object] = {
                "rollout_id": r.rollout_id,
                "split": str(r.split),
                "family": r.family,
                "shock_family": (
                    str(FAMILY_SHOCK[r.family])
                    if r.family is not None
                    else ("compound" if r.slice is RolloutSlice.OOD else None)
                ),
                "seed": r.seed,
                "information_condition": str(r.information_condition),
                "independent_unit_id": r.independent_unit_id,
                "slice": str(r.slice),
                "template_id": r.template_id,
                "held_out_combo": r.slice is RolloutSlice.HELD_OUT_COMBO,
                "combo": (list(combo_of_params(r.params)) if r.params is not None else None),
                "promised_lead_time": r.promised_lead_time,
                "instance": instance,
                "twin": (
                    instance + TWIN_SUFFIX
                    if r.slice not in (RolloutSlice.SILENT_NULL, RolloutSlice.FALSE_ALERT_NULL)
                    else None
                ),
            }
            if r.independent_unit_id in episodes:
                row.update(episodes[r.independent_unit_id])
            else:
                row.update(
                    {"onset": None, "magnitude": None, "duration": None, "supply_effect": None}
                )
            rollouts.append(row)

    bank = [
        {
            "null_id": row.null_id,
            "seed": row.seed,
            "split": str(row.split),
            "group": str(row.group),
            "stratum": str(row.stratum) if row.stratum else None,
            "violation": str(row.violation) if row.violation else None,
            "schedule": str(row.schedule),
            "alert_period": row.alert_period,
            "observation_mode": str(row.observation_mode),
            "proposal_periods": list(row.proposal_periods),
            "horizon": row.horizon,
            "instance": row.relpath,
        }
        for row in build_nullbank(HORIZON)
    ]

    manifest = {
        "format": "collie-shockspec/v1",
        "generated_by": "uv run python -m tools.build_shockspec --all",
        "benchmark_commit": BENCHMARK_COMMIT,
        "horizon": HORIZON,
        "seed_scheme": (
            "family*1_000_000 + {test: 0, dev: 50_000, cal: 60_000} + index; "
            "extrapolation +30_000; ood 70_000_000; null_control 80_000_000; null_bank 90_000_000"
        ),
        "counts": {
            "test_main": 600,
            "test_silent_null": N_SILENT_NULL,
            "test_false_alert_null": N_FALSE_ALERT_NULL,
            "dev": 144,
            "cal": 96,
            "extrapolation": 48,
            "ood": 4,
            "null_bank_well_specified": BANK_SIZE,
            "null_bank_fragility": FRAGILITY_SIZE,
        },
        "rollouts": rollouts,
        "null_bank": bank,
    }
    return json.dumps(manifest, indent=2, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--split", choices=["dev"], help="write instance directories for one split")
    ap.add_argument("--all", action="store_true", help="emit the full manifest instead")
    ap.add_argument(
        "--check",
        action="store_true",
        help="with --all: fail if --out differs from a fresh render, and write nothing",
    )
    ap.add_argument("--limit", type=int, default=18)
    ap.add_argument(
        "--out",
        type=Path,
        help="defaults to manifests/shockspec_v1.json in --all mode; required with --split",
    )
    ap.add_argument(
        "--show",
        action="store_true",
        help="print the first episode's shocked series against its twin with the onset marked",
    )
    ap.add_argument(
        "--show-arrivals",
        action="store_true",
        help="print pause vs loss vs shift arrival timelines on one seed",
    )
    args = ap.parse_args(argv)

    if args.show_arrivals:
        print(render_arrival_comparison())
        return 0

    if args.all:
        out = args.out or REPO_ROOT / "manifests" / "shockspec_v1.json"
        text = render_manifest()
        if args.check:
            current = out.read_text(encoding="utf-8") if out.is_file() else ""
            if current != text:
                raise SystemExit(f"{out} is stale. Re-run without --check.")
            print(f"{out} is up to date")
            return 0
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"wrote {out}")
        return 0

    if args.split is None:
        ap.error("one of --split or --all is required")
    if args.out is None:
        ap.error("--split mode needs --out <directory>")

    written: list[tuple[str, GeneratedEpisode]] = []
    for family, _index, seed in dev_episodes(args.limit):
        ep = generate_episode(seed=seed, horizon=HORIZON, params=FamilyParams(family))
        relpath = f"{args.split}/f{family}/s{seed}"
        write_pair(args.out, ep, relpath=relpath)
        written.append((relpath, ep))

    per_family: dict[str, int] = {}
    for _, ep in written:
        per_family[ep.incident.family.value] = per_family.get(ep.incident.family.value, 0) + 1
    print(f"wrote {len(written)} shocked episodes (+ twins) under {args.out}")
    for name, count in sorted(per_family.items()):
        print(f"  {name}: {count}")
    if args.show and written:
        relpath, ep = written[0]
        print(f"\n{relpath} (twin at {relpath}{TWIN_SUFFIX}):")
        print(render_comparison(ep))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
