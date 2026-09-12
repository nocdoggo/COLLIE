from __future__ import annotations

import json

import pytest

from collie.contracts import (
    AnalysisClass,
    CallLog,
    ControlConfig,
    EpisodeResult,
    InformationCondition,
    LifecycleState,
    ParseOutcome,
    RunRecord,
    ShockFamily,
    Split,
)
from collie.eval.records import (
    episode_result_from_dict,
    episode_result_to_dict,
    load_episode_results_jsonl,
    write_episode_results_jsonl,
)


def sample_result() -> EpisodeResult:
    record = RunRecord(
        episode_id="episode-1",
        arm_id="arm",
        period=1,
        date="2026-09-11",
        on_hand_start=1.0,
        in_transit_start=2.0,
        order_quantity=3.0,
        arrivals=4.0,
        demand=5.0,
        units_sold=4.0,
        lost_sales=1.0,
        on_hand_end=1.0,
        period_profit=16.0,
        period_holding=1.0,
        triggered=True,
        llm_called=True,
        lifecycle_state=LifecycleState.ACTIVE,
        active_spec_id="spec-1",
        control_config=ControlConfig(m=1.5, l_eff=2, gamma=0.25, predictive_model="demand"),
        template_id="tpl",
    )
    call = CallLog(
        call_id="call-1",
        arm_id="arm",
        episode_id="episode-1",
        period=1,
        model_id="fake",
        prompt_hash="prompt",
        decoding_hash="decode",
        attempt_index=2,
        outcome=ParseOutcome.ACCEPTED_AFTER_REPAIR,
        input_tokens=11,
        output_tokens=7,
        latency_ms=12.5,
        usd_cost=0.01,
        cache_hit=True,
        physical=False,
    )
    return EpisodeResult(
        episode_id="episode-1",
        arm_id="arm",
        total_profit=16.0,
        total_holding_cost=1.0,
        total_reward=15.0,
        total_demand=5.0,
        total_sold=4.0,
        total_lost_sales=1.0,
        perfect_foresight=20.0,
        normalized_reward=0.75,
        records=(record,),
        calls=(call,),
        independent_unit_id="unit-1",
        split=Split.DEV,
        family=ShockFamily.DEMAND_LEVEL,
        information_condition=InformationCondition.NO_ALERT,
        analysis_class=AnalysisClass.EXPLORATORY,
    )


def test_episode_result_json_round_trip() -> None:
    result = sample_result()
    payload = episode_result_to_dict(result)
    assert payload["records"][0]["lifecycle_state"] == "active"
    assert payload["records"][0]["control_config"]["predictive_model"] == "demand"
    assert payload["calls"][0]["outcome"] == "accepted_after_repair"
    assert episode_result_from_dict(payload) == result


def test_episode_results_jsonl_round_trip(tmp_path) -> None:
    path = tmp_path / "records.jsonl"
    result = sample_result()
    write_episode_results_jsonl(path, (result,))
    assert load_episode_results_jsonl(path) == (result,)


def test_loader_rejects_unknown_schema_version() -> None:
    payload = episode_result_to_dict(sample_result())
    payload["schema_version"] = 999
    with pytest.raises(ValueError, match="schema_version"):
        episode_result_from_dict(payload)


def test_loader_reports_json_line_number(tmp_path) -> None:
    path = tmp_path / "bad.jsonl"
    path.write_text(json.dumps(episode_result_to_dict(sample_result())) + "\n{bad\n")
    with pytest.raises(ValueError, match=r"bad\.jsonl:2"):
        load_episode_results_jsonl(path)
