// Alternatives card: assumption-backed checks are not confirmed facts (review web-1), and a
// stale evaluation never offers a candidate as applicable now (review web-6).

import assert from "node:assert/strict";
import { test } from "node:test";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { CandidateComparison } from "../src/components/CandidateComparison.tsx";
import {
  applicabilityLabel,
  assumptionsBehind,
  groupChecks,
} from "../src/components/candidateStatus.ts";
import { assumption, check, makeCandidate, makeEvaluation, makeView, textOf } from "./support/view.ts";

const DECLARED = assumption(
  "declared_availability",
  "presenter",
  "presenter is assumed available for demonstrations from the declared window; presenter has not checked in",
);
const ARRIVAL = assumption(
  "arrival_by_start",
  "projector",
  "projector is assumed to arrive by demonstrations start at 17:30; the reported ETA is 17:25",
);
const CATALOG = assumption(
  "catalog_availability",
  "backup_projector",
  "backup_projector is assumed available from the authored catalog; no status record confirms it",
);

const assumed = makeCandidate({
  checks: [
    check("required_activities"),
    check("participant_availability"),
    check("arrival_assumptions"),
    check("resource_status"),
    check("accessibility", "not_applicable"),
  ],
  assumptions: [DECLARED, ARRIVAL, CATALOG],
});

function render(view = makeView({ latest_evaluation: makeEvaluation([assumed]) })): string {
  return textOf(renderToStaticMarkup(createElement(CandidateComparison, { view })));
}

test("each assumption kind backs only its own check", () => {
  const byId = (id: string) => assumed.checks.find((c) => c.constraint_id === id) ?? check(id);
  assert.deepEqual(assumptionsBehind(byId("participant_availability"), assumed), [DECLARED]);
  assert.deepEqual(assumptionsBehind(byId("arrival_assumptions"), assumed), [ARRIVAL]);
  assert.deepEqual(assumptionsBehind(byId("resource_status"), assumed), [CATALOG]);
  assert.deepEqual(assumptionsBehind(byId("required_activities"), assumed), []);
  // A failed check is never "under assumption", whatever the candidate assumes.
  assert.deepEqual(assumptionsBehind(check("participant_availability", "failed"), assumed), []);
});

test("checks without a matching assumption stay confirmed facts", () => {
  const groups = groupChecks(assumed);
  assert.deepEqual(
    groups.confirmed.map((c) => c.constraint_id),
    ["required_activities"],
  );
  assert.deepEqual(
    groups.underAssumption.map((g) => g.check.constraint_id),
    ["participant_availability", "arrival_assumptions", "resource_status"],
  );
  assert.deepEqual(groups.notApplicable.map((c) => c.constraint_id), ["accessibility"]);
  const plain = makeCandidate({ checks: [check("participant_availability")], assumptions: [] });
  assert.deepEqual(groupChecks(plain).confirmed.map((c) => c.constraint_id), ["participant_availability"]);
});

test("a hypothesis counts only for a resource the candidate uses", () => {
  const unused = assumption("hypothesis", "backup_projector", "Hypothesis 'late': backup_projector ready at 17:40");
  const used = assumption("hypothesis", "projector", "Hypothesis 'late': projector ready at 17:40");
  const c = makeCandidate({ checks: [check("resource_status")], assumptions: [unused, used] });
  assert.deepEqual(assumptionsBehind(check("resource_status"), c), [used]);
});

test("the card labels assumption-backed passes 'Passes under assumption' with the assumption", () => {
  const text = render();
  assert.ok(text.includes("≈ Passes under assumption People are available for their slots"), text);
  assert.ok(text.includes(`Assumes: ${DECLARED.text}`));
  assert.ok(
    text.includes("≈ Passes under assumption Expected equipment is reported to arrive before its activity starts"),
  );
  assert.ok(text.includes(`Assumes: ${ARRIVAL.text}`));
  assert.ok(text.includes("≈ Passes under assumption Assigned resources are not unavailable or unknown"));
  assert.ok(text.includes("✓ Confirmed Every required activity is scheduled"));
  for (const name of [
    "People are available for their slots",
    "Expected equipment is reported to arrive before its activity starts",
    "Assigned resources are not unavailable or unknown",
  ]) {
    assert.ok(!text.includes(`✓ Confirmed ${name}`), `${name} must not read as a confirmed fact`);
  }
});

test("a stale evaluation never offers 'Can be applied now'", () => {
  const evaluation = makeEvaluation([assumed], { revision: 4 });
  const stale = render(makeView({ revision: 5, latest_evaluation: evaluation }));
  assert.ok(!stale.includes("Can be applied now"), stale);
  assert.ok(stale.includes("Was applicable at revision 4"));

  const fresh = render(makeView({ revision: 4, latest_evaluation: evaluation }));
  assert.ok(fresh.includes("▶ Can be applied now"));
});

test("applicability follows the evaluation's versions and kind", () => {
  const evaluation = makeEvaluation([assumed], { revision: 4, goal_version: 1 });
  const now = { revision: 4, goalVersion: 1 };
  assert.equal(applicabilityLabel(assumed, evaluation, now).text, "Can be applied now");
  assert.equal(
    applicabilityLabel(assumed, evaluation, { revision: 6, goalVersion: 1 }).text,
    "Was applicable at revision 4",
  );
  assert.equal(
    applicabilityLabel(assumed, evaluation, { revision: 4, goalVersion: 2 }).text,
    "Was applicable at revision 4, goal version 1",
  );
  const blocked = makeCandidate({ applicable_now: false });
  assert.equal(applicabilityLabel(blocked, evaluation, now).text, "Not applicable now");
  assert.equal(
    applicabilityLabel(blocked, evaluation, { revision: 5, goalVersion: 1 }).text,
    "Not applicable at revision 4",
  );
  const whatIf = makeEvaluation([assumed], { hypothetical: true });
  assert.equal(applicabilityLabel(assumed, whatIf, now).tone, "warn");
  assert.notEqual(applicabilityLabel(assumed, whatIf, now).text, "Can be applied now");
});
