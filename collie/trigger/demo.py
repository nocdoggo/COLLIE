"""Checkpoint 1 demo: the trigger-time table over dev episodes.

Generation-side tooling, not decision-making code: this module materialises dev episodes and
reads their registry seeds and realized onsets to *build* the streams, exactly as
``collie/data/`` does. It never feeds a policy. That is why the feature-legality static scan in
``tests/test_triggers.py`` names this file as its single, explicit exemption — and asserts the
exemption list stays exactly this one file.

Run: ``uv run python -m collie.trigger.detectors --trigger-table --episodes 12``.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from collie.contracts import AlertMessage, PeriodObservation, Split
from collie.data.families import generate_episode
from collie.data.splits import FAMILIES, build_units
from collie.data.writer import write_pair
from collie.sim.loader import LoadedInstance, load_instance
from collie.trigger.calibration import FROZEN
from collie.trigger.detectors import (
    AlertOnly,
    AlertOrDetector,
    Cusum,
    PageHinkley,
    PeriodicEveryK,
    RandomMatched,
)
from collie.trigger.protocol import MaxProposalsWrapper, RefractoryWrapper, TraceableTrigger

DEMO_HORIZON = 50
"""The official synthetic horizon (env contract §1), matching tools/build_shockspec.py."""

RULES = ("alert_only", "cusum", "page_hinkley", "alert_or_detector", "periodic", "random")


def dev_episode_streams(
    root: Path, episodes: int
) -> list[tuple[str, int, int, list[PeriodObservation]]]:
    """Materialise dev episodes and build each one's (demand, alert) observation stream.

    The alert channel does not exist yet (module 03 lands later), so the demo injects one
    synthetic accurate alert at ``onset - 1`` — the fixture convention
    (``collie/fakes/fake_generator.py``) — clearly labelled in the table caption. Triggers read
    ``prev_demand`` and alerts only, so the stream is a pure function of the episode and no
    policy needs to run.
    """
    units = build_units(Split.DEV)
    by_family = {f: [u for u in units if u.family == f] for f in FAMILIES}
    cycles = episodes // len(FAMILIES)
    if cycles < 1 or episodes % len(FAMILIES) != 0:
        raise ValueError(f"--episodes must be a positive multiple of 6, got {episodes}")

    streams = []
    for i in range(cycles):
        for family in FAMILIES:
            unit = by_family[family][i]
            assert unit.params is not None  # dev units always carry params
            ep = generate_episode(seed=unit.seed, horizon=DEMO_HORIZON, params=unit.params)
            relpath = f"dev/f{family}/s{unit.seed}"
            write_pair(root, ep, relpath=relpath)
            instance = load_instance(
                root / relpath, episode_id=relpath, promised_lead_time=unit.promised_lead_time
            )
            onset = instance.incident.onset_period if instance.incident else 0
            streams.append((relpath, unit.seed, onset, obs_stream(instance)))
    return streams


def obs_stream(instance: LoadedInstance) -> list[PeriodObservation]:
    """The minimal observation stream the triggers read: prev_demand and the alert."""
    onset = instance.incident.onset_period if instance.incident else None
    alert = (
        AlertMessage(
            alert_id=f"demo_alert_{onset - 1}",
            period=onset - 1,
            text="[demo stand-in for module 03] supplier advisory",
        )
        if onset is not None and onset > 1
        else None
    )
    spec = instance.spec
    return [
        PeriodObservation(
            period=t,
            date=instance.dates[t - 1],
            on_hand=0.0,
            in_transit_total=0.0,
            prev_order=0.0,
            prev_arrivals=0.0,
            profit_per_unit=instance.profits[t - 1],
            holding_cost_per_unit=instance.holding_costs[t - 1],
            promised_lead_time=spec.promised_lead_time,
            prev_demand=0.0 if t == 1 else instance.demand[t - 2],
            alert=alert if alert is not None and alert.period == t else None,
        )
        for t in range(1, spec.horizon + 1)
    ]


def build_wrapped(rule: str, horizon: int, budget: int, seed: int) -> TraceableTrigger:
    """One wrapped trigger chain: rule, refractory window, proposal cap — the full stack."""
    base: TraceableTrigger
    match rule:
        case "alert_only":
            base = AlertOnly()
        case "cusum":
            base = Cusum(FROZEN.mu0, FROZEN.sigma0, FROZEN.cusum_k, FROZEN.cusum_h)
        case "page_hinkley":
            base = PageHinkley(FROZEN.mu0, FROZEN.sigma0, FROZEN.ph_delta, FROZEN.ph_threshold)
        case "alert_or_detector":
            base = AlertOrDetector(Cusum(FROZEN.mu0, FROZEN.sigma0, FROZEN.cusum_k, FROZEN.cusum_h))
        case "periodic":
            base = PeriodicEveryK.from_budget(
                budget, horizon, min_spacing=FROZEN.refractory_window + 1
            )
        case "random":
            base = RandomMatched.from_budget(
                budget, horizon, seed=seed, min_spacing=FROZEN.refractory_window + 1
            )
        case _:  # pragma: no cover - RULES closes this
            raise ValueError(rule)
    return MaxProposalsWrapper(
        RefractoryWrapper(base, FROZEN.refractory_window), FROZEN.max_proposals
    )


def trigger_table(episodes: int) -> str:
    """The Checkpoint 1 table: every rule's firing periods against the true onset."""
    lines = [
        f"Trigger-time table: {episodes} dev episodes, horizon {DEMO_HORIZON}, onsets U{{14..22}}.",
        "Alert channel: one synthetic accurate alert at onset-1 per episode, a demo stand-in",
        "until module 03 lands. periodic/random are budget-matched to alert_or_detector's",
        f"realised count on the same episode. Wrappers: refractory {FROZEN.refractory_window},",
        f"cap {FROZEN.max_proposals}. rel_onset = firing period minus true onset.",
        "",
    ]
    with tempfile.TemporaryDirectory() as tmp:
        streams = dev_episode_streams(Path(tmp), episodes)
        n_near_primary = n_near_random = 0
        for relpath, seed, onset, stream in streams:
            horizon = len(stream)
            lines.append(f"{relpath}  onset={onset}")
            primary: tuple[int, ...] = ()
            for rule in RULES:
                trig = build_wrapped(rule, horizon, len(primary), seed)
                for obs in stream:
                    trig.should_propose(obs)
                periods = trig.trace.periods
                if rule == "alert_or_detector":
                    primary = periods
                rel = "n/a" if not periods else ",".join(str(p - onset) for p in periods)
                lines.append(
                    f"  {rule:<18} fires={len(periods)}  periods={periods}  rel_onset=[{rel}]"
                )
            n_near_primary += sum(1 for p in primary if abs(p - onset) <= 3)
            random_matched = build_wrapped("random", horizon, len(primary), seed)
            for obs in stream:
                random_matched.should_propose(obs)
            n_near_random += sum(1 for p in random_matched.trace.periods if abs(p - onset) <= 3)
        lines += [
            "",
            f"firings within +-3 periods of onset:  alert_or_detector {n_near_primary}, "
            f"random_matched {n_near_random} (same per-episode budgets)",
        ]
    return "\n".join(lines)
