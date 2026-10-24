"""Profile -> domain adapter. A profile id selects an adapter; it never selects a script."""

from __future__ import annotations

from functools import lru_cache

from plan_b.domain.adapters.base import DomainAdapter

CAMPUS_PROFILES = ("campus_showcase", "community_skills_exchange")


@lru_cache(maxsize=8)
def adapter_for(profile_id: str) -> DomainAdapter:
    if profile_id in CAMPUS_PROFILES:
        from plan_b.domain.adapters.campus import CampusAdapter

        return CampusAdapter()
    raise KeyError(f"no domain adapter for profile {profile_id!r} in Wave 1")
