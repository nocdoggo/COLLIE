"""Figure 1 (fig:overview). Where agents break and what a residency contract preserves.

Conceptual diagram with no data and no numbers.

Panel (a) is a strip along an agent trajectory. At four context boundaries
(compaction, subagent handoff, tool-output pruning, session resume) the facts
of the task survive while one condition of use is lost. Each loss carries the
obligation type it violates.

Panel (b) is one constructed debugging handoff. The sender holds six artifacts
a_1 to a_6. A fluent summary and the packet R(K_t) produced under contract K_t
are drawn in detail. A check matrix also evaluates a full copy of the sender
inventory. The dashed row records an artifact omitted from R(K_t), and each
lightning mark names a boundary-replay intervention that tests an obligation.

The artifact texts match the worked example of Appendix B (tab:handoffexample).
Obligation colors are fixed across all figures and Table 1.

House style (supplements/research-writing-flow/assets/table-figure-style.md).
Bold panel tags, cards with a tinted header strip, a pastel body, and a
same-hue border for each group (sender, the two packets, the checks), zebra
rows, boundary stations on the trajectory line, and a rounded warm outer
frame. The height stays at 3.35 in, and every label lies inside the frame.

Output  figures/fig_overview.pdf and figures/fig_overview.png
Usage   python3 illustrate/fig_overview.py
"""

from __future__ import annotations

import re

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import (Arc, Ellipse, FancyArrowPatch, FancyBboxPatch,
                                Polygon, Rectangle)

import style as S

NAME = "fig_overview"

# Fixed obligation color mapping (shared with Table 1 and the other figures).
OBLIGATION_COLOR = {
    "exactness": S.BLUE,
    "scope": S.ORANGE,
    "source role": S.RED,
    "retrievability": S.AQUA,
    "freshness": S.YELLOW,
    "dependency": S.VIOLET,
}

FS = 7.0      # body text (pt)
FS_S = 6.5    # smallest text in the figure (pt)
FS_T = 7.5    # panel titles (pt)
PT = 1 / 72   # one point in inches

W, H = S.TEXT_WIDTH, 3.35
PANEL_A_H = 0.825  # height of the top strip (inches)
FRAME_PAD = 0.003  # outer frame inset (fraction of the figure)
FRAME_FILL = "#fffdf7"      # warm paper inside the outer frame
X0, X1 = 0.075, W - 0.075   # content bounds inside the frame (inches)
Y0 = 0.05                   # lowest content edge (inches)
STRIP = 0.14                # header strip height of a card (inches)


def tt(text: str) -> str:
    """Monospace span, escaped for LaTeX when usetex is active."""
    if plt.rcParams.get("text.usetex"):
        return r"\texttt{" + S.tex_escape(text) + "}"
    return text


def it(text: str) -> str:
    return r"\textit{" + text + "}" if plt.rcParams.get("text.usetex") else text


def bf(text: str) -> str:
    return r"\textbf{" + text + "}" if plt.rcParams.get("text.usetex") else text


def quoted(text: str) -> str:
    if plt.rcParams.get("text.usetex"):
        return "``" + text + "''"
    return "“" + text + "”"


# --- Panel (a) content ------------------------------------------------------
# (boundary type, [(lost condition, obligation it violates)])
BOUNDARIES = [
    ("compaction", [("rule paraphrased", "exactness")]),
    ("subagent handoff", [("edit scope dropped", "scope"),
                          ("tool text read as instruction", "source role")]),
    ("tool-output pruning", [("log dropped, no handle", "retrievability")]),
    ("session resume", [("diagnosis from an old commit reused", "freshness")]),
]


# --- Panel (b) content ------------------------------------------------------
def sender_rows():
    """Sender artifacts (index, text lines, tag, tag obligation)."""
    return [
        ("1", ["task + allowed path", tt("src/cache.py")], None, None),
        ("2", [tt("tests/test_cache.py"), tt("::test_expiry")], None, None),
        ("3", ["current diagnosis"], None, None),
        ("4", ["command log (long)"], None, None),
        ("5", ["diagnosis @", "incompatible commit"], "stale", "freshness"),
        ("6", ["tool text", quoted("also edit " + tt("config.py"))], "untrusted",
         "source role"),
    ]


# Packet regions and exclusion annotation (region, obligation, intervention).
REGIONS = [
    ("instruction/state", "scope", "strip scope"),
    ("exact", "exactness", r"paraphrase $a_2$"),
    ("structured claim", "dependency", None),
    ("evidence pointer", "retrievability", "break pointer"),
    ("data-only", "source role", r"promote $a_6$"),
    ("excluded", "freshness", r"reinstate $a_5$"),
]

# Check matrix rows (label, artifact, obligation, summary, full copy, R(K_t)).
CHECKS = [
    ("exact id", "2", "exactness", False, True, True),
    ("scope", "1", "scope", False, True, True),
    ("evidence reachable", "4", "retrievability", False, True, True),
    ("source role", "6", "source role", False, False, True),
    ("freshness", "5", "freshness", True, False, True),
    ("within budget", None, None, True, False, True),
]
CHECK_COLUMNS = ["summary", "full copy", r"$R(K_t)$"]


class Canvas:
    """An axes in inch coordinates with text measurement and glyph helpers."""

    def __init__(self, fig, ax):
        self.fig, self.ax = fig, ax
        self.renderer = fig.canvas.get_renderer()

    def text(self, x, y, s, fs=FS, color=S.INK, ha="left", va="baseline", **kw):
        return self.ax.text(x, y, s, fontsize=fs, color=color, ha=ha, va=va,
                            zorder=kw.pop("zorder", 6), **kw)

    def width(self, s, fs=FS) -> float:
        t = self.ax.text(0, 0, s, fontsize=fs)
        bb = t.get_window_extent(self.renderer)
        t.remove()
        return bb.width / self.fig.dpi

    def height(self, s, fs=FS) -> float:
        t = self.ax.text(0, 0, s, fontsize=fs)
        bb = t.get_window_extent(self.renderer)
        t.remove()
        return bb.height / self.fig.dpi

    def extent(self, artist):
        bb = artist.get_window_extent(self.renderer)
        inv = self.ax.transData.inverted()
        (x0, y0), (x1, y1) = inv.transform([[bb.x0, bb.y0], [bb.x1, bb.y1]])
        return x0, y0, x1, y1

    def line(self, xs, ys, **kw):
        kw.setdefault("zorder", 3)
        self.ax.add_line(Line2D(xs, ys, **kw))

    def check(self, x, y, s=0.07, color=S.GREEN, lw=1.45):
        """Check mark with its left end at x, vertically centred on y."""
        pts = [(x, y + 0.02), (x + 0.33 * s, y - 0.3 * s), (x + s, y + 0.45 * s)]
        self.line(*zip(*pts), color=color, lw=lw, solid_capstyle="round",
                  solid_joinstyle="round", zorder=7)

    def cross(self, x, y, s=0.055, color=S.RED, lw=1.45):
        """Cross mark with its left end at x, vertically centred on y."""
        h = s / 2
        for (a, b) in (((x, y - h), (x + s, y + h)), ((x, y + h), (x + s, y - h))):
            self.line([a[0], b[0]], [a[1], b[1]], color=color, lw=lw,
                      solid_capstyle="round", zorder=7)

    def bolt(self, x, y, h=0.12, color=S.INK):
        """Lightning glyph centred at (x, y)."""
        w = 0.55 * h
        pts = [(0.62, 1.0), (0.05, 0.42), (0.42, 0.42), (0.28, 0.0),
               (0.95, 0.62), (0.56, 0.62), (0.80, 1.0)]
        verts = [(x + (px - 0.5) * w, y + (py - 0.5) * h) for px, py in pts]
        self.ax.add_patch(Polygon(verts, closed=True, fc=color, ec=S.INK, lw=0.45,
                                  joinstyle="round", zorder=7))

    def chip(self, x, y, s, color, fs=FS_S, fill_alpha=0.22, ha="left", pad=0.035,
             hf=1.3):
        """Rounded tag around text. x is the left (or right) edge, y the centre."""
        w = self.width(s, fs=fs)
        h = fs * PT * hf
        x0 = x if ha == "left" else x - w - 2 * pad
        self.ax.add_patch(FancyBboxPatch(
            (x0, y - h / 2), w + 2 * pad, h, boxstyle="round,pad=0,rounding_size=0.03",
            fc=S.tint(color, fill_alpha) if fill_alpha else S.SURFACE,
            ec=color, lw=0.7, zorder=5))
        self.text(x0 + pad, baseline(y, fs), s, fs=fs)
        return x0 + w + 2 * pad

    def box(self, x, y, w, h, fc, ec, lw=0.7, ls="-", r=0.04, z=2):
        patch = FancyBboxPatch(
            (x, y), w, h, boxstyle=f"round,pad=0,rounding_size={r}",
            fc=fc, ec=ec, lw=lw, ls=ls, zorder=z)
        self.ax.add_patch(patch)
        return patch

    def card(self, x, y, w, h, accent, title, *, body=S.SURFACE, strip_alpha=0.26,
             lw=0.8, r=0.045, z=2.0):
        """Group card with a tinted header strip, a body, and a same-hue border.

        The strip is clipped to the rounded outline, so its top corners follow
        the card. Returns the body patch, which later layers can clip to.
        """
        base = self.box(x, y, w, h, fc=body, ec="none", r=r, z=z)
        band = Rectangle((x, y + h - STRIP), w, STRIP, fc=S.tint(accent, strip_alpha),
                         ec="none", zorder=z + 0.1)
        self.ax.add_patch(band)
        band.set_clip_path(base)
        self.line([x, x + w], [y + h - STRIP] * 2, color=accent, lw=0.5, zorder=z + 0.2)
        self.box(x, y, w, h, fc="none", ec=accent, lw=lw, r=r, z=z + 0.6)
        self.text(x + 0.06, baseline(y + h - STRIP / 2, FS), title, fs=FS)
        return base

    def tag(self, x, y_top, s, color, fs=FS_T):
        """Bold panel tag centered at x with its frame's top at y_top."""
        pad = 0.28 * fs * PT
        h = self.height(bf(s), fs=fs)
        S.panel_tag(self.ax, s, color, x=x / W, y=(y_top - pad - h) / H,
                    ha="center", fontsize=fs)
        return y_top - h - 2 * pad


def baseline(yc, fs=FS):
    """Baseline that visually centres one line of text on height yc."""
    return yc - 0.3 * fs * PT


# ---------------------------------------------------------------------------
def panel_a(c: Canvas, top: float) -> None:
    tag_bot = c.tag((X0 + X1) / 2, top - 0.04,
                    "(a) A long-running agent crosses context boundaries",
                    S.NEUTRAL)

    nb_h = 0.15                # boundary station height
    y_tl = tag_bot - 0.03 - nb_h / 2   # timeline height
    pitch = 0.10               # line pitch below the timeline
    x_start, x_end = X0, X1
    guide = 0.035              # guide line offset from the station's left edge
    lead = 0.085               # marks start this far right of the station edge
    indent = 0.1               # text indent after a check or cross mark

    # Width of each boundary block (station on the line, marks and tags below).
    blocks = []
    for name, losses in BOUNDARIES:
        rows = ["facts kept"] + [loss for loss, _ in losses]
        body = max(c.width(r, fs=FS_S) for r in rows) + lead + indent + 0.02
        tags = sum(c.width(ob, fs=FS_S) + 0.12 for _, ob in losses) + lead
        name_w = c.width(name, fs=FS) + 0.12
        blocks.append((name, losses, max(body, tags, name_w)))
    total = sum(b[2] for b in blocks)
    gap = (x_end - x_start - total) / (len(blocks) - 1 + 0.25)

    # Timeline arrow and its label.
    c.ax.add_patch(FancyArrowPatch(
        (x_start, y_tl), (x_end, y_tl), arrowstyle="-|>,head_length=4.5,head_width=2.5",
        mutation_scale=1, lw=1.3, color=S.MUTED, zorder=3))
    c.text(x_end - 0.03, y_tl + 0.04, it("agent trajectory"), fs=FS_S, color=S.INK_2,
           ha="right")

    tx = x_start
    for name, losses, bw in blocks:
        n_rows = 2 + len(losses)
        # Boundary station on the trajectory line.
        nb_w = c.width(name, fs=FS) + 0.12
        c.box(tx, y_tl - nb_h / 2, nb_w, nb_h, fc=S.tint(S.NEUTRAL, 0.14), ec=S.NEUTRAL,
              lw=0.8, r=0.035, z=4)
        c.text(tx + 0.06, baseline(y_tl), name, fs=FS)
        c.line([tx + guide] * 2, [y_tl - nb_h / 2, y_tl - 0.05 - (n_rows - 0.35) * pitch],
               color=S.BASELINE, lw=0.8, zorder=2)

        # Below the timeline: the facts survive, a condition of use is lost.
        xt = tx + lead
        yc = y_tl - nb_h / 2 - 0.063
        c.check(xt, yc)
        c.text(xt + indent, baseline(yc, FS_S), "facts kept", fs=FS_S)
        for loss, _ in losses:
            yc -= pitch
            c.cross(xt + 0.008, yc)
            c.text(xt + indent, baseline(yc, FS_S), loss, fs=FS_S)
        yc -= pitch + 0.006
        xx = xt
        for _, ob in losses:
            xx = c.chip(xx, yc, ob, OBLIGATION_COLOR[ob]) + 0.05
        tx += bw + gap


def panel_b(c: Canvas, top: float) -> None:
    ax = c.ax
    y_top = top - 0.035
    tag_bot = c.tag((X0 + X1) / 2, y_top, "(b) A debugging handoff", S.BLUE)
    y_top = tag_bot - 0.03
    y_bot = Y0

    # Column geometry (inches).
    sx0, sw = X0, 1.40                    # sender column
    px0 = sx0 + sw + 0.18                 # packets column
    mx1 = X1                              # matrix right edge
    mw = 1.52
    mx0 = mx1 - mw
    pw = mx0 - 0.1 - px0

    # ---- Sender card -----------------------------------------------------
    s_top = y_top
    base = c.card(sx0, y_bot, sw, s_top - y_bot, S.NEUTRAL,
                  bf("sender") + r" at checkpoint $x_t$")
    rows = sender_rows()
    n = len(rows)
    r_top = s_top - STRIP
    rh = (r_top - y_bot) / n
    for i, (aid, lines, tag, tag_ob) in enumerate(rows):
        y1 = r_top - i * rh
        ym = y1 - rh / 2
        if i % 2 == 1:
            band = Rectangle((sx0, y1 - rh), sw, rh, fc=S.tint(S.NEUTRAL, 0.09),
                             ec="none", zorder=2.05)
            ax.add_patch(band)
            band.set_clip_path(base)
        c.text(sx0 + 0.06, baseline(ym, FS), rf"$a_{aid}$", fs=FS)
        ys = [ym] if len(lines) == 1 else [ym + 0.053, ym - 0.053]
        for ln, yy in zip(lines, ys):
            c.text(sx0 + 0.22, baseline(yy, FS_S), ln, fs=FS_S)
        if tag:
            c.chip(sx0 + sw - 0.045, ys[0], tag, OBLIGATION_COLOR[tag_ob], ha="right",
                   fill_alpha=0.0)

    # ---- Packets column --------------------------------------------------
    p_top = y_top
    sum_h = 0.585
    sy0 = p_top - sum_h
    c.card(px0, sy0, pw, sum_h, S.NEUTRAL, bf("fluent summary") + " (illustrative)",
           body=S.tint(S.NEUTRAL, 0.06))
    xl = px0 + 0.06
    pitch = 0.1
    yl = p_top - STRIP - 0.095
    c.text(xl, yl, it("Fix the expiry bug in the cache module."), fs=FS_S,
           color=S.INK_2)
    yl -= pitch
    seg = c.text(xl, yl, it("The"), fs=FS_S, color=S.INK_2)
    x = c.extent(seg)[2] + 0.026
    hl = c.text(x, yl, it("cache test"), fs=FS_S)
    hx0, _, hx1, _ = c.extent(hl)
    _mark(c, hx0, hx1, yl)
    c.text(hx1 + 0.026, yl, it("fails. Expiry uses the wrong clock."), fs=FS_S,
           color=S.INK_2)
    yl -= pitch
    hl = c.text(xl, yl, it("Also edit config.py."), fs=FS_S)
    hx0, _, hx1, _ = c.extent(hl)
    _mark(c, hx0, hx1, yl)
    yl -= pitch + 0.008
    xa = xl
    for s in (r"$a_2$ paraphrased", "no edit scope", r"$a_6$ promoted"):
        c.cross(xa, yl + 0.3 * FS_S * PT, s=0.05)
        t = c.text(xa + 0.085, yl, s, fs=FS_S, color=S.INK)
        xa = c.extent(t)[2] + 0.11

    # Realized packet, distinct from the contract that specifies it.
    ky1 = sy0 - 0.055
    ky0 = y_bot
    c.card(px0, ky0, pw, ky1 - ky0, S.BLUE,
           bf("packet") + r" $R(K_t)$ from contract $K_t$",
           body=S.tint(S.BLUE, 0.07))
    ry1 = ky1 - STRIP - 0.03
    rgap = 0.016
    rx0, rw = px0 + 0.05, pw - 0.15
    rh = (ry1 - (ky0 + 0.035) - (len(REGIONS) - 1) * rgap) / len(REGIONS)
    body_y = {}
    for i, (rname, ob, test) in enumerate(REGIONS):
        y1 = ry1 - i * (rh + rgap)
        y0 = y1 - rh
        excluded = rname == "excluded"
        c.box(rx0, y0, rw, rh, fc=S.SURFACE, ec=S.MUTED if excluded else S.tint(S.BLUE, 0.35),
              lw=0.6, ls=(0, (2, 1.5)) if excluded else "-", r=0.025, z=3)
        ax.add_patch(FancyBboxPatch((rx0 + 0.012, y0 + 0.022), 0.03, rh - 0.044,
                                    boxstyle="round,pad=0,rounding_size=0.012",
                                    fc=OBLIGATION_COLOR[ob], ec="none", zorder=4))
        y_name = y1 - 0.062
        body_y[rname] = y0 + 0.068
        region_label = "omitted from packet" if excluded else rname
        c.text(rx0 + 0.08, baseline(y_name, FS_S), it(region_label),
               fs=FS_S, color=S.INK_2)
        if test:
            t = c.text(rx0 + rw - 0.035, baseline(y_name, FS_S), it(test), fs=FS_S,
                       ha="right")
            c.bolt(c.extent(t)[0] - 0.05, y_name, h=0.12, color=OBLIGATION_COLOR[ob])

    xb = rx0 + 0.08
    y = body_y["instruction/state"]
    t = c.text(xb, baseline(y, FS_S), r"$a_1$ task", fs=FS_S)
    c.chip(c.extent(t)[2] + 0.06, y, "edit " + tt("src/cache.py") + " only",
           OBLIGATION_COLOR["scope"], hf=1.2)
    y = body_y["exact"]
    c.text(xb, baseline(y, FS_S), r"$a_2$ " + tt("tests/test_cache.py::test_expiry"),
           fs=FS_S)
    y = body_y["structured claim"]
    t = c.text(xb, baseline(y, FS_S), r"$a_3$ current diagnosis", fs=FS_S)
    c.chip(c.extent(t)[2] + 0.06, y, "attributed to sender", S.NEUTRAL, fill_alpha=0.0,
           hf=1.2)
    # Dependency arrows from a_3 to a_2 and a_4, in the right margin.
    xd = rx0 + rw + 0.014
    for target, rad in (("exact", 0.55), ("evidence pointer", -0.55)):
        ax.add_patch(FancyArrowPatch(
            (xd, y), (xd, body_y[target]), connectionstyle=f"arc3,rad={rad}",
            arrowstyle="-|>,head_length=3.0,head_width=1.7", mutation_scale=1,
            lw=0.95, color=OBLIGATION_COLOR["dependency"], zorder=8,
            shrinkA=0.5, shrinkB=0.5))
    y = body_y["evidence pointer"]
    t = c.text(xb, baseline(y, FS_S), r"$a_4$ $\rightarrow$", fs=FS_S)
    xs = c.extent(t)[2] + 0.045
    _cylinder(c, xs, y, 0.075, 0.09)
    t = c.text(xs + 0.115, baseline(y, FS_S), "store", fs=FS_S)
    c.text(c.extent(t)[2] + 0.07, baseline(y, FS_S), it("retrieval tokens counted"),
           fs=FS_S, color=S.INK_2)
    y = body_y["data-only"]
    t = c.text(xb, baseline(y, FS_S), r"$a_6$ " + quoted("also edit " + tt("config.py")),
               fs=FS_S)
    c.text(c.extent(t)[2] + 0.08, baseline(y, FS_S), it("data, not authority"),
           fs=FS_S, color=S.INK_2)
    y = body_y["excluded"]
    c.text(xb, baseline(y, FS_S), r"$a_5$ stale (commit mismatch)", fs=FS_S,
           color=S.INK_2)

    # Boundary between the sender and the packets, crossed by both packets.
    bx = 0.5 * (sx0 + sw + px0)
    c.line([bx, bx], [y_bot, s_top], color=S.INK_2, lw=0.8, ls=(0, (3, 2)), zorder=1)
    for yy in (sy0 + (sum_h - STRIP) / 2, 0.5 * (ky0 + ky1 - STRIP)):
        ax.add_patch(FancyArrowPatch(
            (sx0 + sw + 0.02, yy), (px0 - 0.02, yy),
            arrowstyle="-|>,head_length=3.6,head_width=2.1", mutation_scale=1,
            lw=1.1, color=S.INK_2, zorder=4))
    c.text(bx, 0.5 * (sy0 + (sum_h - STRIP) / 2 + 0.5 * (ky0 + ky1 - STRIP)) - 0.02,
           it("subagent handoff"), fs=FS_S, color=S.INK_2, ha="center", va="center",
           rotation=90,
           bbox={"boxstyle": "square,pad=0.12", "fc": FRAME_FILL, "ec": "none"})

    # ---- Check matrix card -----------------------------------------------
    base = c.card(mx0, y_bot, mw, y_top - y_bot, S.NEUTRAL, bf("representation checks"))
    c.text(mx0 + 0.06, y_top - STRIP - 0.105, "on the realized packet", fs=FS_S,
           color=S.INK_2)
    y_leg = y_top - STRIP - 0.235
    c.check(mx0 + 0.06, y_leg)
    t = c.text(mx0 + 0.16, baseline(y_leg, FS_S), "predicate holds", fs=FS_S)
    xl2 = c.extent(t)[2] + 0.13
    c.cross(xl2 + 0.007, y_leg)
    c.text(xl2 + 0.1, baseline(y_leg, FS_S), "violated", fs=FS_S)
    col_w = 0.16
    cx = [mx1 - 0.035 - (2.5 - j) * col_w for j in range(3)]
    head_top = y_leg - 0.085
    head_len = max(c.width(n, fs=FS_S) for n in CHECK_COLUMNS)
    head_base = head_top - head_len
    for j, name in enumerate(CHECK_COLUMNS):
        c.text(cx[j] + 0.3 * FS_S * PT, head_base, name, fs=FS_S, rotation=90,
               ha="left", va="baseline", rotation_mode="anchor")
    row_top = head_base - 0.045
    row_h = (row_top - y_bot) / len(CHECKS)
    tbl_bot = y_bot
    for i in range(1, len(CHECKS), 2):
        band = Rectangle((mx0, row_top - (i + 1) * row_h), mw, row_h,
                         fc=S.tint(S.NEUTRAL, 0.09), ec="none", zorder=2.05)
        ax.add_patch(band)
        band.set_clip_path(base)
    hl = FancyBboxPatch(
        (cx[2] - col_w / 2 + 0.01, tbl_bot + 0.018), col_w - 0.02,
        head_base + c.width(CHECK_COLUMNS[2], fs=FS_S) + 0.035 - tbl_bot - 0.018,
        boxstyle="round,pad=0,rounding_size=0.03", fc=S.tint(S.BLUE, 0.16),
        ec=S.tint(S.BLUE, 0.45), lw=0.5, zorder=2.3)
    ax.add_patch(hl)
    c.line([mx0, mx1], [row_top] * 2, color=S.BASELINE, lw=0.6, zorder=2.2)
    for i, (label, aid, ob, *vals) in enumerate(CHECKS):
        yc = row_top - (i + 0.5) * row_h
        color = OBLIGATION_COLOR[ob] if ob else S.NEUTRAL
        ax.add_patch(FancyBboxPatch((mx0 + 0.05, yc - 0.035), 0.045, 0.07,
                                    boxstyle="round,pad=0,rounding_size=0.012",
                                    fc=color, ec="none", zorder=4))
        s = label + (rf" ($a_{aid}$)" if aid else "")
        c.text(mx0 + 0.13, baseline(yc, FS_S), s, fs=FS_S)
        for j, ok in enumerate(vals):
            if ok:
                c.check(cx[j] - 0.035, yc)
            else:
                c.cross(cx[j] - 0.028, yc, s=0.056)


def _mark(c: Canvas, x0: float, x1: float, yl: float) -> None:
    """Red wash and underline behind a corrupted phrase of the summary."""
    h = FS_S * PT
    c.ax.add_patch(Rectangle((x0 - 0.01, yl - 0.25 * h), x1 - x0 + 0.02, 1.05 * h,
                             fc=S.tint(S.RED, 0.16), ec="none", zorder=4))
    c.line([x0 - 0.01, x1 + 0.01], [yl - 0.25 * h] * 2, color=S.RED, lw=0.8, zorder=5)


def _cylinder(c: Canvas, x: float, yc: float, w: float, h: float) -> None:
    """Small evidence-store cylinder with its left edge at x."""
    ax = c.ax
    e = 0.3 * w
    y0 = yc - h / 2
    top = y0 + h - e / 2
    ax.add_patch(Rectangle((x, y0), w, top - y0, fc=S.tint(S.AQUA, 0.25), ec="none",
                           zorder=5))
    ax.add_patch(Ellipse((x + w / 2, y0), w, e, fc=S.tint(S.AQUA, 0.25), ec="none",
                         zorder=5))
    ax.add_patch(Arc((x + w / 2, y0), w, e, theta1=180, theta2=360, ec=S.INK_2,
                     lw=0.5, zorder=6))
    ax.add_patch(Ellipse((x + w / 2, top), w, e, fc=S.tint(S.AQUA, 0.45), ec=S.INK_2,
                         lw=0.5, zorder=6))
    for xx in (x, x + w):
        c.line([xx, xx], [y0, top], color=S.INK_2, lw=0.5, zorder=6)


def _assert_content(ax) -> None:
    """The teaser is conceptual. It carries no numbers and no forbidden labels."""
    texts = [t.get_text() for t in ax.texts]
    joined = " ".join(texts)
    # Strip artifact indices a_1..a_6, checkpoint and contract subscripts.
    stripped = re.sub(r"a_[1-6]", "", joined)
    assert not re.search(r"\d", stripped), "figure text must not contain numbers"
    for ch in (";", "—", "–", "---", "--"):
        assert ch not in joined, f"forbidden punctuation {ch!r}"
    # Colons appear only inside the verbatim pytest identifier.
    assert joined.replace("::", "").count(":") == 0, "colon in figure text"
    for k in range(1, 7):
        assert f"$a_{k}$" in joined, f"artifact a_{k} missing"
    # The matrix encodes the blueprint's check table exactly.
    expected = {
        "exact id": "xvv", "scope": "xvv", "evidence reachable": "xvv",
        "source role": "xxv", "freshness": "vxv", "within budget": "vxv",
    }
    got = {row[0]: "".join("v" if v else "x" for v in row[3:]) for row in CHECKS}
    assert got == expected, got
    assert all(fs >= FS_S for fs in (t.get_fontsize() for t in ax.texts)), "text < 6.5 pt"


def _assert_layout(c: Canvas) -> None:
    """Every label lies inside the outer frame, and no two labels overlap.

    Panel tags are measured with their rounded frames.
    """
    c.fig.canvas.draw()
    boxes = []
    for t in c.ax.texts:
        if not t.get_text():
            continue
        patch = t.get_bbox_patch()
        ext = c.extent(patch) if patch is not None and "textbf" in t.get_text() \
            and t.get_fontsize() == FS_T else c.extent(t)
        boxes.append((t.get_text(), ext))
    fx, fy = FRAME_PAD * W + 0.03, FRAME_PAD * H + 0.02
    for s, (x0, y0, x1, y1) in boxes:
        assert x0 >= fx and y0 >= fy and x1 <= W - fx and y1 <= H - fy, \
            f"text outside the frame {s!r}"
    tol = 0.004  # inches
    for i, (s, a) in enumerate(boxes):
        for u, b in boxes[i + 1:]:
            ox = min(a[2], b[2]) - max(a[0], b[0])
            oy = min(a[3], b[3]) - max(a[1], b[1])
            assert ox <= tol or oy <= tol, f"overlapping text {s!r} and {u!r}"


def main() -> None:
    S.use_style(font_size=FS)
    fig = plt.figure(figsize=(W, H))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, W)
    ax.set_ylim(0, H)
    ax.axis("off")
    S.rounded_frame(fig, pad=FRAME_PAD, lw=1.2, fill=FRAME_FILL)
    c = Canvas(fig, ax)

    panel_a(c, H)
    y_sep = H - PANEL_A_H
    c.line([X0, X1], [y_sep] * 2, color=S.tint(S.WARM_FRAME, 0.7), lw=0.7,
           ls=(0, (1, 2)))
    panel_b(c, y_sep)

    _assert_content(ax)
    _assert_layout(c)
    S.save(fig, NAME)
    print("assertions passed (content, text size, text inside the frame, "
          "no overlapping text)")


if __name__ == "__main__":
    main()
