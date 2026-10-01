# E6 working notes: estimative terms in FAA Command Center advisories

Working note of 1 October 2026 for experiment E6 of `PLAN.md` (section 5). It is not part of the
registration. E6 is registered by its own amendment at the linker gate on 4 October; everything
marked **draft** below is a proposal for that amendment. Only the development months (April and
May 2026) are parsed or linked. For June to September only the saved files are counted; no
advisory of those months has been opened, and since the review of 1 October (section 13) the
code no longer opens their list pages either before the amendment.

**State on 1 October, after the review.** April and May are complete on disk and linked. The
parser and the linker were reviewed and changed (section 13), and the tables and the gate sheets
were redrawn from the changed code; the sheets of 0610Z are discarded. The download of June to
September ended at 1136Z (section 1). Nothing has been checked by A1 or A2 yet, and no choice of
section 9 has been confirmed by the owner.

## 1. Scope: what the source serves

**Source.** The FAA advisory database at `www.fly.faa.gov/adv/` (US government work). The bare
host `fly.faa.gov` does not resolve; `www.fly.faa.gov` does.

- Daily list, one page per UTC day:
  `https://www.fly.faa.gov/adv/adv_list?whichAdvisories=ATCSCC&advisoryCategory=All&date=YYYY-MM-DD&airflow=true&_airflow=on&ctop=true&_ctop=on&gStop=true&_gStop=on&gDelay=true&_gDelay=on&route=true&_route=on&other=true&_other=on`
  (the GET form at `/adv/advAdvisoryForm`). The page lists every advisory of the day: number,
  control element, brief title, send time.
- One advisory: `https://www.fly.faa.gov/adv/adv_otherdis?adv_date=MMDDYYYY&advn=N`.
- **Past dates are served.** On 1 October 2026 the site returned 31 March and every day from
  1 April 2026 on request, with status 200, no cookie and no session. The Wayback Machine was
  not needed and was not contacted.
- **robots.txt.** `https://www.fly.faa.gov/robots.txt` answered 302 to `/fly/`, which answered
  302 to the status home page on another host (`nasstatus.faa.gov`, not followed: it is outside
  this track's permitted hosts). `/adv/robots.txt` returns an HTML error page. The advisory host
  therefore publishes no robots rules. The collector re-checks at every start and stops if a
  real robots file appears that disallows `/adv/`.
- **What a request carries.** The User-Agent
  `collie-research-fetch/0.1 (academic research; polite, cached)` and nothing else of ours: no
  cookie is stored or sent (the site offers a `JSESSIONID`; it is ignored), no redirect is
  followed.

**Volume and time.**

| Run | Days | Advisories | Requests | Time | Seconds per request |
|---|---|---|---|---|---|
| One-day test, 31 March | 1 | 97 | 99 | 1 min 51 s | 1.12 |
| April | 30 | 3,129 | 3,160 | 58 min 48 s | 1.12 |
| May | 31 | 3,260 | 3,292 | 61 min 1 s | 1.11 |

April and May have 62 to 197 advisories a day (median 99). A request takes about 1.12 seconds:
a one-second pause after each response plus the response itself. The log of the three runs has
no retry and no failure, no two requests in the same second, and no advisory listed but
missing.

The download started at 0405Z on 1 October. June to September ran from 0605Z to 1136Z: 17,725
requests in 5 hours 31 minutes (1.12 seconds per request), with no retry and no failure. The
log (`results/coling/faa/fetch.log`) ends with `END ... status 0`, and every one of its `DAY`
lines, for all six months, ends with `missing 0`: no advisory that a list page names is absent
from disk. `results/coling/faa/fetch_done.txt` is there.

That log is the evidence of completeness for the test months until the amendment.
`python -m analysis.coling.faa` writes `raw_counts_per_day.csv`: for a development day the
files saved, the advisories its list page names and those missing (0 on all 62 days, 31 March
included); for a day of a test month only the count of saved files, because the list page is
not opened before the flag exists. The table on disk was written from a folder holding the
development days only, so it has 62 rows; the first run from the full folder adds one count-only
row per test day.

Six advisory numbers are skipped in the numbering of five development days (11 April: 13;
16 April: 38 and 39; 25 April: 56; 10 May: 34; 11 May: 57). The list pages do not name them,
so they are not "missing" in the sense above, and what they were is not known. They can be
asked for directly (`adv_otherdis?adv_date=04112026&advn=13`, six requests) the next time the
collector is allowed to run.

## 2. What is ready

| File | What it does |
|---|---|
| `analysis/coling/faa_fetch.py` | Collector: list page, then every advisory, cached under `external_data/faa_atcscc/2026/<yyyymmdd>/` (`list.html`, `adv_<nnn>.html`); resumable; `manifest.csv` (file, bytes, sha256), rewritten when a run ends; log in `results/coling/faa/fetch.log`. One request at a time, at least one second apart, backoff 5/20/80/320 s, stop after 3 failed items in a row or 15 in a run, a lock against a second copy. |
| `analysis/coling/faa.py` | Parser (typed advisory records, operations-plan lines), the three statement families with their chains, the month gate, the check that a month is completely on disk, and the per-day table of saved against listed advisories. |
| `analysis/coling/faa_links.py` | Linker, development-month report, seeded sampler for the gate sheets, scorer. |
| `analysis/coling/test_faa.py`, `test_faa_links.py` | 133 tests on trimmed real advisories of 15 July 2024 (the design pilot), on forms seen in April and May 2026, and on made-up day folders for the month gate. |
| `analysis/coling/out/faa/` | `raw_counts_per_day.csv` (all months: files saved, advisories listed, missing; a snapshot until the download ends), `statements_dev.csv`, `links_dev.csv`, `dev_report.json`, `linker_gate_frame.csv`, `linker_gate_meta.json`, `linker_gate_sheet_A1.csv`, `linker_gate_sheet_A2.csv`, `linker_gate_items_A1.md`, `linker_gate_items_A2.md`. |

Commands, from the worktree root with `PYTHONPATH=.` and the study's Python:

```
python -m analysis.coling.faa_fetch --start 2026-04-01 --end 2026-04-30   # collect (resumes)
python -m analysis.coling.faa_fetch --start 2026-04-01 --end 2026-04-30 --manifest-only
python -m analysis.coling.faa                 # parse dev months -> statements_dev.csv, raw counts
python -m analysis.coling.faa_links link      # link dev months -> links_dev.csv
python -m analysis.coling.faa_links report    # counts and sensitivities -> dev_report.json
python -m analysis.coling.faa_links sample    # gate sheets (seed 20261001), dev months only
python -m analysis.coling.faa_links score analysis/coling/out/faa/linker_gate_sheet_A1.csv analysis/coling/out/faa/linker_gate_sheet_A2.csv
python -m pytest analysis/coling/test_faa.py analysis/coling/test_faa_links.py -q
```

The sheets on disk were drawn by `faa.py` with sha256 `dc0ebdd83d6dfcd4...` and `faa_links.py`
with `0e9eb75e7fd24aee...` (`linker_gate_meta.json` has both in full). If either file changes,
the sheets are redrawn before anyone checks them. Once a sheet holds a verdict, `sample`
refuses to write over it: a checked sheet is moved away by hand before another draw.

For months other than the development months, `faa` and `faa_links link` need `--name` (for
example `--name test`): the tables named `dev` take development months only.

**Development / test separation in code.** `faa.check_months` refuses any month after the last
development month unless the flag file `analysis/coling/out/faa/E6_AMENDMENT_REGISTERED` exists.
That file is written by hand when the amendment is pushed; it does not exist now. What the
guard covers, each with a test on a made-up June folder that records every file opened:

- Every function that opens a saved page asks it: `load_day`, `load_months`, `coverage_gaps`,
  and `completeness` for the list pages. `raw_counts` and the count column of `completeness`
  count file names and open nothing.
- A month must be written `YYYY-MM` exactly. `2026-006`, ` 2026-06` or `02026-06` sorted before
  `2026-05` as text and were still read as June by the first version; they are now an error.
- Only a regular file named `E6_AMENDMENT_REGISTERED` counts as the flag. The commands have no
  option to point at another flag (the first version had `--flag`, and any existing path, such
  as `/dev/null`, opened the test months). The tests put their flag in a temporary folder.
- `report` and `sample` refuse test months even when the flag exists.
- No environment variable is read. `--root` chooses the folder, not the months.
- `faa_fetch --manifest-only` (and the end of every collecting run) reads every saved page of
  every month to hash it. It parses nothing and writes only file name, size and sha256.

The development months are the constant `faa.DEV_MONTHS`; if the amendment changes them, that
constant changes with it.

**Coverage.** `load_months` refuses a month that is not completely on disk
(`IncompleteCoverage`): every day needs its list page, every advisory the page names, and
every saved page must parse. "Not extended" and "not issued" are read from the later
advisories, so a day that was not saved must stop the run and not pass for a quiet day. The
lead-in day (31 March) is not held to this.

## 3. What an advisory becomes

`faa.parse_advisory` reads a saved page (or a tag-free pilot file) into an `Advisory`:

- `day`, `number`: the day and number the database lists it under. (An advisory sent at 0000Z
  can carry the previous day's date in its header; the listing is used so that ids stay unique.)
- `sent`: the signature time, UTC. `facility`, `title`.
- `kind`, from the title: `gs` (CDM GROUND STOP), `gs_cnx`, `gdp_proposed`, `gdp`, `gdp_cnx`,
  `afp_proposed`, `afp`, `afp_cnx`, `ctop*`, `gs_manual` (a ground stop written by hand,
  usually for some departure facilities or one airline only), `gs_manual_cnx`, `ops_plan`,
  `reroute` (ROUTE or FCA, RQD / RMD / FYI), `reroute_cnx`, `other`. Any title without `CDM`
  that names a ground stop is a hand-written one (`DFW GROUND STOP (DVRSN EXEMPT)`,
  `CDW GS EXTENSION`). A delay programme or its cancellation under a hand-written title
  (`JVY GROUND DELAY PROGRAM CANCELLATION`) is `gdp` or `gdp_cnx`. A page titled as a programme
  that carries only the cancellation's period is the cancellation.
- `element` (CTL ELEMENT, destination airport or route name), `element_type`, `route_name`,
  `tmi_id`.
- `period`: the stated window (GROUND STOP PERIOD, CUMULATIVE PROGRAM PERIOD or its ANTICIPATED
  form, the CNX periods, EVENT TIME, VALID ... TO ...), resolved to UTC datetimes. An end that
  would make the period longer than 48 hours is a typing error (`25/0040 - 05/0200`) and is
  left unread.
- `prob_extension`: the PROBABILITY OF EXTENSION value exactly as written.
- `plan_lines`: for an operations plan, every timed line of a PLANNED section, with qualifier
  (AFTER / UNTIL / range), time, airports, initiatives and the trailing term as written. A line
  the issuer wrapped is read as one line. A line with two estimates
  (`AFTER 2200 -DEN GROUND DELAY PROGRAM EXPECTED, GROUND STOP POSSIBLE`) gives one record for
  each; the second is about the airports of the first unless it names its own. A slip of one
  letter in an initiative's name is read as the name (`GROUND STOO/DELAY PROGRAM`,
  `DELAY PROGRAOM`). A term is never corrected: `POSSIBL` is no term. A negated term
  (`NOT EXPECTED`, `NO LONGER PROBABLE`) is kept with its negation, as a term of its own.

An "extension" is not an advisory type in this source: an extended ground stop is another
`CDM GROUND STOP` advisory with a later end. Extensions are derived by the linker.

In April and May all 6,389 saved pages parse. Every `CDM GROUND STOP` (644) and every reroute
advisory (832) carries the probability field, and no advisory carries it outside those types
except four hand-written stops for Canadian airports. One title that names a programme stays
unclassified (`SFO CDM GROUND DELAY PROGRAM CORRECTION`, a notice that points to the active
programme's advisory); `dev_report.json` lists such titles.

## 4. Statements (the units of E6) and their chains

Three families. Each statement is taken at its **first issuance**; advisories that repeat it are
kept as `sources`, and lead time is a covariate.

1. **`gs`: probability of extension of a ground stop.** The CDM ground-stop advisories of one
   airport are split into stops ("episodes"): an advisory continues the previous one unless a
   `CDM GS CNX` was sent between the two or its stated start is later than the previous stated
   end. Within a stop, consecutive advisories with the same stated end are one statement (the
   stop re-sent with another scope is not a new estimate of the same end). Lead time: minutes
   from first issuance to the stated end.
2. **`route`: probability of extension of a reroute or flow-constrained area.** Same
   construction on the `VALID ... TO ...` end. Advisories are tied by TMI ID, and must also
   share the route name (one name may extend the other) or say `REPLACES ADVZY n`, because TMI
   IDs are reused from day to day. Of the 180 advisories that say `REPLACES ADVZY n` in April
   and May, 177 keep the TMI ID of the advisory they replace, two take a new one and one could
   not be matched. A `REROUTE CANCELLATION` names the route and is
   attached to the latest earlier advisory of that name (2 of 233 cancellations name a route
   that is in force under two TMI IDs at once).
3. **`plan`: planned ground stop or delay programme in the operations plan.** Lines of the
   `TERMINAL PLANNED` section such as `AFTER 1900 -EWR/LGA/JFK GROUND STOP/DELAY PROGRAM
   PROBABLE`. One statement per airport, initiative set and window text. A line repeated in the
   next operations plan belongs to the same chain; a line that drops out and returns starts a
   new chain; a line whose window text changes (`AFTER 1100` becoming `UNTIL 0200`) is a new
   statement. The term is the one at first issuance; later spellings are kept in `terms_seen`.
   Window: `UNTIL hhmm` runs from first issuance to hhmm; `AFTER hhmm` runs from hhmm to the
   end of the operating day, taken as the next 0800Z (**draft**); a range is used as written.
   The hhmm of `AFTER` is the first one after the plan was sent: the plan sent at 2327Z for the
   day that starts at 0000Z means the next day's 2300Z by `AFTER 2300`. (The first version
   took a time up to 30 minutes before the send time as already begun. The one line that rule
   applied to in April and May, Seattle on 14 May, was read a day early.) Only a plan sent up
   to 60 minutes after its own EVENT TIME is read from that time, so that `AFTER 1600` in the
   plan for 1600Z sent at 1620Z means that day's 1600Z; twelve plans were sent late in the two
   months, and none of their lines is affected.
   Lead time: minutes from first issuance to the window's start (0 for `UNTIL`).

Not built into statements, and why:

- En-route planned lines (`AFTER 1100 -MSP CDRS/SWAP/ARRIVAL ROUTES POSSIBLE`; 3,950 lines in
  April and May) and planned airspace flow programmes (`AFTER 2200 -FCAJXX AFP POSSIBLE`; 106
  lines): PLAN E6 names ground stops and delay programmes, and these lines name route packages
  or placeholder areas that no later advisory identifies reliably.
- Hand-written ground stops (`LGA GROUND STOP`, facilities `ZOB`; 11 in the two months): they
  cover part of the departures, and their extension cannot be read without the facility scope.
- Canadian airports (`CYYZ`, `CYVR`; **draft**): NAV CANADA's programmes reach the database
  under hand-written titles (`CYYZ GROUND DELAY PROGRAM`, `VANCOUVER GDP CANCELLED`), so their
  chains cannot be linked reliably. The two months have 43 such advisories; dropping them
  removes six ground-stop statements and no plan line.
- Plan lines whose element is an area or free text (`N90`, `NY METS`, `EWR SATS`): the area
  part is left out; airports named beside it are kept. No line of April and May is lost this
  way. (The five lines counted here before were `DCA GROUND STOO/DELAY PROGRAM POSSIBLE` on
  26 May, where the misspelling hid the airport; they are read now.)
- Plan lines with no term (five): four that end with the initiative
  (`AFTER 2200 -SFO GROUND DELAY PROGRAM`, in two plans; `AFTER 0200 -SFO GROUND STOP/DELAY
  PROGRAM`; `UNTIL 1800 -AUS GROUND STOP`) and one with a misspelt term (`UNTIL 0000 -SAN
  GROUND STOP/DELAY PROGRAM POSSIBL`). `dev_report.json` lists every such line
  (`terminal_planned_lines_not_used`); the same list has to be read for the test months.
- The free text at the head of a plan, which also carries estimates ("A DELAY PROGRAM FOR SFO
  IS EXPECTED AFTER 2200Z"): PLAN E6 names the planned lines.

## 5. Draft outcome codebook

All times are UTC as written in the advisories. "Actual" means not PROPOSED and not a
cancellation. The checkers read a shorter form of this section at the top of their files
(`faa_links.CODEBOOK`); the two must say the same thing.

**5.1 Extended (families `gs` and `route`).** A statement with stated end *e* is **extended (1)**
when the stop or route goes on past *e* without a break. In full, for a ground stop: there is a
later `CDM GROUND STOP` advisory for the same airport such that (a) no `CDM GS CNX` for the
airport was sent between any two advisories on the way from the statement to it, (b) every
advisory on the way has a stated start no later than the stated end of the one before it (grace
0 minutes, **draft**), and (c) its stated end is later than *e*, by any amount. Otherwise the
statement is **not extended (0)**, with a reason that does not change the outcome: `cancelled`
(a cancellation was sent after the stop's last advisory and no later than its stated end) or
`lapsed` (nothing qualifying followed; a cancellation sent after the stated end is
bookkeeping).

For a route, read "reroute advisory with the same TMI ID and name" and "REROUTE CANCELLATION
naming the route". A route is also extended when it is **carried on under another TMI ID**
(**draft**): an advisory of the same name (the FCA number aside) under another TMI ID is sent
no later than *e* and before any cancellation of the route, and states a start no later than
*e* and an end later than *e* (flag `continued_new_id`). The issuer files the rest of such a
route as a new one (a new FCA number, or the next day's advisory), but the restriction never
stops applying.

Consequences, stated so that the checkers can apply them:

- A stop re-sent with the same end is not an extension. A shortened stop is not an extension
  unless a still later advisory of the same stop goes past *e*.
- A new stop or route that starts after the earlier stated end, or after a cancellation, is a
  new one, even minutes later (flag `new_stop_30` on a stop when the new one starts within 30
  minutes of *e*).
- A delay programme that takes over from a ground stop does not extend the stop (flag
  `gdp_followed`). A hand-written `GROUND STOP CANCELLATION` releases some or all departure
  facilities; it does not close a CDM stop for this rule (flag `manual_release`).
- An advisory sent after *e* still extends the stop when its stated start is no later than *e*.

**5.2 Issued (family `plan`).** A statement for airport *a*, initiative set *I* (ground stop,
delay programme, or either) and window [*s*, *w*] is **issued (1)** when an actual advisory of a
kind in *I* for *a* is sent after the statement's first issuance and no later than *w*, and its
stated period, cut at its own cancellation if that came first, overlaps [*s*, *w*]. A programme
cancelled before its stated start was never in effect and does not count (no case in April and
May). An advisory sent after *w* does not count even when it states a start before *w* (one
case: Orlando on 5 April, sent 2314Z with a start of 2255Z, window to 2300Z). Otherwise
**not issued (0)**. A proposed delay programme alone is not an issuance (flag `proposed_only`).
A programme that ran only before the window opened does not count (flag `outside_window`); one
sent before the window opens whose period reaches into it does. A hand-written ground stop for
the airport counts as a ground stop (**draft**, flag `manual_stop`).

**5.3 Excluded.**

- `already_active`: a named initiative was already running, or already issued and not
  cancelled, for the airport at first issuance, with a stated end at or after the window's
  start. A hand-written stop counts here whenever it counts as an issuance.
  "Running" is read from the send times of the advisories, not from the plan's own
  `TERMINAL ACTIVE` lines. The two differ for 11 of the 1,067 plan statements: ten are
  excluded although the plan lists nothing active (a stop that ends at or just after the
  plan's EVENT TIME), and one is scored although the plan lists the stop as active (Philadelphia
  on 27 May: the stop was sent one minute after the plan and is the advisory that decides
  "issued").
- `unresolved_boundary`: the outcome could still change after the last loaded month and no
  positive evidence was found before it: the stated end, or the window's end, is at or past
  that boundary; or a stop or route has nothing after it and its stated end falls in the last
  two hours of the last month. An extension may be sent after the stated end (up to 21 minutes
  after it for a stop and 49 for a route in April and May), so "lapsed" needs the advisories
  of those two hours. With April and May as development months the rule removes statements
  whose window runs past 31 May 2359Z; no statement falls under the two-hour part.

**5.4 Flags** (kept for sensitivity analyses, never used for the outcome, except that
`continued_new_id` marks the extensions that rest on the carried-on rule): `term_changed`,
`shortened`, `gdp_followed`, `manual_release`, `new_stop_30`, `continued_new_id`,
`manual_stop`, `proposed_only`, `outside_window`.

## 6. Draft term list

A term is a family and a word as written; the family is part of the term because the same word
is linked by a different rule in each family.

| Family | Terms | Spellings folded into them |
|---|---|---|
| `gs` (ground stop, probability of extension) | LOW, MEDIUM, HIGH | MED into MEDIUM (seen on hand-written stops of 2024; none on a CDM stop in April or May) |
| `route` (reroute or FCA, probability of extension) | NONE, LOW, MODERATE, HIGH | MOD into MODERATE (none in April or May) |
| `plan` (planned ground stop or delay programme) | POSSIBLE, PROBABLE, EXPECTED | POSS into POSSIBLE, PROB into PROBABLE (none in April or May) |

LIKELY, UNLIKELY and ANTICIPATED are recognised on plan lines and would appear as terms of
their own; April and May have none. A negated term (`NOT EXPECTED`, `NO LONGER PROBABLE`,
`NEVER ...`) would also appear as a term of its own, with the negation, and never under the
term it negates; April and May have none on a terminal line. The first version had no check
for negation. MEDIUM is written only on ground stops and MODERATE only on
reroutes, as PLAN E6 expects ("MEDIUM against MODERATE is reported as confounded with programme
type"). RELATED.md records that no FAA definition of these levels has been found; the terms are
the issuer's own vocabulary.

## 7. Development months: counts

April and May 2026: 6,389 advisories on 61 days.

| Kind | Advisories |
|---|---|
| Reroute or FCA advisories, and their cancellations | 832, 232 |
| CDM ground stops, and their cancellations | 644, 234 |
| Operations plans | 533 |
| Delay programmes: actual, proposed, cancellations | 292, 206, 224 |
| Airspace flow programmes: actual, proposed, cancellations | 31, 26, 29 |
| Hand-written ground stops, and their releases | 11, 38 |
| Others (volcanic-ash bulletins, hotlines, arrival-delay notices and the like) | 3,057 |

The plans hold 2,422 usable `TERMINAL PLANNED` lines: 2,204 POSSIBLE, 184 PROBABLE, 34 EXPECTED.

**2,413 statements**, 892 of them repeated in at least one later advisory. The plan family has
1,067 statements on 627 airport-days. (Before the review of 1 October: 2,404 statements, 2,359
scored. The difference is nine plan statements gained, eight of them scored, and two re-keyed
from "ground stop" to "ground stop or delay programme"; section 13.)

| Term | Statements | Excluded | Scored | Outcome 1 | Share | Days |
|---|---|---|---|---|---|---|
| gs:LOW | 52 | 1 | 51 | 9 | 0.18 | 32 |
| gs:MEDIUM | 536 | 1 | 535 | 214 | 0.40 | 60 |
| gs:HIGH | 8 | 0 | 8 | 3 | 0.38 | 7 |
| route:NONE | 75 | 0 | 75 | 1 | 0.01 | 26 |
| route:LOW | 324 | 0 | 324 | 29 | 0.09 | 58 |
| route:MODERATE | 327 | 1 | 326 | 84 | 0.26 | 53 |
| route:HIGH | 24 | 0 | 24 | 16 | 0.67 | 7 |
| plan:POSSIBLE | 974 | 40 | 934 | 317 | 0.34 | 61 |
| plan:PROBABLE | 75 | 2 | 73 | 51 | 0.70 | 36 |
| plan:EXPECTED | 18 | 1 | 17 | 15 | 0.88 | 15 |
| All | 2,413 | 46 | 2,367 | 739 | | 61 |

Outcome 1 is "extended" (`gs`, `route`) or "issued" (`plan`). These are development-month
shares under the draft codebook, before any hand check; they are not results.

By outcome code: ground stops 226 extended, 213 cancelled, 155 lapsed, 2 at the boundary;
routes 130 extended (16 of them carried on under a new TMI ID), 243 cancelled, 376 lapsed, 1 at
the boundary; plan lines 383 issued, 641 not issued, 29 already active, 14 at the boundary.

Lead time, quartiles in minutes: ground stops 57, 65, 71 (to the stated end); routes 215, 303,
475 (to the stated end); plan lines 0, 307, 938 (to the window's start).

Flags on the 2,413 statements: `gdp_followed` 92, `term_changed` 38, `manual_release` 29,
`new_stop_30` 26, `outside_window` 23, `shortened` 21, `continued_new_id` 16, `proposed_only`
3, `manual_stop` 2.

Outcomes that would change under another choice:

| Choice | Outcomes changed |
|---|---|
| A new stop within 30 minutes of the stated end counted as an extension | 26 (LOW 4, MEDIUM 20, HIGH 2) |
| A route carried on under a new TMI ID **not** counted as an extension | 16 (HIGH 14, MODERATE 2) |
| Grace of 15 minutes between a stated end and the next stated start | 3 |
| Grace of 30 minutes | 9 |
| Hand-written stops not counted as issued | 3 |
| An extension of under 15 minutes not counted | 0 |
| Operating day ends at 0600Z or at 1000Z instead of 0800Z | 0 |
| An initiative sent before the window opens not counted (it must be sent inside the window) | 58 (POSSIBLE 39, PROBABLE 13, EXPECTED 6) |

The last row is choice 7. Of the 383 "issued" outcomes, 139 rest on an advisory sent before the
window opened whose period reaches into it (a programme published at 1108Z for 1300Z, under
`AFTER 1300`); for 58 of them no other advisory was sent inside the window.

The second row decides what route:HIGH looks like: 16 of 24 extended under the draft, 2 of 24
if only the same TMI ID counts. The 14 statements are twelve South Florida routes of 24 April
and 1 May ("issued due to special operations") and two statements of one Lake Erie route, each
carried on at its stated end under a new FCA number.

## 8. The linker gate on 4 October

**What the gate needs from people.**

1. The owner settles choice 3 and confirms the pass rule (choice 13) **before** the checkers
   start, and is told that choices 1, 2 and 4 to 10 stand as drafted unless the owner says
   otherwise (section 9 sorts the choices). If a rule changes, the sheets are redrawn with
   `faa_links sample` (same seed) and the old ones are discarded.
2. A1 and A2 check the links. Each has a reading file (`linker_gate_items_A?.md`) and a sheet
   (`linker_gate_sheet_A?.csv`). The reading file opens with the instructions and the codebook.
   Each item gives, in this order: the statement; the source advisory; the list of every
   ground-stop, delay-programme or route advisory the linker could see for that airport or
   route; the titles of the other advisories that name the airport in the same hours, which
   the linker does not read; and only then the derived outcome and the advisory that decides
   it. The checkers work out the outcome from the advisories before they read the derived one,
   and write `ok`, `wrong` or `unclear` in `verdict`. For `wrong` or `unclear` they add one
   error code (`S` source misread, `M` missed advisory, `L` wrong link, `R` rule misapplied,
   `X` exclusion wrong, `D` codebook gap) and a note. They judge against the codebook as
   written; a rule they would have chosen differently is a note, not an error. The sheet does
   not show the derived outcome, and it does not mark the rows that are on both sheets: the
   checkers do not confer on any row before both sheets are returned.
3. The owner runs the scorer on the two returned sheets and decides the gate.
4. If the gate passes, the amendment is written (codebook, months, term list, as fixed), pushed,
   and only then is the flag file created and any test month parsed.

**The sheet.** 269 rows drawn with seed 20261001 from the 2,367 scored links and the 46
excluded statements of April and May: 259 scored links (30 per term, or all of a term's links
when the two months hold fewer: 8 for gs:HIGH, 17 for plan:EXPECTED, 24 for route:HIGH) and 10
excluded statements. 30 scored links go to both checkers and the rest alternate, so A1 has 150
rows (71 route, 42 plan, 37 ground stop; 145 scored and 5 excluded) and A2 has 149 (59 route,
50 plan, 40 ground stop; 144 scored and 5 excluded). Neither sheet alone reaches 150 scored
links or the per-term numbers: the gate needs both sheets filled in full, and an empty verdict
leaves its term short. The reading files hold about 33,400 and 33,700 words. **Time: about 3
hours per checker** (up to 4): a ground-stop or route link takes under a minute, a plan link
one to three, and the instructions a quarter of an hour.

The draw is reproducible: the same command on the same code gives the same files to the byte
(checked twice on 1 October).

**Scoring rule (draft).** `faa_links score` counts a link correct when its verdict is `ok`; a
link checked by both is correct only when both say `ok`; `unclear` is not correct. The gate
passes when at least 150 links are checked, every term has 30 checked links (or all of its
links when the development months hold fewer), and at least 90% of checked links are correct.
Shares per term are printed, terms under 90% are listed and the error codes are tallied, but
the pass rule is on the overall share. The ten excluded statements in the sheet are scored
separately and do not count. The result is written to `linker_gate_score.json`.

**If the gate fails.** The error codes say what to fix. A fix changes a rule or the parser,
never single links; after a fix a fresh sample is drawn from the development months
(`faa_links sample --draw 2`) and checked again. The checked sheets of the first draw are moved
to another folder first: they are the record of the failed gate, and `sample` does not write
over a sheet that holds verdicts. With the paper due on 12 October there is room
for one repeat at most.

**What was checked before the sheets went out.** About 130 links were read against the
codebook while the linker was written (April, then 28 plan links of May that the code had not
seen). One inconsistency was found and fixed (a hand-written stop running at issuance), and the
reading of route:HIGH led to the carried-on rule. This is not the gate: it was done by the
person who wrote the linker.

## 9. Open choices for the amendment

Each line gives the draft, the alternative, and what is known about the difference. Counts are
for the development months (section 7). Choices 1 to 10 change what the sheet shows or what a
link's outcome is; the others are for the amendment text.

The review of 1 October sorts them by who has to decide, and when:

- **For the owner, before the sheets go out: choices 3 and 13.** Choice 3 decides the realised
  rate of one term (route:HIGH, 16 of 24 or 2 of 24), was drafted after that rate had been
  seen, and marks 14 rows of the sheet. Choice 13 is the pass rule of the gate; it has to be
  fixed before any verdict is seen.
- **Decided by the draft unless the owner objects: choices 1, 2 and 4 to 10.** For 1 and 9 the
  draft is what PLAN E6 says. For 4 and 5 no outcome depends on the choice. For 2, 6, 7, 8 and
  10 the draft is the plain reading, and the alternative changes few outcomes or is clearly the
  worse reading (7). The alternatives of 2, 6 and 10 stay available as sensitivity analyses
  through the flags and the linker's switches.
- **For the amendment, after the gate: choices 11, 12 and 14 to 17.** None changes a sheet.

1. **Families in the term list.** Draft: all three (`gs`, `route`, `plan`), ten terms.
   Alternative: drop `route`. It adds 114 rows to the sheet (about an hour per checker), and
   its HIGH and NONE terms sit on few days (planned events such as rocket launches, air shows
   and special operations).
2. **What "extended" means for a ground stop.** Draft: a later end within the same stop, with
   no cancellation in between and no gap (grace 0). Alternatives: a grace of 15 or 30 minutes
   (3 or 9 outcomes); or count any new stop that starts within 30 minutes of the stated end
   (flag `new_stop_30`, 26 outcomes), which also covers a stop cancelled and issued again.
3. **What "extended" means for a route.** Settled by the owner on 1 October, before the gate
   sheets went out: the draft stands, and the alternative is registered as a sensitivity
   analysis. Draft: the same TMI ID and name, or the same name
   carried on under a new TMI ID without a break (5.1). Alternative: the same TMI ID only,
   which is what the issuer calls an extension (`REPLACES/EXTENDS ADVZY n` keeps the TMI ID).
   16 outcomes differ, 14 of them among the 24 route:HIGH statements (section 7), so this
   choice decides the realised rate of that term.
4. **Any amount counts.** Draft: an end moved by one minute is an extension. A minimum of 15
   minutes changes no outcome in April and May.
5. **Plan window for `AFTER hhmm`.** Draft: to the next 0800Z. Ending the operating day at
   0600Z or 1000Z changes no outcome.
6. **Hand-written ground stops.** Draft: they count as an issuance for a planned ground stop
   (3 outcomes) and as a running stop for the exclusion; they give no extension statement.
7. **Early issuance.** Draft: a programme sent before the window opens counts when its stated
   period reaches into the window. Alternative: require the advisory to be sent inside the
   window, which changes 58 of the 383 "issued" outcomes to "not issued" (POSSIBLE 39,
   PROBABLE 13, EXPECTED 6). The draft is the plain reading: a programme published at 1108Z
   for 1300Z is what `AFTER 1300 ... EXPECTED` announced.
8. **Exclusions.** Draft: `already_active` (29) and `unresolved_boundary` (17) as in 5.3;
   Canadian airports give no statement. Alternative for `already_active`: score such lines as
   "issued" only when a further advisory extends the running initiative into the window.
9. **Unit of a plan statement.** Draft, as PLAN E6 says: one per airport, initiative set and
   window text, so `MIA/FLL/PBI GROUND STOP POSSIBLE` gives three statements with one term.
   Alternative: one per line, issued when any named airport gets the initiative. A changed
   window text (`AFTER 1100` becoming `UNTIL 0200`) starts a new statement in both.
10. **Term at first issuance.** Draft: the term first written; a later advisory with the same
    stated end and another term is recorded (`term_changed`, 38) and not scored on its own.
11. **Development and test months.** Draft: April and May for development, June to September
    for test. April alone would leave four terms under 30 links for the gate.
12. **Minimum size for a per-term result.** The rare terms (gs:HIGH, plan:EXPECTED, route:HIGH)
    may stay small in the test months. Draft: report a term on its own only with at least 30
    scored statements on at least 10 days in the test months; pool the others by family.
13. **Gate threshold and scoring.** Settled by the owner on 1 October, before any verdict: 90%
    of all checked links; a link checked by both is correct only when both say `ok`; `unclear`
    is not correct; the pass rule is on the overall share, not per term; the ten excluded
    statements are reported apart.
14. **Boundary of the test months.** Draft: statements whose outcome needs 1 October are
    excluded. Alternative: download 1 October (possible from 2 October 0000Z) as a look-ahead
    day that gives no statement.
15. **Items and calls.** PLAN section 9 budgets about 1,200 calls per model. Draft: the ten
    terms in isolation under two framings (20 calls), and a seeded sample of 295 test-month
    statements, stratified by term, each read in context under two framings with the term
    shown and with the term masked (1,180 calls). The realised rate per term uses every scored
    test statement and needs no call.
16. **References the three gaps need.** The perception gap needs an author reading of each
    term (who, and when: before the test months are linked). Issuer calibration needs "the
    conventional meaning"; no FAA definition has been found (RELATED.md), so the amendment has
    to name the reference (the author reading, or a published scale of verbal probabilities).
17. **Covariates of the registered model.** Draft: term, family, lead time in minutes
    (log-scaled), airport or route, hour of first issuance; clustered by UTC day of first
    issuance.

## 10. What remains to build for the E6 runs

Nothing below exists yet. Hours are rough; the total is about 22 hours of work.

1. **Items for the reading harness (about 5 hours).** For each sampled statement, the prompt
   text in two presentations (the term in isolation, with only the field name or the line
   template; the term in context, with the source advisory as the gate sheet shows it) and two
   framings (what probability the writer conveys; the probability that it will happen: the stop
   or route is extended, the initiative is issued in the window). A masked variant with the
   term replaced by `[TERM]`. The item builder must show nothing sent after the statement's
   first issuance: for a plan line that means the plan's own text only, and for a ground stop
   the first advisory only.
2. **Wiring into `read.py` (about 3 hours).** A probability-only prompt and parser, the spend
   caps, the cache, the study ledger. `read.py` has another owner.
3. **Baselines (about 4 hours).** The term-frequency lookup (realised rate per term in the
   development months, the table of section 7 after the gate); a logistic model on airport,
   hour and programme type fitted on the development months (scikit-learn is available); the
   masked-hedge ablation (item 1); perfect information.
4. **Scoring (about 5 hours).** Brier score and its decomposition, cost-loss expense at C/L of
   0.2, 0.5 and 0.8 relative to climatology, the three gaps of PLAN E6.
5. **GEE clustered by day (about 3 hours).** statsmodels is not installed, so the test is coded
   by hand (logistic GEE with an independence working correlation and a cluster-robust sandwich
   variance) or replaced by a cluster bootstrap over days, as DECISIONS 15 allows for E5. The
   cluster is the UTC day of first issuance (`day` in `links_*.csv`): at most 122 clusters in
   the test months, and far fewer for the rare terms (7 days each for gs:HIGH and route:HIGH in
   the development months).
6. **The amendment text (about 2 hours)** and the test-month run of `faa`, `faa_links link`
   after the flag exists (both with `--months` and `--name test`), with the boundary rule
   applied at 30 September 2359Z. Before any outcome of the test months is tabulated, the
   listings of unclassified titles and of planned lines that gave no statement are read.

## 11. Risks

1. **Checker time on 3 and 4 October.** The gate needs about 3 hours from each of A1 and A2 on
   days already given to the main labelling (DECISIONS 2). If only one checker is free, one
   person can fill both sheets (about 5 hours); the 30 double checks are then lost.
2. **Disputed rules read as errors.** The rules of choices 2, 3 and 7 are judgement calls. The
   reading file tells the checkers to judge against the codebook as written, and the flags mark
   the affected links, but a checker who marks them `wrong` or `unclear` can sink the gate: 21
   of the 259 scored links in the sheet (8%) carry `continued_new_id` or `new_stop_30`, against
   a margin of 25 links. The owner should settle choice 3 before the sheets go out (14 of the
   21 links hang on it) and let the checkers know that the other rules stand as written.
3. **Rare terms.** The two development months have 8 statements for gs:HIGH, 18 for
   plan:EXPECTED and 24 for route:HIGH, on 7 to 15 days; route:HIGH is six events. The gate
   takes all of them; the experiment may not be able to say anything about them on their own
   (choice 12), and a per-term claim such as PLAN E6's "differs by at least 15 points" is only
   safe for the six common terms.
4. **After the gate.** About 22 hours of building remain, part of it in a file with another
   owner, between the gate on 4 October and the freeze of numbers on 6 October, while the
   confirmatory runs are under way. This, not the gate, is where E6 is most likely to be cut.
5. **The download.** Finished at 1136Z on 1 October with no retry and no failure (section 1).
   The linker refuses a month that is not completely on disk, so a later loss of files would
   stop the run and not change outcomes.
6. **No stated definition of the terms.** Issuer calibration "against the conventional
   meaning" has no source yet (choice 16).
7. **Dependence.** Statements of one airport and day share weather and staffing, one stop
   gives several statements (one per stated end), and one plan line gives one statement per
   airport. The registered test clusters by day; the descriptive rates per term should be read
   with the number of days beside them.
8. **Parser coverage in the test months.** The parser was written on July 2024 and on April
   and May 2026. Summer months may bring forms not seen yet (CTOP, new title spellings, other
   terms on plan lines). `dev_report.json` lists titles that name a programme without being
   classified; the same listing has to be read for the test months before their outcomes are
   tabulated, and a parser change after the amendment is a logged deviation.
9. **The hand check is of links, not of statements.** The checkers see what the linker saw
   for one airport or route, and, since the review, the titles of the other advisories that
   name the airport in the same hours. An advisory filed under another element would still be
   missed by both, and so would a statement the parser never built. The titles listing (item
   8), the listing of planned lines that gave no statement, and the count of advisories listed
   against saved (section 1) are the guards.
10. **Plans that list an initiative as active before its advisory is sent.** The plan of
    27 May 1956Z lists the Philadelphia ground stop as active; the stop's advisory was sent at
    1957Z and is the one that makes the plan's own line "issued". The codebook reads "running"
    from send times (5.3), so the link is right as written, but a checker may see it as wrong.
    One such link in April and May; it is not in the sheet.

## 12. Log of what was done on 1 October

- 0401Z: robots check by hand (see section 1); the search form and one list page and one
  advisory of 1 April fetched to learn the URL patterns (5 requests).
- 0403Z to 0405Z: one-day test of the collector on 31 March 2026 (99 requests, no error). 31
  March is kept as a lead-in day: it is read as context for 1 April and gives no statement.
- 0405Z: bulk download started as one background process: April, then May, then June to
  September, one request at a time. April ended at 0504Z and May at 0605Z (6,452 requests, no
  retry); June to September started at 0605Z.
- The first version of the linker used a 15-minute grace between a stated end and the next
  stated start. The two cases it changed in the first eleven days of April were both new stops
  after a cancellation, so the draft grace is 0.
- The first version excluded a plan line whenever the named initiative was running at issuance.
  That wrongly removed next-day lines issued during the previous evening's stop; the exclusion
  now requires the running initiative's stated end to reach the line's window.
- Rules added after reading April and May: a hand-written stop running at issuance excludes
  the plan line, as a CDM stop does; Canadian airports give no statement; a cancellation
  between two advisories always separates two stops; hand-written titles for stops and delay
  programmes are classified; a period longer than 48 hours is a typing error; a hand-written
  advisory that names two airports is seen for each; flag `new_stop_30`.
- The first version counted a route as extended only under the same TMI ID. Under it 2 of 24
  route:HIGH statements were extended, because 14 were carried on at their stated end under a
  new FCA number. The draft now counts a route carried on without a break (5.1), keeps the flag
  `continued_new_id`, and reports the strict reading as a sensitivity (choice 3).
- 0610Z: final run of the parser, the linker and the report on April and May; gate sheets
  drawn.
- After 1136Z: review of the collector, the parser, the linker and the sheets (section 13);
  tables and sheets redrawn from the changed code.

## 13. Review of 1 October

A second reading of `faa_fetch.py`, `faa.py`, `faa_links.py`, their tests and the sheets, on the
development months only. No file of June to September was opened, and the flag file was not
created outside the tests' temporary folders. The figures of the first version were reproduced
to the byte before any change (6,389 advisories, 2,404 statements, 2,359 scored, sheets of 149
and 148 rows), so the differences below come from the changes and from nothing else.

**The collector** keeps the network rules: the User-Agent is exactly `collie-research-fetch/0.1
(academic research; polite, cached)` and the only header the code sets; no cookie, no redirect
followed, nothing personal in any URL; at least one second between the end of one request and
the start of the next (1.12 s in practice); a file on disk is never fetched again. It was not
run and not changed.

**The month guard** had four ways round it, all closed now (section 2): a month written
`2026-006` or with a leading blank; `--flag` pointing at any existing path; `load_day` called
directly; and `completeness`, which opened the list pages of every month whenever
`python -m analysis.coling.faa` ran. A list page carries the title and the send time of every
advisory of its day. The run of 0610Z did open the list pages of the three June days then on
disk; it took the advisory numbers from them and nothing else, and wrote three rows of counts
(the old `raw_counts_per_day.csv`). The disclosure in PLAN.md ("the code refuses any later
month") should say so.

**The parser, read by eye.** 34 advisories drawn with the seed, one of each of the 14 types and
two for each of the ten terms: every advisory number, day, facility, type, element, send time
and term was read correctly, and so were the 37 planned terminal lines of the seven plans, their
carry-over and their windows, including the periods that cross midnight. One span differs: a
hand-written stop relayed for Toronto carries both `EVENT TIME` and `GROUND STOP PERIOD`, and
the start is taken from the first (1055Z, not 0958Z); Canadian airports give no statement, so
nothing follows from it. Reading every `TERMINAL PLANNED` line of the two months then found what
the sample had not:

| Found | Lines | Effect before the fix |
|---|---|---|
| `AFTER 2300 -SEA ...` in the plan sent at 2327Z for the next day | 1 | window a day early |
| `BOS GROUND STOP/DELAY PROGRAOM POSSIBLE` | 3 | read as ground stop only (2 statements) |
| `BOS GROUND DELAY PROGRAOM POSSIBLE` | 1 | no statement |
| `DCA GROUND STOO/DELAY PROGRAM POSSIBLE` | 5 | no statement (3 lost) |
| two wrapped lines with two estimates each (4 May, plan 059) | 2 | no statement (5 lost, 2 of them EXPECTED) |
| negation (`NOT EXPECTED`) | 0 | would have been read as EXPECTED |

After the fixes: nine statements more (2,413), two re-keyed, one window moved; every other
statement and link is unchanged, row for row.

**The linker, read by eye.** 40 scored links drawn with the seed (four per term) and 5 excluded
statements, each against every advisory that names the airport or the route, of any type, in
the hours around it: 40 of 40 follow the codebook as written, and so do the 5 exclusions. The
draw held no extended ground stop, so 8 extended stops and 4 extended routes were drawn in
addition: 12 of 12 follow it. With 40 of 40 the 95% interval for the linker's precision against
the codebook is 91% to 100%. Three of the 40 are route:HIGH links that are "extended" only
under the carried-on rule (choice 3). Two cross-checks against the plans' own `TERMINAL ACTIVE`
lines found no advisory the linker had missed. They found the eleven differences of 5.3, and
five "not issued" outcomes for which a later plan lists the initiative as active near the edge
of the window. All five are right by 5.2 as written: a stop sent 14 minutes after the window
closed, with a stated start inside it; two stops that began within ten minutes after the
window closed; a programme published inside the window for a period after it; and a stop that
ended before the window opened.

**"Did not happen" and missing files.** The 62 development days are complete against their
list pages. The linker now refuses an incomplete month (section 2), and "lapsed" is no longer
concluded in the last two hours of the loaded months (5.3).

**The sheets.** Reproducible from the seed; 30 links on both sheets, as stated; the union meets
the gate's counts and neither sheet does alone (section 8). Three things anchored the checker
and were changed: the derived outcome stood in bold above the evidence and in a column of the
sheet; the rows checked twice were marked; and the only list in which a missed advisory could
be looked for was the linker's own.

**The tests.** 91 before, 133 now. 35 single changes to the code (the month guard switched
off, a window bound swapped, the negation check dropped, a cancellation ignored, and so on)
each make at least one test fail; three of them passed unseen before tests were added (an
equal end counted as an extension, an advisory sent after the window counted, a programme
cancelled before its start counted). The code was restored after each change and the hashes
compared.

**Left as it is.** A misspelt term gives no statement (one line, `POSSIBL`). The free text at
the head of a plan is not read. `UNTIL hhmm` in a plan sent just after hhmm would be read as a
window of nearly a day; April and May have no such line (the shortest `UNTIL` window is over 20
minutes, the longest 16 hours 15 minutes).
