"""Sanitized, integrity-protected trace export (trace format 1.0.0) and verification.

A trace is built from an *executed* episode's persisted public records: per-revision public
snapshots, sanitized tool calls, policy decisions and receipts. It contains no tokens, join
codes, moderator code, private case reference, status model, world events or predicates. The
exporter refuses to write a trace in which the leak checker finds private markers.
"""

from __future__ import annotations

import codecs
import json
import re
from pathlib import Path
from typing import Any

from plan_b.domain.digest import canonical_json, sha256_hex
from plan_b.domain.models import RUNTIME_VERSION, TRACE_VERSION
from plan_b.store import repo
from plan_b.store.database import Database
from plan_b.store.projection_db import TRACE_VIEWER, build_view
from plan_b.world.leakcheck import find_leaks
from plan_b.world.world import NO_CASE, load_case

GENERATOR = "plan_b.evaluation.export_trace"
TRACE_KIND = "plan_b_sanitized_trace"
ALGORITHM = "sha256"

# Limits the browser verifier (web/src/replay/integrity.ts) applies with the same values: the
# deepest nesting of objects and arrays (the trace object is level 1), and the longest integer
# in digits without the sign (Python's default int_max_str_digits, fixed here so a different
# interpreter setting cannot change the verdict).
MAX_NESTING = 256
MAX_INT_DIGITS = 4300
_INT_LIMIT = 10**MAX_INT_DIGITS
_LONE_SURROGATE = re.compile("[\ud800-\udfff]")

BOM_PROBLEM = "trace starts with a UTF-8 byte order mark"
UTF8_PROBLEM = "trace is not valid UTF-8"
NOT_OBJECT_PROBLEM = "trace is not a JSON object"
NESTING_PROBLEM = f"trace nests deeper than {MAX_NESTING} levels"
SURROGATE_PROBLEM = "trace has a string that is not well-formed Unicode (a lone surrogate)"
INT_PROBLEM = f"trace has an integer longer than {MAX_INT_DIGITS} digits"
FRAME_HASHES_PROBLEM = "frame_hashes is missing or not a list"


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
        "kind": TRACE_KIND,
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
        "algorithm": ALGORITHM,
        "frame_hashes": frame_hashes,
        "chain_sha256": chain,
        "content_sha256": sha256_hex(canonical_json(body)),
    }


def _revision(state: Any) -> int | None:
    """A state's integer revision; anything else (missing, float, bool, string) is None."""
    value = state.get("revision") if isinstance(state, dict) else None
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _value_problem(trace: Any) -> str | None:
    """The first value the hashes cannot be computed over, walking without recursion: nesting
    deeper than MAX_NESTING, a string (or key) with a lone surrogate, which UTF-8 cannot
    encode, or an integer longer than MAX_INT_DIGITS digits."""
    stack: list[tuple[Any, int]] = [(trace, 1)]
    while stack:
        value, depth = stack.pop()
        if isinstance(value, dict):
            if depth > MAX_NESTING:
                return NESTING_PROBLEM
            for key, item in value.items():
                if isinstance(key, str) and _LONE_SURROGATE.search(key):
                    return SURROGATE_PROBLEM
                stack.append((item, depth + 1))
        elif isinstance(value, list | tuple):
            if depth > MAX_NESTING:
                return NESTING_PROBLEM
            stack.extend((item, depth + 1) for item in value)
        elif isinstance(value, str):
            if _LONE_SURROGATE.search(value):
                return SURROGATE_PROBLEM
        elif isinstance(value, int) and not isinstance(value, bool) and abs(value) >= _INT_LIMIT:
            return INT_PROBLEM
    return None


def _bounded_int(text: str) -> int:
    if len(text.lstrip("-")) > MAX_INT_DIGITS:
        raise ValueError(INT_PROBLEM)
    return int(text)


def verify_trace_bytes(data: bytes) -> list[str]:
    """Return the problems of a trace file's exact bytes; empty when the trace is intact.

    Before ``verify_trace`` it rejects what the browser replay also rejects when it decodes the
    bytes itself: a UTF-8 byte order mark, bytes that are not UTF-8 (encoded surrogates
    included), and text that is not one JSON object. Every problem is reported, never raised.
    """
    if data.startswith(codecs.BOM_UTF8):
        return [BOM_PROBLEM]
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return [UTF8_PROBLEM]
    try:
        value = json.loads(text, parse_int=_bounded_int)
    except RecursionError:
        return [NESTING_PROBLEM]
    except json.JSONDecodeError as exc:
        # Some messages already end in "at" ("Invalid control character at").
        msg = exc.msg.removesuffix(" at")
        return [f"trace is not valid JSON: {msg} at line {exc.lineno} column {exc.colno}"]
    except ValueError as exc:
        # Raised by _bounded_int.
        return [str(exc)]
    if not isinstance(value, dict):
        return [NOT_OBJECT_PROBLEM]
    return verify_trace(value)


def verify_trace(trace: dict[str, Any]) -> list[str]:
    """Return integrity problems; empty when the trace is intact.

    It makes the same checks as the browser replay's ``verifyTraceText``
    (web/src/replay/integrity.ts), so both accept and reject the same traces; the shared vectors
    in web/tests/fixtures/canonical_vectors.json check that in both test suites. A value the
    hashes cannot be computed over (see ``_value_problem``) is reported as the only problem. The
    hashes are not signed: an intact trace is consistent with its own hashes, which detects
    corruption, not deliberate edits. For a file, use ``verify_trace_bytes``.
    """
    value_problem = _value_problem(trace)
    if value_problem is not None:
        return [value_problem]
    frames = trace.get("frames")
    got = trace.get("integrity")
    if not isinstance(frames, list):
        return ["trace has no frames array"]
    if not isinstance(got, dict):
        return ["trace has no integrity block"]
    problems = []
    expected = integrity(trace)
    for key in ("frame_hashes", "chain_sha256", "content_sha256"):
        if key == "frame_hashes" and not isinstance(got.get(key), list):
            # Even with no frames: the exporter writes an empty list, never nothing.
            problems.append(FRAME_HASHES_PROBLEM)
        elif got.get(key) != expected[key]:
            problems.append(f"{key} mismatch")
    if got.get("algorithm") != ALGORITHM:
        problems.append("unsupported integrity algorithm")
    if trace.get("kind") != TRACE_KIND:
        problems.append("unexpected trace kind")
    if trace.get("trace_version") != TRACE_VERSION:
        problems.append("unsupported trace version")
    if frames:
        last = frames[-1].get("state") if isinstance(frames[-1], dict) else None
        last_revision = _revision(last)
        if last_revision is None or last_revision != _revision(trace.get("final_state")):
            problems.append("last frame revision differs from final state")
    return problems


def write_trace(trace: dict[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(trace, indent=1, sort_keys=True) + "\n")
    return path
