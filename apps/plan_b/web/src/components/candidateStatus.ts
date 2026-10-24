// How a stored candidate is labeled (contract section 10).
//
// * A passed check is a confirmed fact only when no assumption of the candidate supports it: a
//   declared window without a check-in, a reported ETA, a catalog entry or a what-if hypothesis
//   is not observed evidence.
// * `applicable_now` describes the evaluation's own revision. Once the event has moved on,
//   apply_plan would reject the candidate as stale, so it is never shown as applicable now.

import type { StatusLabel } from "../format";
import type { CandidateAssumption, CandidateCheck, CandidateResult, EvaluationResult } from "../types";

type AssumptionKind = CandidateAssumption["kind"];

/** Assumption kinds that a passing check of each constraint can rest on. */
export const ASSUMPTIONS_BEHIND_CHECK: Readonly<Record<string, readonly AssumptionKind[]>> = {
  // ETA <= start, or no ETA evidence at all, passes with an arrival_by_start assumption.
  arrival_assumptions: ["arrival_by_start", "hypothesis"],
  // Without a check-in, the declared resource window passes with declared_availability.
  participant_availability: ["declared_availability"],
  // "available" from the authored catalog only, or a hypothesized status.
  resource_status: ["catalog_availability", "hypothesis"],
};

export interface AssumedCheck {
  readonly check: CandidateCheck;
  readonly assumptions: readonly CandidateAssumption[];
}

export interface CheckGroups {
  /** Passed, and no candidate assumption supports the pass. */
  readonly confirmed: readonly CandidateCheck[];
  /** Passed only because of the listed assumptions. */
  readonly underAssumption: readonly AssumedCheck[];
  readonly notApplicable: readonly CandidateCheck[];
  readonly unsupported: readonly CandidateCheck[];
}

/** The candidate's assumptions that a passed check rests on (empty for any other status). */
export function assumptionsBehind(
  check: CandidateCheck,
  candidate: CandidateResult,
): CandidateAssumption[] {
  if (check.status !== "passed") return [];
  const kinds = ASSUMPTIONS_BEHIND_CHECK[check.constraint_id] ?? [];
  if (kinds.length === 0) return [];
  // The other kinds are recorded only for resources the candidate uses; a hypothesis is
  // recorded per evaluation, so it counts only when the candidate uses that resource.
  const used = new Set(candidate.assignments.flatMap((a) => a.resource_ids));
  return candidate.assumptions.filter(
    (a) => kinds.includes(a.kind) && (a.kind !== "hypothesis" || used.has(a.entity_id)),
  );
}

export function groupChecks(candidate: CandidateResult): CheckGroups {
  const confirmed: CandidateCheck[] = [];
  const underAssumption: AssumedCheck[] = [];
  for (const check of candidate.checks) {
    if (check.status !== "passed") continue;
    const assumptions = assumptionsBehind(check, candidate);
    if (assumptions.length > 0) underAssumption.push({ check, assumptions });
    else confirmed.push(check);
  }
  return {
    confirmed,
    underAssumption,
    notApplicable: candidate.checks.filter((c) => c.status === "not_applicable"),
    unsupported: candidate.checks.filter((c) => c.status === "unsupported"),
  };
}

/** The current versions an evaluation is compared against. */
export interface CurrentVersions {
  readonly revision: number;
  readonly goalVersion: number;
}

export function evaluationIsStale(evaluation: EvaluationResult, current: CurrentVersions): boolean {
  return evaluation.revision !== current.revision || evaluation.goal_version !== current.goalVersion;
}

/** "revision 4", plus the goal version when only that one changed or both did. */
function evaluatedAt(evaluation: EvaluationResult, current: CurrentVersions): string {
  const goal =
    evaluation.goal_version !== current.goalVersion ? `, goal version ${evaluation.goal_version}` : "";
  return `revision ${evaluation.revision}${goal}`;
}

export function applicabilityLabel(
  candidate: CandidateResult,
  evaluation: EvaluationResult,
  current: CurrentVersions,
): StatusLabel {
  if (evaluation.hypothetical) {
    return { text: "Not applicable (hypothetical evaluation)", icon: "≈", tone: "warn" };
  }
  if (evaluationIsStale(evaluation, current)) {
    const at = evaluatedAt(evaluation, current);
    return candidate.applicable_now
      ? { text: `Was applicable at ${at}`, icon: "⧖", tone: "neutral" }
      : { text: `Not applicable at ${at}`, icon: "‖", tone: "warn" };
  }
  return candidate.applicable_now
    ? { text: "Can be applied now", icon: "▶", tone: "ok" }
    : { text: "Not applicable now", icon: "‖", tone: "warn" };
}

/** The "best applicable" tag, qualified by its revision once the evaluation is stale. */
export function bestApplicableText(evaluation: EvaluationResult, current: CurrentVersions): string {
  return evaluationIsStale(evaluation, current)
    ? `Best applicable at ${evaluatedAt(evaluation, current)}`
    : "Best applicable";
}
