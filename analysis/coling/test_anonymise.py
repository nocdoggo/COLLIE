"""Tests for the anonymised copies (``anonymise.py``) on small made-up documents.

Every test but the last three works in a temporary folder, on a plan and a guide of a few lines
and a list written here; the names in them are made up. The last three read the study's own
files: the two registered documents, the list, the committed copies and the script.

Covered: the copies (every listed string replaced, by the token of its line, and nothing else:
other bytes, line ends and a missing final newline stay); the longest string first; a place
taken by a longer string closed to a shorter one that overlaps it; a token never read as text;
``HASHES.txt`` (the six hashes and the places by token and file); the same bytes on a second
build and in another folder; each refusal, with one sentence, status 2 and nothing written (a
token already in a registered file, a string in neither file or only inside a longer one, a
string listed twice, an empty string, a blank line, a line of another shape, a token of another
shape, a list that is not sorted, a string that is part of a token, a missing file, a file that
is not UTF-8, two files of one name, an output folder that holds a source), and that a refusal
prints no string and leaves an earlier build alone; ``check`` on a fresh build, on a changed copy, on a missing file, on a changed
list and on a list it refuses; ``scan`` on clean copies, on a planted e-mail address, URL,
path with an account name and commit id of 40 and of 7 characters, on hex strings that are no
commit id, on a listed string in another letter case, without the list and without the copies;
the script run as a file outside the package; and, on the study's files, that the committed
copies are those of a build, that the scan finds nothing in them, that the script imports the
standard library only, and that neither the script nor this file holds a string of the list.

Run::

    PYTHONPATH=. python -m pytest analysis/coling/test_anonymise.py -q -p no:cacheprovider
"""

from __future__ import annotations

import ast
import hashlib
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from analysis.coling import anonymise as A

STUDY = Path(__file__).resolve().parent / "plan"

PLAN = """\
# A plan

The collectors carry the agent `kennel-fetch/0.1 (research)`. The code is in `kennel/` and in
`kennel/lib/run.py`; the earlier paper is the Barks 2031 paper (Barks for short).
The draft is this file at commit `0a1b2c3`. The table has the hash `0123456789abcdef`.
"""
GUIDE = """\
# A guide

The guide follows the plan of the kennel study. Nothing of Barks is used.
"""
PAIRS = {
    "0a1b2c3": "[COMMIT]",
    "Barks": "[OTHER-PAPER]",
    "Barks 2031": "[OTHER-PAPER]",
    "kennel": "[REPOSITORY]",
    "kennel-fetch/0.1 (research)": "[AGENT-STRING]",
    "kennel/lib/run.py": "[PATH]",
}
PLAN_COPY = """\
# A plan

The collectors carry the agent `[AGENT-STRING]`. The code is in `[REPOSITORY]/` and in
`[PATH]`; the earlier paper is the [OTHER-PAPER] paper ([OTHER-PAPER] for short).
The draft is this file at commit `[COMMIT]`. The table has the hash `0123456789abcdef`.
"""
GUIDE_COPY = """\
# A guide

The guide follows the plan of the [REPOSITORY] study. Nothing of [OTHER-PAPER] is used.
"""


@dataclass(frozen=True)
class Study:
    """A made-up study in a temporary folder, and the options that point the script at it."""

    plan: Path
    guide: Path
    strings: Path
    out: Path

    @property
    def args(self) -> list[str]:
        named = {"--plan": self.plan, "--guide": self.guide, "--list": self.strings}
        return [word for key, path in named.items() for word in (key, str(path))] + [
            "--out",
            str(self.out),
        ]


def list_text(pairs: dict[str, str]) -> str:
    return "".join(f"{string}\t{pairs[string]}\n" for string in sorted(pairs))


def study(
    root: Path,
    plan: str | bytes = PLAN,
    guide: str | bytes = GUIDE,
    pairs: dict[str, str] | str = PAIRS,
) -> Study:
    """Write a plan, a guide and a list (a mapping, or the text of the file as it is)."""
    made = Study(root / "PLAN.md", root / "GUIDE.md", root / "strings.tsv", root / "out")
    root.mkdir(parents=True, exist_ok=True)
    for path, content in ((made.plan, plan), (made.guide, guide)):
        path.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))
    text = pairs if isinstance(pairs, str) else list_text(pairs)
    made.strings.write_bytes(text.encode("utf-8"))
    return made


def built(root: Path, **changes: Any) -> Study:
    made = study(root, **changes)
    assert A.main(["build", *made.args]) == 0
    return made


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --------------------------------------------------------------------------------------------
# The copies
# --------------------------------------------------------------------------------------------


def test_build_replaces_every_listed_string_by_its_token(tmp_path: Path) -> None:
    made = built(tmp_path)
    assert (made.out / "PLAN.md").read_text(encoding="utf-8") == PLAN_COPY
    assert (made.out / "GUIDE.md").read_text(encoding="utf-8") == GUIDE_COPY
    assert sorted(path.name for path in made.out.iterdir()) == ["GUIDE.md", "HASHES.txt", "PLAN.md"]


def test_nothing_else_changes(tmp_path: Path) -> None:
    plan = "τ −12 “quoted”\r\n\tkennel\x0bkept\r\nno final newline: Barks".encode()
    made = built(tmp_path, plan=plan, pairs={"kennel": "[REPOSITORY]", "Barks": "[OTHER-PAPER]"})
    expected = "τ −12 “quoted”\r\n\t[REPOSITORY]\x0bkept\r\nno final newline: [OTHER-PAPER]"
    assert (made.out / "PLAN.md").read_bytes() == expected.encode()


def test_a_file_with_no_listed_string_is_copied_as_it_is(tmp_path: Path) -> None:
    made = built(tmp_path, guide="# A guide\n\nNothing to replace.\n")
    assert (made.out / "GUIDE.md").read_bytes() == made.guide.read_bytes()


def test_the_list_may_end_without_a_newline(tmp_path: Path) -> None:
    made = built(tmp_path, pairs=list_text(PAIRS).rstrip("\n"))
    assert (made.out / "PLAN.md").read_text(encoding="utf-8") == PLAN_COPY


def test_longest_string_first() -> None:
    text = "kennel-fetch/0.1 (research) and kennel/lib/run.py and kennel"
    copy, counts = A.replace(text, PAIRS)
    assert copy == "[AGENT-STRING] and [PATH] and [REPOSITORY]"
    assert counts == {"kennel-fetch/0.1 (research)": 1, "kennel/lib/run.py": 1, "kennel": 1}


def test_a_place_taken_by_a_longer_string_is_closed_to_a_shorter_one() -> None:
    # "abc" comes first in the text, but "bcde" is longer and takes its place first.
    copy, counts = A.replace("abcde abc", {"bcde": "[LONG]", "abc": "[SHORT]"})
    assert copy == "a[LONG] [SHORT]"
    assert counts == {"bcde": 1, "abc": 1}


def test_a_token_is_never_read_as_text() -> None:
    # Replaced one string after the other, "]b" would be found where the first token ends.
    copy, _ = A.replace("alpha!b and ]b", {"alpha!": "[X]", "]b": "[Y]"})
    assert copy == "[X]b and [Y]"


def test_a_string_is_replaced_at_every_place_and_in_its_own_letter_case_only() -> None:
    copy, counts = A.replace("Barks, barks, BARKS, Barks.", {"Barks": "[OTHER-PAPER]"})
    assert copy == "[OTHER-PAPER], barks, BARKS, [OTHER-PAPER]."
    assert counts == {"Barks": 2}


# --------------------------------------------------------------------------------------------
# HASHES.txt, and the same bytes again
# --------------------------------------------------------------------------------------------


def test_hashes_file(tmp_path: Path) -> None:
    made = built(tmp_path)
    lines = (made.out / "HASHES.txt").read_text(encoding="utf-8").splitlines()
    assert lines == [
        "sha256",
        f"{sha(made.plan)}  registered  PLAN.md",
        f"{sha(made.guide)}  registered  GUIDE.md",
        f"{sha(made.out / 'PLAN.md')}  anonymised  PLAN.md",
        f"{sha(made.out / 'GUIDE.md')}  anonymised  GUIDE.md",
        f"{sha(Path(A.__file__))}  script      anonymise.py",
        f"{sha(made.strings)}  list        strings.tsv",
        "",
        "places replaced",
        "[AGENT-STRING]  PLAN.md 1  GUIDE.md 0",
        "[COMMIT]  PLAN.md 1  GUIDE.md 0",
        "[OTHER-PAPER]  PLAN.md 2  GUIDE.md 1",
        "[PATH]  PLAN.md 1  GUIDE.md 0",
        "[REPOSITORY]  PLAN.md 1  GUIDE.md 1",
    ]


def test_two_builds_write_the_same_bytes(tmp_path: Path) -> None:
    made = built(tmp_path / "one")
    first = {path.name: path.read_bytes() for path in made.out.iterdir()}
    assert A.main(["build", *made.args]) == 0
    assert {path.name: path.read_bytes() for path in made.out.iterdir()} == first
    other = built(tmp_path / "two" / "elsewhere")
    assert {path.name: path.read_bytes() for path in other.out.iterdir()} == first


def test_no_output_names_a_folder(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    made = built(tmp_path)
    assert A.main(["check", *made.args]) == 0
    assert A.main(["scan", *made.args]) == 0
    printed = capsys.readouterr()
    written = b"".join(path.read_bytes() for path in made.out.iterdir()).decode("utf-8")
    for text in (printed.out, printed.err, written):
        assert str(tmp_path) not in text and tmp_path.name not in text


# --------------------------------------------------------------------------------------------
# Refusals
# --------------------------------------------------------------------------------------------

UNSORTED = "kennel\t[REPOSITORY]\nBarks\t[OTHER-PAPER]\n"
INSIDE = {"kennel": "[REPOSITORY]", "kennel/lib/run.py": "[PATH]"}
REFUSALS: dict[str, tuple[dict[str, Any], str]] = {
    "a token already in a registered file": (
        {"plan": PLAN + "A [PATH] of its own.\n"},
        "the token [PATH] already occurs in the registered PLAN.md.",
    ),
    "a token already in the other file": (
        {"guide": GUIDE + "See [COMMIT].\n"},
        "the token [COMMIT] already occurs in the registered GUIDE.md.",
    ),
    "a string in neither file": (
        {"pairs": {**PAIRS, "absent": "[PATH]"}},
        "line 4 of the list: the string replaces nothing in either file",
    ),
    "a string only inside a longer one": (
        {"plan": "In `kennel/lib/run.py`.\n", "guide": "Nothing.\n", "pairs": INSIDE},
        "line 1 of the list: the string replaces nothing in either file",
    ),
    "a string listed twice": (
        {"pairs": "Barks\t[OTHER-PAPER]\nBarks\t[OTHER-PAPER]\n"},
        "line 2 of the list has a string that is listed before.",
    ),
    "a string listed twice with two tokens": (
        {"pairs": "Barks\t[OTHER-PAPER]\nBarks\t[PATH]\n"},
        "line 2 of the list has a string that is listed before.",
    ),
    "an empty string": (
        {"pairs": "\t[PATH]\nkennel\t[REPOSITORY]\n"},
        "line 1 of the list has an empty string.",
    ),
    "a blank line": (
        {"pairs": "Barks\t[OTHER-PAPER]\n\nkennel\t[REPOSITORY]\n"},
        "line 2 of the list is not string<TAB>token.",
    ),
    "no tab": (
        {"pairs": "kennel [REPOSITORY]\n"},
        "line 1 of the list is not string<TAB>token.",
    ),
    "two tabs": (
        {"pairs": "kennel\t[REPOSITORY]\tnote\n"},
        "line 1 of the list is not string<TAB>token.",
    ),
    "a token without brackets": (
        {"pairs": "kennel\tREPOSITORY\n"},
        "line 1 of the list: the token is not a word in capitals between square brackets.",
    ),
    "a token in small letters": (
        {"pairs": "kennel\t[repository]\n"},
        "line 1 of the list: the token is not a word in capitals between square brackets.",
    ),
    "a list that is not sorted": (
        {"pairs": UNSORTED},
        "the list is not sorted by string at line 2.",
    ),
    "a string that is part of a token": (
        {"pairs": {**PAIRS, "PATH": "[OTHER-PAPER]"}},
        "line 4 of the list: the string is part of the token [PATH].",
    ),
    "a string that is part of a token in other letters": (
        {"pairs": {**PAIRS, "Paper": "[PATH]"}},
        "line 4 of the list: the string is part of the token [OTHER-PAPER].",
    ),
    "a file that is not UTF-8": ({"guide": b"\xff\xfe kennel"}, "GUIDE.md is not UTF-8."),
}


@pytest.mark.parametrize("case", REFUSALS)
def test_refusal(case: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    changes, sentence = REFUSALS[case]
    made = study(tmp_path, **changes)
    for command in ("build", "check"):
        assert A.main([command, *made.args]) == A.REFUSED
        printed = capsys.readouterr()
        assert printed.out == ""
        assert printed.err.startswith(f"refused: {sentence}")
        assert printed.err.count("\n") == 1 and printed.err.endswith(".\n")
        assert not made.out.exists()


@pytest.mark.parametrize("missing", ["plan", "guide", "strings"])
def test_refusal_when_a_file_is_missing(
    missing: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    made = study(tmp_path)
    gone: Path = getattr(made, missing)
    gone.unlink()
    assert A.main(["build", *made.args]) == A.REFUSED
    assert (
        capsys.readouterr().err
        == f"refused: there is no file {gone.name} where it was looked for.\n"
    )
    assert not made.out.exists()


def test_refusal_when_the_two_files_have_one_name(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    made = study(tmp_path)
    (tmp_path / "other").mkdir()
    twin = tmp_path / "other" / made.plan.name
    twin.write_bytes(made.guide.read_bytes())
    args = ["--plan", str(made.plan), "--guide", str(twin), "--list", str(made.strings)]
    assert A.main(["build", *args, "--out", str(made.out)]) == A.REFUSED
    assert capsys.readouterr().err == "refused: the two registered files have one name, PLAN.md.\n"
    assert not made.out.exists()


def test_refusal_when_the_copies_would_be_written_over_their_sources(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    made = study(tmp_path)
    before = made.plan.read_bytes()
    args = ["--plan", str(made.plan), "--guide", str(made.guide), "--list", str(made.strings)]
    assert A.main(["build", *args, "--out", str(tmp_path / "out" / "..")]) == A.REFUSED
    assert capsys.readouterr().err == "refused: the output folder is the folder of PLAN.md.\n"
    assert made.plan.read_bytes() == before and not made.out.exists()


def test_refusal_prints_no_string_of_the_list(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pairs = {**PAIRS, "a-name-not-to-print": "[PATH]"}
    assert A.main(["build", *study(tmp_path, pairs=pairs).args]) == A.REFUSED
    assert "a-name-not-to-print" not in capsys.readouterr().err
    swapped = "[REPOSITORY]\tkennel-club\n"
    assert A.main(["build", *study(tmp_path, pairs=swapped).args]) == A.REFUSED
    assert "kennel" not in capsys.readouterr().err


def test_refusal_leaves_an_earlier_build_alone(tmp_path: Path) -> None:
    made = built(tmp_path)
    before = {path.name: path.read_bytes() for path in made.out.iterdir()}
    made.strings.write_bytes(list_text({**PAIRS, "absent": "[PATH]"}).encode("utf-8"))
    assert A.main(["build", *made.args]) == A.REFUSED
    assert {path.name: path.read_bytes() for path in made.out.iterdir()} == before


# --------------------------------------------------------------------------------------------
# check
# --------------------------------------------------------------------------------------------


def test_check_passes_on_a_fresh_build(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    made = built(tmp_path)
    capsys.readouterr()
    assert A.main(["check", *made.args]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "identical  PLAN.md",
        "identical  GUIDE.md",
        "identical  HASHES.txt",
        "up to date: the copies and the hashes are those of a build",
    ]


def test_check_fails_on_a_changed_copy(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    made = built(tmp_path)
    copy = made.out / "GUIDE.md"
    copy.write_bytes(copy.read_bytes().replace(b"Nothing", b"nothing"))
    capsys.readouterr()
    assert A.main(["check", *made.args]) == A.FOUND
    out = capsys.readouterr().out
    assert "differs    GUIDE.md" in out and "identical  PLAN.md" in out
    assert "out of date: 1 of 3 files are not those of a build" in out


def test_check_fails_on_a_missing_file_and_on_no_build(tmp_path: Path) -> None:
    made = built(tmp_path)
    (made.out / "HASHES.txt").unlink()
    assert A.main(["check", *made.args]) == A.FOUND
    assert A.main(["check", *study(tmp_path / "unbuilt").args]) == A.FOUND


def test_check_fails_when_the_list_or_a_registered_file_changed(tmp_path: Path) -> None:
    made = built(tmp_path)
    made.strings.write_bytes(list_text({**PAIRS, "earlier": "[OTHER-PAPER]"}).encode("utf-8"))
    assert A.main(["check", *made.args]) == A.FOUND
    assert A.main(["build", *made.args]) == 0
    assert A.main(["check", *made.args]) == 0
    made.guide.write_bytes(made.guide.read_bytes() + b"One more line.\n")
    assert A.main(["check", *made.args]) == A.FOUND


def test_check_writes_nothing(tmp_path: Path) -> None:
    made = built(tmp_path)
    copy = made.out / "PLAN.md"
    copy.write_bytes(b"changed")
    assert A.main(["check", *made.args]) == A.FOUND
    assert copy.read_bytes() == b"changed"


# --------------------------------------------------------------------------------------------
# scan
# --------------------------------------------------------------------------------------------

COMMIT_40 = "0123456789abcdef0123456789abcdef01234567"
PLANTED = {
    "e-mail address": ("write to someone@example.org.", "someone@example.org"),
    "URL": ("see <https://example.org/some/page>", "https://example.org/some/page"),
    "host of a code or profile site": (
        "at github.com/someone/project.",
        "github.com/someone/project.",
    ),
    "path with an account name": ("in `/home/someone/work/notes.md`", "/home/someone"),
    "commit id": (f"at commit {COMMIT_40}.", COMMIT_40),
    "affiliation or funding": ("the Department of Barking, funded by a prize", "Department of"),
    "local time zone": ("pushed at 09:00 JST", "JST"),
}


def planted(made: Study, text: str, name: str = "PLAN.md") -> None:
    copy = made.out / name
    copy.write_bytes(copy.read_bytes() + f"\n{text}\n".encode())


def test_scan_finds_nothing_in_clean_copies(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    made = built(tmp_path)
    capsys.readouterr()
    assert A.main(["scan", *made.args]) == 0
    assert capsys.readouterr().out == "nothing found in 2 copies\n"


@pytest.mark.parametrize("kind", PLANTED)
def test_scan_finds_a_planted_string(
    kind: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    text, value = PLANTED[kind]
    made = built(tmp_path)
    planted(made, text, "GUIDE.md")
    capsys.readouterr()
    assert A.main(["scan", *made.args]) == A.FOUND
    assert f"GUIDE.md:5: {kind}: {value}\n" in capsys.readouterr().out


def test_scan_finds_other_paths_and_short_commit_ids(tmp_path: Path) -> None:
    lines = A.scan("X.md", "/Users/someone/x\nC:\\Users\\someone\\x\ncommit `1f2e3d4`\n")
    assert lines == [
        "X.md:1: path with an account name: /Users/someone",
        "X.md:2: path with an account name: C:\\Users\\someone",
        "X.md:3: commit id: 1f2e3d4",
    ]


@pytest.mark.parametrize(
    "text",
    [
        "the hash `0123456789abcdef` of a table",
        "the pin `" + "0a" * 32 + "`",
        "the capture `20201030175604` and the seed 20261001",
        "the event `E67ea1febd54f` and the word defaced",
        "the route `meta/llama-3.3-70b`, at www.example.gov/list, costs $0.00013",
    ],
)
def test_scan_leaves_what_is_no_identifying_string(text: str) -> None:
    assert A.scan("X.md", text) == []


def test_scan_finds_a_listed_string_in_another_letter_case(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pairs = {**PAIRS, "Bx": "[OTHER-PAPER]"}
    made = built(tmp_path, plan=PLAN + "Bx is short.\n", pairs=pairs)
    planted(made, "The KENNEL folder, and bx in small letters.")
    capsys.readouterr()
    assert A.main(["scan", *made.args]) == A.FOUND
    assert capsys.readouterr().out == "PLAN.md:8: string of the list: KENNEL\n"
    planted(made, "Bx as it is listed.")
    assert A.main(["scan", *made.args]) == A.FOUND
    assert "PLAN.md:10: string of the list: Bx\n" in capsys.readouterr().out


def test_scan_runs_on_the_copies_alone(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    made = built(tmp_path)
    for path in (made.plan, made.guide, made.strings):
        path.unlink()
    capsys.readouterr()
    assert A.main(["scan", *made.args]) == 0
    assert capsys.readouterr().out == (
        "nothing found in 2 copies\nthe list is not at hand: its strings were not looked for\n"
    )
    planted(made, "The KENNEL folder; write to someone@example.org.")
    assert A.main(["scan", *made.args]) == A.FOUND
    assert (
        capsys.readouterr().out.splitlines()[0] == "PLAN.md:7: e-mail address: someone@example.org"
    )


def test_scan_refuses_without_the_copies(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert A.main(["scan", *study(tmp_path).args]) == A.REFUSED
    assert capsys.readouterr().err == "refused: there is no file PLAN.md where it was looked for.\n"


# --------------------------------------------------------------------------------------------
# The script on its own, and the study's files
# --------------------------------------------------------------------------------------------


def test_the_script_runs_as_a_file_outside_the_package(tmp_path: Path) -> None:
    made = built(tmp_path / "study")
    command = [sys.executable, "-I", A.__file__, "check", *made.args]
    done = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True, check=False)
    assert (done.returncode, done.stderr) == (0, "")
    assert done.stdout.splitlines()[-1].startswith("up to date")


def test_the_script_imports_the_standard_library_only() -> None:
    tree = ast.parse(Path(A.__file__).read_text(encoding="utf-8"))
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            roots.add((node.module or "").split(".")[0])
    assert roots <= set(sys.stdlib_module_names)


def study_args() -> list[str]:
    files = {"--plan": "PLAN.md", "--guide": "AUDIT_GUIDE.md", "--list": "ANON_STRINGS.tsv"}
    args = [word for key, name in files.items() for word in (key, str(STUDY / name))]
    return [*args, "--out", str(STUDY / "anonymised")]


def test_the_committed_copies_are_those_of_a_build_and_the_scan_is_clean(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert A.main(["check", *study_args()]) == 0, capsys.readouterr().out
    assert A.main(["scan", *study_args()]) == 0, capsys.readouterr().out
    assert capsys.readouterr().out.endswith("nothing found in 2 copies\n")


def test_neither_the_script_nor_this_file_holds_a_string_of_the_list() -> None:
    strings = list(A.read_list((STUDY / "ANON_STRINGS.tsv").read_text(encoding="utf-8")))
    listed = A.finders(strings)[len(A.SCAN) :]
    for path in (Path(A.__file__), Path(__file__)):
        text = path.read_text(encoding="utf-8")
        assert not [match.group(0) for _, finder in listed for match in finder(text)], path.name
