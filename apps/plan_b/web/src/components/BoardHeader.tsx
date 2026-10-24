import type { ReactNode } from "react";

import { ROLE_LABEL, fmtDate, fmtTime, zoneName } from "../format";
import type { EventStateView } from "../types";
import { Code, When } from "./ui";

export type BoardMode = "live" | "replay";

export const PRODUCT_NAME = "Plan B: The Show Must Go On";
export const SANDBOX_NOTICE = "Fictional sandbox — no real bookings, purchases, or messages";

/** Persistent identity strip: product, sandbox notice, mode, clock, goal, versions, viewer. */
export function BoardHeader({
  view,
  mode,
  actions,
}: {
  view: EventStateView;
  mode: BoardMode;
  actions?: ReactNode;
}) {
  const tz = view.timezone;
  const zone = zoneName(view.clock, tz);
  return (
    <header className="board-header">
      <div className="brand-row">
        <p className="product-name">{PRODUCT_NAME}</p>
        <p className="sandbox-label">
          <span aria-hidden="true">⚠ </span>
          {SANDBOX_NOTICE}
        </p>
        <p className={`mode-label mode-${mode}`}>
          <span aria-hidden="true">{mode === "live" ? "⚙ " : "▸ "}</span>
          {mode === "live" ? "Deterministic policy" : "Recorded replay"}
        </p>
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
