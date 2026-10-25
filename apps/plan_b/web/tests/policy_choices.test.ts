// The mode label of the model-driven comparison policies P1 (tool-use/1.0.0) and P3
// (verify-all/1.0.0): once they run, the board names the policy and the returned model and shows
// a model-driven mode, as it does for the live agent (P2).

import assert from "node:assert/strict";
import { test } from "node:test";

import { modelPolicyLabel, policyModeOf } from "../src/components/policyMode.ts";
import type { JsonValue, PolicyDecision } from "../src/types.ts";
import { liveDecision, ruleDecision } from "./support/wave2.ts";

const RETURNED = "test/scripted-model-20261024";

function modelDecision(policyId: string, label: string | null, modelId: string | null = RETURNED): PolicyDecision {
  const base = liveDecision();
  const model = base.details.model as { readonly [key: string]: JsonValue };
  return liveDecision({
    policy_id: policyId,
    details: {
      ...base.details,
      model: { ...model, model_id: modelId, calls: modelId === null ? [] : (model.calls ?? []) },
      policy_mode: label === null ? null : { policy: "tool-use", label },
    },
  });
}

test("P1 and P3 decisions show a model-driven mode with the returned model", () => {
  for (const [policyId, name] of [
    ["tool-use/1.0.0", "Tool-use agent"],
    ["verify-all/1.0.0", "Verify-all agent"],
  ] as const) {
    assert.equal(modelPolicyLabel(policyId), name);
    const stamped = policyModeOf([modelDecision(policyId, `${name} · ${RETURNED}`)]);
    assert.deepEqual(stamped, { kind: "live", label: `${name} · ${RETURNED}`, basis: "ran", modelId: RETURNED });
    // An unstamped (older) decision derives the same label from its policy id.
    const derived = policyModeOf([modelDecision(policyId, null)]);
    assert.equal(derived.label, `${name} · ${RETURNED}`);
    assert.equal(derived.kind, "live");
    // A label stamped before the first reply gives way to the returned model id.
    const early = modelDecision(policyId, `${name} · test/scripted-model (requested; no reply yet)`, null);
    assert.equal(policyModeOf([early, modelDecision(policyId, `${name} · ${RETURNED}`)]).label, `${name} · ${RETURNED}`);
  }
  assert.equal(modelPolicyLabel("rules/1.0.0"), null);
  assert.equal(policyModeOf([ruleDecision()]).kind, "deterministic");
});

test("a P1 or P3 selection without a server label names its own policy", () => {
  assert.equal(policyModeOf([], { choice: "tool-use", modelId: "m" }).label, "Tool-use agent · m");
  assert.equal(policyModeOf([], { choice: "verify-all", modelId: null }).label, "Verify-all agent · model not reported yet");
  assert.equal(policyModeOf([], { choice: "live", modelId: "m" }).label, "Live agent · m");
  assert.equal(policyModeOf([], { choice: "verify-all", modelId: "m" }).kind, "live");
});
