"""Render evaluation tables from stored records."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from collie.arms.shockspec import ARM10_ARM_ID
from collie.contracts import AnalysisClass, EpisodeResult, Split
from collie.eval.efficiency import (
    FrontierPoint,
    auc_over_call_fraction,
    efficiency_summary,
    frontier_from_results,
    pareto_frontier,
)
from collie.eval.endpoints import compatibility_summaries, stratum_weighted_endpoints
from collie.eval.guards import assert_confirmatory_registered
from collie.eval.intervals import (
    PairedInterval,
    bootstrap_paired_interval,
    holm_adjust,
    paired_differences,
    paired_randomization_pvalue,
    stratum_weighted_paired_interval,
    wilcoxon_signed_rank_pvalue,
)
from collie.eval.operational import operational_summaries
from collie.eval.prereg import Preregistration, load_preregistration, primary_stratum_weights
from collie.eval.records import episode_result_to_dict, load_episode_results_jsonl

__all__ = [
    "assert_report_tables_trace_to_records",
    "render_compatibility_table",
    "render_confirmatory_contrasts",
    "render_efficiency_table",
    "render_frontier_table",
    "render_main_table",
    "render_operational_table",
    "report_manifest",
    "write_frontier_svg",
    "write_report_artifacts",
]


def _file_sha256(path: Path | None) -> str | None:
    if path is None or not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _records_sha256(results: Sequence[EpisodeResult]) -> str:
    payloads = [episode_result_to_dict(result) for result in results]
    payloads.sort(key=lambda item: (str(item["episode_id"]), str(item["arm_id"])))
    encoded = json.dumps(payloads, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _provenance(results: Sequence[EpisodeResult], arms: set[str] | None = None) -> str:
    payloads = [
        episode_result_to_dict(result)
        for result in results
        if arms is None or result.arm_id in arms
    ]
    payloads.sort(key=lambda item: (str(item["episode_id"]), str(item["arm_id"])))
    encoded = json.dumps(payloads, sort_keys=True, separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()[:12]
    return f"n={len(payloads)};records_sha256={digest}"


def report_manifest(
    results: Sequence[EpisodeResult],
    *,
    artifacts: Sequence[Path],
    records_path: Path | None,
    prereg: Preregistration,
    freeze_path: Path | None = None,
    compatibility_options: dict[str, object] | None = None,
) -> dict[str, object]:
    """Build the audit manifest for rendered report artifacts."""
    return {
        "schema_version": 1,
        "record_count": len(results),
        "independent_unit_count": len(
            {result.independent_unit_id for result in results if result.independent_unit_id}
        ),
        "records_path": None if records_path is None else str(records_path),
        "records_sha256": _records_sha256(results),
        "records_file_sha256": _file_sha256(records_path),
        "prereg_path": str(prereg.path),
        "prereg_file_sha256": _file_sha256(Path(prereg.path)),
        "freeze_path": None if freeze_path is None else str(freeze_path),
        "freeze_file_sha256": _file_sha256(freeze_path),
        "compatibility_options": compatibility_options or {},
        "artifacts": [
            {
                "path": str(path),
                "sha256": _file_sha256(path),
            }
            for path in artifacts
        ],
    }


def assert_report_tables_trace_to_records(paths: Sequence[Path]) -> None:
    """Require every markdown report table data row to carry a records_sha256 source."""
    violations: list[str] = []
    for path in paths:
        if path.suffix.lower() != ".md":
            continue
        current_header: list[str] | None = None
        for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            line = raw.strip()
            if not line.startswith("|") or not line.endswith("|"):
                continue
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if all(set(cell) <= {"-", ":"} for cell in cells):
                continue
            if "source" in cells:
                current_header = cells
                continue
            if current_header is None:
                continue
            try:
                source = cells[current_header.index("source")]
            except IndexError:
                source = ""
            if "records_sha256=" not in source:
                violations.append(f"{path}:{line_no}")
    if violations:
        raise ValueError(
            "reported markdown table rows lack record provenance: " + ", ".join(violations)
        )


@dataclass(frozen=True, slots=True)
class _ConfirmatoryRow:
    analysis_id: str
    treatment: str
    control: str
    endpoint: str
    source: str
    interval: PairedInterval
    differences: tuple[float, ...]
    n_units: int


def render_confirmatory_contrasts(
    results: Sequence[EpisodeResult],
    prereg: Preregistration,
    *,
    analysis_class: AnalysisClass,
) -> str:
    """Render the registered contrast x endpoint rows using frozen Holm identifiers."""
    endpoint_rows = stratum_weighted_endpoints(results, primary_stratum_weights(prereg.data))
    contrasts = {item["id"]: item for item in prereg.data["confirmatory_contrasts"]}

    lines = [
        "| analysis_class | analysis_id | treatment | control | endpoint | "
        "estimate_ci | cluster_bootstrap_ci | paired_randomization_p | holm_p | "
        "wilcoxon_p | n_units | source |",
        "|---|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    rendered: list[_ConfirmatoryRow] = []
    for member in prereg.data["holm_family"]["members"]:
        analysis_id = str(member["id"])
        assert_confirmatory_registered(analysis_id, analysis_class, prereg)
        contrast = contrasts[str(member["contrast"])]
        endpoint = str(member["endpoint"])
        treatment = str(contrast["treatment"])
        control = str(contrast["control"])
        interval = stratum_weighted_paired_interval(
            results,
            treatment=treatment,
            control=control,
            endpoint=endpoint,
            weights=primary_stratum_weights(prereg.data),
        )
        diffs = paired_differences(results, treatment=treatment, control=control, endpoint=endpoint)
        n_units = min(
            row.n_units
            for row in endpoint_rows
            if row.endpoint == endpoint and row.arm in {treatment, control}
        )
        rendered.append(
            _ConfirmatoryRow(
                analysis_id=analysis_id,
                treatment=treatment,
                control=control,
                endpoint=endpoint,
                source=_provenance(results, {treatment, control}),
                interval=interval,
                differences=diffs,
                n_units=n_units,
            )
        )
    randomization_p = {
        row.analysis_id: paired_randomization_pvalue(row.differences) for row in rendered
    }
    holm_p = holm_adjust(randomization_p)
    for row in rendered:
        bootstrap_low, bootstrap_high = bootstrap_paired_interval(
            row.differences,
            seed=int(hashlib.sha256(row.analysis_id.encode("utf-8")).hexdigest()[:8], 16),
        )
        lines.append(
            f"| {analysis_class.value} | `{row.analysis_id}` | `{row.treatment}` | "
            f"`{row.control}` | {row.endpoint} | {row.interval.estimate:.6g} "
            f"[{row.interval.ci_low:.6g}, {row.interval.ci_high:.6g}] | "
            f"[{bootstrap_low:.6g}, {bootstrap_high:.6g}] | "
            f"{randomization_p[row.analysis_id]:.6g} | {holm_p[row.analysis_id]:.6g} | "
            f"{wilcoxon_signed_rank_pvalue(row.differences):.6g} | "
            f"{row.n_units} | {row.source} |"
        )
    return "\n".join(lines) + "\n"


def render_main_table(
    results: Sequence[EpisodeResult],
    *,
    analysis_class: AnalysisClass = AnalysisClass.EXPLORATORY,
    prereg: Preregistration | None = None,
) -> str:
    prereg = prereg or load_preregistration(require_final=False)
    if analysis_class is AnalysisClass.CONFIRMATORY:
        return render_confirmatory_contrasts(results, prereg, analysis_class=analysis_class)

    rows = stratum_weighted_endpoints(results, primary_stratum_weights(prereg.data))
    lines = [
        "| analysis_class | arm | endpoint | value | n_units | source |",
        "|---|---:|---|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            f"| {analysis_class.value} | `{row.arm}` | {row.endpoint} | "
            f"{row.value:.6g} | {row.n_units} | {_provenance(results, {row.arm})} |"
        )
    return "\n".join(lines) + "\n"


def _budget_points(results: Sequence[EpisodeResult], kind: str) -> tuple[FrontierPoint, ...]:
    def calls(group: Sequence[EpisodeResult]) -> float:
        return float(sum(len(result.calls) for result in group))

    def tokens(group: Sequence[EpisodeResult]) -> float:
        return float(
            sum(log.input_tokens + log.output_tokens for result in group for log in result.calls)
        )

    def cost(group: Sequence[EpisodeResult]) -> float:
        return float(sum(log.usd_cost for result in group for log in result.calls))

    budgets = {"calls": calls, "tokens": tokens, "cost": cost}
    return frontier_from_results(results, budgets[kind])


def render_frontier_table(results: Sequence[EpisodeResult], *, budget: str) -> str:
    """Render realised-budget frontier points for one budget axis."""
    frontier = pareto_frontier(_budget_points(results, budget))
    lines = [
        f"| frontier | arm | mean_profit | realised_{budget} | source |",
        "|---|---:|---:|---:|---|",
    ]
    for point in frontier:
        lines.append(
            f"| profit_vs_{budget} | `{point.arm}` | {point.reward:.6g} | "
            f"{point.budget:.6g} | {_provenance(results, {point.arm})} |"
        )
    return "\n".join(lines) + "\n"


def _matched_budget_point(points: Sequence[FrontierPoint], *, reference_arm: str) -> FrontierPoint:
    if not points:
        raise ValueError("cannot match budget over no points")
    reference = next((point for point in points if point.arm == reference_arm), None)
    if reference is None:
        return min(points, key=lambda point: point.budget)
    candidates = [point for point in points if point.arm != reference_arm]
    if not candidates:
        return reference
    return min(candidates, key=lambda point: abs(point.budget - reference.budget))


def render_efficiency_table(
    results: Sequence[EpisodeResult], *, reference_arm: str = ARM10_ARM_ID
) -> str:
    """Render ledger summaries plus registered frontier diagnostics."""
    summaries = efficiency_summary(results)
    call_frontier = pareto_frontier(_budget_points(results, "calls"))
    token_match = _matched_budget_point(
        _budget_points(results, "tokens"), reference_arm=reference_arm
    )
    cost_match = _matched_budget_point(_budget_points(results, "cost"), reference_arm=reference_arm)
    lines = [
        "| section | arm | metric | value | source |",
        "|---|---:|---|---:|---|",
    ]
    for summary in summaries:
        actions_per_call = (
            "n/a"
            if summary.actions_per_accepted_call is None
            else f"{summary.actions_per_accepted_call:.6g}"
        )
        lines.extend(
            [
                f"| ledger | `{summary.arm}` | attempted_calls | {summary.attempted_calls} | "
                f"{_provenance(results, {summary.arm})} |",
                f"| ledger | `{summary.arm}` | repair_calls | {summary.repair_calls} | "
                f"{_provenance(results, {summary.arm})} |",
                f"| ledger | `{summary.arm}` | rejected_calls | {summary.rejected_calls} | "
                f"{_provenance(results, {summary.arm})} |",
                f"| ledger | `{summary.arm}` | input_tokens | {summary.input_tokens} | "
                f"{_provenance(results, {summary.arm})} |",
                f"| ledger | `{summary.arm}` | output_tokens | {summary.output_tokens} | "
                f"{_provenance(results, {summary.arm})} |",
                f"| ledger | `{summary.arm}` | latency_p50_ms | "
                f"{summary.latency_p50_ms:.6g} | {_provenance(results, {summary.arm})} |",
                f"| ledger | `{summary.arm}` | latency_p95_ms | "
                f"{summary.latency_p95_ms:.6g} | {_provenance(results, {summary.arm})} |",
                f"| ledger | `{summary.arm}` | usd_cost | {summary.usd_cost:.6g} | "
                f"{_provenance(results, {summary.arm})} |",
                f"| ledger | `{summary.arm}` | actions_per_accepted_call | "
                f"{actions_per_call} | {_provenance(results, {summary.arm})} |",
            ]
        )
    lines.append(
        f"| frontier | `all` | auc_call_fraction | {auc_over_call_fraction(call_frontier):.6g} | "
        f"{_provenance(results)} |"
    )
    lines.append(
        f"| matched_budget | `{token_match.arm}` | token_frontier_profit | "
        f"{token_match.reward:.6g} | {_provenance(results, {token_match.arm})} |"
    )
    lines.append(
        f"| matched_budget | `{cost_match.arm}` | dollar_frontier_profit | "
        f"{cost_match.reward:.6g} | {_provenance(results, {cost_match.arm})} |"
    )
    return "\n".join(lines) + "\n"


def render_operational_table(
    results: Sequence[EpisodeResult],
    *,
    shock_periods: dict[str, int] | None = None,
    baseline_inventory: dict[str, float] | None = None,
) -> str:
    """Render operational metrics by arm."""
    lines = [
        "| arm | metric | value | n_episodes | source |",
        "|---:|---|---:|---:|---|",
    ]
    for row in operational_summaries(
        results, shock_periods=shock_periods, baseline_inventory=baseline_inventory
    ):
        lines.append(
            f"| `{row.arm}` | {row.metric} | {row.value:.6g} | {row.n_episodes} | "
            f"{_provenance(results, {row.arm})} |"
        )
    return "\n".join(lines) + "\n"


def render_compatibility_table(
    results: Sequence[EpisodeResult],
    *,
    deployment_weights: dict[str, float] | None = None,
    deployment_field: str = "split",
    harness: str = "eval",
) -> str:
    """Render official normalized-reward compatibility metrics with harness labels."""
    rows = compatibility_summaries(
        results,
        deployment_weights=deployment_weights,
        deployment_field=deployment_field,
        harness=harness,
    )
    lines = [
        "| arm | metric | value | n_units | harness | source |",
        "|---:|---|---:|---:|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| `{row.arm}` | {row.metric} | {row.value:.6g} | {row.n_units} | "
            f"`{row.harness}` | {_provenance(results, {row.arm})} |"
        )
    return "\n".join(lines) + "\n"


def write_frontier_svg(path: Path, points: Sequence[FrontierPoint], *, title: str) -> None:
    """Write a small dependency-free SVG plot for a realised-budget frontier."""
    path.parent.mkdir(parents=True, exist_ok=True)
    frontier = pareto_frontier(points)
    width, height = 640, 420
    left, right, top, bottom = 70, 30, 40, 60
    max_budget = max((point.budget for point in points), default=1.0) or 1.0
    profits = [point.reward for point in points] or [0.0]
    min_profit, max_profit = min(profits), max(profits)
    span_profit = max(max_profit - min_profit, 1.0)

    def x(value: float) -> float:
        return left + (value / max_budget) * (width - left - right)

    def y(value: float) -> float:
        frac = (value - min_profit) / span_profit
        return height - bottom - frac * (height - top - bottom)

    circles = []
    for point in points:
        fill = "#1b6f6a" if point in frontier else "#9aa5b1"
        circles.append(
            f'<circle cx="{x(point.budget):.2f}" cy="{y(point.reward):.2f}" r="5" '
            f'fill="{fill}"><title>{point.arm}: {point.reward:.3g}</title></circle>'
        )
    polyline = " ".join(f"{x(p.budget):.2f},{y(p.reward):.2f}" for p in frontier)
    path.write_text(
        "\n".join(
            [
                f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
                f'viewBox="0 0 {width} {height}">',
                f"<title>{title}</title>",
                '<rect width="100%" height="100%" fill="white"/>',
                f'<text x="{left}" y="24" font-family="Arial" font-size="16">{title}</text>',
                f'<line x1="{left}" y1="{height - bottom}" x2="{width - right}" '
                f'y2="{height - bottom}" stroke="#222"/>',
                f'<line x1="{left}" y1="{top}" x2="{left}" y2="{height - bottom}" stroke="#222"/>',
                f'<polyline points="{polyline}" fill="none" stroke="#1b6f6a" stroke-width="2"/>',
                *circles,
                f'<text x="{width / 2:.0f}" y="{height - 18}" font-family="Arial" '
                f'font-size="12">Realised budget</text>',
                f'<text x="12" y="{height / 2:.0f}" font-family="Arial" font-size="12" '
                f'transform="rotate(-90 12 {height / 2:.0f})">Mean profit</text>',
                "</svg>",
                "",
            ]
        ),
        encoding="utf-8",
    )


def write_report_artifacts(
    results: Sequence[EpisodeResult],
    *,
    prereg: Preregistration,
    out_dir: Path,
    analysis_class: AnalysisClass = AnalysisClass.EXPLORATORY,
    shock_periods: dict[str, int] | None = None,
    baseline_inventory: dict[str, float] | None = None,
    records_path: Path | None = None,
    freeze_path: Path | None = Path("prereg") / "freeze_manifest.json",
    deployment_weights: dict[str, float] | None = None,
    deployment_field: str = "split",
    harness: str = "eval",
) -> tuple[Path, ...]:
    """Write the main table and realised-budget frontier tables/plots."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    main_path = out_dir / "main_table.md"
    main_path.write_text(
        render_main_table(results, analysis_class=analysis_class, prereg=prereg),
        encoding="utf-8",
    )
    written.append(main_path)
    operational_path = out_dir / "operational.md"
    operational_path.write_text(
        render_operational_table(
            results,
            shock_periods=shock_periods,
            baseline_inventory=baseline_inventory,
        ),
        encoding="utf-8",
    )
    written.append(operational_path)
    compatibility_path = out_dir / "compatibility.md"
    compatibility_path.write_text(
        render_compatibility_table(
            results,
            deployment_weights=deployment_weights,
            deployment_field=deployment_field,
            harness=harness,
        ),
        encoding="utf-8",
    )
    written.append(compatibility_path)
    for budget in ("calls", "tokens", "cost"):
        table_path = out_dir / f"frontier_{budget}.md"
        table_path.write_text(render_frontier_table(results, budget=budget), encoding="utf-8")
        written.append(table_path)
        svg_path = out_dir / f"frontier_{budget}.svg"
        write_frontier_svg(
            svg_path,
            _budget_points(results, budget),
            title=f"Profit vs realised {budget}",
        )
        written.append(svg_path)
    efficiency_path = out_dir / "efficiency.md"
    efficiency_path.write_text(render_efficiency_table(results), encoding="utf-8")
    written.append(efficiency_path)
    assert_report_tables_trace_to_records(written)
    manifest_path = out_dir / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            report_manifest(
                results,
                artifacts=written,
                records_path=records_path,
                prereg=prereg,
                freeze_path=freeze_path,
                compatibility_options={
                    "deployment_field": deployment_field,
                    "deployment_weights": deployment_weights,
                    "harness": harness,
                },
            ),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    written.append(manifest_path)
    return tuple(written)


def _filter_split(results: Sequence[EpisodeResult], split: str) -> tuple[EpisodeResult, ...]:
    try:
        requested = Split(split)
    except ValueError:
        requested = None
    if requested is None:
        return tuple(results)
    filtered = tuple(result for result in results if result.split is requested)
    return filtered if filtered else tuple(results)


def _load_int_mapping(path: Path | None) -> dict[str, int] | None:
    if path is None:
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"{path} must contain a JSON object")
    return {str(key): int(value) for key, value in payload.items()}


def _load_float_mapping(path: Path | None) -> dict[str, float] | None:
    if path is None:
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"{path} must contain a JSON object")
    return {str(key): float(value) for key, value in payload.items()}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--table", choices=["main"], default="main")
    ap.add_argument("--split", default="dev")
    ap.add_argument("--records", type=Path)
    ap.add_argument("--out-dir", type=Path, default=Path("reports") / "eval")
    ap.add_argument(
        "--shock-periods",
        type=Path,
        help="JSON object mapping episode_id to shock period for recovery metrics",
    )
    ap.add_argument(
        "--baseline-inventory",
        type=Path,
        help="JSON object mapping episode_id to baseline inventory for excess-inventory metrics",
    )
    ap.add_argument(
        "--deployment-weights",
        type=Path,
        help="JSON object of prevalence weights for compatibility normalized reward",
    )
    ap.add_argument(
        "--deployment-field",
        default="split",
        help="record field used by --deployment-weights; defaults to split",
    )
    ap.add_argument(
        "--harness",
        default="eval",
        help="harness label for compatibility metrics; defaults to eval",
    )
    args = ap.parse_args(argv)

    prereg = load_preregistration(require_final=False)
    if args.records is None:
        print(
            "collie.eval.report is wired, but no stored run-record file was supplied. "
            "Module 06 must produce EpisodeResult records before the main table can render."
        )
        return 2
    results = _filter_split(load_episode_results_jsonl(args.records), args.split)
    shock_periods = _load_int_mapping(args.shock_periods)
    baseline_inventory = _load_float_mapping(args.baseline_inventory)
    deployment_weights = _load_float_mapping(args.deployment_weights)
    written = write_report_artifacts(
        results,
        prereg=prereg,
        out_dir=args.out_dir,
        shock_periods=shock_periods,
        baseline_inventory=baseline_inventory,
        records_path=args.records,
        deployment_weights=deployment_weights,
        deployment_field=args.deployment_field,
        harness=args.harness,
    )
    print(render_main_table(results, prereg=prereg))
    print("wrote:")
    for path in written:
        print(f"  {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
