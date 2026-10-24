"""Resource offers (W2.2): a participant's offer activates only a preconfigured resource it
speaks for, after the owner, option, capability, availability and terms checks.

The offer is ``submit_observation`` with ``kind: resource_offer`` and a structured ``offer``;
the natural-language text stays data. Every call goes through the real store and executor on
the skills-exchange fixture (``SkillsSandbox``), whose kit steward speaks for the registered
backup learning kit, an approved substitute of the shared kit. An offer creates one observation
and one revision and changes the kit's visible status; it never holds, commits, spends or adds
stock. Each refusal is a durable rejected receipt (or, for a malformed body, an attempt without
one) that leaves the state unchanged.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from plan_b.domain import fixtures
from plan_b.domain.models import ToolEnvelope
from plan_b.store import repo
from plan_b.store.database import Database
from plan_b.tools.client import InProcessToolClient
from plan_b.world import world
from tests.test_community_skills_exchange import SCENARIO, SkillsSandbox, t
from tests.test_pantry_fixture import PantrySandbox

KIT = "backup_learning_kit"
TERMS = "community_fixture_catalog_v1"
TEXT = "I can bring the registered backup learning kit; it is complete and here."
LATE_KIT = {
    "resource_id": "learning_kit",
    "assume_ready_at": t("10:25").isoformat(),
    "label": "learning kit ready at 10:25",
}
SUBSTITUTIONS = tuple(
    f"Use backup_learning_kit instead of learning_kit for {activity}"
    for activity in ("skills demo", "practice")
)

Json = dict[str, Any]


def offer_args(
    start: str,
    end: str = "12:00",
    *,
    entity: str = KIT,
    capabilities: tuple[str, ...] = ("guided_learning",),
    terms: str = TERMS,
    **extra: Any,
) -> Json:
    return {
        "text": TEXT,
        "entity_id": entity,
        "kind": "resource_offer",
        "offer": {
            "available": {"start": t(start).isoformat(), "end": t(end).isoformat()},
            "capabilities": list(capabilities),
            "terms_ref": terms,
        },
        **extra,
    }


def offer(
    skills: SkillsSandbox | PantrySandbox,
    args: Json,
    key: str = "offer-1",
    *,
    by: str = "participant_kit_steward",
    expected_revision: int | None = None,
) -> ToolEnvelope:
    client: InProcessToolClient = skills.client(by)
    return client.call(
        "submit_observation",
        arguments=args,
        idempotency_key=key,
        expected_revision=expected_revision,
    )


def kit(skills: SkillsSandbox, rid: str = KIT) -> Any:
    return next(r for r in skills.view().resources if r.definition.resource_id == rid)


def state(skills: SkillsSandbox) -> tuple[Any, ...]:
    """Everything an offer could change: revision, observations, the kit's status, holds,
    commitments, money, plan and grants."""
    view = skills.view()
    backup = kit(skills)
    return (
        view.revision,
        len(view.observations),
        (backup.status, backup.status_basis, backup.status_observation_id, backup.reported_eta),
        view.holds,
        view.commitments,
        skills.ledger(),
        view.plan.plan_version,
        tuple((g.grant.grant_id, g.version) for g in view.grants),
    )


def assert_refused(
    skills: SkillsSandbox, env: ToolEnvelope, code: str, before: tuple[Any, ...]
) -> None:
    assert env.status == "rejected" and env.error is not None, env
    assert env.error.code == code, env.error
    assert env.receipt is not None and env.receipt.status == "rejected"
    assert env.receipt.error_code == code
    assert state(skills) == before


def candidate(env: ToolEnvelope, label: str) -> Json:
    assert env.data is not None
    found = [c for c in env.data["candidates"] if c["label"] == label]
    assert len(found) == 1, label
    return found[0]


def check(cand: Json, constraint_id: str) -> str:
    return str(next(c for c in cand["checks"] if c["constraint_id"] == constraint_id)["status"])


@pytest.fixture
def skills(db: Database) -> SkillsSandbox:
    return SkillsSandbox(db)


@pytest.fixture
def variant(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Json]:
    """A scratch copy of the skills fixture: the steward also speaks for a registered easel
    that no option uses, and the backup kit registers a second capability. The test edits
    nothing else; the fixture is written when the sandbox is created."""
    public = tmp_path / "public"
    public.mkdir()
    name = fixtures.PUBLIC_SCENARIOS[SCENARIO]
    data = json.loads((fixtures.PUBLIC_DIR / name).read_text())
    backup = next(r for r in data["resources"] if r["resource_id"] == KIT)
    backup["capabilities"] = ["guided_learning", "kit_storage"]
    easel = {**backup, "resource_id": "spare_easel", "label": "Spare easel"}
    easel["capabilities"] = ["display"]
    easel["terms"] = {**backup["terms"], "status_source_id": None, "queryable_facts": []}
    data["resources"].append(easel)
    steward = next(p for p in data["principals"] if p["principal_id"] == "participant_kit_steward")
    steward["speaks_for_resource_ids"].append("spare_easel")
    grant = next(g for g in data["authority_grants"] if g["grant_id"] == "grant_kit_offer")
    grant["resource_ids"].append("spare_easel")
    (public / name).write_text(json.dumps(data))
    monkeypatch.setattr(fixtures, "PUBLIC_DIR", public)
    yield data


def registry_case(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, status_code: str, domain_status: str
) -> str:
    """A scratch private case in which the kit registry answers for the backup kit."""
    private = tmp_path / "private"
    shutil.copytree(world.PRIVATE_DIR, private)
    case = {
        "artifact": "plan_b.private_case",
        "runtime_version": "1.1.0",
        "case_ref": "offer_registry",
        "scenario_id": SCENARIO,
        "never_expose_to_agent": True,
        "planning_label": "OFFER-REGISTRY (test only)",
        "description": "The kit registry answers for the backup kit from 09:20.",
        "derived_from": None,
        "status_model": [
            {
                "entity_id": KIT,
                "fact": "availability",
                "available_from": t("09:20").isoformat(),
                "outcome": "ok",
                "response": {
                    "status_code": status_code,
                    "domain_status": domain_status,
                    "reported_eta": None,
                    "source_record_id": "kit_registry_record_1",
                    "observed_at": t("09:20").isoformat(),
                    "text": f"Registry: the backup learning kit is {domain_status}.",
                },
            }
        ],
        "world_events": [],
        "actor_scripts": [],
        "outcome_predicates": [],
        "expected_outcome": "goal_complete",
    }
    (private / "offer_registry.json").write_text(json.dumps(case))
    monkeypatch.setattr(world, "PRIVATE_DIR", private)
    world.load_case.cache_clear()
    return "offer_registry"


@pytest.fixture(autouse=True)
def _fresh_cases() -> Iterator[None]:
    yield
    world.load_case.cache_clear()


# ---------------------------------------------------------------------- activation


def test_owner_offer_activates_the_kit_and_nothing_else(skills: SkillsSandbox) -> None:
    skills.advance_to("09:40")
    before = state(skills)
    env = offer(skills, offer_args("09:40"))
    assert env.status == "succeeded" and env.data is not None, env
    assert env.receipt is not None and env.receipt.status == "applied"
    assert env.receipt.revision_after == before[0] + 1
    activation = env.data["activation"]
    assert activation == {
        "resource_id": KIT,
        "activated": True,
        "status": "available",
        "reported_eta": None,
        "approved_for": ["learning_kit"],
    }
    record = env.data["observation"]
    obs = record["observation"]
    assert (obs["kind"], obs["entity_id"], obs["authority_scope"]) == (
        "resource_offer",
        KIT,
        "self_report",
    )
    assert record["channel"] == "participant_session" and obs["text"] == TEXT
    assert obs["valid_window"] == {"start": "2026-11-07T14:40:00Z", "end": "2026-11-07T17:00:00Z"}
    backup = kit(skills)
    assert (backup.status, backup.status_basis) == ("available", "status_observation")
    assert backup.status_observation_id == obs["observation_id"]
    view = skills.view()
    after = state(skills)
    # One revision and one observation; nothing reserved, committed, spent or re-planned.
    assert after[0] == before[0] + 1 and after[1] == before[1] + 1
    assert after[3:] == before[3:] == ((), (), (0, 0), 1, before[7])
    assert view.budget.committed_cents == 0 and view.budget.reserved_cents == 0
    changes = {(c.entity_id, c.field) for c in env.receipt.state_changes}
    assert changes == {(obs["observation_id"], "observation"), (KIT, "status")}


def test_the_activated_kit_is_an_approved_option_for_the_planner(skills: SkillsSandbox) -> None:
    skills.advance_to("09:40")
    before = skills.evaluate(hypotheses=[LATE_KIT])
    for label in SUBSTITUTIONS:
        assert check(candidate(before, label), "resource_status") == "failed", label
    assert offer(skills, offer_args("09:40")).status == "succeeded"
    after = skills.evaluate(hypotheses=[LATE_KIT])
    for label in SUBSTITUTIONS:
        cand = candidate(after, label)
        assert check(cand, "resource_status") == "passed", label
        assert check(cand, "substitute_compatibility") == "passed", label
        # Usable, but the offer reserved nothing: the coordinator must still hold the kit
        # and the organizer must still authorize the booking.
        assert [h["resource_id"] for h in cand["required_holds"]] == [KIT]
        assert all(h["bound_hold_id"] is None for h in cand["required_holds"])
        assert not cand["applicable_now"]
    hold = skills.agent.call(
        "hold_resource",
        arguments={
            "resource_id": KIT,
            "activity_id": "skills_demo",
            "window": {"start": t("10:10").isoformat(), "end": t("10:40").isoformat()},
        },
        idempotency_key="kit-hold",
        expected_revision=skills.revision(),
    )
    assert hold.status == "succeeded" and hold.receipt is not None
    # The reservation is the coordinator's hold, under its own grant, not the offer's.
    assert hold.receipt.actor_id == "agent_demo" and skills.ledger() == (0, 4000)


def test_an_offer_for_later_makes_the_kit_expected_until_confirmed(skills: SkillsSandbox) -> None:
    first = offer(skills, offer_args("09:30"))  # the clock is 09:20
    assert first.status == "succeeded" and first.data is not None
    assert first.data["activation"]["status"] == "expected"
    backup = kit(skills)
    assert (backup.status, backup.reported_eta) == ("expected", t("09:30"))
    later = skills.evaluate(hypotheses=[LATE_KIT])
    # The kit expected at 09:30 is before the demonstration starts: the arrival check holds.
    assert check(candidate(later, SUBSTITUTIONS[0]), "arrival_assumptions") == "passed"
    skills.advance_to("09:35")
    second = offer(skills, offer_args("09:35"), key="offer-2")
    assert second.status == "succeeded" and second.data is not None
    first_id = first.data["observation"]["observation"]["observation_id"]
    assert second.data["observation"]["observation"]["supersedes"] == [first_id]
    backup = kit(skills)
    assert (backup.status, backup.reported_eta) == ("available", None)


def test_a_retry_with_the_same_key_activates_once(skills: SkillsSandbox) -> None:
    skills.advance_to("09:40")
    observations = len(skills.view().observations)
    first = offer(skills, offer_args("09:40"))
    revision = skills.revision()
    again = offer(skills, offer_args("09:40"))
    assert again.replayed_receipt and again.receipt is not None and first.receipt is not None
    assert again.receipt.receipt_id == first.receipt.receipt_id
    assert skills.revision() == revision
    assert len(skills.view().observations) == observations + 1


def test_a_text_offer_without_the_fields_activates_nothing(skills: SkillsSandbox) -> None:
    before = state(skills)
    env = offer(skills, {"text": TEXT, "entity_id": KIT, "kind": "resource_offer"})
    assert env.status == "succeeded" and env.data is not None
    assert "activation" not in env.data
    after = state(skills)
    assert after[2] == before[2] == ("unknown", "catalog", None, None)
    assert after[3:] == before[3:]


def test_a_status_record_is_never_overridden(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    skills = SkillsSandbox(db, registry_case(tmp_path, monkeypatch, "available", "available"))
    query = skills.agent.call("query_status", arguments={"entity_id": KIT, "fact": "availability"})
    assert query.status == "succeeded"
    record_id = kit(skills).status_observation_id
    skills.advance_to("09:25")
    env = offer(skills, offer_args("09:45"))
    assert env.status == "succeeded" and env.data is not None
    assert env.data["activation"]["activated"] is False
    backup = kit(skills)
    assert (backup.status, backup.status_observation_id) == ("available", record_id)


# ---------------------------------------------------------------------- refusals


def test_refused_unless_the_caller_speaks_for_the_resource(skills: SkillsSandbox) -> None:
    skills.advance_to("09:40")
    before = state(skills)
    for who, key in (("participant_peer_lead", "peer"), ("organizer_demo", "org")):
        assert_refused(
            skills, offer(skills, offer_args("09:40"), key, by=who), "SCOPE_VIOLATION", before
        )


def test_the_coordinator_cannot_offer(skills: SkillsSandbox) -> None:
    skills.advance_to("09:40")
    before = state(skills)
    env = offer(skills, offer_args("09:40"), by="agent_demo")
    assert env.status == "rejected" and env.error is not None
    assert env.error.code == "GRANT_REQUIRED" and env.receipt is None
    assert state(skills) == before


def test_refused_for_a_persons_role(skills: SkillsSandbox) -> None:
    skills.advance_to("09:40")
    before = state(skills)
    env = offer(
        skills,
        offer_args("09:40", entity="peer_lead", capabilities=("peer_facilitation",)),
        by="participant_peer_lead",
    )
    assert_refused(skills, env, "UNSUPPORTED_ACTION", before)


def test_refused_for_consumable_stock(db: Database) -> None:
    pantry = PantrySandbox(db)
    before = pantry.view()
    pool = next(r for r in before.resources if r.definition.resource_id == "partner_stock")
    window = pool.definition.window
    env = pantry.steward.call(
        "submit_observation",
        arguments={
            "text": "We can offer 40 more kits from the partner pool.",
            "entity_id": "partner_stock",
            "kind": "resource_offer",
            "offer": {
                "available": {"start": window.start.isoformat(), "end": window.end.isoformat()},
                "capabilities": list(pool.definition.capabilities) or ["food_kits"],
                "terms_ref": pool.definition.terms.terms_source_ref,
            },
        },
        idempotency_key="stock-offer",
    )
    assert env.status == "rejected" and env.error is not None
    assert env.error.code == "UNSUPPORTED_ACTION" and "cannot add stock" in env.error.message
    after = pantry.view()
    assert after.revision == before.revision and after.stock == before.stock
    assert after.holds == before.holds == ()


def test_refused_for_a_resource_that_is_no_approved_option(db: Database, variant: Json) -> None:
    skills = SkillsSandbox(db)
    skills.advance_to("09:40")
    before = state(skills)
    env = offer(skills, offer_args("09:40", entity="spare_easel", capabilities=("display",)))
    assert_refused(skills, env, "UNSUPPORTED_ACTION", before)
    assert kit(skills, "spare_easel").status == "unknown"


def test_refused_for_a_capability_the_resource_does_not_register(skills: SkillsSandbox) -> None:
    skills.advance_to("09:40")
    before = state(skills)
    env = offer(skills, offer_args("09:40", capabilities=("guided_learning", "projection")))
    assert_refused(skills, env, "CONSTRAINT_VIOLATION", before)


def test_refused_when_the_offer_omits_a_needed_capability(db: Database, variant: Json) -> None:
    skills = SkillsSandbox(db)
    skills.advance_to("09:40")
    before = state(skills)
    env = offer(skills, offer_args("09:40", capabilities=("kit_storage",)))
    assert_refused(skills, env, "CONSTRAINT_VIOLATION", before)
    assert env.error is not None and env.error.details["needed"] == {
        "learning_kit": ["guided_learning"]
    }


@pytest.mark.parametrize(
    ("clock", "start", "end", "code"),
    [
        ("09:20", "09:20", "12:00", "CONSTRAINT_VIOLATION"),  # before the registered window
        ("09:40", "09:40", "11:00", "CONSTRAINT_VIOLATION"),  # short of its end
        ("09:50", "09:30", "09:45", "INVALID_REQUEST"),  # already over
    ],
)
def test_refused_for_an_interval_the_planner_cannot_use(
    skills: SkillsSandbox, clock: str, start: str, end: str, code: str
) -> None:
    skills.advance_to(clock)
    before = state(skills)
    assert_refused(skills, offer(skills, offer_args(start, end)), code, before)


def test_refused_when_a_status_record_reports_it_unavailable(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    skills = SkillsSandbox(
        db, registry_case(tmp_path, monkeypatch, "booked_elsewhere", "unavailable")
    )
    query = skills.agent.call("query_status", arguments={"entity_id": KIT, "fact": "availability"})
    assert query.status == "succeeded" and kit(skills).status == "unavailable"
    skills.advance_to("09:40")
    before = state(skills)
    assert_refused(skills, offer(skills, offer_args("09:40")), "RESOURCE_UNAVAILABLE", before)


def test_refused_without_the_registered_terms(skills: SkillsSandbox) -> None:
    skills.advance_to("09:40")
    before = state(skills)
    env = offer(skills, offer_args("09:40", terms="free loan, no booking needed"))
    assert_refused(skills, env, "CONSTRAINT_VIOLATION", before)


def test_refused_on_a_stale_revision(skills: SkillsSandbox) -> None:
    skills.advance_to("09:40")
    before = state(skills)
    env = offer(skills, offer_args("09:40"), expected_revision=before[0] - 1)
    assert_refused(skills, env, "REVISION_CONFLICT", before)


def test_refused_for_an_unknown_resource(skills: SkillsSandbox) -> None:
    skills.advance_to("09:40")
    before = state(skills)
    assert_refused(
        skills, offer(skills, offer_args("09:40", entity="mystery_kit")), "UNKNOWN_ENTITY", before
    )


@pytest.mark.parametrize(
    "change",
    [
        {"kind": "notice"},  # a structured offer is a resource_offer
        {"entity_id": None},  # and names the resource
        {"observed_at": t("09:40").isoformat()},  # observed when submitted
        {
            "offer": {
                "available": {"start": "x", "end": "y"},
                "capabilities": ["a"],
                "terms_ref": "t",
            }
        },
        {"offer": {**offer_args("09:40")["offer"], "capabilities": []}},
        {"offer": {**offer_args("09:40")["offer"], "terms_ref": ""}},
        {
            "offer": {
                **offer_args("09:40")["offer"],
                "available": {"start": "2026-11-07T14:40:30Z", "end": "2026-11-07T17:00:00Z"},
            }
        },
    ],
)
def test_malformed_offers_are_invalid_requests(skills: SkillsSandbox, change: Json) -> None:
    skills.advance_to("09:40")
    before = state(skills)
    args = {k: v for k, v in {**offer_args("09:40"), **change}.items() if v is not None}
    env = offer(skills, args)
    assert env.status == "rejected" and env.error is not None
    assert env.error.code == "INVALID_REQUEST" and env.receipt is None
    assert state(skills) == before
    with skills.db.read() as conn:
        assert repo.receipts(conn, skills.episode_id) == ()
