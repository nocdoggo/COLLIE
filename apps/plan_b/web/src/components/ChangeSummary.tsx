import type { ReactNode } from "react";

import {
  DECISION_LABEL,
  compareIso,
  fmtTime,
  receiptLabel,
} from "../format";
import type { EventStateView, PolicyDecision } from "../types";
import { authorizationRequests } from "./authorization";
import { Empty, JumpButton, Section, StatusBadge, Tag, When, domId } from "./ui";

interface FeedItem {
  readonly key: string;
  readonly at: string;
  readonly revision: number;
  readonly order: number;
  readonly render: () => ReactNode;
}

const FEED_LIMIT = 8;

export function latestDecision(view: EventStateView): PolicyDecision | null {
  let best: PolicyDecision | null = null;
  for (const d of view.decisions) {
    // Later time wins; at equal time a higher revision, then the later record, wins.
    if (best === null || compareIso(d.at, best.at) > 0) best = d;
    else if (compareIso(d.at, best.at) === 0 && d.revision >= best.revision) best = d;
  }
  return best;
}

/** "What changed and what the app did": latest state changes, decisions and receipts. */
export function ChangeSummary({ view }: { view: EventStateView }) {
  const tz = view.timezone;
  const current = latestDecision(view);
  const openRequests = authorizationRequests(view).filter((r) => r.state === "open");

  const items: FeedItem[] = [];
  view.transitions.forEach((t, index) => {
    items.push({
      key: `t-${t.revision}-${index}`,
      at: t.at,
      revision: t.revision,
      order: 0,
      render: () => (
        <>
          <Tag tone="info" icon="Δ">
            State change
          </Tag>{" "}
          <span>{t.summary}</span>{" "}
          <span className="muted">(revision {t.revision})</span>
        </>
      ),
    });
  });
  view.decisions.forEach((d, index) => {
    items.push({
      key: `d-${d.decision_id}-${index}`,
      at: d.at,
      revision: d.revision,
      order: 1,
      render: () => (
        <>
          <Tag tone="neutral" icon="✎">
            Policy decision
          </Tag>{" "}
          <StatusBadge label={DECISION_LABEL[d.kind]} /> <span>{d.summary}</span>
        </>
      ),
    });
  });
  view.receipts.forEach((r, index) => {
    items.push({
      key: `r-${r.receipt_id}-${index}`,
      at: r.executed_at,
      revision: r.revision_after,
      order: 2,
      render: () => (
        <>
          <Tag tone="neutral" icon="▣">
            Receipt
          </Tag>{" "}
          <StatusBadge label={receiptLabel(r)} /> <strong>{r.tool}</strong>{" "}
          <span>{r.summary}</span>{" "}
          <JumpButton targetId={domId("rcpt", r.receipt_id)}>evidence</JumpButton>
        </>
      ),
    });
  });
  items.sort(
    (a, b) => compareIso(b.at, a.at) || b.revision - a.revision || b.order - a.order,
  );
  const feed = items.slice(0, FEED_LIMIT);

  return (
    <Section
      id="what-changed"
      title="What changed and what the app did"
      subtitle="Policy decisions are narration, not evidence. Only receipts show what was done."
    >
      {current !== null ? (
        <div className="current-decision">
          <span className="eyebrow">Latest policy decision</span>
          <p className="current-decision-text">
            <StatusBadge label={DECISION_LABEL[current.kind]} /> {current.summary}
          </p>
          <p className="muted">
            Recorded at <When iso={current.at} text={fmtTime(current.at, tz)} /> (revision{" "}
            {current.revision}) by <code>{current.policy_id}</code>
            {current.wait_until !== null ? (
              <>
                {" · "}waiting until <When iso={current.wait_until} text={fmtTime(current.wait_until, tz)} />
              </>
            ) : null}
          </p>
        </div>
      ) : (
        <Empty>No policy decision has been recorded yet.</Empty>
      )}
      {openRequests.length > 0 ? (
        <p className="notice tone-warn" role="note">
          <span aria-hidden="true">⚑ </span>
          {openRequests.length === 1
            ? "One authorization request is waiting for the organizer."
            : `${openRequests.length} authorization requests are waiting for the organizer.`}{" "}
          <JumpButton targetId="decisions">See decisions</JumpButton>
        </p>
      ) : null}
      {feed.length > 0 ? (
        <ol className="feed">
          {feed.map((item) => (
            <li key={item.key}>
              <span className="feed-time">
                <When iso={item.at} text={fmtTime(item.at, tz)} />
              </span>
              <span className="feed-body">{item.render()}</span>
            </li>
          ))}
        </ol>
      ) : (
        <Empty>Nothing has changed since the episode was loaded.</Empty>
      )}
    </Section>
  );
}
