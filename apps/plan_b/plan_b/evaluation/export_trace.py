"""Sanitized, integrity-protected trace export (trace format 1.0.0) and verification.

A trace is built from an *executed* episode's persisted public records: per-revision public
snapshots, sanitized tool calls, policy decisions and receipts. It contains no tokens, join
codes, moderator code, private case reference, status model, world events or predicates. The
exporter refuses to write a trace in which the leak checker finds private markers.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from plan_b.domain.digest import canonical_json, sha256_hex
from plan_b.domain.models import RUNTIME_VERSION, TRACE_VERSION, EventStateView
from plan_b.store import repo
from plan_b.store.database import Database
from plan_b.store.projection_db import TRACE_VIEWER, build_view
from plan_b.world.leakcheck import find_leaks
from plan_b.world.world import NO_CASE, load_case

GENERATOR = "plan_b.evaluation.export_trace"


class TraceLeakError(Exception):
    pass


def _compact_envelope(env: dict[str, Any], evaluations: dict[str, Any]) -> dict[str, Any]:
    """Full state views are already in frames and each evaluation is stored once in
    ``evaluations``; keep tool-call envelopes small."""
    data = env.get("data")
    if not isinstance(data, dict):
        return env
    if env.get("tool") == "get_event_state":
        return {
            **env,
            "data": {
                "omitted": "state view; see the frame for this revision",
                "revision": data.get("revision"),
            },
        }
    if env.get("tool") == "evaluate_candidates" and "evaluation_id" in data:
        evaluations.setdefault(data["evaluation_id"], data)
        return {**env, "data": {"evaluation_ref": data["evaluation_id"]}}
    return env


def _compact_state(state: dict[str, Any], evaluations: dict[str, Any]) -> dict[str, Any]:
    latest = state.get("latest_evaluation")
    if isinstance(latest, dict) and "evaluation_id" in latest:
        evaluations.setdefault(latest["evaluation_id"], latest)
        return {**state, "latest_evaluation": {"evaluation_ref": latest["evaluation_id"]}}
    return state


def rehydrate_state(trace: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    """Restore a frame's full ``latest_evaluation`` from the trace's ``evaluations`` map."""
    latest = state.get("latest_evaluation")
    if isinstance(latest, dict) and set(latest) == {"evaluation_ref"}:
        return {**state, "latest_evaluation": trace["evaluations"][latest["evaluation_ref"]]}
    return state


def build_trace(db: Database, episode_id: str, *, policy_id: str | None = None) -> dict[str, Any]:
    with db.read() as conn:
        ep = repo.get_episode(conn, episode_id)
        rows = conn.execute(
            "SELECT revision, at, view_json FROM revision_snapshots WHERE episode_id = ?"
            " ORDER BY revision",
            (episode_id,),
        ).fetchall()
        transitions = {t.revision: t for t in repo.transitions(conn, episode_id)}
        tool_calls = repo.tool_calls(conn, episode_id)
        decisions = repo.decisions(conn, episode_id)
        receipts = repo.receipts(conn, episode_id)
        final = build_view(conn, episode_id, TRACE_VIEWER, visibility="audit")
        private_row = conn.execute(
            "SELECT case_ref FROM episode_private WHERE episode_id = ?", (episode_id,)
        ).fetchone()
    evaluations: dict[str, Any] = {}
    frames = []
    for i, row in enumerate(rows):
        tr = transitions.get(row["revision"])
        frames.append(
            {
                "seq": i + 1,
                "revision": row["revision"],
                "scenario_time": row["at"],
                "cause_kind": tr.cause_kind if tr else "snapshot",
                "cause_ref": tr.cause_ref if tr else None,
                "summary": tr.summary if tr else "",
                "state": _compact_state(json.loads(row["view_json"]), evaluations),
            }
        )
    trace: dict[str, Any] = {
        "trace_version": TRACE_VERSION,
        "runtime_version": RUNTIME_VERSION,
        "kind": "plan_b_sanitized_trace",
        "mode_label": "Recorded replay",
        "source": {
            "episode_id": ep.episode_id,
            "scenario_id": ep.scenario_id,
            "profile_id": ep.profile_id,
            "public_fixture_sha256": ep.public_fixture_sha256,
            "policy_id": policy_id,
            "generator": GENERATOR,
        },
        "frames": frames,
        "tool_calls": [
            {**tc.model_dump(mode="json"), "envelope": _compact_envelope(tc.envelope, evaluations)}
            for tc in tool_calls
        ],
        "evaluations": evaluations,
        "compaction": (
            "frames[].state.latest_evaluation and evaluate_candidates envelope data hold"
            " {evaluation_ref}; the full EvaluationResult is evaluations[evaluation_ref]"
        ),
        "decisions": [d.model_dump(mode="json") for d in decisions],
        "receipts": [r.model_dump(mode="json") for r in receipts],
        "final_state": final.model_dump(mode="json"),
    }
    trace["integrity"] = integrity(trace)
    if private_row is not None and private_row["case_ref"] != NO_CASE:
        leaks = find_leaks(
            canonical_json(trace), load_case(private_row["case_ref"]), final.observations, None
        )
        if leaks:
            raise TraceLeakError(f"refusing to export: private markers found: {leaks[:5]}")
    return trace


def integrity(trace: dict[str, Any]) -> dict[str, Any]:
    frame_hashes = [sha256_hex(canonical_json(f)) for f in trace["frames"]]
    chain = ""
    for h in frame_hashes:
        chain = sha256_hex(chain + h)
    body = {k: v for k, v in trace.items() if k != "integrity"}
    return {
        "algorithm": "sha256",
        "frame_hashes": frame_hashes,
        "chain_sha256": chain,
        "content_sha256": sha256_hex(canonical_json(body)),
    }


def verify_trace(trace: dict[str, Any]) -> list[str]:
    """Return integrity problems; empty when the trace is intact."""
    problems = []
    expected = integrity(trace)
    got = trace.get("integrity", {})
    for key in ("frame_hashes", "chain_sha256", "content_sha256"):
        if got.get(key) != expected[key]:
            problems.append(f"{key} mismatch")
    if trace.get("trace_version") != TRACE_VERSION:
        problems.append("unsupported trace version")
    if trace["frames"]:
        last = EventStateView.model_validate(rehydrate_state(trace, trace["frames"][-1]["state"]))
        final = EventStateView.model_validate(trace["final_state"])
        if last.revision != final.revision:
            problems.append("last frame revision differs from final state")
    return problems


def write_trace(trace: dict[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(trace, indent=1, sort_keys=True) + "\n")
    return path
