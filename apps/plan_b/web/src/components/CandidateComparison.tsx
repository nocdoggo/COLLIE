import { useState } from "react";

import {
  CHECK_STATUS_LABEL,
  PASSES_UNDER_ASSUMPTION_LABEL,
  checkName,
  fmtCents,
  fmtTime,
  fmtWindow,
  lookups,
} from "../format";
import type { CandidateCheck, CandidateResult, EvaluationResult, EventStateView } from "../types";
import { EvidenceCard } from "./EvidenceCard";
import {
  applicabilityLabel,
  bestApplicableText,
  evaluationIsStale,
  groupChecks,
} from "./candidateStatus";
import type { CurrentVersions } from "./candidateStatus";
import { Empty, Section, StatusBadge, Tag, When } from "./ui";

const DEFAULT_SHOWN = 3;

const OBJECTIVE_TERMS: { key: keyof CandidateResult["objective"]; label: string; money?: boolean }[] = [
  { key: "start_shift_minutes", label: "Start-time shift (minutes)" },
  { key: "changed_activities", label: "Changed activities" },
  { key: "additional_committed_cents", label: "Additional committed spend", money: true },
  { key: "optional_activities_removed", label: "Optional activities removed" },
  { key: "participant_notifications", label: "People to notify" },
];

/** Weighted value of one term; the planner keys `weighted` by the same term names. */
function weightedValue(candidate: CandidateResult, key: string): number | null {
  return candidate.objective.weighted[key] ?? null;
}

function CheckLine({ check }: { check: CandidateCheck }) {
  return (
    <>
      <StatusBadge label={CHECK_STATUS_LABEL[check.status]} /> {checkName(check.constraint_id)}
      {check.detail ? <span className="muted"> — {check.detail}</span> : null}
    </>
  );
}

function CandidateCard({
  candidate,
  evaluation,
  view,
  current,
}: {
  candidate: CandidateResult;
  evaluation: EvaluationResult;
  view: EventStateView;
  current: CurrentVersions;
}) {
  const tz = view.timezone;
  const look = lookups(view);
  const groups = groupChecks(candidate);
  const applicability = applicabilityLabel(candidate, evaluation, current);
  const isBest = evaluation.best_candidate_id === candidate.candidate_id;
  const isBestApplicable = evaluation.best_applicable_candidate_id === candidate.candidate_id;
  const isKeep = evaluation.keep_candidate_id === candidate.candidate_id;
  const counts = [
    `${groups.confirmed.length} confirmed`,
    `${groups.underAssumption.length} under assumptions`,
    ...(groups.notApplicable.length > 0 ? [`${groups.notApplicable.length} not applicable`] : []),
    ...(groups.unsupported.length > 0 ? [`${groups.unsupported.length} unsupported`] : []),
  ];
  return (
    <li className="candidate">
      <h3 className="candidate-title">
        {candidate.rank !== null ? <span className="rank">#{candidate.rank}</span> : null}{" "}
        {candidate.label}
      </h3>
      <p className="candidate-tags">
        <Tag tone="ok" icon="✓">
          Feasible under assumptions
        </Tag>
        <Tag tone={applicability.tone} icon={applicability.icon}>
          {applicability.text}
        </Tag>
        {isBest ? <Tag tone="info">Best ranked</Tag> : null}
        {isBestApplicable && !isBest ? <Tag tone="info">{bestApplicableText(evaluation, current)}</Tag> : null}
        {isKeep ? <Tag tone="neutral">Keeps the current plan</Tag> : null}
      </p>
      <p>
        {candidate.changed_activity_ids.length === 0
          ? "No activity changes."
          : `Changes ${candidate.changed_activity_ids.map(look.activityLabel).join(", ")}.`}{" "}
        Additional committed spend {fmtCents(candidate.incremental_committed_cents)}.
      </p>
      <table className="table compact">
        <caption className="sr-only">Objective terms for {candidate.label}</caption>
        <thead>
          <tr>
            <th scope="col">Objective term</th>
            <th scope="col">Value</th>
            <th scope="col">Weighted</th>
          </tr>
        </thead>
        <tbody>
          {OBJECTIVE_TERMS.map((term) => {
            const raw = candidate.objective[term.key];
            const value = typeof raw === "number" ? raw : 0;
            const weighted = weightedValue(candidate, term.key);
            return (
              <tr key={term.key}>
                <th scope="row">{term.label}</th>
                <td>{term.money === true ? fmtCents(value) : value}</td>
                <td>{weighted ?? "—"}</td>
              </tr>
            );
          })}
          <tr className="total-row">
            <th scope="row">Total (lower is better)</th>
            <td />
            <td>{candidate.objective.total}</td>
          </tr>
        </tbody>
      </table>
      {candidate.assumptions.length > 0 ? (
        <ul className="fact-list">
          {candidate.assumptions.map((a) => (
            <li key={a.assumption_id}>
              <Tag tone="warn" icon="≈">
                Assumption
              </Tag>{" "}
              {a.text} <span className="muted">({a.kind.replace(/_/g, " ")}, {look.entityLabel(a.entity_id)})</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted">No assumptions recorded for this alternative.</p>
      )}
      {candidate.required_holds.length > 0 ? (
        <div>
          <span className="eyebrow">Required holds</span>
          <ul className="fact-list">
            {candidate.required_holds.map((h) => (
              <li key={`${h.resource_id}-${h.activity_id}`}>
                {look.resourceLabel(h.resource_id)} for {look.activityLabel(h.activity_id)} (
                {fmtWindow(h.window.start, h.window.end, tz)}):{" "}
                {h.bound_hold_id !== null ? (
                  <Tag tone="ok" icon="‖">
                    Held by {h.bound_hold_id}
                  </Tag>
                ) : (
                  <Tag tone="warn" icon="○">
                    No live hold yet
                  </Tag>
                )}{" "}
                commitment cost {fmtCents(h.commitment_cost_cents)}
                {h.commitment_cutoff !== null ? (
                  <>
                    ; must be committed before{" "}
                    <When iso={h.commitment_cutoff} text={fmtTime(h.commitment_cutoff, tz)} />
                  </>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {candidate.authorization.missing.length > 0 ? (
        <div>
          <span className="eyebrow">Missing permissions</span>
          <ul className="fact-list">
            {candidate.authorization.missing.map((m, index) => (
              <li key={`${m.kind}-${index}`}>
                <Tag tone="bad" icon="⚑">
                  {m.kind.replace(/_/g, " ")}
                </Tag>{" "}
                {m.detail}
                {m.current_value !== null && m.required_value !== null ? (
                  <span className="muted">
                    {" "}
                    (current {m.field === "max_total_committed_cents" || m.field === "max_total_reserved_cents"
                      ? fmtCents(m.current_value)
                      : m.current_value}
                    , required{" "}
                    {m.field === "max_total_committed_cents" || m.field === "max_total_reserved_cents"
                      ? fmtCents(m.required_value)
                      : m.required_value}
                    )
                  </span>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <p className="muted">The current grant authorizes this change.</p>
      )}
      {candidate.execution_preconditions.length > 0 ? (
        <div>
          <span className="eyebrow">Still required at execution time</span>
          <ul className="fact-list">
            {candidate.execution_preconditions.map((p) => (
              <li key={p}>{p}</li>
            ))}
          </ul>
        </div>
      ) : null}
      <details className="inline-details">
        <summary>Hard-constraint checks ({counts.join(", ")})</summary>
        {groups.underAssumption.length > 0 ? (
          <>
            <span className="eyebrow">Pass only under an assumption</span>
            <ul className="fact-list">
              {groups.underAssumption.map(({ check, assumptions }) => (
                <li key={check.constraint_id}>
                  <StatusBadge label={PASSES_UNDER_ASSUMPTION_LABEL} /> {checkName(check.constraint_id)}
                  {check.detail ? <span className="muted"> — {check.detail}</span> : null}
                  <ul className="fact-list sub">
                    {assumptions.map((a) => (
                      <li key={a.assumption_id}>Assumes: {a.text}</li>
                    ))}
                  </ul>
                </li>
              ))}
            </ul>
          </>
        ) : null}
        <span className="eyebrow">Confirmed facts</span>
        {groups.confirmed.length > 0 ? (
          <ul className="fact-list">
            {groups.confirmed.map((c) => (
              <li key={c.constraint_id}>
                <CheckLine check={c} />
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted small">No check passes on observed evidence alone.</p>
        )}
        {groups.notApplicable.length + groups.unsupported.length > 0 ? (
          <ul className="fact-list">
            {[...groups.notApplicable, ...groups.unsupported].map((c) => (
              <li key={c.constraint_id}>
                <CheckLine check={c} />
              </li>
            ))}
          </ul>
        ) : null}
      </details>
      {candidate.rationale ? <p className="muted">{candidate.rationale}</p> : null}
      <EvidenceCard title="Candidate record (JSON)" value={candidate} hint={candidate.candidate_id} />
    </li>
  );
}

function RejectedCard({ candidate }: { candidate: CandidateResult }) {
  const failed = candidate.checks.filter((c) => c.status === "failed");
  const unsupported = candidate.checks.filter((c) => c.status === "unsupported");
  return (
    <li className="candidate rejected">
      <h4 className="candidate-title">
        {candidate.label}{" "}
        {candidate.constraint_status === "infeasible" ? (
          <Tag tone="bad" icon="✖">
            Infeasible
          </Tag>
        ) : (
          <Tag tone="warn" icon="?">
            Result unknown
          </Tag>
        )}
      </h4>
      <ul className="fact-list">
        {failed.map((c) => (
          <li key={c.constraint_id}>
            <span aria-hidden="true">✖ </span>
            <strong>Fails: {checkName(c.constraint_id)}</strong>
            {c.detail ? <> — {c.detail}</> : null}
          </li>
        ))}
        {unsupported.map((c) => (
          <li key={c.constraint_id}>
            <span aria-hidden="true">? </span>
            <strong>Unsupported: {checkName(c.constraint_id)}</strong>
            {c.detail ? <> — {c.detail}</> : null}
          </li>
        ))}
      </ul>
    </li>
  );
}

/** Ranked feasible alternatives and rejected ones from the latest stored evaluation. */
export function CandidateComparison({ view }: { view: EventStateView }) {
  const [showAll, setShowAll] = useState(false);
  const evaluation = view.latest_evaluation;
  const tz = view.timezone;
  if (evaluation === null) {
    return (
      <Section id="candidates" title="Alternatives">
        <Empty>No alternatives have been evaluated in this episode yet.</Empty>
      </Section>
    );
  }
  const feasible = evaluation.candidates
    .filter((c) => c.constraint_status === "feasible_under_assumptions")
    .sort((a, b) => (a.rank ?? Number.MAX_SAFE_INTEGER) - (b.rank ?? Number.MAX_SAFE_INTEGER));
  const rejected = evaluation.candidates.filter(
    (c) => c.constraint_status !== "feasible_under_assumptions",
  );
  const shown = showAll ? feasible : feasible.slice(0, DEFAULT_SHOWN);
  const current: CurrentVersions = { revision: view.revision, goalVersion: view.goal.version };
  const stale = evaluationIsStale(evaluation, current);
  return (
    <Section
      id="candidates"
      title="Alternatives"
      subtitle={
        <>
          Evaluation <code>{evaluation.evaluation_id}</code> at{" "}
          <When iso={evaluation.evaluated_at} text={fmtTime(evaluation.evaluated_at, tz)} /> by{" "}
          <code>{evaluation.actor_id}</code> for revision {evaluation.revision}, goal version{" "}
          {evaluation.goal_version}. {evaluation.generated_count} generated,{" "}
          {evaluation.evaluated_count} evaluated
          {evaluation.truncated ? " (truncated at the candidate cap)" : ""}.
        </>
      }
    >
      {evaluation.hypothetical ? (
        <p className="notice tone-warn">
          <span aria-hidden="true">≈ </span>
          Hypothetical evaluation (what-if: {evaluation.hypotheses.map((h) => h.label).join("; ")}).
          None of these alternatives can be applied.
        </p>
      ) : null}
      {stale ? (
        <p className="notice tone-warn">
          <span aria-hidden="true">⚠ </span>
          The event changed after this evaluation (now revision {view.revision}, goal version{" "}
          {view.goal.version}). These results describe revision {evaluation.revision}; none of
          them can be applied until the alternatives are evaluated again.
        </p>
      ) : null}
      {evaluation.infeasibility !== null ? (
        <div className="notice tone-bad">
          <p>
            <span aria-hidden="true">⚠ </span>
            <strong>No alternative in the declared action space passes every hard constraint.</strong>{" "}
            {evaluation.infeasibility.detail}
          </p>
          <p>
            Blocking: {evaluation.infeasibility.blocking_constraints.map(checkName).join("; ")}.
            Action space: {evaluation.infeasibility.declared_action_space}.
          </p>
        </div>
      ) : null}
      {feasible.length === 0 ? (
        <Empty>No feasible alternative.</Empty>
      ) : (
        <>
          <h3 className="list-heading">
            Feasible alternatives ({feasible.length}), best first
          </h3>
          <ol className="candidates">
            {shown.map((c) => (
              <CandidateCard
                key={c.candidate_id}
                candidate={c}
                evaluation={evaluation}
                view={view}
                current={current}
              />
            ))}
          </ol>
          {feasible.length > DEFAULT_SHOWN ? (
            <button
              type="button"
              className="button secondary"
              aria-expanded={showAll}
              onClick={() => setShowAll(!showAll)}
            >
              {showAll ? `Show the top ${DEFAULT_SHOWN} only` : `Show all ${feasible.length} feasible alternatives`}
            </button>
          ) : null}
        </>
      )}
      {rejected.length > 0 ? (
        <details className="inline-details">
          <summary>Rejected alternatives ({rejected.length}) and the checks they fail</summary>
          <ul className="candidates">
            {rejected.map((c) => (
              <RejectedCard key={c.candidate_id} candidate={c} />
            ))}
          </ul>
        </details>
      ) : null}
    </Section>
  );
}
