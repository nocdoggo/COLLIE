"""analysis/real_content_pilot/evaluate.py — the pre-registered analysis, tested offline.

The unit tests pin the scoring rules to the frozen evaluator's own definitions; the slow test
evaluates the committed scripted-bank reference run and checks the readout against the
registered pilot report.
"""

from __future__ import annotations

import csv
import json
import re
import shutil
from dataclasses import asdict
from pathlib import Path

import pytest

from analysis.real_content_pilot.evaluate import (
    _kappa,
    evaluate,
    payload_key,
    proposal_events,
    render,
    score,
    smoke_summary,
)
from analysis.real_content_pilot.runner import _endpoint_meta, run_pilot, write_run
from analysis.real_content_pilot.transport import GuardedTransport
from collie.arms.protocols import ProposalPayload
from collie.arms.shockspec import ARM8_ARM_ID
from collie.contracts import DurationBin, MagnitudeBin, Persistence, ShockFamily, ShockSpec
from collie.eval.truth import _matches_truth, load_episode_truth_jsonl, truth_by_episode
from collie.llm.demo import scripted_endpoint
from collie.spec.registry import FAMILY_TARGET_STREAM, expected_direction, legal_pairs
from collie.verify.registry import REGISTERED_ONSET_WINDOWS
from tools.run_arms import _DemoTransport

REPO = Path(__file__).resolve().parents[1]
TRUTH = REPO / "reports" / "pilot_truth.jsonl"
REFERENCE = REPO / "analysis" / "real_content_pilot" / "out" / "scripted-bank"


def _wire(payload: ProposalPayload) -> dict:
    """A payload as ``proposals.jsonl`` stores it (enum values, lists)."""
    out = {}
    for key, value in asdict(payload).items():
        if isinstance(value, tuple):
            value = list(value)
        out[key] = value.value if hasattr(value, "value") else value
    return out


def _shapes():
    for family, signature in legal_pairs():
        if family is ShockFamily.NO_CHANGE:
            continue
        for window in REGISTERED_ONSET_WINDOWS:
            for magnitude in (MagnitudeBin.LOW, MagnitudeBin.MEDIUM, MagnitudeBin.HIGH):
                for persistence in Persistence:
                    for duration in DurationBin:
                        yield ProposalPayload(
                            target_stream=FAMILY_TARGET_STREAM[family],
                            shock_family=family,
                            direction=expected_direction(family, signature),
                            onset_window=window,
                            magnitude_bin=magnitude,
                            persistence=persistence,
                            duration_bin=duration,
                            evidence_refs=(),
                            prospective_signature=signature,
                        )


def test_full_ok_is_the_frozen_truth_match() -> None:
    """``score(...)["full_ok"]`` must be ``collie.eval.truth._matches_truth``, shape for shape."""
    rows = {}
    with TRUTH.open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            rows.setdefault((row["family"], row["direction"]), row)
    truths = truth_by_episode(load_episode_truth_jsonl(TRUTH))
    shapes = list(_shapes())
    checked = 0
    for row in rows.values():
        truth = truths[row["episode_id"]]
        for tau in (truth.onset_period - 3, truth.onset_period, truth.onset_period + 2):
            for payload in shapes:
                spec = ShockSpec(
                    **asdict(payload),
                    tau_j=tau,
                    proposal_index=1,
                    model_id="m",
                    decoding_hash="det-v1",
                    prompt_hash="h",
                )
                assert score(_wire(payload), row, tau)["full_ok"] == _matches_truth(spec, truth)
                checked += 1
    assert len(rows) == 6 and checked == 6 * 3 * len(shapes)


def test_abstentions_and_failures_score_as_wrong_on_a_shocked_episode() -> None:
    truth = json.loads(TRUTH.read_text(encoding="utf-8").splitlines()[0])
    abstain = {"shock_family": "no_change"}
    assert not any(score(abstain, truth, 10).values())
    assert not any(score(None, truth, 10).values())


def test_payload_key_matches_the_headroom_keys() -> None:
    assert payload_key(None) is None
    level = {"shock_family": "demand_level", "direction": "demand_down"}
    assert payload_key(level) == "demand_level:demand_down"
    assert payload_key({"shock_family": "compound", "direction": "mixed"}) == "compound"


def _row(period, attempt, *, parsed, abstention=None, family="demand_level"):
    return {
        "episode_id": "dev/f1/s1/early_accurate",
        "arm_id": ARM8_ARM_ID,
        "period": period,
        "attempt_index": attempt,
        "parsed": parsed,
        "abstention": abstention,
        "payload": {"shock_family": family} if parsed else None,
        "prompt_key": f"p{period}-{attempt}",
        "arm10_coerced_abstention": False,
        "rule_u_reason": None,
    }


def test_proposal_events_keep_the_final_attempt_of_each_period() -> None:
    events = proposal_events(
        [
            _row(12, 1, parsed=False),
            _row(12, 2, parsed=True, abstention=True, family="no_change"),
            _row(20, 1, parsed=True, abstention=False),
            _row(30, 1, parsed=False),
            _row(30, 2, parsed=False),
        ]
    )
    assert list(events.tau) == [12, 20, 30]
    assert list(events.outcome) == ["abstain", "shock", "parse_fail"]
    assert list(events.repaired) == [True, False, False]
    assert list(events.attempts) == [2, 1, 2]
    assert list(events.event_index) == [1, 2, 3]


def test_kappa() -> None:
    assert _kappa(["a", "b", "a"], ["a", "b", "a"]) == pytest.approx(1.0)
    assert _kappa(["a", "b"], ["b", "a"]) == pytest.approx(-1.0)
    assert _kappa(["a", "a"], ["a", "a"]) is None  # no variation: undefined
    assert _kappa([], []) is None


def _report_estimates() -> dict[str, float]:
    text = (REPO / "reports" / "pilot_report.md").read_text(encoding="utf-8")
    out = {}
    for match in re.finditer(r"^\| `([a-z_]+)` \| ([^|]+) \|", text, flags=re.MULTILINE):
        out[match.group(1)] = float(match.group(2))
    return out


@pytest.mark.slow
@pytest.mark.skipif(not REFERENCE.is_dir(), reason="the reference run is not committed yet")
def test_evaluation_of_the_committed_reference_run() -> None:
    evaluation = evaluate(["scripted-bank"], reference=None)
    registered = evaluation["runs"]["registered"]
    # Every criterion that does not depend on which arms are present reproduces the report.
    reported = _report_estimates()
    verdicts = registered["readout"]["go"] + registered["readout"]["kill"]
    assert len(verdicts) == len(reported) == 15
    for verdict in verdicts:
        if verdict["id"] == "cost_frontier":  # nine arms here, fifteen in the registered run
            continue
        assert verdict["estimate"] == pytest.approx(reported[verdict["id"]], rel=1e-5, abs=1e-6)
    assert registered["readout"]["decision"] == "kill-or-reframe"
    assert registered["readout"]["freeze_drift"] == []

    reference = evaluation["runs"]["scripted-bank"]
    shocked = reference["q1"]["shocked"]
    assert shocked["n"] == 96 and sum(shocked["outcomes"].values()) == 96
    assert sum(cell["n"] for cell in reference["q1"]["by_condition"].values()) == 96
    assert reference["q6"]["silent"]["n"] == reference["q6"]["false_alert"]["n"] == 12
    # The scripted transport's one payload is demand_up: family-correct exactly on family 1.
    assert reference["q1"]["by_family"]["demand_level:demand_up"]["family_ok"]["rate"] == 1.0
    assert shocked["family_ok"]["k"] == 16
    # Q1's premise: arms 8, 9 and 10 send the identical first prompt in every episode.
    with (REFERENCE / "proposals.jsonl").open(encoding="utf-8") as handle:
        events = proposal_events([json.loads(line) for line in handle])
    first = events[events.event_index == 1]
    per_episode = first.groupby("episode_id").agg(
        arms=("arm", "nunique"), keys=("prompt_key", "nunique")
    )
    assert (per_episode.arms == 3).all() and (per_episode["keys"] == 1).all()
    q4 = reference["q4"]["overall"]
    assert q4["ub-ctrl|gross"]["n"] == 96 and q4["arm10-arm1|gross"]["n"] == 120
    markdown = render(evaluation)
    assert "## Q1." in markdown and "nan" not in markdown.lower()


@pytest.mark.slow
@pytest.mark.skipif(not REFERENCE.is_dir(), reason="the reference run is not committed yet")
def test_two_identical_runs_agree_fully_and_replay_the_non_llm_arms(tmp_path) -> None:
    for name in ("scripted-bank", "copy-a", "copy-b"):
        shutil.copytree(REFERENCE, tmp_path / name)
    evaluation = evaluate(["copy-a", "copy-b"], reference="scripted-bank", root=tmp_path)
    for name in ("copy-a", "copy-b"):
        assert evaluation["runs"][name]["integrity"]["differing"] == []
        effects = evaluation["runs"][name]["q7"]
        assert effects["arm10|gross"]["n"] == 120 and effects["arm8|net|shocked"]["n"] == 96
        assert all(cell["mean"] == 0.0 for cell in effects.values())
    pair = evaluation["agreement"]["copy-a|copy-b"]
    assert pair["identical_first_prompt"] == pair["episodes_called_by_both"] > 0
    assert pair["same_category"]["rate"] == 1.0
    assert pair["kappa_category"] is None  # the scripted payload never varies: kappa undefined
    assert "## Cross-endpoint agreement" in render(evaluation)


@pytest.mark.skipif(not REFERENCE.is_dir(), reason="the reference run is not committed yet")
def test_smoke_projection_recovers_the_reference_cost_for_the_same_transport(tmp_path) -> None:
    """Replay the scripted transport as if it were live: the projection must be the actual cost."""
    shutil.copytree(REFERENCE, tmp_path / "scripted-bank")
    endpoint = scripted_endpoint()
    guard = GuardedTransport(
        inner=_DemoTransport(),
        endpoint=endpoint,
        spend_log=tmp_path / "smoke" / "spend_log.jsonl",
        spend_cap_usd=1.0,
        max_physical_calls=50,
    )
    run = run_pilot(
        endpoint=endpoint,
        transport=guard,
        alert_source="bank",
        cache_dir=tmp_path / "cache",
        episode_ids=["dev/f1/s1050000/early_accurate", "cal/f6/s6060000/unreliable"],
    )
    write_run(
        run,
        out_dir=tmp_path / "smoke",
        local_dir=tmp_path / "local",
        meta={"run_name": "smoke", "endpoint": _endpoint_meta(endpoint), "alert_source": "bank"},
    )
    summary = smoke_summary("smoke", reference="scripted-bank", root=tmp_path)
    assert summary["provider_calls"] == guard.physical_calls > 0
    assert summary["refused"] == summary["retries"] == summary["errors"] == 0
    projection = summary["projection"]
    # The spend log and the proposal log share the model-free prompt digest: every call matches.
    assert projection["matched_prompts"] == summary["provider_calls"]
    assert projection["live_to_scripted_input_token_ratio"] == pytest.approx(1.0)
    with (REFERENCE / "ledger.csv").open(encoding="utf-8", newline="") as handle:
        actual = sum(
            float(r["usd_cost"]) for r in csv.DictReader(handle) if r["physical"] == "true"
        )
    assert projection["expected_usd"] == pytest.approx(actual, rel=1e-3)
    assert projection["worst_case_usd"] > projection["expected_usd"]
