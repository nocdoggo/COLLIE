from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

import tools.run_pilot as run_pilot
from collie.contracts import CallLog, EpisodeResult, ParseOutcome, RunRecord, ShockFamily
from collie.eval.pilot import (
    compute_builtin_pilot_intervals,
    compute_builtin_pilot_metrics,
    evaluate_pilot,
    pilot_manifest_from_records,
    render_pilot_report,
    validate_go_intervals,
    validate_pilot_record_count,
    write_pilot_manifest,
)
from collie.eval.prereg import Preregistration
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


def call(outcome: ParseOutcome) -> CallLog:
    return CallLog(
        call_id=f"call-{outcome.value}",
        arm_id="arm10_shockspec_eprocess",
        episode_id="e",
        period=1,
        model_id="fake",
        prompt_hash="p",
        decoding_hash="d",
        attempt_index=1,
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


def period_record(period: int, sold: float, *, active_spec_id: str | None = None) -> RunRecord:
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
    )


def test_builtin_pilot_metrics_from_episode_results() -> None:
    metrics = compute_builtin_pilot_metrics(
        (
            result("arm10_shockspec_eprocess", 12.0, 3.0),
            result("arm1_capped_base_stock", 10.0, 5.0),
        )
    )
    assert metrics["profit_lift"] == 2.0
    assert metrics["lost_sales_reduction"] == 2.0
    assert "budget_overrun_rate" not in metrics


def test_builtin_pilot_metrics_from_calls_and_null_activations() -> None:
    null_result = replace(
        result("arm10_shockspec_eprocess", 12.0, 0.0),
        family=ShockFamily.NO_CHANGE,
        records=(period_record(1, 100.0, active_spec_id="wrong"),),
        calls=(call(ParseOutcome.ACCEPTED), call(ParseOutcome.FALLBACK)),
    )
    metrics = compute_builtin_pilot_metrics((null_result,))
    assert metrics["parser_failure_rate"] == 0.5
    assert metrics["false_activation_rate"] == 1.0
    assert metrics["false_activation_control"] == 0.0


def test_builtin_pilot_metrics_compute_recovery_time_from_sidecar() -> None:
    sold = [100, 70, 95, 94, 96, 97, 98]
    pilot_result = replace(
        result("arm10_shockspec_eprocess", 12.0, 0.0),
        episode_id="e",
        records=tuple(period_record(t, float(s)) for t, s in enumerate(sold, start=1)),
    )
    metrics = compute_builtin_pilot_metrics((pilot_result,), shock_periods={"e": 2})
    intervals = compute_builtin_pilot_intervals((pilot_result,), shock_periods={"e": 2})
    assert metrics["recovery_time"] == 3.0
    assert intervals["recovery_time"] == (3.0, 3.0)


def test_builtin_pilot_intervals_use_paired_records() -> None:
    paired_results = []
    for unit, arm10_profit, arm1_profit in (("u1", 12.0, 10.0), ("u2", 16.0, 13.0)):
        paired_results.append(
            replace(
                result("arm10_shockspec_eprocess", arm10_profit, 3.0),
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


def test_budget_overrun_rate_requires_a_registered_budget() -> None:
    metrics = compute_builtin_pilot_metrics(
        (
            result("arm10_shockspec_eprocess", 12.0, 3.0),
            result("arm1_capped_base_stock", 10.0, 5.0),
        ),
        call_budget_per_episode=0,
    )
    assert metrics["budget_overrun_rate"] == 0.0


def test_builtin_pilot_metrics_report_cost_frontier_status() -> None:
    arm10 = replace(
        result("arm10_shockspec_eprocess", 12.0, 0.0),
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


def test_render_pilot_report_lists_all_registered_verdicts() -> None:
    decision = evaluate_pilot(prereg(), {"profit_lift": 0.0}, intervals={"profit_lift": (-1, 1)})
    report = render_pilot_report(decision, episodes=120)
    assert "Decision:" in report
    assert "ci_low" in report
    assert "`profit_lift`" in report
    assert "`negative_profit_lift`" in report


def test_pilot_record_count_uses_independent_units() -> None:
    good = tuple(
        replace(result(arm, 1.0, 0.0), independent_unit_id=f"u{i}")
        for i in range(100)
        for arm in ("arm10_shockspec_eprocess", "arm1_capped_base_stock")
    )
    validate_pilot_record_count(good)
    with pytest.raises(ValueError, match="100-150 independent units"):
        validate_pilot_record_count(good[:99])


def test_pilot_record_count_requires_paired_baseline_and_contribution_arms() -> None:
    unpaired = tuple(
        replace(result("arm10_shockspec_eprocess", 1.0, 0.0), independent_unit_id=f"u{i}")
        for i in range(100)
    )
    with pytest.raises(ValueError, match="paired contribution and baseline"):
        validate_pilot_record_count(unpaired)


def test_pilot_manifest_captures_quarantined_seeds_and_templates(tmp_path) -> None:
    records_path = tmp_path / "records.jsonl"
    freeze_path = tmp_path / "freeze_manifest.json"
    manifest_path = tmp_path / "pilot_manifest.json"
    records_path.write_text('{"stub":true}\n', encoding="utf-8")
    freeze_path.write_text('{"manifest_sha256":"stub"}\n', encoding="utf-8")
    pilot_result = result("arm10_shockspec_eprocess", 12.0, 0.0)
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
    )
    write_pilot_manifest(manifest_path, manifest)

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["seeds"] == ["seed-1"]
    assert payload["templates"] == ["template-a", "template-b"]
    assert payload["observed_episode_results"] == 1
    assert payload["freeze_manifest_sha256"]
    assert payload["records_sha256"]


def test_pilot_cli_rejects_metrics_without_records(tmp_path) -> None:
    metrics_path = tmp_path / "metrics.json"
    metrics_path.write_text('{"profit_lift": 1.0}', encoding="utf-8")
    with pytest.raises(SystemExit, match="cannot drive a formal pilot verdict"):
        main(["--episodes", "120", "--metrics", str(metrics_path)])


def test_quarantine_rejects_incomplete_freeze(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        run_pilot,
        "load_freeze",
        lambda: {"complete": False, "files": {"missing.py": {"missing": True}}},
    )
    with pytest.raises(SystemExit, match="method freeze is incomplete"):
        run_pilot._quarantine_check(tmp_path / "pilot_manifest.json")
