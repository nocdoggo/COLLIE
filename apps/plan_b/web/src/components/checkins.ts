// Whether a role's check-in actually covers what it is needed for. Readiness (contract section
// 7) needs the latest check-in's availability to cover the assigned window, so a check-in that
// ended or stops early is not shown as "checked in" for that slot.

import { compareIso, fmtTime, fmtWindow } from "../format";
import type { StatusLabel } from "../format";
import type { ActivityView, CheckInView, TimeWindow, UtcIso } from "../types";

/** The role's current declaration: latest `at`, ties to the later record (as the server). */
export function latestCheckIn(
  checkins: readonly CheckInView[],
  resourceId: string,
): CheckInView | undefined {
  let latest: CheckInView | undefined;
  for (const c of checkins) {
    if (c.resource_id !== resourceId) continue;
    if (latest === undefined || compareIso(c.at, latest.at) >= 0) latest = c;
  }
  return latest;
}

/** A window the check-in must cover, with the activity it belongs to (null: the clock). */
export interface CoverageNeed {
  readonly activityId: string | null;
  readonly window: TimeWindow;
}

export type CheckInCoverage =
  | { readonly kind: "none" }
  | { readonly kind: "covered"; readonly checkin: CheckInView }
  | { readonly kind: "not_covered"; readonly checkin: CheckInView; readonly need: CoverageNeed };

function contains(outer: TimeWindow, inner: TimeWindow): boolean {
  return compareIso(outer.start, inner.start) <= 0 && compareIso(inner.end, outer.end) <= 0;
}

/**
 * The part of an activity's slot that a check-in still has to cover at `clock`: the whole slot
 * before it starts, the rest of it while it runs, nothing once it has ended or stopped.
 */
export function slotToCover(activity: ActivityView, clock: UtcIso): TimeWindow | null {
  const a = activity.assignment;
  if (a === null) return null;
  if (activity.lifecycle === "planned" || activity.lifecycle === "ready") {
    return { start: a.start, end: a.end };
  }
  if (activity.lifecycle === "started" && compareIso(clock, a.end) < 0) {
    return { start: compareIso(clock, a.start) > 0 ? clock : a.start, end: a.end };
  }
  return null;
}

/** What a role's check-in must cover now: its remaining slots, or the clock if none remain. */
export function roleNeeds(
  activities: readonly ActivityView[],
  resourceId: string,
  clock: UtcIso,
): CoverageNeed[] {
  const needs: CoverageNeed[] = [];
  for (const activity of activities) {
    if (activity.assignment === null || !activity.assignment.resource_ids.includes(resourceId)) continue;
    const window = slotToCover(activity, clock);
    if (window !== null) needs.push({ activityId: activity.definition.activity_id, window });
  }
  return needs.length > 0 ? needs : [{ activityId: null, window: { start: clock, end: clock } }];
}

/** Checks the latest check-in against each need in order; the first gap is reported. */
export function checkInCoverage(
  checkins: readonly CheckInView[],
  resourceId: string,
  needs: readonly CoverageNeed[],
): CheckInCoverage {
  const checkin = latestCheckIn(checkins, resourceId);
  if (checkin === undefined) return { kind: "none" };
  for (const need of needs) {
    const ok =
      need.activityId === null
        ? compareIso(checkin.available.start, need.window.start) <= 0 &&
          compareIso(need.window.start, checkin.available.end) < 0
        : contains(checkin.available, need.window);
    if (!ok) return { kind: "not_covered", checkin, need };
  }
  return { kind: "covered", checkin };
}

/**
 * Tag text for a coverage result. With `activityLabel`, a gap names the activity it leaves
 * uncovered ("… does not cover Community demonstrations 17:10–17:30").
 */
export function coverageLabel(
  coverage: CheckInCoverage,
  tz: string,
  activityLabel?: (id: string) => string,
): StatusLabel {
  switch (coverage.kind) {
    case "none":
      return { text: "No check-in yet", icon: "⧗", tone: "warn" };
    case "covered":
      return { text: "Checked in", icon: "✓", tone: "ok" };
    case "not_covered": {
      const { need, checkin } = coverage;
      const what =
        need.activityId === null
          ? `${fmtTime(need.window.start, tz)} (now)`
          : `${activityLabel !== undefined ? `${activityLabel(need.activityId)} ` : ""}${fmtWindow(
              need.window.start,
              need.window.end,
              tz,
            )}`;
      const late = compareIso(checkin.available.start, need.window.start) > 0;
      const bound = late
        ? `from ${fmtTime(checkin.available.start, tz)}`
        : `until ${fmtTime(checkin.available.end, tz)}`;
      return { text: `Check-in available ${bound} — does not cover ${what}`, icon: "⚠", tone: "warn" };
    }
  }
}
