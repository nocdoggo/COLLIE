#!/usr/bin/env python3
"""Figure 2 (fig:method): how certify-then-hedge turns a ShockSpec into an order.

A schematic in the notation of Section VI, read left to right, on the worked example of
Fig. 1 (the model names a lead-time shift):

(a) the ShockSpec the model returns at trigger firing j (stopping time tau_j, at most two
    firings): of its nine fields the hedge reads shock_family and direction, which name the
    hypothesis k-hat_j (``hypothesis_key`` in analysis/commitment/cth.py), and onset_window,
    which dates that hypothesis's e-process; it reads none of the other six. The model cannot
    write an order, a threshold, a likelihood or code;
(b) the prior over the fixed set H: mass a_j w_jk with a_j = alpha 2^-j and
    w_jk = lambda/|H| + (1 - lambda) 1{k = k-hat_j}, lambda = 1/4. The bars are the exact
    weights (13/16 for the named lead-time shift, 1/16 for the others), drawn as the base
    lambda/|H| plus the increment 1 - lambda;
(c) certification: one e-process per (j, k) from tau_j (schematic paths; the named one rises),
    the predictable posterior mass pi_jk,t, which at decision t uses E_jk,t-1, and the size of
    the shock estimated from the data within each hypothesis, giving its law G_jk,t;
(d) the hedge: x_t, the beta = p/(p+h) quantile of the posterior-predictive mixture (schematic
    densities of its two parts), against arm 1's target x0_t, and the order q_t;
(e) the guarantees as the section states them; only the exposure bound needs the known-null
    premise.

No measured numbers appear. The curves in (c) and (d) are schematic and labelled so; the only
numbers are registered constants (j <= 2, the offsets 1 to 3, the five pseudo-observations,
lambda, the weights it implies, log 4 and log 3.25), and the render asserts them.

Usage  uv run python paper/illustrate/method.py [out_dir]   (default ../figures/fig2_method.*)
"""

from __future__ import annotations

import math
import re
import sys
from fractions import Fraction
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import style as S  # noqa: E402
from matplotlib.colors import to_rgb  # noqa: E402
from matplotlib.patches import FancyBboxPatch, Polygon, Rectangle  # noqa: E402

NAME = "fig2_method"

FS = 7.0  # body text (pt)
FS_S = 6.5  # smallest text (pt)
FS_T = 7.5  # card titles (pt)
PT = S.PT
MONO = "Ubuntu Mono"  # narrow TrueType monospace for the ShockSpec fields
DPI = 600  # measuring resolution; text extents are exact to 1/600 in

W, H = S.TEXT_WIDTH, 2.45
FRAME_PAD = 0.004
X0, X1 = 0.085, W - 0.085
Y0, Y1 = 0.075, H - 0.075
STRIP = 0.165  # card header strip (in)
PAD = 0.07  # inner card padding (in)

# The guarantees strip along the bottom, the row of stage cards above it.
G_Y0, G_Y1 = Y0, 0.59
G_STRIP = 0.155
C_Y0, C_Y1 = 0.645, Y1
GAP = 0.14
WIDTHS = (1.33, 1.38, X1 - X0 - 3 * GAP - 1.33 - 1.38 - 1.54, 1.54)  # (c) takes the rest

LAMBDA = 0.25
HYPS = ["demand up", "demand down", "lead-time shift", "upward pulse"]
NAMED = "lead-time shift"  # the hypothesis the example ShockSpec names, as in Fig. 1

ITAL = {"color": S.INK_2, "style": "italic"}
TITLES: list[tuple] = []  # (name, artists, x0, y0, x1, y1 of the header strip)
HEADS: list[tuple] = []  # (name, artists, x0, x1 of the column) for the strip's headings
CURVES: list[tuple] = []  # (name, xs, ys) in inches: plotted lines no text may cover
CLEAR: list = []  # texts that sit inside a plot and must stay off its curves


def bl(yc: float, fs: float = FS) -> float:
    """Baseline that visually centres one line of text on height ``yc``."""
    return yc - 0.3 * fs * PT


def deep(color: str) -> tuple[float, float, float]:
    """A darker shade of ``color`` (the named hypothesis's increment)."""
    return tuple(0.72 * a + 0.28 * b for a, b in zip(to_rgb(color), to_rgb(S.INK), strict=True))


class Canvas(S.Canvas):
    """House canvas; every text also records the box it must stay inside."""

    def __init__(self, fig):
        super().__init__(fig)
        self.owner: dict[int, tuple[str, tuple[float, float, float, float]]] = {}
        self._box: tuple[str, tuple[float, float, float, float]] | None = None

    def inside(self, name: str | None, x0=0.0, y0=0.0, x1=0.0, y1=0.0) -> None:
        self._box = None if name is None else (name, (x0, y0, x1, y1))

    def t(self, x, y, s, fs=FS, **kw):
        art = self.text(x, y, s, fs=fs, **kw)
        if self._box is not None:
            self.owner[id(art)] = self._box
        return art

    def curve(self, name, xs, ys, **kw):
        """A plotted line that texts must keep off."""
        xs, ys = np.asarray(xs, float), np.asarray(ys, float)
        self.line(xs, ys, **kw)
        CURVES.append((name, xs, ys))

    def panel(self, name, x0, y0, x1, y1, fc, ec, ls="-"):
        """Rounded sub-box; the texts that follow must stay inside it."""
        self.box(x0, y0, x1 - x0, y1 - y0, fc=fc, ec=ec, lw=0.6, ls=ls, r=0.03, z=3)
        self.inside(name, x0 + 0.01, y0 + 0.01, x1 - 0.01, y1 - 0.01)

    def swatch(self, x, yc, color, s=0.055):
        self.ax.add_patch(
            FancyBboxPatch(
                (x, yc - s / 2),
                s,
                s,
                boxstyle="round,pad=0,rounding_size=0.012",
                fc=color,
                ec="none",
                zorder=4,
            )
        )
        return x + s

    def dot(self, x, y, color, ms=2.4, z=5):
        self.ax.plot([x], [y], "o", ms=ms, color=color, mec="none", zorder=z)

    def runs(self, x, y, runs, gap):
        """Texts side by side from ``x`` on baseline ``y``; returns the artists."""
        out = []
        for s, fs, kw in runs:
            art = self.t(x, y, s, fs=fs, **kw)
            out.append(art)
            x = self.extent(art)[2] + gap
        return out

    def runs_width(self, runs, gap):
        return sum(self.width(s, fs=fs, **kw) for s, fs, kw in runs) + gap * (len(runs) - 1)

    def block_arrow(self, x0, x1, yc, color, h=0.17):
        """Chunky chevron between two cards."""
        sh = 0.42 * h
        head = 0.55 * (x1 - x0)
        pts = [
            (x0, yc - sh / 2),
            (x1 - head, yc - sh / 2),
            (x1 - head, yc - h / 2),
            (x1, yc),
            (x1 - head, yc + h / 2),
            (x1 - head, yc + sh / 2),
            (x0, yc + sh / 2),
        ]
        self.ax.add_patch(
            Polygon(
                pts,
                closed=True,
                fc=S.tint(color, 0.55),
                ec=color,
                lw=0.6,
                joinstyle="round",
                zorder=4,
            )
        )


def small_caps(word: str, fs: float, small: float) -> list:
    """(text, size) runs that set ``word`` in small capitals."""
    return [
        (run.upper(), fs if run[0].isupper() else small)
        for run in re.findall(r"[A-Z]+|[^A-Z]+", word)
    ]


def card(c: Canvas, name, x, y, w, h, accent, title_runs, body=S.SURFACE, strip=STRIP):
    """Card with a tinted header strip; the title runs (text, size, gap after) centred on it."""
    base = c.box(x, y, w, h, fc=body, ec="none", r=0.05, z=2)
    band = Rectangle((x, y + h - strip), w, strip, fc=S.tint(accent, 0.28), ec="none", zorder=2.1)
    c.ax.add_patch(band)
    band.set_clip_path(base)
    c.line([x, x + w], [y + h - strip] * 2, color=accent, lw=0.5, zorder=2.2)
    c.box(x, y, w, h, fc="none", ec=accent, lw=0.85, r=0.05, z=2.6)
    total = sum(c.width(s, fs=fs, fontweight="bold") for s, fs, _ in title_runs)
    total += sum(g for _, _, g in title_runs[:-1])
    xt = x + w / 2 - total / 2
    yb = bl(y + h - strip / 2, FS_T)
    arts = []
    for s, fs, g in title_runs:
        art = c.text(xt, yb, s, fs=fs, fontweight="bold")
        arts.append(art)
        xt = c.extent(art)[2] + g
    TITLES.append((name, arts, x, y + h - strip, x + w, y + h))
    return y + h - strip


def title(s: str) -> list:
    """A plain one-run title."""
    return [(s, FS_T, 0.0)]


def open_card(c: Canvas, name: str, x: float, w: float, accent: str, runs: list) -> float:
    """Draw a stage card, register its body as the container, return the body's top."""
    top = card(c, name, x, C_Y0, w, C_Y1 - C_Y0, accent, runs)
    c.inside(name, x + 0.025, C_Y0 + 0.02, x + w - 0.025, top - 0.01)
    return top


# -- (a) the ShockSpec -----------------------------------------------------------------------


def card_spec(c: Canvas, x: float, w: float) -> None:
    """The ShockSpec the model returns at tau_j: what the hedge reads of it, and what not."""
    space = c.width("a a", fs=FS_T, fontweight="bold") - c.width("aa", fs=FS_T, fontweight="bold")
    sc = small_caps("ShockSpec", FS_T, FS_S)
    runs = [("(a)", FS_T, space)]
    runs += [(s, fs, 0.0) for s, fs in sc[:-1]] + [(sc[-1][0], sc[-1][1], space)]
    runs += [(r"at firing $j$", FS_T, 0.0)]
    top = open_card(c, "card a", x, w, S.NEUTRAL, runs)
    y = top - 0.11
    c.t(x + w / 2, y, r"one record per firing, $j \leq 2$", fs=FS_S, ha="center", **ITAL)

    # The record: the three fields the hedge reads, then the six it does not.
    keys = ["shock_family", "direction", "onset_window"]
    grey = [
        "stream, magnitude, persistence,",
        "duration, evidence, signature:",
        "not read by the hedge",
    ]
    key_w = max(c.width(k, fs=FS_S, family=MONO) for k in keys)
    pitch, g_pitch = 0.108, 0.1
    r_top = y - 0.07
    rows_bot = r_top - 0.02 - len(keys) * pitch
    rule = rows_bot - 0.012
    r_bot = rule - 0.02 - len(grey) * g_pitch - 0.02
    bx0, bx1 = x + 0.05, x + w - 0.05  # the record is wider than the card's text column
    c.box(
        bx0,
        r_bot,
        bx1 - bx0,
        r_top - r_bot,
        fc=S.SURFACE,
        ec=S.tint(S.NEUTRAL, 0.7),
        lw=0.6,
        r=0.03,
        z=3,
    )
    c.inside("record", bx0 + 0.01, r_bot + 0.01, bx1 - 0.01, r_top - 0.01)
    kx = bx0 + 0.055
    rows = []
    for i, key in enumerate(keys):
        yc = r_top - 0.02 - (i + 0.5) * pitch
        rows.append(yc)
        c.ax.add_patch(
            Rectangle(
                (kx - 0.025, yc - pitch / 2 + 0.01),
                key_w + 0.05,
                pitch - 0.02,
                fc=S.tint(S.HEDGE, 0.14),
                ec="none",
                zorder=3.2,
            )
        )
        c.t(kx, bl(yc, FS_S), key, fs=FS_S, family=MONO)
    bx = kx + key_w + 0.045
    tx = bx + 0.085
    ya, yb = rows[0] + 0.032, rows[1] - 0.032
    c.line([bx, bx + 0.03, bx + 0.03, bx], [ya, ya, yb, yb], color=S.HEDGE, lw=0.7, zorder=4)
    c.line([bx + 0.03, bx + 0.06], [(ya + yb) / 2] * 2, color=S.HEDGE, lw=0.7, zorder=4)
    c.t(tx, bl((ya + yb) / 2, FS_S), r"names $\hat k_j$", fs=FS_S)
    c.line([bx, bx + 0.06], [rows[2]] * 2, color=S.HEDGE, lw=0.7, zorder=4)
    c.t(tx, bl(rows[2], FS_S), r"dates $\hat k_j$", fs=FS_S)
    c.line(
        [bx0 + 0.03, bx1 - 0.03], [rule, rule], color=S.tint(S.NEUTRAL, 0.35), lw=0.5, zorder=3.3
    )
    yy = rule - 0.02 - 0.5 * g_pitch
    for s in grey:
        style = "italic" if s == grey[-1] else "normal"
        c.t(x + w / 2, bl(yy, FS_S), s, fs=FS_S, ha="center", color=S.MUTED, style=style)
        yy -= g_pitch

    # No named hypothesis, then what the model may not write.
    c.inside("card a", x + 0.025, C_Y0 + 0.02, x + w - 0.025, top - 0.01)
    y = r_bot - 0.115
    c.t(x + w / 2, y, r"abstain, unparsed, or outside $\mathcal{H}$:", fs=FS_S, ha="center", **ITAL)
    c.t(x + w / 2, y - 0.118, r"no $\hat k_j$ is named", fs=FS_S, ha="center", **ITAL)
    y -= 0.25
    c.t(x + w / 2, y, "the model cannot write", fs=FS_S, ha="center", **ITAL)
    for row in (["an order", "a threshold"], ["a likelihood", "code"]):
        y -= 0.12
        widths = [0.08 + c.width(s, fs=FS_S) for s in row]
        xx = x + (w - sum(widths) - 0.12) / 2
        for s, ww in zip(row, widths, strict=True):
            c.cross(xx, y + 0.3 * FS_S * PT, s=0.045, lw=1.1)
            c.t(xx + 0.08, y, s, fs=FS_S)
            xx += ww + 0.12
    c.inside(None)


# -- (b) the prior ---------------------------------------------------------------------------


def card_prior(c: Canvas, x: float, w: float) -> None:
    """The prior over the fixed hypothesis set: base weight plus the named increment."""
    top = open_card(c, "card b", x, w, S.HEDGE, title(r"(b) Prior over fixed $\mathcal{H}$"))
    xi, xr = x + PAD, x + w - PAD
    y = top - 0.11
    c.t(
        x + w / 2,
        y,
        r"prior $w_{jk}$: each $k$'s share of $a_j$",
        fs=FS_S,
        ha="center",
        **ITAL,
    )

    lab_w = max(c.width(h, fs=FS_S, fontweight="bold") for h in HYPS)
    sw = 0.055
    bar_x = xi + sw + 0.045 + lab_w + 0.05
    val_w = c.width(r"$13/16$", fs=FS_S)
    track_w = xr - bar_x - val_w - 0.04
    w_small = LAMBDA / len(HYPS)
    pitch = 0.12
    y_top = y - 0.06
    bar_h = 0.062
    for i, hyp in enumerate(HYPS):
        yc = y_top - (i + 0.5) * pitch
        col = S.HYP[hyp]
        named = hyp == NAMED
        c.swatch(xi, yc, col, sw)
        c.t(xi + sw + 0.045, bl(yc, FS_S), hyp, fs=FS_S, fontweight="bold" if named else "normal")
        c.ax.add_patch(
            Rectangle(
                (bar_x, yc - bar_h / 2),
                track_w,
                bar_h,
                fc=S.tint(S.NEUTRAL, 0.14),
                ec="none",
                zorder=3.5,
            )
        )
        c.ax.add_patch(
            Rectangle(
                (bar_x, yc - bar_h / 2),
                track_w * w_small,
                bar_h,
                fc=S.tint(col, 0.6),
                ec="none",
                zorder=4,
            )
        )
        if named:
            c.ax.add_patch(
                Rectangle(
                    (bar_x + track_w * w_small, yc - bar_h / 2),
                    track_w * (1 - LAMBDA),
                    bar_h,
                    fc=deep(col),
                    ec="none",
                    zorder=4,
                )
            )
        c.t(
            bar_x + track_w + 0.04,
            bl(yc, FS_S),
            r"$13/16$" if named else r"$1/16$",
            fs=FS_S,
            color=S.INK if named else S.INK_2,
        )

    # Key to the two tones.
    y = y_top - len(HYPS) * pitch - 0.08
    c.swatch(xi, y, S.tint(S.HYP[NAMED], 0.6), sw)
    c.t(xi + sw + 0.045, bl(y, FS_S), r"$\lambda/|\mathcal{H}|$ each", fs=FS_S, color=S.INK_2)
    y -= 0.118
    c.swatch(xi, y, deep(S.HYP[NAMED]), sw)
    c.t(
        xi + sw + 0.045,
        bl(y, FS_S),
        r"$+(1-\lambda)$ to the named $\hat k_j$",
        fs=FS_S,
        color=S.INK_2,
    )

    # The prior's formula.
    fy1 = y - 0.09
    fy0 = fy1 - 0.4
    c.panel("prior formula", xi, fy0, xr, fy1, S.tint(S.HEDGE, 0.08), S.tint(S.HEDGE, 0.45))
    cx = (xi + xr) / 2
    c.t(
        cx,
        bl(fy1 - 0.08),
        r"$a_j=\alpha\,2^{-j}$,  $A=\Sigma_j\,a_j \leq 3\alpha/4$",
        fs=FS,
        ha="center",
    )
    c.t(
        cx,
        bl(fy1 - 0.203, FS_S),
        r"$w_{jk}=\lambda/|\mathcal{H}| + (1-\lambda)\,\mathbb{1}\{k=\hat k_j\}$",
        fs=FS_S,
        ha="center",
    )
    c.t(
        cx,
        bl(fy1 - 0.315, FS_S),
        r"registered hedge $\lambda = 1/4$",
        fs=FS_S,
        ha="center",
        color=S.INK_2,
    )

    c.inside("card b", x + 0.025, C_Y0 + 0.02, x + w - 0.025, top - 0.01)
    c.t(
        x + w / 2,
        fy0 - 0.13,
        r"no $\hat k_j$: every $w_{jk}=\lambda/|\mathcal{H}|$",
        fs=FS_S,
        ha="center",
        **ITAL,
    )
    c.inside(None)


# -- (c) certification -----------------------------------------------------------------------


def eprocess_paths(n: int = 200):
    """Smooth schematic log e-process paths from tau_j to t - 1 (made up, no data)."""
    u = np.linspace(0, 1, n)

    def wig(f, p):
        return 0.1 * np.sin(f * u + p) * 4 * u * (1 - u)

    return u, {
        "demand up": -0.35 * u + wig(17, 0.3),
        "demand down": -1.15 * u**0.85 + wig(13, 1.1),
        "lead-time shift": 3.1 * u**2.2 + wig(11, 2.0),
        "upward pulse": 0.95 * u - 1.7 * u**2 + wig(19, 0.7),
    }


def card_certify(c: Canvas, x: float, w: float) -> dict:
    """One e-process per hypothesis, the predictable posterior mass, and sizing from the data."""
    top = open_card(c, "card c", x, w, S.HEDGE, title("(c) Certify: evidence to posterior mass"))
    xi, xr = x + PAD, x + w - PAD

    notes = [
        (r"one e-process per $(j,k)$,", S.INK),
        (r"$E_{jk}=1$ at $\tau_j$, data after it;", S.INK),
        (r"anytime valid under $\mathbb{P}_0$;", S.INK),
        ("the model's onset", S.INK_2),
        (r"window dates $\hat k_j$", S.INK_2),
    ]
    notes_w = max(c.width(s, fs=FS_S) for s, _ in notes)
    nx = xr - notes_w
    px0 = xi + 0.07  # the y axis
    x_t = nx - 0.13  # decision t
    x_tm1 = x_t - 0.1  # t - 1
    xs0 = px0 + 0.08  # tau_j
    py1 = top - 0.05
    py0 = py1 - 0.42
    ax_top = py1 - 0.085  # the axis stops under its label
    lo, hi = -2.9, 3.25

    def ymap(v):
        return py0 + (np.asarray(v) - lo) / (hi - lo) * (py1 - py0)

    def xmap(u):
        return xs0 + np.asarray(u) * (x_tm1 - xs0)

    c.ax.add_patch(
        Rectangle(
            (px0, py0), xs0 - px0, ax_top - py0, fc=S.tint(S.NEUTRAL, 0.14), ec="none", zorder=2.5
        )
    )
    c.curve("y axis", [px0, px0], [py0, ax_top], color=S.BASELINE, lw=0.6)
    c.line([px0, x_t + 0.05], [py0, py0], color=S.BASELINE, lw=0.6)
    c.curve("tau_j", [xs0, xs0], [py0, ax_top], color=S.INK_2, lw=0.6, ls=(0, (2, 1.5)))
    c.curve("t-1", [x_tm1, x_tm1], [py0, py1], color=S.INK_2, lw=0.6, ls=(0, (2, 1.5)))
    c.line([x_t, x_t], [py0 - 0.03, py0 + 0.03], color=S.INK, lw=1.0, zorder=4)
    c.line([px0, x_tm1], [ymap(0)] * 2, color=S.MUTED, lw=0.5, ls=(0, (1, 1.5)))
    u, paths = eprocess_paths()
    for hyp, v in paths.items():
        named = hyp == NAMED
        c.curve(
            hyp,
            xmap(u),
            ymap(v),
            color=S.HYP[hyp],
            lw=1.4 if named else 0.9,
            solid_capstyle="round",
            zorder=4.5 if named else 4,
        )
        c.dot(float(xmap(1.0)), float(ymap(v[-1])), S.HYP[hyp], ms=2.8 if named else 2.2)
    c.t(px0 - 0.03, bl(ymap(0), FS_S), "0", fs=FS_S, ha="right", color=S.INK_2)
    CLEAR.append(c.t(px0, bl(py1 - 0.022, FS_S), r"$\log E$", fs=FS_S, ha="center", color=S.INK_2))
    ylab = py0 - 0.1
    c.t(xs0, ylab, r"$\tau_j$", fs=FS_S, ha="center", color=S.INK_2)
    w_dec = c.width(r"decision $t$", fs=FS_S)
    w_t = c.width(r"$t$", fs=FS_S)
    c.t(x_t + w_t / 2 - w_dec, ylab, r"decision $t$", fs=FS_S)
    CLEAR.append(
        c.t(x_tm1 - 0.025, bl(py0 + 0.055, FS_S), r"$t-1$", fs=FS_S, ha="right", color=S.INK_2)
    )
    c.t(
        (xs0 + 0.05 + x_t + w_t / 2 - w_dec) / 2,
        ylab,
        "schematic",
        fs=FS_S,
        ha="center",
        color=S.MUTED,
        style="italic",
    )

    # Direct label on the named path: above it, left of where it climbs past the label.
    y_lab = py1 - 0.025
    v_lab = lo + (y_lab - 0.045 - py0) / (py1 - py0) * (hi - lo)
    u_cross = float(u[np.argmax(paths[NAMED] >= v_lab)])
    lab = c.t(
        float(xmap(u_cross)) - 0.03,
        bl(y_lab, FS_S),
        NAMED,
        fs=FS_S,
        ha="right",
        color=S.HYP[NAMED],
        fontweight="bold",
    )
    CLEAR.append(lab)

    yy = py1 - 0.045
    for s, col in notes:
        c.t(nx, bl(yy, FS_S), s, fs=FS_S, color=col)
        yy -= 0.11

    # Posterior shock mass.
    fy1 = py0 - 0.145
    fy0 = fy1 - 0.34
    c.panel("posterior", xi, fy0, xr, fy1, S.tint(S.HEDGE, 0.08), S.tint(S.HEDGE, 0.45))
    frac = c.t(
        xi + 0.08,
        bl((fy0 + fy1) / 2 + 0.005),
        r"$\pi_{jk,t}=\dfrac{a_j w_{jk}\,E_{jk,t-1}}{1-A_t+N_{t-1}}$",
        fs=FS,
    )
    rx = c.extent(frac)[2] + 0.2
    c.line([rx - 0.1] * 2, [fy0 + 0.05, fy1 - 0.05], color=S.tint(S.HEDGE, 0.45), lw=0.6)
    c.t(rx, bl(fy1 - 0.07, FS_S), r"$N_t=\Sigma_{j,k}\,a_j w_{jk} E_{jk,t}$", fs=FS_S)
    c.t(rx, bl(fy1 - 0.172, FS_S), r"$A_t$: the $a_j$ fired before $t$", fs=FS_S)
    c.t(rx, bl(fy1 - 0.274, FS_S), r"$\Pi_t=\Sigma_{j,k}\,\pi_{jk,t}$", fs=FS_S)

    # Size from the data.
    sy1 = fy0 - 0.045
    sy0 = C_Y0 + 0.04
    c.panel("size", xi, sy0, xr, sy1, S.SURFACE, S.tint(S.NEUTRAL, 0.6), ls=(0, (2.5, 1.5)))
    lx = xi + 0.06
    c.t(
        lx, bl(sy1 - 0.07, FS_S), r"size from the data, within each $k$", fs=FS_S, fontweight="bold"
    )
    y = sy1 - 0.07 - 0.1
    xx = lx
    for hyp in ("demand up", "demand down", "upward pulse"):
        xx = c.swatch(xx, y, S.HYP[hyp], 0.05) + 0.02
    tx = xx + 0.03
    pitch = 0.097
    c.t(tx, bl(y, FS_S), "multipliers, starts and durations; the level", fs=FS_S)
    y -= pitch
    c.t(tx, bl(y, FS_S), "learned from 5 pseudo-observations", fs=FS_S)
    y -= pitch
    c.swatch(lx, y, S.HYP[NAMED], 0.05)
    c.t(tx, bl(y, FS_S), r"offset $\Delta\in\{1,2,3\}$ and start, from arrivals", fs=FS_S)
    y -= pitch
    c.t(tx, bl(y, FS_S), r"$\Rightarrow$ law $G_{jk,t}$, not the model's magnitude bin", fs=FS_S)
    c.inside(None)
    return {"paths": paths}


# -- (d) the hedge ---------------------------------------------------------------------------


def densities():
    """Schematic densities of the requirement: arm 1's null and the lead-time hypothesis."""
    u = np.linspace(0, 1, 800)
    pi_ = 0.45
    f0 = np.exp(-0.5 * ((u - 0.37) / 0.1) ** 2)
    g = np.exp(-0.5 * ((u - 0.6) / 0.125) ** 2)
    f0 /= np.trapezoid(f0, u)
    g /= np.trapezoid(g, u)
    beta = 0.8
    mix = (1 - pi_) * f0 + pi_ * g

    def quantile(dens):
        cdf = np.cumsum(dens)
        return int(np.searchsorted(cdf / cdf[-1], beta))

    return u, pi_, f0, g, mix, beta, quantile(mix), quantile(f0)


def card_hedge(c: Canvas, x: float, w: float) -> dict:
    """The critical-fractile order of the posterior-predictive mixture."""
    top = open_card(c, "card d", x, w, S.HEDGE, title(r"(d) Hedge: the order $q_t$"))
    xi, xr = x + PAD, x + w - PAD

    px0, px1 = xi + 0.02, xr - 0.02
    py1 = top - 0.04
    py0 = py1 - 0.64
    u, pi_, f0, g, mix, beta, i_t, i_0 = densities()
    top_v = mix.max() * 1.62

    def xm(v):
        return px0 + np.asarray(v) * (px1 - px0)

    def ym(v):
        return py0 + np.asarray(v) / top_v * (py1 - py0)

    null, hyp = (1 - pi_) * f0, pi_ * g
    c.ax.fill_between(
        xm(u[: i_t + 1]), py0, ym(mix[: i_t + 1]), color=S.tint(S.HEDGE, 0.2), lw=0, zorder=3
    )
    c.curve("null part", xm(u), ym(null), color=S.BASE, lw=0.95, ls=(0, (3, 1.5)), zorder=3.5)
    c.curve(
        "hypothesis part", xm(u), ym(hyp), color=S.HYP[NAMED], lw=0.95, ls=(0, (3, 1.5)), zorder=3.5
    )
    c.curve("mixture", xm(u), ym(mix), color=S.HEDGE, lw=1.3, zorder=4)
    c.line([px0, px1], [py0, py0], color=S.BASELINE, lw=0.6)
    x0t, xt = float(xm(u[i_0])), float(xm(u[i_t]))
    c.curve(
        "x0_t",
        [x0t, x0t],
        [py0, ym(null[i_0]) + 0.03],
        color=S.BASE,
        lw=0.9,
        ls=(0, (1, 1.2)),
        zorder=4.2,
    )
    c.curve("x_t", [xt, xt], [py0, ym(mix[i_t]) + 0.04], color=S.HEDGE, lw=1.0, zorder=4.2)
    ylab = py0 - 0.105
    c.t(x0t, ylab, r"$x^0_t$ (arm 1)", fs=FS_S, ha="center", color=S.INK_2)
    c.t(xt + 0.01, ylab, r"$x_t$", fs=FS_S, ha="left", color=S.HEDGE)
    c.t(xr, ylab, "schematic", fs=FS_S, ha="right", color=S.MUTED, style="italic")
    kb = int(np.searchsorted(u, 0.27))
    CLEAR.append(
        c.t(float(xm(u[kb])), bl(float(ym(null[kb] * 0.45))), r"$\beta$", fs=FS, ha="center")
    )

    # Direct labels: the two parts of the mixture by leaders to where they part from it.
    y_row = py1 - 0.05
    for s, ha, xa, ua, part, col in (
        (r"$(1-\Pi_t)f_{0,t}$", "left", px0, 0.39, null, S.BASE),
        (r"$\Sigma\,\pi_{jk,t}\,g_{jk,t}$", "right", px1, 0.53, hyp, S.HYP[NAMED]),
    ):
        art = c.t(xa, bl(y_row, FS_S), s, fs=FS_S, ha=ha, color=col)
        CLEAR.append(art)
        e = c.extent(art)
        k = int(np.searchsorted(u, ua))
        xe, ye = float(xm(u[k])), float(ym(part[k]))
        xs = e[0] + 0.7 * (e[2] - e[0]) if ha == "left" else e[0] + 0.3 * (e[2] - e[0])
        c.line([xs, xe], [e[1] - 0.012, ye], color=col, lw=0.5, zorder=4.3)
        c.dot(xe, ye, col, ms=2.2, z=4.4)
    km = int(np.argmax(mix))
    mix_lab = c.t(
        float(xm(u[km])) + 0.02,
        bl(float(ym(mix[km])) + 0.06, FS_S),
        "mixture",
        fs=FS_S,
        ha="left",
        color=S.HEDGE,
    )
    CLEAR.append(mix_lab)

    # The hedge equation.
    fy1 = py0 - 0.15
    fy0 = fy1 - 0.47
    c.panel("hedge formula", xi, fy0, xr, fy1, S.tint(S.HEDGE, 0.08), S.tint(S.HEDGE, 0.45))
    lx = xi + 0.045
    c.t(lx, bl(fy1 - 0.075, FS_S), r"$\beta = p/(p+h)$ quantile of the mixture:", fs=FS_S)
    c.t(lx, bl(fy1 - 0.178, FS_S), r"$x_t=\inf\{x:(1-\Pi_t)F_{0,t}(x+P_t)$", fs=FS_S)
    c.t(
        lx + 0.14,
        bl(fy1 - 0.28, FS_S),
        r"$+\Sigma_{j,k}\,\pi_{jk,t}G_{jk,t}(x+P_t)\geq\beta\}$",
        fs=FS_S,
    )
    c.t(lx, bl(fy1 - 0.39, FS_S), r"$q_t=\min(\max(0,\lceil x_t-I_t\rceil),C_t,\hat C_t)$", fs=FS_S)

    # Nothing live: arm 1.
    by0 = C_Y0 + 0.045
    by1 = by0 + 0.16
    c.panel("arm 1", xi, by0, xr, by1, S.tint(S.BASE, 0.12), S.tint(S.BASE, 0.6))
    c.t(
        x + w / 2,
        bl((by0 + by1) / 2, FS_S),
        r"nothing live: $q_t$ is arm 1's, bit for bit",
        fs=FS_S,
        ha="center",
    )
    c.inside(None)
    assert by1 < fy0 - 0.03, "the arm 1 chip runs into the formula"
    return {"u": u, "f0": f0, "i_0": i_0, "i_t": i_t, "beta": beta}


# -- (e) the guarantees ----------------------------------------------------------------------


def strip_guarantees(c: Canvas) -> None:
    """The guarantees as Section VI states them; only the exposure bound needs P_0."""
    top = card(
        c,
        "strip e",
        X0,
        G_Y0,
        X1 - X0,
        G_Y1 - G_Y0,
        S.FRAME,
        title("(e) Guarantees"),
        body=S.tint(S.FRAME, 0.07),
        strip=G_STRIP,
    )
    c.inside("strip e", X0 + 0.02, G_Y0 + 0.015, X1 - 0.02, top - 0.01)
    gap = 0.07
    head_kw = {"fontweight": "bold"}
    grey_kw = {"color": S.INK_2}
    cols = [
        (
            [
                ("Exposure", FS, head_kw),
                (r"under $\mathbb{P}_0$: known null, registered arrival law", FS_S, grey_kw),
            ],
            [
                (
                    None,
                    r"$\mathbb{E}_0[\Pi_\sigma] \leq A$ at every stopping time $\sigma$ of "
                    r"$(\mathcal{F}_{t-1})$,",
                ),
                (None, "for any model output, adversarial included"),
            ],
        ),
        (
            [("Odds regret", FS, head_kw)],
            [
                (None, r"$c_{F_0}(x_t)-c_{F_0}(x^0_t) \leq \Pi_t\,V_t/(1-\Pi_t)$"),
                (None, "one-period newsvendor surrogate"),
            ],
        ),
        (
            [
                ("Evidence, not validity", FS, head_kw),
                (r"both against $\lambda=1$", FS_S, grey_kw),
            ],
            [
                ("check", r"named: $+\log 3.25$ nats"),
                ("cross", r"wrong or missing family: $-\log 4$ nats"),
            ],
        ),
    ]
    glyph = 0.1
    widths = []
    for head, lines in cols:
        wl = [c.width(s, fs=FS_S) + (glyph if g else 0.0) for g, s in lines]
        widths.append(max(c.runs_width(head, gap), *wl))
    inner0, inner1 = X0 + 0.12, X1 - 0.12
    sep = (inner1 - inner0 - sum(widths)) / (len(widths) - 1)
    ys = (top - 0.1, top - 0.205, top - 0.305)
    x0 = inner0
    for i, ((head, lines), wd) in enumerate(zip(cols, widths, strict=True)):
        cx = x0 + wd / 2
        hw = c.runs_width(head, gap)
        arts = c.runs(cx - hw / 2, ys[0], head, gap)
        HEADS.append((head[0][0], arts, x0, x0 + wd))
        for (g, s), yy in zip(lines, ys[1:], strict=True):
            lw_ = c.width(s, fs=FS_S) + (glyph if g else 0.0)
            xs = cx - lw_ / 2
            if g == "check":
                c.check(xs, yy + 0.022, s=0.06, lw=1.1)
            elif g == "cross":
                c.cross(xs + 0.005, yy + 0.022, s=0.045, lw=1.1)
            c.t(xs + (glyph if g else 0.0), yy, s, fs=FS_S)
        if i:
            xv = x0 - sep / 2
            c.line([xv, xv], [G_Y0 + 0.05, top - 0.05], color=S.tint(S.FRAME, 0.75), lw=0.7)
        x0 += wd + sep
    c.inside(None)


# -- checks ----------------------------------------------------------------------------------


def _layout_problems(c: Canvas) -> list[str]:
    """Texts under 6.5 pt, outside the frame or their box, overlapping, or on a curve."""
    c.fig.canvas.draw()
    bad: list[str] = []
    boxes = []
    for art in c.ax.texts:
        if not art.get_text().strip():
            continue
        if art.get_fontsize() < FS_S - 1e-9:
            bad.append(f"text below 6.5 pt {art.get_text()!r}")
        ext = c.extent(art)
        boxes.append((art.get_text(), ext))
        own = c.owner.get(id(art))
        if own is not None:
            name, (a0, b0, a1, b1) = own
            x0, y0, x1, y1 = ext
            if not (x0 >= a0 - 1e-3 and x1 <= a1 + 1e-3 and y0 >= b0 - 1e-3 and y1 <= b1 + 1e-3):
                box = tuple(round(float(v), 3) for v in ext)
                bad.append(f"text {art.get_text()!r} leaves {name}: {box} vs {own[1]}")
    fx, fy = FRAME_PAD * W + 0.03, FRAME_PAD * H + 0.02
    for s, (x0, y0, x1, y1) in boxes:
        if not (x0 >= fx and y0 >= fy and x1 <= W - fx and y1 <= H - fy):
            bad.append(f"text outside the frame {s!r}")
    tol = 0.004  # inches
    for i, (s, a) in enumerate(boxes):
        for u, b in boxes[i + 1 :]:
            ox = min(a[2], b[2]) - max(a[0], b[0])
            oy = min(a[3], b[3]) - max(a[1], b[1])
            if ox > tol and oy > tol:
                bad.append(f"overlapping text {s!r} and {u!r}")
    for art in CLEAR:
        x0, y0, x1, y1 = c.extent(art)
        for name, xs, ys in CURVES:
            xx = np.interp(np.linspace(0, 1, 400), np.linspace(0, 1, len(xs)), xs)
            yy = np.interp(np.linspace(0, 1, 400), np.linspace(0, 1, len(ys)), ys)
            hit = (xx > x0 - tol) & (xx < x1 + tol) & (yy > y0 - tol) & (yy < y1 + tol)
            if hit.any():
                bad.append(f"text {art.get_text()!r} lies on the curve {name!r}")
    return bad


def _union(c: Canvas, arts) -> tuple[float, float, float, float]:
    exts = [c.extent(a) for a in arts]
    return (
        min(e[0] for e in exts),
        min(e[1] for e in exts),
        max(e[2] for e in exts),
        max(e[3] for e in exts),
    )


def _assert_titles(c: Canvas) -> None:
    """Every panel title is centred over its card and fits its header strip."""
    assert [t[0] for t in TITLES] == ["card a", "card b", "card c", "card d", "strip e"]
    for name, arts, x0, y0, x1, y1 in TITLES:
        a0, b0, a1, b1 = _union(c, arts)
        assert abs((a0 + a1) / 2 - (x0 + x1) / 2) < 0.005, f"title of {name} not centred"
        assert a0 > x0 + 0.04 and a1 < x1 - 0.04, f"title of {name} too wide"
        assert b0 > y0 + 0.01 and b1 < y1 - 0.01, f"title of {name} leaves its strip"
    assert len(HEADS) == 3
    for name, arts, x0, x1 in HEADS:
        a0, _, a1, _ = _union(c, arts)
        assert abs((a0 + a1) / 2 - (x0 + x1) / 2) < 0.005, f"heading {name!r} not centred"


def _assert_content(c: Canvas, cert: dict, hedge: dict) -> None:
    """The printed weights and nats follow from the registered constants; plots are sane."""
    lam, n_h = Fraction(LAMBDA).limit_denominator(), len(HYPS)
    assert lam == Fraction(1, 4)
    assert lam / n_h == Fraction(1, 16) and lam / n_h + 1 - lam == Fraction(13, 16)
    assert abs(math.log(float(lam + (1 - lam) * n_h)) - math.log(3.25)) < 1e-12
    assert abs(math.log(float(1 / lam)) - math.log(4)) < 1e-12
    texts = [t.get_text() for t in c.ax.texts]
    joined = " | ".join(texts)
    for s in (r"$\lambda = 1/4$", r"$-\log 4$", r"$+\log 3.25$"):
        assert s in joined, s
    assert texts.count(r"$13/16$") == 1 and texts.count(r"$1/16$") == n_h - 1
    assert joined.count("schematic") == 2, "both schematic plots must say so"
    stripped = re.sub(r"\$[^$]*\$", "", joined).replace("arm 1", "")
    nums = re.findall(r"\d[\d,.]*\d|\d", stripped)
    # 0 is log E at the e-processes' start (the y tick in (c)); 5 the pseudo-observations.
    assert sorted(nums) == ["0", "5"], f"numbers outside the registered constants: {nums}"
    for k in HYPS:
        assert k in texts, f"hypothesis {k} missing"
    for key in ("shock_family", "direction", "onset_window"):
        assert key in texts, f"ShockSpec field {key} missing"
    # The named hypothesis's path is the one that rises; the others end below one.
    paths = cert["paths"]
    assert paths[NAMED][-1] == max(p[-1] for p in paths.values()) and paths[NAMED][-1] > 2
    assert all(p[-1] < 0 for k, p in paths.items() if k != NAMED)
    # beta > 1/2: arm 1's target sits right of the null's mode, and x_t right of it.
    u, f0 = hedge["u"], hedge["f0"]
    assert hedge["beta"] > 0.5
    assert u[hedge["i_0"]] > u[int(np.argmax(f0))] + 0.05
    assert hedge["i_t"] > hedge["i_0"]


def render(out_dir: Path | None = None) -> None:
    for registry in (TITLES, HEADS, CURVES, CLEAR):
        registry.clear()
    S.use_style(font_size=FS)
    fig = plt.figure(figsize=(W, H), dpi=DPI)
    S.rounded_frame(fig, pad=FRAME_PAD, lw=1.1)
    c = Canvas(fig)
    xs = [X0]
    for wd in WIDTHS[:-1]:
        xs.append(xs[-1] + wd + GAP)
    assert abs(xs[-1] + WIDTHS[-1] - X1) < 1e-6, xs[-1] + WIDTHS[-1] - X1
    card_spec(c, xs[0], WIDTHS[0])
    card_prior(c, xs[1], WIDTHS[1])
    cert = card_certify(c, xs[2], WIDTHS[2])
    hedge = card_hedge(c, xs[3], WIDTHS[3])
    ya = C_Y0 + 0.56 * (C_Y1 - C_Y0)
    for i in range(3):
        a0 = xs[i] + WIDTHS[i] + 0.022
        c.block_arrow(a0, a0 + GAP - 0.044, ya, S.HEDGE)
    strip_guarantees(c)
    problems = _layout_problems(c)
    if "--draft" in sys.argv:
        print("\n".join(problems) or "no layout problems")
    else:
        assert not problems, "\n".join(problems)
        _assert_titles(c)
        _assert_content(c, cert, hedge)
    S.save(fig, NAME, out_dir)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--draft"]
    render(Path(args[0]) if args else None)
    print(f"rendered {NAME}")
