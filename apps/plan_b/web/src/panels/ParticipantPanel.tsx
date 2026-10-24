import { useId, useMemo, useState } from "react";
import type { FormEvent } from "react";

import { buildToolRequest, newClientRecordId } from "../api";
import type { ToolBinding } from "../api";
import { Empty, Section, Tag, When } from "../components/ui";
import { fmtTime, fmtWindow, lookups } from "../format";
import type { EventStateView } from "../types";
import { checkInArguments, endChoices } from "./checkInForm";
import { SubmissionList } from "./MutationStatus";
import { observationArguments, reusableRecordId, unresolvedSubmissions } from "./submissions";
import type { ObservationContent } from "./submissions";
import type { MutationTracker } from "./useMutations";

const OBSERVATION_MAX = 1000;

function snippetOf(text: string): string {
  return text.length > 60 ? `${text.slice(0, 57)}…` : text;
}

export function ParticipantPanel({
  view,
  binding,
  tracker,
}: {
  view: EventStateView;
  binding: ToolBinding;
  tracker: MutationTracker;
}) {
  const tz = view.timezone;
  const look = lookups(view);
  const formId = useId();
  const grant = view.grants.find((g) => g.grant.grant_id === view.viewer.grant_id);
  const own = grant?.grant.resource_ids ?? [];
  const [resourceId, setResourceId] = useState<string>("");
  const [availableEnd, setAvailableEnd] = useState<string>("");
  const [text, setText] = useState("");
  const [entityId, setEntityId] = useState("");
  const [kind, setKind] = useState<"notice" | "resource_offer">("notice");
  const choices = useMemo(() => endChoices(view), [view]);
  const selectedResource = resourceId !== "" && own.includes(resourceId) ? resourceId : own[0] ?? "";
  const checkInSending = tracker.isSending("participant", "check_in");
  const observationSending = tracker.isSending("participant", "submit_observation");
  const entities = [
    ...view.resources.map((r) => ({ id: r.definition.resource_id, label: r.definition.label })),
    ...view.activities.map((a) => ({ id: a.definition.activity_id, label: a.definition.label })),
  ];
  const ownCheckins = view.checkins.filter((c) => own.includes(c.resource_id));
  const checkIn = checkInArguments(selectedResource, availableEnd, view.clock);
  // A chosen end time no longer offered (the clock passed it) stays visible until re-chosen.
  const keptChoice = availableEnd !== "" && !choices.includes(availableEnd) ? availableEnd : null;
  const unresolved = unresolvedSubmissions(tracker.submissions, "participant", "submit_observation");

  const submitCheckIn = (event: FormEvent) => {
    event.preventDefault();
    if (selectedResource === "" || !checkIn.ok) return;
    const request = buildToolRequest(binding, "check_in", checkIn.args, { idempotent: true });
    tracker.submit("participant", `Check in as ${look.resourceLabel(selectedResource)}`, request);
  };

  const submitObservation = (event: FormEvent) => {
    event.preventDefault();
    const trimmed = text.trim();
    if (trimmed.length === 0 || unresolved.length > 0) return;
    const content: ObservationContent = { text: trimmed, entity_id: entityId !== "" ? entityId : null, kind };
    // One client_record_id per logical observation: the same content as an earlier submission
    // whose outcome never became known keeps that id, so the server cannot store it twice.
    const recordId = reusableRecordId(tracker.submissions, content) ?? newClientRecordId();
    const request = buildToolRequest(binding, "submit_observation", observationArguments(content, recordId), {
      idempotent: true,
    });
    tracker.submit("participant", `Update: “${snippetOf(trimmed)}”`, request);
    setText("");
  };

  return (
    <Section
      id="participant-panel"
      title="Your role"
      className="panel"
      subtitle={
        <>
          You are <strong>{view.viewer.display_name}</strong>. You can record your own check-in and
          send updates. You cannot change the plan, the goal or another person&apos;s record.
        </>
      }
    >
      {grant === undefined ? (
        <Empty>Your grant is not visible in this state, so check-in is unavailable.</Empty>
      ) : (
        <>
          {!grant.valid_now ? (
            <p className="notice tone-warn">
              <span aria-hidden="true">⚠ </span>
              Your grant is {grant.revoked ? "revoked" : "not valid at the current scenario time"}. The
              server will reject new actions; the rejection will be shown here.
            </p>
          ) : null}
          <form className="form" onSubmit={submitCheckIn} aria-labelledby={`${formId}-checkin`}>
            <h3 className="list-heading" id={`${formId}-checkin`}>
              Check in
            </h3>
            {own.length > 1 ? (
              <label className="field">
                <span>Role</span>
                <select value={selectedResource} onChange={(e) => setResourceId(e.target.value)}>
                  {own.map((id) => (
                    <option key={id} value={id}>
                      {look.resourceLabel(id)} ({id})
                    </option>
                  ))}
                </select>
              </label>
            ) : (
              <p>
                Role: <strong>{look.resourceLabel(selectedResource)}</strong>{" "}
                <span className="muted">({selectedResource})</span>
              </p>
            )}
            <label className="field">
              <span>Available until (optional, {tz})</span>
              <select value={availableEnd} onChange={(e) => setAvailableEnd(e.target.value)}>
                <option value="">Not specified</option>
                {keptChoice !== null ? (
                  <option value={keptChoice} disabled={!checkIn.ok}>
                    {`${fmtTime(keptChoice, tz)}${!checkIn.ok ? " (already passed)" : ""}`}
                  </option>
                ) : null}
                {choices.map((iso) => (
                  <option key={iso} value={iso}>
                    {fmtTime(iso, tz)}
                  </option>
                ))}
              </select>
            </label>
            {!checkIn.ok ? (
              <p className="notice tone-warn" role="alert">
                <span aria-hidden="true">⚠ </span>
                Your chosen end time {fmtTime(checkIn.passedEnd, tz)} has already passed (scenario clock{" "}
                <When iso={view.clock} text={fmtTime(view.clock, tz)} />). Choose a new “Available until”
                time, or “Not specified”, before checking in. Nothing was sent.
              </p>
            ) : null}
            <p className="muted small">
              With an end time, availability is recorded from the current scenario time (
              <When iso={view.clock} text={fmtTime(view.clock, tz)} />) to that time. Without one, the
              server records your role&apos;s declared window.
            </p>
            <button
              type="submit"
              className="button"
              disabled={checkInSending || selectedResource === "" || !checkIn.ok}
            >
              {checkInSending ? "Sending check-in…" : "Check in"}
            </button>
          </form>
          {ownCheckins.length > 0 ? (
            <ul className="fact-list small">
              {ownCheckins.map((c) => (
                <li key={c.checkin_id}>
                  <Tag tone="ok" icon="✓">
                    Recorded
                  </Tag>{" "}
                  {look.resourceLabel(c.resource_id)} at <When iso={c.at} text={fmtTime(c.at, tz)} />,
                  available {fmtWindow(c.available.start, c.available.end, tz)}
                  {c.channel === "fixture_initial" ? " (authored setup)" : ""}
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted small">No check-in recorded for your role yet.</p>
          )}
        </>
      )}
      <form className="form" onSubmit={submitObservation} aria-labelledby={`${formId}-obs`}>
        <h3 className="list-heading" id={`${formId}-obs`}>
          Send an update
        </h3>
        {unresolved.length > 0 ? (
          <p className="notice tone-warn" role="status">
            <span aria-hidden="true">? </span>
            An earlier update is unresolved:{" "}
            {unresolved
              .map((s) => {
                const earlier = s.request.arguments.text;
                return typeof earlier === "string" ? `“${snippetOf(earlier)}”` : s.label;
              })
              .join("; ")}
            . It may already have been recorded. Use <strong>Check action status</strong> on it under
            “Your submissions in this tab” before sending a new update, or stop tracking it there if
            you accept that it may have been recorded.
          </p>
        ) : null}
        <label className="field">
          <span>What did you observe?</span>
          <textarea
            value={text}
            maxLength={OBSERVATION_MAX}
            rows={3}
            onChange={(e) => setText(e.target.value)}
            required
          />
          <span className="muted small">
            {text.length}/{OBSERVATION_MAX} characters. Recorded as your own report; it cannot grant
            authority.
          </span>
        </label>
        <label className="field">
          <span>About (optional)</span>
          <select value={entityId} onChange={(e) => setEntityId(e.target.value)}>
            <option value="">Nothing specific</option>
            {entities.map((e) => (
              <option key={e.id} value={e.id}>
                {e.label} ({e.id})
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Kind</span>
          <select value={kind} onChange={(e) => setKind(e.target.value === "resource_offer" ? "resource_offer" : "notice")}>
            <option value="notice">Notice</option>
            <option value="resource_offer">Resource offer</option>
          </select>
        </label>
        <button
          type="submit"
          className="button"
          disabled={observationSending || text.trim().length === 0 || unresolved.length > 0}
        >
          {observationSending ? "Sending update…" : "Send update"}
        </button>
      </form>
      <SubmissionList tracker={tracker} panel="participant" view={view} />
    </Section>
  );
}
