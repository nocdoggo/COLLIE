"""Write canonical-JSON test vectors for the browser replay verifier.

The expected values come from ``plan_b.domain.digest`` (the server's canonical JSON), so the
TypeScript canonicalization is checked against the real convention rather than a copy of it.
The ``trace_cases`` are traces that exactly one check of each verifier must reject; the web
suite (tests/integrity.test.ts) and the Python suite (tests/test_trace_verifier.py) both run
them from their UTF-8 bytes, so the browser verifier and ``plan-b verify-trace`` stay
equivalent. ``nesting_limit_trace_text`` is the deepest trace both must still accept.
Run from ``apps/plan_b``: ``uv run python web/tests/make_vectors.py``.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from plan_b.domain.digest import canonical_json, sha256_hex
from plan_b.evaluation.export_trace import MAX_NESTING

OUT = Path(__file__).resolve().parent / "fixtures" / "canonical_vectors.json"

NUMBERS: list[Any] = [
    0,
    1,
    -1,
    2**53 + 1,
    -(2**70),
    1.0,
    -0.0,
    0.0,
    100.0,
    123.456,
    0.1 + 0.2,
    1e15,
    1e16,
    1234567890123456.0,
    12345678901234567.0,
    1e22,
    0.0001,
    0.00001,
    1.5e-5,
    1e-7,
    5e-324,
    1.7976931348623157e308,
    3.141592653589793,
    float("nan"),
    float("inf"),
    float("-inf"),
]

STRINGS = [
    "plain",
    "héllo",
    "日本",
    "\U0001f600 emoji",
    "line sep ",
    "del\x7f",
    "ctl\x00\x01\x1f",
    'quote " and backslash \\',
    "\t\n\r\b\f",
    "slash / stays",
    "<script>&amp;</script>",
]

KEYS = {
    "b": 1,
    "a": 2,
    "B": 3,
    "": 4,
    "é": 5,
    "\U0001f600": 6,
    "￿": 7,
    "": 8,
    "a\U0001f600": 9,
    "a￿": 10,
    "aa": 11,
}

NESTED = {
    "frames": [{"seq": 1, "state": {"clock": "2026-11-05T21:40:00Z", "x": [1, 2.5, None]}}],
    "flags": [True, False, None],
    "empty_obj": {},
    "empty_list": [],
    "text": "Our projector delivery may be about 25 minutes later.",
}


def chain_fold(frame_hashes: list[str]) -> str:
    """The chain fold the browser verifier documents (CHAIN_FOLD_DESCRIPTION)."""
    acc = ""
    for h in frame_hashes:
        acc = sha256_hex(acc + h)
    return acc


LONE_SURROGATE = re.compile("[\ud800-\udfff]")


def escape_lone_surrogates(text: str) -> str:
    """Each lone surrogate as a lowercase \\uXXXX escape, as JavaScript's JSON.stringify writes
    it. Only strings can hold one, so the result is still the same JSON."""
    return LONE_SURROGATE.sub(lambda m: f"\\u{ord(m.group()):04x}", text)


def python_digest(value: Any) -> str:
    return sha256_hex(canonical_json(value))


def browser_digest(value: Any) -> str:
    """The hash the browser computes for a value with a lone surrogate, which Python cannot
    encode: its canonical JSON with the surrogate escaped."""
    return sha256_hex(escape_lone_surrogates(canonical_json(value)))


def seal(trace: dict[str, Any], digest: Callable[[Any], str] = python_digest) -> dict[str, Any]:
    """The trace with its integrity block recomputed from its content, as the exporter does."""
    body = {k: v for k, v in trace.items() if k != "integrity"}
    frame_hashes = [digest(f) for f in body["frames"]]
    return {
        **body,
        "integrity": {
            "algorithm": "sha256",
            "frame_hashes": frame_hashes,
            "chain_sha256": chain_fold(frame_hashes),
            "content_sha256": digest(body),
        },
    }


def nested(levels: int) -> list[Any]:
    """``levels`` arrays, each holding the next; the innermost is empty."""
    value: list[Any] = []
    for _ in range(levels - 1):
        value = [value]
    return value


def fake_trace() -> dict[str, Any]:
    frames = [
        {
            "seq": i,
            "revision": 3 + i,
            "scenario_time": f"2026-11-05T21:4{i}:00Z",
            "cause_kind": "observation",
            "cause_ref": f"obs_{i}",
            "summary": f"frame {i} café \U0001f600",
            "state": {"revision": 3 + i, "ratio": 0.5 * i, "budget": {"remaining_cents": 15000}},
        }
        for i in range(3)
    ]
    trace: dict[str, Any] = {
        "trace_version": "1.0.0",
        "runtime_version": "1.0.0",
        "kind": "plan_b_sanitized_trace",
        "mode_label": "Recorded replay",
        "source": {"episode_id": "ep_test", "policy_id": None, "generator": "vectors"},
        "frames": frames,
        "tool_calls": [],
        "decisions": [],
        "receipts": [],
        "final_state": frames[-1]["state"],
    }
    return seal(trace)


def trace_cases(trace: dict[str, Any]) -> list[dict[str, Any]]:
    """Traces that exactly one verifier check rejects, named by that check."""

    def clone() -> dict[str, Any]:
        # A JSON round trip, so final_state no longer shares the last frame's state dict.
        value: dict[str, Any] = json.loads(json.dumps(trace))
        return value

    t4 = clone()
    t4["integrity"]["algorithm"] = "md5"
    t5 = clone()
    t5["final_state"]["revision"] += 1
    t6 = clone()
    t6["kind"] = "other_trace"
    t7 = clone()
    t7["trace_version"] = "0.9.0"
    t9 = clone()
    t9["frames"][1]["summary"] = "frame 1 cut \ud800 here"
    t10 = clone()
    # The trace object is level 1, so these arrays reach one level past the limit.
    t10["pad"] = nested(MAX_NESTING)
    # No frames, so there is nothing to hash and no last frame to compare: the exporter would
    # still write frame_hashes as an empty list, and both verifiers reject a block without one.
    t11 = clone()
    t11["frames"] = []
    t11 = seal(t11)
    del t11["integrity"]["frame_hashes"]
    cases = [
        ("t4_algorithm_label", "algorithm", "integrity.algorithm is md5; nothing rehashed", t4),
        (
            "t5_final_revision_rehashed",
            "final_revision",
            "final_state.revision is one past the last frame's; every hash recomputed",
            seal(t5),
        ),
        ("t6_kind_rehashed", "kind", "kind is not plan_b_sanitized_trace; rehashed", seal(t6)),
        ("t7_version_rehashed", "trace_version", "trace_version is 0.9.0; rehashed", seal(t7)),
    ]
    texts = [
        (name, check, description, json.dumps(value, ensure_ascii=False, indent=2))
        for name, check, description, value in cases
    ]
    texts += [
        (
            "t8_bom",
            "byte_order_mark",
            "the intact trace's UTF-8 bytes after a byte order mark",
            "\ufeff" + json.dumps(trace, ensure_ascii=False, indent=2),
        ),
        (
            "t9_lone_surrogate",
            "lone_surrogate",
            "a frame summary holds a lone surrogate (\\ud800); hashed as the browser computes them",
            escape_lone_surrogates(
                json.dumps(seal(t9, browser_digest), ensure_ascii=False, indent=2)
            ),
        ),
        (
            "t10_nesting_too_deep",
            "nesting",
            f"a value nested {MAX_NESTING + 1} levels deep; rehashed",
            json.dumps(seal(t10), ensure_ascii=False),
        ),
        (
            "t11_frame_hashes_missing",
            "frames",
            "no frames and no integrity.frame_hashes; every other hash recomputed",
            json.dumps(t11, ensure_ascii=False, indent=2),
        ),
    ]
    return [
        {"name": name, "failing_check": check, "description": description, "text": text}
        for name, check, description, text in texts
    ]


def nesting_limit_trace(trace: dict[str, Any]) -> str:
    """The trace with a value nested exactly MAX_NESTING levels deep: both verifiers accept it."""
    deepest: dict[str, Any] = json.loads(json.dumps(trace))
    deepest["pad"] = nested(MAX_NESTING - 1)
    return json.dumps(seal(deepest), ensure_ascii=False)


def vector(name: str, value: Any, *, ensure_ascii: bool, indent: int | None) -> dict[str, Any]:
    text = json.dumps(value, ensure_ascii=ensure_ascii, indent=indent)
    parsed = json.loads(text)
    canonical = canonical_json(parsed)
    return {
        "name": name,
        "text": text,
        "canonical": canonical,
        "sha256": sha256_hex(canonical),
    }


def main() -> None:
    vectors = [
        vector("numbers", NUMBERS, ensure_ascii=False, indent=None),
        vector("strings_raw", STRINGS, ensure_ascii=False, indent=2),
        vector("strings_escaped", STRINGS, ensure_ascii=True, indent=None),
        vector("key_order", KEYS, ensure_ascii=False, indent=1),
        vector("nested", NESTED, ensure_ascii=False, indent=2),
    ]
    trace = fake_trace()
    payload = {
        "generator": "web/tests/make_vectors.py using plan_b.domain.digest.canonical_json",
        "vectors": vectors,
        "trace_text": json.dumps(trace, ensure_ascii=False, indent=2),
        "tampered_trace_text": json.dumps(
            {
                **trace,
                "frames": [{**trace["frames"][0], "summary": "edited"}, *trace["frames"][1:]],
            },
            ensure_ascii=False,
            indent=2,
        ),
        "trace_cases": trace_cases(trace),
        "nesting_limit_trace_text": nesting_limit_trace(trace),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    # The byte order mark of t8 is written as an escape so that the fixture shows it.
    text = json.dumps(payload, ensure_ascii=False, indent=2).replace("\ufeff", "\\ufeff")
    OUT.write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
