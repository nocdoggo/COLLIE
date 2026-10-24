"""References of a private case checked against its public scenario.

A private case names entities, facts, principals and grants of one public scenario. A typo
(status entity ``projecter``) would otherwise load silently: the status source would never
answer, an arrival would update nothing, and the case could still report its expected outcome.
Like everything that reads ``scenarios/private``, this lives in ``plan_b.world``; callers get
only the list of problems.
"""

from __future__ import annotations

from plan_b.domain.models import (
    OrganizerAuthorizationRule,
    OrganizerGoalUpdateScript,
    ParticipantCheckInScript,
    ParticipantObservationScript,
    PrivateCase,
    PublicScenario,
    StaffDistributionRule,
    StaffHandoffRule,
)
from plan_b.world.world import load_case


def validate_case(public: PublicScenario, private: PrivateCase) -> list[str]:
    """Return human-readable reference problems of ``private``; empty when valid."""
    problems: list[str] = []
    if private.scenario_id != public.scenario_id:
        problems.append(
            f"case {private.case_ref} is for scenario {private.scenario_id}, "
            f"not {public.scenario_id}"
        )
    resources = {r.resource_id: r for r in public.resources}
    # The entities an observation may concern, as in submit_observation.
    entities = set(resources) | {a.activity_id for a in public.activities} | {public.event_id}
    principals = {p.principal_id: p for p in public.principals}
    grants = {g.grant_id for g in public.authority_grants}
    # The tools each principal's own grant allows: a staff simulator acts only within it.
    granted = {
        p.principal_id: next(
            (g.allowed_tools for g in public.authority_grants if g.grant_id == p.grant_id), ()
        )
        for p in public.principals
    }
    pools = {r.resource_id for r in public.resources if r.consumable_stock is not None}
    targets = {t.target_id for t in public.goal.service_targets}
    visible = {o.observation_id for o in public.visible_observations}
    for i, record in enumerate(private.status_model):
        where = f"status_model[{i}]"
        resource = resources.get(record.entity_id)
        if resource is None:
            problems.append(f"{where}: unknown resource {record.entity_id}")
        elif record.fact not in resource.terms.queryable_facts:
            # query_status answers only a resource's queryable facts.
            problems.append(f"{where}: {record.entity_id} has no queryable fact {record.fact}")
    for i, event in enumerate(private.world_events):
        where = f"world_events[{i}]"
        if event.kind == "resource_arrival" and event.entity_id not in resources:
            problems.append(f"{where}: arrival of unknown resource {event.entity_id}")
        elif event.entity_id not in entities:
            problems.append(f"{where}: unknown entity {event.entity_id}")
    for i, script in enumerate(private.actor_scripts):
        where = f"actor_scripts[{i}] ({script.kind})"
        if script.principal_id not in principals:
            problems.append(f"{where}: unknown principal {script.principal_id}")
        if isinstance(script, ParticipantCheckInScript):
            if script.resource_id not in resources:
                problems.append(f"{where}: unknown resource {script.resource_id}")
        elif isinstance(script, ParticipantObservationScript):
            if script.entity_id is not None and script.entity_id not in entities:
                problems.append(f"{where}: unknown entity {script.entity_id}")
        elif isinstance(script, OrganizerAuthorizationRule):
            if script.target_grant_id not in grants:
                problems.append(f"{where}: unknown grant {script.target_grant_id}")
            for rid in script.resource_ids:
                if rid not in resources:
                    problems.append(f"{where}: unknown resource {rid}")
        elif isinstance(script, OrganizerGoalUpdateScript):
            principal = principals.get(script.principal_id)
            if principal is not None and principal.role != "organizer":
                problems.append(f"{where}: {script.principal_id} is not an organizer")
        elif isinstance(script, StaffHandoffRule):
            if public.pantry_parameters is None:
                problems.append(f"{where}: the scenario declares no staff handoff timing")
            for rid in (script.source_resource_id, script.destination_resource_id):
                if rid not in pools:
                    problems.append(f"{where}: {rid} is not a consumable stock pool")
            if script.source_observation_id not in visible:
                problems.append(
                    f"{where}: unknown source observation {script.source_observation_id}"
                )
            if "record_stock_receipt" not in granted.get(script.principal_id, ()):
                problems.append(f"{where}: {script.principal_id} may not record stock receipts")
        elif isinstance(script, StaffDistributionRule):
            if script.service_target_id not in targets:
                problems.append(f"{where}: unknown service target {script.service_target_id}")
            if "record_distribution" not in granted.get(script.principal_id, ()):
                problems.append(f"{where}: {script.principal_id} may not record distributions")
    return problems


def validate_case_ref(public: PublicScenario, case_ref: str) -> list[str]:
    """``validate_case`` for a case named by reference (the case itself stays in this
    package)."""
    return validate_case(public, load_case(case_ref))
