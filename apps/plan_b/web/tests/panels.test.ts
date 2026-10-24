// Role and moderator panels: what a submission may claim (review web-2, web-4), check-in
// availability (web-7), reset confirmation (web-5), stamped moderator results, the
// reset-episode message for 401 EPISODE_CLOSED, applied receipts that changed nothing
// (M1-INV-03), and join links that never show a whole code (C1).

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import {
  ApiError,
  EPISODE_RESET_MESSAGE,
  buildToolRequest,
  errorCodeOf,
  newClientRecordId,
  sessionEndMessage,
} from "../src/api.ts";
import type { StoredSession } from "../src/api.ts";
import { ActionHistory, receiptClass } from "../src/components/ActionHistory.tsx";
import { ChangeSummary } from "../src/components/ChangeSummary.tsx";
import { JoinLink, ModeratorPanel } from "../src/panels/ModeratorPanel.tsx";
import { MutationStatus } from "../src/panels/MutationStatus.tsx";
import { ParticipantPanel } from "../src/panels/ParticipantPanel.tsx";
import { checkInArguments, endChoices } from "../src/panels/checkInForm.ts";
import {
  actionHeadline,
  clockOutcome,
  isEarlierResult,
  joinCodePreview,
  knownActiveEpisode,
  policyOutcome,
  resetNeedsConfirmation,
} from "../src/panels/moderatorState.ts";
import {
  observationArguments,
  receiptAnnouncement,
  receiptBadge,
  reusableRecordId,
  unresolvedSubmissions,
} from "../src/panels/submissions.ts";
import type { MutationTracker, Submission, SubmissionPhase } from "../src/panels/useMutations.ts";
import type { EventStateView, ToolRequest } from "../src/types.ts";
import { local, makeReceipt, makeView, textOf } from "./support/view.ts";

const BINDING = { event_id: "evt_demo", grant_id: "grant_participant_presenter" };
const IDENTIFIER = /^[A-Za-z0-9_.:-]{1,128}$/;
const UNKNOWN: SubmissionPhase = { kind: "unknown", message: "No response within 20 s.", checking: false, lookup: null };

function submission(request: ToolRequest, phase: SubmissionPhase, extra: Partial<Submission> = {}): Submission {
  return { id: "sub-1", panel: "participant", label: "Update", request, sends: 1, phase, dismissed: false, ...extra };
}

function tracker(submissions: readonly Submission[]): MutationTracker {
  return {
    submissions,
    submit: () => undefined,
    checkStatus: () => undefined,
    resend: () => undefined,
    dismiss: () => undefined,
    isSending: () => false,
  };
}

function observationRequest(text: string, recordId = newClientRecordId()): ToolRequest {
  return buildToolRequest(
    BINDING,
    "submit_observation",
    observationArguments({ text, entity_id: null, kind: "notice" }, recordId),
    { idempotent: true },
  );
}

// ------------------------------------------------------------------ web-4: applied receipts

function statusHtml(view: EventStateView, phase: SubmissionPhase): string {
  const request = buildToolRequest(BINDING, "check_in", { resource_id: "presenter" }, { idempotent: true });
  return renderToStaticMarkup(
    createElement(MutationStatus, { submission: submission(request, phase), view, tracker: tracker([]) }),
  );
}

test("an applied receipt is neutral until a fresh state read contains it", () => {
  const receipt = makeReceipt();
  const phase: SubmissionPhase = { kind: "receipt", receipt, replayed: false, via: "response" };
  const pending = statusHtml(makeView(), phase);
  assert.ok(textOf(pending).includes("⧗ Applied — confirming in a fresh state read"), textOf(pending));
  assert.ok(!pending.includes("badge tone-ok"));

  const confirmed = statusHtml(makeView({ receipts: [receipt] }), phase);
  assert.ok(textOf(confirmed).includes("✔ Applied Confirmed in the current state"));
  assert.ok(confirmed.includes("badge tone-ok"));

  assert.equal(receiptBadge(receipt, makeView()).tone, "neutral");
  assert.equal(receiptBadge(makeReceipt({ status: "rejected", error_code: "SCOPE_VIOLATION" }), makeView()).text, "Rejected");
});

test("a 401 EPISODE_CLOSED submission says the episode was reset", () => {
  const html = statusHtml(makeView(), {
    kind: "not_executed",
    httpStatus: 401,
    code: "EPISODE_CLOSED",
    message: "EPISODE_CLOSED: this episode has been reset",
  });
  assert.ok(textOf(html).includes(EPISODE_RESET_MESSAGE));
  assert.ok(!textOf(html).includes("sign in again"));
});

// ------------------------------------------------------------------ web-2: observations

test("every observation request carries a valid client_record_id in its frozen request", () => {
  const request = observationRequest("Presenter here: I am at the side door.");
  const id = request.arguments.client_record_id;
  assert.equal(typeof id, "string");
  assert.match(id as string, IDENTIFIER);
  assert.ok(Object.isFrozen(request));
  assert.notEqual(newClientRecordId(), newClientRecordId());
});

test("an identical observation after an unknown outcome reuses the earlier record id", () => {
  const earlier = observationRequest("Presenter here: I am at the side door.", "web-obs-earlier");
  const same = { text: "Presenter here: I am at the side door.", entity_id: null, kind: "notice" } as const;
  // Still unresolved, or dismissed without an answer: the server must see the same record id.
  assert.equal(reusableRecordId([submission(earlier, UNKNOWN)], same), "web-obs-earlier");
  assert.equal(reusableRecordId([submission(earlier, UNKNOWN, { dismissed: true })], same), "web-obs-earlier");
  // Different content, or an earlier one with a known outcome, is a new logical observation.
  assert.equal(reusableRecordId([submission(earlier, UNKNOWN)], { ...same, text: "Now inside." }), null);
  assert.equal(reusableRecordId([submission(earlier, UNKNOWN)], { ...same, entity_id: "projector" }), null);
  const recorded: SubmissionPhase = { kind: "receipt", receipt: makeReceipt(), replayed: false, via: "response" };
  assert.equal(reusableRecordId([submission(earlier, recorded)], same), null);
});

test("an unresolved observation blocks a new one until checked or dismissed", () => {
  const earlier = observationRequest("Presenter here: I am at the side door.");
  assert.equal(unresolvedSubmissions([submission(earlier, UNKNOWN)], "participant", "submit_observation").length, 1);
  const notFound: SubmissionPhase = {
    ...UNKNOWN,
    lookup: { result: "not_found", message: "No receipt exists for this request's key.", checkedAt: 0 },
  };
  assert.equal(unresolvedSubmissions([submission(earlier, notFound)], "participant", "submit_observation").length, 0);
  const pending: SubmissionPhase = { ...UNKNOWN, lookup: { result: "failed", message: "x", checkedAt: 0 } };
  assert.equal(unresolvedSubmissions([submission(earlier, pending)], "participant", "submit_observation").length, 1);
  assert.equal(
    unresolvedSubmissions([submission(earlier, UNKNOWN, { dismissed: true })], "participant", "submit_observation")
      .length,
    0,
  );
});

test("the update form warns about an unresolved earlier update", () => {
  const earlier = observationRequest("Presenter here: I am at the side door.");
  const render = (subs: readonly Submission[]) =>
    textOf(
      renderToStaticMarkup(
        createElement(ParticipantPanel, { view: makeView(), binding: BINDING, tracker: tracker(subs) }),
      ),
    );
  const warned = render([submission(earlier, UNKNOWN)]);
  assert.ok(
    warned.includes("An earlier update is unresolved: “Presenter here: I am at the side door.”"),
    warned,
  );
  assert.ok(warned.includes("Use Check action status on it"));
  assert.ok(!render([]).includes("An earlier update is unresolved"));
});

// ------------------------------------------------------------------ web-7: availability

test("a chosen 'available until' time that has passed blocks the check-in", () => {
  const blocked = checkInArguments("presenter", local("16:45"), local("16:50"));
  assert.deepEqual(blocked, { ok: false, passedEnd: local("16:45") });
  assert.deepEqual(checkInArguments("presenter", local("16:50"), local("16:50")), {
    ok: false,
    passedEnd: local("16:50"),
  });
  assert.deepEqual(checkInArguments("presenter", local("17:00"), local("16:50")), {
    ok: true,
    args: { resource_id: "presenter", available: { start: local("16:50"), end: local("17:00") } },
  });
  assert.deepEqual(checkInArguments("presenter", "", local("16:50")), { ok: true, args: { resource_id: "presenter" } });
  // The choices themselves start after the clock, so a passed choice can only be a stale one.
  const choices = endChoices(makeView({ clock: local("16:50") }));
  assert.equal(choices[0], local("16:55"));
  assert.equal(choices[choices.length - 1], local("18:00"));
});

// ------------------------------------------------------------------ web-5: reset confirmation

test("reset asks for confirmation whenever an episode might be active", () => {
  const active = makeView();
  const closed = makeView({ episode_status: "closed" });
  assert.equal(resetNeedsConfirmation("ep_1", null), true);
  assert.equal(resetNeedsConfirmation(undefined, null), true, "an unanswered or failed read is 'maybe'");
  assert.equal(resetNeedsConfirmation(null, active), true, "the board's own state is evidence");
  assert.equal(resetNeedsConfirmation(null, closed), false);
  assert.equal(resetNeedsConfirmation(null, null), false);
  assert.equal(knownActiveEpisode(undefined, active), "ep_test");
  assert.equal(knownActiveEpisode("ep_1", active), "ep_1");
  assert.equal(knownActiveEpisode(undefined, closed), null);
});

test("before the current-episode read answers, the load button is the guarded reset", () => {
  const session: StoredSession = {
    token: "t",
    role: "moderator",
    principal_id: "moderator",
    display_name: null,
    episode_id: null,
    event_id: null,
    grant_id: null,
    expires_wall: null,
  };
  const html = renderToStaticMarkup(
    createElement(ModeratorPanel, {
      session,
      view: makeView(),
      track: (run) => run(),
      refresh: async () => null,
      announce: () => undefined,
    }),
  );
  const text = textOf(html);
  assert.ok(text.includes("Reset: load a clean episode…"), text);
  assert.ok(!text.includes("Load episode"));
});

// ------------------------------------------------------------------ moderator results

test("moderator results name the action and the time it ran", () => {
  const tz = "America/New_York";
  const ran = { action: "+1 min", ranAt: local("16:40") };
  assert.equal(
    actionHeadline(ran, clockOutcome(local("16:41"), 3, tz), tz),
    "+1 min at 16:40 → clock 16:41, revision 3",
  );
  assert.equal(actionHeadline({ action: "Export", ranAt: null }, "trace written", tz), "Export → trace written");
  assert.equal(clockOutcome(undefined, undefined, tz), "finished");
  const run = {
    policy_id: "rules/1.0.0",
    status: "waiting",
    decisions: [],
    tool_calls: 1,
    wait_until: local("16:50"),
    note: "",
  } as const;
  assert.equal(
    actionHeadline({ action: "Policy run", ranAt: local("16:41") }, policyOutcome(run, tz), tz),
    "Policy run at 16:41 → waiting after 1 tool call, until 16:50",
  );
  assert.equal(isEarlierResult(3, makeView({ revision: 5 })), true);
  assert.equal(isEarlierResult(5, makeView({ revision: 5 })), false);
});

// ------------------------------------------------------------------ EPISODE_CLOSED

test("a 401 EPISODE_CLOSED ends the session with the reset message", () => {
  const body = { detail: { code: "EPISODE_CLOSED", message: "this episode was reset; ask for a new link" } };
  const error = new ApiError(401, "EPISODE_CLOSED: this episode was reset", body);
  assert.equal(error.code, "EPISODE_CLOSED");
  assert.equal(sessionEndMessage(error.code, error.message), EPISODE_RESET_MESSAGE);
  assert.equal(EPISODE_RESET_MESSAGE, "This episode was reset; ask the moderator for a new link.");
  assert.equal(
    sessionEndMessage("SESSION_INVALID", "session is unknown or revoked"),
    "This tab's session is no longer valid: session is unknown or revoked",
  );
  assert.equal(errorCodeOf({ error: { code: "EPISODE_CLOSED", message: "m" } }), "EPISODE_CLOSED");
  assert.equal(errorCodeOf({ detail: "plain" }), null);
  assert.equal(errorCodeOf("text"), null);
});

// ------------------------------------------------------------------ M1-INV-03: duplicates

const RECORDED = makeReceipt({
  receipt_id: "rcpt_0001",
  tool: "submit_observation",
  revision_before: 3,
  revision_after: 4,
  state_changes: [{ entity_id: "obs_0001", field: "observation", before: null, after: "recorded" }],
  summary: "Recorded observation obs_0001",
});
const DUPLICATE = makeReceipt({
  receipt_id: "rcpt_0002",
  tool: "submit_observation",
  request_idempotency_key: "web-submit_observation-2",
  revision_before: 4,
  revision_after: 4,
  state_changes: [],
  summary: "Duplicate of obs_0001; the existing record was returned and nothing changed",
});

test("a confirmed receipt that changed nothing is announced as no change, not as a confirmed revision", () => {
  const fresh = makeView({ revision: 4, receipts: [RECORDED, DUPLICATE] });
  const said = receiptAnnouncement("Update", DUPLICATE, fresh);
  assert.equal(
    said,
    "Update: applied, no change (duplicate). Nothing new was recorded; the state stays at revision 4.",
  );
  assert.ok(!said.includes("confirmed in state revision"));
  // A receipt that did change state keeps the confirmed wording.
  assert.equal(receiptAnnouncement("Update", RECORDED, fresh), "Update: applied and confirmed in state revision 4.");
  // Until a fresh read shows it, a duplicate is no more confirmed than any other receipt.
  assert.equal(
    receiptAnnouncement("Update", DUPLICATE, makeView({ revision: 4 })),
    "Update: the receipt says applied, but a fresh state read does not show it yet.",
  );
  assert.equal(
    receiptAnnouncement("Update", DUPLICATE, null),
    "Update: the receipt says applied, but a fresh state read does not show it yet.",
  );
});

test("the submission status of a duplicate never shows a green Applied", () => {
  const view = makeView({ revision: 4, receipts: [RECORDED, DUPLICATE] });
  const phase: SubmissionPhase = { kind: "receipt", receipt: DUPLICATE, replayed: false, via: "response" };
  const request = observationRequest("Presenter here: I am at the side door.", "web-obs-1");
  const html = renderToStaticMarkup(
    createElement(MutationStatus, { submission: submission(request, phase), view, tracker: tracker([]) }),
  );
  const text = textOf(html);
  assert.ok(text.includes("⧉ Applied, no change (duplicate)"), text);
  assert.ok(text.includes("Nothing new was recorded: receipt rcpt_0002 changed nothing"), text);
  assert.ok(!text.includes("Confirmed in the current state"), text);
  assert.ok(!html.includes("badge tone-ok"), html);
  assert.equal(receiptBadge(DUPLICATE, view).text, "Applied, no change (duplicate)");
  assert.equal(receiptBadge(RECORDED, view).text, "Applied");
});

test("the action history and the change feed label a duplicate as no change", () => {
  const view = makeView({ revision: 4, receipts: [RECORDED, DUPLICATE] });
  const history = textOf(renderToStaticMarkup(createElement(ActionHistory, { view })));
  assert.ok(history.includes("Applied (2)"), history);
  assert.ok(history.includes("⧉ Applied, no change (duplicate) submit_observation"), history);
  assert.ok(history.includes("No change: this receipt has no transition of its own"), history);
  assert.ok(history.includes("✔ Applied submit_observation"), history);
  assert.equal(history.split("No change: this receipt").length - 1, 1, "only the duplicate says no change");

  const feed = textOf(renderToStaticMarkup(createElement(ChangeSummary, { view })));
  assert.ok(feed.includes("Receipt ⧉ Applied, no change (duplicate) submit_observation"), feed);
  assert.ok(feed.includes("Receipt ✔ Applied submit_observation"), feed);
});

test("a duplicate's Action history card is neutral, not the green applied card", () => {
  const view = makeView({ revision: 4, receipts: [RECORDED, DUPLICATE] });
  const html = renderToStaticMarkup(createElement(ActionHistory, { view }));
  const cardClass = (id: string): string | undefined => new RegExp(`<li class="([^"]*)" id="rcpt-${id}"`).exec(html)?.[1];
  assert.equal(cardClass("rcpt_0002"), "receipt receipt-no-change");
  assert.equal(cardClass("rcpt_0001"), "receipt receipt-applied");
  assert.equal(receiptClass(DUPLICATE), "receipt receipt-no-change");
  assert.equal(receiptClass(makeReceipt({ status: "rejected" })), "receipt receipt-rejected");
  // The neutral class has its own neutral border; only receipt-applied uses the green line.
  const css = readFileSync(new URL("../src/styles.css", import.meta.url), "utf-8");
  assert.match(css, /\.receipt-no-change \{\s*border-left: 5px solid var\(--neutral-line\);/);
  assert.match(css, /\.receipt-applied \{\s*border-left: 5px solid var\(--ok-line\);/);
  assert.ok(!/\.receipt-no-change[^{]*\{[^}]*--ok-line/.test(css));
});

// ------------------------------------------------------------------ C1: join links

test("a join link shows only a short prefix of its code; the href keeps the whole code", () => {
  const code = "P9NeQ7xYz2Lm4Kd8";
  const url = `http://127.0.0.1:8765/#/join/${code}`;
  const html = renderToStaticMarkup(
    createElement(JoinLink, { principalId: "participant_presenter", code, url, expiresWall: undefined }),
  );
  const text = textOf(html);
  assert.equal(text, "Join link for participant_presenter (code P9Ne…) · one-time code");
  assert.ok(!text.includes(code.slice(0, 5)), text);
  assert.ok(html.includes(`href="${url}"`), html);
  assert.ok(html.includes('data-join-link="participant_presenter"'), html);
  // The full code appears once in the markup: in the href, never in text or other attributes.
  assert.equal(html.split(code).length - 1, 1, html);
});

test("the code preview never shows more than a quarter of the code", () => {
  assert.equal(joinCodePreview("P9NeQ7xYz2Lm4Kd8"), "P9Ne…");
  assert.equal(joinCodePreview("abcdefgh"), "ab…");
  assert.equal(joinCodePreview("abc"), "…");
});
