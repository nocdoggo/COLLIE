// Display helpers. Scenario times are always formatted in the event timezone from the state
// view (Intl with an explicit timeZone); the browser's own timezone and clock are never used
// for scenario time.

import type {
  ActionReceipt,
  ActivityView,
  CheckStatus,
  DecisionKind,
  EventStateView,
  HoldStatus,
  LifecycleState,
  ObservationChannel,
  ReceiptStatus,
  ResourceStatus,
  UtcIso,
} from "./types";

const formatterCache = new Map<string, Intl.DateTimeFormat>();

function formatter(timeZone: string, options: Intl.DateTimeFormatOptions): Intl.DateTimeFormat {
  const key = `${timeZone}|${JSON.stringify(options)}`;
  let cached = formatterCache.get(key);
  if (cached === undefined) {
    try {
      cached = new Intl.DateTimeFormat("en-US", { ...options, timeZone });
    } catch {
      // An unrecognized zone falls back to UTC; zoneName() makes the fallback visible.
      cached = new Intl.DateTimeFormat("en-US", { ...options, timeZone: "UTC" });
    }
    formatterCache.set(key, cached);
  }
  return cached;
}

const TIME: Intl.DateTimeFormatOptions = { hour: "2-digit", minute: "2-digit", hourCycle: "h23" };
const DATE: Intl.DateTimeFormatOptions = {
  weekday: "short",
  month: "short",
  day: "numeric",
  year: "numeric",
};
const ZONE: Intl.DateTimeFormatOptions = { timeZoneName: "short", hour: "numeric" };

function parse(iso: UtcIso): Date | null {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? null : date;
}

/** "17:25" in the event timezone. */
export function fmtTime(iso: UtcIso | null | undefined, timeZone: string): string {
  if (iso === null || iso === undefined) return "—";
  const date = parse(iso);
  return date === null ? iso : formatter(timeZone, TIME).format(date);
}

/** "Thu, Nov 5, 2026" in the event timezone. */
export function fmtDate(iso: UtcIso, timeZone: string): string {
  const date = parse(iso);
  return date === null ? iso : formatter(timeZone, DATE).format(date);
}

/** Short zone name such as "EST" for the given instant. */
export function zoneName(iso: UtcIso, timeZone: string): string {
  const date = parse(iso);
  if (date === null) return timeZone;
  const part = formatter(timeZone, ZONE)
    .formatToParts(date)
    .find((p) => p.type === "timeZoneName");
  return part?.value ?? timeZone;
}

/** "17:10–17:30" in the event timezone. */
export function fmtWindow(start: UtcIso, end: UtcIso, timeZone: string): string {
  return `${fmtTime(start, timeZone)}–${fmtTime(end, timeZone)}`;
}

/** Whole minutes from a to b (b - a). */
export function minutesBetween(a: UtcIso, b: UtcIso): number {
  const da = parse(a);
  const db = parse(b);
  if (da === null || db === null) return 0;
  return Math.round((db.getTime() - da.getTime()) / 60000);
}

export function addMinutes(iso: UtcIso, minutes: number): UtcIso {
  const date = parse(iso);
  if (date === null) return iso;
  return toUtcIso(new Date(date.getTime() + minutes * 60000));
}

/** Transport form used by the server: YYYY-MM-DDTHH:MM:SSZ. */
export function toUtcIso(date: Date): UtcIso {
  return date.toISOString().replace(/\.\d{3}Z$/, "Z");
}

export function compareIso(a: UtcIso, b: UtcIso): number {
  const da = parse(a)?.getTime() ?? 0;
  const db = parse(b)?.getTime() ?? 0;
  return da - db;
}

/** A wall-clock time (for join-code expiry). Wall time is shown in the viewer's own zone. */
export function fmtWall(iso: UtcIso): string {
  const date = parse(iso);
  return date === null ? iso : date.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" });
}

const money = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });

/** Integer cents as "$35.00" (fictional sandbox money). */
export function fmtCents(cents: number): string {
  return money.format(cents / 100);
}

export function fmtSignedCents(cents: number): string {
  if (cents === 0) return fmtCents(0);
  return `${cents > 0 ? "+" : "−"}${fmtCents(Math.abs(cents))}`;
}

/** "16 standard kits": a whole-unit stock quantity with its unit, plural when not one. */
export function fmtQuantity(quantity: number, unit: string): string {
  const name = unit.replace(/_/g, " ");
  return `${quantity} ${quantity === 1 || name.endsWith("s") ? name : `${name}s`}`;
}

/** A model call's cost as the provider reported it, in US dollars (real money, not sandbox). */
export function fmtUsd(cost: number | null): string {
  if (cost === null) return "cost not reported";
  return cost === 0 ? "$0 USD" : `$${cost.toFixed(4)} USD`;
}

/** "4.98 s" or "820 ms". */
export function fmtLatency(ms: number | null): string {
  if (ms === null) return "latency not reported";
  return ms >= 1000 ? `${(ms / 1000).toFixed(2)} s` : `${Math.round(ms)} ms`;
}

// ---------------------------------------------------------------------------
// Labels and icons. Every status is shown as text plus an icon, never color alone.
// ---------------------------------------------------------------------------

export type Tone = "ok" | "warn" | "bad" | "info" | "neutral";

export interface StatusLabel {
  readonly text: string;
  readonly icon: string;
  readonly tone: Tone;
}

export const LIFECYCLE_LABEL: Record<LifecycleState, StatusLabel> = {
  planned: { text: "Planned", icon: "○", tone: "neutral" },
  ready: { text: "Ready", icon: "✓", tone: "ok" },
  started: { text: "Started", icon: "▶", tone: "info" },
  completed: { text: "Completed", icon: "✔", tone: "ok" },
  failed: { text: "Failed", icon: "✖", tone: "bad" },
  canceled: { text: "Canceled", icon: "⊘", tone: "neutral" },
};

export const RESOURCE_STATUS_LABEL: Record<ResourceStatus, StatusLabel> = {
  available: { text: "Available", icon: "✓", tone: "ok" },
  expected: { text: "Expected, not yet arrived", icon: "⧗", tone: "warn" },
  unavailable: { text: "Unavailable", icon: "✖", tone: "bad" },
  unknown: { text: "Status unknown", icon: "?", tone: "warn" },
};

export const HOLD_STATUS_LABEL: Record<HoldStatus, StatusLabel> = {
  active: { text: "Held", icon: "‖", tone: "info" },
  committed: { text: "Committed", icon: "✔", tone: "ok" },
  released: { text: "Released", icon: "↩", tone: "neutral" },
  expired: { text: "Expired", icon: "⧖", tone: "warn" },
  fulfilled: { text: "Handed off (fulfilled)", icon: "⇉", tone: "ok" },
};

export const RECEIPT_STATUS_LABEL: Record<ReceiptStatus, StatusLabel> = {
  applied: { text: "Applied", icon: "✔", tone: "ok" },
  rejected: { text: "Rejected", icon: "✖", tone: "bad" },
  unknown: { text: "Unresolved", icon: "?", tone: "warn" },
};

/** An applied receipt that no fresh state read has shown yet: not success until it does. */
export const APPLIED_UNCONFIRMED_LABEL: StatusLabel = {
  text: "Applied, confirming in a fresh state read",
  icon: "⧗",
  tone: "neutral",
};

/**
 * An applied receipt that changed nothing: the revision stayed and no state changes are listed.
 * The server answers this way to a duplicate (for example an observation it already stored), so
 * the receipt has no transition of its own and must not read as a second success.
 */
export const APPLIED_NO_CHANGE_LABEL: StatusLabel = {
  text: "Applied, no change (duplicate)",
  icon: "⧉",
  tone: "neutral",
};

export function appliedWithoutChange(receipt: ActionReceipt): boolean {
  return (
    receipt.status === "applied" &&
    receipt.revision_after === receipt.revision_before &&
    receipt.state_changes.length === 0
  );
}

/** The badge for a receipt in a state read. */
export function receiptLabel(receipt: ActionReceipt): StatusLabel {
  return appliedWithoutChange(receipt) ? APPLIED_NO_CHANGE_LABEL : RECEIPT_STATUS_LABEL[receipt.status];
}

/** `passed` is used only for checks that rest on no candidate assumption. */
export const CHECK_STATUS_LABEL: Record<CheckStatus, StatusLabel> = {
  passed: { text: "Confirmed", icon: "✓", tone: "ok" },
  failed: { text: "Failed", icon: "✖", tone: "bad" },
  not_applicable: { text: "Not applicable", icon: "–", tone: "neutral" },
  unsupported: { text: "Unsupported (result unknown)", icon: "?", tone: "warn" },
};

/** A passed check whose truth rests on one of the candidate's assumptions. */
export const PASSES_UNDER_ASSUMPTION_LABEL: StatusLabel = {
  text: "Passes under assumption",
  icon: "≈",
  tone: "warn",
};

export const DECISION_LABEL: Record<DecisionKind, StatusLabel> = {
  keep: { text: "Keep plan", icon: "=", tone: "neutral" },
  verify: { text: "Verify", icon: "◎", tone: "info" },
  prepare: { text: "Prepare", icon: "‖", tone: "info" },
  commit: { text: "Commit", icon: "✔", tone: "ok" },
  ask: { text: "Ask organizer", icon: "⚑", tone: "warn" },
  infeasible: { text: "Infeasible", icon: "⚠", tone: "bad" },
  wait: { text: "Wait", icon: "⧗", tone: "neutral" },
  unresolved: { text: "Unresolved", icon: "?", tone: "warn" },
  inapplicable: { text: "Does not apply", icon: "⊘", tone: "neutral" },
  duplicate: { text: "Duplicate", icon: "⧉", tone: "neutral" },
  release: { text: "Release", icon: "↩", tone: "neutral" },
  reconcile: { text: "Reconcile", icon: "⇄", tone: "info" },
  stop: { text: "Stop", icon: "■", tone: "neutral" },
};

export const CHANNEL_LABEL: Record<ObservationChannel, string> = {
  fixture_initial: "Authored setup (fixture)",
  scenario_delivery: "Simulated message delivery",
  status_tool: "Status check (query_status)",
  arrival_record: "Receiving-desk arrival record (simulated)",
  participant_session: "Participant session",
  organizer_session: "Organizer session",
};

/** Plain-language names for the planner's hard-constraint checks (contract section 10). */
export const CHECK_NAME: Record<string, string> = {
  required_activities: "Every required activity is scheduled",
  fixed_venue: "Uses the fixed venue",
  started_history: "Started or finished activities stay as they were",
  no_past_change: "No change starts in the past",
  activity_windows: "Each activity keeps its allowed window and length",
  event_window: "Everything ends by the hard end",
  dependencies: "Activities follow their required order",
  program_exclusivity: "Only one program activity at a time",
  occupancy_capacity: "Attendance fits the venue",
  resource_capacity: "No resource is double-booked",
  resource_status: "Assigned resources are not unavailable or unknown",
  arrival_assumptions: "Expected equipment is reported to arrive before its activity starts",
  substitute_compatibility: "Substitutes are approved and compatible",
  participant_availability: "People are available for their slots",
  accessibility: "Accessibility requirements are met",
  commitment_cutoff: "Bookings are committed before their cutoff",
  budget: "Spending stays within the event budget",
  consumable_allocation: "Stock allocations match what the target needs",
  stock_on_hand: "Allocated stock is physically on hand (expected units never count)",
  stock_transfer: "A transfer can still be handed off before the cutoff",
  service_throughput: "Staff can distribute the reserved stock before the event ends",
};

export function checkName(constraintId: string): string {
  return CHECK_NAME[constraintId] ?? constraintId.replace(/_/g, " ");
}

export const PRESET_LABEL: Record<string, string> = {
  balanced: "Balanced",
  preserve_order: "Preserve the announced order",
  minimize_spend: "Minimize additional spend",
};

// ---------------------------------------------------------------------------
// Which coordinator policy ran (mode label)
// ---------------------------------------------------------------------------

export const DETERMINISTIC_POLICY_LABEL = "Deterministic policy";
export const LIVE_AGENT_LABEL = "Live agent";

/** "Live agent · anthropic/claude-sonnet-5.5"; the model id as the provider returned it. */
export function liveAgentLabel(modelId: string | null): string {
  return `${LIVE_AGENT_LABEL} · ${modelId ?? "model not reported yet"}`;
}

/**
 * Live-agent (P2) decisions carry policy ids "live/<version>". P1 (`tool-use/`) and P3
 * (`verify-all/`) are model-driven too: components/policyMode.ts `modelPolicyLabel` covers all three.
 */
export function isLivePolicyId(policyId: string): boolean {
  return policyId.startsWith("live/");
}

export const ROLE_LABEL: Record<string, string> = {
  moderator: "Moderator (sandbox operator)",
  organizer: "Organizer",
  participant: "Participant",
  coordinator_agent: "Coordinator agent",
};

// ---------------------------------------------------------------------------
// Lookups over a state view
// ---------------------------------------------------------------------------

export interface Lookups {
  readonly resourceLabel: (id: string) => string;
  readonly activityLabel: (id: string) => string;
  readonly entityLabel: (id: string) => string;
  readonly tz: string;
}

export function lookups(view: EventStateView): Lookups {
  const resources = new Map(view.resources.map((r) => [r.definition.resource_id, r.definition.label]));
  const activities = new Map(
    view.activities.map((a) => [a.definition.activity_id, a.definition.label]),
  );
  return {
    resourceLabel: (id) => resources.get(id) ?? id,
    activityLabel: (id) => activities.get(id) ?? id,
    entityLabel: (id) => resources.get(id) ?? activities.get(id) ?? id,
    tz: view.timezone,
  };
}

/** Activities ordered by their current assignment start (unassigned last, by definition order). */
export function activitiesInPlanOrder(view: EventStateView): ActivityView[] {
  const withIndex = view.activities.map((a, index) => ({ a, index }));
  withIndex.sort((x, y) => {
    const xs = x.a.assignment?.start;
    const ys = y.a.assignment?.start;
    if (xs !== undefined && ys !== undefined) return compareIso(xs, ys) || x.index - y.index;
    if (xs !== undefined) return -1;
    if (ys !== undefined) return 1;
    return x.index - y.index;
  });
  return withIndex.map((x) => x.a);
}

export function pretty(value: unknown): string {
  return JSON.stringify(value, null, 2);
}
