#!/usr/bin/env python3
"""Figure 1 (fig:overview): the registered gate and certify-then-hedge on one shared input.

(a) The shared input: the operational alert of one fresh-seed lead-time episode
    (dev/f4/s4100006/early_accurate, Gemini 3.8 Flash as the proposer), six of the nine fields
    of the ShockSpec the model returned for it, and the hidden truth.
(b) The registered gate (arm 10) tests the stated hypothesis alone, waits for
    E_{j,t} >= 1/alpha_j, then switches all at once to the configuration compiled from the
    stated magnitude (medium, two extra periods).
(c) Certify-then-hedge keeps the fixed set H, lets the answer only reweight it
    (lambda = 0.25) and date the named hypothesis, runs one e-process per hypothesis, sizes
    the shock from the data and orders the p/(p+h) quantile of the mixture; its exposure
    bound, with the premise and how far the arm as run is from it, sits under the lane.

Both lanes end in the same plot of that arm on the example episode, on shared scales:
commitment on top (gate on or off; the hedge's shock mass Pi_t), cumulative net reward
against arm 1 below. The plotted numbers come from data/fig1_episode.csv and every other fact
(alert, ShockSpec, true and compiled offsets, the method's offset estimate by replay) from
data/fig1_episode_meta.json; cth_figures.py writes both from the study outputs, and the render
asserts what it shows against them.

Usage  uv run python paper/illustrate/overview.py   (writes ../figures/fig1_overview.pdf/.png)
"""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import style as S  # noqa: E402
from matplotlib.colors import to_rgb  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle  # noqa: E402
from matplotlib.text import Text  # noqa: E402

NAME = "fig1_overview"
DATA = SCRIPT_DIR / "data" / "fig1_episode.csv"
META = SCRIPT_DIR / "data" / "fig1_episode_meta.json"

FS = 7.0  # body text (pt)
FS_S = 6.5  # smallest text (pt)
FS_T = 7.5  # card titles (pt)
PT = S.PT
MONO = "Ubuntu Mono"  # narrow TrueType monospace for the ShockSpec fields

W, H = S.TEXT_WIDTH, 2.66
FRAME_PAD = 0.004
X0, X1 = 0.085, W - 0.085
Y0, Y1 = 0.075, H - 0.075
STRIP = 0.155  # card header strip (in)

LAMBDA = 0.25
H_SET = ["demand up", "demand down", "lead-time shift", "upward pulse"]
NAMED = "lead-time shift"
MODEL_NAMES = {"gemini-3.8-flash": "Gemini 3.8 Flash"}
SHOWN_FIELDS = (  # six of the nine ShockSpec fields; the caption says so
    "shock_family",
    "target_stream",
    "direction",
    "magnitude_bin",
    "onset_window",
    "persistence",
)

ITAL = {"color": S.INK_2, "style": "italic"}
CARDS = []  # (name, x0, y0, x1, y1) of every box that holds text, for the border check
PLOTS = {}  # arm -> (commitment axes, net axes)


def minus(s: str) -> str:
    return s.replace("-", "−")


def baseline(yc: float, fs: float = FS) -> float:
    """Baseline that visually centres one line of text on height yc."""
    return yc - 0.3 * fs * PT


def spec_rows(meta: dict) -> list[tuple[str, str]]:
    def fmt(v) -> str:
        return "[" + ", ".join(str(x) for x in v) + "]" if isinstance(v, list) else str(v)

    return [(k, fmt(meta["shockspec"][k])) for k in SHOWN_FIELDS]


def periods(n: int) -> str:
    return f"+{n} period" + ("" if n == 1 else "s")


def load_episode() -> dict:
    with DATA.open() as handle:
        rows = list(csv.DictReader(handle))
    ep = {
        "t": np.array([int(r["period"]) for r in rows]),
        "mass": np.array([float(r["cth_shock_mass"]) for r in rows]),
        "gate": np.array([int(r["gate_active"]) for r in rows]),
        "cth": np.array([float(r["cum_net_cth_minus_arm1"]) for r in rows]),
        "gnet": np.array([float(r["cum_net_gate_minus_arm1"]) for r in rows]),
        "proposal": [int(r["period"]) for r in rows if r["proposal"] == "1"],
        "onset": int(rows[0]["onset"]),
    }
    ep["gate_on"] = int(ep["t"][np.argmax(ep["gate"] > 0)])
    meta = json.loads(META.read_text())
    assert (
        meta["alert_period"] == ep["proposal"][0] and meta["truth"]["onset_period"] == ep["onset"]
    )
    assert meta["gate"]["on_period"] == ep["gate_on"]
    ep["meta"] = meta
    ep["true_offset"] = int(meta["truth"]["offset_periods"])
    ep["gate_offset"] = int(meta["gate"]["compiled_offset_periods"])
    ep["hedge_offset"] = int(meta["hedge"]["offset_map_final"])
    return ep


class Canvas(S.Canvas):
    """House canvas plus a few glyphs and a word wrapper."""

    def wrap(self, text, fs, width, **kw):
        lines, cur = [], ""
        for word in text.split():
            trial = (cur + " " + word).strip()
            if cur and self.width(trial, fs=fs, **kw) > width:
                lines.append(cur)
                cur = word
            else:
                cur = trial
        lines.append(cur)
        return lines

    def arrow(self, a, b, color, lw=1.0, head=(3.6, 2.2), z=4):
        self.ax.add_patch(
            FancyArrowPatch(
                a,
                b,
                arrowstyle=f"-|>,head_length={head[0]},head_width={head[1]}",
                mutation_scale=1,
                lw=lw,
                color=color,
                zorder=z,
                shrinkA=0,
                shrinkB=0,
            )
        )

    def step_glyph(self, x, y, w, h, color):
        """All-or-nothing switch: flat, then a jump to full."""
        xm = x + 0.55 * w
        self.polygon([(xm, y), (xm, y + h), (x + w, y + h), (x + w, y)], S.tint(color, 0.22))
        self.line([x, xm, xm, x + w], [y, y, y + h, y + h], color=color, lw=1.1, zorder=5)

    def ramp_glyph(self, x, y, w, h, color):
        """Graded commitment: a smooth rise."""
        u = np.linspace(0, 1, 40)
        v = 1 / (1 + np.exp(-10 * (u - 0.5)))
        v = (v - v[0]) / (v[-1] - v[0])
        xs, ys = x + w * u, y + h * v
        self.polygon([*zip(xs, ys, strict=True), (x + w, y), (x, y)], S.tint(color, 0.22))
        self.line(xs, ys, color=color, lw=1.1, zorder=5)

    def shield(self, x, y, s, color):
        """Plain shield centred at (x, y), height s."""
        w = 0.8 * s
        pts = [
            (x - w / 2, y + 0.42 * s),
            (x, y + 0.5 * s),
            (x + w / 2, y + 0.42 * s),
            (x + w / 2, y + 0.02 * s),
            (x, y - 0.5 * s),
            (x - w / 2, y + 0.02 * s),
        ]
        self.polygon(pts, color, z=6)

    def swatch(self, x, yc, color, s=0.06):
        self.ax.add_patch(
            FancyBboxPatch(
                (x, yc - s / 2),
                s,
                s,
                boxstyle="round,pad=0,rounding_size=0.012",
                fc=color,
                ec="none",
                zorder=5,
            )
        )

    def cell(self, x, y, w, h, accent, name="cell"):
        CARDS.append((name, x, y, x + w, y + h))
        return self.box(x, y, w, h, fc=S.SURFACE, ec=S.tint(accent, 0.45), lw=0.6, r=0.035, z=3)

    def small_caps(self, x, y, word, fs, small, **kw):
        """Small capitals: capitals at ``fs``, the rest as capitals at ``small``."""
        for run in re.findall(r"[A-Z]+|[^A-Z]+", word):
            size = fs if run[0].isupper() else small
            t = self.text(x, y, run.upper(), fs=size, **kw)
            x = self.extent(t)[2] + 0.004
        return x


def card(c: Canvas, x, y, w, h, accent, title, subtitle=None, body=S.SURFACE):
    """Card with a tinted header strip; the title (and subtitle) centred on the strip."""
    base = c.box(x, y, w, h, fc=body, ec="none", r=0.05, z=2)
    band = Rectangle((x, y + h - STRIP), w, STRIP, fc=S.tint(accent, 0.28), ec="none", zorder=2.1)
    c.ax.add_patch(band)
    band.set_clip_path(base)
    c.line([x, x + w], [y + h - STRIP] * 2, color=accent, lw=0.5, zorder=2.2)
    c.box(x, y, w, h, fc="none", ec=accent, lw=0.85, r=0.05, z=2.6)
    gap = 0.1
    wt = c.width(title, fs=FS_T, fontweight="bold")
    ws = c.width(subtitle, fs=FS_S, style="italic") if subtitle else 0.0
    total = wt + (gap + ws if subtitle else 0.0)
    xt = x + w / 2 - total / 2
    c.text(xt, baseline(y + h - STRIP / 2, FS_T), title, fs=FS_T, fontweight="bold")
    if subtitle:
        c.text(xt + wt + gap, baseline(y + h - STRIP / 2, FS_S), subtitle, fs=FS_S, **ITAL)
    CARDS.append((title, x, y, x + w, y + h))
    return base


def lines_in(c: Canvas, x, y_first, rows, pitch=0.112):
    """Stacked lines (text, fs, kwargs) from the baseline y_first down; returns artists."""
    out, y = [], y_first
    for s, fs, kw in rows:
        out.append(c.text(x, y, s, fs=fs, **kw))
        y -= pitch
    return out


# -- (a) the shared input --------------------------------------------------------------------


def input_card(c: Canvas, x0, x1, ep):
    """The alert, the model's ShockSpec, and the hidden truth. Returns the ShockSpec's centre."""
    w = x1 - x0
    card(c, x0, Y0, w, Y1 - Y0, S.NEUTRAL, f"(a) Alert at period {ep['proposal'][0]}")
    pad = 0.065
    alert = ep["meta"]["alert_text"]
    lines = c.wrap("“" + alert + "”", FS, w - 2 * pad - 0.05, style="italic")
    ep["alert_lines"] = lines
    pitch = 0.108
    y = Y1 - STRIP - 0.13
    y_top = y + 0.08
    for ln in lines:
        c.text(x0 + pad + 0.05, y, ln, fs=FS, style="italic")
        y -= pitch
    y_bot = y + pitch - 0.03
    c.ax.add_patch(
        FancyBboxPatch(
            (x0 + pad, y_bot),
            0.02,
            y_top - y_bot,
            boxstyle="round,pad=0,rounding_size=0.01",
            fc=S.tint(S.NEUTRAL, 0.5),
            ec="none",
            zorder=4,
        )
    )

    # The hidden truth at the bottom of the card.
    sx0, sw = x0 + pad - 0.015, w - 2 * pad + 0.03
    th = 0.27
    ty0 = Y0 + 0.07
    c.box(
        sx0,
        ty0,
        sw,
        th,
        fc=S.tint(S.NEUTRAL, 0.05),
        ec=S.MUTED,
        lw=0.6,
        ls=(0, (2, 1.5)),
        r=0.03,
        z=3,
    )
    CARDS.append(("truth", sx0, ty0, sx0 + sw, ty0 + th))
    c.text(sx0 + sw / 2, ty0 + th - 0.105, "the hidden truth", fs=FS_S, ha="center", **ITAL)
    c.text(
        sx0 + sw / 2,
        ty0 + 0.07,
        f"lead time {periods(ep['true_offset'])}, from period {ep['onset']}",
        fs=FS_S,
        ha="center",
        color=S.INK,
    )

    # What the model never writes, above the truth.
    fy = ty0 + th + 0.08
    c.text(x0 + w / 2, fy + 0.11, "the model never writes", fs=FS_S, ha="center", **ITAL)
    c.text(x0 + w / 2, fy, "an order or a threshold", fs=FS_S, ha="center", **ITAL)

    # The ShockSpec between the quote and what the model cannot write.
    row_h = 0.114
    sub_strip = 0.165
    rows = spec_rows(ep["meta"])
    sub_h = sub_strip + len(rows) * row_h + 0.02
    free0, free1 = fy + 0.2, y_bot
    sy0 = free0 + (free1 - free0 - sub_h) / 2
    sy1 = sy0 + sub_h
    base = c.box(sx0, sy0, sw, sub_h, fc=S.SURFACE, ec="none", r=0.035, z=3)
    band = Rectangle(
        (sx0, sy1 - sub_strip), sw, sub_strip, fc=S.tint(S.NEUTRAL, 0.2), ec="none", zorder=3.1
    )
    c.ax.add_patch(band)
    band.set_clip_path(base)
    c.line([sx0, sx0 + sw], [sy1 - sub_strip] * 2, color=S.tint(S.NEUTRAL, 0.6), lw=0.5, zorder=3.2)
    c.box(sx0, sy0, sw, sub_h, fc="none", ec=S.tint(S.NEUTRAL, 0.7), lw=0.6, r=0.035, z=3.6)
    CARDS.append(("ShockSpec", sx0, sy0, sx0 + sw, sy1))
    yb = baseline(sy1 - sub_strip / 2, FS_S)
    c.small_caps(sx0 + 0.05, yb, "ShockSpec", 7.5, FS_S)
    model = MODEL_NAMES[ep["meta"]["model_id"]]
    c.text(sx0 + sw - 0.05, yb, model, fs=FS_S, ha="right", color=S.INK_2)
    ry = sy1 - sub_strip - 0.01
    for i, (key, val) in enumerate(rows):
        yc = ry - (i + 0.5) * row_h
        if i % 2 == 1:
            zebra = Rectangle(
                (sx0, yc - row_h / 2), sw, row_h, fc=S.tint(S.NEUTRAL, 0.09), ec="none", zorder=3.2
            )
            c.ax.add_patch(zebra)
            zebra.set_clip_path(base)
        c.text(sx0 + 0.05, baseline(yc, FS_S), key, fs=FS_S, color=S.INK_2)
        col = (
            S.HYP[NAMED] if key == "shock_family" else (S.GATE if key == "magnitude_bin" else S.INK)
        )
        c.text(
            sx0 + sw - 0.05,
            baseline(yc, FS_S),
            val,
            fs=FS_S,
            ha="right",
            color=col,
            family=MONO,
            fontweight="bold" if col != S.INK else "normal",
        )
    return (sy0 + sy1) / 2


# -- the example episode ---------------------------------------------------------------------


def mini_plot(c: Canvas, x, y, w, h, ep, arm):
    """Commitment strip on top, cumulative net against arm 1 below (inch rectangle)."""
    fig = c.fig
    color = S.GATE if arm == "gate" else S.HEDGE
    h_c = 0.24 * h
    gap = 0.07
    h_n = h - h_c - gap
    ax_c = fig.add_axes([x / W, (y + h_n + gap) / H, w / W, h_c / H])
    ax_n = fig.add_axes([x / W, y / H, w / W, h_n / H])
    t = ep["t"]
    commit = ep["gate"].astype(float) if arm == "gate" else ep["mass"]
    net = ep["gnet"] if arm == "gate" else ep["cth"]
    for ax in (ax_c, ax_n):
        ax.set_xlim(10, t[-1])
        ax.set_facecolor("none")
        for sp in ("left", "bottom"):
            ax.spines[sp].set_color(S.BASELINE)
            ax.spines[sp].set_linewidth(0.6)
        ax.axvline(ep["proposal"][0], color=S.MUTED, lw=0.6, zorder=1)
        ax.axvline(ep["onset"], color=S.MUTED, lw=0.6, ls=(0, (1, 1.5)), zorder=1)
        ax.tick_params(length=2, width=0.5, pad=1.5, labelsize=FS_S)
    if arm == "gate":
        ax_c.fill_between(t, 0, commit, step="post", color=S.tint(color, 0.25), lw=0)
        ax_c.step(t, commit, where="post", color=color, lw=1.1)
    else:
        ax_c.fill_between(t, 0, commit, color=S.tint(color, 0.18), lw=0)
        ax_c.plot(t, commit, color=color, lw=1.1)
    ax_c.set_ylim(0, 1.05)
    ax_c.set_yticks([1])
    ax_c.set_xticks([])
    ax_c.spines["bottom"].set_visible(False)
    ax_n.axhline(0, color=S.BASE, lw=0.6, zorder=2)
    ax_n.plot(t, net, color=color, lw=1.25, ls=(0, (3.5, 1.5)) if arm == "gate" else "-", zorder=4)
    ax_n.set_ylim(-2600, 1000)
    ax_n.set_yticks([0, -2000])
    ax_n.set_yticklabels(["0", minus("-2,000")])
    ticks = (
        [ep["proposal"][0], ep["gate_on"], t[-1]] if arm == "gate" else [ep["proposal"][0], t[-1]]
    )
    ax_n.set_xticks(ticks)
    ax_n.text(15.5, -1750, "cum. net vs arm 1", fontsize=FS_S, va="center", ha="left", **ITAL)
    ax_n.text(15.5, -620, "arm 1", fontsize=FS_S, va="center", ha="left", color=S.INK_2)
    ax_n.annotate(
        S.signed(net[-1]),
        (t[-1], net[-1]),
        xytext=(3, 0),
        textcoords="offset points",
        va="center",
        ha="left",
        fontsize=FS_T,
        fontweight="bold",
        color=color,
        annotation_clip=False,
    )
    lab = "gate on" if arm == "gate" else r"$\Pi_t$"
    ax_c.annotate(
        lab,
        (t[-1], 1.0),
        xytext=(3, 0),
        textcoords="offset points",
        va="center",
        ha="left",
        fontsize=FS_S,
        color=color,
        annotation_clip=False,
    )
    ax_n.annotate(
        "period",
        (t[-1], -2600),
        xytext=(8, -1.5 - FS_S),
        textcoords="offset points",
        va="baseline",
        ha="left",
        fontsize=FS_S,
        annotation_clip=False,
        **ITAL,
    )
    return ax_c, ax_n


# -- (b) and (c) the two lanes ---------------------------------------------------------------


def prior_column(c: Canvas, xa, wa, y_top):
    """The fixed set with its prior weights drawn to scale on a unit track."""
    track_x0 = xa + 0.8
    track_w = wa - 0.8 - 0.06
    c.text(xa + 0.06, y_top, r"fixed $\mathcal{H}$", fs=FS_S, **ITAL)
    c.text(track_x0 + track_w, y_top, r"prior $w_{jk}$", fs=FS_S, ha="right", **ITAL)
    w_small = LAMBDA / len(H_SET)
    deep = tuple(
        0.72 * a + 0.28 * b for a, b in zip(to_rgb(S.HYP[NAMED]), to_rgb(S.INK), strict=True)
    )
    row_h = 0.095
    y_rows = y_top - 0.05
    for i, k in enumerate(H_SET):
        yc = y_rows - (i + 0.5) * row_h
        if i % 2 == 0:
            c.ax.add_patch(
                Rectangle(
                    (xa + 0.015, yc - row_h / 2),
                    wa - 0.03,
                    row_h,
                    fc=S.tint(S.HEDGE, 0.07),
                    ec="none",
                    zorder=3.2,
                )
            )
        c.swatch(xa + 0.06, yc, S.HYP[k])
        c.text(
            xa + 0.15, baseline(yc, FS_S), k, fs=FS_S, fontweight="bold" if k == NAMED else "normal"
        )
        c.ax.add_patch(
            Rectangle(
                (track_x0, yc - 0.028),
                track_w,
                0.056,
                fc=S.tint(S.NEUTRAL, 0.16),
                ec="none",
                zorder=4,
            )
        )
        c.ax.add_patch(
            Rectangle(
                (track_x0, yc - 0.028),
                track_w * w_small,
                0.056,
                fc=S.tint(S.HYP[k], 0.6),
                ec="none",
                zorder=5,
            )
        )
        if k == NAMED:
            c.ax.add_patch(
                Rectangle(
                    (track_x0 + track_w * w_small, yc - 0.028),
                    track_w * (1 - LAMBDA),
                    0.056,
                    fc=deep,
                    ec="none",
                    zorder=5,
                )
            )
    # Key to the two tones, then what the answer controls.
    y = y_rows - 4 * row_h - 0.095
    c.swatch(xa + 0.06, y + 0.022, S.tint(S.HYP[NAMED], 0.6), s=0.055)
    c.text(xa + 0.15, y, r"$\lambda/|\mathcal{H}|$ each", fs=FS_S, color=S.INK_2)
    c.swatch(xa + 0.06, y - 0.098 + 0.022, deep, s=0.055)
    c.text(xa + 0.15, y - 0.098, r"$+(1-\lambda)$ if named", fs=FS_S, color=S.INK_2)
    lines_in(
        c,
        xa + 0.06,
        y - 0.205,
        [
            (r"$\lambda = 0.25$: the answer only", FS_S, ITAL),
            (r"reweights $\mathcal{H}$ and dates $\hat{k}_j$", FS_S, ITAL),
        ],
        pitch=0.113,
    )


def size_cell(c: Canvas, xc, y_l1, head, size, truth, order_lines):
    """The size the arm acts on, marked right or wrong against the hidden truth, then its order."""
    c.text(xc + 0.06, y_l1, head, fs=FS_S, **ITAL)
    yb = y_l1 - 0.175
    t = c.text(xc + 0.06, yb, periods(size), fs=FS, fontweight="bold")
    mark = c.check if size == truth else c.cross
    mark(c.extent(t)[2] + 0.07, yb + 0.03, s=0.075 if size == truth else 0.065)
    c.text(xc + 0.06, yb - 0.11, f"true shift: {periods(truth)}", fs=FS_S, color=S.INK_2)
    lines_in(c, xc + 0.06, yb - 0.24, order_lines, pitch=0.104)


def lanes(c: Canvas, x0, x1, ep, spec_mid, in_x1):
    gate_h = 0.97
    gutter = 0.2
    g_y1 = Y1
    g_y0 = g_y1 - gate_h
    h_y1 = g_y0 - gutter
    h_y0 = Y0
    card(
        c,
        x0,
        g_y0,
        x1 - x0,
        gate_h,
        S.GATE,
        "(b) Registered gate (arm 10)",
        "waits for the threshold, then acts all at once on the stated size",
        body=S.tint(S.GATE, 0.04),
    )
    card(
        c,
        x0,
        h_y0,
        x1 - x0,
        h_y1 - h_y0,
        S.HEDGE,
        "(c) Certify-then-hedge",
        "prices each hypothesis by its evidence and hedges by that price; with nothing "
        "live, it orders as arm 1",
        body=S.tint(S.HEDGE, 0.04),
    )

    # Columns: hypotheses, commitment, size and order, the example episode.
    pad = 0.07
    arr = 0.11
    widths = [1.07, 0.82, 0.98]
    xs = [x0 + pad]
    for wd in widths:
        xs.append(xs[-1] + wd + arr)
    ex0, ex1 = xs[3], x1 - pad
    widths.append(ex1 - ex0)
    plot_l, plot_r = 0.33, 0.4  # room for the tick labels and the end labels

    # (b) The gate lane.
    cy1 = g_y1 - STRIP - 0.07
    cy0 = g_y0 + 0.07
    ch = cy1 - cy0
    gm = (cy0 + cy1) / 2
    for i, (xx, wd) in enumerate(zip(xs, widths, strict=True)):
        c.cell(xx, cy0, wd, ch, S.GATE)
        if i:
            c.arrow((xx - arr + 0.025, gm), (xx - 0.025, gm), S.GATE)
    y_l1 = cy1 - 0.12
    xa, wa = xs[0], widths[0]
    c.text(xa + 0.06, y_l1, "the stated hypothesis only", fs=FS_S, **ITAL)
    yc = y_l1 - 0.18
    c.swatch(xa + 0.06, yc + 0.022, S.HYP[NAMED])
    c.text(xa + 0.15, yc, NAMED, fs=FS_S, fontweight="bold")
    yc -= 0.18
    c.text(xa + 0.15, yc, "magnitude", fs=FS_S, color=S.INK_2)
    c.chip(xa + wa - 0.06, yc + 0.022, "medium", S.GATE, ha="right", fs=FS_S)
    xb, wb = xs[1], widths[1]
    lines_in(
        c,
        xb + 0.06,
        y_l1,
        [
            ("all at once", FS_S, ITAL),
            (r"$E_{j,t}$ after $\tau_j$", FS_S, {}),
            (r"switch at $E_{j,t} \geq 1/\alpha_j$", FS_S, {}),
        ],
    )
    c.step_glyph(xb + 0.08, cy0 + 0.07, wb - 0.16, 0.12, S.GATE)
    xc = xs[2]
    size_cell(
        c,
        xc,
        y_l1,
        "stated size, compiled",
        ep["gate_offset"],
        ep["true_offset"],
        [("order from the compiled", FS_S, {}), ("configuration", FS_S, {})],
    )
    PLOTS["gate"] = mini_plot(
        c, ex0 + plot_l, cy0 + 0.14, widths[3] - plot_l - plot_r, ch - 0.2, ep, "gate"
    )

    # (c) The hedge lane.
    hy1 = h_y1 - STRIP - 0.07
    hy0 = h_y0 + 0.07
    hc1, hc0 = hy1, hy1 - ch
    hm = (hc0 + hc1) / 2
    c.cell(xs[0], hy0, widths[0], hy1 - hy0, S.HEDGE)
    for i, (xx, wd) in enumerate(zip(xs, widths, strict=True)):
        if i:
            c.cell(xx, hc0, wd, ch, S.HEDGE)
            c.arrow((xx - arr + 0.025, hm), (xx - 0.025, hm), S.HEDGE)
    y_l1 = hc1 - 0.12
    prior_column(c, xs[0], widths[0], y_l1)
    xb = xs[1]
    lines_in(
        c,
        xb + 0.06,
        y_l1,
        [
            ("graded", FS_S, ITAL),
            (r"$E_{jk,t}$ for every $k$", FS_S, {}),
            (r"$\pi_{jk,t} \propto a_j w_{jk} E_{jk,t-1}$", FS_S, {}),
        ],
    )
    c.ramp_glyph(xb + 0.08, hc0 + 0.07, wb - 0.16, 0.12, S.HEDGE)
    xc = xs[2]
    size_cell(
        c,
        xc,
        y_l1,
        "sized from the data",
        ep["hedge_offset"],
        ep["true_offset"],
        [(r"order: $p/(p+h)$ quantile", FS_S, {}), ("of the mixture", FS_S, {})],
    )
    PLOTS["hedge"] = mini_plot(
        c, ex0 + plot_l, hc0 + 0.14, widths[3] - plot_l - plot_r, ch - 0.2, ep, "hedge"
    )

    # The exposure bound, under columns two to four of the hedge lane.
    gx0, gx1 = xs[1], ex1
    gy1, gy0 = hc0 - 0.055, hy0
    c.box(
        gx0, gy0, gx1 - gx0, gy1 - gy0, fc=S.tint(S.HEDGE, 0.12), ec=S.HEDGE, lw=0.7, r=0.035, z=3
    )
    CARDS.append(("bound", gx0, gy0, gx1, gy1))
    gmid = (gy0 + gy1) / 2
    up, down = gmid + 0.017, gmid - 0.088
    c.shield(gx0 + 0.13, gmid, 0.17, S.HEDGE)
    t = c.text(gx0 + 0.26, up, r"$\mathbb{E}_0[\Pi_\sigma] \leq A$", fs=FS_T, fontweight="bold")
    t2 = c.text(gx0 + 0.26, down, r"at every stopping time $\sigma$", fs=FS_S, color=S.INK_2)
    xg = max(c.extent(t)[2], c.extent(t2)[2]) + 0.1
    premise = ("if the null and arrival law are known;", r"as run, up to 2.7$A$ (Limitations)")
    w_right = max(c.width(s, fs=FS_S) for s in premise)
    xr = gx1 - 0.07 - w_right
    body = ("when nothing has changed,", "whatever the model says")
    assert xg + max(c.width(b, fs=FS_S) for b in body) + 0.1 < xr, "bound text too wide"
    for s, yy in zip(body, (up, down), strict=True):
        c.text(xg, yy, s, fs=FS_S)
    for xv in (xg - 0.05, xr - 0.05):
        c.line([xv, xv], [gmid - 0.085, gmid + 0.085], color=S.tint(S.HEDGE, 0.5), lw=0.6)
    for s, yy in zip(premise, (up, down), strict=True):
        c.text(xr, yy, s, fs=FS_S, color=S.INK_2)

    # The shared input forks into both lanes.
    trunk = (in_x1 + x0) / 2
    c.line([in_x1, trunk], [spec_mid] * 2, color=S.INK_2, lw=1.0, zorder=4)
    c.line([trunk, trunk], [hm, gm], color=S.INK_2, lw=1.0, zorder=4, solid_capstyle="butt")
    c.ax.add_patch(plt.Circle((trunk, spec_mid), 0.018, fc=S.INK_2, ec="none", zorder=5))
    for ym, col in ((gm, S.GATE), (hm, S.HEDGE)):
        c.line([trunk - 0.005, trunk + 0.02], [ym] * 2, color=S.INK_2, lw=1.0, zorder=4)
        c.arrow((trunk + 0.015, ym), (x0 - 0.004, ym), col, lw=1.0)

    # The gutter: column headers shared by both lanes; the episode's carries the line key.
    gy = (g_y0 + h_y1) / 2
    rule = S.tint(S.NEUTRAL, 0.55)
    heads = ["hypotheses", "commitment", "size and order", "the example episode"]
    for s, xx, wd in zip(heads, xs, widths, strict=True):
        parts = [(s, {"fontweight": "bold"})]
        if s == heads[-1]:
            parts += [("alert", {}), ("onset", {})]
        ws = [c.width(p, fs=FS_S, **kw) for p, kw in parts]
        key_gap, glyph = 0.12, 0.06
        total = ws[0] + sum(key_gap + glyph + w for w in ws[1:])
        xt = xx + wd / 2 - total / 2
        c.text(xt, baseline(gy, FS_S), parts[0][0], fs=FS_S, color=S.INK_2, **parts[0][1])
        xk = xt + ws[0]
        for (p, _), w, ls in zip(parts[1:], ws[1:], ("-", (0, (1, 1.5))), strict=False):
            xk += key_gap
            c.line([xk + 0.015, xk + 0.015], [gy - 0.045, gy + 0.045], color=S.MUTED, lw=0.6, ls=ls)
            c.text(xk + glyph, baseline(gy, FS_S), p, fs=FS_S, color=S.INK_2)
            xk += glyph + w
        tx0, tx1 = xt, xt + total
        assert tx1 - tx0 + 0.2 < wd, f"column header {s!r} wider than its column"
        for a, b in ((xx + 0.02, tx0 - 0.05), (tx1 + 0.05, xx + wd - 0.02)):
            c.line([a, b], [gy, gy], color=rule, lw=0.6)
        for xe in (xx + 0.02, xx + wd - 0.02):
            c.line([xe, xe], [gy - 0.03, gy + 0.03], color=rule, lw=0.6)


# -- checks ----------------------------------------------------------------------------------


def all_texts(fig):
    return [t for t in fig.findobj(Text) if t.get_visible() and t.get_text().strip()]


def _assert_content(fig, ep) -> None:
    texts = [t.get_text() for t in all_texts(fig)]
    joined = " | ".join(texts)
    assert all(t.get_fontsize() >= FS_S for t in all_texts(fig)), "text < 6.5 pt"
    allowed = {
        "0",
        "1",
        "2",
        "10",
        "13",
        "14",
        "24",
        "50",
        "0.25",
        "198",
        "2,358",
        "2,000",
        "3.8",
        "2.7",
    }
    stripped = re.sub(r"\$[^$]*\$", "", joined)  # maths carries only symbols
    stripped = stripped.replace("arm 10", "").replace("arm 1", "")
    nums = re.findall(r"\d[\d,.]*\d|\d", stripped)
    bad = [n for n in nums if n not in allowed]
    assert not bad, f"numbers not in the fact list: {bad}"
    assert not re.search(r"(?<![A-Za-z_\[])-\d", stripped), "ASCII minus before a digit"
    assert ep["proposal"] == [13] and ep["onset"] == 14 and ep["gate_on"] == 24
    assert round(ep["cth"][-1]) == 198 and round(ep["gnet"][-1]) == -2358
    assert "−2,358" in joined and "+198" in joined
    for k in H_SET:
        assert k in joined, f"hypothesis {k} missing"
    for key, val in spec_rows(ep["meta"]):
        assert key in texts and val in texts, f"ShockSpec field {key} missing"
    meta = ep["meta"]
    assert " ".join(ep["alert_lines"]) == "“" + meta["alert_text"] + "”"
    assert all(line in texts for line in ep["alert_lines"])
    assert ep["true_offset"] == 1 and ep["gate_offset"] == 2 and ep["hedge_offset"] == 1
    for n in (ep["true_offset"], ep["gate_offset"], ep["hedge_offset"]):
        assert periods(n) in joined
    assert f"true shift: {periods(ep['true_offset'])}" in texts
    assert np.all(np.diff(ep["gate"]) >= 0) and ep["gate"][-1] == 1


def _assert_layout(fig) -> None:
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    boxes = []
    for t in all_texts(fig):
        bb = t.get_window_extent(r)
        patch = t.get_bbox_patch()
        if patch is not None:
            bb = patch.get_window_extent(r)
        boxes.append(
            (t.get_text(), (bb.x0 / fig.dpi, bb.y0 / fig.dpi, bb.x1 / fig.dpi, bb.y1 / fig.dpi))
        )
    fx, fy = FRAME_PAD * W + 0.03, FRAME_PAD * H + 0.02
    for s, (x0, y0, x1, y1) in boxes:
        assert x0 >= fx and y0 >= fy and x1 <= W - fx and y1 <= H - fy, f"text outside {s!r}"
    tol = 0.004
    for i, (s, a) in enumerate(boxes):
        for u, b in boxes[i + 1 :]:
            ox = min(a[2], b[2]) - max(a[0], b[0])
            oy = min(a[3], b[3]) - max(a[1], b[1])
            assert ox <= tol or oy <= tol, f"overlapping text {s!r} and {u!r}"
    for name, cx0, cy0, cx1, cy1 in CARDS:
        for s, (x0, y0, x1, y1) in boxes:
            inside = x0 >= cx0 - tol and x1 <= cx1 + tol and y0 >= cy0 - tol and y1 <= cy1 + tol
            outside = x1 <= cx0 + tol or x0 >= cx1 - tol or y1 <= cy0 + tol or y0 >= cy1 - tol
            assert inside or outside, f"text {s!r} straddles the border of {name!r}"


def _assert_plots() -> None:
    """Both lanes end in the same plot: equal size, equal scales, no clipping."""
    (gc, gn), (hc, hn) = PLOTS["gate"], PLOTS["hedge"]
    for a, b in ((gc, hc), (gn, hn)):
        assert a.get_xlim() == b.get_xlim() and a.get_ylim() == b.get_ylim(), "scales differ"
        pa, pb = a.get_position(), b.get_position()
        assert abs(pa.width - pb.width) < 1e-9 and abs(pa.height - pb.height) < 1e-9
        assert abs(pa.x0 - pb.x0) < 1e-9, "plots not aligned"
    lo, hi = gn.get_ylim()
    for line in gn.lines + hn.lines:
        y = np.asarray(line.get_ydata(), dtype=float)
        assert y.min() >= lo and y.max() <= hi, "a series is clipped"


def render(out_dir: Path | None = None) -> None:
    CARDS.clear()
    PLOTS.clear()
    S.use_style(font_size=FS)
    fig = plt.figure(figsize=(W, H))
    S.rounded_frame(fig, pad=FRAME_PAD, lw=1.1)
    c = Canvas(fig)
    ep = load_episode()
    in_x1 = X0 + 1.5
    spec_mid = input_card(c, X0, in_x1, ep)
    lanes(c, in_x1 + 0.17, X1, ep, spec_mid, in_x1)
    fig.canvas.draw()  # tick labels exist only after a draw
    _assert_content(fig, ep)
    _assert_layout(fig)
    _assert_plots()
    S.save(fig, NAME, out_dir)


if __name__ == "__main__":
    render(Path(sys.argv[1]) if len(sys.argv) > 1 else None)
    print(f"rendered {NAME}")
