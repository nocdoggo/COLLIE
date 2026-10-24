-- Consumable stock and service accounting (schema version 4, runtime contract 1.1.0).
--
-- The pantry profile counts standardized units. Reusable resources keep the Wave 1 tables
-- unchanged; consumable stock gets its own ledgers instead of an unexplained consumption flag
-- on holds or the money ledger:
--
--   stock_movements      append-only on-hand ledger, one row per change of a pool's on-hand:
--                        opening (load), receipt (external shipment or internal handoff in),
--                        transfer_out (internal handoff out), distribution. For every pool
--                        closing_on_hand = opening + receipts - transfers_out - distributions.
--   expected_shipments   identified expected supply. Only received_quantity moves, only up,
--                        never past quantity, and only together with a matched stock receipt.
--   stock_receipts       staff-attested physical receipts; receipt_reference is unique per
--                        episode (one event per episode), whatever the request's idempotency
--                        key, so a resubmitted physical receipt cannot credit stock twice.
--   stock_allocations    committed consumable allocations made by apply_plan from holds; only
--                        remaining_quantity moves, only down (distribution consumes it).
--   distributions        staff-attested aggregate distributions; distribution_reference is
--                        unique per episode for the same reason.
--
-- holds is rebuilt with the consumable columns of planning 0.2.0 (remaining_quantity, purpose,
-- destination_resource_id) and the terminal status 'fulfilled' (a stock-transfer hold whose
-- whole quantity was handed off). SQLite cannot change a CHECK constraint in place; the
-- rebuild copies every row, and DROP TABLE removes the old table's triggers before its
-- implicit delete, so the 0001/0003 guards do not fire and are recreated below.
--
-- Guards in the 0003 style (RAISE(ABORT): the statement fails, nothing changes):
--
--   stock_movements    UPDATE, DELETE
--   stock_receipts     UPDATE, DELETE
--   distributions      UPDATE, DELETE
--   stock_allocations  DELETE; UPDATE of any column but remaining_quantity; an UPDATE that
--                      raises remaining_quantity
--   expected_shipments DELETE; UPDATE of any column but received_quantity; an UPDATE that
--                      lowers received_quantity (the CHECK keeps it <= quantity)
--   holds              DELETE (0003, recreated); UPDATE of status once it left 'active' (0001,
--                      recreated); UPDATE of the hold's definition columns; an UPDATE that
--                      raises remaining_quantity; an UPDATE of remaining_quantity of a hold
--                      that is no longer active
--
-- Not refused: inserting new rows; the application's own updates (a hold's status, terminal
-- fields, commitment link and a decreasing remainder; an allocation's decreasing remainder; a
-- shipment's increasing received quantity). As in 0003, REPLACE is refused only on connections
-- with recursive_triggers on, which plan_b.store.database.Database.connect sets.

CREATE TABLE holds_v4 (
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
    status         TEXT NOT NULL
        CHECK (status IN ('active', 'committed', 'released', 'expired', 'fulfilled')),
    actor_id       TEXT NOT NULL,
    grant_id       TEXT NOT NULL,
    commitment_id  TEXT,
    terminal_at    TEXT,
    created_receipt_id TEXT NOT NULL,
    terminal_receipt_id TEXT,
    consumable     INTEGER NOT NULL DEFAULT 0 CHECK (consumable IN (0, 1)),
    remaining_quantity INTEGER NOT NULL CHECK (remaining_quantity >= 0),
    purpose        TEXT NOT NULL DEFAULT 'activity' CHECK (purpose IN ('activity', 'stock_transfer')),
    destination_resource_id TEXT,
    service_target_id TEXT,
    PRIMARY KEY (episode_id, hold_id),
    CHECK (window_end > window_start),
    CHECK (expires_at > created_at),
    CHECK (remaining_quantity <= quantity),
    CHECK (status <> 'fulfilled' OR (consumable = 1 AND remaining_quantity = 0)),
    CHECK ((purpose = 'stock_transfer') = (destination_resource_id IS NOT NULL)),
    CHECK (consumable = 1 OR (purpose = 'activity' AND remaining_quantity = quantity))
);
INSERT INTO holds_v4 (episode_id, hold_id, resource_id, activity_id, quantity, window_start,
    window_end, created_at, expires_at, commitment_cutoff, reserved_cents, hold_fee_cents,
    status, actor_id, grant_id, commitment_id, terminal_at, created_receipt_id,
    terminal_receipt_id, consumable, remaining_quantity, purpose)
SELECT episode_id, hold_id, resource_id, activity_id, quantity, window_start, window_end,
    created_at, expires_at, commitment_cutoff, reserved_cents, hold_fee_cents, status, actor_id,
    grant_id, commitment_id, terminal_at, created_receipt_id, terminal_receipt_id, 0, quantity,
    'activity'
FROM holds ORDER BY rowid;
DROP TABLE holds;
ALTER TABLE holds_v4 RENAME TO holds;

-- The 0001 and 0003 hold guards, unchanged.
CREATE TRIGGER holds_terminal BEFORE UPDATE OF status ON holds
WHEN OLD.status <> 'active'
BEGIN SELECT RAISE(ABORT, 'hold is already terminal'); END;
CREATE TRIGGER holds_no_delete BEFORE DELETE ON holds
BEGIN SELECT RAISE(ABORT, 'holds are never deleted'); END;
-- A hold's terms never change after it is written.
CREATE TRIGGER holds_definition_fixed
BEFORE UPDATE OF episode_id, hold_id, resource_id, activity_id, quantity, window_start,
    window_end, created_at, expires_at, commitment_cutoff, reserved_cents, hold_fee_cents,
    actor_id, grant_id, created_receipt_id, consumable, purpose, destination_resource_id,
    service_target_id ON holds
BEGIN SELECT RAISE(ABORT, 'a hold definition is fixed'); END;
-- A live claim only shrinks (partial handoff, conversion); a terminal hold's remainder is
-- history and never changes.
CREATE TRIGGER holds_remaining_never_grows BEFORE UPDATE OF remaining_quantity ON holds
WHEN NEW.remaining_quantity > OLD.remaining_quantity
BEGIN SELECT RAISE(ABORT, 'a hold remainder never grows'); END;
CREATE TRIGGER holds_remaining_only_while_active BEFORE UPDATE OF remaining_quantity ON holds
WHEN OLD.status <> 'active' AND NEW.remaining_quantity <> OLD.remaining_quantity
BEGIN SELECT RAISE(ABORT, 'a terminal hold remainder is history'); END;

CREATE TABLE stock_movements (
    episode_id   TEXT NOT NULL REFERENCES episodes(episode_id),
    seq          INTEGER NOT NULL,
    at           TEXT NOT NULL,
    resource_id  TEXT NOT NULL,
    kind         TEXT NOT NULL
        CHECK (kind IN ('opening', 'receipt', 'transfer_out', 'distribution')),
    quantity     INTEGER NOT NULL CHECK (quantity >= 0),
    delta        INTEGER NOT NULL,
    counterpart_resource_id TEXT,
    reference    TEXT,
    hold_id      TEXT,
    shipment_id  TEXT,
    receipt_id   TEXT,
    revision     INTEGER NOT NULL,
    PRIMARY KEY (episode_id, seq),
    -- The sign of each kind is fixed: credits are receipts and the opening balance.
    CHECK ((kind IN ('opening', 'receipt') AND delta = quantity)
        OR (kind IN ('transfer_out', 'distribution') AND delta = -quantity))
);
CREATE UNIQUE INDEX stock_movements_one_opening ON stock_movements(episode_id, resource_id)
    WHERE kind = 'opening';
CREATE TRIGGER stock_movements_no_update BEFORE UPDATE ON stock_movements
BEGIN SELECT RAISE(ABORT, 'the stock ledger is append-only'); END;
CREATE TRIGGER stock_movements_no_delete BEFORE DELETE ON stock_movements
BEGIN SELECT RAISE(ABORT, 'the stock ledger is append-only'); END;

CREATE TABLE expected_shipments (
    episode_id   TEXT NOT NULL REFERENCES episodes(episode_id),
    shipment_id  TEXT NOT NULL,
    destination_resource_id TEXT NOT NULL,
    quantity     INTEGER NOT NULL CHECK (quantity >= 1),
    received_quantity INTEGER NOT NULL CHECK (received_quantity >= 0),
    expected_at  TEXT,
    source_ref   TEXT NOT NULL,
    PRIMARY KEY (episode_id, shipment_id),
    CHECK (received_quantity <= quantity)
);
CREATE TRIGGER expected_shipments_no_delete BEFORE DELETE ON expected_shipments
BEGIN SELECT RAISE(ABORT, 'expected shipments are never deleted'); END;
CREATE TRIGGER expected_shipments_definition_fixed
BEFORE UPDATE OF episode_id, shipment_id, destination_resource_id, quantity, expected_at,
    source_ref ON expected_shipments
BEGIN SELECT RAISE(ABORT, 'an expected shipment definition is fixed'); END;
CREATE TRIGGER expected_shipments_received_never_falls
BEFORE UPDATE OF received_quantity ON expected_shipments
WHEN NEW.received_quantity < OLD.received_quantity
BEGIN SELECT RAISE(ABORT, 'a reconciled receipt is never undone'); END;

CREATE TABLE stock_receipts (
    episode_id   TEXT NOT NULL REFERENCES episodes(episode_id),
    stock_receipt_id TEXT NOT NULL,
    receipt_reference TEXT NOT NULL,
    kind         TEXT NOT NULL CHECK (kind IN ('internal_handoff', 'external_shipment')),
    resource_id  TEXT NOT NULL,
    source_resource_id TEXT,
    source_hold_id TEXT,
    shipment_id  TEXT,
    quantity     INTEGER NOT NULL CHECK (quantity >= 1),
    unit         TEXT NOT NULL,
    source_observation_id TEXT NOT NULL,
    at           TEXT NOT NULL,
    actor_id     TEXT NOT NULL,
    receipt_id   TEXT NOT NULL,
    revision     INTEGER NOT NULL,
    PRIMARY KEY (episode_id, stock_receipt_id),
    UNIQUE (episode_id, receipt_reference),
    CHECK ((kind = 'internal_handoff' AND source_resource_id IS NOT NULL
            AND source_hold_id IS NOT NULL AND shipment_id IS NULL)
        OR (kind = 'external_shipment' AND shipment_id IS NOT NULL
            AND source_resource_id IS NULL AND source_hold_id IS NULL))
);
CREATE TRIGGER stock_receipts_no_update BEFORE UPDATE ON stock_receipts
BEGIN SELECT RAISE(ABORT, 'stock receipts are durable and immutable'); END;
CREATE TRIGGER stock_receipts_no_delete BEFORE DELETE ON stock_receipts
BEGIN SELECT RAISE(ABORT, 'stock receipts are durable and immutable'); END;

CREATE TABLE stock_allocations (
    episode_id   TEXT NOT NULL REFERENCES episodes(episode_id),
    allocation_id TEXT NOT NULL,
    resource_id  TEXT NOT NULL,
    service_target_id TEXT NOT NULL,
    activity_id  TEXT NOT NULL,
    quantity     INTEGER NOT NULL CHECK (quantity >= 1),
    remaining_quantity INTEGER NOT NULL CHECK (remaining_quantity >= 0),
    source_hold_id TEXT NOT NULL,
    plan_version INTEGER NOT NULL,
    created_at   TEXT NOT NULL,
    receipt_id   TEXT NOT NULL,
    actor_id     TEXT NOT NULL,
    grant_id     TEXT NOT NULL,
    PRIMARY KEY (episode_id, allocation_id),
    UNIQUE (episode_id, source_hold_id),   -- one hold converts at most once
    CHECK (remaining_quantity <= quantity)
);
CREATE TRIGGER stock_allocations_no_delete BEFORE DELETE ON stock_allocations
BEGIN SELECT RAISE(ABORT, 'committed allocations are never deleted'); END;
CREATE TRIGGER stock_allocations_definition_fixed
BEFORE UPDATE OF episode_id, allocation_id, resource_id, service_target_id, activity_id,
    quantity, source_hold_id, plan_version, created_at, receipt_id, actor_id, grant_id
    ON stock_allocations
BEGIN SELECT RAISE(ABORT, 'a committed allocation is fixed'); END;
CREATE TRIGGER stock_allocations_remaining_never_grows
BEFORE UPDATE OF remaining_quantity ON stock_allocations
WHEN NEW.remaining_quantity > OLD.remaining_quantity
BEGIN SELECT RAISE(ABORT, 'distributed stock never returns to an allocation'); END;

CREATE TABLE distributions (
    episode_id   TEXT NOT NULL REFERENCES episodes(episode_id),
    distribution_id TEXT NOT NULL,
    distribution_reference TEXT NOT NULL,
    resource_id  TEXT NOT NULL,
    service_target_id TEXT NOT NULL,
    activity_id  TEXT NOT NULL,
    quantity     INTEGER NOT NULL CHECK (quantity >= 1),
    unit         TEXT NOT NULL,
    goal_version INTEGER NOT NULL,
    allocation_ids_json TEXT NOT NULL,
    at           TEXT NOT NULL,
    on_time      INTEGER NOT NULL CHECK (on_time IN (0, 1)),
    actor_id     TEXT NOT NULL,
    receipt_id   TEXT NOT NULL,
    revision     INTEGER NOT NULL,
    PRIMARY KEY (episode_id, distribution_id),
    UNIQUE (episode_id, distribution_reference)
);
CREATE TRIGGER distributions_no_update BEFORE UPDATE ON distributions
BEGIN SELECT RAISE(ABORT, 'distribution records are durable and immutable'); END;
CREATE TRIGGER distributions_no_delete BEFORE DELETE ON distributions
BEGIN SELECT RAISE(ABORT, 'distribution records are durable and immutable'); END;

-- Scheduled staff actions whose quantity is decided from the visible state at their instant
-- (the labeled staff simulator): the rule name, its parameters, and why an action did nothing.
ALTER TABLE scheduled_actions ADD COLUMN fill_rule TEXT;
ALTER TABLE scheduled_actions ADD COLUMN fill_json TEXT;
ALTER TABLE scheduled_actions ADD COLUMN note TEXT;
