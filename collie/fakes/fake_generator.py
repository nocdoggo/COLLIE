"""Six tiny fixture episodes, one per shock family, short enough for unit tests.

Not a substitute for branch B's generator: no split logic, no held-out combinations, no null
bank, no InventoryBench-format output. Its only job is to give every other branch a deterministic
shocked episode with a known hidden truth, today.

The hidden truth is returned **separately** from the observable episode, never attached to it, so
a test that accidentally passes hidden state into a controller fails the isolation walk rather
than quietly succeeding.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from collie.contracts import (
    AlertKind,
    AlertMessage,
    Direction,
    DurationBin,
    EpisodeSpec,
    HiddenAlertSpec,
    HiddenIncident,
    MagnitudeBin,
    ObservationMode,
    Persistence,
    ShockFamily,
    Split,
    SupplyEffect,
    SupplyEffectKind,
    SupplyRealization,
    TargetStream,
)

__all__ = ["FakeGenerator", "FixtureEpisode", "fixture_episode", "fixture_episodes"]

# Small but not degenerate: long enough for a mid-episode onset plus post-onset evidence.
HORIZON = 20
ONSET = 10
BASE_DEMAND = 100.0
BASE_SIGMA = 10.0


@dataclass(frozen=True, slots=True)
class FixtureEpisode:
    """An observable episode plus its hidden truth, kept deliberately separate."""

    spec: EpisodeSpec
    demand: tuple[float, ...]
    supply: SupplyRealization
    incident: HiddenIncident
    alert: AlertMessage | None
    baseline_demand: tuple[float, ...]
    """The unshocked twin's demand path, sharing every pre-onset draw."""


def _base_path(rng: random.Random, n: int) -> list[float]:
    return [round(rng.gauss(BASE_DEMAND, BASE_SIGMA), 3) for _ in range(n)]


def _hidden_alert(
    family: ShockFamily,
    stream: TargetStream,
    direction: Direction,
    magnitude: MagnitudeBin,
    persistence: Persistence,
    duration: DurationBin,
    signature: str,
) -> HiddenAlertSpec:
    return HiddenAlertSpec(
        family=family,
        target_stream=stream,
        direction=direction,
        onset_window=(-1, 1),
        magnitude_bin=magnitude,
        persistence=persistence,
        duration_bin=duration,
        prospective_signature=signature,
        kind=AlertKind.ACCURATE,
    )


def fixture_episode(
    family: ShockFamily,
    *,
    seed: int = 0,
    horizon: int = HORIZON,
    onset: int = ONSET,
    with_alert: bool = True,
    observation_mode: ObservationMode = ObservationMode.UNCENSORED,
) -> FixtureEpisode:
    """Build one deterministic fixture episode for ``family``.

    Demand and supply effects mirror branch B's family definitions in miniature, including the
    conditional-independence flag that branch F reads to decide between a joint likelihood and
    alpha splitting.
    """
    rng = random.Random(seed * 1000 + int(list(ShockFamily).index(family)))
    baseline = _base_path(rng, horizon)
    demand = list(baseline)
    lead_times: list[float] = [2.0] * horizon
    pause = [False] * horizon

    magnitude = 1.0
    duration = horizon - onset
    supply_effect: SupplyEffect | None = None
    stream = TargetStream.DEMAND
    direction = Direction.DEMAND_UP
    mag_bin = MagnitudeBin.MEDIUM
    persistence = Persistence.PERSISTENT
    dur_bin = DurationBin.LONGER
    signature = "sig_demand_level_up"
    conditional_independence = True

    match family:
        case ShockFamily.DEMAND_LEVEL:
            magnitude = 1.5
            for t in range(onset, horizon):
                demand[t] = round(demand[t] * magnitude, 3)
        case ShockFamily.TEMPORARY_PULSE:
            magnitude, duration = 2.0, 3
            dur_bin, persistence = DurationBin.SHORT, Persistence.TRANSIENT
            signature = "sig_demand_pulse"
            for t in range(onset, min(onset + duration, horizon)):
                demand[t] = round(demand[t] * magnitude, 3)
        case ShockFamily.LEAD_TIME_SHIFT:
            magnitude = 1.0
            stream, direction = TargetStream.ARRIVAL, Direction.ARRIVAL_DELAYED
            signature = "sig_arrival_delay"
            supply_effect = SupplyEffect(
                SupplyEffectKind.LEAD_TIME_SHIFT, onset, horizon - onset, disrupted_lead_time=4
            )
            for t in range(onset, horizon):
                lead_times[t] = 4.0
        case ShockFamily.SHIPMENT_LOSS:
            magnitude, duration = 1.0, 2
            stream, direction = TargetStream.ARRIVAL, Direction.ARRIVAL_INTERRUPTED
            dur_bin, persistence = DurationBin.SHORT, Persistence.TRANSIENT
            signature = "sig_arrival_loss"
            supply_effect = SupplyEffect(SupplyEffectKind.SHIPMENT_LOSS, onset, duration)
            for t in range(onset, min(onset + duration, horizon)):
                lead_times[t] = math.inf
        case ShockFamily.TRANSIT_PAUSE:
            magnitude, duration = 1.0, 4
            stream, direction = TargetStream.ARRIVAL, Direction.ARRIVAL_INTERRUPTED
            dur_bin, persistence = DurationBin.MEDIUM, Persistence.TRANSIENT
            signature = "sig_arrival_stall"
            supply_effect = SupplyEffect(SupplyEffectKind.TRANSIT_PAUSE, onset, duration)
            for t in range(onset, min(onset + duration, horizon)):
                pause[t] = True
        case ShockFamily.COMPOUND:
            # One incident drives both streams, so the innovations share a latent cause.
            magnitude, duration = 1.5, 8
            stream, direction = TargetStream.BOTH, Direction.MIXED
            signature = "sig_compound"
            conditional_independence = False
            supply_effect = SupplyEffect(SupplyEffectKind.TRANSIT_PAUSE, onset, 4)
            for t in range(onset, min(onset + duration, horizon)):
                demand[t] = round(demand[t] * magnitude, 3)
            for t in range(onset, min(onset + 4, horizon)):
                pause[t] = True
        case ShockFamily.NO_CHANGE:
            stream, direction = TargetStream.NONE, Direction.NONE
            mag_bin, persistence = MagnitudeBin.NONE, Persistence.NONE
            dur_bin, duration = DurationBin.NONE, 0
        case _:  # pragma: no cover - StrEnum is exhaustive above
            raise ValueError(f"unhandled family {family}")

    episode_id = f"fixture-{family.value}-s{seed}"
    incident = HiddenIncident(
        family=family,
        onset_period=onset,
        magnitude=magnitude,
        duration=duration,
        conditional_independence=conditional_independence,
        supply_effect=supply_effect,
        alert_spec=_hidden_alert(
            family, stream, direction, mag_bin, persistence, dur_bin, signature
        ),
        baseline_twin_id=f"{episode_id}-twin",
        seed=seed,
    )
    alert = (
        AlertMessage(
            alert_id=f"alert_{onset - 1}",
            period=onset - 1,
            text=(
                "Supplier advisory: handling at the transfer hub may be disrupted "
                "for a short period. Treat pipeline visibility as degraded."
            ),
        )
        if with_alert and family is not ShockFamily.NO_CHANGE
        else None
    )
    spec = EpisodeSpec(
        episode_id=episode_id,
        item_id="fixture_item",
        horizon=horizon,
        promised_lead_time=2,
        profit_per_unit=4.0,
        holding_cost_per_unit=1.0,
        order_cap=1000.0,
        observation_mode=observation_mode,
        split=Split.DEV,
        family=family,
        independent_unit_id=f"unit-{family.value}-s{seed}",
        source="fixture",
        train_demand=tuple(_base_path(random.Random(seed + 7717), 10)),
    )
    return FixtureEpisode(
        spec=spec,
        demand=tuple(demand),
        supply=SupplyRealization(lead_times=tuple(lead_times), pause_active=tuple(pause)),
        incident=incident,
        alert=alert,
        baseline_demand=tuple(baseline),
    )


def fixture_episodes(*, seed: int = 0, **kw: object) -> tuple[FixtureEpisode, ...]:
    """One fixture per shock family, excluding the ``no_change`` abstention case."""
    families = [f for f in ShockFamily if f is not ShockFamily.NO_CHANGE]
    return tuple(fixture_episode(f, seed=seed, **kw) for f in families)  # type: ignore[arg-type]


@dataclass
class FakeGenerator:
    """Convenience wrapper with a stable, deterministic default set."""

    seed: int = 0

    def episodes(self) -> tuple[FixtureEpisode, ...]:
        return fixture_episodes(seed=self.seed)

    def episode(self, family: ShockFamily) -> FixtureEpisode:
        return fixture_episode(family, seed=self.seed)
