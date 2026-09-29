"""House style for the paper's figures: palette, fonts, and drawing helpers.

One module so that every figure shares the same look: a warm rounded outer frame, cards with a
tinted header strip and a same-hue border, bold panel tags on a tinted label, chips, and check
and cross glyphs. Fonts are Times-like (STIX, a TrueType font bundled with matplotlib, so it embeds cleanly) to
match the IEEE body text.

Colour roles are fixed across figures and tables:

* ``HEDGE`` (blue) is certify-then-hedge, ``GATE`` (orange) the registered gate, ``BASE`` (grey)
  the operations research baseline (arm 1) and ``IMMEDIATE`` (dark grey) acting at once;
* the four hypotheses of the fixed set have their own hues (``HYP``);
* ``GOOD`` and ``BAD`` mark a registered test that rejects or does not.

The blue and orange pair was validated with a colour-vision checker (protan dE 24.7, normal dE
33.6); every series also has its own line style or marker and a direct label.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import to_rgb
from matplotlib.lines import Line2D
from matplotlib.patches import FancyBboxPatch, Polygon, Rectangle

FIGURES_DIR = Path(__file__).resolve().parent.parent / "figures"
TEXT_WIDTH = 516 / 72.27  # IEEEtran \textwidth, 43pc (in), so LaTeX never rescales a figure
COLUMN_WIDTH = 252 / 72.27  # IEEEtran \columnwidth, 21pc (in)
PT = 1 / 72

INK = "#1f2328"
INK_2 = "#4a4f57"
MUTED = "#8a8f98"
BASELINE = "#b9bdc4"
GRIDLINE = "#eceef1"
SURFACE = "#ffffff"
FRAME = "#caa45c"
FRAME_FILL = "#fffcf5"

HEDGE = "#2a78d6"
GATE = "#eb6834"
BASE = "#6b7280"
IMMEDIATE = "#3d434c"
NEUTRAL = "#7d8590"
GOOD = "#2e8b57"
BAD = "#c8453a"

HYP = {
    "demand up": "#3f9b58",
    "demand down": "#8a63c9",
    "lead-time shift": "#1f9aa6",
    "upward pulse": "#d39b1a",
}


def tint(color: str, alpha: float) -> tuple[float, float, float]:
    """``color`` blended with white: ``alpha`` = 1 is the colour, 0 is white."""
    r, g, b = to_rgb(color)
    return (1 - alpha + alpha * r, 1 - alpha + alpha * g, 1 - alpha + alpha * b)


def use_style(font_size: float = 7.5) -> None:
    plt.rcParams.update(
        {
            "font.family": "serif",
            "font.serif": ["STIXGeneral", "DejaVu Serif"],
            "mathtext.fontset": "stix",
            "font.size": font_size,
            "axes.labelsize": font_size,
            "axes.titlesize": font_size,
            "xtick.labelsize": font_size - 0.5,
            "ytick.labelsize": font_size - 0.5,
            "legend.fontsize": font_size - 0.5,
            "axes.edgecolor": BASELINE,
            "axes.labelcolor": INK,
            "text.color": INK,
            "xtick.color": INK_2,
            "ytick.color": INK_2,
            "xtick.major.size": 2.5,
            "ytick.major.size": 2.5,
            "xtick.major.width": 0.6,
            "ytick.major.width": 0.6,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.linewidth": 0.6,
            "axes.grid": False,
            "grid.color": GRIDLINE,
            "grid.linewidth": 0.6,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "savefig.dpi": 300,
        }
    )


def signed(value: float, digits: int = 0) -> str:
    """Signed, comma-grouped number with a true minus sign."""
    return f"{value:+,.{digits}f}".replace("-", "−")


def rounded_frame(
    fig,
    pad: float = 0.004,
    lw: float = 1.1,
    color: str = FRAME,
    fill: str = FRAME_FILL,
    radius: float = 0.018,
) -> FancyBboxPatch:
    """Warm rounded outer frame in figure coordinates, drawn behind everything."""
    patch = FancyBboxPatch(
        (pad, pad),
        1 - 2 * pad,
        1 - 2 * pad,
        boxstyle=f"round,pad=0,rounding_size={radius}",
        transform=fig.transFigure,
        fc=fill,
        ec=color,
        lw=lw,
        zorder=-10,
    )
    fig.patches.append(patch)
    return patch


def panel_tag(
    ax,
    text: str,
    color: str,
    x: float,
    y: float,
    *,
    ha: str = "left",
    va: str = "bottom",
    fontsize: float = 7.5,
    transform=None,
    alpha: float = 0.22,
):
    """Bold panel label on a tinted, rounded label box (like a card's title chip)."""
    return ax.text(
        x,
        y,
        text,
        ha=ha,
        va=va,
        fontsize=fontsize,
        fontweight="bold",
        color=INK,
        transform=transform if transform is not None else ax.transAxes,
        zorder=20,
        bbox={
            "boxstyle": "round,pad=0.28,rounding_size=0.35",
            "fc": tint(color, alpha),
            "ec": tint(color, 0.7),
            "lw": 0.6,
        },
    )


class Canvas:
    """An axes in inch coordinates with text measurement and drawing helpers."""

    def __init__(self, fig, rect=(0, 0, 1, 1)):
        self.fig = fig
        w, h = fig.get_size_inches()
        self.W, self.H = w, h
        self.ax = fig.add_axes(rect)
        self.ax.set_xlim(0, w * rect[2])
        self.ax.set_ylim(0, h * rect[3])
        self.ax.axis("off")
        self.renderer = fig.canvas.get_renderer()

    def text(self, x, y, s, fs=7.0, color=INK, ha="left", va="baseline", **kw):
        return self.ax.text(
            x, y, s, fontsize=fs, color=color, ha=ha, va=va, zorder=kw.pop("zorder", 6), **kw
        )

    def width(self, s, fs=7.0, **kw) -> float:
        t = self.ax.text(0, 0, s, fontsize=fs, **kw)
        bb = t.get_window_extent(self.renderer)
        t.remove()
        return bb.width / self.fig.dpi

    def extent(self, artist):
        bb = artist.get_window_extent(self.renderer)
        inv = self.ax.transData.inverted()
        (x0, y0), (x1, y1) = inv.transform([[bb.x0, bb.y0], [bb.x1, bb.y1]])
        return x0, y0, x1, y1

    def line(self, xs, ys, **kw):
        kw.setdefault("zorder", 3)
        self.ax.add_line(Line2D(xs, ys, **kw))

    def box(self, x, y, w, h, fc, ec, lw=0.7, ls="-", r=0.04, z=2):
        patch = FancyBboxPatch(
            (x, y),
            w,
            h,
            boxstyle=f"round,pad=0,rounding_size={r}",
            fc=fc,
            ec=ec,
            lw=lw,
            ls=ls,
            zorder=z,
        )
        self.ax.add_patch(patch)
        return patch

    def card(
        self,
        x,
        y,
        w,
        h,
        accent,
        title,
        *,
        fs=7.5,
        strip=0.17,
        body=SURFACE,
        strip_alpha=0.28,
        lw=0.8,
        r=0.05,
        z=2.0,
    ):
        """Group card with a tinted header strip, a body, and a same-hue border."""
        base = self.box(x, y, w, h, fc=body, ec="none", r=r, z=z)
        band = Rectangle(
            (x, y + h - strip), w, strip, fc=tint(accent, strip_alpha), ec="none", zorder=z + 0.1
        )
        self.ax.add_patch(band)
        band.set_clip_path(base)
        self.line([x, x + w], [y + h - strip] * 2, color=accent, lw=0.5, zorder=z + 0.2)
        self.box(x, y, w, h, fc="none", ec=accent, lw=lw, r=r, z=z + 0.6)
        self.text(
            x + w / 2, y + h - strip / 2, title, fs=fs, ha="center", va="center", fontweight="bold"
        )
        return base

    def chip(
        self, x, y, s, color, fs=6.5, alpha=0.22, ha="left", pad=0.035, hf=1.35, ec=None, bold=False
    ):
        """Rounded tag around text. ``x`` is the left (or right) edge, ``y`` the centre."""
        w = self.width(s, fs=fs, fontweight="bold" if bold else "normal")
        h = fs * PT * hf
        x0 = x if ha == "left" else (x - w - 2 * pad if ha == "right" else x - w / 2 - pad)
        self.ax.add_patch(
            FancyBboxPatch(
                (x0, y - h / 2),
                w + 2 * pad,
                h,
                boxstyle="round,pad=0,rounding_size=0.03",
                fc=tint(color, alpha) if alpha else SURFACE,
                ec=ec or color,
                lw=0.6,
                zorder=5,
            )
        )
        self.text(
            x0 + pad, y, s, fs=fs, va="center_baseline", fontweight="bold" if bold else "normal"
        )
        return x0 + w + 2 * pad

    def check(self, x, y, s=0.07, color=GOOD, lw=1.3):
        pts = [(x, y + 0.02 * s / 0.07), (x + 0.33 * s, y - 0.3 * s), (x + s, y + 0.45 * s)]
        self.line(
            *zip(*pts, strict=True),
            color=color,
            lw=lw,
            solid_capstyle="round",
            solid_joinstyle="round",
            zorder=7,
        )

    def cross(self, x, y, s=0.055, color=BAD, lw=1.3):
        h = s / 2
        for a, b in (((x, y - h), (x + s, y + h)), ((x, y + h), (x + s, y - h))):
            self.line(
                [a[0], b[0]], [a[1], b[1]], color=color, lw=lw, solid_capstyle="round", zorder=7
            )

    def polygon(self, pts, fc, ec="none", lw=0.5, z=4):
        self.ax.add_patch(Polygon(pts, closed=True, fc=fc, ec=ec, lw=lw, zorder=z))


def save(fig, name: str, out_dir: Path | None = None) -> None:
    out = out_dir or FIGURES_DIR
    out.mkdir(parents=True, exist_ok=True)
    # No creation date, so re-rendering unchanged data leaves the PDF byte-identical.
    fig.savefig(out / f"{name}.pdf", pad_inches=0.0, metadata={"CreationDate": None})
    fig.savefig(out / f"{name}.png", dpi=300, pad_inches=0.0)
    plt.close(fig)
