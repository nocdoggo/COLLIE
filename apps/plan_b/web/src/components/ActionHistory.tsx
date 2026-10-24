import { appliedWithoutChange, compareIso, fmtSignedCents, fmtTime, receiptLabel } from "../format";
import type { ActionReceipt, EventStateView, JsonValue } from "../types";
import { EvidenceCard } from "./EvidenceCard";
import { Code, Empty, Section, StatusBadge, When, domId } from "./ui";

function short(value: JsonValue): string {
  if (value === null) return "none";
  if (typeof value === "string") return value;
  const text = JSON.stringify(value);
  return text.length > 80 ? `${text.slice(0, 77)}…` : text;
}

/** The card's tone class: a no-change ("duplicate") receipt is neutral, never the green applied. */
export function receiptClass(receipt: ActionReceipt): string {
  return `receipt ${appliedWithoutChange(receipt) ? "receipt-no-change" : `receipt-${receipt.status}`}`;
}

function ReceiptItem({ receipt, view }: { receipt: ActionReceipt; view: EventStateView }) {
  const tz = view.timezone;
  const referencedBy = view.decisions.filter((d) => d.receipt_refs.includes(receipt.receipt_id));
  return (
    <li className={receiptClass(receipt)} id={domId("rcpt", receipt.receipt_id)} tabIndex={-1}>
      <p className="receipt-head">
        <StatusBadge label={receiptLabel(receipt)} /> <strong>{receipt.tool}</strong>{" "}
        <span className="muted">
          at <When iso={receipt.executed_at} text={fmtTime(receipt.executed_at, tz)} /> by{" "}
          <Code>{receipt.actor_id}</Code> ({receipt.actor_role.replace(/_/g, " ")}) · revision{" "}
          {receipt.revision_before} → {receipt.revision_after}
        </span>
      </p>
      <p>{receipt.summary}</p>
      {receipt.status === "rejected" ? (
        <p className="tone-text-bad">
          <strong>{receipt.error_code}</strong>
          {receipt.error_message !== null ? `: ${receipt.error_message}` : ""}. Nothing changed; the
          revision stayed {receipt.revision_before}.
        </p>
      ) : null}
      {receipt.status === "unknown" ? (
        <p className="tone-text-warn">
          The outcome of this request is not established.
          {receipt.error_code !== null ? ` ${receipt.error_code}` : ""}
          {receipt.error_message !== null ? `: ${receipt.error_message}` : ""}
        </p>
      ) : null}
      {appliedWithoutChange(receipt) ? (
        <p className="small">
          No change: this receipt has no transition of its own. The server returned an existing
          record, and the revision stayed {receipt.revision_before}.
        </p>
      ) : null}
      {receipt.status === "applied" ? (
        <p className="muted small">
          Committed {fmtSignedCents(receipt.committed_delta_cents)} · reserved{" "}
          {fmtSignedCents(receipt.reserved_delta_cents)}
          {receipt.related_plan_id !== null ? <> · plan <Code>{receipt.related_plan_id}</Code></> : null}
          {receipt.constraint_report_ref !== null ? (
            <> · report <Code>{receipt.constraint_report_ref}</Code></>
          ) : null}
        </p>
      ) : null}
      {receipt.state_changes.length > 0 ? (
        <ul className="state-changes small">
          {receipt.state_changes.map((c, index) => (
            <li key={`${c.entity_id}-${c.field}-${index}`}>
              <Code>{c.entity_id}</Code> {c.field}: {short(c.before)} → {short(c.after)}
            </li>
          ))}
        </ul>
      ) : null}
      <p className="muted small">
        Requested at <When iso={receipt.requested_at} text={fmtTime(receipt.requested_at, tz)} /> · key{" "}
        <Code>{receipt.request_idempotency_key}</Code> · grant <Code>{receipt.grant_id}</Code> v
        {receipt.grant_version}
        {referencedBy.length > 0 ? <> · cited by {referencedBy.length} decision(s)</> : null}
      </p>
      <EvidenceCard title="Receipt evidence (JSON)" value={receipt} hint={receipt.receipt_id} />
    </li>
  );
}

function ReceiptGroup({
  id,
  title,
  receipts,
  view,
  empty,
}: {
  id: string;
  title: string;
  receipts: ActionReceipt[];
  view: EventStateView;
  empty: string;
}) {
  return (
    <div className="history-group" aria-labelledby={`${id}-heading`} role="group">
      <h3 className="list-heading" id={`${id}-heading`}>
        {title} ({receipts.length})
      </h3>
      {receipts.length === 0 ? (
        <Empty>{empty}</Empty>
      ) : (
        <ol className="receipts">
          {receipts.map((r) => (
            <ReceiptItem key={r.receipt_id} receipt={r} view={view} />
          ))}
        </ol>
      )}
    </div>
  );
}

/**
 * Action history from the state read only. Success is shown solely by an applied receipt in
 * this state; a click, a decision or a toast never counts.
 */
export function ActionHistory({ view }: { view: EventStateView }) {
  const tz = view.timezone;
  const newestFirst = [...view.receipts].sort(
    (a, b) => compareIso(b.executed_at, a.executed_at) || b.revision_after - a.revision_after,
  );
  const applied = newestFirst.filter((r) => r.status === "applied");
  const rejected = newestFirst.filter((r) => r.status === "rejected");
  const unknown = newestFirst.filter((r) => r.status === "unknown");
  const attempts = [...view.attempts].reverse();
  return (
    <Section
      id="action-history"
      title="Action history"
      subtitle="From the latest state read. Each receipt links to its evidence."
    >
      <div className="history-grid">
        <ReceiptGroup id="applied" title="Applied" receipts={applied} view={view} empty="No applied actions." />
        <ReceiptGroup id="rejected" title="Rejected" receipts={rejected} view={view} empty="No rejected actions." />
        <ReceiptGroup
          id="unresolved"
          title="Unresolved (unknown)"
          receipts={unknown}
          view={view}
          empty="No unresolved actions."
        />
        <div className="history-group" role="group" aria-labelledby="attempts-heading">
          <h3 className="list-heading" id="attempts-heading">
            Attempted without receipt ({attempts.length})
          </h3>
          {attempts.length === 0 ? (
            <Empty>No attempts ended before a receipt.</Empty>
          ) : (
            <ol className="receipts">
              {attempts.map((a) => (
                <li key={a.call_id} className="receipt receipt-attempt">
                  <p className="receipt-head">
                    <span className="badge tone-bad">
                      <span className="badge-icon" aria-hidden="true">
                        ✖
                      </span>
                      Refused ({a.envelope_status})
                    </span>{" "}
                    <strong>{a.tool}</strong>{" "}
                    <span className="muted">
                      {a.at !== null ? (
                        <>
                          at <When iso={a.at} text={fmtTime(a.at, tz)} />{" "}
                        </>
                      ) : null}
                      {a.actor_id !== null ? <>by <Code>{a.actor_id}</Code></> : "by an unauthenticated caller"}
                    </span>
                  </p>
                  <p className="small">
                    {a.error_code ?? "No error code"} · call <Code>{a.call_id}</Code>
                  </p>
                </li>
              ))}
            </ol>
          )}
        </div>
      </div>
    </Section>
  );
}
