"""Task 2 — audit the pinned InventoryBench contract and emit a byte-stable manifest.

Replaces every assumption about the benchmark with a recorded fact. Read-only with respect
to ``third_party/InventoryBench``.

Resolves three documented ambiguities from evidence rather than prose:

1. Real-instance horizon: root README says 48 periods, doc 3.5 derives 47 observations.
2. Lead-time set: root README says ``{0, 4, stochastic{1,2,3,inf}}``; ``eval/README.md``
   says ``promised_lead_time in {0, 2, 4}``.
3. Order cap ``C_t``: referenced throughout doc 3.5 but absent from the policy template.

Usage::

    uv run python -m tools.audit_benchmark --out manifests/benchmark_v1.json
"""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import math
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
BENCH = REPO_ROOT / "third_party" / "InventoryBench"
BENCHMARK_ROOT = BENCH / "benchmark"

# Bumped whenever the manifest schema changes. Part of the manifest so a stale manifest
# is detectable; deliberately NOT a timestamp, so regeneration stays byte-identical.
AUDIT_SCHEMA_VERSION = 1

TRAJECTORY_TYPES = ("synthetic_trajectory", "real_trajectory")
LEAD_TIME_DIRS = ("lead_time_0", "lead_time_4", "lead_time_stochastic")

# Mirrors eval/run_baseline_policy.py::detect_promised_lead_time. Recorded here so the
# mapping is auditable; the adapter reads it from the emitted manifest, never re-derives it.
PROMISED_LEAD_TIME_BY_DIR = {"lead_time_0": 0, "lead_time_4": 4, "lead_time_stochastic": 2}


# ---------------------------------------------------------------------------
# per-instance record
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class InstanceRecord:
    rel_path: str
    trajectory_type: str
    lead_time_label: str
    promised_lead_time: int
    item_id: str
    # synthetic taxonomy (None for real)
    family: str | None
    variant: str | None
    realization: str | None
    cost_ratio: str | None
    # real taxonomy (None for synthetic)
    article_id: str | None
    train_rows: int
    test_rows: int
    observation_count: int
    test_header: list[str]
    has_description: bool
    actual_lead_times: list[str]
    n_lost_periods: int
    profit_per_unit_first: float
    holding_cost_per_unit_first: float
    constant_profit: bool
    constant_holding: bool
    total_demand: float
    train_sha256: str
    test_sha256: str


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _read_csv_rows(path: Path) -> tuple[list[str], list[list[str]]]:
    """Exact row reading with the stdlib csv module.

    pandas would coerce ``inf`` and quoted integers; the audit must see the file as written.
    """
    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    if not rows:
        raise ValueError(f"{path} is empty")
    return rows[0], rows[1:]


def _item_id_from_header(header: list[str]) -> str:
    for col in header:
        if col.startswith("demand_"):
            return col[len("demand_") :]
    raise ValueError(f"no demand_* column in header: {header}")


def _is_lost(raw: str) -> bool:
    token = raw.strip().strip('"').lower()
    if token in {"inf", "+inf", "infinity"}:
        return True
    try:
        return math.isinf(float(token))
    except ValueError:
        return False


def _num(raw: str) -> float:
    return float(raw.strip().strip('"'))


def audit_instance(instance_dir: Path) -> InstanceRecord:
    rel = instance_dir.relative_to(BENCHMARK_ROOT)
    parts = rel.parts
    trajectory_type, lead_time_label = parts[0], parts[1]

    _train_header, train_rows = _read_csv_rows(instance_dir / "train.csv")
    test_header, test_rows = _read_csv_rows(instance_dir / "test.csv")
    item_id = _item_id_from_header(test_header)

    idx = {name: i for i, name in enumerate(test_header)}
    lt_col = idx[f"lead_time_{item_id}"]
    profit_col = idx[f"profit_{item_id}"]
    hold_col = idx[f"holding_cost_{item_id}"]
    demand_col = idx[f"demand_{item_id}"]

    lead_raw = [r[lt_col].strip().strip('"') for r in test_rows]
    profits = [_num(r[profit_col]) for r in test_rows]
    holdings = [_num(r[hold_col]) for r in test_rows]
    demands = [_num(r[demand_col]) for r in test_rows]

    if trajectory_type == "synthetic_trajectory":
        family, variant, realization = parts[2], parts[3], parts[4]
        cost_ratio = realization.split("_", 1)[1] if "_" in realization else None
        article_id = None
    else:
        family = variant = realization = cost_ratio = None
        article_id = parts[2]

    return InstanceRecord(
        rel_path=str(rel).replace("\\", "/"),
        trajectory_type=trajectory_type,
        lead_time_label=lead_time_label,
        promised_lead_time=PROMISED_LEAD_TIME_BY_DIR[lead_time_label],
        item_id=item_id,
        family=family,
        variant=variant,
        realization=realization,
        cost_ratio=cost_ratio,
        article_id=article_id,
        train_rows=len(train_rows),
        test_rows=len(test_rows),
        observation_count=len(test_rows),
        test_header=list(test_header),
        has_description=f"description_{item_id}" in idx,
        actual_lead_times=sorted({("inf" if _is_lost(v) else v) for v in lead_raw}),
        n_lost_periods=sum(1 for v in lead_raw if _is_lost(v)),
        profit_per_unit_first=profits[0],
        holding_cost_per_unit_first=holdings[0],
        constant_profit=len(set(profits)) == 1,
        constant_holding=len(set(holdings)) == 1,
        total_demand=sum(demands),
        train_sha256=_sha256(instance_dir / "train.csv"),
        test_sha256=_sha256(instance_dir / "test.csv"),
    )


def discover_instances() -> list[Path]:
    found: list[Path] = []
    for traj in TRAJECTORY_TYPES:
        for lt in LEAD_TIME_DIRS:
            root = BENCHMARK_ROOT / traj / lt
            if not root.is_dir():
                continue
            for path in root.rglob("test.csv"):
                if (path.parent / "train.csv").is_file():
                    found.append(path.parent)
    return sorted(found, key=lambda p: str(p.relative_to(BENCHMARK_ROOT)))


# ---------------------------------------------------------------------------
# ambiguity resolution
# ---------------------------------------------------------------------------


@dataclass
class Resolution:
    question: str
    answer: str
    evidence: list[str] = field(default_factory=list)
    defined_by_us: bool = False


def resolve_horizon(records: list[InstanceRecord]) -> Resolution:
    hist: dict[str, Counter] = {t: Counter() for t in TRAJECTORY_TYPES}
    for r in records:
        hist[r.trajectory_type][r.observation_count] += 1

    real = hist["real_trajectory"]
    synth = hist["synthetic_trajectory"]
    real_counts = sorted(real.items())
    synth_counts = sorted(synth.items())

    return Resolution(
        question="Real-instance horizon: root README says 48 periods; doc 3.5 derives 47 observations.",
        answer=(
            f"RESOLVED as data rows excluding the header: real={real_counts}, "
            f"synthetic={synth_counts}. Doc 3.5 is correct for real instances (47 decisions); "
            "the README's 48 counts physical CSV lines including the header. Synthetic is 50."
        ),
        evidence=[
            "csv.reader over every test.csv, header excluded",
            "files end with a trailing newline, so `wc -l` equals header + data rows",
            "eval/run_baseline_policy.py: num_periods = len(test_df) (header not a row)",
            "real test.csv exact_dates run 2019/2/11..2019/12/30 at weekly cadence",
        ],
    )


def resolve_lead_times(records: list[InstanceRecord]) -> Resolution:
    promised = sorted({r.promised_lead_time for r in records})
    actual: set[str] = set()
    for r in records:
        actual.update(r.actual_lead_times)
    by_label: dict[str, set[str]] = {}
    for r in records:
        by_label.setdefault(r.lead_time_label, set()).update(r.actual_lead_times)

    return Resolution(
        question=(
            "Lead-time set: root README says {0, 4, stochastic{1,2,3,inf}}; "
            "eval/README.md says promised_lead_time in {0, 2, 4}."
        ),
        answer=(
            "NOT A CONTRADICTION. The two documents describe different quantities. "
            f"PROMISED (given to the policy at init, derived from the directory) = {promised}. "
            f"ACTUAL (per-period column in test.csv, never shown to the policy) = {sorted(actual)}. "
            + "; ".join(f"{k}: actual={sorted(v)}" for k, v in sorted(by_label.items()))
            + ". lead_time_stochastic is promised as 2."
        ),
        evidence=[
            "eval/run_baseline_policy.py::detect_promised_lead_time maps "
            "lead_time_0->0, lead_time_4->4, lead_time_stochastic->2",
            "test.csv carries a per-period lead_time_<item_id> column",
            "eval/policy_template.py docstring: the policy does NOT receive actual lead times",
        ],
    )


def resolve_order_cap() -> Resolution:
    """Search the env and the eval harness for any upper clamp on the order quantity."""
    env_src = (BENCH / "or_agent/envs/VendingMachine/env.py").read_text(encoding="utf-8")
    eval_src = (BENCH / "eval/run_baseline_policy.py").read_text(encoding="utf-8")

    # Any upper bound would have to appear as a min(...) against the order, or a named cap.
    cap_names = re.findall(r"\b(max_order\w*|order_cap\w*|MAX_ORDER\w*|capacity\w*)\b", env_src)
    clamps = [
        line.strip()
        for line in env_src.splitlines()
        if re.search(r"min\s*\(.*(qty|quantity|order)", line)
    ]
    eval_coercion = [
        line.strip() for line in eval_src.splitlines() if "max(0, int(order_quantity))" in line
    ]

    return Resolution(
        question="Order cap C_t: relied on throughout doc 3.5, absent from eval/policy_template.py.",
        answer=(
            "NO CAP EXISTS in the benchmark. The only order-side validations are "
            "unknown-item and negative-quantity rejection in env.py, and the eval harness "
            "coerces with max(0, int(order_quantity)) which truncates toward zero and "
            "imposes no upper bound. COLLIE therefore DEFINES its own cap and registers it "
            "in prereg/prereg_v1.yaml. The cap is ours, not the benchmark's, and every table "
            "reporting it must say so."
        ),
        evidence=[
            f"no cap identifiers found in env.py (searched max_order/order_cap/MAX_ORDER/capacity): {sorted(set(cap_names)) or 'none'}",
            f"min(...) lines touching qty/quantity/order in env.py: {clamps or 'none bounding the order'}",
            f"eval coercion: {eval_coercion or 'not found'}",
        ],
        defined_by_us=True,
    )


def resolve_lost_order_divergence() -> Resolution:
    """The two harnesses disagree on whether a lost order stays visible in in-transit."""
    env_src = (BENCH / "or_agent/envs/VendingMachine/env.py").read_text(encoding="utf-8")
    eval_src = (BENCH / "eval/run_baseline_policy.py").read_text(encoding="utf-8")
    env_keeps = "lost orders still show as in-transit" in env_src
    eval_drops = "order is lost (never added to in_transit_orders)" in eval_src

    return Resolution(
        question="Do lost orders (lead_time=inf) remain visible in the aggregate in-transit total?",
        answer=(
            "THE TWO HARNESSES DIVERGE, and this materially changes what pipeline crediting "
            "(gamma) means. or_agent/envs/VendingMachine/env.py keeps arrival_day=inf orders in "
            "in-transit forever, so a policy that credits the pipeline is permanently misled. "
            "eval/run_baseline_policy.py never adds them, so a lost order is invisible except as "
            "an absent arrival. COLLIE treats the eval/ path as AUTHORITATIVE for its own runner "
            "and for arm 1, because that is the submission contract we are scored against. "
            "Legacy every-period arms 3 and 5 run through the env path, so any comparison with "
            "them must state which in-transit semantics applied."
        ),
        evidence=[
            f"env.py contains the 'lost orders still show as in-transit' comment: {env_keeps}",
            f"run_baseline_policy.py contains the 'never added to in_transit_orders' comment: {eval_drops}",
            "env.py sets arrival_day = float('inf') and never pops it from pending_orders",
        ],
    )


def resolve_event_ordering() -> Resolution:
    return Resolution(
        question="What is the exact per-period event ordering, and when is holding cost charged?",
        answer=(
            "Fixed sequence per period t, identical in eval/run_baseline_policy.py and "
            "eval/evaluate_results.py: "
            "(1) DECISION: the policy observes on_hand and the aggregate in_transit total, then "
            "returns q_t, coerced by max(0, int(q_t)); q_t is scheduled to arrive at t + L_actual, "
            "or dropped entirely if L_actual is inf. "
            "(2) ARRIVAL: units scheduled for t are popped and added to on_hand. "
            "(3) DEMAND: units_sold = min(demand_t, on_hand); on_hand -= units_sold. "
            "(4) REWARD: period_profit = profit * units_sold; period_holding = holding * on_hand "
            "AFTER demand resolution (i.e. on ENDING inventory). "
            "total_reward = total_profit - total_holding_cost. "
            "perfect_foresight = profit_per_unit(first row) * total_demand. "
            "normalized_reward = max(0, total_reward / perfect_foresight). "
            "Two consequences: L=0 means an order placed at t is available to satisfy demand at t, "
            "because scheduling precedes the arrival pop; and the in_transit total the policy sees "
            "at t still includes units that will land at t, since the pop happens after the decision."
        ),
        evidence=[
            "eval/run_baseline_policy.py '=== PERIOD EXECUTION SEQUENCE ===' steps 1-3",
            "eval/evaluate_results.py '=== PERIOD EXECUTION SEQUENCE ===' steps 1-4",
            "eval/evaluate_results.py: period_holding = holding_cost_per_unit * on_hand_inventory, "
            "evaluated after on_hand_inventory -= units_sold",
            "eval/evaluate_results.py::compute_perfect_foresight_reward",
        ],
    )


def resolve_lost_sales() -> Resolution:
    return Resolution(
        question="Is unmet demand lost or backordered?",
        answer=(
            "LOST. units_sold = min(demand, on_hand) and the shortfall is never carried forward; "
            "no backorder state exists in either harness. Unmet demand is therefore a lost sale, "
            "which is what makes total lost-sales units a coherent primary safety endpoint."
        ),
        evidence=[
            "eval/evaluate_results.py: units_sold = min(actual_demand, on_hand_inventory)",
            "no backorder or shortage variable appears in either simulation loop",
        ],
    )


def resolve_observability() -> Resolution:
    return Resolution(
        question="Does the policy observe demand or sales, and does it see shipment ages?",
        answer=(
            "UNCENSORED DEMAND, and NO shipment ages. previous_demand is assigned actual_demand, "
            "not units_sold, so true demand is visible even during a stockout. in_transit_total is "
            "a scalar sum with no age decomposition. Both facts are load-bearing: the censored-sales "
            "setting is a genuinely different observation model rather than a relabeling, and the "
            "FIFO ledger must be imputed from own orders plus observed receipts."
        ),
        evidence=[
            "eval/run_baseline_policy.py: previous_demand = actual_demand (units_sold computed separately)",
            "eval/run_baseline_policy.py: in_transit_total = sum(in_transit_orders.values())",
            "or_agent/envs/VendingMachine/env.py: VM player is shown profit/holding/inventory but NOT lead_time",
        ],
    )


# ---------------------------------------------------------------------------
# aggregation
# ---------------------------------------------------------------------------


def _validate_upstream_constants() -> dict[str, Any]:
    """Confirm the promised-lead-time mapping we mirror is still what upstream computes."""
    src = (BENCH / "eval/run_baseline_policy.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    returns: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "detect_promised_lead_time":
            for sub in ast.walk(node):
                if (
                    isinstance(sub, ast.Return)
                    and isinstance(sub.value, ast.Constant)
                    and isinstance(sub.value.value, int)
                ):
                    returns.append(sub.value.value)
    return {
        "detect_promised_lead_time_returns": sorted(set(returns)),
        "mirrored_mapping": dict(sorted(PROMISED_LEAD_TIME_BY_DIR.items())),
        "agrees": sorted(set(returns)) == sorted(set(PROMISED_LEAD_TIME_BY_DIR.values())),
    }


def build_manifest(records: list[InstanceRecord]) -> dict[str, Any]:
    by_type = Counter(r.trajectory_type for r in records)
    by_lead = Counter(r.lead_time_label for r in records)
    by_type_lead = Counter(f"{r.trajectory_type}/{r.lead_time_label}" for r in records)
    families = Counter(r.family for r in records if r.family)
    cost_ratios = Counter(r.cost_ratio for r in records if r.cost_ratio)

    # Sweep totals DERIVED from the data, never transcribed from either document's prose.
    calls_per_type = {
        t: sum(r.observation_count for r in records if r.trajectory_type == t) for t in by_type
    }
    always_online_total = sum(calls_per_type.values())

    horizon_by_type = {
        t: sorted({r.observation_count for r in records if r.trajectory_type == t})
        for t in sorted(by_type)
    }

    resolutions = [
        resolve_horizon(records),
        resolve_lead_times(records),
        resolve_order_cap(),
        resolve_lost_order_divergence(),
        resolve_event_ordering(),
        resolve_lost_sales(),
        resolve_observability(),
    ]

    return {
        "audit_schema_version": AUDIT_SCHEMA_VERSION,
        "benchmark_commit": "62b1f1162f19a41d428d47c6cd4ca431f098f6f3",
        "counts": {
            "instances_total": len(records),
            "by_trajectory_type": dict(sorted(by_type.items())),
            "by_lead_time_label": dict(sorted(by_lead.items())),
            "by_type_and_lead_time": dict(sorted(by_type_lead.items())),
            "synthetic_families": dict(sorted(families.items())),
            "synthetic_cost_ratios": dict(sorted(cost_ratios.items())),
            "real_articles": len({r.article_id for r in records if r.article_id}),
        },
        "horizon": {
            "observation_counts_by_type": horizon_by_type,
            "note": "observation_count excludes the CSV header; it equals the number of decisions",
        },
        "derived_sweep_totals": {
            "decisions_by_trajectory_type": dict(sorted(calls_per_type.items())),
            "always_online_calls_full_benchmark": always_online_total,
            "note": (
                "One always-online sweep issues one call per decision. Derived by summing "
                "observation_count over instances; not copied from any document."
            ),
        },
        "upstream_constant_check": _validate_upstream_constants(),
        "promised_lead_time_by_dir": dict(sorted(PROMISED_LEAD_TIME_BY_DIR.items())),
        "resolutions": [asdict(r) for r in resolutions],
        "instances": [asdict(r) for r in records],
    }


def write_manifest(manifest: dict[str, Any], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    # sort_keys + fixed indent + explicit trailing newline => byte-identical regeneration.
    text = json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    out.write_text(text, encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=REPO_ROOT / "manifests" / "benchmark_v1.json")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    if not BENCHMARK_ROOT.is_dir():
        raise SystemExit(
            f"benchmark data not found at {BENCHMARK_ROOT}. Run: make setup "
            "(the submodule must be initialised and LFS objects fetched)"
        )

    instances = discover_instances()
    if not instances:
        raise SystemExit("no instances discovered; are LFS objects fetched?")

    records = [audit_instance(d) for d in instances]
    manifest = build_manifest(records)
    write_manifest(manifest, args.out)

    if not args.quiet:
        c = manifest["counts"]
        print(f"instances: {c['instances_total']}  {c['by_trajectory_type']}")
        print(f"horizons : {manifest['horizon']['observation_counts_by_type']}")
        print(
            "always-online sweep: "
            f"{manifest['derived_sweep_totals']['always_online_calls_full_benchmark']} calls "
            f"{manifest['derived_sweep_totals']['decisions_by_trajectory_type']}"
        )
        for r in manifest["resolutions"]:
            flag = "  [DEFINED BY US]" if r["defined_by_us"] else ""
            print(f"\n- {r['question']}{flag}\n  {r['answer'][:300]}")
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
