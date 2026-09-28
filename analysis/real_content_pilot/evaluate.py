"""Pre-registered analysis of the exploratory real-content pilot. Nothing here is a Gate 3 vote.

Reads committed run outputs (``analysis/real_content_pilot/out/<run>/``) and the registered pilot
artefacts in ``reports/`` (read, never written), and writes ``out/evaluation.json`` and
``out/evaluation.md``. The questions, arms, rules and statistics are fixed in ``PLAN.md``, which
is committed before any live call:

* **readout**: the frozen evaluator's go/kill table on a run's records, computed exactly as
  ``tests/test_pilot.py::_stored_pilot_decision`` recomputes the registered one;
* **Q1** first-proposal accuracy: the first call of an episode, which arms 8, 9 and 10 share;
* **Q2** early-accurate versus unreliable alerts, paired within seed;
* **Q3** arm 10 activation and arm 9 refutation, right- versus wrong-family proposals;
* **Q4** outcome contrasts, gross and net, with episode-level normal and seed-cluster bootstrap
  intervals;
* **Q5** operations: calls, tokens, latency, cost, refusals, retries, parse outcomes;
* **Q6** the null controls, silent versus false-alert;
* **Q7** the content effect: each LLM arm's live outcome minus its scripted-reference outcome,
  episode by episode (everything else is shared);
* cross-endpoint agreement on the shared first proposal, and an integrity check that the six
  arms which never call the model replay the reference exactly.

Run::

    uv run python -m analysis.real_content_pilot.evaluate --runs gemini-bank grok-bank \\
        --reference scripted-bank
    uv run python -m analysis.real_content_pilot.evaluate --smoke gemini-bank
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

from analysis.forensics.common import (
    FAMILY_KEY,
    cluster_bootstrap,
    episode_frame,
    load_truth,
    normal_interval,
    paired,
    parse_episode_id,
    wilson_interval,
)
from analysis.real_content_pilot.alerts import GAP_GENERATOR_FAMILY
from analysis.real_content_pilot.runner import ARMS, LLM_ARMS, OUT_ROOT, REPO, STORED_TRUTH
from collie.arms.base_stock import ARM1_ARM_ID as ARM1
from collie.arms.controls import ALERTSPEC_UB_ARM_ID as UB
from collie.arms.controls import ARM2_ARM_ID as ARM2
from collie.arms.controls import DETECTOR_CONTROL_ARM_ID as CTRL
from collie.arms.controls import KEYWORD_CONTROL_ARM_ID as KEYWORD
from collie.arms.shockspec import ARM8_ARM_ID as ARM8
from collie.arms.shockspec import ARM9_ARM_ID as ARM9
from collie.arms.shockspec import ARM10_ARM_ID as ARM10
from collie.eval.pilot import (
    compute_builtin_pilot_intervals,
    compute_builtin_pilot_metrics,
    evaluate_pilot,
    validate_pilot_record_count,
)
from collie.eval.prereg import load_preregistration, primary_stratum_weights
from collie.eval.records import episode_result_from_dict
from collie.eval.truth import load_episode_truth_jsonl, shock_periods_from_truth, truth_by_episode
from tools.freeze import drift

STORED_RECORDS = REPO / "reports" / "pilot_records.jsonl"
REGISTERED = "registered"
LABEL = {
    ARM1: "arm1",
    ARM2: "arm2",
    ARM8: "arm8",
    ARM9: "arm9",
    ARM10: "arm10",
    CTRL: "ctrl",
    KEYWORD: "keyword",
    UB: "ub",
}
CONTRASTS = (
    ("arm10-arm8", ARM10, ARM8),
    ("arm10-ctrl", ARM10, CTRL),
    ("arm10-arm1", ARM10, ARM1),
    ("arm8-arm1", ARM8, ARM1),
    ("arm10-keyword", ARM10, KEYWORD),
    ("keyword-ctrl", KEYWORD, CTRL),
    ("ub-ctrl", UB, CTRL),
    ("arm2-arm1", ARM2, ARM1),
)
BY_CONDITION = ("arm8-arm1", "arm10-arm1", "arm10-ctrl")
ENDPOINTS = (("gross", "profit"), ("net", "reward"))
CONDITIONS = ("no_alert", "early_accurate", "late_accurate", "unreliable")
NULL_KINDS = (("silent", "no_alert"), ("false_alert", "unreliable"))
COMPONENTS = ("onset_ok", "magnitude_ok", "persistence_ok", "duration_ok")
SCORES = ("family_ok", *COMPONENTS, "full_ok")
OUTCOMES = ("no_call", "parse_fail", "abstain", "shock")


# ---------------------------------------------------------------------------
# loading
# ---------------------------------------------------------------------------


def _jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass
class Run:
    name: str
    raw: list[dict]
    proposals: list[dict] | None = None
    alerts: dict[str, dict] | None = None
    ledger: list[dict] | None = None
    spend: list[dict] | None = None
    manifest: dict | None = None
    inputs: dict[str, str] | None = None

    @property
    def results(self):
        return tuple(episode_result_from_dict(row) for row in self.raw)


def load_run(name: str, *, root: Path = OUT_ROOT, allow_partial: bool = False) -> Run:
    run_dir = root / name
    manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    if manifest.get("analysis_class") != "exploratory":
        raise ValueError(f"{name}: not an exploratory run")
    if manifest.get("partial") and not allow_partial:
        raise ValueError(f"{name}: a partial (smoke) run; the analysis needs all 120 episodes")
    body = gzip.decompress((run_dir / "records.jsonl.gz").read_bytes()).decode("utf-8")
    with (run_dir / "ledger.csv").open(encoding="utf-8", newline="") as handle:
        ledger = list(csv.DictReader(handle))
    spend_path = run_dir / "spend_log.jsonl"
    names = ("records.jsonl.gz", "proposals.jsonl", "alerts.jsonl", "ledger.csv")
    return Run(
        name=name,
        raw=[json.loads(line) for line in body.splitlines() if line],
        proposals=_jsonl(run_dir / "proposals.jsonl"),
        alerts={row["episode_id"]: row for row in _jsonl(run_dir / "alerts.jsonl")},
        ledger=ledger,
        spend=_jsonl(spend_path) if spend_path.is_file() else None,
        manifest=manifest,
        inputs={f"{name}/{n}": _sha256(run_dir / n) for n in names},
    )


def load_registered() -> Run:
    """The registered scripted pilot (demo alerts), restricted to this pilot's nine arms."""
    return Run(
        name=REGISTERED,
        raw=[row for row in _jsonl(STORED_RECORDS) if row["arm_id"] in ARMS],
        inputs={"reports/pilot_records.jsonl": _sha256(STORED_RECORDS)},
    )


# ---------------------------------------------------------------------------
# the frozen evaluator, read out (never a vote)
# ---------------------------------------------------------------------------


def frozen_readout(run: Run) -> dict:
    """``tests/test_pilot.py::_stored_pilot_decision`` on this run's records."""
    results = run.results
    prereg = load_preregistration()
    validate_pilot_record_count(results, prereg=prereg)
    truths = truth_by_episode(load_episode_truth_jsonl(STORED_TRUTH))
    policy = prereg.data["pilot_policy"]
    kwargs = {
        "call_budget_per_episode": int(policy["call_budget_per_episode"]),
        "shock_periods": shock_periods_from_truth(truths),
        "stratum_weights": primary_stratum_weights(prereg.data),
        "never_recovered_value": float(policy["never_recovered_value"]),
        "truths": truths,
    }
    metrics = compute_builtin_pilot_metrics(results, **kwargs)
    drifted = drift()  # read-only hash check of the frozen tree
    metrics["method_freeze_or_quarantine_violation"] = 1.0 if drifted else 0.0
    intervals = compute_builtin_pilot_intervals(results, **kwargs)
    decision = evaluate_pilot(prereg, metrics, intervals=intervals, require_go_intervals=True)
    return {
        "decision": decision.decision,
        "go": [asdict(verdict) for verdict in decision.go],
        "kill": [asdict(verdict) for verdict in decision.kill],
        "freeze_drift": [list(item) for item in drifted],
    }


# ---------------------------------------------------------------------------
# proposals
# ---------------------------------------------------------------------------


def proposal_events(proposals: Sequence[dict]) -> pd.DataFrame:
    """One row per proposal event (episode, arm, period), carrying its final attempt."""
    final: dict[tuple[str, str, int], dict] = {}
    attempts: Counter = Counter()
    for row in proposals:
        key = (row["episode_id"], row["arm_id"], int(row["period"]))
        attempts[key] += 1
        if key not in final or row["attempt_index"] > final[key]["attempt_index"]:
            final[key] = row
    rows = []
    for key, row in final.items():
        if not row["parsed"]:
            outcome = "parse_fail"
        elif row["abstention"]:
            outcome = "abstain"
        else:
            outcome = "shock"
        rows.append(
            {
                "episode_id": key[0],
                "arm": key[1],
                "tau": key[2],
                "attempts": attempts[key],
                "repaired": bool(row["parsed"] and row["attempt_index"] > 1),
                "outcome": outcome,
                "coerced": bool(row.get("arm10_coerced_abstention")),
                "rule_u_reason": row.get("rule_u_reason"),
                "payload": row["payload"],
                "prompt_key": row["prompt_key"],
            }
        )
    frame = pd.DataFrame(rows).sort_values(["episode_id", "arm", "tau"], kind="stable")
    frame = frame.reset_index(drop=True)
    frame["event_index"] = frame.groupby(["episode_id", "arm"]).cumcount() + 1
    return frame


def payload_key(payload: dict | None) -> str | None:
    """The frozen evaluator's headroom key of a proposal: family, plus direction for levels."""
    if payload is None:
        return None
    family = payload["shock_family"]
    return f"{family}:{payload['direction']}" if family == "demand_level" else family


def score(payload: dict | None, truth: dict, tau: int) -> dict[str, bool]:
    """Field-by-field agreement with the hidden truth; ``full_ok`` is ``_matches_truth``."""
    if payload is None or payload["shock_family"] == "no_change":
        return dict.fromkeys(SCORES, False)
    low, high = payload["onset_window"]
    out = {
        "family_ok": payload["shock_family"] == truth["family"]
        and payload["direction"] == truth["direction"],
        "onset_ok": low <= truth["onset_period"] - tau <= high,
        "magnitude_ok": payload["magnitude_bin"] == truth["magnitude_bin"],
        "persistence_ok": payload["persistence"] == truth["persistence"],
        "duration_ok": payload["duration_bin"] == truth["duration_bin"],
    }
    out["full_ok"] = all(out.values()) and payload["target_stream"] == truth["target_stream"]
    return out


def first_proposals(run: Run, truths: dict[str, dict]) -> pd.DataFrame:
    """Per episode: arm 8's first proposal event, i.e. the first call arms 8-10 all share."""
    events = proposal_events(run.proposals)
    first = {
        row.episode_id: row
        for row in events[(events.arm == ARM8) & (events.event_index == 1)].itertuples()
    }
    arm10_first = {
        row.episode_id: row
        for row in events[(events.arm == ARM10) & (events.event_index == 1)].itertuples()
    }
    # A null twin's id carries its source rollout's condition, not its own: read the record's.
    conditions = {record["episode_id"]: record["information_condition"] for record in run.raw}
    rows = []
    for episode_id in sorted(conditions):
        meta = parse_episode_id(episode_id)
        alert = run.alerts[episode_id]
        row = {
            "episode_id": episode_id,
            **meta,
            "condition": conditions[episode_id],
            "alert_period": alert["period"],
            "alert_source": alert["source"],
            "template_kind": alert["template_kind"],
            "tau": None,
            "rel_tau": None,
            "fired_on_alert": False,
            "outcome": "no_call",
            "category": "no_call",
            "repaired": False,
            "prompt_key": None,
            "arm10_coerced": False,
        }
        event = first.get(episode_id)
        truth = None if meta["is_null"] else truths[episode_id]
        if event is not None:
            payload = event.payload if event.outcome != "parse_fail" else None
            row.update(
                tau=int(event.tau),
                fired_on_alert=alert["period"] == int(event.tau),
                outcome=event.outcome,
                category=payload_key(payload) if event.outcome == "shock" else event.outcome,
                repaired=bool(event.repaired),
                prompt_key=event.prompt_key,
            )
            twin = arm10_first.get(episode_id)
            row["arm10_coerced"] = bool(twin is not None and twin.coerced)
            if truth is not None:
                row["rel_tau"] = int(event.tau) - int(truth["onset_period"])
        if truth is None:
            row.update(dict.fromkeys(SCORES, None))
        else:
            row["truth_key"] = FAMILY_KEY[int(meta["fam"])]
            payload = None if event is None or event.outcome == "parse_fail" else event.payload
            row.update(score(payload, truth, row["tau"] or 0))
        rows.append(row)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# small statistics
# ---------------------------------------------------------------------------


def _rate(values: Iterable) -> dict:
    kept = [
        bool(v) for v in values if v is not None and not (isinstance(v, float) and math.isnan(v))
    ]
    n, k = len(kept), sum(kept)
    return {
        "k": k,
        "n": n,
        "rate": k / n if n else None,
        "wilson": list(wilson_interval(k, n)) if n else None,
    }


def _contrast(frame: pd.DataFrame, *, bootstrap: bool = True) -> dict:
    diff = frame["diff"].astype(float)
    out = {"n": len(diff), "mean": float(diff.mean()) if len(diff) else None}
    out["normal"] = list(normal_interval(diff)) if len(diff) > 1 else None
    if bootstrap and len(diff) > 1:
        out["cluster_bootstrap"] = list(cluster_bootstrap(diff, frame["cluster"]))
        out["clusters"] = int(frame["cluster"].nunique())
    return out


def _counts(values: Iterable, order: Sequence[str] = OUTCOMES) -> dict[str, int]:
    counts = Counter(values)
    return {key: int(counts.get(key, 0)) for key in order}


# ---------------------------------------------------------------------------
# the questions
# ---------------------------------------------------------------------------


def q1(first: pd.DataFrame) -> dict:
    """First-proposal accuracy on the 96 shocked episodes; ``no_call`` counts as not correct."""
    shocked = first[~first.is_null]

    def block(group: pd.DataFrame) -> dict:
        return {
            "n": len(group),
            "outcomes": _counts(group.outcome),
            "repaired": int(group.repaired.sum()),
            "arm10_coerced": int(group.arm10_coerced.sum()),
            **{name: _rate(group[name]) for name in SCORES},
        }

    grid = {}
    for (fam, condition), group in shocked.groupby(["fam", "condition"]):
        grid[f"{FAMILY_KEY[int(fam)]}|{condition}"] = {
            name: [int(group[name].sum()), len(group)] for name in ("family_ok", "full_ok")
        }
    timing = {}
    for condition in CONDITIONS:
        group = shocked[(shocked.condition == condition) & (shocked.outcome != "no_call")]
        rel = group.rel_tau.dropna().astype(int)
        timing[condition] = {
            "called": len(group),
            "median_rel_tau": float(rel.median()) if len(rel) else None,
            "before_onset": int((rel < 0).sum()),
            "fired_on_alert": int(group.fired_on_alert.sum()),
        }
    confusion = Counter(zip(shocked.truth_key, shocked.category, strict=True))
    return {
        "shocked": block(shocked),
        "by_condition": {c: block(shocked[shocked.condition == c]) for c in CONDITIONS},
        "by_family": {FAMILY_KEY[int(fam)]: block(group) for fam, group in shocked.groupby("fam")},
        "grid": grid,
        "timing": timing,
        "confusion": [
            {"truth": truth, "proposed": proposed, "count": count}
            for (truth, proposed), count in sorted(confusion.items())
        ],
    }


def q2(first: pd.DataFrame, run: Run) -> dict:
    """Early-accurate versus unreliable, paired within seed; family 2 has no alert in either."""
    shocked = first[~first.is_null & (first.fam != GAP_GENERATOR_FAMILY)]
    out: dict = {
        "excluded": "generator family 2 (bank gap: no alert in either condition)",
        "n_seeds": int(shocked.cluster.nunique()),
    }
    wide = shocked.pivot(index="cluster", columns="condition")
    for name in ("family_ok", "full_ok"):
        early = wide[(name, "early_accurate")].astype(bool)
        unreliable = wide[(name, "unreliable")].astype(bool)
        diff = early.astype(float) - unreliable.astype(float)
        out[name] = {
            "early": _rate(early),
            "unreliable": _rate(unreliable),
            "mean_diff": float(diff.mean()),
            "normal": list(normal_interval(diff)),
            "both": int((early & unreliable).sum()),
            "early_only": int((early & ~unreliable).sum()),
            "unreliable_only": int((~early & unreliable).sum()),
            "neither": int((~early & ~unreliable).sum()),
        }
    kinds = wide[("template_kind", "unreliable")]
    out["by_unreliable_kind"] = {}
    for kind in sorted(kinds.dropna().unique()):
        seeds = kinds[kinds == kind].index
        out["by_unreliable_kind"][kind] = {
            "n": len(seeds),
            "early_family_ok": _rate(wide.loc[seeds, ("family_ok", "early_accurate")]),
            "unreliable_family_ok": _rate(wide.loc[seeds, ("family_ok", "unreliable")]),
            "unreliable_proposed": dict(Counter(wide.loc[seeds, ("category", "unreliable")])),
        }
    frame = episode_frame(run.raw)
    out["outcomes"] = {}
    for name, treatment, control in (("arm8-arm1", ARM8, ARM1), ("arm10-arm1", ARM10, ARM1)):
        for endpoint, column in ENDPOINTS:
            diffs = paired(frame, treatment, control, column)
            diffs = diffs[~diffs.is_null & (diffs.fam != GAP_GENERATOR_FAMILY)]
            by_seed = diffs.pivot(index="cluster", columns="condition", values="diff")
            delta = by_seed["early_accurate"] - by_seed["unreliable"]
            out["outcomes"][f"{name}|{endpoint}"] = {
                "early": float(by_seed["early_accurate"].mean()),
                "unreliable": float(by_seed["unreliable"].mean()),
                "mean_diff": float(delta.mean()),
                "normal": list(normal_interval(delta)),
                "n": len(delta),
            }
    return out


def q3(run: Run, truths: dict[str, dict]) -> dict:
    """Per registered proposal: arm 10's lifecycle and arm 9's rollback, by proposal class."""
    events = proposal_events(run.proposals)
    periods = {
        (record["episode_id"], record["arm_id"]): record["records"]
        for record in run.raw
        if record["arm_id"] in (ARM9, ARM10)
    }
    rows = []
    for arm in (ARM9, ARM10):
        registered = events[(events.arm == arm) & (events.outcome == "shock") & ~events.coerced]
        for episode_id, group in registered.groupby("episode_id"):
            meta = parse_episode_id(episode_id)
            truth = None if meta["is_null"] else truths[episode_id]
            taus = sorted(int(t) for t in group.tau)
            for index, event in enumerate(group.sort_values("tau").itertuples()):
                tau = int(event.tau)
                end = taus[index + 1] if index + 1 < len(taus) else math.inf
                window = [p for p in periods[(episode_id, arm)] if tau <= p["period"] < end]
                states = [p["lifecycle_state"] for p in window if p.get("lifecycle_state")]
                active = [
                    p["period"]
                    for p in window
                    if p.get("active_spec_id") and int(p["active_spec"]["tau_j"]) == tau
                ]
                if truth is None:
                    kind = "null"
                else:
                    kind = "right" if score(event.payload, truth, tau)["family_ok"] else "wrong"
                rows.append(
                    {
                        "arm": arm,
                        "class": kind,
                        "activated": bool(active),
                        "delay": min(active) - tau if active else None,
                        "refuted": "refuted" in states,
                        "terminal": states[-1] if states else None,
                    }
                )
    frame = pd.DataFrame(
        rows, columns=["arm", "class", "activated", "delay", "refuted", "terminal"]
    )
    out: dict = {}
    for arm in (ARM10, ARM9):
        out[LABEL[arm]] = {}
        for kind in ("right", "wrong", "null"):
            group = frame[(frame.arm == arm) & (frame["class"] == kind)]
            delays = group.delay.dropna().astype(float)
            out[LABEL[arm]][kind] = {
                "n": len(group),
                "activated": _rate(group.activated),
                "refuted": _rate(group.refuted),
                "terminal": dict(Counter(str(t) for t in group.terminal)),
                "median_delay": float(delays.median()) if len(delays) else None,
            }
    coerced = events[(events.arm == ARM10) & events.coerced]
    out["arm10_rule_u"] = {
        "events": len(coerced),
        "by_reason": dict(Counter(coerced.rule_u_reason)),
    }
    return out


def q4(run: Run) -> dict:
    frame = episode_frame(run.raw)
    out: dict = {"overall": {}, "by_condition": {}}
    for name, treatment, control in CONTRASTS:
        for endpoint, column in ENDPOINTS:
            out["overall"][f"{name}|{endpoint}"] = _contrast(
                paired(frame, treatment, control, column)
            )
    for name, treatment, control in CONTRASTS:
        if name not in BY_CONDITION:
            continue
        for endpoint, column in ENDPOINTS:
            diffs = paired(frame, treatment, control, column)
            shocked = diffs[~diffs.is_null]
            for condition in CONDITIONS:
                out["by_condition"][f"{name}|{endpoint}|{condition}"] = _contrast(
                    shocked[shocked.condition == condition]
                )
    return out


def _error_class(error: str | None) -> str:
    if not error:
        return "none"
    return error.splitlines()[0][:90]


def _quantiles(values: Sequence[float]) -> dict | None:
    if not values:
        return None
    arr = np.asarray(values, dtype=float)
    return {
        "p50": float(np.quantile(arr, 0.5)),
        "p95": float(np.quantile(arr, 0.95)),
        "max": float(arr.max()),
    }


def q5(run: Run) -> dict:
    physical = [row for row in run.ledger if row["physical"] == "true"]
    charged = [row for row in run.ledger if row["physical"] == "false"]
    arm10_calls = Counter(row["episode_id"] for row in charged if row["arm_id"] == ARM10)
    out: dict = {
        "ledger_this_invocation": {
            "physical_calls": len(physical),
            "charged_calls": len(charged),
            "input_tokens": sum(int(row["input_tokens"]) for row in physical),
            "output_tokens": sum(int(row["output_tokens"]) for row in physical),
            "usd_physical": sum(float(row["usd_cost"]) for row in physical),
            "usd_charged": sum(float(row["usd_cost"]) for row in charged),
        },
        "outcomes_by_arm": {
            LABEL[arm]: dict(Counter(row["outcome"] for row in charged if row["arm_id"] == arm))
            for arm in LLM_ARMS
        },
        "repair_attempts_by_arm": {
            LABEL[arm]: sum(1 for r in charged if r["arm_id"] == arm and r["attempt_index"] == "2")
            for arm in LLM_ARMS
        },
        "arm10_calls_per_episode": {
            "max": max(arm10_calls.values(), default=0),
            "over_budget_4": sum(1 for count in arm10_calls.values() if count > 4),
        },
    }
    if run.spend is not None:
        calls = [row for row in run.spend if row["event"] == "call"]
        retries = [row for row in run.spend if row["event"] == "retry"]
        out["provider"] = {
            "physical_calls": len(calls),
            "ok": sum(1 for row in calls if row["status"] == "ok"),
            "refused": sum(1 for row in calls if row["status"] == "refused"),
            "retries": len(retries),
            "calls_needing_retry": sum(1 for row in calls if row["attempts"] > 1),
            "errors": sum(1 for row in run.spend if row["event"] == "error"),
            "retry_reasons": dict(Counter(row["error"].split(":")[0] for row in retries)),
            "usd": sum(float(row["usd"]) for row in calls),
            "prompt_tokens": sum(int(row["prompt_tokens"]) for row in calls),
            "completion_tokens": sum(int(row["completion_tokens"]) for row in calls),
            "billable_output_tokens": sum(int(row["billable_output_tokens"]) for row in calls),
            "latency_ms": _quantiles(
                [float(row["latency_ms"]) for row in calls if row["status"] == "ok"]
            ),
        }
    failed = [row for row in run.proposals if not row["parsed"]]
    out["parse"] = {
        "attempts": len(run.proposals),
        "parsed": len(run.proposals) - len(failed),
        "failed": len(failed),
        "empty_text": sum(1 for row in failed if row["text_chars"] == 0),
        "abstentions": sum(1 for row in run.proposals if row["parsed"] and row["abstention"]),
        "top_errors": Counter(_error_class(row["error"]) for row in failed).most_common(8),
    }
    out["rule_u"] = (run.manifest or {}).get("rule_u")
    return out


def q6(run: Run, first: pd.DataFrame | None) -> dict:
    frame = episode_frame(run.raw)
    out = {}
    for kind, condition in NULL_KINDS:
        # ``condition`` is the record's own; a null twin's id names its source rollout's.
        nulls = frame[frame.is_null & (frame.condition == condition)]
        block: dict = {"n": int(nulls.episode_id.nunique())}
        for arm in (ARM8, ARM9, ARM10, CTRL, KEYWORD):
            group = nulls[nulls.arm == arm]
            block[LABEL[arm]] = {
                "any_active": _rate(group.n_active > 0),
                "mean_active_periods": float(group.n_active.mean()),
            }
        for name, treatment, control in (
            ("arm8-arm1", ARM8, ARM1),
            ("arm10-arm1", ARM10, ARM1),
            ("ctrl-arm1", CTRL, ARM1),
        ):
            diffs = paired(frame, treatment, control, "profit")
            diffs = diffs[diffs.is_null & (diffs.condition == condition)]
            block[f"{name}|gross"] = _contrast(diffs, bootstrap=False)
        if first is not None:
            group = first[first.is_null & (first.condition == condition)]
            block["first_proposal"] = _counts(group.outcome)
            block["first_proposed"] = dict(Counter(group.category))
        out[kind] = block
    return out


def _kappa(a: Sequence[str], b: Sequence[str]) -> float | None:
    n = len(a)
    if n == 0:
        return None
    observed = sum(x == y for x, y in zip(a, b, strict=True)) / n
    count_a, count_b = Counter(a), Counter(b)
    expected = sum(count_a[c] * count_b[c] for c in set(a) | set(b)) / (n * n)
    return None if expected == 1.0 else (observed - expected) / (1.0 - expected)


def agreement(first_a: pd.DataFrame, first_b: pd.DataFrame) -> dict:
    """Two endpoints' answers to the identical first prompt of each episode."""
    a = first_a.set_index("episode_id")
    b = first_b.set_index("episode_id")
    both = a.join(b, lsuffix="_a", rsuffix="_b", how="inner")
    called = both[(both.outcome_a != "no_call") & (both.outcome_b != "no_call")]
    shocked = called[~called.is_null_a]
    fam_a = shocked.family_ok_a.astype(bool)
    fam_b = shocked.family_ok_b.astype(bool)
    return {
        "episodes_called_by_both": len(called),
        "identical_first_prompt": int((called.prompt_key_a == called.prompt_key_b).sum()),
        "same_category": _rate(called.category_a == called.category_b),
        "kappa_category": _kappa(list(called.category_a), list(called.category_b)),
        "shocked_family_ok": {
            "both": int((fam_a & fam_b).sum()),
            "only_a": int((fam_a & ~fam_b).sum()),
            "only_b": int((~fam_a & fam_b).sum()),
            "neither": int((~fam_a & ~fam_b).sum()),
        },
        "same_full_ok": _rate(shocked.full_ok_a.astype(bool) == shocked.full_ok_b.astype(bool)),
    }


# ---------------------------------------------------------------------------
# the whole evaluation
# ---------------------------------------------------------------------------


NON_LLM_ARMS = tuple(arm for arm in ARMS if arm not in LLM_ARMS)


def content_effect(run: Run, reference: Run) -> dict:
    """Q7: the same arm and episode, live content minus the scripted reference's fixed payload.

    Everything but the model's answers is shared (bank alerts, seeds, trigger, compiler,
    verifier), so the per-episode difference isolates what real content does to each LLM arm.
    """
    live = episode_frame(run.raw).set_index(["episode_id", "arm"])
    base = episode_frame(reference.raw).set_index(["episode_id", "arm"])
    out = {}
    for arm in LLM_ARMS:
        for endpoint, column in ENDPOINTS:
            a = live.xs(arm, level="arm")
            b = base.xs(arm, level="arm")
            frame = a[["cluster", "is_null"]].join((a[column] - b[column]).rename("diff"))
            out[f"{LABEL[arm]}|{endpoint}"] = _contrast(frame)
            out[f"{LABEL[arm]}|{endpoint}|shocked"] = _contrast(frame[~frame.is_null])
    return out


def _arm_digest(run: Run, arm: str) -> str:
    rows = sorted(
        (json.dumps(row, sort_keys=True) for row in run.raw if row["arm_id"] == arm),
    )
    return hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()


def non_llm_integrity(run: Run, reference: Run) -> dict:
    """Arms that never call the model must replay the reference run's records exactly.

    With the same bank alerts, arms 1 and 2, the detector and keyword controls, the upper
    bound and the oracle see identical inputs whatever the endpoint; any difference would
    mean the runs are not comparable.
    """
    differing = [
        arm for arm in NON_LLM_ARMS if _arm_digest(run, arm) != _arm_digest(reference, arm)
    ]
    return {"reference": reference.name, "arms": list(NON_LLM_ARMS), "differing": differing}


def _source(run: Run) -> dict:
    if run.manifest is None:
        return {
            "records": "reports/pilot_records.jsonl (nine of its fifteen arms)",
            "transport": "scripted (one fixed demand_up/medium payload)",
            "alerts": "frozen demo stand-in",
        }
    manifest = run.manifest
    return {
        "model_id": manifest["endpoint"]["model_id"],
        "alerts": manifest["alert_source"],
        "alert_selection_rule": manifest["alert_selection_rule"],
        "git_sha": manifest["git"]["sha"],
        "guard": manifest.get("guard"),
        "truth_identical_to_reports_pilot_truth": manifest[
            "truth_identical_to_reports_pilot_truth"
        ],
    }


def evaluate(runs: Sequence[str], *, reference: str | None, root: Path = OUT_ROOT) -> dict:
    truths = load_truth()
    loaded = [load_registered()]
    if reference is not None:
        loaded.append(load_run(reference, root=root))
    loaded.extend(load_run(name, root=root) for name in runs)
    out: dict = {
        "analysis_class": "exploratory",
        "not_a_gate3_vote": True,
        "plan": "analysis/real_content_pilot/PLAN.md",
        "runs": {},
        "agreement": {},
        "inputs_sha256": {"reports/pilot_truth.jsonl": _sha256(STORED_TRUTH)},
    }
    firsts: dict[str, pd.DataFrame] = {}
    reference_run = loaded[1] if reference is not None else None
    for run in loaded:
        entry: dict = {"source": _source(run), "readout": frozen_readout(run), "q4": q4(run)}
        if reference_run is not None and run.name in runs:
            entry["integrity"] = non_llm_integrity(run, reference_run)
            entry["q7"] = content_effect(run, reference_run)
        if run.proposals is not None:
            first = first_proposals(run, truths)
            firsts[run.name] = first
            entry.update(
                q1=q1(first), q2=q2(first, run), q3=q3(run, truths), q5=q5(run), q6=q6(run, first)
            )
        else:
            entry["q6"] = q6(run, None)
        out["runs"][run.name] = entry
        out["inputs_sha256"].update(run.inputs or {})
    for name_a, name_b in combinations(runs, 2):
        out["agreement"][f"{name_a}|{name_b}"] = agreement(firsts[name_a], firsts[name_b])
    return _clean(out)


def _clean(value):
    """JSON-safe, rounded, byte-stable."""
    if isinstance(value, dict):
        return {str(k): _clean(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_clean(v) for v in value]
    if isinstance(value, np.bool_ | bool):
        return bool(value)
    if isinstance(value, np.integer | int):
        return int(value)
    if isinstance(value, np.floating | float):
        value = float(value)
        return None if math.isnan(value) else round(value, 6)
    return value


# ---------------------------------------------------------------------------
# the smoke check (before the full live runs)
# ---------------------------------------------------------------------------


def smoke_summary(name: str, *, reference: str = "scripted-bank", root: Path = OUT_ROOT) -> dict:
    """Parse success, tokens, latency and refusals of a smoke run, and a full-run cost projection.

    The first prompt of an episode is model-independent, so the smoke's prompts are the scripted
    reference's; their live/scripted input-token ratio scales the reference's input tokens.
    """
    run = load_run(name, root=root, allow_partial=True)
    ref = load_run(reference, root=root)
    calls = [row for row in (run.spend or []) if row["event"] == "call"]
    if not calls:
        raise ValueError(f"{name}: no provider calls in spend_log.jsonl")
    ref_tokens = {
        row["prompt_hash"]: int(row["input_tokens"])
        for row in ref.ledger
        if row["physical"] == "true"
    }
    live_tokens = {
        row["prompt_hash"]: int(row["input_tokens"])
        for row in run.ledger
        if row["physical"] == "true" and row["attempt_index"] == "1"
    }
    matched = [(live_tokens[k], ref_tokens[k]) for k in live_tokens if k in ref_tokens]
    ratio = float(np.mean([live / scripted for live, scripted in matched])) if matched else None
    price_in = float(run.manifest["endpoint"]["price_input_per_mtok"])
    price_out = float(run.manifest["endpoint"]["price_output_per_mtok"])
    first_attempts = [row for row in run.proposals if row["attempt_index"] == 1]
    if not first_attempts:
        raise ValueError(f"{name}: no proposal was made; pick smoke episodes whose trigger fires")
    fallback_rate = sum(not row["parsed"] for row in first_attempts) / len(first_attempts)
    mean_out = float(np.mean([int(row["billable_output_tokens"]) for row in calls]))
    ref_physical = [int(row["input_tokens"]) for row in ref.ledger if row["physical"] == "true"]
    ref_charged = sum(1 for row in ref.ledger if row["physical"] == "false")
    base = None
    if ratio is not None:
        base = (
            sum(ref_physical) * ratio * price_in + len(ref_physical) * mean_out * price_out
        ) / 1e6
    return _clean(
        {
            "run": name,
            "episodes": run.manifest["episodes"],
            "provider_calls": len(calls),
            "refused": sum(1 for row in calls if row["status"] == "refused"),
            "retries": sum(1 for row in run.spend if row["event"] == "retry"),
            "errors": sum(1 for row in run.spend if row["event"] == "error"),
            "usd_so_far": sum(float(row["usd"]) for row in calls),
            "latency_ms": _quantiles(
                [float(r["latency_ms"]) for r in calls if r["status"] == "ok"]
            ),
            "prompt_tokens_mean": float(np.mean([int(row["prompt_tokens"]) for row in calls])),
            "billable_output_tokens_mean": mean_out,
            "parse": {
                "attempts": len(run.proposals),
                "parsed": sum(1 for row in run.proposals if row["parsed"]),
                "abstentions": sum(1 for r in run.proposals if r["parsed"] and r["abstention"]),
                "first_attempt_fallback_rate": fallback_rate,
                "errors": Counter(
                    _error_class(r["error"]) for r in run.proposals if not r["parsed"]
                ).most_common(5),
            },
            "rule_u": run.manifest.get("rule_u"),
            "projection": {
                "matched_prompts": len(matched),
                "live_to_scripted_input_token_ratio": ratio,
                "reference_physical_calls": len(ref_physical),
                "reference_charged_calls": ref_charged,
                "expected_usd": None if base is None else base * (1.0 + fallback_rate),
                "worst_case_usd": None
                if base is None
                else base * 2.0 * ref_charged / len(ref_physical),
                "note": "expected: reference physical calls, each repaired at the smoke's "
                "first-attempt fallback rate; worst case: no call shared across arms and every "
                "call repaired",
            },
        }
    )


# ---------------------------------------------------------------------------
# markdown
# ---------------------------------------------------------------------------


def _num(value, digits: int = 1) -> str:
    return "n/a" if value is None else f"{value:,.{digits}f}"


def _iv(pair, digits: int = 1) -> str:
    return "n/a" if pair is None else f"[{pair[0]:,.{digits}f}, {pair[1]:,.{digits}f}]"


def _kn(rate: dict) -> str:
    if not rate or not rate["n"]:
        return "n/a"
    return f"{rate['k']}/{rate['n']} ({100.0 * rate['rate']:.0f}%)"


def _table(header: Sequence[str], rows: Iterable[Sequence]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    lines.extend("| " + " | ".join(str(cell) for cell in row) + " |" for row in rows)
    return [*lines, ""]


def _contrast_cell(c: dict | None) -> str:
    if not c or c.get("mean") is None:
        return "n/a"
    cell = f"{c['mean']:,.1f} {_iv(c.get('normal'))}"
    if c.get("cluster_bootstrap"):
        cell += f" b{_iv(c['cluster_bootstrap'])}"
    return cell


def render(evaluation: dict) -> str:
    runs = evaluation["runs"]
    names = list(runs)
    llm_names = [n for n in names if "q1" in runs[n]]
    lines = [
        "# Real-content pilot: evaluation tables (exploratory)",
        "",
        "Generated by `analysis/real_content_pilot/evaluate.py` from committed run outputs, under",
        "`analysis/real_content_pilot/PLAN.md`. Exploratory, and not a Gate 3 vote: the registered",
        "pilot record remains `reports/pilot_report.md`. `registered` is the stored scripted pilot",
        "(one fixed demand_up/medium payload, demo alerts) restricted to the same nine arms.",
        "",
        "Intervals: `[a, b]` is the episode-level normal 95% interval; `b[a, b]` resamples seed",
        "clusters (10,000 draws, seed 20260927). Money is in the simulator's currency per episode.",
        "",
    ]
    for name in names:
        integrity = runs[name].get("integrity")
        if integrity is not None:
            verdict = (
                "identical"
                if not integrity["differing"]
                else ("DIFFERENT: " + ", ".join(integrity["differing"]))
            )
            lines.append(
                f"- {name}: the six arms that never call the model are {verdict} to "
                f"`{integrity['reference']}`."
            )
    lines += ["", "## Frozen evaluator readout", ""]
    ids = [v["id"] for v in runs[names[0]]["readout"]["go"] + runs[names[0]]["readout"]["kill"]]
    rows = []
    for criterion in ids:
        row = [f"`{criterion}`"]
        for name in names:
            readout = runs[name]["readout"]
            verdict = next(v for v in readout["go"] + readout["kill"] if v["id"] == criterion)
            is_kill = verdict in readout["kill"]
            flag = (
                ("TRIGGERED" if verdict["passed"] else "clear")
                if is_kill
                else ("pass" if verdict["passed"] else "fail")
            )
            row.append(f"{_num(verdict['estimate'], 3)} {flag}")
        rows.append(row)
    rows.append(["**decision**", *(f"**{runs[n]['readout']['decision']}**" for n in names)])
    lines += _table(["criterion", *names], rows)
    lines += [
        "`cost_frontier` is computed over the nine arms present, not the registered fifteen.",
        "",
        "## Q4. Outcome contrasts (all 120 episodes; ub-ctrl on the 96 shocked)",
        "",
    ]
    rows = []
    for name, _t, _c in CONTRASTS:
        for endpoint, _col in ENDPOINTS:
            key = f"{name}|{endpoint}"
            rows.append(
                [
                    name,
                    endpoint,
                    *(_contrast_cell(runs[n]["q4"]["overall"].get(key)) for n in names),
                ]
            )
    lines += _table(["contrast", "endpoint", *names], rows)
    lines += ["By condition, shocked episodes only (n = 24 each), gross:", ""]
    rows = []
    for name in BY_CONDITION:
        for condition in CONDITIONS:
            key = f"{name}|gross|{condition}"
            rows.append(
                [
                    name,
                    condition,
                    *(_contrast_cell(runs[n]["q4"]["by_condition"].get(key)) for n in names),
                ]
            )
    lines += _table(["contrast", "condition", *names], rows)

    q7_names = [n for n in names if "q7" in runs[n]]
    if q7_names:
        lines += [
            "## Q7. Content effect: live answers minus the scripted payload, same arm and episode",
            "",
        ]
        rows = []
        for arm in LLM_ARMS:
            for endpoint, _col in ENDPOINTS:
                for suffix, label in (("", "all 120"), ("|shocked", "shocked 96")):
                    key = f"{LABEL[arm]}|{endpoint}{suffix}"
                    rows.append(
                        [
                            LABEL[arm],
                            endpoint,
                            label,
                            *(_contrast_cell(runs[n]["q7"].get(key)) for n in q7_names),
                        ]
                    )
        lines += _table(["arm", "endpoint", "episodes", *q7_names], rows)

    lines += ["## Q1. First-proposal accuracy (the call arms 8, 9 and 10 share)", ""]
    for name in llm_names:
        block = runs[name]["q1"]
        lines += [f"### {name}", ""]
        rows = []
        for label, cell in [("all shocked", block["shocked"]), *block["by_condition"].items()]:
            outcomes = cell["outcomes"]
            rows.append(
                [
                    label,
                    cell["n"],
                    *(outcomes[o] for o in OUTCOMES),
                    *(_kn(cell[s]) for s in SCORES),
                ]
            )
        lines += _table(
            [
                "condition",
                "n",
                *OUTCOMES,
                "family",
                "onset",
                "magnitude",
                "persist.",
                "duration",
                "all fields",
            ],
            rows,
        )
        rows = []
        for family, cell in block["by_family"].items():
            rows.append(
                [
                    family,
                    cell["n"],
                    *(cell["outcomes"][o] for o in OUTCOMES),
                    _kn(cell["family_ok"]),
                    _kn(cell["full_ok"]),
                ]
            )
        lines += _table(["family", "n", *OUTCOMES, "family", "all fields"], rows)
        timing = block["timing"]
        lines += _table(
            ["condition", "called", "median tau-onset", "before onset", "fired on alert"],
            [
                [c, t["called"], _num(t["median_rel_tau"]), t["before_onset"], t["fired_on_alert"]]
                for c, t in timing.items()
            ],
        )
        lines += _table(
            ["truth", "proposed", "count"],
            [[r["truth"], r["proposed"], r["count"]] for r in block["confusion"]],
        )

    lines += ["## Q2. Early-accurate versus unreliable, paired within seed", ""]
    rows = []
    for name in llm_names:
        block = runs[name]["q2"]
        for score_name in ("family_ok", "full_ok"):
            s = block[score_name]
            rows.append(
                [
                    name,
                    score_name,
                    _kn(s["early"]),
                    _kn(s["unreliable"]),
                    f"{s['mean_diff']:+.2f} {_iv(s['normal'], 2)}",
                    f"{s['both']}/{s['early_only']}/{s['unreliable_only']}/{s['neither']}",
                ]
            )
    lines += _table(
        ["run", "score", "early", "unreliable", "early - unreliable", "both/early/unrel./neither"],
        rows,
    )
    rows = []
    for name in llm_names:
        for kind, cell in runs[name]["q2"]["by_unreliable_kind"].items():
            rows.append(
                [
                    name,
                    kind,
                    cell["n"],
                    _kn(cell["early_family_ok"]),
                    _kn(cell["unreliable_family_ok"]),
                    ", ".join(f"{k}: {v}" for k, v in sorted(cell["unreliable_proposed"].items())),
                ]
            )
    lines += _table(
        [
            "run",
            "unreliable kind",
            "seeds",
            "early family",
            "unreliable family",
            "proposed under unreliable",
        ],
        rows,
    )
    rows = []
    for name in llm_names:
        for key, cell in runs[name]["q2"]["outcomes"].items():
            rows.append(
                [
                    name,
                    key,
                    _num(cell["early"]),
                    _num(cell["unreliable"]),
                    f"{cell['mean_diff']:,.1f} {_iv(cell['normal'])}",
                    cell["n"],
                ]
            )
    lines += _table(["run", "contrast", "early", "unreliable", "difference", "seeds"], rows)

    lines += ["## Q3. Verification and rollback by proposal class", ""]
    rows = []
    for name in llm_names:
        block = runs[name]["q3"]
        for kind in ("right", "wrong", "null"):
            a10, a9 = block["arm10"][kind], block["arm9"][kind]
            rows.append(
                [
                    name,
                    kind,
                    a10["n"],
                    _kn(a10["activated"]),
                    _num(a10["median_delay"]),
                    _kn(a10["refuted"]),
                    a9["n"],
                    _kn(a9["refuted"]),
                ]
            )
    lines += _table(
        [
            "run",
            "proposal",
            "arm10 n",
            "arm10 activated",
            "median delay",
            "arm10 refuted",
            "arm9 n",
            "arm9 refuted",
        ],
        rows,
    )
    rows = [
        [
            n,
            runs[n]["q3"]["arm10_rule_u"]["events"],
            json.dumps(runs[n]["q3"]["arm10_rule_u"]["by_reason"], sort_keys=True),
        ]
        for n in llm_names
    ]
    lines += _table(["run", "Rule U coercions (arm 10 events)", "by reason"], rows)

    lines += ["## Q5. Operations", ""]
    rows = []
    for name in llm_names:
        block = runs[name]["q5"]
        provider = block.get("provider") or {}
        parse = block["parse"]
        latency = provider.get("latency_ms") or {}
        rows.append(
            [
                name,
                provider.get("physical_calls", block["ledger_this_invocation"]["physical_calls"]),
                block["ledger_this_invocation"]["charged_calls"],
                f"{parse['parsed']}/{parse['attempts']}",
                parse["empty_text"],
                provider.get("refused", "n/a"),
                provider.get("retries", "n/a"),
                _num(latency.get("p50"), 0) + " / " + _num(latency.get("p95"), 0),
                _num(provider.get("usd", block["ledger_this_invocation"]["usd_physical"]), 4),
                block["arm10_calls_per_episode"]["over_budget_4"],
            ]
        )
    lines += _table(
        [
            "run",
            "provider calls",
            "charged",
            "parsed",
            "empty",
            "refused",
            "retries",
            "latency p50/p95 ms",
            "USD",
            "arm10 >4 calls",
        ],
        rows,
    )
    rows = []
    for name in llm_names:
        for error, count in runs[name]["q5"]["parse"]["top_errors"]:
            rows.append([name, count, f"`{error}`"])
    if rows:
        lines += _table(["run", "count", "parse error"], rows)

    lines += ["## Q6. Null controls (12 silent, 12 false-alert)", ""]
    rows = []
    for name in names:
        for kind, _condition in NULL_KINDS:
            block = runs[name]["q6"][kind]
            rows.append(
                [
                    name,
                    kind,
                    *(
                        _kn(block[LABEL[a]]["any_active"])
                        for a in (ARM8, ARM9, ARM10, CTRL, KEYWORD)
                    ),
                    _contrast_cell(block["arm8-arm1|gross"]),
                    _contrast_cell(block["arm10-arm1|gross"]),
                    ", ".join(
                        f"{k}: {v}" for k, v in sorted(block.get("first_proposed", {}).items())
                    )
                    or "n/a",
                ]
            )
    lines += _table(
        [
            "run",
            "nulls",
            "arm8 active",
            "arm9 active",
            "arm10 active",
            "ctrl active",
            "keyword active",
            "arm8-arm1 gross",
            "arm10-arm1 gross",
            "first proposal",
        ],
        rows,
    )
    if evaluation["agreement"]:
        lines += ["## Cross-endpoint agreement on the shared first proposal", ""]
        rows = []
        for pair, cell in evaluation["agreement"].items():
            fam = cell["shocked_family_ok"]
            rows.append(
                [
                    pair,
                    cell["episodes_called_by_both"],
                    cell["identical_first_prompt"],
                    _kn(cell["same_category"]),
                    _num(cell["kappa_category"], 2),
                    f"{fam['both']}/{fam['only_a']}/{fam['only_b']}/{fam['neither']}",
                ]
            )
        lines += _table(
            [
                "pair",
                "called by both",
                "identical prompt",
                "same answer",
                "kappa",
                "family ok both/a/b/neither",
            ],
            rows,
        )
    return "\n".join(lines).rstrip() + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m analysis.real_content_pilot.evaluate")
    ap.add_argument("--runs", nargs="+", default=[], help="live runs, in report order")
    ap.add_argument("--reference", default="scripted-bank", help="'' to omit")
    ap.add_argument("--smoke", help="summarise a smoke run instead, and project the full cost")
    ap.add_argument("--root", type=Path, default=OUT_ROOT)
    ap.add_argument("--out-json", type=Path, default=OUT_ROOT / "evaluation.json")
    ap.add_argument("--out-md", type=Path, default=OUT_ROOT / "evaluation.md")
    args = ap.parse_args(argv)
    if args.smoke:
        summary = smoke_summary(args.smoke, reference=args.reference, root=args.root)
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0
    evaluation = evaluate(args.runs, reference=args.reference or None, root=args.root)
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(evaluation, indent=2, sort_keys=True) + "\n", "utf-8")
    args.out_md.write_text(render(evaluation), encoding="utf-8")
    print(f"wrote {args.out_json} and {args.out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
