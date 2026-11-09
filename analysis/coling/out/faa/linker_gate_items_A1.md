# E6 linker gate: hand check of links (A1)

Development months only. For each link, read the source advisory and the later advisories, and
decide whether the derived outcome follows the draft codebook below. Judge against the codebook
as written, also where you would have chosen another rule: a rule you disagree with is a note,
not an error. Write the verdict in `linker_gate_sheet_A1.csv`, column `verdict`: `ok`, `wrong` or `unclear`. For
`wrong` or `unclear`, add one error code and a short note.

Error codes:

- `S`: source misread: the term, airport, initiative or window is not what the advisory says
- `M`: missed advisory: a later advisory that changes the outcome was not used
- `L`: wrong link: the linked advisory is another stop, route, airport or initiative
- `R`: rule misapplied: the advisories are right but the outcome contradicts the codebook
- `X`: exclusion wrong: excluded but should be scored, or scored but should be excluded
- `D`: codebook gap: the codebook does not decide this case

Each item gives the statement, the source advisory and the later advisories first, and the
derived outcome last. Work out the outcome from the advisories before you read the derived
one.

Times are written day/hhmm. The first list under each item shows every ground-stop,
delay-programme or route advisory the linker could see for the airport or route, up to two
hours after the stated end (one hour after a plan line's window, and from six hours before the
plan); check that none of them was missed. A second list, when there is one, gives the titles
of the other advisories that name the airport in the same hours; the linker does not read
them, and one that is a ground stop or a delay programme under another title is an `M`.

Some rows are also on the other checker's sheet. They are not marked; do not confer on any
row before both sheets are returned.

## Draft codebook

The full text is section 5 of `analysis/coling/plan/E6_NOTES.md`. All times are UTC.

**Ground stops and routes (probability of extension).** The statement is the first advisory
that states an end time for a stop or a route. It is EXTENDED when a later advisory of the same
stop or route states a later end, by any amount.

- The same stop: `CDM GROUND STOP` advisories for the airport, each sent with no `CDM GS CNX`
  between it and the one before, and each with a stated start no later than the stated end of
  the one before.
- The same route: advisories with the same TMI ID and the same name (one name may extend the
  other), with no `REROUTE CANCELLATION` of that name between them. A route is also carried
  on, and so EXTENDED, by an advisory of the same name under another TMI ID (a new FCA number,
  or the next day's advisory) when that advisory is sent no later than the stated end and
  before any cancellation of the route, and states a start no later than the stated end and
  an end later than it (flag `continued_new_id`).
- Otherwise NOT EXTENDED: "cancelled" when a cancellation followed no later than the stated
  end, "lapsed" when nothing followed. A wrong reason with the right outcome is still `ok`;
  say so in the note.
- Not extensions: the same end sent again; a shorter end; a new stop or route that starts
  after the stated end or after a cancellation, even minutes later (flag `new_stop_30` on
  stops); a delay programme that follows the stop (flag `gdp_followed`). A hand-written
  `GROUND STOP CANCELLATION` does not close a CDM stop (flag `manual_release`).

**Planned ground stops and delay programmes (operations plan).** The statement is the first
plan that carries the line for that airport with that window. A line that names several
airports gives one statement for each. A line with two estimates (`DEN GROUND DELAY PROGRAM
EXPECTED, GROUND STOP POSSIBLE`) gives one statement for each estimate.

- Window: `UNTIL hhmm` runs from the plan's send time to hhmm; `AFTER hhmm` runs from the
  first hhmm after the plan was sent to the next 0800Z (a plan sent at 2327Z that says `AFTER
  2300` means 2300Z of the next day); a range is used as written.
- ISSUED when an actual advisory of a named initiative for the airport is sent after the plan
  and no later than the window's end, and its stated period, cut at its own cancellation if
  that came first, overlaps the window. Actual advisories are `CDM GROUND STOP`,
  `CDM GROUND DELAY PROGRAM` and a hand-written `<airport> GROUND STOP` (flag `manual_stop`);
  a `PROPOSED` programme is not one. A line that names both initiatives is met by either. An
  advisory sent before the window opens counts when its period reaches into the window; one
  cancelled before its stated start does not count.
- Otherwise NOT ISSUED.

**Excluded.** `already_active`: a named initiative was running for the airport when the plan
was sent, with a stated end at or after the window's start; "running" is read from the send
times of the advisories, not from the plan's `TERMINAL ACTIVE` lines. `unresolved_boundary`:
the outcome could still change after the last development month (a window or a stated end
that reaches past the month's last day, or a stated end in the last two hours of that day
with nothing after it). Canadian airports give no statement.


## 1. route-20260501-080

- Term: **HIGH** (route:HIGH); written as: `PROBABILITY OF EXTENSION: HIGH`
- Element: FCA012:MIA_VIA_MOGAE; initiative: reroute; first issued 05/01 17:04Z in 20260501-080; window read as 01/2115Z - 02/0200Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 080 DCC 05/01/2026 FCA RQD
NAME: FCA012:MIA_VIA_MOGAE
CONSTRAINED AREA: ZJX/ZMA
REASON: OTHER
INCLUDE TRAFFIC: CZU/CZY/KBWI/KCHO/KCLT/KDCA/KDET/KDTW/KFNT/KIAD/KJF
K/KLAN/KMBS/KORF/KPHF/KPHL/KPTK/KRDU/KRIC/KYIP/ZAU/
ZBW/ZDV/ZID/ZJX/ZKC/ZME/ZMP/ZNY/ZOB/ZTL DEPARTURES
TO KMIA
FACILITIES INCLUDED: CZU/CZY/ZAU/ZBW/ZDC/ZDV/ZID/ZJX/ZKC/ZMA/ZME/ZMP
/ZNY/ZOB/ZTL
FLIGHT STATUS: ALL_FLIGHTS
VALID: FCA ENTRY TIME FROM 012115 TO 020200
PROBABILITY OF EXTENSION: HIGH
REMARKS: SEE DYNAMIC LIST FOR UPDATES. AIRCRAFT FILED VIA AR AND Y
ROUTES ARE EXEMPT.  THIS ROUTE IS ISSUED DUE TO SPECIAL
OPS.
ASSOCIATED RESTRICTIONS:
MODIFICATIONS:
ROUTES: [route table not shown]
TMI ID: RRDCC515
```

Every advisory the linker could see for this element in the horizon:

```
20260502-007  sent 05/02 00:05Z  FCA RQD  FCA028:MIA_VIA_MOGAE  VALID 02/0200Z - 02/2315Z  [PROBABILITY OF EXTENSION: MODERATE]
```

**Derived outcome: EXTENDED = 1**. end 02/0200Z -> 02/2315Z (+1275 min), carried on as FCA028:MIA_VIA_MOGAE under TMI ID RRDCC527. Flags: continued_new_id.

Advisory that decides the outcome:

```
ATCSCC ADVZY 007 DCC 05/02/2026 FCA RQD
NAME: FCA028:MIA_VIA_MOGAE
CONSTRAINED AREA: ZJX/ZMA
REASON: OTHER
INCLUDE TRAFFIC: CZU/CZY/KBWI/KCHO/KCLT/KDCA/KDET/KDTW/KFNT/KIAD/KJF
K/KLAN/KMBS/KORF/KPHF/KPHL/KPTK/KRDU/KRIC/KYIP/ZAU/
ZBW/ZDV/ZID/ZJX/ZKC/ZME/ZMP/ZNY/ZOB/ZTL DEPARTURES
TO KMIA
FACILITIES INCLUDED: CZU/CZY/ZAU/ZBW/ZDC/ZDV/ZID/ZJX/ZKC/ZMA/ZME/ZMP
/ZNY/ZOB/ZTL
FLIGHT STATUS: ALL_FLIGHTS
VALID: FCA ENTRY TIME FROM 020200 TO 022315
PROBABILITY OF EXTENSION: MODERATE
REMARKS: SEE DYNAMIC LIST FOR UPDATES. IMPLEMENTED DUE TO SPECIAL
OPERATIONS. AIRCRAFT ON ILM AREA AR/ATLANTIC Y ROUTES ARE
EXEMPT.
ASSOCIATED RESTRICTIONS:
MODIFICATIONS:
ROUTES: [route table not shown]
TMI ID: RRDCC527
```

## 2. plan-20260531-038-TPA-gs-UNTIL2300

- Term: **POSSIBLE** (plan:POSSIBLE); written as: `UNTIL 2300	-MCO/TPA GROUND STOP POSSIBLE`
- Element: TPA; initiative: gs; first issued 05/31 15:38Z in 20260531-038; window read as 31/1538Z - 31/2300Z
- Repeated in: 20260531-047 20260531-057

Source advisory:

```
ATCSCC ADVZY 038 DCC 05/31/2026 OPERATIONS PLAN
EVENT TIME: 31/1600 - AND LATER
TERMINAL ACTIVE:
UNTIL 2059	-SFO GROUND DELAY PROGRAM
TERMINAL PLANNED:
AFTER 1800	-ATL GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1800	-BOS GROUND STOP/DELAY PROGRAM POSSIBLE
UNTIL 2300	-MCO/TPA GROUND STOP POSSIBLE
```

Every advisory the linker could see for this element in the horizon:

```
(none)
```

Other advisories that name the element (not read by the linker):

```
20260531-045  sent 05/31 17:24Z  MIA / OPF / TMB / FLL / FXE / PBI / RSW / BCT / TPA / SRQ CDRS_FYI
```

**Derived outcome: NOT ISSUED = 0**. no gs advisory for TPA in the window.

No advisory decides the outcome (nothing qualifying was found).

## 3. plan-20260507-062-TEB-gs+gdp-AFTER1900

- Term: **PROBABLE** (plan:PROBABLE); written as: `AFTER 1900	-TEB GROUND STOP/DELAY PROGRAM PROBABLE`
- Element: TEB; initiative: gs/gdp; first issued 05/07 17:59Z in 20260507-062; window read as 07/1900Z - 08/0800Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 062 DCC 05/07/2026 OPERATIONS PLAN
EVENT TIME: 07/1800 - AND LATER
TERMINAL ACTIVE:
UNTIL 2359	-SFO GROUND DELAY PROGRAM
UNTIL 0459	-SAN GROUND DELAY PROGRAM
TERMINAL PLANNED:
AFTER 1900	-TEB GROUND STOP/DELAY PROGRAM PROBABLE
AFTER 2000	-CLT GROUND STOP/DELAY PROGRAM POSSIBLE
```

Every advisory the linker could see for this element in the horizon:

```
20260507-067  sent 05/07 19:08Z  CDM GROUND STOP  TEB  GROUND STOP PERIOD 07/1854Z - 07/2015Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260507-074  sent 05/07 20:08Z  CDM GS CNX  TEB  GS CNX PERIOD 07/2008Z - 07/2042Z
```

Other advisories that name the element (not read by the linker):

```
20260507-075  sent 05/07 20:11Z  TEB AIRPORT ARRIVAL DELAYS
```

**Derived outcome: ISSUED = 1**. CDM GROUND STOP sent 07/1908Z, period 07/1854Z - 07/2008Z.

Advisory that decides the outcome:

```
ATCSCC ADVZY 067 TEB/ZNY 05/07/2026 CDM GROUND STOP
CTL ELEMENT: TEB
ELEMENT TYPE: APT
ADL TIME: 1904Z
GROUND STOP PERIOD: 07/1854Z - 07/2015Z
DEP FACILITIES INCLUDED: (Internal) ZNY
PREVIOUS TOTAL, MAXIMUM, AVERAGE DELAYS: 0 / 0 / 0
NEW TOTAL, MAXIMUM, AVERAGE DELAYS: 266 / 59 / 44
PROBABILITY OF EXTENSION: MEDIUM
IMPACTING CONDITION: VOLUME / VOLUME
COMMENTS: INTERNAL TO ZNY ONLY
```

## 4. route-20260410-064

- Term: **MODERATE** (route:MODERATE); written as: `PROBABILITY OF EXTENSION: MODERATE`
- Element: MIDWEST_TO_HOUSTON; initiative: reroute; first issued 04/10 18:57Z in 20260410-064; window read as 10/1900Z - 10/2230Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 064 DCC 04/10/2026 ROUTE RQD /FL
NAME: MIDWEST_TO_HOUSTON
CONSTRAINED AREA: ZHU
REASON: WEATHER
INCLUDE TRAFFIC: KCLE/KCRW/KDTW/KLEX/KSDF/ZAU/ZFW/ZID/ZKC/ZME/ZMP/ZO
B DEPARTURES TO KHOU/KIAH
FACILITIES INCLUDED: ZAU/ZFW/ZHU/ZID/ZKC/ZME/ZMP/ZOB
FLIGHT STATUS: NOT_AIRBORNE
VALID: ETD 101900 TO 102230
PROBABILITY OF EXTENSION: MODERATE
REMARKS: CONVENTIONAL NAVIGATION AIRCRAFT LANDING IAH/HOU FROM THE
WEST VIA SAT MUST BE AOA FL240 OR MUST FILE SAT CRP (STAR).
IAH CONVENTIONAL DUUUK STAR // HOU CONVENTIONAL TCHDN STAR
CONVENTIONAL NAVIGATION AIRCRAFT VIA SJI LANDING IAH
FILE GILCO STAR.
ASSOCIATED RESTRICTIONS:
MODIFICATIONS:
ROUTES: [route table not shown]
TMI ID: RRDCC505
```

Every advisory the linker could see for this element in the horizon:

```
20260410-067  sent 04/10 19:06Z  REROUTE CANCELLATION  MIDWEST_TO_HOUSTON
```

**Derived outcome: NOT EXTENDED (cancelled) = 0**. cancelled at 10/1906Z; stated end 10/2230Z.

Advisory that decides the outcome:

```
ATCSCC ADVZY 067 DCC 04/10/2026 REROUTE CANCELLATION
MIDWEST_TO_HOUSTON HAS BEEN CANCELLED.

REMARKS: CANCELS ADVZY 064
ASSOCIATED RESTRICTIONS:
```

## 5. route-20260429-031

- Term: **NONE** (route:NONE); written as: `PROBABILITY OF EXTENSION: NONE`
- Element: FCA021:NE_TO_FLORIDA_VIA_Q97_1_PARTIAL; initiative: reroute; first issued 04/29 08:51Z in 20260429-031; window read as 29/1406Z - 29/1636Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 031 DCC 04/29/2026 FCA RQD
NAME: FCA021:NE_TO_FLORIDA_VIA_Q97_1_PARTIAL
CONSTRAINED AREA: ZMA
REASON: OTHER
INCLUDE TRAFFIC: KBWI/KDCA/KIAD/KJFK/KPHL/ZBW/ZNY DEPARTURES TO
KMIA/KTMB
FACILITIES INCLUDED: ZBW/ZDC/ZJX/ZMA/ZNY
FLIGHT STATUS: ALL_FLIGHTS
VALID: FCA ENTRY TIME FROM 291406 TO 291636
PROBABILITY OF EXTENSION: NONE
REMARKS: IMPLEMENTED DUE TO ROCKET LAUNCH. SEE DYNAMIC LIST FOR
UPDATES.
ASSOCIATED RESTRICTIONS:
MODIFICATIONS:
ROUTES: [route table not shown]
TMI ID: RRDCC031
```

Every advisory the linker could see for this element in the horizon:

```
20260429-069  sent 04/29 14:26Z  REROUTE CANCELLATION  FCA021:NE_TO_FLORIDA_VIA_Q97_1_PARTIAL
```

**Derived outcome: NOT EXTENDED (cancelled) = 0**. cancelled at 29/1426Z; stated end 29/1636Z.

Advisory that decides the outcome:

```
ATCSCC ADVZY 069 DCC 04/29/2026 REROUTE CANCELLATION
FCA021:NE_TO_FLORIDA_VIA_Q97_1_PARTIAL HAS BEEN CANCELLED.

REMARKS:
ASSOCIATED RESTRICTIONS:
```

## 6. route-20260529-060

- Term: **NONE** (route:NONE); written as: `PROBABILITY OF EXTENSION: NONE`
- Element: FCA009:CAPE_LAUNCH_WEST_COAST_2; initiative: reroute; first issued 05/29 18:51Z in 20260529-060; window read as 29/2333Z - 30/0054Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 060 DCC 05/29/2026 FCA RQD
NAME: FCA009:CAPE_LAUNCH_WEST_COAST_2
CONSTRAINED AREA: ZJX/ZMA
REASON: OTHER
INCLUDE TRAFFIC: CZU/CZY/KACY/KALN/KATL/KBHM/KBLV/KBMI/KBWI/KCLT/KDC
A/KDET/KDTW/KFAY/KFNT/KIAD/KILM/KJFK/KLAN/KLZU/KMBS
/KMGM/KORF/KPDK/KPHL/KPIA/KPTK/KRDU/KRYY/KSBY/KSOP/
KSPI/KSTL/KSUS/KYIP/ZAU/ZBW/ZDV/ZID/ZKC/ZME/ZMP/ZNY
/ZOB DEPARTURES TO KFLL/KOPF
FACILITIES INCLUDED: CZU/CZY/ZAU/ZBW/ZDC/ZDV/ZID/ZJX/ZKC/ZMA/ZME/ZMP
/ZNY/ZOB/ZTL
FLIGHT STATUS: ALL_FLIGHTS
VALID: FCA ENTRY TIME FROM 292333 TO 300054
PROBABILITY OF EXTENSION: NONE
REMARKS: SEE DYNAMIC LIST FOR UPDATES. IMPLEMENTED DUE TO ROCKET
LAUNCH.  Q100/Y280/Q102/Y290 EXEMPT.
ASSOCIATED RESTRICTIONS:
MODIFICATIONS:
ROUTES: [route table not shown]
TMI ID: RRDCC514
```

Every advisory the linker could see for this element in the horizon:

```
20260530-004  sent 05/30 00:10Z  REROUTE CANCELLATION  FCA009:CAPE_LAUNCH_WEST_COAST_2
```

**Derived outcome: NOT EXTENDED (cancelled) = 0**. cancelled at 30/0010Z; stated end 30/0054Z.

Advisory that decides the outcome:

```
ATCSCC ADVZY 004 DCC 05/30/2026 REROUTE CANCELLATION
FCA009:CAPE_LAUNCH_WEST_COAST_2 HAS BEEN CANCELLED.

REMARKS:
ASSOCIATED RESTRICTIONS:
```

## 7. route-20260402-049

- Term: **LOW** (route:LOW); written as: `PROBABILITY OF EXTENSION: LOW`
- Element: ZDC_TO_LGA; initiative: reroute; first issued 04/02 03:25Z in 20260402-049; window read as 02/0315Z - 02/0500Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 049 DCC 04/02/2026 ROUTE RQD /FL
NAME: ZDC_TO_LGA
CONSTRAINED AREA: ZDC/ZNY
REASON: WEATHER
INCLUDE TRAFFIC: ZDC DEPARTURES TO KLGA
FACILITIES INCLUDED: ZDC/ZNY/ZOB
FLIGHT STATUS: ALL_FLIGHTS
VALID: ETD 020315 TO 020500
PROBABILITY OF EXTENSION: LOW
REMARKS: AD HOC RTE
ASSOCIATED RESTRICTIONS: 40 MIT
MODIFICATIONS:
ROUTES: [route table not shown]
TMI ID: RRDCC049
```

Every advisory the linker could see for this element in the horizon:

```
(none)
```

**Derived outcome: NOT EXTENDED (lapsed) = 0**. no later advisory moved the end past 02/0500Z.

No advisory decides the outcome (nothing qualifying was found).

## 8. route-20260504-058

- Term: **LOW** (route:LOW); written as: `PROBABILITY OF EXTENSION: LOW`
- Element: FCA008:TEXAS_WEST_TO_ORD; initiative: reroute; first issued 05/04 21:48Z in 20260504-058; window read as 04/2200Z - 05/0200Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 058 DCC 05/04/2026 FCA RQD
NAME: FCA008:TEXAS_WEST_TO_ORD
CONSTRAINED AREA: ZKC/ZAU
REASON: WEATHER
INCLUDE TRAFFIC: ZAB/ZDV/ZFW/ZHU/ZLA DEPARTURES TO KORD
FACILITIES INCLUDED: ZAB/ZAU/ZDV/ZFW/ZHU/ZKC/ZLA/ZMP
FLIGHT STATUS: ALL_FLIGHTS
VALID: FCA ENTRY TIME FROM 042200 TO 050200
PROBABILITY OF EXTENSION: LOW
REMARKS: SEE DYNAMIC LIST FOR UPDATES.
ASSOCIATED RESTRICTIONS:
MODIFICATIONS:
ROUTES: [route table not shown]
TMI ID: RRDCC507
```

Every advisory the linker could see for this element in the horizon:

```
(none)
```

**Derived outcome: NOT EXTENDED (lapsed) = 0**. no later advisory moved the end past 05/0200Z.

No advisory decides the outcome (nothing qualifying was found).

## 9. gs-20260415-106

- Term: **HIGH** (gs:HIGH); written as: `PROBABILITY OF EXTENSION: HIGH`
- Element: BFI; initiative: gs; first issued 04/15 23:44Z in 20260415-106; window read as 15/2331Z - 16/0100Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 106 BFI/ZSE 04/15/2026 CDM GROUND STOP
CTL ELEMENT: BFI
ELEMENT TYPE: APT
ADL TIME: 2341Z
GROUND STOP PERIOD: 15/2331Z - 16/0100Z
DEP FACILITIES INCLUDED: (Manual) ZLC ZOA ZSE  CYEG CYVR CYYC CYYJ
CYLW
PREVIOUS TOTAL, MAXIMUM, AVERAGE DELAYS: 0 / 0 / 0
NEW TOTAL, MAXIMUM, AVERAGE DELAYS: 368 / 82 / 53
PROBABILITY OF EXTENSION: HIGH
IMPACTING CONDITION: WEATHER / WIND
COMMENTS:
```

Every advisory the linker could see for this element in the horizon:

```
20260416-001  sent 04/16 00:04Z  CDM GS CNX  BFI  GS CNX PERIOD 16/0004Z - 16/0300Z
```

Other advisories that name the element (not read by the linker):

```
20260415-107  sent 04/15 23:46Z  BFI AIRPORT DIVERSION RECOVERY ACTIVATED
```

**Derived outcome: NOT EXTENDED (cancelled) = 0**. cancelled at 16/0004Z; stated end 16/0100Z.

Advisory that decides the outcome:

```
ATCSCC ADVZY 001 BFI/ZSE 04/16/2026 CDM GS CNX
CTL ELEMENT: BFI
ELEMENT TYPE: APT
ADL TIME: 0004Z
GS CNX PERIOD: 16/0004Z - 16/0300Z
COMMENTS:
```

## 10. route-20260525-134

- Term: **LOW** (route:LOW); written as: `PROBABILITY OF EXTENSION: LOW`
- Element: PHX_NO_J92_PARTIAL; initiative: reroute; first issued 05/25 23:11Z in 20260525-134; window read as 25/1930Z - 26/0200Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 134 DCC 05/25/2026 ROUTE RQD /FL
NAME: PHX_NO_J92_PARTIAL
CONSTRAINED AREA: ZAB
REASON: WEATHER
INCLUDE TRAFFIC: KMRY/KOAK/KSAN/KSFO/KSJC/ZLA/ZOA/ZSE DEPARTURES TO
KPHX
FACILITIES INCLUDED: ZAB/ZLA/ZOA/ZSE
FLIGHT STATUS: ALL_FLIGHTS
VALID: ETD 251930 TO 260200
PROBABILITY OF EXTENSION: LOW
REMARKS: REPLACES ADVZY 087. EXTENDS END TIME.
ASSOCIATED RESTRICTIONS:
MODIFICATIONS:
ROUTES: [route table not shown]
TMI ID: RRDCC501
```

Every advisory the linker could see for this element in the horizon:

```
(none)
```

**Derived outcome: NOT EXTENDED (lapsed) = 0**. no later advisory moved the end past 26/0200Z.

No advisory decides the outcome (nothing qualifying was found).

## 11. gs-20260426-106

- Term: **MEDIUM** (gs:MEDIUM); written as: `PROBABILITY OF EXTENSION: MEDIUM`
- Element: DAL; initiative: gs; first issued 04/26 23:19Z in 20260426-106; window read as 26/2307Z - 27/0015Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 106 DAL/ZFW 04/26/2026 CDM GROUND STOP
CTL ELEMENT: DAL
ELEMENT TYPE: APT
ADL TIME: 2317Z
GROUND STOP PERIOD: 26/2307Z - 27/0015Z
DEP FACILITIES INCLUDED: (Manual) ZHU ZFW ZKC ZME ZAB ZDV
PREVIOUS TOTAL, MAXIMUM, AVERAGE DELAYS: 0 / 0 / 0
NEW TOTAL, MAXIMUM, AVERAGE DELAYS: 558 / 64 / 28
PROBABILITY OF EXTENSION: MEDIUM
IMPACTING CONDITION: EQUIPMENT / OUTAGE
COMMENTS: INTERMITTENT LANDLINE, COMMS, AUTOMATION ISSUES
```

Every advisory the linker could see for this element in the horizon:

```
20260426-114  sent 04/26 23:46Z  CDM GS CNX  DAL  GS CNX PERIOD 26/2344Z - 27/0201Z
```

Other advisories that name the element (not read by the linker):

```
20260426-109  sent 04/26 23:33Z  D10 AIRPORTS DIVERSION RECOVERY ACTIVATED
```

**Derived outcome: NOT EXTENDED (cancelled) = 0**. cancelled at 26/2346Z; stated end 27/0015Z.

Advisory that decides the outcome:

```
ATCSCC ADVZY 114 DAL/ZFW 04/26/2026 CDM GS CNX
CTL ELEMENT: DAL
ELEMENT TYPE: APT
ADL TIME: 2344Z
GS CNX PERIOD: 26/2344Z - 27/0201Z
COMMENTS:
```

## 12. plan-20260423-065-BOS-gdp-AFTER2000

- Term: **EXPECTED** (plan:EXPECTED); written as: `AFTER 2000	-BOS GROUND DELAY PROGRAM EXPECTED`
- Element: BOS; initiative: gdp; first issued 04/23 19:30Z in 20260423-065; window read as 23/2000Z - 24/0800Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 065 DCC 04/23/2026 OPERATIONS PLAN
EVENT TIME: 23/2000 - AND LATER
TERMINAL ACTIVE:
UNTIL 2015	-BOS GROUND STOP
TERMINAL PLANNED:
AFTER 2000	-BOS GROUND DELAY PROGRAM EXPECTED
UNTIL 0200 	-MSP GROUND STOP POSSIBLE
```

Every advisory the linker could see for this element in the horizon:

```
20260423-062  sent 04/23 19:22Z  CDM GROUND STOP  BOS  GROUND STOP PERIOD 23/1906Z - 23/2015Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260423-067  sent 04/23 19:31Z  CDM PROPOSED GROUND DELAY PROGRAM  BOS  ANTICIPATED CUMULATIVE PROGRAM PERIOD 23/1916Z - 24/0359Z
20260423-070  sent 04/23 20:05Z  CDM GROUND DELAY PROGRAM  BOS  CUMULATIVE PROGRAM PERIOD 23/2000Z - 24/0359Z
20260423-079  sent 04/23 20:56Z  CDM GROUND STOP  BOS  GROUND STOP PERIOD 23/2040Z - 23/2200Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260423-093  sent 04/23 21:50Z  CDM GROUND STOP  BOS  GROUND STOP PERIOD 23/2040Z - 23/2230Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260423-095  sent 04/23 22:19Z  CDM GROUND DELAY PROGRAM CNX  BOS  GDP CNX PERIOD 23/2215Z - 25/0142Z
```

Other advisories that name the element (not read by the linker):

```
20260423-084  sent 04/23 21:16Z  BOS AIRPORT ARRIVAL DELAYS
20260423-088  sent 04/23 21:26Z  BOS AIRPORT DIVERSION RECOVERY ACTIVATED
```

**Derived outcome: ISSUED = 1**. CDM GROUND DELAY PROGRAM sent 23/2005Z, period 23/2000Z - 23/2219Z.

Advisory that decides the outcome:

```
ATCSCC ADVZY 070 BOS/ZBW 04/23/2026 CDM GROUND DELAY PROGRAM
CTL ELEMENT: BOS
ELEMENT TYPE: APT
ADL TIME: 2001Z
DELAY ASSIGNMENT MODE: UDP
ARRIVALS ESTIMATED FOR: 23/2000Z - 24/0359Z
CUMULATIVE PROGRAM PERIOD: 23/2000Z - 24/0359Z
PROGRAM RATE: 38
FLT INCL: ALL CONTIGUOUS US DEP
DEP SCOPE: (ALL+CZY_AP) ZLA ZAU ZLC ZTL ZDC ZNY ZHU ZJX ZFW ZOB ZDV
ZOA ZSE ZBW ZMA ZKC ZME ZID ZAB ZMP
CANADIAN DEP ARPTS INCLUDED: CYHZ CYOW CYUL CYYZ CYTZ CYQB
DELAY ASSIGNMENT TABLE APPLIES TO: ZBW
MAXIMUM DELAY: 146
AVERAGE DELAY: 60
IMPACTING CONDITION: RWY-TAXI / MAINTENANCE
COMMENTS: GROUNDSTOP CANCELLED. HOLE IN RWY 32. ONLY ARRIVING RWY 27.
MED POPUP. FROM STATUS.
```

## 13. gs-20260424-073

- Term: **LOW** (gs:LOW); written as: `PROBABILITY OF EXTENSION: LOW`
- Element: LGA; initiative: gs; first issued 04/24 18:13Z in 20260424-073; window read as 24/1800Z - 24/1900Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 073 LGA/ZNY 04/24/2026 CDM GROUND STOP
CTL ELEMENT: LGA
ELEMENT TYPE: APT
ADL TIME: 1810Z
GROUND STOP PERIOD: 24/1800Z - 24/1900Z
DEP FACILITIES INCLUDED: (Manual) ZDC
PREVIOUS TOTAL, MAXIMUM, AVERAGE DELAYS: 0 / 0 / 0
NEW TOTAL, MAXIMUM, AVERAGE DELAYS: 220 / 52 / 37
PROBABILITY OF EXTENSION: LOW
IMPACTING CONDITION: VOLUME / COMPACTED DEMAND
COMMENTS: HIGH ARRIVAL DEMAND OVER RBV CAUSING HOLDING IN ZDC.
```

Every advisory the linker could see for this element in the horizon:

```
20260424-077  sent 04/24 18:55Z  CDM GS CNX  LGA  GS CNX PERIOD 24/1853Z - 24/2011Z
```

**Derived outcome: NOT EXTENDED (cancelled) = 0**. cancelled at 24/1855Z; stated end 24/1900Z.

Advisory that decides the outcome:

```
ATCSCC ADVZY 077 LGA/ZNY 04/24/2026 CDM GS CNX
CTL ELEMENT: LGA
ELEMENT TYPE: APT
ADL TIME: 1853Z
GS CNX PERIOD: 24/1853Z - 24/2011Z
COMMENTS:
```

## 14. gs-20260520-140

- Term: **HIGH** (gs:HIGH); written as: `PROBABILITY OF EXTENSION: HIGH`
- Element: LGA; initiative: gs; first issued 05/20 20:48Z in 20260520-140; window read as 20/1958Z - 20/2200Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 140 LGA/ZNY 05/20/2026 CDM GROUND STOP
CTL ELEMENT: LGA
ELEMENT TYPE: APT
ADL TIME: 2045Z
GROUND STOP PERIOD: 20/1958Z - 20/2200Z
CUMULATIVE PROGRAM PERIOD: 20/1700Z - 21/0359Z
DEP FACILITIES INCLUDED: (2ndTier+CZY_AP) ZAU ZTL ZDC ZNY ZJX ZOB ZBW
ZID ZMP  CYHZ CYOW CYUL CYYZ CYTZ CYQB
PREVIOUS TOTAL, MAXIMUM, AVERAGE DELAYS: 1788 / 155 / 89
NEW TOTAL, MAXIMUM, AVERAGE DELAYS: 2698 / 214 / 135
PROBABILITY OF EXTENSION: HIGH
IMPACTING CONDITION: WEATHER / THUNDERSTORMS
COMMENTS:
```

Every advisory the linker could see for this element in the horizon:

```
20260520-155  sent 05/20 21:42Z  CDM PROPOSED GROUND DELAY PROGRAM  LGA  ANTICIPATED CUMULATIVE PROGRAM PERIOD 20/1700Z - 21/0459Z
20260520-158  sent 05/20 21:50Z  CDM GROUND DELAY PROGRAM  LGA  CUMULATIVE PROGRAM PERIOD 20/1700Z - 21/0459Z
20260520-173  sent 05/20 22:34Z  CDM GROUND STOP  LGA  GROUND STOP PERIOD 20/2220Z - 20/2330Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260520-182  sent 05/20 23:13Z  CDM GROUND STOP  LGA  GROUND STOP PERIOD 20/2220Z - 21/0030Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260520-185  sent 05/20 23:23Z  CDM GROUND STOP  LGA  GROUND STOP PERIOD 20/2220Z - 21/0030Z  [PROBABILITY OF EXTENSION: MEDIUM]
```

**Derived outcome: NOT EXTENDED (lapsed) = 0**. no later advisory moved the end past 20/2200Z. Flags: gdp_followed new_stop_30.

No advisory decides the outcome (nothing qualifying was found).

## 15. gs-20260413-041

- Term: **MEDIUM** (gs:MEDIUM); written as: `PROBABILITY OF EXTENSION: MEDIUM`
- Element: ORD; initiative: gs; first issued 04/13 14:05Z in 20260413-041; window read as 13/1346Z - 13/1515Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 041 ORD/ZAU 04/13/2026 CDM GROUND STOP
CTL ELEMENT: ORD
ELEMENT TYPE: APT
ADL TIME: 1401Z
GROUND STOP PERIOD: 13/1346Z - 13/1515Z
FLT INCL: CARRIER UAL ONLY
DEP FACILITIES INCLUDED: (2ndTier+CZY_AP) ZAU ZLC ZTL ZDC ZNY ZFW ZOB
ZDV ZBW ZKC ZME ZID ZAB ZMP  CYHZ CYOW CYUL CYYZ
PREVIOUS TOTAL, MAXIMUM, AVERAGE DELAYS: 0 / 0 / 0
NEW TOTAL, MAXIMUM, AVERAGE DELAYS: 1412 / 80 / 29
PROBABILITY OF EXTENSION: MEDIUM
IMPACTING CONDITION: OTHER / OTHER
COMMENTS: UAL AND UAL SUBS ONLY
```

Every advisory the linker could see for this element in the horizon:

```
20260413-044  sent 04/13 14:33Z  CDM GS CNX  ORD  GS CNX PERIOD 13/1430Z - 13/1914Z
```

**Derived outcome: NOT EXTENDED (cancelled) = 0**. cancelled at 13/1433Z; stated end 13/1515Z.

Advisory that decides the outcome:

```
ATCSCC ADVZY 044 ORD/ZAU 04/13/2026 CDM GS CNX
CTL ELEMENT: ORD
ELEMENT TYPE: APT
ADL TIME: 1430Z
GS CNX PERIOD: 13/1430Z - 13/1914Z
COMMENTS:
```

## 16. route-20260412-070

- Term: **MODERATE** (route:MODERATE); written as: `PROBABILITY OF EXTENSION: MODERATE`
- Element: WEVEL_PARTIAL; initiative: reroute; first issued 04/12 19:57Z in 20260412-070; window read as 12/2015Z - 13/0000Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 070 DCC 04/12/2026 ROUTE RQD /FL
NAME: WEVEL_PARTIAL
CONSTRAINED AREA: ZDC
REASON: OTHER
INCLUDE TRAFFIC: KBWI/KDCA/KIAD DEPARTURES TO
CYYZ/KALB/KBDL/KBOS/KBUF/KPVD/KROC/KSYR
FACILITIES INCLUDED: CZY/ZBW/ZDC/ZNY/ZOB
FLIGHT STATUS: ALL_FLIGHTS
VALID: ETD 122015 TO 130000
PROBABILITY OF EXTENSION: MODERATE
REMARKS: FLIGHT CREWS MUST COMPLY WITH ALTITUDE RESTRICTIONS. DO NOT
REQUEST AN ALTITUDE HIGHER THAN FL220 DURING THE ENTIRE
FLIGHT.
IMPLEMENTED DUE TO ZDC STAFFING.
ASSOCIATED RESTRICTIONS:
MODIFICATIONS:
ROUTES: [route table not shown]
TMI ID: RRDCC513
```

Every advisory the linker could see for this element in the horizon:

```
(none)
```

**Derived outcome: NOT EXTENDED (lapsed) = 0**. no later advisory moved the end past 13/0000Z.

No advisory decides the outcome (nothing qualifying was found).

## 17. plan-20260427-051-MDW-gs-UNTIL2300

- Term: **PROBABLE** (plan:PROBABLE); written as: `UNTIL 2300 	-MDW GROUND STOP PROBABLE`
- Element: MDW; initiative: gs; first issued 04/27 13:33Z in 20260427-051; window read as 27/1333Z - 27/2300Z
- Repeated in: 20260427-072 20260427-079 20260427-092

Source advisory:

```
ATCSCC ADVZY 051 DCC 04/27/2026 OPERATIONS PLAN
EVENT TIME: 27/1400 - AND LATER
TERMINAL ACTIVE:
UNTIL 2059 	-SFO GROUND DELAY PROGRAM
TERMINAL PLANNED:
AFTER 1600 	-MSP GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 2100 	-DEN GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 2200 	-SFO GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 2200 	-JFK GROUND STOP/DELAY PROGRAM POSSIBLE
UNTIL 2300 	-MDW GROUND STOP PROBABLE
UNTIL 2300 	-ORD GROUND STOP/DELAY PROGRAM PROBABLE
AFTER 0200 	-MEM GROUND STOP POSSIBLE
```

Every advisory the linker could see for this element in the horizon:

```
(none)
```

Other advisories that name the element (not read by the linker):

```
20260427-053  sent 04/27 13:47Z  ORD AND MDW AIRPORT ARRIVAL DELAYS
20260427-069  sent 04/27 15:00Z  ORD MDW CDRS_FYI
20260427-101  sent 04/27 21:09Z  ORD/MDW AIRPORT ARRIVAL DELAYS
```

**Derived outcome: NOT ISSUED = 0**. no gs advisory for MDW in the window.

No advisory decides the outcome (nothing qualifying was found).

## 18. route-20260527-120

- Term: **NONE** (route:NONE); written as: `PROBABILITY OF EXTENSION: NONE`
- Element: NORTH_TO_DFW_DAL; initiative: reroute; first issued 05/27 21:16Z in 20260527-120; window read as 27/1315Z - 28/0000Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 120 DCC 05/27/2026 ROUTE RQD /FL
NAME: NORTH_TO_DFW_DAL
CONSTRAINED AREA: ZFW
REASON: WEATHER
INCLUDE TRAFFIC: CZY/KBUF/KCLE/KDTW/KPIT/KROC/ZAU/ZBW/ZID/ZKC/ZMP/ZN
Y DEPARTURES TO KDAL/KDFW
FACILITIES INCLUDED: CZY/ZAU/ZBW/ZFW/ZID/ZKC/ZMP/ZNY/ZOB
FLIGHT STATUS: ALL_FLIGHTS
VALID: ETD 271315 TO 280000
PROBABILITY OF EXTENSION: NONE
REMARKS: REPLACES ADVZY 085. BASED ON DFW_EAST_1_NORTH_FLOW
ASSOCIATED RESTRICTIONS:
MODIFICATIONS: EXTENDS END TIME...CAUSAL FACTOR IS WEATHER/TS
ROUTES: [route table not shown]
TMI ID: RRDCC507
```

Every advisory the linker could see for this element in the horizon:

```
(none)
```

**Derived outcome: NOT EXTENDED (lapsed) = 0**. no later advisory moved the end past 28/0000Z.

No advisory decides the outcome (nothing qualifying was found).

## 19. plan-20260513-072-TEB-gs+gdp-UNTIL0000

- Term: **POSSIBLE** (plan:POSSIBLE); written as: `UNTIL 0000	-TEB GROUND STOP/DELAY PROGRAM POSSIBLE`
- Element: TEB; initiative: gs/gdp; first issued 05/13 21:31Z in 20260513-072; window read as 13/2131Z - 14/0000Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 072 DCC 05/13/2026 OPERATIONS PLAN
EVENT TIME: 13/2200 - AND LATER
TERMINAL ACTIVE:
UNTIL 0559	-SFO GROUND DELAY PROGRAM
TERMINAL PLANNED:
UNTIL 2300	-IAD/DCA GROUND STOP POSSIBLE
UNTIL 0000	-TEB GROUND STOP/DELAY PROGRAM POSSIBLE
UNTIL 0000	-DEN GROUND STOP POSSIBLE
UNTIL 0200	-JFK GROUND STOP/DELAY PROGRAM POSSIBLE
```

Every advisory the linker could see for this element in the horizon:

```
(none)
```

**Derived outcome: NOT ISSUED = 0**. no gs or gdp advisory for TEB in the window.

No advisory decides the outcome (nothing qualifying was found).

## 20. route-20260410-015

- Term: **LOW** (route:LOW); written as: `PROBABILITY OF EXTENSION: LOW`
- Element: FCA003:LAKE_ERIE_WEST_PARTIAL; initiative: reroute; first issued 04/10 10:20Z in 20260410-015; window read as 10/1100Z - 10/1800Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 015 DCC 04/10/2026 FCA RQD
NAME: FCA003:LAKE_ERIE_WEST_PARTIAL
CONSTRAINED AREA: CZY
REASON: OTHER
INCLUDE TRAFFIC: ZNY DEPARTURES TO
KFNT/KMBS/KMKE/KMSP/KORD/ZAB/ZAU/ZDV/ZKC/ZLA/ZLC/ZM
P/ZOA/ZSE
FACILITIES INCLUDED: ZAB/ZAU/ZDV/ZKC/ZLA/ZLC/ZMP/ZNY/ZOA/ZOB/ZSE
FLIGHT STATUS: ALL_FLIGHTS
VALID: FCA ENTRY TIME FROM 101100 TO 101800
PROBABILITY OF EXTENSION: LOW
REMARKS: SEE DYNAMIC LIST FOR UPDATES. SEA AND ZAN LTFC EXEMPT FROM
ROUTE. IMPLEMENTED DUE TO REDUCED SYSTEM CAPACITY IN CZY.
ASSOCIATED RESTRICTIONS:
MODIFICATIONS:
ROUTES: [route table not shown]
TMI ID: RRDCC501
```

Every advisory the linker could see for this element in the horizon:

```
20260410-022  sent 04/10 11:13Z  FCA RQD  FCA003:LAKE_ERIE_WEST_PARTIAL  VALID 10/1100Z - 10/1500Z  [PROBABILITY OF EXTENSION: LOW]
```

**Derived outcome: NOT EXTENDED (lapsed) = 0**. no later advisory moved the end past 10/1800Z. Flags: shortened.

No advisory decides the outcome (nothing qualifying was found).

## 21. route-20260404-096

- Term: **MODERATE** (route:MODERATE); written as: `PROBABILITY OF EXTENSION: MODERATE`
- Element: EAST_TO_DALLAS; initiative: reroute; first issued 04/04 16:29Z in 20260404-096; window read as 04/1145Z - 04/2000Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 096 DCC 04/04/2026 ROUTE RQD /FL
NAME: EAST_TO_DALLAS
CONSTRAINED AREA: ZFW
REASON: WEATHER
INCLUDE TRAFFIC: KATL/KCLT/KGSO/KMIA/KORF/KRDU/KRIC/KROA/KTPA/ZJX/ZM
A/ZTL DEPARTURES TO KDAL/KDFW
FACILITIES INCLUDED: ZDC/ZFW/ZHU/ZJX/ZMA/ZTL
FLIGHT STATUS: ALL_FLIGHTS
VALID: ETD 041145 TO 042000
PROBABILITY OF EXTENSION: MODERATE
REMARKS: REPLACES ADVZY 078, EXTENDS TIME / REMOVES ZME DFW LANDING
NORTH. BASED ON DFW EAST 1 NORTH FLOW PARTIAL.
ASSOCIATED RESTRICTIONS:
MODIFICATIONS: SHORTENS RTE BACK TO MOLLR CRGER
ROUTES: [route table not shown]
TMI ID: RRDCC501
```

Every advisory the linker could see for this element in the horizon:

```
(none)
```

**Derived outcome: NOT EXTENDED (lapsed) = 0**. no later advisory moved the end past 04/2000Z.

No advisory decides the outcome (nothing qualifying was found).

## 22. plan-20260523-007-DAL-gs+gdp-AFTER1200

- Term: **POSSIBLE** (plan:POSSIBLE); written as: `AFTER 1200	-DFW/DAL GROUND STOP/DELAY PROGRAM POSSIBLE`
- Element: DAL; initiative: gs/gdp; first issued 05/23 01:31Z in 20260523-007; window read as 23/1200Z - 24/0800Z
- Repeated in: 20260523-013

Source advisory:

```
ATCSCC ADVZY 007 DCC 05/23/2026 OPERATIONS PLAN
EVENT TIME: 23/0200 - AND LATER
TERMINAL ACTIVE:
UNTIL 0559	-SAN GROUND DELAY PROGRAM
UNTIL 0659	-SFO GROUND DELAY PROGRAM
TERMINAL PLANNED:
AFTER 1200	-DFW/DAL GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1400	-ATL GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1400	-IAH/HOU GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1500	-SFO GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1700	-JFK GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1700	-DCA GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1800	-CLT GROUND STOP POSSIBLE
AFTER 1800	-AUS/SAT GROUND STOP POSSIBLE
AFTER 1900	-LGA GROUND STOP/DELAY PROGRAM PROBABLE
AFTER 2000	-MCO/TPA GROUND STOP POSSIBLE
```

Every advisory the linker could see for this element in the horizon:

```
(none)
```

Other advisories that name the element (not read by the linker):

```
20260523-019  sent 05/23 10:01Z  DFW DAL CDRS_FYI
20260523-042  sent 05/23 13:02Z  DFW DAL CAPPING/TUNNELING_FYI
20260523-062  sent 05/23 15:25Z  DFW DAL CDRS_FYI
```

**Derived outcome: NOT ISSUED = 0**. no gs or gdp advisory for DAL in the window.

No advisory decides the outcome (nothing qualifying was found).

## 23. plan-20260506-011-EWR-gs+gdp-AFTER1700

- Term: **PROBABLE** (plan:PROBABLE); written as: `AFTER 1700	-EWR GROUND STOP/DELAY PROGRAM PROBABLE`
- Element: EWR; initiative: gs/gdp; first issued 05/06 01:28Z in 20260506-011; window read as 06/1700Z - 07/0800Z
- Repeated in: 20260506-018 20260506-024 20260506-040 20260506-052

Source advisory:

```
ATCSCC ADVZY 011 DCC 05/06/2026 OPERATIONS PLAN
EVENT TIME: 06/0200 - AND LATER
TERMINAL ACTIVE:
UNTIL 0559	-MEM GROUND DELAY PROGRAM
TERMINAL PLANNED:
AFTER 1400	-DEN GROUND STOP/DELAY PROGRAM PROBABLE
AFTER 1500	-SFO GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1600	-LGA GROUND STOP/DELAY PROGRAM PROBABLE
AFTER 1600	-DCA GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1700	-EWR GROUND STOP/DELAY PROGRAM PROBABLE
AFTER 1700	-BOS GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1800	-JFK GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1900	-CLT GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 2100	-IAD/BWI GROUND STOP POSSIBLE
AFTER 2200	-PHL GROUND STOP/DELAY PROGRAM POSSIBLE
```

Every advisory the linker could see for this element in the horizon:

```
20260506-056  sent 05/06 16:12Z  CDM GROUND STOP  EWR  GROUND STOP PERIOD 06/1600Z - 06/1700Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260506-057  sent 05/06 16:52Z  CDM GROUND STOP  EWR  GROUND STOP PERIOD 06/1647Z - 06/1800Z  [PROBABILITY OF EXTENSION: LOW]
20260506-059  sent 05/06 17:30Z  CDM GS CNX  EWR  GS CNX PERIOD 06/1727Z - 06/1940Z
20260506-068  sent 05/06 19:08Z  CDM GROUND STOP  EWR  GROUND STOP PERIOD 06/1852Z - 06/2015Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260506-073  sent 05/06 20:13Z  CDM GS CNX  EWR  GS CNX PERIOD 06/2013Z - 06/2255Z
20260506-091  sent 05/06 23:03Z  CDM GROUND STOP  EWR  GROUND STOP PERIOD 06/2248Z - 07/0000Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260506-097  sent 05/06 23:44Z  CDM GS CNX  EWR  GS CNX PERIOD 06/2343Z - 07/0136Z
```

Other advisories that name the element (not read by the linker):

```
20260506-049  sent 05/06 15:26Z  EWR AIRPORT ARRIVAL DELAYS
```

**Derived outcome: ISSUED = 1**. CDM GROUND STOP sent 06/1612Z, period 06/1600Z - 06/1700Z. Flags: term_changed.

Advisory that decides the outcome:

```
ATCSCC ADVZY 056 EWR/ZNY 05/06/2026 CDM GROUND STOP
CTL ELEMENT: EWR
ELEMENT TYPE: APT
ADL TIME: 1611Z
GROUND STOP PERIOD: 06/1600Z - 06/1700Z
DEP FACILITIES INCLUDED: (Manual) ZTL ZDC ZNY ZOB ZBW ZID  CYHZ CYOW
CYUL CYYZ CYTZ CYQB
PREVIOUS TOTAL, MAXIMUM, AVERAGE DELAYS: 0 / 0 / 0
NEW TOTAL, MAXIMUM, AVERAGE DELAYS: 269 / 46 / 24
PROBABILITY OF EXTENSION: MEDIUM
IMPACTING CONDITION: OTHER / FLIGHT CHECK
COMMENTS: FLIGHT CHECK IN 16Z HOUR CAUSED UNRECOVERABLE SPIKE OF
VOLUME IN 16&17Z ARRIVAL HOURS.
```

## 24. route-20260423-012

- Term: **HIGH** (route:HIGH); written as: `PROBABILITY OF EXTENSION: HIGH`
- Element: FCA004:LAKE_ERIE_WEST_PARTIAL; initiative: reroute; first issued 04/23 10:22Z in 20260423-012; window read as 23/1400Z - 23/2000Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 012 DCC 04/23/2026 FCA RQD
NAME: FCA004:LAKE_ERIE_WEST_PARTIAL
CONSTRAINED AREA: CZY
REASON: OTHER
INCLUDE TRAFFIC: ZNY DEPARTURES TO
KFNT/KMBS/KMKE/KMSP/KORD/ZAB/ZAU/ZDV/ZKC/ZLA/ZLC/ZM
P/ZOA/ZSE
FACILITIES INCLUDED: ZAB/ZAU/ZDV/ZKC/ZLA/ZLC/ZMP/ZNY/ZOA/ZOB/ZSE
FLIGHT STATUS: ALL_FLIGHTS
VALID: FCA ENTRY TIME FROM 231400 TO 232000
PROBABILITY OF EXTENSION: HIGH
REMARKS: SEE DYNAMIC LIST FOR UPDATES. DUE TO REDUCED SYSTEM
CAPACITY IN CZY. EXPECT A SIMILAR RESTRICTION PAST 0300Z
DUE TO CZY STAFFING. CURRENTLY SHORTENED TO 2000Z FOR
FORECASTED WX.
ASSOCIATED RESTRICTIONS:
MODIFICATIONS:
ROUTES: [route table not shown]
TMI ID: RRDCC012
```

Every advisory the linker could see for this element in the horizon:

```
20260423-039  sent 04/23 16:18Z  FCA RQD  FCA004:LAKE_ERIE_WEST_PARTIAL  VALID 23/1400Z - 23/1800Z  [PROBABILITY OF EXTENSION: HIGH]
20260423-040  sent 04/23 16:21Z  FCA RQD  FCA012:LAKE_ERIE_WEST_PARTIAL  VALID 23/1800Z - 24/0300Z  [PROBABILITY OF EXTENSION: LOW]
```

**Derived outcome: EXTENDED = 1**. end 23/2000Z -> 24/0300Z (+420 min), carried on as FCA012:LAKE_ERIE_WEST_PARTIAL under TMI ID RRDCC040. Flags: shortened continued_new_id.

Advisory that decides the outcome:

```
ATCSCC ADVZY 040 DCC 04/23/2026 FCA RQD
NAME: FCA012:LAKE_ERIE_WEST_PARTIAL
CONSTRAINED AREA: CZY
REASON: OTHER
INCLUDE TRAFFIC: KBUF/KIAG/KPHL/KROC/KSYR/ZBW/ZNY DEPARTURES TO
KFNT/KMBS/KMKE/KORD/KPTK/KYIP/ZAB/ZAU/ZDV/ZKC/ZLA/Z
LC/ZOA/ZSE
FACILITIES INCLUDED: ZAB/ZAU/ZBW/ZDV/ZKC/ZLA/ZLC/ZNY/ZOA/ZOB/ZSE
FLIGHT STATUS: ALL_FLIGHTS
VALID: FCA ENTRY TIME FROM 231800 TO 240300
PROBABILITY OF EXTENSION: LOW
REMARKS: DUE TO STAFFING.  SEE DYNAMIC LIST FOR UPDATES.
ASSOCIATED RESTRICTIONS:
MODIFICATIONS:
ROUTES: [route table not shown]
TMI ID: RRDCC040
```

## 25. gs-20260427-081

- Term: **LOW** (gs:LOW); written as: `PROBABILITY OF EXTENSION: LOW`
- Element: LGA; initiative: gs; first issued 04/27 18:07Z in 20260427-081; window read as 27/1752Z - 27/1845Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 081 LGA/ZNY 04/27/2026 CDM GROUND STOP
CTL ELEMENT: LGA
ELEMENT TYPE: APT
ADL TIME: 1802Z
GROUND STOP PERIOD: 27/1752Z - 27/1845Z
DEP FACILITIES INCLUDED: (Manual) ZDC
PREVIOUS TOTAL, MAXIMUM, AVERAGE DELAYS: 0 / 0 / 0
NEW TOTAL, MAXIMUM, AVERAGE DELAYS: 109 / 45 / 36
PROBABILITY OF EXTENSION: LOW
IMPACTING CONDITION: VOLUME / COMPACTED DEMAND
COMMENTS: COMPACTED DEMAND OVER RBV
```

Every advisory the linker could see for this element in the horizon:

```
20260427-084  sent 04/27 18:37Z  CDM GS CNX  LGA  GS CNX PERIOD 27/1832Z - 27/1951Z
```

**Derived outcome: NOT EXTENDED (cancelled) = 0**. cancelled at 27/1837Z; stated end 27/1845Z.

Advisory that decides the outcome:

```
ATCSCC ADVZY 084 LGA/ZNY 04/27/2026 CDM GS CNX
CTL ELEMENT: LGA
ELEMENT TYPE: APT
ADL TIME: 1832Z
GS CNX PERIOD: 27/1832Z - 27/1951Z
COMMENTS: ZDC ABLE TO SCHEDULE INTO STREAM.
```

## 26. route-20260515-074

- Term: **LOW** (route:LOW); written as: `PROBABILITY OF EXTENSION: LOW`
- Element: DEN_GCK_2_PARTIAL; initiative: reroute; first issued 05/15 21:11Z in 20260515-074; window read as 15/2000Z - 15/2300Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 074 DCC 05/15/2026 ROUTE RQD /FL
NAME: DEN_GCK_2_PARTIAL
CONSTRAINED AREA: ZDV
REASON: WEATHER
INCLUDE TRAFFIC: ZFW/ZHU DEPARTURES TO KDEN
FACILITIES INCLUDED: ZAB/ZDV/ZFW/ZHU
FLIGHT STATUS: ALL_FLIGHTS
VALID: ETD 152000 TO 152300
PROBABILITY OF EXTENSION: LOW
REMARKS: REPLACES ADVZY 066.
ASSOCIATED RESTRICTIONS:
MODIFICATIONS: END TIME EXTENDED.
ROUTES: [route table not shown]
TMI ID: RRDCC509
```

Every advisory the linker could see for this element in the horizon:

```
(none)
```

**Derived outcome: NOT EXTENDED (lapsed) = 0**. no later advisory moved the end past 15/2300Z.

No advisory decides the outcome (nothing qualifying was found).

## 27. route-20260407-009

- Term: **LOW** (route:LOW); written as: `PROBABILITY OF EXTENSION: LOW`
- Element: FCA026:MASTERS_2026_AGS_ARVLS; initiative: reroute; first issued 04/07 08:25Z in 20260407-009; window read as 07/1000Z - 08/0200Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 009 DCC 04/07/2026 FCA RQD
NAME: FCA026:MASTERS_2026_AGS_ARVLS
CONSTRAINED AREA: ZTL
REASON: OTHER
INCLUDE TRAFFIC: CZU/CZY/KDTS/KECP/KEWN/KILM/KOAJ/KORF/KPHF/KPIE/KPN
S/KRDU/KSRQ/KTLH/KTPA/KVPS/ZAB/ZAU/ZBW/ZDC/ZDV/ZFW/
ZHU/ZID/ZJX/ZKC/ZLA/ZLC/ZMA/ZME/ZMP/ZNY/ZOA/ZOB/ZSE
DEPARTURES TO KAGS
FACILITIES INCLUDED: CZU/CZY/ZAB/ZAU/ZBW/ZDC/ZDV/ZFW/ZHU/ZID/ZJX/ZKC
/ZLA/ZLC/ZMA/ZME/ZMP/ZNY/ZOA/ZOB/ZSE/ZTL
FLIGHT STATUS: ALL_FLIGHTS
VALID: FCA ENTRY TIME FROM 071000 TO 080200
PROBABILITY OF EXTENSION: LOW
REMARKS: SEE DYNAMIC LIST FOR UPDATES. DUE TO SPECIAL EVENT
ASSOCIATED RESTRICTIONS:
MODIFICATIONS:
ROUTES: [route table not shown]
TMI ID: RRDCC009
```

Every advisory the linker could see for this element in the horizon:

```
(none)
```

**Derived outcome: NOT EXTENDED (lapsed) = 0**. no later advisory moved the end past 08/0200Z.

No advisory decides the outcome (nothing qualifying was found).

## 28. route-20260412-062

- Term: **MODERATE** (route:MODERATE); written as: `PROBABILITY OF EXTENSION: MODERATE`
- Element: IAH_KOBLE_PARTIAL; initiative: reroute; first issued 04/12 18:50Z in 20260412-062; window read as 12/1900Z - 12/2300Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 062 DCC 04/12/2026 ROUTE RQD /FL
NAME: IAH_KOBLE_PARTIAL
CONSTRAINED AREA: ZHU
REASON: WEATHER
INCLUDE TRAFFIC: ABQ/KLAS/KSAN/ZAB/ZDV/ZLA/ZLC/ZOA/ZSE DEPARTURES TO
KHOU/KIAH
FACILITIES INCLUDED: ZAB/ZDV/ZHU/ZLA/ZLC/ZOA/ZSE
FLIGHT STATUS: ALL_FLIGHTS
VALID: ETD 121900 TO 122300
PROBABILITY OF EXTENSION: MODERATE
REMARKS:
ASSOCIATED RESTRICTIONS:
MODIFICATIONS:
ROUTES: [route table not shown]
TMI ID: RRDCC506
```

Every advisory the linker could see for this element in the horizon:

```
(none)
```

**Derived outcome: NOT EXTENDED (lapsed) = 0**. no later advisory moved the end past 12/2300Z.

No advisory decides the outcome (nothing qualifying was found).

## 29. route-20260424-065

- Term: **HIGH** (route:HIGH); written as: `PROBABILITY OF EXTENSION: HIGH`
- Element: FCA014:GA_PROPS_TO_MIA_AND_SATS; initiative: reroute; first issued 04/24 17:54Z in 20260424-065; window read as 24/2045Z - 25/0200Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 065 DCC 04/24/2026 FCA RQD
NAME: FCA014:GA_PROPS_TO_MIA_AND_SATS
CONSTRAINED AREA: ZJX/ZMA
REASON: OTHER
INCLUDE TRAFFIC: UNKN DEPARTURES TO
07FA/KBCT/KFLL/KHST/KHWO/KMIA/KOPF/KTMB/X51
FACILITIES INCLUDED: ZJX/ZMA/ZTL
FLIGHT STATUS: ALL_FLIGHTS
VALID: FCA ENTRY TIME FROM 242045 TO 250200
PROBABILITY OF EXTENSION: HIGH
REMARKS: SEE DYNAMIC LIST FOR UPDATES. THIS ROUTE IS ISSUED DUE TO
SPECIAL OPERATIONS.
ASSOCIATED RESTRICTIONS:
MODIFICATIONS:
ROUTES: [route table not shown]
TMI ID: RRDCC524
```

Every advisory the linker could see for this element in the horizon:

```
20260425-006  sent 04/25 00:43Z  FCA RQD  FCA023:GA_PROPS_TO_MIA_AND_SATS  VALID 25/0200Z - 25/1900Z  [PROBABILITY OF EXTENSION: LOW]
```

**Derived outcome: EXTENDED = 1**. end 25/0200Z -> 25/1900Z (+1020 min), carried on as FCA023:GA_PROPS_TO_MIA_AND_SATS under TMI ID RRDCC504. Flags: continued_new_id.

Advisory that decides the outcome:

```
ATCSCC ADVZY 006 DCC 04/25/2026 FCA RQD
NAME: FCA023:GA_PROPS_TO_MIA_AND_SATS
CONSTRAINED AREA: ZJX/ZMA
REASON: OTHER
INCLUDE TRAFFIC: UNKN DEPARTURES TO
07FA/KBCT/KFLL/KHST/KHWO/KMIA/KOPF/KTMB/X51
FACILITIES INCLUDED: ZJX/ZMA/ZTL
FLIGHT STATUS: ALL_FLIGHTS
VALID: FCA ENTRY TIME FROM 250200 TO 251900
PROBABILITY OF EXTENSION: LOW
REMARKS: SEE DYNAMIC LIST FOR UPDATES. THIS ROUTE IS ISSUED DUE TO
SPECIAL OPERATIONS.
ASSOCIATED RESTRICTIONS:
MODIFICATIONS:
ROUTES: [route table not shown]
TMI ID: RRDCC504
```

## 30. route-20260401-060

- Term: **NONE** (route:NONE); written as: `PROBABILITY OF EXTENSION: NONE`
- Element: FCA010:CAPE_LAUNCH_1B_ARTEMIS; initiative: reroute; first issued 04/01 17:38Z in 20260401-060; window read as 01/2024Z - 02/0109Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 060 DCC 04/01/2026 FCA RQD /FL
NAME: FCA010:CAPE_LAUNCH_1B_ARTEMIS
CONSTRAINED AREA: ZJX/ZMA
REASON: OTHER
INCLUDE TRAFFIC: UNKN DEPARTURES TO UNKN
FACILITIES INCLUDED: ALL+CANADA
FLIGHT STATUS: ALL_FLIGHTS
VALID: FCA ENTRY TIME FROM 012024 TO 020109
PROBABILITY OF EXTENSION: NONE
REMARKS: SEE DYNAMIC LIST FOR UPDATES. IMPLEMENTED DUE TO ROCKET
LAUNCH.  FILE UPT AFTER LAST FIX ON ROUTE.
ASSOCIATED RESTRICTIONS:
MODIFICATIONS:
ROUTES: [route table not shown]
TMI ID: RRDCC503
```

Every advisory the linker could see for this element in the horizon:

```
20260401-129  sent 04/01 22:52Z  REROUTE CANCELLATION  FCA010:CAPE_LAUNCH_1B_ARTEMIS
```

**Derived outcome: NOT EXTENDED (cancelled) = 0**. cancelled at 01/2252Z; stated end 02/0109Z.

Advisory that decides the outcome:

```
ATCSCC ADVZY 129 DCC 04/01/2026 REROUTE CANCELLATION
FCA010:CAPE_LAUNCH_1B_ARTEMIS HAS BEEN CANCELLED.

REMARKS:
ASSOCIATED RESTRICTIONS:
```

## 31. plan-20260515-022-BOS-gdp-AFTER1700

- Term: **EXPECTED** (plan:EXPECTED); written as: `AFTER 1700	-BOS GROUND DELAY PROGRAM EXPECTED`
- Element: BOS; initiative: gdp; first issued 05/15 11:46Z in 20260515-022; window read as 15/1700Z - 16/0800Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 022 DCC 05/15/2026 OPERATIONS PLAN
EVENT TIME: 15/1200 - AND LATER
TERMINAL ACTIVE:
NONE
TERMINAL PLANNED:
AFTER 1500	-SFO GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1700	-BOS GROUND DELAY PROGRAM EXPECTED
AFTER 2200	-JFK GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 2300	-SEA GROUND STOP/DELAY PROGRAM POSSIBLE
```

Every advisory the linker could see for this element in the horizon:

```
20260515-020  sent 05/15 11:41Z  CDM PROPOSED GROUND DELAY PROGRAM  BOS  ANTICIPATED CUMULATIVE PROGRAM PERIOD 15/1700Z - 16/0359Z
20260515-026  sent 05/15 11:55Z  CDM GROUND DELAY PROGRAM  BOS  CUMULATIVE PROGRAM PERIOD 15/1700Z - 16/0359Z
20260515-075  sent 05/15 21:16Z  CDM GROUND STOP  BOS  GROUND STOP PERIOD 15/2059Z - 15/2215Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260515-077  sent 05/15 22:07Z  CDM GROUND DELAY PROGRAM  BOS  CUMULATIVE PROGRAM PERIOD 15/1700Z - 16/0359Z
20260515-086  sent 05/15 23:17Z  CDM GROUND DELAY PROGRAM CNX  BOS  GDP CNX PERIOD 15/2311Z - 16/1145Z
```

**Derived outcome: ISSUED = 1**. CDM GROUND DELAY PROGRAM sent 15/1155Z, period 15/1700Z - 15/2317Z.

Advisory that decides the outcome:

```
ATCSCC ADVZY 026 BOS/ZBW 05/15/2026 CDM GROUND DELAY PROGRAM
CTL ELEMENT: BOS
ELEMENT TYPE: APT
ADL TIME: 1153Z
DELAY ASSIGNMENT MODE: UDP
ARRIVALS ESTIMATED FOR: 15/1700Z - 16/0359Z
CUMULATIVE PROGRAM PERIOD: 15/1700Z - 16/0359Z
PROGRAM RATE: 38
FLT INCL: ALL CONTIGUOUS US DEP
DEP SCOPE: (ALL+CZY_AP) ZLA ZAU ZLC ZTL ZDC ZNY ZHU ZJX ZFW ZOB ZDV
ZOA ZSE ZBW ZMA ZKC ZME ZID ZAB ZMP
CANADIAN DEP ARPTS INCLUDED: CYHZ CYOW CYUL CYYZ CYTZ CYQB
DELAY ASSIGNMENT TABLE APPLIES TO: ZBW
MAXIMUM DELAY: 282
AVERAGE DELAY: 67
IMPACTING CONDITION: WEATHER / LOW CEILINGS
COMMENTS: ARRIVE 04R. DEPART 04R/O4L/09. MEDIUM POP UP. TIME PLUS
45.
```

## 32. gs-20260428-005

- Term: **LOW** (gs:LOW); written as: `PROBABILITY OF EXTENSION: LOW`
- Element: DFW; initiative: gs; first issued 04/28 00:15Z in 20260428-005; window read as 28/0012Z - 28/0115Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 005 DFW/ZFW 04/28/2026 CDM GROUND STOP
CTL ELEMENT: DFW
ELEMENT TYPE: APT
ADL TIME: 0012Z
GROUND STOP PERIOD: 28/0012Z - 28/0115Z
DEP FACILITIES INCLUDED: (Manual) ZHU ZKC ZME
PREVIOUS TOTAL, MAXIMUM, AVERAGE DELAYS: 0 / 0 / 0
NEW TOTAL, MAXIMUM, AVERAGE DELAYS: 368 / 55 / 28
PROBABILITY OF EXTENSION: LOW
IMPACTING CONDITION: WEATHER / THUNDERSTORMS
COMMENTS:
```

Every advisory the linker could see for this element in the horizon:

```
20260428-010  sent 04/28 00:44Z  CDM GS CNX  DFW  GS CNX PERIOD 28/0040Z - 28/0312Z
20260428-018  sent 04/28 01:14Z  CDM GROUND STOP  DFW  GROUND STOP PERIOD 28/0100Z - 28/0215Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260428-021  sent 04/28 02:02Z  CDM GROUND STOP  DFW  GROUND STOP PERIOD 28/0149Z - 28/0315Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260428-023  sent 04/28 02:10Z  CDM GS CNX  DFW  GS CNX PERIOD 28/0207Z - 28/0505Z
```

**Derived outcome: NOT EXTENDED (cancelled) = 0**. cancelled at 28/0044Z; stated end 28/0115Z. Flags: new_stop_30.

Advisory that decides the outcome:

```
ATCSCC ADVZY 010 DFW/ZFW 04/28/2026 CDM GS CNX
CTL ELEMENT: DFW
ELEMENT TYPE: APT
ADL TIME: 0040Z
GS CNX PERIOD: 28/0040Z - 28/0312Z
COMMENTS: OBJECTIVES MET.
```

## 33. gs-20260403-004

- Term: **HIGH** (gs:HIGH); written as: `PROBABILITY OF EXTENSION: HIGH`
- Element: ORD; initiative: gs; first issued 04/03 00:21Z in 20260403-004; window read as 02/2330Z - 03/0130Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 004 ORD/ZAU 04/03/2026 CDM GROUND STOP
CTL ELEMENT: ORD
ELEMENT TYPE: APT
ADL TIME: 0016Z
GROUND STOP PERIOD: 02/2330Z - 03/0130Z
CUMULATIVE PROGRAM PERIOD: 02/1253Z - 03/0759Z
DEP FACILITIES INCLUDED: (Manual) ZAU ZTL ZDC ZNY ZOB ZDV ZBW ZKC ZID
ZMP  CYHZ CYOW CYUL CYYZ
PREVIOUS TOTAL, MAXIMUM, AVERAGE DELAYS: 11596 / 507 / 203
NEW TOTAL, MAXIMUM, AVERAGE DELAYS: 14506 / 541 / 254
PROBABILITY OF EXTENSION: HIGH
IMPACTING CONDITION: WEATHER / THUNDERSTORMS
COMMENTS: EXTENDED TO ADD A MODIFIED 2ND TIER. WILL REMAIN DYNAMIC.
```

Every advisory the linker could see for this element in the horizon:

```
20260403-013  sent 04/03 01:26Z  CDM GROUND STOP  ORD  GROUND STOP PERIOD 03/0111Z - 03/0230Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260403-019  sent 04/03 02:15Z  CDM GROUND STOP  ORD  GROUND STOP PERIOD 03/0201Z - 03/0315Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260403-023  sent 04/03 02:51Z  CDM PROPOSED GROUND DELAY PROGRAM  ORD  ANTICIPATED CUMULATIVE PROGRAM PERIOD 02/1253Z - 03/0759Z
20260403-024  sent 04/03 03:03Z  CDM GROUND DELAY PROGRAM  ORD  CUMULATIVE PROGRAM PERIOD 02/1253Z - 03/0759Z
```

**Derived outcome: EXTENDED = 1**. end 03/0130Z -> 03/0230Z (+60 min).

Advisory that decides the outcome:

```
ATCSCC ADVZY 013 ORD/ZAU 04/03/2026 CDM GROUND STOP
CTL ELEMENT: ORD
ELEMENT TYPE: APT
ADL TIME: 0121Z
GROUND STOP PERIOD: 03/0111Z - 03/0230Z
CUMULATIVE PROGRAM PERIOD: 02/1253Z - 03/0759Z
DEP FACILITIES INCLUDED: (Manual) ZAU ZTL ZDC ZNY ZOB ZBW ZKC ZME ZID
ZMP  CYHZ CYOW CYUL CYYZ
PREVIOUS TOTAL, MAXIMUM, AVERAGE DELAYS: 14043 / 541 / 213
NEW TOTAL, MAXIMUM, AVERAGE DELAYS: 17609 / 601 / 267
PROBABILITY OF EXTENSION: MEDIUM
IMPACTING CONDITION: WEATHER / THUNDERSTORMS
COMMENTS: GROUND STOP EXTENDED, SCOPE CHANGED. ZME ADDED TO GROUND
STOP DUE TO LACK OF ROUTES THROUGH ZKC, ZDV IS RELEASED FROM GROUND
STOP.
```

## 34. route-20260518-053

- Term: **MODERATE** (route:MODERATE); written as: `PROBABILITY OF EXTENSION: MODERATE`
- Element: ATL_NO_JJEDI_PARTIAL; initiative: reroute; first issued 05/18 13:52Z in 20260518-053; window read as 18/1400Z - 18/1800Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 053 DCC 05/18/2026 ROUTE RQD /FL
NAME: ATL_NO_JJEDI_PARTIAL
CONSTRAINED AREA: ZTL
REASON: EQUIPMENT
INCLUDE TRAFFIC: KCAE/KCHS/KEWN/KFAY/KILM/KJAX/KMYR/KOAJ/KORF/KPHF/K
RDU/KSAV/KSSI/ZJX/ZMA DEPARTURES TO KATL
FACILITIES INCLUDED: ZDC/ZJX/ZMA/ZTL
FLIGHT STATUS: ALL_FLIGHTS
VALID: ETD 181400 TO 181800
PROBABILITY OF EXTENSION: MODERATE
REMARKS:
ASSOCIATED RESTRICTIONS:
MODIFICATIONS:
ROUTES: [route table not shown]
TMI ID: RRDCC502
```

Every advisory the linker could see for this element in the horizon:

```
20260518-072  sent 05/18 15:51Z  REROUTE CANCELLATION  ATL_NO_JJEDI_PARTIAL
```

**Derived outcome: NOT EXTENDED (cancelled) = 0**. cancelled at 18/1551Z; stated end 18/1800Z.

Advisory that decides the outcome:

```
ATCSCC ADVZY 072 DCC 05/18/2026 REROUTE CANCELLATION
ATL_NO_JJEDI_PARTIAL HAS BEEN CANCELLED.

REMARKS:
ASSOCIATED RESTRICTIONS:
```

## 35. gs-20260418-039

- Term: **LOW** (gs:LOW); written as: `PROBABILITY OF EXTENSION: LOW`
- Element: DFW; initiative: gs; first issued 04/18 12:17Z in 20260418-039; window read as 18/1057Z - 18/1315Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 039 DFW/ZFW 04/18/2026 CDM GROUND STOP
CTL ELEMENT: DFW
ELEMENT TYPE: APT
ADL TIME: 1214Z
GROUND STOP PERIOD: 18/1057Z - 18/1315Z
DEP FACILITIES INCLUDED: (Manual) ZHU
PREVIOUS TOTAL, MAXIMUM, AVERAGE DELAYS: 409 / 67 / 26
NEW TOTAL, MAXIMUM, AVERAGE DELAYS: 1253 / 127 / 78
PROBABILITY OF EXTENSION: LOW
IMPACTING CONDITION: WEATHER / THUNDERSTORMS
COMMENTS: REDUCED SCOPE TO ZHU ONLY. ZHU WILL WORK TACTICALLY WITH
ZFW.
```

Every advisory the linker could see for this element in the horizon:

```
20260418-042  sent 04/18 12:37Z  CDM GROUND STOP  DFW  GROUND STOP PERIOD 18/1217Z - 18/1330Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260418-044  sent 04/18 12:57Z  CDM GROUND STOP  DFW  GROUND STOP PERIOD 18/1217Z - 18/1330Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260418-045  sent 04/18 13:07Z  CDM GROUND STOP  DFW  GROUND STOP PERIOD 18/1217Z - 18/1330Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260418-048  sent 04/18 13:20Z  CDM GROUND STOP  DFW  GROUND STOP PERIOD 18/1217Z - 18/1430Z  [PROBABILITY OF EXTENSION: LOW]
20260418-052  sent 04/18 14:16Z  CDM GROUND DELAY PROGRAM  DFW  CUMULATIVE PROGRAM PERIOD 18/1400Z - 18/1859Z
```

**Derived outcome: EXTENDED = 1**. end 18/1315Z -> 18/1330Z (+15 min).

Advisory that decides the outcome:

```
ATCSCC ADVZY 042 DFW/ZFW 04/18/2026 CDM GROUND STOP
CTL ELEMENT: DFW
ELEMENT TYPE: APT
ADL TIME: 1232Z
GROUND STOP PERIOD: 18/1217Z - 18/1330Z
DEP FACILITIES INCLUDED: (Manual) ZHU ZFW ZAB
PREVIOUS TOTAL, MAXIMUM, AVERAGE DELAYS: 1238 / 127 / 28
NEW TOTAL, MAXIMUM, AVERAGE DELAYS: 2735 / 150 / 61
PROBABILITY OF EXTENSION: MEDIUM
IMPACTING CONDITION: WEATHER / THUNDERSTORMS
COMMENTS:
```

## 36. route-20260529-030

- Term: **NONE** (route:NONE); written as: `PROBABILITY OF EXTENSION: NONE`
- Element: FCA012:CAPE_LAUNCH_1A_PARTIAL; initiative: reroute; first issued 05/29 12:32Z in 20260529-030; window read as 29/1152Z - 29/1340Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 030 DCC 05/29/2026 FCA RQD
NAME: FCA012:CAPE_LAUNCH_1A_PARTIAL
CONSTRAINED AREA: ZJX/ZMA
REASON: OTHER
INCLUDE TRAFFIC: CYYZ/CZU/CZY/KCLT/ZBW/ZDC/ZID/ZNY/ZOB/ZTL
DEPARTURES TO KFLL/KOPF
FACILITIES INCLUDED: MULTIPLE FACILITIES
FLIGHT STATUS: ALL_FLIGHTS
VALID: FCA ENTRY TIME FROM 291152 TO 291340
PROBABILITY OF EXTENSION: NONE
REMARKS: REPLACES ADVZY017, ADJUSTS END TIME. SEE DYNAMIC LIST FOR
UPDATES. IMPLEMENTED DUE TO ROCKET LAUNCH.
ASSOCIATED RESTRICTIONS:
MODIFICATIONS:
ROUTES: [route table not shown]
TMI ID: RRDCC017
```

Every advisory the linker could see for this element in the horizon:

```
20260529-032  sent 05/29 13:05Z  REROUTE CANCELLATION  FCA012:CAPE_LAUNCH_1A_PARTIAL
```

**Derived outcome: NOT EXTENDED (cancelled) = 0**. cancelled at 29/1305Z; stated end 29/1340Z.

Advisory that decides the outcome:

```
ATCSCC ADVZY 032 DCC 05/29/2026 REROUTE CANCELLATION
FCA012:CAPE_LAUNCH_1A_PARTIAL HAS BEEN CANCELLED.

REMARKS: CANCELS ADVZY 030
ASSOCIATED RESTRICTIONS:
```

## 37. plan-20260527-008-PHL-gs+gdp-AFTER1900

- Term: **POSSIBLE** (plan:POSSIBLE); written as: `AFTER 1900	-PHL GROUND STOP/DELAY PROGRAM POSSIBLE`
- Element: PHL; initiative: gs/gdp; first issued 05/27 01:30Z in 20260527-008; window read as 27/1900Z - 28/0800Z
- Repeated in: 20260527-021 20260527-039 20260527-056 20260527-069 20260527-082

Source advisory:

```
ATCSCC ADVZY 008 DCC 05/27/2026 OPERATIONS PLAN
EVENT TIME: 27/0200 - AND LATER
TERMINAL ACTIVE:
NONE
TERMINAL PLANNED:
AFTER 1300	-DCA GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1300	-TPA GROUND STOP POSSIBLE
AFTER 1300	-IAH/HOU GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1500	-SFO GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1600	-IAH/HOU GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1800	-DEN GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1900	-EWR GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1900	-PHL GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1900	-ATL GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1900	-MCO/TPA GROUND STOP/DELAY PROGRAM POSSIBLE
```

Every advisory the linker could see for this element in the horizon:

```
20260527-101  sent 05/27 19:57Z  CDM GROUND STOP  PHL  GROUND STOP PERIOD 27/1943Z - 27/2115Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260527-110  sent 05/27 20:23Z  CDM PROPOSED GROUND DELAY PROGRAM  PHL  ANTICIPATED CUMULATIVE PROGRAM PERIOD 27/2021Z - 28/0159Z
20260527-117  sent 05/27 20:56Z  CDM GROUND DELAY PROGRAM  PHL  CUMULATIVE PROGRAM PERIOD 27/2052Z - 28/0159Z
20260528-003  sent 05/28 00:18Z  CDM GROUND DELAY PROGRAM CNX  PHL  GDP CNX PERIOD 28/0016Z - 28/1453Z
```

Other advisories that name the element (not read by the linker):

```
20260527-037  sent 05/27 11:00Z  PHL AIRPORT DEPARTURE DELAYS
```

**Derived outcome: ISSUED = 1**. CDM GROUND STOP sent 27/1957Z, period 27/1943Z - 27/2115Z.

Advisory that decides the outcome:

```
ATCSCC ADVZY 101 PHL/ZNY 05/27/2026 CDM GROUND STOP
CTL ELEMENT: PHL
ELEMENT TYPE: APT
ADL TIME: 1953Z
GROUND STOP PERIOD: 27/1943Z - 27/2115Z
DEP FACILITIES INCLUDED: (Manual) ZDC ZNY ZOB ZBW ZJX ZTL ZID  CYHZ
CYOW CYUL CYYZ CYTZ CYQB
PREVIOUS TOTAL, MAXIMUM, AVERAGE DELAYS: 0 / 0 / 0
NEW TOTAL, MAXIMUM, AVERAGE DELAYS: 905 / 87 / 43
PROBABILITY OF EXTENSION: MEDIUM
IMPACTING CONDITION: WEATHER / THUNDERSTORMS
COMMENTS:
```

## 38. plan-20260429-135-BOS-gs+gdp-AFTER1300

- Term: **PROBABLE** (plan:PROBABLE); written as: `AFTER 1300	-BOS GROUND STOP/DELAY PROGRAM PROBABLE`
- Element: BOS; initiative: gs/gdp; first issued 04/29 23:27Z in 20260429-135; window read as 30/1300Z - 01/0800Z
- Repeated in: 20260430-021 20260430-022

Source advisory:

```
ATCSCC ADVZY 135 DCC 04/29/2026 OPERATIONS PLAN
EVENT TIME: 30/0000 - AND LATER
TERMINAL ACTIVE:
UNTIL 0359	-BOS GROUND DELAY PROGRAM
UNTIL 0359	-DCA GROUND DELAY PROGRAM
TERMINAL PLANNED:
AFTER 1300	-BOS GROUND STOP/DELAY PROGRAM PROBABLE
AFTER 1300	-LGA/HPN GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1300	-EWR GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1400	-DEN GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1500	-SFO GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1900	-DCA GROUND STOP POSSIBLE
```

Every advisory the linker could see for this element in the horizon:

```
20260430-001  sent 04/30 00:12Z  CDM GROUND DELAY PROGRAM CNX  BOS  GDP CNX PERIOD 30/0011Z - 30/0440Z
20260430-052  sent 04/30 14:04Z  CDM PROPOSED GROUND DELAY PROGRAM  BOS  ANTICIPATED CUMULATIVE PROGRAM PERIOD 30/1700Z - 01/0359Z
20260430-054  sent 04/30 14:18Z  CDM GROUND DELAY PROGRAM  BOS  CUMULATIVE PROGRAM PERIOD 30/1700Z - 01/0359Z
20260430-121  sent 04/30 22:31Z  CDM GROUND DELAY PROGRAM CNX  BOS  GDP CNX PERIOD 30/2228Z - 01/0510Z
```

**Derived outcome: ISSUED = 1**. CDM GROUND DELAY PROGRAM sent 30/1418Z, period 30/1700Z - 30/2231Z. Flags: term_changed.

Advisory that decides the outcome:

```
ATCSCC ADVZY 054 BOS/ZBW 04/30/2026 CDM GROUND DELAY PROGRAM
CTL ELEMENT: BOS
ELEMENT TYPE: APT
ADL TIME: 1416Z
DELAY ASSIGNMENT MODE: UDP
ARRIVALS ESTIMATED FOR: 30/1700Z - 01/0359Z
CUMULATIVE PROGRAM PERIOD: 30/1700Z - 01/0359Z
PROGRAM RATE: 38
FLT INCL: ALL CONTIGUOUS US DEP
DEP SCOPE: (ALL+CZY_AP) ZLA ZAU ZLC ZTL ZDC ZNY ZHU ZJX ZFW ZOB ZDV
ZOA ZSE ZBW ZMA ZKC ZME ZID ZAB ZMP
CANADIAN DEP ARPTS INCLUDED: CYHZ CYOW CYUL CYYZ CYTZ CYQB
DELAY ASSIGNMENT TABLE APPLIES TO: ZBW
MAXIMUM DELAY: 405
AVERAGE DELAY: 67
IMPACTING CONDITION: WEATHER / LOW CEILINGS
COMMENTS: ARR: 4R DEP: 9 MED HIST POP UP. TIME PLUS 45
```

## 39. gs-20260405-044

- Term: **MEDIUM** (gs:MEDIUM); written as: `PROBABILITY OF EXTENSION: MEDIUM`
- Element: LGA; initiative: gs; first issued 04/05 14:31Z in 20260405-044; window read as 05/1411Z - 05/1545Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 044 LGA/ZNY 04/05/2026 CDM GROUND STOP
CTL ELEMENT: LGA
ELEMENT TYPE: APT
ADL TIME: 1426Z
GROUND STOP PERIOD: 05/1411Z - 05/1545Z
DEP FACILITIES INCLUDED: (Manual) ZDC ZNY ZOB ZBW  CYHZ CYOW CYUL
CYYZ CYTZ CYQB
PREVIOUS TOTAL, MAXIMUM, AVERAGE DELAYS: 684 / 102 / 16
NEW TOTAL, MAXIMUM, AVERAGE DELAYS: 2952 / 162 / 67
PROBABILITY OF EXTENSION: MEDIUM
IMPACTING CONDITION: WEATHER / LOW CEILINGS
COMMENTS:
```

Every advisory the linker could see for this element in the horizon:

```
20260405-051  sent 04/05 15:40Z  CDM GROUND DELAY PROGRAM  LGA  CUMULATIVE PROGRAM PERIOD 05/1530Z - 06/0159Z
20260405-066  sent 04/05 17:04Z  CDM GROUND STOP  LGA  GROUND STOP PERIOD 05/1650Z - 05/1800Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260405-068  sent 04/05 17:35Z  CDM GROUND STOP  LGA  GROUND STOP PERIOD 05/1650Z - 05/1900Z  [PROBABILITY OF EXTENSION: MEDIUM]
```

Other advisories that name the element (not read by the linker):

```
20260405-056  sent 04/05 15:57Z  LGA AIRPORT ARRIVAL DELAYS
20260405-058  sent 04/05 16:00Z  LGA EWR AND METS AIRPORT DIVERSION RECOVERY ACTIVATED
```

**Derived outcome: NOT EXTENDED (lapsed) = 0**. no later advisory moved the end past 05/1545Z. Flags: gdp_followed.

No advisory decides the outcome (nothing qualifying was found).

## 40. route-20260401-059

- Term: **NONE** (route:NONE); written as: `PROBABILITY OF EXTENSION: NONE`
- Element: FCA009:NO_AR_ATLANTIC_Y-RTES_TO_MCO_TPA_RSW_AREAS; initiative: reroute; first issued 04/01 17:38Z in 20260401-059; window read as 01/2139Z - 02/0109Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 059 DCC 04/01/2026 FCA RQD /FL
NAME: FCA009:NO_AR_ATLANTIC_Y-RTES_TO_MCO_TPA_RSW_AREAS
CONSTRAINED AREA: ZJX/ZMA
REASON: OTHER
INCLUDE TRAFFIC: UNKN DEPARTURES TO
KAPF/KFMY/KISM/KLAL/KMCF/KMCO/KMKY/KORL/KPGD/KPIE/K
RSW/KSFB/KSPG/KSRQ/KTPA/KTPF
FACILITIES INCLUDED: ZJX/ZMA/ZDC/ZNY/ZBW/ZID/ZTL/ZOB/CZY
FLIGHT STATUS: ALL_FLIGHTS
VALID: FCA ENTRY TIME FROM 012139 TO 020109
PROBABILITY OF EXTENSION: NONE
REMARKS: SEE DYNAMIC LIST FOR UPDATES. IMPLEMENTED DUE TO ROCKET
LAUNCH ACTIVITIES.
ASSOCIATED RESTRICTIONS:
MODIFICATIONS:
ROUTES: [route table not shown]
TMI ID: RRDCC502
```

Every advisory the linker could see for this element in the horizon:

```
20260401-128  sent 04/01 22:51Z  REROUTE CANCELLATION  FCA009:NO_AR_ATLANTIC_Y-RTES_TO_MCO_TPA_RSW_AREAS
```

**Derived outcome: NOT EXTENDED (cancelled) = 0**. cancelled at 01/2251Z; stated end 02/0109Z.

Advisory that decides the outcome:

```
ATCSCC ADVZY 128 DCC 04/01/2026 REROUTE CANCELLATION
FCA009:NO_AR_ATLANTIC_Y-RTES_TO_MCO_TPA_RSW_AREAS HAS BEEN CANCELLED.

REMARKS:
ASSOCIATED RESTRICTIONS:
```

## 41. gs-20260418-078

- Term: **MEDIUM** (gs:MEDIUM); written as: `PROBABILITY OF EXTENSION: MEDIUM`
- Element: IAH; initiative: gs; first issued 04/18 21:21Z in 20260418-078; window read as 18/2115Z - 18/2230Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 078 IAH/ZHU 04/18/2026 CDM GROUND STOP
CTL ELEMENT: IAH
ELEMENT TYPE: APT
ADL TIME: 2115Z
GROUND STOP PERIOD: 18/2115Z - 18/2230Z
CUMULATIVE PROGRAM PERIOD: 18/2200Z - 19/0259Z
DEP FACILITIES INCLUDED: (1stTier) ZTL ZHU ZJX ZFW ZMA ZME ZAB
PREVIOUS TOTAL, MAXIMUM, AVERAGE DELAYS: 340 / 81 / 26
NEW TOTAL, MAXIMUM, AVERAGE DELAYS: 940 / 117 / 72
PROBABILITY OF EXTENSION: MEDIUM
IMPACTING CONDITION: WEATHER / WIND
COMMENTS:
```

Every advisory the linker could see for this element in the horizon:

```
20260418-086  sent 04/18 22:30Z  IAH GROUND STOP CANCELLATION  IAH
```

Other advisories that name the element (not read by the linker):

```
20260418-079  sent 04/18 21:21Z  IAH HOU CDRS_FYI
20260418-083  sent 04/18 21:41Z  IAH AIRPORT DIVERSION RECOVERY ACTIVATED
```

**Derived outcome: NOT EXTENDED (lapsed) = 0**. no later advisory moved the end past 18/2230Z. Flags: manual_release.

No advisory decides the outcome (nothing qualifying was found).

## 42. plan-20260521-108-DEN-gs-UNTIL0200

- Term: **POSSIBLE** (plan:POSSIBLE); written as: `UNTIL 0200	-DEN GROUND STOP POSSIBLE`
- Element: DEN; initiative: gs; first issued 05/21 19:51Z in 20260521-108; window read as 21/1951Z - 22/0200Z
- Repeated in: 20260521-122

Source advisory:

```
ATCSCC ADVZY 108 DCC 05/21/2026 OPERATIONS PLAN
EVENT TIME: 21/2000 - AND LATER
TERMINAL ACTIVE:
UNTIL 0359	-LGA GROUND DELAY PROGRAM
UNTIL 0659	-SFO GROUND DELAY
TERMINAL PLANNED:
AFTER 2100	-JFK GROUND DELAY PROGRAM PROBABLE
UNTIL 0000	-TPA/MCO GROUND STOP POSSIBLE
UNTIL 0200	-DFW/DAL GROUND STOP/DELAY PROGRAM POSSIBLE
UNTIL 0200	-IAH/HOU GROUND STOP/DELAY PROGRAM POSSIBLE
UNTIL 0200	-DEN GROUND STOP POSSIBLE
```

Every advisory the linker could see for this element in the horizon:

```
20260521-135  sent 05/21 23:17Z  CDM GROUND STOP  DEN  GROUND STOP PERIOD 21/2301Z - 22/0030Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260522-006  sent 05/22 00:19Z  CDM GROUND STOP  DEN  GROUND STOP PERIOD 21/2301Z - 22/0130Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260522-010  sent 05/22 00:47Z  CDM GROUND STOP  DEN  GROUND STOP PERIOD 22/0030Z - 22/0200Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260522-018  sent 05/22 01:55Z  CDM GS CNX  DEN  GS CNX PERIOD 22/0152Z - 22/0422Z
```

Other advisories that name the element (not read by the linker):

```
20260521-111  sent 05/21 20:13Z  DEN CDRS_FYI
20260521-140  sent 05/21 23:49Z  DEN AIRPORT ARRIVAL DELAYS
20260522-003  sent 05/22 00:04Z  DEN AIRPORT DIVERSION RECOVERY ACTIVATED
20260522-013  sent 05/22 01:09Z  DEN CDRS_FYI
```

**Derived outcome: ISSUED = 1**. CDM GROUND STOP sent 21/2317Z, period 21/2301Z - 22/0030Z.

Advisory that decides the outcome:

```
ATCSCC ADVZY 135 DEN/ZDV 05/21/2026 CDM GROUND STOP
CTL ELEMENT: DEN
ELEMENT TYPE: APT
ADL TIME: 2311Z
GROUND STOP PERIOD: 21/2301Z - 22/0030Z
DEP FACILITIES INCLUDED: (1stTier) ZLA ZLC ZDV ZKC ZAB ZMP
PREVIOUS TOTAL, MAXIMUM, AVERAGE DELAYS: 0 / 0 / 0
NEW TOTAL, MAXIMUM, AVERAGE DELAYS: 2368 / 83 / 36
PROBABILITY OF EXTENSION: MEDIUM
IMPACTING CONDITION: WEATHER / WIND
COMMENTS:
```

## 43. gs-20260405-066

- Term: **MEDIUM** (gs:MEDIUM); written as: `PROBABILITY OF EXTENSION: MEDIUM`
- Element: LGA; initiative: gs; first issued 04/05 17:04Z in 20260405-066; window read as 05/1650Z - 05/1800Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 066 LGA/ZNY 04/05/2026 CDM GROUND STOP
CTL ELEMENT: LGA
ELEMENT TYPE: APT
ADL TIME: 1700Z
GROUND STOP PERIOD: 05/1650Z - 05/1800Z
CUMULATIVE PROGRAM PERIOD: 05/1530Z - 06/0159Z
DEP FACILITIES INCLUDED: (Manual) ZDC ZNY ZOB ZBW  CYHZ CYOW CYUL
CYYZ CYTZ CYQB
PREVIOUS TOTAL, MAXIMUM, AVERAGE DELAYS: 1437 / 224 / 57
NEW TOTAL, MAXIMUM, AVERAGE DELAYS: 2734 / 290 / 109
PROBABILITY OF EXTENSION: MEDIUM
IMPACTING CONDITION: WEATHER / LOW CEILINGS
COMMENTS:
```

Every advisory the linker could see for this element in the horizon:

```
20260405-068  sent 04/05 17:35Z  CDM GROUND STOP  LGA  GROUND STOP PERIOD 05/1650Z - 05/1900Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260405-074  sent 04/05 18:56Z  CDM GROUND DELAY PROGRAM  LGA  CUMULATIVE PROGRAM PERIOD 05/1530Z - 06/0359Z
```

**Derived outcome: EXTENDED = 1**. end 05/1800Z -> 05/1900Z (+60 min).

Advisory that decides the outcome:

```
ATCSCC ADVZY 068 LGA/ZNY 04/05/2026 CDM GROUND STOP
CTL ELEMENT: LGA
ELEMENT TYPE: APT
ADL TIME: 1734Z
GROUND STOP PERIOD: 05/1650Z - 05/1900Z
CUMULATIVE PROGRAM PERIOD: 05/1530Z - 06/0159Z
DEP FACILITIES INCLUDED: (2ndTier+CZY_AP) ZAU ZTL ZDC ZNY ZJX ZOB ZBW
ZID ZMP  CYHZ CYOW CYUL CYYZ CYTZ CYQB
PREVIOUS TOTAL, MAXIMUM, AVERAGE DELAYS: 3649 / 215 / 74
NEW TOTAL, MAXIMUM, AVERAGE DELAYS: 6252 / 277 / 128
PROBABILITY OF EXTENSION: MEDIUM
IMPACTING CONDITION: WEATHER / LOW CEILINGS
COMMENTS: EXPANDED TO 2ND TIER TO BUILD MORE RECOVERY ROOM AS WELL AS
EXTENDED AN ADDITIONAL HOUR.
```

## 44. route-20260424-068

- Term: **HIGH** (route:HIGH); written as: `PROBABILITY OF EXTENSION: HIGH`
- Element: FCA017:MIA_AND_SATS_VIA_DEEP_WATER; initiative: reroute; first issued 04/24 17:57Z in 20260424-068; window read as 24/2045Z - 25/0200Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 068 DCC 04/24/2026 FCA RQD
NAME: FCA017:MIA_AND_SATS_VIA_DEEP_WATER
CONSTRAINED AREA: ZJX/ZMA
REASON: OTHER
INCLUDE TRAFFIC: UNKN DEPARTURES TO 07FA/KHST/KMIA/KTMB/X51
FACILITIES INCLUDED: ZMA/ZNY
FLIGHT STATUS: ALL_FLIGHTS
VALID: FCA ENTRY TIME FROM 242045 TO 250200
PROBABILITY OF EXTENSION: HIGH
REMARKS: SEE DYNAMIC LIST FOR UPDATES. THIS ROUTE IS FOR
INTERNATIONAL ARRIVALS TO MIA AREA DUE TO SPECIAL OPS.
ASSOCIATED RESTRICTIONS:
MODIFICATIONS:
ROUTES: [route table not shown]
TMI ID: RRDCC527
```

Every advisory the linker could see for this element in the horizon:

```
20260425-004  sent 04/25 00:41Z  FCA RQD  FCA026:MIA_AND_SATS_VIA_DEEP_WATER  VALID 25/0200Z - 25/1900Z  [PROBABILITY OF EXTENSION: LOW]
```

**Derived outcome: EXTENDED = 1**. end 25/0200Z -> 25/1900Z (+1020 min), carried on as FCA026:MIA_AND_SATS_VIA_DEEP_WATER under TMI ID RRDCC507. Flags: continued_new_id.

Advisory that decides the outcome:

```
ATCSCC ADVZY 004 DCC 04/25/2026 FCA RQD
NAME: FCA026:MIA_AND_SATS_VIA_DEEP_WATER
CONSTRAINED AREA: ZJX/ZMA
REASON: OTHER
INCLUDE TRAFFIC: UNKN DEPARTURES TO 07FA/KHST/KMIA/KTMB/X51
FACILITIES INCLUDED: ZMA/ZNY
FLIGHT STATUS: ALL_FLIGHTS
VALID: FCA ENTRY TIME FROM 250200 TO 251900
PROBABILITY OF EXTENSION: LOW
REMARKS: SEE DYNAMIC LIST FOR UPDATES. THIS ROUTE IS FOR
INTERNATIONAL ARRIVALS TO MIA AREA DUE TO SPECIAL OPS.
ASSOCIATED RESTRICTIONS:
MODIFICATIONS:
ROUTES: [route table not shown]
TMI ID: RRDCC507
```

## 45. route-20260521-083

- Term: **NONE** (route:NONE); written as: `PROBABILITY OF EXTENSION: NONE`
- Element: FCA004:STARSHIP_WEST; initiative: reroute; first issued 05/21 16:50Z in 20260521-083; window read as 21/2215Z - 22/0043Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 083 DCC 05/21/2026 FCA RQD
NAME: FCA004:STARSHIP_WEST
CONSTRAINED AREA: ZHU
REASON: OTHER
INCLUDE TRAFFIC: UNKN/ZAB/ZAU/ZDV/ZFW/ZHU/ZID/ZKC/ZLA/ZLC/ZME/ZMP/ZO
A/ZOB/ZSE DEPARTURES TO UNKN
FACILITIES INCLUDED: ALL + CANADA
FLIGHT STATUS: ALL_FLIGHTS
VALID: FCA ENTRY TIME FROM 212215 TO 220043
PROBABILITY OF EXTENSION: NONE
REMARKS: SEE DYNAMIC LIST FOR UPDATES. IMPLEMENTED DUE TO ROCKET
LAUNCH. USERS SHOULD FILE UPT ROUTING AFTER BRO/ LRD/
SUTOL.  USERS CAN ALSO FILE UPT ROUTING EAST OF THE FCA BUT
CHECK NOTAMS FOR FOREIGN ANSP AIRSPACE CLOSURES ASSOCIATED
WITH THIS LAUNCH.
ASSOCIATED RESTRICTIONS:
MODIFICATIONS:
ROUTES: [route table not shown]
TMI ID: RRDCC506
```

Every advisory the linker could see for this element in the horizon:

```
20260521-139  sent 05/21 23:45Z  REROUTE CANCELLATION  FCA004:STARSHIP_WEST
```

**Derived outcome: NOT EXTENDED (cancelled) = 0**. cancelled at 21/2345Z; stated end 22/0043Z.

Advisory that decides the outcome:

```
ATCSCC ADVZY 139 DCC 05/21/2026 REROUTE CANCELLATION
FCA004:STARSHIP_WEST HAS BEEN CANCELLED.

REMARKS:
ASSOCIATED RESTRICTIONS:
```

## 46. route-20260429-118

- Term: **LOW** (route:LOW); written as: `PROBABILITY OF EXTENSION: LOW`
- Element: FCA020:STAVE_2_FLORIDA_ARVLS; initiative: reroute; first issued 04/29 21:12Z in 20260429-118; window read as 30/0005Z - 30/0500Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 118 DCC 04/29/2026 FCA RQD
NAME: FCA020:STAVE_2_FLORIDA_ARVLS
CONSTRAINED AREA: ZJX/ZMA
REASON: OTHER
INCLUDE TRAFFIC: CLT/CZU/CZY/KCDW/KJFK/KMMU/KPHL/KTEB/UNKN/ZBW/ZDC/Z
NY DEPARTURES TO
KAPF/KBCT/KFLL/KFMY/KFPR/KFXE/KMIA/KMKY/KOPF/KPBI/K
PMP/KRSW/KSUA/KTMB/KVRB
FACILITIES INCLUDED: CZU/CZY/ZBW/ZDC/ZJX/ZMA/ZNY/ZOB/ZTL
FLIGHT STATUS: ALL_FLIGHTS
VALID: FCA ENTRY TIME FROM 300005 TO 300500
PROBABILITY OF EXTENSION: LOW
REMARKS: IMPLEMENTED DUE TO SUA ACTIVITY. SEE DYNAMIC LIST FOR
UPDATES.
ASSOCIATED RESTRICTIONS:
MODIFICATIONS:
ROUTES: [route table not shown]
TMI ID: RRDCC516
```

Every advisory the linker could see for this element in the horizon:

```
20260430-008  sent 04/30 01:56Z  REROUTE CANCELLATION  FCA020:STAVE_2_FLORIDA_ARVLS
```

**Derived outcome: NOT EXTENDED (cancelled) = 0**. cancelled at 30/0156Z; stated end 30/0500Z.

Advisory that decides the outcome:

```
ATCSCC ADVZY 008 DCC 04/30/2026 REROUTE CANCELLATION
FCA020:STAVE_2_FLORIDA_ARVLS HAS BEEN CANCELLED.

REMARKS: CANCELS ADVZY 118
ASSOCIATED RESTRICTIONS:
```

## 47. route-20260423-039

- Term: **HIGH** (route:HIGH); written as: `PROBABILITY OF EXTENSION: HIGH`
- Element: FCA004:LAKE_ERIE_WEST_PARTIAL; initiative: reroute; first issued 04/23 16:18Z in 20260423-039; window read as 23/1400Z - 23/1800Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 039 DCC 04/23/2026 FCA RQD
NAME: FCA004:LAKE_ERIE_WEST_PARTIAL
CONSTRAINED AREA: CZY
REASON: OTHER
INCLUDE TRAFFIC: ZNY DEPARTURES TO
KFNT/KMBS/KMKE/KMSP/KORD/ZAB/ZAU/ZDV/ZKC/ZLA/ZLC/ZM
P/ZOA/ZSE
FACILITIES INCLUDED: ZAB/ZAU/ZDV/ZKC/ZLA/ZLC/ZMP/ZNY/ZOA/ZOB/ZSE
FLIGHT STATUS: ALL_FLIGHTS
VALID: FCA ENTRY TIME FROM 231400 TO 231800
PROBABILITY OF EXTENSION: HIGH
REMARKS: REPLACES ADVZY 012.  SEE DYNAMIC LIST FOR UPDATES. DUE TO
REDUCED SYSTEM CAPACITY IN CZY. EXPECT A SIMILAR
RESTRICTION PAST 0300Z DUE TO CZY STAFFING. CURRENTLY
SHORTENED TO 2000Z FOR FORECASTED WX.
ASSOCIATED RESTRICTIONS:
MODIFICATIONS: TIMES ADJUSTED
ROUTES: [route table not shown]
TMI ID: RRDCC012
```

Every advisory the linker could see for this element in the horizon:

```
20260423-040  sent 04/23 16:21Z  FCA RQD  FCA012:LAKE_ERIE_WEST_PARTIAL  VALID 23/1800Z - 24/0300Z  [PROBABILITY OF EXTENSION: LOW]
```

**Derived outcome: EXTENDED = 1**. end 23/1800Z -> 24/0300Z (+540 min), carried on as FCA012:LAKE_ERIE_WEST_PARTIAL under TMI ID RRDCC040. Flags: continued_new_id.

Advisory that decides the outcome:

```
ATCSCC ADVZY 040 DCC 04/23/2026 FCA RQD
NAME: FCA012:LAKE_ERIE_WEST_PARTIAL
CONSTRAINED AREA: CZY
REASON: OTHER
INCLUDE TRAFFIC: KBUF/KIAG/KPHL/KROC/KSYR/ZBW/ZNY DEPARTURES TO
KFNT/KMBS/KMKE/KORD/KPTK/KYIP/ZAB/ZAU/ZDV/ZKC/ZLA/Z
LC/ZOA/ZSE
FACILITIES INCLUDED: ZAB/ZAU/ZBW/ZDV/ZKC/ZLA/ZLC/ZNY/ZOA/ZOB/ZSE
FLIGHT STATUS: ALL_FLIGHTS
VALID: FCA ENTRY TIME FROM 231800 TO 240300
PROBABILITY OF EXTENSION: LOW
REMARKS: DUE TO STAFFING.  SEE DYNAMIC LIST FOR UPDATES.
ASSOCIATED RESTRICTIONS:
MODIFICATIONS:
ROUTES: [route table not shown]
TMI ID: RRDCC040
```

## 48. gs-20260518-081

- Term: **MEDIUM** (gs:MEDIUM); written as: `PROBABILITY OF EXTENSION: MEDIUM`
- Element: LAS; initiative: gs; first issued 05/18 16:56Z in 20260518-081; window read as 18/1640Z - 18/1800Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 081 LAS/ZLA 05/18/2026 CDM GROUND STOP
CTL ELEMENT: LAS
ELEMENT TYPE: APT
ADL TIME: 1655Z
GROUND STOP PERIOD: 18/1640Z - 18/1800Z
DEP FACILITIES INCLUDED: (1stTier) ZLA ZLC ZDV ZOA ZAB
PREVIOUS TOTAL, MAXIMUM, AVERAGE DELAYS: 0 / 0 / 0
NEW TOTAL, MAXIMUM, AVERAGE DELAYS: 2033 / 71 / 41
PROBABILITY OF EXTENSION: MEDIUM
IMPACTING CONDITION: WEATHER / WIND
COMMENTS: CONFIG 2 AAR DECREASED TO 44.
```

Every advisory the linker could see for this element in the horizon:

```
20260518-083  sent 05/18 17:34Z  CDM PROPOSED GROUND DELAY PROGRAM  LAS  ANTICIPATED CUMULATIVE PROGRAM PERIOD 18/1731Z - 19/0159Z
20260518-090  sent 05/18 17:47Z  CDM GROUND DELAY PROGRAM  LAS  CUMULATIVE PROGRAM PERIOD 18/1741Z - 19/0159Z
```

**Derived outcome: NOT EXTENDED (lapsed) = 0**. no later advisory moved the end past 18/1800Z. Flags: gdp_followed.

No advisory decides the outcome (nothing qualifying was found).

## 49. gs-20260424-092

- Term: **LOW** (gs:LOW); written as: `PROBABILITY OF EXTENSION: LOW`
- Element: DCA; initiative: gs; first issued 04/24 20:35Z in 20260424-092; window read as 24/1940Z - 24/2115Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 092 DCA/ZDC 04/24/2026 CDM GROUND STOP
CTL ELEMENT: DCA
ELEMENT TYPE: APT
ADL TIME: 2032Z
GROUND STOP PERIOD: 24/1940Z - 24/2115Z
CUMULATIVE PROGRAM PERIOD: 24/1757Z - 25/0259Z
DEP FACILITIES INCLUDED: (Manual) ZNY ZBW
PREVIOUS TOTAL, MAXIMUM, AVERAGE DELAYS: 991 / 179 / 66
NEW TOTAL, MAXIMUM, AVERAGE DELAYS: 1440 / 191 / 96
PROBABILITY OF EXTENSION: LOW
IMPACTING CONDITION: WEATHER / THUNDERSTORMS
COMMENTS: OUT OF HOLDING. ROUTES STILL UNAVAILABLE THROUGH ZNY. STOP
CNX FOR OTHER 1ST TIERS, EXTENDED FOR ZNY&ZBW. DCA NOW IN NORTH OP
SCHEDULING TO 30 AAR.
```

Every advisory the linker could see for this element in the horizon:

```
20260424-095  sent 04/24 20:54Z  DCA GROUND STOP CANCELLATION  DCA  EVENT TIME 24/2055Z - ?
```

**Derived outcome: NOT EXTENDED (lapsed) = 0**. no later advisory moved the end past 24/2115Z. Flags: manual_release.

No advisory decides the outcome (nothing qualifying was found).

## 50. route-20260425-003

- Term: **LOW** (route:LOW); written as: `PROBABILITY OF EXTENSION: LOW`
- Element: FCA021:GA_TO_BCT_AREA; initiative: reroute; first issued 04/25 00:40Z in 20260425-003; window read as 25/0200Z - 25/1900Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 003 DCC 04/25/2026 FCA RQD
NAME: FCA021:GA_TO_BCT_AREA
CONSTRAINED AREA: ZJX/ZMA
REASON: OTHER
INCLUDE TRAFFIC: CZU/CZY/KBWI/KCLT/KDCA/KDET/KDTW/KFAY/KFNT/KIAD/KIL
M/KLAN/KMBS/KOAJ/KPTK/KRIC/KROA/KSOP/KYIP/ZAB/ZAU/Z
BW/ZDC/ZDV/ZFW/ZHU/ZID/ZJX/ZKC/ZLA/ZLC/ZME/ZMP/ZNY/
ZOA/ZOB/ZSE/ZTL DEPARTURES TO KBCT/KFXE/KPMP
FACILITIES INCLUDED: CZU/CZY/ZAB/ZAU/ZBW/ZDC/ZDV/ZFW/ZHU/ZID/ZJX/ZKC
/ZLA/ZLC/ZMA/ZME/ZMP/ZNY/ZOA/ZOB/ZSE/ZTL
FLIGHT STATUS: ALL_FLIGHTS
VALID: FCA ENTRY TIME FROM 250200 TO 251900
PROBABILITY OF EXTENSION: LOW
REMARKS: SEE DYNAMIC LIST FOR UPDATES. THIS ROUTE IS ISSUED DUE TO
SPECIAL OPERATIONS.
ASSOCIATED RESTRICTIONS:
MODIFICATIONS:
ROUTES: [route table not shown]
TMI ID: RRDCC500
```

Every advisory the linker could see for this element in the horizon:

```
20260425-053  sent 04/25 18:49Z  REROUTE CANCELLATION  FCA021:GA_TO_BCT_AREA
```

**Derived outcome: NOT EXTENDED (cancelled) = 0**. cancelled at 25/1849Z; stated end 25/1900Z.

Advisory that decides the outcome:

```
ATCSCC ADVZY 053 DCC 04/25/2026 REROUTE CANCELLATION
FCA021:GA_TO_BCT_AREA HAS BEEN CANCELLED.

REMARKS:
ASSOCIATED RESTRICTIONS:
```

## 51. gs-20260404-019

- Term: **LOW** (gs:LOW); written as: `PROBABILITY OF EXTENSION: LOW`
- Element: ORD; initiative: gs; first issued 04/04 03:44Z in 20260404-019; window read as 04/0328Z - 04/0445Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 019 ORD/ZAU 04/04/2026 CDM GROUND STOP
CTL ELEMENT: ORD
ELEMENT TYPE: APT
ADL TIME: 0342Z
GROUND STOP PERIOD: 04/0328Z - 04/0445Z
CUMULATIVE PROGRAM PERIOD: 04/0126Z - 04/0659Z
DEP FACILITIES INCLUDED: (1stTier) ZAU ZOB ZKC ZID ZMP
PREVIOUS TOTAL, MAXIMUM, AVERAGE DELAYS: 507 / 210 / 21
NEW TOTAL, MAXIMUM, AVERAGE DELAYS: 1785 / 181 / 74
PROBABILITY OF EXTENSION: LOW
IMPACTING CONDITION: WEATHER / THUNDERSTORMS
COMMENTS: GDP REVISION PROBABLE
```

Every advisory the linker could see for this element in the horizon:

```
20260404-020  sent 04/04 04:33Z  CDM GROUND STOP  ORD  GROUND STOP PERIOD 04/0328Z - 04/0600Z  [PROBABILITY OF EXTENSION: LOW]
20260404-022  sent 04/04 05:19Z  CDM GROUND DELAY PROGRAM CNX  ORD  GDP CNX PERIOD 04/0513Z - 04/1724Z
20260404-023  sent 04/04 05:22Z  CDM GROUND STOP  ORD  GROUND STOP PERIOD 04/0509Z - 04/0615Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260404-025  sent 04/04 06:01Z  CDM GROUND STOP  ORD  GROUND STOP PERIOD 04/0547Z - 04/0700Z  [PROBABILITY OF EXTENSION: LOW]
20260404-026  sent 04/04 06:15Z  CDM GS CNX  ORD  GS CNX PERIOD 04/0611Z - 04/0918Z
```

**Derived outcome: EXTENDED = 1**. end 04/0445Z -> 04/0600Z (+75 min).

Advisory that decides the outcome:

```
ATCSCC ADVZY 020 ORD/ZAU 04/04/2026 CDM GROUND STOP
CTL ELEMENT: ORD
ELEMENT TYPE: APT
ADL TIME: 0429Z
GROUND STOP PERIOD: 04/0328Z - 04/0600Z
CUMULATIVE PROGRAM PERIOD: 04/0126Z - 04/0659Z
DEP FACILITIES INCLUDED: (Manual) ZKC ZMP
PREVIOUS TOTAL, MAXIMUM, AVERAGE DELAYS: 278 / 178 / 70
NEW TOTAL, MAXIMUM, AVERAGE DELAYS: 592 / 239 / 148
PROBABILITY OF EXTENSION: LOW
IMPACTING CONDITION: WEATHER / THUNDERSTORMS
COMMENTS: ROUTES NOT AVAILABLE WEST OF ORD, GS SCOPE REDUCED
```

## 52. route-20260525-121

- Term: **LOW** (route:LOW); written as: `PROBABILITY OF EXTENSION: LOW`
- Element: FCA014:TEXAS_TO_DEN; initiative: reroute; first issued 05/25 21:38Z in 20260525-121; window read as 25/2230Z - 26/0230Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 121 DCC 05/25/2026 FCA RQD
NAME: FCA014:TEXAS_TO_DEN
CONSTRAINED AREA: ZDV
REASON: WEATHER
INCLUDE TRAFFIC: ZFW/ZHU DEPARTURES TO KDEN
FACILITIES INCLUDED: ZAB/ZDV/ZFW/ZHU
FLIGHT STATUS: ALL_FLIGHTS
VALID: FCA ENTRY TIME FROM 252230 TO 260230
PROBABILITY OF EXTENSION: LOW
REMARKS: SEE DYNAMIC LIST FOR UPDATES.
ASSOCIATED RESTRICTIONS:
MODIFICATIONS: BASED ON DEN_GCK_2
ROUTES: [route table not shown]
TMI ID: RRDCC506
```

Every advisory the linker could see for this element in the horizon:

```
20260526-009  sent 05/26 01:21Z  REROUTE CANCELLATION  FCA014:TEXAS_TO_DEN
```

**Derived outcome: NOT EXTENDED (cancelled) = 0**. cancelled at 26/0121Z; stated end 26/0230Z.

Advisory that decides the outcome:

```
ATCSCC ADVZY 009 DCC 05/26/2026 REROUTE CANCELLATION
FCA014:TEXAS_TO_DEN HAS BEEN CANCELLED.

REMARKS: CANCELS ADVZY 121
ASSOCIATED RESTRICTIONS:
```

## 53. plan-20260420-055-LGA-gs+gdp-UNTIL0100

- Term: **POSSIBLE** (plan:POSSIBLE); written as: `UNTIL 0100	-LGA GROUND STOP/DELAY PROGRAM POSSIBLE`
- Element: LGA; initiative: gs/gdp; first issued 04/20 17:45Z in 20260420-055; window read as 20/1745Z - 21/0100Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 055 DCC 04/20/2026 OPERATIONS PLAN
EVENT TIME: 20/1800 - AND LATER
TERMINAL ACTIVE:
UNTIL 1815	-LGA GROUND STOP
UNTIL 0659	-SFO GROUND DELAY PROGRAM
TERMINAL PLANNED:
AFTER 1900	-JFK GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 2100	-EWR GROUND STOP/DELAY PROGRAM POSSIBLE
UNTIL 2300	-MIA/FLL GROUND STOP POSSIBLE
UNTIL 0100	-LGA GROUND STOP/DELAY PROGRAM POSSIBLE
```

Every advisory the linker could see for this element in the horizon:

```
20260420-053  sent 04/20 17:13Z  CDM GROUND STOP  LGA  GROUND STOP PERIOD 20/1701Z - 20/1815Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260420-059  sent 04/20 18:15Z  CDM GS CNX  LGA  GS CNX PERIOD 20/1813Z - 20/1920Z
20260420-062  sent 04/20 19:03Z  CDM GROUND STOP  LGA  GROUND STOP PERIOD 20/1848Z - 20/2000Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260420-064  sent 04/20 19:15Z  CDM GS CNX  LGA  GS CNX PERIOD 20/1913Z - 20/2136Z
20260420-070  sent 04/20 21:19Z  CDM PROPOSED GROUND DELAY PROGRAM  LGA  ANTICIPATED CUMULATIVE PROGRAM PERIOD 20/2113Z - 21/0259Z
20260420-075  sent 04/20 21:34Z  CDM GROUND DELAY PROGRAM  LGA  CUMULATIVE PROGRAM PERIOD 20/2113Z - 21/0259Z
20260421-007  sent 04/21 00:38Z  CDM GROUND DELAY PROGRAM CNX  LGA  GDP CNX PERIOD 21/0034Z - 22/0041Z
```

Other advisories that name the element (not read by the linker):

```
20260420-042  sent 04/20 14:38Z  LGA AIRPORT ARRIVAL DELAYS
```

**Derived outcome: EXCLUDED (already_active)**. CDM GROUND STOP already running at 20/1745Z, until 20/1815Z.

Advisory that decides the outcome:

```
ATCSCC ADVZY 053 LGA/ZNY 04/20/2026 CDM GROUND STOP
CTL ELEMENT: LGA
ELEMENT TYPE: APT
ADL TIME: 1711Z
GROUND STOP PERIOD: 20/1701Z - 20/1815Z
DEP FACILITIES INCLUDED: (Manual) ZDC ZNY ZOB ZBW
PREVIOUS TOTAL, MAXIMUM, AVERAGE DELAYS: 0 / 0 / 0
NEW TOTAL, MAXIMUM, AVERAGE DELAYS: 307 / 62 / 28
PROBABILITY OF EXTENSION: MEDIUM
IMPACTING CONDITION: WEATHER / WIND
COMMENTS:
```

## 54. route-20260522-052

- Term: **HIGH** (route:HIGH); written as: `PROBABILITY OF EXTENSION: HIGH`
- Element: FCA005:ZBW_CZU_TO_ZDC; initiative: reroute; first issued 05/22 14:15Z in 20260522-052; window read as 22/1700Z - 23/0200Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 052 DCC 05/22/2026 FCA RQD
NAME: FCA005:ZBW_CZU_TO_ZDC
CONSTRAINED AREA: ZDC/ZNY
REASON: OTHER
INCLUDE TRAFFIC: CZU/ZBW DEPARTURES TO KADW/KBWI/KDCA/KESN/KGAI/KMTN
FACILITIES INCLUDED: CZU/ZBW/ZDC/ZNY/ZOB
FLIGHT STATUS: ALL_FLIGHTS
VALID: FCA ENTRY TIME FROM 221700 TO 230200
PROBABILITY OF EXTENSION: HIGH
REMARKS: SEE DYNAMIC LIST FOR UPDATES. IMPLEMENTED DUE TO SPECIAL
OPERATIONS. AIRCRAFT LANDING KDCA AND KADW CAN EXPECT PUPPY
WP AT FL280.  AIRCRAFT LANDING KBWI KMTN KGAI AND KESN CAN
EXPECT PUPPY WP AT FL260
ASSOCIATED RESTRICTIONS:
MODIFICATIONS:
ROUTES: [route table not shown]
TMI ID: RRDCC504
```

Every advisory the linker could see for this element in the horizon:

```
20260522-076  sent 05/22 17:24Z  FCA RQD  FCA005:ZBW_CZU_TO_ZDC  VALID 22/1700Z - 22/2200Z  [PROBABILITY OF EXTENSION: HIGH]
```

**Derived outcome: NOT EXTENDED (lapsed) = 0**. no later advisory moved the end past 23/0200Z. Flags: shortened.

No advisory decides the outcome (nothing qualifying was found).

## 55. plan-20260426-112-MSP-gs+gdp-AFTER1600

- Term: **POSSIBLE** (plan:POSSIBLE); written as: `AFTER 1600	-MSP GROUND STOP/DELAY PROGRAM POSSIBLE`
- Element: MSP; initiative: gs/gdp; first issued 04/26 23:40Z in 20260426-112; window read as 27/1600Z - 28/0800Z
- Repeated in: 20260427-007 20260427-020 20260427-037 20260427-051

Source advisory:

```
ATCSCC ADVZY 112 DCC 04/26/2026 OPERATIONS PLAN
EVENT TIME: 27/0000 - AND LATER
TERMINAL ACTIVE:
UNTIL 0015	-DFW GROUND STOP
UNTIL 0015	-DAL GROUND STOP
UNTIL 0659	-SFO GROUND DELAY PROGRAM
TERMINAL PLANNED:
AFTER 0200	-SEA GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1300	-MDW GROUND STOP PROBABLE
AFTER 1300	-ORD GROUND STOP/DELAY PROGRAM PROBABLE
AFTER 1500	-SFO GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1600	-MSP GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 2100	-DEN GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 2200	-SFO GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 2200	-JFK GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 28/0200	-MEM  GROUND STOP POSSIBLE
```

Every advisory the linker could see for this element in the horizon:

```
(none)
```

**Derived outcome: NOT ISSUED = 0**. no gs or gdp advisory for MSP in the window.

No advisory decides the outcome (nothing qualifying was found).

## 56. plan-20260424-007-IAD-gs-AFTER1800

- Term: **POSSIBLE** (plan:POSSIBLE); written as: `AFTER 1800	-DCA/IAD/BWI GROUND STOP POSSIBLE`
- Element: IAD; initiative: gs; first issued 04/24 01:21Z in 20260424-007; window read as 24/1800Z - 25/0800Z
- Repeated in: 20260424-015 20260424-025 20260424-036 20260424-050 20260424-061

Source advisory:

```
ATCSCC ADVZY 007 DCC 04/24/2026 OPERATIONS PLAN
EVENT TIME: 24/0200 - AND LATER
TERMINAL ACTIVE:
UNTIL 0559	-SEA GROUND DELAY PROGRAM
UNTIL 0659	-SFO GROUND DELAY PROGRAM
TERMINAL PLANNED:
AFTER 1500	-SFO GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1800	-DCA/IAD/BWI GROUND STOP POSSIBLE
AFTER 1900	-DTW GROUND STOP POSSIBLE
```

Every advisory the linker could see for this element in the horizon:

```
(none)
```

**Derived outcome: NOT ISSUED = 0**. no gs advisory for IAD in the window.

No advisory decides the outcome (nothing qualifying was found).

## 57. route-20260518-032

- Term: **LOW** (route:LOW); written as: `PROBABILITY OF EXTENSION: LOW`
- Element: FCA002:PNH_1_PARTIAL; initiative: reroute; first issued 05/18 10:45Z in 20260518-032; window read as 18/1330Z - 18/1800Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 032 DCC 05/18/2026 FCA RQD
NAME: FCA002:PNH_1_PARTIAL
CONSTRAINED AREA: ZKC/ZAU
REASON: WEATHER
INCLUDE TRAFFIC: KCLT/KGSO/KORF/KPHL/KRDU/KRIC/ZDC/ZME/ZTL
DEPARTURES TO
KABQ/KBUR/KDEN/KLAS/KLAX/KLGB/KOAK/KPHX/KSAN/KSFO/K
SJC/KSNA/KVNY
FACILITIES INCLUDED: ZAB/ZDC/ZDV/ZFW/ZID/ZLA/ZLC/ZME/ZNY/ZOA/ZTL
FLIGHT STATUS: ALL_FLIGHTS
VALID: FCA ENTRY TIME FROM 181330 TO 181800
PROBABILITY OF EXTENSION: LOW
REMARKS: SEE DYNAMIC LIST FOR UPDATES.
ASSOCIATED RESTRICTIONS:
MODIFICATIONS:
ROUTES: [route table not shown]
TMI ID: RRDCC501
```

Every advisory the linker could see for this element in the horizon:

```
20260518-098  sent 05/18 18:32Z  ROUTE RQD /FL  PNH_1_PARTIAL  VALID 18/1900Z - 18/2300Z  [PROBABILITY OF EXTENSION: MODERATE]
```

**Derived outcome: NOT EXTENDED (lapsed) = 0**. no later advisory moved the end past 18/1800Z.

No advisory decides the outcome (nothing qualifying was found).

## 58. gs-20260506-057

- Term: **LOW** (gs:LOW); written as: `PROBABILITY OF EXTENSION: LOW`
- Element: EWR; initiative: gs; first issued 05/06 16:52Z in 20260506-057; window read as 06/1647Z - 06/1800Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 057 EWR/ZNY 05/06/2026 CDM GROUND STOP
CTL ELEMENT: EWR
ELEMENT TYPE: APT
ADL TIME: 1647Z
GROUND STOP PERIOD: 06/1647Z - 06/1800Z
DEP FACILITIES INCLUDED: (Manual) ZDC ZNY ZOB ZBW
PREVIOUS TOTAL, MAXIMUM, AVERAGE DELAYS: 90 / 46 / 8
NEW TOTAL, MAXIMUM, AVERAGE DELAYS: 627 / 106 / 57
PROBABILITY OF EXTENSION: LOW
IMPACTING CONDITION: OTHER / FLIGHT CHECK
COMMENTS: GROUND STOP CANCELLED FOR ZID, ZTL AND CZY.  1ST TIERS
SHOULD EXPECT TO COME OUT EARLIER THAN 18Z.
```

Every advisory the linker could see for this element in the horizon:

```
20260506-059  sent 05/06 17:30Z  CDM GS CNX  EWR  GS CNX PERIOD 06/1727Z - 06/1940Z
20260506-068  sent 05/06 19:08Z  CDM GROUND STOP  EWR  GROUND STOP PERIOD 06/1852Z - 06/2015Z  [PROBABILITY OF EXTENSION: MEDIUM]
```

**Derived outcome: NOT EXTENDED (cancelled) = 0**. cancelled at 06/1730Z; stated end 06/1800Z.

Advisory that decides the outcome:

```
ATCSCC ADVZY 059 EWR/ZNY 05/06/2026 CDM GS CNX
CTL ELEMENT: EWR
ELEMENT TYPE: APT
ADL TIME: 1727Z
GS CNX PERIOD: 06/1727Z - 06/1940Z
COMMENTS:
```

## 59. gs-20260402-065

- Term: **MEDIUM** (gs:MEDIUM); written as: `PROBABILITY OF EXTENSION: MEDIUM`
- Element: ORD; initiative: gs; first issued 04/02 10:36Z in 20260402-065; window read as 02/1022Z - 02/1115Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 065 ORD/ZAU 04/02/2026 CDM GROUND STOP
CTL ELEMENT: ORD
ELEMENT TYPE: APT
ADL TIME: 1032Z
GROUND STOP PERIOD: 02/1022Z - 02/1115Z
DEP FACILITIES INCLUDED: (Internal) ZAU
PREVIOUS TOTAL, MAXIMUM, AVERAGE DELAYS: 0 / 0 / 0
NEW TOTAL, MAXIMUM, AVERAGE DELAYS: 291 / 49 / 42
PROBABILITY OF EXTENSION: MEDIUM
IMPACTING CONDITION: WEATHER / THUNDERSTORMS
COMMENTS:
```

Every advisory the linker could see for this element in the horizon:

```
20260402-071  sent 04/02 11:14Z  CDM GS CNX  ORD  GS CNX PERIOD 02/1111Z - 02/1150Z
20260402-075  sent 04/02 11:44Z  CDM GROUND STOP  ORD  GROUND STOP PERIOD 02/1131Z - 02/1245Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260402-087  sent 04/02 12:43Z  CDM GROUND STOP  ORD  GROUND STOP PERIOD 02/1131Z - 02/1330Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260402-090  sent 04/02 13:01Z  CDM PROPOSED GROUND DELAY PROGRAM  ORD  ANTICIPATED CUMULATIVE PROGRAM PERIOD 02/1253Z - 03/0259Z
20260402-093  sent 04/02 13:10Z  CDM GROUND DELAY PROGRAM  ORD  CUMULATIVE PROGRAM PERIOD 02/1253Z - 03/0259Z
```

Other advisories that name the element (not read by the linker):

```
20260402-073  sent 04/02 11:41Z  ORD AIRPORT ARRIVAL DELAYS
20260402-084  sent 04/02 12:21Z  ORD AIRPORT DIVERSION RECOVERY ACTIVATED
20260402-089  sent 04/02 12:54Z  CHICAGO HOTLINE_FYI
```

**Derived outcome: NOT EXTENDED (cancelled) = 0**. cancelled at 02/1114Z; stated end 02/1115Z. Flags: new_stop_30.

Advisory that decides the outcome:

```
ATCSCC ADVZY 071 ORD/ZAU 04/02/2026 CDM GS CNX
CTL ELEMENT: ORD
ELEMENT TYPE: APT
ADL TIME: 1111Z
GS CNX PERIOD: 02/1111Z - 02/1150Z
FLIGHTS MAY RECEIVE NEW EDCTS DUE TO AN ACTIVE AFP
COMMENTS:
```

## 60. plan-20260429-092-LGA-gs+gdp-UNTIL0300

- Term: **PROBABLE** (plan:PROBABLE); written as: `UNTIL 0300 	-LGA/JFK/HPN GROUND STOP/DELAY PROGRAM PROBABLE`
- Element: LGA; initiative: gs/gdp; first issued 04/29 17:40Z in 20260429-092; window read as 29/1740Z - 30/0300Z
- Repeated in: 20260429-107 20260429-121

Source advisory:

```
ATCSCC ADVZY 092 DCC 04/29/2026 OPERATIONS PLAN
EVENT TIME: 29/1800 - AND LATER
TERMINAL ACTIVE:
UNTIL 2029	-SFO GROUND DELAY PROGRAM
UNTIL 0359	-BOS GROUND DELAY PROGRAM
UNTIL 0359	-DCA GROUND DELAY PROGRAM
TERMINAL PLANNED:
UNTIL 0000 	-IAD/BWI GROUND STOP POSSIBLE
UNTIL 0000 	-IAH/HOU GROUND STOP/DELAY PROGRAM PROBABLE
UNTIL 0200 	-EWR/TEB/PHL GROUND STOP/DELAY PROGRAM POSSIBLE
UNTIL 0300 	-LGA/JFK/HPN GROUND STOP/DELAY PROGRAM PROBABLE
```

Every advisory the linker could see for this element in the horizon:

```
(none)
```

**Derived outcome: NOT ISSUED = 0**. no gs or gdp advisory for LGA in the window. Flags: term_changed.

No advisory decides the outcome (nothing qualifying was found).

## 61. route-20260414-009

- Term: **NONE** (route:NONE); written as: `PROBABILITY OF EXTENSION: NONE`
- Element: FCA008:NO_AR_ATLANTIC_Y-RTES_TO_MCO_TPA_RSW_AREAS; initiative: reroute; first issued 04/14 01:31Z in 20260414-009; window read as 14/0528Z - 14/1055Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 009 DCC 04/14/2026 FCA RQD
NAME: FCA008:NO_AR_ATLANTIC_Y-RTES_TO_MCO_TPA_RSW_AREAS
CONSTRAINED AREA: ZJX/ZMA
REASON: OTHER
INCLUDE TRAFFIC: UNKN DEPARTURES TO
KAPF/KFMY/KISM/KLAL/KMCF/KMCO/KMKY/KORL/KPGD/KPIE/K
RSW/KSFB/KSPG/KSRQ/KTPA/KTPF
FACILITIES INCLUDED: ZJX/ZMA/ZDC/ZNY/ZBW
FLIGHT STATUS: ALL_FLIGHTS
VALID: FCA ENTRY TIME FROM 140528 TO 141055
PROBABILITY OF EXTENSION: NONE
REMARKS: SEE DYNAMIC LIST FOR UPDATES. IMPLEMENTED DUE TO ROCKET
LAUNCH ACTIVITIES.
ASSOCIATED RESTRICTIONS:
MODIFICATIONS:
ROUTES: [route table not shown]
TMI ID: RRDCC009
```

Every advisory the linker could see for this element in the horizon:

```
20260414-037  sent 04/14 09:07Z  FCA RQD  FCA008:NO_AR_ATLANTIC_Y-RTES_TO_MCO_TPA_RSW_AREAS  VALID 14/0528Z - 14/1016Z  [PROBABILITY OF EXTENSION: NONE]
20260414-042  sent 04/14 09:40Z  REROUTE CANCELLATION  FCA008:NO_AR_ATLANTIC_Y-RTES_TO_MCO_TPA_RSW_AREAS
```

**Derived outcome: NOT EXTENDED (cancelled) = 0**. cancelled at 14/0940Z; stated end 14/1055Z. Flags: shortened.

Advisory that decides the outcome:

```
ATCSCC ADVZY 042 DCC 04/14/2026 REROUTE CANCELLATION
FCA008:NO_AR_ATLANTIC_Y-RTES_TO_MCO_TPA_RSW_AREAS HAS BEEN CANCELLED.

REMARKS:
ASSOCIATED RESTRICTIONS:
```

## 62. gs-20260402-172

- Term: **HIGH** (gs:HIGH); written as: `PROBABILITY OF EXTENSION: HIGH`
- Element: ORD; initiative: gs; first issued 04/02 23:41Z in 20260402-172; window read as 02/2330Z - 03/0030Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 172 ORD/ZAU 04/02/2026 CDM GROUND STOP
CTL ELEMENT: ORD
ELEMENT TYPE: APT
ADL TIME: 2335Z
GROUND STOP PERIOD: 02/2330Z - 03/0030Z
CUMULATIVE PROGRAM PERIOD: 02/1253Z - 03/0759Z
DEP FACILITIES INCLUDED: (Manual) ZAU ZDV ZKC ZMP ZID  CYHZ CYOW CYUL
CYYZ
PREVIOUS TOTAL, MAXIMUM, AVERAGE DELAYS: 4820 / 449 / 201
NEW TOTAL, MAXIMUM, AVERAGE DELAYS: 6581 / 481 / 274
PROBABILITY OF EXTENSION: HIGH
IMPACTING CONDITION: WEATHER / THUNDERSTORMS
COMMENTS: MODIFIED 1ST TIER STOP DUE TO TSTM ROUTE IMPACTS. STOP
EXPECTED TO EXPAND IN SCOPE AS TSTMS APPROACH FIELD.
```

Every advisory the linker could see for this element in the horizon:

```
20260403-004  sent 04/03 00:21Z  CDM GROUND STOP  ORD  GROUND STOP PERIOD 02/2330Z - 03/0130Z  [PROBABILITY OF EXTENSION: HIGH]
20260403-013  sent 04/03 01:26Z  CDM GROUND STOP  ORD  GROUND STOP PERIOD 03/0111Z - 03/0230Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260403-019  sent 04/03 02:15Z  CDM GROUND STOP  ORD  GROUND STOP PERIOD 03/0201Z - 03/0315Z  [PROBABILITY OF EXTENSION: MEDIUM]
```

**Derived outcome: EXTENDED = 1**. end 03/0030Z -> 03/0130Z (+60 min).

Advisory that decides the outcome:

```
ATCSCC ADVZY 004 ORD/ZAU 04/03/2026 CDM GROUND STOP
CTL ELEMENT: ORD
ELEMENT TYPE: APT
ADL TIME: 0016Z
GROUND STOP PERIOD: 02/2330Z - 03/0130Z
CUMULATIVE PROGRAM PERIOD: 02/1253Z - 03/0759Z
DEP FACILITIES INCLUDED: (Manual) ZAU ZTL ZDC ZNY ZOB ZDV ZBW ZKC ZID
ZMP  CYHZ CYOW CYUL CYYZ
PREVIOUS TOTAL, MAXIMUM, AVERAGE DELAYS: 11596 / 507 / 203
NEW TOTAL, MAXIMUM, AVERAGE DELAYS: 14506 / 541 / 254
PROBABILITY OF EXTENSION: HIGH
IMPACTING CONDITION: WEATHER / THUNDERSTORMS
COMMENTS: EXTENDED TO ADD A MODIFIED 2ND TIER. WILL REMAIN DYNAMIC.
```

## 63. route-20260516-036

- Term: **LOW** (route:LOW); written as: `PROBABILITY OF EXTENSION: LOW`
- Element: NYSATS_TO_FL; initiative: reroute; first issued 05/16 13:09Z in 20260516-036; window read as 16/1315Z - 16/1715Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 036 DCC 05/16/2026 ROUTE RQD /FL
NAME: NYSATS_TO_FL
CONSTRAINED AREA: ZNY
REASON: VOLUME
INCLUDE TRAFFIC: KCDW/KHPN/KMMU/KTEB DEPARTURES TO
KAPF/KBCT/KFLL/KFMY/KFXE/KMCO/KMIA/KMKY/KOPF/KPBI/K
PIE/KRSW/KSRQ/KTPA
FACILITIES INCLUDED: ZDC/ZID/ZJX/ZMA/ZNY/ZTL
FLIGHT STATUS: ALL_FLIGHTS
VALID: ETD 161315 TO 161715
PROBABILITY OF EXTENSION: LOW
REMARKS:
ASSOCIATED RESTRICTIONS:
MODIFICATIONS:
ROUTES: [route table not shown]
TMI ID: RRDCC510
```

Every advisory the linker could see for this element in the horizon:

```
(none)
```

**Derived outcome: NOT EXTENDED (lapsed) = 0**. no later advisory moved the end past 16/1715Z.

No advisory decides the outcome (nothing qualifying was found).

## 64. gs-20260507-067

- Term: **MEDIUM** (gs:MEDIUM); written as: `PROBABILITY OF EXTENSION: MEDIUM`
- Element: TEB; initiative: gs; first issued 05/07 19:08Z in 20260507-067; window read as 07/1854Z - 07/2015Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 067 TEB/ZNY 05/07/2026 CDM GROUND STOP
CTL ELEMENT: TEB
ELEMENT TYPE: APT
ADL TIME: 1904Z
GROUND STOP PERIOD: 07/1854Z - 07/2015Z
DEP FACILITIES INCLUDED: (Internal) ZNY
PREVIOUS TOTAL, MAXIMUM, AVERAGE DELAYS: 0 / 0 / 0
NEW TOTAL, MAXIMUM, AVERAGE DELAYS: 266 / 59 / 44
PROBABILITY OF EXTENSION: MEDIUM
IMPACTING CONDITION: VOLUME / VOLUME
COMMENTS: INTERNAL TO ZNY ONLY
```

Every advisory the linker could see for this element in the horizon:

```
20260507-074  sent 05/07 20:08Z  CDM GS CNX  TEB  GS CNX PERIOD 07/2008Z - 07/2042Z
```

Other advisories that name the element (not read by the linker):

```
20260507-075  sent 05/07 20:11Z  TEB AIRPORT ARRIVAL DELAYS
```

**Derived outcome: NOT EXTENDED (cancelled) = 0**. cancelled at 07/2008Z; stated end 07/2015Z.

Advisory that decides the outcome:

```
ATCSCC ADVZY 074 TEB/ZNY 05/07/2026 CDM GS CNX
CTL ELEMENT: TEB
ELEMENT TYPE: APT
ADL TIME: 2008Z
GS CNX PERIOD: 07/2008Z - 07/2042Z
COMMENTS:
```

## 65. plan-20260531-070-PBI-gs-AFTER1700

- Term: **POSSIBLE** (plan:POSSIBLE); written as: `AFTER 1700	-MIA/FLL/PBI GROUND STOP POSSIBLE`
- Element: PBI; initiative: gs; first issued 05/31 23:23Z in 20260531-070; window read as 01/1700Z - 02/0800Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 070 DCC 05/31/2026 OPERATIONS PLAN
EVENT TIME: 01/0000 - AND LATER
TERMINAL ACTIVE:
UNTIL 0030	-JFK GROUND STOP
UNTIL 0559	-SFO GROUND DELAY PROGRAM
TERMINAL PLANNED:
AFTER 1400	-SFO GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1700	-MIA/FLL/PBI GROUND STOP POSSIBLE
AFTER 1800	-ATL GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1900	-CLT GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 2100	-MCO/TPA GROUND STOP POSSIBLE
AFTER 2100	-DEN GROUND STOP/DELAY PROGRAM POSSIBLE
```

Every advisory the linker could see for this element in the horizon:

```
(none)
```

Other advisories that name the element (not read by the linker):

```
20260531-045  sent 05/31 17:24Z  MIA / OPF / TMB / FLL / FXE / PBI / RSW / BCT / TPA / SRQ CDRS_FYI
```

**Derived outcome: EXCLUDED (unresolved_boundary)**. window ends 02/0800Z, after the loaded months.

No advisory decides the outcome (nothing qualifying was found).

## 66. gs-20260531-072

- Term: **LOW** (gs:LOW); written as: `PROBABILITY OF EXTENSION: LOW`
- Element: DEN; initiative: gs; first issued 05/31 23:48Z in 20260531-072; window read as 31/2334Z - 01/0045Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 072 DEN/ZDV 05/31/2026 CDM GROUND STOP
CTL ELEMENT: DEN
ELEMENT TYPE: APT
ADL TIME: 2344Z
GROUND STOP PERIOD: 31/2334Z - 01/0045Z
DEP FACILITIES INCLUDED: (Internal) ZDV
PREVIOUS TOTAL, MAXIMUM, AVERAGE DELAYS: 0 / 0 / 0
NEW TOTAL, MAXIMUM, AVERAGE DELAYS: 202 / 63 / 22
PROBABILITY OF EXTENSION: LOW
IMPACTING CONDITION: WEATHER / WIND
COMMENTS: WINDSHEAR AT THE FIELD, USERS CAN EXPECT HOLDING FOR ABOUT
30 MIN
```

Every advisory the linker could see for this element in the horizon:

```
(none)
```

**Derived outcome: EXCLUDED (unresolved_boundary)**. end 01/0045Z is at the edge of the loaded months.

No advisory decides the outcome (nothing qualifying was found).

## 67. plan-20260402-174-DEN-gs+gdp-AFTER1200

- Term: **PROBABLE** (plan:PROBABLE); written as: `AFTER 1200	-DEN GROUND STOP/DELAY PROGRAM PROBABLE`
- Element: DEN; initiative: gs/gdp; first issued 04/02 23:54Z in 20260402-174; window read as 03/1200Z - 04/0800Z
- Repeated in: 20260403-042

Source advisory:

```
ATCSCC ADVZY 174 DCC 04/02/2026 OPERATIONS PLAN
EVENT TIME: 03/0000 - AND LATER
TERMINAL ACTIVE:
UNTIL 0030 	-ORD GROUND STOP
UNTIL 0559	-SFO GROUND DELAY PROGRAM
UNTIL 0759 	-ORD GROUND DELAY PROGRAM
TERMINAL PLANNED:
UNTIL 0100	-MCO/TPA GROUND STOP POSSIBLE
UNTIL 0200 	-MDW GROUND STOP POSSIBLE
AFTER 1100	-LGA GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1200	-DEN GROUND STOP/DELAY PROGRAM PROBABLE
AFTER 1500	-SFO GROUND STOP/DELAY PROGRAM PROBABLE
AFTER 1800	-BOS GROUND STOP/DELAY PROGRAM POSSIBLE
```

Every advisory the linker could see for this element in the horizon:

```
20260403-057  sent 04/03 12:38Z  CDM GROUND STOP  DEN  GROUND STOP PERIOD 03/1224Z - 03/1345Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260403-060  sent 04/03 13:09Z  CDM GS CNX  DEN  GS CNX PERIOD 03/1307Z - 03/1754Z
20260403-070  sent 04/03 14:07Z  CDM GROUND STOP  DEN  GROUND STOP PERIOD 03/1352Z - 03/1500Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260403-073  sent 04/03 14:59Z  CDM GS CNX  DEN  GS CNX PERIOD 03/1457Z - 03/1903Z
```

Other advisories that name the element (not read by the linker):

```
20260403-054  sent 04/03 11:59Z  DEN AIRPORT ARRIVAL DELAYS
20260403-055  sent 04/03 11:59Z  DEN AIRPORT SCHEDULING DELAYS
```

**Derived outcome: ISSUED = 1**. CDM GROUND STOP sent 03/1238Z, period 03/1224Z - 03/1309Z.

Advisory that decides the outcome:

```
ATCSCC ADVZY 057 DEN/ZDV 04/03/2026 CDM GROUND STOP
CTL ELEMENT: DEN
ELEMENT TYPE: APT
ADL TIME: 1234Z
GROUND STOP PERIOD: 03/1224Z - 03/1345Z
DEP FACILITIES INCLUDED: (2ndTier) ZLA ZAU ZLC ZHU ZFW ZOB ZDV ZOA
ZSE ZKC ZME ZID ZAB ZMP
PREVIOUS TOTAL, MAXIMUM, AVERAGE DELAYS: 0 / 0 / 0
NEW TOTAL, MAXIMUM, AVERAGE DELAYS: 2807 / 77 / 35
PROBABILITY OF EXTENSION: MEDIUM
IMPACTING CONDITION: WEATHER / WIND
COMMENTS:
```

## 68. route-20260527-028

- Term: **MODERATE** (route:MODERATE); written as: `PROBABILITY OF EXTENSION: MODERATE`
- Element: NORTH_TO_IAH_HOU; initiative: reroute; first issued 05/27 10:12Z in 20260527-028; window read as 27/1015Z - 27/1415Z
- Repeated in: 20260527-030

Source advisory:

```
ATCSCC ADVZY 028 DCC 05/27/2026 ROUTE RQD /FL
NAME: NORTH_TO_IAH_HOU
CONSTRAINED AREA: ZHU/ZFW
REASON: WEATHER
INCLUDE TRAFFIC: CZY/KBWI/KCLE/KDCA/KDTW/KIAD/KJFK/KMDW/KORD/KPHL/KP
IT/ZAU/ZBW/ZFW/ZID/ZKC/ZME/ZMP/ZNY DEPARTURES TO
KHOU/KIAH
FACILITIES INCLUDED: CZY/ZAU/ZBW/ZDC/ZFW/ZHU/ZID/ZKC/ZME/ZMP/ZNY/ZOB
FLIGHT STATUS: ALL_FLIGHTS
VALID: ETD 271015 TO 271415
PROBABILITY OF EXTENSION: MODERATE
REMARKS:
ASSOCIATED RESTRICTIONS:
MODIFICATIONS:
ROUTES: [route table not shown]
TMI ID: RRDCC502
```

Every advisory the linker could see for this element in the horizon:

```
20260527-030  sent 05/27 10:33Z  ROUTE RQD /FL  NORTH_TO_IAH_HOU  VALID 27/1015Z - 27/1415Z  [PROBABILITY OF EXTENSION: MODERATE]
```

**Derived outcome: NOT EXTENDED (lapsed) = 0**. no later advisory moved the end past 27/1415Z.

No advisory decides the outcome (nothing qualifying was found).

## 69. route-20260401-085

- Term: **LOW** (route:LOW); written as: `PROBABILITY OF EXTENSION: LOW`
- Element: FCA025:OBK_PARTIAL; initiative: reroute; first issued 04/01 19:00Z in 20260401-085; window read as 01/2100Z - 02/0300Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 085 DCC 04/01/2026 FCA RQD
NAME: FCA025:OBK_PARTIAL
CONSTRAINED AREA: EAST COAST
REASON: WEATHER
INCLUDE TRAFFIC: ZDV/ZLA/ZLC/ZMP/ZOA/ZSE DEPARTURES TO KBOS/KJFK
FACILITIES INCLUDED: CZY/ZAU/ZBW/ZDV/ZLA/ZLC/ZMP/ZNY/ZOA/ZOB/ZSE
FLIGHT STATUS: ALL_FLIGHTS
VALID: FCA ENTRY TIME FROM 012100 TO 020300
PROBABILITY OF EXTENSION: LOW
REMARKS: SEE DYNAMIC LIST FOR UPDATES.
ASSOCIATED RESTRICTIONS:
MODIFICATIONS:
ROUTES: [route table not shown]
TMI ID: RRDCC520
```

Every advisory the linker could see for this element in the horizon:

```
(none)
```

**Derived outcome: NOT EXTENDED (lapsed) = 0**. no later advisory moved the end past 02/0300Z.

No advisory decides the outcome (nothing qualifying was found).

## 70. route-20260501-079

- Term: **HIGH** (route:HIGH); written as: `PROBABILITY OF EXTENSION: HIGH`
- Element: FCA011:GA_LIGHT_JETS_TO_MIA_AND_SATS; initiative: reroute; first issued 05/01 17:03Z in 20260501-079; window read as 01/2115Z - 02/0200Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 079 DCC 05/01/2026 FCA RQD
NAME: FCA011:GA_LIGHT_JETS_TO_MIA_AND_SATS
CONSTRAINED AREA: ZJX/ZMA
REASON: OTHER
INCLUDE TRAFFIC: CZU/CZY/KCDW/KCLT/KDET/KDTW/KFNT/KJFK/KLAN/KMBS/KMM
U/KPHL/KPTK/KTEB/KYIP/ZAU/ZBW/ZDC/ZID/ZMP/ZNY/ZOB/Z
TL DEPARTURES TO 07FA/KHST/KMIA/KTMB/X51
FACILITIES INCLUDED: CZU/CZY/ZAU/ZBW/ZDC/ZID/ZJX/ZKC/ZMA/ZME/ZMP/ZNY
/ZOB/ZTL
FLIGHT STATUS: ALL_FLIGHTS
VALID: FCA ENTRY TIME FROM 012115 TO 020200
PROBABILITY OF EXTENSION: HIGH
REMARKS: SEE DYNAMIC LIST FOR UPDATES. THIS IS FOR GA VERY LIGHT
JETS ONLY.  THIS ROUTE IS ISSUED DUE TO SPECIAL OPERATIONS.
ASSOCIATED RESTRICTIONS:
MODIFICATIONS:
ROUTES: [route table not shown]
TMI ID: RRDCC514
```

Every advisory the linker could see for this element in the horizon:

```
20260502-006  sent 05/02 00:05Z  FCA RQD  FCA027:GA_LIGHT_JETS_TO_MIA_AND_SATS  VALID 02/0200Z - 02/2315Z  [PROBABILITY OF EXTENSION: MODERATE]
```

**Derived outcome: EXTENDED = 1**. end 02/0200Z -> 02/2315Z (+1275 min), carried on as FCA027:GA_LIGHT_JETS_TO_MIA_AND_SATS under TMI ID RRDCC526. Flags: continued_new_id.

Advisory that decides the outcome:

```
ATCSCC ADVZY 006 DCC 05/02/2026 FCA RQD
NAME: FCA027:GA_LIGHT_JETS_TO_MIA_AND_SATS
CONSTRAINED AREA: ZJX/ZMA
REASON: OTHER
INCLUDE TRAFFIC: CZU/CZY/KCDW/KCLT/KDET/KDTW/KFNT/KJFK/KLAN/KMBS/KMM
U/KPHL/KPTK/KTEB/KYIP/ZAU/ZBW/ZDC/ZID/ZMP/ZNY/ZOB/Z
TL DEPARTURES TO 07FA/KHST/KMIA/KTMB/X51
FACILITIES INCLUDED: CZU/CZY/ZAU/ZBW/ZDC/ZID/ZJX/ZKC/ZMA/ZME/ZMP/ZNY
/ZOB/ZTL
FLIGHT STATUS: ALL_FLIGHTS
VALID: FCA ENTRY TIME FROM 020200 TO 022315
PROBABILITY OF EXTENSION: MODERATE
REMARKS: SEE DYNAMIC LIST FOR UPDATES. IMPLEMENTED DUE TO SPECIAL
OPERATIONS. THIS ROUTE IS FOR GA VERY LIGHT JETS ONLY.
ASSOCIATED RESTRICTIONS:
MODIFICATIONS:
ROUTES: [route table not shown]
TMI ID: RRDCC526
```

## 71. route-20260429-028

- Term: **LOW** (route:LOW); written as: `PROBABILITY OF EXTENSION: LOW`
- Element: FCA018:NO_AR_Y-RTES_TO_RSW_VRB_SUA_FPR_AREA; initiative: reroute; first issued 04/29 08:31Z in 20260429-028; window read as 29/1300Z - 30/0030Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 028 DCC 04/29/2026 FCA RQD
NAME: FCA018:NO_AR_Y-RTES_TO_RSW_VRB_SUA_FPR_AREA
CONSTRAINED AREA: ZJX ZMA
REASON: OTHER
INCLUDE TRAFFIC: UNKN DEPARTURES TO APF/FMY/FPR/MKY/PGD/RSW/SUA/VRB
FACILITIES INCLUDED: ZMA
FLIGHT STATUS: ALL_FLIGHTS
VALID: FCA ENTRY TIME FROM 291300 TO 300030
PROBABILITY OF EXTENSION: LOW
REMARKS: SEE DYNAMIC LIST FOR UPDATES. AR/Y ROUTES, AND FIX-TO-FIX
OVER WATER SOUTH OF ILM/DIW AREA ARE UNAVAILABLE TO THE RSW
FMY APF MKY VRB SUA FPR PGD AREAS. DUE TO SUA ACTIVITY.
ASSOCIATED RESTRICTIONS:
MODIFICATIONS:
ROUTES: [route table not shown]
TMI ID: RRDCC028
```

Every advisory the linker could see for this element in the horizon:

```
20260429-046  sent 04/29 11:47Z  REROUTE CANCELLATION  FCA018:NO_AR_Y-RTES_TO_RSW_VRB_SUA_FPR_AREA
```

**Derived outcome: NOT EXTENDED (cancelled) = 0**. cancelled at 29/1147Z; stated end 30/0030Z.

Advisory that decides the outcome:

```
ATCSCC ADVZY 046 DCC 04/29/2026 REROUTE CANCELLATION
FCA018:NO_AR_Y-RTES_TO_RSW_VRB_SUA_FPR_AREA HAS BEEN CANCELLED.

REMARKS:
ASSOCIATED RESTRICTIONS:
```

## 72. route-20260430-034

- Term: **MODERATE** (route:MODERATE); written as: `PROBABILITY OF EXTENSION: MODERATE`
- Element: NE_TO_FLORIDA_VIA_Q75_2_PARTIAL; initiative: reroute; first issued 04/30 12:17Z in 20260430-034; window read as 30/1220Z - 30/1430Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 034 DCC 04/30/2026 ROUTE RQD /FL
NAME: NE_TO_FLORIDA_VIA_Q75_2_PARTIAL
CONSTRAINED AREA: ZJX
REASON: VOLUME
INCLUDE TRAFFIC: KBWI/KCDW/KDCA/KIAD/KJFK/KMMU/KPHL/KTEB/ZBW/ZNY
DEPARTURES TO KBCT/KMCO/KPBI
FACILITIES INCLUDED: ZBW/ZDC/ZJX/ZMA/ZNY/ZTL
FLIGHT STATUS: ALL_FLIGHTS
VALID: ETD 301220 TO 301430
PROBABILITY OF EXTENSION: MODERATE
REMARKS: FLIGHTS FILED DOWN THE AR'S ARE EXEMPT.
ASSOCIATED RESTRICTIONS:
MODIFICATIONS:
ROUTES: [route table not shown]
TMI ID: RRDCC506
```

Every advisory the linker could see for this element in the horizon:

```
20260430-045  sent 04/30 13:36Z  ROUTE RQD /FL  NE_TO_FLORIDA_VIA_Q75_2_PARTIAL  VALID 30/1220Z - 30/1630Z  [PROBABILITY OF EXTENSION: MODERATE]
20260430-061  sent 04/30 14:57Z  REROUTE CANCELLATION  NE_TO_FLORIDA_VIA_Q75_2_PARTIAL
```

**Derived outcome: EXTENDED = 1**. end 30/1430Z -> 30/1630Z (+120 min).

Advisory that decides the outcome:

```
ATCSCC ADVZY 045 DCC 04/30/2026 ROUTE RQD /FL
NAME: NE_TO_FLORIDA_VIA_Q75_2_PARTIAL
CONSTRAINED AREA: ZJX
REASON: VOLUME
INCLUDE TRAFFIC: KBWI/KCDW/KDCA/KIAD/KJFK/KMMU/KPHL/KTEB/ZBW/ZNY
DEPARTURES TO KBCT/KMCO/KPBI
FACILITIES INCLUDED: ZBW/ZDC/ZJX/ZMA/ZNY/ZTL
FLIGHT STATUS: ALL_FLIGHTS
VALID: ETD 301220 TO 301630
PROBABILITY OF EXTENSION: MODERATE
REMARKS: REPLACES ADVZY 034.
AR'S ARE EXEMPT WHEN AVAILABLE
ASSOCIATED RESTRICTIONS:
MODIFICATIONS:
ROUTES: [route table not shown]
TMI ID: RRDCC506
```

## 73. route-20260501-059

- Term: **LOW** (route:LOW); written as: `PROBABILITY OF EXTENSION: LOW`
- Element: FCA021:MISS_VALLEY_TO_IAH_HOU; initiative: reroute; first issued 05/01 15:09Z in 20260501-059; window read as 01/1330Z - 01/1900Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 059 DCC 05/01/2026 FCA RQD
NAME: FCA021:MISS_VALLEY_TO_IAH_HOU
CONSTRAINED AREA: ZHU
REASON: WEATHER
INCLUDE TRAFFIC: KCLE/KCRW/KDTW/KLEX/KSDF/ZAU/ZID/ZKC/ZME/ZMP/ZOB
DEPARTURES TO KHOU/KIAH
FACILITIES INCLUDED: ZAU/ZFW/ZHU/ZID/ZKC/ZME/ZMP/ZOB
FLIGHT STATUS: ALL_FLIGHTS
VALID: FCA ENTRY TIME FROM 011330 TO 011900
PROBABILITY OF EXTENSION: LOW
REMARKS: REPLACES ADVZY052, EXTENDS TIME. SEE DYNAMIC LIST FOR
UPDATES. BASED ON IAH_DOOBI_NORTH
ASSOCIATED RESTRICTIONS:
MODIFICATIONS:
ROUTES: [route table not shown]
TMI ID: RRDCC520
```

Every advisory the linker could see for this element in the horizon:

```
20260501-087  sent 05/01 18:14Z  FCA RQD  FCA021:MISS_VALLEY_TO_IAH_HOU  VALID 01/1330Z - 01/2100Z  [PROBABILITY OF EXTENSION: LOW]
```

**Derived outcome: EXTENDED = 1**. end 01/1900Z -> 01/2100Z (+120 min).

Advisory that decides the outcome:

```
ATCSCC ADVZY 087 DCC 05/01/2026 FCA RQD
NAME: FCA021:MISS_VALLEY_TO_IAH_HOU
CONSTRAINED AREA: ZHU
REASON: WEATHER
INCLUDE TRAFFIC: KCLE/KCRW/KDTW/KLEX/KSDF/ZAU/ZID/ZKC/ZME/ZMP/ZOB
DEPARTURES TO KHOU/KIAH
FACILITIES INCLUDED: ZAU/ZFW/ZHU/ZID/ZKC/ZME/ZMP/ZOB
FLIGHT STATUS: ALL_FLIGHTS
VALID: FCA ENTRY TIME FROM 011330 TO 012100
PROBABILITY OF EXTENSION: LOW
REMARKS: REPLACES ADVZY 059. SEE DYNAMIC LIST FOR UPDATES. BASED ON
IAH_DOOBI_NORTH
ASSOCIATED RESTRICTIONS:
MODIFICATIONS: TIME EXTENDED
ROUTES: [route table not shown]
TMI ID: RRDCC520
```

## 74. route-20260512-047

- Term: **NONE** (route:NONE); written as: `PROBABILITY OF EXTENSION: NONE`
- Element: FCA008:CAPE_LAUNCH_2A_PARTIAL; initiative: reroute; first issued 05/12 18:26Z in 20260512-047; window read as 12/2306Z - 12/2356Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 047 DCC 05/12/2026 FCA RQD
NAME: FCA008:CAPE_LAUNCH_2A_PARTIAL
CONSTRAINED AREA: ZJX/ZMA
REASON: OTHER
INCLUDE TRAFFIC: CZY/KATL/KBWI/KCDW/KCLT/KDCA/KDET/KDTW/KFNT/KIAD/KJ
FK/KLAN/KMBS/KMMU/KPHL/KPTK/KTEB/KYIP/ZAU/ZBW/ZID/Z
NY/ZOB DEPARTURES TO KFLL/KFXE/KOPF
FACILITIES INCLUDED: CZY/ZAU/ZBW/ZDC/ZID/ZJX/ZMA/ZME/ZNY/ZOB/ZTL
FLIGHT STATUS: ALL_FLIGHTS
VALID: FCA ENTRY TIME FROM 122306 TO 122356
PROBABILITY OF EXTENSION: NONE
REMARKS: SEE DYNAMIC LIST FOR UPDATES. IMPLEMENTED DUE TO ROCKET
LAUNCH.
ASSOCIATED RESTRICTIONS:
MODIFICATIONS:
ROUTES: [route table not shown]
TMI ID: RRDCC504
```

Every advisory the linker could see for this element in the horizon:

```
20260512-057  sent 05/12 20:20Z  REROUTE CANCELLATION  FCA008:CAPE_LAUNCH_2A_PARTIAL
```

**Derived outcome: NOT EXTENDED (cancelled) = 0**. cancelled at 12/2020Z; stated end 12/2356Z.

Advisory that decides the outcome:

```
ATCSCC ADVZY 057 DCC 05/12/2026 REROUTE CANCELLATION
FCA008:CAPE_LAUNCH_2A_PARTIAL HAS BEEN CANCELLED.

REMARKS:
ASSOCIATED RESTRICTIONS:
```

## 75. gs-20260519-153

- Term: **MEDIUM** (gs:MEDIUM); written as: `PROBABILITY OF EXTENSION: MEDIUM`
- Element: DFW; initiative: gs; first issued 05/19 23:00Z in 20260519-153; window read as 19/2245Z - 20/0000Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 153 DFW/ZFW 05/19/2026 CDM GROUND STOP
CTL ELEMENT: DFW
ELEMENT TYPE: APT
ADL TIME: 2255Z
GROUND STOP PERIOD: 19/2245Z - 20/0000Z
CUMULATIVE PROGRAM PERIOD: 19/2100Z - 20/0359Z
FLT INCL: CARRIER AAL ONLY
DEP FACILITIES INCLUDED:  ALL
PREVIOUS TOTAL, MAXIMUM, AVERAGE DELAYS: 6415 / 607 / 99
NEW TOTAL, MAXIMUM, AVERAGE DELAYS: 8252 / 587 / 127
PROBABILITY OF EXTENSION: MEDIUM
IMPACTING CONDITION: OTHER / OTHER
COMMENTS: AAL AND AAL SUBS ONLY. CARRIER REQUEST
```

Every advisory the linker could see for this element in the horizon:

```
20260519-163  sent 05/19 23:39Z  DFW GROUND STOP CANCELLATION (AAL AND AAL SUBS)  DFW
20260520-006  sent 05/20 00:21Z  CDM GROUND STOP  DFW  GROUND STOP PERIOD 20/0000Z - 20/0115Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260520-019  sent 05/20 01:10Z  CDM GROUND DELAY PROGRAM CNX  DFW  GDP CNX PERIOD 20/0106Z - 20/1814Z
```

**Derived outcome: EXTENDED = 1**. end 20/0000Z -> 20/0115Z (+75 min). Flags: manual_release.

Advisory that decides the outcome:

```
ATCSCC ADVZY 006 DFW/ZFW 05/20/2026 CDM GROUND STOP
CTL ELEMENT: DFW
ELEMENT TYPE: APT
ADL TIME: 0019Z
GROUND STOP PERIOD: 20/0000Z - 20/0115Z
CUMULATIVE PROGRAM PERIOD: 19/2100Z - 20/0359Z
DEP FACILITIES INCLUDED: (1stTier) ZHU ZFW ZKC ZME ZAB
PREVIOUS TOTAL, MAXIMUM, AVERAGE DELAYS: 11735 / 587 / 170
NEW TOTAL, MAXIMUM, AVERAGE DELAYS: 15134 / 662 / 219
PROBABILITY OF EXTENSION: MEDIUM
IMPACTING CONDITION: RWY-TAXI / CONSTRUCTION
COMMENTS:
```

## 76. route-20260515-024

- Term: **NONE** (route:NONE); written as: `PROBABILITY OF EXTENSION: NONE`
- Element: FCA002:ZHU_ZFW_ZME_TO_NY_SATS; initiative: reroute; first issued 05/15 11:50Z in 20260515-024; window read as 15/1100Z - 15/2030Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 024 DCC 05/15/2026 FCA RQD
NAME: FCA002:ZHU_ZFW_ZME_TO_NY_SATS
CONSTRAINED AREA: ZDC
REASON: OTHER
INCLUDE TRAFFIC: KBNA/ZFW/ZHU/ZME DEPARTURES TO KMMU/KTEB
FACILITIES INCLUDED: ZDC/ZFW/ZHU/ZME/ZNY/ZTL
FLIGHT STATUS: ALL_FLIGHTS
VALID: FCA ENTRY TIME FROM 151100 TO 152030
PROBABILITY OF EXTENSION: NONE
REMARKS: SEE DYNAMIC LIST FOR UPDATES.
ASSOCIATED RESTRICTIONS:
MODIFICATIONS:
ROUTES: [route table not shown]
TMI ID: RRDCC502
```

Every advisory the linker could see for this element in the horizon:

```
20260515-061  sent 05/15 18:49Z  REROUTE CANCELLATION  FCA002:ZHU_ZFW_ZME_TO_NY_SATS
```

**Derived outcome: NOT EXTENDED (cancelled) = 0**. cancelled at 15/1849Z; stated end 15/2030Z.

Advisory that decides the outcome:

```
ATCSCC ADVZY 061 DCC 05/15/2026 REROUTE CANCELLATION
FCA002:ZHU_ZFW_ZME_TO_NY_SATS HAS BEEN CANCELLED.

REMARKS: CANCELS ADVZY 024
ASSOCIATED RESTRICTIONS:
```

## 77. route-20260424-042

- Term: **LOW** (route:LOW); written as: `PROBABILITY OF EXTENSION: LOW`
- Element: NYSATS_TO_FL; initiative: reroute; first issued 04/24 14:21Z in 20260424-042; window read as 24/1400Z - 24/1800Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 042 DCC 04/24/2026 ROUTE RQD
NAME: NYSATS_TO_FL
CONSTRAINED AREA: ZNY
REASON: VOLUME
INCLUDE TRAFFIC: KCDW/KHPN/KMMU/KTEB DEPARTURES TO
KAPF/KBCT/KFLL/KFMY/KFXE/KMCO/KMIA/KMKY/KOPF/KPBI/K
PIE/KRSW/KSRQ/KTPA
FACILITIES INCLUDED: ZDC/ZID/ZJX/ZMA/ZNY/ZTL
FLIGHT STATUS: ALL_FLIGHTS
VALID: ETD 241400 TO 241800
PROBABILITY OF EXTENSION: LOW
REMARKS: DUE TO COMPACTED DEMAND OFF NY SATS OVER WHITE DEPARTURE
FIX. WATRS EXEMPT WHEN AVAILABLE.
ASSOCIATED RESTRICTIONS:
MODIFICATIONS:
ROUTES: [route table not shown]
TMI ID: RRDCC519
```

Every advisory the linker could see for this element in the horizon:

```
20260424-063  sent 04/24 17:50Z  ROUTE RQD /FL  NYSATS_TO_FL  VALID 24/1400Z - 24/2100Z  [PROBABILITY OF EXTENSION: LOW]
20260424-081  sent 04/24 19:19Z  REROUTE CANCELLATION  NYSATS_TO_FL
```

**Derived outcome: EXTENDED = 1**. end 24/1800Z -> 24/2100Z (+180 min).

Advisory that decides the outcome:

```
ATCSCC ADVZY 063 DCC 04/24/2026 ROUTE RQD /FL
NAME: NYSATS_TO_FL
CONSTRAINED AREA: ZNY
REASON: VOLUME
INCLUDE TRAFFIC: KCDW/KHPN/KMMU/KTEB DEPARTURES TO
KAPF/KBCT/KFLL/KFMY/KFXE/KMCO/KMIA/KMKY/KOPF/KPBI/K
PIE/KRSW/KSRQ/KTPA
FACILITIES INCLUDED: ZDC/ZID/ZJX/ZMA/ZNY/ZTL
FLIGHT STATUS: ALL_FLIGHTS
VALID: ETD 241400 TO 242100
PROBABILITY OF EXTENSION: LOW
REMARKS: REPLACES ADVZY 042
DUE TO COMPACTED DEMAND OFF NY SATS OVER WHITE DEPARTURE
FIX. WATRS EXEMPT WHEN AVAILABLE.
ASSOCIATED RESTRICTIONS:
MODIFICATIONS: TIME EXTENDED
ROUTES: [route table not shown]
TMI ID: RRDCC519
```

## 78. gs-20260519-123

- Term: **MEDIUM** (gs:MEDIUM); written as: `PROBABILITY OF EXTENSION: MEDIUM`
- Element: JFK; initiative: gs; first issued 05/19 21:38Z in 20260519-123; window read as 19/2100Z - 19/2245Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 123 JFK/ZNY 05/19/2026 CDM GROUND STOP
CTL ELEMENT: JFK
ELEMENT TYPE: APT
ADL TIME: 2135Z
GROUND STOP PERIOD: 19/2100Z - 19/2245Z
DEP FACILITIES INCLUDED: (Manual) ZDC ZNY ZOB ZBW  CYHZ CYOW CYUL
CYYZ CYTZ CYQB
PREVIOUS TOTAL, MAXIMUM, AVERAGE DELAYS: 0 / 0 / 0
NEW TOTAL, MAXIMUM, AVERAGE DELAYS: 257 / 71 / 51
PROBABILITY OF EXTENSION: MEDIUM
IMPACTING CONDITION: WEATHER / THUNDERSTORMS
COMMENTS:
```

Every advisory the linker could see for this element in the horizon:

```
20260519-128  sent 05/19 21:48Z  CDM PROPOSED GROUND DELAY PROGRAM  JFK  ANTICIPATED CUMULATIVE PROGRAM PERIOD 19/2143Z - 20/0259Z
20260519-138  sent 05/19 22:07Z  CDM GROUND DELAY PROGRAM  JFK  CUMULATIVE PROGRAM PERIOD 19/2205Z - 20/0259Z
20260519-156  sent 05/19 23:18Z  CDM GROUND STOP  JFK  GROUND STOP PERIOD 19/2300Z - 20/0100Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260519-161  sent 05/19 23:37Z  CDM GROUND STOP  JFK  GROUND STOP PERIOD 19/2322Z - 20/0100Z  [PROBABILITY OF EXTENSION: MEDIUM]
```

**Derived outcome: NOT EXTENDED (lapsed) = 0**. no later advisory moved the end past 19/2245Z. Flags: gdp_followed new_stop_30.

No advisory decides the outcome (nothing qualifying was found).

## 79. plan-20260402-026-SFO-gs+gdp-AFTER1500

- Term: **PROBABLE** (plan:PROBABLE); written as: `AFTER 1500	-SFO GROUND STOP/DELAY PROGRAM PROBABLE`
- Element: SFO; initiative: gs/gdp; first issued 04/02 01:33Z in 20260402-026; window read as 02/1500Z - 03/0800Z
- Repeated in: 20260402-063 20260402-074 20260402-098

Source advisory:

```
ATCSCC ADVZY 026 DCC 04/02/2026 OPERATIONS PLAN
EVENT TIME: 02/0200 - AND LATER
TERMINAL ACTIVE:
UNTIL 0200	-LGA GROUND STOP
UNTIL 0200	-TEB GROUND STOP
UNTIL 0200	-EWR GROUND STOP
UNTIL 0215	-BWI GROUND STOP
UNTIL 0215	-DCA GROUND STOP
UNTIL 0259	-EWR GROUND DELAY PROGRAM
UNTIL 0359	-JFK GROUND DELAY PROGRAM
UNTIL 0359	-DCA GROUND DELAY PROGRAM
UNTIL 0559  	-LGA GROUND DELAY PROGRAM
TERMINAL PLANNED:
AFTER 0345	-MEM GROUND STOP POSSIBLE
AFTER 1200	-MSP GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1300	-LGA GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1300	-DCA GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1300	-ORD/MDW GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1500	-SFO GROUND STOP/DELAY PROGRAM PROBABLE
AFTER 1700	-EWR GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1800	-BOS GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1800	-JFK/HPN GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 2000	-MCO/TPA GROUND STOP POSSIBLE
```

Every advisory the linker could see for this element in the horizon:

```
20260402-086  sent 04/02 12:32Z  CDM PROPOSED GROUND DELAY PROGRAM  SFO  ANTICIPATED CUMULATIVE PROGRAM PERIOD 02/1515Z - 02/2029Z
20260402-088  sent 04/02 12:49Z  CDM GROUND DELAY PROGRAM  SFO  CUMULATIVE PROGRAM PERIOD 02/1515Z - 02/2029Z
20260402-135  sent 04/02 17:47Z  CDM GROUND DELAY PROGRAM CNX  SFO  GDP CNX PERIOD 02/1743Z - 03/0111Z
20260402-155  sent 04/02 21:02Z  CDM GROUND DELAY PROGRAM  SFO  CUMULATIVE PROGRAM PERIOD 02/2200Z - 03/0559Z
20260403-029  sent 04/03 03:49Z  CDM GROUND DELAY PROGRAM  SFO  CUMULATIVE PROGRAM PERIOD 02/2200Z - 03/0659Z
20260403-036  sent 04/03 06:06Z  CDM GROUND DELAY PROGRAM CNX  SFO  GDP CNX PERIOD 03/0604Z - 03/1009Z
```

Other advisories that name the element (not read by the linker):

```
20260402-129  sent 04/02 17:02Z  SFO AIRPORT SCHEDULING DELAYS
```

**Derived outcome: ISSUED = 1**. CDM GROUND DELAY PROGRAM sent 02/1249Z, period 02/1515Z - 02/1747Z.

Advisory that decides the outcome:

```
ATCSCC ADVZY 088 SFO/ZOA 04/02/2026 CDM GROUND DELAY PROGRAM
CTL ELEMENT: SFO
ELEMENT TYPE: APT
ADL TIME: 1245Z
DELAY ASSIGNMENT MODE: UDP
ARRIVALS ESTIMATED FOR: 02/1515Z - 02/2029Z
CUMULATIVE PROGRAM PERIOD: 02/1515Z - 02/2029Z
PROGRAM RATE: 36
FLT INCL: ALL CONTIGUOUS US DEP
DEP SCOPE: 1400
CANADIAN DEP ARPTS INCLUDED: CYEG CYVR CYYC
DELAY ASSIGNMENT TABLE APPLIES TO: ZOA
MAXIMUM DELAY: 213
AVERAGE DELAY: 47
IMPACTING CONDITION: WEATHER / LOW CEILINGS
COMMENTS: ARR: 28L/R DEP: 28L/R TIME PLUS 45 MED HIST POP UP.
```

## 80. route-20260405-070

- Term: **LOW** (route:LOW); written as: `PROBABILITY OF EXTENSION: LOW`
- Element: FLORIDA_TO_NE_5_PARTIAL; initiative: reroute; first issued 04/05 17:50Z in 20260405-070; window read as 05/1815Z - 05/2200Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 070 DCC 04/05/2026 ROUTE RQD /FL
NAME: FLORIDA_TO_NE_5_PARTIAL
CONSTRAINED AREA: ZDC
REASON: WEATHER
INCLUDE TRAFFIC: KAPF/KFMY/KMKY/KPGD/KPIE/KRSW/KSRQ/KTPA/ZJX/ZMA
DEPARTURES TO KBWI/KDCA/KIAD
FACILITIES INCLUDED: ZDC/ZJX/ZMA/ZTL
FLIGHT STATUS: ALL_FLIGHTS
VALID: ETD 051815 TO 052200
PROBABILITY OF EXTENSION: LOW
REMARKS:
ASSOCIATED RESTRICTIONS:
MODIFICATIONS:
ROUTES: [route table not shown]
TMI ID: RRDCC070
```

Every advisory the linker could see for this element in the horizon:

```
(none)
```

**Derived outcome: NOT EXTENDED (lapsed) = 0**. no later advisory moved the end past 05/2200Z.

No advisory decides the outcome (nothing qualifying was found).

## 81. gs-20260510-069

- Term: **LOW** (gs:LOW); written as: `PROBABILITY OF EXTENSION: LOW`
- Element: LGA; initiative: gs; first issued 05/10 19:33Z in 20260510-069; window read as 10/1923Z - 10/2015Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 069 LGA/ZNY 05/10/2026 CDM GROUND STOP
CTL ELEMENT: LGA
ELEMENT TYPE: APT
ADL TIME: 1930Z
GROUND STOP PERIOD: 10/1923Z - 10/2015Z
DEP FACILITIES INCLUDED: (Manual) ZDC ZOB
PREVIOUS TOTAL, MAXIMUM, AVERAGE DELAYS: 0 / 0 / 0
NEW TOTAL, MAXIMUM, AVERAGE DELAYS: 279 / 51 / 35
PROBABILITY OF EXTENSION: LOW
IMPACTING CONDITION: WEATHER / THUNDERSTORMS
COMMENTS: HOLDING DUE TO WX ON FINAL
```

Every advisory the linker could see for this element in the horizon:

```
20260510-077  sent 05/10 19:59Z  CDM GS CNX  LGA  GS CNX PERIOD 10/1958Z - 10/2121Z
20260510-084  sent 05/10 21:00Z  CDM GROUND STOP  LGA  GROUND STOP PERIOD 10/2043Z - 10/2200Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260510-089  sent 05/10 21:59Z  CDM GS CNX  LGA  GS CNX PERIOD 10/2155Z - 11/0036Z
```

Other advisories that name the element (not read by the linker):

```
20260510-072  sent 05/10 19:39Z  LGA AIRPORT DIVERSION RECOVERY ACTIVATED
```

**Derived outcome: NOT EXTENDED (cancelled) = 0**. cancelled at 10/1959Z; stated end 10/2015Z. Flags: new_stop_30.

Advisory that decides the outcome:

```
ATCSCC ADVZY 077 LGA/ZNY 05/10/2026 CDM GS CNX
CTL ELEMENT: LGA
ELEMENT TYPE: APT
ADL TIME: 1958Z
GS CNX PERIOD: 10/1958Z - 10/2121Z
COMMENTS:
```

## 82. gs-20260419-046

- Term: **LOW** (gs:LOW); written as: `PROBABILITY OF EXTENSION: LOW`
- Element: LGA; initiative: gs; first issued 04/19 13:36Z in 20260419-046; window read as 19/1300Z - 19/1430Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 046 LGA/ZNY 04/19/2026 CDM GROUND STOP
CTL ELEMENT: LGA
ELEMENT TYPE: APT
ADL TIME: 1334Z
GROUND STOP PERIOD: 19/1300Z - 19/1430Z
DEP FACILITIES INCLUDED: (Manual) ZAU ZTL ZDC ZNY ZJX ZOB ZBW ZID ZMP
CYHZ CYOW CYUL CYYZ CYTZ CYQB
PREVIOUS TOTAL, MAXIMUM, AVERAGE DELAYS: 0 / 0 / 0
NEW TOTAL, MAXIMUM, AVERAGE DELAYS: 610 / 61 / 25
PROBABILITY OF EXTENSION: LOW
IMPACTING CONDITION: RWY-TAXI / MAINTENANCE
COMMENTS:
```

Every advisory the linker could see for this element in the horizon:

```
20260419-052  sent 04/19 14:20Z  CDM GROUND STOP  LGA  GROUND STOP PERIOD 19/1401Z - 19/1500Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260419-054  sent 04/19 14:59Z  CDM GS CNX  LGA  GS CNX PERIOD 19/1455Z - 19/1723Z
20260419-060  sent 04/19 16:08Z  CDM GROUND STOP  LGA  GROUND STOP PERIOD 19/1555Z - 19/1700Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260419-062  sent 04/19 16:26Z  CDM PROPOSED GROUND DELAY PROGRAM  LGA  ANTICIPATED CUMULATIVE PROGRAM PERIOD 19/1605Z - 20/0359Z
```

**Derived outcome: EXTENDED = 1**. end 19/1430Z -> 19/1500Z (+30 min).

Advisory that decides the outcome:

```
ATCSCC ADVZY 052 LGA/ZNY 04/19/2026 CDM GROUND STOP
CTL ELEMENT: LGA
ELEMENT TYPE: APT
ADL TIME: 1416Z
GROUND STOP PERIOD: 19/1401Z - 19/1500Z
DEP FACILITIES INCLUDED: (Manual) ZAU ZTL ZDC ZNY ZJX ZOB ZBW ZID ZMP
CYHZ CYOW CYUL CYYZ CYTZ CYQB
PREVIOUS TOTAL, MAXIMUM, AVERAGE DELAYS: 529 / 56 / 17
NEW TOTAL, MAXIMUM, AVERAGE DELAYS: 1295 / 86 / 40
PROBABILITY OF EXTENSION: MEDIUM
IMPACTING CONDITION: RWY-TAXI / MAINTENANCE
COMMENTS: GROUND STOP EXTENDED 30 MIN. RWY 04/22 EXPECTED TO OPEN BY
16Z.
```

## 83. gs-20260410-073

- Term: **LOW** (gs:LOW); written as: `PROBABILITY OF EXTENSION: LOW`
- Element: AIK; initiative: gs; first issued 04/10 20:23Z in 20260410-073; window read as 10/1944Z - 10/2130Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 073 AIK/ZTL 04/10/2026 CDM GROUND STOP
CTL ELEMENT: AIK
ELEMENT TYPE: APT
ADL TIME: 2019Z
GROUND STOP PERIOD: 10/1944Z - 10/2130Z
DEP FACILITIES INCLUDED: (Manual) ZTL ZDC ZJX ZMA ZME ZID
PREVIOUS TOTAL, MAXIMUM, AVERAGE DELAYS: 0 / 0 / 0
NEW TOTAL, MAXIMUM, AVERAGE DELAYS: 486 / 75 / 49
PROBABILITY OF EXTENSION: LOW
IMPACTING CONDITION: VOLUME / VOLUME
COMMENTS:
```

Every advisory the linker could see for this element in the horizon:

```
20260410-078  sent 04/10 21:30Z  CDM GS CNX  AIK  GS CNX PERIOD 10/2128Z - 10/2257Z
```

**Derived outcome: NOT EXTENDED (cancelled) = 0**. cancelled at 10/2130Z; stated end 10/2130Z.

Advisory that decides the outcome:

```
ATCSCC ADVZY 078 AIK/ZTL 04/10/2026 CDM GS CNX
CTL ELEMENT: AIK
ELEMENT TYPE: APT
ADL TIME: 2128Z
GS CNX PERIOD: 10/2128Z - 10/2257Z
COMMENTS:
```

## 84. plan-20260410-037-HQU-gs+gdp-UNTIL0000

- Term: **POSSIBLE** (plan:POSSIBLE); written as: `UNTIL 0000	-AIK/DNL/HQU GROUND STOP/DELAY PROGRAM POSSIBLE`
- Element: HQU; initiative: gs/gdp; first issued 04/10 13:39Z in 20260410-037; window read as 10/1339Z - 11/0000Z
- Repeated in: 20260410-045 20260410-053

Source advisory:

```
ATCSCC ADVZY 037 DCC 04/10/2026 OPERATIONS PLAN
EVENT TIME: 10/1400 - AND LATER
TERMINAL ACTIVE:
UNTIL 2259	-SFO GROUND DELAY PROGRAM
UNTIL 0359	-AGS GROUND DELAY PROGRAM
TERMINAL PLANNED:
AFTER 1800	-IAH/HOU GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1900	-AUS GROUND STOP POSSIBLE
AFTER 1900	-SAT GROUND STOP POSSIBLE
AFTER 2000	-DEN GROUND STOP/DELAY PROGRAM POSSIBLE
UNTIL 0000	-AIK/DNL/HQU GROUND STOP/DELAY PROGRAM POSSIBLE
```

Every advisory the linker could see for this element in the horizon:

```
(none)
```

**Derived outcome: NOT ISSUED = 0**. no gs or gdp advisory for HQU in the window.

No advisory decides the outcome (nothing qualifying was found).

## 85. gs-20260520-135

- Term: **HIGH** (gs:HIGH); written as: `PROBABILITY OF EXTENSION: HIGH`
- Element: EWR; initiative: gs; first issued 05/20 20:25Z in 20260520-135; window read as 20/1946Z - 20/2130Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 135 EWR/ZNY 05/20/2026 CDM GROUND STOP
CTL ELEMENT: EWR
ELEMENT TYPE: APT
ADL TIME: 2021Z
GROUND STOP PERIOD: 20/1946Z - 20/2130Z
CUMULATIVE PROGRAM PERIOD: 20/2000Z - 21/0459Z
DEP FACILITIES INCLUDED: (Manual) ZAU ZTL ZDC ZNY ZJX ZOB ZBW ZID ZMP
CYHZ CYOW CYUL CYYZ CYTZ CYQB
PREVIOUS TOTAL, MAXIMUM, AVERAGE DELAYS: 841 / 99 / 53
NEW TOTAL, MAXIMUM, AVERAGE DELAYS: 1158 / 148 / 72
PROBABILITY OF EXTENSION: HIGH
IMPACTING CONDITION: WEATHER / THUNDERSTORMS
COMMENTS: SCOPE EXPANED AND EXTENDED.
```

Every advisory the linker could see for this element in the horizon:

```
20260520-147  sent 05/20 21:14Z  CDM GROUND DELAY PROGRAM  EWR  CUMULATIVE PROGRAM PERIOD 20/2000Z - 21/0459Z
20260520-149  sent 05/20 21:16Z  EWR GROUND STOP CANCELLATION  EWR  EVENT TIME 20/2115Z - 20/2200Z
20260520-184  sent 05/20 23:22Z  CDM GROUND STOP  EWR  GROUND STOP PERIOD 20/2308Z - 21/0030Z  [PROBABILITY OF EXTENSION: MEDIUM]
```

**Derived outcome: NOT EXTENDED (lapsed) = 0**. no later advisory moved the end past 20/2130Z. Flags: gdp_followed manual_release.

No advisory decides the outcome (nothing qualifying was found).

## 86. gs-20260404-020

- Term: **LOW** (gs:LOW); written as: `PROBABILITY OF EXTENSION: LOW`
- Element: ORD; initiative: gs; first issued 04/04 04:33Z in 20260404-020; window read as 04/0328Z - 04/0600Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 020 ORD/ZAU 04/04/2026 CDM GROUND STOP
CTL ELEMENT: ORD
ELEMENT TYPE: APT
ADL TIME: 0429Z
GROUND STOP PERIOD: 04/0328Z - 04/0600Z
CUMULATIVE PROGRAM PERIOD: 04/0126Z - 04/0659Z
DEP FACILITIES INCLUDED: (Manual) ZKC ZMP
PREVIOUS TOTAL, MAXIMUM, AVERAGE DELAYS: 278 / 178 / 70
NEW TOTAL, MAXIMUM, AVERAGE DELAYS: 592 / 239 / 148
PROBABILITY OF EXTENSION: LOW
IMPACTING CONDITION: WEATHER / THUNDERSTORMS
COMMENTS: ROUTES NOT AVAILABLE WEST OF ORD, GS SCOPE REDUCED
```

Every advisory the linker could see for this element in the horizon:

```
20260404-022  sent 04/04 05:19Z  CDM GROUND DELAY PROGRAM CNX  ORD  GDP CNX PERIOD 04/0513Z - 04/1724Z
20260404-023  sent 04/04 05:22Z  CDM GROUND STOP  ORD  GROUND STOP PERIOD 04/0509Z - 04/0615Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260404-025  sent 04/04 06:01Z  CDM GROUND STOP  ORD  GROUND STOP PERIOD 04/0547Z - 04/0700Z  [PROBABILITY OF EXTENSION: LOW]
20260404-026  sent 04/04 06:15Z  CDM GS CNX  ORD  GS CNX PERIOD 04/0611Z - 04/0918Z
```

**Derived outcome: EXTENDED = 1**. end 04/0600Z -> 04/0615Z (+15 min).

Advisory that decides the outcome:

```
ATCSCC ADVZY 023 ORD/ZAU 04/04/2026 CDM GROUND STOP
CTL ELEMENT: ORD
ELEMENT TYPE: APT
ADL TIME: 0519Z
GROUND STOP PERIOD: 04/0509Z - 04/0615Z
DEP FACILITIES INCLUDED: (Manual) ZAU ZKC ZMP
PREVIOUS TOTAL, MAXIMUM, AVERAGE DELAYS: 0 / 0 / 0
NEW TOTAL, MAXIMUM, AVERAGE DELAYS: 1723 / 258 / 66
PROBABILITY OF EXTENSION: MEDIUM
IMPACTING CONDITION: WEATHER / THUNDERSTORMS
COMMENTS: ZAU ADDED TO GROUND STOP
```

## 87. route-20260404-065

- Term: **MODERATE** (route:MODERATE); written as: `PROBABILITY OF EXTENSION: MODERATE`
- Element: FCA016:LEV_WEST_MODIFIED; initiative: reroute; first issued 04/04 12:42Z in 20260404-065; window read as 04/1330Z - 04/1800Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 065 DCC 04/04/2026 FCA RQD
NAME: FCA016:LEV_WEST_MODIFIED
CONSTRAINED AREA: ZHU/ZFW
REASON: WEATHER
INCLUDE TRAFFIC: KATL/KMIA/KTPA/ZJX/ZMA DEPARTURES TO
KLAS/KLAX/KLGB/KOAK/KPHX/KSAN/KSFO/KSJC/KSNA
FACILITIES INCLUDED: ZAB/ZHU/ZJX/ZLA/ZMA/ZOA/ZTL
FLIGHT STATUS: ALL_FLIGHTS
VALID: FCA ENTRY TIME FROM 041330 TO 041800
PROBABILITY OF EXTENSION: MODERATE
REMARKS: SEE DYNAMIC LIST FOR UPDATES.
ASSOCIATED RESTRICTIONS:
MODIFICATIONS: ROUTE MODIFIED BETWEEN PSX AND FST.
ROUTES: [route table not shown]
TMI ID: RRDCC509
```

Every advisory the linker could see for this element in the horizon:

```
(none)
```

**Derived outcome: NOT EXTENDED (lapsed) = 0**. no later advisory moved the end past 04/1800Z.

No advisory decides the outcome (nothing qualifying was found).

## 88. route-20260430-042

- Term: **MODERATE** (route:MODERATE); written as: `PROBABILITY OF EXTENSION: MODERATE`
- Element: FLORIDA_TO_OHIO_VALLEY_1; initiative: reroute; first issued 04/30 13:28Z in 20260430-042; window read as 30/1330Z - 30/1630Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 042 DCC 04/30/2026 ROUTE RQD /FL
NAME: FLORIDA_TO_OHIO_VALLEY_1
CONSTRAINED AREA: EAST COAST
REASON: WEATHER
INCLUDE TRAFFIC: KAPF/KDAB/KISM/KJAX/KMCO/KMKY/KORL/KSFB/ZMA
DEPARTURES TO
CYYZ/KCLE/KCMH/KCVG/KDAY/KDTW/KIND/KLEX/KMDW/KMKE/K
ORD/KPIT/KSDF
FACILITIES INCLUDED: CZY/ZAU/ZID/ZJX/ZMA/ZOB/ZTL
FLIGHT STATUS: ALL_FLIGHTS
VALID: ETD 301330 TO 301630
PROBABILITY OF EXTENSION: MODERATE
REMARKS:
ASSOCIATED RESTRICTIONS:
MODIFICATIONS:
ROUTES: [route table not shown]
TMI ID: RRDCC042
```

Every advisory the linker could see for this element in the horizon:

```
(none)
```

**Derived outcome: NOT EXTENDED (lapsed) = 0**. no later advisory moved the end past 30/1630Z.

No advisory decides the outcome (nothing qualifying was found).

## 89. plan-20260509-080-PHL-gs-AFTER1900

- Term: **POSSIBLE** (plan:POSSIBLE); written as: `AFTER 1900 	-PHL GS POSSIBLE`
- Element: PHL; initiative: gs; first issued 05/09 23:55Z in 20260509-080; window read as 10/1900Z - 11/0800Z
- Repeated in: 20260510-010 20260510-020 20260510-027 20260510-040 20260510-052

Source advisory:

```
ATCSCC ADVZY 080 DCC 05/09/2026 OPERATIONS PLAN
EVENT TIME: 10/0000 - AND LATER
TERMINAL ACTIVE:
NONE
TERMINAL PLANNED:
AFTER 1500 	-SFO GS/GDP POSSIBLE
AFTER 1700 	-DAL GS PROBABLE
AFTER 1700 	-DFW GS/GDP PROBABLE
AFTER 1900 	-LGA/JFK GS POSSIBLE
AFTER 1900 	-DCA/IAD GS POSSIBLE
AFTER 1900 	-EWR GS POSSIBLE
AFTER 1900 	-PHL GS POSSIBLE
AFTER 1900 	-MCO GS POSSIBLE
```

Every advisory the linker could see for this element in the horizon:

```
(none)
```

Other advisories that name the element (not read by the linker):

```
20260510-079  sent 05/10 20:07Z  PHL AIRPORT ARRIVAL DELAYS
```

**Derived outcome: NOT ISSUED = 0**. no gs advisory for PHL in the window.

No advisory decides the outcome (nothing qualifying was found).

## 90. plan-20260510-088-LGA-gs-UNTIL0200

- Term: **POSSIBLE** (plan:POSSIBLE); written as: `UNTIL 0200 	-LGA/JFK GROUND STOP POSSIBLE`
- Element: LGA; initiative: gs; first issued 05/10 21:43Z in 20260510-088; window read as 10/2143Z - 11/0200Z
- Repeated in: 20260510-098

Source advisory:

```
ATCSCC ADVZY 088 DCC 05/10/2026 OPERATIONS PLAN
EVENT TIME: 10/2200 - AND LATER
TERMINAL ACTIVE:
UNTIL 0229	-CYYZ GROUND DELAY PROGRAM
UNTIL 0459	-DFW GROUND DELAY PROGRAM
UNTIL 0659	-SFO GROUND DELAY PROGRAM
TERMINAL PLANNED:
UNTIL 2300 	-DFW GROUND STOP/DELAY PROGRAM PROBABLE
UNTIL 0200 	-LGA/JFK GROUND STOP POSSIBLE
UNTIL 0200	-DCA/IAD GROUND STOP POSSIBLE
UNTIL 0200 	-EWR GROUND STOP POSSIBLE
```

Every advisory the linker could see for this element in the horizon:

```
20260510-069  sent 05/10 19:33Z  CDM GROUND STOP  LGA  GROUND STOP PERIOD 10/1923Z - 10/2015Z  [PROBABILITY OF EXTENSION: LOW]
20260510-077  sent 05/10 19:59Z  CDM GS CNX  LGA  GS CNX PERIOD 10/1958Z - 10/2121Z
20260510-084  sent 05/10 21:00Z  CDM GROUND STOP  LGA  GROUND STOP PERIOD 10/2043Z - 10/2200Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260510-089  sent 05/10 21:59Z  CDM GS CNX  LGA  GS CNX PERIOD 10/2155Z - 11/0036Z
20260510-100  sent 05/10 23:54Z  CDM GROUND STOP  LGA  GROUND STOP PERIOD 10/2340Z - 11/0100Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260511-005  sent 05/11 00:33Z  CDM GS CNX  LGA  GS CNX PERIOD 11/0029Z - 11/0245Z
```

Other advisories that name the element (not read by the linker):

```
20260510-072  sent 05/10 19:39Z  LGA AIRPORT DIVERSION RECOVERY ACTIVATED
```

**Derived outcome: EXCLUDED (already_active)**. CDM GROUND STOP already running at 10/2143Z, until 10/2200Z.

Advisory that decides the outcome:

```
ATCSCC ADVZY 084 LGA/ZNY 05/10/2026 CDM GROUND STOP
CTL ELEMENT: LGA
ELEMENT TYPE: APT
ADL TIME: 2058Z
GROUND STOP PERIOD: 10/2043Z - 10/2200Z
DEP FACILITIES INCLUDED: (Manual) ZTL ZDC ZJX ZMA ZID
PREVIOUS TOTAL, MAXIMUM, AVERAGE DELAYS: 0 / 0 / 0
NEW TOTAL, MAXIMUM, AVERAGE DELAYS: 606 / 67 / 30
PROBABILITY OF EXTENSION: MEDIUM
IMPACTING CONDITION: WEATHER / THUNDERSTORMS
COMMENTS:
```

## 91. plan-20260504-030-MIA-gs+gdp-AFTER1800

- Term: **POSSIBLE** (plan:POSSIBLE); written as: `AFTER 1800	-MIA/FLL/PBI GROUND STOP/DELAY PROGRAM POSSIBLE`
- Element: MIA; initiative: gs/gdp; first issued 05/04 13:37Z in 20260504-030; window read as 04/1800Z - 05/0800Z
- Repeated in: 20260504-035 20260504-040

Source advisory:

```
ATCSCC ADVZY 030 DCC 05/04/2026 OPERATIONS PLAN
EVENT TIME: 04/1400 - AND LATER
TERMINAL ACTIVE:
UNTIL 2259	-SFO GROUND DELAY PROGRAM
TERMINAL PLANNED:
AFTER 1800	-MIA/FLL/PBI GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 2000	-DEN GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 2300	-SFO GROUND STOP/DELAY PROGRAM POSSIBLE
```

Every advisory the linker could see for this element in the horizon:

```
(none)
```

**Derived outcome: NOT ISSUED = 0**. no gs or gdp advisory for MIA in the window.

No advisory decides the outcome (nothing qualifying was found).

## 92. route-20260424-074

- Term: **HIGH** (route:HIGH); written as: `PROBABILITY OF EXTENSION: HIGH`
- Element: FCA016:MIA_VIA_MOGAE_MODIFIED; initiative: reroute; first issued 04/24 18:33Z in 20260424-074; window read as 24/2045Z - 25/0200Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 074 DCC 04/24/2026 FCA RQD
NAME: FCA016:MIA_VIA_MOGAE_MODIFIED
CONSTRAINED AREA: ZJX/ZMA
REASON: OTHER
INCLUDE TRAFFIC: CZU/CZY/KBWI/KCHO/KCLT/KDCA/KDET/KDTW/KFNT/KIAD/KJF
K/KLAN/KMBS/KORF/KPHF/KPHL/KPTK/KRDU/KRIC/KYIP/ZAU/
ZBW/ZDV/ZID/ZJX/ZKC/ZME/ZMP/ZNY/ZOB/ZTL DEPARTURES
TO KMIA
FACILITIES INCLUDED: CZU/CZY/ZAU/ZBW/ZDC/ZDV/ZID/ZJX/ZKC/ZMA/ZME/ZMP
/ZNY/ZOB/ZTL
FLIGHT STATUS: ALL_FLIGHTS
VALID: FCA ENTRY TIME FROM 242045 TO 250200
PROBABILITY OF EXTENSION: HIGH
REMARKS: SEE DYNAMIC LIST FOR UPDATES. AIRCRAFT FILED VIA AR AND Y
ROUTES ARE EXEMPT.  THIS ROUTE IS ISSUED DUE TO SPECIAL
OPS.
ASSOCIATED RESTRICTIONS:
MODIFICATIONS: MODIFIED TO MISS STAVE 1 AND STAVE 2
ROUTES: [route table not shown]
TMI ID: RRDCC526
```

Every advisory the linker could see for this element in the horizon:

```
(none)
```

**Derived outcome: NOT EXTENDED (lapsed) = 0**. no later advisory moved the end past 25/0200Z.

No advisory decides the outcome (nothing qualifying was found).

## 93. gs-20260417-078

- Term: **MEDIUM** (gs:MEDIUM); written as: `PROBABILITY OF EXTENSION: MEDIUM`
- Element: EWR; initiative: gs; first issued 04/17 18:56Z in 20260417-078; window read as 17/1843Z - 17/1930Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 078 EWR/ZNY 04/17/2026 CDM GROUND STOP
CTL ELEMENT: EWR
ELEMENT TYPE: APT
ADL TIME: 1853Z
GROUND STOP PERIOD: 17/1843Z - 17/1930Z
DEP FACILITIES INCLUDED: (Manual) ZOB ZAU
PREVIOUS TOTAL, MAXIMUM, AVERAGE DELAYS: 0 / 0 / 0
NEW TOTAL, MAXIMUM, AVERAGE DELAYS: 42 / 28 / 21
PROBABILITY OF EXTENSION: MEDIUM
IMPACTING CONDITION: WEATHER / THUNDERSTORMS
COMMENTS:
```

Every advisory the linker could see for this element in the horizon:

```
20260417-087  sent 04/17 19:26Z  CDM GROUND STOP  EWR  GROUND STOP PERIOD 17/1843Z - 17/2030Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260417-088  sent 04/17 19:41Z  CDM GS CNX  EWR  GS CNX PERIOD 17/1936Z - 17/2239Z
```

**Derived outcome: EXTENDED = 1**. end 17/1930Z -> 17/2030Z (+60 min).

Advisory that decides the outcome:

```
ATCSCC ADVZY 087 EWR/ZNY 04/17/2026 CDM GROUND STOP
CTL ELEMENT: EWR
ELEMENT TYPE: APT
ADL TIME: 1926Z
GROUND STOP PERIOD: 17/1843Z - 17/2030Z
DEP FACILITIES INCLUDED: (Manual) ZOB ZAU
PREVIOUS TOTAL, MAXIMUM, AVERAGE DELAYS: 42 / 28 / 10
NEW TOTAL, MAXIMUM, AVERAGE DELAYS: 183 / 88 / 46
PROBABILITY OF EXTENSION: MEDIUM
IMPACTING CONDITION: WEATHER / THUNDERSTORMS
COMMENTS:
```

## 94. plan-20260531-019-BOS-gs+gdp-AFTER1800

- Term: **POSSIBLE** (plan:POSSIBLE); written as: `AFTER 1800	-BOS GROUND STOP/DELAY PROGRAM POSSIBLE`
- Element: BOS; initiative: gs/gdp; first issued 05/31 11:47Z in 20260531-019; window read as 31/1800Z - 01/0800Z
- Repeated in: 20260531-028 20260531-038

Source advisory:

```
ATCSCC ADVZY 019 DCC 05/31/2026 OPERATIONS PLAN
EVENT TIME: 31/1200 - AND LATER
TERMINAL ACTIVE:
NONE
TERMINAL PLANNED:
AFTER 1430	-SFO GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1600	-MCO/TPA GROUND STOP POSSIBLE
AFTER 1800	-ATL GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1800	-BOS GROUND STOP/DELAY PROGRAM POSSIBLE
```

Every advisory the linker could see for this element in the horizon:

```
(none)
```

Other advisories that name the element (not read by the linker):

```
20260531-059  sent 05/31 20:25Z  BOS AIRPORT ARRIVAL DELAYS
```

**Derived outcome: EXCLUDED (unresolved_boundary)**. window ends 01/0800Z, after the loaded months.

No advisory decides the outcome (nothing qualifying was found).

## 95. route-20260424-064

- Term: **HIGH** (route:HIGH); written as: `PROBABILITY OF EXTENSION: HIGH`
- Element: FCA012:GA_TO_BCT_AREA; initiative: reroute; first issued 04/24 17:52Z in 20260424-064; window read as 24/2045Z - 25/0200Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 064 DCC 04/24/2026 FCA RQD
NAME: FCA012:GA_TO_BCT_AREA
CONSTRAINED AREA: ZJX/ZMA
REASON: OTHER
INCLUDE TRAFFIC: CZU/CZY/KBWI/KCLT/KDCA/KDET/KDTW/KFAY/KFNT/KIAD/KIL
M/KLAN/KMBS/KOAJ/KPTK/KRIC/KROA/KSOP/KYIP/ZAB/ZAU/Z
BW/ZDC/ZDV/ZFW/ZHU/ZID/ZJX/ZKC/ZLA/ZLC/ZME/ZMP/ZNY/
ZOA/ZOB/ZSE/ZTL DEPARTURES TO KBCT/KFXE/KPMP
FACILITIES INCLUDED: CZU/CZY/ZAB/ZAU/ZBW/ZDC/ZDV/ZFW/ZHU/ZID/ZJX/ZKC
/ZLA/ZLC/ZMA/ZME/ZMP/ZNY/ZOA/ZOB/ZSE/ZTL
FLIGHT STATUS: ALL_FLIGHTS
VALID: FCA ENTRY TIME FROM 242045 TO 250200
PROBABILITY OF EXTENSION: HIGH
REMARKS: SEE DYNAMIC LIST FOR UPDATES. THIS ROUTE IS ISSUED DUE TO
SPECIAL OPERATIONS.
ASSOCIATED RESTRICTIONS:
MODIFICATIONS:
ROUTES: [route table not shown]
TMI ID: RRDCC522
```

Every advisory the linker could see for this element in the horizon:

```
20260425-003  sent 04/25 00:40Z  FCA RQD  FCA021:GA_TO_BCT_AREA  VALID 25/0200Z - 25/1900Z  [PROBABILITY OF EXTENSION: LOW]
```

**Derived outcome: EXTENDED = 1**. end 25/0200Z -> 25/1900Z (+1020 min), carried on as FCA021:GA_TO_BCT_AREA under TMI ID RRDCC500. Flags: continued_new_id.

Advisory that decides the outcome:

```
ATCSCC ADVZY 003 DCC 04/25/2026 FCA RQD
NAME: FCA021:GA_TO_BCT_AREA
CONSTRAINED AREA: ZJX/ZMA
REASON: OTHER
INCLUDE TRAFFIC: CZU/CZY/KBWI/KCLT/KDCA/KDET/KDTW/KFAY/KFNT/KIAD/KIL
M/KLAN/KMBS/KOAJ/KPTK/KRIC/KROA/KSOP/KYIP/ZAB/ZAU/Z
BW/ZDC/ZDV/ZFW/ZHU/ZID/ZJX/ZKC/ZLA/ZLC/ZME/ZMP/ZNY/
ZOA/ZOB/ZSE/ZTL DEPARTURES TO KBCT/KFXE/KPMP
FACILITIES INCLUDED: CZU/CZY/ZAB/ZAU/ZBW/ZDC/ZDV/ZFW/ZHU/ZID/ZJX/ZKC
/ZLA/ZLC/ZMA/ZME/ZMP/ZNY/ZOA/ZOB/ZSE/ZTL
FLIGHT STATUS: ALL_FLIGHTS
VALID: FCA ENTRY TIME FROM 250200 TO 251900
PROBABILITY OF EXTENSION: LOW
REMARKS: SEE DYNAMIC LIST FOR UPDATES. THIS ROUTE IS ISSUED DUE TO
SPECIAL OPERATIONS.
ASSOCIATED RESTRICTIONS:
MODIFICATIONS:
ROUTES: [route table not shown]
TMI ID: RRDCC500
```

## 96. plan-20260502-117-LOU-gs+gdp-AFTER1500

- Term: **POSSIBLE** (plan:POSSIBLE); written as: `AFTER 1500	-JVY/LOU/SDF GROUND STOP/DELAY PROGRAM POSSIBLE`
- Element: LOU; initiative: gs/gdp; first issued 05/02 23:26Z in 20260502-117; window read as 03/1500Z - 04/0800Z
- Repeated in: 20260503-010 20260503-012 20260503-030 20260503-035

Source advisory:

```
ATCSCC ADVZY 117 DCC 05/02/2026 OPERATIONS PLAN
EVENT TIME: 03/0000 - AND LATER
TERMINAL ACTIVE:
NONE
TERMINAL PLANNED:
AFTER 1300	-LGA GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1300	-MIA/FLL/PBI GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1500	-JVY/LOU/SDF GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1600	-SFO GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 2000	-JFK GROUND STOP/DELAY PROGRAM POSSIBLE
```

Every advisory the linker could see for this element in the horizon:

```
(none)
```

**Derived outcome: NOT ISSUED = 0**. no gs or gdp advisory for LOU in the window.

No advisory decides the outcome (nothing qualifying was found).

## 97. route-20260403-094

- Term: **HIGH** (route:HIGH); written as: `PROBABILITY OF EXTENSION: HIGH`
- Element: FCA024:ORD_NO_BENKY_CHMPN_PARTIAL; initiative: reroute; first issued 04/03 18:59Z in 20260403-094; window read as 03/2030Z - 04/0200Z
- Repeated in: 20260403-115

Source advisory:

```
ATCSCC ADVZY 094 DCC 04/03/2026 FCA RQD
NAME: FCA024:ORD_NO_BENKY_CHMPN_PARTIAL
CONSTRAINED AREA: ZKC/ZAU/ZMP
REASON: WEATHER
INCLUDE TRAFFIC: GPI/GTF/HLN/MSO/ZAB/ZDV/ZLA/ZLC/ZOA/ZSE DEPARTURES
TO KORD
FACILITIES INCLUDED: ZAB/ZAU/ZDV/ZLA/ZLC/ZMP/ZOA/ZSE
FLIGHT STATUS: ALL_FLIGHTS
VALID: FCA ENTRY TIME FROM 032030 TO 040200
PROBABILITY OF EXTENSION: HIGH
REMARKS: SEE DYNAMIC LIST FOR UPDATES.
ASSOCIATED RESTRICTIONS:
MODIFICATIONS:
ROUTES: [route table not shown]
TMI ID: RRDCC517
```

Every advisory the linker could see for this element in the horizon:

```
20260403-115  sent 04/03 21:13Z  FCA RQD  FCA024:ORD_NO_BENKY_CHMPN_PARTIAL  VALID 03/2030Z - 04/0200Z  [PROBABILITY OF EXTENSION: HIGH]
20260404-003  sent 04/04 00:18Z  FCA RQD  FCA024:ORD_NO_BENKY_CHMPN_PARTIAL  VALID 03/2030Z - 04/0400Z  [PROBABILITY OF EXTENSION: HIGH]
```

**Derived outcome: EXTENDED = 1**. end 04/0200Z -> 04/0400Z (+120 min).

Advisory that decides the outcome:

```
ATCSCC ADVZY 003 DCC 04/04/2026 FCA RQD
NAME: FCA024:ORD_NO_BENKY_CHMPN_PARTIAL
CONSTRAINED AREA: ZKC/ZAU/ZMP
REASON: WEATHER
INCLUDE TRAFFIC: GPI/GTF/HLN/MSO/ZAB/ZDV/ZLA/ZLC/ZOA/ZSE DEPARTURES
TO KORD
FACILITIES INCLUDED: ZAB/ZAU/ZDV/ZLA/ZLC/ZMP/ZOA/ZSE
FLIGHT STATUS: ALL_FLIGHTS
VALID: FCA ENTRY TIME FROM 032030 TO 040400
PROBABILITY OF EXTENSION: HIGH
REMARKS: REPLACES ADVZY 115. SEE DYNAMIC LIST FOR UPDATES.
ASSOCIATED RESTRICTIONS:
MODIFICATIONS: END TIME EXTENDED.
STAR MODIFIED TO WYNDE.
ROUTES: [route table not shown]
TMI ID: RRDCC517
```

## 98. route-20260428-078

- Term: **MODERATE** (route:MODERATE); written as: `PROBABILITY OF EXTENSION: MODERATE`
- Element: SE_TO_KATL; initiative: reroute; first issued 04/28 13:29Z in 20260428-078; window read as 28/1100Z - 28/1700Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 078 DCC 04/28/2026 ROUTE RQD /FL
NAME: SE_TO_KATL
CONSTRAINED AREA: ZTL
REASON: WEATHER
INCLUDE TRAFFIC: KCHS/KJAX/KSAV/KSSI/ZJX/ZMA DEPARTURES TO KATL
FACILITIES INCLUDED: ZJX/ZMA/ZTL
FLIGHT STATUS: ALL_FLIGHTS
VALID: ETD 281100 TO 281700
PROBABILITY OF EXTENSION: MODERATE
REMARKS: BASED OFF AN ATL_NO_OZZZI_ONDRE
ASSOCIATED RESTRICTIONS:
MODIFICATIONS: PLAY EXTENDED, CHS/SAV AREA DEPARTURES AMENDED
ROUTES: [route table not shown]
TMI ID: RRDCC502
```

Every advisory the linker could see for this element in the horizon:

```
20260428-094  sent 04/28 16:03Z  REROUTE CANCELLATION  SE_TO_KATL
```

**Derived outcome: NOT EXTENDED (cancelled) = 0**. cancelled at 28/1603Z; stated end 28/1700Z.

Advisory that decides the outcome:

```
ATCSCC ADVZY 094 DCC 04/28/2026 REROUTE CANCELLATION
SE_TO_KATL HAS BEEN CANCELLED.

REMARKS: CANCELS ADVZY 078
ASSOCIATED RESTRICTIONS:
```

## 99. plan-20260402-026-LGA-gs+gdp-AFTER1300

- Term: **POSSIBLE** (plan:POSSIBLE); written as: `AFTER 1300	-LGA GROUND STOP/DELAY PROGRAM POSSIBLE`
- Element: LGA; initiative: gs/gdp; first issued 04/02 01:33Z in 20260402-026; window read as 02/1300Z - 03/0800Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 026 DCC 04/02/2026 OPERATIONS PLAN
EVENT TIME: 02/0200 - AND LATER
TERMINAL ACTIVE:
UNTIL 0200	-LGA GROUND STOP
UNTIL 0200	-TEB GROUND STOP
UNTIL 0200	-EWR GROUND STOP
UNTIL 0215	-BWI GROUND STOP
UNTIL 0215	-DCA GROUND STOP
UNTIL 0259	-EWR GROUND DELAY PROGRAM
UNTIL 0359	-JFK GROUND DELAY PROGRAM
UNTIL 0359	-DCA GROUND DELAY PROGRAM
UNTIL 0559  	-LGA GROUND DELAY PROGRAM
TERMINAL PLANNED:
AFTER 0345	-MEM GROUND STOP POSSIBLE
AFTER 1200	-MSP GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1300	-LGA GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1300	-DCA GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1300	-ORD/MDW GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1500	-SFO GROUND STOP/DELAY PROGRAM PROBABLE
AFTER 1700	-EWR GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1800	-BOS GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1800	-JFK/HPN GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 2000	-MCO/TPA GROUND STOP POSSIBLE
```

Every advisory the linker could see for this element in the horizon:

```
20260402-001  sent 04/02 00:00Z  CDM GROUND STOP  LGA  GROUND STOP PERIOD 01/2348Z - 02/0100Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260402-003  sent 04/02 00:03Z  CDM GROUND STOP  LGA  GROUND STOP PERIOD 01/2348Z - 02/0100Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260402-010  sent 04/02 00:19Z  CDM GROUND STOP  LGA  GROUND STOP PERIOD 02/0003Z - 02/0100Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260402-017  sent 04/02 00:49Z  CDM GROUND STOP  LGA  GROUND STOP PERIOD 02/0033Z - 02/0200Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260402-027  sent 04/02 01:48Z  CDM GROUND STOP  LGA  GROUND STOP PERIOD 02/0134Z - 02/0300Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260402-031  sent 04/02 01:58Z  CDM GROUND DELAY PROGRAM CNX  LGA  GDP CNX PERIOD 02/0153Z - 02/0732Z
20260402-032  sent 04/02 02:01Z  CDM GROUND STOP  LGA  GROUND STOP PERIOD 02/0000Z - 02/0300Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260402-037  sent 04/02 02:33Z  CDM GROUND DELAY PROGRAM  LGA  CUMULATIVE PROGRAM PERIOD 02/0100Z - 02/0659Z
20260402-039  sent 04/02 02:38Z  CDM GROUND STOP  LGA  GROUND STOP PERIOD 02/0227Z - 02/0300Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260402-042  sent 04/02 02:54Z  CDM GROUND STOP  LGA  GROUND STOP PERIOD 02/0245Z - 02/0400Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260402-050  sent 04/02 03:39Z  CDM GROUND DELAY PROGRAM  LGA  CUMULATIVE PROGRAM PERIOD 02/0100Z - 02/0759Z
20260402-055  sent 04/02 05:49Z  CDM GROUND DELAY PROGRAM CNX  LGA  GDP CNX PERIOD 02/0549Z - 02/1834Z
20260402-165  sent 04/02 22:37Z  CDM GROUND STOP  LGA  GROUND STOP PERIOD 02/2224Z - 02/2315Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260402-169  sent 04/02 23:12Z  CDM GS CNX  LGA  GS CNX PERIOD 02/2307Z - 03/0007Z
20260403-003  sent 04/03 00:16Z  CDM GROUND STOP  LGA  GROUND STOP PERIOD 03/0002Z - 03/0100Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260403-007  sent 04/03 00:56Z  CDM GS CNX  LGA  GS CNX PERIOD 03/0051Z - 03/0204Z
```

Other advisories that name the element (not read by the linker):

```
20260402-038  sent 04/02 02:37Z  LGA AIRPORT ARRIVAL DELAYS
20260402-096  sent 04/02 13:32Z  LGA AIRPORT ARRIVAL DELAYS
```

**Derived outcome: ISSUED = 1**. CDM GROUND STOP sent 02/2237Z, period 02/2224Z - 02/2312Z.

Advisory that decides the outcome:

```
ATCSCC ADVZY 165 LGA/ZNY 04/02/2026 CDM GROUND STOP
CTL ELEMENT: LGA
ELEMENT TYPE: APT
ADL TIME: 2234Z
GROUND STOP PERIOD: 02/2224Z - 02/2315Z
DEP FACILITIES INCLUDED: (Manual) ZDC
PREVIOUS TOTAL, MAXIMUM, AVERAGE DELAYS: 0 / 0 / 0
NEW TOTAL, MAXIMUM, AVERAGE DELAYS: 229 / 41 / 33
PROBABILITY OF EXTENSION: MEDIUM
IMPACTING CONDITION: VOLUME / COMPACTED DEMAND
COMMENTS:
```

## 100. route-20260401-136

- Term: **LOW** (route:LOW); written as: `PROBABILITY OF EXTENSION: LOW`
- Element: DFW_VKTRY_PARTIAL; initiative: reroute; first issued 04/01 23:09Z in 20260401-136; window read as 01/2145Z - 02/0300Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 136 DCC 04/01/2026 ROUTE RQD /FL
NAME: DFW_VKTRY_PARTIAL
CONSTRAINED AREA: ZFW
REASON: WEATHER
INCLUDE TRAFFIC: KLAS/KPHX/KSAN/KTUS/ZAB/ZDV/ZLA/ZLC/ZOA/ZSE
DEPARTURES TO KDAL/KDFW
FACILITIES INCLUDED: ZAB/ZDV/ZFW/ZLA/ZLC/ZOA/ZSE
FLIGHT STATUS: ALL_FLIGHTS
VALID: ETD 012145 TO 020300
PROBABILITY OF EXTENSION: LOW
REMARKS: REPLACES ADVZY 114.  ROUTE RQD
ASSOCIATED RESTRICTIONS:
MODIFICATIONS: TIME EXTENDED
ROUTES: [route table not shown]
TMI ID: RRDCC527
```

Every advisory the linker could see for this element in the horizon:

```
20260402-012  sent 04/02 00:20Z  REROUTE CANCELLATION  DFW_VKTRY_PARTIAL
```

**Derived outcome: NOT EXTENDED (cancelled) = 0**. cancelled at 02/0020Z; stated end 02/0300Z.

Advisory that decides the outcome:

```
ATCSCC ADVZY 012 DCC 04/02/2026 REROUTE CANCELLATION
DFW_VKTRY_PARTIAL HAS BEEN CANCELLED.

REMARKS: REROUTE IS CANCELLED ONLY FOR FLIGHTS THAT ARE NOT AIRBORNE AS OF 0020Z
ASSOCIATED RESTRICTIONS:
```

## 101. route-20260523-016

- Term: **HIGH** (route:HIGH); written as: `PROBABILITY OF EXTENSION: HIGH`
- Element: NORTH_TO_DFW_DAL; initiative: reroute; first issued 05/23 09:29Z in 20260523-016; window read as 23/1000Z - 23/1500Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 016 DCC 05/23/2026 ROUTE RQD /FL
NAME: NORTH_TO_DFW_DAL
CONSTRAINED AREA: ZFW
REASON: WEATHER
INCLUDE TRAFFIC: CZY/KBUF/KCLE/KDTW/KROC/ZAU/ZID/ZKC/ZMP DEPARTURES
TO KDAL/KDFW
FACILITIES INCLUDED: CZY/ZAU/ZFW/ZID/ZKC/ZMP/ZOB
FLIGHT STATUS: ALL_FLIGHTS
VALID: ETD 231000 TO 231500
PROBABILITY OF EXTENSION: HIGH
REMARKS: BASED ON DFW SEEVR 1 SOUTH FLOW
ASSOCIATED RESTRICTIONS:
MODIFICATIONS:
ROUTES: [route table not shown]
TMI ID: RRDCC500
```

Every advisory the linker could see for this element in the horizon:

```
20260523-056  sent 05/23 14:40Z  ROUTE RQD /FL  NORTH_TO_DFW_DAL  VALID 23/1000Z - 23/1900Z  [PROBABILITY OF EXTENSION: HIGH]
20260523-066  sent 05/23 15:58Z  REROUTE CANCELLATION  NORTH_TO_DFW_DAL
```

**Derived outcome: EXTENDED = 1**. end 23/1500Z -> 23/1900Z (+240 min).

Advisory that decides the outcome:

```
ATCSCC ADVZY 056 DCC 05/23/2026 ROUTE RQD /FL
NAME: NORTH_TO_DFW_DAL
CONSTRAINED AREA: ZFW
REASON: WEATHER
INCLUDE TRAFFIC: ZAU/ZKC/ZMP DEPARTURES TO KDAL/KDFW
FACILITIES INCLUDED: ZAU/ZFW/ZKC/ZMP
FLIGHT STATUS: ALL_FLIGHTS
VALID: ETD 231000 TO 231900
PROBABILITY OF EXTENSION: HIGH
REMARKS: REPLACES ADZY 016.  EXTENDS TIME AND REMOVES ZOB/CZY/ZID
DEPTS.  DFW NORTH FLOW ARRIVAL STARS
ASSOCIATED RESTRICTIONS:
MODIFICATIONS:
ROUTES: [route table not shown]
TMI ID: RRDCC500
```

## 102. plan-20260525-051-DCA-gdp-AFTER1600

- Term: **EXPECTED** (plan:EXPECTED); written as: `AFTER 1600	-DCA GROUND DELAY PROGRAM EXPECTED`
- Element: DCA; initiative: gdp; first issued 05/25 13:44Z in 20260525-051; window read as 25/1600Z - 26/0800Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 051 DCC 05/25/2026 OPERATIONS PLAN
EVENT TIME: 25/1400 - AND LATER
TERMINAL ACTIVE:
UNTIL 1400	-DCA GROUND STOP
UNTIL 2059	-SFO GROUND DELAY PROGRAM
TERMINAL PLANNED:
UNTIL 1500	-ATL GROUND STOP POSSIBLE
UNTIL 1900	-JFK GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1600	-DCA GROUND DELAY PROGRAM EXPECTED
AFTER 1700	-TEB GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1700	-BOS GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1800	-CLT GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1900	-ATL GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 2000	-DEN GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 2100	-TPA/MCO GROUND STOP POSSIBLE
AFTER 2100	-SEA GROUND STOP/DELAY PROGRAM POSSIBLE
```

Every advisory the linker could see for this element in the horizon:

```
20260525-042  sent 05/25 12:31Z  CDM GROUND STOP  DCA  GROUND STOP PERIOD 25/1211Z - 25/1330Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260525-046  sent 05/25 13:29Z  CDM GROUND STOP  DCA  GROUND STOP PERIOD 25/1326Z - 25/1400Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260525-049  sent 05/25 13:40Z  CDM PROPOSED GROUND DELAY PROGRAM  DCA  ANTICIPATED CUMULATIVE PROGRAM PERIOD 25/1334Z - 26/0259Z
20260525-052  sent 05/25 13:49Z  CDM GROUND DELAY PROGRAM  DCA  CUMULATIVE PROGRAM PERIOD 25/1344Z - 26/0259Z
20260525-072  sent 05/25 16:46Z  CDM GROUND STOP  DCA  GROUND STOP PERIOD 25/1639Z - 25/1745Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260525-073  sent 05/25 17:01Z  CDM GROUND DELAY PROGRAM  DCA  CUMULATIVE PROGRAM PERIOD 25/1344Z - 26/0359Z
20260526-004  sent 05/26 00:22Z  CDM GROUND DELAY PROGRAM CNX  DCA  GDP CNX PERIOD 26/0021Z - 26/1228Z
```

Other advisories that name the element (not read by the linker):

```
20260525-036  sent 05/25 12:01Z  DCA AIRPORT BELOW USER MINS
20260525-047  sent 05/25 13:32Z  DCA AIRPORT DIVERSION RECOVERY ACTIVATED
```

**Derived outcome: ISSUED = 1**. CDM GROUND DELAY PROGRAM sent 25/1349Z, period 25/1344Z - 26/0022Z.

Advisory that decides the outcome:

```
ATCSCC ADVZY 052 DCA/ZDC 05/25/2026 CDM GROUND DELAY PROGRAM
CTL ELEMENT: DCA
ELEMENT TYPE: APT
ADL TIME: 1344Z
DELAY ASSIGNMENT MODE: UDP
ARRIVALS ESTIMATED FOR: 25/1344Z - 26/0259Z
CUMULATIVE PROGRAM PERIOD: 25/1344Z - 26/0259Z
PROGRAM RATE: 26/26/26/21/28/28/28/28/28/28/28/28/28/28
FLT INCL: ALL CONTIGUOUS US DEP
DEP SCOPE: (ALL+CZY_AP) ZLA ZAU ZLC ZTL ZDC ZNY ZHU ZJX ZFW ZOB ZDV
ZOA ZSE ZBW ZMA ZKC ZME ZID ZAB ZMP
CANADIAN DEP ARPTS INCLUDED: CYHZ CYOW CYUL CYYZ CYTZ CYQB
DELAY ASSIGNMENT TABLE APPLIES TO: ZDC
MAXIMUM DELAY: 137
AVERAGE DELAY: 46
IMPACTING CONDITION: WEATHER / LOW CEILINGS
COMMENTS: GROUND STOP CANCELED. ARR/DEP 01, LOW POP UP, BY STATUS
```

## 103. route-20260415-028

- Term: **MODERATE** (route:MODERATE); written as: `PROBABILITY OF EXTENSION: MODERATE`
- Element: NORTHEAST_TO_ORD; initiative: reroute; first issued 04/15 09:50Z in 20260415-028; window read as 15/1015Z - 15/1300Z
- Repeated in: 20260415-037

Source advisory:

```
ATCSCC ADVZY 028 DCC 04/15/2026 ROUTE RQD /FL
NAME: NORTHEAST_TO_ORD
CONSTRAINED AREA: ZOB/ZAU
REASON: WEATHER
INCLUDE TRAFFIC: KABE/KAVP/KJFK/KMDT/KPHL/ZBW/ZNY DEPARTURES TO KORD
FACILITIES INCLUDED: ZAU/ZBW/ZNY/ZOB
FLIGHT STATUS: ALL_FLIGHTS
VALID: ETD 151015 TO 151300
PROBABILITY OF EXTENSION: MODERATE
REMARKS:
ASSOCIATED RESTRICTIONS:
MODIFICATIONS:
ROUTES: [route table not shown]
TMI ID: RRDCC503
```

Every advisory the linker could see for this element in the horizon:

```
20260415-037  sent 04/15 11:31Z  ROUTE RQD /FL  NORTHEAST_TO_ORD  VALID 15/1015Z - 15/1300Z  [PROBABILITY OF EXTENSION: MODERATE]
20260415-046  sent 04/15 12:25Z  REROUTE CANCELLATION  NORTHEAST_TO_ORD
```

**Derived outcome: NOT EXTENDED (cancelled) = 0**. cancelled at 15/1225Z; stated end 15/1300Z.

Advisory that decides the outcome:

```
ATCSCC ADVZY 046 DCC 04/15/2026 REROUTE CANCELLATION
NORTHEAST_TO_ORD HAS BEEN CANCELLED.

REMARKS:
ASSOCIATED RESTRICTIONS:
```

## 104. plan-20260511-085-SFO-gs+gdp-AFTER0200

- Term: **EXPECTED** (plan:EXPECTED); written as: `AFTER 0200	-SFO GROUND STOP/DELAY PROGRAM EXPECTED`
- Element: SFO; initiative: gs/gdp; first issued 05/11 23:28Z in 20260511-085; window read as 12/0200Z - 12/0800Z
- Repeated in: 20260512-011

Source advisory:

```
ATCSCC ADVZY 085 DCC 05/11/2026 OPERATIONS PLAN
EVENT TIME: 12/0000 - AND LATER
TERMINAL ACTIVE:
NONE
TERMINAL PLANNED:
AFTER 0200	-SFO GROUND STOP/DELAY PROGRAM EXPECTED
AFTER 1300	-TEB GROUND STOP/DELAY PROGRAM/N93 PROBABLE
AFTER 1400	-SAN GROUND STOP POSSIBLE
AFTER 1500	-SFO GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1800	-ORD/MDW GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1800	-TPA/MCO GROUND STOP POSSIBLE
AFTER 1800	-MIA/FLL/PBI GROUND STOP POSSIBLE
```

Every advisory the linker could see for this element in the horizon:

```
20260511-082  sent 05/11 23:06Z  CDM GROUND DELAY PROGRAM CNX  SFO  GDP CNX PERIOD 11/2303Z - 12/0056Z
20260511-083  sent 05/11 23:14Z  CDM PROPOSED GROUND DELAY PROGRAM  SFO  ANTICIPATED CUMULATIVE PROGRAM PERIOD 12/0200Z - 12/0559Z
20260511-086  sent 05/11 23:45Z  CDM GROUND STOP  SFO  GROUND STOP PERIOD 11/2328Z - 12/0030Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260512-001  sent 05/12 00:07Z  CDM GROUND DELAY PROGRAM  SFO  CUMULATIVE PROGRAM PERIOD 12/0000Z - 12/0559Z
20260512-008  sent 05/12 04:25Z  CDM GROUND DELAY PROGRAM CNX  SFO  GDP CNX PERIOD 12/0422Z - 12/0758Z
```

Other advisories that name the element (not read by the linker):

```
20260511-076  sent 05/11 22:01Z  SFO AIRPORT SCHEDULING DELAYS
```

**Derived outcome: ISSUED = 1**. CDM GROUND DELAY PROGRAM sent 12/0007Z, period 12/0000Z - 12/0425Z.

Advisory that decides the outcome:

```
ATCSCC ADVZY 001 SFO/ZOA 05/12/2026 CDM GROUND DELAY PROGRAM
CTL ELEMENT: SFO
ELEMENT TYPE: APT
ADL TIME: 0004Z
DELAY ASSIGNMENT MODE: UDP
ARRIVALS ESTIMATED FOR: 12/0000Z - 12/0559Z
CUMULATIVE PROGRAM PERIOD: 12/0000Z - 12/0559Z
PROGRAM RATE: 36/36/36/36/32/36
FLT INCL: ALL CONTIGUOUS US DEP
DEP SCOPE: 1625
CANADIAN DEP ARPTS INCLUDED: CYEG CYVR CYYC
DELAY ASSIGNMENT TABLE APPLIES TO: ZOA
MAXIMUM DELAY: 113
AVERAGE DELAY: 38
IMPACTING CONDITION: OTHER / OTHER
COMMENTS: RUNWAY CONSTRUCTION AND PROCEDURAL COMPLIANCE. ARR/DEP
28L/28R. LOW POP-UPS. FROM STATUS, CANCEL GROUND STOP.
```

## 105. route-20260510-025

- Term: **MODERATE** (route:MODERATE); written as: `PROBABILITY OF EXTENSION: MODERATE`
- Element: FCA003:FLORIDA_TO_DALLAS; initiative: reroute; first issued 05/10 13:27Z in 20260510-025; window read as 10/1100Z - 10/1700Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 025 DCC 05/10/2026 FCA RQD
NAME: FCA003:FLORIDA_TO_DALLAS
CONSTRAINED AREA: ZFW/ZME
REASON: WEATHER
INCLUDE TRAFFIC: KMIA/KTPA/ZJX/ZMA DEPARTURES TO KDAL/KDFW
FACILITIES INCLUDED: ZFW/ZHU/ZJX/ZMA
FLIGHT STATUS: ALL_FLIGHTS
VALID: FCA ENTRY TIME FROM 101100 TO 101700
PROBABILITY OF EXTENSION: MODERATE
REMARKS: REPLACES ADVZY 016. SEE DYNAMIC LIST FOR UPDATES.
ASSOCIATED RESTRICTIONS:
MODIFICATIONS: EXTENDS END TIME.
ROUTES: [route table not shown]
TMI ID: RRDCC500
```

Every advisory the linker could see for this element in the horizon:

```
(none)
```

**Derived outcome: NOT EXTENDED (lapsed) = 0**. no later advisory moved the end past 10/1700Z.

No advisory decides the outcome (nothing qualifying was found).

## 106. route-20260501-081

- Term: **HIGH** (route:HIGH); written as: `PROBABILITY OF EXTENSION: HIGH`
- Element: FCA013:MIA_AND_SATS_VIA_DEEP_WATER; initiative: reroute; first issued 05/01 17:05Z in 20260501-081; window read as 01/2115Z - 02/0200Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 081 DCC 05/01/2026 FCA RQD
NAME: FCA013:MIA_AND_SATS_VIA_DEEP_WATER
CONSTRAINED AREA: ZJX/ZMA
REASON: OTHER
INCLUDE TRAFFIC: UNKN DEPARTURES TO 07FA/KHST/KMIA/KTMB/X51
FACILITIES INCLUDED: ZMA/ZNY
FLIGHT STATUS: ALL_FLIGHTS
VALID: FCA ENTRY TIME FROM 012115 TO 020200
PROBABILITY OF EXTENSION: HIGH
REMARKS: SEE DYNAMIC LIST FOR UPDATES. THIS ROUTE IS FOR
INTERNATIONAL ARRIVALS TO MIA AREA DUE TO SPECIAL OPS.
ASSOCIATED RESTRICTIONS:
MODIFICATIONS:
ROUTES: [route table not shown]
TMI ID: RRDCC516
```

Every advisory the linker could see for this element in the horizon:

```
20260502-008  sent 05/02 00:06Z  FCA RQD  FCA029:MIA_AND_SATS_VIA_DEEP_WATER  VALID 02/0200Z - 02/2315Z  [PROBABILITY OF EXTENSION: MODERATE]
```

**Derived outcome: EXTENDED = 1**. end 02/0200Z -> 02/2315Z (+1275 min), carried on as FCA029:MIA_AND_SATS_VIA_DEEP_WATER under TMI ID RRDCC528. Flags: continued_new_id.

Advisory that decides the outcome:

```
ATCSCC ADVZY 008 DCC 05/02/2026 FCA RQD
NAME: FCA029:MIA_AND_SATS_VIA_DEEP_WATER
CONSTRAINED AREA: ZJX/ZMA
REASON: OTHER
INCLUDE TRAFFIC: UNKN DEPARTURES TO 07FA/KHST/KMIA/KTMB/X51
FACILITIES INCLUDED: ZMA/ZNY/ZBW/CZY/CZU
FLIGHT STATUS: ALL_FLIGHTS
VALID: FCA ENTRY TIME FROM 020200 TO 022315
PROBABILITY OF EXTENSION: MODERATE
REMARKS: SEE DYNAMIC LIST FOR UPDATES. IMPLEMENTED DUE TO SPECIAL
OPERATIONS. THIS ROUTE IS FOR INTERNATIONAL ARRIVALS TO MIA
AREA.
ASSOCIATED RESTRICTIONS:
MODIFICATIONS:
ROUTES: [route table not shown]
TMI ID: RRDCC528
```

## 107. plan-20260403-064-SFO-gs+gdp-AFTER1700

- Term: **EXPECTED** (plan:EXPECTED); written as: `AFTER 1700	-SFO GROUND STOP/DELAY PROGRAM EXPECTED`
- Element: SFO; initiative: gs/gdp; first issued 04/03 13:44Z in 20260403-064; window read as 03/1700Z - 04/0800Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 064 DCC 04/03/2026 OPERATIONS PLAN
EVENT TIME: 03/1400 - AND LATER
TERMINAL ACTIVE:
NONE
TERMINAL PLANNED:
AFTER 1700	-SFO GROUND STOP/DELAY PROGRAM EXPECTED
AFTER 1800	-BOS GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1800	-LGA GROUND STOP/DELAY PROGRAM POSSIBLE
UNTIL 2000	-DEN GROUND STOP/DELAY PROGRAM EXPECTED
```

Every advisory the linker could see for this element in the horizon:

```
20260403-063  sent 04/03 13:38Z  CDM PROPOSED GROUND DELAY PROGRAM  SFO  ANTICIPATED CUMULATIVE PROGRAM PERIOD 03/1700Z - 04/0559Z
20260403-069  sent 04/03 14:01Z  CDM GROUND DELAY PROGRAM  SFO  CUMULATIVE PROGRAM PERIOD 03/1700Z - 04/0559Z
20260404-021  sent 04/04 04:51Z  CDM GROUND DELAY PROGRAM CNX  SFO  GDP CNX PERIOD 04/0446Z - 04/1722Z
```

**Derived outcome: ISSUED = 1**. CDM GROUND DELAY PROGRAM sent 03/1401Z, period 03/1700Z - 04/0451Z.

Advisory that decides the outcome:

```
ATCSCC ADVZY 069 SFO/ZOA 04/03/2026 CDM GROUND DELAY PROGRAM
CTL ELEMENT: SFO
ELEMENT TYPE: APT
ADL TIME: 1354Z
DELAY ASSIGNMENT MODE: UDP
ARRIVALS ESTIMATED FOR: 03/1700Z - 04/0559Z
CUMULATIVE PROGRAM PERIOD: 03/1700Z - 04/0559Z
PROGRAM RATE: 36
FLT INCL: ALL CONTIGUOUS US DEP
DEP SCOPE: (ALL+CZV_AP) ZLA ZAU ZLC ZTL ZDC ZNY ZHU ZJX ZFW ZOB ZDV
ZOA ZSE ZBW ZMA ZKC ZME ZID ZAB ZMP
CANADIAN DEP ARPTS INCLUDED: CYEG CYVR CYYC
DELAY ASSIGNMENT TABLE APPLIES TO: ZOA
MAXIMUM DELAY: 84
AVERAGE DELAY: 21
IMPACTING CONDITION: OTHER / OTHER
COMMENTS: ARR/DEPT 28L/28R. PROCEDURAL COMPLIANCE AND RWY
CONSTRUCTION. LOW POP UP.
```

## 108. route-20260520-116

- Term: **MODERATE** (route:MODERATE); written as: `PROBABILITY OF EXTENSION: MODERATE`
- Element: NE_TO_FLORIDA_VIA_Q97_2_PARTIAL; initiative: reroute; first issued 05/20 19:07Z in 20260520-116; window read as 20/1930Z - 20/2300Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 116 DCC 05/20/2026 ROUTE RQD /FL
NAME: NE_TO_FLORIDA_VIA_Q97_2_PARTIAL
CONSTRAINED AREA: ZDC
REASON: WEATHER
INCLUDE TRAFFIC: KBWI/KDCA/KIAD/KJFK/KORF/KPHF/KPHL/ZBW/ZNY
DEPARTURES TO
KAPF/KFMY/KJAX/KMCO/KMKY/KPIE/KRSW/KSAV/KSRQ/KTPA
FACILITIES INCLUDED: ZBW/ZDC/ZJX/ZMA/ZNY
FLIGHT STATUS: ALL_FLIGHTS
VALID: ETD 201930 TO 202300
PROBABILITY OF EXTENSION: MODERATE
REMARKS: AR AND Y ROUTES ARE EXEMPT.
ASSOCIATED RESTRICTIONS:
MODIFICATIONS:
ROUTES: [route table not shown]
TMI ID: RRDCC521
```

Every advisory the linker could see for this element in the horizon:

```
20260520-176  sent 05/20 22:51Z  ROUTE RQD /FL  NE_TO_FLORIDA_VIA_Q97_2_PARTIAL  VALID 20/1930Z - 21/0200Z  [PROBABILITY OF EXTENSION: MODERATE]
```

**Derived outcome: EXTENDED = 1**. end 20/2300Z -> 21/0200Z (+180 min).

Advisory that decides the outcome:

```
ATCSCC ADVZY 176 DCC 05/20/2026 ROUTE RQD /FL
NAME: NE_TO_FLORIDA_VIA_Q97_2_PARTIAL
CONSTRAINED AREA: ZDC
REASON: WEATHER
INCLUDE TRAFFIC: KBWI/KDCA/KIAD/KJFK/KORF/KPHF/KPHL/ZBW/ZNY
DEPARTURES TO
KAPF/KFMY/KJAX/KMCO/KMKY/KPIE/KRSW/KSAV/KSRQ/KTPA
FACILITIES INCLUDED: ZBW/ZDC/ZJX/ZMA/ZNY
FLIGHT STATUS: ALL_FLIGHTS
VALID: ETD 201930 TO 210200
PROBABILITY OF EXTENSION: MODERATE
REMARKS: REPLACES ADVZY 116. AR AND Y ROUTES ARE EXEMPT.
ASSOCIATED RESTRICTIONS:
MODIFICATIONS: TIME EXTENDED
ROUTES: [route table not shown]
TMI ID: RRDCC521
```

## 109. route-20260522-053

- Term: **HIGH** (route:HIGH); written as: `PROBABILITY OF EXTENSION: HIGH`
- Element: FCA006:ZBW_TO_ZDC_VIA_ATR; initiative: reroute; first issued 05/22 14:16Z in 20260522-053; window read as 22/1700Z - 23/0200Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 053 DCC 05/22/2026 FCA RQD
NAME: FCA006:ZBW_TO_ZDC_VIA_ATR
CONSTRAINED AREA: ZDC/ZNY
REASON: OTHER
INCLUDE TRAFFIC: KACK/KBOS/KFOK/KHWV/KHYA/KISP/KJPX/KMTP/KMVY
DEPARTURES TO KADW/KBWI/KDCA/KMTN
FACILITIES INCLUDED: ZBW/ZDC/ZNY
FLIGHT STATUS: ALL_FLIGHTS
VALID: FCA ENTRY TIME FROM 221700 TO 230200
PROBABILITY OF EXTENSION: HIGH
REMARKS: SEE DYNAMIC LIST FOR UPDATES. IMPLEMENTED DUE TO SPECIAL
OPERATIONS.
ASSOCIATED RESTRICTIONS:
MODIFICATIONS:
ROUTES: [route table not shown]
TMI ID: RRDCC506
```

Every advisory the linker could see for this element in the horizon:

```
20260522-078  sent 05/22 17:25Z  FCA RQD  FCA006:ZBW_TO_ZDC_VIA_ATR  VALID 22/1700Z - 22/2200Z  [PROBABILITY OF EXTENSION: LOW]
```

**Derived outcome: NOT EXTENDED (lapsed) = 0**. no later advisory moved the end past 23/0200Z. Flags: shortened.

No advisory decides the outcome (nothing qualifying was found).

## 110. gs-20260517-081

- Term: **MEDIUM** (gs:MEDIUM); written as: `PROBABILITY OF EXTENSION: MEDIUM`
- Element: ATL; initiative: gs; first issued 05/17 21:36Z in 20260517-081; window read as 17/2124Z - 17/2245Z
- Repeated in: 20260517-082

Source advisory:

```
ATCSCC ADVZY 081 ATL/ZTL 05/17/2026 CDM GROUND STOP
CTL ELEMENT: ATL
ELEMENT TYPE: APT
ADL TIME: 2134Z
GROUND STOP PERIOD: 17/2124Z - 17/2245Z
DEP FACILITIES INCLUDED: (1stTier) ZTL ZDC ZHU ZJX ZME ZID
PREVIOUS TOTAL, MAXIMUM, AVERAGE DELAYS: 0 / 0 / 0
NEW TOTAL, MAXIMUM, AVERAGE DELAYS: 2804 / 133 / 43
PROBABILITY OF EXTENSION: MEDIUM
IMPACTING CONDITION: WEATHER / THUNDERSTORMS
COMMENTS:
```

Every advisory the linker could see for this element in the horizon:

```
20260517-082  sent 05/17 21:38Z  CDM GROUND STOP  ATL  GROUND STOP PERIOD 17/2126Z - 17/2245Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260517-085  sent 05/17 22:45Z  CDM GS CNX  ATL  GS CNX PERIOD 17/2243Z - 18/0451Z
```

Other advisories that name the element (not read by the linker):

```
20260517-084  sent 05/17 22:17Z  ATL CDRS_FYI
```

**Derived outcome: NOT EXTENDED (cancelled) = 0**. cancelled at 17/2245Z; stated end 17/2245Z.

Advisory that decides the outcome:

```
ATCSCC ADVZY 085 ATL/ZTL 05/17/2026 CDM GS CNX
CTL ELEMENT: ATL
ELEMENT TYPE: APT
ADL TIME: 2243Z
GS CNX PERIOD: 17/2243Z - 18/0451Z
COMMENTS:
```

## 111. route-20260424-004

- Term: **MODERATE** (route:MODERATE); written as: `PROBABILITY OF EXTENSION: MODERATE`
- Element: FCA014:MIDWEST_PNH_WEST_PARTIAL; initiative: reroute; first issued 04/24 00:55Z in 20260424-004; window read as 23/2200Z - 24/0400Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 004 DCC 04/24/2026 FCA RQD
NAME: FCA014:MIDWEST_PNH_WEST_PARTIAL
CONSTRAINED AREA: ZKC/ZMP
REASON: WEATHER
INCLUDE TRAFFIC: ZAU/ZID/ZOB DEPARTURES TO KLAS/KLAX/KPHX/KSAN/KSFO
FACILITIES INCLUDED: ZAB/ZAU/ZDV/ZFW/ZID/ZKC/ZLA/ZLC/ZOA/ZOB
FLIGHT STATUS: ALL_FLIGHTS
VALID: FCA ENTRY TIME FROM 232200 TO 240400
PROBABILITY OF EXTENSION: MODERATE
REMARKS: REPLACES ADVZY 096. SEE DYNAMIC LIST FOR UPDATES.
ASSOCIATED RESTRICTIONS:
MODIFICATIONS: TIME EXTENDED
ROUTES: [route table not shown]
TMI ID: RRDCC507
```

Every advisory the linker could see for this element in the horizon:

```
(none)
```

**Derived outcome: NOT EXTENDED (lapsed) = 0**. no later advisory moved the end past 24/0400Z.

No advisory decides the outcome (nothing qualifying was found).

## 112. route-20260520-100

- Term: **NONE** (route:NONE); written as: `PROBABILITY OF EXTENSION: NONE`
- Element: CAN_KENPA_WEST_2_PARTIAL; initiative: reroute; first issued 05/20 18:07Z in 20260520-100; window read as 20/2000Z - 21/0200Z
- Repeated in: 20260520-114

Source advisory:

```
ATCSCC ADVZY 100 DCC 05/20/2026 ROUTE RQD /FL
NAME: CAN_KENPA_WEST_2_PARTIAL
CONSTRAINED AREA: ZOB
REASON: WEATHER
INCLUDE TRAFFIC: KEWR/KHPN/KJFK/KLGA/KTEB/ZBW DEPARTURES TO
KPDX/KSEA
FACILITIES INCLUDED: CZY/ZBW/ZLC/ZMP/ZNY/ZSE
FLIGHT STATUS: ALL_FLIGHTS
VALID: ETD 202000 TO 210200
PROBABILITY OF EXTENSION: NONE
REMARKS:
ASSOCIATED RESTRICTIONS: 15 MIT VIA NOVON
MODIFICATIONS:
ROUTES: [route table not shown]
TMI ID: RRDCC515
```

Every advisory the linker could see for this element in the horizon:

```
20260520-114  sent 05/20 18:56Z  ROUTE RQD /FL  CAN_KENPA_WEST_2_PARTIAL  VALID 20/2000Z - 21/0200Z  [PROBABILITY OF EXTENSION: NONE]
```

**Derived outcome: NOT EXTENDED (lapsed) = 0**. no later advisory moved the end past 21/0200Z.

No advisory decides the outcome (nothing qualifying was found).

## 113. plan-20260403-053-DEN-gs+gdp-UNTIL2000

- Term: **PROBABLE** (plan:PROBABLE); written as: `UNTIL 2000	-DEN GROUND STOP/DELAY PROGRAM PROBABLE`
- Element: DEN; initiative: gs/gdp; first issued 04/03 11:55Z in 20260403-053; window read as 03/1155Z - 03/2000Z
- Repeated in: 20260403-064 20260403-076

Source advisory:

```
ATCSCC ADVZY 053 DCC 04/03/2026 OPERATIONS PLAN
EVENT TIME: 03/1200 - AND LATER
TERMINAL ACTIVE:
NONE
TERMINAL PLANNED:
AFTER 1500	-SFO GROUND STOP/DELAY PROGRAM PROBABLE
AFTER 1800	-BOS GROUND STOP/DELAY PROGRAM POSSIBLE
UNTIL 2000	-DEN GROUND STOP/DELAY PROGRAM PROBABLE
UNTIL 0000	-LGA GROUND STOP/DELAY PROGRAM POSSIBLE
```

Every advisory the linker could see for this element in the horizon:

```
20260403-057  sent 04/03 12:38Z  CDM GROUND STOP  DEN  GROUND STOP PERIOD 03/1224Z - 03/1345Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260403-060  sent 04/03 13:09Z  CDM GS CNX  DEN  GS CNX PERIOD 03/1307Z - 03/1754Z
20260403-070  sent 04/03 14:07Z  CDM GROUND STOP  DEN  GROUND STOP PERIOD 03/1352Z - 03/1500Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260403-073  sent 04/03 14:59Z  CDM GS CNX  DEN  GS CNX PERIOD 03/1457Z - 03/1903Z
```

Other advisories that name the element (not read by the linker):

```
20260403-054  sent 04/03 11:59Z  DEN AIRPORT ARRIVAL DELAYS
20260403-055  sent 04/03 11:59Z  DEN AIRPORT SCHEDULING DELAYS
```

**Derived outcome: ISSUED = 1**. CDM GROUND STOP sent 03/1238Z, period 03/1224Z - 03/1309Z. Flags: term_changed.

Advisory that decides the outcome:

```
ATCSCC ADVZY 057 DEN/ZDV 04/03/2026 CDM GROUND STOP
CTL ELEMENT: DEN
ELEMENT TYPE: APT
ADL TIME: 1234Z
GROUND STOP PERIOD: 03/1224Z - 03/1345Z
DEP FACILITIES INCLUDED: (2ndTier) ZLA ZAU ZLC ZHU ZFW ZOB ZDV ZOA
ZSE ZKC ZME ZID ZAB ZMP
PREVIOUS TOTAL, MAXIMUM, AVERAGE DELAYS: 0 / 0 / 0
NEW TOTAL, MAXIMUM, AVERAGE DELAYS: 2807 / 77 / 35
PROBABILITY OF EXTENSION: MEDIUM
IMPACTING CONDITION: WEATHER / WIND
COMMENTS:
```

## 114. route-20260530-061

- Term: **LOW** (route:LOW); written as: `PROBABILITY OF EXTENSION: LOW`
- Element: FCA011:DEN_GCK_2_PARTIAL; initiative: reroute; first issued 05/30 19:54Z in 20260530-061; window read as 30/2100Z - 31/0200Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 061 DCC 05/30/2026 FCA RQD
NAME: FCA011:DEN_GCK_2_PARTIAL
CONSTRAINED AREA: ZDV
REASON: WEATHER
INCLUDE TRAFFIC: KCLT/KMIA/KTPA/ZFW/ZHU/ZJX/ZMA/ZTL DEPARTURES TO
KDEN
FACILITIES INCLUDED: ZAB/ZDV/ZFW/ZHU/ZJX/ZMA/ZME/ZTL
FLIGHT STATUS: ALL_FLIGHTS
VALID: FCA ENTRY TIME FROM 302100 TO 310200
PROBABILITY OF EXTENSION: LOW
REMARKS: SEE DYNAMIC LIST FOR UPDATES.
ASSOCIATED RESTRICTIONS:
MODIFICATIONS:
ROUTES: [route table not shown]
TMI ID: RRDCC505
```

Every advisory the linker could see for this element in the horizon:

```
20260531-004  sent 05/31 00:31Z  REROUTE CANCELLATION  FCA011:DEN_GCK_2_PARTIAL
```

**Derived outcome: NOT EXTENDED (cancelled) = 0**. cancelled at 31/0031Z; stated end 31/0200Z.

Advisory that decides the outcome:

```
ATCSCC ADVZY 004 DCC 05/31/2026 REROUTE CANCELLATION
FCA011:DEN_GCK_2_PARTIAL HAS BEEN CANCELLED.

REMARKS:
ASSOCIATED RESTRICTIONS:
```

## 115. gs-20260507-063

- Term: **MEDIUM** (gs:MEDIUM); written as: `PROBABILITY OF EXTENSION: MEDIUM`
- Element: LGA; initiative: gs; first issued 05/07 18:21Z in 20260507-063; window read as 07/1805Z - 07/1930Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 063 LGA/ZNY 05/07/2026 CDM GROUND STOP
CTL ELEMENT: LGA
ELEMENT TYPE: APT
ADL TIME: 1815Z
GROUND STOP PERIOD: 07/1805Z - 07/1930Z
DEP FACILITIES INCLUDED: (1stTier) ZDC ZNY ZOB ZBW
PREVIOUS TOTAL, MAXIMUM, AVERAGE DELAYS: 0 / 0 / 0
NEW TOTAL, MAXIMUM, AVERAGE DELAYS: 504 / 80 / 46
PROBABILITY OF EXTENSION: MEDIUM
IMPACTING CONDITION: WEATHER / WIND
COMMENTS: COMPRESSION IN FINAL
```

Every advisory the linker could see for this element in the horizon:

```
20260507-066  sent 05/07 19:02Z  CDM GS CNX  LGA  GS CNX PERIOD 07/1900Z - 07/2048Z
```

Other advisories that name the element (not read by the linker):

```
20260507-064  sent 05/07 18:32Z  LGA AIRPORT ARRIVAL DELAYS
```

**Derived outcome: NOT EXTENDED (cancelled) = 0**. cancelled at 07/1902Z; stated end 07/1930Z.

Advisory that decides the outcome:

```
ATCSCC ADVZY 066 LGA/ZNY 05/07/2026 CDM GS CNX
CTL ELEMENT: LGA
ELEMENT TYPE: APT
ADL TIME: 1900Z
GS CNX PERIOD: 07/1900Z - 07/2048Z
COMMENTS: NO FURTHER INITATIVES. OVERAGES MANAGED INTERNALLY
```

## 116. gs-20260402-016

- Term: **MEDIUM** (gs:MEDIUM); written as: `PROBABILITY OF EXTENSION: MEDIUM`
- Element: EWR; initiative: gs; first issued 04/02 00:48Z in 20260402-016; window read as 02/0034Z - 02/0200Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 016 EWR/ZNY 04/02/2026 CDM GROUND STOP
CTL ELEMENT: EWR
ELEMENT TYPE: APT
ADL TIME: 0044Z
GROUND STOP PERIOD: 02/0034Z - 02/0200Z
CUMULATIVE PROGRAM PERIOD: 01/2100Z - 02/0259Z
DEP FACILITIES INCLUDED: (Manual) ZDC
PREVIOUS TOTAL, MAXIMUM, AVERAGE DELAYS: 525 / 164 / 105
NEW TOTAL, MAXIMUM, AVERAGE DELAYS: 805 / 224 / 161
PROBABILITY OF EXTENSION: MEDIUM
IMPACTING CONDITION: WEATHER / THUNDERSTORMS
COMMENTS:
```

Every advisory the linker could see for this element in the horizon:

```
20260402-029  sent 04/02 01:49Z  CDM GROUND STOP  EWR  GROUND STOP PERIOD 02/0138Z - 02/0300Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260402-043  sent 04/02 02:56Z  CDM GROUND STOP  EWR  GROUND STOP PERIOD 02/0244Z - 02/0400Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260402-051  sent 04/02 03:58Z  CDM GROUND STOP  EWR  GROUND STOP PERIOD 02/0340Z - 02/0530Z  [PROBABILITY OF EXTENSION: MEDIUM]
```

**Derived outcome: EXTENDED = 1**. end 02/0200Z -> 02/0300Z (+60 min).

Advisory that decides the outcome:

```
ATCSCC ADVZY 029 EWR/ZNY 04/02/2026 CDM GROUND STOP
CTL ELEMENT: EWR
ELEMENT TYPE: APT
ADL TIME: 0148Z
GROUND STOP PERIOD: 02/0138Z - 02/0300Z
CUMULATIVE PROGRAM PERIOD: 01/2100Z - 02/0259Z
DEP FACILITIES INCLUDED: (Manual) ZDC
PREVIOUS TOTAL, MAXIMUM, AVERAGE DELAYS: 614 / 224 / 88
NEW TOTAL, MAXIMUM, AVERAGE DELAYS: 1046 / 284 / 149
PROBABILITY OF EXTENSION: MEDIUM
IMPACTING CONDITION: WEATHER / THUNDERSTORMS
COMMENTS: LACK OF ROUTE
```

## 117. route-20260410-022

- Term: **LOW** (route:LOW); written as: `PROBABILITY OF EXTENSION: LOW`
- Element: FCA003:LAKE_ERIE_WEST_PARTIAL; initiative: reroute; first issued 04/10 11:13Z in 20260410-022; window read as 10/1100Z - 10/1500Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 022 DCC 04/10/2026 FCA RQD
NAME: FCA003:LAKE_ERIE_WEST_PARTIAL
CONSTRAINED AREA: CZY
REASON: OTHER
INCLUDE TRAFFIC: ZNY DEPARTURES TO
KFNT/KMBS/KMKE/KMSP/KORD/ZAB/ZAU/ZDV/ZKC/ZLA/ZLC/ZM
P/ZOA/ZSE
FACILITIES INCLUDED: ZAB/ZAU/ZDV/ZKC/ZLA/ZLC/ZMP/ZNY/ZOA/ZOB/ZSE
FLIGHT STATUS: ALL_FLIGHTS
VALID: FCA ENTRY TIME FROM 101100 TO 101500
PROBABILITY OF EXTENSION: LOW
REMARKS: ***REPLACES ADVZY 015***
SEE DYNAMIC LIST FOR UPDATES. SEA AND ZAN LTFC EXEMPT FROM
ROUTE. IMPLEMENTED DUE TO REDUCED SYSTEM CAPACITY IN CZY.
ASSOCIATED RESTRICTIONS:
MODIFICATIONS: END TIME AMENDED
ROUTES: [route table not shown]
TMI ID: RRDCC501
```

Every advisory the linker could see for this element in the horizon:

```
(none)
```

**Derived outcome: NOT EXTENDED (lapsed) = 0**. no later advisory moved the end past 10/1500Z.

No advisory decides the outcome (nothing qualifying was found).

## 118. gs-20260518-121

- Term: **HIGH** (gs:HIGH); written as: `PROBABILITY OF EXTENSION: HIGH`
- Element: DTW; initiative: gs; first issued 05/18 20:16Z in 20260518-121; window read as 18/2015Z - 18/2145Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 121 DTW/ZOB 05/18/2026 CDM GROUND STOP
CTL ELEMENT: DTW
ELEMENT TYPE: APT
ADL TIME: 2015Z
GROUND STOP PERIOD: 18/2015Z - 18/2145Z
DEP FACILITIES INCLUDED: (Manual) ZAU ZDC ZNY ZOB ZBW ZID ZMP  CYHZ
CYOW CYUL CYYZ
PREVIOUS TOTAL, MAXIMUM, AVERAGE DELAYS: 0 / 0 / 0
NEW TOTAL, MAXIMUM, AVERAGE DELAYS: 902 / 91 / 35
PROBABILITY OF EXTENSION: HIGH
IMPACTING CONDITION: WEATHER / THUNDERSTORMS
COMMENTS: LINE OF TSTMS APPROACHING FROM WEST. FACILITIES EAST OF DTW
CAN EXPECT TO REMAIN IN STOP AFTER 2145Z
```

Every advisory the linker could see for this element in the horizon:

```
20260518-139  sent 05/18 21:39Z  CDM GROUND STOP  DTW  GROUND STOP PERIOD 18/2126Z - 18/2245Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260518-144  sent 05/18 22:13Z  CDM GROUND STOP  DTW  GROUND STOP PERIOD 18/2126Z - 18/2245Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260518-146  sent 05/18 22:40Z  CDM GS CNX  DTW  GS CNX PERIOD 18/2238Z - 19/0016Z
```

Other advisories that name the element (not read by the linker):

```
20260518-134  sent 05/18 21:21Z  DTW AIRPORT ARRIVAL DELAYS
```

**Derived outcome: EXTENDED = 1**. end 18/2145Z -> 18/2245Z (+60 min).

Advisory that decides the outcome:

```
ATCSCC ADVZY 139 DTW/ZOB 05/18/2026 CDM GROUND STOP
CTL ELEMENT: DTW
ELEMENT TYPE: APT
ADL TIME: 2136Z
GROUND STOP PERIOD: 18/2126Z - 18/2245Z
DEP FACILITIES INCLUDED: (Manual) ZDC ZID
PREVIOUS TOTAL, MAXIMUM, AVERAGE DELAYS: 191 / 66 / 11
NEW TOTAL, MAXIMUM, AVERAGE DELAYS: 921 / 126 / 54
PROBABILITY OF EXTENSION: MEDIUM
IMPACTING CONDITION: WEATHER / THUNDERSTORMS
COMMENTS: GROUND STOP EXTENDED FOR ZID AND ZDC.
```

## 119. gs-20260502-087

- Term: **MEDIUM** (gs:MEDIUM); written as: `PROBABILITY OF EXTENSION: MEDIUM`
- Element: TPA; initiative: gs; first issued 05/02 19:05Z in 20260502-087; window read as 02/1752Z - 02/2030Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 087 TPA/ZMA 05/02/2026 CDM GROUND STOP
CTL ELEMENT: TPA
ELEMENT TYPE: APT
ADL TIME: 1904Z
GROUND STOP PERIOD: 02/1752Z - 02/2030Z
DEP FACILITIES INCLUDED: (Manual) ZTL ZDC ZHU ZJX ZMA
PREVIOUS TOTAL, MAXIMUM, AVERAGE DELAYS: 392 / 143 / 30
NEW TOTAL, MAXIMUM, AVERAGE DELAYS: 1282 / 203 / 99
PROBABILITY OF EXTENSION: MEDIUM
IMPACTING CONDITION: WEATHER / THUNDERSTORMS
COMMENTS:
```

Every advisory the linker could see for this element in the horizon:

```
20260502-095  sent 05/02 20:30Z  CDM GROUND STOP  TPA  GROUND STOP PERIOD 02/2010Z - 02/2130Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260502-104  sent 05/02 21:24Z  CDM GROUND STOP  TPA  GROUND STOP PERIOD 02/2010Z - 02/2230Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260502-115  sent 05/02 22:20Z  CDM GS CNX  TPA  GS CNX PERIOD 02/2219Z - 02/2332Z
```

**Derived outcome: EXTENDED = 1**. end 02/2030Z -> 02/2130Z (+60 min).

Advisory that decides the outcome:

```
ATCSCC ADVZY 095 TPA/ZMA 05/02/2026 CDM GROUND STOP
CTL ELEMENT: TPA
ELEMENT TYPE: APT
ADL TIME: 2025Z
GROUND STOP PERIOD: 02/2010Z - 02/2130Z
DEP FACILITIES INCLUDED: (Internal) ZMA
PREVIOUS TOTAL, MAXIMUM, AVERAGE DELAYS: 96 / 96 / 12
NEW TOTAL, MAXIMUM, AVERAGE DELAYS: 370 / 156 / 46
PROBABILITY OF EXTENSION: MEDIUM
IMPACTING CONDITION: WEATHER / THUNDERSTORMS
COMMENTS: SCOPE REDUCED TO ZMA ONLY.
```

## 120. route-20260501-082

- Term: **HIGH** (route:HIGH); written as: `PROBABILITY OF EXTENSION: HIGH`
- Element: FCA014:NORTH_TO_FLL_AREA; initiative: reroute; first issued 05/01 17:06Z in 20260501-082; window read as 01/2115Z - 02/0200Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 082 DCC 05/01/2026 FCA RQD
NAME: FCA014:NORTH_TO_FLL_AREA
CONSTRAINED AREA: ZJX/ZMA
REASON: OTHER
INCLUDE TRAFFIC: CZU/CZY/KACY/KALN/KBHM/KBLV/KBMI/KDET/KDTW/KFAY/KFN
T/KILM/KJFK/KLAN/KMBS/KMGM/KORF/KPHL/KPIA/KPTK/KRDU
/KSBY/KSOP/KSPI/KSTL/KSUS/KYIP/ZAU/ZBW/ZDC/ZDV/ZID/
ZKC/ZME/ZMP/ZNY/ZOB/ZTL DEPARTURES TO KFLL/KOPF
FACILITIES INCLUDED: CZU/CZY/ZAU/ZBW/ZDC/ZDV/ZID/ZJX/ZKC/ZMA/ZME/ZMP
/ZNY/ZOB/ZTL
FLIGHT STATUS: ALL_FLIGHTS
VALID: FCA ENTRY TIME FROM 012115 TO 020200
PROBABILITY OF EXTENSION: HIGH
REMARKS: SEE DYNAMIC LIST FOR UPDATES. IMPLEMENTED DUE TO SPECIAL
OPERATIONS
ASSOCIATED RESTRICTIONS:
MODIFICATIONS:
ROUTES: [route table not shown]
TMI ID: RRDCC517
```

Every advisory the linker could see for this element in the horizon:

```
20260502-009  sent 05/02 00:06Z  FCA RQD  FCA031:NORTH_TO_FLL_AREA  VALID 02/0200Z - 02/2315Z  [PROBABILITY OF EXTENSION: MODERATE]
```

**Derived outcome: EXTENDED = 1**. end 02/0200Z -> 02/2315Z (+1275 min), carried on as FCA031:NORTH_TO_FLL_AREA under TMI ID RRDCC529. Flags: continued_new_id.

Advisory that decides the outcome:

```
ATCSCC ADVZY 009 DCC 05/02/2026 FCA RQD
NAME: FCA031:NORTH_TO_FLL_AREA
CONSTRAINED AREA: ZJX/ZMA
REASON: OTHER
INCLUDE TRAFFIC: CZU/CZY/KACY/KALN/KBHM/KBLV/KBMI/KDET/KDTW/KFAY/KFN
T/KILM/KJFK/KLAN/KMBS/KMGM/KORF/KPHL/KPIA/KPTK/KRDU
/KSBY/KSOP/KSPI/KSTL/KSUS/KYIP/ZAU/ZBW/ZDC/ZDV/ZID/
ZKC/ZME/ZMP/ZNY/ZOB/ZTL DEPARTURES TO KFLL/KOPF
FACILITIES INCLUDED: CZU/CZY/ZAU/ZBW/ZDC/ZDV/ZID/ZJX/ZKC/ZMA/ZME/ZMP
/ZNY/ZOB/ZTL
FLIGHT STATUS: ALL_FLIGHTS
VALID: FCA ENTRY TIME FROM 020200 TO 022315
PROBABILITY OF EXTENSION: MODERATE
REMARKS: SEE DYNAMIC LIST FOR UPDATES. IMPLEMENTED DUE TO SPECIAL
OPERATIONS.
ASSOCIATED RESTRICTIONS:
MODIFICATIONS:
ROUTES: [route table not shown]
TMI ID: RRDCC529
```

## 121. route-20260502-005

- Term: **MODERATE** (route:MODERATE); written as: `PROBABILITY OF EXTENSION: MODERATE`
- Element: FCA026:GA_PROPS_TO_MIA_AND_SATS; initiative: reroute; first issued 05/02 00:05Z in 20260502-005; window read as 02/0200Z - 02/2315Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 005 DCC 05/02/2026 FCA RQD
NAME: FCA026:GA_PROPS_TO_MIA_AND_SATS
CONSTRAINED AREA: ZJX/ZMA
REASON: OTHER
INCLUDE TRAFFIC: UNKN DEPARTURES TO
07FA/KBCT/KFLL/KHST/KHWO/KMIA/KOPF/KTMB/X51
FACILITIES INCLUDED: ZJX/ZMA/ZTL/ZDC/ZID/ZME/ZFW/ZHU
FLIGHT STATUS: ALL_FLIGHTS
VALID: FCA ENTRY TIME FROM 020200 TO 022315
PROBABILITY OF EXTENSION: MODERATE
REMARKS: SEE DYNAMIC LIST FOR UPDATES. IMPLEMENTED DUE TO SPECIAL
OPERATIONS.
ASSOCIATED RESTRICTIONS:
MODIFICATIONS:
ROUTES: [route table not shown]
TMI ID: RRDCC525
```

Every advisory the linker could see for this element in the horizon:

```
(none)
```

**Derived outcome: NOT EXTENDED (lapsed) = 0**. no later advisory moved the end past 02/2315Z.

No advisory decides the outcome (nothing qualifying was found).

## 122. route-20260527-059

- Term: **MODERATE** (route:MODERATE); written as: `PROBABILITY OF EXTENSION: MODERATE`
- Element: DFW_VKTRY_PARTIAL; initiative: reroute; first issued 05/27 14:39Z in 20260527-059; window read as 27/1430Z - 27/1900Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 059 DCC 05/27/2026 ROUTE RQD /FL
NAME: DFW_VKTRY_PARTIAL
CONSTRAINED AREA: ZFW
REASON: WEATHER
INCLUDE TRAFFIC: ZAB/ZLA/ZOA DEPARTURES TO KDAL/KDFW
FACILITIES INCLUDED: ZAB/ZDV/ZFW/ZLA/ZLC/ZOA
FLIGHT STATUS: ALL_FLIGHTS
VALID: ETD 271430 TO 271900
PROBABILITY OF EXTENSION: MODERATE
REMARKS:
ASSOCIATED RESTRICTIONS:
MODIFICATIONS:
ROUTES: [route table not shown]
TMI ID: RRDCC509
```

Every advisory the linker could see for this element in the horizon:

```
20260527-084  sent 05/27 18:15Z  ROUTE RQD /FL  DFW_VKTRY_PARTIAL  VALID 27/1430Z - 27/2200Z  [PROBABILITY OF EXTENSION: MODERATE]
20260527-089  sent 05/27 18:39Z  ROUTE RQD /FL  DFW_VKTRY_PARTIAL  VALID 27/1430Z - 27/2200Z  [PROBABILITY OF EXTENSION: MODERATE]
```

**Derived outcome: EXTENDED = 1**. end 27/1900Z -> 27/2200Z (+180 min).

Advisory that decides the outcome:

```
ATCSCC ADVZY 084 DCC 05/27/2026 ROUTE RQD /FL
NAME: DFW_VKTRY_PARTIAL
CONSTRAINED AREA: ZFW
REASON: WEATHER
INCLUDE TRAFFIC: ZAB/ZLA/ZOA DEPARTURES TO KDAL/KDFW
FACILITIES INCLUDED: ZAB/ZDV/ZFW/ZLA/ZLC/ZOA
FLIGHT STATUS: ALL_FLIGHTS
VALID: ETD 271430 TO 272200
PROBABILITY OF EXTENSION: MODERATE
REMARKS: REPLACES ADVZY 059.
ASSOCIATED RESTRICTIONS:
MODIFICATIONS: EXTENDS END TIME.
ROUTES: [route table not shown]
TMI ID: RRDCC509
```

## 123. plan-20260507-070-TEB-gdp-UNTIL0100

- Term: **PROBABLE** (plan:PROBABLE); written as: `UNTIL 0100	-TEB GROUND DELAY PROGRAM PROBABLE`
- Element: TEB; initiative: gdp; first issued 05/07 19:41Z in 20260507-070; window read as 07/1941Z - 08/0100Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 070 DCC 05/07/2026 OPERATIONS PLAN
EVENT TIME: 07/2000 - AND LATER
TERMINAL ACTIVE:
UNTIL 2015	-TEB GROUND STOP
UNTIL 2359	-SFO GROUND DELAY PROGRAM
UNTIL 0459	-SAN GROUND DELAY PROGRAM
TERMINAL PLANNED:
UNTIL 0100	-TEB GROUND DELAY PROGRAM PROBABLE
UNTIL 0100	-CLT GROUND STOP/DELAY PROGRAM POSSIBLE
UNTIL 0700	-SFO GROUND STOP/DELAY PROGRAM POSSIBLE
```

Every advisory the linker could see for this element in the horizon:

```
20260507-067  sent 05/07 19:08Z  CDM GROUND STOP  TEB  GROUND STOP PERIOD 07/1854Z - 07/2015Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260507-074  sent 05/07 20:08Z  CDM GS CNX  TEB  GS CNX PERIOD 07/2008Z - 07/2042Z
```

Other advisories that name the element (not read by the linker):

```
20260507-075  sent 05/07 20:11Z  TEB AIRPORT ARRIVAL DELAYS
```

**Derived outcome: NOT ISSUED = 0**. no gdp advisory for TEB in the window.

No advisory decides the outcome (nothing qualifying was found).

## 124. plan-20260411-079-SFO-gs+gdp-AFTER1500

- Term: **PROBABLE** (plan:PROBABLE); written as: `AFTER 1500	-SFO GROUND STOP/DELAY PROGRAM PROBABLE`
- Element: SFO; initiative: gs/gdp; first issued 04/11 23:24Z in 20260411-079; window read as 12/1500Z - 13/0800Z
- Repeated in: 20260412-013 20260412-030

Source advisory:

```
ATCSCC ADVZY 079 DCC 04/11/2026 OPERATIONS PLAN
EVENT TIME: 12/0000 - AND LATER
TERMINAL ACTIVE:
UNTIL 0759	-SFO GROUND DELAY PROGRAM
TERMINAL PLANNED:
AFTER 1100	-DFW GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1100	-DAL GROUND STOP POSSIBLE
AFTER 1300	-AGS/AIK/DNL/HQU GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1500	-SFO GROUND STOP/DELAY PROGRAM PROBABLE
AFTER 1500	-ORD GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1800	-IAH GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1800	-HOU GROUND STOP POSSIBLE
AFTER 2000	-MDW GROUND STOP POSSIBLE
```

Every advisory the linker could see for this element in the horizon:

```
20260411-059  sent 04/11 19:10Z  CDM PROPOSED GROUND DELAY PROGRAM  SFO  ANTICIPATED CUMULATIVE PROGRAM PERIOD 11/2130Z - 12/0659Z
20260411-064  sent 04/11 19:34Z  CDM GROUND DELAY PROGRAM  SFO  CUMULATIVE PROGRAM PERIOD 11/2130Z - 12/0759Z
20260411-071  sent 04/11 21:06Z  CDM GROUND STOP  SFO  GROUND STOP PERIOD 11/2053Z - 11/2215Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260411-075  sent 04/11 21:54Z  CDM GROUND DELAY PROGRAM  SFO  CUMULATIVE PROGRAM PERIOD 11/2130Z - 12/0759Z
20260412-003  sent 04/12 00:31Z  CDM GROUND STOP  SFO  GROUND STOP PERIOD 12/0019Z - 12/0145Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260412-006  sent 04/12 01:19Z  CDM GROUND DELAY PROGRAM CNX  SFO  GDP CNX PERIOD 12/0116Z - 12/1030Z
20260412-074  sent 04/12 21:00Z  CDM PROPOSED GROUND DELAY PROGRAM  SFO  ANTICIPATED CUMULATIVE PROGRAM PERIOD 12/2056Z - 13/0659Z
20260412-078  sent 04/12 21:08Z  CDM GROUND DELAY PROGRAM  SFO  CUMULATIVE PROGRAM PERIOD 12/2106Z - 13/0659Z
20260413-017  sent 04/13 03:38Z  CDM GROUND STOP  SFO  GROUND STOP PERIOD 13/0323Z - 13/0445Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260413-019  sent 04/13 04:43Z  SFO GROUND STOP CANCELLATION  SFO  EVENT TIME 13/0445Z - 13/0500Z
20260413-020  sent 04/13 05:45Z  CDM GROUND DELAY PROGRAM CNX  SFO  GDP CNX PERIOD 13/0543Z - 13/1855Z
```

Other advisories that name the element (not read by the linker):

```
20260411-061  sent 04/11 19:21Z  SFO AIRPORT ARRIVAL DELAYS
20260412-034  sent 04/12 12:30Z  SFO AIRPORT SCHEDULING DELAYS
20260412-063  sent 04/12 19:05Z  SFO AIRPORT SCHEDULING DELAYS
```

**Derived outcome: ISSUED = 1**. CDM GROUND DELAY PROGRAM sent 12/2108Z, period 12/2106Z - 13/0545Z.

Advisory that decides the outcome:

```
ATCSCC ADVZY 078 SFO/ZOA 04/12/2026 CDM GROUND DELAY PROGRAM
CTL ELEMENT: SFO
ELEMENT TYPE: APT
ADL TIME: 2106Z
DELAY ASSIGNMENT MODE: UDP
ARRIVALS ESTIMATED FOR: 12/2106Z - 13/0659Z
CUMULATIVE PROGRAM PERIOD: 12/2106Z - 13/0659Z
PROGRAM RATE: 36
FLT INCL: ALL CONTIGUOUS US DEP
DEP SCOPE: (ALL+CZV_AP) ZLA ZAU ZLC ZTL ZDC ZNY ZHU ZJX ZFW ZOB ZDV
ZOA ZSE ZBW ZMA ZKC ZME ZID ZAB ZMP
CANADIAN DEP ARPTS INCLUDED: CYEG CYVR CYYC
DELAY ASSIGNMENT TABLE APPLIES TO: ZOA
MAXIMUM DELAY: 88
AVERAGE DELAY: 36
IMPACTING CONDITION: WEATHER / RAIN
COMMENTS: ARR AND DEP RWY 28L/R LOW POP UP.
```

## 125. plan-20260407-060-DCA-gdp-AFTER2100

- Term: **EXPECTED** (plan:EXPECTED); written as: `AFTER 2100	-DCA GROUND DELAY PROGRAM EXPECTED`
- Element: DCA; initiative: gdp; first issued 04/07 19:35Z in 20260407-060; window read as 07/2100Z - 08/0800Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 060 DCC 04/07/2026 OPERATIONS PLAN
EVENT TIME: 07/2000 - AND LATER
TERMINAL ACTIVE:
UNTIL 2259	-MIA GROUND DELAY PROGRAM
TERMINAL PLANNED:
AFTER 2100	-DCA GROUND DELAY PROGRAM EXPECTED
AFTER 2200	-DEN GROUND STOP/DELAY PROGRAM POSSIBLE
UNTIL 0000	-MCO/TPA GROUND STOP POSSIBLE
UNTIL 0000	-FLL/PBI GROUND STOP POSSIBLE
UNTIL 0200	-LGA GROUND STOP/DELAY PROGRAM POSSIBLE
```

Every advisory the linker could see for this element in the horizon:

```
20260407-061  sent 04/07 19:52Z  CDM PROPOSED GROUND DELAY PROGRAM  DCA  ANTICIPATED CUMULATIVE PROGRAM PERIOD 07/2200Z - 08/0359Z
20260407-064  sent 04/07 20:09Z  CDM GROUND DELAY PROGRAM  DCA  CUMULATIVE PROGRAM PERIOD 07/2200Z - 08/0359Z
20260408-003  sent 04/08 01:58Z  CDM GROUND DELAY PROGRAM CNX  DCA  GDP CNX PERIOD 08/0153Z - 08/0428Z
```

**Derived outcome: ISSUED = 1**. CDM GROUND DELAY PROGRAM sent 07/2009Z, period 07/2200Z - 08/0158Z.

Advisory that decides the outcome:

```
ATCSCC ADVZY 064 DCA/ZDC 04/07/2026 CDM GROUND DELAY PROGRAM
CTL ELEMENT: DCA
ELEMENT TYPE: APT
ADL TIME: 2004Z
DELAY ASSIGNMENT MODE: UDP
ARRIVALS ESTIMATED FOR: 07/2200Z - 08/0359Z
CUMULATIVE PROGRAM PERIOD: 07/2200Z - 08/0359Z
PROGRAM RATE: 26
FLT INCL: ALL CONTIGUOUS US DEP
DEP SCOPE: 1000
CANADIAN DEP ARPTS INCLUDED: CYHZ CYOW CYUL CYYZ CYTZ CYQB
DELAY ASSIGNMENT TABLE APPLIES TO: ZDC
MAXIMUM DELAY: 60
AVERAGE DELAY: 25
IMPACTING CONDITION: STAFFING / STAFFING
COMMENTS: DCA TOWER STAFFING. ARR & DEP 01. NO POP UP. TIME+45.
```

## 126. route-20260424-054

- Term: **LOW** (route:LOW); written as: `PROBABILITY OF EXTENSION: LOW`
- Element: DFW_VKTRY_MODIFIED; initiative: reroute; first issued 04/24 16:18Z in 20260424-054; window read as 24/1400Z - 24/1900Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 054 DCC 04/24/2026 ROUTE RQD /FL
NAME: DFW_VKTRY_MODIFIED
CONSTRAINED AREA: ZFW
REASON: VOLUME
INCLUDE TRAFFIC: KPHX/KSAN/KTUS/ZLA/ZOA DEPARTURES TO KDAL/KDFW
FACILITIES INCLUDED: ZAB/ZFW/ZLA/ZOA
FLIGHT STATUS: ALL_FLIGHTS
VALID: ETD 241400 TO 241900
PROBABILITY OF EXTENSION: LOW
REMARKS: REPLACES ADVZY 039, EXTENDS TIME. ZMP AND ZKC REMOVED.
ASSOCIATED RESTRICTIONS:
MODIFICATIONS: STARTED ZOA OVER ABQ
ROUTES: [route table not shown]
TMI ID: RRDCC035
```

Every advisory the linker could see for this element in the horizon:

```
20260424-070  sent 04/24 18:02Z  ROUTE RQD /FL  DFW_VKTRY_MODIFIED  VALID 24/1400Z - 25/0000Z  [PROBABILITY OF EXTENSION: LOW]
```

**Derived outcome: EXTENDED = 1**. end 24/1900Z -> 25/0000Z (+300 min).

Advisory that decides the outcome:

```
ATCSCC ADVZY 070 DCC 04/24/2026 ROUTE RQD /FL
NAME: DFW_VKTRY_MODIFIED
CONSTRAINED AREA: ZFW
REASON: VOLUME
INCLUDE TRAFFIC: KPHX/KSAN/KTUS/ZLA/ZOA DEPARTURES TO KDAL/KDFW
FACILITIES INCLUDED: ZAB/ZFW/ZLA/ZOA
FLIGHT STATUS: ALL_FLIGHTS
VALID: ETD 241400 TO 250000
PROBABILITY OF EXTENSION: LOW
REMARKS: REPLACES ADVZY 054, EXTENDS TIME. ZMP AND ZKC REMOVED.
ASSOCIATED RESTRICTIONS:
MODIFICATIONS: STARTED ZOA OVER ABQ
ROUTES: [route table not shown]
TMI ID: RRDCC035
```

## 127. plan-20260411-047-SFO-gs+gdp-AFTER2000

- Term: **PROBABLE** (plan:PROBABLE); written as: `AFTER 2000	-SFO GROUND STOP/DELAY PROGRAM PROBABLE`
- Element: SFO; initiative: gs/gdp; first issued 04/11 15:23Z in 20260411-047; window read as 11/2000Z - 12/0800Z
- Repeated in: 20260411-052

Source advisory:

```
ATCSCC ADVZY 047 DCC 04/11/2026 OPERATIONS PLAN
EVENT TIME: 11/1600 - AND LATER
TERMINAL ACTIVE:
NONE
TERMINAL PLANNED:
AFTER 1800	-DEN GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 2000	-SFO GROUND STOP/DELAY PROGRAM PROBABLE
```

Every advisory the linker could see for this element in the horizon:

```
20260411-059  sent 04/11 19:10Z  CDM PROPOSED GROUND DELAY PROGRAM  SFO  ANTICIPATED CUMULATIVE PROGRAM PERIOD 11/2130Z - 12/0659Z
20260411-064  sent 04/11 19:34Z  CDM GROUND DELAY PROGRAM  SFO  CUMULATIVE PROGRAM PERIOD 11/2130Z - 12/0759Z
20260411-071  sent 04/11 21:06Z  CDM GROUND STOP  SFO  GROUND STOP PERIOD 11/2053Z - 11/2215Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260411-075  sent 04/11 21:54Z  CDM GROUND DELAY PROGRAM  SFO  CUMULATIVE PROGRAM PERIOD 11/2130Z - 12/0759Z
20260412-003  sent 04/12 00:31Z  CDM GROUND STOP  SFO  GROUND STOP PERIOD 12/0019Z - 12/0145Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260412-006  sent 04/12 01:19Z  CDM GROUND DELAY PROGRAM CNX  SFO  GDP CNX PERIOD 12/0116Z - 12/1030Z
```

Other advisories that name the element (not read by the linker):

```
20260411-037  sent 04/11 12:26Z  SFO AIRPORT SCHEDULING DELAYS
20260411-061  sent 04/11 19:21Z  SFO AIRPORT ARRIVAL DELAYS
```

**Derived outcome: ISSUED = 1**. CDM GROUND DELAY PROGRAM sent 11/1934Z, period 11/2130Z - 12/0119Z.

Advisory that decides the outcome:

```
ATCSCC ADVZY 064 SFO/ZOA 04/11/2026 CDM GROUND DELAY PROGRAM
CTL ELEMENT: SFO
ELEMENT TYPE: APT
ADL TIME: 1929Z
DELAY ASSIGNMENT MODE: UDP
ARRIVALS ESTIMATED FOR: 11/2130Z - 12/0759Z
CUMULATIVE PROGRAM PERIOD: 11/2130Z - 12/0759Z
PROGRAM RATE: 27
FLT INCL: ALL CONTIGUOUS US DEP
DEP SCOPE: (ALL+CZV_AP) ZLA ZAU ZLC ZTL ZDC ZNY ZHU ZJX ZFW ZOB ZDV
ZOA ZSE ZBW ZMA ZKC ZME ZID ZAB ZMP
CANADIAN DEP ARPTS INCLUDED: CYEG CYVR CYYC
DELAY ASSIGNMENT TABLE APPLIES TO: ZOA
MAXIMUM DELAY: 187
AVERAGE DELAY: 95
IMPACTING CONDITION: WEATHER / WIND
COMMENTS: ARR 19L DEP 10L/10R. RWY 19R UNAVAILABLE DUE TO RUNWAY
CONSTRUCTION. LOW POP-UPS. TIME +30.
```

## 128. plan-20260426-112-MDW-gs-AFTER1300

- Term: **PROBABLE** (plan:PROBABLE); written as: `AFTER 1300	-MDW GROUND STOP PROBABLE`
- Element: MDW; initiative: gs; first issued 04/26 23:40Z in 20260426-112; window read as 27/1300Z - 28/0800Z
- Repeated in: 20260427-007 20260427-020 20260427-037

Source advisory:

```
ATCSCC ADVZY 112 DCC 04/26/2026 OPERATIONS PLAN
EVENT TIME: 27/0000 - AND LATER
TERMINAL ACTIVE:
UNTIL 0015	-DFW GROUND STOP
UNTIL 0015	-DAL GROUND STOP
UNTIL 0659	-SFO GROUND DELAY PROGRAM
TERMINAL PLANNED:
AFTER 0200	-SEA GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1300	-MDW GROUND STOP PROBABLE
AFTER 1300	-ORD GROUND STOP/DELAY PROGRAM PROBABLE
AFTER 1500	-SFO GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1600	-MSP GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 2100	-DEN GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 2200	-SFO GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 2200	-JFK GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 28/0200	-MEM  GROUND STOP POSSIBLE
```

Every advisory the linker could see for this element in the horizon:

```
(none)
```

Other advisories that name the element (not read by the linker):

```
20260427-053  sent 04/27 13:47Z  ORD AND MDW AIRPORT ARRIVAL DELAYS
20260427-069  sent 04/27 15:00Z  ORD MDW CDRS_FYI
20260427-101  sent 04/27 21:09Z  ORD/MDW AIRPORT ARRIVAL DELAYS
```

**Derived outcome: NOT ISSUED = 0**. no gs advisory for MDW in the window.

No advisory decides the outcome (nothing qualifying was found).

## 129. route-20260415-038

- Term: **LOW** (route:LOW); written as: `PROBABILITY OF EXTENSION: LOW`
- Element: SERMN_SOUTH_PARTIAL; initiative: reroute; first issued 04/15 11:32Z in 20260415-038; window read as 15/1130Z - 15/1400Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 038 DCC 04/15/2026 ROUTE RQD /FL
NAME: SERMN_SOUTH_PARTIAL
CONSTRAINED AREA: ZNY
REASON: VOLUME
INCLUDE TRAFFIC: KEWR/KHPN/KJFK/KLGA/KMMU/KTEB DEPARTURES TO
KBWI/KCHO/KDCA/KGAI/KHEF/KIAD/KORF/KRIC/KROA
FACILITIES INCLUDED: ZDC/ZNY
FLIGHT STATUS: ALL_FLIGHTS
VALID: ETD 151130 TO 151400
PROBABILITY OF EXTENSION: LOW
REMARKS: THIS ADVISORY APPLIES TO TURBOJET AIRCRAFT ONLY. FLIGHT
CREWS MUST COMPLY WITH ALTITUDE RESTRICTIONS.  DO NOT
REQUEST HIGHER ALTITUDE.  INITIAL ALTITUDE: 080. EXPECT
DESCENT CLEARANCE TO 060 WITH WRI APPROACH.
ASSOCIATED RESTRICTIONS:
MODIFICATIONS:
ROUTES: [route table not shown]
TMI ID: RRDCC038
```

Every advisory the linker could see for this element in the horizon:

```
(none)
```

**Derived outcome: NOT EXTENDED (lapsed) = 0**. no later advisory moved the end past 15/1400Z.

No advisory decides the outcome (nothing qualifying was found).

## 130. route-20260525-027

- Term: **NONE** (route:NONE); written as: `PROBABILITY OF EXTENSION: NONE`
- Element: FCA001:NO_AR_ATLANTIC_Y_RTES_TO_MCO_TPA_RSW_AREAS; initiative: reroute; first issued 05/25 09:00Z in 20260525-027; window read as 25/1056Z - 25/1623Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 027 DCC 05/25/2026 FCA RQD
NAME: FCA001:NO_AR_ATLANTIC_Y_RTES_TO_MCO_TPA_RSW_AREAS
CONSTRAINED AREA: ZJX/ZMA
REASON: OTHER
INCLUDE TRAFFIC: UNKN DEPARTURES TO
KAPF/KFMY/KISM/KLAL/KMCF/KMCO/KMKY/KORL/KPGD/KPIE/K
RSW/KSFB/KSPG/KSRQ/KTPA/KTPF
FACILITIES INCLUDED: ZJX/ZMA/ZDC/ZOB/ZNY/ZBW/CZY
FLIGHT STATUS: ALL_FLIGHTS
VALID: FCA ENTRY TIME FROM 251056 TO 251623
PROBABILITY OF EXTENSION: NONE
REMARKS: SEE DYNAMIC LIST FOR UPDATES. IMPLEMENTED DUE TO ROCKET
LAUNCH ACTIVITIES.
ASSOCIATED RESTRICTIONS:
MODIFICATIONS:
ROUTES: [route table not shown]
TMI ID: RRDCC027
```

Every advisory the linker could see for this element in the horizon:

```
20260525-031  sent 05/25 11:20Z  FCA RQD  FCA001:NO_AR_ATLANTIC_Y_RTES_TO_MCO_TPA_RSW_AREAS  VALID 25/1056Z - 25/1231Z  [PROBABILITY OF EXTENSION: NONE]
20260525-034  sent 05/25 11:54Z  REROUTE CANCELLATION  FCA001:NO_AR_ATLANTIC_Y_RTES_TO_MCO_TPA_RSW_AREAS
```

**Derived outcome: NOT EXTENDED (cancelled) = 0**. cancelled at 25/1154Z; stated end 25/1623Z. Flags: shortened.

Advisory that decides the outcome:

```
ATCSCC ADVZY 034 DCC 05/25/2026 REROUTE CANCELLATION
FCA001:NO_AR_ATLANTIC_Y_RTES_TO_MCO_TPA_RSW_AREAS HAS BEEN CANCELLED.

REMARKS:
ASSOCIATED RESTRICTIONS:
```

## 131. gs-20260521-135

- Term: **MEDIUM** (gs:MEDIUM); written as: `PROBABILITY OF EXTENSION: MEDIUM`
- Element: DEN; initiative: gs; first issued 05/21 23:17Z in 20260521-135; window read as 21/2301Z - 22/0030Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 135 DEN/ZDV 05/21/2026 CDM GROUND STOP
CTL ELEMENT: DEN
ELEMENT TYPE: APT
ADL TIME: 2311Z
GROUND STOP PERIOD: 21/2301Z - 22/0030Z
DEP FACILITIES INCLUDED: (1stTier) ZLA ZLC ZDV ZKC ZAB ZMP
PREVIOUS TOTAL, MAXIMUM, AVERAGE DELAYS: 0 / 0 / 0
NEW TOTAL, MAXIMUM, AVERAGE DELAYS: 2368 / 83 / 36
PROBABILITY OF EXTENSION: MEDIUM
IMPACTING CONDITION: WEATHER / WIND
COMMENTS:
```

Every advisory the linker could see for this element in the horizon:

```
20260522-006  sent 05/22 00:19Z  CDM GROUND STOP  DEN  GROUND STOP PERIOD 21/2301Z - 22/0130Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260522-010  sent 05/22 00:47Z  CDM GROUND STOP  DEN  GROUND STOP PERIOD 22/0030Z - 22/0200Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260522-018  sent 05/22 01:55Z  CDM GS CNX  DEN  GS CNX PERIOD 22/0152Z - 22/0422Z
```

Other advisories that name the element (not read by the linker):

```
20260521-140  sent 05/21 23:49Z  DEN AIRPORT ARRIVAL DELAYS
20260522-003  sent 05/22 00:04Z  DEN AIRPORT DIVERSION RECOVERY ACTIVATED
20260522-013  sent 05/22 01:09Z  DEN CDRS_FYI
```

**Derived outcome: EXTENDED = 1**. end 22/0030Z -> 22/0130Z (+60 min).

Advisory that decides the outcome:

```
ATCSCC ADVZY 006 DEN/ZDV 05/22/2026 CDM GROUND STOP
CTL ELEMENT: DEN
ELEMENT TYPE: APT
ADL TIME: 0016Z
GROUND STOP PERIOD: 21/2301Z - 22/0130Z
DEP FACILITIES INCLUDED: (1stTier) ZLA ZLC ZDV ZKC ZAB ZMP
PREVIOUS TOTAL, MAXIMUM, AVERAGE DELAYS: 1827 / 76 / 21
NEW TOTAL, MAXIMUM, AVERAGE DELAYS: 6113 / 136 / 69
PROBABILITY OF EXTENSION: MEDIUM
IMPACTING CONDITION: WEATHER / WIND
COMMENTS:
```

## 132. plan-20260502-074-MCO-gs+gdp-UNTIL2300

- Term: **PROBABLE** (plan:PROBABLE); written as: `UNTIL 2300 	-MCO GROUND STOP/DELAY PROGRAM PROBABLE`
- Element: MCO; initiative: gs/gdp; first issued 05/02 17:27Z in 20260502-074; window read as 02/1727Z - 02/2300Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 074 DCC 05/02/2026 OPERATIONS PLAN
EVENT TIME: 02/1800 - AND LATER
TERMINAL ACTIVE:
UNTIL 1815	-TPA GROUND STOP
UNTIL 2359	-LGA GROUND DELAY PROGRAM
TERMINAL PLANNED:
AFTER 1800 	-IAH GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 2000 	-JFK GROUND STOP/DELAY PROGRAM POSSIBLE
UNTIL 2300 	-MCO GROUND STOP/DELAY PROGRAM PROBABLE
UNTIL 0000	-BOS GROUND STOP/DELAY PROGRAM POSSIBLE
```

Every advisory the linker could see for this element in the horizon:

```
20260502-059  sent 05/02 15:55Z  CDM GROUND STOP  MCO  GROUND STOP PERIOD 02/1540Z - 02/1715Z  [PROBABILITY OF EXTENSION: HIGH]
20260502-060  sent 05/02 15:58Z  CDM GROUND STOP  MCO  GROUND STOP PERIOD 02/1540Z - 02/1715Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260502-068  sent 05/02 16:52Z  CDM GROUND STOP  MCO  GROUND STOP PERIOD 02/1638Z - 02/1715Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260502-069  sent 05/02 16:58Z  CDM GROUND STOP - CORRECTION  MCO  GROUND STOP PERIOD 02/1638Z - 02/1715Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260502-072  sent 05/02 17:09Z  CDM GS CNX  MCO  GS CNX PERIOD 02/1707Z - 02/1833Z
20260502-078  sent 05/02 17:41Z  CDM GROUND STOP  MCO  GROUND STOP PERIOD 02/1717Z - 02/1845Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260502-082  sent 05/02 18:20Z  CDM GROUND STOP  MCO  GROUND STOP PERIOD 02/1806Z - 02/1945Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260502-089  sent 05/02 19:32Z  CDM GROUND STOP  MCO  GROUND STOP PERIOD 02/1806Z - 02/2045Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260502-097  sent 05/02 20:42Z  CDM GROUND STOP  MCO  GROUND STOP PERIOD 02/2012Z - 02/2145Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260502-099  sent 05/02 20:58Z  CDM GROUND STOP  MCO  GROUND STOP PERIOD 02/2012Z - 02/2145Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260502-102  sent 05/02 21:09Z  CDM GS CNX  MCO  GS CNX PERIOD 02/2108Z - 03/0024Z
```

Other advisories that name the element (not read by the linker):

```
20260502-065  sent 05/02 16:28Z  MCO AIRPORT DIVERSION RECOVERY ACTIVATED
20260502-079  sent 05/02 18:00Z  MCO AIRPORT ARRIVAL DELAYS
```

**Derived outcome: ISSUED = 1**. CDM GROUND STOP sent 02/1741Z, period 02/1717Z - 02/1845Z.

Advisory that decides the outcome:

```
ATCSCC ADVZY 078 MCO/ZJX 05/02/2026 CDM GROUND STOP
CTL ELEMENT: MCO
ELEMENT TYPE: APT
ADL TIME: 1737Z
GROUND STOP PERIOD: 02/1717Z - 02/1845Z
DEP FACILITIES INCLUDED: (Manual) ZTL ZDC ZHU ZJX
PREVIOUS TOTAL, MAXIMUM, AVERAGE DELAYS: 0 / 0 / 0
NEW TOTAL, MAXIMUM, AVERAGE DELAYS: 829 / 146 / 75
PROBABILITY OF EXTENSION: MEDIUM
IMPACTING CONDITION: WEATHER / THUNDERSTORMS
COMMENTS:
```

## 133. route-20260430-051

- Term: **MODERATE** (route:MODERATE); written as: `PROBABILITY OF EXTENSION: MODERATE`
- Element: FCA008:IAH_KOBLE_PARTIAL; initiative: reroute; first issued 04/30 14:02Z in 20260430-051; window read as 30/1700Z - 30/2100Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 051 DCC 04/30/2026 FCA RQD
NAME: FCA008:IAH_KOBLE_PARTIAL
CONSTRAINED AREA: ZHU ZFW
REASON: WEATHER
INCLUDE TRAFFIC: ABQ/KLAS/KSAN/ZAB/ZDV/ZLA/ZLC/ZOA/ZSE DEPARTURES TO
KHOU/KIAH
FACILITIES INCLUDED: ZAB/ZDV/ZHU/ZLA/ZLC/ZOA/ZSE
FLIGHT STATUS: ALL_FLIGHTS
VALID: FCA ENTRY TIME FROM 301700 TO 302100
PROBABILITY OF EXTENSION: MODERATE
REMARKS: CME MRF LINE REMOVED
SEE DYNAMIC LIST FOR UPDATES.
ASSOCIATED RESTRICTIONS:
MODIFICATIONS:
ROUTES: [route table not shown]
TMI ID: RRDCC507
```

Every advisory the linker could see for this element in the horizon:

```
20260430-093  sent 04/30 19:43Z  FCA RQD  FCA008:IAH_KOBLE_PARTIAL  VALID 30/1700Z - 30/2300Z  [PROBABILITY OF EXTENSION: MODERATE]
```

**Derived outcome: EXTENDED = 1**. end 30/2100Z -> 30/2300Z (+120 min).

Advisory that decides the outcome:

```
ATCSCC ADVZY 093 DCC 04/30/2026 FCA RQD
NAME: FCA008:IAH_KOBLE_PARTIAL
CONSTRAINED AREA: ZHU ZFW
REASON: WEATHER
INCLUDE TRAFFIC: ABQ/KLAS/KSAN/ZAB/ZDV/ZLA/ZLC/ZOA/ZSE DEPARTURES TO
KHOU/KIAH
FACILITIES INCLUDED: ZAB/ZDV/ZHU/ZLA/ZLC/ZOA/ZSE
FLIGHT STATUS: ALL_FLIGHTS
VALID: FCA ENTRY TIME FROM 301700 TO 302300
PROBABILITY OF EXTENSION: MODERATE
REMARKS: REPLACES ADVZY051, EXTENDS TIME. CME MRF LINE REMOVED
SEE DYNAMIC LIST FOR UPDATES.
ASSOCIATED RESTRICTIONS:
MODIFICATIONS:
ROUTES: [route table not shown]
TMI ID: RRDCC507
```

## 134. route-20260402-061

- Term: **NONE** (route:NONE); written as: `PROBABILITY OF EXTENSION: NONE`
- Element: FCA001:NO_AR_ATLANTIC_Y-RTES_TO_MCO_TPA_RSW_AREAS; initiative: reroute; first issued 04/02 09:37Z in 20260402-061; window read as 02/1107Z - 02/1634Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 061 DCC 04/02/2026 FCA RQD
NAME: FCA001:NO_AR_ATLANTIC_Y-RTES_TO_MCO_TPA_RSW_AREAS
CONSTRAINED AREA: ZJX/ZMA
REASON: OTHER
INCLUDE TRAFFIC: UNKN DEPARTURES TO
KAPF/KFMY/KISM/KLAL/KMCF/KMCO/KMKY/KORL/KPGD/KPIE/K
RSW/KSFB/KSPG/KSRQ/KTPA/KTPF
FACILITIES INCLUDED: ZJX/ZMA/ZDC/ZBW/ZOB
FLIGHT STATUS: ALL_FLIGHTS
VALID: FCA ENTRY TIME FROM 021107 TO 021634
PROBABILITY OF EXTENSION: NONE
REMARKS: SEE DYNAMIC LIST FOR UPDATES. IMPLEMENTED DUE TO ROCKET
LAUNCH ACTIVITIES.
ASSOCIATED RESTRICTIONS:
MODIFICATIONS:
ROUTES: [route table not shown]
TMI ID: RRDCC061
```

Every advisory the linker could see for this element in the horizon:

```
20260402-078  sent 04/02 12:03Z  REROUTE CANCELLATION  FCA001:NO_AR_ATLANTIC_Y-RTES_TO_MCO_TPA_RSW_AREAS
```

**Derived outcome: NOT EXTENDED (cancelled) = 0**. cancelled at 02/1203Z; stated end 02/1634Z.

Advisory that decides the outcome:

```
ATCSCC ADVZY 078 DCC 04/02/2026 REROUTE CANCELLATION
FCA001:NO_AR_ATLANTIC_Y-RTES_TO_MCO_TPA_RSW_AREAS HAS BEEN CANCELLED.

REMARKS: LAUNCH ACTIVITIES COMPLETE
ASSOCIATED RESTRICTIONS:
```

## 135. route-20260415-010

- Term: **NONE** (route:NONE); written as: `PROBABILITY OF EXTENSION: NONE`
- Element: DC_METRO_NATS_ESCAPE_VIA_GOATR; initiative: reroute; first issued 04/15 01:41Z in 20260415-010; window read as 15/0100Z - 15/0400Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 010 DCC 04/15/2026 ROUTE RMD /FL
NAME: DC_METRO_NATS_ESCAPE_VIA_GOATR
CONSTRAINED AREA: ZDC
REASON: WEATHER
INCLUDE TRAFFIC: KADW/KBWI/KIAD DEPARTURES TO ZEU
FACILITIES INCLUDED: ZBW/ZDC/ZEU/ZOB
FLIGHT STATUS: ALL_FLIGHTS
VALID: ETD 150100 TO 150400
PROBABILITY OF EXTENSION: NONE
REMARKS: AIRCRAFT FILED TUSKY OR SOUTH PLEASE FILE APPROPRIATE ROUTE
TO GOATR THEN DIRECT ALLEX THEN DIRECT OEP.
ASSOCIATED RESTRICTIONS:
MODIFICATIONS:
ROUTES: [route table not shown]
TMI ID: RRDCC502
```

Every advisory the linker could see for this element in the horizon:

```
(none)
```

**Derived outcome: NOT EXTENDED (lapsed) = 0**. no later advisory moved the end past 15/0400Z.

No advisory decides the outcome (nothing qualifying was found).

## 136. plan-20260430-032-BOS-gs+gdp-AFTER1700

- Term: **EXPECTED** (plan:EXPECTED); written as: `AFTER 1700	-BOS GROUND STOP/DELAY PROGRAM EXPECTED`
- Element: BOS; initiative: gs/gdp; first issued 04/30 11:51Z in 20260430-032; window read as 30/1700Z - 01/0800Z
- Repeated in: 20260430-033 20260430-046

Source advisory:

```
ATCSCC ADVZY 032 DCC 04/30/2026 OPERATIONS PLAN
EVENT TIME: 30/1200 - AND LATER
TERMINAL ACTIVE:
NONE
TERMINAL PLANNED:
AFTER 1300	-LGA/HPN GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1500	-SFO GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1700	-BOS GROUND STOP/DELAY PROGRAM EXPECTED
AFTER 1700	-EWR GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1900	-DCA GROUND STOP POSSIBLE
```

Every advisory the linker could see for this element in the horizon:

```
20260430-052  sent 04/30 14:04Z  CDM PROPOSED GROUND DELAY PROGRAM  BOS  ANTICIPATED CUMULATIVE PROGRAM PERIOD 30/1700Z - 01/0359Z
20260430-054  sent 04/30 14:18Z  CDM GROUND DELAY PROGRAM  BOS  CUMULATIVE PROGRAM PERIOD 30/1700Z - 01/0359Z
20260430-121  sent 04/30 22:31Z  CDM GROUND DELAY PROGRAM CNX  BOS  GDP CNX PERIOD 30/2228Z - 01/0510Z
```

**Derived outcome: ISSUED = 1**. CDM GROUND DELAY PROGRAM sent 30/1418Z, period 30/1700Z - 30/2231Z.

Advisory that decides the outcome:

```
ATCSCC ADVZY 054 BOS/ZBW 04/30/2026 CDM GROUND DELAY PROGRAM
CTL ELEMENT: BOS
ELEMENT TYPE: APT
ADL TIME: 1416Z
DELAY ASSIGNMENT MODE: UDP
ARRIVALS ESTIMATED FOR: 30/1700Z - 01/0359Z
CUMULATIVE PROGRAM PERIOD: 30/1700Z - 01/0359Z
PROGRAM RATE: 38
FLT INCL: ALL CONTIGUOUS US DEP
DEP SCOPE: (ALL+CZY_AP) ZLA ZAU ZLC ZTL ZDC ZNY ZHU ZJX ZFW ZOB ZDV
ZOA ZSE ZBW ZMA ZKC ZME ZID ZAB ZMP
CANADIAN DEP ARPTS INCLUDED: CYHZ CYOW CYUL CYYZ CYTZ CYQB
DELAY ASSIGNMENT TABLE APPLIES TO: ZBW
MAXIMUM DELAY: 405
AVERAGE DELAY: 67
IMPACTING CONDITION: WEATHER / LOW CEILINGS
COMMENTS: ARR: 4R DEP: 9 MED HIST POP UP. TIME PLUS 45
```

## 137. route-20260423-089

- Term: **MODERATE** (route:MODERATE); written as: `PROBABILITY OF EXTENSION: MODERATE`
- Element: GFK_WEST; initiative: reroute; first issued 04/23 21:26Z in 20260423-089; window read as 23/2130Z - 24/0100Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 089 DCC 04/23/2026 ROUTE RQD /FL
NAME: GFK_WEST
CONSTRAINED AREA: ZMP/ZAU/ZKC
REASON: WEATHER
INCLUDE TRAFFIC: ZBW/ZNY DEPARTURES TO KDEN/KPDX/KSEA/KSFO/KSLC
FACILITIES INCLUDED: ZBW/ZDV/ZLC/ZMP/ZNY/ZOA/ZOB/ZSE
FLIGHT STATUS: ALL_FLIGHTS
VALID: ETD 232130 TO 240100
PROBABILITY OF EXTENSION: MODERATE
REMARKS: AD HOC ROUTE.
ASSOCIATED RESTRICTIONS:
MODIFICATIONS:
ROUTES: [route table not shown]
TMI ID: RRDCC516
```

Every advisory the linker could see for this element in the horizon:

```
(none)
```

**Derived outcome: NOT EXTENDED (lapsed) = 0**. no later advisory moved the end past 24/0100Z.

No advisory decides the outcome (nothing qualifying was found).

## 138. gs-20260520-142

- Term: **MEDIUM** (gs:MEDIUM); written as: `PROBABILITY OF EXTENSION: MEDIUM`
- Element: PHL; initiative: gs; first issued 05/20 20:59Z in 20260520-142; window read as 20/2041Z - 20/2215Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 142 PHL/ZNY 05/20/2026 CDM GROUND STOP
CTL ELEMENT: PHL
ELEMENT TYPE: APT
ADL TIME: 2056Z
GROUND STOP PERIOD: 20/2041Z - 20/2215Z
CUMULATIVE PROGRAM PERIOD: 20/2030Z - 21/0259Z
DEP FACILITIES INCLUDED: (2ndTier+CZY_AP) ZAU ZTL ZDC ZNY ZJX ZOB ZBW
ZID ZMP  CYHZ CYOW CYUL CYYZ CYTZ CYQB
PREVIOUS TOTAL, MAXIMUM, AVERAGE DELAYS: 247 / 118 / 16
NEW TOTAL, MAXIMUM, AVERAGE DELAYS: 1223 / 183 / 82
PROBABILITY OF EXTENSION: MEDIUM
IMPACTING CONDITION: WEATHER / THUNDERSTORMS
COMMENTS:
```

Every advisory the linker could see for this element in the horizon:

```
20260520-161  sent 05/20 21:54Z  CDM GROUND STOP  PHL  GROUND STOP PERIOD 20/2041Z - 20/2300Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260520-178  sent 05/20 22:58Z  CDM GROUND DELAY PROGRAM CNX  PHL  GDP CNX PERIOD 20/2254Z - 21/0529Z
20260520-179  sent 05/20 23:00Z  CDM GROUND STOP  PHL  GROUND STOP PERIOD 20/2249Z - 21/0000Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260520-192  sent 05/20 23:47Z  CDM GS CNX  PHL  GS CNX PERIOD 20/2345Z - 21/0145Z
```

**Derived outcome: EXTENDED = 1**. end 20/2215Z -> 20/2300Z (+45 min).

Advisory that decides the outcome:

```
ATCSCC ADVZY 161 PHL/ZNY 05/20/2026 CDM GROUND STOP
CTL ELEMENT: PHL
ELEMENT TYPE: APT
ADL TIME: 2153Z
GROUND STOP PERIOD: 20/2041Z - 20/2300Z
CUMULATIVE PROGRAM PERIOD: 20/2030Z - 21/0259Z
DEP FACILITIES INCLUDED: (2ndTier+CZY_AP) ZAU ZTL ZDC ZNY ZJX ZOB ZBW
ZID ZMP  CYHZ CYOW CYUL CYYZ CYTZ CYQB
PREVIOUS TOTAL, MAXIMUM, AVERAGE DELAYS: 981 / 183 / 52
NEW TOTAL, MAXIMUM, AVERAGE DELAYS: 1662 / 222 / 87
PROBABILITY OF EXTENSION: MEDIUM
IMPACTING CONDITION: WEATHER / THUNDERSTORMS
COMMENTS:
```

## 139. plan-20260414-041-ORD-gs+gdp-AFTER1000

- Term: **POSSIBLE** (plan:POSSIBLE); written as: `AFTER 1000	-ORD/MDW GROUND STOP/DELAY PROGRAM POSSIBLE`
- Element: ORD; initiative: gs/gdp; first issued 04/14 09:29Z in 20260414-041; window read as 14/1000Z - 15/0800Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 041 DCC 04/14/2026 OPERATIONS PLAN
EVENT TIME: 14/1000 - AND LATER
TERMINAL ACTIVE:
NONE
TERMINAL PLANNED:
AFTER 1000	-ORD/MDW GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1100	-DTW GROUND STOP POSSIBLE
AFTER 1500	-SFO GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1900	-DEN GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 2000	-JFK GROUND STOP/DELAY PROGRAM POSSIBLE
```

Every advisory the linker could see for this element in the horizon:

```
20260414-014  sent 04/14 03:50Z  CDM GROUND DELAY PROGRAM CNX  ORD  GDP CNX PERIOD 14/0347Z - 14/0715Z
20260414-044  sent 04/14 09:47Z  CDM GROUND STOP  ORD  GROUND STOP PERIOD 14/0945Z - 14/1100Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260414-047  sent 04/14 10:38Z  CDM GROUND STOP  ORD  GROUND STOP PERIOD 14/0945Z - 14/1145Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260414-055  sent 04/14 11:16Z  CDM PROPOSED GROUND DELAY PROGRAM  ORD  ANTICIPATED CUMULATIVE PROGRAM PERIOD 14/1113Z - 15/0059Z
20260414-060  sent 04/14 11:42Z  CDM GROUND DELAY PROGRAM  ORD  CUMULATIVE PROGRAM PERIOD 14/1138Z - 15/0059Z
20260414-085  sent 04/14 14:54Z  CDM GROUND DELAY PROGRAM CNX  ORD  GDP CNX PERIOD 14/1452Z - 15/0254Z
20260414-089  sent 04/14 16:23Z  CDM GROUND STOP  ORD  GROUND STOP PERIOD 14/1607Z - 14/1715Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260414-092  sent 04/14 17:14Z  CDM GS CNX  ORD  GS CNX PERIOD 14/1713Z - 14/2251Z
20260415-004  sent 04/15 00:53Z  CDM GROUND STOP  ORD  GROUND STOP PERIOD 15/0038Z - 15/0145Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260415-006  sent 04/15 01:18Z  CDM GS CNX  ORD  GS CNX PERIOD 15/0113Z - 15/1423Z
20260415-014  sent 04/15 02:40Z  CDM GROUND STOP  ORD  GROUND STOP PERIOD 15/0228Z - 15/0345Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260415-018  sent 04/15 03:34Z  CDM GROUND STOP  ORD  GROUND STOP PERIOD 15/0320Z - 15/0445Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260415-021  sent 04/15 04:41Z  CDM GROUND STOP  ORD  GROUND STOP PERIOD 15/0424Z - 15/0545Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260415-022  sent 04/15 05:44Z  CDM GROUND STOP  ORD  GROUND STOP PERIOD 15/0531Z - 15/0630Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260415-024  sent 04/15 06:25Z  CDM GS CNX  ORD  GS CNX PERIOD 15/0618Z - 15/1854Z
```

Other advisories that name the element (not read by the linker):

```
20260414-049  sent 04/14 10:47Z  ORD AIRPORT ARRIVAL DELAYS
20260414-052  sent 04/14 10:54Z  ORD AIRPORT DIVERSION RECOVERY ACTIVATED
20260414-103  sent 04/14 20:21Z  ORD MDW CDRS_FYI
20260414-115  sent 04/14 23:25Z  ORD MDW CDRS_FYI
```

**Derived outcome: ISSUED = 1**. CDM GROUND STOP sent 14/0947Z, period 14/0945Z - 14/1100Z.

Advisory that decides the outcome:

```
ATCSCC ADVZY 044 ORD/ZAU 04/14/2026 CDM GROUND STOP
CTL ELEMENT: ORD
ELEMENT TYPE: APT
ADL TIME: 0942Z
GROUND STOP PERIOD: 14/0945Z - 14/1100Z
DEP FACILITIES INCLUDED: (Manual) ZAU ZTL ZDC ZNY ZJX ZOB ZBW ZKC ZME
ZID ZMP  CYHZ CYOW CYUL CYYZ
PREVIOUS TOTAL, MAXIMUM, AVERAGE DELAYS: 0 / 0 / 0
NEW TOTAL, MAXIMUM, AVERAGE DELAYS: 2834 / 76 / 33
PROBABILITY OF EXTENSION: MEDIUM
IMPACTING CONDITION: WEATHER / THUNDERSTORMS
COMMENTS:
```

## 140. gs-20260426-099

- Term: **MEDIUM** (gs:MEDIUM); written as: `PROBABILITY OF EXTENSION: MEDIUM`
- Element: MIA; initiative: gs; first issued 04/26 21:46Z in 20260426-099; window read as 26/2045Z - 26/2300Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 099 MIA/ZMA 04/26/2026 CDM GROUND STOP
CTL ELEMENT: MIA
ELEMENT TYPE: APT
ADL TIME: 2142Z
GROUND STOP PERIOD: 26/2045Z - 26/2300Z
DEP FACILITIES INCLUDED: (Manual) ZTL ZJX ZMA
PREVIOUS TOTAL, MAXIMUM, AVERAGE DELAYS: 413 / 66 / 19
NEW TOTAL, MAXIMUM, AVERAGE DELAYS: 1272 / 126 / 58
PROBABILITY OF EXTENSION: MEDIUM
IMPACTING CONDITION: WEATHER / THUNDERSTORMS
COMMENTS:
```

Every advisory the linker could see for this element in the horizon:

```
20260426-102  sent 04/26 22:56Z  CDM GS CNX  MIA  GS CNX PERIOD 26/2251Z - 27/0100Z
```

**Derived outcome: NOT EXTENDED (cancelled) = 0**. cancelled at 26/2256Z; stated end 26/2300Z.

Advisory that decides the outcome:

```
ATCSCC ADVZY 102 MIA/ZMA 04/26/2026 CDM GS CNX
CTL ELEMENT: MIA
ELEMENT TYPE: APT
ADL TIME: 2251Z
GS CNX PERIOD: 26/2251Z - 27/0100Z
COMMENTS: OBJECTIVES MET.
```

## 141. route-20260417-024

- Term: **LOW** (route:LOW); written as: `PROBABILITY OF EXTENSION: LOW`
- Element: FCA003:SUN_N_FUN_ROUTE; initiative: reroute; first issued 04/17 09:55Z in 20260417-024; window read as 17/1200Z - 18/0100Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 024 DCC 04/17/2026 FCA RQD
NAME: FCA003:SUN_N_FUN_ROUTE
CONSTRAINED AREA: ZMA/ZJX
REASON: VOLUME
INCLUDE TRAFFIC: KABE/KELM/KITH/KJFK/KMDT/KSYR/KUNV/ZBW/ZDC/ZID/ZNY/
ZOB/ZTL DEPARTURES TO KPIE/KSRQ/KVNC
FACILITIES INCLUDED: ZBW/ZDC/ZID/ZJX/ZMA/ZNY/ZOB/ZTL
FLIGHT STATUS: ALL_FLIGHTS
VALID: FCA ENTRY TIME FROM 171200 TO 180100
PROBABILITY OF EXTENSION: LOW
REMARKS: SEE DYNAMIC LIST FOR UPDATES. IMPLEMENTED FOR SUN-N-FUN
EVENT.
ASSOCIATED RESTRICTIONS:
MODIFICATIONS:
ROUTES: [route table not shown]
TMI ID: RRDCC024
```

Every advisory the linker could see for this element in the horizon:

```
(none)
```

**Derived outcome: NOT EXTENDED (lapsed) = 0**. no later advisory moved the end past 18/0100Z.

No advisory decides the outcome (nothing qualifying was found).

## 142. route-20260401-008

- Term: **NONE** (route:NONE); written as: `PROBABILITY OF EXTENSION: NONE`
- Element: FCA014:SW_WEST_TO_ORD; initiative: reroute; first issued 04/01 01:11Z in 20260401-008; window read as 31/2200Z - 01/0300Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 008 DCC 04/01/2026 FCA RQD
NAME: FCA014:SW_WEST_TO_ORD
CONSTRAINED AREA: ZAU
REASON: EQUIPMENT
INCLUDE TRAFFIC: KAUS/KHOU/KIAH/KSAT/ZAB/ZDV/ZFW/ZLA/ZLC/ZOA/ZSE
DEPARTURES TO KORD
FACILITIES INCLUDED: ZAB/ZAU/ZDV/ZFW/ZHU/ZKC/ZLA/ZLC/ZMP/ZOA/ZSE
FLIGHT STATUS: ALL_FLIGHTS
VALID: FCA ENTRY TIME FROM 312200 TO 010300
PROBABILITY OF EXTENSION: NONE
REMARKS: REPLACES ADVZY070, EXTENDS TIME. SEE DYNAMIC LIST FOR
UPDATES. BASED ON ORD OXI ROYKO 2 PARTIAL
ASSOCIATED RESTRICTIONS:
MODIFICATIONS:
ROUTES: [route table not shown]
TMI ID: RRDCC506
```

Every advisory the linker could see for this element in the horizon:

```
(none)
```

**Derived outcome: NOT EXTENDED (lapsed) = 0**. no later advisory moved the end past 01/0300Z.

No advisory decides the outcome (nothing qualifying was found).

## 143. route-20260430-024

- Term: **LOW** (route:LOW); written as: `PROBABILITY OF EXTENSION: LOW`
- Element: FCA028:NO_Q34_2_PARTIAL; initiative: reroute; first issued 04/30 10:40Z in 20260430-024; window read as 30/1200Z - 30/2100Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 024 DCC 04/30/2026 FCA RQD
NAME: FCA028:NO_Q34_2_PARTIAL
CONSTRAINED AREA: ZDC
REASON: OTHER
INCLUDE TRAFFIC: KBNA/ZFW/ZHU/ZME DEPARTURES TO
KCDW/KEWR/KLGA/KMMU/KTEB
FACILITIES INCLUDED: ZFW/ZHU/ZID/ZME/ZNY/ZOB
FLIGHT STATUS: ALL_FLIGHTS
VALID: FCA ENTRY TIME FROM 301200 TO 302100
PROBABILITY OF EXTENSION: LOW
REMARKS: IMPLEMENTED DUE TO SUA. SEE DYNAMIC LIST FOR UPDATES. ZHU
AIRPORTS (HOUSTON TERMINAL AND WEST).  MSY AREA DEPTS ONLY:
USE PREF ROUTES FROM MGM
ASSOCIATED RESTRICTIONS:
MODIFICATIONS:
ROUTES: [route table not shown]
TMI ID: RRDCC501
```

Every advisory the linker could see for this element in the horizon:

```
20260430-085  sent 04/30 18:16Z  REROUTE CANCELLATION  FCA028:NO_Q34_2_PARTIAL
```

**Derived outcome: NOT EXTENDED (cancelled) = 0**. cancelled at 30/1816Z; stated end 30/2100Z.

Advisory that decides the outcome:

```
ATCSCC ADVZY 085 DCC 04/30/2026 REROUTE CANCELLATION
FCA028:NO_Q34_2_PARTIAL HAS BEEN CANCELLED.

REMARKS:
ASSOCIATED RESTRICTIONS:
```

## 144. gs-20260426-105

- Term: **MEDIUM** (gs:MEDIUM); written as: `PROBABILITY OF EXTENSION: MEDIUM`
- Element: DFW; initiative: gs; first issued 04/26 23:18Z in 20260426-105; window read as 26/2255Z - 27/0015Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 105 DFW/ZFW 04/26/2026 CDM GROUND STOP
CTL ELEMENT: DFW
ELEMENT TYPE: APT
ADL TIME: 2315Z
GROUND STOP PERIOD: 26/2255Z - 27/0015Z
DEP FACILITIES INCLUDED: (Manual) ZHU ZFW ZKC ZME ZAB ZDV
PREVIOUS TOTAL, MAXIMUM, AVERAGE DELAYS: 0 / 0 / 0
NEW TOTAL, MAXIMUM, AVERAGE DELAYS: 1137 / 66 / 37
PROBABILITY OF EXTENSION: MEDIUM
IMPACTING CONDITION: EQUIPMENT / OUTAGE
COMMENTS: INTERMITTENT LANDLINE, COMMS, AUTOMATION ISSUES
```

Every advisory the linker could see for this element in the horizon:

```
20260426-113  sent 04/26 23:46Z  CDM GS CNX  DFW  GS CNX PERIOD 26/2342Z - 27/0212Z
```

**Derived outcome: NOT EXTENDED (cancelled) = 0**. cancelled at 26/2346Z; stated end 27/0015Z.

Advisory that decides the outcome:

```
ATCSCC ADVZY 113 DFW/ZFW 04/26/2026 CDM GS CNX
CTL ELEMENT: DFW
ELEMENT TYPE: APT
ADL TIME: 2342Z
GS CNX PERIOD: 26/2342Z - 27/0212Z
COMMENTS:
```

## 145. plan-20260516-008-SFO-gs+gdp-AFTER1500

- Term: **PROBABLE** (plan:PROBABLE); written as: `AFTER 1500	-SFO GROUND STOP/DELAY PROGRAM PROBABLE`
- Element: SFO; initiative: gs/gdp; first issued 05/16 01:23Z in 20260516-008; window read as 16/1500Z - 17/0800Z
- Repeated in: 20260516-015 20260516-025

Source advisory:

```
ATCSCC ADVZY 008 DCC 05/16/2026 OPERATIONS PLAN
EVENT TIME: 16/0200 - AND LATER
TERMINAL ACTIVE:
UNTIL 0215	-DFW GROUND STOP
UNTIL 0659	-SFO GROUND DELAY PROGRAM
TERMINAL PLANNED:
AFTER 1500	-SFO GROUND STOP/DELAY PROGRAM PROBABLE
AFTER 2000	-DEN GROUND STOP/DELAY PROGRAM POSSIBLE
```

Every advisory the linker could see for this element in the horizon:

```
20260515-084  sent 05/15 23:00Z  CDM GROUND DELAY PROGRAM  SFO  CUMULATIVE PROGRAM PERIOD 15/1500Z - 16/0659Z
20260516-012  sent 05/16 05:22Z  CDM GROUND DELAY PROGRAM CNX  SFO  GDP CNX PERIOD 16/0520Z - 16/0924Z
```

Other advisories that name the element (not read by the linker):

```
20260515-085  sent 05/15 23:04Z  SFO AIRPORT ARRIVAL DELAYS
20260516-028  sent 05/16 12:25Z  SFO AIRPORT SCHEDULING AND ARRIVAL DELAYS
20260516-065  sent 05/16 21:36Z  SFO AIRPORT SCHEDULING DELAYS
```

**Derived outcome: NOT ISSUED = 0**. no gs or gdp advisory for SFO in the window.

No advisory decides the outcome (nothing qualifying was found).

## 146. plan-20260404-007-DFW-gs+gdp-AFTER1100

- Term: **PROBABLE** (plan:PROBABLE); written as: `AFTER 1100	-DFW/DAL GROUND STOP/DELAY PROGRAM PROBABLE`
- Element: DFW; initiative: gs/gdp; first issued 04/04 01:25Z in 20260404-007; window read as 04/1100Z - 05/0800Z
- Repeated in: 20260404-035

Source advisory:

```
ATCSCC ADVZY 007 DCC 04/04/2026 OPERATIONS PLAN
EVENT TIME: 04/0200 - AND LATER
TERMINAL ACTIVE:
UNTIL 0559	-SFO GROUND DELAY PROGRAM
TERMINAL PLANNED:
AFTER 0200	-ORD/MDW GROUND STOP/DELAY PROGRAM EXPECTED
AFTER 1100	-DFW/DAL GROUND STOP/DELAY PROGRAM PROBABLE
AFTER 1500	-SFO GROUND DELAY PROGRAM PROBABLE
AFTER 1600	-AUS GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1700	-DTW GROUND STOP POSSIBLE
AFTER 1800	-ATL GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1800	-IAH/HOU GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 2000	-CLT GROUND STOP POSSIBLE
```

Every advisory the linker could see for this element in the horizon:

```
20260404-038  sent 04/04 10:04Z  CDM GROUND STOP  DFW  GROUND STOP PERIOD 04/0945Z - 04/1045Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260404-046  sent 04/04 10:32Z  CDM GROUND STOP  DFW  GROUND STOP PERIOD 04/0945Z - 04/1145Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260404-056  sent 04/04 11:32Z  CDM GROUND STOP  DFW  GROUND STOP PERIOD 04/1117Z - 04/1245Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260404-062  sent 04/04 12:17Z  CDM GS CNX  DFW  GS CNX PERIOD 04/1214Z - 04/1524Z
20260404-075  sent 04/04 14:10Z  CDM GROUND STOP  DFW  GROUND STOP PERIOD 04/1356Z - 04/1515Z  [PROBABILITY OF EXTENSION: MEDIUM]
20260404-088  sent 04/04 15:14Z  CDM GROUND STOP  DFW  GROUND STOP PERIOD 04/1356Z - 04/1615Z  [PROBABILITY OF EXTENSION: LOW]
20260404-090  sent 04/04 15:25Z  CDM GS CNX  DFW  GS CNX PERIOD 04/1524Z - 04/1815Z
```

Other advisories that name the element (not read by the linker):

```
20260403-118  sent 04/03 21:34Z  DFW DAL CDRS_FYI
20260404-040  sent 04/04 10:08Z  DFW AIRPORT ARRIVAL DELAYS
20260404-041  sent 04/04 10:09Z  DFW DAL CDRS_FYI
20260404-042  sent 04/04 10:10Z  DFW AIRPORT DIVERSION RECOVERY ACTIVATED
20260404-089  sent 04/04 15:17Z  DFW AIRPORT DIVERSION RECOVERY ACTIVATED
20260404-102  sent 04/04 17:29Z  DFW DAL CDRS_FYI
```

**Derived outcome: ISSUED = 1**. CDM GROUND STOP sent 04/1032Z, period 04/0945Z - 04/1145Z.

Advisory that decides the outcome:

```
ATCSCC ADVZY 046 DFW/ZFW 04/04/2026 CDM GROUND STOP
CTL ELEMENT: DFW
ELEMENT TYPE: APT
ADL TIME: 1029Z
GROUND STOP PERIOD: 04/0945Z - 04/1145Z
DEP FACILITIES INCLUDED: (1stTier) ZHU ZFW ZKC ZME ZAB
PREVIOUS TOTAL, MAXIMUM, AVERAGE DELAYS: 132 / 35 / 5
NEW TOTAL, MAXIMUM, AVERAGE DELAYS: 997 / 95 / 38
PROBABILITY OF EXTENSION: MEDIUM
IMPACTING CONDITION: WEATHER / THUNDERSTORMS
COMMENTS:
```

## 147. route-20260502-037

- Term: **NONE** (route:NONE); written as: `PROBABILITY OF EXTENSION: NONE`
- Element: FCAZH7:FCAZH7_ICR; initiative: reroute; first issued 05/02 12:14Z in 20260502-037; window read as 02/1500Z - 02/2000Z
- Repeated in: no later advisory

Source advisory:

```
ATCSCC ADVZY 037 DCC 05/02/2026 FCA RQD
NAME: FCAZH7:FCAZH7_ICR
CONSTRAINED AREA: ZHU
REASON: WEATHER
INCLUDE TRAFFIC: CZE/CZV/ZAB/ZAU/ZDV/ZFW/ZHU/ZID/ZKC/ZLA/ZLC/ZME/ZMP
/ZOA/ZSE DEPARTURES TO UNKN
FACILITIES INCLUDED: CZE/CZV/ZAB/ZAU/ZDV/ZFW/ZHU/ZID/ZKC/ZLA/ZLC/ZME
/ZMP/ZOA/ZSE
FLIGHT STATUS: ALL_FLIGHTS
VALID: FCA ENTRY TIME FROM 021500 TO 022000
PROBABILITY OF EXTENSION: NONE
REMARKS: ICR PROCESS IS IN EFFECT FOR FCAZH7.  STAKEHOLDERS CAN
ROUTE AROUND THE FCA WITH UPT ROUTING.  THOSE FLIGHTS THAT
REMAIN IN THE FCA COULD RECEIVE MORE EXTENSIVE REROUTES OR
AFP EDCT DELAYS. WEATHER DEVELOPMENT FROM L214 EAST DOES
NOT MAKE EASTBOUND ROUTE OUTS A RECOMMENDED.
ASSOCIATED RESTRICTIONS:
MODIFICATIONS:
ROUTES: [route table not shown]
TMI ID: RRDCC503
```

Every advisory the linker could see for this element in the horizon:

```
20260502-058  sent 05/02 15:55Z  REROUTE CANCELLATION  FCAZH7:FCAZH7_ICR
```

**Derived outcome: NOT EXTENDED (cancelled) = 0**. cancelled at 02/1555Z; stated end 02/2000Z.

Advisory that decides the outcome:

```
ATCSCC ADVZY 058 DCC 05/02/2026 REROUTE CANCELLATION
FCAZH7:FCAZH7_ICR HAS BEEN CANCELLED.

REMARKS: ICR CANCELED, OBJECTIVES MET.
ASSOCIATED RESTRICTIONS:
```

## 148. plan-20260521-017-ATL-gs-AFTER1900

- Term: **POSSIBLE** (plan:POSSIBLE); written as: `AFTER 1900	-ATL GROUND STOP POSSIBLE`
- Element: ATL; initiative: gs; first issued 05/21 01:30Z in 20260521-017; window read as 21/1900Z - 22/0800Z
- Repeated in: 20260521-042 20260521-055 20260521-068 20260521-080

Source advisory:

```
ATCSCC ADVZY 017 DCC 05/21/2026 OPERATIONS PLAN
EVENT TIME: 21/0200 - AND LATER
TERMINAL ACTIVE:
UNTIL 0200	-JFK GROUND STOP
UNTIL 0230	-EWR GROUND STOP
UNTIL 0230	-IAD GROUND STOP
UNTIL 0230	-DCA GROUND STOP
UNTIL 0459	-LGA GROUND DELAY PROGRAM
UNTIL 0459	-JFK GROUND DELAY PROGRAM
UNTIL 0459	-EWR GROUND DELAY PROGRAM
UNTIL 0559	-SFO GROUND DELAY PROGRAM
TERMINAL PLANNED:
AFTER 1100	-LGA GROUND STOP/DELAY PROGRAM PROBABLE
AFTER 1200	-IAH/HOU GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1500	-SFO GROUND DELAY PROGRAM PROBABLE
AFTER 1600	-DFW/DAL GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1800	-TPA/MCO GROUND STOP POSSIBLE
AFTER 1900	-ATL GROUND STOP POSSIBLE
AFTER 2000	-CLT GROUND STOP POSSIBLE
AFTER 2000	-DEN GROUND STOP POSSIBLE
```

Every advisory the linker could see for this element in the horizon:

```
(none)
```

Other advisories that name the element (not read by the linker):

```
20260520-171  sent 05/20 22:26Z  ATL CDRS_FYI
20260521-059  sent 05/21 12:11Z  ATL CDRS_FYI
20260521-093  sent 05/21 18:20Z  ATL CLT CDRS_FYI
20260521-125  sent 05/21 22:06Z  ATL CDRS_FYI
20260521-127  sent 05/21 22:12Z  ATL CLT CDRS_FYI
```

**Derived outcome: NOT ISSUED = 0**. no gs advisory for ATL in the window.

No advisory decides the outcome (nothing qualifying was found).

## 149. plan-20260506-040-SFO-gs+gdp-AFTER2100

- Term: **PROBABLE** (plan:PROBABLE); written as: `AFTER 2100	-SFO GROUND STOP/DELAY PROGRAM PROBABLE`
- Element: SFO; initiative: gs/gdp; first issued 05/06 13:57Z in 20260506-040; window read as 06/2100Z - 07/0800Z
- Repeated in: 20260506-052 20260506-063

Source advisory:

```
ATCSCC ADVZY 040 DCC 05/06/2026 OPERATIONS PLAN
TERMINAL ACTIVE:
UNTIL 2059	-SFO GROUND DELAY PROGRAM
TERMINAL PLANNED:
AFTER 1600	-LGA GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1600	-DCA GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1700	-EWR GROUND STOP/DELAY PROGRAM PROBABLE
AFTER 1700	-BOS GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1800	-JFK GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1900	-CLT GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 2100	-IAD/BWI GROUND STOP POSSIBLE
AFTER 2100	-SFO GROUND STOP/DELAY PROGRAM PROBABLE
UNTIL 0100	-DEN GROUND STOP/DELAY PROGRAM PROBABLE
```

Every advisory the linker could see for this element in the horizon:

```
20260506-030  sent 05/06 12:40Z  CDM PROPOSED GROUND DELAY PROGRAM  SFO  ANTICIPATED CUMULATIVE PROGRAM PERIOD 06/1500Z - 06/2059Z
20260506-031  sent 05/06 12:54Z  CDM GROUND DELAY PROGRAM  SFO  CUMULATIVE PROGRAM PERIOD 06/1500Z - 06/2059Z
20260506-065  sent 05/06 18:28Z  CDM PROPOSED GROUND DELAY PROGRAM  SFO  ANTICIPATED CUMULATIVE PROGRAM PERIOD 06/1500Z - 07/0659Z
20260506-066  sent 05/06 18:44Z  CDM GROUND DELAY PROGRAM  SFO  CUMULATIVE PROGRAM PERIOD 06/1500Z - 07/0659Z
20260507-012  sent 05/07 04:52Z  CDM GROUND DELAY PROGRAM CNX  SFO  GDP CNX PERIOD 07/0449Z - 07/0935Z
```

Other advisories that name the element (not read by the linker):

```
20260507-009  sent 05/07 02:33Z  SFO AIRPORT ARRIVAL DELAYS
```

**Derived outcome: ISSUED = 1**. CDM GROUND DELAY PROGRAM sent 06/1844Z, period 06/1500Z - 07/0452Z.

Advisory that decides the outcome:

```
ATCSCC ADVZY 066 SFO/ZOA 05/06/2026 CDM GROUND DELAY PROGRAM
CTL ELEMENT: SFO
ELEMENT TYPE: APT
ADL TIME: 1838Z
DELAY ASSIGNMENT MODE: UDP
ARRIVALS ESTIMATED FOR: 06/1838Z - 07/0659Z
CUMULATIVE PROGRAM PERIOD: 06/1500Z - 07/0659Z
PROGRAM RATE: 32/33/36/31/26/26/26/36/36/36/36/36/36
FLT INCL: ALL CONTIGUOUS US DEP
DEP SCOPE: (ALL+CZV_AP) ZLA ZAU ZLC ZTL ZDC ZNY ZHU ZJX ZFW ZOB ZDV
ZOA ZSE ZBW ZMA ZKC ZME ZID ZAB ZMP
CANADIAN DEP ARPTS INCLUDED: CYEG CYVR CYYC
DELAY ASSIGNMENT TABLE APPLIES TO: ZOA
MAXIMUM DELAY: 503
AVERAGE DELAY: 89
IMPACTING CONDITION: WEATHER / LOW CEILINGS
COMMENTS: GDP ADJUSTED FOR OVERAGES IN 18Z AND FLLIGHT CHECK
```

## 150. plan-20260409-069-SFO-gs+gdp-AFTER1500

- Term: **PROBABLE** (plan:PROBABLE); written as: `AFTER 1500	-SFO GROUND STOP/DELAY PROGRAM PROBABLE`
- Element: SFO; initiative: gs/gdp; first issued 04/09 23:35Z in 20260409-069; window read as 10/1500Z - 11/0800Z
- Repeated in: 20260410-011 20260410-027

Source advisory:

```
ATCSCC ADVZY 069 DCC 04/09/2026 OPERATIONS PLAN
EVENT TIME: 10/0000 - AND LATER
TERMINAL ACTIVE:
NONE
TERMINAL PLANNED:
AFTER 2200	-DEN GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1300	-AGS GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1500	-SFO GROUND STOP/DELAY PROGRAM PROBABLE
AFTER 1800	-IAH/HOU GROUND STOP/DELAY PROGRAM POSSIBLE
AFTER 1900	-AUS GROUND STOP POSSIBLE
AFTER 1900	-SAT GROUND STOP POSSIBLE
AFTER 2000	-DEN GROUND STOP/DELAY PROGRAM POSSIBLE
```

Every advisory the linker could see for this element in the horizon:

```
20260409-048  sent 04/09 19:32Z  CDM GROUND DELAY PROGRAM CNX  SFO  GDP CNX PERIOD 09/1930Z - 09/2339Z
20260409-070  sent 04/09 23:42Z  CDM GROUND DELAY PROGRAM  SFO  CUMULATIVE PROGRAM PERIOD 10/0215Z - 10/0559Z
20260410-006  sent 04/10 04:18Z  CDM GROUND DELAY PROGRAM CNX  SFO  GDP CNX PERIOD 10/0417Z - 10/1009Z
20260410-033  sent 04/10 12:39Z  CDM PROPOSED GROUND DELAY PROGRAM  SFO  ANTICIPATED CUMULATIVE PROGRAM PERIOD 10/1515Z - 10/2259Z
20260410-035  sent 04/10 12:50Z  CDM GROUND DELAY PROGRAM  SFO  CUMULATIVE PROGRAM PERIOD 10/1500Z - 10/2259Z
20260410-084  sent 04/10 22:23Z  CDM GROUND DELAY PROGRAM CNX  SFO  GDP CNX PERIOD 10/2220Z - 11/0217Z
20260411-003  sent 04/11 00:40Z  CDM PROPOSED GROUND DELAY PROGRAM  SFO  ANTICIPATED CUMULATIVE PROGRAM PERIOD 11/0230Z - 11/0559Z
20260411-006  sent 04/11 00:54Z  CDM GROUND DELAY PROGRAM  SFO  CUMULATIVE PROGRAM PERIOD 11/0230Z - 11/0559Z
20260411-012  sent 04/11 04:56Z  CDM GROUND DELAY PROGRAM CNX  SFO  GDP CNX PERIOD 11/0454Z - 11/0704Z
```

Other advisories that name the element (not read by the linker):

```
20260410-086  sent 04/10 23:04Z  SFO AIRPORT ARRIVAL DELAYS
```

**Derived outcome: ISSUED = 1**. CDM GROUND DELAY PROGRAM sent 10/1250Z, period 10/1500Z - 10/2223Z.

Advisory that decides the outcome:

```
ATCSCC ADVZY 035 SFO/ZOA 04/10/2026 CDM GROUND DELAY PROGRAM
CTL ELEMENT: SFO
ELEMENT TYPE: APT
ADL TIME: 1247Z
DELAY ASSIGNMENT MODE: UDP
ARRIVALS ESTIMATED FOR: 10/1500Z - 10/2259Z
CUMULATIVE PROGRAM PERIOD: 10/1500Z - 10/2259Z
PROGRAM RATE: 36
FLT INCL: ALL CONTIGUOUS US DEP
DEP SCOPE: 1400
CANADIAN DEP ARPTS INCLUDED: CYEG CYVR CYYC
DELAY ASSIGNMENT TABLE APPLIES TO: ZOA
MAXIMUM DELAY: 96
AVERAGE DELAY: 30
IMPACTING CONDITION: WEATHER / LOW CEILINGS
COMMENTS: ARR/DEP 28L/R, LOW POP-UP, TIME +45
```
