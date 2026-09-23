from __future__ import annotations

import json

import pytest

from collie.contracts import (
    AnalysisClass,
    CallLog,
    EpisodeResult,
    InformationCondition,
    ParseOutcome,
    RunRecord,
    ShockFamily,
    Split,
)
from collie.eval.prereg import Preregistration
from collie.eval.records import write_episode_results_jsonl
from collie.eval.report import (
    assert_report_tables_trace_to_records,
    render_compatibility_table,
    render_efficiency_table,
    render_frontier_table,
    render_main_table,
    render_operational_table,
    report_manifest,
    write_report_artifacts,
)


def result(
    arm: str, unit: str, profit: float, *, calls: int = 0, split: Split | None = None
) -> EpisodeResult:
    return EpisodeResult(
        episode_id=f"e-{unit}-{arm}",
        arm_id=arm,
        total_profit=profit,
        total_holding_cost=0.0,
        total_reward=profit,
        total_demand=100.0,
        total_sold=100.0,
        total_lost_sales=0.0,
        perfect_foresight=100.0,
        normalized_reward=profit / 100.0,
        calls=tuple(
            CallLog(
                call_id=f"call-{arm}-{i}",
                arm_id=arm,
                episode_id=f"e-{unit}-{arm}",
                period=i + 1,
                model_id="fake",
                prompt_hash="p",
                decoding_hash="d",
                attempt_index=1,
                outcome=ParseOutcome.ACCEPTED,
                input_tokens=10,
                output_tokens=5,
                usd_cost=0.01,
            )
            for i in range(calls)
        ),
        independent_unit_id=unit,
        split=split,
        family=ShockFamily.DEMAND_LEVEL,
        information_condition=InformationCondition.NO_ALERT,
    )


def period_record(period: int, sold: float, *, on_hand_end: float = 0.0) -> RunRecord:
    return RunRecord(
        episode_id="e",
        arm_id="arm",
        period=period,
        date=f"p{period}",
        on_hand_start=0.0,
        in_transit_start=0.0,
        order_quantity=0.0,
        arrivals=0.0,
        demand=100.0,
        units_sold=sold,
        lost_sales=100.0 - sold,
        on_hand_end=on_hand_end,
        period_profit=sold,
        period_holding=0.0,
    )


def prereg() -> Preregistration:
    return Preregistration(
        path=__file__,
        data={
            "stratum_weights": {
                "family": {"demand_level": 1.0},
                "information_condition": {"no_alert": 1.0},
            },
            "confirmatory_contrasts": [
                {
                    "id": "arm10_vs_arm1",
                    "treatment": "arm10_spec_eprocess",
                    "control": "arm1_capped_base_stock",
                }
            ],
            "holm_family": {
                "members": [
                    {
                        "id": "arm10_vs_arm1:profit",
                        "contrast": "arm10_vs_arm1",
                        "endpoint": "cumulative_undiscounted_profit",
                    }
                ]
            },
        },
    )


def test_confirmatory_report_uses_registered_holm_ids() -> None:
    table = render_main_table(
        (
            result("arm10_spec_eprocess", "u1", 12.0),
            result("arm1_capped_base_stock", "u1", 10.0),
        ),
        analysis_class=AnalysisClass.CONFIRMATORY,
        prereg=prereg(),
    )
    assert "`arm10_vs_arm1:profit`" in table
    assert "paired_randomization_p" in table
    assert "cluster_bootstrap_ci" in table
    assert "holm_p" in table
    assert "wilcoxon_p" in table
    assert " 2 " in table
    assert "source" in table


def test_report_renders_from_stored_records(tmp_path) -> None:
    path = tmp_path / "records.jsonl"
    results = (
        result("arm10_spec_eprocess", "u1", 12.0),
        result("arm1_capped_base_stock", "u1", 10.0),
    )
    write_episode_results_jsonl(path, results)

    from collie.eval.records import load_episode_results_jsonl

    table = render_main_table(load_episode_results_jsonl(path), prereg=prereg())
    assert "`arm10_spec_eprocess`" in table
    assert "cumulative_undiscounted_profit" in table


def test_report_source_digest_changes_when_record_values_change() -> None:
    left = render_main_table((result("arm", "u1", 12.0),), prereg=prereg())
    right = render_main_table((result("arm", "u1", 13.0),), prereg=prereg())
    assert "records_sha256=" in left
    assert left != right


def test_frontier_table_uses_realised_call_budgets() -> None:
    table = render_frontier_table(
        (
            result("cheap", "u1", 10.0, calls=1),
            result("expensive", "u1", 12.0, calls=3),
        ),
        budget="calls",
    )
    assert "profit_vs_calls" in table
    assert "`cheap`" in table
    assert "`expensive`" in table


def test_write_report_artifacts_writes_tables_and_svg_plots(tmp_path) -> None:
    written = write_report_artifacts(
        (
            result("cheap", "u1", 10.0, calls=1),
            result("expensive", "u1", 12.0, calls=3),
        ),
        prereg=prereg(),
        out_dir=tmp_path,
    )
    names = {path.name for path in written}
    assert "main_table.md" in names
    assert "operational.md" in names
    assert "compatibility.md" in names
    assert "frontier_calls.md" in names
    assert "frontier_calls.svg" in names
    assert "efficiency.md" in names
    assert "report_manifest.json" in names
    assert (tmp_path / "frontier_calls.svg").read_text(encoding="utf-8").startswith("<svg")
    manifest = json.loads((tmp_path / "report_manifest.json").read_text(encoding="utf-8"))
    assert manifest["record_count"] == 2
    assert manifest["records_sha256"]
    assert {artifact["path"].split("\\")[-1] for artifact in manifest["artifacts"]} >= {
        "main_table.md",
        "frontier_calls.svg",
    }
    assert_report_tables_trace_to_records(written)


def test_write_report_artifacts_passes_compatibility_options(tmp_path) -> None:
    written = write_report_artifacts(
        (
            result("arm", "u1", 10.0, split=Split.DEV),
            result("arm", "u2", 30.0, split=Split.CAL),
        ),
        prereg=prereg(),
        out_dir=tmp_path,
        deployment_weights={"dev": 0.70, "cal": 0.15},
        deployment_field="split",
        harness="eval",
    )
    assert any(path.name == "report_manifest.json" for path in written)
    compatibility = (tmp_path / "compatibility.md").read_text(encoding="utf-8")
    assert "official_normalized_reward_split_mixture" in compatibility
    assert "`eval`" in compatibility
    manifest = json.loads((tmp_path / "report_manifest.json").read_text(encoding="utf-8"))
    assert manifest["compatibility_options"]["deployment_field"] == "split"
    assert manifest["compatibility_options"]["deployment_weights"] == {
        "cal": 0.15,
        "dev": 0.70,
    }


def test_report_trace_guard_rejects_hand_entered_table_value(tmp_path) -> None:
    path = tmp_path / "manual.md"
    path.write_text(
        "\n".join(
            [
                "| arm | metric | value | source |",
                "|---|---|---:|---|",
                "| `a` | profit | 1.23 | analyst note |",
                "",
            ]
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="lack record provenance"):
        assert_report_tables_trace_to_records((path,))


def test_report_manifest_hashes_record_contents() -> None:
    left = report_manifest(
        (result("arm", "u1", 12.0),),
        artifacts=(),
        records_path=None,
        prereg=prereg(),
    )
    right = report_manifest(
        (result("arm", "u1", 13.0),),
        artifacts=(),
        records_path=None,
        prereg=prereg(),
    )
    assert left["records_sha256"] != right["records_sha256"]


def test_efficiency_table_reports_auc_and_matched_budget_points() -> None:
    table = render_efficiency_table(
        (
            result("arm10_spec_eprocess", "u1", 12.0, calls=2),
            result("arm1_capped_base_stock", "u1", 10.0, calls=0),
        )
    )
    assert "auc_call_fraction" in table
    assert "token_frontier_profit" in table
    assert "dollar_frontier_profit" in table
    assert "repair_calls" in table
    assert "rejected_calls" in table
    assert "latency_p50_ms" in table
    assert "latency_p95_ms" in table
    assert "actions_per_accepted_call" in table
    matched_rows = [line for line in table.splitlines() if line.startswith("| matched_budget")]
    assert matched_rows
    assert all("`arm1_capped_base_stock`" in line for line in matched_rows)


def test_operational_table_renders_metrics() -> None:
    table = render_operational_table((result("arm", "u1", 12.0),))
    assert "cvar10_profit" in table
    assert "fill_rate" in table


def test_operational_table_renders_recovery_inventory_with_sidecar() -> None:
    records = tuple(
        period_record(t, float(s), on_hand_end=20.0)
        for t, s in enumerate([100, 70, 95, 94, 96, 97, 98], start=1)
    )
    episode = result("arm", "u1", 12.0)
    episode = EpisodeResult(
        episode_id="e",
        arm_id=episode.arm_id,
        total_profit=episode.total_profit,
        total_holding_cost=episode.total_holding_cost,
        total_reward=episode.total_reward,
        total_demand=episode.total_demand,
        total_sold=episode.total_sold,
        total_lost_sales=episode.total_lost_sales,
        perfect_foresight=episode.perfect_foresight,
        normalized_reward=episode.normalized_reward,
        records=records,
        independent_unit_id=episode.independent_unit_id,
        family=episode.family,
        information_condition=episode.information_condition,
    )
    table = render_operational_table(
        (episode,), shock_periods={"e": 2}, baseline_inventory={"e": 10.0}
    )
    assert "time_to_recovery" in table
    assert "post_recovery_excess_inventory" in table


def test_compatibility_table_labels_the_harness() -> None:
    table = render_compatibility_table((result("arm", "u1", 12.0),), harness="eval")
    assert "official_normalized_reward_micro" in table
    assert "`eval`" in table
