# illustrate/ — figure renderers

Scripts in this folder generate every figure the paper includes; nothing in `../figures/` is
edited by hand. `cth_figures.py` is the entry point: for each figure it first writes the numbers
and facts it will draw to `data/` (CSV or JSON, read from the committed study outputs in
`analysis/commitment/out/`), then renders from those files.

| File | What it does |
| --- | --- |
| `cth_figures.py` | Entry point; writes the data sidecars and renders every figure by name |
| `style.py` | The house style shared by every figure: palette, STIX fonts, frame, cards, tags, chips, glyphs |
| `overview.py` | Fig. 1, the gate and certify-then-hedge on one shared input |
| `method.py` | Fig. 2, how certify-then-hedge turns a ShockSpec into an order (schematic curves) |
| `data/` | The sidecars each figure is drawn from |

## Usage

```bash
uv run python paper/illustrate/cth_figures.py                 # every figure, from the repo root
uv run python paper/illustrate/cth_figures.py fig1_overview   # one figure by name
```

Or `make figures` from `paper/`. The rendered PDFs are tracked in git, so building the paper
never requires this step. `fig1_overview` replays the frozen method arm on its episode (a few
seconds) and stops unless the replay reproduces the recorded total reward exactly.

## Conventions

- One renderer per figure, registered by name in `FIGURES` in `cth_figures.py`; the name is the
  output base name in `figures/`. Each figure is written as `<name>.pdf` (vector, included by
  LaTeX) and `<name>.png` (300 dpi preview).
- `main.tex` sets `\graphicspath{{figures/}}`, so sections include figures by bare name.
- Sizes follow the IEEE grid (`style.TEXT_WIDTH = 7.16`, `style.COLUMN_WIDTH = 3.5` in); text is
  at least 6.5 pt. Figures are saved at their exact size (no tight bounding box), so LaTeX never
  rescales them.
- Diagrams are drawn on a `style.Canvas`, an axes in inch units with text measurement, so layout
  code can place and check text exactly.
- Renderers assert what they draw: every number against its sidecar, text inside its card, no
  overlapping text, panel titles centred over their panels.
- Renderers never hard-code a measured quantity; facts come from the sidecars.

## Style

Following the owner's house style: a warm rounded outer frame, cards with a tinted header strip
and a same-hue border, **bold panel titles centred over their panels**, chips, check and cross
marks, and zebra rows. STIX fonts match the IEEE body text and embed as TrueType.

Colour roles are fixed across figures and tables:

| Role | Hex | What wears it |
| --- | --- | --- |
| Certify-then-hedge | `#2a78d6` | the method, its shock mass and bound |
| Registered gate | `#eb6834` | arm 10, its switch and compiled size |
| Baseline | `#6b7280` | arm 1 (operations research base stock) |
| Hypotheses | teal, green, purple, amber | lead-time shift, demand up, demand down, upward pulse |
| Verdicts | `#2e8b57` / `#c8453a` | check (right or rejects) and cross (wrong or does not) |

Colour never carries identity on its own: every coloured series also has its own line style or
marker and a direct label. The blue and orange pair clears the colour-vision-deficiency and
normal-vision separation floors on a light surface (worst-pair CVD ΔE 24.7 protan, normal ΔE
33.6).

## Current figures

| Name | Where | Drawn from |
| --- | --- | --- |
| `fig1_overview` | Fig. 1, Sec. I, full width | `data/fig1_episode.csv` (plotted series), `data/fig1_episode_meta.json` (alert, ShockSpec, offsets, replayed posterior) |
| `fig2_method` | Fig. 2, Sec. VI, full width | the registered constants only (λ, \|H\|); its curves are schematic and labelled so |
| `fig3_models` | Fig. 3, Sec. VIII, full width | `data/fig3_models.csv` (the fresh-seed confirmation across six models) |
