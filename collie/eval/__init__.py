"""Branch H (P4). Endpoints, strata, operational and lifecycle metrics, frontiers, statistics."""

from collie.eval.endpoints import (
    CompatibilitySummary,
    EndpointSummary,
    aggregate_primary_endpoints,
    compatibility_summaries,
)
from collie.eval.guards import (
    assert_aggregation_unit_frame,
    assert_confirmatory_registered,
    classify_analysis,
)
from collie.eval.intervals import (
    PairedInterval,
    bootstrap_paired_interval,
    holm_adjust,
    paired_interval,
    paired_randomization_pvalue,
    stratum_weighted_paired_interval,
    wilcoxon_signed_rank_pvalue,
)
from collie.eval.pilot import (
    PilotDecision,
    PilotManifest,
    compute_builtin_pilot_intervals,
    evaluate_pilot,
    pilot_manifest_from_records,
    render_pilot_report,
    validate_pilot_record_count,
    write_pilot_manifest,
)
from collie.eval.prereg import Preregistration, load_preregistration
from collie.eval.records import load_episode_results_jsonl, write_episode_results_jsonl
from collie.eval.report import assert_report_tables_trace_to_records, report_manifest

__all__ = [
    "CompatibilitySummary",
    "EndpointSummary",
    "PairedInterval",
    "PilotDecision",
    "PilotManifest",
    "Preregistration",
    "aggregate_primary_endpoints",
    "assert_aggregation_unit_frame",
    "assert_confirmatory_registered",
    "assert_report_tables_trace_to_records",
    "bootstrap_paired_interval",
    "classify_analysis",
    "compatibility_summaries",
    "compute_builtin_pilot_intervals",
    "evaluate_pilot",
    "holm_adjust",
    "load_episode_results_jsonl",
    "load_preregistration",
    "paired_interval",
    "paired_randomization_pvalue",
    "pilot_manifest_from_records",
    "render_pilot_report",
    "report_manifest",
    "stratum_weighted_paired_interval",
    "validate_pilot_record_count",
    "wilcoxon_signed_rank_pvalue",
    "write_episode_results_jsonl",
    "write_pilot_manifest",
]
