// Hand-written mirror of the models in plan_b/domain/models.py that cross HTTP
// (runtime contract 1.0.0, trace format 1.0.0). Datetimes are UTC ISO 8601 strings ending in "Z".
// Python tuples arrive as JSON arrays; they are typed readonly because every model is frozen.

export type UtcIso = string;
export type JsonValue =
  | null
  | boolean
  | number
  | string
  | readonly JsonValue[]
  | { readonly [key: string]: JsonValue };
export type JsonObject = { readonly [key: string]: JsonValue };

// ---------------------------------------------------------------------------
// Shared vocabulary
// ---------------------------------------------------------------------------

export type ResourceKind = "space" | "equipment" | "person" | "supply";
export type ResourceStatus = "available" | "expected" | "unavailable" | "unknown";
export type StatusBasis = "catalog" | "status_observation" | "arrival_observation";
export type LifecycleState = "planned" | "ready" | "started" | "completed" | "failed" | "canceled";
export type PrincipalRole = "organizer" | "coordinator_agent" | "participant";
export type SessionRole = "organizer" | "coordinator_agent" | "participant" | "moderator";
export type ObservationKind = "notice" | "status" | "check_in" | "resource_offer" | "policy";
export type AuthorityScope =
  | "self_report"
  | "resource_status"
  | "organizer_instruction"
  | "public_policy";
export type ObservationChannel =
  | "fixture_initial"
  | "scenario_delivery"
  | "status_tool"
  | "arrival_record"
  | "participant_session"
  | "organizer_session";
export type EnvelopeStatus = "succeeded" | "rejected" | "unknown" | "unavailable";
export type ReceiptStatus = "applied" | "rejected" | "unknown";
export type HoldStatus = "active" | "committed" | "released" | "expired";
export type ConstraintResult = "feasible_under_assumptions" | "infeasible" | "unknown";
export type CheckStatus = "passed" | "failed" | "not_applicable" | "unsupported";
export type PreferencePreset = "balanced" | "preserve_order" | "minimize_spend";

export const READ_TOOLS = [
  "get_event_state",
  "get_action_receipt",
  "list_resources",
  "query_status",
  "evaluate_candidates",
] as const;
export const MUTATION_TOOLS = [
  "hold_resource",
  "release_hold",
  "apply_plan",
  "check_in",
  "submit_observation",
] as const;
export const CONTROL_TOOLS = ["update_goal", "update_grant"] as const;

export type ReadTool = (typeof READ_TOOLS)[number];
export type MutationTool = (typeof MUTATION_TOOLS)[number];
export type ControlTool = (typeof CONTROL_TOOLS)[number];
export type ToolName = ReadTool | MutationTool | ControlTool;

export type ErrorCode =
  | "AUTH_REQUIRED"
  | "SESSION_INVALID"
  | "EPISODE_CLOSED"
  | "EVENT_MISMATCH"
  | "GRANT_REQUIRED"
  | "GRANT_EXPIRED"
  | "GRANT_REVOKED"
  | "GRANT_MISMATCH"
  | "SCOPE_VIOLATION"
  | "REVIEW_REQUIRED"
  | "INVALID_REQUEST"
  | "UNKNOWN_TOOL"
  | "UNKNOWN_ENTITY"
  | "REVISION_CONFLICT"
  | "GOAL_VERSION_CONFLICT"
  | "IDEMPOTENCY_CONFLICT"
  | "HOLD_EXPIRED"
  | "HOLD_NOT_ACTIVE"
  | "HOLD_CONVERTED"
  | "HOLD_NOT_SUPPORTED"
  | "RESOURCE_CONFLICT"
  | "RESOURCE_UNAVAILABLE"
  | "BUDGET_EXCEEDED"
  | "COMMITMENT_CUTOFF_PASSED"
  | "CONSTRAINT_VIOLATION"
  | "CANDIDATE_NOT_FOUND"
  | "CANDIDATE_STALE"
  | "CANDIDATE_REPORT_MISMATCH"
  | "CANDIDATE_HYPOTHETICAL"
  | "CANDIDATE_NOT_APPLICABLE"
  | "STATUS_UNKNOWN"
  | "STATUS_UNAVAILABLE"
  | "STATUS_SOURCE_NOT_REGISTERED"
  | "INVALID_EVIDENCE_REFERENCE"
  | "DUPLICATE_CHECK_IN"
  | "UNSUPPORTED_ACTION"
  | "EVENT_CLOSED"
  /** The call failed inside the server (HTTP 500); none of its effects were kept. */
  | "INTERNAL_ERROR";

// ---------------------------------------------------------------------------
// Scenario configuration (public parts that appear inside views)
// ---------------------------------------------------------------------------

export interface TimeWindow {
  readonly start: UtcIso;
  readonly end: UtcIso;
}

export interface ResourceTerms {
  readonly booking_required: boolean;
  readonly commitment_cost_cents: number;
  readonly hold_fee_cents: number;
  readonly reserved_exposure_cents: number;
  readonly hold_max_minutes: number | null;
  readonly commitment_cutoff_minutes_before_use: number | null;
  readonly refundable_on_release: boolean;
  readonly cancellation_supported: boolean;
  readonly booking_ref: string | null;
  readonly status_source_id: string | null;
  readonly queryable_facts: readonly string[];
  readonly terms_source_ref: string;
}

export interface ResourceDef {
  readonly resource_id: string;
  readonly label: string;
  readonly kind: ResourceKind;
  readonly capacity: number;
  readonly window: TimeWindow;
  readonly initial_status: ResourceStatus;
  readonly source_ref: string;
  readonly capabilities: readonly string[];
  readonly approved_substitute_ids: readonly string[];
  readonly terms: ResourceTerms;
}

export interface ActivityDef {
  readonly activity_id: string;
  readonly label: string;
  readonly duration_minutes: number;
  readonly window: TimeWindow;
  readonly predecessors: readonly string[];
  readonly required_resources: readonly string[];
  readonly required: boolean;
  readonly program: boolean;
}

export interface ObjectiveWeights {
  readonly start_shift_per_minute: number;
  readonly changed_activity: number;
  readonly spend_per_100_cents: number;
  readonly optional_activity_removed: number;
  readonly participant_notification: number;
}

export interface AccessibilityRequirement {
  readonly requirement_id: string;
  readonly kind: string;
  readonly activity_ids: readonly string[];
  readonly capability: string | null;
  readonly detail: string;
}

export interface EventGoal {
  readonly goal_id: string;
  readonly description: string;
  readonly required_activity_ids: readonly string[];
  readonly public_start: UtcIso;
  readonly hard_end: UtcIso;
  readonly budget_cents: number;
  readonly attendance_target: number;
  readonly fixed_venue_id: string;
  readonly priorities: readonly string[];
  readonly version: number;
  readonly preference_preset: PreferencePreset;
  readonly objective_weights: ObjectiveWeights;
  readonly accessibility_requirements: readonly AccessibilityRequirement[];
  readonly program_concurrency: number;
}

export interface AuthorityGrant {
  readonly grant_id: string;
  readonly event_id: string;
  readonly principal_role: PrincipalRole;
  readonly principal_id: string;
  readonly allowed_tools: readonly string[];
  readonly resource_ids: readonly string[];
  readonly activity_ids: readonly string[];
  readonly max_total_committed_cents: number;
  readonly max_total_reserved_cents: number;
  readonly expires_at: UtcIso;
  readonly review_required_for: readonly string[];
}

export interface Observation {
  readonly observation_id: string;
  readonly event_id: string;
  readonly entity_id: string;
  readonly kind: ObservationKind;
  readonly source_id: string;
  readonly source_record_id: string;
  readonly correlation_group: string;
  readonly observed_at: UtcIso;
  readonly received_at: UtcIso;
  readonly valid_window: TimeWindow;
  readonly authority_scope: AuthorityScope;
  readonly text: string;
  readonly supersedes: readonly string[];
}

export interface Assignment {
  readonly activity_id: string;
  readonly start: UtcIso;
  readonly end: UtcIso;
  readonly resource_ids: readonly string[];
}

export interface PlanningAssumption {
  readonly assumption_id: string;
  readonly description: string;
  readonly basis: "scenario_design" | "operator_input" | "public_source";
  readonly source_ref: string;
}

export interface Hypothesis {
  readonly resource_id: string;
  readonly assume_ready_at: UtcIso | null;
  readonly assume_status: ResourceStatus | null;
  readonly label: string;
}

// ---------------------------------------------------------------------------
// Requests, envelopes and receipts
// ---------------------------------------------------------------------------

/** One request shape for every tool. Identity is never part of the body. */
export interface ToolRequest {
  readonly tool: ToolName;
  readonly event_id: string;
  readonly grant_id?: string | null;
  readonly idempotency_key?: string | null;
  readonly expected_revision?: number | null;
  readonly expected_goal_version?: number | null;
  readonly arguments: JsonObject;
}

export interface GetActionReceiptArgs {
  readonly idempotency_key: string;
  readonly actor_id?: string | null;
}

export interface EvaluateCandidatesArgs {
  readonly templates?: readonly string[] | null;
  readonly hypotheses?: readonly Hypothesis[];
}

export interface CheckInArgs {
  readonly resource_id: string;
  readonly available?: TimeWindow | null;
}

export interface SubmitObservationArgs {
  readonly text: string;
  readonly entity_id?: string | null;
  readonly kind?: "notice" | "resource_offer";
  readonly observed_at?: UtcIso | null;
  readonly client_record_id?: string | null;
  readonly correlation_group?: string | null;
  readonly supersedes?: readonly string[];
}

export interface UpdateGoalArgs {
  readonly preference_preset: PreferencePreset;
  readonly reason: string;
}

export interface UpdateGrantArgs {
  readonly target_grant_id: string;
  readonly max_total_committed_cents?: number | null;
  readonly max_total_reserved_cents?: number | null;
  readonly revoke?: boolean;
  readonly reason: string;
}

export interface ToolError {
  readonly code: ErrorCode;
  readonly message: string;
  readonly details: JsonObject;
}

export interface StateChange {
  readonly entity_id: string;
  readonly field: string;
  readonly before: JsonValue;
  readonly after: JsonValue;
}

export interface ActionReceipt {
  readonly runtime_version: "1.0.0";
  readonly receipt_id: string;
  readonly episode_id: string;
  readonly event_id: string;
  readonly tool: string;
  readonly request_idempotency_key: string;
  readonly request_digest: string;
  readonly grant_id: string;
  readonly grant_version: number;
  readonly actor_id: string;
  readonly actor_role: PrincipalRole;
  readonly status: ReceiptStatus;
  readonly revision_before: number;
  readonly revision_after: number;
  readonly requested_at: UtcIso;
  readonly executed_at: UtcIso;
  readonly simulation: true;
  readonly state_changes: readonly StateChange[];
  readonly committed_delta_cents: number;
  readonly reserved_delta_cents: number;
  readonly related_plan_id: string | null;
  readonly constraint_report_ref: string | null;
  readonly error_code: ErrorCode | null;
  readonly error_message: string | null;
  readonly summary: string;
}

export interface ToolEnvelope {
  readonly runtime_version: "1.0.0";
  readonly call_id: string;
  readonly tool: string;
  readonly status: EnvelopeStatus;
  readonly episode_id: string | null;
  readonly event_id: string | null;
  readonly revision: number | null;
  readonly goal_version: number | null;
  readonly scenario_time: UtcIso | null;
  readonly data: JsonObject | null;
  readonly error: ToolError | null;
  readonly receipt: ActionReceipt | null;
  readonly replayed_receipt: boolean;
}

/** `data` of a succeeded get_action_receipt call. */
export interface ReceiptLookupData {
  readonly lookup_status: "found" | "not_found" | "pending";
  readonly receipt: ActionReceipt | null;
}

/** `data.freshness` of a succeeded query_status call. */
export interface StatusFreshness {
  readonly observed_at: UtcIso;
  readonly retrieved_at: UtcIso;
  readonly age_minutes: number;
  readonly stale: boolean;
}

// ---------------------------------------------------------------------------
// Projections (what callers can see)
// ---------------------------------------------------------------------------

export interface StatusFacts {
  readonly fact: string;
  readonly status_code: string;
  readonly domain_status: ResourceStatus;
  readonly reported_eta: UtcIso | null;
}

export interface ObservationRecord {
  readonly observation: Observation;
  readonly channel: ObservationChannel;
  readonly submitted_by: string | null;
  readonly revision_after: number;
  readonly structured: StatusFacts | null;
}

export interface ActivityLifecycleEvent {
  readonly seq: number;
  readonly activity_id: string;
  readonly state: LifecycleState;
  readonly at: UtcIso;
  readonly revision: number;
  readonly reasons: readonly string[];
  readonly evidence_refs: readonly string[];
}

export interface ReadinessReport {
  readonly activity_id: string;
  readonly at: UtcIso;
  readonly mode: "preview" | "execution";
  readonly ready: boolean;
  readonly met: readonly string[];
  readonly unmet: readonly string[];
  readonly pending: readonly string[];
  readonly evidence_refs: readonly string[];
}

export interface ActivityView {
  readonly definition: ActivityDef;
  readonly lifecycle: LifecycleState;
  readonly history: readonly ActivityLifecycleEvent[];
  readonly assignment: Assignment | null;
  readonly readiness: ReadinessReport | null;
}

export interface OccupancyEntry {
  readonly kind: "plan" | "hold" | "commitment";
  readonly ref: string;
  readonly activity_id: string | null;
  readonly window: TimeWindow;
  readonly quantity: number;
}

export interface ResourceView {
  readonly definition: ResourceDef;
  readonly status: ResourceStatus;
  readonly status_basis: StatusBasis;
  readonly status_observation_id: string | null;
  readonly status_observed_at: UtcIso | null;
  readonly reported_eta: UtcIso | null;
  readonly occupancy: readonly OccupancyEntry[];
}

export interface HoldView {
  readonly hold_id: string;
  readonly resource_id: string;
  readonly activity_id: string;
  readonly quantity: number;
  readonly window: TimeWindow;
  readonly created_at: UtcIso;
  readonly expires_at: UtcIso;
  readonly commitment_cutoff: UtcIso | null;
  readonly reserved_cents: number;
  readonly hold_fee_cents: number;
  readonly status: HoldStatus;
  readonly effective_status: HoldStatus;
  readonly actor_id: string;
  readonly grant_id: string;
  readonly commitment_id: string | null;
  readonly terminal_at: UtcIso | null;
  readonly created_receipt_id: string;
  readonly terminal_receipt_id: string | null;
}

export interface CommitmentView {
  readonly commitment_id: string;
  readonly resource_id: string;
  readonly activity_id: string;
  readonly window: TimeWindow;
  readonly committed_cents: number;
  readonly source_hold_id: string | null;
  readonly plan_version: number;
  readonly status: "active";
  readonly created_at: UtcIso;
  readonly receipt_id: string;
  readonly actor_id: string;
  readonly grant_id: string;
}

export interface CheckInView {
  readonly checkin_id: string;
  readonly principal_id: string | null;
  readonly resource_id: string;
  readonly at: UtcIso;
  readonly available: TimeWindow;
  readonly observation_id: string | null;
  readonly channel: "fixture_initial" | "participant_session";
}

export interface BudgetView {
  readonly budget_cents: number;
  readonly committed_cents: number;
  readonly reserved_cents: number;
  readonly remaining_cents: number;
}

export interface GrantView {
  readonly grant: AuthorityGrant;
  readonly version: number;
  readonly revoked: boolean;
  readonly valid_now: boolean;
  readonly committed_used_cents: number;
  readonly reserved_used_cents: number;
  readonly issued_receipt_id: string | null;
}

export interface PlanView {
  readonly plan_version: number;
  readonly assignments: readonly Assignment[];
  readonly applied_receipt_id: string | null;
  readonly candidate_id: string | null;
  readonly applied_at: UtcIso | null;
}

export interface TransitionView {
  readonly revision: number;
  readonly at: UtcIso;
  readonly cause_kind: string;
  readonly cause_ref: string | null;
  readonly summary: string;
}

export interface StatusSource {
  readonly source_id: string;
  readonly label: string;
  readonly entity_ids: readonly string[];
  readonly facts: readonly string[];
  readonly freshness_minutes: number;
  readonly authority_scope: "resource_status";
}

/** A query_status call as a visible fact, including unknown/unavailable outcomes. */
export interface StatusCheckView {
  readonly call_id: string;
  readonly actor_id: string | null;
  readonly entity_id: string | null;
  readonly fact: string | null;
  readonly requested_at: UtcIso | null;
  readonly completed_at: UtcIso | null;
  readonly envelope_status: EnvelopeStatus;
  readonly error_code: string | null;
  readonly observation_id: string | null;
  readonly deduplicated: boolean;
  readonly stale: boolean | null;
  readonly reason: string | null;
}

export interface AttemptView {
  readonly call_id: string;
  readonly at: UtcIso | null;
  readonly actor_id: string | null;
  readonly tool: string;
  readonly envelope_status: EnvelopeStatus;
  readonly error_code: string | null;
}

export interface ViewerInfo {
  readonly principal_id: string;
  readonly role: SessionRole;
  readonly display_name: string;
  readonly grant_id: string | null;
}

export interface AuthorizationRequest {
  readonly request_id: string;
  readonly target_grant_id: string;
  readonly field: "max_total_committed_cents";
  readonly current_value: number;
  readonly requested_value: number;
  readonly resource_id: string;
  readonly candidate_id: string;
  /** Policy-written explanation, at most 400 characters. */
  readonly reason: string;
}

export type DecisionKind =
  | "keep"
  | "verify"
  | "prepare"
  | "commit"
  | "ask"
  | "infeasible"
  | "wait"
  | "unresolved"
  | "inapplicable"
  | "duplicate"
  | "release"
  | "reconcile"
  | "stop";

/** A policy's recorded decision. Narration only: it is not evidence and not an action. */
export interface PolicyDecision {
  readonly decision_id: string;
  readonly policy_id: string;
  readonly at: UtcIso;
  readonly revision: number;
  readonly kind: DecisionKind;
  readonly summary: string;
  readonly observation_refs: readonly string[];
  readonly tool_call_refs: readonly string[];
  readonly candidate_refs: readonly string[];
  readonly receipt_refs: readonly string[];
  readonly authorization_request: AuthorizationRequest | null;
  readonly wait_until: UtcIso | null;
  readonly details: JsonObject;
}

// ---------------------------------------------------------------------------
// Planner contract
// ---------------------------------------------------------------------------

export interface Edit {
  readonly kind: "keep" | "swap" | "shift" | "substitute" | "alternate_format";
  readonly activity_ids: readonly string[];
  readonly offset_minutes: number | null;
  readonly resource_id: string | null;
  readonly substitute_id: string | null;
  readonly format_id: string | null;
}

export interface CandidateCheck {
  readonly constraint_id: string;
  readonly status: CheckStatus;
  readonly detail: string;
  readonly entity_ids: readonly string[];
}

export interface CandidateAssumption {
  readonly assumption_id: string;
  readonly kind: "arrival_by_start" | "catalog_availability" | "declared_availability" | "hypothesis";
  readonly entity_id: string;
  readonly text: string;
  readonly basis_ref: string | null;
}

export interface ObjectiveComponents {
  readonly start_shift_minutes: number;
  readonly changed_activities: number;
  readonly additional_committed_cents: number;
  readonly optional_activities_removed: number;
  readonly participant_notifications: number;
  readonly weighted: { readonly [term: string]: number };
  readonly total: number;
}

export interface RequiredHold {
  readonly resource_id: string;
  readonly activity_id: string;
  readonly window: TimeWindow;
  readonly bound_hold_id: string | null;
  readonly commitment_cost_cents: number;
  readonly commitment_cutoff: UtcIso | null;
}

export interface MissingPermission {
  readonly kind:
    | "committed_spend_limit"
    | "reserved_spend_limit"
    | "tool_not_granted"
    | "resource_out_of_scope"
    | "activity_out_of_scope"
    | "review_required"
    | "grant_invalid";
  readonly detail: string;
  readonly grant_id: string | null;
  readonly field: string | null;
  readonly current_value: number | null;
  readonly required_value: number | null;
}

export interface AuthorizationAssessment {
  readonly sufficient: boolean;
  readonly missing: readonly MissingPermission[];
}

export interface CandidateResult {
  readonly candidate_id: string;
  readonly report_id: string;
  readonly signature: string;
  readonly label: string;
  readonly edits: readonly Edit[];
  readonly assignments: readonly Assignment[];
  readonly changed_activity_ids: readonly string[];
  readonly incremental_committed_cents: number;
  readonly constraint_status: ConstraintResult;
  readonly checks: readonly CandidateCheck[];
  readonly assumptions: readonly CandidateAssumption[];
  readonly execution_preconditions: readonly string[];
  readonly required_holds: readonly RequiredHold[];
  readonly authorization: AuthorizationAssessment;
  readonly objective: ObjectiveComponents;
  readonly rank: number | null;
  readonly applicable_now: boolean;
  readonly rationale: string;
}

export interface InfeasibilitySummary {
  readonly declared_action_space: string;
  readonly blocking_constraints: readonly string[];
  readonly detail: string;
}

export interface EvaluationResult {
  readonly evaluation_id: string;
  readonly event_id: string;
  readonly revision: number;
  readonly goal_version: number;
  readonly evaluated_at: UtcIso;
  readonly actor_id: string;
  readonly hypothetical: boolean;
  readonly hypotheses: readonly Hypothesis[];
  readonly templates: readonly string[];
  readonly max_combined_edits: number;
  readonly candidate_cap: number;
  readonly generated_count: number;
  readonly evaluated_count: number;
  readonly truncated: boolean;
  readonly candidates: readonly CandidateResult[];
  readonly best_candidate_id: string | null;
  readonly best_applicable_candidate_id: string | null;
  readonly keep_candidate_id: string | null;
  readonly infeasibility: InfeasibilitySummary | null;
}

export interface EventStateView {
  readonly runtime_version: "1.0.0";
  readonly episode_id: string;
  readonly event_id: string;
  readonly scenario_id: string;
  readonly profile_id: string;
  readonly fictional: true;
  readonly sandbox_label: string;
  readonly timezone: string;
  readonly episode_status: "active" | "closed";
  readonly clock: UtcIso;
  readonly revision: number;
  readonly goal: EventGoal;
  readonly goal_history: readonly EventGoal[];
  readonly activities: readonly ActivityView[];
  readonly plan: PlanView;
  readonly plan_history: readonly PlanView[];
  readonly resources: readonly ResourceView[];
  readonly holds: readonly HoldView[];
  readonly commitments: readonly CommitmentView[];
  readonly checkins: readonly CheckInView[];
  readonly budget: BudgetView;
  readonly grants: readonly GrantView[];
  readonly grant_history: readonly GrantView[];
  readonly observations: readonly ObservationRecord[];
  readonly status_sources: readonly StatusSource[];
  readonly status_checks: readonly StatusCheckView[];
  readonly receipts: readonly ActionReceipt[];
  readonly attempts: readonly AttemptView[];
  readonly decisions: readonly PolicyDecision[];
  readonly latest_evaluation: EvaluationResult | null;
  readonly transitions: readonly TransitionView[];
  readonly declared_assumptions: readonly PlanningAssumption[];
  readonly tool_durations_minutes: { readonly [tool: string]: number };
  readonly viewer: ViewerInfo;
}

// ---------------------------------------------------------------------------
// Episode history, policy runs
// ---------------------------------------------------------------------------

export interface ToolCallRecord {
  readonly seq: number;
  readonly call_id: string;
  readonly actor_id: string | null;
  readonly actor_role: string | null;
  readonly tool: string;
  readonly requested_at: UtcIso | null;
  readonly completed_at: UtcIso | null;
  readonly revision_before: number | null;
  readonly revision_after: number | null;
  readonly envelope_status: EnvelopeStatus;
  readonly error_code: string | null;
  readonly receipt_id: string | null;
  readonly request: JsonObject;
  readonly envelope: JsonObject;
}

export interface PolicyRunResult {
  readonly policy_id: string;
  readonly status: "waiting" | "stopped" | "budget_exhausted";
  readonly decisions: readonly PolicyDecision[];
  readonly tool_calls: number;
  readonly wait_until: UtcIso | null;
  readonly note: string;
}

// ---------------------------------------------------------------------------
// HTTP API bodies (contract section 3)
// ---------------------------------------------------------------------------

export interface HealthResponse {
  readonly ok: boolean;
  readonly runtime_version: string;
  readonly mode: string;
}

export interface ModeratorAuthResponse {
  readonly token: string;
  readonly role: "moderator";
  readonly principal_id: string;
  readonly display_name?: string;
  /** Listed by the contract; optional because the server may omit it. */
  readonly expires_wall?: UtcIso;
}

export interface JoinAuthResponse {
  readonly token: string;
  readonly role: SessionRole;
  readonly principal_id: string;
  readonly display_name: string;
  readonly episode_id: string;
  readonly event_id: string;
  readonly grant_id: string;
}

/** `GET /api/auth/whoami`. The contract says only "session info"; every field is optional. */
export interface WhoAmIResponse {
  readonly role?: SessionRole;
  readonly principal_id?: string;
  readonly display_name?: string;
  readonly episode_id?: string | null;
  readonly event_id?: string | null;
  readonly grant_id?: string | null;
  readonly expires_wall?: UtcIso | null;
}

export interface ModeratorCase {
  readonly case_ref: string;
}

export interface ModeratorCurrent {
  readonly episode_id: string | null;
}

export interface IssuedSession {
  readonly join_code: string;
  readonly join_path: string;
  readonly principal_id: string;
  readonly role: SessionRole;
  readonly display_name?: string;
  /** Listed by the contract; optional because the server may omit it. */
  readonly expires_wall?: UtcIso;
}

/** `POST /api/moderator/episodes`. */
export interface LoadedEpisode {
  readonly episode_id: string;
  readonly event_id?: string;
  readonly clock?: UtcIso;
  readonly revision?: number;
}

/** `POST /api/moderator/run`. */
export interface RunMinutesResult {
  readonly clock?: UtcIso;
  readonly revision?: number;
  readonly policy_runs?: readonly PolicyRunResult[];
}

/** `POST /api/moderator/export`: the written trace's name and the trace itself. */
export interface ExportResult {
  readonly name?: string;
  readonly trace?: SanitizedTrace;
}

export interface ClockAdvanceResult {
  readonly clock: UtcIso;
  readonly revision: number;
  readonly transitions: readonly TransitionView[];
}

// ---------------------------------------------------------------------------
// Sanitized trace (contract section 13, trace format 1.0.0)
// ---------------------------------------------------------------------------

export interface TraceSource {
  readonly episode_id: string;
  readonly scenario_id: string;
  readonly profile_id: string;
  readonly public_fixture_sha256: string;
  readonly policy_id: string | null;
  readonly generator: string;
}

/** Frames store latest_evaluation as {evaluation_ref}; see SanitizedTrace.evaluations. */
export interface EvaluationRef {
  readonly evaluation_ref: string;
}

export type CompactedStateView = Omit<EventStateView, "latest_evaluation"> & {
  readonly latest_evaluation: EvaluationResult | EvaluationRef | null;
};

export interface TraceFrame {
  readonly seq: number;
  readonly revision: number;
  readonly scenario_time: UtcIso;
  readonly cause_kind: string;
  readonly cause_ref: string | null;
  readonly summary: string;
  readonly state: CompactedStateView;
}

export interface TraceIntegrity {
  readonly algorithm: "sha256";
  readonly frame_hashes: readonly string[];
  readonly chain_sha256: string;
  readonly content_sha256: string;
}

export interface SanitizedTrace {
  readonly trace_version: string;
  readonly runtime_version: string;
  readonly kind: "plan_b_sanitized_trace";
  readonly mode_label: string;
  readonly source: TraceSource;
  readonly frames: readonly TraceFrame[];
  readonly tool_calls: readonly ToolCallRecord[];
  readonly decisions: readonly PolicyDecision[];
  readonly receipts: readonly ActionReceipt[];
  readonly evaluations: { readonly [evaluationId: string]: EvaluationResult };
  readonly compaction?: string;
  readonly final_state: EventStateView;
  readonly integrity: TraceIntegrity;
}
