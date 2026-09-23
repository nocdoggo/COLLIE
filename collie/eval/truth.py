"""Evaluation-only hidden-truth sidecar for lifecycle and wrong-spec metrics."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from collie.arms.oracle import incident_to_payload
from collie.contracts import (
    Direction,
    DurationBin,
    EpisodeResult,
    HiddenIncident,
    MagnitudeBin,
    Persistence,
    ShockFamily,
    ShockSpec,
    TargetStream,
)

__all__ = [
    "TRUTH_SCHEMA_VERSION",
    "EpisodeTruth",
    "episode_truth_from_incident",
    "load_episode_truth_jsonl",
    "shock_periods_from_truth",
    "truth_by_episode",
    "write_episode_truth_jsonl",
    "wrong_spec_exposure",
]

TRUTH_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class EpisodeTruth:
    """Hidden target fields retained outside policy-visible episode records."""

    episode_id: str
    independent_unit_id: str
    family: ShockFamily
    target_stream: TargetStream
    direction: Direction
    onset_period: int
    magnitude_bin: MagnitudeBin
    persistence: Persistence
    duration_bin: DurationBin
    final_shock_period: int

    def __post_init__(self) -> None:
        if self.family is ShockFamily.NO_CHANGE:
            raise ValueError("EpisodeTruth describes shocked episodes; no_change has no ShockSpec")
        if self.onset_period < 1:
            raise ValueError("onset_period must be positive")
        if self.final_shock_period < self.onset_period:
            raise ValueError("final_shock_period cannot precede onset_period")


def episode_truth_from_incident(
    episode_id: str, independent_unit_id: str, incident: HiddenIncident
) -> EpisodeTruth:
    """Convert harness-only hidden truth into the evaluation sidecar schema."""
    payload = incident_to_payload(incident)
    return EpisodeTruth(
        episode_id=episode_id,
        independent_unit_id=independent_unit_id,
        family=incident.family,
        target_stream=payload.target_stream,
        direction=payload.direction,
        onset_period=incident.onset_period,
        magnitude_bin=payload.magnitude_bin,
        persistence=payload.persistence,
        duration_bin=payload.duration_bin,
        final_shock_period=incident.onset_period + incident.duration - 1,
    )


def _to_dict(truth: EpisodeTruth) -> dict[str, object]:
    payload = asdict(truth)
    return {
        "schema_version": TRUTH_SCHEMA_VERSION,
        "type": "EpisodeTruth",
        **{
            key: value.value if hasattr(value, "value") else value for key, value in payload.items()
        },
    }


def write_episode_truth_jsonl(path: Path, truths: Sequence[EpisodeTruth]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for truth in truths:
            handle.write(json.dumps(_to_dict(truth), sort_keys=True, separators=(",", ":")) + "\n")


def _from_dict(data: Mapping[str, object]) -> EpisodeTruth:
    if data.get("schema_version") != TRUTH_SCHEMA_VERSION or data.get("type") != "EpisodeTruth":
        raise ValueError("unsupported evaluation truth record")
    return EpisodeTruth(
        episode_id=str(data["episode_id"]),
        independent_unit_id=str(data["independent_unit_id"]),
        family=ShockFamily(str(data["family"])),
        target_stream=TargetStream(str(data["target_stream"])),
        direction=Direction(str(data["direction"])),
        onset_period=int(data["onset_period"]),
        magnitude_bin=MagnitudeBin(str(data["magnitude_bin"])),
        persistence=Persistence(str(data["persistence"])),
        duration_bin=DurationBin(str(data["duration_bin"])),
        final_shock_period=int(data["final_shock_period"]),
    )


def load_episode_truth_jsonl(path: Path) -> tuple[EpisodeTruth, ...]:
    truths: list[EpisodeTruth] = []
    with path.open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no}: invalid JSON") from exc
            if not isinstance(data, Mapping):
                raise ValueError(f"{path}:{line_no}: truth record must be an object")
            truths.append(_from_dict(data))
    truth_by_episode(truths)
    return tuple(truths)


def truth_by_episode(truths: Sequence[EpisodeTruth]) -> dict[str, EpisodeTruth]:
    indexed: dict[str, EpisodeTruth] = {}
    for truth in truths:
        if truth.episode_id in indexed:
            raise ValueError(f"duplicate evaluation truth for episode {truth.episode_id!r}")
        indexed[truth.episode_id] = truth
    return indexed


def shock_periods_from_truth(truths: Mapping[str, EpisodeTruth]) -> dict[str, int]:
    return {episode_id: truth.final_shock_period for episode_id, truth in truths.items()}


def _matches_truth(spec: ShockSpec, truth: EpisodeTruth) -> bool:
    relative_onset = truth.onset_period - spec.tau_j
    return (
        spec.shock_family is truth.family
        and spec.target_stream is truth.target_stream
        and spec.direction is truth.direction
        and spec.onset_window[0] <= relative_onset <= spec.onset_window[1]
        and spec.magnitude_bin is truth.magnitude_bin
        and spec.persistence is truth.persistence
        and spec.duration_bin is truth.duration_bin
    )


def wrong_spec_exposure(result: EpisodeResult, truth: EpisodeTruth) -> float:
    """Fraction of all periods carrying an active spec that disagrees with any truth field."""
    if result.episode_id != truth.episode_id:
        raise ValueError("episode result and evaluation truth ids do not match")
    if result.independent_unit_id != truth.independent_unit_id:
        raise ValueError("episode result and evaluation truth independent-unit ids do not match")
    if not result.records:
        return 0.0
    wrong = 0
    for record in result.records:
        if record.active_spec_id is not None and record.active_spec is None:
            raise ValueError("active_spec_id requires active_spec provenance")
        if record.active_spec is not None and not _matches_truth(record.active_spec, truth):
            wrong += 1
    return wrong / len(result.records)
