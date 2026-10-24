"""verify_trace and the browser verifier accept and reject the same traces (review WEB-3).

The shared cases in web/tests/fixtures/canonical_vectors.json come from web/tests/make_vectors.py;
web/tests/integrity.test.ts runs the same cases, from the same UTF-8 bytes, through
verifyTraceBytes. The checks are also made on a trace exported from a real episode, tampered
the same ways. Byte-level input (a byte order mark, invalid UTF-8, a lone surrogate, deep
nesting) is reported as a problem, never raised.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from plan_b.cli import main
from plan_b.evaluation.export_trace import (
    MAX_INT_DIGITS,
    MAX_NESTING,
    build_trace,
    integrity,
    verify_trace,
    verify_trace_bytes,
    write_trace,
)
from tests.conftest import Sandbox

VECTORS = (
    Path(__file__).resolve().parents[1] / "web" / "tests" / "fixtures" / "canonical_vectors.json"
)
FIXTURE: dict[str, Any] = json.loads(VECTORS.read_text(encoding="utf-8"))

# The problem verify_trace reports for each check a shared case names in failing_check.
PROBLEM = {
    "algorithm": "unsupported integrity algorithm",
    "final_revision": "last frame revision differs from final state",
    "kind": "unexpected trace kind",
    "trace_version": "unsupported trace version",
    "byte_order_mark": "trace starts with a UTF-8 byte order mark",
    "lone_surrogate": "trace has a string that is not well-formed Unicode (a lone surrogate)",
    "nesting": "trace nests deeper than 256 levels",
    "frames": "frame_hashes is missing or not a list",
}

INTACT_BYTES = FIXTURE["trace_text"].encode("utf-8")


def _clone(trace: dict[str, Any]) -> dict[str, Any]:
    value: dict[str, Any] = json.loads(json.dumps(trace))
    return value


def _resealed(trace: dict[str, Any]) -> dict[str, Any]:
    """The trace with every hash recomputed, as someone editing it on purpose would do."""
    body = {k: v for k, v in trace.items() if k != "integrity"}
    return {**body, "integrity": integrity(body)}


def test_the_shared_intact_trace_verifies_and_matches_the_exporters_hashes() -> None:
    trace = json.loads(FIXTURE["trace_text"])
    assert verify_trace(trace) == []
    assert trace["integrity"] == integrity(trace)


def test_the_shared_edited_frame_fails_its_hashes_only() -> None:
    problems = verify_trace(json.loads(FIXTURE["tampered_trace_text"]))
    # verify_trace folds the recomputed frame hashes, so the chain differs too; the browser
    # folds the listed ones. Either way the trace is rejected.
    assert problems == ["frame_hashes mismatch", "chain_sha256 mismatch", "content_sha256 mismatch"]


def test_the_shared_cases_cover_every_check_the_two_verifiers_add() -> None:
    assert [c["failing_check"] for c in FIXTURE["trace_cases"]] == list(PROBLEM)


@pytest.mark.parametrize("case", FIXTURE["trace_cases"], ids=lambda c: str(c["name"]))
def test_each_shared_case_fails_only_its_named_check(case: dict[str, Any]) -> None:
    # From the file's bytes, as `plan-b verify-trace` reads it and the browser decodes it.
    assert verify_trace_bytes(case["text"].encode("utf-8")) == [PROBLEM[case["failing_check"]]]


def test_the_shared_intact_trace_verifies_from_its_bytes() -> None:
    assert verify_trace_bytes(INTACT_BYTES) == []


def test_the_deepest_shared_trace_both_verifiers_accept_is_intact() -> None:
    assert MAX_NESTING == 256
    assert verify_trace_bytes(FIXTURE["nesting_limit_trace_text"].encode("utf-8")) == []


def _t11_text() -> str:
    text: str = next(c for c in FIXTURE["trace_cases"] if c["name"] == "t11_frame_hashes_missing")[
        "text"
    ]
    return text


@pytest.mark.parametrize(
    "value",
    [None, "none", {}, 0],
    ids=["null", "string", "object", "number"],
)
def test_a_zero_frame_trace_whose_frame_hashes_is_not_a_list_is_rejected(value: Any) -> None:
    # The shared case t11 leaves frame_hashes out; the browser verifier rejects these too
    # (web/tests/integrity.test.ts). The content hash does not cover the integrity block.
    trace = json.loads(_t11_text())
    assert trace["frames"] == []
    assert verify_trace(trace) == [PROBLEM["frames"]]
    trace["integrity"]["frame_hashes"] = value
    assert verify_trace(trace) == [PROBLEM["frames"]]


def test_a_zero_frame_trace_with_the_exporters_empty_list_is_intact() -> None:
    trace = json.loads(_t11_text())
    trace["integrity"]["frame_hashes"] = []
    assert verify_trace(trace) == []
    assert trace["integrity"] == integrity(trace)


def test_a_trace_with_frames_whose_frame_hashes_is_not_a_list_is_rejected() -> None:
    trace = json.loads(FIXTURE["trace_text"])
    trace["integrity"]["frame_hashes"] = "none"
    # The chain is recomputed from the frames here; the browser folds the listed hashes and
    # also reports the chain. Either way the trace is rejected.
    assert verify_trace(trace) == [PROBLEM["frames"]]


def test_a_byte_order_mark_is_reported_not_raised() -> None:
    # json.loads would raise "Unexpected UTF-8 BOM"; a browser's response.text() would drop it.
    assert verify_trace_bytes(b"\xef\xbb\xbf" + INTACT_BYTES) == [PROBLEM["byte_order_mark"]]


@pytest.mark.parametrize(
    "bad",
    [b"caf\xff", b"caf\xc3", b"caf\xed\xa0\x80"],
    ids=["invalid-byte", "truncated-sequence", "encoded-surrogate"],
)
def test_bytes_that_are_not_utf8_are_reported_not_raised(bad: bytes) -> None:
    data = INTACT_BYTES.replace("café".encode(), bad, 1)
    assert data != INTACT_BYTES
    assert verify_trace_bytes(data) == ["trace is not valid UTF-8"]


@pytest.mark.parametrize("escape", ["\\ud800", "\\udfff", "\\ude00\\ud83d"])
def test_a_lone_surrogate_anywhere_is_reported_not_raised(escape: str) -> None:
    # In a value, and in a key; a low surrogate before a high one is two lone halves.
    trace = json.loads(FIXTURE["trace_text"])
    trace["frames"][0]["summary"] = "x"
    text = json.dumps(trace).replace('"summary": "x"', f'"summary": "{escape}"', 1)
    assert verify_trace_bytes(text.encode()) == [PROBLEM["lone_surrogate"]]
    keyed = json.dumps(trace).replace('"summary": "x"', f'"{escape}": "x"', 1)
    assert verify_trace_bytes(keyed.encode()) == [PROBLEM["lone_surrogate"]]
    # verify_trace itself reports it too, instead of a UnicodeEncodeError from hashing.
    assert verify_trace(json.loads(text)) == [PROBLEM["lone_surrogate"]]


def test_an_escaped_surrogate_pair_is_one_character_and_verifies() -> None:
    text = FIXTURE["trace_text"].replace("\U0001f600", "\\ud83d\\ude00")
    assert text != FIXTURE["trace_text"]
    assert verify_trace_bytes(text.encode()) == []


@pytest.mark.parametrize("depth", [MAX_NESTING + 1, 5_000, 100_000])
def test_deep_nesting_is_reported_not_raised(depth: int) -> None:
    # The trace object is level 1; the arrays under "pad" add depth - 1 levels.
    pad = "[" * (depth - 1) + "]" * (depth - 1)
    data = INTACT_BYTES.replace(b"{", b'{"pad": ' + pad.encode() + b", ", 1)
    assert verify_trace_bytes(data) == [PROBLEM["nesting"]]


def test_an_integer_longer_than_the_limit_is_reported_not_raised() -> None:
    longest = b'{"n": -' + b"9" * MAX_INT_DIGITS + b"}"
    assert verify_trace_bytes(longest) == ["trace has no frames array"]
    too_long = b'{"n": ' + b"9" * (MAX_INT_DIGITS + 1) + b"}"
    assert verify_trace_bytes(too_long) == [
        f"trace has an integer longer than {MAX_INT_DIGITS} digits"
    ]
    assert verify_trace({"n": 10**MAX_INT_DIGITS, "frames": []}) == [
        f"trace has an integer longer than {MAX_INT_DIGITS} digits"
    ]


@pytest.mark.parametrize(
    ("data", "problem"),
    [
        (
            b"{not json",
            "trace is not valid JSON: Expecting property name enclosed in double quotes",
        ),
        (b"[1, 2]", "trace is not a JSON object"),
        (b"", "trace is not valid JSON: Expecting value"),
    ],
)
def test_text_that_is_not_one_json_object_is_reported(data: bytes, problem: str) -> None:
    [reported] = verify_trace_bytes(data)
    assert reported.startswith(problem)


@pytest.fixture
def exported(sandbox: Sandbox) -> dict[str, Any]:
    """A trace of a real episode with several revisions."""
    sandbox.query()
    sandbox.check_in("participant_presenter", "presenter", "trace-checkin")
    sandbox.advance(5)
    trace = build_trace(sandbox.db, sandbox.episode_id, policy_id=None)
    assert len(trace["frames"]) >= 3
    return trace


def test_an_exported_trace_is_intact(exported: dict[str, Any]) -> None:
    assert verify_trace(exported) == []
    assert exported["kind"] == "plan_b_sanitized_trace"
    assert exported["integrity"]["algorithm"] == "sha256"


def test_an_algorithm_label_alone_is_rejected(exported: dict[str, Any]) -> None:
    # t4: the label sits inside the integrity block, so no hash covers it.
    trace = _clone(exported)
    trace["integrity"]["algorithm"] = "md5"
    assert verify_trace(trace) == ["unsupported integrity algorithm"]


def test_a_rehashed_final_state_past_the_last_frame_is_rejected(exported: dict[str, Any]) -> None:
    # t5: every hash matches the edited content; only the revision check can see it.
    trace = _clone(exported)
    trace["final_state"]["revision"] += 1
    assert verify_trace(_resealed(trace)) == ["last frame revision differs from final state"]


def test_a_rehashed_trace_of_another_kind_is_rejected(exported: dict[str, Any]) -> None:
    trace = _clone(exported)
    trace["kind"] = "other_trace"
    assert verify_trace(_resealed(trace)) == ["unexpected trace kind"]


def test_a_non_integer_revision_never_matches(exported: dict[str, Any]) -> None:
    trace = _clone(exported)
    trace["final_state"]["revision"] = str(trace["final_state"]["revision"])
    assert verify_trace(_resealed(trace)) == ["last frame revision differs from final state"]


def test_a_trace_without_frames_or_integrity_is_reported_not_raised(
    exported: dict[str, Any],
) -> None:
    no_frames = {k: v for k, v in exported.items() if k != "frames"}
    assert verify_trace(no_frames) == ["trace has no frames array"]
    no_integrity = {k: v for k, v in exported.items() if k != "integrity"}
    assert verify_trace(no_integrity) == ["trace has no integrity block"]


def test_the_cli_reports_each_rejection(
    exported: dict[str, Any], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    intact = write_trace(exported, tmp_path / "intact.json")
    assert main(["verify-trace", str(intact)]) == 0
    assert capsys.readouterr().out.strip() == "intact"
    trace = _clone(exported)
    trace["final_state"]["revision"] += 1
    edited = write_trace(_resealed(trace), tmp_path / "t5.json")
    assert main(["verify-trace", str(edited)]) == 1
    assert capsys.readouterr().out.strip() == "last frame revision differs from final state"


@pytest.mark.parametrize(
    ("data", "problem"),
    [
        (b"\xef\xbb\xbf" + INTACT_BYTES, "trace starts with a UTF-8 byte order mark"),
        (INTACT_BYTES.replace("café".encode(), b"caf\xff", 1), "trace is not valid UTF-8"),
        (
            next(c for c in FIXTURE["trace_cases"] if c["name"] == "t9_lone_surrogate")[
                "text"
            ].encode(),
            PROBLEM["lone_surrogate"],
        ),
    ],
    ids=["bom", "invalid-utf8", "lone-surrogate"],
)
def test_the_cli_reports_byte_level_problems_without_a_traceback(
    data: bytes, problem: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "trace.json"
    path.write_bytes(data)
    assert main(["verify-trace", str(path)]) == 1
    captured = capsys.readouterr()
    assert captured.out.strip() == problem
    assert "Traceback" not in captured.err


@pytest.mark.parametrize(
    ("data", "problem"),
    [
        (
            INTACT_BYTES.replace(b'"summary"', b'"sum\x01mary"', 1),
            "trace is not valid JSON: Invalid control character at line ",
        ),
        (
            b'{"frames": [], "x": "cut',
            "trace is not valid JSON: Unterminated string starting at line ",
        ),
    ],
    ids=["control-character", "unterminated-string"],
)
def test_the_cli_says_at_once_in_a_json_error(
    data: bytes, problem: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # json's own message ends in "at" for these; the CLI adds "at line ... column ...".
    path = tmp_path / "trace.json"
    path.write_bytes(data)
    assert main(["verify-trace", str(path)]) == 1
    out = capsys.readouterr().out.strip()
    assert out.startswith(problem), out
    assert "at at" not in out
    assert re.fullmatch(r".* at line \d+ column \d+", out), out


def test_the_cli_rejects_the_shared_zero_frame_case(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "t11.json"
    path.write_bytes(_t11_text().encode("utf-8"))
    assert main(["verify-trace", str(path)]) == 1
    assert capsys.readouterr().out.strip() == PROBLEM["frames"]


def test_the_cli_reports_a_file_it_cannot_read(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "missing.json"
    assert main(["verify-trace", str(missing)]) == 1
    assert capsys.readouterr().out.strip() == f"cannot read {missing}: No such file or directory"
