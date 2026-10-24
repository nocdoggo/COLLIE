import { compareIso, fmtTime, fmtWindow, lookups } from "../format";
import type { Assignment, EventStateView, PlanView } from "../types";
import { Empty, Section, Tag, When } from "./ui";

/** The plan version just before the active one, if any. */
export function previousPlan(view: EventStateView): PlanView | null {
  let best: PlanView | null = null;
  for (const plan of view.plan_history) {
    if (plan.plan_version >= view.plan.plan_version) continue;
    if (best === null || plan.plan_version > best.plan_version) best = plan;
  }
  return best;
}

interface Row {
  readonly activityId: string;
  readonly before: Assignment | undefined;
  readonly after: Assignment | undefined;
  readonly changes: string[];
}

function compare(
  before: PlanView,
  after: PlanView,
  tz: string,
  resourceLabel: (id: string) => string,
): Row[] {
  const ids: string[] = [];
  for (const a of [...before.assignments, ...after.assignments]) {
    if (!ids.includes(a.activity_id)) ids.push(a.activity_id);
  }
  return ids.map((activityId) => {
    const b = before.assignments.find((a) => a.activity_id === activityId);
    const a = after.assignments.find((x) => x.activity_id === activityId);
    const changes: string[] = [];
    if (b === undefined && a !== undefined) changes.push("added to the plan");
    else if (b !== undefined && a === undefined) changes.push("removed from the plan");
    else if (b !== undefined && a !== undefined) {
      if (compareIso(b.start, a.start) !== 0 || compareIso(b.end, a.end) !== 0) {
        changes.push(`time ${fmtWindow(b.start, b.end, tz)} → ${fmtWindow(a.start, a.end, tz)}`);
      }
      const removed = b.resource_ids.filter((r) => !a.resource_ids.includes(r));
      const added = a.resource_ids.filter((r) => !b.resource_ids.includes(r));
      if (removed.length > 0) changes.push(`no longer uses ${removed.map(resourceLabel).join(", ")}`);
      if (added.length > 0) changes.push(`now uses ${added.map(resourceLabel).join(", ")}`);
    }
    return { activityId, before: b, after: a, changes };
  });
}

function Slot({ assignment, tz, resourceLabel }: { assignment: Assignment | undefined; tz: string; resourceLabel: (id: string) => string }) {
  if (assignment === undefined) return <span className="muted">Not scheduled</span>;
  return (
    <>
      <When iso={assignment.start} text={fmtWindow(assignment.start, assignment.end, tz)} />
      <span className="sub">{assignment.resource_ids.map(resourceLabel).join(", ")}</span>
    </>
  );
}

/** Before/after comparison of the previous and current plan versions. */
export function PlanComparison({ view }: { view: EventStateView }) {
  const tz = view.timezone;
  const look = lookups(view);
  const previous = previousPlan(view);
  const current = view.plan;
  return (
    <Section id="plan-comparison" title="Before and after">
      {previous === null ? (
        <Empty>
          The active plan is version {current.plan_version}. No plan change has been applied in
          this episode.
        </Empty>
      ) : (
        <>
          <p className="card-subtitle">
            Plan version {previous.plan_version} → {current.plan_version}
            {current.applied_at !== null ? (
              <>
                , applied at <When iso={current.applied_at} text={fmtTime(current.applied_at, tz)} />
              </>
            ) : null}
            {current.applied_receipt_id !== null ? (
              <>
                {" "}by receipt <code>{current.applied_receipt_id}</code>
              </>
            ) : null}
            {current.candidate_id !== null ? (
              <>
                {" "}from candidate <code>{current.candidate_id}</code>
              </>
            ) : null}
            .
          </p>
          <table className="table">
            <caption className="sr-only">
              Each activity in plan version {previous.plan_version} and {current.plan_version}
            </caption>
            <thead>
              <tr>
                <th scope="col">Activity</th>
                <th scope="col">Before (v{previous.plan_version})</th>
                <th scope="col">After (v{current.plan_version})</th>
                <th scope="col">Change</th>
              </tr>
            </thead>
            <tbody>
              {compare(previous, current, tz, look.resourceLabel).map((row) => (
                <tr key={row.activityId} className={row.changes.length > 0 ? "row-changed" : undefined}>
                  <th scope="row">{look.activityLabel(row.activityId)}</th>
                  <td>
                    <Slot assignment={row.before} tz={tz} resourceLabel={look.resourceLabel} />
                  </td>
                  <td>
                    <Slot assignment={row.after} tz={tz} resourceLabel={look.resourceLabel} />
                  </td>
                  <td>
                    {row.changes.length > 0 ? (
                      <Tag tone="info" icon="↻">
                        Changed: {row.changes.join("; ")}
                      </Tag>
                    ) : (
                      <span className="muted">Unchanged</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </Section>
  );
}
