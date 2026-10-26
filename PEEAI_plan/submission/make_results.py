"""Read the committed Wave 3 held-out results and write every number the three items cite.

The source is the run `wave3_heldout_20261025T1625Z` (commit c052338), one `metrics.json` per
suite, as written by `plan-b eval report`. Nothing is typed in by hand. The script writes:

- `slides/figures/results_numbers.tex`: one macro per number, read as `\\res{campus:P2:met}`;
- `slides/figures/fig_results.tex` and `fig_results_v.tex`: the results figure (runs met per
  policy, per suite), side by side for the slides and stacked for the poster;
- `documentation/results.json`: the same numbers for `build_doc.py`.

The pgfplots charts `slides/figures/fig_result.tex` (deck and document), `fig_result_v.tex`
(poster) and `fig_result_record.tex` (the earlier 12-case test, document only) are written from
the same numbers, with plain policy names instead of codes. `slides/figures/results_numbers_final.tex`
holds the sums the single-system story reads (`\\res{final:P2:metk}`, `\\res{dev:recorded}`).

Wave 3b adds two more sources and never replaces the first. The fresh held-out run of policy
1.2 (`wave3b_fresh_20261025T2327Z`, cases C09 to C12, T05 and T06) gives the keys
`\\res{fresh:campus:P2:met}`, and the post-hoc diagnostic rerun of 1.2 on the spent cases
(`wave3b_rerun_spent_20261025T2345Z`, not a held-out result) gives `\\res{rerun:campus:P2:met}`.
They go to `slides/figures/results_numbers_v12.tex` and `documentation/results_v12.json`.

    python3 make_results.py
"""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
RUN_ID = "wave3_heldout_20261025T1625Z"
RUN = REPO / "apps/plan_b/evaluation/results" / RUN_ID
# Wave 3b, policy 1.2: the fresh held-out run and the post-hoc diagnostic rerun on spent cases.
V12_RUNS = {
    "fresh": "wave3b_fresh_20261025T2327Z",
    "rerun": "wave3b_rerun_spent_20261025T2345Z",
}
POLICIES = ["P0", "P1", "P2", "P3"]
NAMES = {
    "P0": "P0 fixed rules",
    "P1": "P1 model calls tools",
    "P2": "P2 model picks options",
    "P3": "P3 every check first",
}
# Rejection codes that mean the request was made on a state that had changed meanwhile.
STALE_CODES = ("REVISION_CONFLICT", "CANDIDATE_STALE")
# The outcome classes of each suite, as the report names them.
CLASSES = {
    "campus": [("goal", "goal_completion"), ("infeas", "appropriate_infeasibility")],
    "pantry": [("target", "target_attainment"), ("partial", "supported_partial")],
}


def suite_numbers(suite: str, run: Path = RUN) -> dict[str, dict[str, object]]:
    metrics = json.loads((run / suite / "report" / "metrics.json").read_text(encoding="utf-8"))
    out: dict[str, dict[str, object]] = {}
    for policy in POLICIES:
        p = metrics["by_policy"][policy]
        row: dict[str, object] = {}
        met_k = met_n = 0
        for short, key in CLASSES[suite]:
            k, n = p[key]["k"], p[key]["n"]
            row[short] = f"{k}/{n}"
            met_k += k
            met_n += n
        cases = [c["policies"][policy] for c in metrics["by_case"].values()]
        row["met"] = f"{met_k}/{met_n}"
        row["metk"] = met_k
        row["metn"] = met_n
        row["cases"] = sum(1 for c in cases if c["n"] and c["success"] == c["n"])
        row["ncases"] = len(cases)
        row["recorded"] = p["recorded"]
        row["planned"] = p["planned"]
        row["capped"] = p["capped"]
        row["viol"] = p["executed_violations"]
        row["refused"] = p["invalid_attempts"]
        row["unnec"] = p["unnecessary_changes"]["committed_changes"]
        row["unnecn"] = p["unnecessary_changes"]["n"]
        row["usd"] = f"{p['computation']['cost_usd']:.2f}"
        row["calls"] = p["computation"]["model_calls"]
        row["checks"] = f"{p['verification']['status_checks'] / p['scored']:.1f}"
        if suite == "pantry":
            ledger = p["pantry"]
            row["kits"] = f"{ledger['kits_on_time']}/{ledger['original_target']}"
            row["conserv"] = ledger["conservation_failures"]
            row["credits"] = ledger["duplicate_or_unauthorized_credits"]
        out[policy] = row
    total = {
        "recorded": sum(int(r["recorded"]) for r in out.values()),
        "planned": sum(int(r["planned"]) for r in out.values()),
        "viol": sum(int(r["viol"]) for r in out.values()),
        "refused": sum(int(r["refused"]) for r in out.values()),
        "unnec": sum(int(r["unnec"]) for r in out.values()),
        "stale": sum(
            int((e.get("invalid_attempts") or {}).get("by_code", {}).get(code, 0))
            for e in metrics["episodes"]
            for code in STALE_CODES
        ),
        "capped": sum(int(r["capped"]) for r in out.values()),
        "missing": len(metrics["missing"]),
        "aborted": len(metrics["aborted"]),
    }
    out["all"] = total
    return out


def macros(numbers: dict[str, dict[str, dict[str, object]]]) -> str:
    lines = [
        f"% Written by make_results.py from {RUN_ID}/<suite>/report/metrics.json. Do not edit.",
        "\\providecommand{\\res}[1]{\\csname res:#1\\endcsname}",
    ]
    for suite, rows in numbers.items():
        for policy, row in rows.items():
            for key, value in row.items():
                lines.append(f"\\expandafter\\def\\csname res:{suite}:{policy}:{key}\\endcsname{{{value}}}")
    both = {
        key: sum(int(numbers[s]["all"][key]) for s in numbers)
        for key in ("recorded", "planned", "viol", "refused", "stale", "unnec", "capped")
    }
    for key, value in both.items():
        lines.append(f"\\expandafter\\def\\csname res:both:{key}\\endcsname{{{value}}}")
    return "\n".join(lines) + "\n"


def v12_macros(sets: dict[str, dict[str, dict[str, dict[str, object]]]]) -> str:
    """The Wave 3b numbers under their own prefixes (`fresh:` and `rerun:`), so no key of the
    v1.1 record is shadowed."""
    lines = [
        "% Written by make_results.py from "
        + ", ".join(f"{V12_RUNS[k]} ({k})" for k in sets)
        + ", <suite>/report/metrics.json. Do not edit.",
        "\\providecommand{\\res}[1]{\\csname res:#1\\endcsname}",
    ]
    for prefix, numbers in sets.items():
        for suite, rows in numbers.items():
            for policy, row in rows.items():
                for key, value in row.items():
                    lines.append(
                        f"\\expandafter\\def\\csname res:{prefix}:{suite}:{policy}:{key}\\endcsname{{{value}}}"
                    )
        both = {
            key: sum(int(numbers[s]["all"][key]) for s in numbers)
            for key in ("recorded", "planned", "viol", "refused", "stale", "unnec", "capped")
        }
        run = REPO / "apps/plan_b/evaluation/results" / V12_RUNS[prefix]
        cost = sum(
            json.loads((run / s / "report" / "metrics.json").read_text(encoding="utf-8"))["by_policy"][p]["computation"]["cost_usd"]
            for s in numbers
            for p in POLICIES
        )
        both["usd"] = f"{cost:.2f}"
        both["metk"] = sum(int(numbers[s][p]["metk"]) for s in numbers for p in POLICIES)
        both["metn"] = sum(int(numbers[s][p]["metn"]) for s in numbers for p in POLICIES)
        for key, value in both.items():
            lines.append(f"\\expandafter\\def\\csname res:{prefix}:both:{key}\\endcsname{{{value}}}")
    return "\n".join(lines) + "\n"


def figure(numbers: dict[str, dict[str, dict[str, object]]], stacked: bool = False) -> str:
    """Two panels of horizontal bars, side by side or stacked: the share of recorded runs that
    met the case's outcome, per policy, labelled with the count. The stacked one is for the
    poster: larger type, closer rows and no captions (the poster's text carries them)."""
    width = 3.4 if stacked else 3.8
    labels = 4.9 if stacked else 4.1
    step = 0.85 if stacked else 1.0
    half = 0.28 if stacked else 0.32
    title_font = "\\large" if stacked else ""
    parts = [
        f"% Written by make_results.py from {RUN_ID}/<suite>/report/metrics.json. Do not edit.",
        "% Runs that met the case's outcome, per policy and suite (held-out, one run of the protocol).",
        "\\documentclass[border=4pt]{standalone}",
        "\\input{fig_style}",
        "\\begin{document}",
        f"\\begin{{tikzpicture}}[font=\\{'large' if stacked else 'normalsize'}]",
    ]
    captions = {
        "campus": "Cases with every run met, of 8: "
        + ", ".join(f"{p} {numbers['campus'][p]['cases']}" for p in POLICIES)
        + ". P0 runs once per case, P1 to P3 three times.",
        "pantry": "Cases with every run met, of 4: "
        + ", ".join(f"{p} {numbers['pantry'][p]['cases']}" for p in POLICIES)
        + ". One reported run, after a first attempt voided for a rate limit. No significance test.",
    }
    titles = {
        "campus": "Campus: 8 held-out cases, 80 runs",
        "pantry": "Pantry: 4 held-out cases, 40 runs",
    }
    for col, suite in enumerate(["campus", "pantry"]):
        x0 = 0.0 if stacked else col * (labels + width + 2.6)
        y0 = -col * 4.7 if stacked else 0.0
        parts.append(
            f"\\node[anchor=west, font={title_font}\\bfseries\\color{{primary}}] at ({x0 - labels:.2f},{y0 + 0.8:.2f}) {{{titles[suite]}}};"
        )
        for i, policy in enumerate(POLICIES):
            row = numbers[suite][policy]
            y = y0 - i * step
            share = int(row["metk"]) / int(row["metn"])
            fill = "primary" if policy == "P2" else "umbblue!55"
            parts += [
                f"\\node[anchor=east, text=ink] at ({x0 - 0.15:.2f},{y:.2f}) {{{NAMES[policy]}}};",
                f"\\fill[softgray] ({x0:.2f},{y - half:.2f}) rectangle ({x0 + width:.2f},{y + half:.2f});",
            ]
            if share > 0:
                parts.append(
                    f"\\fill[{fill}] ({x0:.2f},{y - half:.2f}) rectangle ({x0 + width * share:.3f},{y + half:.2f});"
                )
            parts.append(
                f"\\node[anchor=west, text=ink] at ({x0 + width + 0.1:.2f},{y:.2f}) "
                f"{{\\bfseries {row['metk']} of {row['metn']}}};"
            )
        if not stacked:
            parts.append(
                f"\\node[anchor=north west, text=muted, font=\\small, align=left, text width={labels + width + 0.9:.1f}cm] "
                f"at ({x0 - labels:.2f},{y0 - 3.5:.2f}) "
                f"{{{captions[suite]}}};"
            )
    parts += ["\\end{tikzpicture}", "\\end{document}", ""]
    return "\n".join(parts)

def final_macros(fresh: dict[str, dict[str, dict[str, object]]], record: dict[str, dict[str, dict[str, object]]]) -> str:
    """The sums the single-system story reads (keys `final:` and `dev:`): runs met per policy over
    both suites of the fresh held-out run, its case count, the model cost per run, and the size
    of the earlier 12-case test. Derived only from the numbers above."""
    run = REPO / "apps/plan_b/evaluation/results" / V12_RUNS["fresh"]
    lines = [
        f"% Written by make_results.py from {V12_RUNS['fresh']} (final:) and {RUN_ID} (dev:), "
        "<suite>/report/metrics.json. Do not edit.",
        "\\providecommand{\\res}[1]{\\csname res:#1\\endcsname}",
    ]
    values: dict[str, object] = {}
    for policy in POLICIES:
        values[f"final:{policy}:metk"] = sum(int(fresh[s][policy]["metk"]) for s in fresh)
        values[f"final:{policy}:metn"] = sum(int(fresh[s][policy]["metn"]) for s in fresh)
        for suite in fresh:
            metrics = json.loads((run / suite / "report" / "metrics.json").read_text(encoding="utf-8"))
            p = metrics["by_policy"][policy]
            values[f"final:{policy}:{suite}:usdrun"] = f"{p['computation']['cost_usd'] / p['recorded']:.2f}"
    values["final:cases"] = sum(int(fresh[s]["P2"]["ncases"]) for s in fresh)
    values["dev:cases"] = sum(int(record[s]["P2"]["ncases"]) for s in record)
    values["dev:recorded"] = sum(int(record[s]["all"]["recorded"]) for s in record)
    for key, value in values.items():
        lines.append(f"\\expandafter\\def\\csname res:{key}\\endcsname{{{value}}}")
    return "\n".join(lines) + "\n"


# Plain names for the charts the audience reads: no policy codes.
PLAIN = {
    "P0": "Fixed rules (baseline)",
    "P1": "Tool-calling model",
    "P2": "Our coordinator: picks checked options",
    "P3": "Check-all variant",
}


def chart(numbers: dict[str, dict[str, dict[str, object]]], source: str, stacked: bool = False) -> str:
    """The results chart in pgfplots: per suite, the share of recorded runs that met the case's
    outcome, one horizontal bar per policy, labelled with the count k of n. Plan B's own policy
    is in the brand colour and the others in grey. Side by side for the deck and the document,
    stacked with larger type for the poster."""
    parts = [
        f"% Written by make_results.py from {source}/<suite>/report/metrics.json. Do not edit.",
        "% Share of recorded runs that met the case's outcome, per policy and suite.",
        "\\documentclass[border=3pt]{standalone}",
        "\\input{planb_figstyle}",
        "\\begin{document}",
        f"\\begin{{tikzpicture}}[font=\\{'LARGE' if stacked else 'small'}]",
    ]
    order = ["P0", "P1", "P3", "P2"]
    for col, suite in enumerate(["campus", "pantry"]):
        rows = numbers[suite]
        ncases = rows["P2"]["ncases"]
        runs = rows["all"]["recorded"]
        name = "Campus event" if suite == "campus" else "Food pantry"
        title = f"{name}: {ncases} cases, {runs} runs"
        labels = col == 0 or stacked
        if col == 0:
            place = "name=campus"
        elif stacked:
            place = "name=pantry, at={(campus.south west)}, anchor=north west, yshift=-3.6cm"
        else:
            place = "name=pantry, at={(campus.south east)}, anchor=south west, xshift=1.9cm"
        opts = [
            "planb", place, "scale only axis",
            f"width={'7.2cm' if stacked else '4.7cm'}", f"height={'5.2cm' if stacked else '5.0cm'}",
            "xbar, bar width=" + ("20pt" if stacked else "17pt"),
            "xmin=0, xmax=100, xtick={0,25,50,75,100}",
            "xticklabels={0\\%,25\\%,50\\%,75\\%,100\\%}",
            "xmajorgrids, axis x line*=bottom, axis y line*=left",
            "ytick={1,2,3,4}, y dir=reverse, ymin=0.45, ymax=4.55, ytick style={draw=none}",
            "yticklabels={" + ",".join(
                ("{\\bfseries\\color{primary}" + PLAIN[p] + "}" if p == "P2" else "{" + PLAIN[p] + "}") for p in order
            ) + "}" if labels else "yticklabels={}",
            "xlabel={runs that met the expected outcome}",
            "clip=false",
        ]
        parts.append("\\begin{axis}[" + ",\n  ".join(opts) + "]")
        for i, policy in enumerate(order, start=1):
            row = rows[policy]
            share = 100 * int(row["metk"]) / int(row["metn"])
            fill = "primary" if policy == "P2" else "quiet"
            parts.append(f"\\addplot[draw=none, fill={fill}, bar shift=0pt] coordinates {{({share:.4f},{i})}};")
            weight = "\\bfseries" if policy == "P2" else ""
            parts.append(
                f"\\node[anchor=west, text=ink] at (axis cs:{share:.4f},{i}) {{{weight}\\,{row['metk']} of {row['metn']}}};"
            )
        parts.append("\\end{axis}")
        panel = "campus" if col == 0 else "pantry"
        parts.append(f"\\node[anchor=south west, text=ink] at ({panel}.outer north west) {{\\bfseries {title}}};")
    parts += ["\\end{tikzpicture}", "\\end{document}", ""]
    return "\n".join(parts)


def main() -> None:
    numbers = {suite: suite_numbers(suite) for suite in ["campus", "pantry"]}
    (HERE / "slides/figures/results_numbers.tex").write_text(macros(numbers), encoding="utf-8")
    (HERE / "slides/figures/fig_results.tex").write_text(figure(numbers), encoding="utf-8")
    (HERE / "slides/figures/fig_results_v.tex").write_text(figure(numbers, stacked=True), encoding="utf-8")
    payload = {"run_id": RUN_ID, "source": f"apps/plan_b/evaluation/results/{RUN_ID}", **numbers}
    (HERE / "documentation/results.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    sets = {
        key: {suite: suite_numbers(suite, REPO / "apps/plan_b/evaluation/results" / run) for suite in ["campus", "pantry"]}
        for key, run in V12_RUNS.items()
    }
    (HERE / "slides/figures/results_numbers_v12.tex").write_text(v12_macros(sets), encoding="utf-8")
    v12 = {
        "note": "fresh is the held-out result of policy 1.2 on C09 to C12, T05 and T06. "
        "rerun is a post-hoc diagnostic rerun after fixes, on spent cases, not a held-out result.",
        **{key: {"run_id": V12_RUNS[key], "source": f"apps/plan_b/evaluation/results/{V12_RUNS[key]}", **n} for key, n in sets.items()},
    }
    (HERE / "documentation/results_v12.json").write_text(json.dumps(v12, indent=2) + "\n", encoding="utf-8")
    # The final system's evaluation (the fresh held-out run) as the deck, poster and document
    # show it, and the earlier 12-case test in the same style for the document's full record.
    figures = HERE / "slides/figures"
    (figures / "fig_result.tex").write_text(chart(sets["fresh"], V12_RUNS["fresh"]), encoding="utf-8")
    (figures / "fig_result_v.tex").write_text(chart(sets["fresh"], V12_RUNS["fresh"], stacked=True), encoding="utf-8")
    (figures / "fig_result_record.tex").write_text(chart(numbers, RUN_ID), encoding="utf-8")
    (figures / "results_numbers_final.tex").write_text(final_macros(sets["fresh"], numbers), encoding="utf-8")
    for key, n in sets.items():
        for suite in n:
            print(key, suite, " ".join(f"{p} {n[suite][p]['met']}" for p in POLICIES), "all", n[suite]["all"])
    for suite in numbers:
        for policy in POLICIES:
            row = numbers[suite][policy]
            print(suite, policy, row["met"], "cases", row["cases"], "of", row["ncases"], "usd", row["usd"])
        print(suite, "all", numbers[suite]["all"])


if __name__ == "__main__":
    main()
