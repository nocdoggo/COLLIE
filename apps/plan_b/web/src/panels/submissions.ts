// What a panel may claim about its own submissions. Kept free of React so tests can check it.

import { APPLIED_UNCONFIRMED_LABEL, appliedWithoutChange, receiptLabel } from "../format";
import type { StatusLabel } from "../format";
import type { ActionReceipt, EventStateView, JsonObject } from "../types";
import type { PanelName, Submission } from "./useMutations";

/** An applied receipt counts as success only once a fresh state read contains it. */
export function receiptConfirmed(receipt: ActionReceipt, view: EventStateView): boolean {
  return (
    receipt.status === "applied" &&
    view.receipts.some((r) => r.receipt_id === receipt.receipt_id && r.status === "applied")
  );
}

/**
 * The badge for a submission's receipt: green "Applied" only after that confirmation, and never
 * for an applied receipt that changed nothing (a duplicate).
 */
export function receiptBadge(receipt: ActionReceipt, view: EventStateView): StatusLabel {
  if (receipt.status === "applied" && !receiptConfirmed(receipt, view)) return APPLIED_UNCONFIRMED_LABEL;
  return receiptLabel(receipt);
}

/** The live-region announcement once a receipt is in hand and a fresh state read was tried. */
export function receiptAnnouncement(label: string, receipt: ActionReceipt, fresh: EventStateView | null): string {
  if (receipt.status === "rejected") {
    return `${label}: rejected. ${receipt.error_code ?? ""} ${receipt.error_message ?? ""}`.trim();
  }
  if (receipt.status === "unknown") return `${label}: unresolved. The outcome is not established.`;
  if (fresh === null || !receiptConfirmed(receipt, fresh)) {
    return `${label}: the receipt says applied, but a fresh state read does not show it yet.`;
  }
  if (appliedWithoutChange(receipt)) {
    return `${label}: applied, no change (duplicate). Nothing new was recorded; the state stays at revision ${receipt.revision_after}.`;
  }
  return `${label}: applied and confirmed in state revision ${fresh.revision}.`;
}

/**
 * Shown submissions of one tool whose outcome is still open: no receipt, and no status check
 * has shown that the server has none for its key. A form warns before a new one is sent.
 */
export function unresolvedSubmissions(
  submissions: readonly Submission[],
  panel: PanelName,
  tool: string,
): Submission[] {
  return submissions.filter(
    (s) =>
      !s.dismissed &&
      s.panel === panel &&
      s.request.tool === tool &&
      s.phase.kind === "unknown" &&
      s.phase.lookup?.result !== "not_found",
  );
}

/** The fields that make two observation submissions the same observation. */
export interface ObservationContent {
  readonly text: string;
  readonly entity_id: string | null;
  readonly kind: "notice" | "resource_offer";
}

function contentOf(args: JsonObject): ObservationContent | null {
  const { text, entity_id: entity, kind } = args;
  if (typeof text !== "string") return null;
  return {
    text,
    entity_id: typeof entity === "string" ? entity : null,
    kind: kind === "resource_offer" ? "resource_offer" : "notice",
  };
}

/**
 * The client_record_id of an earlier submission of the same observation whose outcome never
 * became known (dismissed ones included). Reusing it lets the server store the observation once
 * even if the earlier request was recorded after all.
 */
export function reusableRecordId(
  submissions: readonly Submission[],
  content: ObservationContent,
): string | null {
  for (const s of submissions) {
    if (s.request.tool !== "submit_observation" || s.phase.kind !== "unknown") continue;
    const earlier = contentOf(s.request.arguments);
    const id = s.request.arguments.client_record_id;
    if (
      earlier !== null &&
      typeof id === "string" &&
      earlier.text === content.text &&
      earlier.entity_id === content.entity_id &&
      earlier.kind === content.kind
    ) {
      return id;
    }
  }
  return null;
}

export function observationArguments(content: ObservationContent, clientRecordId: string): JsonObject {
  return {
    text: content.text,
    kind: content.kind,
    ...(content.entity_id !== null ? { entity_id: content.entity_id } : {}),
    client_record_id: clientRecordId,
  };
}
