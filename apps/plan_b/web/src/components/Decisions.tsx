import { useState } from "react";

import { DECISION_LABEL, compareIso, fmtCents, fmtTime, lookups } from "../format";
import type { EventStateView } from "../types";
import { AUTHORIZATION_STATE_TEXT, authorizationRequests } from "./authorization";
import { EvidenceCard } from "./EvidenceCard";
import { Code, Empty, JumpButton, Section, StatusBadge, Tag, When, domId } from "./ui";

/** Policy decisions (kind + summary), newest first, with their evidence references. */
export function Decisions({ view }: { view: EventStateView }) {
  const tz = view.timezone;
  const look = lookups(view);
  const requests = new Map(authorizationRequests(view).map((item) => [item.request.request_id, item]));
  const decisions = view.decisions
    .map((d, index) => ({ d, index }))
    .sort((a, b) => compareIso(b.d.at, a.d.at) || b.d.revision - a.d.revision || b.index - a.index)
    .map((x) => x.d);
  return (
    <Section
      id="decisions"
      title={`Policy decisions (${decisions.length})`}
      subtitle="What the deterministic policy decided and why, as narration. Receipts are the evidence."
    >
      {decisions.length === 0 ? (
        <Empty>No decisions recorded.</Empty>
      ) : (
        <ol className="decisions">
          {decisions.map((d) => {
            const request = d.authorization_request;
            const item = request !== null ? requests.get(request.request_id) : undefined;
            const isLatestForRequest = item !== undefined && item.decision.decision_id === d.decision_id;
            return (
              <li key={d.decision_id} id={domId("dec", d.decision_id)} tabIndex={-1} className="decision">
                <p>
                  <StatusBadge label={DECISION_LABEL[d.kind]} /> {d.summary}
                </p>
                <p className="muted small">
                  <When iso={d.at} text={fmtTime(d.at, tz)} /> · revision {d.revision} · <Code>{d.policy_id}</Code>
                  {d.wait_until !== null ? (
                    <>
                      {" "}· wait until <When iso={d.wait_until} text={fmtTime(d.wait_until, tz)} />
                    </>
                  ) : null}
                </p>
                {request !== null ? (
                  <div className="notice tone-warn">
                    <p>
                      <span aria-hidden="true">⚑ </span>
                      <strong>Authorization request</strong>: raise <Code>{request.target_grant_id}</Code>{" "}
                      committed limit from {fmtCents(request.current_value)} to{" "}
                      {fmtCents(request.requested_value)} for {look.resourceLabel(request.resource_id)} (candidate{" "}
                      <Code>{request.candidate_id}</Code>). {request.reason}
                    </p>
                    {isLatestForRequest ? (
                      <p>
                        <Tag tone={item.state === "open" ? "warn" : "neutral"} icon={item.state === "open" ? "⧗" : "✓"}>
                          {AUTHORIZATION_STATE_TEXT[item.state]}
                        </Tag>
                      </p>
                    ) : null}
                  </div>
                ) : null}
                {d.observation_refs.length > 0 ? (
                  <p className="small">
                    Updates:{" "}
                    {d.observation_refs.map((ref) => (
                      <JumpButton key={ref} targetId={domId("obs", ref)}>
                        {ref}
                      </JumpButton>
                    ))}
                  </p>
                ) : null}
                {d.receipt_refs.length > 0 ? (
                  <p className="small">
                    Receipts:{" "}
                    {d.receipt_refs.map((ref) => (
                      <JumpButton key={ref} targetId={domId("rcpt", ref)}>
                        {ref}
                      </JumpButton>
                    ))}
                  </p>
                ) : null}
                {d.candidate_refs.length > 0 ? (
                  <p className="small muted">Candidates: {d.candidate_refs.join(", ")}</p>
                ) : null}
                {d.tool_call_refs.length > 0 ? (
                  <p className="small muted">Tool calls: {d.tool_call_refs.join(", ")}</p>
                ) : null}
                {Object.keys(d.details).length > 0 ? (
                  <EvidenceCard title="Decision details (JSON)" value={d.details} />
                ) : null}
              </li>
            );
          })}
        </ol>
      )}
    </Section>
  );
}

const TRANSITIONS_SHOWN = 10;

/** Every revision increment, newest first. */
export function Transitions({ view }: { view: EventStateView }) {
  const [showAll, setShowAll] = useState(false);
  const tz = view.timezone;
  const items = [...view.transitions].sort((a, b) => b.revision - a.revision);
  const shown = showAll ? items : items.slice(0, TRANSITIONS_SHOWN);
  return (
    <Section id="transitions" title={`State transitions (${items.length})`}>
      {items.length === 0 ? (
        <Empty>No transitions recorded.</Empty>
      ) : (
        <>
          <ol className="transitions">
            {shown.map((t) => (
              <li key={`${t.revision}-${t.cause_kind}-${t.cause_ref ?? ""}`}>
                <span className="feed-time">
                  <When iso={t.at} text={fmtTime(t.at, tz)} />
                </span>{" "}
                <strong>r{t.revision}</strong> <span className="muted">{t.cause_kind}</span> {t.summary}
              </li>
            ))}
          </ol>
          {items.length > TRANSITIONS_SHOWN ? (
            <button
              type="button"
              className="button secondary"
              aria-expanded={showAll}
              onClick={() => setShowAll(!showAll)}
            >
              {showAll ? "Show recent transitions only" : `Show all ${items.length} transitions`}
            </button>
          ) : null}
        </>
      )}
    </Section>
  );
}

/** Raw JSON of everything the board is built from. */
export function EvidenceDrawer({ view }: { view: EventStateView }) {
  return (
    <section id="evidence" aria-labelledby="evidence-title" className="card">
      <details className="drawer">
        <summary>
          <h2 id="evidence-title" className="card-title inline">
            Evidence drawer (raw JSON)
          </h2>
        </summary>
        <div className="drawer-body">
          <EvidenceCard title={`Receipts (${view.receipts.length})`} value={view.receipts} />
          <EvidenceCard title="Latest evaluation" value={view.latest_evaluation} />
          <EvidenceCard title={`Observations (${view.observations.length})`} value={view.observations} />
          <EvidenceCard title={`Transitions (${view.transitions.length})`} value={view.transitions} />
          <EvidenceCard title={`Policy decisions (${view.decisions.length})`} value={view.decisions} />
          <EvidenceCard title={`Attempts without receipt (${view.attempts.length})`} value={view.attempts} />
          <EvidenceCard title="Plan and plan history" value={{ plan: view.plan, plan_history: view.plan_history }} />
          <EvidenceCard title="Holds and commitments" value={{ holds: view.holds, commitments: view.commitments }} />
          <EvidenceCard title="Check-ins" value={view.checkins} />
          <EvidenceCard title="Grants and grant history" value={{ grants: view.grants, grant_history: view.grant_history }} />
          <EvidenceCard title="Goal and goal history" value={{ goal: view.goal, goal_history: view.goal_history }} />
          <EvidenceCard title="Resources" value={view.resources} />
          <EvidenceCard title="Activities" value={view.activities} />
          <EvidenceCard title="Complete state view" value={view} />
        </div>
      </details>
    </section>
  );
}
