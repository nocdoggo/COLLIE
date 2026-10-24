// Typed state-view fixtures for component and helper tests, modeled on the campus fixture
// (event on 2026-11-05 in America/New_York, EST = UTC-5). Only what the tests need is filled.

import type {
  ActionReceipt,
  ActivityView,
  Assignment,
  AuthorityGrant,
  CandidateAssumption,
  CandidateCheck,
  CandidateResult,
  CheckInView,
  EvaluationResult,
  EventStateView,
  GrantView,
  ResourceKind,
  ResourceStatus,
  ResourceView,
  UtcIso,
} from "../../src/types.ts";

/** "16:40" on the event day (EST) as the UTC transport form. */
export function local(hhmm: string): UtcIso {
  const [h = 0, m = 0] = hhmm.split(":").map(Number);
  return new Date(Date.UTC(2026, 10, 5, h + 5, m)).toISOString().replace(/\.\d{3}Z$/, "Z");
}

function resource(
  id: string,
  label: string,
  kind: ResourceKind,
  status: ResourceStatus,
  bookingRequired = false,
): ResourceView {
  return {
    definition: {
      resource_id: id,
      label,
      kind,
      capacity: kind === "space" ? 120 : 1,
      window: { start: local("16:00"), end: local("18:00") },
      initial_status: status,
      source_ref: `fixture:${id}`,
      capabilities: [],
      approved_substitute_ids: id === "projector" ? ["backup_projector"] : [],
      terms: {
        booking_required: bookingRequired,
        commitment_cost_cents: bookingRequired ? 3500 : 0,
        hold_fee_cents: 0,
        reserved_exposure_cents: bookingRequired ? 3500 : 0,
        hold_max_minutes: bookingRequired ? 10 : null,
        commitment_cutoff_minutes_before_use: bookingRequired ? 15 : null,
        refundable_on_release: true,
        cancellation_supported: false,
        booking_ref: null,
        status_source_id: null,
        queryable_facts: [],
        terms_source_ref: `fixture:${id}:terms`,
      },
    },
    status,
    status_basis: "catalog",
    status_observation_id: null,
    status_observed_at: null,
    reported_eta: null,
    occupancy: [],
  };
}

export const ASSIGNMENTS: readonly Assignment[] = [
  { activity_id: "setup", start: local("16:30"), end: local("17:10"), resource_ids: ["main_hall", "host"] },
  {
    activity_id: "demonstrations",
    start: local("17:10"),
    end: local("17:30"),
    resource_ids: ["main_hall", "projector", "presenter"],
  },
  {
    activity_id: "skills_exchange",
    start: local("17:30"),
    end: local("17:50"),
    resource_ids: ["main_hall", "facilitator"],
  },
  { activity_id: "closing", start: local("17:50"), end: local("18:00"), resource_ids: ["main_hall", "host"] },
];

const LABELS: Record<string, string> = {
  setup: "Room setup",
  demonstrations: "Community demonstrations",
  skills_exchange: "Skills exchange",
  closing: "Closing",
};

function activity(a: Assignment): ActivityView {
  return {
    definition: {
      activity_id: a.activity_id,
      label: LABELS[a.activity_id] ?? a.activity_id,
      duration_minutes: 20,
      window: { start: local("16:30"), end: local("18:00") },
      predecessors: [],
      required_resources: a.resource_ids,
      required: true,
      program: a.activity_id !== "setup",
    },
    lifecycle: a.activity_id === "setup" ? "started" : "planned",
    history: [],
    assignment: a,
    readiness: null,
  };
}

function grant(principalId: string, role: AuthorityGrant["principal_role"], resourceIds: string[]): GrantView {
  return {
    grant: {
      grant_id: `grant_${principalId}`,
      event_id: "evt_demo",
      principal_role: role,
      principal_id: principalId,
      allowed_tools: role === "participant" ? ["check_in", "submit_observation"] : [],
      resource_ids: resourceIds,
      activity_ids: [],
      max_total_committed_cents: 0,
      max_total_reserved_cents: role === "coordinator_agent" ? 3500 : 0,
      expires_at: local("18:30"),
      review_required_for: [],
    },
    version: 1,
    revoked: false,
    valid_now: true,
    committed_used_cents: 0,
    reserved_used_cents: 0,
    issued_receipt_id: null,
  };
}

export function checkin(resourceId: string, at: string, until: string, seq = 1): CheckInView {
  return {
    checkin_id: `chk_${String(seq).padStart(4, "0")}`,
    principal_id: `participant_${resourceId}`,
    resource_id: resourceId,
    at: local(at),
    available: { start: local(at), end: local(until) },
    observation_id: null,
    channel: "participant_session",
  };
}

export function makeView(overrides: Partial<EventStateView> = {}): EventStateView {
  const grants = [
    grant("participant_presenter", "participant", ["presenter"]),
    grant("organizer_demo", "organizer", []),
    grant("agent_demo", "coordinator_agent", ["backup_projector"]),
  ];
  return {
    runtime_version: "1.0.0",
    episode_id: "ep_test",
    event_id: "evt_demo",
    scenario_id: "dev_fixture_01",
    profile_id: "campus_showcase",
    fictional: true,
    sandbox_label: "Fictional sandbox",
    timezone: "America/New_York",
    episode_status: "active",
    clock: local("16:40"),
    revision: 4,
    goal: {
      goal_id: "goal_demo",
      description: "Run the showcase",
      required_activity_ids: ["setup", "demonstrations", "skills_exchange", "closing"],
      public_start: local("16:30"),
      hard_end: local("18:00"),
      budget_cents: 15000,
      attendance_target: 80,
      fixed_venue_id: "main_hall",
      priorities: [],
      version: 1,
      preference_preset: "balanced",
      objective_weights: {
        start_shift_per_minute: 1,
        changed_activity: 10,
        spend_per_100_cents: 4,
        optional_activity_removed: 1000,
        participant_notification: 5,
      },
      accessibility_requirements: [],
      program_concurrency: 1,
    },
    goal_history: [],
    activities: ASSIGNMENTS.map(activity),
    plan: { plan_version: 1, assignments: ASSIGNMENTS, applied_receipt_id: null, candidate_id: null, applied_at: null },
    plan_history: [],
    resources: [
      resource("main_hall", "Main hall", "space", "available"),
      resource("projector", "Projector", "equipment", "expected"),
      resource("backup_projector", "Backup projector", "equipment", "available", true),
      resource("presenter", "Demonstration lead", "person", "available"),
      resource("facilitator", "Skills facilitator", "person", "available"),
      resource("host", "Event host", "person", "available"),
    ],
    holds: [],
    commitments: [],
    checkins: [],
    budget: { budget_cents: 15000, committed_cents: 0, reserved_cents: 0, remaining_cents: 15000 },
    grants,
    grant_history: grants,
    observations: [],
    status_sources: [],
    status_checks: [],
    receipts: [],
    attempts: [],
    decisions: [],
    latest_evaluation: null,
    transitions: [],
    declared_assumptions: [],
    tool_durations_minutes: {},
    viewer: {
      principal_id: "participant_presenter",
      role: "participant",
      display_name: "Demonstration lead",
      grant_id: "grant_participant_presenter",
    },
    ...overrides,
  };
}

export function check(constraintId: string, status: CandidateCheck["status"] = "passed"): CandidateCheck {
  return { constraint_id: constraintId, status, detail: `${constraintId} detail`, entity_ids: [] };
}

export function assumption(
  kind: CandidateAssumption["kind"],
  entityId: string,
  text: string,
): CandidateAssumption {
  return { assumption_id: `asm_${kind}_${entityId}`, kind, entity_id: entityId, text, basis_ref: null };
}

export function makeCandidate(overrides: Partial<CandidateResult> = {}): CandidateResult {
  return {
    candidate_id: "cand_0001_aaaaaaaa",
    report_id: "rpt_0001_aaaaaaaa",
    signature: "a".repeat(64),
    label: "Swap demonstrations and skills exchange",
    edits: [],
    assignments: ASSIGNMENTS,
    changed_activity_ids: ["demonstrations", "skills_exchange"],
    incremental_committed_cents: 0,
    constraint_status: "feasible_under_assumptions",
    checks: [check("required_activities")],
    assumptions: [],
    execution_preconditions: [],
    required_holds: [],
    authorization: { sufficient: true, missing: [] },
    objective: {
      start_shift_minutes: 40,
      changed_activities: 2,
      additional_committed_cents: 0,
      optional_activities_removed: 0,
      participant_notifications: 2,
      weighted: {},
      total: 70,
    },
    rank: 1,
    applicable_now: true,
    rationale: "",
    ...overrides,
  };
}

export function makeEvaluation(
  candidates: readonly CandidateResult[],
  overrides: Partial<EvaluationResult> = {},
): EvaluationResult {
  return {
    evaluation_id: "eval_0001",
    event_id: "evt_demo",
    revision: 4,
    goal_version: 1,
    evaluated_at: local("16:42"),
    actor_id: "agent_demo",
    hypothetical: false,
    hypotheses: [],
    templates: ["keep", "swap"],
    max_combined_edits: 2,
    candidate_cap: 64,
    generated_count: candidates.length,
    evaluated_count: candidates.length,
    truncated: false,
    candidates,
    best_candidate_id: candidates[0]?.candidate_id ?? null,
    best_applicable_candidate_id: candidates.find((c) => c.applicable_now)?.candidate_id ?? null,
    keep_candidate_id: null,
    infeasibility: null,
    ...overrides,
  };
}

export function makeReceipt(overrides: Partial<ActionReceipt> = {}): ActionReceipt {
  return {
    runtime_version: "1.0.0",
    receipt_id: "rcpt_0001",
    episode_id: "ep_test",
    event_id: "evt_demo",
    tool: "check_in",
    request_idempotency_key: "web-check_in-1",
    request_digest: "0".repeat(64),
    grant_id: "grant_participant_presenter",
    grant_version: 1,
    actor_id: "participant_presenter",
    actor_role: "participant",
    status: "applied",
    revision_before: 4,
    revision_after: 5,
    requested_at: local("16:40"),
    executed_at: local("16:40"),
    simulation: true,
    state_changes: [],
    committed_delta_cents: 0,
    reserved_delta_cents: 0,
    related_plan_id: null,
    constraint_report_ref: null,
    error_code: null,
    error_message: null,
    summary: "Checked in presenter",
    ...overrides,
  };
}

/** Visible text of rendered markup, with tags removed and whitespace collapsed. */
export function textOf(html: string): string {
  return html
    .replace(/<[^>]+>/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&quot;/g, '"')
    .replace(/&#x27;/g, "'")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/\s+/g, " ")
    .trim();
}
