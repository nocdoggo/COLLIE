"""Anonymised copies of the registered plan and guide, for a double-blind submission.

PLAN.md section 14 ("Anonymity and the evidence of registration") promises this script. It makes
a copy of each registered file (``plan/PLAN.md`` and ``plan/AUDIT_GUIDE.md``) in which every
string of a list (``plan/ANON_STRINGS.tsv``) is replaced by a fixed token, and it changes
nothing else. The two copies and a file of hashes go to ``plan/anonymised/``. With the
registered files, this script and the list, the copies can be built again byte for byte; with
the copies alone, they can be compared with the hashes written beside them.

The list. One line per string, ``string<TAB>token``, in UTF-8, sorted by string, each string
once. A string is taken literally: it is no pattern, its letter case counts, and it cannot run
over two lines. A token is a short word in capitals between square brackets (``[PATH]``,
``[COMMIT]``); strings of the same kind share a token.

Replacement. The strings are looked for in the registered text, the longest first, and a place
that a longer string has taken is closed to a shorter one: a string inside a longer string of
the list is replaced once, with the longer one. The tokens are written when every place is
known, so a token is never read as text. Outside the places, the copy has the bytes of the
registered file.

Refusals. Each one stops the script with one sentence and status 2, before anything is written:

- a line of the list that is not ``string<TAB>token``, an empty string, a string listed twice,
  a token of another shape, or a list that is not sorted;
- a string that is part of a token of the list, in any letter case: the token would put the
  string back into the copy;
- a token that already occurs in a registered file: in the copy it could not be told from a
  place;
- a string that replaces nothing in either file, because it occurs in neither or only inside a
  longer string of the list;
- a file that is missing or is not UTF-8, two registered files of one name, and an output
  folder that holds a registered file or the list (a copy would be written over its source).

A refusal names a line of the list, a token or a file, and never a string of the list.

``HASHES.txt``. The sha256 of the two registered files, of the two copies, of this script and
of the list; then one line per token with the number of places it replaces in each file. The
file holds names and no folder, and no date, so a second build writes the same bytes anywhere.

Commands.

- ``build`` writes the two copies and ``HASHES.txt``.
- ``check`` builds in memory and compares with the three files on disk. Its status is 0 only
  when all three are identical.
- ``scan`` reads the two copies on disk and prints, with file and line, whatever still looks
  like an identifying string. Its status is 1 when it prints anything. It looks for an e-mail
  address; a URL with a scheme, and the host of a site for code or profiles written without
  one; a path with an account name (``/home/<name>``, ``/Users/<name>``); a commit id (7 to
  40 hex characters, with a letter and a digit); the words of an affiliation or of funding; a
  local time zone; and, when the list is at hand, every string of the list, also in other
  letter cases when it has five characters or more. Hex strings of 16 characters are left
  alone: that is the length at which the plan writes its sha256 prefixes, so a commit id cut
  to that length is not found, and neither is one made of digits only. A bare host of a data
  source (``www.`` and no scheme) is not reported. The scan is a net and does not replace a
  reading of the copies: a name that is in no list and has none of these shapes passes it.

Only the standard library is used, so that the script runs on its own. It reads the files
named on its command line (the defaults are below) and its own file, and makes no request.

Usage (from the repository root)::

    PYTHONPATH=. python -m analysis.coling.anonymise build
    PYTHONPATH=. python -m analysis.coling.anonymise check    # exit status 1 when out of date
    PYTHONPATH=. python -m analysis.coling.anonymise scan     # exit status 1 when it finds any
    python anonymise.py scan --out FOLDER                     # with the copies alone
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from itertools import pairwise
from pathlib import Path

PLAN_DIR = Path("analysis/coling/plan")
PLAN = PLAN_DIR / "PLAN.md"
GUIDE = PLAN_DIR / "AUDIT_GUIDE.md"
LIST = PLAN_DIR / "ANON_STRINGS.tsv"
OUT = PLAN_DIR / "anonymised"
HASHES = "HASHES.txt"

FOUND = 1
"""Exit status of ``check`` when a file differs, and of ``scan`` when it prints anything."""
REFUSED = 2
SHA256_PREFIX = 16
"""The length at which the plan writes a sha256: the scan takes no such string for a commit id."""
VARIANT_FROM = 5
"""A listed string of this length or more is looked for in every letter case by the scan."""

_TOKEN = re.compile(r"\[[A-Z][A-Z0-9-]*\]")
_HEX = re.compile(r"(?<![0-9A-Za-z])[0-9a-f]{7,40}(?![0-9A-Za-z])")
_END = r"\s`\"'<>)"
_HOSTS = "github|gitlab|bitbucket|codeberg|huggingface|openreview|orcid|linkedin"
_ZONES = "JST|KST|IST|CET|CEST|EET|EEST|BST|GMT|EST|EDT|CST|CDT|MST|MDT|PST|PDT|AEST|AEDT"

Finder = Callable[[str], Iterable[re.Match[str]]]


class Refusal(Exception):
    """One sentence that says why nothing is built."""


def commit_ids(text: str) -> Iterable[re.Match[str]]:
    """The hex strings that may be commit ids: 7 to 40 characters, a letter and a digit among
    them, and not the length of a sha256 prefix."""
    for match in _HEX.finditer(text):
        value = match.group(0)
        if len(value) != SHA256_PREFIX and not value.isdigit() and not value.isalpha():
            yield match


SCAN: tuple[tuple[str, Finder], ...] = (
    ("e-mail address", re.compile(r"[\w.%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+").finditer),
    ("URL", re.compile(rf"[A-Za-z][A-Za-z0-9+.-]*://[^{_END}]+").finditer),
    (
        "host of a code or profile site",
        re.compile(rf"\b(?:{_HOSTS})\.[a-z]{{2,}}[^{_END}]*", re.IGNORECASE).finditer,
    ),
    (
        "path with an account name",
        re.compile(rf"(?:/home/|/Users/|[A-Za-z]:\\Users\\)[^/\\{_END}]+").finditer,
    ),
    ("commit id", commit_ids),
    (
        "affiliation or funding",
        re.compile(
            r"\b(?:University|Institute|Laboratory|Department|Faculty|College|School) of\b"
            r"|\bfunded by\b|\bgrant (?:no\b|number|agreement)",
            re.IGNORECASE,
        ).finditer,
    ),
    ("local time zone", re.compile(rf"\b(?:{_ZONES})\b").finditer),
)


# --------------------------------------------------------------------------------------------
# The files and the list
# --------------------------------------------------------------------------------------------


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read(path: Path) -> tuple[bytes, str]:
    """The bytes of a file and their text; a refusal when it is missing or is not UTF-8."""
    if not path.is_file():
        raise Refusal(f"there is no file {path.name} where it was looked for.")
    data = path.read_bytes()
    try:
        return data, data.decode("utf-8")
    except UnicodeDecodeError:
        raise Refusal(f"{path.name} is not UTF-8.") from None


def read_list(text: str) -> dict[str, str]:
    """The list as string to token, in file order; a refusal when the list is not in form."""
    lines = text.split("\n")
    if lines[-1] == "":
        lines.pop()
    pairs: dict[str, str] = {}
    for number, line in enumerate(lines, 1):
        cells = line.split("\t")
        if len(cells) != 2:
            raise Refusal(f"line {number} of the list is not string<TAB>token.")
        string, token = cells
        if not string:
            raise Refusal(f"line {number} of the list has an empty string.")
        if not _TOKEN.fullmatch(token):
            raise Refusal(
                f"line {number} of the list: the token is not a word in capitals between "
                "square brackets."
            )
        if string in pairs:
            raise Refusal(f"line {number} of the list has a string that is listed before.")
        pairs[string] = token
    for number, (before, after) in enumerate(pairwise(pairs), 2):
        if after < before:
            raise Refusal(f"the list is not sorted by string at line {number}.")
    tokens = sorted(set(pairs.values()))
    for number, string in enumerate(pairs, 1):
        for token in tokens:
            if string.lower() in token.lower():
                raise Refusal(
                    f"line {number} of the list: the string is part of the token {token}."
                )
    return pairs


# --------------------------------------------------------------------------------------------
# Replacement
# --------------------------------------------------------------------------------------------


def places(text: str, strings: Iterable[str]) -> list[tuple[int, str]]:
    """Where the text is replaced: the start of each place and its string, in text order. The
    longest string is looked for first, and a place does not overlap one taken before it."""
    taken = bytearray(len(text))
    found = []
    for string in sorted(strings, key=lambda s: (-len(s), s)):
        start = text.find(string)
        while start >= 0:
            end = start + len(string)
            if any(taken[start:end]):
                start = text.find(string, start + 1)
                continue
            taken[start:end] = b"\x01" * len(string)
            found.append((start, string))
            start = text.find(string, end)
    return sorted(found)


def replace(text: str, pairs: Mapping[str, str]) -> tuple[str, Counter[str]]:
    """The copy of a text, and the number of places of each string."""
    parts, at = [], 0
    counts: Counter[str] = Counter()
    for start, string in places(text, pairs):
        parts += [text[at:start], pairs[string]]
        at = start + len(string)
        counts[string] += 1
    parts.append(text[at:])
    return "".join(parts), counts


def hashes_text(
    rows: Sequence[tuple[str, str, bytes]],
    names: Sequence[str],
    by_token: Mapping[str, Mapping[str, int]],
) -> str:
    """``HASHES.txt``: a line per hashed file, then a line per token with its places by file."""
    width = max(len(what) for what, _, _ in rows)
    lines = ["sha256"]
    lines += [f"{sha256(data)}  {what:<{width}}  {name}" for what, name, data in rows]
    lines += ["", "places replaced"]
    for token, counts in by_token.items():
        lines.append(f"{token}  " + "  ".join(f"{name} {counts[name]}" for name in names))
    return "\n".join(lines) + "\n"


def build(plan: Path, guide: Path, strings: Path) -> dict[str, bytes]:
    """The files of the output folder by name: the two copies and ``HASHES.txt``. Nothing is
    written here, and a refusal leaves nothing half done."""
    if plan.name == guide.name:
        raise Refusal(f"the two registered files have one name, {plan.name}.")
    sources = {path.name: read(path) for path in (plan, guide)}
    list_bytes, list_text = read(strings)
    pairs = read_list(list_text)
    tokens = sorted(set(pairs.values()))
    for name, (_, text) in sources.items():
        for token in tokens:
            if token in text:
                raise Refusal(f"the token {token} already occurs in the registered {name}.")
    copies: dict[str, bytes] = {}
    used: Counter[str] = Counter()
    by_token: dict[str, Counter[str]] = {token: Counter() for token in tokens}
    for name, (_, text) in sources.items():
        copy, counts = replace(text, pairs)
        copies[name] = copy.encode("utf-8")
        used += counts
        for string, count in counts.items():
            by_token[pairs[string]][name] += count
    for number, string in enumerate(pairs, 1):
        if not used[string]:
            raise Refusal(
                f"line {number} of the list: the string replaces nothing in either file "
                "(it occurs in neither, or only inside a longer string of the list)."
            )
    rows = [("registered", name, data) for name, (data, _) in sources.items()]
    rows += [("anonymised", name, data) for name, data in copies.items()]
    rows += [("script", Path(__file__).name, Path(__file__).read_bytes())]
    rows += [("list", strings.name, list_bytes)]
    text = hashes_text(rows, list(sources), by_token)
    return {**copies, HASHES: text.encode("utf-8")}


def write(out: Path, files: Mapping[str, bytes]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        (out / name).write_bytes(data)


def compare(out: Path, files: Mapping[str, bytes]) -> dict[str, str]:
    """For each file of a build, how the file on disk stands to it."""
    states = {}
    for name, data in files.items():
        path = out / name
        if not path.is_file():
            states[name] = "missing"
        else:
            states[name] = "identical" if path.read_bytes() == data else "differs"
    return states


# --------------------------------------------------------------------------------------------
# The scan
# --------------------------------------------------------------------------------------------


def finders(strings: Iterable[str] = ()) -> list[tuple[str, Finder]]:
    """The patterns of the scan, and one for each string of the list."""
    listed = [
        (
            "string of the list",
            re.compile(re.escape(s), re.IGNORECASE if len(s) >= VARIANT_FROM else 0).finditer,
        )
        for s in strings
    ]
    return [*SCAN, *listed]


def scan(name: str, text: str, strings: Iterable[str] = ()) -> list[str]:
    """One line for each candidate in a text: file, line number, kind and the string found."""
    found = set()
    for what, finder in finders(strings):
        for match in finder(text):
            found.add((text.count("\n", 0, match.start()) + 1, what, match.group(0)))
    return [f"{name}:{line}: {what}: {value}" for line, what, value in sorted(found)]


# --------------------------------------------------------------------------------------------
# The command line
# --------------------------------------------------------------------------------------------


def run_build(args: argparse.Namespace) -> int:
    files = build(args.plan, args.guide, args.strings)
    for path in (args.plan, args.guide, args.strings):
        if path.resolve().parent == args.out.resolve():
            raise Refusal(f"the output folder is the folder of {path.name}.")
    write(args.out, files)
    print(files[HASHES].decode("utf-8"), end="")
    return 0


def run_check(args: argparse.Namespace) -> int:
    states = compare(args.out, build(args.plan, args.guide, args.strings))
    for name, state in states.items():
        print(f"{state:<9}  {name}")
    stale = sum(state != "identical" for state in states.values())
    print(
        f"out of date: {stale} of {len(states)} files are not those of a build"
        if stale
        else "up to date: the copies and the hashes are those of a build"
    )
    return FOUND if stale else 0


def run_scan(args: argparse.Namespace) -> int:
    strings = list(read_list(read(args.strings)[1])) if args.strings.is_file() else []
    names = (args.plan.name, args.guide.name)
    lines = [line for name in names for line in scan(name, read(args.out / name)[1], strings)]
    print("\n".join(lines) if lines else f"nothing found in {len(names)} copies")
    if not args.strings.is_file():
        print("the list is not at hand: its strings were not looked for")
    return FOUND if lines else 0


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m analysis.coling.anonymise", description=(__doc__ or "").splitlines()[0]
    )
    ap.add_argument("command", choices=("build", "check", "scan"))
    ap.add_argument("--plan", type=Path, default=PLAN, help="the registered plan")
    ap.add_argument("--guide", type=Path, default=GUIDE, help="the registered guide")
    ap.add_argument("--list", dest="strings", type=Path, default=LIST, help="the list of strings")
    ap.add_argument("--out", type=Path, default=OUT, help="the folder of the copies")
    args = ap.parse_args(None if argv is None else list(argv))
    run = {"build": run_build, "check": run_check, "scan": run_scan}[args.command]
    try:
        return run(args)
    except Refusal as refusal:
        print(f"refused: {refusal}", file=sys.stderr)
        return REFUSED


if __name__ == "__main__":
    raise SystemExit(main())
