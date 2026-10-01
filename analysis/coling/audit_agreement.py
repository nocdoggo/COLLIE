"""Agreement on the literal-reading labels: statistics, the pilot gate, adjudication, gold.

The agreement script of ``AUDIT_GUIDE.md`` (sections 4, 5 and 8.1) for task A and for its pilot,
check set and reserve. It reads the two filled sheets that ``audit_sample.py`` handed out blank,
and nothing else: no outcome and no reader output.

Statistics (section 8.1), always before adjudication
----------------------------------------------------
* Month offsets of ``start`` and of ``end`` from the Date of update,
  ``12 x (year(d) - year(a)) + (month(d) - month(a))``, and day offsets as a secondary.
* Krippendorff's alpha with the interval metric, two coders, on the start offset and on the end
  offset, over the items where both annotators gave an interval (:func:`krippendorff_alpha`,
  coded here from the coincidence matrix; the tests check it against published examples).
* The share of items with identical intervals: the same start and the same end, or two
  abstentions; an interval against an abstention is not identical.
* Cohen's kappa over all items on ``abstain``, ``certainty``, ``statement_type``, ``stale`` and
  any distractor, each with the raw agreement, both annotators' marginal shares, and
  Krippendorff's alpha with the nominal metric beside it.
* The same by stratum and by period (from the task's key), with alpha only where a cell has at
  least ``MIN_PAIRS`` pairs of intervals.
* 95% percentile bootstrap intervals over items, ``DRAWS`` draws, seed 20261001.
* Mean seconds per item, from the sitting times in each sheet's header.

Gate (section 4)
----------------
On the check set (or the reserve): alpha on the start month offsets and alpha on the end month
offsets must both reach ``GATE_ALPHA``. The share of identical intervals is printed beside them
and is not part of the gate. When fewer than ``MIN_PAIRS`` check items have an interval from both
annotators, or an alpha is undefined because the offsets do not vary, the pilot items are pooled
with the check items. A gate that is still undefined after pooling is reported as not passed.
The guide has the check set labelled under the revised guide, and the reserve under the guide
revised once more. So the gate also names the earlier sets (the pilot; for the reserve, the
check set too) whose submitted sheets carry the same guide line (``same_guide_as``; null when
none of them was submitted). A warning is printed for each, and the exit status does not change.

Adjudication and gold (section 5)
---------------------------------
``agree`` first checks both sheets against the blanks that were handed out (which must still be
under ``--dir``, unchanged, so a sheet is filled in a copy kept elsewhere), records the sha256
of both submitted sheets and saves the statistics; only then does it write the list of
disagreements. An item goes on the list when the two rows differ in ``statement_type``,
``abstain``, ``start``, ``end``, ``certainty``, the distractor roles (as a set with counts) or
``abstain_reason``; ``quote``, ``note``, ``hard`` and the distractor quotes alone do not put it
there. For the literal task the list is the adjudication sheet: the adjudicator fills the
entered columns with the decided label, ``adj_decision`` (``slip`` or ``gap``) and
``adj_note``. A ``gap`` row left without a label is an item that could not be settled; it is
left out of the gold and counted. The adjudicator fills a copy kept elsewhere: ``agree`` does
not run again on the literal task while the sheet under ``--dir`` holds a decision, so that it
cannot overwrite one.

``gold`` checks the filled adjudication sheet with the validator's row checks and writes
``literal_gold.csv``: ``item_id``, the entered columns (dates in full), ``adj_decision`` (``agree``,
``slip``, ``gap``) and ``adj_note``, sorted by item, with its sha256 in ``manifest.json``. On an
item the annotators agreed on, the gold takes the shorter of the two quotes, ``hard`` when either
set it, both notes, and A1's distractor quotes. The pilot, the check set and the reserve get no
gold.

Outputs, under ``--dir`` (``analysis/coling/out/audit`` unless another is named)
---------------------------------------------------------------------------------
``submitted/<task>_<A1|A2>.csv`` (the sheets as submitted), ``<task>_agreement.json``,
``<task>_labels.csv`` (both annotators' rows with ``stale``, the four offsets and ``check``),
``<task>_disagreements.csv`` (pilot, check, reserve) or ``literal_adjudication.csv``, and
``literal_gold.csv``. Hashes go to the ``submitted``, ``agreement`` and ``gold`` entries of
``manifest.json``.

Usage (from the repository root)::

    PYTHONPATH=. python -m analysis.coling.audit_agreement validate SHEET [--blank BLANK]
    PYTHONPATH=. python -m analysis.coling.audit_agreement agree --task pilot \\
        --a1 FILLED_A1.csv --a2 FILLED_A2.csv [--dir analysis/coling/out/audit] [--keys DIR]
    PYTHONPATH=. python -m analysis.coling.audit_agreement agree --task check \\
        --a1 FILLED_A1.csv --a2 FILLED_A2.csv        # prints the gate; exit status 0 on pass
    PYTHONPATH=. python -m analysis.coling.audit_agreement gold --adjudication FILLED.csv

Exit status: 0 done (and the gate passed, for ``check`` and ``reserve``), 1 the gate did not
pass, 2 a sheet does not validate or a filled adjudication sheet is in the way.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from collections.abc import Callable, Hashable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from analysis.coling import audit_sample as S

SEED = S.SEED
DRAWS = 2000
GATE_ALPHA = 0.6
MIN_PAIRS = 10
GATE_TASKS = ("check", "reserve")
# the sets labelled before a gated one, each under an earlier version of the guide
GATE_TASKS_BEFORE = {"check": ("pilot",), "reserve": ("pilot", "check")}
SUBMITTED_DIR = "submitted"
ADJUDICATION = "literal_adjudication.csv"
GOLD = "literal_gold.csv"
OFFSETS = ("start_offset_m", "end_offset_m", "start_offset_d", "end_offset_d")
CLASS_FIELDS = ("abstain", "certainty", "statement_type", "stale", "any_distractor")
ADJUDICATED = (
    "statement_type",
    "abstain",
    "start",
    "end",
    "certainty",
    "distractor_roles",
    "abstain_reason",
)
DECISIONS = ("slip", "gap")
LABEL_COLUMNS = ("item_id", "annotator", *S.ENTERED, "stale", *OFFSETS, "check")
ADJUDICATION_COLUMNS = (
    *S.SHOWN,
    "differs",
    *(f"{a}_{c}" for a in S.ANNOTATORS for c in S.ENTERED),
    *S.ENTERED,
    "adj_decision",
    "adj_note",
)
GOLD_COLUMNS = ("item_id", *S.ENTERED, "adj_decision", "adj_note")

Pair = tuple[S.Label, S.Label]


# --------------------------------------------------------------------------------------------
# Agreement coefficients
# --------------------------------------------------------------------------------------------


def krippendorff_alpha(
    units: Iterable[Sequence[Hashable | None]], metric: str = "interval"
) -> float | None:
    """Krippendorff's alpha for any number of coders, with missing values.

    ``units`` holds, for each unit, the values the coders gave (None where a coder gave none). A
    unit with fewer than two values is not pairable and is left out. ``metric`` is ``nominal``
    (the difference of two values is 1 unless they are equal) or ``interval`` (the squared
    difference). The coefficient is ``1 - D_o / D_e`` from the coincidence matrix (Krippendorff
    2011, "Computing Krippendorff's Alpha-Reliability"). It is None when there is nothing to
    pair or when every value is the same, since the expected disagreement is then zero.
    """
    if metric not in ("nominal", "interval"):
        raise ValueError(f"metric must be nominal or interval: {metric!r}")
    kept = [[v for v in unit if v is not None] for unit in units]
    kept = [unit for unit in kept if len(unit) >= 2]
    values = sorted({v for unit in kept for v in unit}, key=lambda v: (str(type(v)), v))
    if len(values) < 2:
        return None
    index = {v: n for n, v in enumerate(values)}
    coincidence = np.zeros((len(values), len(values)))
    for unit in kept:
        counts = Counter(unit)
        weight = 1.0 / (len(unit) - 1)
        for c, n_c in counts.items():
            for k, n_k in counts.items():
                pairs = n_c * (n_c - 1) if c == k else n_c * n_k
                coincidence[index[c], index[k]] += pairs * weight
    totals = coincidence.sum(axis=1)
    n = totals.sum()
    if metric == "interval":
        numbers = np.array([float(v) for v in values])
        delta = (numbers[:, None] - numbers[None, :]) ** 2
    else:
        delta = 1.0 - np.eye(len(values))
    expected = float((np.outer(totals, totals) * delta).sum())
    if expected == 0:
        return None
    observed = float((coincidence * delta).sum())
    return 1.0 - (n - 1) * observed / expected


def cohen_kappa(pairs: Sequence[tuple[Hashable, Hashable]]) -> float | None:
    """Cohen's kappa for two raters; None with no pair or when chance agreement is complete."""
    n = len(pairs)
    if n == 0:
        return None
    agree = sum(a == b for a, b in pairs) / n
    first, second = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    chance = sum(first[c] * second[c] for c in first) / (n * n)
    return None if chance >= 1 else (agree - chance) / (1 - chance)


def bootstrap(
    n: int, statistic: Callable[[Sequence[int]], float | None], draws: int = DRAWS, seed: int = SEED
) -> dict[str, Any] | None:
    """95% percentile interval of ``statistic`` over resampled items.

    ``statistic`` takes the positions of the resampled items. Draws on which it is undefined are
    left out and counted.
    """
    if n == 0:
        return None
    picks = np.random.default_rng(seed).integers(0, n, size=(draws, n))
    found = [statistic(row.tolist()) for row in picks]
    defined = [v for v in found if v is not None]
    if not defined:
        return None
    low, high = np.percentile(defined, [2.5, 97.5])
    return {"low": round(float(low), 6), "high": round(float(high), 6), "draws": len(defined)}


# --------------------------------------------------------------------------------------------
# Statistics of one pair of sheets
# --------------------------------------------------------------------------------------------


def class_value(label: S.Label, name: str) -> str:
    if name == "any_distractor":
        return "yes" if label.distractor_roles else "no"
    if name in ("abstain", "stale"):
        return "yes" if getattr(label, name) else "no"
    return str(getattr(label, name))


def same_interval(a: S.Label, b: S.Label) -> bool:
    """The same start and the same end, or two abstentions."""
    return a.interval == b.interval


def offset_units(pairs: Sequence[Pair], name: str) -> list[tuple[int, int]]:
    """The offsets of the two annotators on the items where both gave an interval."""
    both = [(a, b) for a, b in pairs if a.interval and b.interval]
    return [(a.offsets()[name], b.offsets()[name]) for a, b in both]  # type: ignore[misc]


def rounded(value: float | None) -> float | None:
    return None if value is None else round(float(value), 6)


def class_statistics(pairs: Sequence[Pair], name: str) -> dict[str, Any]:
    values = [(class_value(a, name), class_value(b, name)) for a, b in pairs]
    n = len(values)
    marginals = {
        annotator: {k: round(c / n, 6) for k, c in sorted(Counter(v[i] for v in values).items())}
        for i, annotator in enumerate(S.ANNOTATORS)
        if n
    }
    return {
        "n": n,
        "kappa": rounded(cohen_kappa(values)),
        "raw_agreement": rounded(sum(a == b for a, b in values) / n) if n else None,
        "alpha_nominal": rounded(krippendorff_alpha(values, "nominal")),
        "marginal_shares": marginals,
    }


def cell_statistics(pairs: Sequence[Pair], *, intervals: bool = False) -> dict[str, Any]:
    """The statistics of section 8.1 on a set of items; with ``intervals``, the bootstrap too."""
    n = len(pairs)
    interval_pairs = sum(1 for a, b in pairs if a.interval and b.interval)
    out: dict[str, Any] = {
        "n": n,
        "interval_pairs": interval_pairs,
        "identical_intervals": rounded(sum(same_interval(a, b) for a, b in pairs) / n)
        if n
        else None,
    }
    enough = interval_pairs >= MIN_PAIRS or intervals
    for name in OFFSETS:
        out[f"alpha_{name}"] = (
            rounded(krippendorff_alpha(offset_units(pairs, name))) if enough else None
        )
    for name in CLASS_FIELDS:
        out[name] = class_statistics(pairs, name)
    if intervals and n:
        out["intervals_95"] = {
            "identical_intervals": bootstrap(
                n, lambda rows: sum(same_interval(*pairs[r]) for r in rows) / len(rows)
            )
        }
        for name in OFFSETS:
            units = offset_units(pairs, name)
            out["intervals_95"][f"alpha_{name}"] = bootstrap(
                len(units), lambda rows, units=units: krippendorff_alpha([units[r] for r in rows])
            )
        for name in CLASS_FIELDS:
            values = [(class_value(a, name), class_value(b, name)) for a, b in pairs]
            out["intervals_95"][f"kappa_{name}"] = bootstrap(
                n, lambda rows, values=values: cohen_kappa([values[r] for r in rows])
            )
    return out


def paired(a1: S.Checked, a2: S.Checked) -> dict[str, Pair]:
    """The two labels of every item, by item id; the sheets must hold the same items."""
    if set(a1.labels) != set(a2.labels):
        odd = sorted(set(a1.labels) ^ set(a2.labels))
        raise ValueError(f"the two sheets do not hold the same items: {odd[:5]}")
    return {i: (a1.labels[i], a2.labels[i]) for i in sorted(a1.labels)}


def statistics(
    pairs: Mapping[str, Pair],
    minutes: Mapping[str, int | None],
    key: Mapping[str, Mapping[str, str]] | None = None,
) -> dict[str, Any]:
    """Everything section 8.1 asks for on one pair of sheets."""
    items = list(pairs.values())
    out = cell_statistics(items, intervals=True)
    out["hard"] = dict(
        zip(S.ANNOTATORS, (sum(p[i].hard for p in items) for i in range(2)), strict=True)
    )
    out["seconds_per_item"] = {
        a: None if m is None or not items else round(60 * m / len(items), 1)
        for a, m in minutes.items()
    }
    out["to_adjudication"] = sum(bool(differences(a, b)) for a, b in items)
    if key:
        for by in ("stratum", "period"):
            groups: dict[str, list[Pair]] = {}
            for item, pair in pairs.items():
                groups.setdefault(key.get(item, {}).get(by, "unknown"), []).append(pair)
            out[f"by_{by}"] = {g: cell_statistics(groups[g]) for g in sorted(groups)}
    return out


def gate(check: Sequence[Pair], pilot: Sequence[Pair] | None = None) -> dict[str, Any]:
    """The gate of section 4 on the check items, pooled with the pilot items when it must be."""

    def measure(items: Sequence[Pair]) -> dict[str, Any]:
        return {
            "items": len(items),
            "interval_pairs": sum(1 for a, b in items if a.interval and b.interval),
            "alpha_start_offset_m": rounded(
                krippendorff_alpha(offset_units(items, "start_offset_m"))
            ),
            "alpha_end_offset_m": rounded(krippendorff_alpha(offset_units(items, "end_offset_m"))),
            "identical_intervals": rounded(sum(same_interval(a, b) for a, b in items) / len(items))
            if items
            else None,
        }

    def undefined(m: Mapping[str, Any]) -> bool:
        return (
            m["interval_pairs"] < MIN_PAIRS
            or m["alpha_start_offset_m"] is None
            or m["alpha_end_offset_m"] is None
        )

    result = measure(check)
    result["pooled_with_pilot"] = False
    if undefined(result) and pilot is not None:
        result = {"check_alone": result, **measure([*check, *pilot]), "pooled_with_pilot": True}
    result["threshold"] = GATE_ALPHA
    if undefined(result):
        result["passed"] = False
        result["reason"] = "undefined: too few pairs of intervals, or offsets that do not vary" + (
            "" if result["pooled_with_pilot"] else "; give the pilot sheets to pool them"
        )
        return result
    alphas = (result["alpha_start_offset_m"], result["alpha_end_offset_m"])
    result["passed"] = all(a >= GATE_ALPHA for a in alphas)
    result["reason"] = "both alphas reach the threshold" if result["passed"] else "an alpha is low"
    return result


# --------------------------------------------------------------------------------------------
# Disagreements, the adjudication sheet and the gold
# --------------------------------------------------------------------------------------------


def differences(a: S.Label, b: S.Label) -> list[str]:
    """The adjudicated fields on which two labels differ."""
    views = [
        {
            "statement_type": x.statement_type,
            "abstain": x.abstain,
            "start": x.start,
            "end": x.end,
            "certainty": x.certainty,
            "distractor_roles": sorted(x.distractor_roles),
            "abstain_reason": x.abstain_reason,
        }
        for x in (a, b)
    ]
    return [name for name in ADJUDICATED if views[0][name] != views[1][name]]


def label_rows(checked: Mapping[str, S.Checked]) -> list[dict[str, Any]]:
    """Both annotators' rows with the computed columns (stale, offsets, check)."""
    rows = []
    for annotator, sheet in checked.items():
        notes: dict[str, list[str]] = {}
        for line in sheet.warnings:
            where, _, what = line.partition(": ")
            if where.startswith("row "):
                notes.setdefault(where[where.find("(") + 1 : where.find(")")], []).append(what)
        for item, label in sheet.labels.items():
            offsets = {k: "" if v is None else v for k, v in label.offsets().items()}
            rows.append(
                {
                    "item_id": item,
                    "annotator": annotator,
                    **label.entered(),
                    "stale": int(label.stale),
                    **offsets,
                    "check": "; ".join(notes.get(item, [])) or "ok",
                }
            )
    return sorted(rows, key=lambda r: (r["item_id"], r["annotator"]))


def disagreement_rows(
    pairs: Mapping[str, Pair], shown: Mapping[str, Mapping[str, str]]
) -> list[dict[str, Any]]:
    """One row per item on which the annotators differ, with both labels side by side."""
    rows = []
    for item, (a, b) in pairs.items():
        differs = differences(a, b)
        if not differs:
            continue
        row: dict[str, Any] = {c: S.unguarded(shown[item].get(c, "")) for c in S.SHOWN}
        row["differs"] = "; ".join(differs)
        for annotator, label in zip(S.ANNOTATORS, (a, b), strict=True):
            row |= {f"{annotator}_{c}": v for c, v in label.entered().items()}
        rows.append(row)
    return rows


def agreed_gold(item: str, a: S.Label, b: S.Label) -> dict[str, str]:
    """The gold row of an item the annotators agree on."""
    quotes = [q for q in (a.quote, b.quote) if q]
    notes = [f"{who}: {x.note}" for who, x in zip(S.ANNOTATORS, (a, b), strict=True) if x.note]
    row = a.entered()
    row |= {
        "quote": min(quotes, key=len) if quotes else "",
        "hard": "1" if a.hard or b.hard else "0",
        "note": "; ".join(notes),
    }
    return {"item_id": item, **row, "adj_decision": "agree", "adj_note": ""}


def build_gold(
    pairs: Mapping[str, Pair], adjudicated: Sequence[Mapping[str, str]]
) -> tuple[list[dict[str, str]], dict[str, Any], list[str]]:
    """The gold rows, the counts to report, and what is wrong with the adjudication sheet."""
    need = {item: differences(a, b) for item, (a, b) in pairs.items() if differences(a, b)}
    errors: list[str] = []
    decided: dict[str, dict[str, str]] = {}
    left_out: list[str] = []
    counts: dict[str, Counter[str]] = {d: Counter() for d in DECISIONS}
    for n, row in enumerate(adjudicated, start=1):
        item = row.get("item_id", "")
        where = f"row {n} ({item or 'no item_id'})"
        decision = (row.get("adj_decision") or "").strip().lower()
        if item not in need or item in decided or item in left_out:
            errors.append(f"{where}: not an item to adjudicate, or repeated")
            continue
        if decision not in DECISIONS:
            errors.append(f"{where}: adj_decision must be one of {', '.join(DECISIONS)}")
            continue
        if decision == "gap" and not any((row.get(c) or "").strip() for c in S.ENTERED):
            left_out.append(item)
            counts[decision].update(need[item])
            continue
        label, wrong, _ = S.read_label(row)
        errors += [f"{where}: {e}" for e in wrong]
        if label is not None:
            decided[item] = {
                "item_id": item,
                **label.entered(),
                "adj_decision": decision,
                "adj_note": (row.get("adj_note") or "").strip(),
            }
            counts[decision].update(need[item])
    missing = sorted(set(need) - set(decided) - set(left_out))
    if not errors:
        errors += [f"sheet: item {item} is not adjudicated" for item in missing]
    rows = [
        decided[item] if item in decided else agreed_gold(item, a, b)
        for item, (a, b) in pairs.items()
        if item not in left_out and (item in decided or item not in need)
    ]
    report = {
        "items": len(pairs),
        "gold_rows": len(rows),
        "agree": len(pairs) - len(need),
        "slip": sum(1 for r in decided.values() if r["adj_decision"] == "slip"),
        "gap": sum(1 for r in decided.values() if r["adj_decision"] == "gap") + len(left_out),
        "left_out": len(left_out),
        "decisions_by_field": {d: dict(sorted(c.items())) for d, c in counts.items()},
    }
    return sorted(rows, key=lambda r: r["item_id"]), report, errors


# --------------------------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------------------------


def read_key(path: Path) -> dict[str, dict[str, str]]:
    return {r["item_id"]: r for r in S.read_csv(path)} if path.is_file() else {}


def submit(root: Path, task: str, sheets: Mapping[str, Path]) -> dict[str, S.Checked] | None:
    """Validate both sheets against the blanks that were handed out; when both pass, copy them
    byte for byte under ``submitted/`` and record their sha256. Returns None when a sheet does
    not validate."""
    handed = load_manifest(root).get("sheets", {}).get(task, {}).get("files", {})
    checked: dict[str, S.Checked] = {}
    for annotator, path in sheets.items():
        blank = root / f"{task}_{annotator}.csv"
        usable = blank.is_file() and blank.resolve() != path.resolve()
        sheet = S.check_file(path, blank if usable else None, root)
        named = S.meta_value(sheet.meta, "sheet"), S.meta_value(sheet.meta, "annotator")
        if named != (task, annotator):
            sheet.errors.append(
                f"sheet: the header says {named[0]} {named[1]}, not {task} {annotator}"
            )
        if not usable:
            sheet.errors.append(
                f"sheet: {blank} is missing or is the file given; move the filled sheet out of "
                f"{root}, write the blank again (audit_sample sheets --task {task}) and re-run"
            )
        recorded = handed.get(blank.name)
        if usable and recorded and recorded != hashlib.sha256(blank.read_bytes()).hexdigest():
            sheet.errors.append(
                f"sheet: {blank} is not the blank sheet the manifest records; write it again "
                f"(audit_sample sheets --task {task}) and re-run"
            )
        S.report_check(path, sheet)
        checked[annotator] = sheet
    if not all(sheet.ok for sheet in checked.values()):
        return None
    entry = {}
    for annotator, path in sheets.items():
        name = f"{SUBMITTED_DIR}/{task}_{annotator}.csv"
        entry[name] = S.write_bytes(root, name, path.read_bytes())
    S.update_manifest(root, "submitted", {**load_manifest(root).get("submitted", {}), **entry})
    return checked


def decisions_entered(path: Path) -> bool:
    """Whether the adjudication sheet at ``path`` holds a decision, a decided label or a note (a
    file that cannot be read counts as filled)."""
    if not path.is_file():
        return False
    try:
        _, rows = S.read_sheet(path)
    except UnicodeDecodeError:
        return True
    return any(row.get(c) for row in rows for c in (*S.ENTERED, "adj_decision", "adj_note"))


def guide_lines(root: Path, task: str) -> set[str]:
    """The guide lines in the headers of the submitted sheets of a task (empty when there is
    none)."""
    paths = [root / SUBMITTED_DIR / f"{task}_{a}.csv" for a in S.ANNOTATORS]
    lines = set()
    for path in paths:
        if path.is_file():
            try:
                lines.add(S.meta_value(S.read_sheet(path)[0], "guide"))
            except UnicodeDecodeError:
                continue
    return lines


def load_manifest(root: Path) -> dict[str, Any]:
    path = root / S.MANIFEST
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def print_statistics(task: str, stats: Mapping[str, Any]) -> None:
    print(f"{task}: {stats['n']} items, {stats['interval_pairs']} with an interval from both")
    for name in OFFSETS:
        span = stats["intervals_95"].get(f"alpha_{name}")
        between = f" [{span['low']}, {span['high']}]" if span else ""
        print(f"  alpha {name}: {stats[f'alpha_{name}']}{between}")
    print(f"  identical intervals: {stats['identical_intervals']}")
    for name in CLASS_FIELDS:
        print(
            f"  kappa {name}: {stats[name]['kappa']} (raw agreement {stats[name]['raw_agreement']})"
        )
    print(f"  seconds per item: {stats['seconds_per_item']}")
    print(f"  items that differ in an adjudicated field: {stats['to_adjudication']}")


def run_agree(args: argparse.Namespace) -> int:
    root: Path = args.dir
    task: str = args.task
    if task == "literal" and decisions_entered(root / ADJUDICATION):
        print(
            f"{root / ADJUDICATION} holds adjudication decisions and would be overwritten; "
            "move it out of the folder first. Nothing was scored"
        )
        return 2
    checked = submit(root, task, {"A1": args.a1, "A2": args.a2})
    if checked is None:
        print("a sheet does not validate; nothing was scored")
        return 2
    pairs = paired(checked["A1"], checked["A2"])
    key = read_key((args.keys or root / S.KEYS_DIR) / f"{task}_key.csv")
    minutes = {a: sheet.minutes for a, sheet in checked.items()}
    stats: dict[str, Any] = {
        "task": task,
        "guide": {a: S.meta_value(sheet.meta, "guide") for a, sheet in checked.items()},
        "sheets_sha256": {
            a: hashlib.sha256((root / SUBMITTED_DIR / f"{task}_{a}.csv").read_bytes()).hexdigest()
            for a in checked
        },
        **statistics(pairs, minutes, key),
    }
    notes: list[str] = []
    if task in GATE_TASKS:
        pilot = None
        pooled = {a: root / SUBMITTED_DIR / f"pilot_{a}.csv" for a in S.ANNOTATORS}
        if all(p.is_file() for p in pooled.values()):
            sheets = {a: S.check_file(p, None, root) for a, p in pooled.items()}
            if all(s.ok for s in sheets.values()):
                pilot = list(paired(sheets["A1"], sheets["A2"]).values())
            else:
                notes.append(
                    "the submitted pilot sheets do not validate against the blanks under "
                    f"{root}, so the pilot items cannot be pooled"
                )
        earlier = {t: guide_lines(root, t) for t in GATE_TASKS_BEFORE[task]}
        same = [t for t, lines in earlier.items() if lines & set(stats["guide"].values())]
        notes += [
            f"a {task} sheet carries the guide line of the {t} sheets "
            f"({', '.join(sorted(earlier[t]))}); the guide has the {task} set labelled under "
            "a revised guide (write its sheets again after the revision)"
            for t in same
        ]
        stats["gate"] = gate(list(pairs.values()), pilot) | {
            "same_guide_as": same if any(earlier.values()) else None
        }
    name = f"{task}_agreement.json"
    files = {name: S.write_text(root, name, json.dumps(stats, indent=1, sort_keys=True) + "\n")}
    name = f"{task}_labels.csv"
    files[name] = S.write_text(root, name, S.plain_csv(LABEL_COLUMNS, label_rows(checked)))
    shown = {r["item_id"]: r for r in checked["A1"].rows}
    rows = disagreement_rows(pairs, shown)
    meta = [
        ("task", S.TASKS[task]),
        ("sheet", f"{task} disagreements"),
        ("seed", SEED),
        ("items", len(rows)),
        ("values of adj_decision", " | ".join(DECISIONS)),
    ]
    literal = task == "literal"
    name = ADJUDICATION if literal else f"{task}_disagreements.csv"
    columns = ADJUDICATION_COLUMNS if literal else ADJUDICATION_COLUMNS[: -len(S.ENTERED) - 2]
    files[name] = S.write_text(root, name, S.sheet_text(columns, rows, meta))
    manifest = load_manifest(root)
    S.update_manifest(root, "agreement", {**manifest.get("agreement", {}), task: files})
    print_statistics(task, stats)
    print(f"wrote {', '.join(sorted(files))} under {root}")
    for line in notes:
        print(f"warning: {line}")
    if "gate" in stats:
        g = stats["gate"]
        print(
            f"gate: alpha start {g['alpha_start_offset_m']}, alpha end {g['alpha_end_offset_m']}, "
            f"threshold {GATE_ALPHA}; identical intervals {g['identical_intervals']}; "
            f"pooled with the pilot: {g['pooled_with_pilot']}; "
            f"{'PASSED' if g['passed'] else 'NOT PASSED'} ({g['reason']})"
        )
        return 0 if g["passed"] else 1
    return 0


def run_gold(args: argparse.Namespace) -> int:
    root: Path = args.dir
    recorded = load_manifest(root).get("submitted", {})
    sheets: dict[str, S.Checked] = {}
    for annotator in S.ANNOTATORS:
        name = f"{SUBMITTED_DIR}/literal_{annotator}.csv"
        path = root / name
        if (
            not path.is_file()
            or recorded.get(name) != hashlib.sha256(path.read_bytes()).hexdigest()
        ):
            print(f"{path} is missing or is not the sheet the manifest records; run agree first")
            return 2
        sheets[annotator] = S.check_file(path, None, root)
    pairs = paired(sheets["A1"], sheets["A2"])
    try:
        _, adjudicated = S.read_sheet(args.adjudication)
    except UnicodeDecodeError:
        print(f"error: {S.NOT_UTF8}")
        print("the adjudication sheet does not validate; no gold was written")
        return 2
    rows, report, errors = build_gold(pairs, adjudicated)
    for line in errors:
        print(f"error: {line}")
    if errors:
        print("the adjudication sheet does not validate; no gold was written")
        return 2
    name = f"{SUBMITTED_DIR}/{ADJUDICATION}"
    report["adjudication_sha256"] = S.write_bytes(root, name, args.adjudication.read_bytes())
    report["file"] = GOLD
    report["sha256"] = S.write_text(root, report["file"], S.plain_csv(GOLD_COLUMNS, rows))
    S.update_manifest(root, "gold", report)
    print(json.dumps(report, indent=1, sort_keys=True))
    return 0


def run_validate(args: argparse.Namespace) -> int:
    return S.report_check(args.sheet, S.check_file(args.sheet, args.blank, args.dir))


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="python -m analysis.coling.audit_agreement",
        description=(__doc__ or "").splitlines()[0],
    )
    sub = ap.add_subparsers(dest="command", required=True)
    check = sub.add_parser("validate", help="check a filled sheet")
    check.add_argument("sheet", type=Path)
    check.add_argument("--blank", type=Path, default=None)
    check.add_argument("--dir", type=Path, default=S.OUT)
    check.set_defaults(run=run_validate)
    agree = sub.add_parser("agree", help="agreement of two filled sheets, the gate, disagreements")
    agree.add_argument("--task", required=True, choices=S.FIRST_SAMPLES)
    agree.add_argument("--a1", type=Path, required=True)
    agree.add_argument("--a2", type=Path, required=True)
    agree.add_argument("--dir", type=Path, default=S.OUT)
    agree.add_argument("--keys", type=Path, default=None)
    agree.set_defaults(run=run_agree)
    gold = sub.add_parser("gold", help="write the gold file from the adjudication sheet")
    gold.add_argument("--adjudication", type=Path, required=True)
    gold.add_argument("--dir", type=Path, default=S.OUT)
    gold.set_defaults(run=run_gold)
    return ap


def main(argv: Iterable[str] | None = None) -> int:
    args = parser().parse_args(None if argv is None else list(argv))
    return args.run(args)


if __name__ == "__main__":
    sys.exit(main())
