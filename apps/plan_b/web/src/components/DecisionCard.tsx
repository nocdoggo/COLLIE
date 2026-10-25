import { DECISION_LABEL, fmtCents, fmtLatency, fmtTime, fmtUsd, lookups } from "../format";
import type { StatusLabel } from "../format";
import type { DecisionModelUsage, EventStateView, PolicyDecision } from "../types";
import { AUTHORIZATION_STATE_TEXT } from "./authorization";
import type { AuthorizationItem } from "./authorization";
import { choiceOf, chosenBy, failureOf, modelUsageOf, reportRefsOf, returnedModelId, toolTurnOf } from "./decisionDetails";
import { EvidenceCard } from "./EvidenceCard";
import { modelPolicyLabel } from "./policyMode";
import { Code, JumpButton, StatusBadge, Tag, When, domId } from "./ui";

/** Plain-language names for the live policy's failure classes (contract section 15). */
export const FAILURE_TEXT: Record<string, string> = {
  malformed_output: "the model's output did not match the required structure after one repair",
  invalid_choice: "the model chose an option outside the server's menu",
  unknown_entity: "the model named something that is not registered",
  model_call_cap: "the episode's model-call cap is reached",
  tool_call_cap: "the episode's tool-call cap is reached",
  spend_cap: "the spend cap would be exceeded; nothing was sent",
  provider_timeout: "the model provider did not answer in time",
  provider_error: "the model provider failed or could not be reached",
  provider_config: "the model endpoint is not configured",
  stale_revision: "the state changed before the action ran",
  lost_response: "a mutation's response was lost and could not be reconciled",
};

/** The decision's badge; an ask with no grant request (a staff handoff) is not an organizer ask. */
function labelOf(d: PolicyDecision): StatusLabel {
  if (d.kind === "ask" && d.authorization_request === null) return { text: "Ask", icon: "⚑", tone: "warn" };
  return DECISION_LABEL[d.kind] ?? { text: d.kind, icon: "•", tone: "neutral" };
}

/** P3's relevance rule (`details.verify_all.rule`) when the server itself requested this check. */
export function verifyAllRuleOf(d: PolicyDecision): string | null {
  const v = d.details.verify_all;
  if (typeof v !== "object" || v === null || Array.isArray(v)) return null;
  const rule = (v as { readonly rule?: unknown }).rule;
  return typeof rule === "string" && rule.length > 0 ? rule : "verify-all";
}

/** Who chose a model-driven policy's decision: a model call, a server check (P3) or the server. */
export function chooserText(d: PolicyDecision): string {
  const by = chosenBy(d);
  if (by === "model") return "chosen by a model call";
  const rule = verifyAllRuleOf(d);
  if (by === "server" && rule !== null) return `server check under ${rule}, no model choice`;
  return by === "server" ? "recorded by the server, no model choice" : "";
}

function sumOrNull(values: readonly (number | null)[]): number | null {
  const known = values.filter((v): v is number => v !== null);
  return known.length > 0 ? known.reduce((a, b) => a + b, 0) : null;
}

/**
 * The model accounting of one model-driven decision: returned model, latency, tokens and cost.
 * `noCall` says who recorded a decision without a model call (default: the live agent's menu).
 */
export function ModelUsage({ usage, noCall }: { usage: DecisionModelUsage; noCall?: string }) {
  const returned = returnedModelId(usage);
  const calls = usage.calls;
  const latency = usage.latency_ms ?? sumOrNull(calls.map((c) => c.latency_ms));
  const cost = usage.cost_usd ?? sumOrNull(calls.map((c) => c.cost_usd));
  const episode = usage.episode;
  return (
    <div className="model-usage">
      {calls.length === 0 ? (
        <p className="small">
          No model call: {noCall ?? "the server recorded this from the menu alone"} (requested model{" "}
          <Code>{usage.requested_model ?? "not reported"}</Code>).
        </p>
      ) : (
        <dl className="model-figures">
          <div>
            <dt>Model (as returned)</dt>
            <dd>
              <Code>{returned ?? "not reported"}</Code>
              {usage.requested_model !== null && usage.requested_model !== returned ? (
                <span className="sub">requested {usage.requested_model}</span>
              ) : null}
            </dd>
          </div>
          <div>
            <dt>Latency</dt>
            <dd>{fmtLatency(latency)}</dd>
          </div>
          <div>
            <dt>Cost</dt>
            <dd>{fmtUsd(cost)}</dd>
          </div>
          <div>
            <dt>Calls</dt>
            <dd>
              {calls.length}
              <span className="sub">
                {usage.total_tokens !== null ? `${usage.total_tokens} tokens` : "tokens not reported"}
              </span>
            </dd>
          </div>
        </dl>
      )}
      {calls.length > 0 ? (
        <ol className="small model-calls">
          {calls.map((c) => (
            <li key={c.call_id}>
              <Code>{c.call_id}</Code> {c.purpose.replace(/_/g, " ")}: {c.outcome}
              {" · "}
              {fmtLatency(c.latency_ms)} · {fmtUsd(c.cost_usd)}
              {c.cost_basis !== null ? ` (${c.cost_basis.replace(/_/g, " ")})` : ""}
              {c.consumed_tool_call_ids.length > 0 ? <> · read the results of {c.consumed_tool_call_ids.join(", ")}</> : null}
              {c.error !== null ? <span className="tone-text-bad"> · {c.error}</span> : null}
            </li>
          ))}
        </ol>
      ) : null}
      {episode !== null ? (
        <p className="muted small">
          Episode so far: {episode.model_calls ?? "?"} of {episode.max_model_calls ?? "?"} model calls,{" "}
          {episode.tool_calls ?? "?"} of {episode.max_tool_calls ?? "?"} tool calls, {fmtUsd(episode.cost_usd)}.
        </p>
      ) : null}
    </div>
  );
}

/**
 * One policy decision: its kind and summary, what it cites (observations, constraint reports,
 * receipts, tool calls) and, for a model-driven policy's decision (P1 `tool-use/`, P2 `live/`,
 * P3 `verify-all/`), who chose it (a model call, a P3 server check, or the server) and the model
 * calls with their latency and cost. A decision is narration: the receipts are the evidence.
 */
export function DecisionCard({
  decision,
  view,
  authorization,
}: {
  decision: PolicyDecision;
  view: EventStateView;
  /** The board's open/answered state of this decision's authorization request, if it is the latest. */
  authorization?: AuthorizationItem;
}) {
  const d = decision;
  const tz = view.timezone;
  const look = lookups(view);
  const live = modelPolicyLabel(d.policy_id) !== null;
  const usage = modelUsageOf(d);
  const choice = choiceOf(d);
  const chooser = live ? chooserText(d) : "";
  const turn = choice === null ? toolTurnOf(d) : null;
  const noCall =
    verifyAllRuleOf(d) !== null
      ? "the server requested this check under its verify-all rule"
      : d.policy_id.startsWith("tool-use/")
        ? "the server recorded this itself"
        : undefined;
  const failure = failureOf(d);
  const { reportId, evaluationId } = reportRefsOf(d);
  const request = d.authorization_request;
  return (
    <li id={domId("dec", d.decision_id)} tabIndex={-1} className={`decision${live ? " decision-live" : ""}`} data-decision-kind={d.kind}>
      <p>
        <StatusBadge label={labelOf(d)} /> {d.summary}
      </p>
      <p className="muted small">
        <When iso={d.at} text={fmtTime(d.at, tz)} /> · revision {d.revision} · <Code>{d.policy_id}</Code>
        {chooser !== "" ? <span data-chosen-by={chosenBy(d) ?? ""}> · {chooser}</span> : null}
        {d.details.recorded_by === "host" ? " · recorded by the policy host (episode cap)" : ""}
        {d.wait_until !== null ? (
          <>
            {" "}· wait until <When iso={d.wait_until} text={fmtTime(d.wait_until, tz)} />
          </>
        ) : null}
      </p>
      {failure !== null ? (
        <p className="small tone-text-warn">
          <span aria-hidden="true">⚠ </span>
          Failure <Code>{failure}</Code>: {FAILURE_TEXT[failure] ?? failure.replace(/_/g, " ")}. Nothing was invented in
          its place.
        </p>
      ) : null}
      {request !== null ? (
        <div className="notice tone-warn">
          <p>
            <span aria-hidden="true">⚑ </span>
            <strong>Authorization request</strong>: raise <Code>{request.target_grant_id}</Code> committed limit from{" "}
            {fmtCents(request.current_value)} to {fmtCents(request.requested_value)} for{" "}
            {look.resourceLabel(request.resource_id)} (candidate <Code>{request.candidate_id}</Code>). {request.reason}
          </p>
          {authorization !== undefined ? (
            <p>
              <Tag tone={authorization.state === "open" ? "warn" : "neutral"} icon={authorization.state === "open" ? "⧗" : "✓"}>
                {AUTHORIZATION_STATE_TEXT[authorization.state]}
              </Tag>
            </p>
          ) : null}
        </div>
      ) : null}
      <dl className="decision-refs small">
        {d.observation_refs.length > 0 ? (
          <div>
            <dt>Observations</dt>
            <dd>
              {d.observation_refs.map((ref) => (
                <JumpButton key={ref} targetId={domId("obs", ref)}>
                  {ref}
                </JumpButton>
              ))}
            </dd>
          </div>
        ) : null}
        {reportId !== null || evaluationId !== null || d.candidate_refs.length > 0 ? (
          <div>
            <dt>Reports</dt>
            <dd>
              {reportId !== null ? <Code>{reportId}</Code> : null}
              {d.candidate_refs.length > 0 ? <span> candidate {d.candidate_refs.join(", ")}</span> : null}
              {evaluationId !== null ? <span className="muted"> (evaluation {evaluationId})</span> : null}
            </dd>
          </div>
        ) : null}
        {d.receipt_refs.length > 0 ? (
          <div>
            <dt>Receipts</dt>
            <dd>
              {d.receipt_refs.map((ref) => (
                <JumpButton key={ref} targetId={domId("rcpt", ref)}>
                  {ref}
                </JumpButton>
              ))}
            </dd>
          </div>
        ) : null}
        {d.tool_call_refs.length > 0 ? (
          <div>
            <dt>Tool calls</dt>
            <dd>{d.tool_call_refs.join(", ")}</dd>
          </div>
        ) : null}
      </dl>
      {live && usage !== null ? <ModelUsage usage={usage} noCall={noCall} /> : null}
      {choice !== null ? (
        <div className="small">
          <p>
            Chose menu option <Code>{choice.option_id}</Code>
            {choice.model_call_id !== null ? <> in model call <Code>{choice.model_call_id}</Code></> : null}
            {choice.cited_refs.length > 0 ? <>, citing {choice.cited_refs.join(", ")}</> : null}.
          </p>
          {choice.rationale_untrusted !== null ? (
            <blockquote className="untrusted">
              <p className="muted">Model&apos;s stated rationale (untrusted model text, not evidence):</p>
              <p>{choice.rationale_untrusted}</p>
            </blockquote>
          ) : null}
        </div>
      ) : null}
      {turn !== null ? (
        <div className="small">
          <p>
            {turn.model_call_id !== null ? (
              <>
                Model call <Code>{turn.model_call_id}</Code>
              </>
            ) : (
              "The model"
            )}{" "}
            named {turn.calls.length > 0 ? turn.calls.map((c) => c.tool).join(", ") : "no tool call"}
            {turn.decision !== null && turn.decision !== "none" ? (
              <>
                {" "}and decided <Code>{turn.decision}</Code>
              </>
            ) : null}
            {turn.cited_refs.length > 0 ? <>, citing {turn.cited_refs.join(", ")}</> : null}. The executor checked
            every call.
          </p>
          {turn.rationale_untrusted !== null ? (
            <blockquote className="untrusted">
              <p className="muted">Model&apos;s stated rationale (untrusted model text, not evidence):</p>
              <p>{turn.rationale_untrusted}</p>
            </blockquote>
          ) : null}
        </div>
      ) : null}
      {Object.keys(d.details).length > 0 ? <EvidenceCard title="Decision details (JSON)" value={d.details} /> : null}
    </li>
  );
}
