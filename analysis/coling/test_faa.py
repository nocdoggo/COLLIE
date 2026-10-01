"""Tests for the FAA advisory parser and the E6 statements (``faa.py``).

The fixtures are real advisories of 15 July 2024 from the design pilot
(``external_data/faa_atcscc/pilot_2024``), trimmed: delay counts, route tables and the long
sections of the operations plan are cut. Two fixtures are marked as edited copies. The HTML
fixture wraps a pilot advisory in the page layout the database served in 2026.

Run::

    PYTHONPATH=. python -m pytest analysis/coling/test_faa.py -q
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from analysis.coling import faa


def advisory(header: str, body: str, effective: str, signature: str, label: str = "MESSAGE:"):
    """An advisory in the tag-free layout of the pilot files."""
    return f"ATCSCC Advisory\n{header}\n{label}\n{body}\nEFFECTIVE TIME:\n{effective}\nSIGNATURE:\n{signature}\n"


def ground_stop(number, element, centre, adl, period, term, sent, effective, comments=""):
    return advisory(
        f"ATCSCC ADVZY {number} {element}/{centre} 07/15/2024 CDM GROUND STOP",
        f"CTL ELEMENT: {element}\nELEMENT TYPE: APT\nADL TIME: {adl}Z\n"
        f"GROUND STOP PERIOD: {period}\nDEP FACILITIES INCLUDED: (Manual) ZTL ZDC ZJX\n"
        f"PROBABILITY OF EXTENSION: {term}\nIMPACTING CONDITION: WEATHER / THUNDERSTORMS\n"
        f"COMMENTS: {comments}",
        effective,
        f"24/07/15 {sent}",
    )


# The Orlando ground stop of 15 July 2024: issued, extended four times, then cancelled.
MCO_106 = ground_stop(
    "106", "MCO", "ZJX", "2018", "15/2003Z - 15/2130Z", "MEDIUM", "20:19", "152019-152230"
)
MCO_118 = ground_stop(
    "118",
    "MCO",
    "ZJX",
    "2055",
    "15/2003Z - 15/2215Z",
    "MEDIUM",
    "20:59",
    "152057-152315",
    "DUE TO LACK OF ROUTES",
)
MCO_139 = ground_stop(
    "139", "MCO", "ZJX", "2149", "15/2134Z - 15/2300Z", "MEDIUM", "21:50", "152150-160000"
)
MCO_149 = ground_stop(
    "149", "MCO", "ZJX", "2220", "15/2134Z - 15/2330Z", "MEDIUM", "22:26", "152225-160030"
)
MCO_157 = ground_stop(
    "157", "MCO", "ZJX", "2316", "15/2306Z - 16/0030Z", "MEDIUM", "23:22", "152320-160130"
)
MCO_165 = advisory(
    "ATCSCC ADVZY 165 MCO/ZJX 07/15/2024 CDM GS CNX",
    "CTL ELEMENT: MCO\nELEMENT TYPE: APT\nADL TIME: 2347Z\nGS CNX PERIOD: 15/2347Z - 16/0432Z\nCOMMENTS:",
    "152348-160532",
    "24/07/15 23:48",
)
# Edited copy of 118: the same stated end sent again six minutes later (a reissue).
MCO_118_REISSUED = ground_stop(
    "119", "MCO", "ZJX", "2101", "15/2051Z - 15/2215Z", "HIGH", "21:05", "152105-152315"
)
MCO_CHAIN = (MCO_106, MCO_118, MCO_139, MCO_149, MCO_157, MCO_165)

ORD_016 = ground_stop(
    "016", "ORD", "ZAU", "0247", "15/0237Z - 15/0400Z", "MEDIUM", "02:52", "150252-150500"
)
ORD_021 = advisory(
    "ATCSCC ADVZY 021 ORD/ZAU 07/15/2024 CDM GS CNX",
    "CTL ELEMENT: ORD\nELEMENT TYPE: APT\nADL TIME: 0352Z\nGS CNX PERIOD: 15/0352Z - 15/0504Z\nCOMMENTS:",
    "150357-150604",
    "24/07/15 03:57",
)

SFO_041 = advisory(
    "ATCSCC ADVZY 041 SFO/ZOA 07/15/2024 CDM PROPOSED GROUND DELAY PROGRAM",
    "CTL ELEMENT: SFO\nELEMENT TYPE: APT\nADL TIME: 1236Z\nDELAY ASSIGNMENT MODE: UDP\n"
    "ARRIVALS ESTIMATED FOR: 15/1600Z - 15/1859Z\n"
    "ANTICIPATED CUMULATIVE PROGRAM PERIOD: 15/1600Z - 15/1859Z\n"
    "ANTICIPATED PROGRAM RATE: 36/36/40\nIMPACTING CONDITION: WEATHER / LOW CEILINGS\n"
    "COMMENTS: CONFERENCE AT 1245Z",
    "151238-151359",
    "24/07/15 12:39",
)
SFO_042 = advisory(
    "ATCSCC ADVZY 042 SFO/ZOA 07/15/2024 CDM GROUND DELAY PROGRAM",
    "CTL ELEMENT: SFO\nELEMENT TYPE: APT\nADL TIME: 1246Z\nDELAY ASSIGNMENT MODE: UDP\n"
    "ARRIVALS ESTIMATED FOR: 15/1600Z - 15/1859Z\n"
    "CUMULATIVE PROGRAM PERIOD: 15/1600Z - 15/1859Z\nPROGRAM RATE: 36/36/40\n"
    "IMPACTING CONDITION: WEATHER / LOW CEILINGS\n"
    "COMMENTS: ARR 28L, DEP 01L/01R, LOW POP UP, EXEMPT TIME +45",
    "151250-151959",
    "24/07/15 12:51",
)
SFO_082 = advisory(
    "ATCSCC ADVZY 082 SFO/ZOA 07/15/2024 CDM GROUND DELAY PROGRAM CNX",
    "CTL ELEMENT: SFO\nELEMENT TYPE: APT\nADL TIME: 1831Z\nGDP CNX PERIOD: 15/1831Z - 15/2047Z\n"
    "DISREGARD EDCTS FOR DEST SFO\nCOMMENTS:",
    "151836-152147",
    "24/07/15 18:37",
)

BOS_151 = advisory(
    "ATCSCC ADVZY 151 BOS/ZBW 07/15/2024 BOS GROUND STOP",
    "EVENT TIME: 15/2230 - 15/2330\nCONSTRAINED FACILITIES: ZBW\nDESTINATION AIRPORT: BOS\n"
    "DEP FACILITIES INCLUDED: ZOB\nPROBABILITY OF EXTENSION: MED\n"
    "IMPACTING CONDITION: LACK OF ROUTES",
    "152239-160000",
    "24/07/15 22:39",
)
BOS_136 = advisory(
    "ATCSCC ADVZY 136 BOS/ZBW 07/15/2024 BOS GROUND STOP CANCELLATION",
    "EVENT TIME: 15/2140 - 2140\nCONSTRAINED FACILITIES: ZBW\nDESTINATION AIRPORT: BOS\n"
    "RELEASED FACILITIES: ZAU\nREMARKS: GS CANCELLED FOR ZAU",
    "152142-152210",
    "24/07/15 21:42",
)

ROUTE_BODY_028 = (
    "NAME: FCA001:LAKE_ERIE_WEST_PARTIAL\nCONSTRAINED AREA: CZY\nREASON: OTHER\n"
    "INCLUDE TRAFFIC: KBUF/KROC/KSYR/ZBW DEPARTURES TO KORD\nFACILITIES INCLUDED: ZAU/ZBW/ZOB\n"
    "FLIGHT STATUS: ALL_FLIGHTS\nVALID: FCA ENTRY TIME FROM 151000 TO 151600\n"
    "PROBABILITY OF EXTENSION: LOW\nREMARKS: SEE DYNAMIC LIST FOR UPDATES. DUE TO REDUCED SYSTEM\n"
    "CAPACITY.\nASSOCIATED RESTRICTIONS:\nMODIFICATIONS:\nROUTES:\nFROM:\n"
    "ORIG                                 ROUTE - ORIGIN SEGMENTS\n"
    "KBUF                                 >DAVVK CHAAP\n"
    "TO:\n"
    "KORD                                 RAAKK Q436 EMMMA< WYNDE2\n"
    "TMI ID: RRDCC028"
)
ROUTE_028 = advisory(
    "ATCSCC ADVZY 028 DCC 07/15/2024 FCA RQD", ROUTE_BODY_028, "151000-151600", "24/07/15 10:02"
)
ROUTE_047 = advisory(
    "ATCSCC ADVZY 047 DCC 07/15/2024 FCA RQD",
    ROUTE_BODY_028.replace("TO 151600", "TO 151800")
    .replace("REMARKS: SEE", "REMARKS: REPLACES ADVZY 028. SEE")
    .replace("MODIFICATIONS:", "MODIFICATIONS: TIME EXTENDED"),
    "151000-151800",
    "24/07/15 13:37",
)
ROUTE_031 = advisory(
    "ATCSCC ADVZY 031 DCC 07/15/2024 ROUTE RQD /FL",
    "NAME: OHIO_VALLEY_TO_FLORIDA_2_PARTIAL\nCONSTRAINED AREA: ZJX\nREASON: WEATHER\n"
    "VALID: ETD 151130 TO 151530\nPROBABILITY OF EXTENSION: MODERATE\nREMARKS:\n"
    "TMI ID: RRDCC500\n151104-151530\n24/07/15 11:04  DCCOPS.lxstn32",
    "",
    "",
    label="RAW TEXT:",
).replace("EFFECTIVE TIME:\n\nSIGNATURE:\n\n", "")
ROUTE_040 = advisory(
    "ATCSCC ADVZY 040 DCC 07/15/2024 REROUTE CANCELLATION",
    "OHIO_VALLEY_TO_FLORIDA_2_PARTIAL HAS BEEN CANCELLED.\nREMARKS: CANCELS ADVZY 031\n"
    "ASSOCIATED RESTRICTIONS:",
    "151239-151530",
    "24/07/15 12:39",
)

PLAN_HEAD = (
    "___________________________________________________________________________\n"
    "SIGNIFICANT CONVECTIVE ACTIVITY REMAINS IN THE FORECAST THROUGHOUT MUCH\n"
    "OF THE NAS TODAY. TERMINAL/EN ROUTE INITIATIVES ARE POSSIBLE FROM BOS SOUTH\n"
    "TO FLORIDA WEST TO MSP AND SOUTH TO I90 TERMINALS.\n"
    "___________________________________________________________________________\n"
    "STAFFING TRIGGERS:\nUNTIL 0230\t-N90 - EWR AREA\n"
    "TERMINAL CONSTRAINT(S):\nBOS/N90/PHL/PCT/ATL/CLT/FLORIDA/MSP/DEN/C90/I90/LAS - TSTMS\n"
    "TERMINAL ACTIVE:\nNONE\nTERMINAL PLANNED:\n"
)
PLAN_TAIL = (
    "EN ROUTE CONSTRAINT(S):\nZNY/ZDC/ZJX/ZMA/ZID/ZOB/ZAU/ZFW/ZHU/ZDV/ZAB/ZLC/ZOA - TSTMS\n"
    "EN ROUTE ACTIVE:\nNONE\nEN ROUTE PLANNED:\n"
    "AFTER 1100\t-C90 ARRIVAL RTES POSSIBLE\n"
    "AFTER 1730\t-ORD/MDW CDRS SWAP EXPECTED\n"
    "CDR/SWAP/CAPPING/TUNNELING ADVISORIES/HOTLINES:\nUNTIL 0300\t-DEN_CDRS_SWAP\n"
    "RUNWAY/EQUIPMENT/SYSTEM IMPACT REPORTS (SIRs):\nATL - RWY 08R/26L CLOSED UNTIL 1130Z\n"
    "AIRSPACE FLOW PROGRAM(S) ACTIVE:\nNONE\nAIRSPACE FLOW PROGRAM(S) PLANNED:\nNONE\n"
    "PLANNED LAUNCH:\nSPACE X STARLINK 10-9, KENNEDY SPACE CENTER FL\n"
    "PRIMARY:\t07/18/24\t0613Z-1043Z\n"
    "FLIGHT CHECK(S):\nAFTER 0400\t-BOS\nAFTER 16/0400\t-EWR\n"
    "NEXT PLANNING WEBINAR: 1115Z\n"
)


def operations_plan(number: str, event: str, planned: str, effective: str, signature: str) -> str:
    return (
        f"ATCSCC Advisory\nATCSCC ADVZY {number} DCC 07/15/2024 OPERATIONS PLAN\nRAW TEXT:\n"
        f"EVENT TIME: {event} - AND LATER\n{PLAN_HEAD}{planned}{PLAN_TAIL}{effective}\n"
        f"{signature}  DCCOPS.lxstn35\n"
    )


PLANNED_013 = (
    "UNTIL 0400\t-ORD/MDW GROUND STOP POSSIBLE\n"
    "AFTER 1530\t-SFO GROUND STOP/DELAY PROGRAM POSSIBLE\n"
    "AFTER 1900\t-EWR/LGA/JFK GROUND STOP/DELAY PROGRAM PROBABLE\n"
    "AFTER 1900\t-BOS GROUND STOP POSSIBLE\n"
    "AFTER 1900\t-TPA/MCO GROUND STOP POSSIBLE\n"
)
PLAN_013 = operations_plan("013", "15/0200", PLANNED_013, "150123-150959", "24/07/15 01:23")
PLAN_026 = operations_plan("026", "15/1000", PLANNED_013, "150935-151159", "24/07/15 09:35")
# 033 drops the ORD/MDW line; 078 restates the New York line with an end and a new time.
PLAN_033 = operations_plan(
    "033", "15/1200", PLANNED_013.split("\n", 1)[1], "151151-151359", "24/07/15 11:51"
)
PLAN_078 = operations_plan(
    "078",
    "15/1800",
    "UNTIL 2300\t-EWR/LGA/JFK GROUND STOP/DELAY PROGRAM PROBABLE\n"
    "UNTIL 2300\t-BOS GROUND STOP POSSIBLE\nUNTIL 2300\t-TPA/MCO GROUND STOP POSSIBLE\n",
    "151736-151959",
    "24/07/15 17:36",
)

HTML_PAGE = (
    "<html><head><title>ATCSCC Advisory</title></head><BODY>\r\n"
    '<TABLE id="Table3" BORDER=0 CELLSPACING=2 CELLPADDING=1>\r\n<TR VALIGN="top" ALIGN="left">\r\n'
    '<TH class=header align="center" colspan=2>ATCSCC&nbsp;ADVZY&nbsp;028&nbsp;DCC&nbsp;'
    "07/15/2024&nbsp;FCA RQD</TH>\r\n</TR>\r\n<TR>\r\n<TD class=nam>\r\n"
    "<P align=right>MESSAGE:&nbsp;</P>\r\n</TD>\r\n<TD class=val>\r\n\t\t<PRE>"
    + ROUTE_BODY_028
    + "&nbsp;</PRE>\r\n</TD>\r\n</TR>\r\n<TR>\r\n<TD class=nam>\r\n"
    "<P align=right>EFFECTIVE TIME:&nbsp;</P>\r\n</TD>\r\n<TD class=val>151000-151600</TD>\r\n</TR>\r\n"
    "<TR>\r\n<TD class=nam>\r\n<P align=right>SIGNATURE:&nbsp;</P>\r\n</TD>\r\n"
    "<TD class=val>\r\n\t24/07/15 10:02&nbsp;&nbsp;\r\n</TD>\r\n</TR>\r\n</TABLE>\r\n"
    '<input type="button" value="< Back to Results" onClick="window.location=\'/adv/adv_list\';">\r\n'
    "</BODY></html>\r\n"
)

# The first lines of a pilot file as it sits on disk: tabs, a carriage return, a button.
PILOT_LAYOUT = (
    "\t\tATCSCC Advisory\r\n\t\t\t\t\tATCSCC ADVZY 100 HOU/ZHU 07/15/2024 CDM GROUND STOP\r\n"
    "\t\t\t\t\t\tMESSAGE: \r\n\t\t\t\t\t\tCTL ELEMENT: HOU\nELEMENT TYPE: APT\nADL TIME: 1950Z\n"
    "GROUND STOP PERIOD: 15/1918Z - 15/2115Z\nDEP FACILITIES INCLUDED: (Manual) ZHU ZFW  \n"
    "PROBABILITY OF EXTENSION: LOW\nIMPACTING CONDITION: RWY-TAXI / OBSTRUCTION\nCOMMENTS:  \r\n"
    "\t\t\t\t\t\t\tEFFECTIVE TIME: \r\n\t\t\t\t\t\t151951-152215\r\n\t\t\t\t\t\t\tSIGNATURE: \r\n"
    "\t\t\t\t\t\t\t24/07/15 19:51  \r\n"
    '\t\t\t\t<input type="button" value="< Back to Results"\r\n'
)


def parse_all(*texts: str) -> list[faa.Advisory]:
    advisories = [faa.parse_advisory(text) for text in texts]
    return sorted(advisories, key=lambda a: (a.sent, a.number))


# --------------------------------------------------------------------------------------
# Advisories
# --------------------------------------------------------------------------------------


def test_ground_stop_fields_from_the_pilot_layout():
    a = faa.parse_advisory(PILOT_LAYOUT)
    assert (a.id, a.number, a.day) == ("20240715-100", 100, dt.date(2024, 7, 15))
    assert (a.facility, a.title, a.kind) == ("HOU/ZHU", "CDM GROUND STOP", "gs")
    assert (a.element, a.element_type) == ("HOU", "APT")
    assert a.sent == dt.datetime(2024, 7, 15, 19, 51)
    assert a.period == (dt.datetime(2024, 7, 15, 19, 18), dt.datetime(2024, 7, 15, 21, 15))
    assert a.period_label == "GROUND STOP PERIOD"
    assert a.prob_extension == "LOW"
    assert a.text.splitlines()[0] == "ATCSCC ADVZY 100 HOU/ZHU 07/15/2024 CDM GROUND STOP"
    assert "EFFECTIVE TIME" not in a.text and "151951" not in a.text and "<input" not in a.text


def test_html_page_keeps_angle_brackets_in_the_message():
    a = faa.parse_advisory(HTML_PAGE)
    assert (a.number, a.kind, a.title) == (28, "reroute", "FCA RQD")
    assert a.sent == dt.datetime(2024, 7, 15, 10, 2)
    assert a.route_name == "FCA001:LAKE_ERIE_WEST_PARTIAL"
    assert a.tmi_id == "RRDCC028"  # sits after the route table, whose lines hold < and >
    assert ">DAVVK CHAAP" in a.text and "EMMMA< WYNDE2" in a.text
    assert a.prob_extension == "LOW"
    assert a.period == (dt.datetime(2024, 7, 15, 10, 0), dt.datetime(2024, 7, 15, 16, 0))
    assert a == faa.parse_advisory(ROUTE_028)  # the same record from the tag-free layout


@pytest.mark.parametrize(
    ("title", "kind"),
    [
        ("CDM GROUND STOP", "gs"),
        ("CDM GS CNX", "gs_cnx"),
        ("CDM PROPOSED GROUND DELAY PROGRAM", "gdp_proposed"),
        ("CDM GROUND DELAY PROGRAM", "gdp"),
        ("CDM GROUND DELAY PROGRAM CNX", "gdp_cnx"),
        ("CDM PROPOSED AIRSPACE FLOW PROGRAM", "afp_proposed"),
        ("CDM AIRSPACE FLOW PROGRAM", "afp"),
        ("CDM AIRSPACE FLOW PROGRAM CNX", "afp_cnx"),
        ("BOS GROUND STOP", "gs_manual"),
        ("NY METS GROUND STOP CANCELLATION", "gs_manual_cnx"),
        ("DFW CAT I GROUND STOP (DVRSN EXEMPT)", "gs_manual"),
        ("CDW GS EXTENSION", "gs_manual"),
        ("LGA/JFK GROUND STOP CANCELLATION FOR DAL AND SUBS", "gs_manual_cnx"),
        ("CYUL GS CNX", "gs_manual_cnx"),
        ("OPERATIONS PLAN", "ops_plan"),
        ("ROUTE RQD /FL", "reroute"),
        ("FCA RQD", "reroute"),
        ("ROUTE FYI", "reroute"),
        ("REROUTE CANCELLATION", "reroute_cnx"),
        ("JVY GROUND DELAY PROGRAM CANCELLATION", "gdp_cnx"),
        ("VANCOUVER GDP CANCELLED", "gdp_cnx"),
        ("CYYZ GROUND DELAY PROGRAM", "gdp"),
        ("SFO CDM GROUND DELAY PROGRAM CORRECTION", "other"),
        ("O'HARE AIRPORT ARRIVAL DELAYS", "other"),
        ("VOLCANIC ACTIVITY BULLETIN - SANGAY", "other"),
        ("ZNY SWAP IMPLEMENTATION PLAN_FYI", "other"),
    ],
)
def test_classify(title, kind):
    assert faa.classify(title) == kind


def test_programme_periods_and_proposed_variants():
    proposed, actual, cancelled = parse_all(SFO_041, SFO_042, SFO_082)
    assert [a.kind for a in (proposed, actual, cancelled)] == ["gdp_proposed", "gdp", "gdp_cnx"]
    assert proposed.period_label == "ANTICIPATED CUMULATIVE PROGRAM PERIOD"
    assert actual.period == (dt.datetime(2024, 7, 15, 16, 0), dt.datetime(2024, 7, 15, 18, 59))
    assert cancelled.period[0] == dt.datetime(2024, 7, 15, 18, 31)
    assert proposed.prob_extension is None and actual.element == "SFO"


def test_cancellation_under_the_programme_title_is_a_cancellation():
    # edited copy of 082: NAV CANADA relays cancellations under the title of the programme
    relayed = SFO_082.replace("PROGRAM CNX", "PROGRAM").replace("SFO", "CYYZ")
    a = faa.parse_advisory(relayed)
    assert (a.title, a.kind, a.element) == ("CDM GROUND DELAY PROGRAM", "gdp_cnx", "CYYZ")
    assert a.period_label == "GDP CNX PERIOD" and a.period[0] == dt.datetime(2024, 7, 15, 18, 31)
    assert faa.parse_advisory(SFO_042).kind == "gdp"  # a programme with its own period stays one


def test_manual_ground_stop_keeps_the_term_as_written():
    stop, cancellation = faa.parse_advisory(BOS_151), faa.parse_advisory(BOS_136)
    assert (stop.kind, stop.element, stop.prob_extension) == ("gs_manual", "BOS", "MED")
    assert stop.period == (dt.datetime(2024, 7, 15, 22, 30), dt.datetime(2024, 7, 15, 23, 30))
    assert cancellation.kind == "gs_manual_cnx" and cancellation.element == "BOS"
    # "15/2140 - 2140": the end has no day and is read on the start's day
    assert cancellation.period == (dt.datetime(2024, 7, 15, 21, 40),) * 2


def test_period_crosses_a_month_end_and_tolerates_a_broken_end():
    reference = dt.datetime(2026, 3, 31, 23, 26)
    body = "GROUND STOP PERIOD: 31/2311Z - 01/0030Z"
    assert faa._period("gs", body, reference)[:2] == (
        dt.datetime(2026, 3, 31, 23, 11),
        dt.datetime(2026, 4, 1, 0, 30),
    )
    start, end, label = faa._period("gs_manual", "EVENT TIME: 31/1400 - 31/153", reference)
    assert (start, end, label) == (dt.datetime(2026, 3, 31, 14, 0), None, "EVENT TIME")
    assert faa._period("ops_plan", "EVENT TIME: 31/1000 - AND LATER", reference)[1] is None
    # a mistyped day would make the stop run for eleven days: the end is not read
    typo = faa._period(
        "gs_manual", "EVENT TIME: 25/0040 - 05/0200", dt.datetime(2026, 5, 25, 0, 42)
    )
    assert typo[:2] == (dt.datetime(2026, 5, 25, 0, 40), None)


def test_reroute_cancellation_names_the_route():
    route, cancellation = faa.parse_advisory(ROUTE_031), faa.parse_advisory(ROUTE_040)
    assert (route.kind, route.prob_extension, route.tmi_id) == ("reroute", "MODERATE", "RRDCC500")
    assert route.sent == dt.datetime(2024, 7, 15, 11, 4)  # signature inside the raw text
    assert "DCCOPS" not in route.text
    assert route.period == (dt.datetime(2024, 7, 15, 11, 30), dt.datetime(2024, 7, 15, 15, 30))
    assert cancellation.kind == "reroute_cnx"
    assert cancellation.route_name == "OHIO_VALLEY_TO_FLORIDA_2_PARTIAL"


# --------------------------------------------------------------------------------------
# Operations plan lines
# --------------------------------------------------------------------------------------


def test_operations_plan_lines():
    plan = faa.parse_advisory(PLAN_013)
    assert plan.kind == "ops_plan" and plan.sent == dt.datetime(2024, 7, 15, 1, 23)
    assert plan.period[0] == dt.datetime(2024, 7, 15, 2, 0)
    terminal = [x for x in plan.plan_lines if x.section == "TERMINAL PLANNED"]
    assert [(x.qualifier, x.time_text, x.airports, x.initiatives, x.term) for x in terminal] == [
        ("UNTIL", "0400", ("ORD", "MDW"), ("gs",), "POSSIBLE"),
        ("AFTER", "1530", ("SFO",), ("gs", "gdp"), "POSSIBLE"),
        ("AFTER", "1900", ("EWR", "LGA", "JFK"), ("gs", "gdp"), "PROBABLE"),
        ("AFTER", "1900", ("BOS",), ("gs",), "POSSIBLE"),
        ("AFTER", "1900", ("TPA", "MCO"), ("gs",), "POSSIBLE"),
    ]
    assert terminal[1].raw == "AFTER 1530\t-SFO GROUND STOP/DELAY PROGRAM POSSIBLE"
    # en-route lines are parsed but name no ground stop or delay programme
    en_route = [x for x in plan.plan_lines if x.section == "EN ROUTE PLANNED"]
    assert [(x.element_text, x.initiatives, x.term) for x in en_route] == [
        ("C90 ARRIVAL RTES", (), "POSSIBLE"),
        ("ORD/MDW CDRS SWAP", (), "EXPECTED"),
    ]
    # staffing triggers, hotlines, launches and flight checks are not planned initiatives
    assert {x.section for x in plan.plan_lines} == {"TERMINAL PLANNED", "EN ROUTE PLANNED"}


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("UNTIL 2300 \t-TEB GDP PROBABLE", ("UNTIL", "2300", ("TEB",), ("gdp",), "PROBABLE")),
        (
            "AFTER 1100\t-LGA GROUND DELAY PROGRAM EXPECTED",
            ("AFTER", "1100", ("LGA",), ("gdp",), "EXPECTED"),
        ),
        (
            "AFTER 16/0400\t-EWR GROUND STOP POSSIBLE",
            ("AFTER", "16/0400", ("EWR",), ("gs",), "POSSIBLE"),
        ),
        ("AFTER O400\t-PHL GROUND STOP POSSIBLE", ("AFTER", "0400", ("PHL",), ("gs",), "POSSIBLE")),
        (
            "1400 - 2159\t-DEN GROUND STOP POSSIBLE",
            ("RANGE", "1400-2159", ("DEN",), ("gs",), "POSSIBLE"),
        ),
        # areas, centres and free text are not airports; a misspelt term is no term (no statement)
        ("AFTER 1900\t-N90 GROUND STOP POSSIBLE", ("AFTER", "1900", (), ("gs",), "POSSIBLE")),
        ("AFTER 1900\t-NY METS GROUND STOP POSSIBLE", ("AFTER", "1900", (), ("gs",), "POSSIBLE")),
        (
            "UNTIL 2300\t-EWR/EWR SATS GROUND STOP/DELAY PROGRAM POSSIBLE",
            ("UNTIL", "2300", ("EWR",), ("gs", "gdp"), "POSSIBLE"),
        ),
        (
            "AFTER 1900\t-ZNY/PHL GROUND STOP POSSIBLE",
            ("AFTER", "1900", ("PHL",), ("gs",), "POSSIBLE"),
        ),
        ("AFTER 1900\t-ATL GROUND STOP PROSSIBLE", ("AFTER", "1900", ("ATL",), ("gs",), None)),
        # a negated term is a term of its own, never the term it negates
        (
            "AFTER 1900\t-ATL GROUND STOP NOT EXPECTED",
            ("AFTER", "1900", ("ATL",), ("gs",), "NOT EXPECTED"),
        ),
        (
            "UNTIL 0200\t-EWR/LGA GROUND STOP/DELAY PROGRAM NO LONGER PROBABLE",
            ("UNTIL", "0200", ("EWR", "LGA"), ("gs", "gdp"), "NO LONGER PROBABLE"),
        ),
        ("AFTER 1900\t-NO ATL GROUND STOP EXPECTED", ("AFTER", "1900", (), ("gs",), "EXPECTED")),
        # a slip of one letter in the initiative's name is read as the name (May 2026)
        (
            "AFTER 1100\t-DCA GROUND STOO/DELAY PROGRAM POSSIBLE",
            ("AFTER", "1100", ("DCA",), ("gs", "gdp"), "POSSIBLE"),
        ),
        (
            "UNTIL 0200\t-BOS GROUND STOP/DELAY PROGRAOM POSSIBLE",
            ("UNTIL", "0200", ("BOS",), ("gs", "gdp"), "POSSIBLE"),
        ),
        (
            "UNTIL 0200\t-BOS GROUND DELAY PROGRAOM POSSIBLE",
            ("UNTIL", "0200", ("BOS",), ("gdp",), "POSSIBLE"),
        ),
        (
            "AFTER 1900\t-STP GROUNG STOPS PROBABLE",
            ("AFTER", "1900", ("STP",), ("gs",), "PROBABLE"),
        ),
        # two slips, or a slip in a word that stands alone, are not read
        ("AFTER 1900\t-ATL GRUOND STPO POSSIBLE", ("AFTER", "1900", (), (), "POSSIBLE")),
        ("AFTER 1900\t-STP/STOO DELAYS POSSIBLE", ("AFTER", "1900", ("STP",), (), "POSSIBLE")),
    ],
)
def test_plan_line_forms(line, expected):
    parsed = faa.parse_plan_line("TERMINAL PLANNED", line)
    assert (
        parsed.qualifier,
        parsed.time_text,
        parsed.airports,
        parsed.initiatives,
        parsed.term,
    ) == expected


def test_untimed_lines_are_not_plan_lines():
    assert faa.parse_plan_line("TERMINAL PLANNED", "NONE") is None
    assert faa.parse_plan_line("TERMINAL PLANNED", "ATL - RWY 08R/26L CLOSED UNTIL 1130Z") is None


def test_one_letter_slips():
    assert faa._one_slip("STOO", "STOP") and faa._one_slip("PROGRAOM", "PROGRAM")
    assert faa._one_slip("PROGRM", "PROGRAM") and faa._one_slip("PORGRAM", "PROGRAM")
    assert not faa._one_slip("STOP", "STOP") and not faa._one_slip("STPO0", "STOP")
    # names spelt right are kept as written, plural or not
    assert faa._respell("EWR GROUND STOP/DELAY PROGRAMS") == "EWR GROUND STOP/DELAY PROGRAMS"
    assert faa._respell("ORD/MDW GROUND STOPS") == "ORD/MDW GROUND STOPS"
    assert faa._respell("DCA GROUND STOO/DELAY PROGRAM") == "DCA GROUND STOP/DELAY PROGRAM"


def test_wrapped_line_with_two_estimates_gives_one_line_each():
    # plan 059 of 4 May 2026: two lines the issuer wrapped, each with two terms
    planned = (
        "AFTER 2200\t-ORD GROUND DELAY PROGRAM EXPECTED, ORD/MDW GROUND\nSTOPS POSSIBLE\n"
        "AFTER 2200\t-DEN GROUND DELAY PROGRAM EXPECTED, GROUND STOP\nPOSSIBLE\n"
        "AFTER 0100\t-SFO GROUND STOP/DELAY PROGRAM POSSIBLE\n"
    )
    plan = faa.parse_advisory(
        operations_plan("059", "15/2200", planned, "152149-152359", "24/07/15 21:49")
    )
    terminal = [x for x in plan.plan_lines if x.section == "TERMINAL PLANNED"]
    assert [(x.airports, x.initiatives, x.term) for x in terminal] == [
        (("ORD",), ("gdp",), "EXPECTED"),
        (("ORD", "MDW"), ("gs",), "POSSIBLE"),
        (("DEN",), ("gdp",), "EXPECTED"),
        (("DEN",), ("gs",), "POSSIBLE"),  # the second estimate is about the first one's airport
        (("SFO",), ("gs", "gdp"), "POSSIBLE"),
    ]
    assert terminal[2].raw == terminal[3].raw  # both keep the whole entry as written
    assert terminal[3].raw == "AFTER 2200\t-DEN GROUND DELAY PROGRAM EXPECTED, GROUND STOP POSSIBLE"
    statements = {s.sid: s.term for s in faa.plan_statements([plan])}
    assert statements == {
        "plan-20240715-059-ORD-gdp-AFTER2200": "EXPECTED",
        "plan-20240715-059-ORD-gs-AFTER2200": "POSSIBLE",
        "plan-20240715-059-MDW-gs-AFTER2200": "POSSIBLE",
        "plan-20240715-059-DEN-gdp-AFTER2200": "EXPECTED",
        "plan-20240715-059-DEN-gs-AFTER2200": "POSSIBLE",
        "plan-20240715-059-SFO-gs+gdp-AFTER0100": "POSSIBLE",
    }
    # the sections after the planned lines are not swallowed by the wrapped line
    assert {x.section for x in plan.plan_lines} == {"TERMINAL PLANNED", "EN ROUTE PLANNED"}
    # a comma that does not separate two estimates leaves the line as it was
    one = faa.parse_plan_entry("TERMINAL PLANNED", "AFTER 1900\t-EWR, LGA GROUND STOP POSSIBLE")
    assert [(x.airports, x.term) for x in one] == [((), "POSSIBLE")]


def test_a_negated_line_is_not_a_statement_of_the_term_it_negates():
    plan = operations_plan(
        "013",
        "15/0200",
        "AFTER 1900\t-BOS GROUND STOP NOT EXPECTED\nAFTER 1900\t-TPA GROUND STOP EXPECTED\n",
        "150123-150959",
        "24/07/15 01:23",
    )
    statements = faa.plan_statements(parse_all(plan))
    assert {(s.element, s.term, s.stratum) for s in statements} == {
        ("BOS", "NOT EXPECTED", "plan:NOT EXPECTED"),
        ("TPA", "EXPECTED", "plan:EXPECTED"),
    }


def test_plan_window():
    def window(text, issued):
        line = faa.parse_plan_line("TERMINAL PLANNED", text)
        return faa.plan_window(line, issued)

    early = dt.datetime(2024, 7, 15, 1, 23)
    assert window("UNTIL 0400\t-ORD GROUND STOP POSSIBLE", early) == (
        early,
        dt.datetime(2024, 7, 15, 4, 0),
    )
    # AFTER: from the stated start to the end of the operating day (next 0800Z)
    assert window("AFTER 1900\t-BOS GROUND STOP POSSIBLE", early) == (
        dt.datetime(2024, 7, 15, 19, 0),
        dt.datetime(2024, 7, 16, 8, 0),
    )
    late = dt.datetime(2024, 7, 15, 23, 48)
    assert window("AFTER 0345\t-MEM GROUND STOP POSSIBLE", late) == (
        dt.datetime(2024, 7, 16, 3, 45),
        dt.datetime(2024, 7, 16, 8, 0),
    )
    assert window("UNTIL 0200\t-LAS GROUND STOP POSSIBLE", late)[1] == dt.datetime(
        2024, 7, 16, 2, 0
    )
    assert window("AFTER 16/0400\t-EWR GROUND STOP POSSIBLE", early)[0] == dt.datetime(
        2024, 7, 16, 4, 0
    )
    assert window("1400 - 2159\t-DEN GROUND STOP POSSIBLE", early) == (
        dt.datetime(2024, 7, 15, 14, 0),
        dt.datetime(2024, 7, 15, 21, 59),
    )


def test_after_window_counts_from_the_issuance_or_from_a_late_plans_own_start():
    line = faa.parse_plan_line("TERMINAL PLANNED", "AFTER 2300\t-SEA GROUND STOP POSSIBLE")
    # plan 098 of 14 May 2026: sent 2327Z for the day that starts at 0000Z. "AFTER 2300" is the
    # next day's 2300Z, not the 2300Z that passed 27 minutes before the plan was sent.
    sent, event = dt.datetime(2026, 5, 14, 23, 27), dt.datetime(2026, 5, 15, 0, 0)
    next_day = (dt.datetime(2026, 5, 15, 23, 0), dt.datetime(2026, 5, 16, 8, 0))
    assert faa.plan_window(line, sent, event_start=event) == next_day
    assert faa.plan_window(line, sent) == next_day
    # a plan for 2300Z that was sent at 2320Z means the 2300Z of its own start
    late = dt.datetime(2026, 5, 14, 23, 20)
    assert faa.plan_window(line, late, event_start=dt.datetime(2026, 5, 14, 23, 0)) == (
        dt.datetime(2026, 5, 14, 23, 0),
        dt.datetime(2026, 5, 15, 8, 0),
    )
    # an event time that is mistyped (a day early) or long past is not used
    for wrong in (dt.datetime(2026, 5, 13, 23, 0), dt.datetime(2026, 5, 14, 22, 0)):
        assert faa.plan_window(line, late, event_start=wrong) == next_day
    # UNTIL is never moved: it runs from the issuance
    until = faa.parse_plan_line("TERMINAL PLANNED", "UNTIL 2300\t-SEA GROUND STOP POSSIBLE")
    assert faa.plan_window(until, late, event_start=dt.datetime(2026, 5, 14, 23, 0)) == (
        late,
        dt.datetime(2026, 5, 15, 23, 0),
    )
    # the statement takes the event time from its first plan
    plan = operations_plan(
        "098",
        "16/0000",
        "AFTER 2300\t-SEA GROUND STOP POSSIBLE\n",
        "152327-160159",
        "24/07/15 23:27",
    )
    (statement,) = faa.plan_statements(parse_all(plan))
    assert (statement.window_start, statement.lead_minutes) == (
        dt.datetime(2024, 7, 16, 23, 0),
        23 * 60 + 33,
    )


# --------------------------------------------------------------------------------------
# Statements
# --------------------------------------------------------------------------------------


def test_ground_stop_statements_one_per_stated_end():
    statements = faa.gs_statements(parse_all(*MCO_CHAIN))
    assert [s.sid for s in statements] == [
        f"gs-20240715-{n}" for n in ("106", "118", "139", "149", "157")
    ]
    first = statements[0]
    assert (first.family, first.term, first.element, first.initiative) == (
        "gs",
        "MEDIUM",
        "MCO",
        "gs",
    )
    assert first.issued == dt.datetime(2024, 7, 15, 20, 19)
    assert first.window_end == dt.datetime(2024, 7, 15, 21, 30)
    assert first.lead_minutes == 71
    assert first.line == "PROBABILITY OF EXTENSION: MEDIUM"
    assert all(len(s.episode) == 5 and s.episode_end == "cancelled" for s in statements)
    assert all(s.cancel_id == "20240715-165" for s in statements)
    assert first.stratum == "gs:MEDIUM"


def test_reissue_with_the_same_end_is_one_statement_at_first_issuance():
    statements = faa.gs_statements(parse_all(*MCO_CHAIN, MCO_118_REISSUED))
    second = statements[1]
    assert second.sources == ("20240715-118", "20240715-119")
    assert second.issued == dt.datetime(2024, 7, 15, 20, 59)
    assert (second.term, second.terms_seen) == ("MEDIUM", ("MEDIUM", "HIGH"))
    assert len(statements) == 5


def test_a_cancellation_or_a_gap_ends_the_stop():
    # ORD: stop 0237-0400, cancelled at 0357. A later, separate stop is a new episode.
    later = ground_stop(
        "120", "ORD", "ZAU", "2010", "15/2000Z - 15/2100Z", "LOW", "20:12", "152012-152200"
    )
    statements = faa.gs_statements(parse_all(ORD_016, ORD_021, later))
    assert [(s.sid, s.episode_end, len(s.episode)) for s in statements] == [
        ("gs-20240715-016", "cancelled", 1),
        ("gs-20240715-120", "lapsed", 1),
    ]
    # without the cancellation the gap alone separates them (start after the earlier end)
    statements = faa.gs_statements(parse_all(ORD_016, later))
    assert [s.episode_end for s in statements] == ["lapsed", "lapsed"]
    assert [len(s.episode) for s in statements] == [1, 1]


def test_a_late_cancellation_still_separates_two_stops():
    # ORD: stop 0237-0400; the cancellation comes at 0405, after the stated end; a stop sent at
    # 0410 restates the old start. The cancellation in between makes it a new stop.
    late_cancel = ORD_021.replace("03:57", "04:05")
    restated = ground_stop(
        "030", "ORD", "ZAU", "0408", "15/0237Z - 15/0500Z", "MEDIUM", "04:10", "150410-150600"
    )
    statements = faa.gs_statements(parse_all(ORD_016, late_cancel, restated))
    assert [(len(s.episode), s.episode_end, s.cancel_id) for s in statements] == [
        (1, "lapsed", ""),  # the stop had run out before it was cancelled
        (1, "lapsed", ""),
    ]
    assert [len(s.episode) for s in faa.gs_statements(parse_all(ORD_016, restated))] == [2, 2]


def test_a_cancellation_closes_only_the_stop_sent_before_it():
    # a new stop (022) sent in the same minute as the cancellation (021) of the earlier one
    same_minute = ground_stop(
        "022", "ORD", "ZAU", "0355", "15/0357Z - 15/0500Z", "LOW", "03:57", "150357-150600"
    )
    statements = faa.gs_statements(parse_all(ORD_016, ORD_021, same_minute))
    assert [(s.sid, s.episode_end, s.cancel_id) for s in statements] == [
        ("gs-20240715-016", "cancelled", "20240715-021"),
        ("gs-20240715-022", "lapsed", ""),
    ]


def test_canadian_airports_give_no_statement():
    assert faa.in_scope("ORD") and faa.in_scope("AGS") and not faa.in_scope("CYYZ")
    toronto = ground_stop(
        "050", "CYYZ", "CZY", "1000", "15/0958Z - 15/1130Z", "MEDIUM", "10:02", "151002-151230"
    )
    assert faa.gs_statements(parse_all(toronto)) == []
    plan = operations_plan(
        "013",
        "15/0200",
        "AFTER 1900\t-CYYZ/BOS GROUND DELAY PROGRAM POSSIBLE\n",
        "150123-150959",
        "24/07/15 01:23",
    )
    assert [s.element for s in faa.plan_statements(parse_all(plan))] == ["BOS"]


def test_grace_joins_a_stop_that_restarts_shortly_after_its_end():
    restart = ground_stop(
        "030", "ORD", "ZAU", "0417", "15/0407Z - 15/0500Z", "MEDIUM", "04:20", "150420-150600"
    )
    advisories = parse_all(ORD_016, restart)
    assert [len(s.episode) for s in faa.gs_statements(advisories, grace=0)] == [1, 1]
    assert [len(s.episode) for s in faa.gs_statements(advisories, grace=15)] == [2, 2]


def test_manual_ground_stops_make_no_statement():
    assert faa.gs_statements(parse_all(BOS_151, BOS_136)) == []


def test_route_statements_and_identity():
    advisories = parse_all(ROUTE_028, ROUTE_047, ROUTE_031, ROUTE_040)
    statements = {s.sid: s for s in faa.route_statements(advisories)}
    assert set(statements) == {"route-20240715-028", "route-20240715-047", "route-20240715-031"}
    first = statements["route-20240715-028"]
    assert (first.term, first.key, first.initiative) == ("LOW", "RRDCC028", "reroute")
    assert first.episode == ("20240715-028", "20240715-047")
    cancelled = statements["route-20240715-031"]
    assert (cancelled.episode_end, cancelled.cancel_id) == ("cancelled", "20240715-040")
    # the same TMI ID under another name is another route
    other = faa.parse_advisory(
        ROUTE_047.replace("FCA001:LAKE_ERIE_WEST_PARTIAL", "KDEN_CDRS_SWAP").replace(
            "REPLACES ADVZY 028. ", ""
        )
    )
    assert not faa.same_route(advisories[0], other)
    assert faa.same_route(advisories[0], faa.parse_advisory(ROUTE_047))


def test_plan_statements_chain_at_first_issuance():
    plans = parse_all(PLAN_013, PLAN_026, PLAN_033, PLAN_078)
    statements = {s.sid: s for s in faa.plan_statements(plans)}
    # 9 airport lines in the first plan, 6 restated with a new window in the last
    assert len(statements) == 15
    ord_ = statements["plan-20240715-013-ORD-gs-UNTIL0400"]
    assert ord_.sources == ("20240715-013", "20240715-026")  # dropped from plan 033
    assert (ord_.term, ord_.initiative, ord_.element) == ("POSSIBLE", "gs", "ORD")
    assert (ord_.window_start, ord_.window_end) == (
        dt.datetime(2024, 7, 15, 1, 23),
        dt.datetime(2024, 7, 15, 4, 0),
    )
    assert ord_.lead_minutes == 0
    ewr = statements["plan-20240715-013-EWR-gs+gdp-AFTER1900"]
    assert ewr.sources == ("20240715-013", "20240715-026", "20240715-033")
    assert (ewr.term, ewr.initiative, ewr.stratum) == ("PROBABLE", "gs/gdp", "plan:PROBABLE")
    assert ewr.lead_minutes == 17 * 60 + 37
    assert ewr.line == "AFTER 1900\t-EWR/LGA/JFK GROUND STOP/DELAY PROGRAM PROBABLE"
    restated = statements["plan-20240715-078-EWR-gs+gdp-UNTIL2300"]
    assert restated.issued == dt.datetime(2024, 7, 15, 17, 36)
    assert restated.window_end == dt.datetime(2024, 7, 15, 23, 0)


def test_a_line_that_returns_after_a_gap_starts_a_new_chain():
    plans = parse_all(
        PLAN_013, PLAN_033, PLAN_026.replace("ADVZY 026", "ADVZY 050").replace("09:35", "13:35")
    )
    ord_chains = [s for s in faa.plan_statements(plans) if s.element == "ORD"]
    assert [s.sources for s in ord_chains] == [("20240715-013",), ("20240715-050",)]


# --------------------------------------------------------------------------------------
# Development / test separation
# --------------------------------------------------------------------------------------


def listing(day: str, numbers) -> str:
    """A day's list page as the database serves it, cut down to the advisory links."""
    link = '<a href="adv_otherdis?adv_date={stamp}&advn={n}">{n}</a>'
    stamp = f"{day[4:]}{day[:4]}"
    return f"ADVISORIES FOR {day[:4]}-{day[4:6]}-{day[6:]}" + "".join(
        link.format(stamp=stamp, n=n) for n in numbers
    )


def write_day(root, day: str, pages: dict[str, str], listed: bool = True) -> None:
    """Save pages for one day, with a list page that names them unless one is given."""
    folder = root / day
    folder.mkdir(parents=True, exist_ok=True)
    if listed and "list.html" not in pages:
        numbers = [int(name[4:7]) for name in pages if name.startswith("adv_")]
        pages = pages | {"list.html": listing(day, numbers)}
    for name, text in pages.items():
        (folder / name).write_text(text, encoding="latin-1")


def write_month(root, month: str) -> None:
    """Every day of a month on disk, each with a list page that names no advisory."""
    for day in faa.month_days(month):
        write_day(root, f"{day:%Y%m%d}", {})


def page_2026(text: str, date: str) -> str:
    """A pilot fixture re-dated (the loader reads the day from the advisory itself)."""
    month, day = date[4:6], date[6:8]
    text = text.replace("07/15/2024", f"{month}/{day}/2026").replace(
        "24/07/15", f"26/{month}/{day}"
    )
    return text.replace(" 15/", f" {day}/")


@pytest.fixture
def opened(monkeypatch):
    """Every path opened through pathlib while the test runs."""
    seen: list[str] = []
    for name in ("open", "read_text", "read_bytes"):
        original = getattr(Path, name)

        def spy(self, *args, _original=original, **kwargs):
            seen.append(str(self))
            return _original(self, *args, **kwargs)

        monkeypatch.setattr(Path, name, spy)
    return seen


@pytest.fixture
def test_month_on_disk(tmp_path):
    """April complete with one stop, and a June day with a list page and two advisories."""
    write_month(tmp_path, "2026-04")
    write_day(tmp_path, "20260331", {"adv_016.html": page_2026(ORD_016, "20260331")})
    write_day(tmp_path, "20260415", {"adv_016.html": page_2026(ORD_016, "20260415")})
    june = {f"adv_{n:03d}.html": page_2026(ORD_016, "20260601") for n in (1, 2)}
    write_day(tmp_path, "20260601", june | {"list.html": listing("20260601", (1, 2, 3))})
    return tmp_path


FLAG = faa.AMENDMENT_FLAG_NAME


def test_test_months_are_refused_until_the_flag_exists(tmp_path):
    flag = tmp_path / FLAG
    faa.check_months(["2026-04", "2026-05"], flag)
    faa.check_months(["2026-03"], flag)  # before the study months: allowed as context
    for months in (["2026-06"], ["2026-05", "2026-09"], ["2026-10"], ["2027-01"], {"2026-07"}):
        with pytest.raises(faa.TestMonthsLocked):
            faa.check_months(months, flag)
    with pytest.raises(faa.TestMonthsLocked):
        faa.load_months(tmp_path, ["2026-06"], flag)
    flag.write_text("registered\n")
    faa.check_months(["2026-06", "2026-09"], flag)


@pytest.mark.parametrize(
    "month",
    ["2026-006", " 2026-06", "2026-06 ", "02026-06", "2026-6", "2026-+6", "2026/06", "202606",
     "2026-13", "2026-00", "2026-06-01", "", 202606, None, ("2026", "06")],
)  # fmt: skip
def test_a_month_not_written_yyyy_mm_is_refused(tmp_path, month):
    # "2026-006" sorts before "2026-05" as text and would still be read as June
    for call in (faa.is_locked, faa.month_days, lambda m: faa.check_months([m], tmp_path / FLAG)):
        with pytest.raises(ValueError, match="YYYY-MM"):
            call(month)
    with pytest.raises(ValueError):
        faa.load_months(tmp_path, [month], tmp_path / FLAG)


def test_months_given_as_one_string_are_refused(tmp_path):
    for call in (faa.check_months, lambda m: faa.load_months(tmp_path, m)):
        with pytest.raises(ValueError, match="list"):
            call("2026-06")


def test_only_the_named_flag_file_opens_the_test_months(tmp_path, monkeypatch):
    other = tmp_path / "some-other-file"
    other.write_text("exists\n")
    folder = tmp_path / "folder" / FLAG
    folder.mkdir(parents=True)
    for not_the_flag in (other, folder, tmp_path, tmp_path / "absent" / FLAG, Path("/dev/null")):
        assert not faa.amendment_registered(not_the_flag)
        with pytest.raises(faa.TestMonthsLocked):
            faa.check_months(["2026-06"], not_the_flag)
    # with no flag given, the one flag of the study decides
    monkeypatch.setattr(faa, "AMENDMENT_FLAG", tmp_path / FLAG)
    assert not faa.amendment_registered()
    with pytest.raises(faa.TestMonthsLocked):
        faa.check_months(["2026-06"])
    (tmp_path / FLAG).write_text("registered\n")
    assert faa.amendment_registered() and faa.amendment_registered(tmp_path / FLAG)
    faa.check_months(["2026-06"])


def test_the_test_months_are_the_locked_ones():
    assert faa.AMENDMENT_FLAG == faa.OUT / "E6_AMENDMENT_REGISTERED"
    assert max(faa.DEV_MONTHS) == "2026-05" and min(faa.TEST_MONTHS) == "2026-06"
    assert all(faa.is_locked(m) for m in faa.TEST_MONTHS)
    assert not any(faa.is_locked(m) for m in faa.DEV_MONTHS)


def test_every_reader_refuses_a_test_month_without_the_flag(test_month_on_disk, opened):
    root, flag = test_month_on_disk, test_month_on_disk / FLAG
    june = dt.date(2026, 6, 1)
    with pytest.raises(faa.TestMonthsLocked):
        faa.load_day(root, june, flag)
    with pytest.raises(faa.TestMonthsLocked):
        faa.coverage_gaps(root, [dt.date(2026, 5, 31), june], flag)
    for months in (["2026-06"], ["2026-04", "2026-06"], ["2026-07"]):  # July's lead-in is June
        for complete in (True, False):
            with pytest.raises(faa.TestMonthsLocked):
                faa.load_months(root, months, flag, complete=complete)
    # what may run on every month counts the files and opens none of them
    assert faa.raw_counts(root)["20260601"] == 2
    rows = {row["day"]: row for row in faa.completeness(root, flag)}
    assert rows["20260601"] == {"day": "20260601", "advisories": 2, "listed": "", "missing": ""}
    assert rows["20260415"] == {"day": "20260415", "advisories": 1, "listed": 1, "missing": 0}
    # the development month loads, and nothing of June was opened on the way
    advisories, _ = faa.load_months(root, ["2026-04"], flag)
    assert [a.id for a in advisories] == ["20260331-016", "20260415-016"]
    assert opened and not any("202606" in path for path in opened)


def test_the_flag_opens_the_test_months(test_month_on_disk, opened):
    root, flag = test_month_on_disk, test_month_on_disk / FLAG
    flag.write_text("registered\n")
    assert [a.id for a in faa.load_day(root, dt.date(2026, 6, 1), flag)] == [
        "20260601-001",
        "20260601-002",
    ]
    rows = {row["day"]: row for row in faa.completeness(root, flag)}
    assert rows["20260601"] == {"day": "20260601", "advisories": 2, "listed": 3, "missing": 1}
    assert faa.coverage_gaps(root, [dt.date(2026, 6, 1)], flag) == [
        "2026-06-01: 1 listed advisories not saved"
    ]
    assert any("20260601" in path for path in opened)


def test_the_command_refuses_a_test_month_and_opens_none_by_default(
    test_month_on_disk, opened, monkeypatch, capsys
):
    root, out = test_month_on_disk, test_month_on_disk / "out"
    monkeypatch.setattr(faa, "AMENDMENT_FLAG", root / FLAG)
    common = ["--root", str(root), "--out", str(out)]
    for months in (["2026-06"], ["2026-04", "2026-06"]):
        with pytest.raises(faa.TestMonthsLocked):
            faa.main(["--months", *months, "--name", "test", *common])
    with pytest.raises(ValueError, match="YYYY-MM"):
        faa.main(["--months", "2026-006", "--name", "test", *common])
    with pytest.raises(SystemExit):  # the flag cannot be pointed elsewhere from the command line
        faa.main(["--months", "2026-06", "--flag", str(root / "list.html"), *common])
    assert not out.exists()
    assert not any("202606" in path for path in opened)
    # the default run reads the development month, and counts June without opening it
    assert faa.main(["--months", "2026-04", *common]) == 0
    assert "1 advisories parsed" in capsys.readouterr().out
    with (out / "raw_counts_per_day.csv").open(newline="") as f:
        assert "20260601,2,,\n" in f.read()
    assert (out / "statements_dev.csv").exists()
    assert not any("202606" in path for path in opened)


def test_tables_named_dev_hold_development_months_only():
    assert faa.table_name(["2026-04", "2026-05"], None) == "dev"
    assert faa.table_name(["2026-04"], "april") == "april"
    assert faa.table_name(["2026-06"], "test") == "test"
    for name in (None, "dev"):
        with pytest.raises(ValueError):
            faa.table_name(["2026-05", "2026-06"], name)


def test_load_months_reads_only_what_was_asked(tmp_path):
    write_day(tmp_path, "20260331", {"adv_016.html": page_2026(ORD_016, "20260331")})
    april = {"adv_016.html": page_2026(ORD_016, "20260415"), "adv_017.html": "an error page"}
    write_day(tmp_path, "20260415", april)
    write_day(tmp_path, "20260601", {"adv_001.html": "not parsed", "adv_002.html": "not parsed"})
    with pytest.warns(UserWarning, match=r"adv_017\.html: not parsed"):
        advisories, data_end = faa.load_months(tmp_path, ["2026-04"], complete=False)
    assert [a.id for a in advisories] == ["20260331-016", "20260415-016"]  # lead-in day, then April
    assert data_end == dt.datetime(2026, 5, 1)
    statements = faa.build_statements(advisories, ["2026-04"])
    assert [s.sid for s in statements] == ["gs-20260415-016"]  # none from the lead-in day
    # counting files reads nothing, so June may be counted
    assert faa.raw_counts(tmp_path) == {"20260331": 1, "20260415": 2, "20260601": 2}


def test_a_month_that_is_not_all_on_disk_is_not_loaded(tmp_path):
    # "not issued" and "not extended" are read from the later advisories: a day that was not
    # saved, or not saved in full, must stop the run and not pass for a quiet day
    write_month(tmp_path, "2026-04")
    stop = {"adv_016.html": page_2026(ORD_016, "20260415")}
    write_day(tmp_path, "20260415", stop)
    assert faa.coverage_gaps(tmp_path, faa.month_days("2026-04")) == []
    advisories, _ = faa.load_months(tmp_path, ["2026-04"])
    assert [a.id for a in advisories] == ["20260415-016"]  # no lead-in day on disk: allowed

    def gaps():
        with pytest.raises(faa.IncompleteCoverage) as error:
            faa.load_months(tmp_path, ["2026-04"])
        return str(error.value)

    # a listed advisory that was not saved
    write_day(tmp_path, "20260415", stop | {"list.html": listing("20260415", (16, 21))})
    assert "2026-04-15: 1 listed advisories not saved" in gaps()
    # a saved page that is not an advisory
    write_day(tmp_path, "20260415", stop | {"adv_021.html": "an error page"})
    with pytest.warns(UserWarning, match="not parsed"):
        assert "2026-04-15: 1 saved pages not parsed" in gaps()
    (tmp_path / "20260415" / "adv_021.html").unlink()
    write_day(tmp_path, "20260415", stop)
    # a day without its list page, and a day without a folder
    (tmp_path / "20260420" / "list.html").unlink()
    assert "2026-04-20: no list page" in gaps()
    (tmp_path / "20260421" / "list.html").unlink()
    (tmp_path / "20260421").rmdir()
    message = gaps()
    assert "2 gaps in 2026-04" in message and "2026-04-21: no list page" in message
    with pytest.raises(faa.IncompleteCoverage):
        faa.main(["--root", str(tmp_path), "--out", str(tmp_path / "out"), "--months", "2026-04"])
    assert not (tmp_path / "out" / "statements_dev.csv").exists()
    # asked for by name, the partial month can still be read (the tests of the linker do)
    assert len(faa.load_months(tmp_path, ["2026-04"], complete=False)[0]) == 1


def test_completeness_compares_saved_files_with_the_list_page(tmp_path):
    saved = {"list.html": listing("20260501", (1, 2, 3)), "adv_001.html": "x", "adv_003.html": "x"}
    write_day(tmp_path, "20260501", saved)
    write_day(tmp_path, "20260502", {"adv_001.html": "x"}, listed=False)  # no list page yet
    assert faa.completeness(tmp_path) == [
        {"day": "20260501", "advisories": 2, "listed": 3, "missing": 1},
        {"day": "20260502", "advisories": 1, "listed": "", "missing": ""},
    ]


def test_listing_day_and_number_replace_the_header(tmp_path):
    # sent at 0000Z on the 16th and listed there as number 001, but headed with the 15th
    midnight = ground_stop(
        "001", "LGA", "ZNY", "2355", "15/2348Z - 16/0100Z", "MEDIUM", "23:59", "160000-160200"
    )
    midnight = midnight.replace("24/07/15 23:59", "24/07/16 00:00")
    assert faa.parse_advisory(midnight).id == "20240715-001"
    write_day(tmp_path, "20240716", {"adv_001.html": midnight})
    assert faa.coverage_gaps(tmp_path, [dt.date(2024, 7, 16)]) == []
    (listed,) = faa.load_day(tmp_path, dt.date(2024, 7, 16))
    assert (listed.id, listed.day, listed.number) == ("20240716-001", dt.date(2024, 7, 16), 1)
    assert listed.sent == dt.datetime(2024, 7, 16, 0, 0)
    assert listed.period[1] == dt.datetime(2024, 7, 16, 1, 0)


def test_statement_row_is_flat():
    (statement,) = faa.gs_statements(parse_all(ORD_016, ORD_021))
    row = faa.statement_row(statement)
    assert tuple(row) == faa.STATEMENT_COLUMNS
    assert row["issued"] == "2024-07-15T02:52Z" and row["window_end"] == "2024-07-15T04:00Z"
    assert (row["term"], row["term_norm"], row["n_sources"]) == ("MEDIUM", "MEDIUM", 1)
