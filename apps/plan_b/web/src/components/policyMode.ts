// The mode label: which coordinator policy ran. It is read from the recorded decisions, so a
// board, a role tab and a replay agree on it. The server stamps each decision with
// `details.policy_mode.label` ("Deterministic policy" or "Live agent · <returned model id>");
// for decisions without that stamp (older traces) the label is derived: a live-policy decision
// (`live/...`) names the model id the provider returned, and every other policy is the
// deterministic baseline. Before any decision is recorded, a known selection (the server's
// `GET /api/policy`, or the moderator's choice) decides the label; with none, the board shows
// the deterministic default, as in Wave 1.

import { DETERMINISTIC_POLICY_LABEL, isLivePolicyId, liveAgentLabel } from "../format";
import type { PolicyChoice, PolicyDecision } from "../types";
import { modelUsageOf, returnedModelId } from "./decisionDetails";

export interface PolicySelection {
  readonly choice: PolicyChoice;
  /** The configured model id (live only); the returned id replaces it once a call was made. */
  readonly modelId: string | null;
  /** The server's label for the selection, when it gave one. */
  readonly label?: string | null;
}

export interface PolicyMode {
  readonly kind: "deterministic" | "live";
  /** "Deterministic policy", "Live agent · <model id>", or both in the order they first ran. */
  readonly label: string;
  /** "ran": from recorded decisions; "selected": nothing ran yet; "default": nothing known. */
  readonly basis: "ran" | "selected" | "default";
  /** The model id the provider returned (live decisions only). */
  readonly modelId: string | null;
}

/** The model id the newest live decision reports, as returned (else as requested). */
export function liveModelId(decisions: readonly PolicyDecision[]): string | null {
  let requested: string | null = null;
  for (let i = decisions.length - 1; i >= 0; i -= 1) {
    const d = decisions[i];
    if (d === undefined || !isLivePolicyId(d.policy_id)) continue;
    const usage = modelUsageOf(d);
    if (usage === null) continue;
    const returned = returnedModelId(usage);
    if (returned !== null) return returned;
    requested ??= usage.requested_model;
  }
  return requested;
}

/** The label the server stamped on a decision (`details.policy_mode.label`), if any. */
export function stampedLabel(decision: PolicyDecision): string | null {
  const mode = decision.details.policy_mode;
  if (typeof mode !== "object" || mode === null || Array.isArray(mode)) return null;
  const label = (mode as { readonly label?: unknown }).label;
  return typeof label === "string" && label.length > 0 ? label : null;
}

export function policyModeOf(
  decisions: readonly PolicyDecision[],
  selection: PolicySelection | null = null,
): PolicyMode {
  if (decisions.length > 0) {
    const liveId = liveModelId(decisions);
    const labels: string[] = [];
    for (const d of decisions) {
      const derived = isLivePolicyId(d.policy_id) ? liveAgentLabel(liveId) : DETERMINISTIC_POLICY_LABEL;
      // A live label is stamped before the first reply too; the returned id, once known, wins.
      const stamped = stampedLabel(d);
      const label = stamped !== null && (!isLivePolicyId(d.policy_id) || liveId === null) ? stamped : derived;
      if (!labels.includes(label)) labels.push(label);
    }
    const last = decisions[decisions.length - 1];
    const live = last !== undefined && isLivePolicyId(last.policy_id);
    return { kind: live ? "live" : "deterministic", label: labels.join(" → "), basis: "ran", modelId: liveId };
  }
  if (selection !== null) {
    const label = typeof selection.label === "string" && selection.label.length > 0 ? selection.label : null;
    return selection.choice === "live"
      ? { kind: "live", label: label ?? liveAgentLabel(selection.modelId), basis: "selected", modelId: null }
      : { kind: "deterministic", label: label ?? DETERMINISTIC_POLICY_LABEL, basis: "selected", modelId: null };
  }
  return { kind: "deterministic", label: DETERMINISTIC_POLICY_LABEL, basis: "default", modelId: null };
}
