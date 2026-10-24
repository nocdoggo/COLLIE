// Check-in form rules. Availability is reported as chosen or not at all: a chosen end time that
// the scenario clock has passed blocks the submission instead of silently becoming "not
// specified" (which the server would record as the role's whole declared window).

import { addMinutes, compareIso, toUtcIso } from "../format";
import type { EventStateView, JsonObject, UtcIso } from "../types";

/** Availability end choices: every 5 minutes from just after the scenario clock to the hard end. */
export function endChoices(view: Pick<EventStateView, "clock" | "goal">): UtcIso[] {
  const out: UtcIso[] = [];
  const clockMs = new Date(view.clock).getTime();
  const firstMs = Math.ceil((clockMs + 60_000) / 300_000) * 300_000;
  let t = toUtcIso(new Date(firstMs));
  while (compareIso(t, view.goal.hard_end) <= 0 && out.length < 60) {
    out.push(t);
    t = addMinutes(t, 5);
  }
  return out;
}

export type CheckInChoice =
  | { readonly ok: true; readonly args: JsonObject }
  /** The chosen "available until" time is no longer after the scenario clock. */
  | { readonly ok: false; readonly passedEnd: UtcIso };

/** check_in arguments for the chosen end time ("" = not specified), or why they cannot be sent. */
export function checkInArguments(resourceId: string, availableEnd: UtcIso | "", clock: UtcIso): CheckInChoice {
  if (availableEnd === "") return { ok: true, args: { resource_id: resourceId } };
  if (compareIso(availableEnd, clock) <= 0) return { ok: false, passedEnd: availableEnd };
  return { ok: true, args: { resource_id: resourceId, available: { start: clock, end: availableEnd } } };
}
