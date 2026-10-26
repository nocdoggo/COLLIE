import {
  LIFECYCLE_LABEL,
  RESOURCE_STATUS_LABEL,
  activitiesInPlanOrder,
  compareIso,
  fmtTime,
  fmtWindow,
  lookups,
} from "../format";
import type { ActivityView, Assignment, EventStateView, PlanView, ResourceView } from "../types";
import { previousPlan } from "./PlanComparison";
import { checkInCoverage, coverageLabel, latestCheckIn, slotToCover } from "./checkins";
import { Empty, Section, StatusBadge, Tag, When } from "./ui";

function percent(iso: string, start: number, span: number): number {
  const t = new Date(iso).getTime();
  return Math.min(100, Math.max(0, ((t - start) / span) * 100));
}

function changeNote(
  assignment: Assignment | null,
  before: Assignment | undefined,
  tz: string,
  resourceLabel: (id: string) => string,
): string | null {
  if (assignment === null || before === undefined) return null;
  const notes: string[] = [];
  if (compareIso(before.start, assignment.start) !== 0 || compareIso(before.end, assignment.end) !== 0) {
    notes.push(`was ${fmtWindow(before.start, before.end, tz)}`);
  }
  const removed = before.resource_ids.filter((r) => !assignment.resource_ids.includes(r));
  const added = assignment.resource_ids.filter((r) => !before.resource_ids.includes(r));
  if (removed.length > 0 || added.length > 0) {
    notes.push(
      `uses ${added.map(resourceLabel).join(", ") || "no new resource"} instead of ${
        removed.map(resourceLabel).join(", ") || "nothing"
      }`,
    );
  }
  return notes.length > 0 ? notes.join("; ") : null;
}

function PersonLine({
  resource,
  view,
  activity,
}: {
  resource: ResourceView;
  view: EventStateView;
  activity: ActivityView;
}) {
  const tz = view.timezone;
  const def = resource.definition;
  const latest = latestCheckIn(view.checkins, def.resource_id);
  if (latest === undefined) {
    return (
      <li>
        <strong>{def.label}</strong>{" "}
        <Tag tone="warn" icon="⧗">
          No check-in yet
        </Tag>
      </li>
    );
  }
  const recorded = (
    <>
      at <When iso={latest.at} text={fmtTime(latest.at, tz)} />, available{" "}
      {fmtWindow(latest.available.start, latest.available.end, tz)}
    </>
  );
  // Only a slot that is still ahead (or running) can be covered or not; past slots are history.
  const slot = slotToCover(activity, view.clock);
  if (slot === null) {
    return (
      <li>
        <strong>{def.label}</strong>{" "}
        <Tag tone="neutral" icon="○">
          Latest check-in {recorded}
        </Tag>
      </li>
    );
  }
  const coverage = checkInCoverage(view.checkins, def.resource_id, [
    { activityId: activity.definition.activity_id, window: slot },
  ]);
  if (coverage.kind === "covered") {
    return (
      <li>
        <strong>{def.label}</strong>{" "}
        <Tag tone="ok" icon="✓">
          Checked in {recorded}
        </Tag>
      </li>
    );
  }
  const label = coverageLabel(coverage, tz);
  return (
    <li>
      <strong>{def.label}</strong>{" "}
      <Tag tone={label.tone} icon={label.icon}>
        {label.text}
      </Tag>{" "}
      <span className="muted small">(checked in {recorded})</span>
    </li>
  );
}

function ResourceLine({
  resource,
  view,
  activity,
}: {
  resource: ResourceView | undefined;
  view: EventStateView;
  activity: ActivityView;
}) {
  const tz = view.timezone;
  if (resource === undefined) return null;
  const def = resource.definition;
  if (def.kind === "person") return <PersonLine resource={resource} view={view} activity={activity} />;
  const activityId = activity.definition.activity_id;
  const commitment = view.commitments.find(
    (c) => c.resource_id === def.resource_id && c.activity_id === activityId,
  );
  const hold = view.holds.find(
    (h) =>
      h.resource_id === def.resource_id &&
      h.activity_id === activityId &&
      h.effective_status === "active",
  );
  return (
    <li>
      <strong>{def.label}</strong> <StatusBadge label={RESOURCE_STATUS_LABEL[resource.status]} />
      {resource.reported_eta !== null ? (
        <Tag tone="warn" icon="◷">
          Reported ETA <When iso={resource.reported_eta} text={fmtTime(resource.reported_eta, tz)} />. A
          reported ETA is not an arrival
        </Tag>
      ) : null}
      {def.terms.booking_required ? (
        commitment !== undefined ? (
          <Tag tone="ok" icon="✔">
            Booking committed ({commitment.commitment_id})
          </Tag>
        ) : hold !== undefined ? (
          <Tag tone="info" icon="‖">
            Held until <When iso={hold.expires_at} text={fmtTime(hold.expires_at, tz)} />, not yet
            committed
          </Tag>
        ) : (
          <Tag tone="neutral" icon="○">
            Booking required, none committed
          </Tag>
        )
      ) : null}
    </li>
  );
}

function ActivityRow({
  activity,
  view,
  previous,
  axisStart,
  axisSpan,
}: {
  activity: ActivityView;
  view: EventStateView;
  previous: PlanView | null;
  axisStart: number;
  axisSpan: number;
}) {
  const tz = view.timezone;
  const look = lookups(view);
  const def = activity.definition;
  const assignment = activity.assignment;
  const resources = new Map(view.resources.map((r) => [r.definition.resource_id, r]));
  const before = previous?.assignments.find((a) => a.activity_id === def.activity_id);
  const change = changeNote(assignment, before, tz, look.resourceLabel);
  const readiness = activity.readiness;
  const lastEvent = activity.history[activity.history.length - 1];
  return (
    <li className={`activity lifecycle-${activity.lifecycle}`}>
      <div className="activity-time">
        {assignment !== null ? (
          <>
            <When iso={assignment.start} text={fmtTime(assignment.start, tz)} />–
            <When iso={assignment.end} text={fmtTime(assignment.end, tz)} />
          </>
        ) : (
          "Not scheduled"
        )}
      </div>
      <div className="activity-main">
        <h3 className="activity-title">
          {def.label} <span className="muted">({def.activity_id})</span>{" "}
          <StatusBadge label={LIFECYCLE_LABEL[activity.lifecycle]} />
          {def.required ? null : (
            <Tag tone="neutral" icon="○">
              Optional
            </Tag>
          )}
          {change !== null ? (
            <Tag tone="info" icon="↻">
              Changed: {change}
            </Tag>
          ) : null}
        </h3>
        {assignment !== null ? (
          <div className="activity-bar" aria-hidden="true">
            <span
              className="activity-bar-fill"
              style={{
                left: `${percent(assignment.start, axisStart, axisSpan)}%`,
                width: `${Math.max(
                  1,
                  percent(assignment.end, axisStart, axisSpan) -
                    percent(assignment.start, axisStart, axisSpan),
                )}%`,
              }}
            />
            <span className="activity-bar-now" style={{ left: `${percent(view.clock, axisStart, axisSpan)}%` }} />
          </div>
        ) : null}
        {assignment !== null && assignment.resource_ids.length > 0 ? (
          <ul className="resource-lines">
            {assignment.resource_ids.map((rid) => (
              <ResourceLine key={rid} resource={resources.get(rid)} view={view} activity={activity} />
            ))}
          </ul>
        ) : null}
        {readiness !== null ? (
          <div className="readiness">
            <p className="readiness-head">
              Readiness ({readiness.mode === "preview" ? "preview" : "execution check"} at{" "}
              <When iso={readiness.at} text={fmtTime(readiness.at, tz)} />):{" "}
              {readiness.ready ? (
                <Tag tone="ok" icon="✓">
                  Nothing unmet
                </Tag>
              ) : (
                <Tag tone="bad" icon="✗">
                  {readiness.unmet.length} unmet
                </Tag>
              )}
              {readiness.pending.length > 0 ? (
                <Tag tone="warn" icon="⧗">
                  {readiness.pending.length} pending
                </Tag>
              ) : null}
            </p>
            <ul className="readiness-list">
              {readiness.unmet.map((item) => (
                <li key={`u-${item}`} className="tone-text-bad">
                  <span aria-hidden="true">✗ </span>
                  <span className="sr-label">Unmet: </span>
                  {item}
                </li>
              ))}
              {readiness.pending.map((item) => (
                <li key={`p-${item}`} className="tone-text-warn">
                  <span aria-hidden="true">⧗ </span>
                  <span className="sr-label">Pending: </span>
                  {item}
                </li>
              ))}
              {readiness.met.map((item) => (
                <li key={`m-${item}`} className="tone-text-ok">
                  <span aria-hidden="true">✓ </span>
                  <span className="sr-label">Met: </span>
                  {item}
                </li>
              ))}
            </ul>
          </div>
        ) : lastEvent !== undefined ? (
          <p className="muted">
            {LIFECYCLE_LABEL[lastEvent.state].text} at{" "}
            <When iso={lastEvent.at} text={fmtTime(lastEvent.at, tz)} /> (revision {lastEvent.revision})
            {lastEvent.reasons.length > 0 ? `: ${lastEvent.reasons.join("; ")}` : ""}
          </p>
        ) : null}
      </div>
    </li>
  );
}

/** Current schedule in plan order, with lifecycle and readiness as text. */
export function Schedule({ view }: { view: EventStateView }) {
  const tz = view.timezone;
  const ordered = activitiesInPlanOrder(view);
  const previous = previousPlan(view);
  const starts = ordered
    .map((a) => a.assignment?.start)
    .filter((s): s is string => s !== undefined);
  const first = [...starts, view.goal.public_start].sort(compareIso)[0] ?? view.goal.public_start;
  const axisStart = new Date(first).getTime();
  const axisSpan = Math.max(60_000, new Date(view.goal.hard_end).getTime() - axisStart);
  return (
    <Section
      id="schedule"
      title={`Current schedule (plan version ${view.plan.plan_version})`}
      subtitle={
        <>
          Times in {tz}. The bar marks each slot between{" "}
          <When iso={first} text={fmtTime(first, tz)} /> and the hard end{" "}
          <When iso={view.goal.hard_end} text={fmtTime(view.goal.hard_end, tz)} />; the thin line
          is the scenario clock.
        </>
      }
    >
      {ordered.length === 0 ? (
        <Empty>No activities are defined.</Empty>
      ) : (
        <ol className="activities">
          {ordered.map((activity) => (
            <ActivityRow
              key={activity.definition.activity_id}
              activity={activity}
              view={view}
              previous={previous}
              axisStart={axisStart}
              axisSpan={axisSpan}
            />
          ))}
        </ol>
      )}
    </Section>
  );
}
