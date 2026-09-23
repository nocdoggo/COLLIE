from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

import tools.run_pilot as run_pilot
from collie.contracts import (
    CallLog,
    Direction,
    DurationBin,
    EpisodeResult,
    InformationCondition,
    MagnitudeBin,
    ParseOutcome,
    Persistence,
    RunRecord,
    ShockFamily,
    ShockSpec,
    Split,
    TargetStream,
)
from collie.eval.pilot import (
    compute_builtin_pilot_intervals,
    compute_builtin_pilot_metrics,
    evaluate_pilot,
    pilot_manifest_from_records,
    render_pilot_report,
    validate_go_intervals,
    validate_pilot_intervals,
    validate_pilot_metrics,
    validate_pilot_record_count,
    write_pilot_manifest,
)
from collie.eval.prereg import Preregistration, load_preregistration
from tools.run_pilot import main


def prereg() -> Preregistration:
    return Preregistration(
        path=Path("prereg/prereg_v1.yaml"),
        data={
            "go_criteria": [
                {"id": "profit_lift", "threshold": 1.0, "operator": ">="},
                {"id": "lost_sales_reduction", "threshold": 0.0, "operator": ">="},
            ],
            "kill_thresholds": {
                "negative_profit_lift": 0.0,
                "false_activation_rate": 0.1,
            },
            "kill_triggers": [
                {
                    "id": "negative_profit_lift",
                    "threshold": "negative_profit_lift",
                    "operator": "<",
                },
                {"id": "false_activation_rate", "threshold": "false_activation_rate"},
            ],
        },
    )


def full_go_prereg() -> Preregistration:
    data = prereg().data
    return Preregistration(
        path=Path("prereg/prereg_v1.yaml"),
        data={
            **data,
            "go_criteria": [
                {"id": "profit_lift", "threshold": 1.0, "operator": ">="},
                {"id": "lost_sales_reduction", "threshold": 0.0, "operator": ">="},
                {"id": "false_activation_control", "threshold": 0.0, "operator": ">="},
                {"id": "wrong_family_exposure", "threshold": 0.0, "operator": "<="},
                {"id": "fill_rate_floor", "threshold": 0.0, "operator": ">="},
                {"id": "cost_frontier", "threshold": 1.0, "operator": "=="},
                {"id": "recovery_time", "threshold": 10.0, "operator": "<="},
            ],
        },
    )


def result(arm: str, profit: float, lost: float) -> EpisodeResult:
    return EpisodeResult(
        episode_id=f"e-{arm}",
        arm_id=arm,
        total_profit=profit,
        total_holding_cost=0.0,
        total_reward=profit,
        total_demand=100.0,
        total_sold=100.0 - lost,
        total_lost_sales=lost,
        perfect_foresight=100.0,
        normalized_reward=profit / 100.0,
        independent_unit_id=f"u-{arm}",
    )


def call(outcome: ParseOutcome, *, attempt_index: int = 1, period: int = 1) -> CallLog:
    return CallLog(
        call_id=f"call-{period}-{attempt_index}-{outcome.value}",
        arm_id="arm10_spec_eprocess",
        episode_id="e",
        period=period,
        model_id="fake",
        prompt_hash="p",
        decoding_hash="d",
        attempt_index=attempt_index,
        outcome=outcome,
    )


def record(template_id: str) -> RunRecord:
    return RunRecord(
        episode_id="e",
        arm_id="a",
        period=1,
        date="p1",
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
        template_id=template_id,
    )


def spec(family: ShockFamily) -> ShockSpec:
    return ShockSpec(
        target_stream=TargetStream.DEMAND,
        shock_family=family,
        direction=Direction.DEMAND_UP,
        onset_window=(-1, 1),
        magnitude_bin=MagnitudeBin.MEDIUM,
        persistence=Persistence.PERSISTENT,
        duration_bin=DurationBin.LONGER,
        evidence_refs=(),
        prospective_signature="sig_demand_level_up",
        tau_j=1,
        proposal_index=1,
        model_id="fake",
        decoding_hash="d",
        prompt_hash="p",
    )


def period_record(
    period: int,
    sold: float,
    *,
    active_spec_id: str | None = None,
    active_spec: ShockSpec | None = None,
) -> RunRecord:
    return RunRecord(
        episode_id="e",
        arm_id="a",
        period=period,
        date=f"p{period}",
        on_hand_start=0.0,
        in_transit_start=0.0,
        order_quantity=0.0,
        arrivals=0.0,
        demand=100.0,
        units_sold=sold,
        lost_sales=100.0 - sold,
        on_hand_end=0.0,
        period_profit=sold,
        period_holding=0.0,
        active_spec_id=active_spec_id,
        active_spec=active_spec,
    )


def test_builtin_pilot_metrics_from_episode_results() -> None:
    metrics = compute_builtin_pilot_metrics(
        (
            result("arm10_spec_eprocess", 12.0, 3.0),
            result("arm1_capped_base_stock", 10.0, 5.0),
        )
    )
    assert metrics["profit_lift"] == 2.0
    assert metrics["lost_sales_reduction"] == 2.0
    assert "budget_overrun_rate" not in metrics


def test_builtin_pilot_metrics_from_calls_and_null_activations() -> None:
    null_result = replace(
        result("arm10_spec_eprocess", 12.0, 0.0),
        family=ShockFamily.NO_CHANGE,
        records=(period_record(1, 100.0, active_spec_id="wrong"),),
        calls=(call(ParseOutcome.ACCEPTED), call(ParseOutcome.FALLBACK, period=2)),
    )
    metrics = compute_builtin_pilot_metrics((null_result,))
    assert metrics["parser_failure_rate"] == 0.5
    assert metrics["false_activation_rate"] == 1.0
    assert metrics["false_activation_control"] == 0.0


def test_parser_failure_counts_terminal_proposal_outcome_not_repaired_attempt() -> None:
    repaired = replace(
        result("arm10_spec_eprocess", 12.0, 0.0),
        calls=(
            call(ParseOutcome.FALLBACK),
            call(ParseOutcome.ACCEPTED_AFTER_REPAIR, attempt_index=2),
        ),
    )
    failed = replace(
        result("arm10_spec_eprocess", 12.0, 0.0),
        episode_id="failed",
        independent_unit_id="failed",
        calls=(
            call(ParseOutcome.FALLBACK),
            call(ParseOutcome.FALLBACK, attempt_index=2),
        ),
    )
    metrics = compute_builtin_pilot_metrics((repaired, failed))
    intervals = compute_builtin_pilot_intervals((repaired, failed))
    assert metrics["parser_failure_rate"] == 0.5
    assert intervals["parser_failure_rate"][0] < 0.5 < intervals["parser_failure_rate"][1]


def test_builtin_pilot_metrics_compute_registered_headroom_family_count() -> None:
    results = []
    families = tuple(family for family in ShockFamily if family is not ShockFamily.NO_CHANGE)
    for family_index, family in enumerate(families):
        for unit_index in range(2):
            unit = f"{family.value}-{unit_index}"
            baseline = replace(
                result("arm1_capped_base_stock", 100.0, 0.0),
                episode_id=unit,
                independent_unit_id=unit,
                family=family,
            )
            oracle_profit = 106.0 if family_index < 4 else 100.0
            oracle = replace(
                result("oracle_shockspec_headroom", oracle_profit, 0.0),
                episode_id=unit,
                independent_unit_id=unit,
                family=family,
            )
            results.extend((baseline, oracle))
    metrics = compute_builtin_pilot_metrics(tuple(results))
    intervals = compute_builtin_pilot_intervals(tuple(results))
    assert metrics["insufficient_headroom"] == 4.0
    assert intervals["insufficient_headroom"] == (4.0, 4.0)


def test_builtin_pilot_metrics_compute_detector_contrast_and_interval() -> None:
    results = []
    for index, treatment_profit in enumerate((12.0, 14.0, 16.0)):
        unit = f"u{index}"
        results.extend(
            (
                replace(
                    result("arm10_spec_eprocess", treatment_profit, 0.0),
                    episode_id=unit,
                    independent_unit_id=unit,
                ),
                replace(
                    result("ctrl_cusum_to_compiler", 10.0, 0.0),
                    episode_id=unit,
                    independent_unit_id=unit,
                ),
            )
        )
    metrics = compute_builtin_pilot_metrics(tuple(results))
    intervals = compute_builtin_pilot_intervals(tuple(results))
    assert metrics["detector_indistinguishable"] == 4.0
    low, high = intervals["detector_indistinguishable"]
    assert low < 4.0 < high


def test_builtin_pilot_metrics_derive_wrong_family_from_active_spec_records() -> None:
    correct = replace(
        result("arm10_spec_eprocess", 12.0, 0.0),
        family=ShockFamily.DEMAND_LEVEL,
        records=(
            period_record(
                1,
                100.0,
                active_spec_id="spec-1",
                active_spec=spec(ShockFamily.DEMAND_LEVEL),
            ),
        ),
    )
    wrong = replace(
        result("arm10_spec_eprocess", 12.0, 0.0),
        family=ShockFamily.SHIPMENT_LOSS,
        records=(
            period_record(
                1,
                100.0,
                active_spec_id="spec-1",
                active_spec=spec(ShockFamily.DEMAND_LEVEL),
            ),
        ),
    )
    metrics = compute_builtin_pilot_metrics((correct, wrong))
    intervals = compute_builtin_pilot_intervals((correct, wrong))
    assert metrics["wrong_family_exposure"] == 0.5
    assert metrics["wrong_family_activation_rate"] == 0.5
    assert intervals["wrong_family_exposure"][0] < 0.5 < intervals["wrong_family_exposure"][1]


def test_wrong_family_metrics_require_active_spec_provenance() -> None:
    missing = replace(
        result("arm10_spec_eprocess", 12.0, 0.0),
        family=ShockFamily.DEMAND_LEVEL,
        records=(period_record(1, 100.0, active_spec_id="spec-1"),),
    )
    with pytest.raises(ValueError, match="active_spec provenance"):
        compute_builtin_pilot_metrics((missing,))


def test_builtin_pilot_metrics_compute_recovery_time_from_sidecar() -> None:
    sold = [100, 70, 95, 94, 96, 97, 98]
    pilot_result = replace(
        result("arm10_spec_eprocess", 12.0, 0.0),
        episode_id="e",
        records=tuple(period_record(t, float(s)) for t, s in enumerate(sold, start=1)),
    )
    metrics = compute_builtin_pilot_metrics((pilot_result,), shock_periods={"e": 2})
    intervals = compute_builtin_pilot_intervals((pilot_result,), shock_periods={"e": 2})
    assert metrics["recovery_time"] == 3.0
    assert intervals["recovery_time"] == (3.0, 3.0)


def test_pilot_recovery_refuses_to_drop_never_recovered_episodes() -> None:
    pilot_result = replace(
        result("arm10_spec_eprocess", 12.0, 0.0),
        episode_id="never",
        family=ShockFamily.DEMAND_LEVEL,
        records=tuple(period_record(t, 50.0) for t in range(1, 8)),
    )
    with pytest.raises(ValueError, match="never recover"):
        compute_builtin_pilot_metrics((pilot_result,), shock_periods={"never": 2})


def test_pilot_recovery_scores_never_recovered_at_registered_horizon_plus_one() -> None:
    pilot_result = replace(
        result("arm10_spec_eprocess", 12.0, 0.0),
        episode_id="never",
        family=ShockFamily.DEMAND_LEVEL,
        records=tuple(period_record(t, 50.0) for t in range(1, 8)),
    )
    metrics = compute_builtin_pilot_metrics(
        (pilot_result,),
        shock_periods={"never": 2},
        never_recovered_value=51,
    )
    intervals = compute_builtin_pilot_intervals(
        (pilot_result,),
        shock_periods={"never": 2},
        never_recovered_value=51,
    )
    assert metrics["recovery_time"] == 51.0
    assert intervals["recovery_time"] == (51.0, 51.0)


def test_builtin_pilot_intervals_use_paired_records() -> None:
    paired_results = []
    for unit, arm10_profit, arm1_profit in (("u1", 12.0, 10.0), ("u2", 16.0, 13.0)):
        paired_results.append(
            replace(
                result("arm10_spec_eprocess", arm10_profit, 3.0),
                independent_unit_id=unit,
            )
        )
        paired_results.append(
            replace(
                result("arm1_capped_base_stock", arm1_profit, 5.0),
                independent_unit_id=unit,
            )
        )
    intervals = compute_builtin_pilot_intervals(tuple(paired_results))
    assert intervals["profit_lift"][0] < 2.5 < intervals["profit_lift"][1]
    assert intervals["lost_sales_reduction"][0] <= 2.0 <= intervals["lost_sales_reduction"][1]
    assert intervals["cost_frontier"] == (1.0, 1.0)


def test_builtin_primary_metrics_use_registered_stratum_weights() -> None:
    paired_results = []
    cases = [
        ("u1", ShockFamily.DEMAND_LEVEL, 20.0, 10.0),
        ("u2", ShockFamily.TEMPORARY_PULSE, 10.0, 10.0),
        ("u3", ShockFamily.TEMPORARY_PULSE, 10.0, 10.0),
        ("u4", ShockFamily.TEMPORARY_PULSE, 10.0, 10.0),
    ]
    for unit, family, arm10_profit, arm1_profit in cases:
        for arm, profit in (
            ("arm10_spec_eprocess", arm10_profit),
            ("arm1_capped_base_stock", arm1_profit),
        ):
            paired_results.append(
                replace(
                    result(arm, profit, 0.0),
                    independent_unit_id=unit,
                    family=family,
                    information_condition=InformationCondition.NO_ALERT,
                )
            )
    weights = {
        (ShockFamily.DEMAND_LEVEL.value, InformationCondition.NO_ALERT.value): 0.5,
        (ShockFamily.TEMPORARY_PULSE.value, InformationCondition.NO_ALERT.value): 0.5,
    }
    metrics = compute_builtin_pilot_metrics(tuple(paired_results), stratum_weights=weights)
    intervals = compute_builtin_pilot_intervals(tuple(paired_results), stratum_weights=weights)
    assert metrics["profit_lift"] == 5.0
    assert intervals["profit_lift"][0] <= 5.0 <= intervals["profit_lift"][1]


def test_budget_overrun_rate_requires_a_registered_budget() -> None:
    metrics = compute_builtin_pilot_metrics(
        (
            result("arm10_spec_eprocess", 12.0, 3.0),
            result("arm1_capped_base_stock", 10.0, 5.0),
        ),
        call_budget_per_episode=0,
    )
    assert metrics["budget_overrun_rate"] == 0.0


def test_builtin_pilot_metrics_report_cost_frontier_status() -> None:
    arm10 = replace(
        result("arm10_spec_eprocess", 12.0, 0.0),
        calls=(call(ParseOutcome.ACCEPTED),),
    )
    baseline = result("arm1_capped_base_stock", 10.0, 0.0)
    metrics = compute_builtin_pilot_metrics((arm10, baseline))
    assert metrics["cost_frontier"] == 1.0


def test_evaluate_pilot_records_go_and_kill_verdicts() -> None:
    decision = evaluate_pilot(
        prereg(),
        {"profit_lift": 2.0, "lost_sales_reduction": 1.0, "false_activation_rate": 0.0},
    )
    assert decision.decision == "go"
    assert all(verdict.passed for verdict in decision.go)
    assert not any(verdict.passed for verdict in decision.kill)


def test_formal_pilot_requires_intervals_for_every_go_criterion() -> None:
    with pytest.raises(ValueError, match="missing intervals"):
        validate_go_intervals(full_go_prereg(), {"profit_lift": (1.0, 2.0)})


def test_evaluate_pilot_can_enforce_formal_go_intervals() -> None:
    with pytest.raises(ValueError, match="formal pilot go criteria"):
        evaluate_pilot(
            full_go_prereg(),
            {"profit_lift": 2.0},
            intervals={"profit_lift": (1.0, 3.0)},
            require_go_intervals=True,
        )


def test_formal_go_uses_conservative_confidence_bound() -> None:
    pilot_prereg = Preregistration(
        path=Path("prereg/prereg_v1.yaml"),
        data={
            "go_criteria": [
                {"id": "profit_lift", "threshold": 0.0, "operator": ">="},
                {"id": "wrong_family_exposure", "threshold": 0.10, "operator": "<="},
            ],
            "kill_thresholds": {},
            "kill_triggers": [],
        },
    )
    decision = evaluate_pilot(
        pilot_prereg,
        {"profit_lift": 1.0, "wrong_family_exposure": 0.05},
        intervals={"profit_lift": (-0.1, 2.1), "wrong_family_exposure": (0.0, 0.20)},
        require_go_intervals=True,
    )
    assert not any(verdict.passed for verdict in decision.go)


def test_formal_pilot_requires_every_registered_metric() -> None:
    pilot_prereg = full_go_prereg()
    intervals = {item["id"]: (0.0, 1.0) for item in pilot_prereg.data["go_criteria"]}
    intervals.update(
        {
            item["id"]: (0.0, 1.0)
            for item in pilot_prereg.data["kill_triggers"]
            if item["id"] != "method_freeze_or_quarantine_violation"
        }
    )
    with pytest.raises(ValueError, match="missing estimates"):
        validate_pilot_metrics(pilot_prereg, {"profit_lift": 2.0})
    with pytest.raises(ValueError, match="every registered criterion"):
        evaluate_pilot(
            pilot_prereg,
            {"profit_lift": 2.0},
            intervals=intervals,
            require_go_intervals=True,
        )


def test_formal_pilot_requires_intervals_for_statistical_kill_triggers() -> None:
    pilot_prereg = full_go_prereg()
    go_intervals = {item["id"]: (0.0, 1.0) for item in pilot_prereg.data["go_criteria"]}
    with pytest.raises(ValueError, match="formal pilot criteria require intervals"):
        validate_pilot_intervals(pilot_prereg, go_intervals)


def test_kill_trigger_overrides_go() -> None:
    decision = evaluate_pilot(
        prereg(),
        {
            "profit_lift": 2.0,
            "lost_sales_reduction": 1.0,
            "negative_profit_lift": -0.1,
        },
    )
    assert decision.decision == "kill-or-reframe"


def test_quarantine_violation_can_trigger_without_a_numeric_threshold() -> None:
    data = prereg().data
    pilot_prereg = Preregistration(
        path=Path("prereg/prereg_v1.yaml"),
        data={
            **data,
            "kill_triggers": [
                {
                    "id": "method_freeze_or_quarantine_violation",
                    "threshold": "none",
                    "operator": "==",
                }
            ],
        },
    )
    decision = evaluate_pilot(
        pilot_prereg,
        {
            "profit_lift": 2.0,
            "lost_sales_reduction": 1.0,
            "method_freeze_or_quarantine_violation": 1.0,
        },
    )
    assert decision.decision == "kill-or-reframe"


def test_render_pilot_report_lists_all_registered_verdicts() -> None:
    decision = evaluate_pilot(prereg(), {"profit_lift": 0.0}, intervals={"profit_lift": (-1, 1)})
    report = render_pilot_report(decision, episodes=120)
    assert "Decision:" in report
    assert "ci_low" in report
    assert "`profit_lift`" in report
    assert "`negative_profit_lift`" in report
    assert "clear" in report


def test_pilot_record_count_uses_independent_units() -> None:
    good = tuple(
        replace(result(arm, 1.0, 0.0), independent_unit_id=f"u{i}")
        for i in range(100)
        for arm in ("arm10_spec_eprocess", "arm1_capped_base_stock")
    )
    validate_pilot_record_count(good)
    with pytest.raises(ValueError, match="100-150 independent units"):
        validate_pilot_record_count(good[:99])


def test_pilot_record_count_requires_paired_baseline_and_contribution_arms() -> None:
    unpaired = tuple(
        replace(result("arm10_spec_eprocess", 1.0, 0.0), independent_unit_id=f"u{i}")
        for i in range(100)
    )
    with pytest.raises(ValueError, match="paired contribution and baseline"):
        validate_pilot_record_count(unpaired)


def test_pilot_record_count_rejects_duplicate_unit_arm_rows() -> None:
    paired = tuple(
        replace(result(arm, 1.0, 0.0), independent_unit_id=f"u{i}")
        for i in range(100)
        for arm in ("arm10_spec_eprocess", "arm1_capped_base_stock")
    )
    with pytest.raises(ValueError, match="at most one row"):
        validate_pilot_record_count((*paired, paired[0]))


def test_formal_pilot_requires_registered_dev_cal_strata() -> None:
    preregistration = load_preregistration(require_final=False)
    families = tuple(family for family in ShockFamily if family is not ShockFamily.NO_CHANGE)
    conditions = tuple(InformationCondition)
    records = []
    for index in range(100):
        family = families[index % len(families)]
        condition = conditions[(index // len(families)) % len(conditions)]
        for arm in (
            "arm10_spec_eprocess",
            "arm1_capped_base_stock",
            "oracle_shockspec_headroom",
            "ctrl_cusum_to_compiler",
        ):
            records.append(
                replace(
                    result(arm, 1.0, 0.0),
                    independent_unit_id=f"u{index}",
                    split=Split.DEV if index % 2 == 0 else Split.CAL,
                    family=family,
                    information_condition=condition,
                )
            )
    validate_pilot_record_count(tuple(records), prereg=preregistration)
    with pytest.raises(ValueError, match="dev/cal"):
        validate_pilot_record_count(
            tuple(replace(item, split=Split.TEST) for item in records),
            prereg=preregistration,
        )


def test_pilot_manifest_captures_quarantined_seeds_and_templates(tmp_path) -> None:
    records_path = tmp_path / "records.jsonl"
    freeze_path = tmp_path / "freeze_manifest.json"
    manifest_path = tmp_path / "pilot_manifest.json"
    truth_path = tmp_path / "truth.jsonl"
    records_path.write_text('{"stub":true}\n', encoding="utf-8")
    freeze_path.write_text('{"manifest_sha256":"stub"}\n', encoding="utf-8")
    truth_path.write_text('{"truth":true}\n', encoding="utf-8")
    pilot_result = result("arm10_spec_eprocess", 12.0, 0.0)
    pilot_result = replace(
        pilot_result,
        episode_id="episode-1",
        independent_unit_id="seed-1",
        records=(record("template-a"), record("template-b")),
    )

    manifest = pilot_manifest_from_records(
        (pilot_result,),
        requested_episodes=120,
        freeze_manifest_path=freeze_path,
        records_path=records_path,
        truth_path=truth_path,
    )
    write_pilot_manifest(manifest_path, manifest)

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["seeds"] == ["seed-1"]
    assert payload["templates"] == ["template-a", "template-b"]
    assert payload["observed_episode_results"] == 1
    assert payload["freeze_manifest_sha256"]
    assert payload["records_sha256"]
    assert payload["truth_sha256"]


def test_pilot_cli_rejects_untraceable_metric_overrides() -> None:
    with pytest.raises(SystemExit):
        main(["--episodes", "120", "--metrics", "metrics.json"])


def test_quarantine_rejects_incomplete_freeze(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        run_pilot,
        "load_freeze",
        lambda: {
            "complete": False,
            "incomplete_reasons": ["missing registered files: missing.py"],
        },
    )
    with pytest.raises(SystemExit, match="method freeze is incomplete"):
        run_pilot._quarantine_check(tmp_path / "pilot_manifest.json")
