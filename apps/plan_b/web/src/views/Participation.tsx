// A registered volunteer's own view (W2.2): the alias they act under, their role's declared
// window, a check-in whose availability is scoped to that role, a resource offer for a
// resource they speak for, and free-text updates. Every action goes through the common tool
// endpoint under the volunteer's own session; nothing here can change the plan, the goal or
// another person's record, and a message cannot grant authority.

import { useEffect, useId, useMemo, useState } from "react";
import type { FormEvent } from "react";

import { buildToolRequest, newClientRecordId, readParticipation } from "../api";
import type { StoredSession, ToolBinding } from "../api";
import { checkInCoverage, coverageLabel, latestCheckIn, roleNeeds } from "../components/checkins";
import { Code, Empty, Section, Tag, When } from "../components/ui";
import { addMinutes, compareIso, fmtTime, fmtWindow, lookups, toUtcIso } from "../format";
import type {
  EventStateView,
  GrantView,
  JsonObject,
  OfferPrefill,
  ParticipationMe,
  ResourceView,
  SpokenForResource,
  UtcIso,
} from "../types";
import { checkInArguments, endChoices } from "../panels/checkInForm";
import { SubmissionList } from "../panels/MutationStatus";
import { observationArguments, reusableRecordId, unresolvedSubmissions } from "../panels/submissions";
import type { ObservationContent } from "../panels/submissions";
import type { MutationTracker } from "../panels/useMutations";

const OBSERVATION_MAX = 1000;

function snippetOf(text: string): string {
  return text.length > 60 ? `${text.slice(0, 57)}…` : text;
}

/** The roles (person resources) a participant may check in for: own scope, check_in granted. */
export function checkInRoles(view: EventStateView, grant: GrantView | undefined): ResourceView[] {
  if (grant === undefined || !grant.grant.allowed_tools.includes("check_in")) return [];
  return view.resources.filter(
    (r) => r.definition.kind === "person" && grant.grant.resource_ids.includes(r.definition.resource_id),
  );
}

/** Resources the server says this session may offer, with the registered facts to confirm. */
export function offerableResources(me: ParticipationMe | null): (SpokenForResource & { offer: OfferPrefill })[] {
  return (me?.speaks_for ?? []).filter((r): r is SpokenForResource & { offer: OfferPrefill } => r.offer !== null);
}

/** Offer start choices: from the later of the clock and the registered start, every 5 minutes. */
export function offerStartChoices(clock: UtcIso, window: { start: UtcIso; end: UtcIso }): UtcIso[] {
  const first = compareIso(clock, window.start) > 0 ? clock : window.start;
  const out: UtcIso[] = [first];
  const ms = new Date(first).getTime();
  let t = toUtcIso(new Date(Math.ceil((ms + 60_000) / 300_000) * 300_000));
  while (compareIso(t, window.end) < 0 && out.length < 40) {
    out.push(t);
    t = addMinutes(t, 5);
  }
  return out;
}

/**
 * The capabilities an offer states by default: those an approved target needs that the resource
 * has registered (all registered ones when no target names any).
 */
export function defaultOfferCapabilities(offer: OfferPrefill): string[] {
  const needed = new Set(Object.values(offer.needed_capabilities).flat());
  const covered = offer.registered_capabilities.filter((c) => needed.has(c));
  return covered.length > 0 ? covered : [...offer.registered_capabilities];
}

/**
 * submit_observation arguments of a structured offer. The text stays data; the server checks
 * only the owner, the preconfigured option, the stated capabilities, the interval (inside the
 * registered window and ending at its end) and the confirmed terms.
 */
export function offerArguments(
  resourceId: string,
  text: string,
  start: UtcIso,
  offer: OfferPrefill,
  capabilities: readonly string[],
  clientRecordId: string,
): JsonObject {
  return {
    text,
    kind: "resource_offer",
    entity_id: resourceId,
    client_record_id: clientRecordId,
    offer: {
      available: { start, end: offer.registered_window.end },
      capabilities: [...capabilities],
      terms_ref: offer.terms_ref,
    },
  };
}

/** A structured offer of a resource the volunteer speaks for. */
export function OfferForm({
  view,
  me,
  disabled,
  onSubmit,
}: {
  view: EventStateView;
  me: ParticipationMe | null;
  disabled: boolean;
  onSubmit: (resourceId: string, args: (clientRecordId: string) => JsonObject, label: string, text: string) => void;
}) {
  const formId = useId();
  const tz = view.timezone;
  const look = lookups(view);
  const offerable = offerableResources(me);
  const [resourceId, setResourceId] = useState("");
  const [start, setStart] = useState("");
  const [text, setText] = useState("");
  const [picked, setPicked] = useState<readonly string[] | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const target = offerable.find((r) => r.resource_id === resourceId) ?? offerable[0];
  if (target === undefined) return null;
  const offer = target.offer;
  const starts = offerStartChoices(view.clock, offer.registered_window);
  const chosenStart = start !== "" && starts.includes(start) ? start : (starts[0] ?? offer.registered_window.start);
  const capabilities = picked ?? defaultOfferCapabilities(offer);
  const ended = compareIso(view.clock, offer.registered_window.end) >= 0;
  const ready = !ended && confirmed && capabilities.length > 0 && text.trim().length > 0;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!ready) return;
    const trimmed = text.trim();
    onSubmit(
      target.resource_id,
      (recordId) => offerArguments(target.resource_id, trimmed, chosenStart, offer, capabilities, recordId),
      `Offer ${target.label}`,
      trimmed,
    );
    setText("");
    setConfirmed(false);
  };

  return (
    <form className="form" onSubmit={submit} aria-labelledby={`${formId}-offer`}>
      <h3 className="list-heading" id={`${formId}-offer`}>
        Offer a resource
      </h3>
      {offerable.length > 1 ? (
        <label className="field">
          <span>Resource you speak for</span>
          <select value={target.resource_id} onChange={(e) => setResourceId(e.target.value)}>
            {offerable.map((r) => (
              <option key={r.resource_id} value={r.resource_id}>
                {r.label} ({r.resource_id})
              </option>
            ))}
          </select>
        </label>
      ) : (
        <p>
          Resource: <strong>{target.label}</strong> <span className="muted">({target.resource_id})</span>, status{" "}
          {view.resources.find((r) => r.definition.resource_id === target.resource_id)?.status ?? target.status ?? "unknown"};
          an approved option for {offer.approved_for.map(look.resourceLabel).join(", ")}.
        </p>
      )}
      <label className="field">
        <span>Available from ({tz})</span>
        <select value={chosenStart} onChange={(e) => setStart(e.target.value)} disabled={ended}>
          {starts.map((iso) => (
            <option key={iso} value={iso}>
              {fmtTime(iso, tz)}
            </option>
          ))}
        </select>
      </label>
      <p className="muted small">
        Until {fmtTime(offer.registered_window.end, tz)}: an offer must lie inside the registered window (
        {fmtWindow(offer.registered_window.start, offer.registered_window.end, tz)}) and cover it to its end.
      </p>
      <fieldset className="field">
        <legend>Capabilities offered</legend>
        {offer.registered_capabilities.map((c) => (
          <label key={c} className="radio">
            <input
              type="checkbox"
              checked={capabilities.includes(c)}
              onChange={(e) =>
                setPicked(e.target.checked ? [...capabilities, c] : capabilities.filter((x) => x !== c))
              }
            />
            <span>{c.replace(/_/g, " ")}</span>
          </label>
        ))}
      </fieldset>
      <label className="radio">
        <input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} />
        <span>
          I confirm the registered terms <code>{offer.terms_ref}</code>
        </span>
      </label>
      <label className="field">
        <span>Your offer</span>
        <textarea value={text} maxLength={OBSERVATION_MAX} rows={2} onChange={(e) => setText(e.target.value)} required />
        <span className="muted small">
          Recorded as your own report. The offer can make this preconfigured resource available to the planner
          after the server checks its owner, capabilities, interval and terms; it reserves nothing, adds no
          inventory and spends no money.
        </span>
      </label>
      {ended ? <p className="small tone-text-warn">The registered window has ended; nothing can be offered.</p> : null}
      <button type="submit" className="button" disabled={disabled || !ready}>
        Send offer
      </button>
    </form>
  );
}

/** Who the volunteer is in this sandbox: alias, principal, registered roles and their windows. */
function Alias({ view, grant, roles }: { view: EventStateView; grant: GrantView | undefined; roles: ResourceView[] }) {
  const tz = view.timezone;
  const look = lookups(view);
  return (
    <dl className="alias" data-alias={view.viewer.principal_id}>
      <div>
        <dt>Alias</dt>
        <dd>
          <strong>{view.viewer.display_name}</strong> <span className="sub">registered volunteer {view.viewer.principal_id}</span>
        </dd>
      </div>
      <div>
        <dt>Registered role</dt>
        <dd>
          {roles.length > 0
            ? roles.map((r) => (
                <span key={r.definition.resource_id} className="alias-role">
                  {r.definition.label} <span className="muted">({r.definition.resource_id})</span>, declared{" "}
                  {fmtWindow(r.definition.window.start, r.definition.window.end, tz)}
                </span>
              ))
            : grant !== undefined && grant.grant.resource_ids.length > 0
              ? grant.grant.resource_ids.map(look.resourceLabel).join(", ")
              : "No role resource"}
        </dd>
      </div>
      <div>
        <dt>Grant</dt>
        <dd>
          {grant !== undefined ? (
            <>
              <Code>{grant.grant.grant_id}</Code> v{grant.version}
              <span className="sub">{grant.grant.allowed_tools.filter((t) => t !== "get_event_state").join(", ")}</span>
            </>
          ) : (
            "Not visible"
          )}
        </dd>
      </div>
    </dl>
  );
}

export function Participation({
  view,
  binding,
  tracker,
  session,
  me: given,
}: {
  view: EventStateView;
  binding: ToolBinding;
  tracker: MutationTracker;
  /** Reads GET /api/participation/me for the offer form's registered facts. */
  session?: StoredSession;
  /** Prefill given directly (tests); otherwise read with `session`. */
  me?: ParticipationMe | null;
}) {
  const [fetched, setFetched] = useState<ParticipationMe | null>(null);
  useEffect(() => {
    if (session === undefined || given !== undefined) return;
    let cancelled = false;
    readParticipation(session).then(
      (me) => {
        if (!cancelled) setFetched(me);
      },
      () => {
        if (!cancelled) setFetched(null);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [session, given, view.episode_id]);
  const me = given !== undefined ? given : fetched;
  const tz = view.timezone;
  const look = lookups(view);
  const formId = useId();
  const grant = view.grants.find((g) => g.grant.grant_id === view.viewer.grant_id);
  const roles = checkInRoles(view, grant);
  const own = roles.map((r) => r.definition.resource_id);
  const [resourceId, setResourceId] = useState<string>("");
  const [availableEnd, setAvailableEnd] = useState<string>("");
  const [text, setText] = useState("");
  const [entityId, setEntityId] = useState("");
  const [kind, setKind] = useState<"notice" | "resource_offer">("notice");
  const selectedResource = resourceId !== "" && own.includes(resourceId) ? resourceId : own[0] ?? "";
  const role = roles.find((r) => r.definition.resource_id === selectedResource);
  const roleEnd = role?.definition.window.end;
  const choices = useMemo(() => endChoices(view, roleEnd), [view, roleEnd]);
  const checkInSending = tracker.isSending("participant", "check_in");
  const observationSending = tracker.isSending("participant", "submit_observation");
  const entities = [
    ...view.resources.map((r) => ({ id: r.definition.resource_id, label: r.definition.label })),
    ...view.activities.map((a) => ({ id: a.definition.activity_id, label: a.definition.label })),
  ];
  const ownCheckins = view.checkins.filter((c) => own.includes(c.resource_id));
  const latest = selectedResource !== "" ? latestCheckIn(view.checkins, selectedResource) : undefined;
  const coverage =
    selectedResource !== ""
      ? coverageLabel(
          checkInCoverage(view.checkins, selectedResource, roleNeeds(view.activities, selectedResource, view.clock)),
          tz,
          look.activityLabel,
        )
      : null;
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

  const sendObservation = (content: ObservationContent, label: string) => {
    // One client_record_id per logical observation: the same content as an earlier submission
    // whose outcome never became known keeps that id, so the server cannot store it twice.
    const recordId = reusableRecordId(tracker.submissions, content) ?? newClientRecordId();
    const request = buildToolRequest(binding, "submit_observation", observationArguments(content, recordId), {
      idempotent: true,
    });
    tracker.submit("participant", label, request);
  };

  const submitObservation = (event: FormEvent) => {
    event.preventDefault();
    const trimmed = text.trim();
    if (trimmed.length === 0 || unresolved.length > 0) return;
    sendObservation({ text: trimmed, entity_id: entityId !== "" ? entityId : null, kind }, `Update: “${snippetOf(trimmed)}”`);
    setText("");
  };

  const submitOffer = (resourceId: string, args: (recordId: string) => JsonObject, label: string, trimmed: string) => {
    if (unresolved.length > 0) return;
    const content: ObservationContent = { text: trimmed, entity_id: resourceId, kind: "resource_offer" };
    const recordId = reusableRecordId(tracker.submissions, content) ?? newClientRecordId();
    const request = buildToolRequest(binding, "submit_observation", args(recordId), { idempotent: true });
    tracker.submit("participant", `${label}: “${snippetOf(trimmed)}”`, request);
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
      <Alias view={view} grant={grant} roles={roles} />
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
          {roles.length === 0 ? (
            <p className="muted small">Your grant has no role to check in for.</p>
          ) : (
            <form className="form" onSubmit={submitCheckIn} aria-labelledby={`${formId}-checkin`}>
              <h3 className="list-heading" id={`${formId}-checkin`}>
                Check in
              </h3>
              {roles.length > 1 ? (
                <label className="field">
                  <span>Role</span>
                  <select value={selectedResource} onChange={(e) => setResourceId(e.target.value)}>
                    {roles.map((r) => (
                      <option key={r.definition.resource_id} value={r.definition.resource_id}>
                        {r.definition.label} ({r.definition.resource_id})
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
              {coverage !== null ? (
                <p className="small" data-checkin-status={selectedResource}>
                  <Tag tone={coverage.tone} icon={coverage.icon}>
                    {coverage.text}
                  </Tag>
                  {latest !== undefined ? (
                    <>
                      {" "}
                      Latest: at <When iso={latest.at} text={fmtTime(latest.at, tz)} />, available{" "}
                      {fmtWindow(latest.available.start, latest.available.end, tz)}
                    </>
                  ) : null}
                </p>
              ) : null}
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
                Availability is scoped to your role: it starts at the current scenario time (
                <When iso={view.clock} text={fmtTime(view.clock, tz)} />, a check-in records presence now) and
                ends at the time you choose
                {roleEnd !== undefined ? <>, no later than your declared window&apos;s end ({fmtTime(roleEnd, tz)})</> : null}.
                Without one, the server records your role&apos;s declared window. A later check-in replaces the
                earlier one.
              </p>
              <button
                type="submit"
                className="button"
                disabled={checkInSending || selectedResource === "" || !checkIn.ok}
              >
                {checkInSending ? "Sending check-in…" : "Check in"}
              </button>
            </form>
          )}
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
          ) : roles.length > 0 ? (
            <p className="muted small">No check-in recorded for your role yet.</p>
          ) : null}
        </>
      )}
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
      <OfferForm view={view} me={me} disabled={observationSending || unresolved.length > 0} onSubmit={submitOffer} />
      <form className="form" onSubmit={submitObservation} aria-labelledby={`${formId}-obs`}>
        <h3 className="list-heading" id={`${formId}-obs`}>
          Send an update
        </h3>
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
