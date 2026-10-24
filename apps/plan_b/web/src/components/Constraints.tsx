import { PRESET_LABEL, fmtCents, fmtTime, lookups } from "../format";
import type { EventStateView } from "../types";
import { Section, Tag, When } from "./ui";

/** Hard constraints (never traded away) and soft preferences of the current goal version. */
export function Constraints({ view }: { view: EventStateView }) {
  const tz = view.timezone;
  const look = lookups(view);
  const goal = view.goal;
  const venue = view.resources.find((r) => r.definition.resource_id === goal.fixed_venue_id);
  const dependencies = view.activities.filter((a) => a.definition.predecessors.length > 0);
  const w = goal.objective_weights;
  return (
    <Section id="constraints" title="Required constraints">
      <ul className="constraint-list">
        <li>
          <Tag tone="neutral" icon="■">
            Hard
          </Tag>{" "}
          Fixed venue: {look.resourceLabel(goal.fixed_venue_id)}
          {venue !== undefined ? ` (capacity ${venue.definition.capacity})` : ""}
        </li>
        <li>
          <Tag tone="neutral" icon="■">
            Hard
          </Tag>{" "}
          Opens <When iso={goal.public_start} text={fmtTime(goal.public_start, tz)} />, everything
          ends by <When iso={goal.hard_end} text={fmtTime(goal.hard_end, tz)} />
        </li>
        <li>
          <Tag tone="neutral" icon="■">
            Hard
          </Tag>{" "}
          Required activities: {goal.required_activity_ids.map(look.activityLabel).join(", ")}
        </li>
        <li>
          <Tag tone="neutral" icon="■">
            Hard
          </Tag>{" "}
          Attendance target {goal.attendance_target}
          {venue !== undefined ? ` within venue capacity ${venue.definition.capacity}` : ""}
        </li>
        <li>
          <Tag tone="neutral" icon="■">
            Hard
          </Tag>{" "}
          At most {goal.program_concurrency} program{" "}
          {goal.program_concurrency === 1 ? "activity" : "activities"} at a time
        </li>
        {dependencies.map((a) => (
          <li key={a.definition.activity_id}>
            <Tag tone="neutral" icon="■">
              Hard
            </Tag>{" "}
            {a.definition.label} after {a.definition.predecessors.map(look.activityLabel).join(" and ")}
          </li>
        ))}
        <li>
          <Tag tone="neutral" icon="■">
            Hard
          </Tag>{" "}
          Total committed and held spending within {fmtCents(goal.budget_cents)}
        </li>
        <li>
          <Tag tone="neutral" icon="■">
            Hard
          </Tag>{" "}
          {goal.accessibility_requirements.length === 0
            ? "No accessibility requirements are configured for this event."
            : `Accessibility: ${goal.accessibility_requirements.map((r) => r.detail).join("; ")}`}
        </li>
      </ul>
      <h3 className="list-heading">Preferences (goal version {goal.version})</h3>
      <p>
        <Tag tone="info" icon="◇">
          Soft
        </Tag>{" "}
        Preset: <strong>{PRESET_LABEL[goal.preference_preset] ?? goal.preference_preset}</strong>
      </p>
      <p className="muted small">
        Ranking weights: {w.start_shift_per_minute} per minute moved, {w.changed_activity} per changed
        activity, {w.spend_per_100_cents} per $1.00 spent, {w.optional_activity_removed} per optional
        activity removed, {w.participant_notification} per person to notify.
      </p>
      {goal.priorities.length > 0 ? (
        <ol className="muted small">
          {goal.priorities.map((p) => (
            <li key={p}>{p}</li>
          ))}
        </ol>
      ) : null}
      {view.declared_assumptions.length > 0 ? (
        <details className="inline-details">
          <summary>Declared scenario assumptions ({view.declared_assumptions.length})</summary>
          <ul className="fact-list">
            {view.declared_assumptions.map((a) => (
              <li key={a.assumption_id}>
                <Tag tone="warn" icon="≈">
                  Assumption
                </Tag>{" "}
                {a.description}
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </Section>
  );
}

/** The authority envelope: each visible grant, its limits, usage and validity. */
export function Authority({ view }: { view: EventStateView }) {
  const tz = view.timezone;
  return (
    <Section id="authority" title="Authority (grants)">
      {view.grants.length === 0 ? (
        <p className="empty">No grant is visible to this role.</p>
      ) : (
        <ul className="grant-list">
          {view.grants.map((g) => {
            const status = g.revoked
              ? { tone: "bad" as const, icon: "⊘", text: "Revoked" }
              : g.valid_now
                ? { tone: "ok" as const, icon: "✓", text: "Valid now" }
                : { tone: "warn" as const, icon: "⧖", text: "Not valid now" };
            return (
              <li key={g.grant.grant_id}>
                <p>
                  <strong>{g.grant.principal_id}</strong>{" "}
                  <span className="muted">
                    ({g.grant.principal_role.replace(/_/g, " ")}, <code>{g.grant.grant_id}</code> v{g.version})
                  </span>{" "}
                  <Tag tone={status.tone} icon={status.icon}>
                    {status.text}
                  </Tag>
                </p>
                <p className="small">
                  Committed {fmtCents(g.committed_used_cents)} of {fmtCents(g.grant.max_total_committed_cents)}
                  {" · "}held {fmtCents(g.reserved_used_cents)} of {fmtCents(g.grant.max_total_reserved_cents)}
                  {" · "}expires <When iso={g.grant.expires_at} text={fmtTime(g.grant.expires_at, tz)} />
                </p>
                <p className="muted small">Tools: {g.grant.allowed_tools.join(", ")}</p>
                {g.grant.review_required_for.length > 0 ? (
                  <p className="muted small">Needs review: {g.grant.review_required_for.join("; ")}</p>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
    </Section>
  );
}
