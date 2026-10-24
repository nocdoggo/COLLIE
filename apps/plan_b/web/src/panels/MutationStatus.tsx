import { EPISODE_RESET_MESSAGE } from "../api";
import { EvidenceCard } from "../components/EvidenceCard";
import { Code, StatusBadge } from "../components/ui";
import { appliedWithoutChange } from "../format";
import type { EventStateView } from "../types";
import { receiptBadge, receiptConfirmed } from "./submissions";
import type { MutationTracker, Submission } from "./useMutations";

function Body({ submission, view, tracker }: { submission: Submission; view: EventStateView; tracker: MutationTracker }) {
  const phase = submission.phase;
  switch (phase.kind) {
    case "sending":
      return (
        <p className="status-line tone-text-info">
          <span aria-hidden="true">⧗ </span>
          Attempted. Waiting for the server&apos;s receipt…
        </p>
      );
    case "receipt": {
      const r = phase.receipt;
      return (
        <>
          <p className="status-line">
            <StatusBadge label={receiptBadge(r, view)} />{" "}
            {r.status === "applied"
              ? receiptConfirmed(r, view)
                ? appliedWithoutChange(r)
                  ? `Nothing new was recorded: receipt ${r.receipt_id} changed nothing and the state stays at revision ${r.revision_after}.`
                  : `Confirmed in the current state: receipt ${r.receipt_id}, revision ${r.revision_before} → ${r.revision_after}.`
                : `The receipt ${r.receipt_id} says applied; it counts as done once a fresh state read shows it.`
              : null}
            {r.status === "rejected"
              ? `${r.error_code ?? ""}${r.error_message !== null ? `: ${r.error_message}` : ""}. Nothing changed (revision stays ${r.revision_before}).`
              : null}
            {r.status === "unknown" ? "The server recorded an unresolved outcome." : null}
          </p>
          <p className="muted small">{r.summary}</p>
          {phase.replayed ? (
            <p className="muted small">This is the original receipt of an identical earlier request.</p>
          ) : null}
          {phase.via === "status_check" ? (
            <p className="muted small">Found by checking the action status with the original key.</p>
          ) : null}
          <EvidenceCard title="Receipt (JSON)" value={r} hint={r.receipt_id} />
        </>
      );
    }
    case "refused":
      return (
        <p className="status-line tone-text-bad">
          <span aria-hidden="true">✖ </span>
          Refused before a receipt was recorded:{" "}
          {phase.envelope.error !== null
            ? `${phase.envelope.error.code}: ${phase.envelope.error.message}`
            : phase.envelope.status}
          . Nothing changed.
        </p>
      );
    case "not_executed":
      return (
        <p className="status-line tone-text-bad">
          <span aria-hidden="true">✖ </span>
          Not executed (HTTP {phase.httpStatus}): {phase.message}.
          {phase.code === "EPISODE_CLOSED"
            ? ` ${EPISODE_RESET_MESSAGE}`
            : phase.httpStatus === 401
              ? " This tab's session is no longer valid; sign in again."
              : ""}
        </p>
      );
    case "unknown":
      return (
        <>
          <p className="status-line tone-text-warn">
            <span aria-hidden="true">? </span>
            <strong>Checking whether this was recorded.</strong> {phase.message} The request may or may
            not have been executed; it is not resent automatically.
          </p>
          {phase.lookup !== null ? (
            <p className="small">
              Last check ({new Date(phase.lookup.checkedAt).toLocaleTimeString()} wall clock):{" "}
              {phase.lookup.message}
            </p>
          ) : null}
          <div className="button-row">
            <button
              type="button"
              className="button"
              disabled={phase.checking}
              onClick={() => tracker.checkStatus(submission.id)}
            >
              {phase.checking ? "Checking action status…" : "Check action status"}
            </button>
            {phase.lookup !== null && phase.lookup.result !== "pending" ? (
              <button
                type="button"
                className="button secondary"
                disabled={phase.checking}
                onClick={() => tracker.resend(submission.id)}
              >
                Send the identical request again (same key)
              </button>
            ) : null}
          </div>
        </>
      );
  }
}

/** One submission's lifecycle: attempted → receipt status → confirmed by a fresh state read. */
export function MutationStatus({
  submission,
  view,
  tracker,
}: {
  submission: Submission;
  view: EventStateView;
  tracker: MutationTracker;
}) {
  const settled = submission.phase.kind !== "sending" && !(submission.phase.kind === "unknown" && submission.phase.checking);
  return (
    <li className={`submission phase-${submission.phase.kind}`}>
      <p className="submission-head">
        <strong>{submission.label}</strong>{" "}
        <span className="muted small">
          {submission.request.tool} · key <Code>{submission.request.idempotency_key ?? "none"}</Code>
          {submission.sends > 1 ? ` · sent ${submission.sends} times with the same key` : ""}
        </span>
      </p>
      <Body submission={submission} view={view} tracker={tracker} />
      {settled ? (
        <button type="button" className="link-button small" onClick={() => tracker.dismiss(submission.id)}>
          {submission.phase.kind === "unknown"
            ? "Stop tracking (it may still have been recorded; see the action history)"
            : "Dismiss"}
        </button>
      ) : null}
    </li>
  );
}

export function SubmissionList({
  tracker,
  panel,
  view,
}: {
  tracker: MutationTracker;
  panel: Submission["panel"];
  view: EventStateView;
}) {
  const items = tracker.submissions.filter((s) => s.panel === panel && !s.dismissed);
  if (items.length === 0) return null;
  return (
    <div className="submissions">
      <h3 className="list-heading">Your submissions in this tab</h3>
      <ol>
        {items.map((s) => (
          <MutationStatus key={s.id} submission={s} view={view} tracker={tracker} />
        ))}
      </ol>
    </div>
  );
}
