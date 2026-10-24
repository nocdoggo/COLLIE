-- History guards (schema version 3, runtime contract 1.0.0).
--
-- 0001 refused updates and deletes of activity_events and ledger, updates of observations,
-- receipts and candidates, lifecycle moves out of started or terminal states, and status
-- changes of a hold that has left 'active'. This migration adds the guards below. The
-- application writes these tables only by INSERT, plus two UPDATEs the guards allow: the
-- activities.lifecycle move that accompanies each activity_events row, and a hold's one move out
-- of 'active'.
--
-- Exactly these statements are refused (RAISE(ABORT): the statement fails, nothing changes):
--
--   activity_events  UPDATE, DELETE (0001)
--   ledger           UPDATE, DELETE (0001)
--   observations     UPDATE (0001); DELETE (0003)
--   receipts         UPDATE (0001); DELETE (0003)
--   candidates       UPDATE (0001); DELETE (0003)
--   plans            UPDATE, DELETE (0003)
--   goals            UPDATE, DELETE (0003)
--   activities       DELETE (0003); UPDATE that sets episode_id, activity_id or definition_json
--                    (0003); UPDATE that sets lifecycle, unless it moves planned or ready to
--                    planned, ready, started, failed or canceled, or started to completed or
--                    failed (0001 and 0003)
--   holds            DELETE (0003); UPDATE that sets status once the hold is no longer
--                    'active' (0001)
--
-- An UPSERT's DO UPDATE is an UPDATE and is refused the same way. REPLACE conflict resolution
-- (INSERT OR REPLACE, REPLACE INTO, UPDATE OR REPLACE) removes the conflicting row by a delete,
-- and SQLite fires DELETE triggers for that delete only when the connection has
-- PRAGMA recursive_triggers = ON. plan_b.store.database.Database.connect turns it on for every
-- connection, so on those connections a REPLACE over an existing row of any table above is
-- refused. A connection that leaves it off (for example a bare sqlite3 shell) can still replace
-- rows of these tables.
--
-- Not refused: INSERT of a new row into any table; UPDATE of a hold's columns other than status;
-- any write to a table without triggers: episodes (including its plan_version and goal_version
-- pointers), episode_private, world_events_processed, scenario_config, resources, checkins,
-- commitments, grants, sessions, join_codes, idempotency, evaluations, state_transitions,
-- revision_snapshots, tool_calls, policy_decisions, runner_log, scheduled_actions and
-- schema_migrations. Triggers cannot stop DROP TRIGGER or an edit of the database file itself.

-- Observations, receipts and stored candidates are never deleted (0001 refuses updates).
CREATE TRIGGER observations_no_delete BEFORE DELETE ON observations
BEGIN SELECT RAISE(ABORT, 'observations are immutable'); END;
CREATE TRIGGER receipts_no_delete BEFORE DELETE ON receipts
BEGIN SELECT RAISE(ABORT, 'receipts are durable and immutable'); END;
CREATE TRIGGER candidates_no_delete BEFORE DELETE ON candidates
BEGIN SELECT RAISE(ABORT, 'stored candidates are immutable'); END;

-- Plan and goal versions are append-only: apply_plan and update_goal insert a new version and
-- move the episode's pointer; an existing version never changes or disappears.
CREATE TRIGGER plans_no_update BEFORE UPDATE ON plans
BEGIN SELECT RAISE(ABORT, 'plan history is append-only'); END;
CREATE TRIGGER plans_no_delete BEFORE DELETE ON plans
BEGIN SELECT RAISE(ABORT, 'plan history is append-only'); END;
CREATE TRIGGER goals_no_update BEFORE UPDATE ON goals
BEGIN SELECT RAISE(ABORT, 'goal history is append-only'); END;
CREATE TRIGGER goals_no_delete BEFORE DELETE ON goals
BEGIN SELECT RAISE(ABORT, 'goal history is append-only'); END;

-- An activity row is never deleted and its definition never changes; only its lifecycle moves.
CREATE TRIGGER activities_no_delete BEFORE DELETE ON activities
BEGIN SELECT RAISE(ABORT, 'activities are never deleted'); END;
CREATE TRIGGER activities_definition_fixed
BEFORE UPDATE OF episode_id, activity_id, definition_json ON activities
BEGIN SELECT RAISE(ABORT, 'an activity definition is fixed for its episode'); END;
-- Lifecycle order: completed only from started; started only from planned or ready; failed and
-- canceled never from a terminal state. Together with 0001 (nothing leaves a terminal state;
-- started moves only to completed or failed) the legal moves are planned<->ready,
-- planned/ready -> started/failed/canceled, and started -> completed/failed (a planned or
-- ready activity may also be set to its own state, which changes nothing).
CREATE TRIGGER activities_lifecycle_order BEFORE UPDATE OF lifecycle ON activities
WHEN (NEW.lifecycle = 'completed' AND OLD.lifecycle <> 'started')
  OR (NEW.lifecycle = 'started' AND OLD.lifecycle NOT IN ('planned', 'ready'))
  OR (NEW.lifecycle IN ('failed', 'canceled') AND OLD.lifecycle IN ('completed', 'failed', 'canceled'))
BEGIN SELECT RAISE(ABORT, 'illegal lifecycle transition'); END;

-- A hold row is never deleted: 0001 lets its status leave 'active' once, and without this a
-- delete (or a REPLACE, which deletes) could bring a released, expired or committed hold back.
CREATE TRIGGER holds_no_delete BEFORE DELETE ON holds
BEGIN SELECT RAISE(ABORT, 'holds are never deleted'); END;
