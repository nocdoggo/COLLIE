import {
  HOLD_STATUS_LABEL,
  fmtCents,
  fmtTime,
  fmtWindow,
  lookups,
} from "../format";
import type { EventStateView } from "../types";
import { EvidenceCard } from "./EvidenceCard";
import { checkInCoverage, coverageLabel, latestCheckIn, roleNeeds } from "./checkins";
import { Empty, Section, StatusBadge, Tag, When } from "./ui";

/** Committed (spent) versus reserved (held, refundable) versus remaining. */
export function Budget({ view }: { view: EventStateView }) {
  const b = view.budget;
  const total = Math.max(1, b.budget_cents);
  const pct = (cents: number) => `${Math.min(100, Math.max(0, (cents / total) * 100))}%`;
  return (
    <Section id="budget" title="Budget">
      <dl className="budget-figures">
        <div>
          <dt>Spent (committed)</dt>
          <dd>{fmtCents(b.committed_cents)}</dd>
        </div>
        <div>
          <dt>Held (reserved, refundable)</dt>
          <dd>{fmtCents(b.reserved_cents)}</dd>
        </div>
        <div>
          <dt>Remaining</dt>
          <dd className={b.remaining_cents < 0 ? "tone-text-bad" : undefined}>
            {fmtCents(b.remaining_cents)}
          </dd>
        </div>
        <div>
          <dt>Event budget</dt>
          <dd>{fmtCents(b.budget_cents)}</dd>
        </div>
      </dl>
      <div className="budget-bar" aria-hidden="true">
        <span className="budget-committed" style={{ width: pct(b.committed_cents) }} />
        <span className="budget-reserved" style={{ width: pct(b.reserved_cents) }} />
      </div>
      <p className="muted small">
        Bar: solid = spent, striped = held, empty = remaining. Amounts are fictional sandbox money.
      </p>
    </Section>
  );
}

/**
 * Check-ins for every person resource, and which scheduled activities need them. "Checked in"
 * means the latest check-in covers every remaining slot (or the clock, when none remain).
 */
export function RoleReadiness({ view }: { view: EventStateView }) {
  const tz = view.timezone;
  const look = lookups(view);
  const people = view.resources.filter((r) => r.definition.kind === "person");
  return (
    <Section
      id="role-readiness"
      title="Role readiness"
      subtitle={
        "A missing check-in means not yet confirmed, not absent. A check-in counts only for the " +
        "slots its availability covers."
      }
    >
      {people.length === 0 ? (
        <Empty>No roles are defined.</Empty>
      ) : (
        <ul className="role-list">
          {people.map((r) => {
            const id = r.definition.resource_id;
            const latest = latestCheckIn(view.checkins, id);
            const needed = view.plan.assignments.filter((a) => a.resource_ids.includes(id));
            const coverage = checkInCoverage(view.checkins, id, roleNeeds(view.activities, id, view.clock));
            const label = coverageLabel(coverage, tz, look.activityLabel);
            return (
              <li key={id}>
                <p>
                  <strong>{r.definition.label}</strong> <span className="muted">({id})</span>{" "}
                  <Tag tone={label.tone} icon={label.icon}>
                    {label.text}
                  </Tag>
                </p>
                {latest !== undefined ? (
                  <p className="muted">
                    At <When iso={latest.at} text={fmtTime(latest.at, tz)} />, available{" "}
                    {fmtWindow(latest.available.start, latest.available.end, tz)}
                    {latest.channel === "fixture_initial" ? " (authored setup)" : " (participant session)"}
                    {latest.principal_id !== null ? <> by <code>{latest.principal_id}</code></> : null}
                  </p>
                ) : null}
                {needed.length > 0 ? (
                  <p className="muted small">
                    Needed for{" "}
                    {needed
                      .map((a) => `${look.activityLabel(a.activity_id)} ${fmtWindow(a.start, a.end, tz)}`)
                      .join(", ")}
                  </p>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
    </Section>
  );
}

/** Holds with expiry and commitment cutoff shown apart from the activity start; commitments. */
export function HoldsAndCommitments({ view }: { view: EventStateView }) {
  const tz = view.timezone;
  const look = lookups(view);
  const holds = [...view.holds].reverse();
  return (
    <Section id="holds" title="Holds and commitments">
      <h3 className="list-heading">Holds ({holds.length})</h3>
      {holds.length === 0 ? (
        <Empty>No holds have been placed.</Empty>
      ) : (
        <ul className="hold-list">
          {holds.map((h) => {
            const activity = view.activities.find((a) => a.definition.activity_id === h.activity_id);
            const start = activity?.assignment?.start ?? h.window.start;
            return (
              <li key={h.hold_id} className="hold">
                <p>
                  <strong>{look.resourceLabel(h.resource_id)}</strong> for{" "}
                  {look.activityLabel(h.activity_id)}{" "}
                  <StatusBadge label={HOLD_STATUS_LABEL[h.effective_status]} />
                  {h.status !== h.effective_status ? (
                    <span className="muted"> (stored as {h.status}; effective at the current clock)</span>
                  ) : null}
                </p>
                <dl className="hold-times">
                  <div>
                    <dt>Hold expires</dt>
                    <dd>
                      <When iso={h.expires_at} text={fmtTime(h.expires_at, tz)} />
                    </dd>
                  </div>
                  <div>
                    <dt>Commit before (cutoff)</dt>
                    <dd>
                      {h.commitment_cutoff !== null ? (
                        <When iso={h.commitment_cutoff} text={fmtTime(h.commitment_cutoff, tz)} />
                      ) : (
                        "No cutoff"
                      )}
                    </dd>
                  </div>
                  <div>
                    <dt>Activity starts</dt>
                    <dd>
                      <When iso={start} text={fmtTime(start, tz)} />
                    </dd>
                  </div>
                  <div>
                    <dt>Reserved</dt>
                    <dd>
                      {fmtCents(h.reserved_cents)}
                      {h.hold_fee_cents > 0 ? `, fee ${fmtCents(h.hold_fee_cents)}` : ""}
                    </dd>
                  </div>
                </dl>
                <p className="muted small">
                  Window {fmtWindow(h.window.start, h.window.end, tz)} · quantity {h.quantity} · placed
                  at <When iso={h.created_at} text={fmtTime(h.created_at, tz)} /> by{" "}
                  <code>{h.actor_id}</code> (receipt <code>{h.created_receipt_id}</code>)
                  {h.terminal_at !== null ? (
                    <>
                      {" "}· ended at <When iso={h.terminal_at} text={fmtTime(h.terminal_at, tz)} />
                      {h.terminal_receipt_id !== null ? <> (receipt <code>{h.terminal_receipt_id}</code>)</> : null}
                    </>
                  ) : null}
                  {h.commitment_id !== null ? <> · became commitment <code>{h.commitment_id}</code></> : null}
                </p>
                <EvidenceCard title="Hold record (JSON)" value={h} />
              </li>
            );
          })}
        </ul>
      )}
      <h3 className="list-heading">Commitments ({view.commitments.length})</h3>
      {view.commitments.length === 0 ? (
        <Empty>No commitments. Nothing has been booked or charged.</Empty>
      ) : (
        <ul className="hold-list">
          {view.commitments.map((c) => (
            <li key={c.commitment_id} className="hold">
              <p>
                <strong>{look.resourceLabel(c.resource_id)}</strong> for {look.activityLabel(c.activity_id)}{" "}
                <Tag tone="ok" icon="✔">
                  Committed {fmtCents(c.committed_cents)}
                </Tag>
              </p>
              <p className="muted small">
                Window {fmtWindow(c.window.start, c.window.end, tz)} · plan version {c.plan_version} ·
                created <When iso={c.created_at} text={fmtTime(c.created_at, tz)} /> by{" "}
                <code>{c.actor_id}</code> (receipt <code>{c.receipt_id}</code>)
                {c.source_hold_id !== null ? <> · from hold <code>{c.source_hold_id}</code></> : null}
              </p>
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}
