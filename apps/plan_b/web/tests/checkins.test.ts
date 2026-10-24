// Role readiness and schedule person lines: "Checked in" only when the latest check-in covers
// what it is needed for (review web-3).

import assert from "node:assert/strict";
import { test } from "node:test";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { RoleReadiness } from "../src/components/Resources.tsx";
import { Schedule } from "../src/components/Schedule.tsx";
import {
  checkInCoverage,
  coverageLabel,
  latestCheckIn,
  roleNeeds,
  slotToCover,
} from "../src/components/checkins.ts";
import type { EventStateView } from "../src/types.ts";
import { checkin, local, makeView, textOf } from "./support/view.ts";

const TZ = "America/New_York";

function roleText(view: EventStateView): string {
  return textOf(renderToStaticMarkup(createElement(RoleReadiness, { view })));
}

function scheduleText(view: EventStateView): string {
  return textOf(renderToStaticMarkup(createElement(Schedule, { view })));
}

/** The text of one role's entry (from its label up to the next role). */
function roleEntry(text: string, label: string, next: string): string {
  const start = text.indexOf(label);
  const end = text.indexOf(next, start + label.length);
  return text.slice(start, end === -1 ? undefined : end);
}

test("the latest check-in is the one with the latest time, ties to the later record", () => {
  const early = checkin("presenter", "16:35", "18:00", 1);
  const late = checkin("presenter", "16:40", "16:45", 2);
  const sameMinute = checkin("presenter", "16:40", "17:00", 3);
  assert.equal(latestCheckIn([late, early], "presenter"), late);
  assert.equal(latestCheckIn([early, late, sameMinute], "presenter"), sameMinute);
  assert.equal(latestCheckIn([early], "facilitator"), undefined);
});

test("coverage of a slot requires the whole window", () => {
  const view = makeView({ clock: local("16:50") });
  const needs = roleNeeds(view.activities, "presenter", view.clock);
  assert.deepEqual(needs, [{ activityId: "demonstrations", window: { start: local("17:10"), end: local("17:30") } }]);
  const short = checkInCoverage([checkin("presenter", "16:40", "16:45")], "presenter", needs);
  assert.equal(short.kind, "not_covered");
  assert.equal(
    coverageLabel(short, TZ).text,
    "Check-in available until 16:45 — does not cover 17:10–17:30",
  );
  assert.equal(coverageLabel(short, TZ).tone, "warn");
  const stopsEarly = checkInCoverage([checkin("presenter", "16:40", "17:15")], "presenter", needs);
  assert.equal(
    coverageLabel(stopsEarly, TZ, () => "Community demonstrations").text,
    "Check-in available until 17:15 — does not cover Community demonstrations 17:10–17:30",
  );
  const full = checkInCoverage([checkin("presenter", "16:40", "17:30")], "presenter", needs);
  assert.equal(full.kind, "covered");
  assert.equal(checkInCoverage([], "presenter", needs).kind, "none");
});

test("with no slot left, the check-in must cover the clock", () => {
  const view = makeView({ clock: local("16:50") });
  const done = view.activities.map((a) =>
    a.definition.activity_id === "demonstrations" ? { ...a, lifecycle: "completed" as const } : a,
  );
  const needs = roleNeeds(done, "presenter", view.clock);
  assert.deepEqual(needs, [{ activityId: null, window: { start: local("16:50"), end: local("16:50") } }]);
  const ended = checkInCoverage([checkin("presenter", "16:40", "16:45")], "presenter", needs);
  assert.equal(coverageLabel(ended, TZ).text, "Check-in available until 16:45 — does not cover 16:50 (now)");
  assert.equal(checkInCoverage([checkin("presenter", "16:40", "17:00")], "presenter", needs).kind, "covered");
});

test("a running activity needs only its remaining part", () => {
  const view = makeView({ clock: local("16:50") });
  const setup = view.activities.find((a) => a.definition.activity_id === "setup");
  assert.ok(setup !== undefined && setup.lifecycle === "started");
  assert.deepEqual(slotToCover(setup, view.clock), { start: local("16:50"), end: local("17:10") });
  assert.equal(slotToCover({ ...setup, lifecycle: "completed" }, view.clock), null);
});

test("role readiness warns when the check-in ended before the slot", () => {
  const view = makeView({ clock: local("16:50"), checkins: [checkin("presenter", "16:40", "16:45")] });
  const entry = roleEntry(roleText(view), "Demonstration lead", "Skills facilitator");
  assert.ok(!entry.includes("✓ Checked in"), entry);
  assert.ok(
    entry.includes("⚠ Check-in available until 16:45 — does not cover Community demonstrations 17:10–17:30"),
    entry,
  );
  const html = renderToStaticMarkup(createElement(RoleReadiness, { view }));
  assert.ok(html.includes('class="tag tone-warn"'));

  const covered = makeView({ clock: local("16:50"), checkins: [checkin("presenter", "16:40", "18:00")] });
  assert.ok(roleEntry(roleText(covered), "Demonstration lead", "Skills facilitator").includes("✓ Checked in"));
});

test("the schedule's person line matches the slot it sits in", () => {
  const view = makeView({ clock: local("16:50"), checkins: [checkin("presenter", "16:40", "16:45")] });
  const text = scheduleText(view);
  assert.ok(!text.includes("✓ Checked in at 16:40"), text);
  assert.ok(text.includes("Demonstration lead ⚠ Check-in available until 16:45 — does not cover 17:10–17:30"));

  const covered = makeView({ clock: local("16:50"), checkins: [checkin("presenter", "16:40", "18:00")] });
  assert.ok(scheduleText(covered).includes("Demonstration lead ✓ Checked in at 16:40 , available 16:40–18:00"));
});
