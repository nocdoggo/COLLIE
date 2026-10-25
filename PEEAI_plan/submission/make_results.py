"""Read the committed Wave 3 held-out results and write every number the three items cite.

The source is the run `wave3_heldout_20261025T1625Z` (commit c052338), one `metrics.json` per
suite, as written by `plan-b eval report`. Nothing is typed in by hand. The script writes:

- `slides/figures/results_numbers.tex`: one macro per number, read as `\\res{campus:P2:met}`;
- `slides/figures/fig_results.tex` and `fig_results_v.tex`: the results figure (runs met per
  policy, per suite), side by side for the slides and stacked for the poster;
- `documentation/results.json`: the same numbers for `build_doc.py`.

    python3 make_results.py
"""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
RUN_ID = "wave3_heldout_20261025T1625Z"
RUN = REPO / "apps/plan_b/evaluation/results" / RUN_ID
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


def suite_numbers(suite: str) -> dict[str, dict[str, object]]:
    metrics = json.loads((RUN / suite / "report" / "metrics.json").read_text(encoding="utf-8"))
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


def figure(numbers: dict[str, dict[str, dict[str, object]]], stacked: bool = False) -> str:
    """Two panels of horizontal bars, side by side or stacked: the share of recorded runs that
    met the case's outcome, per policy, labelled with the count. The stacked one is for the
    poster: larger type, closer rows and no captions (the poster's text carries them)."""
    width = 3.4 if stacked else 3.8
    labels = 4.9 if stacked else 4.1
    step = 0.85 if stacked else 1.0
    half = 0.28 if stacked else 0.32
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
            f"\\node[anchor=west, font=\\bfseries\\color{{primary}}] at ({x0 - labels:.2f},{y0 + 0.8:.2f}) {{{titles[suite]}}};"
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


def main() -> None:
    numbers = {suite: suite_numbers(suite) for suite in ["campus", "pantry"]}
    (HERE / "slides/figures/results_numbers.tex").write_text(macros(numbers), encoding="utf-8")
    (HERE / "slides/figures/fig_results.tex").write_text(figure(numbers), encoding="utf-8")
    (HERE / "slides/figures/fig_results_v.tex").write_text(figure(numbers, stacked=True), encoding="utf-8")
    payload = {"run_id": RUN_ID, "source": f"apps/plan_b/evaluation/results/{RUN_ID}", **numbers}
    (HERE / "documentation/results.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    for suite in numbers:
        for policy in POLICIES:
            row = numbers[suite][policy]
            print(suite, policy, row["met"], "cases", row["cases"], "of", row["ncases"], "usd", row["usd"])
        print(suite, "all", numbers[suite]["all"])


if __name__ == "__main__":
    main()
