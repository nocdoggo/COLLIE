"""Tests for the capture manifest on small synthetic capture folders.

Each test writes a few fake capture files (and, where needed, a fake archive index) to a
temporary directory. Covered: which files are listed and in what order, the manifest's bytes and
hash, ``compare`` on a folder with a file missing, added or changed, on a missing or malformed
manifest and against a pinned hash, ``verify`` stopping a caller on any difference (also one
that calls it with the defaults and looks only for ``False``), the coverage counts (captures and
days per year, days with several captures, long gaps and their threshold), the archive digest,
the reasons given for indexed captures with no file, and the command line in its write and check
modes, including what it says when it replaces a manifest with other content.

Run::

    PYTHONPATH=. python -m pytest analysis/coling/test_manifest.py -q
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from analysis.coling import corpus as C
from analysis.coling import manifest as M

CSV = (
    b"Generic Name,Company Name,Presentation,Date of Update,Status\r\nA,B,C,01/02/2020,Current\r\n"
)


def put(directory: Path, files: dict[str, bytes]) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    for name, raw in files.items():
        (directory / name).write_bytes(raw)
    return directory


def index_row(stamp: str, raw: bytes) -> dict[str, str]:
    return {
        "timestamp": stamp,
        "statuscode": "200",
        "digest": M.archive_digest(raw),
        "length": str(len(raw)),
    }


def test_rows_cover_exactly_the_capture_files_in_name_order(tmp_path: Path) -> None:
    put(
        tmp_path,
        {
            "20200301000000.csv": b"second",
            "20200101120000.csv": b"first",
            "cdx.json": b"[]",
            "notes.csv": b"not a capture",
            "2020010112000.csv": b"thirteen digits",
            "20200101120000.txt": b"wrong suffix",
        },
    )
    rows = M.capture_rows(tmp_path)
    assert [r["file"] for r in rows] == ["20200101120000.csv", "20200301000000.csv"]
    assert [r["file"] for r in rows] == [p.name for p in C.capture_files(tmp_path)]
    assert rows[0] == {
        "file": "20200101120000.csv",
        "timestamp": "20200101120000",
        "bytes": "5",
        "sha256": hashlib.sha256(b"first").hexdigest(),
    }


def test_manifest_bytes_are_stable_and_the_hash_is_of_the_file(tmp_path: Path) -> None:
    caps = put(tmp_path / "caps", {"20200101120000.csv": b"a", "20200301000000.csv": b"bc"})
    rows = M.capture_rows(caps)
    path = tmp_path / "out" / "capture_manifest.csv"
    digest = M.write_manifest(rows, path)
    raw = path.read_bytes()
    assert digest == hashlib.sha256(raw).hexdigest()
    assert raw.startswith(b"file,timestamp,bytes,sha256\n20200101120000.csv,20200101120000,1,")
    assert raw.count(b"\n") == 3 and b"\r" not in raw
    assert M.write_manifest(M.capture_rows(caps), path) == digest
    assert M.read_manifest(path) == rows


def test_compare_reports_missing_added_and_changed_files(tmp_path: Path) -> None:
    files = {"20200101120000.csv": b"a", "20200201120000.csv": b"b", "20200301120000.csv": b"c"}
    caps = put(tmp_path / "caps", files)
    path = tmp_path / "capture_manifest.csv"
    M.write_manifest(M.capture_rows(caps), path)
    assert M.compare(caps, path) == []
    assert M.compare(str(caps), str(path)) == []
    (caps / "cdx.json").write_text("[]")  # the index is not part of the capture set
    assert M.compare(caps, path) == []

    (caps / "20200101120000.csv").unlink()
    (caps / "20200201120000.csv").write_bytes(b"B!")
    (caps / "20200401120000.csv").write_bytes(b"d")
    found = M.compare(caps, path)
    assert len(found) == 3
    assert found[0] == "20200101120000.csv: in the manifest, not in the folder"
    assert found[1].startswith("20200201120000.csv: content differs (manifest 1 bytes")
    assert "folder 2 bytes" in found[1]
    assert found[2] == "20200401120000.csv: in the folder, not in the manifest"


def test_compare_detects_a_change_that_keeps_the_size(tmp_path: Path) -> None:
    caps = put(tmp_path / "caps", {"20200101120000.csv": b"abc"})
    path = tmp_path / "capture_manifest.csv"
    M.write_manifest(M.capture_rows(caps), path)
    (caps / "20200101120000.csv").write_bytes(b"abd")
    assert len(M.compare(caps, path)) == 1


def test_compare_needs_a_wellformed_manifest_and_honours_the_pin(tmp_path: Path) -> None:
    caps = put(tmp_path / "caps", {"20200101120000.csv": b"a"})
    path = tmp_path / "capture_manifest.csv"
    assert M.compare(caps, path) == [f"{path}: no manifest"]
    path.write_text("name,size\nx,1\n")
    assert "not a capture manifest" in M.compare(caps, path)[0]
    path.write_bytes(b"\xff\xfe not text")
    assert M.compare(caps, path) == [f"{path}: not a capture manifest (not ASCII text)"]
    digest = M.write_manifest(M.capture_rows(caps), path)
    assert M.compare(caps, path, pin=digest[:16]) == []
    assert M.compare(caps, path, pin=digest[:16].upper()) == []
    wrong = M.compare(caps, path, pin="0" * 16)
    assert len(wrong) == 1 and "does not start with" in wrong[0]


def test_compare_rejects_a_cut_or_padded_row_and_names_a_file_listed_twice(tmp_path: Path) -> None:
    caps = put(tmp_path / "caps", {"20200101120000.csv": b"a", "20200201120000.csv": b"b"})
    path = tmp_path / "capture_manifest.csv"
    M.write_manifest(M.capture_rows(caps), path)
    good = path.read_text()
    line = good.splitlines()[2]

    path.write_text(good[: good.rindex(",")] + "\n")  # the last row lost its hash
    assert M.compare(caps, path) == [f"{path}: row 2 does not have 4 cells"]
    path.write_text(good.rstrip("\n") + ",extra\n")
    assert M.compare(caps, path) == [f"{path}: row 2 does not have 4 cells"]
    path.write_text(good + line + "\n")
    assert M.compare(caps, path) == ["20200201120000.csv: listed 2 times in the manifest"]
    path.write_text(good.replace(",1,", ",7,", 1))  # a wrong size with the right hash
    assert len(M.compare(caps, path)) == 1


def test_verify_stops_on_any_difference_and_returns_the_empty_list_otherwise(
    tmp_path: Path,
) -> None:
    files = {f"202001{day:02d}120000.csv": bytes([day]) for day in range(1, 26)}
    caps = put(tmp_path / "caps", files)
    path = tmp_path / "capture_manifest.csv"
    digest = M.write_manifest(M.capture_rows(caps), path)
    assert M.verify(caps, path) == []
    assert M.verify(caps, path, pin=digest[:16]) == []

    (caps / "20200201120000.csv").write_bytes(b"new")
    with pytest.raises(M.CaptureSetError) as one:
        M.verify(caps, path)
    assert isinstance(one.value, SystemExit)  # a command that does not catch it exits with 1
    assert one.value.differences == ["20200201120000.csv: in the folder, not in the manifest"]
    assert str(one.value).splitlines() == [
        f"{caps}: not the capture set of {path} (1 differences)",
        "  20200201120000.csv: in the folder, not in the manifest",
    ]
    assert M.verify(caps, path, refuse=False) == one.value.differences
    (caps / "20200201120000.csv").unlink()

    with pytest.raises(M.CaptureSetError, match="does not start with"):
        M.verify(caps, path, pin="0" * 16)
    with pytest.raises(M.CaptureSetError, match="no manifest"):
        M.verify(caps, tmp_path / "absent.csv")

    empty = put(tmp_path / "empty", {})  # every file is missing: the message stays short
    with pytest.raises(M.CaptureSetError) as many:
        M.verify(empty, path)
    assert len(many.value.differences) == 25
    lines = str(many.value).splitlines()
    assert len(lines) == 1 + M.MAX_SHOWN + 1 and lines[-1] == "  ... and 5 more"


def test_verify_with_the_defaults_stops_a_caller_that_looks_only_for_false(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The corpus builder calls ``verify(directory)`` and goes on unless that is ``False``."""

    def build(directory: Path) -> str:
        if M.verify(directory) is False:
            raise AssertionError("verify does not return False")
        return "built"

    monkeypatch.chdir(tmp_path)
    caps = put(tmp_path / "caps", {"20200101120000.csv": b"a"})
    with pytest.raises(SystemExit, match="no manifest"):
        build(caps)  # no manifest at the default path: nothing to build against
    M.write_manifest(M.capture_rows(caps), M.MANIFEST)
    assert (tmp_path / M.MANIFEST).is_file()
    assert build(caps) == "built"
    (caps / "20200102120000.csv").write_bytes(b"later capture")
    with pytest.raises(
        SystemExit, match=r"20200102120000\.csv: in the folder, not in the manifest"
    ):
        build(caps)


def test_coverage_counts_captures_days_years_and_gaps() -> None:
    stamps = [
        "20201030172525",
        "20191229133343",
        "20201030022459",  # same day as the first: two captures, one day
        "20201110180625",
        "20210301000000",
    ]
    cov = M.coverage(stamps)
    assert cov["captures"] == 5 and cov["capture_days"] == 4
    assert cov["first"] == "20191229133343" and cov["last"] == "20210301000000"
    assert cov["captures_per_year"] == {"2019": 1, "2020": 3, "2021": 1}
    assert cov["days_per_year"] == {"2019": 1, "2020": 2, "2021": 1}
    assert cov["days_with_several_captures"] == {"2020-10-30": 2}
    assert cov["long_gaps"] == ["2019-12-29..2020-10-30 (306 d)", "2020-11-10..2021-03-01 (111 d)"]
    # the same days and gaps as the corpus report prints
    summary = C.gap_summary([pd.Timestamp(s[:8]) for s in stamps])
    assert summary["gaps_over_60_days"] == cov["long_gaps"]
    assert summary["capture_days"] == cov["capture_days"]
    assert {str(k): v for k, v in summary["per_year"].items()} == cov["days_per_year"]
    assert M.coverage([])["captures"] == 0 and M.coverage([])["first"] == ""


def test_a_gap_is_long_only_above_sixty_days() -> None:
    # 2020-01-01 to 2020-03-01 is 60 days (not listed); to 2020-03-02 is 61
    assert M.long_gaps(["20200101000000", "20200301000000"]) == []
    stamps = ["20200101000000", "20200302000000"]
    assert M.long_gaps(stamps) == ["2020-01-01..2020-03-02 (61 d)"]
    for pair in (["20200101000000", "20200301000000"], stamps):
        summary = C.gap_summary([pd.Timestamp(s[:8]) for s in pair])
        assert summary["gaps_over_60_days"] == M.long_gaps(pair)


def test_archive_digest_is_base32_sha1() -> None:
    assert M.archive_digest(b"") == "3I42H3S6NNFQ2MSVX7XZKYAYSCX5QBYJ"


def test_indexed_captures_without_a_file_get_a_reason() -> None:
    index = [
        index_row("20200101000000", b"one"),
        index_row("20200101060000", b"one"),  # repeat, same day
        index_row("20200102000000", b"one"),  # repeat, next day, day not covered
        index_row("20200105000000", b"two"),
        index_row("20200107000000", b"one"),  # back to the first content after another
        index_row("20200108000000", b"three"),  # never fetched, inside the span
        index_row("20200109000000", b"three"),  # its repeat: nothing on disk to stand for it
        index_row("20200110000000", b"four"),
        index_row("20200110090000", b"two"),  # earlier content again; the day is covered
        index_row("20200120000000", b"five"),  # indexed after the last file
    ]
    on_disk = ["20200101000000", "20200105000000", "20200110000000"]
    unused = M.unused_index_rows(index, on_disk)
    got = {u.timestamp: u for u in unused}
    assert [u.timestamp for u in unused] == sorted(got)
    assert set(got) == {r["timestamp"] for r in index} - set(on_disk)
    assert got["20200101060000"].kind == "repeat"
    assert "20200101000000, the same day" in got["20200101060000"].reason
    assert "no capture is used" not in got["20200101060000"].reason
    assert got["20200102000000"].kind == "repeat"
    assert "1 day later" in got["20200102000000"].reason
    assert "no capture is used for 2020-01-02" in got["20200102000000"].reason
    assert got["20200107000000"].kind == "return"
    assert "6 days later, after different content" in got["20200107000000"].reason
    assert got["20200107000000"].reason.endswith("should be fetched")
    assert got["20200108000000"].kind == "not_fetched"
    assert "inside the covered span" in got["20200108000000"].reason
    assert got["20200109000000"].kind == "not_fetched"
    assert "20200108000000, which has no file" in got["20200109000000"].reason
    assert got["20200110090000"].kind == "return"
    assert "no capture is used" not in got["20200110090000"].reason
    assert got["20200120000000"].kind == "not_fetched"
    assert "later than the last file" in got["20200120000000"].reason
    assert M.unused_index_rows(index[:1], on_disk) == []


def test_a_capture_is_judged_against_the_nearest_earlier_file_with_its_content() -> None:
    index = [
        index_row("20200101000000", b"one"),
        index_row("20200105000000", b"two"),
        index_row("20200107000000", b"one"),  # the return, fetched as the report asks
        index_row("20200108000000", b"one"),  # repeats the fetched return, not the first capture
        index_row("20200109000000", b"one"),  # still the same run
        index_row("20200112000000", b"three"),
        index_row("20200120000000", b"one"),  # back again: the nearest file is the one of 7 Jan
    ]
    on_disk = ["20200101000000", "20200105000000", "20200107000000", "20200112000000"]
    got = {u.timestamp: u for u in M.unused_index_rows(index, on_disk)}
    assert set(got) == {"20200108000000", "20200109000000", "20200120000000"}
    assert got["20200108000000"].kind == "repeat"
    assert "same content as 20200107000000, 1 day later, nothing different" in (
        got["20200108000000"].reason
    )
    assert got["20200109000000"].kind == "repeat"
    assert "same content as 20200107000000, 2 days later" in got["20200109000000"].reason
    assert got["20200120000000"].kind == "return"
    assert "same content as 20200107000000, 13 days later, after different content" in (
        got["20200120000000"].reason
    )


def test_index_check_compares_files_with_the_archive_digest(tmp_path: Path) -> None:
    put(
        tmp_path,
        {"20200101000000.csv": b"one", "20200105000000.csv": b"two", "20200109000000.csv": b"x"},
    )
    index = [index_row("20200105000000", b"other"), index_row("20200101000000", b"one")]
    (tmp_path / "cdx.json").write_text(json.dumps(index))
    assert [r["timestamp"] for r in M.read_index(tmp_path)] == ["20200101000000", "20200105000000"]
    assert M.index_check(tmp_path, M.read_index(tmp_path)) == {
        "not_in_index": ["20200109000000.csv"],
        "digest_equal": ["20200101000000.csv"],
        "digest_differs": ["20200105000000.csv"],
    }
    assert M.read_index(tmp_path / "nowhere") == []
    for bad in ("{", '{"timestamp": "20200101000000"}', '[{"timestamp": "20200101000000"}]'):
        (tmp_path / "cdx.json").write_text(bad)
        with pytest.raises(ValueError):
            M.read_index(tmp_path)


def test_files_the_parser_rejects_are_named(tmp_path: Path) -> None:
    put(tmp_path, {"20200101000000.csv": CSV, "20200201000000.csv": b"<html>not a csv</html>"})
    rejected = M.rejected_by_parser(tmp_path)
    assert len(rejected) == 1 and rejected[0].startswith("20200201000000.csv")
    assert len(M.capture_rows(tmp_path)) == 2  # listed all the same: the manifest is of files


def test_command_line_writes_reports_and_checks(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    files = {"20200101000000.csv": CSV, "20200215000000.csv": CSV + b"D,E,F,02/03/2020,Current\r\n"}
    caps = put(tmp_path / "caps", files)
    index = [index_row(name[:14], raw) for name, raw in files.items()]
    index.append(index_row("20200216000000", files["20200215000000.csv"]))
    (caps / "cdx.json").write_text(json.dumps(index))
    out = tmp_path / "out" / "capture_manifest.csv"
    args = ["--captures", str(caps), "--out", str(out)]

    assert M.main(args) == 0
    first = capsys.readouterr().out
    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    assert f"sha256 {digest} (short {digest[:16]})" in first
    assert "captures: 2 files on 2 days (UTC)" in first
    assert "first capture: 20200101000000 (2020-01-01 00:00:00 UTC)" in first
    assert "last capture: 20200215000000 (2020-02-15 00:00:00 UTC)" in first
    assert "captures per year: 2020: 2" in first
    assert "files the parser rejects (skipped by the corpus): 0" in first
    assert "3 captures on 3 days" in first
    assert (
        "files with the archive's digest: 2; with another digest: 0; not in the index: 0" in first
    )
    assert "indexed captures with no file: 1 (repeat: 1)" in first
    assert "20200216000000  repeat: same content as 20200215000000, 1 day later" in first

    assert M.main(args) == 0  # same folder, same output, same bytes
    assert capsys.readouterr().out == first
    assert hashlib.sha256(out.read_bytes()).hexdigest() == digest

    assert "REPLACED" not in first

    assert M.main([*args, "--check"]) == 0
    assert "as in the manifest" in capsys.readouterr().out
    assert M.main([*args, "--check", "--pin", digest[:16]]) == 0
    assert M.main([*args, "--check", "--pin", "0" * 16]) == 1
    assert "does not start with" in capsys.readouterr().out
    (caps / "20200216000000.csv").write_bytes(CSV)
    assert M.main([*args, "--check"]) == 1
    report = capsys.readouterr().out
    assert "20200216000000.csv: in the folder, not in the manifest" in report
    assert "1 differences" in report
    assert hashlib.sha256(out.read_bytes()).hexdigest() == digest  # check mode writes nothing

    with pytest.raises(SystemExit):
        M.main(["--captures", str(tmp_path / "empty"), "--out", str(out)])
    with pytest.raises(SystemExit):
        M.main([*args, "--pin", digest[:16]])  # a pin is for --check only
    assert hashlib.sha256(out.read_bytes()).hexdigest() == digest
    capsys.readouterr()

    # writing over a manifest of another capture set says so and names the difference
    (caps / "cdx.json").write_text("{")
    assert M.main(args) == 0
    again = capsys.readouterr().out
    assert hashlib.sha256(out.read_bytes()).hexdigest() != digest
    assert f"REPLACED a manifest with other content (sha256 {digest[:16]})" in again
    assert "  20200216000000.csv: in the folder, not in the manifest" in again
    assert "captures: 3 files on 3 days (UTC)" in again
    assert "index: unreadable" in again
    assert M.main([*args, "--check"]) == 0


def test_changes_to_is_silent_only_for_the_same_bytes(tmp_path: Path) -> None:
    caps = put(tmp_path / "caps", {"20200101120000.csv": b"a"})
    rows = M.capture_rows(caps)
    path = tmp_path / "capture_manifest.csv"
    assert M.changes_to(path, rows) == []  # nothing there yet
    M.write_manifest(rows, path)
    assert M.changes_to(path, rows) == []
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    assert "written differently" in M.changes_to(path, rows)[0]
    path.write_text("name,size\nx,1\n")
    assert "not a capture manifest" in M.changes_to(path, rows)[0]
