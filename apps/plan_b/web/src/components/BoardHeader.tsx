import type { ReactNode } from "react";

import { ROLE_LABEL, fmtDate, fmtTime, zoneName } from "../format";
import type { EventStateView } from "../types";
import { policyModeOf } from "./policyMode";
import type { PolicyMode, PolicySelection } from "./policyMode";
import { Code, When } from "./ui";

export type BoardMode = "live" | "replay";

export const PRODUCT_NAME = "Plan B: The Show Must Go On";
export const SANDBOX_NOTICE = "Fictional sandbox: no real bookings, purchases, or messages";

/** The policy label: which coordinator policy ran ("Deterministic policy", "Live agent · <model>"). */
export function PolicyLabel({ policy, mode }: { policy: PolicyMode; mode: BoardMode }) {
  return (
    <p className={`mode-label ${mode === "live" ? "mode-live" : "mode-policy"} policy-${policy.kind}`} data-policy-mode={policy.kind}>
      <span aria-hidden="true">{policy.kind === "live" ? "✦ " : "⚙ "}</span>
      {policy.label}
      {policy.basis === "selected" ? <span className="mode-note"> · selected, not run yet</span> : null}
    </p>
  );
}

/** Persistent identity strip: product, sandbox notice, mode, clock, goal, versions, viewer. */
export function BoardHeader({
  view,
  mode,
  actions,
  selection = null,
}: {
  view: EventStateView;
  mode: BoardMode;
  actions?: ReactNode;
  /** The policy a moderator selected; it labels the board until a decision is recorded. */
  selection?: PolicySelection | null;
}) {
  const tz = view.timezone;
  const zone = zoneName(view.clock, tz);
  const policy = policyModeOf(view.decisions, selection);
  return (
    <header className="board-header">
      <div className="brand-row">
        <p className="product-name">{PRODUCT_NAME}</p>
        <p className="sandbox-label">
          <span aria-hidden="true">⚠ </span>
          {SANDBOX_NOTICE}
        </p>
        {mode === "replay" ? (
          <p className="mode-label mode-replay">
            <span aria-hidden="true">▸ </span>Recorded replay
          </p>
        ) : null}
        <PolicyLabel policy={policy} mode={mode} />
        <p className="viewer-label">
          {mode === "live" ? "Signed in as " : "Recorded view of "}
          <strong>{view.viewer.display_name}</strong>
          {" · "}
          {ROLE_LABEL[view.viewer.role] ?? view.viewer.role}
          {" · "}
          <Code>{view.viewer.principal_id}</Code>
        </p>
        {actions}
      </div>
      <div className="hero">
        <div className="hero-clock">
          <span className="eyebrow">Scenario clock</span>
          <span className="clock-time">
            <When iso={view.clock} text={fmtTime(view.clock, tz)} />
          </span>
          <span className="clock-date">
            {fmtDate(view.clock, tz)} · {zone} ({tz})
          </span>
        </div>
        <div className="hero-goal">
          <span className="eyebrow">Event goal</span>
          <p className="goal-text">{view.goal.description}</p>
          <p className="goal-deadline">
            Opens <When iso={view.goal.public_start} text={fmtTime(view.goal.public_start, tz)} />
            {" · "}
            Public deadline:{" "}
            <strong>
              must finish by <When iso={view.goal.hard_end} text={fmtTime(view.goal.hard_end, tz)} />{" "}
              {zoneName(view.goal.hard_end, tz)}
            </strong>
          </p>
        </div>
        <dl className="hero-versions">
          <div>
            <dt>State revision</dt>
            <dd>{view.revision}</dd>
          </div>
          <div>
            <dt>Goal version</dt>
            <dd>{view.goal.version}</dd>
          </div>
          <div>
            <dt>Episode</dt>
            <dd>
              {view.episode_status === "active" ? "Active" : "Closed"}
              <span className="sub">
                <Code>{view.episode_id}</Code>
              </span>
            </dd>
          </div>
        </dl>
      </div>
    </header>
  );
}
