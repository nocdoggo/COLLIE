// Typed reads of a policy decision's `details` (a free JSON object). The live policy
// (`live/1.0.0`) records which model call chose an action and what each call cost; the
// deterministic policies record none of that. Every read is defensive: a field of an unexpected
// shape reads as absent, so a hand-made or older trace never breaks the board.

import type {
  DecisionChoice,
  DecisionModelUsage,
  JsonObject,
  JsonValue,
  ModelCallRecord,
  PolicyDecision,
} from "../types";

function objectOf(value: JsonValue | undefined): JsonObject | null {
  return typeof value === "object" && value !== null && !Array.isArray(value) ? (value as JsonObject) : null;
}

function stringOf(value: JsonValue | undefined): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function numberOf(value: JsonValue | undefined): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function stringsOf(value: JsonValue | undefined): string[] {
  return Array.isArray(value) ? value.filter((v): v is string => typeof v === "string") : [];
}

function callOf(value: JsonValue): ModelCallRecord | null {
  const c = objectOf(value);
  if (c === null) return null;
  return {
    call_id: stringOf(c.call_id) ?? "",
    purpose: stringOf(c.purpose) ?? "",
    requested_model: stringOf(c.requested_model),
    model_id: stringOf(c.model_id),
    latency_ms: numberOf(c.latency_ms),
    outcome: stringOf(c.outcome) ?? "",
    prompt_tokens: numberOf(c.prompt_tokens),
    completion_tokens: numberOf(c.completion_tokens),
    total_tokens: numberOf(c.total_tokens),
    cost_usd: numberOf(c.cost_usd),
    cost_basis: stringOf(c.cost_basis),
    error: stringOf(c.error),
    consumed_tool_call_ids: stringsOf(c.consumed_tool_call_ids),
  };
}

/** `details.model`: the model calls attributed to this decision, or null for a rule policy. */
export function modelUsageOf(decision: PolicyDecision): DecisionModelUsage | null {
  const m = objectOf(decision.details.model);
  if (m === null) return null;
  const episode = objectOf(m.episode);
  const calls = Array.isArray(m.calls) ? m.calls.map(callOf).filter((c): c is ModelCallRecord => c !== null) : [];
  return {
    requested_model: stringOf(m.requested_model),
    model_id: stringOf(m.model_id),
    calls,
    latency_ms: numberOf(m.latency_ms),
    prompt_tokens: numberOf(m.prompt_tokens),
    completion_tokens: numberOf(m.completion_tokens),
    total_tokens: numberOf(m.total_tokens),
    cost_usd: numberOf(m.cost_usd),
    episode:
      episode === null
        ? null
        : {
            model_calls: numberOf(episode.model_calls),
            max_model_calls: numberOf(episode.max_model_calls),
            tool_calls: numberOf(episode.tool_calls),
            max_tool_calls: numberOf(episode.max_tool_calls),
            cost_usd: numberOf(episode.cost_usd),
          },
  };
}

/** The model id behind a decision: as returned by the provider, else as any call returned it. */
export function returnedModelId(usage: DecisionModelUsage): string | null {
  return usage.model_id ?? usage.calls.find((c) => c.model_id !== null)?.model_id ?? null;
}

/** `details.choice`: the menu option a model call chose, or null when no model chose. */
export function choiceOf(decision: PolicyDecision): DecisionChoice | null {
  const c = objectOf(decision.details.choice);
  const option = c !== null ? stringOf(c.option_id) : null;
  if (c === null || option === null) return null;
  return {
    option_id: option,
    model_call_id: stringOf(c.model_call_id),
    rationale_untrusted: stringOf(c.rationale_untrusted),
    cited_refs: stringsOf(c.cited_refs),
    dropped_refs: stringsOf(c.dropped_refs),
    consumed_tool_call_ids: stringsOf(c.consumed_tool_call_ids),
  };
}

/** One P1 (`tool-use/`) model turn: the tool calls it named, its decision and its rationale. */
export interface ToolTurnChoice {
  readonly model_call_id: string | null;
  readonly decision: string | null;
  readonly calls: readonly { readonly tool: string; readonly arguments_json: string }[];
  readonly rationale_untrusted: string | null;
  readonly cited_refs: readonly string[];
}

/** `details.choice` of a P1 turn (no menu option; the model named the tools), or null. */
export function toolTurnOf(decision: PolicyDecision): ToolTurnChoice | null {
  const c = objectOf(decision.details.choice);
  if (c === null || stringOf(c.option_id) !== null || !Array.isArray(c.calls)) return null;
  const calls = c.calls
    .map(objectOf)
    .filter((x): x is JsonObject => x !== null)
    .map((x) => ({ tool: stringOf(x.tool) ?? "?", arguments_json: stringOf(x.arguments_json) ?? "{}" }));
  return {
    model_call_id: stringOf(c.model_call_id),
    decision: stringOf(c.decision),
    calls,
    rationale_untrusted: stringOf(c.rationale_untrusted),
    cited_refs: stringsOf(c.cited_refs),
  };
}

/** "model" when a model call chose the action, "server" when the server recorded it alone. */
export function chosenBy(decision: PolicyDecision): "model" | "server" | null {
  const by = decision.details.chosen_by;
  return by === "model" || by === "server" ? by : null;
}

/** The live policy's failure class (malformed_output, provider_timeout, ...), if any. */
export function failureOf(decision: PolicyDecision): string | null {
  return stringOf(decision.details.failure);
}

/**
 * The constraint reports a decision cites: its candidate references' report ids are not stored
 * on the decision, so these are the `report_id` and `evaluation_id` the policy recorded.
 */
export function reportRefsOf(decision: PolicyDecision): { reportId: string | null; evaluationId: string | null } {
  return { reportId: stringOf(decision.details.report_id), evaluationId: stringOf(decision.details.evaluation_id) };
}
