import { useState } from "react";
import type { FormEvent } from "react";

import { buildToolRequest, callTool } from "../api";
import type { StoredSession, ToolBinding } from "../api";
import { authorizationRequests } from "../components/authorization";
import type { AuthorizationItem } from "../components/authorization";
import { Code, Empty, Section, Tag } from "../components/ui";
import { PRESET_LABEL, fmtCents, lookups } from "../format";
import type { EvaluationResult, EventStateView, GrantView, PreferencePreset } from "../types";
import { SubmissionList } from "./MutationStatus";
import type { MutationTracker } from "./useMutations";

const PRESETS: { value: PreferencePreset; hint: string }[] = [
  { value: "balanced", hint: "Weigh time shifts, changes, spend and notifications together." },
  { value: "preserve_order", hint: "Prefer keeping the announced order of activities." },
  { value: "minimize_spend", hint: "Prefer alternatives that add the least committed spend." },
];

function AuthorizationAnswer({
  item,
  view,
  binding,
  tracker,
}: {
  item: AuthorizationItem;
  view: EventStateView;
  binding: ToolBinding;
  tracker: MutationTracker;
}) {
  const look = lookups(view);
  const r = item.request;
  const [reason, setReason] = useState(
    `Approve ${fmtCents(r.requested_value)} committed spending for ${look.resourceLabel(r.resource_id)}`,
  );
  const sending = tracker.isSending("organizer", "update_grant");
  const owner = item.grant?.grant.principal_id ?? r.target_grant_id;
  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (reason.trim().length === 0) return;
    const request = buildToolRequest(
      binding,
      "update_grant",
      {
        target_grant_id: r.target_grant_id,
        max_total_committed_cents: r.requested_value,
        reason: reason.trim(),
      },
      { idempotent: true, expectedRevision: view.revision },
    );
    tracker.submit("organizer", `Approve ${fmtCents(r.requested_value)} for ${owner}`, request);
  };
  return (
    <form className="form authorization" onSubmit={onSubmit}>
      <p>
        <Tag tone="warn" icon="⚑">
          Waiting for you
        </Tag>{" "}
        {r.reason}
      </p>
      <p className="consequence">
        <strong>If you approve:</strong> the committed-spending limit of <Code>{r.target_grant_id}</Code>{" "}
        ({owner}) rises from {fmtCents(r.current_value)} to {fmtCents(r.requested_value)}. The coordinator
        may then commit {look.resourceLabel(r.resource_id)} for candidate <Code>{r.candidate_id}</Code> if it
        still passes every check when applied. This records a new grant version and receipt in the
        sandbox; no real purchase is made.
      </p>
      <label className="field">
        <span>Reason (recorded with the grant change)</span>
        <input value={reason} maxLength={500} onChange={(e) => setReason(e.target.value)} required />
      </label>
      <button type="submit" className="button" disabled={sending || reason.trim().length === 0}>
        {sending ? "Sending approval…" : `Approve: raise the limit to ${fmtCents(r.requested_value)}`}
      </button>
    </form>
  );
}

function RevokeCoordinator({
  grant,
  view,
  binding,
  tracker,
}: {
  grant: GrantView;
  view: EventStateView;
  binding: ToolBinding;
  tracker: MutationTracker;
}) {
  const [confirming, setConfirming] = useState(false);
  const [reason, setReason] = useState("");
  const sending = tracker.isSending("organizer", "update_grant");
  if (grant.revoked) {
    return (
      <p>
        <Tag tone="bad" icon="⊘">
          Revoked
        </Tag>{" "}
        The coordinator grant <Code>{grant.grant.grant_id}</Code> (version {grant.version}) is revoked.
      </p>
    );
  }
  if (!confirming) {
    return (
      <button type="button" className="button danger" onClick={() => setConfirming(true)}>
        Revoke the coordinator grant…
      </button>
    );
  }
  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (reason.trim().length === 0) return;
    const request = buildToolRequest(
      binding,
      "update_grant",
      { target_grant_id: grant.grant.grant_id, revoke: true, reason: reason.trim() },
      { idempotent: true, expectedRevision: view.revision },
    );
    tracker.submit("organizer", "Revoke the coordinator grant", request);
    setConfirming(false);
    setReason("");
  };
  return (
    <form className="form confirm" onSubmit={onSubmit}>
      <p className="consequence">
        <strong>Confirm revocation.</strong> The coordinator agent (<Code>{grant.grant.principal_id}</Code>)
        will be refused every further action under <Code>{grant.grant.grant_id}</Code>: no holds, releases
        or plan changes. Accepted commitments are not erased.
      </p>
      <label className="field">
        <span>Reason (required)</span>
        <input value={reason} maxLength={500} onChange={(e) => setReason(e.target.value)} required autoFocus />
      </label>
      <div className="button-row">
        <button type="submit" className="button danger" disabled={sending || reason.trim().length === 0}>
          Confirm revoke
        </button>
        <button type="button" className="button secondary" onClick={() => setConfirming(false)}>
          Cancel
        </button>
      </div>
    </form>
  );
}

export function OrganizerPanel({
  view,
  session,
  binding,
  tracker,
  track,
  refresh,
}: {
  view: EventStateView;
  session: StoredSession;
  binding: ToolBinding;
  tracker: MutationTracker;
  track: <T>(run: () => Promise<T>) => Promise<T>;
  refresh: () => Promise<EventStateView | null>;
}) {
  const [preset, setPreset] = useState<PreferencePreset>(view.goal.preference_preset);
  const [reason, setReason] = useState("");
  const [evaluating, setEvaluating] = useState(false);
  const [evaluation, setEvaluation] = useState<{ ok: true; result: EvaluationResult } | { ok: false; message: string } | null>(null);
  const sendingGoal = tracker.isSending("organizer", "update_goal");
  const open = authorizationRequests(view).filter((item) => item.state === "open");
  const coordinator = view.grants.find((g) => g.grant.principal_role === "coordinator_agent");
  const look = lookups(view);

  const submitGoal = (event: FormEvent) => {
    event.preventDefault();
    if (reason.trim().length === 0) return;
    const request = buildToolRequest(
      binding,
      "update_goal",
      { preference_preset: preset, reason: reason.trim() },
      { idempotent: true, expectedRevision: view.revision, expectedGoalVersion: view.goal.version },
    );
    tracker.submit("organizer", `Change preference to “${PRESET_LABEL[preset] ?? preset}”`, request);
  };

  const evaluate = async () => {
    setEvaluating(true);
    const request = buildToolRequest(binding, "evaluate_candidates", {}, { expectedGoalVersion: view.goal.version });
    const outcome = await track(() => callTool(session, request));
    if (outcome.kind === "envelope" && outcome.envelope.status === "succeeded" && outcome.envelope.data !== null) {
      setEvaluation({ ok: true, result: outcome.envelope.data as unknown as EvaluationResult });
    } else if (outcome.kind === "envelope") {
      const e = outcome.envelope.error;
      setEvaluation({ ok: false, message: e !== null ? `${e.code}: ${e.message}` : outcome.envelope.status });
    } else {
      setEvaluation({ ok: false, message: outcome.message });
    }
    await track(() => refresh());
    setEvaluating(false);
  };

  const evaluated = evaluation !== null && evaluation.ok ? evaluation.result : null;
  const best = evaluated?.candidates.find((c) => c.candidate_id === evaluated.best_candidate_id);

  return (
    <Section
      id="organizer-panel"
      title="Organizer controls"
      className="panel"
      subtitle="Changes here are recorded as new goal or grant versions with receipts."
    >
      <form className="form" onSubmit={submitGoal}>
        <h3 className="list-heading">Preference</h3>
        <p className="small">
          Current: <strong>{PRESET_LABEL[view.goal.preference_preset] ?? view.goal.preference_preset}</strong> (goal
          version {view.goal.version}). A preference changes ranking only; hard constraints stay.
        </p>
        <fieldset className="field">
          <legend>New preference</legend>
          {PRESETS.map((p) => (
            <label key={p.value} className="radio">
              <input
                type="radio"
                name="preset"
                value={p.value}
                checked={preset === p.value}
                onChange={() => setPreset(p.value)}
              />
              <span>
                <strong>{PRESET_LABEL[p.value]}</strong> <span className="muted small">{p.hint}</span>
              </span>
            </label>
          ))}
        </fieldset>
        <label className="field">
          <span>Reason (required)</span>
          <input value={reason} maxLength={500} onChange={(e) => setReason(e.target.value)} required />
        </label>
        <button
          type="submit"
          className="button"
          disabled={sendingGoal || reason.trim().length === 0 || preset === view.goal.preference_preset}
        >
          {preset === view.goal.preference_preset ? "Already the current preference" : "Change preference"}
        </button>
      </form>

      <div className="form">
        <h3 className="list-heading">Re-rank alternatives</h3>
        <p className="small muted">
          Evaluates the declared alternatives against the current state. Read-only: no hold, spend or
          plan change.
        </p>
        <button type="button" className="button secondary" disabled={evaluating} onClick={() => void evaluate()}>
          {evaluating ? "Evaluating…" : "Evaluate alternatives now"}
        </button>
        {evaluation !== null ? (
          evaluation.ok ? (
            <p className="small">
              Evaluation <Code>{evaluation.result.evaluation_id}</Code> for revision {evaluation.result.revision}:{" "}
              {evaluation.result.evaluated_count} alternatives,{" "}
              {best !== undefined ? <>best ranked “{best.label}” (total {best.objective.total})</> : "none feasible"}.
              The Alternatives card shows the latest stored evaluation.
            </p>
          ) : (
            <p className="small tone-text-bad">Evaluation did not complete: {evaluation.message}</p>
          )
        ) : null}
      </div>

      <div className="form">
        <h3 className="list-heading">Authorization requests</h3>
        {open.length === 0 ? (
          <Empty>No authorization request is waiting.</Empty>
        ) : (
          open.map((item) => (
            <AuthorizationAnswer
              key={item.request.request_id}
              item={item}
              view={view}
              binding={binding}
              tracker={tracker}
            />
          ))
        )}
      </div>

      <div className="form">
        <h3 className="list-heading">Coordinator authority</h3>
        {coordinator === undefined ? (
          <Empty>No coordinator grant is visible.</Empty>
        ) : (
          <>
            <p className="small">
              <Code>{coordinator.grant.grant_id}</Code> v{coordinator.version}: committed{" "}
              {fmtCents(coordinator.committed_used_cents)} of {fmtCents(coordinator.grant.max_total_committed_cents)}, held{" "}
              {fmtCents(coordinator.reserved_used_cents)} of {fmtCents(coordinator.grant.max_total_reserved_cents)};
              resources {coordinator.grant.resource_ids.map(look.resourceLabel).join(", ")}.
            </p>
            <RevokeCoordinator grant={coordinator} view={view} binding={binding} tracker={tracker} />
          </>
        )}
      </div>
      <SubmissionList tracker={tracker} panel="organizer" view={view} />
    </Section>
  );
}
