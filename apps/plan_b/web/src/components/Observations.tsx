import {
  CHANNEL_LABEL,
  DECISION_LABEL,
  RESOURCE_STATUS_LABEL,
  compareIso,
  fmtTime,
  lookups,
  minutesBetween,
} from "../format";
import type { EventStateView, ObservationRecord, PolicyDecision } from "../types";
import type { BoardMode } from "./BoardHeader";
import { EvidenceCard } from "./EvidenceCard";
import { Empty, JumpButton, Section, StatusBadge, Tag, When, domId } from "./ui";

export function observationsNewestFirst(view: EventStateView): ObservationRecord[] {
  return [...view.observations].sort(
    (a, b) =>
      compareIso(b.observation.received_at, a.observation.received_at) ||
      b.revision_after - a.revision_after,
  );
}

function decisionsByObservation(view: EventStateView): Map<string, PolicyDecision[]> {
  const map = new Map<string, PolicyDecision[]>();
  for (const decision of view.decisions) {
    for (const ref of decision.observation_refs) {
      const list = map.get(ref) ?? [];
      list.push(decision);
      map.set(ref, list);
    }
  }
  return map;
}

/** Status facts of a status_tool or arrival_record observation, with honest time labels. */
export function StatusFactsLine({
  record,
  view,
  mode,
}: {
  record: ObservationRecord;
  view: EventStateView;
  mode: BoardMode;
}) {
  const tz = view.timezone;
  const obs = record.observation;
  const facts = record.structured;
  const age = minutesBetween(obs.observed_at, view.clock);
  return (
    <div className="status-facts">
      {facts !== null ? (
        <p>
          <strong>{facts.fact.replace(/_/g, " ")}</strong>: reported <code>{facts.status_code}</code>{" "}
          <StatusBadge label={RESOURCE_STATUS_LABEL[facts.domain_status]} />
          {facts.reported_eta !== null ? (
            <Tag tone="warn" icon="◷">
              Reported ETA <When iso={facts.reported_eta} text={fmtTime(facts.reported_eta, tz)} /> —
              a reported ETA is not an arrival
            </Tag>
          ) : null}
        </p>
      ) : null}
      <p className="muted">
        Source time <When iso={obs.observed_at} text={fmtTime(obs.observed_at, tz)} />
        {" · "}
        {record.channel === "status_tool" ? "retrieved" : "received"} at{" "}
        <When iso={obs.received_at} text={fmtTime(obs.received_at, tz)} />
        {" · "}
        {mode === "replay" ? (
          <strong className="recorded-label">
            Recorded at <When iso={obs.received_at} text={fmtTime(obs.received_at, tz)} /> — not
            re-queried
          </strong>
        ) : (
          <>
            {age} min old at the current scenario clock (
            <When iso={view.clock} text={fmtTime(view.clock, tz)} />)
          </>
        )}
      </p>
    </div>
  );
}

function ObservationItem({
  record,
  view,
  mode,
  decisions,
}: {
  record: ObservationRecord;
  view: EventStateView;
  mode: BoardMode;
  decisions: PolicyDecision[];
}) {
  const tz = view.timezone;
  const look = lookups(view);
  const obs = record.observation;
  return (
    <li className="observation" id={domId("obs", obs.observation_id)} tabIndex={-1}>
      <div className="observation-head">
        <Tag tone="neutral">{CHANNEL_LABEL[record.channel]}</Tag>
        <span>
          Affects <strong>{look.entityLabel(obs.entity_id)}</strong>{" "}
          <span className="muted">({obs.entity_id})</span>
        </span>
        <span className="muted">
          {obs.kind} · from <code>{obs.source_id}</code>
          {record.submitted_by !== null && record.submitted_by !== obs.source_id ? (
            <>
              {" "}via <code>{record.submitted_by}</code>
            </>
          ) : null}
        </span>
      </div>
      <blockquote className="observation-text">{obs.text}</blockquote>
      {record.channel === "status_tool" || record.channel === "arrival_record" ? (
        <StatusFactsLine record={record} view={view} mode={mode} />
      ) : (
        <p className="muted">
          Observed <When iso={obs.observed_at} text={fmtTime(obs.observed_at, tz)} />
          {" · "}received <When iso={obs.received_at} text={fmtTime(obs.received_at, tz)} />
          {mode === "replay" ? " (recorded)" : ""}
        </p>
      )}
      <p className="muted small">
        Authority scope: {obs.authority_scope.replace(/_/g, " ")} · correlation group{" "}
        <code>{obs.correlation_group}</code> · revision {record.revision_after}
        {obs.supersedes.length > 0 ? <> · supersedes {obs.supersedes.join(", ")}</> : null}
      </p>
      <div className="interpretation">
        <span className="eyebrow">Policy interpretation</span>
        {decisions.length === 0 ? (
          <p className="muted">No policy decision references this update yet.</p>
        ) : (
          <ul>
            {decisions.map((d) => (
              <li key={d.decision_id}>
                <StatusBadge label={DECISION_LABEL[d.kind]} /> {d.summary}{" "}
                <JumpButton targetId={domId("dec", d.decision_id)}>decision</JumpButton>
              </li>
            ))}
          </ul>
        )}
      </div>
      <EvidenceCard title="Observation record (JSON)" value={record} />
    </li>
  );
}

/** Incoming updates: every visible observation with provenance, times and interpretation. */
export function Observations({ view, mode }: { view: EventStateView; mode: BoardMode }) {
  const records = observationsNewestFirst(view);
  const byObservation = decisionsByObservation(view);
  return (
    <Section
      id="observations"
      title={`Incoming updates (${records.length})`}
      subtitle="Newest first. Message text is shown as data; instructions inside it change nothing."
    >
      {records.length === 0 ? (
        <Empty>No updates have been received.</Empty>
      ) : (
        <ol className="observations">
          {records.map((record) => (
            <ObservationItem
              key={record.observation.observation_id}
              record={record}
              view={view}
              mode={mode}
              decisions={byObservation.get(record.observation.observation_id) ?? []}
            />
          ))}
        </ol>
      )}
    </Section>
  );
}

/** The status query results and arrival records, and each equipment resource's current status. */
const QUERY_OUTCOME: Record<string, { label: string; tone: "ok" | "warn" | "bad" | "neutral"; icon: string }> = {
  succeeded: { label: "Answered", tone: "ok", icon: "✓" },
  unknown: { label: "Unknown — source had no answer", tone: "warn", icon: "?" },
  unavailable: { label: "Unavailable — service did not respond", tone: "bad", icon: "✕" },
  rejected: { label: "Rejected — not executed", tone: "bad", icon: "✕" },
};

/** Every status query with its actual outcome. Unknown and unavailable are not an all-clear. */
function StatusQueries({ view, mode }: { view: EventStateView; mode: BoardMode }) {
  const tz = view.timezone;
  const look = lookups(view);
  const checks = [...view.status_checks].reverse();
  if (checks.length === 0) {
    return <Empty>No status query has been made yet.</Empty>;
  }
  return (
    <ol className="status-results" aria-label="Status queries">
      {checks.map((check) => {
        const outcome = QUERY_OUTCOME[check.envelope_status] ?? QUERY_OUTCOME.rejected!;
        return (
          <li key={check.call_id}>
            <Tag tone={outcome.tone} icon={outcome.icon}>
              {outcome.label}
            </Tag>{" "}
            <strong>{check.entity_id !== null ? look.entityLabel(check.entity_id) : "unknown entity"}</strong>{" "}
            <span className="muted">
              {check.fact?.replace(/_/g, " ") ?? ""} · asked by <code>{check.actor_id ?? "?"}</code>
              {check.requested_at !== null ? (
                <>
                  {" "}at <When iso={check.requested_at} text={fmtTime(check.requested_at, tz)} />
                </>
              ) : null}
              {check.completed_at !== null ? (
                <>
                  , answered <When iso={check.completed_at} text={fmtTime(check.completed_at, tz)} />
                </>
              ) : null}
            </span>
            {check.deduplicated ? <Tag tone="neutral">same source record as before</Tag> : null}
            {check.stale === true ? (
              <Tag tone="warn" icon="◷">
                stale source record
              </Tag>
            ) : null}
            {check.error_code !== null ? (
              <p className="muted">
                <code>{check.error_code}</code>
                {check.reason !== null ? <> — {check.reason}</> : null}
              </p>
            ) : null}
            {mode === "replay" && check.completed_at !== null ? (
              <p>
                <strong className="recorded-label">
                  Recorded at <When iso={check.completed_at} text={fmtTime(check.completed_at, tz)} /> — not
                  re-queried
                </strong>
              </p>
            ) : null}
            {check.observation_id !== null ? (
              <JumpButton targetId={domId("obs", check.observation_id)}>answer as observation</JumpButton>
            ) : null}
          </li>
        );
      })}
    </ol>
  );
}

export function StatusChecks({ view, mode }: { view: EventStateView; mode: BoardMode }) {
  const tz = view.timezone;
  const look = lookups(view);
  const records = observationsNewestFirst(view).filter(
    (r) => r.channel === "status_tool" || r.channel === "arrival_record",
  );
  const equipment = view.resources.filter((r) => r.definition.kind === "equipment");
  return (
    <Section
      id="status-checks"
      title="Status checks and arrivals"
      subtitle="A status check reports what a source said at its time. Only an arrival record shows equipment is here."
    >
      <ul className="status-now">
        {equipment.map((r) => (
          <li key={r.definition.resource_id}>
            <strong>{r.definition.label}</strong>{" "}
            <StatusBadge label={RESOURCE_STATUS_LABEL[r.status]} />{" "}
            <span className="muted">
              basis: {r.status_basis.replace(/_/g, " ")}
              {r.status_observed_at !== null ? (
                <>
                  {" "}at <When iso={r.status_observed_at} text={fmtTime(r.status_observed_at, tz)} />
                </>
              ) : null}
            </span>
            {r.reported_eta !== null ? (
              <Tag tone="warn" icon="◷">
                Reported ETA <When iso={r.reported_eta} text={fmtTime(r.reported_eta, tz)} /> — not an
                arrival
              </Tag>
            ) : null}
          </li>
        ))}
      </ul>
      <StatusQueries view={view} mode={mode} />
      {records.length === 0 ? (
        <Empty>No status answer or arrival has been recorded as an observation.</Empty>
      ) : (
        <ol className="status-results">
          {records.map((record) => (
            <li key={record.observation.observation_id}>
              <Tag tone="neutral">{CHANNEL_LABEL[record.channel]}</Tag>{" "}
              <strong>{look.entityLabel(record.observation.entity_id)}</strong>
              <StatusFactsLine record={record} view={view} mode={mode} />
              <JumpButton targetId={domId("obs", record.observation.observation_id)}>
                full update
              </JumpButton>
            </li>
          ))}
        </ol>
      )}
    </Section>
  );
}
