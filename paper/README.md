# COLLIE — IEEE UV 2026 paper

Working repository for the COLLIE paper, targeting the 8th IEEE International
Conference on Universal Village (IEEE UV2026, virtual and local, October 17–20,
2026, theme "Human-Centered AI Transformation for Future Empowerment").

This repository holds the **first complete draft**. The method, the
audited-benchmark findings, the arm ladder and the claim discipline are written;
the sweeps are still running, so **every experimental result is a placeholder** —
each missing number sits in a `\pending{}` slot whose shape matches the result
table that will fill it. Every substantive claim traces to its evidence in
[`CLAIMS.md`](CLAIMS.md).

## Build

```bash
make              # -> main.pdf
make check        # structural checks, no TeX toolchain needed
make check-pages  # page count against the venue's nominal limit (reports, does not gate)
make figures      # re-render the scripted figures in illustrate/ (needs matplotlib)
```

`make` uses `latexmk` when it is on PATH and falls back to a
`pdflatex`/`bibtex`/`pdflatex`×2 sequence otherwise. Without either it exits 1
and says so, while `make check` still runs: every structural check is pure text
processing.

## Repository map

| Path | Purpose |
| --- | --- |
| `main.tex` | Top-level file: IEEEtran conference preamble, `\pending` convention, notation shorthands, author block, UV2026 header/footer, section order, bibliography |
| `sections/` | One numbered `.tex` file per section, input by `main.tex` in order |
| `figures/` | Rendered figures, PDF plus a PNG preview, tracked so that building the paper never requires matplotlib; `main.tex` sets `\graphicspath{{figures/}}` |
| `illustrate/` | The renderers. `figures.py` draws every figure; `illustrate/data/` holds the CSV sidecars they read. See `illustrate/README.md` |
| `citations.bib` | The paper's bibliography, 40 entries; `IEEEabrv.bib` (journal abbreviations) is loaded before it |
| `check.py` | Structural checks, no TeX needed; run via `make check` |
| `CLAIMS.md` | Every substantive claim → its evidence → its status |
| `conference_paper_instructions.tex` | Venue-provided annotated sample; formatting reference, not part of the paper |
| `IEEEtran.bst`, `IEEEtran_HOWTO.pdf` | IEEEtran bibliography style and class documentation |
| `IEEEexample.bib` | Ready-made BibTeX entry patterns for every reference type; copy patterns into `citations.bib` |

Section order, as `main.tex` inputs them:

```
00_abstract   01_introduction   02_background      03_setup
04_method_spec   05_method_compile   06_method_verify
07_triggers_alerts   08_ladder_accounting   09_experiments
10_related_work   11_limitations   12_conclusion   13_acknowledgment
```

Sponsor acknowledgments belong in `\thanks` in the author block, not in
`sections/13_acknowledgment.tex`.

## Figures

All three figures are rendered by `illustrate/figures.py` into `figures/` as a
PDF, which `\includegraphics` picks up, plus a 300 dpi PNG preview. Nothing in
`figures/` is edited by hand.

| Figure | Where | What it carries |
| --- | --- | --- |
| `fig1_overview` | Sec. I, full width | (a) the handshake — the three brackets WHEN / WHAT / WHETHER over the pipeline, the gate drawn as a valve, the dashed baseline bypass, the dotted closed loop; (b) the running episode, schematic |
| `fig2_method` | Sec. IV, full width | One key, two consumers: the frozen `ShockSpec`, the registered key, and the two branches — verifier registry upward, compiler and the 72-point grid downward — meeting again at the gate |
| `fig3_frontier` | Sec. IX, one column | The reward-against-compute slot. The calls axis is registered in advance and drawn; the profit endpoint is pending, and the panel says so |

Two accents only, and each means the same thing in both figures: **blue is the
evidence path** (the e-process, its threshold, the gate) and **orange is the
control path** (the compiler, the configuration, the order). Everything else is
neutral grey. Colour never carries identity alone — every coloured path is also
a distinct line style and every band is also labelled — because these figures
are printed, often in black and white. The pair clears the colour-vision
deficiency and normal-vision separation floors on a light surface (worst-pair
CVD ΔE 24.7 protan, normal ΔE 33.6).

`fig3_frontier` reads `illustrate/data/frontier.csv`, which carries one row per
arm with the registered call budget filled in and the profit columns empty. Fill
those columns and the figure completes with no code change.

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
| Regular paper length | **5 to 8 pages** (CFP: "REGULAR PAPERS (5-8 pages)") |
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
appendix. It does run past the nominal 8 pages: see section 2 on why, and
`make check-pages` for the current count.

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

The machine this draft was written on has a full TeX toolchain, so the build was
run rather than assumed:

```
pdfTeX 3.141592653-2.6-1.40.29 (TeX Live 2026)
latexmk 4.88 (9 March 2026)
IEEEtran.cls, IEEEtran.bst  present in texmf-dist
```

Last clean build: **10 pages**, US Letter (612 x 792 pt), zero undefined
references, zero undefined citations, zero LaTeX warnings on the final pass, and
exactly one overfull box, 5.4 pt, in the Section V compiler table (the
registered-mapping tabular). `make check` exits 0.

**On the page count.** The call names 5 to 8 pages for a regular paper, but the
limit is not enforced at this venue, and a self-contained argument is worth more
than two pages saved. The draft is therefore written to be complete rather than
to fit: the per-family validity table and the reward-against-compute figure,
both of which an earlier 8-page revision had cut, are in. `make check-pages`
reports the count and names the nominal limit; it no longer fails. Run
`make check-pages PAGE_LIMIT=8` to turn it back into a hard gate.

Build products, `main.pdf` included, are ignored by `.gitignore` and are
regenerated by `make`. The rendered figures under `figures/` are the exception:
they are tracked on purpose, so that building the paper never requires
matplotlib. Regenerate them with `make figures`.

---

## 3. Placeholder inventory

The `\pending` convention is mandatory: a half-filled draft must be impossible to
mistake for a finished one. `python3 check.py pending` prints this table and its
total, and the total below must equal that output exactly.

| File | `\pending` | `\pcell` | What is missing |
|---|---:|---:|---|
| `main.tex` | 3 | 0 | author list, affiliation, email |
| `sections/00_abstract.tex` | 1 | 0 | headline result sentence |
| `sections/01_introduction.tex` | 1 | 0 | nothing numeric; the marker is the standing note that every result cell is pending |
| `sections/07_triggers_alerts.tex` | 1 | 0 | inter-rater agreement, templates pruned for leakage |
| `sections/08_ladder_accounting.tex` | 0 | 51 | Table I: 15 arms and controls by three endpoints (45 cells), plus 3 contrasts by two endpoints (6 cells) |
| `sections/09_experiments.tex` | 3 | 0 | the Fig. 3 frontier; activation ablation; null-audit calibration and fragility; content against timing; efficiency; operational, hypothesis and traced-case tables |
| `sections/11_limitations.tex` | 2 | 0 | headroom band under the integrated pipeline; integration status, pilot verdict, frozen registration hash |
| `sections/12_conclusion.tex` | 1 | 0 | final result paragraph |
| `sections/13_acknowledgment.tex` | 1 | 0 | funding, compute, readers of the draft |
| **Total** | **13** | **51** | **64 markers** |

`sections/02_background.tex`, `03_setup.tex`, `04_method_spec.tex`,
`05_method_compile.tex`, `06_method_verify.tex` and `10_related_work.tex` carry
no placeholders: everything in them is either established today or cited.

Two `\pending` markers are the convention demonstrating itself rather than a
missing number — the one in the introduction and the one opening Section IX both
render as a red marker inline, so a reader meets the convention before meeting a
result slot. They are counted above because the grep counts them.

---

## 4. Completeness over page count

An earlier revision was compressed to 8 pages and two display items were folded
into prose to make it fit. Both are now back, because the limit is not enforced
and a reader should not have to reconstruct a register from a paragraph:

1. **The per-family validity table** (Table III) is restored in
   `sections/06_method_verify.tex`. The prose around it was rewritten rather
   than left as-is: the table carries the enumeration, and the prose keeps only
   the reasoning the table cannot hold — why the arrival-side status is
   restricted, why the compound family is budget-split rather than multiplied,
   and why the plug-in variant is permanently rather than temporarily empirical.
   Printing both the table and its paraphrase would have been the worse paper.
2. **The reward-against-compute frontier** is Fig. 3, included in
   `sections/09_experiments.tex`.

Two presentational decisions from that compression were improvements and are
kept. The arm ladder and the main result table are **merged** into one
full-width table, so each rung's objection sits on the same line as the number
that answers it. Figure 1 dropped its ladder side panel once that table carried
the same eleven rungs, and the space went to the running-episode panel instead.

---

## 5. Reference verification

Every entry carried over into `citations.bib` was verified online on
**2026-09-17**: a page showing the title, the authors and the venue or year was
fetched for each one. Nothing is present that could not be verified, and no
field was guessed. Where a page range or a venue does not exist yet, the field is
omitted rather than invented. A 2026-09-24 citation pass closed the draft's
citation gaps with five new entries, each verified online the same day (URLs
below), and wired every verified entry into the text: **40 entries are verified
and 39 are cited**, leaving only `uv2026cfp` (the venue's call for papers,
cited from this README rather than from the paper). `python3 check.py refs`
lists the uncited ones. Only entries cited with `\cite{...}` reach the
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

## 6. Source material, and where the numbers came from

The draft was written against the repository, not against its prose. Every
number in the paper traces to `CLAIMS.md`. Two notes on provenance:

**The `collect_res/` result schemas.** The task brief pointed at
`~/Overleaf/ICLR_COLLIE/collect_res/`, described as 23 result-table CSVs plus a
README. **That folder no longer exists**: `~/Overleaf/ICLR_COLLIE` was removed
and replaced by a clone of the IEEE Overleaf project. The generator that built it
survives verbatim in shell history, so all 23 schemas were recovered and used as
the table skeletons here. The recovered index also settles the confirmatory
contrast set as arm 10 against arms 8, 6 and 11, which is what this draft uses.
The folder name says ICLR for historical reasons only; the venue is IEEE UV.

**Two whitelisted numbers were dropped after checking them.** The brief listed
"~1063 tests" and "100% coverage on shipped modules" as statable. Live collection
at `HEAD` returns exactly **1063** tests, so that figure is right, but the
project configures **no coverage gate at all** and the only coverage artifact on
disk measures one file of the 61 under `collie/`. No coverage percentage is
substantiable, so neither the test count nor any coverage figure appears in the
paper. `CLAIMS.md` records both decisions.

---

## 7. Open questions whose answers would change the draft

1. **The running example's family number.** The brief says "family 5 transit
   pause". In the frozen code, family 5 is `shipment_loss` and `transit_pause`
   is the supply leg of family 6, `compound`
   (`collie/data/families/base.py:173-180`). The draft uses family 5, a
   lost-shipment burst, which keeps the brief's family number and its
   supply-disruption character. Switching the running example to the compound
   family would change Sections 4 through 7.
2. **The third confirmatory contrast.** The recovered result index and the brief
   both name arm 11. Design doc 03\_5 §6.3 names telemetry-only adaptive OR, arm
   2, instead. This draft follows the index and the brief, presents arm 11 as C3,
   marks C3 as a benchmark rather than a mechanism contrast, and keeps arm 2 as
   the registered secondary comparator. Nothing is frozen yet, so this is
   reversible in one paragraph.
3. ~~**Whether the page-1 IEEE copyright footer is required.**~~ **Resolved:
   follow the call.** The CFP asks for headers and footers to be removed, so the
   `fancyhdr` block is commented out in `main.tex` and the submission carries no
   header, footer or page number. The block is kept verbatim because the venue's
   own sample installs the footer and the ISBN string is required at
   camera-ready; re-enabling it is two uncomments plus the session designation.

---

## Before submission

- Remove any remaining template text, and confirm every `\pending{}` and
  `\pcell` is gone — `make check` prints the running total.
- Fill the author block; `\AuthorCell` and `\CorrespondingMark` in `main.tex`
  handle multi-author rows.
- Embed all fonts in the final PDF, per the UV2026 submission instructions.
- At camera-ready, re-enable the `fancyhdr` block in `main.tex` (preamble and
  body) and set the session designation, if the venue asks for the ISBN footer.
