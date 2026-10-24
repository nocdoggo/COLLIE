-- Plan B runtime store, schema version 1 (runtime contract 1.0.0).
--
-- Every operational row is scoped by episode_id. An episode is one loaded sandbox run;
-- reset closes the old episode and creates a new one, so receipts, idempotency records,
-- holds, observations and evaluations never cross episodes.
--
-- Timestamps are UTC ISO 8601 text ('YYYY-MM-DDTHH:MM:SSZ'), which sorts chronologically.
-- Domain invariants that SQL cannot express (interval overlap, budget sums, authority)
-- are enforced by the executor inside the same BEGIN IMMEDIATE transaction as the write.

CREATE TABLE episodes (
    episode_id        TEXT PRIMARY KEY,
    scenario_id       TEXT NOT NULL,
    profile_id        TEXT NOT NULL,
    event_id          TEXT NOT NULL,
    status            TEXT NOT NULL CHECK (status IN ('active', 'closed')),
    clock             TEXT NOT NULL,
    revision          INTEGER NOT NULL CHECK (revision >= 0),
    goal_version      INTEGER NOT NULL CHECK (goal_version >= 1),
    plan_version      INTEGER NOT NULL CHECK (plan_version >= 1),
    public_fixture_sha256 TEXT NOT NULL,
    runtime_version   TEXT NOT NULL,
    created_wall      TEXT NOT NULL,
    closed_wall       TEXT,
    counters_json     TEXT NOT NULL DEFAULT '{}'   -- per-episode id sequences
);

-- Private runner linkage lives in its own table. Nothing that builds a public projection,
-- planning snapshot, policy input or trace export reads this table.
CREATE TABLE episode_private (
    episode_id   TEXT PRIMARY KEY REFERENCES episodes(episode_id),
    case_ref     TEXT NOT NULL,
    case_sha256  TEXT NOT NULL
);

CREATE TABLE world_events_processed (
    episode_id   TEXT NOT NULL REFERENCES episodes(episode_id),
    event_index  INTEGER NOT NULL,
    processed_at TEXT NOT NULL,
    outcome      TEXT NOT NULL,
    PRIMARY KEY (episode_id, event_index)
);

CREATE TABLE scenario_config (
    episode_id   TEXT PRIMARY KEY REFERENCES episodes(episode_id),
    public_json  TEXT NOT NULL   -- the validated PublicScenario, for public configuration only
);

CREATE TABLE goals (
    episode_id   TEXT NOT NULL REFERENCES episodes(episode_id),
    version      INTEGER NOT NULL,
    body_json    TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    created_by   TEXT NOT NULL,
    receipt_id   TEXT,
    PRIMARY KEY (episode_id, version)
);

CREATE TABLE activities (
    episode_id      TEXT NOT NULL REFERENCES episodes(episode_id),
    activity_id     TEXT NOT NULL,
    definition_json TEXT NOT NULL,
    lifecycle       TEXT NOT NULL
        CHECK (lifecycle IN ('planned', 'ready', 'started', 'completed', 'failed', 'canceled')),
    PRIMARY KEY (episode_id, activity_id)
);

-- Append-only lifecycle history. Started/completed/failed records are immutable history.
CREATE TABLE activity_events (
    episode_id   TEXT NOT NULL REFERENCES episodes(episode_id),
    seq          INTEGER NOT NULL,
    activity_id  TEXT NOT NULL,
    state        TEXT NOT NULL
        CHECK (state IN ('planned', 'ready', 'started', 'completed', 'failed', 'canceled')),
    at           TEXT NOT NULL,
    revision     INTEGER NOT NULL,
    reasons_json TEXT NOT NULL DEFAULT '[]',
    evidence_json TEXT NOT NULL DEFAULT '[]',
    PRIMARY KEY (episode_id, seq)
);
CREATE TRIGGER activity_events_no_update BEFORE UPDATE ON activity_events
BEGIN SELECT RAISE(ABORT, 'activity history is append-only'); END;
CREATE TRIGGER activity_events_no_delete BEFORE DELETE ON activity_events
BEGIN SELECT RAISE(ABORT, 'activity history is append-only'); END;
-- A started/completed/failed/canceled activity can never return to planned/ready/started.
CREATE TRIGGER activities_terminal_lifecycle BEFORE UPDATE OF lifecycle ON activities
WHEN (OLD.lifecycle IN ('completed', 'failed', 'canceled'))
  OR (OLD.lifecycle = 'started' AND NEW.lifecycle NOT IN ('completed', 'failed'))
BEGIN SELECT RAISE(ABORT, 'illegal lifecycle transition from immutable history'); END;

CREATE TABLE resources (
    episode_id       TEXT NOT NULL REFERENCES episodes(episode_id),
    resource_id      TEXT NOT NULL,
    definition_json  TEXT NOT NULL,
    status           TEXT NOT NULL CHECK (status IN ('available', 'expected', 'unavailable', 'unknown')),
    status_basis     TEXT NOT NULL CHECK (status_basis IN ('catalog', 'status_observation', 'arrival_observation')),
    status_observation_id TEXT,
    status_observed_at TEXT,
    reported_eta     TEXT,
    PRIMARY KEY (episode_id, resource_id)
);

CREATE TABLE plans (
    episode_id       TEXT NOT NULL REFERENCES episodes(episode_id),
    plan_version     INTEGER NOT NULL,
    assignments_json TEXT NOT NULL,
    candidate_id     TEXT,
    receipt_id       TEXT,
    applied_at       TEXT,
    PRIMARY KEY (episode_id, plan_version)
);

CREATE TABLE observations (
    episode_id       TEXT NOT NULL REFERENCES episodes(episode_id),
    observation_id   TEXT NOT NULL,
    source_id        TEXT NOT NULL,
    source_record_id TEXT NOT NULL,
    body_json        TEXT NOT NULL,
    channel          TEXT NOT NULL,
    submitted_by     TEXT,
    structured_json  TEXT,
    received_at      TEXT NOT NULL,
    revision_after   INTEGER NOT NULL,
    PRIMARY KEY (episode_id, observation_id),
    UNIQUE (episode_id, source_id, source_record_id)
);
CREATE TRIGGER observations_no_update BEFORE UPDATE ON observations
BEGIN SELECT RAISE(ABORT, 'observations are immutable'); END;

CREATE TABLE checkins (
    episode_id     TEXT NOT NULL REFERENCES episodes(episode_id),
    checkin_id     TEXT NOT NULL,
    principal_id   TEXT,
    resource_id    TEXT NOT NULL,
    at             TEXT NOT NULL,
    available_start TEXT NOT NULL,
    available_end  TEXT NOT NULL,
    observation_id TEXT,
    channel        TEXT NOT NULL CHECK (channel IN ('fixture_initial', 'participant_session')),
    PRIMARY KEY (episode_id, checkin_id)
);

CREATE TABLE holds (
    episode_id     TEXT NOT NULL REFERENCES episodes(episode_id),
    hold_id        TEXT NOT NULL,
    resource_id    TEXT NOT NULL,
    activity_id    TEXT NOT NULL,
    quantity       INTEGER NOT NULL CHECK (quantity >= 1),
    window_start   TEXT NOT NULL,
    window_end     TEXT NOT NULL,
    created_at     TEXT NOT NULL,
    expires_at     TEXT NOT NULL,
    commitment_cutoff TEXT,
    reserved_cents INTEGER NOT NULL CHECK (reserved_cents >= 0),
    hold_fee_cents INTEGER NOT NULL CHECK (hold_fee_cents >= 0),
    status         TEXT NOT NULL CHECK (status IN ('active', 'committed', 'released', 'expired')),
    actor_id       TEXT NOT NULL,
    grant_id       TEXT NOT NULL,
    commitment_id  TEXT,
    terminal_at    TEXT,
    created_receipt_id TEXT NOT NULL,
    terminal_receipt_id TEXT,
    PRIMARY KEY (episode_id, hold_id),
    CHECK (window_end > window_start),
    CHECK (expires_at > created_at)
);
-- A hold leaves 'active' exactly once; terminal states never change again.
CREATE TRIGGER holds_terminal BEFORE UPDATE OF status ON holds
WHEN OLD.status <> 'active'
BEGIN SELECT RAISE(ABORT, 'hold is already terminal'); END;

CREATE TABLE commitments (
    episode_id     TEXT NOT NULL REFERENCES episodes(episode_id),
    commitment_id  TEXT NOT NULL,
    resource_id    TEXT NOT NULL,
    activity_id    TEXT NOT NULL,
    window_start   TEXT NOT NULL,
    window_end     TEXT NOT NULL,
    committed_cents INTEGER NOT NULL CHECK (committed_cents >= 0),
    source_hold_id TEXT,
    plan_version   INTEGER NOT NULL,
    status         TEXT NOT NULL CHECK (status IN ('active')),
    created_at     TEXT NOT NULL,
    receipt_id     TEXT NOT NULL,
    actor_id       TEXT NOT NULL,
    grant_id       TEXT NOT NULL,
    PRIMARY KEY (episode_id, commitment_id),
    UNIQUE (episode_id, source_hold_id)   -- one hold converts at most once
);

-- Authoritative money ledger. Projections (committed/reserved) are sums over it.
CREATE TABLE ledger (
    episode_id   TEXT NOT NULL REFERENCES episodes(episode_id),
    seq          INTEGER NOT NULL,
    at           TEXT NOT NULL,
    kind         TEXT NOT NULL CHECK (kind IN
        ('reserve', 'release_reserve', 'expire_reserve', 'convert_reserve', 'commit_charge', 'hold_fee')),
    committed_delta_cents INTEGER NOT NULL,
    reserved_delta_cents  INTEGER NOT NULL,
    hold_id      TEXT,
    commitment_id TEXT,
    grant_id     TEXT NOT NULL,
    receipt_id   TEXT,
    PRIMARY KEY (episode_id, seq)
);
-- A hold's reservation is returned at most once (release, expiry or conversion).
CREATE UNIQUE INDEX ledger_one_return_per_hold ON ledger(episode_id, hold_id)
    WHERE kind IN ('release_reserve', 'expire_reserve', 'convert_reserve');
CREATE UNIQUE INDEX ledger_one_reserve_per_hold ON ledger(episode_id, hold_id)
    WHERE kind = 'reserve';
CREATE TRIGGER ledger_no_update BEFORE UPDATE ON ledger
BEGIN SELECT RAISE(ABORT, 'ledger is append-only'); END;
CREATE TRIGGER ledger_no_delete BEFORE DELETE ON ledger
BEGIN SELECT RAISE(ABORT, 'ledger is append-only'); END;

CREATE TABLE grants (
    episode_id   TEXT NOT NULL REFERENCES episodes(episode_id),
    grant_id     TEXT NOT NULL,
    version      INTEGER NOT NULL CHECK (version >= 1),
    body_json    TEXT NOT NULL,
    principal_id TEXT NOT NULL,
    revoked      INTEGER NOT NULL DEFAULT 0 CHECK (revoked IN (0, 1)),
    is_current   INTEGER NOT NULL CHECK (is_current IN (0, 1)),
    issued_at    TEXT NOT NULL,
    issued_receipt_id TEXT,
    PRIMARY KEY (episode_id, grant_id, version)
);
CREATE UNIQUE INDEX grants_one_current ON grants(episode_id, grant_id) WHERE is_current = 1;

CREATE TABLE sessions (
    token_sha256 TEXT PRIMARY KEY,
    session_id   TEXT NOT NULL UNIQUE,
    episode_id   TEXT REFERENCES episodes(episode_id),   -- NULL only for moderator sessions
    principal_id TEXT NOT NULL,
    role         TEXT NOT NULL CHECK (role IN ('organizer', 'coordinator_agent', 'participant', 'moderator')),
    grant_id     TEXT,
    created_wall TEXT NOT NULL,
    expires_wall TEXT NOT NULL,
    revoked      INTEGER NOT NULL DEFAULT 0 CHECK (revoked IN (0, 1))
);

CREATE TABLE join_codes (
    code_sha256  TEXT PRIMARY KEY,
    episode_id   TEXT NOT NULL REFERENCES episodes(episode_id),
    principal_id TEXT NOT NULL,
    created_wall TEXT NOT NULL,
    expires_wall TEXT NOT NULL,
    used         INTEGER NOT NULL DEFAULT 0 CHECK (used IN (0, 1))
);

CREATE TABLE receipts (
    episode_id   TEXT NOT NULL REFERENCES episodes(episode_id),
    receipt_id   TEXT NOT NULL,
    actor_id     TEXT NOT NULL,
    tool         TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    status       TEXT NOT NULL CHECK (status IN ('applied', 'rejected', 'unknown')),
    revision_before INTEGER NOT NULL,
    revision_after  INTEGER NOT NULL,
    executed_at  TEXT NOT NULL,
    body_json    TEXT NOT NULL,
    PRIMARY KEY (episode_id, receipt_id)
);
CREATE TRIGGER receipts_no_update BEFORE UPDATE ON receipts
BEGIN SELECT RAISE(ABORT, 'receipts are durable and immutable'); END;

-- Idempotency scope is (episode, authenticated actor, key). The digest pins the body.
CREATE TABLE idempotency (
    episode_id     TEXT NOT NULL REFERENCES episodes(episode_id),
    actor_id       TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    tool           TEXT NOT NULL,
    request_digest TEXT NOT NULL,
    receipt_id     TEXT NOT NULL,
    created_at     TEXT NOT NULL,
    PRIMARY KEY (episode_id, actor_id, idempotency_key)
);

CREATE TABLE evaluations (
    episode_id     TEXT NOT NULL REFERENCES episodes(episode_id),
    evaluation_id  TEXT NOT NULL,
    revision       INTEGER NOT NULL,
    goal_version   INTEGER NOT NULL,
    evaluated_at   TEXT NOT NULL,
    actor_id       TEXT NOT NULL,
    hypothetical   INTEGER NOT NULL CHECK (hypothetical IN (0, 1)),
    body_json      TEXT NOT NULL,
    PRIMARY KEY (episode_id, evaluation_id)
);

CREATE TABLE candidates (
    episode_id     TEXT NOT NULL REFERENCES episodes(episode_id),
    candidate_id   TEXT NOT NULL,
    report_id      TEXT NOT NULL,
    evaluation_id  TEXT NOT NULL,
    signature      TEXT NOT NULL,
    based_on_revision INTEGER NOT NULL,
    goal_version   INTEGER NOT NULL,
    hypothetical   INTEGER NOT NULL CHECK (hypothetical IN (0, 1)),
    constraint_status TEXT NOT NULL,
    body_json      TEXT NOT NULL,
    PRIMARY KEY (episode_id, candidate_id),
    UNIQUE (episode_id, report_id),
    FOREIGN KEY (episode_id, evaluation_id) REFERENCES evaluations(episode_id, evaluation_id)
);
CREATE TRIGGER candidates_no_update BEFORE UPDATE ON candidates
BEGIN SELECT RAISE(ABORT, 'stored candidates are immutable'); END;

-- One row per revision: what changed the operational state.
CREATE TABLE state_transitions (
    episode_id   TEXT NOT NULL REFERENCES episodes(episode_id),
    revision     INTEGER NOT NULL,
    at           TEXT NOT NULL,
    cause_kind   TEXT NOT NULL,
    cause_ref    TEXT,
    summary      TEXT NOT NULL,
    PRIMARY KEY (episode_id, revision)
);

-- Sanitized public projection captured at each revision, for trace export and replay.
CREATE TABLE revision_snapshots (
    episode_id   TEXT NOT NULL REFERENCES episodes(episode_id),
    revision     INTEGER NOT NULL,
    at           TEXT NOT NULL,
    view_json    TEXT NOT NULL,
    PRIMARY KEY (episode_id, revision)
);

-- Every tool call, sanitized (no tokens). Rejected attempts without receipts live here.
CREATE TABLE tool_calls (
    episode_id   TEXT NOT NULL REFERENCES episodes(episode_id),
    seq          INTEGER NOT NULL,
    call_id      TEXT NOT NULL,
    actor_id     TEXT,
    actor_role   TEXT,
    tool         TEXT NOT NULL,
    requested_at TEXT,
    completed_at TEXT,
    revision_before INTEGER,
    revision_after  INTEGER,
    envelope_status TEXT NOT NULL,
    error_code   TEXT,
    receipt_id   TEXT,
    request_json TEXT NOT NULL,
    envelope_json TEXT NOT NULL,
    PRIMARY KEY (episode_id, seq),
    UNIQUE (episode_id, call_id)
);

CREATE TABLE policy_decisions (
    episode_id   TEXT NOT NULL REFERENCES episodes(episode_id),
    seq          INTEGER NOT NULL,
    decision_id  TEXT NOT NULL,
    at           TEXT NOT NULL,
    revision     INTEGER NOT NULL,
    body_json    TEXT NOT NULL,
    PRIMARY KEY (episode_id, seq),
    UNIQUE (episode_id, decision_id)
);

-- Runner-side record of scripted exogenous actor actions (private harness bookkeeping).
CREATE TABLE runner_log (
    episode_id   TEXT NOT NULL REFERENCES episodes(episode_id),
    seq          INTEGER NOT NULL,
    at           TEXT NOT NULL,
    entry_json   TEXT NOT NULL,
    PRIMARY KEY (episode_id, seq)
);
