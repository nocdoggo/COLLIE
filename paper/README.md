# COLLIE — IEEE UV 2026 paper

Working repository for the COLLIE paper, *Certify, Then Hedge: Graded Commitment to
Language-Model Shock Hypotheses in Inventory Control*, for the 8th IEEE International
Conference on Universal Village (IEEE UV2026, virtual and local, October 17–20, 2026; final
manuscripts due October 15, 2026).

This is the **camera-ready draft**. Every number comes from a committed output under
`analysis/`, and every substantive claim traces to its evidence and status in
[`CLAIMS.md`](CLAIMS.md). The only placeholders left are the team's: the author block (section 3
below). The paper has no acknowledgment section.

## Build

```bash
make              # -> main.pdf
make check        # structural checks, no TeX toolchain needed
make check-pages  # body pages (up to the references) against the 9-page camera-ready limit
make figures      # re-render the two figures from the committed study outputs (uv environment)
```

`make` uses `latexmk` when it is on PATH and falls back to a
`pdflatex`/`bibtex`/`pdflatex`×2 sequence otherwise. Without either it exits 1
and says so, while `make check` still runs: every structural check is pure text
processing.

## Repository map

| Path | Purpose |
| --- | --- |
| `main.tex` | Top-level file: IEEEtran conference preamble, `\pending` convention, notation shorthands, author block, the (commented) UV2026 header/footer, section order, bibliography |
| `sections/` | One `.tex` file per section, input by `main.tex` in order |
| `figures/` | Rendered figures, PDF plus a PNG preview, tracked so that building the paper never requires matplotlib |
| `illustrate/` | `cth_figures.py` renders both figures from `analysis/commitment/out/`; `illustrate/data/` holds the CSV sidecars it writes. `figures.py` and its three figures belong to the submitted draft and are retired |
| `citations.bib` | The bibliography, 54 entries (26 cited); `IEEEabrv.bib` (journal abbreviations) is loaded before it |
| `check.py` | Structural checks, no TeX needed; run via `make check` |
| `CLAIMS.md` | Every substantive claim → its evidence → its status |
| `IEEEtran.bst` | IEEEtran bibliography style (forces "et al." above five authors) |

Section order, as `main.tex` inputs them:

```
00_abstract   01_introduction   02_background   03_setup   04_interface
06_method_verify   06_method_hedge   07_design   08_results
10_related_work   11_limitations   12_conclusion
```

There is no acknowledgment section; any sponsor note would go in `\thanks` in the author block.

## Figures

The figures are rendered by `illustrate/cth_figures.py` (`make figures`) into `figures/` as a
PDF, which `\includegraphics` picks up, plus a PNG preview. Nothing in `figures/` is edited by
hand, and the renderers read every value from the committed outputs.

| Figure | Where | What it carries |
| --- | --- | --- |
| `fig1_overview` | Sec. I, full width | The gate and certify-then-hedge on one shared input: (a) the alert, the model's ShockSpec and the truth; (b) the gate lane and (c) the hedge lane, each ending in the same fresh-seed lead-time episode (chosen post hoc; the caption says so), with the exposure bound under the hedge |
| `fig2_method` | Sec. VI, full width | How certify-then-hedge turns a ShockSpec into an order: (a) the fields the hedge reads, (b) the prior over the fixed set, (c) the e-processes and posterior, with sizing from the data, (d) the mixture quantile, (e) the guarantees and their premise; schematic curves |
| `fig3_models` | Sec. VIII, full width | The fresh-seed confirmation with six proposer models: perception, acting at once, and the gate and the hedge against arm 1, with the content-free control as a band |

All figures share `illustrate/style.py`: a warm rounded frame, cards with tinted header strips,
centred panel titles, and STIX fonts that embed as TrueType. **Blue is certify-then-hedge**,
**orange is the gate**, grey is the operations research baseline; the four hypotheses keep one
hue each. The blue and orange pair clears the colour-vision deficiency and normal-vision
separation floors on a light surface (worst-pair CVD ΔE 24.7 protan, normal ΔE 33.6), and
every coloured series also differs in marker or line style.

---

## 1. Venue facts

Verified against the live call for papers on **2026-09-17** at
<https://universalvillage.org/ieee-uv2026/call-for-paper-4/> (HTTP 200, no
redirect). Each fact below was read off that page.

| Fact | Value |
|---|---|
| Conference | 8th IEEE International Conference on Universal Village (IEEE UV 2026) |
| Dates, mode | October 17 to 20, 2026, virtual and local |
| Theme | "Human-Centered AI Transformation for Future Empowerment: Explainable & Human-Intelligible Understanding, Intent-Aware Reasoning & Accountable Decision-Making, Human-Authorized AI Action, and Human-Supervised Reflective Learning" |
| Regular paper length | **5 to 8 pages** in the CFP ("REGULAR PAPERS (5-8 pages)"); for the camera-ready the organisers allow **9 pages, references not counted** (owner, 2026-09-29) |
| Short paper length | 3 to 4 pages (CFP: "SHORT PAPERS (3-4 pages)") |
| Template | IEEE two-column conference template (`\documentclass[conference]{IEEEtran}`) |
| Paper size | US Letter, explicitly "not A4" |
| Separate abstract | 100 to 300 words, submitted through EasyChair |
| Submission system, deadline | EasyChair, **September 25, 2026** |
| Other dates | portal opened March 25, 2026; notification October 5, 2026; final manuscripts October 15, 2026 |
| Indexing | submitted for inclusion in IEEE Xplore |
| Formatting asks | remove running headers and footers, page numbering, and blue underlining on URLs and email addresses |
| **Blind review** | **Not blind.** See below. |

**Blind review, resolved rather than assumed.** A search for *blind*, *anonymous*
and *anonymised* returned zero hits across the live CFP page, the venue's
annotated sample (`conference_paper_instructions.tex` and its PDF), and every
file of the local scaffold. The venue distributes no anonymous style file, and
its own sample ships a full `\author` block with affiliations and emails. The
draft therefore uses the non-anonymous author form. The author names themselves
are `\pending{}` because the author list is the submitting authors' to set, not
this draft's.

**Assumptions used where a fact was not stated.** The CFP does not mention
over-length pages, page charges, or an appendix allowance. The draft carries no
appendix, and its body fits the 9 camera-ready pages (references excluded).

**Formatting asks, all honoured.** `hyperref` is loaded with `[hidelinks]`, so
no URL or address is underlined or coloured. IEEEtran's conference mode emits no
running header and no page number, and this draft adds none: the `fancyhdr`
block carrying the session line and the page-1 copyright footer with the ISBN
string `979-8-3195-2714-1/26/$31.00 (c)2026 IEEE` is **commented out** in
`main.tex`, in both the preamble and the body, because the call governs and it
asks for headers and footers to be removed. The venue's own annotated sample
installs that footer and it is required at camera-ready, so the block is kept
verbatim rather than deleted; re-enabling it is two uncomments and setting the
session designation.

---

## 2. Build status

Last clean build (2026-09-29, TeX Live 2026, latexmk 4.88): **8 pages** including references,
US Letter (612 x 792 pt), zero undefined references or citations, zero overfull boxes, and both
columns of the last page full. `make check` exits 0.

Build products, `main.pdf` included, are ignored by `.gitignore` and are
regenerated by `make`. The rendered figures under `figures/` are the exception:
they are tracked on purpose, so that building the paper never requires
matplotlib. Regenerate them with `make figures`.

---

## 3. Placeholder inventory

The `\pending` convention is mandatory: a half-filled draft must be impossible to
mistake for a finished one. `python3 check.py pending` prints this table's total, and the total
below must equal that output exactly.

| File | `\pending` | `\pcell` | What is missing |
|---|---:|---:|---|
| `main.tex` | 3 | 0 | author list, affiliation, email |
| **Total** | **3** | **0** | **3 markers** |

At camera-ready the team also sets the session designation and re-enables the header and the
page-1 copyright footer in `main.tex` (section 1).

---

## 4. Reference verification

Every entry carried over into `citations.bib` was verified online on
**2026-09-17**: a page showing the title, the authors and the venue or year was
fetched for each one. Nothing is present that could not be verified, and no
field was guessed. Where a page range or a venue does not exist yet, the field is
omitted rather than invented. A 2026-09-24 citation pass closed the draft's
citation gaps with five new entries, each verified online the same day (URLs
below). The 2026-09-29 rewrite around certify-then-hedge added 14 entries, each checked against
arXiv, Crossref or PMLR, and now cites **26 of the 54 entries**; the rest are verified but
belong to the submitted draft's sections. `python3 check.py refs` lists the uncited ones. Only entries cited with `\cite{...}` reach the
References section.

Entries added and verified on **2026-09-24**:

- `hinkley-cusum-1971` — Hinkley, *Biometrika* 58(3):509-523, 1971, verified
  through Crossref: <https://api.crossref.org/works/10.1093/biomet/58.3.509>.
  This, not the 1970 `hinkley-changepoint`, is the canonical Page-Hinkley
  source, so §7 cites it for the Page-Hinkley rule; the 1970 paper stays with
  the classical changepoint machinery in §10.
- `holm-multitest` — Holm, *Scandinavian Journal of Statistics* 6(2):65-70,
  1979. JSTOR (<https://www.jstor.org/stable/4615733>) answers bots with a
  client challenge, so the metadata were confirmed against the journal
  bibliography at <https://ftp.math.utah.edu/pub/tex/bib/scandjstat.html>;
  author, volume, issue, pages, year and the JSTOR id all agree. Pre-DOI, so
  no `doi` field.
- `wilcoxon` — Wilcoxon, *Biometrics Bulletin* 1(6):80-83, 1945, DOI
  `10.2307/3001968`. Confirmed from the JSTOR issue record
  (<https://www.jstor.org/stable/i350470>) as surfaced in search metadata;
  JSTOR itself answers bots with a client challenge, as above.
- `cameron-miller-cluster` — Cameron and Miller, *Journal of Human Resources*
  50(2):317-372, 2015, verified through Crossref:
  <https://api.crossref.org/works/10.3368/jhr.50.2.317>.
- `gemini-pricing` — Google Cloud's generative-AI pricing page, fetched live:
  <https://cloud.google.com/vertex-ai/generative-ai/pricing>. It lists Gemini
  Flash models at \$0.75 per million input and \$3.75 per million output
  tokens ("response and reasoning"), the dated price §8 states.

Three identifiers carried in the project's design documents were checked and one
is wrong:

- **InventoryBench is arXiv:2602.12631**, "AI Agents for Inventory Control:
  Human-LLM-OR Complementarity", Baek, Fu, Ma and Peng. The design doc's id is
  correct. The upstream repository README's own BibTeX says `year={2025}` and
  keys it `baek2025ai`, but the arXiv record shows first submission 13 February
  2026. `citations.bib` uses **2026** to match the verified record; the upstream
  BibTeX is stale.
- **`InstructMPC` is arXiv:2504.05946**, not the 2512.05876 the design doc
  gives. That id resolves to a different, later paper by overlapping authors,
  now titled "Context-Aware Model Predictive Control for Microgrid Energy
  Management via LLMs". The entry is not cited in this draft.
- **The event-triggered-invocation title was truncated** in the design doc. Its
  full title ends "...in Streaming Systems", it has a single author, and it is
  accepted to the ECML PKDD 2026 Research Track with code at
  <https://github.com/GeoffreyWang1117/event-triggered-llm-streaming>.

Spot-verified facts behind sentences in the paper:

- The 4.92 percent figure is in the abstract of Kesavan, Kushwaha and Steele,
  *Management Science* 72(1):119-127, 2026, DOI `10.1287/mnsc.2024.06321`. Note
  the year of record is 2026, not the 2025 of the Article-in-Advance.
- The 21-day figure is in the abstract of Carreras-Valle and Ferrari, *AEA
  Papers and Proceedings* 115:618-623, 2025, DOI `10.1257/pandp.20251089`.
- **InvEvolve has no public code artifact.** A GitHub repository search returns
  zero repositories of that name, the paper carries no code-availability
  statement, and a coauthor's own curated index lists only the arXiv link. The
  paper says so and does not reimplement it.

One bibliographic abbreviation was applied for length: the Stockpyl chapter's
`booktitle` is given as "Tutorials in Operations Research" rather than the full
INFORMS volume subtitle.

---

## 5. Where the numbers come from

The submitted draft (Overleaf `68f996d`, imported at `0967e30`) was rewritten around the
commitment study in `analysis/commitment/` (`PLAN.md` for the registered stages and their
amendments, `REPORT.md` for the readout). The paper's numbers come from:

- `analysis/commitment/out/confirm.json`: the registered stage C evaluation (Table I, Fig. 3);
- `analysis/commitment/out/confirm_d.json` and `readout_d.json`: the registered stage D
  evaluation and its registered secondaries;
- `analysis/commitment/out/posthoc.json`, `sensitivity.json` and `ablation.json`: post-hoc
  readouts, labelled post hoc wherever the paper uses them;
- `analysis/commitment/out/mc_exposure.json`: the null exposure simulation;
- `analysis/commitment/out/ladder.json`: the model ladder;
- `analysis/real_content_pilot/out/evaluation.json`, `analysis/kill_trigger_forensics.md` and
  `reports/`: the pilots and the benchmark audit.

Integers in the paper are rounded once from unrounded values; two independent checks of the
draft (2026-09-29) are what `CLAIMS.md` reflects.

---

## 6. Open questions for the team

1. The author block and the session designation (section 3). No acknowledgment section is needed.
2. Whether the abstract should be cut toward IEEE's usual 150-250 words; it is 294 words, inside
   the call's 100-300.

---

## Before submission

- Remove any remaining template text, and confirm every `\pending{}` and
  `\pcell` is gone — `make check` prints the running total.
- Fill the author block; `\AuthorCell` and `\CorrespondingMark` in `main.tex`
  handle multi-author rows.
- Embed all fonts in the final PDF, per the UV2026 submission instructions.
- At camera-ready, re-enable the `fancyhdr` block in `main.tex` (preamble and
  body) and set the session designation, if the venue asks for the ISBN footer.
