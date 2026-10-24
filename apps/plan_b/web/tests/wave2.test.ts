// Wave 2 views: the mode label (which policy ran), DecisionCard, the Participation view, the
// organizer's goal versions, the PantryBoard's separate counters, the staff actions, and replay of
// pantry and community states through the same read-only board.

import assert from "node:assert/strict";
import { test } from "node:test";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { buildToolRequest } from "../src/api.ts";
import { BoardView } from "../src/board/BoardView.tsx";
import { BoardHeader } from "../src/components/BoardHeader.tsx";
import { DecisionCard, FAILURE_TEXT } from "../src/components/DecisionCard.tsx";
import { choiceOf, modelUsageOf, reportRefsOf } from "../src/components/decisionDetails.ts";
import { Decisions } from "../src/components/Decisions.tsx";
import { PantryBoard, conservationText } from "../src/components/PantryBoard.tsx";
import { policyModeOf } from "../src/components/policyMode.ts";
import { GoalVersions, OrganizerPanel } from "../src/panels/OrganizerPanel.tsx";
import { endChoices } from "../src/panels/checkInForm.ts";
import {
  RUN_POLICY_LABEL,
  scenarioOfCase,
  selectionOf,
  settingLabel,
} from "../src/panels/moderatorState.ts";
import type { MutationTracker } from "../src/panels/useMutations.ts";
import { rehydrateState } from "../src/replay/ReplayView.tsx";
import type { EventStateView, ParticipationMe, SanitizedTrace } from "../src/types.ts";
import { MUTATION_TOOLS, STAFF_TOOLS } from "../src/types.ts";
import {
  OfferForm,
  Participation,
  checkInRoles,
  defaultOfferCapabilities,
  offerArguments,
  offerStartChoices,
} from "../src/views/Participation.tsx";
import {
  StaffActions,
  StaffWorkspace,
  distributableNow,
  nextReference,
  openHandoffs,
  receiptArguments,
  staffToolsOf,
  wholeQuantity,
} from "../src/views/StaffActions.tsx";
import { local, makeEvaluation, makeView, textOf } from "./support/view.ts";
import { liveDecision, makePantryView, pantryStock, ruleDecision } from "./support/wave2.ts";
import type { PantryStep } from "./support/wave2.ts";

const BINDING = { event_id: "evt_demo", grant_id: "grant_participant_presenter" };

function tracker(): MutationTracker {
  return {
    submissions: [],
    submit: () => undefined,
    checkStatus: () => undefined,
    resend: () => undefined,
    dismiss: () => undefined,
    isSending: () => false,
  };
}

const html = (element: Parameters<typeof renderToStaticMarkup>[0]) => renderToStaticMarkup(element);

// ------------------------------------------------------------------ mode label

test("the mode label is the deterministic default until a policy is selected or runs", () => {
  assert.equal(policyModeOf([]).label, "Deterministic policy");
  assert.equal(policyModeOf([]).basis, "default");
  const selected = policyModeOf([], { choice: "live", modelId: "anthropic/claude-sonnet-5.5" });
  assert.equal(selected.label, "Live agent · anthropic/claude-sonnet-5.5");
  assert.equal(selected.basis, "selected");
  // The server's own label wins over the derived one.
  const served = policyModeOf([], { choice: "live", modelId: null, label: "Live agent · m (requested; no reply yet)" });
  assert.equal(served.label, "Live agent · m (requested; no reply yet)");
  assert.equal(policyModeOf([ruleDecision()]).label, "Deterministic policy");
});

test("a live decision names the model id the provider returned, not the requested one", () => {
  const unstamped = liveDecision({ details: { ...liveDecision().details, policy_mode: null } });
  const mode = policyModeOf([unstamped], { choice: "rules", modelId: null });
  assert.equal(mode.kind, "live");
  assert.equal(mode.basis, "ran");
  assert.equal(mode.label, "Live agent · test/scripted-model-20261024");
  // Both policies in one record are both named, in the order they first ran.
  assert.equal(
    policyModeOf([ruleDecision(), liveDecision()]).label,
    "Deterministic policy → Live agent · test/scripted-model-20261024",
  );
});

test("the header shows the policy label live and in replay, beside Recorded replay", () => {
  const live = textOf(html(createElement(BoardHeader, { view: makeView(), mode: "live" })));
  assert.ok(live.includes("Deterministic policy"), live);
  assert.ok(!live.includes("Recorded replay"));
  const chosen = textOf(
    html(
      createElement(BoardHeader, {
        view: makeView(),
        mode: "live",
        selection: { choice: "live", modelId: "anthropic/claude-sonnet-5.5" },
      }),
    ),
  );
  assert.ok(chosen.includes("Live agent · anthropic/claude-sonnet-5.5 · selected, not run yet"), chosen);
  const replayed = html(createElement(BoardHeader, { view: makeView({ decisions: [liveDecision()] }), mode: "replay" }));
  assert.ok(textOf(replayed).includes("Recorded replay"));
  assert.ok(textOf(replayed).includes("Live agent · test/scripted-model-20261024"), textOf(replayed));
  assert.ok(replayed.includes('data-policy-mode="live"'));
});

test("the moderator's policy switch helpers name the policy and the case's scenario", () => {
  assert.equal(RUN_POLICY_LABEL.rules, "Run deterministic policy");
  assert.equal(RUN_POLICY_LABEL.live, "Run live agent");
  assert.equal(settingLabel({ policy: "rules" }), "Deterministic policy");
  assert.equal(settingLabel({ policy: "live", model_id: "anthropic/claude-sonnet-5.5" }), "Live agent · anthropic/claude-sonnet-5.5");
  assert.equal(settingLabel({ policy: "live", label: "Live agent · x (requested; no reply yet)" }), "Live agent · x (requested; no reply yet)");
  assert.deepEqual(selectionOf({ policy: "live", model_id: "m", label: null }), { choice: "live", modelId: "m", label: null });
  const cases = [{ case_ref: "dev01" }, { case_ref: "pantry_dev01", scenario_id: "dev_fixture_03", profile_id: "pantry_continuity" }];
  assert.equal(scenarioOfCase(cases, "pantry_dev01"), "dev_fixture_03");
  assert.equal(scenarioOfCase(cases, "dev01"), null, "omitted: the server uses the case's own scenario");
  assert.equal(scenarioOfCase(null, "dev01"), null);
});

// ------------------------------------------------------------------ DecisionCard

test("a live DecisionCard shows kind, summary, citations, model id, latency and cost", () => {
  const view = makeView();
  const card = html(createElement(DecisionCard, { decision: liveDecision(), view }));
  const text = textOf(card);
  for (const expected of [
    "Commit",
    "Applied Swap demonstrations and skills exchange",
    "Observations obs_notice_01",
    "Reports rpt_0002_dc26f35f",
    "candidate cand_0002_dc26f35f",
    "Receipts rcpt_0001",
    "Model (as returned) test/scripted-model-20261024",
    "requested test/scripted-model",
    "Latency 3.25 s",
    "Cost $0.0126 USD",
    "chosen by a model call",
    "Episode so far: 3 of 8 model calls, 6 of 48 tool calls, $0.0351 USD.",
    "Model's stated rationale (untrusted model text, not evidence):",
  ]) {
    assert.ok(text.includes(expected), `${expected} :: ${text}`);
  }
  assert.ok(card.includes('data-decision-kind="commit"'));
  assert.equal(modelUsageOf(liveDecision())?.calls.length, 1);
  assert.equal(choiceOf(liveDecision())?.option_id, "apply:cand_0002_dc26f35f");
  assert.deepEqual(reportRefsOf(liveDecision()), { reportId: "rpt_0002_dc26f35f", evaluationId: "eval_0002" });
});

test("a deterministic DecisionCard has no model block; a failure is named, never hidden", () => {
  const view = makeView();
  const rule = textOf(html(createElement(DecisionCard, { decision: ruleDecision(), view })));
  assert.ok(rule.includes("Verify") && rule.includes("Observations obs_0001"), rule);
  assert.ok(!rule.includes("Model (as returned)") && !rule.includes("Latency"), rule);
  const failed = liveDecision({
    kind: "wait",
    summary: "The model provider did not answer; waiting to retry.",
    details: { chosen_by: "server", failure: "provider_timeout", model: { requested_model: "m", model_id: null, calls: [] } },
  });
  const text = textOf(html(createElement(DecisionCard, { decision: failed, view })));
  assert.ok(text.includes(`Failure provider_timeout : ${FAILURE_TEXT.provider_timeout}`), text);
  assert.ok(text.includes("No model call: the server recorded this from the menu alone"), text);
  const list = textOf(html(createElement(Decisions, { view: makeView({ decisions: [ruleDecision(), liveDecision()] }) })));
  assert.ok(list.includes("Policy decisions (2)"), list);
  assert.ok(list.includes("Policy that ran: Deterministic policy → Live agent · test/scripted-model-20261024"), list);
});

// ------------------------------------------------------------------ Participation

const PEER_ME: ParticipationMe = {
  principal_id: "participant_kit_steward",
  display_name: "Backup kit steward",
  staff_tools: [],
  speaks_for: [
    {
      resource_id: "backup_projector",
      label: "Backup projector",
      kind: "equipment",
      status: "unknown",
      check_in: false,
      offer: {
        approved_for: ["projector"],
        needed_capabilities: { projector: ["hdmi"] },
        registered_capabilities: ["hdmi", "usb_c"],
        registered_window: { start: local("16:00"), end: local("18:00") },
        terms_ref: "fixture_catalog_v1",
      },
    },
  ],
};

test("the participation view shows the alias, the role's declared window and one check-in", () => {
  const view = makeView();
  const markup = html(createElement(Participation, { view, binding: BINDING, tracker: tracker(), me: null }));
  const text = textOf(markup);
  assert.ok(text.includes("Your role"), text);
  assert.ok(text.includes("Alias Demonstration lead registered volunteer participant_presenter"), text);
  assert.ok(text.includes("Registered role Demonstration lead (presenter) , declared 16:00–18:00"), text);
  assert.ok(text.includes("no later than your declared window's end (18:00)"), text);
  assert.equal((markup.match(/>Check in<\/button>/g) ?? []).length, 1, "exactly one Check in button");
  assert.ok(!text.includes("Offer a resource"), "no structured offer without the server's prefill");
  assert.deepEqual(
    checkInRoles(view, view.grants[0]).map((r) => r.definition.resource_id),
    ["presenter"],
  );
});

test("availability choices are scoped to the role's declared window", () => {
  const view = makeView({ clock: local("16:40") });
  const scoped = endChoices(view, local("17:05"));
  assert.equal(scoped[0], local("16:45"));
  assert.equal(scoped[scoped.length - 1], local("17:05"));
  assert.equal(endChoices(view).at(-1), local("18:00"));
});

test("a resource offer states the registered window to its end, capabilities and terms", () => {
  const prefill = PEER_ME.speaks_for[0]?.offer;
  assert.ok(prefill !== undefined && prefill !== null);
  assert.deepEqual(defaultOfferCapabilities(prefill), ["hdmi"]);
  const starts = offerStartChoices(local("16:42"), prefill.registered_window);
  assert.equal(starts[0], local("16:42"));
  assert.equal(starts[1], local("16:45"));
  assert.deepEqual(offerArguments("backup_projector", "I can bring it.", local("16:42"), prefill, ["hdmi"], "web-obs-1"), {
    text: "I can bring it.",
    kind: "resource_offer",
    entity_id: "backup_projector",
    client_record_id: "web-obs-1",
    offer: { available: { start: local("16:42"), end: local("18:00") }, capabilities: ["hdmi"], terms_ref: "fixture_catalog_v1" },
  });
  const form = textOf(
    html(createElement(OfferForm, { view: makeView(), me: PEER_ME, disabled: false, onSubmit: () => undefined })),
  );
  assert.ok(form.includes("Offer a resource") && form.includes("I confirm the registered terms fixture_catalog_v1"), form);
  assert.ok(form.includes("it reserves nothing, adds no inventory and spends no money"), form);
  assert.ok(form.includes("Until 18:00"), form);
});

// ------------------------------------------------------------------ organizer goal version

test("a preference change is a goal-versioned request; older reports read as stale", () => {
  const request = buildToolRequest(
    { event_id: "evt_demo", grant_id: "grant_organizer_demo" },
    "update_goal",
    { preference_preset: "preserve_order", reason: "Keep the announced order" },
    { idempotent: true, expectedRevision: 6, expectedGoalVersion: 1 },
  );
  assert.equal(request.expected_goal_version, 1);
  assert.equal(request.expected_revision, 6);
  const v1 = makeView().goal;
  const v2 = { ...v1, version: 2, preference_preset: "preserve_order" as const };
  const view = makeView({
    goal: v2,
    goal_history: [v1, v2],
    latest_evaluation: makeEvaluation([], { goal_version: 1 }),
    viewer: { principal_id: "organizer_demo", role: "organizer", display_name: "Organizer", grant_id: "grant_organizer_demo" },
  });
  const text = textOf(html(createElement(GoalVersions, { view })));
  assert.ok(text.includes("Goal versions (2)"), text);
  assert.ok(text.includes("v2 : Preserve the announced order ● Current"), text);
  assert.ok(text.includes("v1 : Balanced"), text);
  assert.ok(text.includes("was made under goal v1. Its candidate reports are stale"), text);
  const panel = textOf(
    html(
      createElement(OrganizerPanel, {
        view,
        session: { token: "t", role: "organizer", principal_id: "organizer_demo", display_name: null, episode_id: null, event_id: null, grant_id: null, expires_wall: null },
        binding: BINDING,
        tracker: tracker(),
        track: (run) => run(),
        refresh: async () => null,
      }),
    ),
  );
  assert.ok(panel.includes("Current: Preserve the announced order (goal version 2)"), panel);
});

// ------------------------------------------------------------------ PantryBoard

function counters(step: PantryStep): Record<string, string> {
  const markup = html(createElement(PantryBoard, { view: makePantryView(step) }));
  const out: Record<string, string> = {};
  for (const m of markup.matchAll(/data-counter="([a-z_]+)"><dt>[^<]*<\/dt><dd><span class="counter-value">([^<]*)<\/span>/g)) {
    out[m[1] ?? ""] = m[2] ?? "";
  }
  return out;
}

test("the supply gap and the unfulfilled target are separate counters that move as planned", () => {
  // planning 02_adaptation.md: 16/40 -> 16/40 -> 0/40 -> 0/40 -> 0/0.
  const expected: [PantryStep, string, string][] = [
    ["initial", "16 standard kits", "40 standard kits"],
    ["held", "16 standard kits", "40 standard kits"],
    ["handed_off", "0 standard kits", "40 standard kits"],
    ["committed", "0 standard kits", "40 standard kits"],
    ["distributed", "0 standard kits", "0 standard kits"],
  ];
  for (const [step, gap, unfulfilled] of expected) {
    const c = counters(step);
    assert.equal(c.supply_gap, gap, `${step} supply gap`);
    assert.equal(c.unfulfilled, unfulfilled, `${step} unfulfilled`);
  }
  assert.equal(counters("committed").achieved, "0 of 40 on time", "a commitment serves nobody");
  assert.equal(counters("distributed").achieved, "40 of 40 on time");
  assert.equal(counters("committed").committed, "40 standard kits");
});

test("each pool shows on-hand, reserved and available; expected units stay outside stock", () => {
  const row = (step: PantryStep, id: string): Record<string, string> => {
    const markup = html(createElement(PantryBoard, { view: makePantryView(step) }));
    const tr = new RegExp(`<tr data-stock="${id}">([\\s\\S]*?)</tr>`).exec(markup)?.[1] ?? "";
    const out: Record<string, string> = {};
    for (const m of tr.matchAll(/data-quantity="([a-z_]+)">(\d+)/g)) out[m[1] ?? ""] = m[2] ?? "";
    return out;
  };
  assert.deepEqual(row("initial", "pantry_stock"), { on_hand: "24", reserved: "0", available: "24", expected: "20", distributed: "0" });
  assert.deepEqual(row("held", "partner_stock"), { on_hand: "16", reserved: "16", available: "0", expected: "0", distributed: "0" });
  assert.deepEqual(row("handed_off", "pantry_stock"), { on_hand: "40", reserved: "0", available: "40", expected: "20", distributed: "0" });
  assert.deepEqual(row("handed_off", "partner_stock"), { on_hand: "0", reserved: "0", available: "0", expected: "0", distributed: "0" });
  assert.deepEqual(row("committed", "pantry_stock"), { on_hand: "40", reserved: "40", available: "0", expected: "20", distributed: "0" });
  assert.deepEqual(row("distributed", "pantry_stock"), { on_hand: "0", reserved: "0", available: "0", expected: "20", distributed: "40" });
  const text = textOf(html(createElement(PantryBoard, { view: makePantryView("distributed") })));
  assert.ok(text.includes("Shipment S20 into Pantry-controlled standardized kits: 20 expected at 12:55"), text);
  assert.ok(text.includes("received 0, outstanding 20"), text);
  assert.ok(text.includes("Distributed on time distribution_001 : 40"), text);
  assert.ok(text.includes("Receipt handoff_001 : 16 into Pantry-controlled standardized kits from Partner-controlled kits"), text);
  const pantry = pantryStock("distributed").balances[0];
  assert.ok(pantry !== undefined);
  assert.equal(conservationText(pantry), "opening 24 + received 16 − transferred out 0 − distributed 40 = 0 on hand");
  // No stock projection: no board (campus and community profiles).
  assert.equal(html(createElement(PantryBoard, { view: makeView() })), "");
});

// ------------------------------------------------------------------ StaffActions

test("the staff session records the handoff it is asked for, with its hold and evidence", () => {
  const view = makePantryView("held");
  const stock = view.stock;
  assert.ok(stock !== null && stock !== undefined);
  assert.deepEqual(openHandoffs(stock).map((t) => t.hold_id), ["hold_0001"]);
  const built = receiptArguments(view, { kind: "handoff", holdId: "hold_0001" }, "16", "obs_partner_stock", "handoff_001");
  assert.deepEqual(built, {
    ok: true,
    args: {
      resource_id: "pantry_stock",
      quantity: 16,
      unit: "standard_kit",
      source_observation_id: "obs_partner_stock",
      receipt_reference: "handoff_001",
      source_resource_id: "partner_stock",
      source_hold_id: "hold_0001",
    },
  });
  const shipment = receiptArguments(view, { kind: "shipment", shipmentId: "S20" }, "20", "obs_partner_stock", "receipt_001");
  assert.equal(shipment.ok && shipment.args.shipment_id, "S20");
  for (const bad of ["1.5", "-2", "0", "", "ten"]) {
    assert.equal(wholeQuantity(bad), null, bad);
    assert.equal(receiptArguments(view, { kind: "handoff", holdId: "hold_0001" }, bad, "obs_partner_stock", "h").ok, false);
  }
  assert.equal(receiptArguments(view, { kind: "handoff", holdId: "hold_0001" }, "16", "", "h").ok, false);
  assert.equal(receiptArguments(view, { kind: "handoff", holdId: "hold_0001" }, "16", "obs_partner_stock", "bad ref").ok, false);
  assert.equal(nextReference("handoff", []), "handoff_001");
  assert.equal(nextReference("handoff", ["handoff_001"]), "handoff_002");
  const text = textOf(html(createElement(StaffActions, { view, binding: BINDING, tracker: tracker() })));
  assert.ok(text.includes("Staff actions") && text.includes("Record a stock receipt"), text);
  assert.ok(text.includes("Hold hold_0001 reserves 16 standard kits of Partner-controlled kits"), text);
  assert.ok(text.includes("Record stock receipt") && text.includes("Record distribution"), text);
  assert.ok(text.includes("Nothing is committed to this target yet"), text);
});

test("a distribution is offered only from committed stock, within capacity, and says if it is late", () => {
  const view = makePantryView("committed");
  const service = view.stock?.service[0];
  assert.ok(service !== undefined);
  assert.equal(distributableNow(service, 40), 40);
  assert.equal(distributableNow({ ...service, capacity_quantity: 10 }, 40), 10, "staffed throughput bounds it");
  assert.equal(distributableNow({ ...service, distributed_quantity: 34 }, 40), 6, "the original target bounds it");
  const text = textOf(html(createElement(StaffActions, { view, binding: BINDING, tracker: tracker() })));
  assert.ok(text.includes("Recorded now at 13:40 : counts on time (deadline 13:40, inclusive)"), text);
  assert.ok(text.includes("allocations alloc_0001"), text);
  const late = textOf(
    html(createElement(StaffActions, { view: makePantryView("committed", { clock: local("13:45") }), binding: BINDING, tracker: tracker() })),
  );
  assert.ok(late.includes("after the 13:40 deadline. It is recorded truthfully as late"), late);
});

test("staff tools are a grant, listed in the web's mutation tools, and open a staff tab", () => {
  assert.deepEqual([...STAFF_TOOLS], ["record_stock_receipt", "record_distribution"]);
  for (const tool of STAFF_TOOLS) assert.ok((MUTATION_TOOLS as readonly string[]).includes(tool));
  const view = makePantryView("held");
  assert.deepEqual(staffToolsOf(view.grants[0]), ["record_stock_receipt", "record_distribution"]);
  assert.deepEqual(staffToolsOf(makeView().grants[0]), []);
  const workspace = html(createElement(StaffWorkspace, { view, binding: BINDING, tracker: tracker() }));
  assert.ok(workspace.includes('role="tablist"') && workspace.includes('aria-selected="true"'), workspace);
  assert.ok(textOf(workspace).startsWith("Staff actions Updates Staff actions"), textOf(workspace));
});

// ------------------------------------------------------------------ replay of pantry and community states

test("replay renders pantry and community states read-only through the same board", () => {
  const steps: PantryStep[] = ["initial", "held", "handed_off", "committed", "distributed"];
  for (const step of steps) {
    const view: EventStateView = { ...makePantryView(step), decisions: [ruleDecision({ policy_id: "pantry-rules/1.0.0" })] };
    const markup = html(createElement(BoardView, { view, mode: "replay" }));
    const text = textOf(markup);
    assert.ok(text.includes("Recorded replay") && text.includes("Stock and service"), step);
    assert.ok(text.includes("Deterministic policy"), step);
    assert.ok(!markup.includes("<form"), "the replay board holds no forms");
  }
  // A community (skills exchange) state: no stock section, same board, live label from decisions.
  const community = makeView({ profile_id: "community_skills_exchange", scenario_id: "dev_fixture_02", decisions: [liveDecision()] });
  const text = textOf(html(createElement(BoardView, { view: community, mode: "replay" })));
  assert.ok(text.includes("Recorded replay") && !text.includes("Stock and service"), text);
  assert.ok(text.includes("Live agent · test/scripted-model-20261024"), text);
  // A frame compacted with an evaluation reference rehydrates for a pantry state too.
  const trace = { evaluations: { eval_0001: makeEvaluation([]) } } as unknown as SanitizedTrace;
  const frame = { ...makePantryView("held"), latest_evaluation: { evaluation_ref: "eval_0001" } };
  assert.equal(rehydrateState(trace, frame).latest_evaluation?.evaluation_id, "eval_0001");
  assert.equal(rehydrateState(trace, frame).stock?.handoff_tasks[0]?.hold_id, "hold_0001");
});

test("a fulfilled stock-transfer hold renders with its own label", () => {
  const base = makePantryView("handed_off");
  const holds = [
    {
      hold_id: "hold_0001",
      resource_id: "partner_stock",
      activity_id: "distribution",
      quantity: 16,
      window: { start: local("12:35"), end: local("12:50") },
      created_at: local("12:35"),
      expires_at: local("12:55"),
      commitment_cutoff: null,
      reserved_cents: 0,
      hold_fee_cents: 0,
      status: "fulfilled" as const,
      effective_status: "fulfilled" as const,
      actor_id: "agent_demo",
      grant_id: "grant_pantry_agent",
      commitment_id: null,
      terminal_at: local("12:37"),
      created_receipt_id: "rcpt_0001",
      terminal_receipt_id: "rcpt_0002",
      consumable: true,
      remaining_quantity: 0,
      purpose: "stock_transfer" as const,
      destination_resource_id: "pantry_stock",
      service_target_id: null,
    },
  ];
  const text = textOf(html(createElement(BoardView, { view: { ...base, holds }, mode: "replay" })));
  assert.ok(text.includes("Handed off (fulfilled)"), text);
  assert.ok(text.includes("Staff handoff of 16 standard kits into Pantry-controlled standardized kits; 0 still reserved"), text);
});
