"""What a signed-in participant, organizer or staff member can contribute (read-only).

Every contribution itself goes through ``POST /api/tools/{tool}`` and the common executor:
``check_in`` (a person's own availability), ``submit_observation`` with ``kind
resource_offer`` and an ``offer`` (activates a preconfigured resource the caller speaks for),
``update_goal`` (organizer) and ``record_stock_receipt`` / ``record_distribution`` (staff).
``GET /api/participation/me`` only tells the browser which of those this session may use and
prefills the registered facts an offer must confirm. It reveals nothing beyond the public
scenario and the caller's own grant.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, get_args

from fastapi import APIRouter, Header, HTTPException

from plan_b.domain.models import STAFF_TOOLS, PreferencePreset, ResourceDef
from plan_b.domain.timeutil import fmt_ts
from plan_b.store import repo
from plan_b.store.database import Database
from plan_b.store.sessions import Session
from plan_b.tools.handlers import offer_targets

PRESETS: tuple[str, ...] = get_args(PreferencePreset)


def _offer(resource: ResourceDef, targets: tuple[ResourceDef, ...]) -> dict[str, Any] | None:
    """The registered facts an offer of ``resource`` must state, or None when no offer can
    activate it (a person's role, consumable stock, or not an approved option of anything)."""
    if resource.kind in ("person", "supply") or resource.consumable_stock is not None:
        return None
    if not targets:
        return None
    return {
        "approved_for": [t.resource_id for t in targets],
        "needed_capabilities": {t.resource_id: list(t.capabilities) for t in targets},
        "registered_capabilities": list(resource.capabilities),
        "registered_window": {
            "start": fmt_ts(resource.window.start),
            "end": fmt_ts(resource.window.end),
        },
        "terms_ref": resource.terms.terms_source_ref,
        "terms": resource.terms.model_dump(mode="json"),
    }


def participation_router(db: Database, session_of: Callable[[str | None], Session]) -> APIRouter:
    router = APIRouter()

    @router.get("/api/participation/me")
    def me(authorization: str | None = Header(default=None)) -> dict[str, Any]:
        s = session_of(authorization)
        if s.role == "moderator" or s.episode_id is None:
            raise HTTPException(
                status_code=403,
                detail={"code": "GRANT_REQUIRED", "message": "an event session is required"},
            )
        episode_id = s.episode_id
        with db.read() as conn:
            ep = repo.get_episode(conn, episode_id)
            sc = repo.scenario(conn, episode_id)
            p = repo.principal(conn, episode_id, s.principal_id)
            found = repo.current_grant(conn, episode_id, s.grant_id) if s.grant_id else None
            goal = repo.goal(conn, episode_id)
            rows = {r["resource_id"]: r["status"] for r in repo.resource_rows(conn, episode_id)}
        grant = found[0] if found else None
        tools = set(grant.allowed_tools) if grant else set()
        speaks_for = []
        for rid in p.speaks_for_resource_ids if p else ():
            resource = next((r for r in sc.resources if r.resource_id == rid), None)
            if resource is None:
                continue
            offer = _offer(resource, offer_targets(sc, rid))
            speaks_for.append(
                {
                    "resource_id": rid,
                    "label": resource.label,
                    "kind": resource.kind,
                    "status": rows.get(rid),
                    "in_grant": grant is not None and rid in grant.resource_ids,
                    "check_in": resource.kind == "person" and "check_in" in tools,
                    "offer": offer if offer is not None and "submit_observation" in tools else None,
                }
            )
        return {
            "episode_id": episode_id,
            "event_id": ep.event_id,
            "principal_id": s.principal_id,
            "role": s.role,
            "display_name": p.display_name if p else s.principal_id,
            "grant": {
                "grant_id": grant.grant_id,
                "allowed_tools": list(grant.allowed_tools),
                "resource_ids": list(grant.resource_ids),
                "activity_ids": list(grant.activity_ids),
                "expires_at": fmt_ts(grant.expires_at),
            }
            if grant
            else None,
            "speaks_for": speaks_for,
            "organizer": {
                "goal_version": goal.version,
                "preference_preset": goal.preference_preset,
                "presets": list(PRESETS),
            }
            if "update_goal" in tools
            else None,
            "staff_tools": [t for t in STAFF_TOOLS if t in tools],
        }

    return router
