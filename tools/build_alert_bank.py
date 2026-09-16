"""Run implemented bank checks and print an analysis-only review sheet.

--prototype is explicitly a development check, never a complete CP1 audit.
Committed manifest metadata and explicitly supplied incident sidecars are scanned.
Module 02 registry validation remains an explicit integration step.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict, deque
from dataclasses import asdict, replace
from pathlib import Path

import yaml

from collie.contracts import AlertKind, ShockFamily
from collie.data.alerts.audit import default_audit_config
from collie.data.alerts.bank import (
    forbidden_from_metadata,
    load_alert_bank,
    render_alert,
    validate_bank_composition,
    validate_no_repeated_renderings,
    validate_template_leakage,
    validate_wording_holdout,
)
from collie.data.alerts.conditions import load_manifest, render_conditions
from collie.data.alerts.controls import VARIANTS, render_content_controls
from collie.fakes import ConstantController, fixture_episode
from collie.sim.loader import LoadedInstance
from collie.sim.runner import EpisodeRunner

ROOT = Path(__file__).resolve().parents[1]


def review_sample(templates, count):
    # Round-robin over family/kind cells; rotate split priority across cells.
    # The review sheet is deterministic and carries actual template IDs.
    # Round-robin over family/kind cells and rotate the split starting point, so the human review covers distinct categories and stays reproducible.
    groups = defaultdict(list)
    for template in templates:
        groups[(template.family.value, template.kind.value)].append(template)
    queues = []
    for index, key in enumerate(sorted(groups)):
        group = sorted(groups[key], key=lambda t: (t.split.value, t.template_id))
        offset = index % len(group)
        queues.append(deque(group[offset:] + group[:offset]))
    selected = []
    while len(selected) < count and any(queues):
        for queue in queues:
            if queue and len(selected) < count:
                selected.append(queue.popleft())
    return selected


def main(argv=None):
    # The CP1 path validates the full bank and prints the review sheet; the CP2 path switches via flags to a paired replay of one seed.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--templates", type=Path, default=ROOT / "collie/data/alerts/templates")
    parser.add_argument("--render-sheet", type=int, default=24)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--prototype",
        action="store_true",
        help="Development only: skip the 180-template composition requirement",
    )
    parser.add_argument(
        "--forbidden-values",
        type=Path,
        help="Optional JSON list of forbidden strings; not automatic metadata extraction",
    )
    parser.add_argument(
        "--incident",
        type=Path,
        action="append",
        default=[],
        help="Additional incident.json sidecars to scan against",
    )
    parser.add_argument("--replay-one-seed", action="store_true")
    parser.add_argument("--show-diff", action="store_true")
    args = parser.parse_args(argv)
    if args.replay_one_seed:
        replay_one_seed(args.show_diff)
        return 0
    if args.render_sheet < 1:
        parser.error("--render-sheet must be positive")
    try:
        forbidden = forbidden_from_metadata(
            ROOT / "manifests/benchmark_v1.json",
            ROOT / "manifests/shockspec_v1.json",
            args.incident,
        )
        if args.forbidden_values:
            raw = json.loads(args.forbidden_values.read_text(encoding="utf-8"))
            if not isinstance(raw, list) or any(
                not isinstance(v, str) or not v.strip() for v in raw
            ):
                raise ValueError("forbidden values must be a JSON list of non-empty strings")
            forbidden = tuple(sorted(set(forbidden) | set(raw)))
        templates = load_alert_bank(args.templates)
        if not templates:
            raise ValueError("no templates loaded")
        if not args.prototype:
            validate_bank_composition(templates)
            if args.render_sheet > len(templates):
                raise ValueError("render-sheet exceeds the number of distinct templates")
        validate_wording_holdout(templates)
        for template in templates:
            validate_template_leakage(template, forbidden_literals=forbidden)
        validate_no_repeated_renderings(templates)
        selected = review_sample(templates, min(args.render_sheet, len(templates)))
        mode = (
            "PROTOTYPE CHECKS PASSED (not CP1 audit)"
            if args.prototype
            else "IMPLEMENTED BANK CHECKS PASSED"
        )
        print(mode)
        print(
            f"Templates loaded: {len(templates)}; review rows: {len(selected)}; seed: {args.seed}"
        )
        print("Registry validation: pending integration")
        print(
            f"Manifest/sidecar forbidden strings: {len(forbidden)}; sidecars: {len(args.incident)}"
        )
        print("Analysis-only sheet: hidden labels must never be passed to the policy.")
        for number, template in enumerate(selected, 1):
            rendered = render_alert(template, args.seed)
            print(
                f"\n[{number}] {template.template_id} | {template.split.value} | "
                f"{template.family.value} | {template.kind.value}"
            )
            print(f"Text: {rendered.text}")
            print("HiddenAlertSpec: " + json.dumps(asdict(rendered.alert_spec), ensure_ascii=False))
        return 0
    except (ValueError, OSError, yaml.YAMLError) as exc:
        print(f"CHECK FAILED: {exc}", file=sys.stderr)
        return 1


def replay_one_seed(show_diff=False):
    # This is a fake-backed engineering demo; it does not mean real generator integration is complete, and it is not used to report LLM effects.
    manifest = load_manifest(ROOT / "manifests/shockspec_v1.json")
    config = default_audit_config()
    row = next(
        r
        for r in manifest["rollouts"]
        if r["split"] == "dev" and r["family"] == 1 and r["template_id"] is not None
    )
    bank = load_alert_bank(ROOT / "collie/data/alerts/templates")
    candidates = [
        t for t in bank if t.split.value == row["split"] and t.family.value == row["shock_family"]
    ]
    accurate = next(t for t in candidates if t.kind is AlertKind.ACCURATE)
    unreliable = next(t for t in candidates if t.kind is AlertKind.OVERSTATED)
    wrong = next(
        t
        for t in bank
        if t.split == accurate.split
        and t.family != accurate.family
        and t.kind is AlertKind.ACCURATE
    )
    episode = fixture_episode(
        ShockFamily(row["shock_family"]),
        seed=row["seed"],
        onset=row["onset"],
        horizon=manifest["horizon"],
    )
    rollouts = render_conditions(
        manifest=manifest,
        independent_unit_id=row["independent_unit_id"],
        demand=episode.demand,
        lead_times=episode.supply.lead_times,
        pause_active=episode.supply.pause_active,
        onset=episode.incident.onset_period,
        accurate=accurate,
        unreliable=unreliable,
        unreliable_offset=config["unreliable_offset"],
    )

    def run_rollout(rollout, message):
        # Every run uses the same exogenous inputs and a fresh controller instance; the hidden incident stays on the runner side.
        spec = replace(
            episode.spec,
            independent_unit_id=rollout.independent_unit_id,
            information_condition=rollout.condition,
        )
        instance = LoadedInstance(
            spec=spec,
            demand=episode.demand,
            supply=episode.supply,
            profits=(spec.profit_per_unit,) * spec.horizon,
            holding_costs=(spec.holding_cost_per_unit,) * spec.horizon,
            dates=tuple(str(i) for i in range(1, spec.horizon + 1)),
            incident=episode.incident,
        )
        outcome = EpisodeRunner(
            instance=instance,
            alerts={message.period: message} if message else {},
            template_ids={message.period: rollout.template_id} if message else {},
            strict_isolation=True,
            check_controller_isolation=True,
        ).run(ConstantController())
        if outcome.result.independent_unit_id != rollout.independent_unit_id:
            raise ValueError("runner lost independent-unit identity")
        return outcome

    reference = run_rollout(rollouts[0], None)
    reference_observations = tuple(replace(obs, alert=None) for obs in reference.observations)
    runs = 1

    def check_runner(rollout, message):
        # The constant controller never reacts to alerts, so observations, orders and reward with alert stripped must match the baseline replay exactly.
        nonlocal runs
        outcome = run_rollout(rollout, message)
        runs += 1
        if (
            outcome.order_rows() != reference.order_rows()
            or outcome.result.total_reward != reference.result.total_reward
            or tuple(replace(obs, alert=None) for obs in outcome.observations)
            != reference_observations
        ):
            raise ValueError("constant-controller replay changed beyond alert content/timing")
        return outcome

    fingerprints = {r.exogenous.fingerprint_bytes() for r in rollouts}
    if len(fingerprints) != 1:
        raise ValueError("paired trajectory changed")
    result = {
        "analysis_class": "exploratory",
        "source": "FakeGenerator fixture",
        "independent_unit_id": row["independent_unit_id"],
        "seed": row["seed"],
        "manifest_template_slot": row["template_id"],
        "bound_template_ids": [accurate.template_id, unreliable.template_id],
        "exogenous_sha256": hashlib.sha256(fingerprints.pop()).hexdigest(),
        "condition_diff_allowed": ["message", "timestamp", "analysis-side template metadata"],
        "conditions": [],
        "content_sets": [],
    }
    for rollout in rollouts:
        if rollout.message is not None:
            check_runner(rollout, rollout.message)
        result["conditions"].append(
            {
                "condition": rollout.condition.value,
                "timestamp": rollout.message.period if rollout.message else None,
                "text": rollout.message.text if rollout.message else None,
                "exogenous_changed": False,
            }
        )
        if rollout.message is None:
            continue
        trace = [{"period": rollout.message.period, "reason": "alert"}]
        variants = render_content_controls(
            rollout.message,
            trigger_trace=trace,
            wrong_text=render_alert(wrong, row["seed"]).text,
            true_family=accurate.family,
            wrong_family=wrong.family,
            seed=row["seed"],
            length_tolerance=config["length_tolerance"],
        )
        for key in VARIANTS:
            check_runner(rollout, variants.message(key))
        result["content_sets"].append(
            {
                "condition": rollout.condition.value,
                "timestamp": variants.timestamp,
                "trigger_trace_hash": variants.trigger_trace_hash,
                "diff": {
                    key: {
                        "text_changed": variants.message(key).text != rollout.message.text,
                        "timestamp_changed": variants.message(key).period != rollout.message.period,
                        "trigger_trace_changed": False,
                        "exogenous_changed": False,
                        **({"text": variants.message(key).text} if show_diff else {}),
                    }
                    for key in VARIANTS
                },
            }
        )
    result["episode_runner_replays"] = runs
    result["constant_controller_observations_equal_excluding_alert"] = True
    print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    raise SystemExit(main())
