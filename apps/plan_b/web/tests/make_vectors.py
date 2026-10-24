"""Write canonical-JSON test vectors for the browser replay verifier.

The expected values come from ``plan_b.domain.digest`` (the server's canonical JSON), so the
TypeScript canonicalization is checked against the real convention rather than a copy of it.
Run from ``apps/plan_b``: ``uv run python web/tests/make_vectors.py``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from plan_b.domain.digest import canonical_json, sha256_hex

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
    frame_hashes = [sha256_hex(canonical_json(f)) for f in frames]
    trace["integrity"] = {
        "algorithm": "sha256",
        "frame_hashes": frame_hashes,
        "chain_sha256": chain_fold(frame_hashes),
        "content_sha256": sha256_hex(canonical_json(trace)),
    }
    return trace


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
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
