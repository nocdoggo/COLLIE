#!/usr/bin/env python3
"""Render the certify-then-hedge figures into ../figures/ from the committed study outputs.

  fig1_overview  the gate and certify-then-hedge on one shared input, each lane ending in one
                 fresh-seed lead-time episode (drawn by overview.py from data/fig1_episode.csv)
  fig2_method    how certify-then-hedge turns a ShockSpec into an order (drawn by method.py;
                 schematic curves, the registered constants)
  fig3_models    the registered fresh-seed confirmation across six language models

Each renderer first writes its plotted numbers to illustrate/data/<name>.csv, then draws from
that file, so the figure can be checked against a table. Run from the repository with
``uv run python paper/illustrate/cth_figures.py [name ...]``.

Style, palette and fonts come from style.py, shared by every figure: blue for certify-then-hedge,
orange for the registered gate, grey for the operations research baseline. Every series also has
its own line style or marker and a direct label, so print in black and white loses nothing.
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
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
FIGURES_DIR = SCRIPT_DIR.parent / "figures"
DATA_DIR = SCRIPT_DIR / "data"
OUT = SCRIPT_DIR.parents[1] / "analysis" / "commitment" / "out"

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
    with (OUT / EPISODE_RUN / "truth.jsonl").open() as handle:
        truth = next(
            json.loads(line) for line in handle if json.loads(line)["episode_id"] == EPISODE_ID
        )
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
                truth["onset_period"],
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
            "onset",
        ],
        rows,
    )


def _replay_lead_offset() -> tuple[dict[int, dict[int, float]], float, list[int], int]:
    """Replay the frozen method arm on the Fig. 1 episode with its logged answer and record the
    lead-time hypothesis's posterior over the offset per decision. Returns that posterior, the
    replayed total reward, the realised lead times and the promised lead time. The arm does not log the posterior, so
    the replay must reproduce the recorded reward exactly (checked by the caller)."""
    import tempfile
    from collections import defaultdict

    from analysis.commitment.cth import CertifyThenHedgeArm
    from analysis.commitment.episodes import build_layout, layout_alerts
    from collie.contracts import AnalysisClass
    from collie.sim.runner import EpisodeRunner
    from collie.trigger.demo import build_wrapped

    replay = {}
    with (OUT / EPISODE_RUN / "proposals.jsonl").open() as handle:
        for line in handle:
            row = json.loads(line)
            if row["episode_id"] == EPISODE_ID and row["arm_id"] == CTH:
                replay[row["period"]] = row["payload"] if row["parsed"] else None
    posterior: dict[int, dict[int, float]] = {}

    class Recording(CertifyThenHedgeArm):
        def _lt_posterior(self, h, t, lead, it_now):
            out = super()._lt_posterior(h, t, lead, it_now)
            mass: dict[int, float] = defaultdict(float)
            for p, delta, _start in out:
                mass[delta] += p
            posterior[t] = dict(mass)
            return out

    with tempfile.TemporaryDirectory() as tmp:
        layout = build_layout(Path(tmp), 8, profit=4.0)
        alerts = layout_alerts(layout)
        instance, seed = next(
            (i, s) for i, s in layout.instances if i.spec.episode_id == EPISODE_ID
        )
        spec = instance.spec
        arm = Recording(
            lam=0.25,
            promised_lead_time=spec.promised_lead_time,
            horizon=spec.horizon,
            train_demand=spec.train_demand,
            order_cap=spec.order_cap,
            trigger=build_wrapped("alert_or_detector", spec.horizon, 0, seed),
            replay=replay,
            arm_id=CTH,
        )
        channel = alerts[EPISODE_ID]
        result = (
            EpisodeRunner(
                instance,
                alerts=channel.alerts,
                template_ids=channel.template_ids,
                analysis_class=AnalysisClass.EXPLORATORY,
                check_controller_isolation=True,
            )
            .run(arm)
            .result
        )
        leads = [float(x) for x in instance.supply.lead_times]
        assert all(x.is_integer() for x in leads)
        leads = [int(x) for x in leads]
        return posterior, float(result.total_reward), leads, spec.promised_lead_time


def data_fig1_meta() -> Path:
    """Everything Fig. 1 shows besides the plotted series, read from the run's files and checked:
    the alert, the model's ShockSpec, the true offset, the gate's compiled offset and switch
    period, and the method's posterior over the offset (by replay)."""
    run = OUT / EPISODE_RUN
    with (run / "alerts.jsonl").open() as handle:
        alert = next(r for r in map(json.loads, handle) if r["episode_id"] == EPISODE_ID)
    payloads = {}
    with (run / "proposals.jsonl").open() as handle:
        for r in map(json.loads, handle):
            if r["episode_id"] == EPISODE_ID and r["period"] == alert["period"] and r["parsed"]:
                payloads[r["arm_id"]] = r["payload"]
    assert {ARM8, ARM10, CTH} <= payloads.keys()
    assert payloads[ARM8] == payloads[ARM10] == payloads[CTH], "arms saw different answers"
    with (run / "truth.jsonl").open() as handle:
        truth = next(r for r in map(json.loads, handle) if r["episode_id"] == EPISODE_ID)
    records, totals = {}, {}
    with gzip.open(run / "records.jsonl.gz", "rt") as handle:
        for line in handle:
            row = json.loads(line)
            if row["episode_id"] == EPISODE_ID:
                records[row["arm_id"]] = row["records"]
                totals[row["arm_id"]] = float(row["total_reward"])
    gate_on = next(p for p in records[ARM10] if p["active_spec_id"])
    posterior, replayed, leads, promised = _replay_lead_offset()
    assert replayed == totals[CTH], f"replay {replayed} != recorded {totals[CTH]}"
    onset = truth["onset_period"]
    true_offset = {lead - promised for lead in leads[onset - 1 :]}
    assert len(true_offset) == 1 and {lead - promised for lead in leads[: onset - 1]} == {0}
    final = posterior[max(posterior)]
    meta = {
        "episode_id": EPISODE_ID,
        "model_id": gate_on["active_spec"]["model_id"],
        "alert_period": alert["period"],
        "alert_text": alert["text"],
        "shockspec": payloads[CTH],
        "truth": {
            "family": truth["family"],
            "onset_period": onset,
            "offset_periods": true_offset.pop(),
        },
        "gate": {
            "on_period": gate_on["period"],
            "compiled_offset_periods": gate_on["control_config"]["l_eff"] - promised,
        },
        "hedge": {
            "offset_posterior": {
                str(t): {str(d): round(p, 4) for d, p in sorted(m.items())}
                for t, m in sorted(posterior.items())
            },
            "offset_map_final": max(final, key=final.get),
            "replayed_total_reward": replayed,
        },
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / "fig1_episode_meta.json"
    path.write_text(json.dumps(meta, indent=1, ensure_ascii=False) + "\n")
    return path


def fig1_overview() -> None:
    import overview

    data_fig1_episode()
    data_fig1_meta()
    overview.render(FIGURES_DIR)


# -- figure 2 -----------------------------------------------------------------


def data_fig3_models() -> Path:
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
                *(round(v, 3) for v in (c["arm8-arm1|net"]["mean"], *c["arm8-arm1|net"]["b"])),
                *(round(v, 3) for v in (c["arm10-arm1|net"]["mean"], *c["arm10-arm1|net"]["b"])),
                *(round(v, 3) for v in (c["cth-arm1|net"]["mean"], *c["cth-arm1|net"]["b"])),
                *(
                    round(v, 3)
                    for v in (c["uniform-arm1|net"]["mean"], *c["uniform-arm1|net"]["b"])
                ),
            ]
        )
    return _write_csv(
        "fig3_models",
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


def fig3_models() -> None:
    import style as S

    rows = _read_csv(data_fig3_models())
    labels = [r["model"] for r in rows]
    primary = {"Gemini 3.8 Flash", "Grok 4.20"}
    n = len(rows)
    y = list(range(n))[::-1]
    S.use_style(font_size=7.5)
    W, H = S.TEXT_WIDTH, 2.12
    fig = plt.figure(figsize=(W, H))
    S.rounded_frame(fig, pad=0.004)
    # Panel geometry in figure fractions: labels | perception | at once | verified commitment.
    left, bottom, top = 0.145, 0.205, 0.735
    widths, gaps = (0.17, 0.215, 0.36), (0.03, 0.035)
    xs = [left, left + widths[0] + gaps[0], left + widths[0] + gaps[0] + widths[1] + gaps[1]]
    axes = [fig.add_axes([x, bottom, w, top - bottom]) for x, w in zip(xs, widths, strict=True)]
    ax_p, ax_i, ax_c = axes
    for ax in axes:
        ax.set_ylim(-0.6, n - 0.4)
        ax.tick_params(axis="y", length=0)
        ax.set_yticks([])
        ax.spines["left"].set_visible(False)
        for k in range(n):
            if k % 2 == 0:
                ax.axhspan(y[k] - 0.5, y[k] + 0.5, color=S.tint(S.NEUTRAL, 0.09), lw=0, zorder=0)
        ax.grid(axis="x", color=S.GRIDLINE, lw=0.6, zorder=0.5)
        ax.set_axisbelow(True)
    # Model names in the left margin, the primaries in bold.
    for yy, name in zip(y, labels, strict=True):
        ax_p.text(
            -0.04,
            yy,
            name,
            transform=ax_p.get_yaxis_transform(),
            ha="right",
            va="center",
            fontsize=7.5,
            color=S.INK,
            fontweight="bold" if name in primary else "normal",
        )

    share = [100.0 * int(r["family_right"]) / int(r["called_shocked"]) for r in rows]
    ax_p.barh(
        y,
        share,
        height=0.56,
        color=S.tint(S.NEUTRAL, 0.35),
        edgecolor=S.NEUTRAL,
        linewidth=0.6,
        zorder=2,
    )
    for yy, v in zip(y, share, strict=True):
        ax_p.text(v + 1.8, yy, f"{v:.0f}%", va="center", fontsize=6.8, color=S.INK_2)
    ax_p.set_xlim(0, 78)
    ax_p.set_xlabel("right family and direction (%)")

    imm = [float(r["immediate_mean"]) for r in rows]
    lo = [float(r["immediate_lo"]) for r in rows]
    hi = [float(r["immediate_hi"]) for r in rows]
    ax_i.hlines(y, lo, hi, color=S.IMMEDIATE, lw=1.1, zorder=3)
    ax_i.plot(imm, y, "s", color=S.IMMEDIATE, ms=4.2, mec="white", mew=0.6, zorder=4)
    ax_i.axvline(0, color=S.INK_2, lw=0.7, zorder=2)
    ax_i.set_xlim(-4200, 400)
    ax_i.set_xticks(
        [-4000, -3000, -2000, -1000, 0],
        ["\u22124,000", "\u22123,000", "\u22122,000", "\u22121,000", "0"],
    )
    ax_i.set_xlabel("net vs arm 1, per episode")

    # The content-free control calls no model, so it is one value for every row: a band.
    u_mean, u_lo, u_hi = (float(rows[0][f"uniform_{k}"]) for k in ("mean", "lo", "hi"))
    ax_c.axvspan(
        u_lo,
        u_hi,
        fc=S.tint(S.NEUTRAL, 0.16),
        ec=S.tint(S.NEUTRAL, 0.55),
        hatch="////",
        lw=0.0,
        zorder=1,
    )
    ax_c.axvline(u_mean, color=S.NEUTRAL, lw=0.9, ls=(0, (3, 2)), zorder=1.5)
    off = 0.15
    for key, color, marker, dy in (("gate", S.GATE, "D", -off), ("cth", S.HEDGE, "o", off)):
        mean = [float(r[f"{key}_mean"]) for r in rows]
        lo = [float(r[f"{key}_lo"]) for r in rows]
        hi = [float(r[f"{key}_hi"]) for r in rows]
        yy = [v + dy for v in y]
        ax_c.hlines(yy, lo, hi, color=color, lw=1.3, zorder=3)
        ax_c.plot(mean, yy, marker, color=color, ms=4.6, mec="white", mew=0.7, zorder=4)
    ax_c.axvline(0, color=S.INK_2, lw=0.7, zorder=2)
    ax_c.set_xlim(-420, 420)
    ax_c.set_xticks([-400, -200, 0, 200, 400], ["\u2212400", "\u2212200", "0", "200", "400"])
    ax_c.set_xlabel("net vs arm 1, per episode")

    # Panel tags on tinted labels, and a legend row of chips over panel (c).
    tag_y = top + 0.04
    for ax, text, color in (
        (ax_p, "(a) Perception", S.NEUTRAL),
        (ax_i, "(b) Acting at once (arm 8)", S.IMMEDIATE),
        (ax_c, "(c) Verified commitment", S.HEDGE),
    ):
        pos = ax.get_position()
        fig.text(
            pos.x0 + pos.width / 2,
            tag_y,
            text,
            fontsize=7.5,
            fontweight="bold",
            color=S.INK,
            ha="center",
            va="bottom",
            bbox={
                "boxstyle": "round,pad=0.28,rounding_size=0.35",
                "fc": S.tint(color, 0.2),
                "ec": S.tint(color, 0.65),
                "lw": 0.6,
            },
        )
    ly = 0.885
    handles = [
        Line2D([], [], color=S.GATE, marker="D", ms=4.2, mec="white", lw=1.2),
        Line2D([], [], color=S.HEDGE, marker="o", ms=4.4, mec="white", lw=1.2),
        Patch(fc=S.tint(S.NEUTRAL, 0.16), ec=S.tint(S.NEUTRAL, 0.55), hatch="////", lw=0.0),
    ]
    fig.legend(
        handles,
        ["gate (arm 10)", "certify-then-hedge", "content-free control (no model call)"],
        loc="lower right",
        bbox_to_anchor=(xs[2] + widths[2], ly),
        ncol=3,
        frameon=False,
        fontsize=6.8,
        handletextpad=0.4,
        handlelength=1.5,
        columnspacing=1.0,
        borderaxespad=0.0,
    )
    S.save(fig, "fig3_models")


def fig2_method() -> None:
    import method

    method.render(FIGURES_DIR)


FIGURES = {"fig1_overview": fig1_overview, "fig2_method": fig2_method, "fig3_models": fig3_models}


def main(argv: list[str]) -> int:
    names = argv or list(FIGURES)
    for name in names:
        FIGURES[name]()
        print(f"rendered {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
