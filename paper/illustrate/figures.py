#!/usr/bin/env python3
"""Render the paper's figures into ../figures/.

Every figure in the paper is produced by a function registered in FIGURES.
Each renderer writes two files with the same base name:

  figures/<name>.pdf   vector output, the one \\includegraphics picks up
  figures/<name>.png   300 dpi raster preview

Usage (from anywhere; paths resolve relative to this file):

  python3 illustrate/figures.py                 # render every figure
  python3 illustrate/figures.py fig1_overview   # render one figure by name
  python3 illustrate/figures.py --list          # list registered figures

Conventions:
  * One function per figure, named after the figure file it renders.
  * Figure data lives beside this script in illustrate/data/ (JSON or CSV
    sidecars), never inline; figures are regenerated from data, not edited.
  * Sizing follows the IEEE two-column grid: a column is 3.5 in wide and the
    full text width is 7.16 in; label text is 8 pt serif per IEEE guidance.

Colour, and why there is so little of it. These figures are printed, often in
black and white, so colour never carries identity on its own: every coloured
path is also a distinct line style, and every coloured band is also labelled.
Two accents only, and each one means the same thing in every figure:

  EVIDENCE (blue)  the statistical path: the e-process, its threshold, the gate
  CONTROL (orange) the control path: the compiler, the configuration, the order

Everything else is neutral grey chrome. The pair validates clear of the
colour-vision-deficiency and normal-vision floors on a light surface
(worst-pair CVD dE 24.7 protan, normal dE 33.6).
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle

SCRIPT_DIR = Path(__file__).resolve().parent
FIGURES_DIR = SCRIPT_DIR.parent / "figures"
DATA_DIR = SCRIPT_DIR / "data"

SINGLE_COLUMN_IN = 3.5   # IEEE column width
DOUBLE_COLUMN_IN = 7.16  # IEEE full text width

# --- the palette (see the module docstring) ---------------------------------
EVIDENCE = "#2a78d6"   # the e-process, its threshold, the gate
CONTROL = "#eb6834"    # the compiler, the configuration, the order
INK = "#1a1a1a"
MUTED = "#5c5c5c"
RULE = "#8c8c8c"
FILL_PLAIN = "#f4f4f4"  # ordinary stage
FILL_STRONG = "#e4e4e4"  # the stage the figure is about
PENDING_RED = "#c0392b"

mpl.rcParams.update(
    {
        "font.family": "serif",
        "font.size": 8,             # IEEE figure-label size
        "mathtext.fontset": "stix",
        "axes.linewidth": 0.6,
        "lines.linewidth": 1.0,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.02,
        "text.color": INK,
        "axes.edgecolor": RULE,
        "axes.labelcolor": INK,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "xtick.labelsize": 7,
        "ytick.labelsize": 7,
    }
)


def _finish(fig: plt.Figure, name: str) -> None:
    """Write one figure to figures/ as PDF plus a 300 dpi PNG preview."""
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    pdf_path = FIGURES_DIR / f"{name}.pdf"
    png_path = FIGURES_DIR / f"{name}.png"
    fig.savefig(pdf_path)
    fig.savefig(png_path, dpi=300)
    plt.close(fig)
    print(f"rendered {pdf_path.relative_to(SCRIPT_DIR.parent)} "
          f"and {png_path.relative_to(SCRIPT_DIR.parent)}")


# --- small drawing helpers ---------------------------------------------------
# Diagram axes work in inches: xlim and ylim match the axes rectangle exactly,
# so a width of 0.9 in the data is 0.9 inches on the page and rounded corners
# keep the same radius everywhere.

def _diagram_axes(fig, rect_in, size_in):
    """An invisible axes whose data units are inches."""
    w_in, h_in = size_in
    x0, y0, w, h = rect_in
    ax = fig.add_axes([x0 / w_in, y0 / h_in, w / w_in, h / h_in])
    ax.set_xlim(0, w)
    ax.set_ylim(0, h)
    ax.set_aspect("equal")
    ax.axis("off")
    return ax


def _box(ax, x, y, w, h, lines, *, fill=FILL_PLAIN, edge=RULE, lw=0.7,
         fontsize=6.6, color=INK, weight="normal", zorder=3):
    """A rounded box centred text block. x, y is the lower-left corner."""
    ax.add_patch(
        FancyBboxPatch(
            (x, y), w, h,
            boxstyle="round,pad=0,rounding_size=0.035",
            linewidth=lw, edgecolor=edge, facecolor=fill, zorder=zorder,
        )
    )
    ax.text(x + w / 2, y + h / 2, "\n".join(lines), ha="center", va="center",
            fontsize=fontsize, color=color, fontweight=weight,
            linespacing=1.35, zorder=zorder + 1)
    return (x, y, w, h)


def _arrow(ax, p0, p1, *, color=RULE, lw=0.8, style="-|>", ls="-",
           connectionstyle="arc3,rad=0", zorder=2, ms=5.5):
    ax.add_patch(
        FancyArrowPatch(
            p0, p1, arrowstyle=style, mutation_scale=ms, linewidth=lw,
            color=color, linestyle=ls, connectionstyle=connectionstyle,
            shrinkA=0, shrinkB=0, zorder=zorder,
        )
    )


def _elbow(ax, pts, *, color=RULE, lw=0.8, ls="-", zorder=2, ms=5.5):
    """A right-angle polyline with the arrowhead on its final segment."""
    ax.plot([p[0] for p in pts[:-1]], [p[1] for p in pts[:-1]], color=color,
            lw=lw, ls=ls, zorder=zorder, solid_joinstyle="miter")
    _arrow(ax, pts[-2], pts[-1], color=color, lw=lw, ls=ls, zorder=zorder, ms=ms)


def _brace_label(ax, x0, x1, y, text, *, color=INK, fontsize=7.2, drop=0.055):
    """A flat bracket above a span of the pipeline, with a word over it."""
    ax.plot([x0, x0, x1, x1], [y - drop, y, y, y - drop],
            color=color, linewidth=0.7, solid_joinstyle="miter", zorder=2)
    ax.text((x0 + x1) / 2, y + 0.045, text, ha="center", va="bottom",
            fontsize=fontsize, color=color, fontweight="bold")


# =============================================================================
# Figure 1 - the overview, for the introduction
# =============================================================================

def fig1_overview() -> None:
    """Figure 1. The whole idea in one picture, then the running episode.

    Panel (a) is the handshake: a shared trigger decides WHEN the model is
    consulted, a closed schema decides WHAT it may say, and an anytime-valid
    e-process decides WHETHER the answer touches an order. The gate is drawn as
    a valve rather than an arrow because that is the point of the figure: the
    compiled configuration is computed immediately and flows only after
    evidence gathered strictly after tau_j drives E above 1/alpha_j. The dashed
    path is the baseline configuration, live until then. The dotted return is
    what makes fact (F1) load-bearing rather than decorative, since the
    controller's own orders shape the observations the test consumes.

    Panel (b) walks the running episode along the same colours: the carrier
    suspension arrives as text, the hypothesis is frozen at tau_1, only periods
    after tau_1 count as evidence, and the compiled configuration goes live at
    the crossing and not before. The panel is a SCHEMATIC of the mechanism. No
    measured quantity appears in it; the measured frontier is Fig. 3.
    """
    W = DOUBLE_COLUMN_IN
    H_A = 1.62          # panel (a), diagram inches
    H_PLOT = 1.16       # panel (b), the e-process staircase
    H_BAND = 0.30       # panel (b), the live-configuration band
    H = H_A + 0.30 + H_PLOT + H_BAND + 0.46

    fig = plt.figure(figsize=(W, H))

    # ---------------- panel (a): the handshake -------------------------------
    ax = _diagram_axes(fig, (0, H - H_A, W, H_A), (W, H))

    ymid, bh = 0.72, 0.40
    src_w = 0.74
    # One row of stages, left to right. The widths and the gap are chosen so the
    # row plus the outgoing q_t arrow ends exactly at the text width: anything
    # drawn past it would widen the tight bounding box and shrink the whole
    # figure when LaTeX scales it back to \textwidth.
    widths = {"trig": 0.70, "llm": 0.70, "spec": 0.92, "comp": 0.84,
              "gate": 0.98, "ctrl": 0.82}
    gap = 0.176
    x = 0.0
    xs = {}
    xs["src"] = x
    x += src_w + gap
    for key in ("trig", "llm", "spec", "comp", "gate", "ctrl"):
        xs[key] = x
        x += widths[key] + gap
    out_x = x  # where the q_t arrow starts

    alert = _box(ax, xs["src"], ymid + 0.055, src_w, bh - 0.02,
                 ["operational", "alert"])
    tele = _box(ax, xs["src"], ymid - 0.44, src_w, bh - 0.02,
                ["demand", "telemetry"])
    trig = _box(ax, xs["trig"], ymid - 0.20, widths["trig"], bh,
                ["trigger", r"$\tau_j$"])
    llm = _box(ax, xs["llm"], ymid - 0.20, widths["llm"], bh,
               ["language", "model"])
    spec = _box(ax, xs["spec"], ymid - 0.20, widths["spec"], bh,
                [r"$\mathrm{\mathsf{ShockSpec}}$", r"frozen at $\tau_j$"],
                fill=FILL_STRONG, edge=INK, lw=1.0)
    comp = _box(ax, xs["comp"], ymid - 0.20, widths["comp"], bh,
                ["compiler", "1 of 72"], fill=FILL_PLAIN, edge=CONTROL, lw=0.9)
    gate = _box(ax, xs["gate"], ymid - 0.20, widths["gate"], bh,
                [r"$e$-process gate", r"$E_{j,t}\geq 1/\alpha_j$"],
                fill=FILL_STRONG, edge=EVIDENCE, lw=1.2)
    ctrl = _box(ax, xs["ctrl"], ymid - 0.20, widths["ctrl"], bh,
                ["capped", "base-stock"])

    def right(b):
        return (b[0] + b[2], b[1] + b[3] / 2)

    def left(b):
        return (b[0], b[1] + b[3] / 2)

    # the spine
    _arrow(ax, right(alert), (trig[0], ymid + 0.06))
    _arrow(ax, right(tele), (trig[0], ymid - 0.06))
    for a, b in ((trig, llm), (llm, spec), (spec, comp)):
        _arrow(ax, right(a), left(b))
    _arrow(ax, right(comp), left(gate), color=CONTROL, lw=1.0)
    _arrow(ax, right(gate), left(ctrl), color=CONTROL, lw=1.0)
    _arrow(ax, right(ctrl), (W - 0.17, ymid), color=CONTROL, lw=1.0)
    ax.text(W - 0.15, ymid, r"$q_t$", ha="left", va="center",
            fontsize=7.6, color=CONTROL, fontweight="bold")

    # the gate is a valve, not an arrow
    gx, gy = gate[0] + gate[2] / 2, gate[1] + gate[3]
    ax.plot([gx - 0.09, gx + 0.09], [gy + 0.085, gy + 0.085],
            color=EVIDENCE, lw=1.1, zorder=5)
    ax.plot([gx, gx], [gy, gy + 0.085], color=EVIDENCE, lw=1.1, zorder=5)

    # the baseline bypass, live while the gate is closed
    by = ymid + 0.36
    ax.plot([comp[0] + comp[2] / 2, comp[0] + comp[2] / 2, ctrl[0] + ctrl[2] / 2,
             ctrl[0] + ctrl[2] / 2],
            [ymid + 0.20, by, by, ymid + 0.20],
            color=CONTROL, lw=0.9, ls=(0, (3.2, 2.0)), zorder=2,
            solid_joinstyle="miter")
    _arrow(ax, (ctrl[0] + ctrl[2] / 2, by - 0.10),
           (ctrl[0] + ctrl[2] / 2, ymid + 0.20), color=CONTROL, lw=0.9,
           ls=(0, (3.2, 2.0)))
    ax.text((comp[0] + comp[2] / 2 + ctrl[0] + ctrl[2] / 2) / 2, by + 0.035,
            "baseline configuration, live until activation",
            ha="center", va="bottom", fontsize=6.3, color=CONTROL)

    # the closed loop: our own orders shape the observations the test consumes
    fy = ymid - 0.60
    ax.plot([W - 0.17, W - 0.17, tele[0] + src_w / 2, tele[0] + src_w / 2],
            [ymid - 0.10, fy, fy, tele[1]],
            color=MUTED, lw=0.7, ls=(0, (1.0, 1.6)), zorder=1,
            solid_joinstyle="miter")
    _arrow(ax, (tele[0] + src_w / 2, fy + 0.10), (tele[0] + src_w / 2, tele[1]),
           color=MUTED, lw=0.7, ls=(0, (1.0, 1.6)))
    ax.text((W - 0.17 + tele[0] + src_w / 2) / 2, fy - 0.025,
            r"realized $Y_{t+1}$ — it feeds the telemetry and the evidence path alike",
            ha="center", va="top", fontsize=6.3, color=MUTED)

    # the three separable decisions, which is the paper's whole thesis
    top = ymid + 0.63
    _brace_label(ax, trig[0], trig[0] + trig[2], top, "WHEN")
    _brace_label(ax, llm[0], spec[0] + spec[2], top, "WHAT")
    _brace_label(ax, gate[0], gate[0] + gate[2], top, "WHETHER")

    ax.text(0.01, ymid + 0.63, "(a)", ha="left", va="bottom", fontsize=7.6,
            fontweight="bold")
    ax.text(trig[0] + trig[2] / 2, ymid - 0.245, "refractory 5, $\\leq 2$",
            ha="center", va="top", fontsize=6.0, color=MUTED)
    ax.text(gate[0] + gate[2] / 2, ymid - 0.245,
            r"evidence from $\tau_j{+}1$ only", ha="center", va="top",
            fontsize=6.0, color=EVIDENCE)
    ax.text(spec[0] + spec[2] / 2, ymid - 0.245,
            "closed vocabulary, no order", ha="center", va="top",
            fontsize=6.0, color=MUTED)

    # ---------------- panel (b): the running episode -------------------------
    left_m, right_m = 0.52 / W, 0.035
    plot_bottom = (H_BAND + 0.42) / H
    ax_e = fig.add_axes([left_m, plot_bottom, 1 - left_m - right_m, H_PLOT / H])
    ax_b = fig.add_axes([left_m, 0.40 / H, 1 - left_m - right_m, H_BAND / H])

    alpha = 0.05
    thresh = 2.0 / alpha                      # 1/alpha_1 with alpha_1 = alpha/2
    t0, t1 = -4, 12
    # A schematic wealth path: flat before the freeze, then arrivals that do not
    # happen push the ratio up until it clears the threshold.
    path = {0: 1.0, 1: 1.6, 2: 1.3, 3: 3.1, 4: 6.0, 5: 5.2, 6: 14.0,
            7: 31.0, 8: 74.0, 9: 88.0, 10: 96.0, 11: 101.0, 12: 104.0}
    ts = sorted(path)
    cross = next(t for t in ts if path[t] >= thresh)

    ax_e.set_xlim(t0, t1)
    ax_e.set_yscale("log")
    ax_e.set_ylim(0.55, 420)

    # the periods that motivated the hypothesis, and are never counted
    ax_e.add_patch(Rectangle((t0, 0.55), -t0, 420, facecolor="#ebebeb",
                             edgecolor="none", zorder=0))
    ax_e.text(t0 + 0.12, 230, "periods that motivated the claim\n"
              "— never counted as evidence", fontsize=6.0, color=MUTED,
              ha="left", va="top", linespacing=1.3)

    ax_e.axhline(thresh, color=EVIDENCE, lw=0.9, ls=(0, (4.0, 2.2)), zorder=2)
    ax_e.text(t1 - 0.12, thresh * 1.18, r"Ville threshold $1/\alpha_1 = 2/\alpha$",
              fontsize=6.3, color=EVIDENCE, ha="right", va="bottom")

    ax_e.step(ts, [path[t] for t in ts], where="post", color=EVIDENCE, lw=1.3,
              zorder=4, solid_joinstyle="miter")
    ax_e.plot([t0, 0], [1.0, 1.0], color=EVIDENCE, lw=1.0, ls=":", zorder=3)
    ax_e.plot([cross], [path[cross]], marker="o", ms=4.4, color=EVIDENCE,
              markeredgecolor="white", markeredgewidth=0.7, zorder=5)
    ax_e.text(cross + 0.22, path[cross] * 2.9, "activation", fontsize=6.6,
              color=EVIDENCE, fontweight="bold", ha="left", va="bottom")

    for x_ in (0, cross):
        ax_e.axvline(x_, color=INK if x_ == 0 else EVIDENCE, lw=0.7,
                     ls=(0, (2.0, 1.8)), zorder=1)

    ax_e.text(0.16, 300, r"$\tau_1$: alert read, $\mathrm{\mathsf{ShockSpec}}$ frozen"
              "\n" r"$\mathtt{shipment\_loss}$, arrival stream, duration $1\!-\!3$",
              fontsize=6.2, color=INK, ha="left", va="top", linespacing=1.35)

    ax_e.set_ylabel(r"$E_{1,t}$", fontsize=7.4, labelpad=1.5)
    ax_e.set_yticks([1, 10, 100])
    ax_e.set_yticklabels(["1", "10", "100"])
    ax_e.tick_params(length=2.2, width=0.6, pad=1.6)
    ax_e.set_xticklabels([])
    ax_e.tick_params(axis="x", length=0)
    for side in ("top", "right"):
        ax_e.spines[side].set_visible(False)
    ax_e.text(-0.072, 1.02, "(b)", transform=ax_e.transAxes, ha="left",
              va="bottom", fontsize=7.6, fontweight="bold")
    ax_e.text(1.0, 1.02, "schematic: mechanism only, no measured quantity",
              transform=ax_e.transAxes, ha="right", va="bottom", fontsize=6.0,
              color=MUTED, style="italic")

    # the band: which configuration the controller is actually running
    ax_b.set_xlim(t0, t1)
    ax_b.set_ylim(0, 1)
    ax_b.add_patch(Rectangle((t0, 0.08), cross - t0, 0.84, facecolor="white",
                             edgecolor=RULE, lw=0.7, hatch="////", zorder=2))
    ax_b.add_patch(Rectangle((cross, 0.08), t1 - cross, 0.84,
                             facecolor=CONTROL, edgecolor=CONTROL, lw=0.7,
                             alpha=0.85, zorder=2))
    ax_b.text((t0 + cross) / 2, 0.5, "baseline configuration", ha="center",
              va="center", fontsize=6.3, color=INK, zorder=4)
    ax_b.text((cross + t1) / 2, 0.5,
              r"compiled configuration: $\gamma\!:\,1\rightarrow0.5$",
              ha="center", va="center", fontsize=6.3, color="white",
              fontweight="bold", zorder=4)
    ax_b.set_xticks([t0, 0, cross, t1])
    ax_b.set_xticklabels([r"$\tau_1{-}4$", r"$\tau_1$", r"$\tau_1{+}%d$" % cross,
                          r"$\tau_1{+}12$"])
    ax_b.set_yticks([])
    ax_b.tick_params(length=2.2, width=0.6, pad=1.6)
    for side in ("top", "right", "left"):
        ax_b.spines[side].set_visible(False)
    ax_b.set_xlabel("period", fontsize=7.0, labelpad=1.0)
    ax_b.text(-0.012, 0.5, "controller", transform=ax_b.transAxes, ha="right",
              va="center", fontsize=6.6, color=MUTED)

    _finish(fig, "fig1_overview")


# =============================================================================
# Figure 2 - the method, for Sections IV-VI
# =============================================================================

def fig2_method() -> None:
    """Figure 2. One key, two consumers.

    The typed hypothesis leaves the model once and is then read twice, by two
    machines that must not be allowed to disagree. Downward, the compiler turns
    it into one point of the registered 72-point grid and the controller acts on
    that point. Upward, the registry resolves the same key into the verifier
    construction that will test it. Drawing both branches off one key is the
    whole content of the figure: a hypothesis cannot be acted on under one
    reading and tested under another, and the gate is where the two branches
    meet again.
    """
    W, H = DOUBLE_COLUMN_IN, 3.10
    fig = plt.figure(figsize=(W, H))
    ax = _diagram_axes(fig, (0, 0, W, H), (W, H))

    ymid = 1.75
    up_y, dn_y = 2.48, 1.02

    # ---- the spec card ------------------------------------------------------
    card_x, card_w, card_y, card_h = 0.02, 1.66, 0.80, 1.90
    card_top = card_y + card_h
    ax.add_patch(FancyBboxPatch(
        (card_x, card_y), card_w, card_h,
        boxstyle="round,pad=0,rounding_size=0.04",
        linewidth=1.0, edgecolor=INK, facecolor=FILL_STRONG, zorder=3))
    ax.text(card_x + card_w / 2, card_top - 0.11,
            r"$\mathrm{\mathsf{ShockSpec}}\ h_j$", ha="center", va="top",
            fontsize=8.0, fontweight="bold", zorder=4)
    ax.text(card_x + card_w / 2, card_top - 0.30,
            r"frozen at $\tau_j$,  $\mathcal{F}_{\tau_j}$-measurable  (A4)",
            ha="center", va="top", fontsize=5.9, color=MUTED, zorder=4)
    ax.plot([card_x + 0.10, card_x + card_w - 0.10], [card_top - 0.42] * 2,
            color=RULE, lw=0.6, zorder=4)

    ax.text(card_x + 0.10, card_top - 0.50, "9 fields the model selects",
            ha="left", va="top", fontsize=6.1, fontweight="bold", zorder=4)
    for i, line in enumerate((
            r"$\mathtt{shock\_family}$   $\mathtt{target\_stream}$",
            r"$\mathtt{direction}$   $\mathtt{onset\_window}$",
            r"$\mathtt{magnitude\_bin}$   $\mathtt{persistence}$",
            r"$\mathtt{duration\_bin}$   $\mathtt{evidence\_refs}$",
            r"$\mathtt{prospective\_signature}$")):
        ax.text(card_x + 0.10, card_top - 0.645 - 0.135 * i, line,
                ha="left", va="top", fontsize=5.5, zorder=4)

    ax.plot([card_x + 0.10, card_x + card_w - 0.10], [card_y + 0.44] * 2,
            color=RULE, lw=0.6, ls=(0, (2, 2)), zorder=4)
    ax.text(card_x + 0.10, card_y + 0.37, "5 fields the system stamps",
            ha="left", va="top", fontsize=6.1, color=MUTED, fontweight="bold",
            zorder=4)
    ax.text(card_x + 0.10, card_y + 0.235,
            r"$\tau_j$, proposal index, model id,", ha="left", va="top",
            fontsize=5.5, color=MUTED, zorder=4)
    ax.text(card_x + 0.10, card_y + 0.115, "decoding hash, prompt hash",
            ha="left", va="top", fontsize=5.5, color=MUTED, zorder=4)
    ax.text(card_x + card_w / 2, card_y - 0.06,
            "no order, no threshold, no likelihood, no code",
            ha="center", va="top", fontsize=6.0, style="italic")

    # ---- the key ------------------------------------------------------------
    key_x, key_w = 1.98, 1.16
    _box(ax, key_x, ymid - 0.24, key_w, 0.48,
         ["registered key", r"$(\mathtt{family},\ \mathtt{signature})$"],
         fill="white", edge=INK, lw=1.1, fontsize=6.3)
    _arrow(ax, (card_x + card_w, ymid), (key_x, ymid), color=INK, lw=1.0)
    ax.text(key_x + key_w / 2, ymid - 0.29, "(A3) closed selection space",
            ha="center", va="top", fontsize=5.9, color=MUTED)

    # ---- the two consumers, one box each ------------------------------------
    bx, bw, bh = 3.46, 2.34, 0.88
    for y_c, accent, title, sub, formula, note in (
        (up_y, EVIDENCE, "verifier registry",
         r"mixture ratio   $|$   forward recursion",
         r"$E_{j,t}=\prod_{r=\tau_j+1}^{t}\frac{p_{h_j,\theta}}{p_0}$",
         r"conditioned on $\mathcal{F}_{r-1},\,A_{r-1}$; starts at $\tau_j{+}1$"),
        (dn_y, CONTROL, "compiler",
         "total, pure, deterministic; no state, history or clock",
         r"$\mathrm{\mathsf{ControlConfig}}\ \ "
         r"(m,\ L_{\mathrm{eff}},\ \gamma,\ k)$",
         r"precedence: family, direction, magnitude, stream"),
    ):
        ax.add_patch(FancyBboxPatch(
            (bx, y_c - bh / 2), bw, bh,
            boxstyle="round,pad=0,rounding_size=0.04",
            linewidth=1.0, edgecolor=accent, facecolor=FILL_PLAIN, zorder=3))
        ax.text(bx + bw / 2, y_c + bh / 2 - 0.08, title, ha="center", va="top",
                fontsize=6.8, fontweight="bold", zorder=4)
        ax.text(bx + bw / 2, y_c + bh / 2 - 0.21, sub, ha="center", va="top",
                fontsize=5.9, color=MUTED, zorder=4)
        ax.text(bx + bw / 2, y_c - bh / 2 + 0.30, formula, ha="center",
                va="center", fontsize=6.4, zorder=4)
        ax.text(bx + bw / 2, y_c - bh / 2 + 0.09, note, ha="center",
                va="center", fontsize=5.4, color=MUTED, zorder=4)

    xe = key_x + key_w + 0.16
    _elbow(ax, [(key_x + key_w, ymid + 0.10), (xe, ymid + 0.10), (xe, up_y),
                (bx, up_y)], color=EVIDENCE, lw=1.0)
    _elbow(ax, [(key_x + key_w, ymid - 0.10), (xe, ymid - 0.10), (xe, dn_y),
                (bx, dn_y)], color=CONTROL, lw=1.0)
    ax.text(bx + bw / 2, up_y + bh / 2 + 0.04, "tested under", ha="center",
            va="bottom", fontsize=6.5, color=EVIDENCE, fontweight="bold")
    ax.text(bx + bw / 2, dn_y + bh / 2 + 0.04, "acted on under", ha="center",
            va="bottom", fontsize=6.5, color=CONTROL, fontweight="bold")

    # the 72-point grid, so "one of 72" is a picture rather than a number
    gx0, gy0 = bx + 0.10, 0.34
    for c in range(6):
        for r in range(4):
            sel = (c == 3 and r == 2)
            ax.plot(gx0 + c * 0.070, gy0 + r * 0.060, marker="s",
                    ms=3.6 if sel else 2.4,
                    color=CONTROL if sel else "#c4c4c4", zorder=4)
    ax.text(gx0 + 6 * 0.070 + 0.05, gy0 + 0.09,
            r"$6\,m \times 4\,L_{\mathrm{eff}} \times 3\,\gamma = 72$"
            "\nregistered points, one of which the claim names",
            ha="left", va="center", fontsize=5.9, color=MUTED, linespacing=1.4)

    # ---- the gate, where the branches meet ----------------------------------
    gate_x, gate_w, gate_h = 6.08, 0.80, 0.64
    _box(ax, gate_x, ymid - gate_h / 2, gate_w, gate_h,
         [r"$e$-process", "gate: open iff", r"$E_{j,t}\geq 1/\alpha_j$"],
         fill=FILL_STRONG, edge=EVIDENCE, lw=1.3, fontsize=6.2)
    gcx = gate_x + gate_w / 2
    _elbow(ax, [(bx + bw, up_y), (gcx, up_y), (gcx, ymid + gate_h / 2)],
           color=EVIDENCE, lw=1.0)
    _elbow(ax, [(bx + bw, dn_y), (gate_x - 0.17, dn_y), (gate_x - 0.17, ymid),
                (gate_x, ymid)], color=CONTROL, lw=1.0)
    _arrow(ax, (gate_x + gate_w, ymid), (W - 0.16, ymid), color=CONTROL, lw=1.1)
    ax.text(W - 0.14, ymid, r"$q_t$", ha="left", va="center", fontsize=7.6,
            color=CONTROL, fontweight="bold")
    ax.text(gcx, ymid - gate_h / 2 - 0.06, "Theorem 1 covers\nthis transition",
            ha="center", va="top", fontsize=5.9, color=EVIDENCE,
            linespacing=1.35)

    # ---- the sentence the figure exists to make -----------------------------
    ax.text(W / 2, 0.04,
            "One key, two consumers: a hypothesis cannot be acted on under one "
            "reading and tested under another.",
            ha="center", va="bottom", fontsize=7.0, style="italic")

    _finish(fig, "fig2_method")


# =============================================================================
# Figure 3 - the results slot
# =============================================================================

def fig3_frontier() -> None:
    """Figure 3. Reward against compute, the headroom figure.

    Horizontal axis: realized charged calls per episode. Vertical axis:
    stratum-weighted cumulative profit per episode, the primary endpoint, not
    the clipped normalized reward. Every arm is one marked point with a vertical
    error bar from the seed-level cluster bootstrap; the two horizontal rules
    are the arm 1 floor and the oracle ceiling, and the gap between them is the
    only space any arm can win in, which makes this the headroom figure as well.
    Arms 8, 9 and 10 sit at the same horizontal position by construction,
    because they share one physical call set, so the vertical spread among those
    three markers is exactly the effect of the activation stage.

    The sweep is still running. This renderer draws the real frame and the real
    arm positions on the calls axis, which are registered in advance, and leaves
    the profit axis empty: illustrate/data/frontier.csv carries one row per arm
    with an empty profit column. Fill that column and the figure completes with
    no other change.
    """
    with (DATA_DIR / "frontier.csv").open() as fh:
        body = [ln for ln in fh if not ln.lstrip().startswith("#")]
    rows = list(csv.DictReader(body))

    have_profit = [r for r in rows if r["profit"].strip()]

    fig, ax = plt.subplots(figsize=(SINGLE_COLUMN_IN, 2.25))
    calls = sorted({float(r["calls"]) for r in rows})
    ax.set_xlim(-2.5, 55)
    ax.set_ylim(0, 1)
    ax.set_xticks([0, 2, 10, 25, 50])
    ax.set_xlabel("realized charged calls per episode", fontsize=7.2,
                  labelpad=1.5)
    ax.set_ylabel("profit per episode", fontsize=7.2, labelpad=2.0)
    ax.set_yticks([])
    ax.grid(axis="x", color="#e6e6e6", lw=0.5)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.tick_params(length=2.2, width=0.6, pad=1.6)

    if have_profit:
        for r in have_profit:
            ax.errorbar(float(r["calls"]), float(r["profit"]),
                        yerr=[[float(r["profit"]) - float(r["ci_low"])],
                              [float(r["ci_high"]) - float(r["profit"])]],
                        fmt="o", ms=3.6, lw=0.8, capsize=1.6, color=EVIDENCE)
    else:
        # The arms whose call budget is already registered, marked on the axis
        # they are registered on, with the endpoint they are missing left blank.
        for c in calls:
            ax.plot([c], [0.02], marker="^", ms=3.0, color="#bdbdbd",
                    clip_on=False, zorder=3)
        ax.text(0.5, 0.56, "PENDING", transform=ax.transAxes, ha="center",
                va="center", fontsize=9.5, color=PENDING_RED,
                fontweight="bold")
        ax.text(0.5, 0.45,
                f"{len(rows)} arms and controls registered on the calls axis;\n"
                "the profit endpoint lands with the sweep",
                transform=ax.transAxes, ha="center", va="center",
                fontsize=6.4, color=PENDING_RED, linespacing=1.35)
        ax.text(0.5, -0.30, "grey marks: the registered call budget of each arm",
                transform=ax.transAxes, ha="center", va="top", fontsize=6.0,
                color=MUTED)

    _finish(fig, "fig3_frontier")


# Registry: figure name -> renderer. Add one entry per new figure.
FIGURES = {
    "fig1_overview": fig1_overview,
    "fig2_method": fig2_method,
    "fig3_frontier": fig3_frontier,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "names",
        nargs="*",
        help="figure names to render (default: all registered figures)",
    )
    parser.add_argument(
        "--list", action="store_true", help="list registered figures and exit"
    )
    args = parser.parse_args(argv)

    if args.list:
        for name in FIGURES:
            print(name)
        return 0

    unknown = [n for n in args.names if n not in FIGURES]
    if unknown:
        parser.error(
            f"unknown figure(s): {', '.join(unknown)}; "
            f"registered: {', '.join(FIGURES)}"
        )

    for name in args.names or FIGURES:
        FIGURES[name]()
    return 0


if __name__ == "__main__":
    sys.exit(main())
