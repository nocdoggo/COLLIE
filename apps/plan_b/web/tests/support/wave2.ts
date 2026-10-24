// Wave 2 fixtures for component tests: pantry states at each step of the planned handoff
// sequence (planning doc 02_adaptation.md, "Two counters must remain separate"), a community
// participant, and live-policy decisions shaped like the live coordinator's records.

import type {
  ConsumableStateView,
  EventStateView,
  GrantView,
  PolicyDecision,
  ResourceView,
  ServiceProgressView,
  StockBalanceView,
} from "../../src/types.ts";
import { local, makeView } from "./view.ts";

export type PantryStep = "initial" | "held" | "handed_off" | "committed" | "distributed";

function balance(
  resourceId: string,
  opening: number,
  parts: Partial<StockBalanceView> = {},
): StockBalanceView {
  const received = parts.received_quantity ?? 0;
  const out = parts.transferred_out_quantity ?? 0;
  const distributed = parts.distributed_quantity ?? 0;
  const held = parts.held_quantity ?? 0;
  const committed = parts.committed_quantity ?? 0;
  const onHand = opening + received - out - distributed;
  return {
    resource_id: resourceId,
    unit: "standard_kit",
    opening_quantity: opening,
    received_quantity: received,
    transferred_out_quantity: out,
    distributed_quantity: distributed,
    on_hand_quantity: onHand,
    held_quantity: held,
    committed_quantity: committed,
    reserved_quantity: held + committed,
    available_quantity: onHand - held - committed,
    expected_quantity: parts.expected_quantity ?? 0,
    conserved: true,
  };
}

function service(parts: Partial<ServiceProgressView>): ServiceProgressView {
  return {
    target_id: "kits_40",
    unit: "standard_kit",
    activity_id: "distribution",
    deadline: local("13:40"),
    target_quantity: 40,
    original_quantity: 40,
    distributed_quantity: 0,
    on_time_quantity: 0,
    late_quantity: 0,
    committed_quantity: 0,
    supply_gap_quantity: 16,
    unfulfilled_quantity: 40,
    qualified_minutes: 0,
    capacity_quantity: 0,
    attained: false,
    ...parts,
  };
}

const SHIPMENT = {
  shipment: {
    shipment_id: "S20",
    destination_resource_id: "pantry_stock",
    quantity: 20,
    received_quantity: 0,
    expected_at: local("12:55"),
    source_ref: "obs_pantry_stock",
  },
  outstanding_quantity: 20,
  reported_eta: local("14:10"),
  status_observation_id: "obs_0001",
};

const TASK = {
  hold_id: "hold_0001",
  source_resource_id: "partner_stock",
  destination_resource_id: "pantry_stock",
  requested_quantity: 16,
  remaining_quantity: 16,
  requested_at: local("12:35"),
  respond_after: local("12:37"),
  cutoff: local("12:50"),
  status: "open" as const,
  stock_receipt_ids: [] as string[],
};

const RECEIPT = {
  stock_receipt_id: "srec_0001",
  receipt_reference: "handoff_001",
  kind: "internal_handoff" as const,
  resource_id: "pantry_stock",
  source_resource_id: "partner_stock",
  source_hold_id: "hold_0001",
  shipment_id: null,
  quantity: 16,
  unit: "standard_kit",
  source_observation_id: "obs_partner_stock",
  at: local("12:37"),
  actor_id: "fictional_staff",
  receipt_id: "rcpt_0002",
  revision: 7,
};

const ALLOCATION = {
  allocation_id: "alloc_0001",
  resource_id: "pantry_stock",
  service_target_id: "kits_40",
  activity_id: "distribution",
  quantity: 40,
  remaining_quantity: 40,
  source_hold_id: "hold_0002",
  plan_version: 2,
  created_at: local("12:39"),
  receipt_id: "rcpt_0004",
  actor_id: "agent_demo",
  grant_id: "grant_pantry_agent",
};

/** The stock projection at one step of the planned sequence (24/16 -> 40/0 -> distributed 40). */
export function pantryStock(step: PantryStep): ConsumableStateView {
  const base = { movements: [], receipts: [], distributions: [], allocations: [], handoff_tasks: [] };
  switch (step) {
    case "initial":
      return {
        ...base,
        balances: [balance("pantry_stock", 24, { expected_quantity: 20 }), balance("partner_stock", 16)],
        expected_shipments: [SHIPMENT],
        service: [service({})],
      };
    case "held":
      return {
        ...base,
        balances: [
          balance("pantry_stock", 24, { expected_quantity: 20 }),
          balance("partner_stock", 16, { held_quantity: 16 }),
        ],
        expected_shipments: [SHIPMENT],
        service: [service({})],
        handoff_tasks: [TASK],
      };
    case "handed_off":
      return {
        ...base,
        balances: [
          balance("pantry_stock", 24, { received_quantity: 16, expected_quantity: 20 }),
          balance("partner_stock", 16, { transferred_out_quantity: 16 }),
        ],
        expected_shipments: [SHIPMENT],
        service: [service({ supply_gap_quantity: 0 })],
        handoff_tasks: [{ ...TASK, remaining_quantity: 0, status: "fulfilled", stock_receipt_ids: ["srec_0001"] }],
        receipts: [RECEIPT],
      };
    case "committed":
      return {
        ...base,
        balances: [
          balance("pantry_stock", 24, { received_quantity: 16, committed_quantity: 40, expected_quantity: 20 }),
          balance("partner_stock", 16, { transferred_out_quantity: 16 }),
        ],
        expected_shipments: [SHIPMENT],
        service: [
          service({ supply_gap_quantity: 0, committed_quantity: 40, qualified_minutes: 40, capacity_quantity: 40 }),
        ],
        handoff_tasks: [{ ...TASK, remaining_quantity: 0, status: "fulfilled", stock_receipt_ids: ["srec_0001"] }],
        receipts: [RECEIPT],
        allocations: [ALLOCATION],
      };
    case "distributed":
      return {
        ...base,
        balances: [
          balance("pantry_stock", 24, { received_quantity: 16, distributed_quantity: 40, expected_quantity: 20 }),
          balance("partner_stock", 16, { transferred_out_quantity: 16 }),
        ],
        expected_shipments: [SHIPMENT],
        service: [
          service({
            supply_gap_quantity: 0,
            unfulfilled_quantity: 0,
            distributed_quantity: 40,
            on_time_quantity: 40,
            qualified_minutes: 40,
            attained: true,
          }),
        ],
        handoff_tasks: [{ ...TASK, remaining_quantity: 0, status: "fulfilled", stock_receipt_ids: ["srec_0001"] }],
        receipts: [RECEIPT],
        allocations: [{ ...ALLOCATION, remaining_quantity: 0 }],
        distributions: [
          {
            distribution_id: "dist_0001",
            distribution_reference: "distribution_001",
            resource_id: "pantry_stock",
            service_target_id: "kits_40",
            activity_id: "distribution",
            quantity: 40,
            unit: "standard_kit",
            goal_version: 1,
            allocation_ids: ["alloc_0001"],
            at: local("13:40"),
            on_time: true,
            actor_id: "fictional_staff",
            receipt_id: "rcpt_0005",
            revision: 16,
          },
        ],
      };
  }
}

function pool(id: string, label: string): ResourceView {
  return {
    definition: {
      resource_id: id,
      label,
      kind: "supply",
      capacity: 100,
      window: { start: local("12:30"), end: local("14:00") },
      initial_status: "available",
      source_ref: `obs_${id}`,
      capabilities: ["standard_kit"],
      approved_substitute_ids: [],
      terms: {
        booking_required: false,
        commitment_cost_cents: 0,
        hold_fee_cents: 0,
        reserved_exposure_cents: 0,
        hold_max_minutes: 30,
        commitment_cutoff_minutes_before_use: null,
        refundable_on_release: true,
        cancellation_supported: false,
        booking_ref: null,
        status_source_id: null,
        queryable_facts: [],
        terms_source_ref: "fixture_catalog_pantry_v1",
      },
      consumable_stock: { unit: "standard_kit", on_hand_quantity: 0, reserved_quantity: 0, distributed_quantity: 0, expected_quantity: 0 },
    },
    status: "available",
    status_basis: "catalog",
    status_observation_id: null,
    status_observed_at: null,
    reported_eta: null,
    occupancy: [],
  };
}

function staffGrant(): GrantView {
  return {
    grant: {
      grant_id: "grant_pantry_staff",
      event_id: "e_pantry_01",
      principal_role: "participant",
      principal_id: "fictional_staff",
      allowed_tools: ["get_event_state", "record_stock_receipt", "record_distribution", "submit_observation"],
      resource_ids: ["pantry_room", "staff", "pantry_stock", "partner_stock"],
      activity_ids: ["distribution"],
      max_total_committed_cents: 0,
      max_total_reserved_cents: 0,
      expires_at: local("14:00"),
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

/** A pantry state view (viewed by the staff session) at one step of the plan. */
export function makePantryView(step: PantryStep, overrides: Partial<EventStateView> = {}): EventStateView {
  const base = makeView();
  const distribution = base.activities[1];
  const activities =
    distribution === undefined
      ? base.activities
      : [
          {
            ...distribution,
            definition: { ...distribution.definition, activity_id: "distribution", label: "Record aggregate kit distribution" },
            lifecycle: step === "distributed" ? ("completed" as const) : step === "committed" ? ("started" as const) : ("planned" as const),
          },
        ];
  return makeView({
    profile_id: "pantry_continuity",
    scenario_id: "dev_fixture_03",
    runtime_version: "1.1.0",
    clock: step === "distributed" || step === "committed" ? local("13:40") : local("12:35"),
    activities,
    resources: [...base.resources, pool("pantry_stock", "Pantry-controlled standardized kits"), pool("partner_stock", "Partner-controlled kits")],
    grants: [staffGrant()],
    observations: [
      {
        observation: {
          observation_id: "obs_partner_stock",
          event_id: "e_pantry_01",
          entity_id: "partner_stock",
          kind: "status",
          source_id: "fictional_partner_steward",
          source_record_id: "obs_partner_stock_v1",
          correlation_group: "obs_partner_stock",
          observed_at: local("12:30"),
          received_at: local("12:30"),
          valid_window: { start: local("12:30"), end: local("14:00") },
          authority_scope: "self_report",
          text: "16 standardized kits are available at the shared venue.",
          supersedes: [],
        },
        channel: "fixture_initial",
        submitted_by: null,
        revision_after: 3,
        structured: null,
      },
    ],
    viewer: {
      principal_id: "fictional_staff",
      role: "participant",
      display_name: "Pantry staff (fictional)",
      grant_id: "grant_pantry_staff",
    },
    stock: pantryStock(step),
    ...overrides,
  });
}

/** A live-policy decision shaped like the live coordinator's records (scripted model ids). */
export function liveDecision(overrides: Partial<PolicyDecision> = {}): PolicyDecision {
  return {
    decision_id: "dec_0002",
    policy_id: "live/1.0.0",
    at: local("16:43"),
    revision: 5,
    kind: "commit",
    summary: "Applied Swap demonstrations and skills exchange (cand_0002_dc26f35f, report rpt_0002_dc26f35f)",
    observation_refs: ["obs_notice_01"],
    tool_call_refs: ["call_00006"],
    candidate_refs: ["cand_0002_dc26f35f"],
    receipt_refs: ["rcpt_0001"],
    authorization_request: null,
    wait_until: null,
    details: {
      chosen_by: "model",
      evaluation_id: "eval_0002",
      report_id: "rpt_0002_dc26f35f",
      model: {
        requested_model: "test/scripted-model",
        model_id: "test/scripted-model-20261024",
        calls: [
          {
            call_id: "mc_0003",
            purpose: "choose_action",
            requested_model: "test/scripted-model",
            model_id: "test/scripted-model-20261024",
            latency_ms: 3248,
            outcome: "ok",
            prompt_tokens: 5274,
            completion_tokens: 201,
            total_tokens: 5475,
            cost_usd: 0.012558,
            cost_basis: "provider_usage",
            error: null,
            consumed_tool_call_ids: ["call_00003"],
          },
        ],
        latency_ms: 3248,
        prompt_tokens: 5274,
        completion_tokens: 201,
        total_tokens: 5475,
        cost_usd: 0.012558,
        episode: { model_calls: 3, max_model_calls: 8, tool_calls: 6, max_tool_calls: 48, cost_usd: 0.03509 },
      },
      choice: {
        option_id: "apply:cand_0002_dc26f35f",
        model_call_id: "mc_0003",
        rationale_untrusted: "The verified delay makes the swap the safest option.",
        cited_refs: ["call_00003"],
        dropped_refs: [],
        consumed_tool_call_ids: ["call_00003"],
        menu: [],
      },
      policy_mode: { policy: "live", label: "Live agent · test/scripted-model-20261024" },
    },
    ...overrides,
  };
}

/** A deterministic-policy decision. */
export function ruleDecision(overrides: Partial<PolicyDecision> = {}): PolicyDecision {
  return {
    decision_id: "dec_0001",
    policy_id: "rules/1.0.0",
    at: local("16:42"),
    revision: 4,
    kind: "verify",
    summary: "Checked projector delivery_eta: delayed, ETA 17:25",
    observation_refs: ["obs_0001"],
    tool_call_refs: ["call_00003"],
    candidate_refs: [],
    receipt_refs: [],
    authorization_request: null,
    wait_until: null,
    details: { outcome: "ok" },
    ...overrides,
  };
}
