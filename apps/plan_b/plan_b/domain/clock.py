"""Scenario clock semantics (pure).

The clock is injected and server-owned: it is stored per episode and moves only through the
moderator clock control, the runner, and modeled tool durations. When several things happen
at one instant they are processed in ``EVENT_ORDER``:

1. ``activity_completion`` - the hard end is inclusive, so a required activity ending exactly
   at the deadline completes;
2. ``world_event`` - arrivals and message deliveries due at that instant;
   then ``actor_action`` - scheduled exogenous actor actions (scripted check-ins, the simulated
   organizer) due at that instant, executed through each actor's own session;
3. ``hold_expiry`` - a hold is usable only while ``clock < expires_at``;
4. ``grant_expiry`` - a grant is valid only while ``clock < expires_at``;
5. ``activity_start`` - strict readiness after the arrivals at the same instant;
6. ``event_close`` - after completions at the hard end.
"""

from __future__ import annotations

from datetime import datetime, timedelta

EVENT_ORDER = (
    "activity_completion",
    "world_event",
    "actor_action",
    "hold_expiry",
    "grant_expiry",
    "activity_start",
    "event_close",
)

MAX_ADVANCE_MINUTES = 240


def is_live(expires_at: datetime, clock: datetime) -> bool:
    """Holds and grants: valid strictly before their expiry instant."""
    return clock < expires_at


def validate_advance(current: datetime, minutes: int) -> datetime:
    if minutes < 0:
        raise ValueError("the scenario clock cannot move backward")
    if minutes > MAX_ADVANCE_MINUTES:
        raise ValueError(f"advance at most {MAX_ADVANCE_MINUTES} minutes at a time")
    return current + timedelta(minutes=minutes)
