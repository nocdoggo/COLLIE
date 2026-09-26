from __future__ import annotations

from dataclasses import replace

import pytest

from collie.contracts import (
    Direction,
    DurationBin,
    EpisodeResult,
    HiddenIncident,
    MagnitudeBin,
    Persistence,
    RunRecord,
    ShockFamily,
    ShockSpec,
    TargetStream,
)
from collie.eval.truth import (
    EpisodeTruth,
    episode_truth_from_incident,
    load_episode_truth_jsonl,
    shock_periods_from_truth,
    truth_by_episode,
    write_episode_truth_jsonl,
    wrong_spec_exposure,
)


def _incident() -> HiddenIncident:
    return HiddenIncident(
        family=ShockFamily.DEMAND_LEVEL,
        onset_period=4,
        magnitude=1.5,
        duration=5,
        conditional_independence=True,
    )


def _spec(*, direction: Direction = Direction.DEMAND_UP) -> ShockSpec:
    return ShockSpec(
        target_stream=TargetStream.DEMAND,
        shock_family=ShockFamily.DEMAND_LEVEL,
        direction=direction,
        onset_window=(0, 2),
        magnitude_bin=MagnitudeBin.MEDIUM,
        persistence=Persistence.PERSISTENT,
        duration_bin=DurationBin.MEDIUM,
        evidence_refs=(),
        prospective_signature="sig_demand_level_up",
        tau_j=3,
        proposal_index=1,
        model_id="fake",
        decoding_hash="d",
        prompt_hash="p",
    )


def _record(period: int, active_spec: ShockSpec | None) -> RunRecord:
    return RunRecord(
        episode_id="episode",
        arm_id="arm10_spec_eprocess",
        period=period,
        date=f"p{period}",
        on_hand_start=0.0,
        in_transit_start=0.0,
        order_quantity=0.0,
        arrivals=0.0,
        demand=100.0,
        units_sold=100.0,
        lost_sales=0.0,
        on_hand_end=0.0,
        period_profit=100.0,
        period_holding=0.0,
        active_spec_id=None if active_spec is None else "spec-1",
        active_spec=active_spec,
    )


def _result(records: tuple[RunRecord, ...]) -> EpisodeResult:
    return EpisodeResult(
        episode_id="episode",
        arm_id="arm10_spec_eprocess",
        total_profit=100.0,
        total_holding_cost=0.0,
        total_reward=100.0,
        total_demand=100.0,
        total_sold=100.0,
        total_lost_sales=0.0,
        perfect_foresight=100.0,
        normalized_reward=1.0,
        records=records,
        independent_unit_id="unit",
        family=ShockFamily.DEMAND_LEVEL,
    )


def test_truth_sidecar_round_trips_and_derives_final_shock_period(tmp_path) -> None:
    truth = episode_truth_from_incident("episode", "unit", _incident())
    path = tmp_path / "truth.jsonl"
    write_episode_truth_jsonl(path, (truth,))
    loaded = load_episode_truth_jsonl(path)
    assert loaded == (truth,)
    assert shock_periods_from_truth(truth_by_episode(loaded)) == {"episode": 8}


def test_wrong_spec_exposure_checks_fields_beyond_family() -> None:
    truth = episode_truth_from_incident("episode", "unit", _incident())
    correct = _spec()
    wrong_direction = correct.model_copy(update={"direction": Direction.DEMAND_DOWN})
    result = _result((_record(1, None), _record(2, correct), _record(3, wrong_direction)))
    assert wrong_spec_exposure(result, truth) == 1 / 3


def test_wrong_spec_exposure_checks_onset_coverage() -> None:
    truth = episode_truth_from_incident("episode", "unit", _incident())
    misses_onset = _spec().model_copy(update={"onset_window": (-2, 0)})
    result = _result((_record(1, misses_onset),))
    assert wrong_spec_exposure(result, truth) == 1.0


def test_episode_truth_describes_only_shocked_episodes() -> None:
    base = dict(
        episode_id="episode",
        independent_unit_id="unit",
        family=ShockFamily.DEMAND_LEVEL,
        target_stream=TargetStream.DEMAND,
        direction=Direction.DEMAND_UP,
        onset_period=4,
        magnitude_bin=MagnitudeBin.MEDIUM,
        persistence=Persistence.PERSISTENT,
        duration_bin=DurationBin.MEDIUM,
        final_shock_period=8,
    )
    with pytest.raises(ValueError, match="no_change has no ShockSpec"):
        EpisodeTruth(**{**base, "family": ShockFamily.NO_CHANGE})
    with pytest.raises(ValueError, match="onset_period must be positive"):
        EpisodeTruth(**{**base, "onset_period": 0})
    with pytest.raises(ValueError, match="cannot precede onset"):
        EpisodeTruth(**{**base, "final_shock_period": 3})


def test_truth_loader_rejects_bad_lines_and_duplicate_episodes(tmp_path) -> None:
    truth = episode_truth_from_incident("episode", "unit", _incident())
    path = tmp_path / "truth.jsonl"
    write_episode_truth_jsonl(path, (truth,))
    good_line = path.read_text(encoding="utf-8").strip()

    path.write_text('{"schema_version": 2, "type": "EpisodeTruth"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="unsupported evaluation truth record"):
        load_episode_truth_jsonl(path)

    path.write_text("{bad\n", encoding="utf-8")
    with pytest.raises(ValueError, match=r"truth\.jsonl:1: invalid JSON"):
        load_episode_truth_jsonl(path)

    path.write_text("[1, 2]\n", encoding="utf-8")
    with pytest.raises(ValueError, match="truth record must be an object"):
        load_episode_truth_jsonl(path)

    path.write_text(good_line + "\n\n" + good_line + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate evaluation truth"):
        load_episode_truth_jsonl(path)


def test_wrong_spec_exposure_requires_matching_provenance() -> None:
    truth = episode_truth_from_incident("episode", "unit", _incident())
    result = _result((_record(1, None),))
    with pytest.raises(ValueError, match="ids do not match"):
        wrong_spec_exposure(result, replace(truth, episode_id="other"))
    with pytest.raises(ValueError, match="independent-unit ids do not match"):
        wrong_spec_exposure(result, replace(truth, independent_unit_id="other"))


def test_wrong_spec_exposure_is_zero_without_records() -> None:
    truth = episode_truth_from_incident("episode", "unit", _incident())
    assert wrong_spec_exposure(_result(()), truth) == 0.0


def test_wrong_spec_exposure_requires_active_spec_provenance() -> None:
    truth = episode_truth_from_incident("episode", "unit", _incident())
    record = _record(1, None)
    record = RunRecord(
        episode_id=record.episode_id,
        arm_id=record.arm_id,
        period=record.period,
        date=record.date,
        on_hand_start=record.on_hand_start,
        in_transit_start=record.in_transit_start,
        order_quantity=record.order_quantity,
        arrivals=record.arrivals,
        demand=record.demand,
        units_sold=record.units_sold,
        lost_sales=record.lost_sales,
        on_hand_end=record.on_hand_end,
        period_profit=record.period_profit,
        period_holding=record.period_holding,
        active_spec_id="spec-1",
    )
    with pytest.raises(ValueError, match="active_spec provenance"):
        wrong_spec_exposure(_result((record,)), truth)
