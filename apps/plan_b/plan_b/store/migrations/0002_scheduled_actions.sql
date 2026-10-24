-- Scheduled exogenous actor actions (runner input, private).
--
-- In headless runs the private case scripts participant check-ins and a simulated organizer.
-- Each such action is registered here with the actor's own server-held session and executed by
-- the clock engine at its exact scenario instant, through the same executor path as any other
-- call. That makes the instant independent of what any policy happens to be doing (a policy's
-- tool duration that spans the instant processes it like a world event). Nothing that builds a
-- public projection, snapshot, policy input or trace reads this table; its effects appear only
-- through the ordinary receipts, observations and tool-call records they produce.

CREATE TABLE scheduled_actions (
    episode_id     TEXT NOT NULL REFERENCES episodes(episode_id),
    action_id      TEXT NOT NULL,
    due_at         TEXT NOT NULL,
    order_index    INTEGER NOT NULL,
    principal_id   TEXT NOT NULL,
    session_id     TEXT NOT NULL REFERENCES sessions(session_id),
    tool           TEXT NOT NULL,
    body_json      TEXT NOT NULL,
    fill_expected_revision INTEGER NOT NULL DEFAULT 0 CHECK (fill_expected_revision IN (0, 1)),
    status         TEXT NOT NULL CHECK (status IN ('pending', 'done')),
    executed_at    TEXT,
    call_id        TEXT,
    envelope_status TEXT,
    receipt_id     TEXT,
    receipt_status TEXT,
    error_code     TEXT,
    PRIMARY KEY (episode_id, action_id)
);
CREATE INDEX scheduled_actions_due ON scheduled_actions(episode_id, status, due_at, order_index);
