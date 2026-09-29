# illustrate/ — figure renderers

Scripts in this folder generate every figure the paper includes; nothing in
`../figures/` is edited by hand.

## Usage

```bash
python3 illustrate/figures.py                 # render all figures into ../figures/
python3 illustrate/figures.py fig1_overview   # render one figure by name
python3 illustrate/figures.py --list          # list registered figures
```

Or `make figures` from the repository root. Requires `matplotlib`
(`pip install matplotlib`). The rendered PDFs are tracked in git, so building
the paper never requires this step.

## Conventions

- One renderer function per figure, registered by name in the `FIGURES` dict in
  `figures.py`; the name is the output base name in `figures/`.
- Each figure is written twice: `<name>.pdf` (vector, included by LaTeX via
  `\includegraphics`) and `<name>.png` (300 dpi preview).
- `main.tex` sets `\graphicspath{{figures/}}`, so section files include figures
  by bare name: `\includegraphics[width=\textwidth]{fig1_overview.pdf}`.
- Sizing matches the IEEE two-column grid: `SINGLE_COLUMN_IN = 3.5`,
  `DOUBLE_COLUMN_IN = 7.16`; label text is 8 pt serif per IEEE guidance. Keep
  every mark inside that width — anything drawn past it widens the tight
  bounding box and silently shrinks the whole figure when LaTeX scales it back.
- Diagram panels use an axes whose data units are inches (`_diagram_axes`), so a
  width of `0.9` in the drawing code is 0.9 inches on the page and rounded
  corners keep one radius throughout.
- Figure data lives in `illustrate/data/` as JSON or CSV sidecars; renderers
  read the sidecars, they never hard-code measurements.

## Colour

Two accents, and each one means the same thing in every figure:

| Role | Hex | What wears it |
| --- | --- | --- |
| **Evidence** | `#2a78d6` | the e-process, its threshold, the gate |
| **Control** | `#eb6834` | the compiler, the configuration, the order |

Everything else is neutral grey chrome. Colour never carries identity on its
own: every coloured path is also a distinct line style and every coloured band
is also labelled, because these figures are printed and often in black and
white, where the two accents sit only about 30 grey levels apart. The pair
clears the colour-vision-deficiency and normal-vision separation floors on a
light surface (worst-pair CVD ΔE 24.7 protan, normal ΔE 33.6).

## Current figures

| Name | Output | Notes |
| --- | --- | --- |
| `fig1_overview` | `figures/fig1_overview.pdf`, `.png` | Fig. 1, full text width. (a) the handshake: WHEN / WHAT / WHETHER over the pipeline, the gate as a valve, the dashed baseline bypass, the dotted closed loop. (b) the running episode, **schematic** — no measured quantity appears in it. |
| `fig2_method` | `figures/fig2_method.pdf`, `.png` | Fig. 2, full text width. One key, two consumers: the frozen `ShockSpec`, the registered key, the verifier branch upward and the compiler branch downward, meeting again at the gate. |
| `fig3_frontier` | `figures/fig3_frontier.pdf`, `.png` | Fig. 3, one column. Reads `data/frontier.csv`. The calls axis is registered and drawn; the profit columns are empty, and the renderer draws a PENDING panel until they are filled. Fill them and the figure completes with no code change. |
