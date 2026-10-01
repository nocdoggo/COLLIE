"""Tests for the E6 linker, the hand-check sample and its scorer (``faa_links.py``).

The advisories are the trimmed pilot fixtures of ``test_faa.py`` (15 July 2024).

Run::

    PYTHONPATH=. python -m pytest analysis/coling/test_faa_links.py -q
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import re

import pytest

from analysis.coling import faa
from analysis.coling import faa_links as links
from analysis.coling import test_faa as fx

DATA_END = dt.datetime(2024, 8, 1)
opened = fx.opened  # the fixture of test_faa.py: every path opened while a test runs


def linked(*texts: str, data_end: dt.datetime = DATA_END, **options):
    advisories = fx.parse_all(*texts)
    statements = (
        faa.gs_statements(advisories)
        + faa.route_statements(advisories)
        + faa.plan_statements(advisories)
    )
    result = links.link_all(statements, advisories, data_end, **options)
    return {s.sid: (s, link) for s, link in zip(statements, result, strict=True)}


# --------------------------------------------------------------------------------------
# Probability of extension
# --------------------------------------------------------------------------------------


def test_ground_stop_extended_four_times_then_cancelled():
    result = linked(*fx.MCO_CHAIN)
    codes = [(link.outcome, link.code, link.evidence) for _, link in result.values()]
    assert codes == [
        (1, "extended", ("20240715-118",)),
        (1, "extended", ("20240715-139",)),
        (1, "extended", ("20240715-149",)),
        (1, "extended", ("20240715-157",)),
        (0, "cancelled", ("20240715-165",)),
    ]
    first = result["gs-20240715-106"][1]
    assert first.detail == "end 15/2130Z -> 15/2215Z (+45 min)"
    # the checker sees every later advisory for the airport up to two hours past the end
    assert first.context == ("20240715-118", "20240715-139", "20240715-149", "20240715-157")


def test_a_reissue_with_the_same_end_is_not_an_extension():
    result = linked(fx.MCO_106, fx.MCO_118, fx.MCO_118_REISSUED)
    assert result["gs-20240715-106"][1].code == "extended"
    statement, link = result["gs-20240715-118"]
    assert statement.sources == ("20240715-118", "20240715-119")
    assert (link.outcome, link.code, link.flags) == (0, "lapsed", ("term_changed",))


def test_a_stop_shortened_and_then_restated_to_the_same_end_is_not_extended():
    # ORD stop to 0400Z, cut back to 0330Z, then stated to 0400Z again: no end later than 0400Z
    shorter = fx.ground_stop(
        "017", "ORD", "ZAU", "0300", "15/0237Z - 15/0330Z", "MEDIUM", "03:02", "150302-150430"
    )
    again = fx.ground_stop(
        "018", "ORD", "ZAU", "0320", "15/0237Z - 15/0400Z", "MEDIUM", "03:22", "150322-150500"
    )
    result = linked(fx.ORD_016, shorter, again)
    first = result["gs-20240715-016"][1]
    assert (first.outcome, first.code, first.flags) == (0, "lapsed", ("shortened",))
    assert result["gs-20240715-017"][1].code == "extended"  # 0330Z became 0400Z
    # one minute more is an extension
    longer = again.replace("15/0237Z - 15/0400Z", "15/0237Z - 15/0401Z")
    first = linked(fx.ORD_016, shorter, longer)["gs-20240715-016"][1]
    assert (first.outcome, first.detail) == (1, "end 15/0400Z -> 15/0401Z (+1 min)")


def test_a_new_stop_after_the_end_is_not_an_extension():
    later = fx.ground_stop(
        "120", "ORD", "ZAU", "2010", "15/2000Z - 15/2100Z", "LOW", "20:12", "152012-152200"
    )
    result = linked(fx.ORD_016, later)
    assert [link.code for _, link in result.values()] == ["lapsed", "lapsed"]
    assert result["gs-20240715-016"][1].context == ()  # nothing within two hours of the end


def test_a_stop_that_restarts_within_thirty_minutes_is_flagged_not_extended():
    restart = fx.ground_stop(
        "030", "ORD", "ZAU", "0417", "15/0407Z - 15/0500Z", "MEDIUM", "04:20", "150420-150600"
    )
    result = linked(fx.ORD_016, restart)
    first = result["gs-20240715-016"][1]
    assert (first.outcome, first.code, first.flags) == (0, "lapsed", ("new_stop_30",))
    assert result["gs-20240715-030"][1].flags == ()
    # after a cancellation too: the stop cancelled at 0357Z, a new one from 0407Z
    first = linked(fx.ORD_016, fx.ORD_021, restart)["gs-20240715-016"][1]
    assert (first.outcome, first.code, first.flags) == (0, "cancelled", ("new_stop_30",))
    # with a grace of 15 minutes the same restart is an extension, and nothing is flagged
    first = linked(fx.ORD_016, restart, grace=15)["gs-20240715-016"][1]
    assert first.code == "lapsed"  # the statements passed in were built with grace 0
    advisories = fx.parse_all(fx.ORD_016, restart)
    joined = faa.gs_statements(advisories, grace=15)
    (first, _) = links.link_all(joined, advisories, DATA_END, grace=15)
    assert (first.outcome, first.code, first.flags) == (1, "extended", ())


def test_a_route_carried_on_under_a_new_tmi_id_is_extended_and_flagged():
    # edited copy of 028: the same name under a new FCA number and TMI ID, from the old end on
    renamed = (
        fx.ROUTE_028.replace("ADVZY 028", "ADVZY 060")
        .replace("FCA001:", "FCA007:")
        .replace("FROM 151000 TO 151600", "FROM 151600 TO 152200")
        .replace("RRDCC028", "RRDCC060")
        .replace("24/07/15 10:02", "24/07/15 15:30")
    )
    result = linked(fx.ROUTE_028, renamed)
    first = result["route-20240715-028"][1]
    assert (first.outcome, first.code, first.evidence) == (1, "extended", ("20240715-060",))
    assert first.flags == ("continued_new_id",)
    assert first.detail == (
        "end 15/1600Z -> 15/2200Z (+360 min), carried on as FCA007:LAKE_ERIE_WEST_PARTIAL "
        "under TMI ID RRDCC060"
    )
    assert result["route-20240715-060"][1].flags == ()
    # the strict reading (same TMI ID only) keeps the flag and gives 0
    strict = linked(fx.ROUTE_028, renamed, count_renamed=False)["route-20240715-028"][1]
    assert (strict.outcome, strict.code, strict.flags) == (0, "lapsed", ("continued_new_id",))
    # the same name the next morning, starting after the old end, is another route
    next_day = renamed.replace("FROM 151600 TO 152200", "FROM 161000 TO 161600")
    later = linked(fx.ROUTE_028, next_day)["route-20240715-028"][1]
    assert (later.outcome, later.code, later.flags) == (0, "lapsed", ())
    # sent after the old end: the route had run out, so it is another route
    late = renamed.replace("24/07/15 15:30", "24/07/15 16:10")
    assert linked(fx.ROUTE_028, late)["route-20240715-028"][1].code == "lapsed"
    # another name under another TMI ID is another route
    other = renamed.replace("LAKE_ERIE_WEST_PARTIAL", "LAKE_ERIE_EAST")
    assert linked(fx.ROUTE_028, other)["route-20240715-028"][1].code == "lapsed"


def test_a_route_cancelled_before_it_is_issued_again_is_not_carried_on():
    # 031 (1130-1530Z) is cancelled at 1239Z; the same name comes back at 1300Z under a new ID
    again = (
        fx.ROUTE_031.replace("ADVZY 031", "ADVZY 055")
        .replace("ETD 151130 TO 151530", "ETD 151300 TO 151900")
        .replace("RRDCC500", "RRDCC507")
        .replace("24/07/15 11:04", "24/07/15 13:00")
    )
    result = linked(fx.ROUTE_031, fx.ROUTE_040, again)
    first = result["route-20240715-031"][1]
    assert (first.outcome, first.code, first.flags) == (0, "cancelled", ())
    # issued again before the cancellation: a handover, so the route is carried on
    handover = again.replace("24/07/15 13:00", "24/07/15 12:30")
    first = linked(fx.ROUTE_031, fx.ROUTE_040, handover)["route-20240715-031"][1]
    assert (first.outcome, first.code, first.flags) == (1, "extended", ("continued_new_id",))


def test_shortened_and_delay_programme_flags():
    shorter = fx.ground_stop(
        "017", "ORD", "ZAU", "0300", "15/0237Z - 15/0330Z", "MEDIUM", "03:02", "150302-150430"
    )
    programme = fx.SFO_042.replace("SFO", "ORD").replace("12:51", "03:20")
    _, link = linked(fx.ORD_016, shorter, programme)["gs-20240715-016"]
    assert (link.outcome, link.code) == (0, "lapsed")
    assert set(link.flags) == {"shortened", "gdp_followed"}


def test_outcome_at_the_edge_of_the_loaded_months_is_excluded():
    edge = dt.datetime(2024, 7, 16)
    result = linked(*fx.MCO_CHAIN[:5], data_end=edge)
    # extensions seen before the edge stand; the last stated end (16/0030Z) is past it
    assert [link.code for _, link in result.values()] == ["extended"] * 4 + ["unresolved_boundary"]
    assert result["gs-20240715-157"][1].outcome is None


def test_lapsed_is_not_concluded_when_a_late_extension_could_not_have_been_loaded():
    # ORD stop 0237-0400Z, nothing after it. An extension may be sent after the stated end, so
    # "lapsed" needs the advisories of the two hours after 0400Z.
    (covered,) = linked(fx.ORD_016, data_end=dt.datetime(2024, 7, 15, 6, 1)).values()
    assert (covered[1].outcome, covered[1].code) == (0, "lapsed")
    for edge in (dt.datetime(2024, 7, 15, 6, 0), dt.datetime(2024, 7, 15, 4, 30)):
        (near,) = linked(fx.ORD_016, data_end=edge).values()
        assert (near[1].outcome, near[1].code) == (None, "unresolved_boundary")
        assert "too near the edge" in near[1].detail
    # a cancellation that was loaded is evidence: the outcome stands however near the edge
    result = linked(fx.ORD_016, fx.ORD_021, data_end=dt.datetime(2024, 7, 15, 4, 30))
    assert result["gs-20240715-016"][1].code == "cancelled"
    # and so is an extension that was loaded
    result = linked(*fx.MCO_CHAIN[:2], data_end=dt.datetime(2024, 7, 15, 21, 40))
    assert result["gs-20240715-106"][1].code == "extended"


def test_route_extended_and_route_cancelled():
    result = linked(fx.ROUTE_028, fx.ROUTE_047, fx.ROUTE_031, fx.ROUTE_040)
    assert {sid: link.code for sid, (_, link) in result.items()} == {
        "route-20240715-028": "extended",
        "route-20240715-047": "lapsed",
        "route-20240715-031": "cancelled",
    }
    assert result["route-20240715-028"][1].evidence == ("20240715-047",)
    assert result["route-20240715-031"][1].evidence == ("20240715-040",)


# --------------------------------------------------------------------------------------
# Planned ground stops and delay programmes
# --------------------------------------------------------------------------------------


def test_planned_lines_issued_and_not_issued():
    result = linked(
        fx.PLAN_013, fx.PLAN_026, fx.ORD_016, fx.ORD_021, fx.SFO_041, fx.SFO_042, *fx.MCO_CHAIN
    )
    codes = {sid: (link.outcome, link.code, link.evidence) for sid, (_, link) in result.items()}
    # ORD: ground stop sent 0252Z inside "UNTIL 0400"; MDW, named on the same line: nothing
    assert codes["plan-20240715-013-ORD-gs-UNTIL0400"] == (1, "issued", ("20240715-016",))
    assert codes["plan-20240715-013-MDW-gs-UNTIL0400"] == (0, "not_issued", ())
    # SFO: the proposed programme is not an issuance, the actual one (period from 1600Z) is
    assert codes["plan-20240715-013-SFO-gs+gdp-AFTER1530"] == (1, "issued", ("20240715-042",))
    # MCO: ground stop from 2003Z inside "AFTER 1900"; TPA and BOS: nothing
    assert codes["plan-20240715-013-MCO-gs-AFTER1900"] == (1, "issued", ("20240715-106",))
    assert codes["plan-20240715-013-TPA-gs-AFTER1900"] == (0, "not_issued", ())
    assert codes["plan-20240715-013-BOS-gs-AFTER1900"] == (0, "not_issued", ())
    sfo = result["plan-20240715-013-SFO-gs+gdp-AFTER1530"][1]
    assert sfo.context == ("20240715-041", "20240715-042")


def test_proposed_only_and_outside_the_window_are_not_issued():
    result = linked(fx.PLAN_013, fx.SFO_041)
    _, link = result["plan-20240715-013-SFO-gs+gdp-AFTER1530"]
    assert (link.outcome, link.code, link.flags) == (0, "not_issued", ("proposed_only",))
    # a Boston stop that ends before the window opens (AFTER 1900) does not count
    early = fx.ground_stop(
        "060", "BOS", "ZBW", "1500", "15/1450Z - 15/1600Z", "LOW", "15:02", "151502-151700"
    )
    _, link = linked(fx.PLAN_013, early)["plan-20240715-013-BOS-gs-AFTER1900"]
    assert (link.outcome, link.code, link.flags) == (0, "not_issued", ("outside_window",))


def test_a_stop_sent_after_the_window_closed_does_not_count():
    # Orlando, 5 April 2026: "UNTIL 2300 MCO GROUND STOP POSSIBLE"; the stop was sent at 2314Z
    # with a stated start of 2255Z. Sent after the window's end, it is not an issuance.
    plan = fx.operations_plan(
        "077",
        "15/2000",
        "UNTIL 2300\t-MCO GROUND STOP POSSIBLE\n",
        "151931-152159",
        "24/07/15 19:31",
    )
    late = fx.ground_stop(
        "095", "MCO", "ZJX", "2312", "15/2255Z - 16/0015Z", "MEDIUM", "23:14", "152314-160115"
    )
    key = "plan-20240715-077-MCO-gs-UNTIL2300"
    _, link = linked(plan, late)[key]
    assert (link.outcome, link.code, link.evidence) == (0, "not_issued", ())
    in_time = late.replace("23:14", "22:59")
    _, link = linked(plan, in_time)[key]
    assert (link.outcome, link.code, link.evidence) == (1, "issued", ("20240715-095",))


def test_a_stop_cancelled_before_the_window_opens_is_not_in_the_window():
    # Boston stop 1830-1930Z would reach into "AFTER 1900", but it is cancelled at 1845Z
    stop = fx.ground_stop(
        "070", "BOS", "ZBW", "1832", "15/1830Z - 15/1930Z", "LOW", "18:34", "151834-152030"
    )
    cancel = fx.ORD_021.replace("ORD/ZAU", "BOS/ZBW").replace(
        "CTL ELEMENT: ORD", "CTL ELEMENT: BOS"
    )
    cancel = cancel.replace("ADVZY 021", "ADVZY 071").replace("03:57", "18:45")
    key = "plan-20240715-013-BOS-gs-AFTER1900"
    assert linked(fx.PLAN_013, stop)[key][1].code == "issued"
    _, link = linked(fx.PLAN_013, stop, cancel)[key]
    assert (link.outcome, link.code, link.flags) == (0, "not_issued", ("outside_window",))


def test_a_programme_cancelled_before_it_began_was_never_in_effect():
    # SFO: "AFTER 1530". The programme for 1600-1859Z is sent at 1251Z and cancelled at 1400Z,
    # before its stated start: its period, cut at the cancellation, is empty.
    key = "plan-20240715-013-SFO-gs+gdp-AFTER1530"
    assert linked(fx.PLAN_013, fx.SFO_042)[key][1].code == "issued"
    # ... whether the cancellation comes before the window opens (1400Z) or inside it (1545Z)
    for at in ("14:00", "15:45"):
        cancelled = fx.SFO_082.replace("18:37", at)
        _, link = linked(fx.PLAN_013, fx.SFO_042, cancelled)[key]
        assert (link.outcome, link.code, link.flags) == (0, "not_issued", ("outside_window",))
    # cancelled at 1837Z, after it began: in effect from 1600Z to 1837Z, inside the window
    _, link = linked(fx.PLAN_013, fx.SFO_042, fx.SFO_082)[key]
    assert (link.code, link.detail) == (
        "issued",
        "CDM GROUND DELAY PROGRAM sent 15/1251Z, period 15/1600Z - 15/1837Z",
    )


def test_manual_stop_counts_unless_switched_off():
    stop = fx.BOS_151  # hand-written stop for Boston, 2230-2330Z, inside "AFTER 1900"
    _, link = linked(fx.PLAN_013, stop)["plan-20240715-013-BOS-gs-AFTER1900"]
    assert (link.outcome, link.code, link.flags) == (1, "issued", ("manual_stop",))
    _, link = linked(fx.PLAN_013, stop, count_manual=False)["plan-20240715-013-BOS-gs-AFTER1900"]
    assert (link.outcome, link.code) == (0, "not_issued")


def test_hand_written_advisory_for_two_airports_is_seen_for_each():
    both = fx.BOS_151.replace("DESTINATION AIRPORT: BOS", "DESTINATION AIRPORT: BOS AND TPA")
    index = links.index_by_element(fx.parse_all(both, fx.ORD_016))
    assert sorted(index) == ["BOS", "ORD", "TPA"]
    assert [a.id for a in index["TPA"]] == ["20240715-151"]
    result = linked(fx.PLAN_013, both)
    assert result["plan-20240715-013-TPA-gs-AFTER1900"][1].code == "issued"
    assert result["plan-20240715-013-MCO-gs-AFTER1900"][1].code == "not_issued"


def test_manual_stop_running_at_issuance_excludes_the_line_when_manual_stops_count():
    # hand-written Boston stop 2230-2330Z, sent 2239Z; the plan of 2245Z says "UNTIL 0100"
    plan = fx.operations_plan(
        "155",
        "15/2300",
        "UNTIL 0100\t-BOS GROUND STOP POSSIBLE\n",
        "152245-160059",
        "24/07/15 22:45",
    )
    key = "plan-20240715-155-BOS-gs-UNTIL0100"
    _, link = linked(fx.BOS_151, plan)[key]
    assert (link.outcome, link.code, link.evidence) == (None, "already_active", ("20240715-151",))
    _, link = linked(fx.BOS_151, plan, count_manual=False)[key]
    assert (link.outcome, link.code) == (0, "not_issued")


def test_initiative_already_running_into_the_window_is_excluded():
    running = fx.ground_stop(
        "005", "ORD", "ZAU", "0050", "15/0040Z - 15/0200Z", "MEDIUM", "00:52", "150052-150300"
    )
    result = linked(running, fx.PLAN_013)
    _, link = result["plan-20240715-013-ORD-gs-UNTIL0400"]
    assert (link.outcome, link.code, link.evidence) == (None, "already_active", ("20240715-005",))
    # a stop running at issuance that ends before the window opens does not exclude the line
    evening = fx.ground_stop(
        "006", "BOS", "ZBW", "0050", "15/0040Z - 15/0200Z", "MEDIUM", "00:52", "150052-150300"
    )
    _, link = linked(evening, fx.PLAN_013)["plan-20240715-013-BOS-gs-AFTER1900"]
    assert (link.outcome, link.code) == (0, "not_issued")


def test_plan_window_past_the_loaded_months_is_excluded_unless_already_issued():
    edge = dt.datetime(2024, 7, 16)  # "AFTER 1900" runs to 16/0800Z
    result = linked(fx.PLAN_013, *fx.MCO_CHAIN, data_end=edge)
    assert result["plan-20240715-013-MCO-gs-AFTER1900"][1].code == "issued"
    assert result["plan-20240715-013-TPA-gs-AFTER1900"][1].code == "unresolved_boundary"
    assert result["plan-20240715-013-ORD-gs-UNTIL0400"][1].code == "not_issued"


def test_link_row_and_count_table():
    result = linked(fx.PLAN_013, fx.ORD_016, fx.ORD_021, *fx.MCO_CHAIN)
    statements = [s for s, _ in result.values()]
    all_links = [link for _, link in result.values()]
    row = links.link_row(*result["gs-20240715-106"])
    assert tuple(row) == links.LINK_COLUMNS
    assert (row["outcome"], row["code"], row["evidence"], row["day"]) == (
        1,
        "extended",
        "20240715-118",
        "2024-07-15",
    )
    table = {r["term"]: r for r in links.count_table(statements, all_links, with_outcomes=True)}
    assert table["gs:MEDIUM"] == {
        "term": "gs:MEDIUM",
        "statements": 6,
        "excluded": 0,
        "scored": 6,
        "yes": 4,
        "days": 1,
    }
    assert table["plan:POSSIBLE"]["statements"] == 6 and table["plan:PROBABLE"]["statements"] == 3
    hidden = links.count_table(statements, all_links, with_outcomes=False)
    assert all("yes" not in r for r in hidden)


def test_dev_report_counts_statements_outcomes_and_sensitivities():
    # a Boston stop extended by ten minutes only, and a Toronto programme (out of scope)
    short = fx.ground_stop(
        "090", "BOS", "ZBW", "2000", "15/1950Z - 15/2100Z", "LOW", "20:02", "152002-152200"
    )
    longer = fx.ground_stop(
        "095", "BOS", "ZBW", "2050", "15/1950Z - 15/2110Z", "LOW", "20:52", "152052-152210"
    )
    toronto = fx.SFO_042.replace("SFO", "CYYZ")
    odd = fx.SFO_042.replace("CDM GROUND DELAY PROGRAM", "SFO CDM GROUND DELAY PROGRAM CORRECTION")
    odd = odd.replace("ADVZY 042", "ADVZY 043")
    # a route carried on under a new TMI ID (edited copy of 028)
    renamed = fx.ROUTE_028.replace("ADVZY 028", "ADVZY 060").replace("FCA001:", "FCA007:")
    renamed = renamed.replace("TO 151600", "TO 152200").replace("RRDCC028", "RRDCC060")
    renamed = renamed.replace("24/07/15 10:02", "24/07/15 15:30")
    advisories = fx.parse_all(
        fx.PLAN_013, fx.ORD_016, fx.ORD_021, *fx.MCO_CHAIN, short, longer, toronto, odd,
        fx.ROUTE_028, renamed,
    )  # fmt: skip
    report = links.dev_report(advisories, ["2024-07"], DATA_END)
    assert (report["advisories"], report["days_with_advisories"]) == (15, 1)
    assert report["statements"] == 1 + 5 + 2 + 9 + 2
    assert report["codes"]["route:extended"] == 1 and report["flags"]["continued_new_id"] == 1
    assert report["codes"]["gs:extended"] == 5 and report["codes"]["plan:issued"] == 3
    assert report["plan_line_terms_as_written"] == {"POSSIBLE": 4, "PROBABLE": 1}  # lines
    assert report["probability_of_extension_as_written"] == {
        "gs:LOW": 2,
        "gs:MEDIUM": 6,
        "reroute:LOW": 2,
    }
    assert report["advisories_for_canadian_airports_by_kind"] == {"gdp": 1}
    assert report["titles_naming_a_programme_but_not_classified"] == {
        "SFO CDM GROUND DELAY PROGRAM CORRECTION": 1
    }
    changed = report["outcomes_changed_by"]
    assert changed["an extension of under 15 minutes not counted"] == 1  # Boston, +10 minutes
    assert changed["hand-written stops not counted as issued"] == 0
    assert changed["a route carried on under a new TMI ID not counted as an extension"] == 1
    assert report["lead_minutes_quartiles"]["gs"][1] > 0
    assert report["days_by_family"] == {"gs": 1, "route": 1, "plan": 1}


# --------------------------------------------------------------------------------------
# The sample and the sheets
# --------------------------------------------------------------------------------------


def synthetic(n_by_stratum: dict[str, int], n_excluded: int = 0):
    """Statements and links with made-up ids: enough structure for the sampler."""
    statements, out = [], []
    moment = dt.datetime(2026, 4, 1, 12, 0)
    for stratum, n in n_by_stratum.items():
        family, term = stratum.split(":")
        for i in range(n):
            sid = f"{family}-{term}-{i:04d}"
            statements.append(
                faa.Statement(
                    sid,
                    family,
                    term,
                    "AAA",
                    family,
                    moment,
                    moment,
                    moment,
                    0,
                    (sid,),
                    (term,),
                    "",
                    "AAA",
                )
            )
            out.append(links.Link(sid, i % 2, "extended" if i % 2 else "lapsed", (), (), "", ()))
    for i in range(n_excluded):
        sid = f"plan-EXCLUDED-{i:04d}"
        statements.append(
            faa.Statement(
                sid,
                "plan",
                "POSSIBLE",
                "AAA",
                "gs",
                moment,
                moment,
                moment,
                0,
                (sid,),
                ("POSSIBLE",),
                "",
                "AAA",
            )
        )
        out.append(links.Link(sid, None, "already_active", (), (), "", ()))
    return statements, out


def test_sample_takes_thirty_per_term_or_all_and_is_reproducible():
    statements, all_links = synthetic(
        {"gs:MEDIUM": 400, "gs:LOW": 45, "gs:HIGH": 12, "plan:POSSIBLE": 90}, 25
    )
    rows, frame = links.draw_sample(statements, all_links)
    # 30 per term, or all 12 when the term has no more; then topped up to 150 links
    assert (
        sum(sampled for stratum, (_, sampled, _) in frame.items() if stratum != "excluded") == 150
    )
    assert all(sampled >= required for _, sampled, required in frame.values())
    assert frame["gs:HIGH"] == (12, 12, 12) and frame["excluded"] == (25, 10, 0)
    assert len(rows) == 160 and len({r["sid"] for r in rows}) == 160
    assert sum(r["checker"] == "both" for r in rows) == links.N_DOUBLE_CHECKED
    assert all(r["stratum"] != "excluded" for r in rows if r["checker"] == "both")
    single = [r["checker"] for r in rows if r["checker"] != "both"]
    assert abs(single.count("A1") - single.count("A2")) <= 1
    # the same input in another order gives the same sheet
    again, _ = links.draw_sample(statements[::-1], all_links[::-1])
    assert again == rows
    # a repeat of the gate (draw 2) and another seed give other sheets
    second, _ = links.draw_sample(statements, all_links, draw=2)
    assert [r["sid"] for r in second] != [r["sid"] for r in rows]
    other, _ = links.draw_sample(statements, all_links, seed=1)
    assert [r["sid"] for r in other] != [r["sid"] for r in rows]


def test_dropping_a_family_leaves_the_other_draws_unchanged():
    statements, all_links = synthetic(
        {
            "gs:MEDIUM": 200,
            "gs:LOW": 100,
            "route:LOW": 100,
            "plan:POSSIBLE": 100,
            "plan:PROBABLE": 100,
        }
    )
    rows, _ = links.draw_sample(statements, all_links)
    kept = [s for s in statements if s.family != "route"]
    kept_links = [link for link in all_links if not link.sid.startswith("route")]
    fewer, _ = links.draw_sample(kept, kept_links, minimum=0)
    for stratum in ("gs:LOW", "plan:PROBABLE"):
        assert {r["sid"] for r in rows if r["stratum"] == stratum} == {
            r["sid"] for r in fewer if r["stratum"] == stratum
        }


def test_sheets_show_source_linked_advisories_and_an_empty_verdict(tmp_path):
    advisories = fx.parse_all(fx.PLAN_013, fx.PLAN_026, fx.ORD_016, fx.ORD_021, *fx.MCO_CHAIN)
    statements = faa.gs_statements(advisories) + faa.plan_statements(advisories)
    all_links = links.link_all(statements, advisories, DATA_END)
    rows, _ = links.draw_sample(statements, all_links, n_double=4)
    paths = links.write_sheets(tmp_path, rows, statements, all_links, advisories)
    assert [p.name for p in paths] == [
        "linker_gate_sheet_A1.csv", "linker_gate_items_A1.md",
        "linker_gate_sheet_A2.csv", "linker_gate_items_A2.md",
    ]  # fmt: skip
    with paths[0].open(newline="") as f:
        sheet = list(csv.DictReader(f))
    with paths[2].open(newline="") as f:
        other_sheet = list(csv.DictReader(f))
    assert tuple(sheet[0]) == links.SHEET_COLUMNS
    assert all(r["verdict"] == "" and r["error_code"] == "" and r["note"] == "" for r in sheet)
    # the sheet does not show what the linker derived; the reading file does, after the evidence
    assert not {"derived_outcome", "evidence", "outcome", "code"} & set(sheet[0])
    assert not re.search(r"EXTENDED|ISSUED|= [01]\b", paths[0].read_text())
    # four links are on both sheets, and neither sheet says which
    shared = {r["link_id"] for r in sheet} & {r["link_id"] for r in other_sheet}
    assert shared == {r["sid"] for r in rows if r["checker"] == "both"} and len(shared) == 4
    assert {r["checker"] for r in sheet} == {"A1"} and {r["checker"] for r in other_sheet} == {"A2"}
    assert len({r["link_id"] for r in sheet + other_sheet}) == len(rows)  # every link is on a sheet
    assert [int(r["row"]) for r in sheet] == list(range(1, len(sheet) + 1))
    items = paths[1].read_text()
    assert "`both`" not in items and "do not confer on any" in items
    assert len(re.findall(r"(?m)^## \d+\. ", items)) == len(sheet)
    assert "## Draft codebook" in items and "`continued_new_id`" in items  # the rules, in the file
    for code in links.ERROR_CODES:
        assert f"- `{code}`:" in items
    by_id = {a.id: a for a in advisories}
    pairs = {s.sid: (s, x) for s, x in zip(statements, all_links, strict=True)}
    both = links.item_text(1, *pairs["gs-20240715-106"], by_id)
    assert "PROBABILITY OF EXTENSION: MEDIUM" in both  # the source advisory text
    assert "GROUND STOP PERIOD: 15/2003Z - 15/2215Z" in both  # the advisory that decides
    assert "**Derived outcome: EXTENDED = 1**" in both
    assert "20240715-157  sent 07/15 23:22Z  CDM GROUND STOP  MCO" in both  # the timeline
    # the checker reads the source and the later advisories before the derived outcome
    order = [both.index(mark) for mark in ("Source advisory:", "Every advisory the linker could",
                                           "**Derived outcome", "Advisory that decides")]  # fmt: skip
    assert order == sorted(order)
    assert both.count("Derived outcome") == 1 and "(+45 min)" not in both[: order[2]]
    plan_item = links.item_text(2, *pairs["plan-20240715-013-ORD-gs-UNTIL0400"], by_id)
    assert "UNTIL 0400\t-ORD/MDW GROUND STOP POSSIBLE" in plan_item
    assert "EN ROUTE PLANNED" not in plan_item and "STARLINK" not in plan_item  # excerpt only
    assert "Repeated in: 20240715-026" in plan_item


def test_the_checker_sees_the_titles_of_advisories_the_linker_does_not_read():
    # an arrival-delay notice and a programme under a title the parser does not know, both for
    # ORD and both inside the hours shown for the plan line "UNTIL 0400 ORD/MDW GROUND STOP"
    notice = fx.advisory(
        "ATCSCC ADVZY 014 ORD/ZAU 07/15/2024 ORD AIRPORT ARRIVAL DELAYS",
        "EVENT TIME: 15/0230 - 15/0400\nUSERS CAN EXPECT ARRIVAL DELAYS",
        "150231-150400",
        "24/07/15 02:31",
    )
    odd = fx.ORD_016.replace("ADVZY 016", "ADVZY 015").replace("CDM GROUND STOP", "ORD CDM STOP")
    elsewhere = notice.replace("ORD", "MDW").replace("ADVZY 014", "ADVZY 017")
    advisories = fx.parse_all(fx.PLAN_013, fx.ORD_016, notice, odd, elsewhere)
    assert [a.kind for a in advisories] == ["ops_plan", "other", "other", "other", "gs"]
    statements = faa.gs_statements(advisories) + faa.plan_statements(advisories)
    by_sid = {s.sid: s for s in statements}
    plan_line = by_sid["plan-20240715-013-ORD-gs-UNTIL0400"]
    assert links.others_naming(plan_line, advisories) == [
        "20240715-014  sent 07/15 02:31Z  ORD AIRPORT ARRIVAL DELAYS",
        "20240715-015  sent 07/15 02:52Z  ORD CDM STOP",
    ]
    # for a ground stop the hours start at its first issuance (0252Z)
    assert links.others_naming(by_sid["gs-20240715-016"], advisories) == [
        "20240715-015  sent 07/15 02:52Z  ORD CDM STOP"
    ]
    assert links.context_span(by_sid["gs-20240715-016"]) == (
        dt.datetime(2024, 7, 15, 2, 52),
        dt.datetime(2024, 7, 15, 6, 0),
    )
    all_links = {x.sid: x for x in links.link_all(statements, advisories, DATA_END)}
    by_id = {a.id: a for a in advisories}
    item = links.item_text(
        1, plan_line, all_links[plan_line.sid], by_id, links.others_naming(plan_line, advisories)
    )
    assert "Other advisories that name the element (not read by the linker):" in item
    assert item.index("ORD CDM STOP") < item.index("**Derived outcome")
    # no second list when there is nothing to put in it, and none for a route
    assert "Other advisories" not in links.item_text(1, plan_line, all_links[plan_line.sid], by_id)
    (route,) = faa.route_statements(fx.parse_all(fx.ROUTE_028))
    assert links.others_naming(route, advisories) == []


# --------------------------------------------------------------------------------------
# The scorer
# --------------------------------------------------------------------------------------


def returned_sheet(path, verdicts: dict[str, tuple[str, str]]):
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(links.SHEET_COLUMNS))
        writer.writeheader()
        for number, (link_id, (term, verdict)) in enumerate(verdicts.items(), start=1):
            writer.writerow({"row": number, "link_id": link_id, "term": term, "verdict": verdict})
    return path


def test_score_passes_at_ninety_percent_with_enough_links(tmp_path):
    verdicts = {f"gs-{i}": ("gs:MEDIUM", "ok") for i in range(100)}
    verdicts |= {f"plan-{i}": ("plan:POSSIBLE", "OK " if i < 35 else "wrong") for i in range(50)}
    verdicts |= {f"x-{i}": ("excluded", "wrong") for i in range(5)}  # reported, not in the gate
    checked = links.read_verdicts([returned_sheet(tmp_path / "a.csv", verdicts)])
    result = links.score(checked, {"gs:MEDIUM": 30, "plan:POSSIBLE": 30, "excluded": 0})
    assert (result["checked"], result["correct"], result["share_correct"]) == (150, 135, 0.9)
    assert result["passed"] is True
    assert result["terms"]["plan:POSSIBLE"]["share_correct"] == 0.7
    assert result["terms_below_threshold"] == ["plan:POSSIBLE"]
    assert result["terms"]["excluded"] == {
        "checked": 5,
        "required": 0,
        "correct": 0,
        "share_correct": 0.0,
        "unclear": 0,
    }


def test_score_fails_on_share_on_count_and_on_a_short_term(tmp_path):
    base = {f"gs-{i}": ("gs:MEDIUM", "ok") for i in range(120)}
    required = {"gs:MEDIUM": 30, "gs:LOW": 30}
    low_ok = {f"low-{i}": ("gs:LOW", "ok") for i in range(30)}

    def run(verdicts):
        return links.score(
            links.read_verdicts([returned_sheet(tmp_path / "s.csv", verdicts)]), required
        )

    assert run(base | low_ok)["passed"] is True
    one_short = dict(list((base | low_ok).items())[:-1])  # 149 links, 29 for gs:LOW
    result = run(one_short)
    assert (result["passed"], result["enough_links"], result["terms_short_of_required"]) == (
        False,
        False,
        ["gs:LOW"],
    )
    bad = base | {f"low-{i}": ("gs:LOW", "unclear" if i < 16 else "ok") for i in range(30)}
    result = run(bad)  # 134 of 150 = 0.893: unclear counts as not correct
    assert (result["passed"], result["share_correct"], result["terms"]["gs:LOW"]["unclear"]) == (
        False,
        0.8933,
        16,
    )
    assert run({k: v for k, v in base.items()})["terms_short_of_required"] == ["gs:LOW"]


def test_double_checked_link_needs_both_verdicts(tmp_path):
    a = returned_sheet(
        tmp_path / "a.csv",
        {"gs-1": ("gs:LOW", "ok"), "gs-2": ("gs:LOW", "ok"), "gs-3": ("gs:LOW", "")},
    )
    b = returned_sheet(tmp_path / "b.csv", {"gs-1": ("gs:LOW", "ok"), "gs-2": ("gs:LOW", "w")})
    result = links.score(links.read_verdicts([a, b]), {"gs:LOW": 2}, minimum=2)
    assert (result["checked"], result["correct"]) == (2, 1)  # the unchecked row is left out
    assert (result["double_checked"], result["double_agree"]) == (2, 1)
    assert result["passed"] is False


def test_error_codes_are_tallied_for_links_not_marked_ok(tmp_path):
    path = tmp_path / "a.csv"
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(links.SHEET_COLUMNS))
        writer.writeheader()
        for link_id, verdict, code in (
            ("gs-1", "ok", "M"),  # a code beside an ok verdict is ignored
            ("gs-2", "wrong", "m"),
            ("gs-3", "unclear", "D"),
            ("gs-4", "wrong", ""),
        ):
            writer.writerow(
                {"link_id": link_id, "term": "gs:LOW", "verdict": verdict, "error_code": code}
            )
    result = links.score(links.read_verdicts([path]), {"gs:LOW": 4}, minimum=4)
    assert result["error_codes"] == {"D": 1, "M": 1}
    assert (result["checked"], result["correct"], result["passed"]) == (4, 1, False)


def test_unknown_verdict_is_an_error(tmp_path):
    sheet = returned_sheet(tmp_path / "a.csv", {"gs-1": ("gs:LOW", "maybe")})
    with pytest.raises(ValueError, match="maybe"):
        links.read_verdicts([sheet])


# --------------------------------------------------------------------------------------
# Commands and the development / test separation
# --------------------------------------------------------------------------------------


@pytest.fixture
def root(tmp_path, monkeypatch):
    """April complete with the pilot day on the 15th, a June day, and the flag in a test folder."""
    monkeypatch.setattr(faa, "AMENDMENT_FLAG", tmp_path / fx.FLAG)
    fx.write_month(tmp_path, "2026-04")
    pages = {
        f"adv_{n}.html": fx.page_2026(text, "20260415")
        for n, text in zip(("013", "016", "021", "106", "118", "139", "149", "157", "165"),
                           (fx.PLAN_013, fx.ORD_016, fx.ORD_021, *fx.MCO_CHAIN), strict=True)
    }  # fmt: skip
    fx.write_day(tmp_path, "20260415", pages)
    june = {"adv_001.html": fx.page_2026(fx.ORD_016, "20260601")}
    fx.write_day(tmp_path, "20260601", june)
    return tmp_path


def test_commands_refuse_test_months(root, opened):
    common = ["--root", str(root), "--out", str(root / "out")]
    for command in ("link", "sample", "report"):
        name = ["--name", "x"] if command == "link" else []
        for months in (["2026-06"], ["2026-04", "2026-06"], ["2026-10"]):
            with pytest.raises(faa.TestMonthsLocked):
                links.main([command, "--months", *months, *name, *common])
        with pytest.raises(ValueError, match="YYYY-MM"):
            links.main([command, "--months", "2026-006", *common])
        with pytest.raises(SystemExit):  # the flag cannot be pointed elsewhere
            links.main([command, "--months", "2026-06", "--flag", str(root / "list.html"), *common])
    (root / fx.FLAG).write_text("registered\n")
    # the hand-check sheet and the report are for development months even after the amendment
    for command in ("sample", "report"):
        with pytest.raises(faa.TestMonthsLocked, match="development months only"):
            links.main([command, "--months", "2026-06", *common])
    # and the tables named "dev" never take a test month
    with pytest.raises(ValueError, match="--name"):
        links.main(["link", "--months", "2026-06", *common])
    with pytest.raises(ValueError, match="dev"):
        links.main(["link", "--months", "2026-06", "--name", "dev", *common])
    assert not (root / "out").exists()
    assert not any("202606" in path for path in opened)


def test_commands_refuse_a_month_that_is_not_all_on_disk(root):
    common = ["--root", str(root), "--out", str(root / "out")]
    (root / "20260415" / "adv_106.html").unlink()  # the first Orlando stop was never saved
    for command in ("link", "sample", "report"):
        with pytest.raises(faa.IncompleteCoverage, match="2026-04-15: 1 listed advisories"):
            links.main([command, "--months", "2026-04", *common])
    assert not (root / "out").exists()


def test_link_and_sample_commands_write_their_tables(root, opened, capsys):
    common = ["--root", str(root), "--out", str(root / "out")]
    assert links.main(["link", "--months", "2026-04", *common]) == 0
    with (root / "out" / "links_dev.csv").open(newline="") as f:
        table = list(csv.DictReader(f))
    assert len(table) == 6 + 9
    assert {r["code"] for r in table} == {"extended", "cancelled", "issued", "not_issued"}
    assert "gs:MEDIUM" in capsys.readouterr().out
    assert links.main(["sample", "--months", "2026-04", "--minimum", "5", *common]) == 0
    with (root / "out" / "linker_gate_frame.csv").open(newline="") as f:
        frame = {r["term"]: r for r in csv.DictReader(f)}
    assert frame["gs:MEDIUM"] == {
        "term": "gs:MEDIUM",
        "available": "6",
        "sampled": "6",
        "required": "6",
    }
    assert links.read_frame(root / "out" / "linker_gate_frame.csv")["plan:POSSIBLE"] == 6
    assert (root / "out" / "linker_gate_items_A2.md").exists()
    meta = json.loads((root / "out" / "linker_gate_meta.json").read_text())
    assert (meta["seed"], meta["draw"], meta["months"]) == (20261001, 1, ["2026-04"])
    assert meta["scored_links_in_frame"] == 15 and set(meta["sha256"]) == {"faa.py", "faa_links.py"}
    assert meta["rows_per_checker"] == {"A1": 15, "A2": 15} and meta["double_checked"] == 15
    # drawn again, the sheets are the same to the byte
    first = {p.name: p.read_bytes() for p in (root / "out").glob("linker_gate_*")}
    assert links.main(["sample", "--months", "2026-04", "--minimum", "5", *common]) == 0
    assert first == {p.name: p.read_bytes() for p in (root / "out").glob("linker_gate_*")}
    # once a checker has written a verdict, a new draw does not write over the sheet
    sheet = root / "out" / "linker_gate_sheet_A2.csv"
    blank = sheet.read_text()
    filled = blank.replace(",A2,,,\n", ",A2,ok,,\n", 1)
    sheet.write_text(filled)
    frame_before = (root / "out" / "linker_gate_frame.csv").read_bytes()
    for draw in ("1", "2"):
        with pytest.raises(FileExistsError, match=r"linker_gate_sheet_A2\.csv"):
            links.main(["sample", "--months", "2026-04", "--minimum", "5", "--draw", draw, *common])
    assert sheet.read_text() == filled != blank
    assert (root / "out" / "linker_gate_frame.csv").read_bytes() == frame_before
    assert (
        first["linker_gate_sheet_A1.csv"]
        == (root / "out" / "linker_gate_sheet_A1.csv").read_bytes()
    )
    assert links.main(["report", "--months", "2026-04", *common]) == 0
    report = json.loads((root / "out" / "dev_report.json").read_text())
    assert (report["advisories"], report["statements"]) == (9, 15)
    # the June day on disk was not opened by any of the three commands
    assert not any("202606" in path for path in opened)
