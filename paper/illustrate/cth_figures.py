#!/usr/bin/env python3
"""Render the certify-then-hedge figures into ../figures/ from the committed study outputs.

  fig1_episode   one fresh-seed lead-time episode: commitment over time, and cumulative net
                 reward against arm 1, for certify-then-hedge and the registered gate
  fig2_models    the registered fresh-seed confirmation across six language models

Each renderer first writes its plotted numbers to illustrate/data/<name>.csv, then draws from
that file, so the figure can be checked against a table. Run from the repository with
``uv run python paper/illustrate/cth_figures.py [name ...]``.

Palette: the paper's two accents, validated with the dataviz palette checker (all checks pass;
protan dE 24.7, normal dE 33.6): EVIDENCE blue for certify-then-hedge, CONTROL orange for the
registered gate; immediate action is a neutral grey reference. Every series also has its own line
style or marker and a direct label, so print in black and white loses nothing.
"""

from __future__ import annotations

import csv
import gzip
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

SCRIPT_DIR = Path(__file__).resolve().parent
FIGURES_DIR = SCRIPT_DIR.parent / "figures"
DATA_DIR = SCRIPT_DIR / "data"
OUT = SCRIPT_DIR.parents[1] / "analysis" / "commitment" / "out"
SINGLE_COLUMN_IN = 3.5
DOUBLE_COLUMN_IN = 7.16
EVIDENCE = "#2a78d6"
CONTROL = "#eb6834"
INK = "#1a1a1a"
MUTED = "#5c5c5c"
RULE = "#8c8c8c"
GRID = "#e6e6e6"

ARM1, ARM8, ARM10, CTH = (
    "arm1_capped_base_stock",
    "arm8_spec_immediate",
    "arm10_spec_eprocess",
    "arm12_cth",
)
EPISODE_RUN = "fresh-gemini-3.8-flash"
EPISODE_ID = "dev/f4/s4100006/early_accurate"
MODELS = (
    ("fresh-gemini-3.8-flash", "Gemini 3.8 Flash"),
    ("fresh-grok-4.20", "Grok 4.20"),
    ("fresh-deepseek-v3", "DeepSeek-V3"),
    ("fresh-gemini-2.5-flash-lite", "Gemini 2.5 Flash-Lite"),
    ("fresh-gpt-3.5-turbo", "GPT-3.5 Turbo"),
    ("fresh-llama-3.1-8b", "Llama 3.1 8B"),
)


def _style() -> None:
    plt.rcParams.update(
        {
            "font.family": "serif",
            "font.size": 8,
            "axes.labelsize": 8,
            "axes.titlesize": 8,
            "xtick.labelsize": 7,
            "ytick.labelsize": 7,
            "axes.edgecolor": RULE,
            "axes.labelcolor": INK,
            "xtick.color": MUTED,
            "ytick.color": MUTED,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.linewidth": 0.6,
            "pdf.fonttype": 42,
        }
    )


def _signed(value: float) -> str:
    """A signed, comma-grouped integer with a true minus sign."""
    return f"{value:+,.0f}".replace("-", "\u2212")


def _save(fig, name: str) -> None:
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURES_DIR / f"{name}.pdf", bbox_inches="tight", pad_inches=0.02)
    fig.savefig(FIGURES_DIR / f"{name}.png", dpi=300, bbox_inches="tight", pad_inches=0.02)
    plt.close(fig)


def _write_csv(name: str, header: list[str], rows: list[list]) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / f"{name}.csv"
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)
    return path


def _read_csv(path: Path) -> list[dict]:
    with path.open() as handle:
        return list(csv.DictReader(handle))


# -- figure 1 -----------------------------------------------------------------


def data_fig1_episode() -> Path:
    records = {}
    with gzip.open(OUT / EPISODE_RUN / "records.jsonl.gz", "rt") as handle:
        for line in handle:
            row = json.loads(line)
            if row["episode_id"] == EPISODE_ID:
                records[row["arm_id"]] = {p["period"]: p for p in row["records"]}
    mass = {}
    with gzip.open(OUT / EPISODE_RUN / "cth_log.jsonl.gz", "rt") as handle:
        for line in handle:
            row = json.loads(line)
            if row["episode_id"] == EPISODE_ID and row["arm_id"] == CTH:
                mass[row["period"]] = row["shock_mass"]
    rows, cum = [], {CTH: 0.0, ARM10: 0.0, ARM8: 0.0}
    for t in sorted(records[ARM1]):
        base = records[ARM1][t]
        net = {
            arm: records[arm][t]["period_profit"] - records[arm][t]["period_holding"]
            for arm in (ARM1, ARM8, ARM10, CTH)
        }
        for arm in cum:
            cum[arm] += net[arm] - net[ARM1]
        rows.append(
            [
                t,
                round(mass.get(t, 0.0), 6),
                1 if records[ARM10][t]["active_spec_id"] else 0,
                1 if records[CTH][t]["triggered"] else 0,
                base["demand"],
                round(cum[CTH], 1),
                round(cum[ARM10], 1),
                round(cum[ARM8], 1),
            ]
        )
    return _write_csv(
        "fig1_episode",
        [
            "period",
            "cth_shock_mass",
            "gate_active",
            "proposal",
            "demand",
            "cum_net_cth_minus_arm1",
            "cum_net_gate_minus_arm1",
            "cum_net_immediate_minus_arm1",
        ],
        rows,
    )


def fig1_episode() -> None:
    rows = _read_csv(data_fig1_episode())
    t = [int(r["period"]) for r in rows]
    mass = [float(r["cth_shock_mass"]) for r in rows]
    gate = [int(r["gate_active"]) for r in rows]
    proposal = [int(r["period"]) for r in rows if r["proposal"] == "1"]
    onset = 14  # the episode's truth (analysis/commitment/out/<run>/truth.jsonl)
    cth = [float(r["cum_net_cth_minus_arm1"]) for r in rows]
    gate_net = [float(r["cum_net_gate_minus_arm1"]) for r in rows]

    fig, (ax_a, ax_b) = plt.subplots(
        2, 1, figsize=(SINGLE_COLUMN_IN, 2.9), sharex=True, gridspec_kw={"hspace": 0.28}
    )
    for ax in (ax_a, ax_b):
        ax.axvline(onset, color=RULE, lw=0.6, ls=":", zorder=1)
        for p in proposal:
            ax.axvline(p, color=RULE, lw=0.6, ls="-", zorder=1)
        ax.grid(axis="y", color=GRID, lw=0.5)
        ax.set_axisbelow(True)
    ax_a.step(t, gate, where="post", color=CONTROL, lw=1.2, ls="--", zorder=3)
    ax_a.plot(t, mass, color=EVIDENCE, lw=1.4, zorder=4)
    ax_a.set_ylim(-0.04, 1.08)
    ax_a.set_yticks([0, 0.5, 1])
    ax_a.set_ylabel("commitment")
    ax_a.text(t[-1] + 0.6, mass[-1], "hedge $\\Pi_t$", color=INK, va="center", fontsize=7)
    ax_a.text(t[-1] + 0.6, gate[-1] - 0.14, "gate", color=INK, va="center", fontsize=7)
    ax_a.text(onset + 0.4, 1.02, "onset", color=MUTED, fontsize=6.5, va="bottom")
    ax_a.text(
        proposal[0] - 0.4, 1.02, "proposal", color=MUTED, fontsize=6.5, va="bottom", ha="right"
    )
    ax_a.set_title("(a) commitment to the lead-time hypothesis", loc="left", color=INK)

    ax_b.axhline(0, color=RULE, lw=0.6)
    ax_b.plot(t, gate_net, color=CONTROL, lw=1.2, ls="--", zorder=3)
    ax_b.plot(t, cth, color=EVIDENCE, lw=1.4, zorder=4)
    ax_b.text(t[-1] + 0.6, cth[-1], f"hedge {_signed(cth[-1])}", color=INK, va="center", fontsize=7)
    ax_b.text(
        t[-1] + 0.6,
        gate_net[-1],
        f"gate {_signed(gate_net[-1])}",
        color=INK,
        va="center",
        fontsize=7,
    )
    ax_b.set_ylabel("net vs arm 1")
    ax_b.set_xlabel("period")
    ax_b.set_title("(b) cumulative net reward minus the baseline", loc="left", color=INK)
    ax_b.set_xlim(1, t[-1])
    _save(fig, "fig1_episode")


# -- figure 2 -----------------------------------------------------------------


def data_fig2_models() -> Path:
    confirm = json.loads((OUT / "confirm.json").read_text())["runs"]
    rows = []
    for run, label in MODELS:
        c = confirm[run]["contrasts"]
        perception = confirm[run]["perception"][ARM8]
        rows.append(
            [
                label,
                run,
                perception["family_right"],
                perception["called_shocked"],
                perception["parse_fail"],
                perception["abstain"],
                *(round(v, 1) for v in (c["arm8-arm1|net"]["mean"], *c["arm8-arm1|net"]["b"])),
                *(round(v, 1) for v in (c["arm10-arm1|net"]["mean"], *c["arm10-arm1|net"]["b"])),
                *(round(v, 1) for v in (c["cth-arm1|net"]["mean"], *c["cth-arm1|net"]["b"])),
                *(
                    round(v, 1)
                    for v in (c["uniform-arm1|net"]["mean"], *c["uniform-arm1|net"]["b"])
                ),
            ]
        )
    return _write_csv(
        "fig2_models",
        [
            "model",
            "run",
            "family_right",
            "called_shocked",
            "parse_fail",
            "abstain",
            "immediate_mean",
            "immediate_lo",
            "immediate_hi",
            "gate_mean",
            "gate_lo",
            "gate_hi",
            "cth_mean",
            "cth_lo",
            "cth_hi",
            "uniform_mean",
            "uniform_lo",
            "uniform_hi",
        ],
        rows,
    )


def fig2_models() -> None:
    rows = _read_csv(data_fig2_models())
    labels = [r["model"] for r in rows]
    y = list(range(len(rows)))[::-1]
    fig, axes = plt.subplots(
        1,
        3,
        figsize=(DOUBLE_COLUMN_IN, 1.95),
        sharey=True,
        gridspec_kw={"width_ratios": [0.9, 1.2, 1.6], "wspace": 0.22},
    )
    ax_p, ax_i, ax_c = axes
    for ax in axes:
        ax.grid(axis="x", color=GRID, lw=0.5)
        ax.set_axisbelow(True)
        ax.tick_params(axis="y", length=0)
    share = [100.0 * int(r["family_right"]) / int(r["called_shocked"]) for r in rows]
    ax_p.barh(y, share, height=0.55, color=RULE, edgecolor="white", linewidth=0.8)
    for yy, s in zip(y, share, strict=True):
        ax_p.text(s + 1.5, yy, f"{s:.0f}%", va="center", fontsize=6.5, color=INK)
    ax_p.set_xlim(0, 75)
    ax_p.set_yticks(y, labels)
    ax_p.set_xlabel("% right family and direction")
    ax_p.set_title("(a) perception", loc="left", pad=20)

    imm = [float(r["immediate_mean"]) for r in rows]
    lo = [float(r["immediate_lo"]) for r in rows]
    hi = [float(r["immediate_hi"]) for r in rows]
    ax_i.hlines(y, lo, hi, color=MUTED, lw=1.0)
    ax_i.plot(imm, y, "s", color=MUTED, ms=4)
    ax_i.axvline(0, color=RULE, lw=0.6)
    ax_i.set_xlim(-4200, 300)
    ax_i.set_xlabel("net vs arm 1, per episode")
    ax_i.set_title("(b) acting at once (arm 8)", loc="left", pad=20)

    # The content-free control calls no model, so it is one value for every row: a band.
    u_mean, u_lo, u_hi = (float(rows[0][f"uniform_{k}"]) for k in ("mean", "lo", "hi"))
    ax_c.axvspan(u_lo, u_hi, color=GRID, alpha=0.9, lw=0, zorder=0)
    ax_c.axvline(u_mean, color=MUTED, lw=0.8, ls=(0, (3, 2)), zorder=1)
    off = 0.14
    for key, color, marker, dy, name in (
        ("gate", CONTROL, "D", -off, "gate (arm 10)"),
        ("cth", EVIDENCE, "o", off, "certify-then-hedge"),
    ):
        mean = [float(r[f"{key}_mean"]) for r in rows]
        lo = [float(r[f"{key}_lo"]) for r in rows]
        hi = [float(r[f"{key}_hi"]) for r in rows]
        yy = [v + dy for v in y]
        ax_c.hlines(yy, lo, hi, color=color, lw=1.2)
        ax_c.plot(mean, yy, marker, color=color, ms=4.5, mec="white", mew=0.6, label=name)
    ax_c.axvline(0, color=RULE, lw=0.6)
    ax_c.set_xlabel("net vs arm 1, per episode")
    ax_c.set_title("(c) verified commitment", loc="left", pad=20)
    handles, names = ax_c.get_legend_handles_labels()
    handles.append(Patch(facecolor=GRID, edgecolor=MUTED, linestyle=(0, (3, 2)), lw=0.8))
    names.append("content-free")
    ax_c.legend(
        handles,
        names,
        loc="lower left",
        bbox_to_anchor=(0.0, 1.0),
        ncol=3,
        frameon=False,
        fontsize=6.5,
        handletextpad=0.4,
        handlelength=1.4,
        columnspacing=1.0,
        borderaxespad=0.0,
    )
    _save(fig, "fig2_models")


FIGURES = {"fig1_episode": fig1_episode, "fig2_models": fig2_models}


def main(argv: list[str]) -> int:
    _style()
    names = argv or list(FIGURES)
    for name in names:
        FIGURES[name]()
        print(f"rendered {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
