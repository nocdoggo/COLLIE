// The staff receipt form's default source: recording the handoff never moves the form on to the
// expected shipment, which has not arrived (audit item E3).

import assert from "node:assert/strict";
import { test } from "node:test";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import type { MutationTracker } from "../src/panels/useMutations.ts";
import { StaffActions, receiptChoiceKey } from "../src/views/StaffActions.tsx";
import { textOf } from "./support/view.ts";
import { makePantryView } from "./support/wave2.ts";

const html = (element: Parameters<typeof renderToStaticMarkup>[0]) => renderToStaticMarkup(element);
const BINDING = { event_id: "evt_demo", grant_id: "grant_staff" };

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

test("the receipt form keeps a picked source and otherwise defaults to an open handoff or to none", () => {
  const both = ["hold:hold_0001", "hold:hold_0002", "shipment:S20"];
  assert.equal(receiptChoiceKey(both, ""), "hold:hold_0001", "an open handoff comes first");
  assert.equal(receiptChoiceKey(both, "shipment:S20"), "shipment:S20", "a shipment staff picked stays chosen");
  assert.equal(receiptChoiceKey(both, "hold:hold_0002"), "hold:hold_0002");
  // The recorded handoff is gone: the next open handoff, never the shipment.
  assert.equal(receiptChoiceKey(["hold:hold_0002", "shipment:S20"], "hold:hold_0001"), "hold:hold_0002");
  assert.equal(receiptChoiceKey(["shipment:S20"], "hold:hold_0001"), "");
  assert.equal(receiptChoiceKey(["shipment:S20"], ""), "", "a shipment is never chosen for staff");
  assert.equal(receiptChoiceKey([], ""), "");
});

test("after the handoff is recorded the form waits for a choice instead of offering the shipment", () => {
  const markup = html(createElement(StaffActions, { view: makePantryView("handed_off"), binding: BINDING, tracker: tracker() }));
  const text = textOf(markup);
  assert.ok(text.includes("Choose what arrived"), text);
  assert.ok(text.includes("Shipment S20: 20 outstanding"), "the shipment can still be picked");
  assert.ok(text.includes("Choose a handoff task or a shipment. Nothing is sent until this is fixed."), text);
  assert.match(markup, /<button type="submit" class="button" disabled="">Record stock receipt<\/button>/);
  // While the handoff is open it is the default, as before.
  const held = textOf(html(createElement(StaffActions, { view: makePantryView("held"), binding: BINDING, tracker: tracker() })));
  assert.ok(held.includes("Hold hold_0001 reserves 16 standard kits") && !held.includes("Choose what arrived"), held);
});
