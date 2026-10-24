// Tracks each logical submission of a mutation from "attempted" to its receipt.
//
// * The ToolRequest (with its idempotency key) is built once per submission and resent
//   unchanged on any retry, so an identical retry can only return the original receipt.
// * A lost response is never retried automatically and never retried with a fresh key: it is
//   shown as "Checking whether this was recorded" until the user checks the action status
//   (get_action_receipt with the original key) or resends the identical request.
// * Success is never inferred from the click or the envelope alone: the panel shows "applied"
//   as confirmed only when a fresh state read contains the applied receipt.
// * Dismissing a submission only hides it. An unresolved one stays known to the tab, so a form
//   can warn about it and an identical observation can reuse its client_record_id.

import { useCallback, useRef, useState } from "react";

import { callTool, lookupReceipt } from "../api";
import type { StoredSession, ToolBinding, ToolCallOutcome } from "../api";
import type { ActionReceipt, EventStateView, ReceiptLookupData, ToolEnvelope, ToolRequest } from "../types";

export type PanelName = "participant" | "organizer";

export interface LookupNote {
  readonly result: "not_found" | "pending" | "failed";
  readonly message: string;
  /** Wall-clock time of the lookup (when the user pressed the control). */
  readonly checkedAt: number;
}

export type SubmissionPhase =
  | { readonly kind: "sending" }
  | {
      readonly kind: "receipt";
      readonly receipt: ActionReceipt;
      readonly replayed: boolean;
      readonly via: "response" | "status_check";
    }
  /** Envelope "rejected" without a durable receipt (authorization, validation, idempotency). */
  | { readonly kind: "refused"; readonly envelope: ToolEnvelope }
  /** HTTP 4xx before execution (session, body validation). Nothing was done. */
  | {
      readonly kind: "not_executed";
      readonly httpStatus: number;
      readonly code: string | null;
      readonly message: string;
    }
  /** The outcome is not established; the original key must be checked. */
  | {
      readonly kind: "unknown";
      readonly message: string;
      readonly checking: boolean;
      readonly lookup: LookupNote | null;
    };

export interface Submission {
  readonly id: string;
  readonly panel: PanelName;
  readonly label: string;
  readonly request: ToolRequest;
  readonly sends: number;
  readonly phase: SubmissionPhase;
  /** Hidden from the panel by the user; the tab still remembers it. */
  readonly dismissed: boolean;
}

export interface TrackerDeps {
  readonly session: StoredSession;
  readonly binding: ToolBinding | null;
  readonly refresh: () => Promise<EventStateView | null>;
  readonly announce: (text: string) => void;
  /** Runs a request while polling is paused. */
  readonly track: <T>(run: () => Promise<T>) => Promise<T>;
}

export interface MutationTracker {
  /** Every submission of this tab, newest first, including dismissed ones. */
  readonly submissions: readonly Submission[];
  submit(panel: PanelName, label: string, request: ToolRequest): void;
  checkStatus(id: string): void;
  resend(id: string): void;
  dismiss(id: string): void;
  isSending(panel: PanelName, tool: string): boolean;
}

function receiptAnnouncement(label: string, receipt: ActionReceipt, fresh: EventStateView | null): string {
  if (receipt.status === "rejected") {
    return `${label}: rejected. ${receipt.error_code ?? ""} ${receipt.error_message ?? ""}`.trim();
  }
  if (receipt.status === "unknown") return `${label}: unresolved. The outcome is not established.`;
  const confirmed = fresh?.receipts.some((r) => r.receipt_id === receipt.receipt_id && r.status === "applied");
  return confirmed === true
    ? `${label}: applied and confirmed in state revision ${fresh?.revision ?? receipt.revision_after}.`
    : `${label}: the receipt says applied, but a fresh state read does not show it yet.`;
}

let localCounter = 0;

export function useMutationTracker(deps: TrackerDeps): MutationTracker {
  const [submissions, setSubmissions] = useState<readonly Submission[]>([]);
  const ref = useRef<readonly Submission[]>([]);
  const depsRef = useRef(deps);
  depsRef.current = deps;

  const update = useCallback((id: string, change: (s: Submission) => Submission) => {
    const next = ref.current.map((s) => (s.id === id ? change(s) : s));
    ref.current = next;
    setSubmissions(next);
  }, []);

  const settle = useCallback(
    async (id: string, outcome: ToolCallOutcome, via: "response" | "status_check") => {
      const d = depsRef.current;
      const label = ref.current.find((s) => s.id === id)?.label ?? "Action";
      if (outcome.kind === "no_response") {
        update(id, (s) => ({
          ...s,
          phase: { kind: "unknown", message: outcome.message, checking: false, lookup: null },
        }));
        d.announce(`${label}: no response. Checking whether this was recorded is needed.`);
        return;
      }
      if (outcome.kind === "not_executed") {
        update(id, (s) => ({
          ...s,
          phase: {
            kind: "not_executed",
            httpStatus: outcome.httpStatus,
            code: outcome.code,
            message: outcome.message,
          },
        }));
        d.announce(`${label}: not executed. ${outcome.message}`);
        return;
      }
      const envelope = outcome.envelope;
      if (envelope.receipt !== null) {
        const receipt = envelope.receipt;
        update(id, (s) => ({
          ...s,
          phase: { kind: "receipt", receipt, replayed: envelope.replayed_receipt, via },
        }));
        const fresh = await d.track(() => d.refresh());
        d.announce(receiptAnnouncement(label, receipt, fresh));
        return;
      }
      if (envelope.status === "rejected") {
        update(id, (s) => ({ ...s, phase: { kind: "refused", envelope } }));
        d.announce(
          `${label}: refused before a receipt was recorded. ${envelope.error?.code ?? ""} ${
            envelope.error?.message ?? ""
          }`.trim(),
        );
        await d.track(() => d.refresh());
        return;
      }
      const message =
        envelope.error !== null
          ? `${envelope.error.code}: ${envelope.error.message}`
          : `The server answered "${envelope.status}" without a receipt.`;
      update(id, (s) => ({ ...s, phase: { kind: "unknown", message, checking: false, lookup: null } }));
      d.announce(`${label}: outcome not established. ${message}`);
    },
    [update],
  );

  const send = useCallback(
    async (id: string) => {
      const d = depsRef.current;
      const submission = ref.current.find((s) => s.id === id);
      if (submission === undefined) return;
      update(id, (s) => ({ ...s, sends: s.sends + 1, phase: { kind: "sending" } }));
      const outcome = await d.track(() => callTool(d.session, submission.request));
      await settle(id, outcome, "response");
    },
    [settle, update],
  );

  const submit = useCallback(
    (panel: PanelName, label: string, request: ToolRequest) => {
      localCounter += 1;
      const submission: Submission = {
        id: `sub-${localCounter}`,
        panel,
        label,
        request,
        sends: 0,
        phase: { kind: "sending" },
        dismissed: false,
      };
      ref.current = [submission, ...ref.current];
      setSubmissions(ref.current);
      void send(submission.id);
    },
    [send],
  );

  const checkStatus = useCallback(
    (id: string) => {
      const d = depsRef.current;
      const submission = ref.current.find((s) => s.id === id);
      const key = submission?.request.idempotency_key;
      if (submission === undefined || submission.phase.kind !== "unknown") return;
      if (key === undefined || key === null || d.binding === null) return;
      const binding = d.binding;
      update(id, (s) =>
        s.phase.kind === "unknown" ? { ...s, phase: { ...s.phase, checking: true } } : s,
      );
      void (async () => {
        const outcome = await d.track(() => lookupReceipt(d.session, binding, key));
        let note: LookupNote;
        if (outcome.kind === "envelope" && outcome.envelope.status === "succeeded") {
          const data = outcome.envelope.data as ReceiptLookupData | null;
          if (data !== null && data.lookup_status === "found" && data.receipt !== null) {
            await settle(id, { kind: "envelope", envelope: { ...outcome.envelope, receipt: data.receipt } }, "status_check");
            return;
          }
          note =
            data !== null && data.lookup_status === "pending"
              ? { result: "pending", message: "The server is still processing this request.", checkedAt: Date.now() }
              : {
                  result: "not_found",
                  message: "No receipt exists for this request's key.",
                  checkedAt: Date.now(),
                };
        } else {
          const message =
            outcome.kind === "envelope"
              ? outcome.envelope.error !== null
                ? `${outcome.envelope.error.code}: ${outcome.envelope.error.message}`
                : `Lookup answered "${outcome.envelope.status}".`
              : outcome.message;
          note = { result: "failed", message: `The status check did not complete: ${message}`, checkedAt: Date.now() };
        }
        update(id, (s) =>
          s.phase.kind === "unknown"
            ? { ...s, phase: { ...s.phase, checking: false, lookup: note } }
            : s,
        );
        depsRef.current.announce(`Status check: ${note.message}`);
      })();
    },
    [settle, update],
  );

  const resend = useCallback(
    (id: string) => {
      const submission = ref.current.find((s) => s.id === id);
      if (submission === undefined || submission.phase.kind !== "unknown") return;
      void send(id);
    },
    [send],
  );

  const dismiss = useCallback((id: string) => update(id, (s) => ({ ...s, dismissed: true })), [update]);

  const isSending = useCallback(
    (panel: PanelName, tool: string) =>
      submissions.some((s) => s.panel === panel && s.request.tool === tool && s.phase.kind === "sending"),
    [submissions],
  );

  return { submissions, submit, checkStatus, resend, dismiss, isSending };
}
