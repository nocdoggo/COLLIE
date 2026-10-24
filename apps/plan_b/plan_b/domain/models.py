"""Plan B runtime contract, version ``RUNTIME_VERSION``.

These Pydantic models are the interface between the store, tools, planner, policy, runner,
API and browser. ``docs/RUNTIME_CONTRACT.md`` explains their semantics.

Runtime 1.1.0 (Wave 2) adds optional consumable-stock and service-target fields (pantry
profile): ``EventGoal.service_targets``, ``ResourceDef.consumable_stock``,
``Assignment.consumable_allocations``, expected shipments, typed ``pantry_parameters`` and the
staff-only ``record_stock_receipt`` / ``record_distribution`` tools. It also adds the
structured resource offer (``SubmitObservationArgs.offer``), the ``organizer_goal_update`` actor
script and the per-episode caps recorded in outcome reports. Every addition has a default, so
1.0.0 fixtures, receipts, snapshots and traces still parse unchanged.

Relationship to the planning bundle (``PEEAI_plan/schemas/planning.schema.json`` 0.2.0):
planning objects forbid additional properties, so runtime records are separate models that
*contain* the planning fields and add runtime fields beside them. ``domain/planning_map.py``
projects runtime records back into planning-valid artifacts, and the tests validate those
projections against the planning schema.

All models are strict (unknown fields rejected) and immutable. Timestamps are UTC.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Final, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
    model_validator,
)

from plan_b.domain.timeutil import to_utc

RUNTIME_VERSION: Final = "1.1.0"
TRACE_VERSION: Final = "1.0.0"
# Stored records keep the version they were written with: 1.0.0 data still parses.
RuntimeVersion = Literal["1.0.0", "1.1.0"]
PLANNING_SCHEMA_VERSION: Final = "0.2.0"

UtcDatetime = Annotated[datetime, AfterValidator(to_utc)]


def _minute_aligned(value: datetime) -> datetime:
    if value.second or value.microsecond:
        raise ValueError("scenario times are whole minutes (seconds must be :00)")
    if not 2000 <= value.year <= 2100:
        raise ValueError("scenario times must fall between the years 2000 and 2100")
    return value


# Request arguments: stored scenario times are whole minutes, so reject anything finer.
MinuteDatetime = Annotated[datetime, AfterValidator(to_utc), AfterValidator(_minute_aligned)]
Identifier = Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.:\-]+$")]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# ---------------------------------------------------------------------------
# Shared vocabulary
# ---------------------------------------------------------------------------

ResourceKind = Literal["space", "equipment", "person", "supply"]
ResourceStatus = Literal["available", "expected", "unavailable", "unknown"]
StatusBasis = Literal["catalog", "status_observation", "arrival_observation"]
LifecycleState = Literal["planned", "ready", "started", "completed", "failed", "canceled"]
PrincipalRole = Literal["organizer", "coordinator_agent", "participant"]
SessionRole = Literal["organizer", "coordinator_agent", "participant", "moderator"]
ObservationKind = Literal["notice", "status", "check_in", "resource_offer", "policy"]
AuthorityScope = Literal["self_report", "resource_status", "organizer_instruction", "public_policy"]
ObservationChannel = Literal[
    "fixture_initial",  # authored setup in the public fixture
    "scenario_delivery",  # simulated external message delivered by the scenario at its time
    "status_tool",  # result of a query_status call
    "arrival_record",  # simulated receiving-desk record of a physical arrival
    "participant_session",  # submitted through an authenticated participant session
    "organizer_session",  # submitted through an authenticated organizer session
]
EnvelopeStatus = Literal["succeeded", "rejected", "unknown", "unavailable"]
ReceiptStatus = Literal["applied", "rejected", "unknown"]
# ``fulfilled``: a consumable stock-transfer hold whose whole quantity was handed off.
HoldStatus = Literal["active", "committed", "released", "expired", "fulfilled"]
HoldPurpose = Literal["activity", "stock_transfer"]
ConstraintResult = Literal["feasible_under_assumptions", "infeasible", "unknown"]
CheckStatus = Literal["passed", "failed", "not_applicable", "unsupported"]

READ_TOOLS = (
    "get_event_state",
    "get_action_receipt",
    "list_resources",
    "query_status",
    "evaluate_candidates",
)
# Staff-only physical attestations (runtime 1.1.0). They are mutation tools under the common
# transaction rules, granted only to staff principals and never to a coordinator agent.
STAFF_TOOLS = ("record_stock_receipt", "record_distribution")
MUTATION_TOOLS = (
    "hold_resource",
    "release_hold",
    "apply_plan",
    "check_in",
    "submit_observation",
    *STAFF_TOOLS,
)
# Organizer control operations. They follow the mutation transaction rules but are not
# coordinator-agent tools and appear in no coordinator grant.
CONTROL_TOOLS = ("update_goal", "update_grant")
ALL_TOOLS = READ_TOOLS + MUTATION_TOOLS + CONTROL_TOOLS

ErrorCode = Literal[
    "AUTH_REQUIRED",
    "SESSION_INVALID",
    "EPISODE_CLOSED",
    "EVENT_MISMATCH",
    "GRANT_REQUIRED",
    "GRANT_EXPIRED",
    "GRANT_REVOKED",
    "GRANT_MISMATCH",
    "SCOPE_VIOLATION",
    "REVIEW_REQUIRED",
    "INVALID_REQUEST",
    "UNKNOWN_TOOL",
    "UNKNOWN_ENTITY",
    "REVISION_CONFLICT",
    "GOAL_VERSION_CONFLICT",
    "IDEMPOTENCY_CONFLICT",
    "HOLD_EXPIRED",
    "HOLD_NOT_ACTIVE",
    "HOLD_CONVERTED",
    "HOLD_NOT_SUPPORTED",
    "RESOURCE_CONFLICT",
    "RESOURCE_UNAVAILABLE",
    "BUDGET_EXCEEDED",
    "COMMITMENT_CUTOFF_PASSED",
    "CONSTRAINT_VIOLATION",
    "CANDIDATE_NOT_FOUND",
    "CANDIDATE_STALE",
    "CANDIDATE_REPORT_MISMATCH",
    "CANDIDATE_HYPOTHETICAL",
    "CANDIDATE_NOT_APPLICABLE",
    "STATUS_UNKNOWN",
    "STATUS_UNAVAILABLE",
    "STATUS_SOURCE_NOT_REGISTERED",
    "INVALID_EVIDENCE_REFERENCE",
    "DUPLICATE_CHECK_IN",
    "UNSUPPORTED_ACTION",
    "EVENT_CLOSED",
    "INTERNAL_ERROR",
    # runtime 1.1.0 (consumable stock)
    "DUPLICATE_REFERENCE",
    "INSUFFICIENT_STOCK",
    "UNIT_MISMATCH",
    "THROUGHPUT_EXCEEDED",
    "HANDOFF_WINDOW_CLOSED",
]


# ---------------------------------------------------------------------------
# Scenario configuration (public)
# ---------------------------------------------------------------------------


class TimeWindow(Strict):
    start: UtcDatetime
    end: UtcDatetime

    @model_validator(mode="after")
    def _ordered(self) -> TimeWindow:
        if self.end <= self.start:
            raise ValueError("window end must be after start")
        return self

    def contains(self, other: TimeWindow) -> bool:
        return self.start <= other.start and other.end <= self.end

    def overlaps(self, other: TimeWindow) -> bool:
        # Half-open intervals [start, end): back-to-back windows do not overlap.
        return self.start < other.end and other.start < self.end


def require_minute_window(window: TimeWindow | None) -> None:
    """Request-argument windows must have whole-minute bounds (stored times are whole minutes)."""
    if window is not None:
        _minute_aligned(window.start)
        _minute_aligned(window.end)


class ResourceTerms(Strict):
    """Explicit holding/commitment terms. Planning ``booking_cost_cents`` maps to
    ``commitment_cost_cents``; the other fields are runtime extensions."""

    booking_required: bool
    commitment_cost_cents: int = Field(ge=0)
    hold_fee_cents: int = Field(default=0, ge=0)
    reserved_exposure_cents: int = Field(ge=0)
    hold_max_minutes: int | None = Field(default=None, ge=1)
    commitment_cutoff_minutes_before_use: int | None = Field(default=None, ge=0)
    refundable_on_release: bool = True
    cancellation_supported: bool = False
    booking_ref: str | None = None
    status_source_id: str | None = None
    queryable_facts: tuple[str, ...] = ()
    terms_source_ref: str


# Quantities of consumable stock are whole units: a fractional, negative or string quantity is
# refused rather than coerced.
StockQuantity = Annotated[int, Field(strict=True, ge=1)]


class ConsumableStock(Strict):
    """Planning ConsumableStock, unchanged (integer units).

    On a ``ResourceDef`` it is the stock at load. On a ``ResourceView`` it is the live
    projection: ``on_hand_quantity`` includes reserved, unconsumed units; available is
    ``on_hand - reserved``; ``expected_quantity`` (outstanding expected shipments) is never part
    of on-hand stock."""

    unit: Identifier
    on_hand_quantity: int = Field(ge=0)
    reserved_quantity: int = Field(ge=0)
    distributed_quantity: int = Field(ge=0)
    expected_quantity: int = Field(ge=0)


class ResourceDef(Strict):
    resource_id: Identifier
    label: str
    kind: ResourceKind
    capacity: int = Field(ge=1)
    window: TimeWindow
    initial_status: ResourceStatus
    source_ref: str
    capabilities: tuple[str, ...]
    approved_substitute_ids: tuple[str, ...]
    terms: ResourceTerms
    # Runtime 1.1.0: a consumable pool (kind "supply"). None for reusable resources.
    consumable_stock: ConsumableStock | None = None


class ActivityDef(Strict):
    activity_id: Identifier
    label: str
    duration_minutes: int = Field(ge=1)
    window: TimeWindow
    predecessors: tuple[str, ...]
    required_resources: tuple[str, ...]
    required: bool
    program: bool = True  # participates in main-program exclusivity


class ObjectiveWeights(Strict):
    """Integer weights of the documented ranking cost (see docs/RUNTIME_CONTRACT.md)."""

    start_shift_per_minute: int = Field(ge=0)
    changed_activity: int = Field(ge=0)
    spend_per_100_cents: int = Field(ge=0)
    optional_activity_removed: int = Field(ge=0)
    participant_notification: int = Field(ge=0)


class AccessibilityRequirement(Strict):
    requirement_id: Identifier
    kind: str  # only "venue_capability" is supported in Wave 1; others report "unsupported"
    activity_ids: tuple[str, ...]
    capability: str | None = None
    detail: str


PreferencePreset = Literal["balanced", "preserve_order", "minimize_spend"]


class ServiceTarget(Strict):
    """Planning ServiceTarget, unchanged: a staff-defined quantity of one unit, tied to a
    registered activity and a deadline (inclusive)."""

    target_id: Identifier
    unit: Identifier
    quantity: int = Field(ge=1)
    deadline: UtcDatetime
    activity_id: Identifier


class EventGoal(Strict):
    # Planning EventGoal fields
    goal_id: Identifier
    description: str
    required_activity_ids: tuple[str, ...]
    public_start: UtcDatetime
    hard_end: UtcDatetime
    budget_cents: int = Field(ge=0)
    attendance_target: int = Field(ge=0)
    fixed_venue_id: Identifier
    priorities: tuple[str, ...]
    version: int = Field(ge=1)
    # Runtime extensions
    preference_preset: PreferencePreset
    objective_weights: ObjectiveWeights
    accessibility_requirements: tuple[AccessibilityRequirement, ...] = ()
    program_concurrency: int = Field(default=1, ge=1)
    # Runtime 1.1.0 (planning EventGoal.service_targets): quantity targets. Only distribution
    # recorded by staff on time counts toward them.
    service_targets: tuple[ServiceTarget, ...] = ()


class KeepTemplate(Strict):
    template: Literal["keep"]


class SwapTemplate(Strict):
    template: Literal["swap"]
    activity_ids: tuple[str, str]


class ShiftTemplate(Strict):
    template: Literal["shift"]
    activity_id: str
    offsets_minutes: tuple[int, ...]


class SubstituteTemplate(Strict):
    template: Literal["substitute"]
    activity_id: str
    resource_id: str
    substitute_ids: tuple[str, ...]


class AlternateFormatTemplate(Strict):
    template: Literal["alternate_format"]
    activity_id: str
    format_id: Identifier
    label: str
    duration_minutes: int = Field(ge=1)
    required_resources: tuple[str, ...]


EditTemplate = Annotated[
    KeepTemplate | SwapTemplate | ShiftTemplate | SubstituteTemplate | AlternateFormatTemplate,
    Field(discriminator="template"),
]


class PlanningConfig(Strict):
    edit_templates: tuple[EditTemplate, ...]
    max_combined_edits: int = Field(default=2, ge=1, le=3)
    candidate_cap: int = Field(default=64, ge=1)
    tie_breaks: tuple[str, ...] = (
        "objective_total",
        "changed_activities",
        "additional_committed_cents",
        "candidate_signature",
    )


class Principal(Strict):
    principal_id: Identifier
    role: PrincipalRole
    display_name: str
    speaks_for_resource_ids: tuple[str, ...]
    grant_id: Identifier


class AuthorityGrant(Strict):
    """Planning AuthorityGrant fields, unchanged."""

    grant_id: Identifier
    event_id: Identifier
    principal_role: PrincipalRole
    principal_id: Identifier
    allowed_tools: tuple[str, ...]
    resource_ids: tuple[str, ...]
    activity_ids: tuple[str, ...]
    max_total_committed_cents: int = Field(ge=0)
    max_total_reserved_cents: int = Field(ge=0)
    expires_at: UtcDatetime
    review_required_for: tuple[str, ...]


class StatusSource(Strict):
    source_id: Identifier
    label: str
    entity_ids: tuple[str, ...]
    facts: tuple[str, ...]
    freshness_minutes: int = Field(ge=1)
    authority_scope: Literal["resource_status"] = "resource_status"


class Observation(Strict):
    """Planning Observation fields, unchanged."""

    observation_id: Identifier
    event_id: Identifier
    entity_id: str
    kind: ObservationKind
    source_id: str
    source_record_id: str
    correlation_group: str
    observed_at: UtcDatetime
    received_at: UtcDatetime
    valid_window: TimeWindow
    authority_scope: AuthorityScope
    text: str = Field(min_length=1, max_length=2000)
    supersedes: tuple[str, ...]


class ConsumableAllocation(Strict):
    """Planning ConsumableAllocation, unchanged: demand on one stock pool for one target. The
    quantity is the plan's total claim on that pool for the target over the session, including
    units already distributed from it."""

    resource_id: Identifier
    quantity: int = Field(ge=1)
    service_target_id: Identifier


class Assignment(Strict):
    activity_id: Identifier
    start: UtcDatetime
    end: UtcDatetime
    resource_ids: tuple[str, ...]
    # Runtime 1.1.0: consumable demand of this activity (empty for reusable resources only).
    consumable_allocations: tuple[ConsumableAllocation, ...] = ()

    @property
    def window(self) -> TimeWindow:
        return TimeWindow(start=self.start, end=self.end)


class PlanningAssumption(Strict):
    """Planning Assumption fields, unchanged."""

    assumption_id: Identifier
    description: str
    basis: Literal["scenario_design", "operator_input", "public_source"]
    source_ref: str


class InitialLifecycle(Strict):
    activity_id: Identifier
    state: Literal["started"]
    at: UtcDatetime
    source_ref: str


class InitialCheckIn(Strict):
    principal_id: Identifier | None
    resource_id: Identifier
    at: UtcDatetime
    available: TimeWindow
    source_ref: str


class ServiceProgress(Strict):
    """Planning ServiceProgress, unchanged."""

    target_id: Identifier
    distributed_quantity: int = Field(ge=0)


class ExpectedShipment(Strict):
    """Planning ExpectedShipment, unchanged. Outstanding = ``quantity - received_quantity``;
    only a matched staff-recorded receipt reconciles it."""

    shipment_id: Identifier
    destination_resource_id: Identifier
    quantity: int = Field(ge=1)
    received_quantity: int = Field(ge=0)
    expected_at: UtcDatetime | None
    source_ref: str


class InitialState(Strict):
    event_id: Identifier
    revision: int = Field(ge=0)
    clock: UtcDatetime
    committed_cents: int = Field(ge=0)
    reserved_cents: int = Field(ge=0)
    assignments: tuple[Assignment, ...]
    lifecycle: tuple[InitialLifecycle, ...]
    checked_in: tuple[InitialCheckIn, ...]
    # Runtime 1.1.0 (planning EventState fields)
    service_progress: tuple[ServiceProgress, ...] = ()
    expected_shipments: tuple[ExpectedShipment, ...] = ()


class DerivedFrom(Strict):
    path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    schema_version: str


class FixtureExtension(Strict):
    extension_id: Identifier
    field_path: str
    reason: str


class PantryParameters(Strict):
    """Planning PantryParameters, unchanged: typed service capacity and staff-response timing,
    the same for every policy. ``handoff_window.end`` is the exclusive source cutoff."""

    service_activity_id: Identifier
    staff_resource_id: Identifier
    service_rate_units_per_minute: int = Field(ge=1)
    handoff_duration_minutes: int = Field(ge=1)
    handoff_window: TimeWindow


StockOptionKind = Literal["allocate_stock", "transfer_stock", "await_shipment"]


class StockOption(Strict):
    """One declared option of the consumable candidate menu (runtime extension).

    ``allocate_stock`` allocates the pool's physical stock to the target; ``transfer_stock``
    also counts an alternate pool's units after a staff-recorded handoff into the pool;
    ``await_shipment`` counts the pool's outstanding expected shipments (expected units are not
    stock, so the stock validator always rejects it while they are unreceived)."""

    option: StockOptionKind
    activity_id: Identifier
    service_target_id: Identifier
    resource_id: Identifier
    source_resource_id: Identifier | None = None

    @model_validator(mode="after")
    def _source(self) -> StockOption:
        if (self.option == "transfer_stock") != (self.source_resource_id is not None):
            raise ValueError("source_resource_id is set exactly for a transfer_stock option")
        return self


class PublicScenario(Strict):
    artifact: Literal["plan_b.public_scenario"]
    runtime_version: RuntimeVersion
    scenario_id: Identifier
    profile_id: Literal["campus_showcase", "community_skills_exchange", "pantry_continuity"]
    fictional: Literal[True]
    timezone: Literal["America/New_York"]
    event_id: Identifier
    derived_from: DerivedFrom | None
    goal: EventGoal
    activities: tuple[ActivityDef, ...]
    resources: tuple[ResourceDef, ...]
    initial_state: InitialState
    visible_observations: tuple[Observation, ...]
    principals: tuple[Principal, ...]
    authority_grants: tuple[AuthorityGrant, ...]
    status_sources: tuple[StatusSource, ...]
    planning: PlanningConfig
    tool_durations_minutes: dict[str, int]
    declared_assumptions: tuple[PlanningAssumption, ...]
    fixture_extensions: tuple[FixtureExtension, ...]
    # Runtime 1.1.0 (consumable profiles only)
    pantry_parameters: PantryParameters | None = None
    stock_options: tuple[StockOption, ...] = ()


# ---------------------------------------------------------------------------
# Private runner input (never projected to policy, planner, API, browser or public traces)
# ---------------------------------------------------------------------------


class StatusResponse(Strict):
    status_code: Literal[
        "delayed", "on_schedule", "cancelled", "available", "booked_elsewhere", "arrived"
    ]
    domain_status: ResourceStatus
    reported_eta: UtcDatetime | None
    source_record_id: str
    observed_at: UtcDatetime
    text: str
    # The evidence lineage the record belongs to, e.g. the delivery whose notices and arrival
    # share it. The observation created from the record carries it; None means
    # "<entity_id>_status".
    correlation_group: Identifier | None = None
    # Runtime 1.1.0: the record reports an expected shipment to this (consumable) resource. Its
    # ETA updates that shipment's reported ETA; it never moves the stock's status or quantity.
    shipment_id: Identifier | None = None


class StatusRecord(Strict):
    """What the registered status source would answer from ``available_from`` onward."""

    entity_id: str
    fact: str
    available_from: UtcDatetime
    outcome: Literal["ok", "unknown", "unavailable"]
    response: StatusResponse | None = None


class WorldEvent(Strict):
    """A timed exogenous change, visible only when the scenario clock reaches ``at``."""

    at: UtcDatetime
    kind: Literal["resource_arrival", "message_delivery"]
    entity_id: str
    observation_kind: ObservationKind
    source_id: str
    source_record_id: str
    correlation_group: str
    observed_at: UtcDatetime
    authority_scope: AuthorityScope
    text: str
    new_status: ResourceStatus | None = None
    supersedes: tuple[str, ...] = ()


class ParticipantCheckInScript(Strict):
    kind: Literal["participant_check_in"]
    at: UtcDatetime
    principal_id: Identifier
    resource_id: Identifier
    available_start: UtcDatetime
    available_end: UtcDatetime


class ParticipantObservationScript(Strict):
    kind: Literal["participant_observation"]
    at: UtcDatetime
    principal_id: Identifier
    entity_id: str | None
    text: str
    client_record_id: str


class OrganizerAuthorizationRule(Strict):
    """Simulated organizer: answers an open authorization request from the policy's decision
    log after ``latency_minutes`` if the request is within these bounds."""

    kind: Literal["organizer_authorization_rule"]
    principal_id: Identifier
    target_grant_id: Identifier
    latency_minutes: int = Field(ge=0)
    max_committed_cents: int = Field(ge=0)
    resource_ids: tuple[str, ...]


class OrganizerGoalUpdateScript(Strict):
    """Simulated organizer: at ``at`` changes the goal's preference preset with
    ``update_goal`` through its own session, citing ``expected_goal_version`` and the revision
    current at that instant."""

    kind: Literal["organizer_goal_update"]
    at: UtcDatetime
    principal_id: Identifier
    preference_preset: PreferencePreset
    expected_goal_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=500)


class StaffHandoffRule(Strict):
    """Labeled staff simulator (runtime 1.1.0): answers each valid ``stock_transfer`` hold from
    ``source_resource_id`` into ``destination_resource_id`` with one ``record_stock_receipt``,
    ``pantry_parameters.handoff_duration_minutes`` after the hold was created, while the hold,
    the handoff window and the staff grant are valid. It confirms the hold's remaining quantity
    and cites ``source_observation_id``. ``max_quantity`` caps the units this staff confirms from
    the source over the whole episode (a partial handoff that a repeated request cannot top
    up)."""

    kind: Literal["staff_handoff_rule"]
    principal_id: Identifier
    source_resource_id: Identifier
    destination_resource_id: Identifier
    source_observation_id: Identifier
    receipt_reference_prefix: Identifier
    max_quantity: int | None = Field(default=None, ge=1)
    label: str


class StaffDistributionRule(Strict):
    """Labeled staff simulator (runtime 1.1.0): at ``at`` records one aggregate
    ``record_distribution`` for the target. The quantity is decided from the visible state at
    that instant: min(committed undistributed stock, target - distributed, accrued service
    capacity - distributed). Nothing is recorded when that is zero."""

    kind: Literal["staff_distribution_rule"]
    principal_id: Identifier
    at: UtcDatetime
    service_target_id: Identifier
    distribution_reference: Identifier
    label: str


ActorScript = Annotated[
    ParticipantCheckInScript
    | ParticipantObservationScript
    | OrganizerAuthorizationRule
    | OrganizerGoalUpdateScript
    | StaffHandoffRule
    | StaffDistributionRule,
    Field(discriminator="kind"),
]


class OutcomePredicate(Strict):
    predicate_id: Identifier
    kind: Literal[
        "all_required_completed_by_deadline",
        "activity_started_at",
        "activity_not_completed",
        "no_equipment_start_before_arrival",
        "no_executed_violations",
        "committed_within_limits",
        "committed_spend_equals",
        "applied_plan_count",
        "infeasibility_reported",
        # runtime 1.1.0 (consumable stock and service)
        "service_on_time_equals",
        "service_unfulfilled_equals",
        "stock_on_hand_equals",
        "expected_unreceived_equals",
        "stock_conserved",
        "no_staff_attestation_by_agent",
    ]
    params: dict[str, Any] = Field(default_factory=dict)
    description: str


class PrivateCase(Strict):
    artifact: Literal["plan_b.private_case"]
    runtime_version: RuntimeVersion
    case_ref: Identifier
    scenario_id: Identifier
    never_expose_to_agent: Literal[True]
    planning_label: str
    description: str
    derived_from: DerivedFrom | None
    status_model: tuple[StatusRecord, ...]
    world_events: tuple[WorldEvent, ...]
    actor_scripts: tuple[ActorScript, ...]
    outcome_predicates: tuple[OutcomePredicate, ...]
    expected_outcome: Literal["goal_complete", "goal_not_complete_infeasibility_reported"]


# ---------------------------------------------------------------------------
# Requests, envelopes and receipts
# ---------------------------------------------------------------------------


class ToolRequest(Strict):
    """One request shape for every tool. Identity is never part of the body: the actor,
    role and grant come from the server-validated session. ``grant_id`` must equal the
    session's bound grant. Mutations require ``idempotency_key``; see the contract table for
    which tools require ``expected_revision`` / ``expected_goal_version``."""

    tool: str
    event_id: Identifier
    grant_id: Identifier | None = None
    idempotency_key: Identifier | None = None
    expected_revision: int | None = Field(default=None, ge=0)
    expected_goal_version: int | None = Field(default=None, ge=1)
    arguments: dict[str, Any] = Field(default_factory=dict)


class GetEventStateArgs(Strict):
    view: Literal["full"] = "full"


class GetActionReceiptArgs(Strict):
    idempotency_key: Identifier
    actor_id: Identifier | None = None  # another actor's receipt: organizer review authority only


class ListResourcesArgs(Strict):
    capability: str | None = None
    window: TimeWindow | None = None

    @model_validator(mode="after")
    def _minutes(self) -> ListResourcesArgs:
        require_minute_window(self.window)
        return self


class QueryStatusArgs(Strict):
    entity_id: Identifier
    fact: Identifier


class Hypothesis(Strict):
    """What-if input for robustness checks. Evaluations with hypotheses are stored as
    hypothetical and can never be applied."""

    resource_id: Identifier
    assume_ready_at: MinuteDatetime | None = None
    assume_status: ResourceStatus | None = None
    label: str


TemplateName = Literal[
    "keep",
    "swap",
    "shift",
    "substitute",
    "alternate_format",
    # runtime 1.1.0: declared stock options (``PublicScenario.stock_options``)
    "allocate_stock",
    "transfer_stock",
    "await_shipment",
]


class EvaluateCandidatesArgs(Strict):
    templates: tuple[TemplateName, ...] | None = None
    hypotheses: tuple[Hypothesis, ...] = ()


class HoldResourceArgs(Strict):
    resource_id: Identifier
    activity_id: Identifier
    window: TimeWindow
    # Whole units: a fractional or string quantity is refused, not coerced (runtime 1.1.0).
    quantity: int = Field(default=1, ge=1, strict=True)
    hold_minutes: int | None = Field(default=None, ge=1)
    # Runtime 1.1.0, consumable resources only. ``stock_transfer`` reserves an alternate pool's
    # units for a staff handoff into ``destination_resource_id`` (a local staff task); an
    # ``activity`` hold reserves the pool's own units for ``service_target_id``.
    purpose: HoldPurpose = "activity"
    destination_resource_id: Identifier | None = None
    service_target_id: Identifier | None = None

    @model_validator(mode="after")
    def _minutes(self) -> HoldResourceArgs:
        require_minute_window(self.window)
        if (self.purpose == "stock_transfer") != (self.destination_resource_id is not None):
            raise ValueError("destination_resource_id is set exactly for a stock_transfer hold")
        return self

    @model_serializer(mode="wrap")
    def _without_stock_defaults(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        """A hold on a reusable resource serializes exactly as in runtime 1.0.0: the consumable
        fields appear only when set, so its request body, logged arguments and idempotency key
        are unchanged."""
        data: dict[str, Any] = handler(self)
        if self.purpose == "activity":
            data.pop("purpose", None)
        for name in ("destination_resource_id", "service_target_id"):
            if getattr(self, name) is None:
                data.pop(name, None)
        return data


class ReleaseHoldArgs(Strict):
    hold_id: Identifier
    reason: str = Field(min_length=1, max_length=500)


class ApplyPlanArgs(Strict):
    candidate_plan_id: Identifier
    constraint_report_ref: Identifier


class CheckInArgs(Strict):
    resource_id: Identifier
    available: TimeWindow | None = None

    @model_validator(mode="after")
    def _minutes(self) -> CheckInArgs:
        require_minute_window(self.available)
        return self


class ResourceOffer(Strict):
    """The structured part of a resource offer (runtime 1.1.0): the registered resource's owner
    states the interval it is offered for, the capabilities it provides and the registered terms
    it confirms. The natural-language text stays data; only these fields are checked, and an
    offer that passes activates the preconfigured resource's availability and nothing else."""

    available: TimeWindow
    capabilities: tuple[Identifier, ...] = Field(min_length=1)
    terms_ref: str = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def _minutes(self) -> ResourceOffer:
        require_minute_window(self.available)
        return self


class SubmitObservationArgs(Strict):
    text: str = Field(min_length=1, max_length=1000)
    entity_id: Identifier | None = None
    kind: Literal["notice", "resource_offer"] = "notice"
    observed_at: MinuteDatetime | None = None
    client_record_id: Identifier | None = None
    correlation_group: Identifier | None = None
    supersedes: tuple[Identifier, ...] = ()
    # Runtime 1.1.0: a structured offer that may activate the resource ``entity_id`` names.
    # Without it a ``resource_offer`` is an unverified proposal that activates nothing.
    offer: ResourceOffer | None = None

    @model_validator(mode="after")
    def _offer_shape(self) -> SubmitObservationArgs:
        if self.offer is not None and (self.kind != "resource_offer" or self.entity_id is None):
            raise ValueError("a structured offer needs kind resource_offer and the entity_id")
        if self.offer is not None and self.observed_at is not None:
            raise ValueError("an offer is observed when it is submitted; omit observed_at")
        return self

    @model_serializer(mode="wrap")
    def _without_offer_default(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        """An observation without an offer serializes exactly as in runtime 1.0.0, so its
        logged arguments are unchanged."""
        data: dict[str, Any] = handler(self)
        if self.offer is None:
            data.pop("offer", None)
        return data


class RecordStockReceiptArgs(Strict):
    """Staff attestation of a physical receipt into ``resource_id`` (runtime 1.1.0).

    Either a registered internal handoff (``source_resource_id`` and the matching
    ``source_hold_id``) or a matched external receipt (``shipment_id``), never both.
    ``receipt_reference`` is the physical record's identity: unique per event, whatever the
    request's idempotency key."""

    resource_id: Identifier
    quantity: StockQuantity
    unit: Identifier
    source_observation_id: Identifier
    receipt_reference: Identifier
    source_resource_id: Identifier | None = None
    source_hold_id: Identifier | None = None
    shipment_id: Identifier | None = None

    @model_validator(mode="after")
    def _one_source(self) -> RecordStockReceiptArgs:
        internal = self.source_resource_id is not None or self.source_hold_id is not None
        if internal and (self.source_resource_id is None or self.source_hold_id is None):
            raise ValueError("an internal handoff names both source_resource_id and source_hold_id")
        if internal == (self.shipment_id is not None):
            raise ValueError("name either an internal handoff source or a shipment_id")
        return self


class RecordDistributionArgs(Strict):
    """Staff attestation of an aggregate, completed distribution (runtime 1.1.0). It consumes
    committed, reserved stock (``allocation_ids``) of ``resource_id`` for one target.
    ``distribution_reference`` is unique per event, whatever the idempotency key."""

    resource_id: Identifier
    quantity: StockQuantity
    unit: Identifier
    service_target_id: Identifier
    activity_id: Identifier
    distribution_reference: Identifier
    allocation_ids: tuple[Identifier, ...] = Field(min_length=1)


class UpdateGoalArgs(Strict):
    preference_preset: PreferencePreset
    reason: str = Field(min_length=1, max_length=500)


class UpdateGrantArgs(Strict):
    target_grant_id: Identifier
    max_total_committed_cents: int | None = Field(default=None, ge=0)
    max_total_reserved_cents: int | None = Field(default=None, ge=0)
    revoke: bool = False
    reason: str = Field(min_length=1, max_length=500)


TOOL_ARGUMENT_MODELS: dict[str, type[Strict]] = {
    "get_event_state": GetEventStateArgs,
    "get_action_receipt": GetActionReceiptArgs,
    "list_resources": ListResourcesArgs,
    "query_status": QueryStatusArgs,
    "evaluate_candidates": EvaluateCandidatesArgs,
    "hold_resource": HoldResourceArgs,
    "release_hold": ReleaseHoldArgs,
    "apply_plan": ApplyPlanArgs,
    "check_in": CheckInArgs,
    "submit_observation": SubmitObservationArgs,
    "update_goal": UpdateGoalArgs,
    "update_grant": UpdateGrantArgs,
    "record_stock_receipt": RecordStockReceiptArgs,
    "record_distribution": RecordDistributionArgs,
}

# Which envelope fields each tool requires. "optional" fields are checked when supplied.
TOOL_REQUIREMENTS: dict[str, dict[str, str]] = {
    "get_event_state": {},
    "get_action_receipt": {},
    "list_resources": {},
    "query_status": {},
    "evaluate_candidates": {"expected_goal_version": "optional"},
    "hold_resource": {"idempotency_key": "required", "expected_revision": "required"},
    "release_hold": {"idempotency_key": "required", "expected_revision": "required"},
    "apply_plan": {
        "idempotency_key": "required",
        "expected_revision": "required",
        "expected_goal_version": "required",
    },
    "check_in": {"idempotency_key": "required", "expected_revision": "optional"},
    "submit_observation": {"idempotency_key": "required", "expected_revision": "optional"},
    "update_goal": {
        "idempotency_key": "required",
        "expected_revision": "required",
        "expected_goal_version": "required",
    },
    "update_grant": {"idempotency_key": "required", "expected_revision": "required"},
    "record_stock_receipt": {"idempotency_key": "required", "expected_revision": "required"},
    "record_distribution": {
        "idempotency_key": "required",
        "expected_revision": "required",
        "expected_goal_version": "required",
    },
}


class ToolError(Strict):
    code: ErrorCode
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class StateChange(Strict):
    entity_id: str
    field: str
    before: Any
    after: Any


class ActionReceipt(Strict):
    runtime_version: RuntimeVersion
    receipt_id: Identifier
    episode_id: Identifier
    event_id: Identifier
    tool: str
    request_idempotency_key: Identifier
    request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    grant_id: Identifier
    grant_version: int = Field(ge=1)
    actor_id: Identifier
    actor_role: PrincipalRole
    status: ReceiptStatus
    revision_before: int = Field(ge=0)
    revision_after: int = Field(ge=0)
    requested_at: UtcDatetime
    executed_at: UtcDatetime
    simulation: Literal[True]
    state_changes: tuple[StateChange, ...]
    committed_delta_cents: int
    reserved_delta_cents: int
    related_plan_id: str | None
    constraint_report_ref: str | None
    error_code: ErrorCode | None
    error_message: str | None
    summary: str

    @model_validator(mode="after")
    def _consistent(self) -> ActionReceipt:
        if self.status == "applied" and self.error_code is not None:
            raise ValueError("applied receipts carry no error code")
        if self.status == "rejected":
            if self.error_code is None:
                raise ValueError("rejected receipts carry an error code")
            if self.state_changes or self.committed_delta_cents or self.reserved_delta_cents:
                raise ValueError("rejected receipts carry no state changes or deltas")
            if self.revision_after != self.revision_before:
                raise ValueError("a rejected action does not advance the revision")
        return self


class ToolEnvelope(Strict):
    runtime_version: RuntimeVersion
    call_id: Identifier
    tool: str
    status: EnvelopeStatus
    episode_id: str | None
    event_id: str | None
    revision: int | None
    goal_version: int | None
    scenario_time: UtcDatetime | None
    data: dict[str, Any] | None = None
    error: ToolError | None = None
    receipt: ActionReceipt | None = None
    replayed_receipt: bool = False  # an identical completed request's original receipt


# ---------------------------------------------------------------------------
# Projections (what callers can see)
# ---------------------------------------------------------------------------


class StatusFacts(Strict):
    fact: str
    status_code: str
    domain_status: ResourceStatus
    reported_eta: UtcDatetime | None
    # Runtime 1.1.0: the facts concern this expected shipment, not the resource's own status.
    shipment_id: str | None = None


class ObservationRecord(Strict):
    observation: Observation
    channel: ObservationChannel
    submitted_by: str | None
    revision_after: int
    structured: StatusFacts | None = None


class ActivityLifecycleEvent(Strict):
    seq: int
    activity_id: str
    state: LifecycleState
    at: UtcDatetime
    revision: int
    reasons: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()


class ReadinessReport(Strict):
    """``mode='execution'`` is the strict check at the scheduled start. ``mode='preview'``
    reports current evidence for a future start: predecessor completions that are still due
    by schedule are ``pending`` (not unmet) and program exclusivity is evaluated only at
    execution. ``ready`` is true when nothing is unmet; pending items may remain in preview."""

    activity_id: str
    at: UtcDatetime
    mode: Literal["preview", "execution"]
    ready: bool
    met: tuple[str, ...]
    unmet: tuple[str, ...]
    pending: tuple[str, ...]
    evidence_refs: tuple[str, ...]


class ActivityView(Strict):
    definition: ActivityDef
    lifecycle: LifecycleState
    history: tuple[ActivityLifecycleEvent, ...]
    assignment: Assignment | None
    readiness: ReadinessReport | None  # current readiness for not-yet-started activities


class OccupancyEntry(Strict):
    kind: Literal["plan", "hold", "commitment"]
    ref: str
    activity_id: str | None
    window: TimeWindow
    quantity: int


class ResourceView(Strict):
    definition: ResourceDef
    status: ResourceStatus
    status_basis: StatusBasis
    status_observation_id: str | None
    status_observed_at: UtcDatetime | None
    reported_eta: UtcDatetime | None
    occupancy: tuple[OccupancyEntry, ...]
    # Runtime 1.1.0: live stock of a consumable pool (None for reusable resources).
    consumable_stock: ConsumableStock | None = None


class HoldView(Strict):
    hold_id: str
    resource_id: str
    activity_id: str
    quantity: int
    window: TimeWindow
    created_at: UtcDatetime
    expires_at: UtcDatetime
    commitment_cutoff: UtcDatetime | None
    reserved_cents: int
    hold_fee_cents: int
    status: HoldStatus  # stored status
    effective_status: HoldStatus  # evaluated against the scenario clock
    actor_id: str
    grant_id: str
    commitment_id: str | None
    terminal_at: UtcDatetime | None
    created_receipt_id: str
    terminal_receipt_id: str | None
    # Runtime 1.1.0 (consumable holds). ``remaining_quantity`` is the live claim: a partial
    # handoff lowers it, and only a live (active) remainder reserves stock.
    consumable: bool = False
    remaining_quantity: int | None = None
    purpose: HoldPurpose = "activity"
    destination_resource_id: str | None = None
    service_target_id: str | None = None


class CommitmentView(Strict):
    commitment_id: str
    resource_id: str
    activity_id: str
    window: TimeWindow
    committed_cents: int
    source_hold_id: str | None
    plan_version: int
    status: Literal["active"]
    created_at: UtcDatetime
    receipt_id: str
    actor_id: str
    grant_id: str


class CheckInView(Strict):
    checkin_id: str
    principal_id: str | None
    resource_id: str
    at: UtcDatetime
    available: TimeWindow
    observation_id: str | None
    channel: Literal["fixture_initial", "participant_session"]


class BudgetView(Strict):
    budget_cents: int
    committed_cents: int
    reserved_cents: int
    remaining_cents: int


class GrantView(Strict):
    grant: AuthorityGrant
    version: int
    revoked: bool
    valid_now: bool
    committed_used_cents: int
    reserved_used_cents: int
    issued_receipt_id: str | None


class PlanView(Strict):
    plan_version: int
    assignments: tuple[Assignment, ...]
    applied_receipt_id: str | None
    candidate_id: str | None
    applied_at: UtcDatetime | None


class TransitionView(Strict):
    revision: int
    at: UtcDatetime
    cause_kind: str
    cause_ref: str | None
    summary: str


# ---------------------------------------------------------------------------
# Consumable stock and service projections (runtime 1.1.0)
# ---------------------------------------------------------------------------

StockMovementKind = Literal["opening", "receipt", "transfer_out", "distribution"]


class StockBalanceView(Strict):
    """One pool's balance and its conservation terms:
    ``on_hand = opening + received - transferred_out - distributed``. Reserved stock is the
    live hold remainders plus the undistributed committed allocations (disjoint parts)."""

    resource_id: str
    unit: str
    opening_quantity: int
    received_quantity: int
    transferred_out_quantity: int
    distributed_quantity: int
    on_hand_quantity: int
    held_quantity: int
    committed_quantity: int
    reserved_quantity: int
    available_quantity: int
    expected_quantity: int
    conserved: bool


class StockMovementView(Strict):
    """Append-only stock ledger row. ``delta`` is the signed change of the pool's on-hand."""

    seq: int
    at: UtcDatetime
    resource_id: str
    kind: StockMovementKind
    quantity: int
    delta: int
    counterpart_resource_id: str | None
    reference: str | None
    hold_id: str | None
    shipment_id: str | None
    receipt_id: str | None
    revision: int


class StockReceiptView(Strict):
    stock_receipt_id: str
    receipt_reference: str
    kind: Literal["internal_handoff", "external_shipment"]
    resource_id: str
    source_resource_id: str | None
    source_hold_id: str | None
    shipment_id: str | None
    quantity: int
    unit: str
    source_observation_id: str
    at: UtcDatetime
    actor_id: str
    receipt_id: str
    revision: int


class DistributionView(Strict):
    distribution_id: str
    distribution_reference: str
    resource_id: str
    service_target_id: str
    activity_id: str
    quantity: int
    unit: str
    goal_version: int
    allocation_ids: tuple[str, ...]
    at: UtcDatetime
    on_time: bool  # completed no later than the target's deadline (inclusive)
    actor_id: str
    receipt_id: str
    revision: int


class StockAllocationView(Strict):
    """A committed consumable allocation, created by ``apply_plan`` from a hold."""

    allocation_id: str
    resource_id: str
    service_target_id: str
    activity_id: str
    quantity: int
    remaining_quantity: int  # committed, reserved and not yet distributed
    source_hold_id: str
    plan_version: int
    created_at: UtcDatetime
    receipt_id: str
    actor_id: str
    grant_id: str


class ExpectedShipmentView(Strict):
    shipment: ExpectedShipment  # planning shape; received_quantity is the reconciled amount
    outstanding_quantity: int
    reported_eta: UtcDatetime | None  # latest typed shipment status, if any was queried
    status_observation_id: str | None


class ServiceProgressView(Strict):
    """Service accounting for one target. The two counters stay separate:
    ``supply_gap_quantity = max(remaining target - pantry-controlled on hand, 0)`` with the
    remaining target measured after every distribution so far, and
    ``unfulfilled_quantity = original target - distributed on time``. Reservations, plan
    commitments and receipts never change ``unfulfilled_quantity``."""

    target_id: str
    unit: str
    activity_id: str
    deadline: UtcDatetime
    target_quantity: int  # the current goal version's target
    original_quantity: int  # the first goal version's target (attainment is scored on it)
    distributed_quantity: int  # cumulative, on time and late
    on_time_quantity: int
    late_quantity: int
    committed_quantity: int  # committed allocations not yet distributed
    supply_gap_quantity: int
    unfulfilled_quantity: int
    qualified_minutes: int  # staffed service minutes with committed stock, up to the clock
    capacity_quantity: int  # rate * qualified minutes - distributed (never negative)
    attained: bool


HandoffTaskStatus = Literal["open", "fulfilled", "partially_fulfilled", "lapsed"]


class HandoffTaskView(Strict):
    """The local staff task a live ``stock_transfer`` hold creates."""

    hold_id: str
    source_resource_id: str
    destination_resource_id: str
    requested_quantity: int
    remaining_quantity: int
    requested_at: UtcDatetime
    respond_after: UtcDatetime  # requested_at + the modeled staff response latency
    cutoff: UtcDatetime  # min(hold expiry, handoff window end); exclusive
    status: HandoffTaskStatus
    stock_receipt_ids: tuple[str, ...]


class ConsumableStateView(Strict):
    balances: tuple[StockBalanceView, ...]
    expected_shipments: tuple[ExpectedShipmentView, ...]
    service: tuple[ServiceProgressView, ...]
    allocations: tuple[StockAllocationView, ...]
    movements: tuple[StockMovementView, ...]
    receipts: tuple[StockReceiptView, ...]
    distributions: tuple[DistributionView, ...]
    handoff_tasks: tuple[HandoffTaskView, ...]


class AttemptView(Strict):
    """Tool calls that ended without a durable receipt (authentication, scope or validation
    failures). Kept as rejected-attempt evidence."""

    call_id: str
    at: UtcDatetime | None
    actor_id: str | None
    tool: str
    envelope_status: EnvelopeStatus
    error_code: str | None


class StatusCheckView(Strict):
    """A query_status call as visible fact: who asked what, when, and what came back
    (including unknown and unavailable outcomes, which ingest no observation)."""

    call_id: str
    actor_id: str | None
    entity_id: str | None
    fact: str | None
    requested_at: UtcDatetime | None
    completed_at: UtcDatetime | None
    envelope_status: EnvelopeStatus
    error_code: str | None
    observation_id: str | None
    deduplicated: bool
    stale: bool | None
    reason: str | None


class ViewerInfo(Strict):
    principal_id: str
    role: SessionRole
    display_name: str
    grant_id: str | None


class AuthorizationRequest(Strict):
    request_id: str
    target_grant_id: str
    field: Literal["max_total_committed_cents"]
    current_value: int
    requested_value: int
    resource_id: str
    candidate_id: str
    reason: str = Field(max_length=400)


DecisionKind = Literal[
    "keep",
    "verify",
    "prepare",
    "commit",
    "ask",
    "infeasible",
    "wait",
    "unresolved",
    "inapplicable",
    "duplicate",
    "release",
    "reconcile",
    "stop",
]


class PolicyDecision(Strict):
    """A policy's recorded decision. Narration only: it is not evidence and not an action."""

    decision_id: str
    policy_id: str
    at: UtcDatetime
    revision: int
    kind: DecisionKind
    summary: str
    observation_refs: tuple[str, ...] = ()
    tool_call_refs: tuple[str, ...] = ()
    candidate_refs: tuple[str, ...] = ()
    receipt_refs: tuple[str, ...] = ()
    authorization_request: AuthorizationRequest | None = None
    wait_until: UtcDatetime | None = None
    details: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Planner contract
# ---------------------------------------------------------------------------


class Edit(Strict):
    # Stock edits (runtime 1.1.0): ``allocate_stock`` / ``await_shipment`` name the pool in
    # ``resource_id``; ``transfer_stock`` names the pool in ``resource_id`` and the alternate
    # pool whose units stand in for its shortfall in ``substitute_id``.
    kind: Literal[
        "keep",
        "swap",
        "shift",
        "substitute",
        "alternate_format",
        "allocate_stock",
        "transfer_stock",
        "await_shipment",
    ]
    activity_ids: tuple[str, ...] = ()
    offset_minutes: int | None = None
    resource_id: str | None = None
    substitute_id: str | None = None
    format_id: str | None = None


class CandidateCheck(Strict):
    constraint_id: str
    status: CheckStatus
    detail: str
    entity_ids: tuple[str, ...] = ()


class CandidateAssumption(Strict):
    assumption_id: str
    kind: Literal[
        "arrival_by_start",
        "catalog_availability",
        "declared_availability",
        "hypothesis",
        # runtime 1.1.0: alternate units counted only after a staff-recorded handoff
        "stock_handoff",
    ]
    entity_id: str
    text: str
    basis_ref: str | None  # observation id, catalog source ref, or hypothesis label


class ObjectiveComponents(Strict):
    start_shift_minutes: int
    changed_activities: int
    additional_committed_cents: int
    optional_activities_removed: int
    participant_notifications: int
    weighted: dict[str, int]
    total: int


class RequiredHold(Strict):
    resource_id: str
    activity_id: str
    window: TimeWindow
    bound_hold_id: str | None  # a live hold by this actor that covers the window, if any
    commitment_cost_cents: int
    commitment_cutoff: UtcDatetime | None


class MissingPermission(Strict):
    kind: Literal[
        "committed_spend_limit",
        "reserved_spend_limit",
        "tool_not_granted",
        "resource_out_of_scope",
        "activity_out_of_scope",
        "review_required",
        "grant_invalid",
    ]
    detail: str
    grant_id: str | None
    field: str | None = None
    current_value: int | None = None
    required_value: int | None = None


class AuthorizationAssessment(Strict):
    sufficient: bool
    missing: tuple[MissingPermission, ...]


class RequiredStockHold(Strict):
    """Consumable units a candidate still has to claim before ``apply_plan``: live activity
    holds by this actor on the pool, for the activity and target, whose remaining quantities
    sum exactly to ``quantity``. ``apply_plan`` converts them into committed allocations."""

    resource_id: str
    activity_id: str
    service_target_id: str
    quantity: int
    held_quantity: int  # the actor's live matching hold remainders
    bound_hold_ids: tuple[str, ...]  # empty unless held_quantity == quantity


class StockTransferNeed(Strict):
    """Units an alternate pool must hand off (a staff-recorded ``record_stock_receipt``) before
    a transfer candidate can be feasible. A live ``stock_transfer`` hold reserves them."""

    source_resource_id: str
    destination_resource_id: str
    activity_id: str
    service_target_id: str
    quantity: int
    held_quantity: int
    bound_hold_ids: tuple[str, ...]
    handoff_cutoff: UtcDatetime | None


class ServiceCoverage(Strict):
    """What a candidate would leave of a target. ``allocated`` counts units already distributed;
    ``on_time`` is the part staff can distribute by the deadline at the declared rate (late
    units can still be distributed, truthfully, but do not count);
    ``unfulfilled = target - on_time``. A coverage gap is not a hard-check failure; the
    objective weighs it."""

    target_id: str
    target_quantity: int
    distributed_quantity: int
    allocated_quantity: int
    on_time_quantity: int
    unfulfilled_quantity: int


class CandidateResult(Strict):
    candidate_id: str  # unique per evaluation
    report_id: str  # unique per evaluation
    signature: str  # sha256 of the canonical edit list; equal edits share a signature
    label: str
    edits: tuple[Edit, ...]
    assignments: tuple[Assignment, ...]
    changed_activity_ids: tuple[str, ...]
    incremental_committed_cents: int
    constraint_status: ConstraintResult
    checks: tuple[CandidateCheck, ...]
    assumptions: tuple[CandidateAssumption, ...]
    execution_preconditions: tuple[str, ...]
    required_holds: tuple[RequiredHold, ...]
    authorization: AuthorizationAssessment
    objective: ObjectiveComponents
    rank: int | None  # 1-based rank among constraint-feasible candidates
    applicable_now: bool  # feasible, authorized, every required hold bound, not hypothetical
    rationale: str
    # Runtime 1.1.0 (consumable profiles; empty otherwise)
    required_stock_holds: tuple[RequiredStockHold, ...] = ()
    stock_transfers: tuple[StockTransferNeed, ...] = ()
    service_coverage: tuple[ServiceCoverage, ...] = ()


class EvaluationRequest(Strict):
    templates: tuple[str, ...] | None = None
    hypotheses: tuple[Hypothesis, ...] = ()


class InfeasibilitySummary(Strict):
    declared_action_space: str
    blocking_constraints: tuple[str, ...]
    detail: str


class EvaluationResult(Strict):
    evaluation_id: str
    event_id: str
    revision: int
    goal_version: int
    evaluated_at: UtcDatetime
    actor_id: str
    hypothetical: bool
    hypotheses: tuple[Hypothesis, ...]
    templates: tuple[str, ...]
    max_combined_edits: int
    candidate_cap: int
    generated_count: int
    evaluated_count: int
    truncated: bool
    candidates: tuple[CandidateResult, ...]  # feasible by rank first, then the rest by signature
    best_candidate_id: str | None  # best constraint-feasible candidate
    best_applicable_candidate_id: str | None
    keep_candidate_id: str | None
    infeasibility: InfeasibilitySummary | None


class ActorContext(Strict):
    principal_id: str
    role: SessionRole
    grant: AuthorityGrant | None
    grant_version: int | None
    grant_valid: bool
    committed_used_cents: int
    reserved_used_cents: int


class PlanningSnapshot(Strict):
    """Everything the planner may read. Built by the server from public state only."""

    event_id: str
    revision: int
    clock: UtcDatetime
    goal: EventGoal
    planning: PlanningConfig
    activities: tuple[ActivityView, ...]
    resources: tuple[ResourceView, ...]
    plan: PlanView
    holds: tuple[HoldView, ...]
    commitments: tuple[CommitmentView, ...]
    checkins: tuple[CheckInView, ...]
    budget: BudgetView
    # When an apply_plan issued now would take effect (clock + its modeled duration). Time-
    # dependent checks (no_past_change, commitment_cutoff, hold and grant liveness) use it, so
    # a candidate reported applicable is still valid when its apply executes. None = clock.
    effective_at: UtcDatetime | None = None
    # Runtime 1.1.0 (consumable profiles; None / empty otherwise)
    stock: ConsumableStateView | None = None
    pantry_parameters: PantryParameters | None = None
    stock_options: tuple[StockOption, ...] = ()


class EventStateView(Strict):
    runtime_version: RuntimeVersion
    episode_id: str
    event_id: str
    scenario_id: str
    profile_id: str
    fictional: Literal[True]
    sandbox_label: str
    timezone: str
    episode_status: Literal["active", "closed"]
    clock: UtcDatetime
    revision: int
    goal: EventGoal
    goal_history: tuple[EventGoal, ...]
    activities: tuple[ActivityView, ...]
    plan: PlanView
    plan_history: tuple[PlanView, ...]
    resources: tuple[ResourceView, ...]
    holds: tuple[HoldView, ...]
    commitments: tuple[CommitmentView, ...]
    checkins: tuple[CheckInView, ...]
    budget: BudgetView
    grants: tuple[GrantView, ...]
    grant_history: tuple[GrantView, ...]  # every version, oldest first (same visibility filter)
    observations: tuple[ObservationRecord, ...]
    status_sources: tuple[StatusSource, ...] = ()  # additive in 1.0.0; the server always fills
    status_checks: tuple[StatusCheckView, ...] = ()
    receipts: tuple[ActionReceipt, ...]
    attempts: tuple[AttemptView, ...]
    decisions: tuple[PolicyDecision, ...]
    latest_evaluation: EvaluationResult | None
    transitions: tuple[TransitionView, ...]
    declared_assumptions: tuple[PlanningAssumption, ...]
    tool_durations_minutes: dict[str, int]
    viewer: ViewerInfo
    # Runtime 1.1.0 (consumable profiles; None / empty otherwise)
    stock: ConsumableStateView | None = None
    pantry_parameters: PantryParameters | None = None
    stock_options: tuple[StockOption, ...] = ()


# ---------------------------------------------------------------------------
# Episode history, policy runs, outcome reports
# ---------------------------------------------------------------------------


class ToolCallRecord(Strict):
    """One sanitized tool call as persisted (no session tokens)."""

    seq: int
    call_id: str
    actor_id: str | None
    actor_role: str | None
    tool: str
    requested_at: UtcDatetime | None
    completed_at: UtcDatetime | None
    revision_before: int | None
    revision_after: int | None
    envelope_status: EnvelopeStatus
    error_code: str | None
    receipt_id: str | None
    request: dict[str, Any]
    envelope: dict[str, Any]


class EpisodeHistory(Strict):
    tool_calls: tuple[ToolCallRecord, ...]
    transitions: tuple[TransitionView, ...]
    decisions: tuple[PolicyDecision, ...]
    receipts: tuple[ActionReceipt, ...]


class PolicyRunResult(Strict):
    policy_id: str
    status: Literal["waiting", "stopped", "budget_exhausted"]
    decisions: tuple[PolicyDecision, ...]
    tool_calls: int
    wait_until: UtcDatetime | None = None
    note: str = ""
    # True when the run stopped before finishing its work (for example a lost state read): the
    # host wakes it again on the next tick instead of waiting for an unrelated change.
    incomplete: bool = False


class PredicateResult(Strict):
    predicate_id: str
    kind: str
    passed: bool
    detail: str


class ActivityOutcome(Strict):
    activity_id: str
    required: bool
    lifecycle: LifecycleState
    started_at: UtcDatetime | None
    completed_at: UtcDatetime | None
    failure_reasons: tuple[str, ...]


class HoldStats(Strict):
    created: int
    released: int
    expired: int
    committed: int
    active_at_end: int
    fulfilled: int = 0  # runtime 1.1.0: stock-transfer holds handed off in full


class ServiceOutcome(Strict):
    """A service target scored against its original quantity (runtime 1.1.0)."""

    target_id: str
    unit: str
    original_quantity: int
    distributed_quantity: int
    on_time_quantity: int
    late_quantity: int
    unfulfilled_quantity: int
    supply_gap_quantity: int
    attained: bool


class StockOutcome(Strict):
    """One pool's conservation at the end (runtime 1.1.0)."""

    resource_id: str
    opening_quantity: int
    received_quantity: int
    transferred_out_quantity: int
    distributed_quantity: int
    closing_on_hand_quantity: int
    expected_unreceived_quantity: int
    conserved: bool


class EpisodeCapsReport(Strict):
    """The per-episode caps every coordinator policy runs under, and what this episode used
    (runtime 1.1.0). ``phase`` is ``development`` for the Wave 2 values that Wave 3 freezes.
    Tool calls count every call the coordinator session made (failed calls, retries and receipt
    lookups included); model calls count every provider call attributed to a decision."""

    phase: Literal["development", "frozen"]
    max_tool_calls: int = Field(ge=1)
    max_model_calls: int = Field(ge=1)
    tool_calls: int = Field(ge=0)
    model_calls: int = Field(ge=0)
    reached: tuple[Literal["tool_calls", "model_calls"], ...] = ()


class OutcomeReport(Strict):
    """State-based outcome of one episode. Computed from persisted records, never from
    policy narration. ``predicates`` and ``expected_outcome`` are present only in
    runner-side (private) reports; the public, browser-facing summary omits them."""

    report_version: Literal["1.0.0"]
    episode_id: str
    scenario_id: str
    final_clock: UtcDatetime
    final_revision: int
    goal_complete: bool
    activities: tuple[ActivityOutcome, ...]
    committed_cents: int
    reserved_cents_at_end: int
    holds: HoldStats
    applied_plans: int
    changed_assignments: int
    status_queries: int
    failed_status_queries: int
    rejected_receipts: int
    rejected_attempts_without_receipt: int
    violations: tuple[str, ...]
    infeasibility_reported: bool
    recovery_delay_minutes: int | None
    case_ref: str | None = None
    policy_id: str | None = None
    predicates: tuple[PredicateResult, ...] = ()
    expected_outcome: str | None = None
    matches_expectation: bool | None = None
    # Runtime 1.1.0 (consumable profiles; empty / zero otherwise)
    service: tuple[ServiceOutcome, ...] = ()
    stock: tuple[StockOutcome, ...] = ()
    staff_confirmations: int = 0  # applied staff receipts and distributions
    duplicate_records_rejected: int = 0  # DUPLICATE_REFERENCE rejections
    unnecessary_reservations: int = 0  # consumable holds that lapsed or were released unused
    # Runtime 1.1.0: which coordinator policy ran ("Deterministic policy" or
    # "Live agent · <returned model id>") and the per-episode caps it ran under.
    mode_label: str | None = None
    episode_caps: EpisodeCapsReport | None = None
