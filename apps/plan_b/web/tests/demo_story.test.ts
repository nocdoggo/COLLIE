// Presentation clarity for the seven-minute demo (PEEAI_plan/handoffs/wave_2/DEMO.md): every
// model-driven policy's decision card (P1 tool-use/, P2 live/, P3 verify-all/) says who chose it,
// P3's own status checks read as server checks, hold cards show their id next to the expiry, the
// pantry board uses the presentation's terms, and a transition row keeps its text in one cell.

import assert from "node:assert/strict";
import { test } from "node:test";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { DecisionCard, FAILURE_TEXT, chooserText, verifyAllRuleOf } from "../src/components/DecisionCard.tsx";
import { toolTurnOf } from "../src/components/decisionDetails.ts";
import { Transitions } from "../src/components/Decisions.tsx";
import { PantryBoard, ServiceTargetCard } from "../src/components/PantryBoard.tsx";
import { HoldsAndCommitments } from "../src/components/Resources.tsx";
import type { HoldView, JsonValue, PolicyDecision } from "../src/types.ts";
import { local, makeView, textOf } from "./support/view.ts";
import { liveDecision, makePantryView, pantryStock, ruleDecision } from "./support/wave2.ts";

const html = (element: Parameters<typeof renderToStaticMarkup>[0]) => renderToStaticMarkup(element);
const card = (d: PolicyDecision) => html(createElement(DecisionCard, { decision: d, view: makeView() }));
const RULE = "verify-all-relevance/1.0.0";

/** A decision of another model-driven policy, with the live fixture's model accounting. */
function modelDriven(policyId: string, details: Record<string, JsonValue>): PolicyDecision {
  const base = liveDecision();
  return liveDecision({ policy_id: policyId, details: { model: base.details.model ?? null, ...details } });
}

/** A P3 status check the server requested itself (agent/policies/verify_all.py). */
function serverCheck(): PolicyDecision {
  return modelDriven("verify-all/1.0.0", {
    chosen_by: "server",
    verify_all: { rule: RULE, why: "unresolved notice obs_notice_01", attempt: 1, max_attempts: 2 },
    entity_id: "projector",
    fact: "delivery_eta",
    outcome: "succeeded",
    error_code: null,
    model: { requested_model: "test/scripted-model", model_id: null, calls: [] },
  });
}

/** A P1 turn: the model named the tools itself (agent/policies/tool_use.py `details.choice`). */
function toolTurn(): PolicyDecision {
  return modelDriven("tool-use/1.0.0", {
    chosen_by: "model",
    choice: {
      model_call_id: "mc_0002",
      decision: "none",
      calls: [{ tool: "query_status", arguments_json: '{"entity_id":"projector","fact":"delivery_eta"}' }],
      rationale_untrusted: "Check the delivery before changing anything.",
      cited_refs: ["obs_notice_01"],
      dropped_refs: [],
      consumed_tool_call_ids: [],
    },
  });
}

test("P1, P2 and P3 decisions chosen by a model call carry the note, the styling and the model block", () => {
  const p3Commit = liveDecision({ policy_id: "verify-all/1.0.0" });
  for (const d of [liveDecision(), toolTurn(), p3Commit]) {
    const markup = card(d);
    const text = textOf(markup);
    assert.ok(markup.includes('class="decision decision-live"'), `${d.policy_id} styling`);
    assert.ok(markup.includes('data-chosen-by="model"'), d.policy_id);
    assert.ok(text.includes("chosen by a model call"), `${d.policy_id} :: ${text}`);
    assert.ok(text.includes("Model (as returned) test/scripted-model-20261024"), `${d.policy_id} :: ${text}`);
    assert.ok(text.includes("Cost $0.0126 USD"), d.policy_id);
  }
  assert.equal(chooserText(liveDecision()), "chosen by a model call");
});

test("a P1 turn shows the tools the model named and its untrusted rationale", () => {
  const turn = toolTurnOf(toolTurn());
  assert.deepEqual(turn?.calls.map((c) => c.tool), ["query_status"]);
  assert.equal(toolTurnOf(liveDecision()), null, "a menu choice is not a P1 turn");
  const text = textOf(card(toolTurn()));
  assert.ok(text.includes("Model call mc_0002 named query_status, citing obs_notice_01. The executor checked every call."), text);
  assert.ok(text.includes("Model's stated rationale (untrusted model text, not evidence):"), text);
  assert.ok(text.includes("Check the delivery before changing anything."), text);
  assert.ok(!text.includes("Chose menu option"), text);
});

test("P3's own status checks read as server checks under its relevance rule, never as model choices", () => {
  const d = serverCheck();
  assert.equal(verifyAllRuleOf(d), RULE);
  assert.equal(verifyAllRuleOf(liveDecision()), null);
  const markup = card(d);
  const text = textOf(markup);
  assert.ok(markup.includes('class="decision decision-live"'), markup);
  assert.ok(markup.includes('data-chosen-by="server"'), markup);
  assert.ok(text.includes(`server check under ${RULE}, no model choice`), text);
  assert.ok(text.includes("No model call: the server requested this check under its verify-all rule"), text);
  assert.ok(!text.includes("chosen by a model call"), text);
  // A P2 or P3 decision the server recorded from the menu keeps its own wording.
  const keep = liveDecision({ policy_id: "verify-all/1.0.0", details: { chosen_by: "server", model: { calls: [] } } });
  assert.ok(textOf(card(keep)).includes("recorded by the server, no model choice"));
  const p1Server = modelDriven("tool-use/1.0.0", { chosen_by: "server", model: { calls: [] } });
  assert.ok(textOf(card(p1Server)).includes("No model call: the server recorded this itself"));
});

test("a deterministic decision has no chooser note and no model styling", () => {
  const markup = card(ruleDecision());
  assert.ok(markup.includes('class="decision"'), markup);
  assert.ok(!markup.includes("data-chosen-by"), markup);
  assert.ok(!textOf(markup).includes("chosen by a model call"));
});

test("a hold card shows the hold id beside its expiry and cutoff", () => {
  const hold: HoldView = {
    hold_id: "hold_0001",
    resource_id: "backup_projector",
    activity_id: "demonstrations",
    quantity: 1,
    window: { start: local("17:10"), end: local("17:30") },
    created_at: local("16:45"),
    expires_at: local("16:55"),
    commitment_cutoff: local("16:55"),
    reserved_cents: 3500,
    hold_fee_cents: 0,
    status: "active",
    effective_status: "active",
    actor_id: "agent_demo",
    grant_id: "grant_coordinator_demo",
    commitment_id: null,
    terminal_at: null,
    created_receipt_id: "rcpt_0001",
    terminal_receipt_id: null,
  };
  const text = textOf(html(createElement(HoldsAndCommitments, { view: makeView({ holds: [hold] }) })));
  assert.ok(text.includes("hold_0001"), text);
  assert.ok(text.includes("Hold expires 16:55"), text);
  assert.ok(text.includes("Commit before (cutoff) 16:55"), text);
});

test("the pantry board names the fictional sandbox, the supply shortfall and the service deficit", () => {
  const markup = html(createElement(PantryBoard, { view: makePantryView("initial") }));
  const text = textOf(markup);
  assert.ok(text.includes("Fictional pantry sandbox"), text);
  assert.ok(markup.includes('data-counter="supply_gap"><dt>Supply shortfall</dt>'), markup);
  assert.ok(markup.includes('data-counter="unfulfilled"><dt>Service deficit</dt>'), markup);
  assert.ok(text.includes("Only a staff receipt closes it; expected units never do."), text);
  assert.ok(text.includes("Only kits distributed on time reduce it"), text);
});

test("the pantry capacity tile says what staff can still distribute now", () => {
  const view = makePantryView("initial");
  const service = { ...pantryStock("initial").service[0]!, qualified_minutes: 40, capacity_quantity: 0, distributed_quantity: 40 };
  const markup = html(createElement(ServiceTargetCard, { service, view }));
  const text = textOf(markup);
  assert.ok(markup.includes('data-counter="capacity"><dt>Can still be distributed now</dt>'), markup);
  assert.ok(text.includes("Staffed throughput so far (40 staffed minutes with committed stock) minus 40"), text);
  assert.ok(!text.includes("Staffed capacity so far"), text);
});

test("a provider failure reads as failed or unreachable, not only as an error reply", () => {
  assert.equal(FAILURE_TEXT.provider_error, "the model provider failed or could not be reached");
});

test("a transition row is the time and one text cell (the list is a two-column grid)", () => {
  const view = makeView({
    transitions: [
      { revision: 4, at: local("16:42"), cause_kind: "observation_received", cause_ref: "obs_0001", summary: "Status from supplier" },
    ],
  });
  const markup = html(createElement(Transitions, { view }));
  const row = /<li>([\s\S]*?)<\/li>/.exec(markup)?.[1] ?? "";
  const cells = row.match(/^<span class="feed-time">[\s\S]*?<\/span><span>[\s\S]*<\/span>$/);
  assert.ok(cells !== null, row);
  assert.ok(textOf(markup).includes("r4 observation received · Status from supplier"), textOf(markup));
});
